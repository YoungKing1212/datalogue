# ============================================================
# File Name   : d2e3f4a5b6c7_add_datasource_capability_fields.py
# Description:
#   为数据源增加多类型适配能力字段。
#
# Responsibilities:
#   - 保存方言、驱动、默认 schema、连接选项和最近诊断。
#   - 为现有数据源按 db_type 回填基础能力信息。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

"""add datasource capability fields

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CAPABILITY_DEFAULTS = {
    "mysql": ("mysql", "pymysql", None),
    "postgres": ("postgres", "psycopg2", "public"),
    "postgresql": ("postgres", "psycopg2", "public"),
    "sqlite": ("sqlite", None, "main"),
    "oracle": ("oracle", "oracledb", None),
    "hive": ("hive", "pyhive", "default"),
    "clickhouse": ("clickhouse", "clickhouse-sqlalchemy", None),
    "sqlserver": ("tsql", "pyodbc", None),
    "trino": ("trino", "trino", None),
    "presto": ("presto", "pyhive", None),
    "bigquery": ("bigquery", "sqlalchemy-bigquery", None),
}


def _columns(table_name: str) -> set[str]:
    inspector = inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    existing = _columns("datasource")
    columns = {
        "dialect": sa.Column("dialect", sa.String(length=50), nullable=True),
        "driver": sa.Column("driver", sa.String(length=100), nullable=True),
        "default_schema": sa.Column("default_schema", sa.String(length=100), nullable=True),
        "connection_options": sa.Column("connection_options", sa.JSON(), nullable=True),
        "connect_timeout_seconds": sa.Column("connect_timeout_seconds", sa.Integer(), nullable=True),
        "query_timeout_seconds": sa.Column("query_timeout_seconds", sa.Integer(), nullable=True),
        "last_test_result": sa.Column("last_test_result", sa.JSON(), nullable=True),
        "last_error_code": sa.Column("last_error_code", sa.String(length=50), nullable=True),
        "last_error_message": sa.Column("last_error_message", sa.Text(), nullable=True),
    }
    for name, column in columns.items():
        if name not in existing:
            op.add_column("datasource", column)

    bind = op.get_bind()
    rows = bind.execute(text("SELECT id, db_type FROM datasource")).fetchall()
    for ds_id, db_type in rows:
        dialect, driver, default_schema = CAPABILITY_DEFAULTS.get(
            str(db_type or "postgres").lower(),
            ("postgres", "psycopg2", "public"),
        )
        bind.execute(
            text(
                """
                UPDATE datasource
                SET dialect = COALESCE(dialect, :dialect),
                    driver = COALESCE(driver, :driver),
                    default_schema = COALESCE(default_schema, :default_schema),
                    connect_timeout_seconds = COALESCE(connect_timeout_seconds, 10),
                    query_timeout_seconds = COALESCE(query_timeout_seconds, 30)
                WHERE id = :id
                """
            ),
            {
                "id": ds_id,
                "dialect": dialect,
                "driver": driver,
                "default_schema": default_schema,
            },
        )


def downgrade() -> None:
    existing = _columns("datasource")
    for name in (
        "last_error_message",
        "last_error_code",
        "last_test_result",
        "query_timeout_seconds",
        "connect_timeout_seconds",
        "connection_options",
        "default_schema",
        "driver",
        "dialect",
    ):
        if name in existing:
            op.drop_column("datasource", name)
