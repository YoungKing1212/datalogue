# ============================================================
# File Name   : planner.py
# Description:
#   DatasetSubAgent 查询规划的规则兜底 planner。
#
# Responsibilities:
#   - 在 LLM 规划不可用或置信不足时，根据候选资产生成保守查询计划。
#   - 支持明细查询、指标查询和蓝图缺参澄清的基础规则分流。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.subagent_planning.contracts import (
    CANDIDATE_ASSET_TYPES,
    CandidateAsset,
    QueryPlan,
    QueryPlanValidationError,
)

DETAIL_PATTERNS = ("明细", "列表", "日志", "记录", "最近", "前", "条", "limit")
METRIC_PATTERNS = ("统计", "数量", "总数", "平均", "占比", "汇总", "趋势")
BLUEPRINT_PATTERNS = ("日报", "周报", "月报", "分析", "报告")


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    normalized = str(text or "").lower()
    return any(pattern.lower() in normalized for pattern in patterns)


CandidateAssetInput = list[dict[str, Any] | CandidateAsset] | dict[str, Any] | None


def _asset_items(candidate_assets: CandidateAssetInput) -> list[dict[str, Any] | CandidateAsset]:
    if isinstance(candidate_assets, dict):
        items = candidate_assets.get("assets")
        return items if isinstance(items, list) else []
    if isinstance(candidate_assets, list):
        return candidate_assets
    return []


def _assets(candidate_assets: CandidateAssetInput) -> list[CandidateAsset]:
    assets: list[CandidateAsset] = []
    for item in _asset_items(candidate_assets):
        try:
            if isinstance(item, CandidateAsset):
                if item.asset_type in CANDIDATE_ASSET_TYPES:
                    assets.append(item)
                continue
            if not isinstance(item, dict):
                continue
            assets.append(CandidateAsset.from_dict(item))
        except (QueryPlanValidationError, TypeError, ValueError):
            continue
    return assets


def _parameter_items(parameters: Any) -> list[dict[str, Any]]:
    if isinstance(parameters, list):
        return [parameter for parameter in parameters if isinstance(parameter, dict)]
    if not isinstance(parameters, dict):
        return []

    items: list[dict[str, Any]] = []
    properties = parameters.get("properties")
    required_names = parameters.get("required")
    required_set = {str(name) for name in required_names} if isinstance(required_names, list) else set()
    if isinstance(properties, dict):
        for name, spec in properties.items():
            item = dict(spec) if isinstance(spec, dict) else {}
            item.setdefault("name", name)
            if name in required_set:
                item["required"] = True
            items.append(item)

    for name, spec in parameters.items():
        if name in {"properties", "required"}:
            continue
        if isinstance(spec, dict):
            item = dict(spec)
            item.setdefault("name", name)
            items.append(item)
        elif isinstance(spec, bool):
            items.append({"name": name, "required": spec})
    return items


def _routing_has_input(routing: Any, name: str) -> bool:
    if not name:
        return False
    if isinstance(routing, dict):
        for key, value in routing.items():
            if str(key) == name and value not in (None, "", [], {}):
                return True
            if _routing_has_input(value, name):
                return True
    elif isinstance(routing, list):
        for item in routing:
            if isinstance(item, dict):
                item_name = item.get("name") or item.get("key")
                item_value = item.get("value") or item.get("resolved_value") or item.get("text")
                if item_name and str(item_name) == name and item_value not in (None, "", [], {}):
                    return True
            if _routing_has_input(item, name):
                return True
    return False


def _required_inputs(blueprint: CandidateAsset | None, routing: Any = None) -> list[dict[str, Any]]:
    if not blueprint:
        return []
    required: list[dict[str, Any]] = []
    for parameter in _parameter_items(blueprint.metadata.get("parameters")):
        if not isinstance(parameter, dict) or not parameter.get("required"):
            continue
        name = parameter.get("name") or parameter.get("key")
        if not name:
            continue
        if _routing_has_input(routing, str(name)):
            continue
        required.append(
            {
                "name": str(name),
                "required": True,
                "source": "blueprint.parameters",
                "display_name": parameter.get("display_name") or parameter.get("label") or str(name),
            }
        )
    return required


def _with_usage(asset: CandidateAsset, usage: str) -> CandidateAsset:
    return CandidateAsset(
        asset_type=asset.asset_type,
        asset_id=asset.asset_id,
        name=asset.name,
        display_name=asset.display_name,
        source=asset.source,
        confidence=asset.confidence,
        match_signals=deepcopy(asset.match_signals),
        metadata=deepcopy(asset.metadata),
        usage=usage,
        match_reason=asset.match_reason,
        reject_reason=asset.reject_reason,
    )


