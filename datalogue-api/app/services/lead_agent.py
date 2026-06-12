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
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app import models
from app.core.config import get_settings
from app.graph.llm import get_llm
from app.prompts.lead_agent import LEAD_AGENT_PLANNER_SYSTEM
from app.services.dataset_manifest import build_dataset_schema_version
from app.services.dataset_router import route_dataset_for_question
from app.services.llm_config import resolve_llm_config
from app.services.observability.prompts import get_prompt_manager
from app.utils.json_utils import safe_json_parse

DEFAULT_TIMEZONE = "Asia/Shanghai"
LEAD_AGENT_PROMPT_NAME = "lead_agent_planner"
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
    LeadSkill("ConversationContinuitySkill", "处理会话上下文和显式数据集锁定。", ("thread_context",)),
    LeadSkill("DatasetRoutingSkill", "选择或确认候选数据集。", ("manifest_router", "clarification")),
    LeadSkill("SchemaFreshnessSkill", "检查 Manifest 绑定 schema 是否过期。", ("schema_status",)),
    LeadSkill("SubAgentDelegationSkill", "判断是否可以把问题交给 SubAgent。", ("subagent_dispatch",)),
    LeadSkill("AuditSkill", "记录 LeadAgent 工具规划和执行轨迹。", ("audit_trace",)),
)


def build_tool_policy(
    *,
    conversation: models.Conversation | None = None,
    payload_dataset_id: int | None = None,
) -> dict[str, Any]:
    """ToolPolicy：生成 LeadAgent 本轮可用工具和硬性边界。"""

    locked_dataset_id = payload_dataset_id if payload_dataset_id is not None else (
        conversation.dataset_id if conversation else None
    )
    constraints = [
        "LeadAgent 只能使用控制面工具，不可读取指标、维度、术语、蓝图、SQL 或字段级 schema。",
        "ToolPolicy.blocked_tools 中的工具即使被 LLM 规划也不能执行。",
        "未确认 dataset 时不可执行 subagent_dispatch。",
        "显式选择数据集或会话已锁定数据集时，manifest_router 只能锁定该数据集，不可自动改选。",
        "schema stale 必须记录到 schema_status 和 audit_trace。",
    ]
    return {
        "required_tools": ["thread_context"],
        "allowed_tools": list(ALLOWED_LEAD_TOOLS),
        "blocked_tools": list(BLOCKED_LEAD_TOOLS),
        "constraints": constraints,
        "locked_dataset_id": locked_dataset_id,
        "explicit_dataset_locked": payload_dataset_id is not None,
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

    availability = _lead_agent_llm_available(db)
    if not availability["available"]:
        return build_fallback_plan(reason=availability["reason"])

    generation = None
    planner_input = {
        "question": question,
        "conversation": conversation_summary,
        "tool_policy": tool_policy,
        "skills": skills,
        "tool_schemas": _tool_schemas(),
    }
    try:
        prompt = get_prompt_manager().get_text_prompt(
            LEAD_AGENT_PROMPT_NAME,
            fallback=LEAD_AGENT_PLANNER_SYSTEM,
        )
        llm = get_llm(temperature=0.1, role="lead_agent", db=db)
        messages = [
            SystemMessage(content=prompt.content),
            HumanMessage(content=json.dumps(planner_input, ensure_ascii=False, default=str)),
        ]
        if tracer is not None and trace_context is not None:
            generation = tracer.start_generation(
                name="llm.lead_agent_planner",
                model=getattr(llm, "model_name", None) or getattr(llm, "model", None),
                messages=messages,
                metadata={
                    "path": "lead_agent_planner",
                    "prompt_name": LEAD_AGENT_PROMPT_NAME,
                    "prompt_version": prompt.version,
                    "prompt_source": prompt.source,
                    "tool_policy": tool_policy,
                    "skills": [item.get("name") for item in skills],
                },
            )
        response = llm.invoke(messages)
        raw_content = str(getattr(response, "content", "") or "")
        parsed = safe_json_parse(raw_content)
        normalized = _normalize_planner_plan(parsed)
        if tracer is not None:
            tracer.end_generation(
                generation,
                output=raw_content,
                usage=getattr(response, "usage_metadata", None),
                metadata={
                    "path": "lead_agent_planner",
                    "parse_ok": bool(normalized),
                    "planner_fallback": not bool(normalized),
                },
            )
        if not normalized:
            return build_fallback_plan(reason="planner_invalid_json")
        normalized["planner_fallback"] = False
        normalized["fallback_reason"] = None
        return normalized
    except Exception as exc:
        if tracer is not None:
            tracer.end_generation(
                generation,
                output=f"LeadAgent Planner 调用失败: {exc}",
                usage=None,
                metadata={
                    "path": "lead_agent_planner",
                    "parse_ok": False,
                    "planner_fallback": True,
                    "error": str(exc),
                },
            )
        logger.warning("LeadAgent Planner 调用失败，使用安全降级计划: %s", exc)
        return build_fallback_plan(reason="planner_llm_error")


def _conversation_summary(
    conversation: models.Conversation | None,
    payload_dataset_id: int | None,
) -> dict[str, Any]:
    return {
        "conversation_id": conversation.id if conversation else None,
        "thread_id": conversation.thread_id if conversation else None,
        "conversation_dataset_id": conversation.dataset_id if conversation else None,
        "payload_dataset_id": payload_dataset_id,
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
        str(item).strip()
        for item in value.get("selected_skills") or []
        if str(item).strip()
    ]
    return {
        "reasoning_summary": str(value.get("reasoning_summary") or "").strip(),
        "selected_skills": selected_skills,
        "tool_calls": tool_calls,
    }


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
) -> dict[str, Any]:
    """TimeTool：解析用户问题中的常见时间范围线索。"""

    current = _normalize_now(now, timezone_name)
    today = current.date()
    detected = _detect_iso_date_range(question)
    if not detected:
        detected = _detect_chinese_month_or_year(question)
    if not detected:
        detected = _detect_relative_range(question, today)

    return {
        "tool": "time",
        "timezone": timezone_name,
        "now": current.isoformat(),
        "today": today.isoformat(),
        "detected_time_range": detected,
    }


