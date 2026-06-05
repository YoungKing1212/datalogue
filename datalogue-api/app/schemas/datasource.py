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
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DatasourceCreate(BaseModel):
    name: str
    db_type: str = "postgres"
    host: str
    port: int = 5432
    database_name: str
    username: str
    password: str


class DatasourceUpdate(BaseModel):
    name: Optional[str] = None
    db_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class DatasourceOut(BaseModel):
    id: int
    name: str
    db_type: str
    host: str
    port: int
    database_name: str
    username: str
    status: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
