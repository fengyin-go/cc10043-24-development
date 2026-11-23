"""规则影响明细路由：字段转换器的影响查询、版本编辑、按引用重跑，以及 Schema 侧的目标列预检。

这些路径都带固定二级前缀，需在通用资源路由 resource 之前注册，避免被 /api/{module} 抢先匹配。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import service_for
from app.services.field_transform import FieldTransformService
from app.services.schema_registry import SchemaRegistryService

router = APIRouter(prefix="/api", tags=["规则影响明细"])


class RuleEditPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class RerunPayload(BaseModel):
    ref_id: int | None = None
    sample_id: int | None = None
    sample_value: Any = None


class ColumnRerunPayload(BaseModel):
    schema_name: str
    schema_version: str
    target_field: str
    ref_id: int | None = None


@router.get("/field_transform/impact")
def rule_impact(
    schema_name: str | None = None,
    schema_version: str | None = None,
    source_field: str | None = None,
    target_field: str | None = None,
    binding: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """规则影响明细：按 Schema 版本、来源字段、目标字段定位规则并筛选绑定状态。"""
    service: FieldTransformService = service_for("field_transform")  # type: ignore[assignment]
    return service.rule_impact(
        schema_name=schema_name,
        schema_version=schema_version,
        source_field=source_field,
        target_field=target_field,
        binding=binding,
        keyword=keyword,
        page=page,
        size=size,
    )


@router.post("/field_transform/rules/{rule_id}/edit")
def edit_rule(rule_id: int, payload: RuleEditPayload) -> dict[str, Any]:
    """编辑生效规则：沉淀新版本，旧版本标记失效并记录原因。"""
    service: FieldTransformService = service_for("field_transform")  # type: ignore[assignment]
    entry, message = service.edit_rule(rule_id, payload.values)
    if entry is None:
        raise HTTPException(status_code=404, detail=message)
    return {"ok": True, "message": message, "entry": entry}


@router.post("/field_transform/rules/{rule_id}/rerun")
def rerun_rule(rule_id: int, payload: RerunPayload) -> dict[str, Any]:
    """从影响查询行重跑规则；带旧引用时返回引用状态与版本失效依据。"""
    service: FieldTransformService = service_for("field_transform")  # type: ignore[assignment]
    result = service.rerun_rule(
        rule_id,
        ref_id=payload.ref_id,
        sample_id=payload.sample_id,
        sample_value=payload.sample_value,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("message", "重跑失败"))
    return result


@router.get("/field_transform/previews")
def preview_history(
    rule_id: int | None = None,
    ref_id: int | None = None,
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """预览/重跑留痕：核对每一笔样本的原版本预览依据。"""
    service: FieldTransformService = service_for("field_transform")  # type: ignore[assignment]
    return service.preview_history(rule_id=rule_id, ref_id=ref_id, page=page, size=size)


@router.get("/schema_registry/impact")
def schema_impact_targets(
    schema_name: str | None = None,
    schema_version: str | None = None,
    target_field: str | None = None,
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """Schema 注册中心侧的影响清单：列出实际关联的目标列及规则引用。"""
    service: SchemaRegistryService = service_for("schema_registry")  # type: ignore[assignment]
    return service.impact_targets(
        schema_name=schema_name,
        schema_version=schema_version,
        target_field=target_field,
        page=page,
        size=size,
    )


@router.post("/schema_registry/rerun-column")
def rerun_target_column(payload: ColumnRerunPayload) -> dict[str, Any]:
    """发布前拿报表中的规则引用重跑选中的目标列。"""
    service: SchemaRegistryService = service_for("schema_registry")  # type: ignore[assignment]
    result = service.rerun_target_column(
        schema_name=payload.schema_name,
        schema_version=payload.schema_version,
        target_field=payload.target_field,
        ref_id=payload.ref_id,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("message", "目标列重跑失败"))
    return result
