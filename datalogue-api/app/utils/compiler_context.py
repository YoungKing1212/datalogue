# ============================================================
# File Name   : compiler_context.py
# Description:
#   查询计划编译器上下文裁剪工具。
#
# Responsibilities:
#   - 从 sql_generation_context 中提取编译器安全可见的语义资产键。
#   - 显式排除 SQL 文本逃逸字段（llm_sql / direct_sql / raw_sql / sql / sql_template）。
#
# Author      : yangkai
# ============================================================

from __future__ import annotations

from copy import deepcopy
from typing import Any

COMPILER_CONTEXT_KEYS = {
    "selected_assets",
    "reference_assets",
    "table_schemas",
    "field_search_results",
    "metric_definitions",
    "dimension_definitions",
    "blueprint_references",
    "coverage",
    "risk_flags",
    "schema_version",
    "manifest_version",
}
SQL_LIKE_CONTEXT_KEYS = {"sql", "raw_sql", "direct_sql", "llm_sql", "sql_template"}


def build_query_plan_compiler_context(sql_generation_context: dict[str, Any] | None) -> dict[str, Any]:
    """裁剪给工具编译器的上下文，显式排除任何 SQL 文本逃逸字段。"""

    source = sql_generation_context if isinstance(sql_generation_context, dict) else {}
    compiler_context: dict[str, Any] = {}
    for key, value in source.items():
        if key in SQL_LIKE_CONTEXT_KEYS:
            continue  # 编译器只能读取语义资产和 schema，不能读取模型或蓝图 SQL 文本。
        if key in COMPILER_CONTEXT_KEYS:
            compiler_context[key] = deepcopy(value)
    return compiler_context
