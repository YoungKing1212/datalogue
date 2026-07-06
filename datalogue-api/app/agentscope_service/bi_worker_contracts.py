# ============================================================
# File Name   : bi_worker_contracts.py
# Description:
#   BI Worker 渐进式上下文与安全结果回传的契约模型。
#
# Responsibilities:
#   - 定义查询计划、上下文缺口、修复请求和结果卡片的安全 Pydantic 模型。
#   - 约束 Worker 与 Agent Team 之间只交换引用、摘要和行列数等安全 payload。
#   - 拒绝自由 join 条件、原始 SQL、数据库错误片段和明细行泄露。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SupportStatus = Literal["supported", "needs_more_context", "needs_clarification", "unsupported"]
QueryIntent = Literal["detail_query", "metric_query", "knowledge_qa", "unsupported"]
JoinType = Literal["inner", "left"]
RepairStatus = Literal["needs_plan_revision", "auto_repaired", "unsupported", "failed"]
FailureStage = Literal["validate", "compile", "execute", "artifact"]

_FORBIDDEN_SAFE_REASON_FRAGMENTS = (
    "select ",
    " from ",
    " where ",
    "relation ",
    "table ",
    "column ",
)


class StrictModel(BaseModel):
    """所有契约默认拒绝额外字段，避免模型输出把 SQL/schema/raw rows 混入安全面。"""

    model_config = ConfigDict(extra="forbid")


class FieldTarget(StrictModel):
    """查询字段定位，仅保存字段引用和展示语义，不保存真实表达式。"""

    entity_ref: str | None = None
    field_ref: str = Field(min_length=1)
    display_name: str | None = None


class QueryFilter(StrictModel):
    """查询过滤条件的安全描述，值只用于计划语义，不承载 SQL 条件片段。"""

    target: FieldTarget
    operator: str = Field(min_length=1)
    value: Any | None = None
    value_ref: str | None = None
    safe_description: str | None = None


class QuerySelect(StrictModel):
    """明细查询返回列。"""

    target: FieldTarget
    alias: str | None = None


class QueryMetric(StrictModel):
    """指标查询中的聚合指标定义。"""

    target: FieldTarget | None = None
    metric_ref: str | None = None
    aggregation: str = Field(min_length=1)
    alias: str | None = None


class QueryOrdering(StrictModel):
    """排序意图，只引用字段或指标，不携带 order by 原文。"""

    target: FieldTarget | None = None
    metric_ref: str | None = None
    direction: Literal["asc", "desc"] = "asc"


class ResultShape(StrictModel):
    """结果形状约束，用于控制返回表格、指标或文本摘要的安全外观。"""

    kind: Literal["table", "metric", "text"] = "table"
    limit: int | None = Field(default=None, ge=1)


class QueryEntity(StrictModel):
    """查询涉及的数据实体引用。"""

    entity_ref: str = Field(min_length=1)
    display_name: str | None = None
    role: Literal["fact", "dimension", "lookup", "unknown"] = "unknown"
    table_ref: str | None = None


class QueryDataGraph(StrictModel):
    """多表关系图的安全版本，只暴露实体和关系引用，不暴露 join 表达式。"""

    nodes: list[QueryEntity] = Field(default_factory=list)
    relationships: list["JoinRequirement"] = Field(default_factory=list)


class JoinRequirement(StrictModel):
    """Worker 只能通过已治理关系引用声明 join 需求，不能输出自由 join 条件。"""

    relationship_ref: str = Field(min_length=1)
    join_type: JoinType = "inner"
    required: bool = True
    from_entity_ref: str | None = None
    to_entity_ref: str | None = None
    description: str | None = None


class BIWorkerQueryPlan(StrictModel):
    """BI Worker 生成的查询计划契约，按 intent 校验最小必要字段。"""

    intent: QueryIntent
    entities: list[QueryEntity] = Field(default_factory=list)
    data_graph: QueryDataGraph | None = None
    selects: list[QuerySelect] = Field(default_factory=list)
    filters: list[QueryFilter] = Field(default_factory=list)
    metrics: list[QueryMetric] = Field(default_factory=list)
    orderings: list[QueryOrdering] = Field(default_factory=list)
    join_requirements: list[JoinRequirement] = Field(default_factory=list)
    result_shape: ResultShape = Field(default_factory=ResultShape)
    safe_question: str | None = None

    @model_validator(mode="after")
    def _validate_intent_requirements(self) -> "BIWorkerQueryPlan":
        if self.intent == "detail_query" and not self.selects:
            raise ValueError("detail_query requires at least one select")
        if self.intent == "metric_query" and not self.metrics:
            raise ValueError("metric_query requires at least one metric")
        return self


