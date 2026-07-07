# ============================================================
# File Name   : query_plan_compiler.py
# Description:
#   查询计划到只读 SQL 的工具编译器。
#
# Responsibilities:
#   - 将语义查询计划（dict 格式）/ 资产上下文编译为执行层 SQL。
#   - 拒绝把 LLM 生成 SQL 或 direct_sql 当作执行依据。
#   - 输出 control_plane / query_artifact / trace 可复用的 tool_compiler 元数据。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

import logging
from typing import Any

from app.services.sql_dialect_adapter import (
    EXECUTION_SOURCE_TOOL_COMPILER,
    adapt_sql_for_execution,
    quote_identifier,
)

logger = logging.getLogger(__name__)

_EXECUTABLE_STRATEGIES = {"query_graph", "blueprint_as_reference"}
_LLM_SQL_KEYS = {"llm_sql", "direct_sql", "raw_sql", "sql"}
_METRIC_AGGREGATIONS = {"sum", "count", "avg", "min", "max", "count_distinct"}


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
    """识别模型 SQL 逃逸字段；命中即拒绝，避免绕过查询计划编译边界。"""

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


def _asset_table_name(asset: dict[str, Any]) -> str:
    metadata = asset.get("metadata")
    meta = metadata if isinstance(metadata, dict) else {}
    return str(meta.get("table_name") or asset.get("name") or "").strip()


def _asset_column_name(asset: dict[str, Any]) -> str:
    metadata = asset.get("metadata")
    meta = metadata if isinstance(metadata, dict) else {}
    return str(meta.get("column_name") or asset.get("name") or "").split(".")[-1].strip()


def _asset_ref_value(asset_ref: Any) -> str:
    text = str(asset_ref or "").strip()
    if ":" in text:
        return text.split(":", 1)[1].strip()
    return text


def _table_from_field_ref(asset_ref: Any, field_name: Any) -> str | None:
    raw = _asset_ref_value(asset_ref)
    field = str(field_name or "").strip()
    if field and raw.endswith(f".{field}"):
        table_name = raw[: -(len(field) + 1)].strip(".")
        return table_name or None
    if raw and "." not in raw:
        return raw
    return None


def _field_table_name(item: dict[str, Any], main_table: str) -> str:
    metadata = item.get("metadata")
    meta = metadata if isinstance(metadata, dict) else {}
    return str(
        meta.get("table_name")
        or item.get("table_name")
        or _table_from_field_ref(item.get("asset_ref"), item.get("field") or item.get("name"))
        or main_table
    ).strip()


def _field_column_name(item: dict[str, Any]) -> str:
    metadata = item.get("metadata")
    meta = metadata if isinstance(metadata, dict) else {}
    return str(meta.get("column_name") or item.get("field") or item.get("name") or "").split(".")[-1].strip()


def _table_schema_name(schema: dict[str, Any]) -> str:
    return str(schema.get("table_name") or schema.get("name") or schema.get("asset_id") or "").strip()


def _main_table(query_plan: dict[str, Any], sql_generation_context: dict[str, Any] | None) -> str | None:
    debug_payload = query_plan.get("debug")
    debug = debug_payload if isinstance(debug_payload, dict) else {}
    selected = str(debug.get("selected_main_table") or "").strip()
    if selected:
        return selected

    for asset in query_plan.get("selected_assets") or []:
        if not isinstance(asset, dict):
            continue
        table_name = _asset_table_name(asset)
        if table_name:
            return table_name

    context = sql_generation_context if isinstance(sql_generation_context, dict) else {}
    for schema in context.get("table_schemas") or []:
        if isinstance(schema, dict) and _table_schema_name(schema):
            return _table_schema_name(schema)
    return None