def resolve_thread_context(
    *,
    conversation: models.Conversation | None = None,
    payload_dataset_id: int | None = None,
) -> dict[str, Any]:
    """ThreadContextTool：整理会话级锁定信息和本轮显式数据集选择。"""

    conversation_dataset_id = conversation.dataset_id if conversation else None
    locked_dataset_id = payload_dataset_id if payload_dataset_id is not None else conversation_dataset_id
    return {
        "tool": "thread_context",
        "conversation_id": conversation.id if conversation else None,
        "thread_id": conversation.thread_id if conversation else None,
        "user_id": conversation.user_id if conversation else None,
        "payload_dataset_id": payload_dataset_id,
        "conversation_dataset_id": conversation_dataset_id,
        "locked_dataset_id": locked_dataset_id,
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
        "reason": "Manifest 绑定 schema 已过期。" if stale else "Manifest 绑定 schema 与当前数据集一致。",
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
        system_inferred_tool_calls.append({"tool": "schema_status", "reason": "system_required_after_route"})
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
        "executed_tool_calls": [*executed_tool_calls, {"tool": "audit_trace", "reason": "系统审计"}],
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
    timezone_name: str,
    now: datetime | None,
    results: dict[str, Any],
    policy_violations: list[dict[str, Any]],
) -> bool:
    if tool_name == "time":
        results["time_context"] = resolve_time_context(question, timezone_name=timezone_name, now=now)
        results["resolved_question"] = build_resolved_question(question, results["time_context"])
        return True
    if tool_name == "thread_context":
        results["thread_context"] = resolve_thread_context(
            conversation=conversation,
            payload_dataset_id=payload_dataset_id,
        )
        return True
    if tool_name == "manifest_router":
        thread_context = results["thread_context"] or resolve_thread_context(
            conversation=conversation,
            payload_dataset_id=payload_dataset_id,
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
            question=results["resolved_question"] or build_resolved_question(
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
        violations.append({"tool": "subagent_dispatch", "reason": "dispatch_without_confirmed_dataset"})
    if tool_policy.get("explicit_dataset_locked") and route_decision:
        locked_dataset_id = tool_policy.get("locked_dataset_id")
        if route_decision.get("dataset_id") != locked_dataset_id:
            violations.append({"tool": "manifest_router", "reason": "explicit_dataset_changed"})
    schema_status = results.get("schema_status")
    if schema_status and schema_status.get("stale") and schema_status.get("status") != "needs_review":
        violations.append({"tool": "schema_status", "reason": "stale_schema_not_recorded"})
    return violations


def _requires_fallback(
    results: dict[str, Any],
    validation_violations: list[dict[str, Any]],
) -> bool:
    if not results.get("route_decision"):
        return True
    missing_required = any(item.get("reason") == "required_tool_missing" for item in validation_violations)
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
    elif source == "relative_last_month":
        patterns = [r"上月"]
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
    timezone_name: str = DEFAULT_TIMEZONE,
    now: datetime | None = None,
    tracer: Any | None = None,
    trace_context: Any | None = None,
) -> dict[str, Any]:
    """LeadAgent：按 ToolPolicy + Skills + Planner 执行控制面工具。"""

    tool_policy = build_tool_policy(
        conversation=conversation,
        payload_dataset_id=payload_dataset_id,
    )
    skills = available_lead_skills(tool_policy)
    plan = plan_tool_calls_with_llm(
        db,
        question=question,
        conversation_summary=_conversation_summary(conversation, payload_dataset_id),
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
    return {
        "tool_policy": tool_policy,
        "skills": skills,
        "selected_skills": plan.get("selected_skills") or [],
        "planned_tool_calls": plan.get("tool_calls") or [],
        "executed_tool_calls": execution.get("executed_tool_calls") or [],
        "system_inferred_tool_calls": execution.get("system_inferred_tool_calls") or [],
        "policy_violations": execution.get("policy_violations") or [],
        "planner_fallback": bool(plan.get("planner_fallback")),
        "fallback_reason": plan.get("fallback_reason"),
        "planner_reasoning_summary": plan.get("reasoning_summary"),
        "original_question": question,
        "resolved_question": execution.get("resolved_question") or build_resolved_question(
            question,
            execution.get("time_context"),
        ),
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


def _detect_relative_range(question: str, today) -> dict[str, str] | None:
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
    if "上月" in question:
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
