# ============================================================
# File Name   : datasource.py
# Description:
#   数据源持久化模型。
#
# Responsibilities:
#   - 存储数据源连接元数据。
#   - 表示外部数据库连接配置。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from sqlalchemy import Column, Integer, String, Text, JSON

from app.core.database import Base
from app.models.base import TimestampMixin


class Datasource(Base, TimestampMixin):
    __tablename__ = "datasource"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    db_type = Column(String(20), nullable=False, default="postgres")
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False, default=5432)
    database_name = Column(String(100), nullable=False)
    username = Column(String(100), nullable=False)
    password_enc = Column(Text, nullable=False)
    status = Column(String(20), default="disconnected", server_default="disconnected")
    dialect = Column(String(50), nullable=True)
    driver = Column(String(100), nullable=True)
    default_schema = Column(String(100), nullable=True)
    connection_options = Column(JSON, nullable=True)
    connect_timeout_seconds = Column(Integer, nullable=True, default=10)
    query_timeout_seconds = Column(Integer, nullable=True, default=30)
    last_test_result = Column(JSON, nullable=True)
    last_error_code = Column(String(50), nullable=True)
    last_error_message = Column(Text, nullable=True)
