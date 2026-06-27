# ============================================================
# File Name   : query_plan_compiler.py
# Description:
#   QueryPlan 到只读 SQL 的工具编译器。
#
# Responsibilities:
#   - 将 DatasetSubAgent 内部 QueryPlan / 资产上下文编译为执行层 SQL。
#   - 拒绝把 LLM 生成 SQL 或 direct_sql 当作执行依据。
#   - 输出 control_plane / query_artifact / trace 可复用的 tool_compiler 元数据。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

from typing import Any

from app.services.sql_dialect_adapter import (
    EXECUTION_SOURCE_TOOL_COMPILER,
    adapt_sql_for_execution,
    quote_identifier,
)
from app.services.subagent_planning.contracts import CandidateAsset, QueryPlan

_EXECUTABLE_STRATEGIES = {"query_graph", "blueprint_as_reference"}
_LLM_SQL_KEYS = {"llm_sql", "direct_sql", "raw_sql", "sql"}


def _failure(
    *,
    code: str,
    error: str,
    dialect: str | None = None,
    sql_guard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "code": code,
        "error": error,
        "sql": None,
        "sql_list": [],
        "dialect": dialect,
        "execution_source": EXECUTION_SOURCE_TOOL_COMPILER,
        "sql_guard": sql_guard,
        "warnings": [],
        "control_plane": {"execution_source": EXECUTION_SOURCE_TOOL_COMPILER, "status": "blocked", "code": code},
        "query_artifact": None,
        "trace": {"execution_source": EXECUTION_SOURCE_TOOL_COMPILER, "status": "blocked", "code": code},
    }


def _contains_llm_sql_payload(value: Any, depth: int = 0) -> bool:
    """识别模型 SQL 逃逸字段；命中即拒绝，避免绕过 QueryPlan 编译边界。"""

    if depth > 4:
        return False
    if isinstance(value, dict):
        for key, item in value.items():
            key_lower = str(key).lower()
            if key_lower in _LLM_SQL_KEYS and isinstance(item, str) and item.strip():
                return True
            if _contains_llm_sql_payload(item, depth + 1):
                return True
    if isinstance(value, list):
        return any(_contains_llm_sql_payload(item, depth + 1) for item in value)
    return False


def _asset_table_name(asset: CandidateAsset) -> str:
    return str((asset.metadata or {}).get("table_name") or asset.name or "").strip()


def _asset_column_name(asset: CandidateAsset) -> str:
    return str((asset.metadata or {}).get("column_name") or asset.name or "").split(".")[-1].strip()


def _table_schema_name(schema: dict[str, Any]) -> str:
    return str(schema.get("table_name") or schema.get("name") or schema.get("asset_id") or "").strip()


def _main_table(query_plan: QueryPlan, sql_generation_context: dict[str, Any] | None) -> str | None:
    debug = query_plan.debug if isinstance(query_plan.debug, dict) else {}
    selected = str(debug.get("selected_main_table") or "").strip()
    if selected:
        return selected

    for asset in query_plan.selected_assets:
        table_name = _asset_table_name(asset)
        if table_name:
            return table_name

    context = sql_generation_context if isinstance(sql_generation_context, dict) else {}
    for schema in context.get("table_schemas") or []:
        if isinstance(schema, dict) and _table_schema_name(schema):
            return _table_schema_name(schema)
    return None


def _selected_field_assets(query_plan: QueryPlan) -> list[CandidateAsset]:
    return [
        asset
        for asset in query_plan.selected_assets
        if asset.asset_type == "field" and _asset_column_name(asset)
    ]


def _fallback_schema_fields(
    sql_generation_context: dict[str, Any] | None,
    main_table: str,
) -> list[dict[str, Any]]:
    context = sql_generation_context if isinstance(sql_generation_context, dict) else {}
    for schema in context.get("table_schemas") or []:
        if not isinstance(schema, dict) or _table_schema_name(schema) != main_table:
            continue
        fields = schema.get("fields") or schema.get("columns") or []
        return [field for field in fields if isinstance(field, dict)]
    return []


