# ============================================================
# File Name   : lead_agent.py
# Description:
#   LeadAgent 控制面工具编排服务。
#
# Responsibilities:
#   - 解析问数入口的时间、会话、Manifest 路由和 schema 状态。
#   - 生成数据集级澄清与 SubAgent 调度上下文。
#   - 保持 LeadAgent 不读取指标、维度、术语和蓝图等语义层内部资产。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

from __future__ import annotations

import json
import logging
import re
from calendar import monthrange
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app import models
from app.core.config import get_settings
from app.graph.llm import get_llm
from app.prompts.lead_agent import LEAD_AGENT_SKILL_SELECTOR_SYSTEM, LEAD_AGENT_TOOL_PLANNER_SYSTEM
from app.services.dataset_manifest import build_dataset_schema_version
from app.services.dataset_router import route_dataset_for_question
from app.services.lead_agent_planner_projection import (
    DEFAULT_MAX_PRIOR_TURNS,
    PROJECTION_SCHEMA_VERSION,
    build_projection_metrics,
    build_skill_selector_input,
    build_tool_planner_input,
)
from app.services.llm_config import resolve_llm_config
from app.services.multiturn_context import MergeDecision, MultiturnContextBuilder
from app.services.observability.prompts import get_prompt_manager
from app.utils.json_utils import safe_json_parse

DEFAULT_TIMEZONE = "Asia/Shanghai"
LEAD_AGENT_SKILL_SELECTOR_PROMPT_NAME = "lead_agent_skill_selector"
LEAD_AGENT_TOOL_PLANNER_PROMPT_NAME = "lead_agent_tool_planner"
LEAD_AGENT_PROMPT_NAME = LEAD_AGENT_TOOL_PLANNER_PROMPT_NAME
logger = logging.getLogger(__name__)

ALLOWED_LEAD_TOOLS = (
    "time",
    "thread_context",
    "manifest_router",
    "schema_status",
    "clarification",
    "subagent_dispatch",
    "audit_trace",
)
BLOCKED_LEAD_TOOLS = (
    "metric_resolution",
    "dimension_resolution",
    "term_normalization",
    "analysis_blueprint_match",
    "analysis_blueprint_execute",
    "sql_generate",
    "sql_execute",
    "schema_recall",
)


@dataclass(frozen=True)
class LeadSkill:
    """LeadAgent Skill 只描述控制面能力和可用工具，不直接执行逻辑。"""

    name: str
    purpose: str
    allowed_tools: tuple[str, ...]


@dataclass(frozen=True)
class PlannedToolCall:
    """LLM Planner 输出的单个工具调用计划。"""

    tool: str
    reason: str


LEAD_SKILLS = (
    LeadSkill("TimeUnderstandingSkill", "解析用户问题中的时间线索。", ("time",)),
    LeadSkill(
        "ConversationContinuitySkill", "处理会话上下文和显式数据集锁定。", ("thread_context",)
    ),
    LeadSkill(
        "DatasetRoutingSkill", "选择或确认候选数据集。", ("manifest_router", "clarification")
    ),
    LeadSkill("SchemaFreshnessSkill", "检查 Manifest 绑定 schema 是否过期。", ("schema_status",)),
    LeadSkill(
        "SubAgentDelegationSkill", "判断是否可以把问题交给 SubAgent。", ("subagent_dispatch",)
    ),
    LeadSkill("AuditSkill", "记录 LeadAgent 工具规划和执行轨迹。", ("audit_trace",)),
)


def build_tool_policy(
    *,
    conversation: models.Conversation | None = None,
    payload_dataset_id: int | None = None,
    active_dataset_id: int | None = None,
) -> dict[str, Any]:
    """ToolPolicy：生成 LeadAgent 本轮可用工具和硬性边界。"""

    conversation_dataset_id = conversation.dataset_id if conversation else None
    locked_dataset_id = (
        payload_dataset_id
        if payload_dataset_id is not None
        else (active_dataset_id if active_dataset_id is not None else conversation_dataset_id)
    )
    dataset_lock_source = "none"
    if payload_dataset_id is not None:
        dataset_lock_source = "payload"
    elif active_dataset_id is not None:
        dataset_lock_source = "multiturn_active"
    elif conversation_dataset_id is not None:
        dataset_lock_source = "conversation"
    constraints = [
        "LeadAgent 只能使用控制面工具，不可读取指标、维度、术语、蓝图、SQL 或字段级 schema。",
        "ToolPolicy.blocked_tools 中的工具即使被 LLM 规划也不能执行。",
        "未确认 dataset 时不可执行 subagent_dispatch。",
        "显式选择数据集或会话已锁定数据集时，manifest_router 只能锁定该数据集，不可自动改选。",
        "多轮 active_dataset_id 只作为 LeadAgent 控制面继承锁定，不代表用户本轮显式选择。",
        "schema stale 必须记录到 schema_status 和 audit_trace。",
    ]
    return {
        "required_tools": ["thread_context"],
        "allowed_tools": list(ALLOWED_LEAD_TOOLS),
        "blocked_tools": list(BLOCKED_LEAD_TOOLS),
        "constraints": constraints,
        "locked_dataset_id": locked_dataset_id,
        "explicit_dataset_locked": payload_dataset_id is not None,
        "inherited_dataset_locked": dataset_lock_source == "multiturn_active",
        "dataset_lock_source": dataset_lock_source,
        "active_dataset_id": active_dataset_id,
        "conversation_dataset_id": conversation.dataset_id if conversation else None,
    }


def available_lead_skills(tool_policy: dict[str, Any]) -> list[dict[str, Any]]:
    """返回当前 ToolPolicy 下可被 Planner 选择的 Skill。"""

    allowed = set(tool_policy.get("allowed_tools") or [])
    skills: list[dict[str, Any]] = []
    for skill in LEAD_SKILLS:
        tools = [tool for tool in skill.allowed_tools if tool in allowed]
        if tools:
            payload = asdict(skill)
            payload["allowed_tools"] = tools
            skills.append(payload)
    return skills


def build_fallback_plan(
    *,
    reason: str,
) -> dict[str, Any]:
    """Planner 失败或输出不完整时使用的最小安全计划。"""

    return {
        "reasoning_summary": f"使用安全降级计划：{reason}",
        "selected_skills": [
            "TimeUnderstandingSkill",
            "ConversationContinuitySkill",
            "DatasetRoutingSkill",
            "SchemaFreshnessSkill",
            "SubAgentDelegationSkill",
            "AuditSkill",
        ],
        "tool_calls": [
            {"tool": "time", "reason": "低风险控制面上下文，供后续时间口径使用。"},
            {"tool": "thread_context", "reason": "必须先读取会话和显式数据集锁定。"},
            {"tool": "manifest_router", "reason": "根据锁定数据集或 current Manifest 决定数据集。"},
            {"tool": "schema_status", "reason": "路由后检查 Manifest 绑定 schema 是否过期。"},
            {"tool": "clarification", "reason": "路由不明确或 schema stale 时生成数据集级澄清。"},
            {"tool": "subagent_dispatch", "reason": "数据集明确时生成 SubAgent 调度上下文。"},
            {"tool": "audit_trace", "reason": "记录工具执行摘要。"},
        ],
        "planner_fallback": True,
        "fallback_reason": reason,
    }


FAST_PATH_QUERY_INTENTS = {"new", "new_query", "query", "self_contained"}
FAST_PATH_QUERY_KEYWORDS = (
    "查",
    "查询",
    "看",
    "列",
    "明细",
    "日志",
    "日报",
    "记录",
    "多少",
    "统计",
    "趋势",
    "排名",
)
FAST_PATH_TOOLS = (
    "thread_context",
    "manifest_router",
    "schema_status",
    "subagent_dispatch",
    "audit_trace",
)
FAST_PATH_SKILLS = [
    "ConversationContinuitySkill",
    "DatasetRoutingSkill",
    "SchemaFreshnessSkill",
    "SubAgentDelegationSkill",
    "AuditSkill",
]


def _fast_path_query_signal(question: str) -> bool:
    return any(keyword in question for keyword in FAST_PATH_QUERY_KEYWORDS)


def _deterministic_tool_plan(
    *,
    question: str,
    conversation_summary: dict[str, Any],
    tool_policy: dict[str, Any],
) -> dict[str, Any] | None:
    """锁定数据集的新自包含查询直接走固定控制面计划，绕开两次 LLM。"""

    if not tool_policy.get("locked_dataset_id"):
        return None
    multiturn_classification = conversation_summary.get("multiturn_classification") or {}
    turn_intent = str(multiturn_classification.get("intent") or "new_query")
    if turn_intent not in FAST_PATH_QUERY_INTENTS:
        return None
    if multiturn_classification.get("should_inherit_dataset") is True:
        return None
    if not _fast_path_query_signal(question):
        return None
    allowed_tools = set(tool_policy.get("allowed_tools") or [])
    if not set(FAST_PATH_TOOLS).issubset(allowed_tools):
        return None
    return {
        "reasoning_summary": "锁定数据集的新自包含查询命中确定性控制面快路径。",
        "selected_skills": FAST_PATH_SKILLS,
        "tool_calls": [
            {"tool": "thread_context", "reason": "读取会话和显式数据集锁定。"},
            {"tool": "manifest_router", "reason": "使用已锁定数据集，不重新选择数据集。"},
            {"tool": "schema_status", "reason": "检查锁定数据集的 Manifest/schema 状态。"},
            {"tool": "subagent_dispatch", "reason": "数据集已明确，直接调度 SubAgent。"},
            {"tool": "audit_trace", "reason": "记录确定性快路径控制面摘要。"},
        ],
        "planner_fallback": False,
        "fallback_reason": None,
        "planner_source": "deterministic",
        "fast_path_hit": True,
        "llm_skipped_reason": "locked_dataset_self_contained_query",
    }