def _selected_field_assets(query_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        asset
        for asset in (query_plan.get("selected_assets") or [])
        if isinstance(asset, dict)
        and asset.get("asset_type") == "field"
        and _asset_column_name(asset)
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


def _sql_value_literal(value: Any) -> str:
    """将 Python 值转为 SQL 字面量，仅限字符串、数字和布尔类型。"""
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "NULL"
    # 兜底：非预期的复杂类型不进入 SQL
    return "NULL"


def _compile_where_clauses(
    filters: Any,
    main_table: str,
    dialect: str | None,
) -> list[str] | None:
    """将 query_plan.filters 列表编译为安全 WHERE 条件片段。

    遇到不支持的 operator 时 fail-closed 返回 None，避免过滤条件静默丢失导致查询返回过多行。
    """
    if not isinstance(filters, list) or not filters:
        return []

    clauses: list[str] = []
    for item in filters:
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("field") or "").strip()
        if not field_name:
            continue
        operator = str(item.get("operator") or "=").strip()
        value = item.get("value")
        # alias 是 QueryPlan 内部实体别名，不等于物理表名；优先使用 runtime 透传的 metadata。
        table_name = _field_table_name(item, main_table)
        column_ref = f"{quote_identifier(table_name, dialect)}.{quote_identifier(field_name, dialect)}"

        if operator == "between" and isinstance(value, list) and len(value) >= 2:
            clauses.append(
                f"{column_ref} BETWEEN {_sql_value_literal(value[0])} AND {_sql_value_literal(value[1])}"
            )
        elif operator == "in" and isinstance(value, list):
            if not value:
                continue
            in_values = ", ".join(_sql_value_literal(v) for v in value)
            clauses.append(f"{column_ref} IN ({in_values})")
        elif operator == "contains":
            safe_value = str(value).replace("%", r"\%").replace("_", r"\_").replace("'", "''")
            clauses.append(f"{column_ref} LIKE '%{safe_value}%' ESCAPE '\\'")
        elif operator in {"=", "!=", ">", ">=", "<", "<="}:
            clauses.append(f"{column_ref} {operator} {_sql_value_literal(value)}")
        else:
            # 未识别算子 fail-closed：避免过滤条件丢失导致返回过多行
            logger.warning("不支持的筛选算子，fail-closed 拒绝编译: %s", operator)
            return None
    return clauses


def _compile_order_clauses(
    ordering: Any,
    main_table: str,
    dialect: str | None,
) -> list[str]:
    """将 query_plan.ordering 编译为 ORDER BY 片段。"""
    if not isinstance(ordering, list) or not ordering:
        return []

    clauses: list[str] = []
    for item in ordering:
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("field") or "").strip()
        if not field_name:
            continue
        direction = str(item.get("direction") or "asc").upper()
        if direction not in {"ASC", "DESC"}:
            direction = "ASC"
        # 排序字段同样不能把 QueryPlan alias 当物理表名。
        table_name = _field_table_name(item, main_table)
        column_ref = f"{quote_identifier(table_name, dialect)}.{quote_identifier(field_name, dialect)}"
        clauses.append(f"{column_ref} {direction}")
    return clauses


def _compile_group_by_items(
    group_by: Any,
    main_table: str,
    dialect: str | None,
) -> tuple[list[str], list[str]]:
    """返回 SELECT 中的分组字段和 GROUP BY 子句字段。"""

    if not isinstance(group_by, list) or not group_by:
        return [], []

    select_items: list[str] = []
    group_clauses: list[str] = []
    for item in group_by:
        if not isinstance(item, dict):
            continue
        column_name = _field_column_name(item)
        if not column_name:
            continue
        table_name = _field_table_name(item, main_table)
        column_ref = f"{quote_identifier(table_name, dialect)}.{quote_identifier(column_name, dialect)}"
        label = str(item.get("display_name") or item.get("name") or column_name)
        select_items.append(f"{column_ref} AS {quote_identifier(label, dialect)}")
        group_clauses.append(column_ref)
    return select_items, group_clauses


def _compile_metric_select_items(
    metrics: Any,
    main_table: str,
    dialect: str | None,
) -> list[str]:
    """将 QueryPlan metrics 编译为聚合 SELECT 片段。"""

    if not isinstance(metrics, list) or not metrics:
        return []

    select_items: list[str] = []
    for item in metrics:
        if not isinstance(item, dict):
            continue
        column_name = _field_column_name(item)
        aggregation = str(item.get("aggregation") or "").lower().strip()
        if not column_name or aggregation not in _METRIC_AGGREGATIONS:
            continue
        table_name = _field_table_name(item, main_table)
        column_ref = f"{quote_identifier(table_name, dialect)}.{quote_identifier(column_name, dialect)}"
        label = str(item.get("display_name") or column_name)
        if aggregation == "count_distinct":
            expression = f"COUNT(DISTINCT {column_ref})"
        elif aggregation == "count":
            expression = f"COUNT({column_ref})"
        else:
            expression = f"{aggregation.upper()}({column_ref})"
        select_items.append(f"{expression} AS {quote_identifier(label, dialect)}")
    return select_items