def _top_asset(assets: list[CandidateAsset], asset_type: str) -> CandidateAsset | None:
    filtered = [asset for asset in assets if asset.asset_type == asset_type]
    if not filtered:
        return None
    return max(filtered, key=lambda asset: float(asset.confidence or 0))


def build_fallback_query_plan(
    question: str,
    candidate_assets: CandidateAssetInput = None,
    *,
    routing: Any = None,
    fallback_reason: str | None = None,
) -> QueryPlan:
    assets = _assets(candidate_assets)
    blueprint = _top_asset(assets, "blueprint")
    field_table_assets = [asset for asset in assets if asset.asset_type in {"field", "table"}]
    metric_dimension_assets = [asset for asset in assets if asset.asset_type in {"metric", "dimension"}]
    is_detail_query = _contains_any(question, DETAIL_PATTERNS)
    is_metric_query = _contains_any(question, METRIC_PATTERNS)
    is_blueprint_query = _contains_any(question, BLUEPRINT_PATTERNS)

    required_inputs = _required_inputs(blueprint, routing)
    if is_blueprint_query and blueprint and required_inputs:
        return QueryPlan(
            query_type="blueprint_query",
            execution_strategy="clarify",
            confidence=0.78,
            required_inputs=required_inputs,
            clarification={
                "message": "需要补充蓝图查询的必要参数后才能继续。",
                "required_inputs": required_inputs,
            },
            fallback_reason=fallback_reason or "blueprint_required_inputs_missing",
            planner_source="fallback",
            explanation={
                "summary": "问题命中蓝图类查询，但缺少必填参数。",
                "matched_blueprint": blueprint.display_name or blueprint.name,
            },
        )

    if is_blueprint_query and blueprint:
        return QueryPlan(
            query_type="blueprint_query",
            execution_strategy="blueprint_execute",
            confidence=0.82,
            selected_assets=[_with_usage(blueprint, "selected")],
            fallback_reason=fallback_reason or "blueprint_query_ready",
            planner_source="fallback",
            explanation={
                "summary": "问题命中蓝图类查询，且必要参数已满足或无需参数。",
                "matched_blueprint": blueprint.display_name or blueprint.name,
            },
        )

    if is_detail_query and blueprint and field_table_assets:
        return QueryPlan(
            query_type="detail_query",
            execution_strategy="blueprint_as_reference",
            confidence=0.74,
            selected_assets=[_with_usage(asset, "selected") for asset in field_table_assets],
            reference_assets=[_with_usage(blueprint, "reference")],
            fallback_reason=fallback_reason or "detail_query_with_blueprint_reference",
            planner_source="fallback",
            explanation={
                "summary": "识别为明细查询，蓝图仅作为字段和表推理参考。",
                "why_not_blueprint_execute": "用户问题不是固定蓝图分析，不能强制执行蓝图。",
                "why_continue_without_metric": "明细查询不要求必须命中指标或维度。",
            },
        )

    if is_detail_query and field_table_assets:
        return QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.7,
            selected_assets=[_with_usage(asset, "selected") for asset in field_table_assets],
            fallback_reason=fallback_reason or "detail_query_field_table_fallback",
            planner_source="fallback",
            explanation={
                "summary": "识别为明细查询，使用字段和表构建查询图。",
                "why_continue_without_metric": "明细查询不要求必须命中指标或维度。",
            },
        )

    if is_metric_query and metric_dimension_assets:
        return QueryPlan(
            query_type="metric_query",
            execution_strategy="query_graph",
            confidence=0.68,
            selected_assets=[_with_usage(asset, "selected") for asset in metric_dimension_assets],
            fallback_reason=fallback_reason or "metric_query_semantic_asset_fallback",
            planner_source="fallback",
            explanation={"summary": "识别为指标类查询，使用指标或维度资产构建查询图。"},
        )

    return QueryPlan(
        query_type="unsupported",
        execution_strategy="reject",
        confidence=0.2,
        rejected_assets=[_with_usage(asset, "rejected") for asset in assets],
        fallback_reason=fallback_reason or "insufficient_assets_for_rule_planning",
        planner_source="fallback",
        explanation={"summary": "候选资产不足，规则兜底无法形成可执行查询计划。"},
    )
