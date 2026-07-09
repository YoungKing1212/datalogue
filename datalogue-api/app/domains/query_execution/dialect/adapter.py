# ============================================================
# File Name   : adapter.py
# Description:
#   查询执行领域的 SQL 方言适配外壳。
#
# Responsibilities:
#   - 对工具编译器产出的 SQL 做当前阶段允许方言的 fail-closed 校验。
#   - 复用 SQL Guard 守住只读、单语句、授权表和 LIMIT 边界。
#   - 返回稳定的 execution_source=tool_compiler 执行来源标记。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.domains.query_execution.dialect.names import quote_ident
from app.domains.query_execution.guard import guard_readonly_sql

EXECUTION_SOURCE_TOOL_COMPILER = "tool_compiler"

_DIALECT_ALIASES = {
    "doris": "mysql",
    "mariadb": "mysql",
}
_SUPPORTED_DIALECTS = {"mysql", "oracle", "sqlite"}
_CURRENT_DATASOURCE_DIALECT_ERROR = "DIALECT_UNSUPPORTED_FOR_CURRENT_DATASOURCE"


def normalize_execution_dialect(dialect: str | None) -> str | None:
    """归一化服务端执行方言别名；未知值原样返回，交给调用方边界处理。"""

    normalized = str(dialect or "").strip().lower()
    if not normalized:
        return None
    return _DIALECT_ALIASES.get(normalized, normalized)


def normalize_supported_dialect(dialect: str | None) -> str | None:
    """归一化当前阶段真实启用的数据源方言；未知值必须 fail closed。"""

    normalized = normalize_execution_dialect(dialect)
    if not normalized:
        return None
    return normalized if normalized in _SUPPORTED_DIALECTS else None


def quote_identifier(name: str | None, dialect: str | None) -> str:
    """只在已支持方言内生成 identifier 引号，避免未知方言误适配。"""

    supported = normalize_supported_dialect(dialect)
    if not supported:
        return str(name or "")
    return quote_ident(name, supported) or str(name or "")


def _unsupported_dialect_result(dialect: str | None, current_datasource_dialect: str | None) -> dict[str, Any]:
    error = (
        "查询计划目标方言与当前数据源方言不一致或当前数据源方言未启用："
        f"target={dialect or 'unknown'}, current={current_datasource_dialect or 'unknown'}"
    )
    return {
        "ok": False,
        "code": _CURRENT_DATASOURCE_DIALECT_ERROR,
        "error": error,
        "sql": None,
        "dialect": None,
        "execution_source": EXECUTION_SOURCE_TOOL_COMPILER,
        "sql_guard": {
            "ok": False,
            "normalized_sql": None,
            "code": _CURRENT_DATASOURCE_DIALECT_ERROR,
            "error": error,
            "keyword": None,
            "warnings": [],
        },
        "warnings": [],
    }


def adapt_sql_for_execution(
    sql: str | None,
    *,
    dialect: str | None,
    current_datasource_dialect: str | None = None,
    query_constraints: dict[str, Any] | None = None,
    allowed_tables: list[str] | None = None,
) -> dict[str, Any]:
    """将工具编译 SQL 适配到执行层可接收形态，并强制经过 SQL Guard。

    这里不接受模型生成 SQL 的来源判断，只处理上游已确认为 tool compiler 的 SQL；
    运行期只允许当前选中数据源 dialect；查询计划目标方言与当前数据源不一致时 fail closed。
    """

    supported = normalize_supported_dialect(dialect)
    current_supported = normalize_supported_dialect(current_datasource_dialect or dialect)
    if not supported or not current_supported or supported != current_supported:
        return _unsupported_dialect_result(dialect, current_datasource_dialect or dialect)

    guard_result = guard_readonly_sql(
        sql,
        dialect=supported,
        query_constraints=query_constraints,
        allowed_tables=allowed_tables,
    )
    guard_payload = asdict(guard_result)
    if not guard_result.ok:
        return {
            "ok": False,
            "code": guard_result.code,
            "error": guard_result.error,
            "sql": None,
            "dialect": supported,
            "execution_source": EXECUTION_SOURCE_TOOL_COMPILER,
            "sql_guard": guard_payload,
            "warnings": guard_result.warnings,
        }

    return {
        "ok": True,
        "code": None,
        "error": None,
        "sql": guard_result.normalized_sql or (sql or "").strip(),
        "dialect": supported,
        "execution_source": EXECUTION_SOURCE_TOOL_COMPILER,
        "sql_guard": guard_payload,
        "warnings": guard_result.warnings,
    }