def plan_tool_calls_with_llm(
    db: Session,
    *,
    question: str,
    conversation_summary: dict[str, Any],
    tool_policy: dict[str, Any],
    skills: list[dict[str, Any]],
    tracer: Any | None = None,
    trace_context: Any | None = None,
) -> dict[str, Any]:
    """LeadAgentPlanner：用 LLM 生成工具计划，失败时返回安全降级计划。"""

    deterministic_plan = _deterministic_tool_plan(
        question=question,
        conversation_summary=conversation_summary,
        tool_policy=tool_policy,
    )
    if deterministic_plan:
        if tracer is not None and trace_context is not None:
            try:
                tracer.start_span(
                    trace_context,
                    node="llm.lead_agent_tool_planner",
                    display_name="llm.lead_agent_tool_planner",
                    input_payload={
                        "question": question,
                        "locked_dataset_id": tool_policy.get("locked_dataset_id"),
                    },
                )
                tracer.end_span(
                    trace_context,
                    node="llm.lead_agent_tool_planner",
                    output_payload=deterministic_plan,
                )
            except Exception:
                pass
        return deterministic_plan

    availability = _lead_agent_llm_available(db)
    if not availability["available"]:
        return build_fallback_plan(reason=availability["reason"])

    use_projection = bool(get_settings().LEAD_AGENT_PLANNER_USE_PROJECTION)
    projection_recent_context = _build_projection_recent_context(
        conversation_summary=conversation_summary,
        tool_policy=tool_policy,
    )
    skill_generation = None
    tool_generation = None
    raw_skill_input = {
        "question": question,
        "conversation": conversation_summary,
        "tool_policy": tool_policy,
        "skills": skills,
    }
    skill_input = (
        build_skill_selector_input(
            question=question,
            candidate_skills=skills,
            recent_context=projection_recent_context,
        )
        if use_projection
        else raw_skill_input
    )
    skill_projection_metrics = (
        build_projection_metrics(
            raw_payload=raw_skill_input,
            projected_payload=skill_input,
        )
        if use_projection
        else None
    )
    try:
        prompt_manager = get_prompt_manager()
        skill_prompt = prompt_manager.get_text_prompt(
            LEAD_AGENT_SKILL_SELECTOR_PROMPT_NAME,
            fallback=LEAD_AGENT_SKILL_SELECTOR_SYSTEM,
        )
        llm = get_llm(temperature=0.1, role="lead_agent", db=db)
        skill_messages = [
            SystemMessage(content=skill_prompt.content),
            HumanMessage(content=json.dumps(skill_input, ensure_ascii=False, default=str)),
        ]
        if tracer is not None and trace_context is not None:
            skill_generation = tracer.start_generation(
                name="llm.lead_agent_skill_selector",
                model=getattr(llm, "model_name", None) or getattr(llm, "model", None),
                messages=skill_messages,
                metadata={
                    "path": "lead_agent_skill_selector",
                    "prompt_name": LEAD_AGENT_SKILL_SELECTOR_PROMPT_NAME,
                    "prompt_version": skill_prompt.version,
                    "prompt_source": skill_prompt.source,
                    "progressive_disclosure": True,
                    "disclosure_stage": "skill_selection",
                    "tool_policy": tool_policy,
                    "skills": [item.get("name") for item in skills],
                    "tool_schemas_disclosed": [],
                    "projection_enabled": use_projection,
                    **(
                        {
                            "projection_metrics": skill_projection_metrics,
                            "projection_schema_version": PROJECTION_SCHEMA_VERSION,
                            **skill_projection_metrics,
                        }
                        if use_projection and skill_projection_metrics is not None
                        else {}
                    ),
                },
            )
        logger.info(
            "LeadAgent Planner 调用: stage=skill_selector, prompt_name=%s, version=%s, "
            "skills=%s, tool_policy_locked_dataset=%s",
            LEAD_AGENT_SKILL_SELECTOR_PROMPT_NAME,
            getattr(skill_prompt, "version", None),
            [item.get("name") for item in skills],
            tool_policy.get("locked_dataset_id"),
        )
        logger.debug(
            "LeadAgent Planner skill_selector 请求: system=%s | human=%s",
            skill_messages[0].content,
            skill_messages[1].content,
        )
        skill_response = llm.invoke(skill_messages)
        skill_raw_content = str(getattr(skill_response, "content", "") or "")
        skill_parsed = safe_json_parse(skill_raw_content)
        logger.info(
            "LeadAgent Planner skill_selector 返回: parse_ok=%s, selected=%s, reasoning=%s, "
            "raw_len=%d",
            bool(skill_parsed),
            (skill_parsed or {}).get("selected_skills"),
            (skill_parsed or {}).get("reasoning_summary"),
            len(skill_raw_content),
        )
        logger.debug(
            "LeadAgent Planner skill_selector 原始返回: %s",
            skill_raw_content,
        )
        skill_selection = _normalize_skill_selection(skill_parsed, skills)
        if tracer is not None:
            tracer.end_generation(
                skill_generation,
                output=skill_raw_content,
                usage=getattr(skill_response, "usage_metadata", None),
                metadata={
                    "path": "lead_agent_skill_selector",
                    "parse_ok": bool(skill_selection),
                    "planner_fallback": not bool(skill_selection),
                    "progressive_disclosure": True,
                    "disclosure_stage": "skill_selection",
                    "projection_enabled": use_projection,
                    **(
                        {
                            "projection_schema_version": PROJECTION_SCHEMA_VERSION,
                            "projection_metrics": skill_projection_metrics,
                        }
                        if use_projection and skill_projection_metrics is not None
                        else {}
                    ),
                },
            )
        if not skill_selection:
            return build_fallback_plan(reason="skill_selector_invalid_json")

        selected_skill_names = skill_selection["selected_skills"]
        selected_skill_payloads = _skill_payloads_by_name(skills, selected_skill_names)
        disclosed_tool_schemas = _tool_schemas_for_skills(selected_skill_names, skills, tool_policy)
        tool_prompt = prompt_manager.get_text_prompt(
            LEAD_AGENT_TOOL_PLANNER_PROMPT_NAME,
            fallback=LEAD_AGENT_TOOL_PLANNER_SYSTEM,
        )
        raw_planner_input = {
            "question": question,
            "conversation": conversation_summary,
            "tool_policy": tool_policy,
            "selected_skills": selected_skill_payloads,
            "tool_schemas": disclosed_tool_schemas,
        }
        planner_input = (
            build_tool_planner_input(
                question=question,
                selected_skills=selected_skill_names,
                candidate_tools=disclosed_tool_schemas,
                recent_context=projection_recent_context,
            )
            if use_projection
            else raw_planner_input
        )
        planner_projection_metrics = (
            build_projection_metrics(
                raw_payload=raw_planner_input,
                projected_payload=planner_input,
            )
            if use_projection
            else None
        )
        tool_messages = [
            SystemMessage(content=tool_prompt.content),
            HumanMessage(content=json.dumps(planner_input, ensure_ascii=False, default=str)),
        ]
        if tracer is not None and trace_context is not None:
            tool_generation = tracer.start_generation(
                name="llm.lead_agent_tool_planner",
                model=getattr(llm, "model_name", None) or getattr(llm, "model", None),
                messages=tool_messages,
                metadata={
                    "path": "lead_agent_tool_planner",
                    "prompt_name": LEAD_AGENT_TOOL_PLANNER_PROMPT_NAME,
                    "prompt_version": tool_prompt.version,
                    "prompt_source": tool_prompt.source,
                    "progressive_disclosure": True,
                    "disclosure_stage": "tool_planning",
                    "selected_skills": selected_skill_names,
                    "disclosed_tools": [item.get("name") for item in disclosed_tool_schemas],
                    "tool_policy": tool_policy,
                    "projection_enabled": use_projection,
                    **(
                        {
                            "projection_metrics": planner_projection_metrics,
                            "projection_schema_version": PROJECTION_SCHEMA_VERSION,
                            **planner_projection_metrics,
                        }
                        if use_projection and planner_projection_metrics is not None
                        else {}
                    ),
                },
            )
        logger.info(
            "LeadAgent Planner 调用: stage=tool_planner, prompt_name=%s, version=%s, "
            "selected_skills=%s, disclosed_tools=%s",
            LEAD_AGENT_TOOL_PLANNER_PROMPT_NAME,
            getattr(tool_prompt, "version", None),
            selected_skill_names,
            [item.get("name") for item in disclosed_tool_schemas],
        )
        logger.debug(
            "LeadAgent Planner tool_planner 请求: system=%s | human=%s",
            tool_messages[0].content,
            tool_messages[1].content,
        )
        tool_response = llm.invoke(tool_messages)
        tool_raw_content = str(getattr(tool_response, "content", "") or "")
        parsed = safe_json_parse(tool_raw_content)
        logger.info(
            "LeadAgent Planner tool_planner 返回: parse_ok=%s, planned_tools=%s, "
            "reasoning=%s, raw_len=%d",
            bool(parsed),
            [(p or {}).get("tool") for p in (parsed or {}).get("tool_calls") or []],
            (parsed or {}).get("reasoning_summary"),
            len(tool_raw_content),
        )
        logger.debug(
            "LeadAgent Planner tool_planner 原始返回: %s",
            tool_raw_content,
        )
        normalized = _normalize_planner_plan(parsed)
        if tracer is not None:
            tracer.end_generation(
                tool_generation,
                output=tool_raw_content,
                usage=getattr(tool_response, "usage_metadata", None),
                metadata={
                    "path": "lead_agent_tool_planner",
                    "parse_ok": bool(normalized),
                    "planner_fallback": not bool(normalized),
                    "progressive_disclosure": True,
                    "disclosure_stage": "tool_planning",
                    "selected_skills": selected_skill_names,
                    "disclosed_tools": [item.get("name") for item in disclosed_tool_schemas],
                    "normalized_plan": normalized,
                    "projection_enabled": use_projection,
                    **(
                        {
                            "projection_schema_version": PROJECTION_SCHEMA_VERSION,
                            "projection_metrics": planner_projection_metrics,
                        }
                        if use_projection and planner_projection_metrics is not None
                        else {}
                    ),
                },
            )
        if not normalized:
            return build_fallback_plan(reason="planner_invalid_json")
        normalized["planner_fallback"] = False
        normalized["fallback_reason"] = None
        normalized["selected_skills"] = selected_skill_names
        normalized["skill_selection_reasoning_summary"] = skill_selection.get("reasoning_summary")
        normalized["tool_planning_reasoning_summary"] = normalized.get("reasoning_summary")
        normalized["reasoning_summary"] = _merge_reasoning_summary(
            skill_selection.get("reasoning_summary"),
            normalized.get("reasoning_summary"),
        )
        normalized["progressive_disclosure"] = True
        normalized["disclosed_tools"] = [item.get("name") for item in disclosed_tool_schemas]
        return normalized
    except Exception as exc:
        if tracer is not None:
            tracer.end_generation(
                tool_generation or skill_generation,
                output=f"LeadAgent Planner 调用失败: {exc}",
                usage=None,
                metadata={
                    "path": "lead_agent_planner",
                    "parse_ok": False,
                    "planner_fallback": True,
                    "error": str(exc),
                },
            )
        logger.exception(
            "LeadAgent Planner 调用失败，使用安全降级计划: %s",
            exc,
        )
        return build_fallback_plan(reason="planner_llm_error")