def _safe_limit(limit: Any) -> int | None:
    """安全地提取 LIMIT 值，限制在 1-500 范围。"""
    if limit is None:
        return None
    try:
        value = int(limit)
        return max(1, min(value, 500))
    except (TypeError, ValueError):
        return None


def _compile_select_sql(
    *,
    query_plan: dict[str, Any],
    sql_generation_context: dict[str, Any] | None,
    dialect: str | None,
) -> str | None:
    """从查询计划资产引用生成最小可执行 SELECT；不读取任何模型 SQL 文本。"""

    main_table = _main_table(query_plan, sql_generation_context)
    if not main_table:
        return None

    group_select_items, group_clauses = _compile_group_by_items(
        query_plan.get("group_by"),
        main_table,
        dialect,
    )
    metric_items = _compile_metric_select_items(query_plan.get("metrics"), main_table, dialect)
    selected_fields = _selected_field_assets(query_plan)
    select_items: list[str] = []
    select_items.extend(group_select_items)
    select_items.extend(metric_items)
    for asset in selected_fields:
        table_name = _asset_table_name(asset) or main_table
        column_name = _asset_column_name(asset)
        label = str(asset.get("display_name") or asset.get("name") or column_name)
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

    sql = f"SELECT {', '.join(select_items)} FROM {quote_identifier(main_table, dialect)}"

    # 从 query_plan.filters 生成安全 WHERE 子句
    where_clauses = _compile_where_clauses(query_plan.get("filters"), main_table, dialect)
    if where_clauses is None:
        return None
    if where_clauses:
        sql += f" WHERE {' AND '.join(where_clauses)}"

    if group_clauses:
        sql += f" GROUP BY {', '.join(group_clauses)}"

    # 支持 ORDER BY
    order_clauses = _compile_order_clauses(query_plan.get("ordering"), main_table, dialect)
    if order_clauses:
        sql += f" ORDER BY {', '.join(order_clauses)}"

    # 支持 LIMIT
    limit = _safe_limit(query_plan.get("limit"))
    if limit is not None:
        sql += f" LIMIT {limit}"

    return sql


def _success_payload(
    *,
    query_plan: dict[str, Any],
    adapted: dict[str, Any],
) -> dict[str, Any]:
    sql = adapted["sql"]
    control_plane = {
        "execution_source": EXECUTION_SOURCE_TOOL_COMPILER,
        "status": "compiled",
        "query_type": query_plan.get("query_type"),
        "execution_strategy": query_plan.get("execution_strategy"),
        "dialect": adapted["dialect"],
    }
    query_artifact = {
        "kind": "compiled_sql",
        "execution_source": EXECUTION_SOURCE_TOOL_COMPILER,
        "sql": sql,
        "sql_list": [sql],
        "query_plan": query_plan,
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
    query_plan: dict[str, Any],
    sql_generation_context: dict[str, Any] | None,
    dialect: str | None,
    current_datasource_dialect: str | None = None,
    query_constraints: dict[str, Any] | None = None,
    allowed_tables: list[str] | None = None,
) -> dict[str, Any]:
    """编译语义查询计划，返回执行层可使用的 SQL patch。

    `sql_generation_context` 只能提供表结构、字段、指标/维度定义等语义资产；一旦出现
    `llm_sql` / `direct_sql` / `raw_sql` / `sql` 字段，说明上游试图把模型 SQL 作为执行依据，
    本编译器必须 fail closed。
    """

    execution_strategy = query_plan.get("execution_strategy")
    if execution_strategy not in _EXECUTABLE_STRATEGIES:
        return _failure(
            code="UNSUPPORTED_STRATEGY",
            error=f"当前执行策略不支持工具编译：{execution_strategy}",
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
            error="查询计划缺少可编译的表字段资产",
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
