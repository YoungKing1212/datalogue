from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, ConfigDict


class DatasetCreate(BaseModel):
    name: str
    datasource_id: int
    tables_json: Dict[str, Any] = {}
    description: Optional[str] = None
    prompt_instructions: Optional[str] = None
    status: str = "draft"


class DatasetUpdate(BaseModel):
    """数据集部分更新 — 重命名等场景。"""

    name: Optional[str] = None
    description: Optional[str] = None
    prompt_instructions: Optional[str] = None
    status: Optional[str] = None
    tables_json: Optional[Dict[str, Any]] = None


class DatasetOut(BaseModel):
    id: int
    name: str
    datasource_id: int
    tables_json: Dict[str, Any]
    description: Optional[str] = None
    prompt_instructions: Optional[str] = None
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
    user_description: Optional[str] = None
    user_semantic_role: Optional[str] = None
    effective_desc: Optional[str] = None
    desc_source: Optional[str] = None
    annotated_at: Optional[datetime] = None
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


class SelectTablesPayload(BaseModel):
    source_table_ids: List[int]