def _build_projection_recent_context(
    *,
    conversation_summary: Mapping[str, Any] | None,
    tool_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """把 LeadAgent 控制面状态翻译为 Planner 投影输入的 recent_context。

    只携带 Planner 投影契约需要的字段（dataset_id、routing_path、
    turn_policy、prior_turns），避免把完整 conversation_summary/multiturn_context
    注入 LLM payload。
    """

    conversation_summary = conversation_summary or {}
    tool_policy = tool_policy or {}

    recent: dict[str, Any] = {}
    summary_dataset_id = conversation_summary.get("dataset_id")
    locked_dataset_id = tool_policy.get("locked_dataset_id")
    if locked_dataset_id is not None:
        recent["dataset_id"] = locked_dataset_id
    elif summary_dataset_id is not None:
        recent["dataset_id"] = summary_dataset_id

    payload_dataset_id = conversation_summary.get("payload_dataset_id")
    conversation_dataset_id = conversation_summary.get("conversation_dataset_id")
    summary_routing_path = conversation_summary.get("routing_path") or conversation_summary.get(
        "entry_route"
    )
    if summary_routing_path:
        recent["routing_path"] = summary_routing_path
    elif payload_dataset_id is not None:
        recent["routing_path"] = "payload"
    elif conversation_dataset_id is not None:
        recent["routing_path"] = "conversation"
    else:
        recent["routing_path"] = "pending"

    multiturn_classification = conversation_summary.get("multiturn_classification") or {}
    turn_policy: dict[str, Any] = {}
    turn_intent = str(multiturn_classification.get("intent") or "").strip()
    if turn_intent:
        turn_policy["intent"] = turn_intent
    should_inherit_dataset = multiturn_classification.get("should_inherit_dataset")
    if isinstance(should_inherit_dataset, bool):
        turn_policy["should_inherit_dataset"] = should_inherit_dataset

    for key in (
        "dataset_lock_source",
        "explicit_dataset_locked",
        "inherited_dataset_locked",
    ):
        value = tool_policy.get(key)
        if value is not None:
            turn_policy[key] = value
    if turn_policy:
        recent["turn_policy"] = turn_policy

    prior_turns = conversation_summary.get("prior_turns") or conversation_summary.get("history")
    if isinstance(prior_turns, list | tuple):
        recent["prior_turns"] = list(prior_turns)[-DEFAULT_MAX_PRIOR_TURNS:]

    raw_multiturn_context = conversation_summary.get("multiturn_context")
    multiturn_context = raw_multiturn_context if isinstance(raw_multiturn_context, dict) else {}
    prior_turn: dict[str, Any] = {}
    last_question = multiturn_context.get("last_question") or multiturn_context.get(
        "last_resolved_question"
    )
    if last_question:
        prior_turn["question"] = last_question
    inheritance_summary = multiturn_context.get("inheritance_summary")
    if inheritance_summary:
        prior_turn["inheritance_summary"] = inheritance_summary
    if prior_turn:
        prior_routing_path: str | None = None
        for key in ("routing_path", "prior_routing_path", "last_routing_path"):
            value = multiturn_context.get(key)
            if isinstance(value, str) and value.strip():
                prior_routing_path = value.strip()
                break
        if prior_routing_path:
            prior_turn["routing_path"] = prior_routing_path
        recent.setdefault("prior_turns", []).append(prior_turn)

    return recent


def _conversation_summary(
    conversation: models.Conversation | None,
    payload_dataset_id: int | None,
    multiturn_context: dict[str, Any] | None = None,
    multiturn_classification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "conversation_id": conversation.id if conversation else None,
        "thread_id": conversation.thread_id if conversation else None,
        "conversation_dataset_id": conversation.dataset_id if conversation else None,
        "payload_dataset_id": payload_dataset_id,
        "multiturn_context": multiturn_context or {},
        "multiturn_classification": multiturn_classification or {},
    }


def _lead_agent_llm_available(db: Session) -> dict[str, Any]:
    try:
        config = resolve_llm_config(get_settings(), role="lead_agent", db=db)
    except Exception as exc:
        return {"available": False, "reason": f"llm_config_error:{exc}"}
    if not config.api_key:
        return {"available": False, "reason": "lead_agent_llm_not_configured"}
    return {"available": True, "reason": None}


def _normalize_planner_plan(value: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    raw_tool_calls = value.get("tool_calls")
    if not isinstance(raw_tool_calls, list) or not raw_tool_calls:
        return None
    tool_calls: list[dict[str, str]] = []
    for item in raw_tool_calls:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "").strip()
        if not tool:
            continue
        tool_calls.append(
            {
                "tool": tool,
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    if not tool_calls:
        return None
    selected_skills = [
        str(item).strip() for item in value.get("selected_skills") or [] if str(item).strip()
    ]
    return {
        "reasoning_summary": str(value.get("reasoning_summary") or "").strip(),
        "selected_skills": selected_skills,
        "tool_calls": tool_calls,
    }


def _normalize_skill_selection(
    value: dict[str, Any], skills: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    available_names = {str(item.get("name")) for item in skills if item.get("name")}
    selected_skills = [
        str(item).strip()
        for item in value.get("selected_skills") or []
        if str(item).strip() in available_names
    ]
    if not selected_skills:
        return None
    return {
        "reasoning_summary": str(value.get("reasoning_summary") or "").strip(),
        "selected_skills": selected_skills,
    }


def _skill_payloads_by_name(skills: list[dict[str, Any]], names: list[str]) -> list[dict[str, Any]]:
    selected = set(names)
    return [item for item in skills if item.get("name") in selected]


def _tool_schemas_for_skills(
    skill_names: list[str],
    skills: list[dict[str, Any]],
    tool_policy: dict[str, Any],
) -> list[dict[str, Any]]:
    selected = set(skill_names)
    policy_allowed = set(tool_policy.get("allowed_tools") or [])
    allowed_tools: set[str] = set()
    for skill in skills:
        if skill.get("name") in selected:
            allowed_tools.update(skill.get("allowed_tools") or [])
    disclosed_tools = allowed_tools & policy_allowed
    return [schema for schema in _tool_schemas() if schema.get("name") in disclosed_tools]


def _merge_reasoning_summary(skill_reason: str | None, tool_reason: str | None) -> str:
    parts = [item for item in [skill_reason, tool_reason] if item]
    return "；".join(parts)


def _tool_schemas() -> list[dict[str, Any]]:
    return [
        {"name": "time", "purpose": "解析用户问题中的时间线索。", "inputs": ["question"]},
        {
            "name": "thread_context",
            "purpose": "读取会话 ID、thread ID、显式选择数据集和会话锁定数据集。",
            "inputs": ["conversation", "payload_dataset_id"],
        },
        {
            "name": "manifest_router",
            "purpose": "基于 current Manifest 路由数据集；已有锁定数据集时只能沿用。",
            "inputs": ["question", "locked_dataset_id"],
        },
        {
            "name": "schema_status",
            "purpose": "比较 Manifest 绑定 schema 和当前 schema hash。",
            "inputs": ["route_decision"],
        },
        {
            "name": "clarification",
            "purpose": "生成数据集级澄清，不处理术语或指标细节。",
            "inputs": ["route_decision", "schema_status"],
        },
        {
            "name": "subagent_dispatch",
            "purpose": "数据集明确后生成 SubAgent 调度上下文。",
            "inputs": ["route_decision", "time_context", "thread_context", "schema_status"],
        },
        {"name": "audit_trace", "purpose": "记录 LeadAgent 工具规划和执行摘要。", "inputs": []},
    ]


def resolve_time_context(
    question: str,
    *,
    timezone_name: str = DEFAULT_TIMEZONE,
    now: datetime | None = None,
    prior_time_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """TimeTool：解析用户问题中的常见时间范围线索。"""

    current = _normalize_now(now, timezone_name)
    today = current.date()
    detected = _detect_iso_date_range(question)
    if not detected:
        detected = _detect_chinese_month_or_year(question)
    if not detected:
        detected = _detect_relative_range(question, today, prior_time_context=prior_time_context)

    return {
        "tool": "time",
        "timezone": timezone_name,
        "now": current.isoformat(),
        "today": today.isoformat(),
        "detected_time_range": detected,
        "inherited_from_prior_time": bool(
            detected and str(detected.get("source") or "").startswith("prior_")
        ),
        "prior_time_context": _time_context_summary(prior_time_context),
    }


def resolve_thread_context(
    *,
    conversation: models.Conversation | None = None,
    payload_dataset_id: int | None = None,
    active_dataset_id: int | None = None,
    inheritance_summary: str | None = None,
    multiturn_classification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """ThreadContextTool：整理会话级锁定信息和本轮显式数据集选择。"""

    conversation_dataset_id = conversation.dataset_id if conversation else None
    locked_dataset_id = (
        payload_dataset_id
        if payload_dataset_id is not None
        else (active_dataset_id if active_dataset_id is not None else conversation_dataset_id)
    )
    dataset_lock_source = "none"
    if payload_dataset_id is not None:
        dataset_lock_source = "payload"
    elif active_dataset_id is not None:
        dataset_lock_source = "multiturn_active"
    elif conversation_dataset_id is not None:
        dataset_lock_source = "conversation"
    return {
        "tool": "thread_context",
        "conversation_id": conversation.id if conversation else None,
        "thread_id": conversation.thread_id if conversation else None,
        "user_id": conversation.user_id if conversation else None,
        "payload_dataset_id": payload_dataset_id,
        "conversation_dataset_id": conversation_dataset_id,
        "active_dataset_id": active_dataset_id,
        "locked_dataset_id": locked_dataset_id,
        "dataset_lock_source": dataset_lock_source,
        "inheritance_summary": inheritance_summary,
        "multiturn_classification": multiturn_classification or {},
        "manifest_locked": False,
        "manifest_lock_reason": "首期仅锁定显式数据集；manifest 会话级锁定待持久化字段落地。",
    }


def route_with_manifest(
    db: Session,
    *,
    question: str,
    locked_dataset_id: int | None = None,
) -> dict[str, Any]:
    """ManifestRouterTool：根据 current Manifest 路由或锁定数据集。"""

    decision = route_dataset_for_question(db, question, dataset_id=locked_dataset_id)
    return {
        **decision,
        "tool": "manifest_router",
    }


def check_schema_status(db: Session, route_decision: dict[str, Any]) -> dict[str, Any]:
    """SchemaStatusTool：比较路由 manifest 绑定 schema 和当前 schema hash。"""

    dataset_id = route_decision.get("dataset_id")
    bound_schema_version = route_decision.get("bound_schema_version")
    manifest_version = route_decision.get("manifest_version")
    if not dataset_id:
        return {
            "tool": "schema_status",
            "status": "not_selected",
            "stale": False,
            "dataset_id": None,
            "manifest_version": manifest_version,
            "bound_schema_version": bound_schema_version,
            "latest_schema_version": None,
            "reason": "尚未选定数据集，跳过 schema 状态检查。",
        }

    latest_schema_version = build_dataset_schema_version(db, int(dataset_id))
    if not bound_schema_version:
        return {
            "tool": "schema_status",
            "status": "not_bound",
            "stale": False,
            "dataset_id": int(dataset_id),
            "manifest_version": manifest_version,
            "bound_schema_version": None,
            "latest_schema_version": latest_schema_version,
            "reason": "当前数据集没有 current Manifest 绑定版本，按显式选择继续执行。",
        }

    stale = bound_schema_version != latest_schema_version
    if stale:
        _mark_manifest_needs_review(db, int(dataset_id), manifest_version)
    return {
        "tool": "schema_status",
        "status": "needs_review" if stale else "ok",
        "stale": stale,
        "dataset_id": int(dataset_id),
        "manifest_version": manifest_version,
        "bound_schema_version": bound_schema_version,
        "latest_schema_version": latest_schema_version,
        "reason": (
            "Manifest 绑定 schema 已过期。" if stale else "Manifest 绑定 schema 与当前数据集一致。"
        ),
    }


def build_clarification(
    route_decision: dict[str, Any],
    schema_status: dict[str, Any],
) -> dict[str, Any] | None:
    """ClarificationTool：只生成数据集级澄清，不触碰语义层内部资产。"""

    decision = route_decision.get("decision")
    if decision == "ambiguous":
        return {
            "tool": "clarification",
            "kind": "dataset_choice",
            "message": "多个数据集 Manifest 命中接近，需要用户确认数据集。",
            "candidates": route_decision.get("candidates") or [],
            "reason": route_decision.get("reason"),
        }
    if decision == "no_match":
        return {
            "tool": "clarification",
            "kind": "dataset_missing",
            "message": "未找到足够明确的 current Manifest，需要用户选择数据集或补充问题。",
            "candidates": route_decision.get("candidates") or [],
            "reason": route_decision.get("reason"),
        }
    if schema_status.get("stale"):
        return {
            "tool": "clarification",
            "kind": "manifest_stale",
            "message": "当前 Manifest 绑定 schema 已变化，本轮暂按显式路由继续并记录需 review。",
            "reason": schema_status.get("reason"),
        }
    return None


def build_subagent_dispatch(
    *,
    question: str,
    route_decision: dict[str, Any],
    time_context: dict[str, Any],
    thread_context: dict[str, Any],
    schema_status: dict[str, Any],
    original_question: str | None = None,
) -> dict[str, Any] | None:
    """SubAgentDispatchTool：生成传给后续图工作流的控制面上下文。"""

    if route_decision.get("decision") not in {"selected", "locked"}:
        return None
    dataset_id = route_decision.get("dataset_id")
    if dataset_id is None:
        return None
    capsule = build_subagent_capsule(
        dataset_id=int(dataset_id),
        route_decision=route_decision,
        thread_context=thread_context,
        schema_status=schema_status,
    )
    return {
        "tool": "subagent_dispatch",
        "question": question,
        "original_question": original_question or question,
        "dataset_id": int(dataset_id),
        "manifest_version": route_decision.get("manifest_version"),
        "bound_schema_version": route_decision.get("bound_schema_version"),
        "time_context": time_context,
        "thread_context": thread_context,
        "schema_status": schema_status,
        "route_decision": route_decision,
        "capsule": capsule,
        "subagent_capsule": capsule,
    }


def build_subagent_capsule(
    *,
    dataset_id: int,
    route_decision: dict[str, Any],
    thread_context: dict[str, Any],
    schema_status: dict[str, Any],
) -> dict[str, Any]:
    """生成 SubAgent 数据集内状态胶囊，避免 LeadAgent 直接读写语义层内部资产。"""

    multiturn_classification = thread_context.get("multiturn_classification") or {}
    multiturn_intent = multiturn_classification.get("intent")
    execution_mode = "interpret_result" if multiturn_intent == "interpret" else "query"
    return {
        "scope": "dataset",
        "dataset_id": dataset_id,
        "thread_id": thread_context.get("thread_id"),
        "manifest_version": route_decision.get("manifest_version"),
        "bound_schema_version": route_decision.get("bound_schema_version"),
        "schema_status": schema_status.get("status"),
        "active_dataset_id": thread_context.get("active_dataset_id"),
        "dataset_lock_source": thread_context.get("dataset_lock_source"),
        "inheritance_summary": thread_context.get("inheritance_summary"),
        "multiturn_intent": multiturn_intent,
        "multiturn_classification": multiturn_classification,
        "execution_mode": execution_mode,
        "should_generate_query": execution_mode != "interpret_result",
        "interpretation_source": (
            "prior_capsule.result_digest" if execution_mode == "interpret_result" else None
        ),
        "state_boundary": "LeadAgent 只持有跨轮控制面状态；SubAgent 只读写当前数据集内状态。",
    }


def build_audit_trace(
    *,
    route_decision: dict[str, Any],
    schema_status: dict[str, Any],
    clarification: dict[str, Any] | None,
    dispatch: dict[str, Any] | None,
    selected_skills: list[str] | None = None,
    planned_tool_calls: list[dict[str, Any]] | None = None,
    executed_tool_calls: list[dict[str, Any]] | None = None,
    system_inferred_tool_calls: list[dict[str, Any]] | None = None,
    policy_violations: list[dict[str, Any]] | None = None,
    planner_fallback: bool = False,
) -> dict[str, Any]:
    """AuditTraceTool：输出 LeadAgent 工具调用摘要，便于 Langfuse/消息审计保存。"""

    return {
        "tool": "audit_trace",
        "tools": [
            item.get("tool")
            for item in [*(executed_tool_calls or []), *(system_inferred_tool_calls or [])]
        ],
        "decision": route_decision.get("decision"),
        "dataset_id": route_decision.get("dataset_id"),
        "manifest_version": route_decision.get("manifest_version"),
        "schema_status": schema_status.get("status"),
        "clarification_kind": clarification.get("kind") if clarification else None,
        "dispatched": dispatch is not None,
        "selected_skills": selected_skills or [],
        "planned_tool_count": len(planned_tool_calls or []),
        "executed_tool_count": len(executed_tool_calls or []),
        "system_inferred_tool_count": len(system_inferred_tool_calls or []),
        "policy_violation_count": len(policy_violations or []),
        "planner_fallback": planner_fallback,
    }


def execute_tool_plan(
    db: Session,
    *,
    question: str,
    conversation: models.Conversation | None,
    payload_dataset_id: int | None,
    timezone_name: str,
    now: datetime | None,
    tool_policy: dict[str, Any],
    plan: dict[str, Any],
    active_dataset_id: int | None = None,
    inheritance_summary: str | None = None,
    multiturn_classification: dict[str, Any] | None = None,
    inherited_time_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """ToolExecutor：按计划执行允许的工具，并记录策略违规。"""

    allowed_tools = set(tool_policy.get("allowed_tools") or [])
    blocked_tools = set(tool_policy.get("blocked_tools") or [])
    planned_tool_calls = plan.get("tool_calls") or []
    executed_tool_calls: list[dict[str, Any]] = []
    system_inferred_tool_calls: list[dict[str, Any]] = []
    policy_violations: list[dict[str, Any]] = []
    results: dict[str, Any] = {
        "time_context": None,
        "resolved_question": None,
        "thread_context": None,
        "route_decision": None,
        "schema_status": None,
        "clarification": None,
        "dispatch": None,
    }

    for item in planned_tool_calls:
        tool_name = str((item or {}).get("tool") or "").strip()
        if not tool_name:
            continue
        if tool_name in blocked_tools or tool_name not in allowed_tools:
            policy_violations.append(
                {
                    "tool": tool_name,
                    "reason": "tool_not_allowed_by_policy",
                    "planned_reason": (item or {}).get("reason"),
                }
            )
            continue
        if tool_name == "audit_trace":
            continue

        try:
            executed = _execute_single_tool(
                db,
                tool_name=tool_name,
                question=question,
                conversation=conversation,
                payload_dataset_id=payload_dataset_id,
                active_dataset_id=active_dataset_id,
                inheritance_summary=inheritance_summary,
                multiturn_classification=multiturn_classification,
                inherited_time_context=inherited_time_context,
                timezone_name=timezone_name,
                now=now,
                results=results,
                policy_violations=policy_violations,
            )
        except Exception as exc:
            policy_violations.append({"tool": tool_name, "reason": f"tool_execution_error:{exc}"})
            continue
        if executed:
            executed_tool_calls.append({"tool": tool_name, "reason": (item or {}).get("reason")})

    validation_violations = validate_tool_execution(tool_policy, results)
    policy_violations.extend(validation_violations)
    if _requires_fallback(results, validation_violations):
        return {
            **results,
            "executed_tool_calls": executed_tool_calls,
            "system_inferred_tool_calls": system_inferred_tool_calls,
            "policy_violations": policy_violations,
            "requires_fallback": True,
        }

    route_decision = results["route_decision"] or _default_no_match_decision()
    schema_status = results["schema_status"]
    if schema_status is None:
        schema_status = check_schema_status(db, route_decision)
        system_inferred_tool_calls.append(
            {"tool": "schema_status", "reason": "system_required_after_route"}
        )
    clarification = results["clarification"]
    if clarification is None:
        clarification = build_clarification(route_decision, schema_status)
        if clarification is not None:
            system_inferred_tool_calls.append(
                {"tool": "clarification", "reason": "system_required_after_route"}
            )
    dispatch = results["dispatch"]
    if dispatch is None and route_decision.get("decision") in {"selected", "locked"}:
        resolved_question = results["resolved_question"] or build_resolved_question(
            question,
            results["time_context"],
        )
        dispatch = build_subagent_dispatch(
            question=resolved_question,
            original_question=question,
            route_decision=route_decision,
            time_context=results["time_context"] or {},
            thread_context=results["thread_context"] or {},
            schema_status=schema_status,
        )
        if dispatch is not None:
            system_inferred_tool_calls.append(
                {"tool": "subagent_dispatch", "reason": "system_required_after_selected_route"}
            )

    audit_trace = build_audit_trace(
        route_decision=route_decision,
        schema_status=schema_status,
        clarification=clarification,
        dispatch=dispatch,
        selected_skills=plan.get("selected_skills") or [],
        planned_tool_calls=planned_tool_calls,
        executed_tool_calls=[*executed_tool_calls, {"tool": "audit_trace", "reason": "系统审计"}],
        system_inferred_tool_calls=system_inferred_tool_calls,
        policy_violations=policy_violations,
        planner_fallback=bool(plan.get("planner_fallback")),
    )
    return {
        "time_context": results["time_context"],
        "resolved_question": results["resolved_question"]
        or build_resolved_question(question, results["time_context"]),
        "thread_context": results["thread_context"],
        "route_decision": route_decision,
        "schema_status": schema_status,
        "clarification": clarification,
        "dispatch": dispatch,
        "audit_trace": audit_trace,
        "executed_tool_calls": [
            *executed_tool_calls,
            {"tool": "audit_trace", "reason": "系统审计"},
        ],
        "system_inferred_tool_calls": system_inferred_tool_calls,
        "policy_violations": policy_violations,
        "requires_fallback": False,
    }


def _execute_single_tool(
    db: Session,
    *,
    tool_name: str,
    question: str,
    conversation: models.Conversation | None,
    payload_dataset_id: int | None,
    active_dataset_id: int | None,
    inheritance_summary: str | None,
    multiturn_classification: dict[str, Any] | None,
    inherited_time_context: dict[str, Any] | None,
    timezone_name: str,
    now: datetime | None,
    results: dict[str, Any],
    policy_violations: list[dict[str, Any]],
) -> bool:
    if tool_name == "time":
        results["time_context"] = resolve_time_context(
            question,
            timezone_name=timezone_name,
            now=now,
            prior_time_context=inherited_time_context,
        )
        results["resolved_question"] = build_resolved_question(question, results["time_context"])
        return True
    if tool_name == "thread_context":
        results["thread_context"] = resolve_thread_context(
            conversation=conversation,
            payload_dataset_id=payload_dataset_id,
            active_dataset_id=active_dataset_id,
            inheritance_summary=inheritance_summary,
            multiturn_classification=multiturn_classification,
        )
        return True
    if tool_name == "manifest_router":
        thread_context = results["thread_context"] or resolve_thread_context(
            conversation=conversation,
            payload_dataset_id=payload_dataset_id,
            active_dataset_id=active_dataset_id,
            inheritance_summary=inheritance_summary,
            multiturn_classification=multiturn_classification,
        )
        if results["thread_context"] is None:
            results["thread_context"] = thread_context
            policy_violations.append(
                {"tool": "thread_context", "reason": "auto_dependency_for_manifest_router"}
            )
        results["route_decision"] = route_with_manifest(
            db,
            question=question,
            locked_dataset_id=thread_context.get("locked_dataset_id"),
        )
        return True
    if tool_name == "schema_status":
        route_decision = results["route_decision"]
        if not route_decision:
            policy_violations.append({"tool": tool_name, "reason": "missing_route_decision"})
            return False
        results["schema_status"] = check_schema_status(db, route_decision)
        return True
    if tool_name == "clarification":
        route_decision = results["route_decision"]
        if not route_decision:
            policy_violations.append({"tool": tool_name, "reason": "missing_route_decision"})
            return False
        schema_status = results["schema_status"] or check_schema_status(db, route_decision)
        results["schema_status"] = schema_status
        results["clarification"] = build_clarification(route_decision, schema_status)
        return True
    if tool_name == "subagent_dispatch":
        route_decision = results["route_decision"]
        if not route_decision:
            policy_violations.append({"tool": tool_name, "reason": "missing_route_decision"})
            return False
        if route_decision.get("decision") not in {"selected", "locked"}:
            policy_violations.append({"tool": tool_name, "reason": "dataset_not_confirmed"})
            return False
        schema_status = results["schema_status"] or check_schema_status(db, route_decision)
        results["schema_status"] = schema_status
        results["dispatch"] = build_subagent_dispatch(
            question=results["resolved_question"]
            or build_resolved_question(
                question,
                results["time_context"],
            ),
            original_question=question,
            route_decision=route_decision,
            time_context=results["time_context"] or {},
            thread_context=results["thread_context"] or {},
            schema_status=schema_status,
        )
        return results["dispatch"] is not None
    return False


def validate_tool_execution(
    tool_policy: dict[str, Any],
    results: dict[str, Any],
) -> list[dict[str, Any]]:
    """PolicyValidator：校验工具执行后的关键不变量。"""

    violations: list[dict[str, Any]] = []
    if not results.get("thread_context"):
        violations.append({"tool": "thread_context", "reason": "required_tool_missing"})
    route_decision = results.get("route_decision")
    dispatch = results.get("dispatch")
    if dispatch and not route_decision:
        violations.append({"tool": "subagent_dispatch", "reason": "dispatch_without_route"})
    if dispatch and route_decision and route_decision.get("decision") not in {"selected", "locked"}:
        violations.append(
            {"tool": "subagent_dispatch", "reason": "dispatch_without_confirmed_dataset"}
        )
    if tool_policy.get("explicit_dataset_locked") and route_decision:
        locked_dataset_id = tool_policy.get("locked_dataset_id")
        if route_decision.get("dataset_id") != locked_dataset_id:
            violations.append({"tool": "manifest_router", "reason": "explicit_dataset_changed"})
    schema_status = results.get("schema_status")
    if (
        schema_status
        and schema_status.get("stale")
        and schema_status.get("status") != "needs_review"
    ):
        violations.append({"tool": "schema_status", "reason": "stale_schema_not_recorded"})
    return violations


def _requires_fallback(
    results: dict[str, Any],
    validation_violations: list[dict[str, Any]],
) -> bool:
    if not results.get("route_decision"):
        return True
    missing_required = any(
        item.get("reason") == "required_tool_missing" for item in validation_violations
    )
    return missing_required


def _default_no_match_decision() -> dict[str, Any]:
    return {
        "decision": "no_match",
        "dataset_id": None,
        "manifest_version": None,
        "bound_schema_version": None,
        "score": 0,
        "candidates": [],
        "reason": "LeadAgent 工具计划未产生有效数据集路由结果。",
        "tool": "manifest_router",
    }


def build_resolved_question(question: str, time_context: dict[str, Any] | None) -> str:
    """基于 LeadAgent 时间解析结果生成下游可消费的问题文本。"""

    detected = (time_context or {}).get("detected_time_range") or {}
    start_date = detected.get("start_date")
    end_date = detected.get("end_date")
    if not start_date or not end_date:
        return question

    replacement = _time_range_replacement(detected)
    source = detected.get("source")
    patterns = []
    if source == "relative_last_year":
        patterns = [r"去年|上一年"]
    elif source == "relative_this_year":
        patterns = [r"今年|本年"]
    elif source == "relative_this_month":
        patterns = [r"本月"]
    elif source in {"relative_last_month", "prior_relative_last_month"}:
        patterns = [r"上月|上个月"]
    elif source == "relative_this_week":
        patterns = [r"本周"]
    elif source == "relative_last_week":
        patterns = [r"上周"]
    elif source == "relative_today":
        patterns = [r"今天|今日"]
    elif source == "relative_yesterday":
        patterns = [r"昨天|昨日"]
    elif source == "relative_recent_days":
        patterns = [r"(?:最近|近)\s*\d{1,3}\s*[天日]"]

    for pattern in patterns:
        resolved = re.sub(pattern, replacement, question, count=1)
        if resolved != question:
            return resolved

    label = detected.get("label")
    if label and label in question:
        return question.replace(label, replacement, 1)
    return f"{question}（时间范围：{start_date}至{end_date}）"


def normalize_multiturn_context(multiturn_context: dict[str, Any] | None) -> dict[str, Any]:
    """归一化调用方传入的 LeadAgent 跨轮状态，只保留控制面字段。"""

    if not isinstance(multiturn_context, dict):
        return {
            "active_dataset_id": None,
            "inheritance_summary": None,
            "last_question": None,
            "last_resolved_question": None,
            "raw": {},
        }

    active_dataset_id = _first_int(
        multiturn_context,
        "active_dataset_id",
        "current_dataset_id",
        "last_dataset_id",
        "effective_dataset_id",
        "dataset_id",
    )
    active_dataset = multiturn_context.get("active_dataset")
    if active_dataset_id is None and isinstance(active_dataset, dict):
        active_dataset_id = _coerce_int(
            active_dataset.get("id") or active_dataset.get("dataset_id")
        )

    inheritance_summary = _string_or_none(
        multiturn_context.get("inheritance_summary")
        or multiturn_context.get("summary")
        or multiturn_context.get("last_answer_summary")
        or multiturn_context.get("topic_summary")
    )
    return {
        "active_dataset_id": active_dataset_id,
        "inheritance_summary": inheritance_summary,
        "last_question": _string_or_none(multiturn_context.get("last_question")),
        "last_resolved_question": _string_or_none(multiturn_context.get("last_resolved_question")),
        "topic_anchor": _string_or_none(multiturn_context.get("topic_anchor")),
        "resolved_time_context": _dict_or_none(multiturn_context.get("resolved_time_context")),
        "raw": multiturn_context,
    }


def classify_multiturn_turn(
    question: str,
    *,
    payload_dataset_id: int | None,
    conversation: models.Conversation | None,
    multiturn_context: dict[str, Any],
) -> dict[str, Any]:
    """LeadAgent 多轮分类 fallback：用确定性规则识别续问、切换、解释和闲聊。"""

    normalized_question = re.sub(r"\s+", "", question or "").lower()
    active_dataset_id = multiturn_context.get("active_dataset_id")
    conversation_dataset_id = conversation.dataset_id if conversation else None

    if _looks_like_chitchat(normalized_question):
        intent = "chitchat"
        confidence = 0.86
        reason = "命中闲聊或礼貌用语，不应调度数据集 SubAgent。"
    elif _looks_like_interpret_question(normalized_question):
        intent = "interpret"
        confidence = 0.78
        reason = "命中解释上一轮结果的表达，优先继承 active_dataset_id。"
    elif (
        payload_dataset_id is not None
        and active_dataset_id is not None
        and payload_dataset_id != active_dataset_id
    ):
        intent = "switch"
        confidence = 0.92
        reason = "本轮显式选择的数据集与 active_dataset_id 不同。"
    elif _looks_like_dataset_switch(normalized_question):
        intent = "switch"
        confidence = 0.74
        reason = "命中切换或重新选择数据集的表达，不继承 active_dataset_id。"
    elif active_dataset_id is not None and _looks_like_followup(normalized_question):
        intent = "continue"
        confidence = 0.8
        reason = "命中续问表达，继承 active_dataset_id。"
    elif (
        active_dataset_id is not None
        and payload_dataset_id is None
        and conversation_dataset_id is None
    ):
        intent = "continue"
        confidence = 0.62
        reason = "存在 active_dataset_id 且本轮没有显式切换，按续问处理。"
    else:
        intent = "continue"
        confidence = 0.55
        reason = "未命中特殊多轮意图，按普通问数轮次处理。"

    should_inherit_dataset = (
        intent in {"continue", "interpret"}
        and payload_dataset_id is None
        and active_dataset_id is not None
    )
    return {
        "intent": intent,
        "label": intent,
        "confidence": confidence,
        "source": "heuristic",
        "reason": reason,
        "active_dataset_id": active_dataset_id,
        "conversation_dataset_id": conversation_dataset_id,
        "payload_dataset_id": payload_dataset_id,
        "should_inherit_dataset": should_inherit_dataset,
        "inheritance_summary": multiturn_context.get("inheritance_summary"),
    }


def _looks_like_chitchat(normalized_question: str) -> bool:
    if not normalized_question:
        return True
    return bool(
        re.fullmatch(
            r"(你好|您好|hi|hello|谢谢|感谢|辛苦了|好的|好|ok|收到|再见|拜拜)[!！。.]?",
            normalized_question,
        )
    )


def _looks_like_interpret_question(normalized_question: str) -> bool:
    return bool(
        re.search(
            r"(解释|说明|解读|什么意思|怎么看|为什么|原因|上面.*结果|刚才.*结果)",
            normalized_question,
        )
    )


def _looks_like_dataset_switch(normalized_question: str) -> bool:
    return bool(
        re.search(
            r"(切换|换到|改用|重新选择|选择.*数据集|使用.*数据集|换.*数据集)", normalized_question
        )
    )


def _looks_like_followup(normalized_question: str) -> bool:
    if len(normalized_question) <= 18:
        return True
    return bool(
        re.search(
            r"(继续|刚才|上面|上一轮|这个|那个|这些|再看|拆分|细分|换成|改成|同比|环比)",
            normalized_question,
        )
    )


def _first_int(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = _coerce_int(payload.get(key))
        if value is not None:
            return value
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _time_context_summary(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    detected = value.get("detected_time_range")
    if not isinstance(detected, dict):
        return None
    return {
        "label": detected.get("label"),
        "start_date": detected.get("start_date"),
        "end_date": detected.get("end_date"),
        "granularity": detected.get("granularity"),
        "source": detected.get("source"),
    }


def _time_range_replacement(detected: dict[str, Any]) -> str:
    start_date = str(detected.get("start_date") or "")
    end_date = str(detected.get("end_date") or "")
    granularity = detected.get("granularity")
    if granularity == "year" and start_date[:4] == end_date[:4]:
        return f"{start_date[:4]}年"
    if granularity == "month" and start_date[:7] == end_date[:7]:
        year, month = start_date[:7].split("-")
        return f"{int(year)}年{int(month)}月"
    if start_date == end_date:
        return start_date
    return f"{start_date}至{end_date}"


def build_lead_agent_context(
    db: Session,
    *,
    question: str,
    conversation: models.Conversation | None = None,
    payload_dataset_id: int | None = None,
    multiturn_context: dict[str, Any] | None = None,
    timezone_name: str = DEFAULT_TIMEZONE,
    now: datetime | None = None,
    tracer: Any | None = None,
    trace_context: Any | None = None,
) -> dict[str, Any]:
    """LeadAgent：按 ToolPolicy + Skills + Planner 执行控制面工具。"""

    normalized_multiturn_context = normalize_multiturn_context(multiturn_context)
    multiturn_classification = classify_multiturn_turn(
        question,
        payload_dataset_id=payload_dataset_id,
        conversation=conversation,
        multiturn_context=normalized_multiturn_context,
    )
    inherited_active_dataset_id = (
        normalized_multiturn_context.get("active_dataset_id")
        if multiturn_classification.get("should_inherit_dataset")
        else None
    )
    tool_policy = build_tool_policy(
        conversation=conversation,
        payload_dataset_id=payload_dataset_id,
        active_dataset_id=inherited_active_dataset_id,
    )
    skills = available_lead_skills(tool_policy)
    conversation_summary = _conversation_summary(
        conversation,
        payload_dataset_id,
        normalized_multiturn_context,
        multiturn_classification,
    )
    if tracer is not None and trace_context is not None and hasattr(tracer, "start_span"):
        tracer.start_span(
            trace_context,
            node="lead_agent_control_plane",
            display_name="lead_agent_control_plane",
            input_payload={
                "question": question,
                "conversation": conversation_summary,
                "tool_policy": tool_policy,
                "available_skills": [item.get("name") for item in skills],
                "multiturn_context": normalized_multiturn_context,
                "multiturn_classification": multiturn_classification,
                "progressive_disclosure": True,
            },
        )
    if multiturn_classification.get("intent") == "chitchat":
        lead_agent_context = _build_chitchat_lead_agent_context(
            question=question,
            conversation=conversation,
            payload_dataset_id=payload_dataset_id,
            active_dataset_id=normalized_multiturn_context.get("active_dataset_id"),
            inheritance_summary=normalized_multiturn_context.get("inheritance_summary"),
            multiturn_context=normalized_multiturn_context,
            multiturn_classification=multiturn_classification,
            tool_policy=tool_policy,
            skills=skills,
            timezone_name=timezone_name,
            now=now,
        )
        if tracer is not None and trace_context is not None and hasattr(tracer, "end_span"):
            tracer.end_span(
                trace_context,
                node="lead_agent_control_plane",
                output_payload=lead_agent_context,
            )
        return lead_agent_context
    plan = plan_tool_calls_with_llm(
        db,
        question=question,
        conversation_summary=conversation_summary,
        tool_policy=tool_policy,
        skills=skills,
        tracer=tracer,
        trace_context=trace_context,
    )
    execution = execute_tool_plan(
        db,
        question=question,
        conversation=conversation,
        payload_dataset_id=payload_dataset_id,
        timezone_name=timezone_name,
        now=now,
        tool_policy=tool_policy,
        plan=plan,
        active_dataset_id=inherited_active_dataset_id,
        inheritance_summary=normalized_multiturn_context.get("inheritance_summary"),
        multiturn_classification=multiturn_classification,
        inherited_time_context=normalized_multiturn_context.get("resolved_time_context"),
    )
    if execution.get("requires_fallback") and not plan.get("planner_fallback"):
        fallback_plan = build_fallback_plan(reason="planner_incomplete_execution")
        fallback_execution = execute_tool_plan(
            db,
            question=question,
            conversation=conversation,
            payload_dataset_id=payload_dataset_id,
            timezone_name=timezone_name,
            now=now,
            tool_policy=tool_policy,
            plan=fallback_plan,
            active_dataset_id=inherited_active_dataset_id,
            inheritance_summary=normalized_multiturn_context.get("inheritance_summary"),
            multiturn_classification=multiturn_classification,
            inherited_time_context=normalized_multiturn_context.get("resolved_time_context"),
        )
        fallback_execution["policy_violations"] = [
            *(execution.get("policy_violations") or []),
            *(fallback_execution.get("policy_violations") or []),
        ]
        plan = fallback_plan
        execution = fallback_execution

    route_decision = execution.get("route_decision") or _default_no_match_decision()
    schema_status = execution.get("schema_status") or check_schema_status(db, route_decision)
    clarification = execution.get("clarification")
    if clarification is None:
        clarification = build_clarification(route_decision, schema_status)
    dispatch = execution.get("dispatch")
    effective_dataset_id = dispatch.get("dataset_id") if dispatch else None
    lead_agent_context = {
        "tool_policy": tool_policy,
        "skills": skills,
        "selected_skills": plan.get("selected_skills") or [],
        "planned_tool_calls": plan.get("tool_calls") or [],
        "executed_tool_calls": execution.get("executed_tool_calls") or [],
        "system_inferred_tool_calls": execution.get("system_inferred_tool_calls") or [],
        "policy_violations": execution.get("policy_violations") or [],
        "progressive_disclosure": bool(plan.get("progressive_disclosure")),
        "disclosed_tools": plan.get("disclosed_tools") or [],
        "skill_selection_reasoning_summary": plan.get("skill_selection_reasoning_summary"),
        "tool_planning_reasoning_summary": plan.get("tool_planning_reasoning_summary"),
        "planner_fallback": bool(plan.get("planner_fallback")),
        "fallback_reason": plan.get("fallback_reason"),
        "planner_reasoning_summary": plan.get("reasoning_summary"),
        "original_question": question,
        "resolved_question": execution.get("resolved_question")
        or build_resolved_question(
            question,
            execution.get("time_context"),
        ),
        "multiturn_context": normalized_multiturn_context,
        "multiturn_classification": multiturn_classification,
        "active_dataset_id": normalized_multiturn_context.get("active_dataset_id"),
        "inheritance_summary": normalized_multiturn_context.get("inheritance_summary"),
        "time_context": execution.get("time_context"),
        "thread_context": execution.get("thread_context"),
        "route_decision": route_decision,
        "schema_status": schema_status,
        "clarification": clarification,
        "dispatch": dispatch,
        "audit_trace": execution.get("audit_trace"),
        "should_continue": dispatch is not None,
        "effective_dataset_id": effective_dataset_id,
    }
    if tracer is not None and trace_context is not None and hasattr(tracer, "end_span"):
        tracer.end_span(
            trace_context,
            node="lead_agent_control_plane",
            output_payload=lead_agent_context,
        )
    return lead_agent_context


def _build_chitchat_lead_agent_context(
    *,
    question: str,
    conversation: models.Conversation | None,
    payload_dataset_id: int | None,
    active_dataset_id: int | None,
    inheritance_summary: str | None,
    multiturn_context: dict[str, Any],
    multiturn_classification: dict[str, Any],
    tool_policy: dict[str, Any],
    skills: list[dict[str, Any]],
    timezone_name: str,
    now: datetime | None,
) -> dict[str, Any]:
    """闲聊轮次不进入数据集路由，防止误把 active_dataset_id 当成查询请求。"""

    time_context = resolve_time_context(question, timezone_name=timezone_name, now=now)
    thread_context = resolve_thread_context(
        conversation=conversation,
        payload_dataset_id=payload_dataset_id,
        active_dataset_id=None,
        inheritance_summary=inheritance_summary,
        multiturn_classification=multiturn_classification,
    )
    route_decision = {
        "decision": "chitchat",
        "dataset_id": None,
        "manifest_version": None,
        "bound_schema_version": None,
        "score": 0,
        "candidates": [],
        "reason": "LeadAgent 多轮分类识别为闲聊，本轮不进行数据集路由。",
        "tool": "manifest_router",
    }
    schema_status = {
        "tool": "schema_status",
        "status": "not_selected",
        "stale": False,
        "dataset_id": None,
        "manifest_version": None,
        "bound_schema_version": None,
        "latest_schema_version": None,
        "reason": "闲聊轮次不选定数据集，跳过 schema 状态检查。",
    }
    clarification = {
        "tool": "clarification",
        "kind": "chitchat",
        "message": "本轮是闲聊或礼貌表达，不需要调度数据集 SubAgent。",
        "reason": multiturn_classification.get("reason"),
    }
    executed_tool_calls = [
        {"tool": "time", "reason": "记录本轮时间上下文。"},
        {"tool": "thread_context", "reason": "记录多轮上下文但不继承为查询。"},
        {"tool": "audit_trace", "reason": "系统审计"},
    ]
    audit_trace = build_audit_trace(
        route_decision=route_decision,
        schema_status=schema_status,
        clarification=clarification,
        dispatch=None,
        selected_skills=[],
        planned_tool_calls=[],
        executed_tool_calls=executed_tool_calls,
        planner_fallback=True,
    )
    return {
        "tool_policy": tool_policy,
        "skills": skills,
        "selected_skills": [],
        "planned_tool_calls": [],
        "executed_tool_calls": executed_tool_calls,
        "system_inferred_tool_calls": [],
        "policy_violations": [],
        "progressive_disclosure": False,
        "disclosed_tools": [],
        "skill_selection_reasoning_summary": None,
        "tool_planning_reasoning_summary": None,
        "planner_fallback": True,
        "fallback_reason": "multiturn_chitchat",
        "planner_reasoning_summary": "LeadAgent 多轮分类识别为闲聊，跳过工具规划。",
        "original_question": question,
        "resolved_question": question,
        "multiturn_context": multiturn_context,
        "multiturn_classification": multiturn_classification,
        "active_dataset_id": active_dataset_id,
        "inheritance_summary": inheritance_summary,
        "time_context": time_context,
        "thread_context": thread_context,
        "route_decision": route_decision,
        "schema_status": schema_status,
        "clarification": clarification,
        "dispatch": None,
        "audit_trace": audit_trace,
        "should_continue": False,
        "effective_dataset_id": None,
    }


def _normalize_now(now: datetime | None, timezone_name: str) -> datetime:
    timezone = ZoneInfo(timezone_name)
    if now is None:
        return datetime.now(timezone)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone)
    return now.astimezone(timezone)


def _range_payload(
    *,
    label: str,
    start_date,
    end_date,
    granularity: str,
    source: str,
) -> dict[str, str]:
    return {
        "label": label,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "granularity": granularity,
        "source": source,
    }


def _detect_iso_date_range(question: str) -> dict[str, str] | None:
    matches = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", question)
    if not matches:
        return None
    dates = [datetime.strptime(item, "%Y-%m-%d").date() for item in matches[:2]]
    start_date = min(dates)
    end_date = max(dates)
    return _range_payload(
        label="至".join(date.isoformat() for date in [start_date, end_date][: len(dates)]),
        start_date=start_date,
        end_date=end_date,
        granularity="range" if len(dates) > 1 else "day",
        source="explicit_date",
    )


def _detect_chinese_month_or_year(question: str) -> dict[str, str] | None:
    month_match = re.search(r"(?P<year>\d{4})\s*年\s*(?P<month>\d{1,2})\s*月", question)
    if month_match:
        year = int(month_match.group("year"))
        month = int(month_match.group("month"))
        if 1 <= month <= 12:
            last_day = monthrange(year, month)[1]
            return _range_payload(
                label=f"{year}年{month}月",
                start_date=datetime(year, month, 1).date(),
                end_date=datetime(year, month, last_day).date(),
                granularity="month",
                source="explicit_month",
            )

    year_match = re.search(r"(?P<year>\d{4})\s*年", question)
    if year_match:
        year = int(year_match.group("year"))
        return _range_payload(
            label=f"{year}年",
            start_date=datetime(year, 1, 1).date(),
            end_date=datetime(year, 12, 31).date(),
            granularity="year",
            source="explicit_year",
        )
    return None


def _detect_relative_range(
    question: str,
    today,
    *,
    prior_time_context: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    prior_detected = _prior_detected_time_range(prior_time_context)
    prior_month = _relative_prior_month(question, prior_detected)
    if prior_month:
        return prior_month

    recent_match = re.search(r"(最近|近)\s*(?P<days>\d{1,3})\s*[天日]", question)
    if recent_match:
        days = max(1, int(recent_match.group("days")))
        return _range_payload(
            label=f"最近{days}日",
            start_date=today - timedelta(days=days - 1),
            end_date=today,
            granularity="day",
            source="relative_recent_days",
        )

    if re.search(r"今天|今日", question):
        return _range_payload(
            label="今天",
            start_date=today,
            end_date=today,
            granularity="day",
            source="relative_today",
        )
    if re.search(r"昨天|昨日", question):
        yesterday = today - timedelta(days=1)
        return _range_payload(
            label="昨天",
            start_date=yesterday,
            end_date=yesterday,
            granularity="day",
            source="relative_yesterday",
        )
    if "本周" in question:
        start = today - timedelta(days=today.weekday())
        return _range_payload(
            label="本周",
            start_date=start,
            end_date=today,
            granularity="week",
            source="relative_this_week",
        )
    if "上周" in question:
        this_week_start = today - timedelta(days=today.weekday())
        start = this_week_start - timedelta(days=7)
        return _range_payload(
            label="上周",
            start_date=start,
            end_date=start + timedelta(days=6),
            granularity="week",
            source="relative_last_week",
        )
    if "本月" in question:
        return _range_payload(
            label="本月",
            start_date=today.replace(day=1),
            end_date=today,
            granularity="month",
            source="relative_this_month",
        )
    if "上月" in question or "上个月" in question:
        this_month_start = today.replace(day=1)
        last_month_end = this_month_start - timedelta(days=1)
        return _range_payload(
            label="上月",
            start_date=last_month_end.replace(day=1),
            end_date=last_month_end,
            granularity="month",
            source="relative_last_month",
        )
    if re.search(r"今年|本年", question):
        return _range_payload(
            label="今年",
            start_date=today.replace(month=1, day=1),
            end_date=today,
            granularity="year",
            source="relative_this_year",
        )
    if re.search(r"去年|上一年", question):
        year = today.year - 1
        return _range_payload(
            label="去年",
            start_date=datetime(year, 1, 1).date(),
            end_date=datetime(year, 12, 31).date(),
            granularity="year",
            source="relative_last_year",
        )
    return None


def _prior_detected_time_range(prior_time_context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(prior_time_context, dict):
        return None
    detected = prior_time_context.get("detected_time_range")
    return detected if isinstance(detected, dict) else None


def _relative_prior_month(
    question: str, prior_detected: dict[str, Any] | None
) -> dict[str, str] | None:
    """基于上一轮时间范围解析“再看上个月”，避免始终按今天倒推。"""

    if not prior_detected or not re.search(r"上月|上个月", question):
        return None
    start_text = str(prior_detected.get("start_date") or "")
    try:
        start_date = datetime.strptime(start_text, "%Y-%m-%d").date()
    except ValueError:
        return None
    current_month_start = start_date.replace(day=1)
    prior_month_end = current_month_start - timedelta(days=1)
    prior_month_start = prior_month_end.replace(day=1)
    return _range_payload(
        label="上个月",
        start_date=prior_month_start,
        end_date=prior_month_end,
        granularity="month",
        source="prior_relative_last_month",
    )


def _mark_manifest_needs_review(
    db: Session,
    dataset_id: int,
    manifest_version: str | None,
) -> None:
    if not manifest_version:
        return
    manifest = (
        db.query(models.DatasetSubAgentManifest)
        .filter(
            models.DatasetSubAgentManifest.dataset_id == dataset_id,
            models.DatasetSubAgentManifest.manifest_version == manifest_version,
        )
        .first()
    )
    if manifest and manifest.review_status != "needs_review":
        manifest.review_status = "needs_review"
        db.commit()


# ============================================================
# Phase 2: 上提 Merge 阶段到 LeadAgent
# ============================================================


def merge_multiturn_decision_for_chat(
    *,
    state: dict,
    out_capsule_factory: Callable | None = None,
    tracer: Any | None = None,
    trace_context: Any | None = None,
) -> MergeDecision:
    """LeadAgent 控制面：在 LangGraph 之外完成多轮合并决策。

    Phase 2 上提：原 LangGraph `merge_prior_context_node` 节点内的决策逻辑整体迁到这里。
    LangGraph 入口仍保留同名 `merge_prior_context` 节点（已改为 noop 虚拟 span 节点），
    仅为兼容 SSE 阶段标签和 observability 链路；真正的决策由本函数产出。

    调用方在 chat.py 调 LangGraph 之前：
    1. 先调 `build_lead_agent_context` 拿到 `lead_agent_context`
    2. 再调本函数得到 `MergeDecision`
    3. 早退判定：若 `decision.interpret_payload is not None` → 直接生成 answer
    4. 否则把 decision 字段塞进 LangGraph initial_state
    """
    if tracer is not None and trace_context is not None and hasattr(tracer, "start_span"):
        tracer.start_span(
            trace_context,
            node="lead.merge_prior_context",
            display_name="lead.merge_prior_context",
            input_payload={
                "turn_type": state.get("turn_type"),
                "has_prior_capsule": state.get("prior_capsule") is not None,
                "has_lead_agent_context": state.get("lead_agent_context") is not None,
                "dataset_id": state.get("dataset_id"),
            },
        )
    builder = MultiturnContextBuilder(out_capsule_factory=out_capsule_factory)
    decision = builder.build(state)

    if tracer is not None and trace_context is not None and hasattr(tracer, "end_span"):
        tracer.end_span(
            trace_context,
            node="lead.merge_prior_context",
            output_payload={
                "turn_type": decision.turn_type,
                "has_synthesized_question": decision.synthesized_question is not None,
                "has_blueprint_shortcut": decision.blueprint_shortcut is not None,
                "is_interpret": decision.interpret_payload is not None,
                "merge_debug": decision.merge_debug,
            },
        )
    return decision
