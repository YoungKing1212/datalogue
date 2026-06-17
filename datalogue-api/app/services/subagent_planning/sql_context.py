# ============================================================
# File Name   : sql_context.py
# Description:
#   SubAgent SQL 生成阶段使用的资产上下文组装服务。
#
# Responsibilities:
#   - 从 QueryPlan 和按需拉取的资产详情中组装 SQL 生成上下文。
#   - 按资产类型和详情级别拆分表结构、字段搜索、指标、维度和蓝图引用。
#   - 保持 QueryPlan 轻量化，避免把完整详情嵌入规划结果。
#
# Author      : yangkai
# Created On  : 2026-06-18
# ============================================================

from __future__ import annotations

from typing import Any

from app.services.subagent_planning.asset_detail import AssetDetailResult
from app.services.subagent_planning.contracts import QueryPlan


def build_sql_generation_context(
    *,
    query_plan: QueryPlan,
    asset_details: list[AssetDetailResult],
    lightweight_catalog: dict[str, Any] | None,
) -> dict[str, Any]:
    summary = (lightweight_catalog or {}).get("summary") or {}
    summary = summary if isinstance(summary, dict) else {}
    context: dict[str, Any] = {
        "selected_assets": [asset.to_dict() for asset in query_plan.selected_assets],
        "reference_assets": [asset.to_dict() for asset in query_plan.reference_assets],
        "table_schemas": [],
        "field_search_results": [],
        "metric_definitions": [],
        "dimension_definitions": [],
        "blueprint_references": [],
        "coverage": {},
        "risk_flags": [],
        "schema_version": summary.get("schema_version"),
        "manifest_version": summary.get("manifest_version"),
    }

    risk_flags: set[str] = set()
    for detail in asset_details:
        asset_id = str(detail.request.asset_id)
        context["coverage"][asset_id] = detail.coverage
        risk_flags.update(str(flag) for flag in detail.risk_flags)

        bucket = _detail_bucket(detail)
        if bucket is None:
            continue
        context[bucket].append(_payload_with_asset_id(detail.payload, asset_id))

    context["risk_flags"] = sorted(risk_flags)
    return context


def _detail_bucket(detail: AssetDetailResult) -> str | None:
    asset_type = detail.request.asset_type
    detail_level = detail.request.detail_level
    if asset_type == "table" and detail_level == "full_schema":
        return "table_schemas"
    if asset_type == "table" and detail_level == "field_search":
        return "field_search_results"
    if asset_type == "metric":
        return "metric_definitions"
    if asset_type == "dimension":
        return "dimension_definitions"
    if asset_type == "blueprint":
        return "blueprint_references"
    return None


def _payload_with_asset_id(payload: dict[str, Any], asset_id: str) -> dict[str, Any]:
    copied_payload = dict(payload if isinstance(payload, dict) else {})
    copied_payload["asset_id"] = asset_id
    return copied_payload
