# ============================================================
# File Name   : dsl.py
# Description:
#   NL2DSL v2 的结构化资产引用 Schema。
#
# Responsibilities:
#   - 定义 DSL 中指标、维度、字段、术语和蓝图的资产引用对象。
#   - 提供旧版字符串 DSL 到 v2 资产引用 DSL 的兼容转换。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AssetType = Literal["term", "metric", "dimension", "column", "field", "blueprint"]
ASSET_TYPES = {"term", "metric", "dimension", "column", "field", "blueprint"}
ASSET_TYPE_ALIASES = {
    "business_term": "term",
    "analysis_blueprint": "blueprint",
    "source_column": "column",
}


class DslAssetRef(BaseModel):
    """DSL 中对语义资产的显式引用。"""

    name: str
    asset_type: AssetType
    asset_id: int | None = None
    display_name: str | None = None
    matched_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None

    model_config = ConfigDict(extra="allow")


class DslAmbiguity(BaseModel):
    """NL2DSL 解析时保留的歧义信息，供前端或后续澄清使用。"""

    text: str | None = None
    reason: str | None = None
    candidates: list[DslAssetRef] = Field(default_factory=list)
    resolution_hint: str | None = None

    model_config = ConfigDict(extra="allow")


class DslFilter(BaseModel):
    """DSL 过滤条件，field 支持旧字符串和 v2 资产引用对象。"""

    field: str | DslAssetRef
    op: Literal["eq", "in", "gt", "gte", "lt", "lte", "between", "neq"]
    values: list[Any] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    ambiguities: list[DslAmbiguity] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class DslOrderBy(BaseModel):
    """DSL 排序条件，field 支持旧字符串和 v2 资产引用对象。"""

    field: str | DslAssetRef
    direction: Literal["ASC", "DESC"] = "DESC"

    @field_validator("direction", mode="before")
    @classmethod
    def normalize_direction(cls, value: Any) -> str:
        return str(value or "DESC").upper()

    model_config = ConfigDict(extra="allow")


class Nl2Dsl(BaseModel):
    """NL2DSL v2 根对象。

    旧版 DSL 可继续通过 normalize_dsl 转为本结构；direct_sql 路径保留为逃逸模式。
    """

    version: str = "2.0"
    metrics: list[DslAssetRef] = Field(default_factory=list)
    dimensions: list[DslAssetRef] = Field(default_factory=list)
    fields: list[DslAssetRef] = Field(default_factory=list)
    terms: list[DslAssetRef] = Field(default_factory=list)
    blueprints: list[DslAssetRef] = Field(default_factory=list)
    filters: list[DslFilter] = Field(default_factory=list)
    time_range: dict[str, Any] | None = None
    order_by: list[DslOrderBy] = Field(default_factory=list)
    limit: int | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    ambiguities: list[DslAmbiguity] = Field(default_factory=list)
    direct_sql: str | None = None
    inferred: bool = False

    model_config = ConfigDict(extra="allow")


def normalize_asset_ref(value: Any, default_type: AssetType) -> dict[str, Any]:
    """把旧字符串或 LLM 输出的松散对象转换为标准资产引用字典。"""
    if isinstance(value, DslAssetRef):
        return value.model_dump(exclude_none=True)
    if isinstance(value, str):
        return {
            "name": value,
            "asset_type": default_type,
            "asset_id": None,
            "confidence": None,
        }
    if isinstance(value, dict):
        name = value.get("name") or value.get("resolved") or value.get("display_name") or value.get("field")
        if not name:
            name = str(value.get("asset_id") or "")
        raw_asset_type = str(value.get("asset_type") or default_type)
        asset_type = ASSET_TYPE_ALIASES.get(raw_asset_type, raw_asset_type)
        if asset_type not in ASSET_TYPES:
            asset_type = default_type
        normalized = {**value, "name": str(name), "asset_type": asset_type}
        normalized.setdefault("asset_id", None)
        normalized.setdefault("confidence", None)
        return DslAssetRef.model_validate(normalized).model_dump(exclude_none=True)
    return {
        "name": str(value),
        "asset_type": default_type,
        "asset_id": None,
        "confidence": None,
    }


def get_dsl_item_name(value: Any) -> str:
    """从旧字符串或 v2 资产引用对象中读取用于编译的稳定名称。"""
    if isinstance(value, str):
        return value
    if isinstance(value, DslAssetRef):
        return value.name
    if isinstance(value, dict):
        return str(value.get("name") or value.get("resolved") or value.get("field") or "")
    return str(value)


def get_dsl_asset_id(value: Any) -> int | None:
    """读取 DSL 资产引用中的 asset_id。旧字符串没有 asset_id。"""
    if isinstance(value, DslAssetRef):
        return value.asset_id
    if isinstance(value, dict):
        asset_id = value.get("asset_id")
        return asset_id if isinstance(asset_id, int) else None
    return None


def _normalize_filters(filters: Any) -> list[dict[str, Any]]:
    if not isinstance(filters, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in filters:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        next_item = {**item}
        if isinstance(field, dict):
            next_item["field"] = normalize_asset_ref(field, "field")
        normalized.append(DslFilter.model_validate(next_item).model_dump(exclude_none=True))
    return normalized


def _normalize_order_by(order_by: Any) -> list[dict[str, Any]]:
    if not isinstance(order_by, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in order_by:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        next_item = {**item}
        if isinstance(field, dict):
            next_item["field"] = normalize_asset_ref(field, "field")
        normalized.append(DslOrderBy.model_validate(next_item).model_dump(exclude_none=True))
    return normalized


def normalize_dsl(dsl: dict[str, Any] | None) -> dict[str, Any]:
    """将旧 DSL 或 LLM 松散 DSL 规范化为 NL2DSL v2 字典。

    兼容原则：
    - direct_sql / inferred 路径不强制要求 metrics。
    - 旧的 metrics/dimensions 字符串列表会被包装为资产引用对象。
    - 未知扩展字段保留，便于灰度接入新节点。
    """
    if not isinstance(dsl, dict):
        return {}

    normalized = dict(dsl)
    if "direct_sql" in normalized:
        normalized.setdefault("version", "2.0")
        return normalized

    normalized["version"] = str(normalized.get("version") or "2.0")
    normalized["metrics"] = [
        normalize_asset_ref(item, "metric") for item in normalized.get("metrics") or []
    ]
    normalized["dimensions"] = [
        normalize_asset_ref(item, "dimension") for item in normalized.get("dimensions") or []
    ]
    normalized["fields"] = [
        normalize_asset_ref(item, "field") for item in normalized.get("fields") or []
    ]
    normalized["terms"] = [
        normalize_asset_ref(item, "term") for item in normalized.get("terms") or []
    ]
    normalized["blueprints"] = [
        normalize_asset_ref(item, "blueprint") for item in normalized.get("blueprints") or []
    ]
    normalized["filters"] = _normalize_filters(normalized.get("filters") or [])
    normalized["order_by"] = _normalize_order_by(normalized.get("order_by") or [])

    ambiguities = normalized.get("ambiguities") or []
    if isinstance(ambiguities, list):
        normalized["ambiguities"] = [
            DslAmbiguity.model_validate(item).model_dump(exclude_none=True)
            for item in ambiguities
            if isinstance(item, dict)
        ]
    else:
        normalized["ambiguities"] = []

    return Nl2Dsl.model_validate(normalized).model_dump(exclude_none=True)
