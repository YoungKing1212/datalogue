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
QueryFailureType = Literal[
    "FIELD_NOT_FOUND",
    "FILTER_MISSING",
    "AGGREGATION_WRONG",
    "VALUE_BINDING_FAILED",
    "SQL_GUARD_BLOCKED",
    "EMPTY_RESULT",
]

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


class JoinKey(StrictModel):
    """显式声明 join 键，避免 LLM 靠 relationship_ref 语义猜关联字段。

    LLM 从蓝图 call_template 或 L2 schema slice 推断出 join 条件时，通过 join_keys
    把左右字段名精确传出。后端不做 SQL 解析，仅在 legacy DSL 里透传，供上层编译器
    未来消费；本字段不参与 L4 relationship_ref 校验，只承担声明性通道。
    """

    left_field: str = Field(min_length=1)
    right_field: str = Field(min_length=1)


class JoinRequirement(StrictModel):
    left_alias: str = Field(min_length=1)
    right_alias: str = Field(min_length=1)
    relationship_ref: str = Field(min_length=1)
    join_type: JoinType = "inner"
    required: bool = True
    reason: str = Field(min_length=1)
    # join_keys 用于把蓝图 SQL 里的物理 join 条件（如 p.account=ep.person_card）
    # 从 LLM 侧显式传给后端；旧编译器暂不消费，后续可平滑接入。
    join_keys: list[JoinKey] = Field(default_factory=list)


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
    context_state_patch: dict[str, Any] = Field(default_factory=dict)
    context_state_usage: str | None = None
    summary: str


class TableDetailContext(StrictModel):
    """L2b describe_tables 工具的返回契约:精确点名表的字段/样例详情。"""

    datalogue_event_type: Literal["bi_worker_l2_table_detail"] = "bi_worker_l2_table_detail"
    dataset_id: int
    entities: list[dict[str, Any]] = Field(default_factory=list)
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


REPAIR_HINTS: dict[QueryFailureType, dict[str, str]] = {
    "FIELD_NOT_FOUND": {
        "safe_reason": "查询计划中引用了未在上下文中发现的字段，需要补充数据资产信息。",
        "recommended_action": "使用 datalogue_request_schema_slice 补充缺失字段的 schema 切片，然后基于新上下文重新生成查询计划。",
    },
    "FILTER_MISSING": {
        "safe_reason": "查询计划缺少必要的过滤条件，可能导致结果不准确或执行失败。",
        "recommended_action": "为用户的问题补充适当的过滤条件（时间范围、业务维度等），然后重新生成查询计划。",
    },
    "AGGREGATION_WRONG": {
        "safe_reason": "聚合操作与字段类型或上下文不匹配，无法正确执行。",
        "recommended_action": "检查指标字段的聚合方式（sum/count/avg/min/max/count_distinct），确保与字段口径一致。",
    },
    "VALUE_BINDING_FAILED": {
        "safe_reason": "查询参数值绑定失败，当前上下文提供的参数不满足执行要求。",
        "recommended_action": "确认查询参数值后重新生成查询计划并重试。",
    },
    "SQL_GUARD_BLOCKED": {
        "safe_reason": "查询被安全规则拦截，涉及未授权的数据访问范围。",
        "recommended_action": "调整查询范围，仅使用已授权数据集和字段，确认后重新生成查询计划。",
    },
    "EMPTY_RESULT": {
        "safe_reason": "查询执行成功但未返回数据行，可能是过滤条件过严或数据集无匹配记录。",
        "recommended_action": "放宽过滤条件，或确认数据集在所选时间范围内是否有数据。",
    },
}


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

    @classmethod
    def from_failure_type(
        cls,
        failure_type: QueryFailureType,
        *,
        retry_count: int = 0,
    ) -> "RepairRequest":
        """根据 QueryFailureType 生成标准化修复请求。"""
        hints = REPAIR_HINTS.get(failure_type, {})
        return cls(
            repair_status="needs_plan_revision",
            failure_stage="validate",
            failure_class=failure_type,
            safe_reason=hints.get("safe_reason", "查询执行过程中遇到未知错误。"),
            recommended_action=hints.get("recommended_action", "重新生成查询计划后重试。"),
            missing_context=[
                {
                    "type": failure_type,
                    "hint": hints.get("safe_reason", ""),
                    "retry_count": retry_count,
                }
            ],
        )


FAILURE_DIAGNOSIS_MAP: dict[QueryFailureType, dict[str, str]] = {
    "FIELD_NOT_FOUND": {
        "safe_diagnosis": "查询引用了当前上下文中不存在的字段引用。",
        "recommended_action": "使用 datalogue_request_schema_slice 验证并补充缺失字段后重新生成查询计划。",
    },
    "FILTER_MISSING": {
        "safe_diagnosis": "查询计划缺少必要的过滤条件引用。",
        "recommended_action": "补齐过滤条件所需的实体和关系引用后重试。",
    },
    "AGGREGATION_WRONG": {
        "safe_diagnosis": "聚合操作与字段类型或上下文不兼容。",
        "recommended_action": "检查指标字段的聚合方式是否正确（sum/count/avg/min/max/count_distinct）。",
    },
    "VALUE_BINDING_FAILED": {
        "safe_diagnosis": "查询参数绑定失败，无法完成执行。",
        "recommended_action": "重新生成查询计划后重试。",
    },
    "SQL_GUARD_BLOCKED": {
        "safe_diagnosis": "查询被安全规则拦截，可能涉及未授权的数据范围或操作。",
        "recommended_action": "调整查询范围，确认只访问已授权数据集和字段后重试。",
    },
    "EMPTY_RESULT": {
        "safe_diagnosis": "查询执行成功但未返回数据。",
        "recommended_action": "尝试放宽过滤条件或确认数据集在所选时间范围内是否有数据。",
    },
}


class BIWorkerQueryResult(StrictModel):
    answer_summary: str
    artifact_ref: str | None
    checkpoint_ref: str | None
    row_count: int | None
    column_count: int | None
    failure_type: QueryFailureType | None = None
    safe_diagnosis: str | None = None
    recommended_action: str | None = None

    def to_tool_payload(self) -> dict[str, Any]:
        if self.failure_type:
            return {
                "status": "failed",
                "failure_type": self.failure_type,
                "safe_diagnosis": self.safe_diagnosis
                or FAILURE_DIAGNOSIS_MAP.get(self.failure_type, {}).get(
                    "safe_diagnosis", "未知错误"
                ),
                "recommended_action": self.recommended_action
                or FAILURE_DIAGNOSIS_MAP.get(self.failure_type, {}).get(
                    "recommended_action", "重试或联系管理员。"
                ),
                "datalogue_event_type": "dataset_query_result",
                "summary": self.answer_summary,
            }
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
            }
        return {
            "status": "completed",
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
