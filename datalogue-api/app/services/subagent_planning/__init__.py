# ============================================================
# File Name   : __init__.py
# Description:
#   SubAgent 查询规划包的公共导出入口。
#
# Responsibilities:
#   - 暴露候选资产、查询计划和执行结果等稳定契约。
#   - 隔离 DatasetSubAgent 编排层与底层规划实现细节。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

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


_LAZY_EXPORTS = {
    "ALLOWED_CATALOG_ASSET_TYPES": ("app.services.subagent_planning.asset_catalog", "ALLOWED_CATALOG_ASSET_TYPES"),
    "AssetDetailRequest": ("app.services.subagent_planning.asset_detail", "AssetDetailRequest"),
    "AssetDetailResult": ("app.services.subagent_planning.asset_detail", "AssetDetailResult"),
    "AssetDetailService": ("app.services.subagent_planning.asset_detail", "AssetDetailService"),
    "PlannerDetailLoop": ("app.services.subagent_planning.detail_loop", "PlannerDetailLoop"),
    "PlannerLoopResult": ("app.services.subagent_planning.detail_loop", "PlannerLoopResult"),
    "build_allowed_asset_scope": ("app.services.subagent_planning.asset_catalog", "build_allowed_asset_scope"),
    "build_blueprint_reference_context": (
        "app.services.subagent_planning.execution",
        "build_blueprint_reference_context",
    ),
    "build_candidate_assets_from_context": (
        "app.services.subagent_planning.asset_recall",
        "build_candidate_assets_from_context",
    ),
    "build_clarify_result": ("app.services.subagent_planning.execution", "build_clarify_result"),
    "build_query_plan_compiler_context": (
        "app.services.subagent_planning.sql_context",
        "build_query_plan_compiler_context",
    ),
    "build_reject_result": ("app.services.subagent_planning.execution", "build_reject_result"),
    "build_rule_based_query_plan": ("app.services.subagent_planning.planner", "build_rule_based_query_plan"),
    "build_sql_generation_context": ("app.services.subagent_planning.sql_context", "build_sql_generation_context"),
    "plan_query": ("app.services.subagent_planning.planner", "plan_query"),
    "plan_query_with_detail_context": ("app.services.subagent_planning.planner", "plan_query_with_detail_context"),
    "project_lightweight_asset_catalog": (
        "app.services.subagent_planning.asset_catalog",
        "project_lightweight_asset_catalog",
    ),
    "recall_candidate_assets": ("app.services.subagent_planning.asset_recall", "recall_candidate_assets"),
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
    "ALLOWED_CATALOG_ASSET_TYPES",
    "AssetDetailRequest",
    "AssetDetailResult",
    "AssetDetailService",
    "CANDIDATE_ASSET_TYPES",
    "EXECUTION_STRATEGIES",
    "EXECUTION_SOURCES",
    "ExecutionSource",
    "PlannerDetailLoop",
    "PlannerLoopResult",
    "QUERY_TYPES",
    "CandidateAsset",
    "QueryPlan",
    "QueryPlanValidationError",
    "SubAgentEvent",
    "SubAgentResult",
    "build_allowed_asset_scope",
    "build_blueprint_reference_context",
    "build_candidate_assets_from_context",
    "build_clarify_result",
    "build_rule_based_query_plan",
    "build_reject_result",
    "build_query_plan_compiler_context",
    "build_sql_generation_context",
    "normalize_query_plan",
    "plan_query",
    "plan_query_with_detail_context",
    "project_lightweight_asset_catalog",
    "recall_candidate_assets",
    "validate_asset_detail_requests",
]