def _compile_select_sql(
    *,
    query_plan: QueryPlan,
    sql_generation_context: dict[str, Any] | None,
    dialect: str | None,
) -> str | None:
    """从 QueryPlan 资产引用生成最小可执行 SELECT；不读取任何模型 SQL 文本。"""

    main_table = _main_table(query_plan, sql_generation_context)
    if not main_table:
        return None

    selected_fields = _selected_field_assets(query_plan)
    select_items: list[str] = []
    for asset in selected_fields:
        table_name = _asset_table_name(asset) or main_table
        column_name = _asset_column_name(asset)
        label = str(asset.display_name or asset.name or column_name)
        select_items.append(
            f"{quote_identifier(table_name, dialect)}.{quote_identifier(column_name, dialect)} "
            f"AS {quote_identifier(label, dialect)}"
        )

    if not select_items:
        # 无字段资产时只回退到已水合 table_schema 的前 8 个字段，避免 SELECT * 扩大暴露面。
        for field in _fallback_schema_fields(sql_generation_context, main_table)[:8]:
            column_name = str(field.get("column_name") or field.get("name") or "").strip()
            if not column_name:
                continue
            label = str(field.get("display_name") or field.get("comment") or column_name)
            select_items.append(
                f"{quote_identifier(main_table, dialect)}.{quote_identifier(column_name, dialect)} "
                f"AS {quote_identifier(label, dialect)}"
            )

    if not select_items:
        return None
    return f"SELECT {', '.join(select_items)} FROM {quote_identifier(main_table, dialect)}"


def _success_payload(
    *,
    query_plan: QueryPlan,
    adapted: dict[str, Any],
) -> dict[str, Any]:
    sql = adapted["sql"]
    control_plane = {
        "execution_source": EXECUTION_SOURCE_TOOL_COMPILER,
        "status": "compiled",
        "query_type": query_plan.query_type,
        "execution_strategy": query_plan.execution_strategy,
        "dialect": adapted["dialect"],
    }
    query_artifact = {
        "kind": "compiled_sql",
        "execution_source": EXECUTION_SOURCE_TOOL_COMPILER,
        "sql": sql,
        "sql_list": [sql],
        "query_plan": query_plan.to_dict(),
        "sql_guard": adapted["sql_guard"],
    }
    trace = {
        "execution_source": EXECUTION_SOURCE_TOOL_COMPILER,
        "status": "compiled",
        "dialect": adapted["dialect"],
        "sql_guard_code": adapted["sql_guard"].get("code"),
        "sql_guard_warnings": adapted["warnings"],
    }
    return {
        "ok": True,
        "code": None,
        "error": None,
        "sql": sql,
        "sql_list": [sql],
        "dialect": adapted["dialect"],
        "execution_source": EXECUTION_SOURCE_TOOL_COMPILER,
        "sql_guard": adapted["sql_guard"],
        "warnings": adapted["warnings"],
        "control_plane": control_plane,
        "query_artifact": query_artifact,
        "trace": trace,
    }


def compile_query_plan_to_sql(
    *,
    query_plan: QueryPlan,
    sql_generation_context: dict[str, Any] | None,
    dialect: str | None,
    current_datasource_dialect: str | None = None,
    query_constraints: dict[str, Any] | None = None,
    allowed_tables: list[str] | None = None,
) -> dict[str, Any]:
    """编译 DatasetSubAgent 内部语义计划，返回执行层可使用的 SQL patch。

    `sql_generation_context` 只能提供表结构、字段、指标/维度定义等语义资产；一旦出现
    `llm_sql` / `direct_sql` / `raw_sql` / `sql` 字段，说明上游试图把模型 SQL 作为执行依据，
    本编译器必须 fail closed。
    """

    if query_plan.execution_strategy not in _EXECUTABLE_STRATEGIES:
        return _failure(
            code="UNSUPPORTED_STRATEGY",
            error=f"当前执行策略不支持工具编译：{query_plan.execution_strategy}",
            dialect=dialect,
        )

    if _contains_llm_sql_payload(sql_generation_context):
        return _failure(
            code="LLM_SQL_NOT_EXECUTABLE",
            error="LLM 生成 SQL 只能作为语义计划输入，不能直接作为执行 SQL",
            dialect=dialect,
        )

    sql = _compile_select_sql(
        query_plan=query_plan,
        sql_generation_context=sql_generation_context,
        dialect=dialect,
    )
    if not sql:
        return _failure(
            code="PLAN_NOT_COMPILABLE",
            error="QueryPlan 缺少可编译的表字段资产",
            dialect=dialect,
        )

    adapted = adapt_sql_for_execution(
        sql,
        dialect=dialect,
        current_datasource_dialect=current_datasource_dialect or dialect,
        query_constraints=query_constraints,
        allowed_tables=allowed_tables,
    )
    if not adapted["ok"]:
        return _failure(
            code=adapted.get("code") or "SQL_GUARD_BLOCKED",
            error=adapted.get("error") or "SQL Guard 拦截",
            dialect=adapted.get("dialect") or dialect,
            sql_guard=adapted.get("sql_guard"),
        )
    return _success_payload(query_plan=query_plan, adapted=adapted)
