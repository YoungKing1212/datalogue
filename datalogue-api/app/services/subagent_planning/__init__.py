# ============================================================
# File Name   : __init__.py
# Description:
#   SubAgent 查询规划包的公共导出入口。
#
# Responsibilities:
#   - 暴露当前 Dataset Query Skill 仍使用的查询计划契约。
#   - 保留 planner / asset_detail 的历史导入路径，移除旧 SubAgent 编排导出。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from copy import deepcopy
from typing import Any

from app.services.subagent_planning.contracts import (
    CANDIDATE_ASSET_TYPES,
    EXECUTION_STRATEGIES,
    EXECUTION_SOURCES,
    QUERY_TYPES,
    CandidateAsset,
    ExecutionSource,
    QueryPlan,
    QueryPlanValidationError,
    SubAgentEvent,
    SubAgentResult,
    normalize_query_plan,
)

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


_LAZY_EXPORTS = {
    "AssetDetailRequest": ("app.services.subagent_planning.asset_detail", "AssetDetailRequest"),
    "AssetDetailResult": ("app.services.subagent_planning.asset_detail", "AssetDetailResult"),
    "AssetDetailService": ("app.services.subagent_planning.asset_detail", "AssetDetailService"),
    "build_rule_based_query_plan": ("app.services.subagent_planning.planner", "build_rule_based_query_plan"),
    "plan_query": ("app.services.subagent_planning.planner", "plan_query"),
    "plan_query_with_detail_context": ("app.services.subagent_planning.planner", "plan_query_with_detail_context"),
    "validate_asset_detail_requests": (
        "app.services.subagent_planning.asset_detail",
        "validate_asset_detail_requests",
    ),
}


def __getattr__(name: str):
    """延迟加载规划器/graph 相关导出，避免 compiler 冷启动导入 contracts 时形成循环。"""

    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module_name, attr_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value

__all__ = [
    "AssetDetailRequest",
    "AssetDetailResult",
    "AssetDetailService",
    "CANDIDATE_ASSET_TYPES",
    "EXECUTION_STRATEGIES",
    "EXECUTION_SOURCES",
    "ExecutionSource",
    "QUERY_TYPES",
    "CandidateAsset",
    "QueryPlan",
    "QueryPlanValidationError",
    "SubAgentEvent",
    "SubAgentResult",
    "build_rule_based_query_plan",
    "build_query_plan_compiler_context",
    "normalize_query_plan",
    "plan_query",
    "plan_query_with_detail_context",
    "validate_asset_detail_requests",
]
