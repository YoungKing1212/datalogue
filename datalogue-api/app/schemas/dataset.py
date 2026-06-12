# ============================================================
# File Name   : dataset.py
# Description:
#   语义数据集 API 的 Pydantic Schema。
#
# Responsibilities:
#   - 校验数据集、指标、维度、术语和蓝图请求。
#   - 为前端序列化语义治理资源。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from datetime import datetime
from typing import Optional, Dict, Any, List, Literal

from pydantic import BaseModel, ConfigDict


class DatasetCreate(BaseModel):
    name: str
    datasource_id: int
    tables_json: Dict[str, Any] = {}
    description: Optional[str] = None
    prompt_instructions: Optional[str] = None
    query_constraints: Optional[Dict[str, Any]] = None
    status: str = "draft"


class DatasetUpdate(BaseModel):
    """数据集部分更新 — 重命名等场景。"""

    name: Optional[str] = None
    description: Optional[str] = None
    prompt_instructions: Optional[str] = None
    query_constraints: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    tables_json: Optional[Dict[str, Any]] = None


class DatasetOut(BaseModel):
    id: int
    name: str
    datasource_id: int
    tables_json: Dict[str, Any]
    description: Optional[str] = None
    prompt_instructions: Optional[str] = None
    query_constraints: Optional[Dict[str, Any]] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MetricCreate(BaseModel):
    name: str
    display_name: str
    expr: str
    table_name: Optional[str] = None
    time_field: Optional[str] = None
    granularity: Optional[str] = None
    format_str: Optional[str] = None
    filter_sql: Optional[str] = None
    synonyms: Optional[List[str]] = None
    description: Optional[str] = None


class MetricOut(BaseModel):
    id: int
    dataset_id: int
    name: str
    display_name: str
    expr: str
    table_name: Optional[str] = None
    time_field: Optional[str] = None
    granularity: Optional[str] = None
    format_str: Optional[str] = None
    filter_sql: Optional[str] = None
    synonyms: Optional[List[str]] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DimensionCreate(BaseModel):
    name: str
    display_name: str
    column_name: str
    table_name: Optional[str] = None
    join_to: Optional[str] = None
    join_key: Optional[str] = None
    hierarchy: Optional[Dict[str, Any]] = None
    enum_values: Optional[List[str]] = None
    synonyms: Optional[List[str]] = None


class DimensionOut(BaseModel):
    id: int
    dataset_id: int
    name: str
    display_name: str
    column_name: str
    table_name: Optional[str] = None
    join_to: Optional[str] = None
    join_key: Optional[str] = None
    hierarchy: Optional[Dict[str, Any]] = None
    enum_values: Optional[List[str]] = None
    synonyms: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


class SourceTableOut(BaseModel):
    id: int
    datasource_id: int
    schema_name: str
    table_name: str
    table_comment: Optional[str] = None
    business_desc: Optional[str] = None
    ai_description: Optional[str] = None
    user_description: Optional[str] = None
    effective_desc: Optional[str] = None
    desc_source: Optional[str] = None
    annotated_at: Optional[datetime] = None
    row_count_approx: Optional[int] = None
    status: str
    synced_at: Optional[datetime] = None
    column_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class SourceColumnOut(BaseModel):
    id: int
    table_id: int
    column_name: str
    data_type: Optional[str] = None
    column_comment: Optional[str] = None
    business_desc: Optional[str] = None
    ai_description: Optional[str] = None
    ai_semantic_role: Optional[str] = None
    ai_suggested_agg: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_reason: Optional[str] = None
    suggested_synonyms: Optional[List[str]] = None
    suggested_enum_values: Optional[List[str]] = None
    user_description: Optional[str] = None
    user_semantic_role: Optional[str] = None
    effective_desc: Optional[str] = None
    desc_source: Optional[str] = None
    annotated_at: Optional[datetime] = None
    review_status: Optional[str] = None
    converted_metric_id: Optional[int] = None
    converted_dimension_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    is_nullable: Optional[str] = None
    column_default: Optional[str] = None
    ordinal_position: Optional[int] = None
    semantic_role: Optional[str] = None
    default_agg: Optional[str] = None
    sample_values: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


class DatasetSourceTableOut(BaseModel):
    id: int
    dataset_id: int
    source_table_id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SourceColumnUpdate(BaseModel):
    user_description: Optional[str] = None
    user_semantic_role: Optional[str] = None


class SourceColumnReviewPayload(BaseModel):
    review_status: str


