# ============================================================
# File Name   : lead_agent_planner_projection.py
# Description:
#   LeadAgent 规划器输入投影契约。
#
# Responsibilities:
#   - 将原始 LeadAgent 上下文压缩为 Skill Selector 和 Tool Planner 可消费的稳定输入。
#   - 提供投影前后字符量指标，支撑灰度期观测与回退判断。
#
# Author      : yangkai
# Created On  : 2026-06-16
# ============================================================

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Mapping, TypedDict

from app.core.config import get_settings

PROJECTION_SCHEMA_VERSION = "lead_agent_planner_projection.v2"
DEFAULT_MAX_PRIOR_TURNS = 3
DEFAULT_MAX_TEXT_CHARS = 240
DEFAULT_MAX_PRIOR_BRIEF_CHARS = 360

MAX_PROJECTED_SIGNALS = 3
PROJECTED_ASSET_METADATA_KEYS = {"table_name", "column_name", "parameters", "expr"}
LeadPlannerStage = Literal["skill_selection", "tool_planning"]


class ProjectionMetrics(TypedDict):
    projection_schema_version: str
    raw_chars: int
    projected_chars: int
    projection_saved_chars: int


@dataclass(frozen=True)
class SkillBrief:
    """候选技能的最小描述，避免把完整技能注册上下文送入选择器。"""

    name: str
    description: str = ""
    parameters: Mapping[str, Any] | None = None


