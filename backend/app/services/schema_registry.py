"""Schema注册中心领域服务：注册和管理消息数据的Schema定义和版本兼容性。

数据链路位置：元数据管理层，为消息解析和字段转换提供Schema版本定义，确保数据格式向下兼容。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class SchemaRegistryService(BaseModuleService):
    MODULE = "schema_registry"
    ENTITY = "Schema版本"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["Schema名称", "版本号", "字段定义", "兼容模式", "注册时间"]
    REQUIRED_FIELDS = ["Schema名称", "版本号", "字段定义"]
    STATUS_ORDER = ["草稿", "已注册", "已废弃"]
    ACTION_RULES = {"注册版本": "已注册", "废弃版本": "已废弃"}
    NEGATIVE_ACTIONS = []

    # ---- 业务扩展：Schema版本管理与兼容性检查 ----

    def check_compatibility(self, entry_id: int, new_fields: list[str]) -> dict[str, Any]:
        """检查新字段定义与已注册Schema版本的兼容性。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已注册":
            return {"compatible": False, "message": "Schema未注册"}
        existing = str(entry.get("字段定义", "")).split(",")
        existing = [f.strip() for f in existing if f.strip()]
        mode = entry.get("兼容模式", "向前兼容")
        added = set(new_fields) - set(existing)
        removed = set(existing) - set(new_fields)
        if mode == "向前兼容" and removed:
            return {"compatible": False, "message": "向前兼容不允许删除已有字段", "removed": list(removed)}
        if mode == "向后兼容" and added:
            return {"compatible": False, "message": "向后兼容不允许新增必填字段", "added": list(added)}
        return {"compatible": True, "message": "版本兼容", "added": list(added), "removed": list(removed)}

    def register_new_version(self, schema_name: str, version: str, fields: str, mode: str) -> dict[str, Any]:
        """注册新的Schema版本。"""
        existing = store.rows(self.MODULE)
        same_version = [e for e in existing
                        if e.get("Schema名称") == schema_name and e.get("版本号") == version]
        if same_version:
            return {"ok": False, "message": f"版本 {version} 已存在"}
        sid = max((int(r.get("id", 0)) for r in existing), default=0) + 1
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "id": sid, "Schema名称": schema_name, "版本号": version,
            "字段定义": fields, "兼容模式": mode, "注册时间": now,
            "status": "已注册", "pending": True, "abnormal": False,
        }
        existing.append(entry)
        return {"ok": True, "schema_id": sid, "version": version}

    def validate_parser_binding(self, schema_name: str) -> dict[str, Any]:
        """校验Schema与消息解析器模板的绑定关系。"""
        parsers = store.rows("message_parser")
        bound = [p.get("模板名称", "") for p in parsers if schema_name in str(p.get("模板名称", ""))]
        return {"schema_name": schema_name, "bound_parsers": bound, "bound": len(bound) > 0}

    def link_to_transform_rules(self, schema_name: str) -> list[str]:
        """查找与Schema字段关联的转换规则。"""
        entry = store.find(self.MODULE, min((int(r.get("id", 0)) for r in store.rows(self.MODULE)
                                            if r.get("Schema名称") == schema_name), default=0))
        if entry is None:
            return []
        fields = str(entry.get("字段定义", "")).split(",")
        fields = [f.strip() for f in fields if f.strip()]
        transform_rules = store.rows("field_transform")
        linked = []
        for rule in transform_rules:
            if rule.get("status") == "已启用" and rule.get("源字段", "") in fields:
                linked.append(rule.get("规则名称", ""))
        return linked

    # ---- 影响清单：发布前从 Schema 侧选中实际关联的目标列 ----

    def impact_targets(
        self,
        *,
        schema_name: str | None = None,
        schema_version: str | None = None,
        target_field: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """按 Schema 版本汇总实际关联的目标列，每列附上规则引用和样本采用方。"""
        # 延迟导入避免与字段转换器服务在模块加载期产生循环依赖。
        from app.services import service_for

        impact = service_for("field_transform").rule_impact(
            schema_name=schema_name,
            schema_version=schema_version,
            target_field=target_field,
            page=1,
            size=10_000,
        )
        grouped: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
        for row in impact["items"]:
            # Schema 侧清单只收实际绑定到 Schema 版本的目标列，未填 Schema 的规则不进影响清单。
            if not row["Schema名称"] or not row["Schema版本"]:
                continue
            key = (row["Schema名称"], row["Schema版本"], row["目标字段"])
            column = grouped.setdefault(key, {
                "Schema名称": row["Schema名称"],
                "Schema版本": row["Schema版本"],
                "目标字段": row["目标字段"],
                "规则数": 0,
                "生效规则数": 0,
                "候选规则数": 0,
                "失效规则数": 0,
                "竞争来源": [],
                "样本采用规则ID": None,
                "reference": row.get("reference"),
                "当前绑定": row.get("当前绑定"),
                "关联规则": [],
            })
            column["规则数"] += 1
            state = row["绑定状态"]
            if state == "生效中":
                column["生效规则数"] += 1
            elif state == "候选":
                column["候选规则数"] += 1
            elif state == "已失效":
                column["失效规则数"] += 1
            if row["竞争组"]["has_competition"]:
                for rival in row["竞争组"]["competing"]:
                    source = rival["写入来源"]
                    if source and source not in column["竞争来源"]:
                        column["竞争来源"].append(source)
            if column["样本采用规则ID"] is None and row["竞争组"]["adopted_by_sample"]:
                column["样本采用规则ID"] = row["rule_id"]
            column["关联规则"].append({
                "rule_id": row["rule_id"],
                "规则名称": row["规则名称"],
                "源字段": row["源字段"],
                "写入来源": row["写入来源"],
                "规则版本": row["规则版本"],
                "绑定状态": state,
            })
        items = sorted(
            grouped.values(),
            key=lambda item: (str(item["Schema名称"]), str(item["Schema版本"]), str(item["目标字段"])),
        )
        total = len(items)
        start = (page - 1) * size
        return {"items": items[start:start + size], "total": total, "page": page, "size": size}

    def rerun_target_column(
        self,
        *,
        schema_name: str,
        schema_version: str,
        target_field: str,
        ref_id: int | None = None,
    ) -> dict[str, Any]:
        """发布前拿报表中的规则引用重跑指定目标列（草稿 Schema 版本也允许预检）。"""
        from app.services import service_for
        from app.services.field_transform import REF_TABLE

        service = service_for("field_transform")
        ref = next((
            row for row in store.rows(REF_TABLE)
            if row.get("Schema名称") == schema_name
            and row.get("Schema版本") == schema_version
            and row.get("目标字段") == target_field
            and (ref_id is None or int(row.get("id", 0)) == ref_id)
        ), None)
        if ref is None:
            # 该目标列没有报表引用时，退化为当前生效规则，保证发布前仍可预检。
            active = next((
                row for row in store.rows("field_transform")
                if row.get("Schema名称") == schema_name
                and row.get("Schema版本") == schema_version
                and row.get("目标字段") == target_field
                and row.get("status") == "已启用"
                and row.get("版本状态") == "当前"
            ), None)
            if active is None:
                return {"ok": False, "message": "目标列缺少报表规则引用，且没有当前生效规则可重跑"}
            return service.rerun_rule(int(active["id"]))
        return service.rerun_rule(int(ref["规则ID"]), ref_id=int(ref["id"]))