# ============================================================
# File Name   : registry.py
# Description:
#   数据源适配器能力注册表真实实现。
#
# Responsibilities:
#   - 维护数据源类型能力、别名和 adapter 实例注册表。
#   - 提供 db_type 归一化与 adapter 查找入口，供 service 和旧兼容入口复用。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from typing import Any

from app.domains.data_source.adapters.base import DatasourceAdapter
from app.domains.data_source.adapters.hive import HiveAdapter
from app.domains.data_source.adapters.oracle import OracleAdapter
from app.domains.data_source.capabilities import DatasourceCapability


CAPABILITIES: dict[str, DatasourceCapability] = {
    "mysql": DatasourceCapability(
        db_type="mysql",
        label="MySQL",
        dialect="mysql",
        driver="pymysql",
        driver_module="pymysql",
        sqlalchemy_driver="mysql+pymysql",
        default_port=3306,
        stable=True,
        test_sql="SELECT 1",
    ),
    "doris": DatasourceCapability(
        db_type="doris",
        label="Apache Doris",
        dialect="mysql",
        driver="pymysql",
        driver_module="pymysql",
        sqlalchemy_driver="mysql+pymysql",
        default_port=9030,
        stable=True,
        test_sql="SELECT 1",
    ),
    "postgres": DatasourceCapability(
        db_type="postgres",
        label="PostgreSQL",
        dialect="postgres",
        driver="psycopg2",
        driver_module="psycopg2",
        sqlalchemy_driver="postgresql+psycopg2",
        default_port=5432,
        default_schema="public",
        stable=True,
        test_sql="SELECT 1",
    ),
    "sqlite": DatasourceCapability(
        db_type="sqlite",
        label="SQLite",
        dialect="sqlite",
        driver=None,
        driver_module=None,
        sqlalchemy_driver="sqlite",
        default_port=0,
        default_schema="main",
        stable=True,
        test_sql="SELECT 1",
    ),
    "oracle": DatasourceCapability(
        db_type="oracle",
        label="Oracle",
        dialect="oracle",
        driver="oracledb",
        driver_module="oracledb",
        sqlalchemy_driver="oracle+oracledb",
        default_port=1521,
        required_options=("service_name",),
        optional_options=("sid",),
        test_sql="SELECT 1 FROM DUAL",
    ),
    "hive": DatasourceCapability(
        db_type="hive",
        label="Hive",
        dialect="hive",
        driver="pyhive",
        driver_module="pyhive.hive",
        sqlalchemy_driver="hive",
        default_port=10000,
        default_schema="default",
        optional_options=("auth", "protocol", "kerberos_service_name"),
        test_sql="SELECT 1",
    ),
    "clickhouse": DatasourceCapability(
        db_type="clickhouse",
        label="ClickHouse",
        dialect="clickhouse",
        driver="clickhouse-sqlalchemy",
        driver_module="clickhouse_sqlalchemy",
        sqlalchemy_driver="clickhouse+native",
        default_port=9000,
    ),
    "sqlserver": DatasourceCapability(
        db_type="sqlserver",
        label="SQL Server",
        dialect="tsql",
        driver="pyodbc",
        driver_module="pyodbc",
        sqlalchemy_driver="mssql+pyodbc",
        default_port=1433,
        optional_options=("driver_name", "instance"),
    ),
    "trino": DatasourceCapability(
        db_type="trino",
        label="Trino",
        dialect="trino",
        driver="trino",
        driver_module="trino",
        sqlalchemy_driver="trino",
        default_port=8080,
        optional_options=("catalog", "schema"),
    ),
    "presto": DatasourceCapability(
        db_type="presto",
        label="Presto",
        dialect="presto",
        driver="pyhive",
        driver_module="pyhive.presto",
        sqlalchemy_driver="presto",
        default_port=8080,
        optional_options=("catalog", "schema"),
    ),
    "bigquery": DatasourceCapability(
        db_type="bigquery",
        label="BigQuery",
        dialect="bigquery",
        driver="sqlalchemy-bigquery",
        driver_module="sqlalchemy_bigquery",
        sqlalchemy_driver="bigquery",
        default_port=0,
        optional_options=("project", "dataset", "credentials_path"),
    ),
}


ALIASES = {
    "postgresql": "postgres",
    "pg": "postgres",
    "mssql": "sqlserver",
    "sql_server": "sqlserver",
}


ADAPTERS: dict[str, DatasourceAdapter] = {
    key: DatasourceAdapter(capability) for key, capability in CAPABILITIES.items()
}
ADAPTERS["oracle"] = OracleAdapter(CAPABILITIES["oracle"])
ADAPTERS["hive"] = HiveAdapter(CAPABILITIES["hive"])


def normalize_db_type(value: str | None) -> str:
    """归一化数据源类型标识。"""
    normalized = str(value or "postgres").strip().lower()
    return ALIASES.get(normalized, normalized)


def get_adapter(db_type: str | None) -> DatasourceAdapter:
    """按 db_type 获取适配器，不支持时抛出稳定诊断异常。"""
    normalized = normalize_db_type(db_type)
    adapter = ADAPTERS.get(normalized)
    if not adapter:
        raise ValueError(f"Unsupported datasource type: {db_type}")
    return adapter


__all__: list[str] = [
    "ADAPTERS",
    "ALIASES",
    "CAPABILITIES",
    "get_adapter",
    "normalize_db_type",
]