class DatasetCapabilityContext(StrictModel):
    """L0 数据集能力上下文，只表达是否支持查询、指标和关联等安全能力。"""

    context_level: Literal["L0_dataset_capability"] = "L0_dataset_capability"
    dataset_ref: str | None = None
    supports_detail_query: bool = True
    supports_metric_query: bool = True
    supports_join: bool = False
    limitations: list[str] = Field(default_factory=list)


class QueryAssetContext(StrictModel):
    """L1 查询资产上下文，用于表达候选资产或缺失依赖，不包含资产内部结构。"""

    context_level: Literal["L1_query_asset", "L2_schema_slice", "L3_value_profile"] = "L1_query_asset"
    dependency_type: Literal[
        "dataset_capability",
        "query_asset",
        "schema_slice",
        "value_profile",
        "lookup_dependency",
    ] = "query_asset"
    asset_ref: str | None = None
    entity_ref: str | None = None
    field_ref: str | None = None
    relationship_ref: str | None = None
    reason: str = Field(min_length=1)


class SchemaSliceContext(StrictModel):
    """L2 schema slice 上下文，只传字段和关系引用，不传建表语句或数据库类型细节。"""

    context_level: Literal["L2_schema_slice"] = "L2_schema_slice"
    entity_ref: str = Field(min_length=1)
    field_refs: list[str] = Field(default_factory=list)
    relationship_refs: list[str] = Field(default_factory=list)
    safe_description: str | None = None


class ValueProfileContext(StrictModel):
    """L3 值画像上下文，只保存脱敏后的枚举或分布摘要。"""

    context_level: Literal["L3_value_profile"] = "L3_value_profile"
    field_ref: str = Field(min_length=1)
    sample_values: list[str] = Field(default_factory=list)
    distribution_summary: str | None = None


class QuerySupportValidation(StrictModel):
    """查询可支持性判断，missing_context 用于驱动 Worker 渐进补上下文。"""

    status: SupportStatus
    missing_context: list[QueryAssetContext] = Field(default_factory=list)
    safe_reason: str | None = None
    supported_plan: BIWorkerQueryPlan | None = None


class RepairRequest(StrictModel):
    """失败修复请求，对外只允许安全原因，不能携带 SQL 或数据库原始报错。"""

    status: RepairStatus
    failure_stage: FailureStage
    safe_reason: str = Field(min_length=1)
    plan_ref: str | None = None
    retryable: bool = False

    @field_validator("safe_reason")
    @classmethod
    def _reject_internal_fragments(cls, value: str) -> str:
        lowered = value.lower()
        # 这些片段通常来自 SQL 或数据库错误，进入 Agent Team 会把内部实现暴露给用户。
        if any(fragment in lowered for fragment in _FORBIDDEN_SAFE_REASON_FRAGMENTS):
            raise ValueError("safe_reason contains forbidden SQL or database error fragment")
        return value


class BIWorkerQueryResult(StrictModel):
    """BI Worker 查询成功后可 TeamSay 给 Leader 的安全结果。"""

    answer_summary: str = Field(min_length=1)
    artifact_ref: str | None = None
    checkpoint_ref: str | None = None
    row_count: int | None = Field(default=None, ge=0)
    column_count: int | None = Field(default=None, ge=0)

    def to_tool_payload(self) -> dict[str, Any]:
        """生成用户可见的安全 artifact card，不包含 SQL、schema 或 raw rows。"""

        return {
            "answer_summary": self.answer_summary,
            "artifact_ref": self.artifact_ref,
            "checkpoint_ref": self.checkpoint_ref,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "datalogue_event_type": "dataset_query_result",
            "summary": self.answer_summary,
            "result_ref": self.artifact_ref,
            "artifact_card": {
                "artifact_type": "bi_answer",
                "title": "查询结果",
                "status": "completed",
                "summary_for_chat": self.answer_summary,
                "preview_payload": {
                    "row_count": self.row_count or 0,
                    "column_count": self.column_count or 0,
                },
                "primary_ref": {
                    "ref_id": self.artifact_ref,
                    "ref_type": "result",
                    "label": "查询结果",
                },
                "related_refs": [],
                "actions": [
                    {
                        "action_type": "view",
                        "label": "查看详情",
                        "ref": self.artifact_ref,
                        "disabled": False,
                    },
                    {
                        "action_type": "export",
                        "label": "导出",
                        "ref": self.artifact_ref,
                        "disabled": True,
                    },
                ],
            },
        }
