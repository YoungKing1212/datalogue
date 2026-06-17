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
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Iterable, Mapping, TypedDict

PROJECTION_SCHEMA_VERSION = "lead_agent_planner_projection.v2"
DEFAULT_MAX_PRIOR_TURNS = 3
DEFAULT_MAX_TEXT_CHARS = 240
DEFAULT_MAX_PRIOR_BRIEF_CHARS = 360


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
                    DEFAULT_MAX_TEXT_CHARS,
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
        "question": _truncate_text(question, DEFAULT_MAX_TEXT_CHARS * 2),
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
        "question": _truncate_text(question, DEFAULT_MAX_TEXT_CHARS * 2),
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
                    DEFAULT_MAX_TEXT_CHARS,
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
        briefs = [_build_prior_turn_brief(turn) for turn in prior_turns[-DEFAULT_MAX_PRIOR_TURNS:]]
        projected["prior_turns"] = [brief for brief in briefs if brief]

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
        brief["question"] = _truncate_text(question, DEFAULT_MAX_PRIOR_BRIEF_CHARS)

    routing_path = _first_text(turn, "routing_path", "entry_route")
    if routing_path:
        brief["routing_path"] = routing_path

    inheritance_summary = _first_text(turn, "inheritance_summary", "summary", "last_answer_summary")
    if inheritance_summary:
        brief["inheritance_summary"] = _truncate_text(
            inheritance_summary, DEFAULT_MAX_PRIOR_BRIEF_CHARS
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
                name: _truncate_text(text, DEFAULT_MAX_TEXT_CHARS)
                for name, text in value.items()
                if name in {"type", "description", "title"} and isinstance(text, str)
            }
        elif isinstance(value, str):
            projected[str(key)] = _truncate_text(value, DEFAULT_MAX_TEXT_CHARS)
    return projected


def _project_tool_inputs(inputs: Any) -> list[str]:
    if not isinstance(inputs, (list, tuple)):
        return []

    projected: list[str] = []
    for item in inputs:
        if isinstance(item, str) and item.strip():
            projected.append(_truncate_text(item, DEFAULT_MAX_TEXT_CHARS))
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