def _settings_int(name: str, default: int) -> int:
    try:
        value = int(getattr(get_settings(), name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def projection_max_prior_turns() -> int:
    return _settings_int("LEAD_AGENT_PLANNER_PROJECTION_MAX_PRIOR_TURNS", DEFAULT_MAX_PRIOR_TURNS)


def _projection_max_text_chars() -> int:
    return _settings_int("LEAD_AGENT_PLANNER_PROJECTION_MAX_TEXT_CHARS", DEFAULT_MAX_TEXT_CHARS)


def _projection_max_prior_brief_chars() -> int:
    return _settings_int(
        "LEAD_AGENT_PLANNER_PROJECTION_MAX_PRIOR_BRIEF_CHARS",
        DEFAULT_MAX_PRIOR_BRIEF_CHARS,
    )


def project_skills_for_selector(skills: Any) -> list[dict[str, Any]]:
    """把技能集合投影为名称、描述和参数摘要。"""

    if isinstance(skills, (str, bytes)) or not isinstance(skills, (list, tuple)):
        return []

    projected: list[dict[str, Any]] = []
    items: Iterable[Any] = skills
    for item in items:
        if isinstance(item, SkillBrief):
            raw = asdict(item)
        elif is_dataclass(item) and not isinstance(item, type):
            raw = asdict(item)
        elif isinstance(item, Mapping):
            raw = dict(item)
        else:
            continue

        name = _first_text(raw, "name", "skill_name", "id")
        if not name:
            continue
        projected.append(
            {
                "name": name,
                "description": _truncate_text(
                    _first_text(raw, "description", "purpose", "summary"),
                    _projection_max_text_chars(),
                ),
                "parameters": _project_parameters(
                    raw.get("parameters")
                    if raw.get("parameters") is not None
                    else raw.get("args_schema")
                ),
            }
        )

    return projected


def build_skill_selector_input(
    *,
    question: str,
    candidate_skills: Any,
    recent_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 Skill Selector 的投影输入。"""

    return {
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "question": _truncate_text(question, _projection_max_text_chars() * 2),
        "candidate_skills": project_skills_for_selector(candidate_skills),
        "recent_context": _project_recent_context(recent_context),
    }


def build_tool_planner_input(
    *,
    question: str,
    selected_skills: list[str] | None,
    candidate_tools: Any,
    recent_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 Tool Planner 的投影输入。"""

    return {
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "question": _truncate_text(question, _projection_max_text_chars() * 2),
        "selected_skills": list(selected_skills) if selected_skills else [],
        "candidate_tools": project_tools_for_planner(candidate_tools),
        "recent_context": _project_recent_context(recent_context),
    }


def project_tools_for_planner(tools: Any) -> list[dict[str, Any]]:
    """把 LeadAgent 工具 schema 投影为规划器需要的用途和输入约束。"""

    if isinstance(tools, (str, bytes)) or not isinstance(tools, (list, tuple)):
        return []

    projected: list[dict[str, Any]] = []
    for item in tools:
        if not isinstance(item, Mapping):
            continue

        name = _first_text(item, "name", "tool")
        if not name:
            continue

        projected.append(
            {
                "name": name,
                "description": _truncate_text(
                    _first_text(item, "purpose", "description", "summary"),
                    _projection_max_text_chars(),
                ),
                "inputs": _project_tool_inputs(item.get("inputs")),
            }
        )

    return projected


def build_projection_metrics(*, raw_payload: Any, projected_payload: Any) -> ProjectionMetrics:
    """返回投影前后可观测字符量，便于灰度期对比。"""

    raw_chars = _json_chars(raw_payload)
    projected_chars = _json_chars(projected_payload)
    return {
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "raw_chars": raw_chars,
        "projected_chars": projected_chars,
        "projection_saved_chars": max(raw_chars - projected_chars, 0),
    }


def project_assets_for_lead_planner(
    assets: list[dict[str, Any]],
    *,
    stage: LeadPlannerStage,
    token_budget: int = 1200,
    question: str | None = None,
) -> dict[str, Any]:
    """把过滤后的候选资产投影成 LeadAgent Planner 可消费的轻量上下文。

    Args:
        assets: 已经过 ``filter_lead_planner_assets`` 过滤后的候选资产。
        stage: skill_selection 阶段需要类型摘要；tool_planning 阶段需要
            top 资产详情。
        token_budget: 投影结果建议占用的最大 token 数（按 JSON 字符 / 4 估算）。
        question: 用于计算问题相关片段，可选。

    Returns:
        包含轻量资产列表、类型摘要、stage、预算和时间戳的字典。
    """
    projected_assets = [_project_single_asset(asset) for asset in assets]
    projected_assets.sort(
        key=lambda asset: float(asset.get("confidence") or 0),
        reverse=True,
    )

    # 按 token 预算做最终保险截断；至少保留第一条资产，避免预算过小时输出为空。
    kept: list[dict[str, Any]] = []
    estimated_tokens = 0
    for asset in projected_assets:
        size = _estimate_asset_tokens(asset)
        if kept and estimated_tokens + size > token_budget:
            continue
        kept.append(asset)
        estimated_tokens += size

    summary = _build_asset_projection_summary(kept, projected_assets)
    return {
        "assets": kept,
        "summary": summary,
        "stage": stage,
        "token_budget": token_budget,
        "question": question,
        "projected_at": datetime.now(timezone.utc).isoformat(),
    }


def _project_single_asset(asset: dict[str, Any]) -> dict[str, Any]:
    """把单条候选资产裁剪为 LeadAgent Planner 可消费的轻量字段。"""
    metadata = dict(asset.get("metadata") or {})
    signals = list(asset.get("match_signals") or [])
    signals.sort(
        key=lambda signal: float(signal.get("score") or 0) if isinstance(signal, dict) else 0.0,
        reverse=True,
    )
    projected_signals = [
        {key: signal[key] for key in ("type", "value", "score") if key in signal}
        for signal in signals[:MAX_PROJECTED_SIGNALS]
        if isinstance(signal, dict)
    ]
    return {
        "asset_type": str(asset.get("asset_type") or ""),
        "asset_id": str(asset.get("asset_id") or ""),
        "name": str(asset.get("name") or ""),
        "display_name": str(asset.get("display_name") or asset.get("name") or ""),
        "source": str(asset.get("source") or ""),
        "confidence": round(float(asset.get("confidence") or 0), 4),
        "usage": str(asset.get("usage") or "candidate"),
        "match_reason": str(asset.get("match_reason") or ""),
        "match_signals": projected_signals,
        "metadata": {
            key: metadata[key] for key in PROJECTED_ASSET_METADATA_KEYS if key in metadata
        },
    }


def _estimate_asset_tokens(asset: dict[str, Any]) -> int:
    """按 JSON 字符数 / 4 做极简 token 估算，仅用于最终预算截断。"""
    try:
        return max(1, len(json.dumps(asset, ensure_ascii=False, default=str)) // 4)
    except (TypeError, ValueError):
        return 1


def _build_asset_projection_summary(
    assets: list[dict[str, Any]],
    all_projected: list[dict[str, Any]],
) -> dict[str, Any]:
    """构造投影资产的类型统计、覆盖率与 token 估算摘要。"""
    counts = Counter(str(asset.get("asset_type") or "") for asset in assets)

    max_confidence_by_type: dict[str, float] = {}
    for asset in all_projected:
        asset_type = str(asset.get("asset_type") or "")
        confidence = float(asset.get("confidence") or 0)
        max_confidence_by_type[asset_type] = max(
            max_confidence_by_type.get(asset_type, 0.0),
            confidence,
        )

    top_asset_types = sorted(
        [
            {
                "asset_type": asset_type,
                "count": counts.get(asset_type, 0),
                "max_confidence": round(max_confidence_by_type[asset_type], 4),
            }
            for asset_type in max_confidence_by_type
        ],
        key=lambda item: (item["max_confidence"], item["count"]),
        reverse=True,
    )[:3]

    signal_types = sorted(
        {
            str(signal.get("type"))
            for asset in assets
            for signal in asset.get("match_signals") or []
            if signal.get("type")
        }
    )

    total = len(assets)
    scored = sum(1 for asset in assets if float(asset.get("confidence") or 0) > 0)
    token_estimate = sum(_estimate_asset_tokens(asset) for asset in assets)

    return {
        "total": total,
        "counts_by_type": dict(counts),
        "top_asset_types": top_asset_types,
        "coverage": {
            "scored_assets": scored,
            "scored_ratio": round(scored / total, 4) if total else 0.0,
            "signal_types": signal_types,
        },
        "token_estimate": token_estimate,
        "dropped_by_budget": max(0, len(all_projected) - len(assets)),
    }


def _project_recent_context(recent_context: Mapping[str, Any] | None) -> dict[str, Any]:
    if not recent_context:
        return {}

    projected: dict[str, Any] = {}
    dataset_id = recent_context.get("dataset_id")
    if dataset_id is not None:
        projected["dataset_id"] = dataset_id

    routing_path = _first_text(recent_context, "routing_path", "entry_route")
    if routing_path:
        projected["routing_path"] = routing_path

    turn_policy = _project_turn_policy(recent_context.get("turn_policy"))
    if turn_policy:
        projected["turn_policy"] = turn_policy

    prior_turns = recent_context.get("prior_turns")
    if prior_turns is None:
        prior_turns = recent_context.get("history")
    if prior_turns is None:
        prior_turns = []
    if isinstance(prior_turns, (list, tuple)):
        briefs = [_build_prior_turn_brief(turn) for turn in prior_turns[-projection_max_prior_turns():]]
        projected["prior_turns"] = [brief for brief in briefs if brief]

    last_success_task = _project_last_success_task(recent_context.get("last_success_task"))
    if last_success_task:
        projected["last_success_task"] = last_success_task

    return projected


def _project_last_success_task(value: Any) -> dict[str, Any]:
    """投影上一轮成功任务的最小摘要，避免把 SQL 或结果行注入 LeadAgent Planner。"""

    if not isinstance(value, Mapping):
        return {}

    projected: dict[str, Any] = {}
    for key in ("dataset_id", "query_type", "main_table", "turn_index"):
        item = value.get(key)
        if item not in (None, "", [], {}):
            projected[key] = item

    selected_fields = value.get("selected_field_refs") or value.get("selected_fields")
    if isinstance(selected_fields, list):
        projected["selected_field_refs"] = selected_fields[:12]

    filters_count = value.get("filters_count")
    if isinstance(filters_count, int):
        projected["filters_count"] = filters_count
    elif isinstance(value.get("filters"), list):
        projected["filters_count"] = len(value.get("filters") or [])

    time_window = value.get("time_window") or value.get("time_range")
    if time_window not in (None, "", [], {}):
        projected["time_window"] = time_window

    result_digest = value.get("result_digest")
    if isinstance(result_digest, Mapping):
        compact_digest = {
            key: result_digest[key]
            for key in ("row_count", "columns", "artifact_ref")
            if result_digest.get(key) not in (None, "", [], {})
        }
        if compact_digest:
            projected["result_digest"] = compact_digest

    return projected


def _project_turn_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}

    projected: dict[str, Any] = {}
    intent = _first_text(value, "intent", "turn_intent")
    if intent:
        projected["intent"] = intent

    dataset_lock_source = _first_text(value, "dataset_lock_source")
    if dataset_lock_source:
        projected["dataset_lock_source"] = dataset_lock_source

    for key in (
        "should_inherit_dataset",
        "explicit_dataset_locked",
        "inherited_dataset_locked",
    ):
        flag = value.get(key)
        if isinstance(flag, bool):
            projected[key] = flag

    return projected


def _build_prior_turn_brief(turn: Any) -> dict[str, Any]:
    if not isinstance(turn, Mapping):
        return {}

    brief: dict[str, Any] = {}
    question = _first_text(turn, "question", "resolved_question", "user_query")
    if question:
        brief["question"] = _truncate_text(question, _projection_max_prior_brief_chars())

    routing_path = _first_text(turn, "routing_path", "entry_route")
    if routing_path:
        brief["routing_path"] = routing_path

    inheritance_summary = _first_text(turn, "inheritance_summary", "summary", "last_answer_summary")
    if inheritance_summary:
        brief["inheritance_summary"] = _truncate_text(
            inheritance_summary, _projection_max_prior_brief_chars()
        )

    row_count = turn.get("row_count")
    if row_count is None and isinstance(turn.get("result_summary"), Mapping):
        row_count = turn["result_summary"].get("row_count")
    if row_count is not None:
        brief["row_count"] = row_count

    return brief


def _project_parameters(parameters: Any) -> Any:
    if not isinstance(parameters, Mapping):
        return {}

    projected: dict[str, Any] = {}
    for key, value in parameters.items():
        if isinstance(value, Mapping):
            projected[str(key)] = {
                name: _truncate_text(text, _projection_max_text_chars())
                for name, text in value.items()
                if name in {"type", "description", "title"} and isinstance(text, str)
            }
        elif isinstance(value, str):
            projected[str(key)] = _truncate_text(value, _projection_max_text_chars())
    return projected


def _project_tool_inputs(inputs: Any) -> list[str]:
    if not isinstance(inputs, (list, tuple)):
        return []

    projected: list[str] = []
    for item in inputs:
        if isinstance(item, str) and item.strip():
            projected.append(_truncate_text(item, _projection_max_text_chars()))
    return projected


def _first_text(data: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _truncate_text(text: Any, max_chars: int) -> str:
    if not isinstance(text, str):
        return ""
    value = text.strip()
    if len(value) <= max_chars:
        return value
    if max_chars <= 1:
        return value[:max_chars]
    return value[: max_chars - 1] + "…"


def _json_chars(payload: Any) -> int:
    try:
        return len(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    except (TypeError, ValueError):
        return len(str(payload))
