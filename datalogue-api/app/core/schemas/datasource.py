# ============================================================
# File Name   : datasource.py
# Description:
#   数据源 API 的 Pydantic Schema。
#
# Responsibilities:
#   - 校验数据源连接请求。
#   - 序列化数据源、表和字段元数据。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class DatasourceCreate(BaseModel):
    name: str
    db_type: str = "postgres"
    host: str
    port: int = 5432
    database_name: str
    username: str
    password: str
    dialect: Optional[str] = None
    driver: Optional[str] = None
    default_schema: Optional[str] = None
    connection_options: Optional[dict[str, Any]] = None
    connect_timeout_seconds: Optional[int] = 10
    query_timeout_seconds: Optional[int] = 30


class DatasourceUpdate(BaseModel):
    name: Optional[str] = None
    db_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    dialect: Optional[str] = None
    driver: Optional[str] = None
    default_schema: Optional[str] = None
    connection_options: Optional[dict[str, Any]] = None
    connect_timeout_seconds: Optional[int] = None
    query_timeout_seconds: Optional[int] = None


class DatasourceOut(BaseModel):
    id: int
    name: str
    db_type: str
    host: str
    port: int
    database_name: str
    username: str
    status: Optional[str] = None
    dialect: Optional[str] = None
    driver: Optional[str] = None
    default_schema: Optional[str] = None
    connection_options: Optional[dict[str, Any]] = None
    connect_timeout_seconds: Optional[int] = None
    query_timeout_seconds: Optional[int] = None
    last_test_result: Optional[dict[str, Any]] = None
    last_error_code: Optional[str] = None
    last_error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DatasourceCapabilityOut(BaseModel):
    db_type: str
    label: str
    dialect: str
    driver: Optional[str] = None
    driver_module: Optional[str] = None
    driver_status: str = "builtin"
    install_hint: Optional[str] = None
    default_port: int
    default_schema: Optional[str] = None
    stable: bool = False
    required_options: list[str] = []
    optional_options: list[str] = []
    supports_sqlalchemy: bool = True


class DatasourcePreviewRequest(BaseModel):
    """数据源表预览请求；表名仍须由 API 与已同步元数据做精确白名单匹配。"""

    model_config = ConfigDict(populate_by_name=True)

    schema_name: Optional[str] = Field(default=None, alias="schema", min_length=1, max_length=100)
    table: str = Field(..., min_length=1, max_length=100)
    limit: int = Field(default=5, ge=1, le=100)
