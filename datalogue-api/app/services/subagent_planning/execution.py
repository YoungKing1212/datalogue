# ============================================================
# File Name   : execution.py
# Description:
#   SubAgent 查询计划执行策略辅助函数。
#
# Responsibilities:
#   - 将 QueryPlan 中的蓝图参考资产转换为 QueryGraph 可消费的参考上下文。
#   - 为澄清和拒答执行策略生成稳定的 SubAgentResult 结构。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

import json
from typing import Any

from app.services.subagent_planning.contracts import CandidateAsset, QueryPlan, SubAgentResult

TEXT_LIMIT = 600
SQL_LIMIT = 400
PARAMETERS_LIMIT = 900
TRUNCATED_SUFFIX = "...[已截断]"


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + TRUNCATED_SUFFIX


def _compact_value(value: Any, limit: int = TEXT_LIMIT) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return _truncate_text(value, limit)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _truncate_text(text, limit)


def _asset_value(asset: CandidateAsset, key: str) -> Any:
    return asset.metadata.get(key)


def build_blueprint_reference_context(plan: QueryPlan) -> str:
    """构造蓝图参考上下文，强调参考 SQL 不能被原样执行。"""
    if plan.execution_strategy != "blueprint_as_reference":
        return ""

    blueprint_assets = [
        asset for asset in plan.reference_assets
        if asset.asset_type == "blueprint"
    ]
    if not blueprint_assets:
        return ""

    sections = [
        "以下分析蓝图只能作为参考证据，不能原样执行其中 SQL，也不能强行补齐蓝图必填参数。",
        "QueryGraph 可以参考蓝图的业务口径、参数含义和 SQL 模板，自行结合当前问题与已确认输入生成查询。",
    ]
    for index, asset in enumerate(blueprint_assets, start=1):
        metadata = asset.metadata or {}
        title = asset.display_name or asset.name or str(asset.asset_id)
        lines = [
            f"蓝图 {index}: {title}",
            f"- asset_id: {asset.asset_id}",
        ]
        description = _asset_value(asset, "description")
        when_to_use = _asset_value(asset, "when_to_use")
        parameters = _asset_value(asset, "parameters")
        sql_template = (
            metadata.get("sql_template")
            or metadata.get("call_template")
            or metadata.get("raw_sql")
        )
        if description:
            lines.append(f"- description: {_compact_value(description)}")
        if when_to_use:
            lines.append(f"- when_to_use: {_compact_value(when_to_use)}")
        if parameters:
            lines.append(f"- parameters: {_compact_value(parameters, PARAMETERS_LIMIT)}")
        if sql_template:
            lines.append("- SQL 参考模板（只能作为参考证据，不能原样执行）:")
            lines.append("```sql")
            lines.append(_compact_value(sql_template, SQL_LIMIT))
            lines.append("```")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def _plan_assets_payload(plan: QueryPlan) -> dict[str, Any]:
    assets = [
        asset.to_dict()
        for asset in [
            *plan.selected_assets,
            *plan.reference_assets,
            *plan.rejected_assets,
        ]
    ]
    by_type: dict[str, int] = {}
    by_usage: dict[str, int] = {}
    for asset in assets:
        asset_type = str(asset.get("asset_type") or "unknown")
        usage = str(asset.get("usage") or "candidate")
        by_type[asset_type] = by_type.get(asset_type, 0) + 1
        by_usage[usage] = by_usage.get(usage, 0) + 1
    return {
        "assets": assets,
        "summary": {
            "total_count": len(assets),
            "by_type": by_type,
            "by_usage": by_usage,
        },
    }


def _summary(plan: QueryPlan) -> str | None:
    summary = (plan.explanation or {}).get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return None


def _stable_final_state(
    *,
    plan: QueryPlan,
    answer: str,
    entry_route: str,
    entry_intent: str,
    route_payload: dict[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "answer": answer,
        "query_plan": plan.to_dict(),
        "route_payload": route_payload,
        "required_inputs": plan.required_inputs,
        "entry_route": entry_route,
        "entry_intent": entry_intent,
        "sql": None,
        "sql_list": [],
        "sql_result": None,
        "error": error,
        "should_retry": False,
    }


def build_clarify_result(plan: QueryPlan) -> SubAgentResult:
    """将 clarify 查询计划转换为澄清态 SubAgentResult。"""
    clarification = plan.clarification or {}
    message = clarification.get("message")
    answer = message.strip() if isinstance(message, str) and message.strip() else None
    answer = answer or _summary(plan) or "请补充必要信息后再继续查询。"
    route_payload = {
        "kind": "query_plan_clarification",
        "message": answer,
        "required_inputs": plan.required_inputs,
    }
    final_state = _stable_final_state(
        plan=plan,
        answer=answer,
        entry_route="clarify",
        entry_intent="clarification",
        route_payload=route_payload,
    )
    return SubAgentResult(
        final_state=final_state,
        query_plan=plan,
        candidate_assets=_plan_assets_payload(plan),
        step_traces=[{"node": "subagent_query_plan_execution", "strategy": "clarify"}],
    )


def build_reject_result(plan: QueryPlan) -> SubAgentResult:
    """将 reject 查询计划转换为拒答态 SubAgentResult。"""
    answer = _summary(plan) or "当前数据集暂不支持处理该问题。"
    route_payload = {
        "kind": "query_plan_reject",
        "query_type": plan.query_type,
        "summary": answer,
    }
    final_state = _stable_final_state(
        plan=plan,
        answer=answer,
        entry_route="reject",
        entry_intent="rejection",
        route_payload=route_payload,
    )
    return SubAgentResult(
        final_state=final_state,
        query_plan=plan,
        candidate_assets=_plan_assets_payload(plan),
        step_traces=[{"node": "subagent_query_plan_execution", "strategy": "reject"}],
    )
