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
    QUERY_TYPES,
    CandidateAsset,
    QueryPlan,
    QueryPlanValidationError,
    SubAgentEvent,
    SubAgentResult,
    normalize_query_plan,
)
from app.services.subagent_planning.asset_catalog import (
    ALLOWED_CATALOG_ASSET_TYPES,
    build_allowed_asset_scope,
    project_lightweight_asset_catalog,
)
from app.services.subagent_planning.asset_detail import (
    AssetDetailRequest,
    AssetDetailResult,
    AssetDetailService,
    validate_asset_detail_requests,
)
from app.services.subagent_planning.detail_loop import PlannerDetailLoop, PlannerLoopResult
from app.services.subagent_planning.asset_recall import (
    build_candidate_assets_from_context,
    recall_candidate_assets,
)
from app.services.subagent_planning.execution import (
    build_blueprint_reference_context,
    build_clarify_result,
    build_reject_result,
)
from app.services.subagent_planning.planner import build_fallback_query_plan, plan_query
from app.services.subagent_planning.sql_context import build_sql_generation_context

__all__ = [
    "ALLOWED_CATALOG_ASSET_TYPES",
    "AssetDetailRequest",
    "AssetDetailResult",
    "AssetDetailService",
    "CANDIDATE_ASSET_TYPES",
    "EXECUTION_STRATEGIES",
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
    "build_fallback_query_plan",
    "build_reject_result",
    "build_sql_generation_context",
    "normalize_query_plan",
    "plan_query",
    "project_lightweight_asset_catalog",
    "recall_candidate_assets",
    "validate_asset_detail_requests",
]
