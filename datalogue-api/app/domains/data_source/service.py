# ============================================================
# File Name   : datasource.py
# Description:
#   多数据源连接、能力注册和结构探查服务。
#
# Responsibilities:
#   - 统一管理不同数据源类型的 SQLAlchemy 连接能力。
#   - 提供连接测试、Schema 拉取、表字段同步和字段样例采集。
#   - 将驱动缺失、权限不足、Schema 不可读等异常转成稳定诊断。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.domains.data_source.adapters.base import DatasourceAdapter
from app.domains.data_source.adapters.hive import HiveAdapter
from app.domains.data_source.adapters.oracle import OracleAdapter
from app.domains.data_source.adapters.registry import (
    ADAPTERS,
    ALIASES,
    CAPABILITIES,
    get_adapter,
    normalize_db_type,
)
from app.domains.data_source.capabilities import DatasourceCapability
from app.domains.data_source.context import DatasourceContext
from app.domains.data_source.diagnostics import (
    DIAGNOSTIC_META,
    DatasourceDiagnostic,
    _classify_exception,
    _diagnostic,
)
from app.models.datasource import Datasource


def get_capabilities() -> list[dict[str, Any]]:
    """返回前端创建表单可使用的数据源能力列表。"""
    items: list[dict[str, Any]] = []
    for capability in CAPABILITIES.values():
        adapter = ADAPTERS[capability.db_type]
        if not capability.driver_module:
            driver_status = "builtin"
            install_hint = None
        elif adapter.driver_available():
            driver_status = "installed"
            install_hint = None
        else:
            driver_status = "missing"
            install_hint = (
                "请在有网构建机执行 datalogue-api/scripts/download_enterprise_wheels.sh，"
                "再在内网使用 pip install --no-index --find-links ./wheelhouse "
                "-r requirements-enterprise.txt 安装。"
            )
        items.append(
            {
                "db_type": capability.db_type,
                "label": capability.label,
                "dialect": capability.dialect,
                "driver": capability.driver,
                "driver_module": capability.driver_module,
                "driver_status": driver_status,
                "install_hint": install_hint,
                "default_port": capability.default_port,
                "default_schema": capability.default_schema,
                "stable": capability.stable,
                "required_options": list(capability.required_options),
                "optional_options": list(capability.optional_options),
                "supports_sqlalchemy": capability.supports_sqlalchemy,
            }
        )
    return items


def enrich_datasource_defaults(data: dict[str, Any]) -> dict[str, Any]:
    """创建或更新数据源前补齐 dialect、driver、默认端口等字段。"""
    db_type = normalize_db_type(data.get("db_type"))
    data["db_type"] = db_type
    capability = CAPABILITIES.get(db_type)
    if not capability:
        return data
    if not data.get("dialect"):
        data["dialect"] = capability.dialect
    if not data.get("driver"):
        data["driver"] = capability.driver
    if data.get("port") in (None, 0) and capability.default_port:
        data["port"] = capability.default_port
    if not data.get("default_schema"):
        data["default_schema"] = capability.default_schema
    if data.get("connection_options") is None:
        data["connection_options"] = {}
    if data.get("connect_timeout_seconds") is None:
        data["connect_timeout_seconds"] = 10
    if data.get("query_timeout_seconds") is None:
        data["query_timeout_seconds"] = 30
    return data


def build_datasource_context(
    ds: Datasource | None,
    *,
    allowed_tables: list[str] | None = None,
    schema_version: str | None = None,
) -> dict[str, Any] | None:
    """构建问数链路透传的数据源上下文。"""
    if ds is None:
        return None
    db_type = normalize_db_type(getattr(ds, "db_type", None))
    capability = CAPABILITIES.get(db_type)
    dialect = getattr(ds, "dialect", None) or (capability.dialect if capability else db_type)
    context = DatasourceContext(
        datasource_id=getattr(ds, "id", None),
        db_type=db_type,
        dialect=dialect,
        driver=getattr(ds, "driver", None) or (capability.driver if capability else None),
        default_schema=getattr(ds, "default_schema", None)
        or (capability.default_schema if capability else None),
        allowed_tables=allowed_tables or [],
        query_timeout_seconds=int(getattr(ds, "query_timeout_seconds", None) or 30),
        schema_version=schema_version,
    )
    return asdict(context)


def create_engine_for_datasource(ds: Datasource) -> Engine:
    """为指定数据源创建 SQLAlchemy Engine。"""
    adapter = get_adapter(getattr(ds, "db_type", None))
    return adapter.create_engine(ds)