class ColumnMetricConvertPayload(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    expr: Optional[str] = None
    table_name: Optional[str] = None
    time_field: Optional[str] = None
    granularity: Optional[str] = None
    format_str: Optional[str] = None
    filter_sql: Optional[str] = None
    synonyms: Optional[List[str]] = None
    description: Optional[str] = None


class ColumnDimensionConvertPayload(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    column_name: Optional[str] = None
    table_name: Optional[str] = None
    join_to: Optional[str] = None
    join_key: Optional[str] = None
    hierarchy: Optional[Dict[str, Any]] = None
    enum_values: Optional[List[str]] = None
    synonyms: Optional[List[str]] = None


class BusinessTermAssetLinkOut(BaseModel):
    id: int
    term_id: int
    asset_type: str
    asset_id: int
    asset_name: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BusinessTermCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    term_type: str = "business_object"
    definition: Optional[str] = None
    aliases: List[str] = []
    forbidden_aliases: List[str] = []
    examples: List[str] = []
    owner: Optional[str] = None
    status: str = "draft"
    source: str = "manual"
    confidence: Optional[float] = None
    extra_metadata: Dict[str, Any] = {}


class BusinessTermUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    term_type: Optional[str] = None
    definition: Optional[str] = None
    aliases: Optional[List[str]] = None
    forbidden_aliases: Optional[List[str]] = None
    examples: Optional[List[str]] = None
    owner: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    confidence: Optional[float] = None
    extra_metadata: Optional[Dict[str, Any]] = None


class BusinessTermOut(BaseModel):
    id: int
    dataset_id: int
    name: str
    display_name: str
    term_type: str
    definition: Optional[str] = None
    aliases: List[str] = []
    forbidden_aliases: List[str] = []
    examples: List[str] = []
    owner: Optional[str] = None
    status: str
    source: str
    confidence: Optional[float] = None
    extra_metadata: Dict[str, Any] = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    asset_links: List[BusinessTermAssetLinkOut] = []

    model_config = ConfigDict(from_attributes=True)


class BusinessTermAssetLinkPayload(BaseModel):
    links: List[Dict[str, Any]]


class BusinessTermDiscoverOut(BaseModel):
    candidates: List[Dict[str, Any]]


class BusinessTermConflictOut(BaseModel):
    conflicts: List[Dict[str, Any]]


class SemanticValidationCaseCreate(BaseModel):
    question: str
    status: str = "unknown"
    route_type: Optional[str] = None
    entry_intent: Optional[str] = None
    entry_route: Optional[str] = None
    blueprint_id: Optional[int] = None
    sql: Optional[str] = None
    answer: Optional[str] = None
    error: Optional[str] = None
    report: Dict[str, Any] = {}
    created_by: Optional[str] = None


class SemanticValidationCaseOut(BaseModel):
    id: int
    dataset_id: int
    question: str
    status: str
    route_type: Optional[str] = None
    entry_intent: Optional[str] = None
    entry_route: Optional[str] = None
    blueprint_id: Optional[int] = None
    sql: Optional[str] = None
    answer: Optional[str] = None
    error: Optional[str] = None
    report: Dict[str, Any] = {}
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ManifestManualFields(BaseModel):
    description: str = ""
    business_domain: List[str] = []
    sample_questions: List[str] = []
    routing_negative_examples: List[str] = []


class ManifestAutoFields(BaseModel):
    dataset_id: int
    name: str
    manifest_version: str
    bound_schema_version: str
    key_metrics: List[Dict[str, Any]] = []
    key_dimensions: List[Dict[str, Any]] = []
    permission_scope: Dict[str, Any] = {}


class ManifestLintIssue(BaseModel):
    code: str
    severity: Literal["warning", "error"]
    message: str


class DatasetSubAgentManifestOut(BaseModel):
    dataset_id: int
    manifest_version: str
    bound_schema_version: str
    manifest_json: Dict[str, Any]
    is_current: bool
    review_status: str
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DatasetSubAgentManifestDetailOut(BaseModel):
    dataset_id: int
    current_manifest: Optional[DatasetSubAgentManifestOut] = None
    draft_manifest: Optional[DatasetSubAgentManifestOut] = None
    auto_fields_preview: ManifestAutoFields
    manual_fields: ManifestManualFields
    lint: List[ManifestLintIssue] = []
    stale: bool = False
    review_status: str = "missing"


class ManifestSavePayload(BaseModel):
    manual_fields: ManifestManualFields
    created_by: Optional[str] = None


class ManifestPublishPayload(BaseModel):
    manual_fields: Optional[ManifestManualFields] = None
    created_by: Optional[str] = None


class ManifestRouteCheckRequest(BaseModel):
    questions: List[str]
    expected: Optional[Literal["positive", "negative"]] = None


class ManifestRouteCheckResult(BaseModel):
    question: str
    top_dataset_id: Optional[int] = None
    matched_manifest_version: Optional[str] = None
    score: float
    decision: Literal["hit", "miss", "ambiguous"]
    reasons: List[str] = []
    suggestions: List[str] = []


class ManifestRouteCheckResponse(BaseModel):
    results: List[ManifestRouteCheckResult]


class SelectTablesPayload(BaseModel):
    source_table_ids: List[int]


class BlueprintCreate(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_keywords: List[str] = []
    trigger_examples: List[str] = []
    when_to_use: Optional[str] = None
    parameters: List[Dict[str, Any]] = []
    implementation_type: str = "stored_procedure"
    call_template: Optional[str] = None
    output_schema: List[Dict[str, Any]] = []
    timeout_seconds: int = 30
    steps: List[Dict[str, Any]] = []
    attribution_hints: Optional[str] = None
    raw_sql: Optional[str] = None
    status: str = "draft"
    creation_source: str = "manual"
    ai_generated: bool = False
    ai_generation_type: Optional[str] = None
    ai_confidence: Optional[float] = None
    owner: Optional[str] = None


class BlueprintUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_keywords: Optional[List[str]] = None
    trigger_examples: Optional[List[str]] = None
    when_to_use: Optional[str] = None
    parameters: Optional[List[Dict[str, Any]]] = None
    implementation_type: Optional[str] = None
    call_template: Optional[str] = None
    output_schema: Optional[List[Dict[str, Any]]] = None
    timeout_seconds: Optional[int] = None
    steps: Optional[List[Dict[str, Any]]] = None
    attribution_hints: Optional[str] = None
    raw_sql: Optional[str] = None
    creation_source: Optional[str] = None
    ai_generated: Optional[bool] = None
    ai_generation_type: Optional[str] = None
    ai_confidence: Optional[float] = None
    owner: Optional[str] = None


class BlueprintOut(BaseModel):
    id: int
    dataset_id: int
    name: str
    description: Optional[str] = None
    trigger_keywords: List[str] = []
    trigger_examples: List[str] = []
    when_to_use: Optional[str] = None
    parameters: List[Dict[str, Any]] = []
    implementation_type: Optional[str] = None
    call_template: Optional[str] = None
    output_schema: List[Dict[str, Any]] = []
    timeout_seconds: int = 30
    steps: List[Dict[str, Any]] = []
    attribution_hints: Optional[str] = None
    raw_sql: Optional[str] = None
    status: str
    version: int
    creation_source: str = "manual"
    ai_generated: bool = False
    ai_generation_type: Optional[str] = None
    ai_confidence: Optional[float] = None
    owner: Optional[str] = None
    last_validated_at: Optional[datetime] = None
    usage_count: int = 0
    last_test_result: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BlueprintStatusPayload(BaseModel):
    action: str
    change_summary: Optional[str] = None
    published_by: Optional[str] = None


class BlueprintAnalyzeSqlPayload(BaseModel):
    sql: str
    mode: str = "sql_import"


class BlueprintAnalyzeDescriptionPayload(BaseModel):
    """手动创建蓝图时提交的业务场景描述。"""

    name: Optional[str] = None
    business_scenario: str
    example_questions: List[str] = []
    expected_output: Optional[str] = None
    business_rules: Optional[str] = None
    owner: Optional[str] = None


class BlueprintAnalyzeTaskOut(BaseModel):
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BlueprintTestPayload(BaseModel):
    params: Dict[str, Any] = {}
    question: Optional[str] = None


class BlueprintTestOut(BaseModel):
    ok: bool
    execution_success: bool
    execution_time_ms: int
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int = 0
    diagnosis: Optional[Dict[str, Any]] = None
    masking_summary: Optional[Dict[str, Any]] = None
    sql_preview: Optional[str] = None
    interpretation_preview: Optional[str] = None
    error_message: Optional[str] = None


class BlueprintVersionOut(BaseModel):
    id: int
    blueprint_id: int
    version: int
    snapshot: Dict[str, Any]
    change_summary: Optional[str] = None
    published_by: Optional[str] = None
    published_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BlueprintRollbackPayload(BaseModel):
    version: int
    change_summary: Optional[str] = None


class BlueprintUsageLogOut(BaseModel):
    id: int
    blueprint_id: int
    question: Optional[str] = None
    extracted_params: Optional[Dict[str, Any]] = None
    execution_success: Optional[bool] = None
    execution_time_ms: Optional[int] = None
    row_count: Optional[int] = None
    diagnosis: Optional[Dict[str, Any]] = None
    user_feedback: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
