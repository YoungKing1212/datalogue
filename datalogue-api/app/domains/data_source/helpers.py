# ============================================================
# File Name   : helpers.py
# Description:
#   数据源领域内部通用辅助函数。
#
# Responsibilities:
#   - 统一连接选项、系统 schema 和标识符引用规则。
#   - 为 adapter 与 service 共享无副作用的小工具，避免循环导入。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from typing import Any

from app.models.datasource import Datasource


SYSTEM_SCHEMAS = {
    "information_schema",
    "mysql",
    "performance_schema",
    "sys",
    "pg_catalog",
    "pg_toast",
}


def _connection_options(ds: Datasource) -> dict[str, Any]:
    """读取可选连接参数；非 dict 时降级为空，避免脏配置打断兼容路径。"""
    value = getattr(ds, "connection_options", None)
    return value if isinstance(value, dict) else {}


def quote_identifier(name: str, db_type: str | None) -> str:
    """按数据源类型引用标识符。"""
    if not name:
        return name
    from app.domains.data_source.adapters.registry import normalize_db_type  # 延迟导入，避免 registry/base 互相初始化。

    normalized = normalize_db_type(db_type)
    if normalized == "mysql":
        return f"`{name}`"
    if normalized in {"hive", "trino", "presto", "bigquery", "clickhouse"}:
        return f"`{name}`"
    if normalized == "sqlserver":
        return f"[{name}]"
    return f'"{name}"'


def _table_ref(schema: str | None, table: str, db_type: str | None) -> str:
    """拼接表引用；保持原 datasource 行为，不改变 MySQL/SQLite schema 处理。"""
    from app.domains.data_source.adapters.registry import normalize_db_type  # 延迟导入，避免启动期循环导入。

    table_q = quote_identifier(table, db_type)
    if schema and normalize_db_type(db_type) not in {"mysql", "sqlite"}:
        return f"{quote_identifier(schema, db_type)}.{table_q}"
    return table_q


__all__ = ["SYSTEM_SCHEMAS", "_connection_options", "_table_ref", "quote_identifier"]
