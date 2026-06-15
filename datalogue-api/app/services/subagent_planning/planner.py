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

import json
from json import JSONDecodeError
from copy import deepcopy
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.llm import get_llm
from app.services.subagent_planning.contracts import (
    CANDIDATE_ASSET_TYPES,
    CandidateAsset,
    QueryPlan,
    QueryPlanValidationError,
    normalize_query_plan,
)

DETAIL_PATTERNS = ("明细", "列表", "日志", "记录", "最近", "前", "条", "limit")
METRIC_PATTERNS = ("统计", "数量", "总数", "平均", "占比", "汇总", "趋势")
BLUEPRINT_PATTERNS = ("日报", "周报", "月报", "分析", "报告")
PROMPT_ASSET_LIMIT = 40
LIGHTWEIGHT_METADATA_KEYS = {"table_name", "column_name", "parameters", "implementation_type"}
PROMPT_TEXT_LIMIT = 120
PROMPT_LIST_LIMIT = 20
PROMPT_DEPTH_LIMIT = 4
LIGHTWEIGHT_ASSET_KEYS = {
    "asset_type",
    "asset_id",
    "name",
    "display_name",
    "source",
    "confidence",
    "usage",
    "match_reason",
    "reject_reason",
}
LIGHTWEIGHT_SIGNAL_KEYS = {"type", "value", "score", "field", "table", "name"}


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


def _planner_system_prompt() -> str:
    return "\n".join(
        [
            "你是数语 DatasetSubAgent 的查询规划器，只能输出严格 JSON。",
            "不要输出 Markdown、解释文字或代码块之外的任何内容。",
            "JSON 必须符合 QueryPlan 契约：query_type、execution_strategy、confidence、planner_source、explanation。",
            "planner_source 必须为 llm。",
            "可选资产字段包括 selected_assets、reference_assets、rejected_assets、required_inputs、clarification、debug。",
            "execution_strategy 可选：blueprint_execute、blueprint_as_reference、query_graph、clarify、reject。",
            "明细查询命中 field/table 时，应优先 query_graph 或 blueprint_as_reference，不要因为缺少指标而 clarify。",
        ]
    )


def _compact_error_text(exc: Exception, max_length: int = 200) -> str:
    text = str(exc) or exc.__class__.__name__
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def _truncate_text(value: str, max_length: int = PROMPT_TEXT_LIMIT) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."


def _compact_prompt_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, str):
        return _truncate_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if depth >= PROMPT_DEPTH_LIMIT:
        return _truncate_text(str(value))
    if isinstance(value, list):
        return [_compact_prompt_value(item, depth=depth + 1) for item in value[:PROMPT_LIST_LIMIT]]
    if isinstance(value, dict):
        return {
            str(key): _compact_prompt_value(item, depth=depth + 1)
            for key, item in list(value.items())[:PROMPT_LIST_LIMIT]
        }
    return _truncate_text(str(value))


