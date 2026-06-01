from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, ConfigDict


class DatasetCreate(BaseModel):
    name: str
    datasource_id: int
    tables_json: Dict[str, Any] = {}
    description: Optional[str] = None
    status: str = "draft"


class DatasetOut(BaseModel):
    id: int
    name: str
    datasource_id: int
    tables_json: Dict[str, Any]
    description: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MetricCreate(BaseModel):
    name: str
    display_name: str
    expr: str
    filter_sql: Optional[str] = None
    synonyms: Optional[List[str]] = None
    description: Optional[str] = None


class MetricOut(BaseModel):
    id: int
    dataset_id: int
    name: str
    display_name: str
    expr: str
    filter_sql: Optional[str] = None
    synonyms: Optional[List[str]] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DimensionCreate(BaseModel):
    name: str
    display_name: str
    column_name: str
    enum_values: Optional[List[str]] = None
    synonyms: Optional[List[str]] = None


class DimensionOut(BaseModel):
    id: int
    dataset_id: int
    name: str
    display_name: str
    column_name: str
    enum_values: Optional[List[str]] = None
    synonyms: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)
