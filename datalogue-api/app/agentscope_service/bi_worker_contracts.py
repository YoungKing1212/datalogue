# ============================================================
# File Name   : bi_worker_contracts.py
# Description:
#   BI Worker 渐进式上下文和 Query Plan v1 契约。
#
# Responsibilities:
#   - 定义 L0-L5 安全 payload 结构。
#   - 定义多表 Query Plan v1、支持度校验和安全修复请求。
#   - 统一生成 AgentScope BI Worker 可 TeamSay 的安全结果 payload。
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
    """所有契约默认拒绝额外字段，避免 SQL/schema/raw rows 混入安全面。"""

    model_config = ConfigDict(extra="forbid")


class FieldTarget(StrictModel):
    asset_ref: str = Field(min_length=1)
    alias: str = Field(min_length=1)
    field: str = Field(min_length=1)


class QueryFilter(StrictModel):
    target: FieldTarget
    operator: Literal["=", "!=", ">", ">=", "<", "<=", "between", "in", "contains"]
    value: Any
    reason: str = Field(min_length=1)


class QuerySelect(StrictModel):
    target: FieldTarget
    display_name: str = Field(min_length=1)
    display_semantic: str | None = None
    requires_decoding: bool = False


class QueryMetric(StrictModel):
    target: FieldTarget
    aggregation: Literal["sum", "count", "avg", "min", "max", "count_distinct"]
    display_name: str = Field(min_length=1)


class QueryOrdering(StrictModel):
    target: FieldTarget
    direction: Literal["asc", "desc"] = "asc"


class ResultShape(StrictModel):
    type: Literal["table", "metric", "chart"] = "table"
    grain: str = Field(min_length=1)
    limit: int = Field(default=100, ge=1, le=500)


class QueryEntity(StrictModel):
    asset_ref: str = Field(min_length=1)
    alias: str = Field(min_length=1)
    role: str = Field(min_length=1)
    join_purpose: str | None = None


class QueryDataGraph(StrictModel):
    primary_entity: QueryEntity
    supporting_entities: list[QueryEntity] = Field(default_factory=list)


class JoinRequirement(StrictModel):
    left_alias: str = Field(min_length=1)
    right_alias: str = Field(min_length=1)
    relationship_ref: str = Field(min_length=1)
    join_type: JoinType = "inner"
    required: bool = True
    reason: str = Field(min_length=1)


class BIWorkerQueryPlan(StrictModel):
    intent: QueryIntent
    question: str = Field(min_length=1)
    result_shape: ResultShape
    data_graph: QueryDataGraph
    join_requirements: list[JoinRequirement] = Field(default_factory=list)
    filters: list[QueryFilter] = Field(default_factory=list)
    selects: list[QuerySelect] = Field(default_factory=list)
    metrics: list[QueryMetric] = Field(default_factory=list)
    group_by: list[FieldTarget] = Field(default_factory=list)
    ordering: list[QueryOrdering] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_shape(self) -> "BIWorkerQueryPlan":
        if self.intent == "metric_query" and not self.metrics:
            raise ValueError("metric_query requires at least one metric")
        if self.intent == "detail_query" and not self.selects:
            raise ValueError("detail_query requires at least one selected field")
        return self


class DatasetCapabilityContext(StrictModel):
    datalogue_event_type: Literal["bi_worker_l0_capability"] = "bi_worker_l0_capability"
    dataset_id: int
    dataset_name: str
    business_domain: str | None = None
    supported_questions: list[str] = Field(default_factory=list)
    key_metrics: list[str] = Field(default_factory=list)
    key_dimensions: list[str] = Field(default_factory=list)
    summary: str


class QueryAssetContext(StrictModel):
    datalogue_event_type: Literal["bi_worker_l1_assets"] = "bi_worker_l1_assets"
    dataset_id: int
    question: str
    assets: list[dict[str, Any]] = Field(default_factory=list)
    summary: str


class SchemaSliceContext(StrictModel):
    datalogue_event_type: Literal["bi_worker_l2_schema_slice"] = "bi_worker_l2_schema_slice"
    dataset_id: int
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    summary: str


class ValueProfileContext(StrictModel):
    datalogue_event_type: Literal["bi_worker_l3_value_profile"] = "bi_worker_l3_value_profile"
    dataset_id: int
    profiles: list[dict[str, Any]] = Field(default_factory=list)
    summary: str


class QuerySupportValidation(StrictModel):
    datalogue_event_type: Literal["bi_worker_l4_validation"] = "bi_worker_l4_validation"
    support_status: SupportStatus
    safe_reason: str
    missing_context: list[dict[str, Any]] = Field(default_factory=list)
    auto_context_expansions: list[dict[str, Any]] = Field(default_factory=list)
    recommended_next_tool: str | None = None


class RepairRequest(StrictModel):
    datalogue_event_type: Literal["bi_worker_repair_request"] = "bi_worker_repair_request"
    repair_status: RepairStatus
    failure_stage: FailureStage
    failure_class: str = Field(min_length=1)
    safe_reason: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    missing_context: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("safe_reason")
    @classmethod
    def _reject_raw_error_text(cls, value: str) -> str:
        lowered = value.lower()
        # 这些片段通常来自 SQL 或数据库错误，进入 Agent Team 会暴露内部实现。
        if any(token in lowered for token in _FORBIDDEN_SAFE_REASON_FRAGMENTS):
            raise ValueError("safe_reason contains raw database or SQL detail")
        return value


class BIWorkerQueryResult(StrictModel):
    answer_summary: str
    artifact_ref: str | None
    checkpoint_ref: str | None
    row_count: int | None
    column_count: int | None

    def to_tool_payload(self) -> dict[str, Any]:
        artifact_card = None
        if self.artifact_ref:
            artifact_card = {
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
                    {"action_type": "view", "label": "查看详情", "ref": self.artifact_ref, "disabled": False},
                    {"action_type": "export", "label": "导出", "ref": self.artifact_ref, "disabled": True},
                ],
            }
        return {
            "answer_summary": self.answer_summary,
            "artifact_ref": self.artifact_ref,
            "checkpoint_ref": self.checkpoint_ref,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "datalogue_event_type": "dataset_query_result",
            "summary": self.answer_summary,
            "result_ref": self.artifact_ref,
            "artifact_card": artifact_card,
        }
