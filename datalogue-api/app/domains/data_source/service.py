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
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.domains.data_source.adapters.registry import (
    ADAPTERS,
    CAPABILITIES,
    get_adapter,
    normalize_db_type,
)
from app.domains.data_source.context import DatasourceContext
from app.domains.data_source.diagnostics import (
    _classify_exception,
    _diagnostic,
)
from app.core.models.datasource import Datasource
from app.domains.data_source.helpers import _table_ref


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
    # 仅补齐默认值时不覆盖用户显式设置的 dialect；Doris → mysql 映射由 normalize_execution_dialect 负责。
    if data.get("dialect"):
        data["dialect"] = normalize_execution_dialect(db_type, str(data["dialect"]).strip().lower())
    else:
        data["dialect"] = normalize_execution_dialect(db_type)
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


def normalize_execution_dialect(db_type: str | None, dialect: str | None = None) -> str:
    """归一化真实执行方言；Doris/MariaDB 等 MySQL 兼容产品固定落到 MySQL 执行方言。"""
    normalized_db_type = normalize_db_type(db_type)
    if normalized_db_type in ("doris",):
        return "mysql"
    if dialect:
        cleaned = str(dialect).strip().lower()
        if cleaned in ("mariadb",):
            return "mysql"
        return cleaned
    capability = CAPABILITIES.get(normalized_db_type)
    return capability.dialect if capability else normalized_db_type


def resolve_schema_name(ds: Datasource, schema_name: str | None = None) -> str | None:
    """解析数据源实际使用的 Schema，显式选择优先于产品默认值。"""

    explicit = str(schema_name or "").strip()
    if explicit:
        return explicit
    configured = str(getattr(ds, "default_schema", None) or "").strip()
    if configured:
        return configured
    db_type = normalize_db_type(getattr(ds, "db_type", None))
    capability = CAPABILITIES.get(db_type)
    capability_default = str(getattr(capability, "default_schema", None) or "").strip()
    if capability_default:
        return capability_default
    options = getattr(ds, "connection_options", None)
    options = options if isinstance(options, dict) else {}
    if db_type in {"trino", "presto"}:
        return str(options.get("schema") or "").strip() or None
    if db_type == "bigquery":
        return str(options.get("dataset") or "").strip() or None
    if db_type == "oracle":
        return str(getattr(ds, "username", None) or "").strip().upper() or None
    # MySQL/Doris 的 Schema 即 database；其他兼容数据源也保留 database_name 兜底。
    return str(getattr(ds, "database_name", None) or "").strip() or None


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
    dialect = normalize_execution_dialect(
        db_type,
        getattr(ds, "dialect", None) or (capability.dialect if capability else db_type),
    )
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


def configure_statement_timeout(conn, ds: Datasource):
    """为单次预览连接设置数据库侧语句超时；不支持的方言保留驱动默认值。"""

    timeout_seconds = max(1, min(int(getattr(ds, "query_timeout_seconds", None) or 30), 300))
    timeout_ms = timeout_seconds * 1000
    db_type = normalize_db_type(getattr(ds, "db_type", None))
    driver_connection = getattr(getattr(conn, "connection", None), "driver_connection", None)
    if db_type in {"postgres", "postgresql"}:
        conn.execute(text("SET LOCAL statement_timeout = :timeout_ms"), {"timeout_ms": timeout_ms})
    elif db_type in {"mysql", "doris"}:
        # 超时值先转为受限整数，避免 SET 语句不能绑定参数时重新引入拼接风险。
        conn.execute(text(f"SET SESSION MAX_EXECUTION_TIME = {timeout_ms}"), {})
    elif db_type == "oracle":
        if driver_connection is not None and hasattr(driver_connection, "call_timeout"):
            driver_connection.call_timeout = timeout_ms
    elif db_type == "sqlite" and driver_connection is not None and hasattr(
        driver_connection, "set_progress_handler"
    ):
        deadline = time.monotonic() + timeout_seconds
        driver_connection.set_progress_handler(
            lambda: 1 if time.monotonic() >= deadline else 0,
            1000,
        )
    if hasattr(conn, "execution_options"):
        return conn.execution_options(timeout=timeout_seconds)
    return conn


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


def sync_source_tables(ds: Datasource, schema_name: str | None = None) -> dict[str, Any]:
    """连接数据源，拉取指定 Schema 的表和字段信息。"""
    try:
        schema = resolve_schema_name(ds, schema_name)
        return get_adapter(getattr(ds, "db_type", None)).sync_source_tables(ds, schema_name=schema)
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


def get_schema(ds: Datasource, schema_name: str | None = None) -> list[dict[str, Any]]:
    """获取指定 schema 的表和字段元信息。"""
    try:
        return get_adapter(getattr(ds, "db_type", None)).get_schema(ds, schema_name=schema_name)
    except ValueError as exc:
        raise RuntimeError(_diagnostic("UNSUPPORTED_DB_TYPE", "当前数据源类型尚未注册", exc))
    except Exception as exc:
        diagnostic = _classify_exception(exc, default_code="SCHEMA_UNREADABLE")
        raise RuntimeError(diagnostic)


def preview_table(ds: Datasource, schema: str | None, table: str, limit: int = 5) -> dict[str, Any]:
    """从数据源实时查询某张表的前 N 条数据。"""
    db_type = normalize_db_type(getattr(ds, "db_type", None))
    safe_limit = max(1, min(int(limit or 5), 100))  # 预览是诊断能力，绝不能演变成全表导出通道。
    engine = create_engine_for_datasource(ds)
    try:
        with engine.connect() as conn:
            conn = configure_statement_timeout(conn, ds)
            table_ref = _table_ref(schema, table, db_type)
            sql = f"SELECT * FROM {table_ref} LIMIT :limit"
            if db_type == "oracle":
                sql = f"SELECT * FROM {table_ref} FETCH FIRST :limit ROWS ONLY"
            result = conn.execute(text(sql), {"limit": safe_limit})
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
            return {"columns": columns, "rows": rows}
    except Exception as exc:
        diagnostic = _classify_exception(exc, default_code="UNKNOWN_DATASOURCE_ERROR")
        raise RuntimeError(diagnostic)
    finally:
        engine.dispose()