def test_connection(ds: Datasource) -> dict[str, Any]:
    """测试数据源连接，返回统一诊断结构。"""
    try:
        adapter = get_adapter(getattr(ds, "db_type", None))
    except ValueError as exc:
        diagnostic = _diagnostic("UNSUPPORTED_DB_TYPE", "当前数据源类型尚未注册", exc)
        return {"ok": False, "message": diagnostic["message"], **diagnostic}
    try:
        if not adapter.driver_available():
            diagnostic = _diagnostic(
                "DRIVER_MISSING",
                f"{adapter.capability.label} 驱动未安装",
                adapter.capability.driver_module,
            )
            return {
                "ok": False,
                "message": diagnostic["message"],
                "db_type": adapter.capability.db_type,
                "dialect": adapter.capability.dialect,
                "driver": adapter.capability.driver,
                "driver_status": "missing",
                "schema_readable": False,
                "diagnostic": diagnostic,
                **diagnostic,
            }
        return adapter.test_connection(ds)
    except Exception as exc:
        diagnostic = _classify_exception(exc, default_code="CONNECTION_FAILED")
        return {
            "ok": False,
            "message": diagnostic["message"],
            "db_type": adapter.capability.db_type,
            "dialect": adapter.capability.dialect,
            "driver": adapter.capability.driver,
            "driver_status": "available" if adapter.driver_available() else "missing",
            "schema_readable": False,
            "diagnostic": diagnostic,
            **diagnostic,
        }


def sync_source_tables(ds: Datasource) -> dict[str, Any]:
    """连接数据源，拉取所有表和字段信息。"""
    try:
        return get_adapter(getattr(ds, "db_type", None)).sync_source_tables(ds)
    except ValueError as exc:
        raise RuntimeError(_diagnostic("UNSUPPORTED_DB_TYPE", "当前数据源类型尚未注册", exc))
    except Exception as exc:
        diagnostic = _classify_exception(exc, default_code="SCHEMA_UNREADABLE")
        raise RuntimeError(diagnostic)


def get_schemas(ds: Datasource) -> list[str]:
    """获取数据源中的 schema/database 列表。"""
    try:
        return get_adapter(getattr(ds, "db_type", None)).get_schemas(ds)
    except ValueError as exc:
        raise RuntimeError(_diagnostic("UNSUPPORTED_DB_TYPE", "当前数据源类型尚未注册", exc))
    except Exception as exc:
        diagnostic = _classify_exception(exc, default_code="SCHEMA_UNREADABLE")
        raise RuntimeError(diagnostic)


def get_schema(ds: Datasource, schema_name: str = None) -> list[dict[str, Any]]:
    """获取指定 schema 的表和字段元信息。"""
    try:
        return get_adapter(getattr(ds, "db_type", None)).get_schema(ds, schema_name=schema_name)
    except ValueError as exc:
        raise RuntimeError(_diagnostic("UNSUPPORTED_DB_TYPE", "当前数据源类型尚未注册", exc))
    except Exception as exc:
        diagnostic = _classify_exception(exc, default_code="SCHEMA_UNREADABLE")
        raise RuntimeError(diagnostic)


def quote_identifier(name: str, db_type: str | None) -> str:
    """按数据源类型引用标识符。"""
    if not name:
        return name
    normalized = normalize_db_type(db_type)
    if normalized == "mysql":
        return f"`{name}`"
    if normalized in {"hive", "trino", "presto", "bigquery", "clickhouse"}:
        return f"`{name}`"
    if normalized == "sqlserver":
        return f"[{name}]"
    return f'"{name}"'


def _table_ref(schema: str | None, table: str, db_type: str | None) -> str:
    table_q = quote_identifier(table, db_type)
    if schema and normalize_db_type(db_type) not in {"mysql", "sqlite"}:
        return f"{quote_identifier(schema, db_type)}.{table_q}"
    return table_q


def preview_table(ds: Datasource, schema: str | None, table: str, limit: int = 5) -> dict[str, Any]:
    """从数据源实时查询某张表的前 N 条数据。"""
    db_type = normalize_db_type(getattr(ds, "db_type", None))
    engine = create_engine_for_datasource(ds)
    try:
        with engine.connect() as conn:
            table_ref = _table_ref(schema, table, db_type)
            sql = f"SELECT * FROM {table_ref} LIMIT :limit"
            if db_type == "oracle":
                sql = f"SELECT * FROM {table_ref} FETCH FIRST :limit ROWS ONLY"
            result = conn.execute(text(sql), {"limit": int(limit or 5)})
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
            return {"columns": columns, "rows": rows}
    except Exception as exc:
        diagnostic = _classify_exception(exc, default_code="UNKNOWN_DATASOURCE_ERROR")
        raise RuntimeError(diagnostic)
    finally:
        engine.dispose()