def _pick_keys(payload: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {
        key: _compact_prompt_value(payload[key])
        for key in keys
        if key in payload and payload[key] not in (None, "", [], {})
    }


def _manifest_summary(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return _pick_keys(
        value,
        (
            "manifest_id",
            "id",
            "name",
            "display_name",
            "dataset_id",
            "version",
            "status",
        ),
    )


def _routing_summary(routing: Any) -> dict[str, Any]:
    summary = _pick_keys(
        routing,
        (
            "entry_route",
            "entry_intent",
            "dataset_id",
            "manifest_id",
            "matched_manifest_id",
        ),
    )
    if isinstance(routing, dict):
        for source_key in ("matched_manifest", "manifest"):
            if source_key in routing:
                manifest = _manifest_summary(routing[source_key])
                if manifest not in (None, "", [], {}):
                    summary["matched_manifest"] = manifest
                break
        if "route" in routing and "entry_route" not in summary:
            summary["entry_route"] = routing["route"]
        if "intent" in routing and "entry_intent" not in summary:
            summary["entry_intent"] = routing["intent"]
    return summary


def _multiturn_summary(multiturn_context: Any) -> dict[str, Any]:
    return _pick_keys(
        multiturn_context,
        (
            "question_context",
            "resolved_references",
            "active_filters",
            "previous_query_summary",
        ),
    )


def _lead_agent_context_summary(lead_agent_context: Any) -> dict[str, Any]:
    return _pick_keys(
        lead_agent_context,
        (
            "time_context",
            "schema_status",
            "dataset_selection",
            "permission_scope",
        ),
    )


def _lightweight_match_signal(signal: Any) -> dict[str, Any] | None:
    if not isinstance(signal, dict):
        return None
    compact = _pick_keys(signal, tuple(LIGHTWEIGHT_SIGNAL_KEYS))
    return compact or None


def _lightweight_asset(asset: CandidateAsset) -> dict[str, Any]:
    payload = asset.to_dict()
    compact = _pick_keys(payload, tuple(LIGHTWEIGHT_ASSET_KEYS))
    signals = [
        signal
        for signal in (_lightweight_match_signal(item) for item in payload.get("match_signals") or [])
        if signal
    ]
    if signals:
        compact["match_signals"] = signals[:5]
    metadata = {
        key: _compact_prompt_value(value)
        for key, value in (payload.get("metadata") or {}).items()
        if key in LIGHTWEIGHT_METADATA_KEYS and value not in (None, "", [], {})
    }
    if metadata:
        compact["metadata"] = metadata
    return compact


def _planner_human_prompt(
    *,
    question: str,
    routing: Any,
    candidate_assets: CandidateAssetInput,
    multiturn_context: Any = None,
    lead_agent_context: Any = None,
) -> str:
    assets = [_lightweight_asset(asset) for asset in _assets(candidate_assets)]
    asset_counts: dict[str, int] = {}
    for asset in assets:
        asset_type = str(asset.get("asset_type") or "unknown")
        asset_counts[asset_type] = asset_counts.get(asset_type, 0) + 1

    payload = {
        "question": question,
        "routing": _routing_summary(routing),
        "candidate_summary": {
            "total": len(assets),
            "counts_by_type": asset_counts,
        },
        "candidate_assets": assets[:PROMPT_ASSET_LIMIT],
        "multiturn_context": _multiturn_summary(multiturn_context),
        "lead_agent_context_summary": _lead_agent_context_summary(lead_agent_context),
        "rules": [
            "blueprint_execute 只能用于固定蓝图查询，且不能携带 required_inputs。",
            "blueprint_as_reference 必须提供 reference_assets。",
            "reject 必须提供 explanation.summary。",
            "detail_query 如果候选中已有 field/table，不应返回 clarify。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _safe_json_parse(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise QueryPlanValidationError("planner output must be a JSON object")
    return parsed


def _validate_hard_rules(
    plan: QueryPlan,
    *,
    question: str,
    candidate_assets: CandidateAssetInput,
) -> None:
    del question
    if plan.execution_strategy == "blueprint_execute" and plan.required_inputs:
        raise QueryPlanValidationError("blueprint_execute cannot include required_inputs")
    if plan.execution_strategy == "blueprint_as_reference" and not plan.reference_assets:
        raise QueryPlanValidationError("blueprint_as_reference requires reference_assets")
    if plan.execution_strategy == "reject" and not str(plan.explanation.get("summary") or "").strip():
        raise QueryPlanValidationError("reject requires explanation.summary")

    has_field_or_table = any(asset.asset_type in {"field", "table"} for asset in _assets(candidate_assets))
    if plan.query_type == "detail_query" and plan.execution_strategy == "clarify" and has_field_or_table:
        raise QueryPlanValidationError("detail_query cannot clarify when field/table candidates exist")


def _invoke_planner_llm(db: Any, messages: list[Any]) -> Any:
    try:
        llm = get_llm(temperature=0.0, role="lead_agent", db=db)
        return llm.invoke(messages)
    except (RuntimeError, TimeoutError, ConnectionError) as exc:
        raise QueryPlanValidationError(_compact_error_text(exc)) from exc


def plan_query(
    *,
    db: Any,
    question: str,
    routing: Any,
    candidate_assets: CandidateAssetInput,
    multiturn_context: Any = None,
    lead_agent_context: Any = None,
) -> QueryPlan:
    messages = [
        SystemMessage(content=_planner_system_prompt()),
        HumanMessage(
            content=_planner_human_prompt(
                question=question,
                routing=routing,
                candidate_assets=candidate_assets,
                multiturn_context=multiturn_context,
                lead_agent_context=lead_agent_context,
            )
        ),
    ]
    try:
        response = _invoke_planner_llm(db, messages)
    except QueryPlanValidationError as exc:
        return build_fallback_query_plan(
            question=question,
            routing=routing,
            candidate_assets=candidate_assets,
            fallback_reason=_compact_error_text(exc),
        )

    try:
        payload = _safe_json_parse(getattr(response, "content", response))
        plan = normalize_query_plan(payload)
        _validate_hard_rules(plan, question=question, candidate_assets=candidate_assets)
        return plan
    except (JSONDecodeError, QueryPlanValidationError, ValueError, TypeError) as exc:
        return build_fallback_query_plan(
            question=question,
            routing=routing,
            candidate_assets=candidate_assets,
            fallback_reason=_compact_error_text(exc),
        )
