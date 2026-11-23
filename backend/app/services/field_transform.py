"""字段转换器领域服务：对消息字段执行类型转换、脱敏、编码和单位统一，管理转换规则链。

数据链路位置：数据变换层，在解析完成后对字段执行业务语义转换，输出标准化数据字段。

规则影响明细扩展：
- 以 Schema 版本 + 源字段 + 目标字段定位规则，用实际样本区分「生效中」规则与「候选」规则；
- 同版同目标的竞争规则给出竞争来源，并标出一笔样本实际采用哪条规则；
- 工程师编辑生效规则时沉淀新版本，旧版本保留为「已失效」并记录失效原因，报表旧引用可据此重跑核对。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.store import store

# 影响明细三张内部表的表名（在 store 中注册但不作为业务模块对外暴露）。
SAMPLE_TABLE = "transform_samples"
REF_TABLE = "transform_refs"
PREVIEW_TABLE = "transform_previews"


class FieldTransformService(BaseModuleService):
    MODULE = "field_transform"
    ENTITY = "转换规则"
    OPERATION_TERM = "转换"
    LIST_FIELDS = ["规则名称", "源字段", "目标字段", "转换函数", "错误处理"]
    REQUIRED_FIELDS = ["规则名称", "源字段", "目标字段"]
    STATUS_ORDER = ["草稿", "已启用", "已停用"]
    ACTION_RULES = {"启用规则": "已启用", "停用规则": "已停用"}
    NEGATIVE_ACTIONS = ["停用规则"]

    # ---- 通用登记：补齐规则版本相关扩展字段 ----

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        entry, missing = super().create_entry(values)
        if missing:
            return entry, missing
        assert entry is not None
        entry.update({
            "Schema名称": str(values.get("Schema名称") or ""),
            "Schema版本": str(values.get("Schema版本") or ""),
            "写入来源": str(values.get("写入来源") or ""),
            "规则键": str(values.get("规则键") or f"rule-{entry['id']}"),
            "规则版本": int(values.get("规则版本") or 1),
            "版本状态": "当前",
            "失效原因": None,
        })
        return entry, []

    # ---- 业务扩展：字段转换与脱敏 ----

    def execute_rule(self, rule: dict[str, Any], source_value: Any) -> dict[str, Any]:
        """按规则快照执行一次转换，不依赖规则当前状态（显式重跑也要能算出结果）。"""
        fn_name = str(rule.get("转换函数", ""))
        error_policy = rule.get("错误处理", "忽略")
        try:
            value = str(source_value)
            if "金额转分" in fn_name or "round*100" in fn_name:
                result = int(round(float(value) * 100))
            elif "int" in fn_name or "取整" in fn_name:
                result = int(float(value))
            elif "float" in fn_name:
                result = float(value)
            elif "mask" in fn_name or "脱敏" in fn_name:
                result = value[:3] + "***" + value[-4:] if len(value) > 7 else "***"
            elif "upper" in fn_name:
                result = value.upper()
            elif "lower" in fn_name:
                result = value.lower()
            elif "strip" in fn_name:
                result = value.strip()
            elif "datetime" in fn_name or "日期" in fn_name:
                result = datetime.now(timezone.utc).isoformat()
            else:
                result = value
            return {"ok": True, "message": "转换成功", "result": result}
        except (ValueError, TypeError) as exc:
            if error_policy == "中断":
                return {"ok": False, "message": f"转换失败: {exc}", "result": None}
            return {"ok": False, "message": f"转换异常已忽略: {exc}", "result": source_value}

    def apply_transform(self, entry_id: int, source_value: Any) -> dict[str, Any]:
        """应用转换规则到源字段值（仅当前生效版本可用）。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已启用" or entry.get("版本状态") == "已失效":
            return {"ok": False, "message": "规则不可用", "result": source_value}
        return self.execute_rule(entry, source_value)

    def validate_transform_chain(self, source_field: str) -> dict[str, Any]:
        """校验同一源字段的转换规则链是否存在冲突。"""
        rules = store.rows(self.MODULE)
        chain = [r for r in rules if r.get("源字段", "") == source_field and r.get("status") == "已启用"]
        conflicts = []
        targets = [r.get("目标字段", "") for r in chain]
        if len(set(targets)) < len(targets):
            conflicts.append("存在多个规则转换到相同目标字段")
        return {"source": source_field, "rules": len(chain), "conflicts": conflicts}

    def route_transformed_to_sink(self, entry_id: int, result: Any) -> str | None:
        """转换后的数据路由到数据落地配置。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None
        target_field = entry.get("目标字段", "")
        sinks = store.rows("data_sink")
        for sink in sinks:
            if sink.get("status") == "已启用" and target_field in str(sink.get("配置名称", "")):
                return sink.get("配置名称", "")
        return None

    def handle_transform_error(self, entry_id: int, source_value: Any, error: str) -> None:
        """处理转换错误：按规则配置的错误处理策略。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return
        policy = entry.get("错误处理", "忽略")
        if policy == "隔离":
            now = datetime.now(timezone.utc).isoformat()
            isolation_rows = store.rows("failure_isolation")
            fid = max((int(r.get("id", 0)) for r in isolation_rows), default=0) + 1
            isolation_rows.append({
                "id": fid, "失败消息ID": f"tf-err-{entry_id}",
                "失败原因": f"转换失败: {error}, 源值={source_value}",
                "原始Topic": entry.get("规则名称", ""),
                "隔离时间": now, "重试次数": "0",
                "status": "待处理", "pending": True, "abnormal": False,
            })

    # ---- 规则影响明细：查询、筛选、竞争识别 ----

    @staticmethod
    def _binding_state(rule: dict[str, Any]) -> str:
        if rule.get("版本状态") == "已失效":
            return "已失效"
        status = rule.get("status")
        if status == "已启用":
            return "生效中"
        if status == "已停用":
            return "已停用"
        return "候选"

    @staticmethod
    def _same_column(rule: dict[str, Any], schema_name: str, version: str, target: str) -> bool:
        return (
            rule.get("Schema名称") == schema_name
            and rule.get("Schema版本") == version
            and rule.get("目标字段") == target
        )

    def _find_sample(self, rule: dict[str, Any]) -> dict[str, Any] | None:
        """按 Schema 版本 + 源字段（必要时叠加写入来源）找一笔实际样本。"""
        for sample in store.rows(SAMPLE_TABLE):
            if (
                sample.get("Schema名称") == rule.get("Schema名称")
                and sample.get("Schema版本") == rule.get("Schema版本")
                and sample.get("源字段") == rule.get("源字段")
            ):
                source = rule.get("写入来源")
                if not source or sample.get("写入来源") == source:
                    return sample
        return None

    def _competition(self, rule: dict[str, Any]) -> dict[str, Any]:
        """同版同目标字段的竞争规则组，并标出样本实际采用方。"""
        schema_name, version, target = (
            rule.get("Schema名称", ""), rule.get("Schema版本", ""), rule.get("目标字段", ""),
        )
        rivals = [
            row for row in store.rows(self.MODULE)
            if row.get("版本状态") != "已失效"
            and self._same_column(row, schema_name, version, target)
        ]
        winner_id: int | None = None
        # 只在已启用规则里选采用方；优先有实际样本的那条，再按规则ID稳定排序。
        enabled = sorted(
            (row for row in rivals if row.get("status") == "已启用"),
            key=lambda row: int(row.get("id", 0)),
        )
        with_sample = [row for row in enabled if self._find_sample(row) is not None]
        if with_sample:
            winner_id = int(with_sample[0]["id"])
        elif enabled:
            winner_id = int(enabled[0]["id"])
        return {
            "competing": [
                {
                    "rule_id": row.get("id"),
                    "规则名称": row.get("规则名称"),
                    "源字段": row.get("源字段"),
                    "写入来源": row.get("写入来源"),
                    "status": row.get("status"),
                    "规则版本": row.get("规则版本"),
                }
                for row in sorted(rivals, key=lambda row: int(row.get("id", 0)))
            ],
            "winner_rule_id": winner_id,
            "adopted_by_sample": winner_id == int(rule.get("id", 0)),
            "has_competition": len(rivals) > 1,
        }

    def _reference_state(self, rule: dict[str, Any], ref: dict[str, Any]) -> str:
        """报表引用与规则行的关系：匹配 / 版本已失效 / 新版本待绑定 / 规则已替换。"""
        if int(ref.get("规则ID", 0)) == int(rule.get("id", 0)):
            return "版本已失效" if rule.get("版本状态") == "已失效" else "匹配"
        if ref.get("规则键") == rule.get("规则键"):
            # 同一规则键的新版本：引用还指向旧版本，当前版本待报表重新绑定。
            return "版本已失效" if rule.get("版本状态") == "已失效" else "新版本待绑定"
        return "规则已替换"

    def _reference_view(self, rule: dict[str, Any]) -> dict[str, Any] | None:
        """目标列上的报表规则引用，以及它与当前规则行的匹配/失效关系。"""
        ref = next((
            row for row in store.rows(REF_TABLE)
            if row.get("Schema名称") == rule.get("Schema名称")
            and row.get("Schema版本") == rule.get("Schema版本")
            and row.get("目标字段") == rule.get("目标字段")
        ), None)
        if ref is None:
            return None
        return {
            "ref_id": ref.get("id"),
            "引用编号": ref.get("引用编号"),
            "报表名称": ref.get("报表名称"),
            "引用规则版本": ref.get("规则版本"),
            "reference_state": self._reference_state(rule, ref),
        }

    def _current_binding(self, rule: dict[str, Any]) -> dict[str, Any] | None:
        """报表引用当前绑定到的规则版本（用于和旧引用对照）。"""
        ref = next((
            row for row in store.rows(REF_TABLE)
            if row.get("Schema名称") == rule.get("Schema名称")
            and row.get("Schema版本") == rule.get("Schema版本")
            and row.get("目标字段") == rule.get("目标字段")
        ), None)
        if ref is None:
            return None
        current = next((
            row for row in store.rows(self.MODULE)
            if row.get("规则键") == ref.get("规则键") and row.get("版本状态") == "当前"
        ), None)
        if current is None:
            return None
        return {
            "rule_id": current.get("id"),
            "规则名称": current.get("规则名称"),
            "规则版本": current.get("规则版本"),
            "status": current.get("status"),
        }

    def _impact_row(self, rule: dict[str, Any]) -> dict[str, Any]:
        sample = self._find_sample(rule)
        return {
            "rule_id": rule.get("id"),
            "规则名称": rule.get("规则名称"),
            "源字段": rule.get("源字段"),
            "目标字段": rule.get("目标字段"),
            "转换函数": rule.get("转换函数"),
            "错误处理": rule.get("错误处理"),
            "status": rule.get("status"),
            "Schema名称": rule.get("Schema名称"),
            "Schema版本": rule.get("Schema版本"),
            "写入来源": rule.get("写入来源"),
            "规则键": rule.get("规则键"),
            "规则版本": rule.get("规则版本"),
            "版本状态": rule.get("版本状态"),
            "失效原因": rule.get("失效原因"),
            "绑定状态": self._binding_state(rule),
            "has_sample": sample is not None,
            "样本": None if sample is None else {
                "sample_id": sample.get("id"),
                "源字段": sample.get("源字段"),
                "样本原始值": sample.get("样本原始值"),
                "写入来源": sample.get("写入来源"),
                "采集批次": sample.get("采集批次"),
                "消息ID": sample.get("消息ID"),
            },
            "竞争组": self._competition(rule),
            "reference": self._reference_view(rule),
            "当前绑定": self._current_binding(rule),
        }

    def rule_impact(
        self,
        *,
        schema_name: str | None = None,
        schema_version: str | None = None,
        source_field: str | None = None,
        target_field: str | None = None,
        binding: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """规则影响明细查询：按 Schema 版本、来源字段、目标字段定位并筛选。"""
        rows = store.rows(self.MODULE)
        if schema_name:
            rows = [r for r in rows if r.get("Schema名称") == schema_name]
        if schema_version:
            rows = [r for r in rows if r.get("Schema版本") == schema_version]
        if source_field:
            rows = [r for r in rows if source_field.casefold() in str(r.get("源字段", "")).casefold()]
        if target_field:
            rows = [r for r in rows if target_field.casefold() in str(r.get("目标字段", "")).casefold()]
        if binding:
            rows = [r for r in rows if self._binding_state(r) == binding]
        if keyword:
            rows = [
                r for r in rows
                if keyword.casefold() in str(r.get("规则名称", "")).casefold()
                or keyword.casefold() in str(r.get("写入来源", "")).casefold()
            ]
        rows = sorted(rows, key=lambda r: int(r.get("id", 0)))
        items = [self._impact_row(rule) for rule in rows]
        total = len(items)
        start = (page - 1) * size
        return {"items": items[start:start + size], "total": total, "page": page, "size": size}

    # ---- 规则编辑：生效规则被改后沉淀新版本，旧版本失效留痕 ----

    def edit_rule(self, rule_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        old = store.find(self.MODULE, rule_id)
        if old is None:
            return None, f"规则 {rule_id} 不存在或已归档"
        rows = store.rows(self.MODULE)
        new_id = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        same_key = [r for r in rows if r.get("规则键") == old.get("规则键")]
        new_version = max((int(r.get("规则版本", 1)) for r in same_key), default=1) + 1
        new_rule = dict(old)
        for field in self.LIST_FIELDS:
            if field in values and str(values.get(field) or "").strip():
                new_rule[field] = values[field]
        new_rule.update({
            "id": new_id,
            "规则版本": new_version,
            "版本状态": "当前",
            "失效原因": None,
        })
        was_active = old.get("status") == "已启用"
        if was_active:
            # 生效规则被编辑：新版本直接接棒生效，旧版本停用并标记失效，保留失效原因供旧引用核对。
            new_rule["status"] = "已启用"
            new_rule["pending"] = True
            new_rule["abnormal"] = False
            old["版本状态"] = "已失效"
            old["status"] = "已停用"
            old["pending"] = False
            reason = (
                f"规则已被工程师编辑，新版本 v{new_version}（规则ID {new_id}）接棒生效，"
                f"本版本停留在 v{old.get('规则版本')}，原报表引用需复核重跑"
            )
            old["失效原因"] = reason
            message = f"生效规则已编辑：新版本 v{new_version} 生效，旧版本 v{old.get('规则版本')} 已失效"
        else:
            new_rule["status"] = "草稿"
            new_rule["pending"] = True
            new_rule["abnormal"] = False
            message = f"规则已另存为新版本 v{new_version}（草稿候选），原规则未受影响"
        rows.append(new_rule)
        return new_rule, message

    # ---- 按引用/样本重跑：旧引用重跑时给出版本失效依据 ----

    def rerun_rule(
        self,
        rule_id: int,
        *,
        ref_id: int | None = None,
        sample_id: int | None = None,
        sample_value: Any = None,
    ) -> dict[str, Any]:
        rule = store.find(self.MODULE, rule_id)
        if rule is None:
            return {"ok": False, "message": f"规则 {rule_id} 不存在或已归档"}

        sample = None
        if sample_id is not None:
            sample = store.find(SAMPLE_TABLE, sample_id)
            if sample is not None and (
                sample.get("Schema名称") != rule.get("Schema名称")
                or sample.get("源字段") != rule.get("源字段")
            ):
                sample = None
        if sample is None:
            sample = self._find_sample(rule)
        raw_value = sample_value if sample_value is not None else (
            sample.get("样本原始值") if sample is not None else None
        )

        ref = store.find(REF_TABLE, ref_id) if ref_id is not None else None
        reference_state = None
        stale_reason: str | None = None
        if ref is not None:
            reference_state = self._reference_state(rule, ref)
        if rule.get("版本状态") == "已失效":
            stale_reason = rule.get("失效原因") or "规则版本已失效"

        execution = self.execute_rule(rule, raw_value)
        preview = {
            "id": max((int(r.get("id", 0)) for r in store.rows(PREVIEW_TABLE)), default=0) + 1,
            "预览时间": datetime.now(timezone.utc).isoformat(),
            "rule_id": rule_id,
            "规则名称": rule.get("规则名称"),
            "规则键": rule.get("规则键"),
            "规则版本": rule.get("规则版本"),
            "版本状态": rule.get("版本状态"),
            "转换函数": rule.get("转换函数"),
            "Schema名称": rule.get("Schema名称"),
            "Schema版本": rule.get("Schema版本"),
            "源字段": rule.get("源字段"),
            "目标字段": rule.get("目标字段"),
            "ref_id": ref_id,
            "引用编号": ref.get("引用编号") if ref else None,
            "reference_state": reference_state,
            "stale_reason": stale_reason,
            "sample_id": sample.get("id") if sample else None,
            "样本原始值": raw_value,
            "采集批次": sample.get("采集批次") if sample else None,
            "转换结果": execution.get("result"),
            "ok": execution.get("ok"),
            "message": execution.get("message"),
        }
        store.rows(PREVIEW_TABLE).append(preview)
        return {
            "ok": True,
            "message": "重跑完成，结果与版本依据已留痕",
            "preview": preview,
            "reference_state": reference_state,
            "stale_reason": stale_reason,
            "当前绑定": self._current_binding(rule),
        }

    def preview_history(
        self, *, rule_id: int | None = None, ref_id: int | None = None, page: int = 1, size: int = 20,
    ) -> dict[str, Any]:
        """预览/重跑留痕，供发布前和事后独立核对。"""
        rows = list(store.rows(PREVIEW_TABLE))
        if rule_id is not None:
            rows = [r for r in rows if int(r.get("rule_id", 0)) == rule_id]
        if ref_id is not None:
            rows = [r for r in rows if r.get("ref_id") == ref_id]
        rows = sorted(rows, key=lambda r: int(r.get("id", 0)), reverse=True)
        total = len(rows)
        start = (page - 1) * size
        return {"items": rows[start:start + size], "total": total, "page": page, "size": size}
