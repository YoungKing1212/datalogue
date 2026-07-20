# ============================================================
# File Name   : sql_identifiers.py
# Description:
#   跨领域共享的 SQL 标识符引用与转义工具。
#
# Responsibilities:
#   - 按数据库方言选择标识符引号。
#   - 转义标识符内部的闭合引号，避免各执行链路行为漂移。
#
# Author      : yangkai
# Created On  : 2026-07-17
# ============================================================

from __future__ import annotations


BACKTICK_DIALECTS = {
    "mysql",
    "sqlite",
    "hive",
    "trino",
    "presto",
    "bigquery",
    "clickhouse",
    "doris",
    "mariadb",
}
BRACKET_DIALECTS = {"tsql", "sqlserver", "mssql"}


def quote_identifier(name: str | None, dialect: str | None) -> str:
    """按方言引用并转义标识符；空值返回空串，由调用方决定是否输出。"""

    if not name:
        return ""
    normalized = str(dialect or "").strip().lower()
    if normalized in BACKTICK_DIALECTS:
        return f"`{name.replace('`', '``')}`"
    if normalized in BRACKET_DIALECTS:
        return f"[{name.replace(']', ']]')}]"
    return f'"{name.replace(chr(34), chr(34) * 2)}"'


__all__ = ["BACKTICK_DIALECTS", "BRACKET_DIALECTS", "quote_identifier"]
