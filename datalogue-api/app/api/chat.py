# ============================================================
# File Name   : chat.py
# Description:
#   聊天问数 API 端点。
#
# Responsibilities:
#   - 流式输出 NL2SQL 工作流事件和最终回答。
#   - 持久化聊天消息、SQL 和执行轨迹元数据。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# 问数对话路由 — SSE 流式输出 + LangGraph Agent 工作流

import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app import schemas, models
from app.graph.workflow import build_workflow
from app.services.answer_explanation import (
    build_answer_explanation,
)
from app.services.observability.context import (
    current_observability_context,
    set_observability_context,
)
from app.services.observability.feedback import submit_message_feedback
from app.services.observability.tracer import get_observability_tracer
from app.services.lead_agent import (
    build_lead_agent_context,
    merge_multiturn_decision_for_chat,
)
from app.services.lead_agent_routing import (
    resolve_term_clarification,
    route_query_intent,
)
from app.services.dataset_subagent import DatasetSubAgent
from app.services.multiturn_context import MergeDecision
from app.services.report_generation import stream_sql_result_report
from app.services.runner import DatasetSubAgentRequest, InProcessDatasetSubAgentRunner
from app.services.conversation_store import (
    ConversationStore,
    pending_clarification_from_final_payload,
    session_key,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# 节点名称到前端展示名的映射
_NODE_DISPLAY_NAMES = {
    "merge_prior_context": "多轮上下文",
    "clarification_resolution": "澄清解析",
    "intent_recognition": "意图识别",
    "entry_intent_classification": "入口分类",
    "analysis_blueprint_execute": "蓝图执行",
    "schema_recall": "Schema 召回",
    "term_conflict_resolve": "术语冲突解析",
    "metric_resolve": "指标解析",
    "dsl_generate": "DSL 生成",
    "dsl_validate": "DSL 校验",
    "dsl_compiler": "SQL 编译",
    "sql_execute": "SQL 执行",
    "sql_audit": "SQL 诊断",
    "report_generator": "报告生成",
    "lead_agent_report_generator": "LeadAgent 报告生成",
}

_STATE_OUTPUT_KEYS = {
    "conversation_id",
    "original_question",
    "resolved_question",
    "manifest_version",
    "bound_schema_version",
    "time_context",
    "thread_context",
    "route_decision",
    "schema_status",
    "lead_agent_context",
    "skip_subagent_report",
    "report_owner",
    "subagent_report_skipped",
    "lead_agent_report",
    "intent",
    "entities",
    "entry_intent",
    "entry_route",
    "entry_reason",
    "blueprint_id",
    "blueprint_match",
    "blueprint_context",
    "knowledge_term_id",
    "route_payload",
    "clarification_response",
    "clarification_resolution_result",
    "prior_capsule",
    "prior_capsule_status",
    "out_capsule",
    "multiturn_context",
    "turn_type",
    "merge_debug",
    "selected_term_id",
    "schema_context",
    "query_constraints",
    "dataset_context_debug",
    "datasource_context",
    "term_normalization",
    "semantic_asset_resolution",
    "metric_resolution",
    "dsl",
    "dsl_valid",
    "sql",
    "sql_result",
    "datasource_dialect",
    "sql_audit_result",
    "sql_diagnosis",
    "sql_retry_trace",
    "answer",
    "answer_explanation",
    "sql_list",
    "error",
    "generation_mode",
    "should_retry",
    "token_usage",
}

TERM_CLARIFICATION_TTL_MINUTES = 30


def _sse_data(payload: dict) -> dict:
    """将 SSE payload 转成 JSON 字符串，兼容 datetime/date/Decimal 等对象。"""
    return {"data": json.dumps(jsonable_encoder(payload), ensure_ascii=False)}


def _is_state_output(value: dict) -> bool:
    """判断字典是否像 AgentState 节点输出。"""
    return bool(_STATE_OUTPUT_KEYS.intersection(value.keys()))


def _find_state_output(value: object, lg_node: str = "", depth: int = 0) -> dict:
    """递归查找 LangGraph/LCEL 事件中的 AgentState 输出片段。"""
    if depth > 5 or not isinstance(value, dict):
        return {}

    if lg_node and isinstance(value.get(lg_node), dict):
        nested = _find_state_output(value[lg_node], lg_node, depth + 1)
        return nested or value[lg_node]

    if _is_state_output(value):
        return value

    for key in ("output", "__end__", "state", "result"):
        nested = _find_state_output(value.get(key), lg_node, depth + 1)
        if nested:
            return nested

    if len(value) == 1:
        nested = _find_state_output(next(iter(value.values())), lg_node, depth + 1)
        if nested:
            return nested

    return {}


def _extract_node_output(event: dict, lg_node: str) -> dict:
    """从 LangGraph 事件中提取当前节点的真实输出。

    astream_events(version="v2") 在不同 LangGraph 版本/事件层级下可能返回两类结构：
    1. {"output": {"entry_intent": "..."}}
    2. {"output": {"entry_intent_classification": {"entry_intent": "..."}}}
    前端 step 事件需要的是节点真实输出，而不是外层节点名包装。
    """
    return _find_state_output(event.get("data", {}).get("output", {}) or {}, lg_node)


def _term_candidate_display(candidate: dict, term: models.BusinessTerm | None = None) -> dict:
    """归一化术语候选展示字段，兼容历史 payload 和前端字段命名。"""

    name = (
        candidate.get("name")
        or candidate.get("term_name")
        or candidate.get("termName")
        or (term.name if term else None)
    )
    display_name = (
        candidate.get("display_name")
        or candidate.get("displayName")
        or candidate.get("label")
        or candidate.get("title")
        or (term.display_name if term else None)
        or name
    )
    return {
        **candidate,
        "name": name,
        "display_name": display_name,
        "definition": candidate.get("definition") or (term.definition if term else None),
        "term_type": candidate.get("term_type") or candidate.get("termType") or (term.term_type if term else None),
        "aliases": candidate.get("aliases") or (term.aliases if term else []),
    }


def _business_term_by_id(db: Session | None, term_id: object) -> models.BusinessTerm | None:
    """按候选 term_id 回查业务术语，历史 payload 不合法时静默降级。"""

    if not db or term_id is None:
        return None
    try:
        return db.get(models.BusinessTerm, int(term_id))
    except (TypeError, ValueError):
        return None


def _term_conflict_candidates(route_payload: dict, db: Session | None = None) -> list[dict]:
    """从术语冲突 payload 里整理可展示候选。"""
    existing = route_payload.get("candidates")
    if existing:
        candidates: list[dict] = []
        for index, candidate in enumerate(existing, start=1):
            if not isinstance(candidate, dict):
                continue
            term_id = candidate.get("term_id") or candidate.get("id")
            term = _business_term_by_id(db, term_id)
            normalized = _term_candidate_display(candidate, term)
            normalized["index"] = normalized.get("index") or index
            candidates.append(normalized)
        return candidates
    candidates: list[dict] = []
    seen: set[int] = set()
    for conflict in route_payload.get("conflicts") or []:
        token = conflict.get("token")
        for term in conflict.get("terms") or []:
            term_id = term.get("id") or term.get("term_id")
            if term_id is None or term_id in seen:
                continue
            seen.add(term_id)
            db_term = _business_term_by_id(db, term_id)
            candidates.append(
                _term_candidate_display(
                    {
                        "index": len(candidates) + 1,
                        "term_id": term_id,
                        "name": term.get("name"),
                        "display_name": term.get("display_name") or term.get("name"),
                        "definition": term.get("definition"),
                        "term_type": term.get("term_type"),
                        "aliases": term.get("aliases") or [],
                        "matched_text": token,
                    },
                    db_term,
                )
            )
    return candidates


def _ensure_pending_term_clarification(
    db: Session,
    *,
    conversation_id: int,
    dataset_id: int | None,
    question: str,
    route_payload: dict,
) -> dict:
    """为术语冲突创建 pending clarification，并回填前端需要的字段。"""
    if route_payload.get("clarification_id"):
        return route_payload
    candidates = _term_conflict_candidates(route_payload, db)
    expires_at = datetime.utcnow() + timedelta(minutes=TERM_CLARIFICATION_TTL_MINUTES)
    pending = models.PendingClarification(
        conversation_id=conversation_id,
        dataset_id=dataset_id,
        clarification_type="term_conflict",
        status="pending",
        original_question=question,
        conflict_payload=jsonable_encoder(route_payload),
        candidates=jsonable_encoder(candidates),
        expires_at=expires_at,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    enriched = dict(route_payload)
    enriched.update(
        {
            "clarification_id": pending.id,
            "candidates": candidates,
            "expires_at": expires_at.isoformat(),
        }
    )
    return enriched


def _route_decision_event(route_decision: dict) -> dict:
    """整理路由决策 SSE 事件，供前端和审计复用。"""

    return {
        "type": "route_decision",
        "decision": route_decision.get("decision"),
        "dataset_id": route_decision.get("dataset_id"),
        "dataset_name": route_decision.get("dataset_name"),
        "manifest_version": route_decision.get("manifest_version"),
        "bound_schema_version": route_decision.get("bound_schema_version"),
        "score": route_decision.get("score"),
        "candidates": route_decision.get("candidates") or [],
        "reason": route_decision.get("reason"),
    }


def _report_control_for_route(route_decision: dict, payload_dataset_id: int | None) -> dict:
    """根据路由来源决定报告生成归属。"""

    auto_routed = route_decision.get("decision") == "selected" and payload_dataset_id is None
    return {
        "skip_subagent_report": auto_routed,
        "report_owner": "lead_agent" if auto_routed else "subagent",
        "subagent_report_skipped": False,
        "lead_agent_report": {"generated": False},
    }


def _should_generate_lead_agent_report(final_state: dict) -> bool:
    """工作流结束后判断是否由 LeadAgent 接管报告生成。"""

    if final_state.get("report_owner") != "lead_agent":
        return False
    if not final_state.get("skip_subagent_report"):
        return False
    if final_state.get("answer"):
        return False
    if final_state.get("error"):
        return False
    return final_state.get("sql_result") is not None


def _multiturn_observability_metrics(
    *,
    lead_agent_context: dict,
    final_state: dict,
) -> dict:
    """整理多轮链路轻量指标，供 trace metadata 后续聚合。"""

    classification = lead_agent_context.get("multiturn_classification") or {}
    prior_capsule_status = final_state.get("prior_capsule_status") or {}
    multiturn_context = final_state.get("multiturn_context") or {}
    merge_debug = final_state.get("merge_debug") or {}
    blueprint_shortcut = multiturn_context.get("blueprint_shortcut") or {}
    capsule_status = prior_capsule_status.get("status")
    return {
        "turn_intent": classification.get("intent"),
        "turn_confidence": classification.get("confidence"),
        "turn_classifier_source": classification.get("source"),
        "continued_with_active_dataset": bool(classification.get("should_inherit_dataset")),
        "delta_type": multiturn_context.get("delta_type")
        or (multiturn_context.get("delta") or {}).get("delta_type"),
        "delta_operations": (multiturn_context.get("delta") or {}).get("operations") or [],
        "delta_merge_used_prior": bool(merge_debug.get("used_prior")),
        "delta_merge_conflict": merge_debug.get("reason") == "merged_metrics_empty_downgraded_to_new_query",
        "blueprint_shortcut_candidate": bool(blueprint_shortcut),
        "blueprint_shortcut_hit": final_state.get("entry_route") == "analysis_blueprint"
        and bool(blueprint_shortcut),
        "capsule_status": capsule_status,
        "capsule_invalidated": capsule_status in {"invalid", "stale"},
    }


_BUSINESS_STAGE_META = {
    "understand": {
        "name": "理解问题与上下文",
        "nodes": {
            "merge_prior_context",
            "clarification_resolution",
            "intent_recognition",
            "entry_intent_classification",
        },
    },
    "route": {
        "name": "选择数据集与分析路径",
        "nodes": {"analysis_blueprint_execute"},
    },
    "semantic": {
        "name": "确认业务口径",
        "nodes": {
            "schema_recall",
            "term_conflict_resolve",
            "metric_resolve",
        },
    },
    "plan_query": {
        "name": "生成查询计划",
        "nodes": {"dsl_generate", "dsl_validate", "dsl_compiler"},
    },
    "execute_query": {
        "name": "执行查询与诊断",
        "nodes": {"sql_execute", "sql_audit"},
    },
    "narrate": {
        "name": "生成业务回答",
        "nodes": {"report_generator", "lead_agent_report_generator"},
    },
}


def _business_stage_for_node(node: str | None) -> str:
    """将技术节点归并为前端右侧展示用的业务阶段。"""

    if not node:
        return "other"
    for stage_key, stage_meta in _BUSINESS_STAGE_META.items():
        if node in stage_meta["nodes"]:
            return stage_key
    return "other"


def _row_count(sql_result: dict | None) -> int | None:
    """从 SQL 执行结果中稳定提取行数。"""

    if not isinstance(sql_result, dict):
        return None
    if sql_result.get("row_count") is not None:
        return sql_result.get("row_count")
    rows = sql_result.get("rows")
    if isinstance(rows, list):
        return len(rows)
    return None


def _last_step_elapsed_ms(step_traces: list[dict], *nodes: str) -> int | None:
    """读取最后一个指定节点的耗时，避免前端从 step_trace 自行推断。"""

    node_set = set(nodes)
    for step in reversed(step_traces or []):
        if step.get("node") in node_set and step.get("elapsed_ms") is not None:
            return step.get("elapsed_ms")
    return None


def _business_execution_stages(step_traces: list[dict]) -> list[dict]:
    """把 step_trace 压缩成业务化执行阶段，完整 trace 仍保留在 step_trace。"""

    stages: dict[str, dict] = {}
    for step in step_traces or []:
        node = step.get("node")
        stage_key = _business_stage_for_node(node)
        stage_meta = _BUSINESS_STAGE_META.get(stage_key, {"name": "其他处理", "nodes": set()})
        stage = stages.setdefault(
            stage_key,
            {
                "key": stage_key,
                "name": stage_meta["name"],
                "status": "pending",
                "elapsed_ms": 0,
                "nodes": [],
            },
        )
        if node and node not in stage["nodes"]:
            stage["nodes"].append(node)
        status = step.get("status")
        if status:
            stage["status"] = status
        if step.get("elapsed_ms") is not None:
            stage["elapsed_ms"] += int(step.get("elapsed_ms") or 0)

    ordered_keys = [*list(_BUSINESS_STAGE_META.keys()), "other"]
    return [stages[key] for key in ordered_keys if key in stages]


def _build_query_profile(
    *,
    final_state: dict,
    lead_agent_context: dict,
    route_decision: dict,
    step_traces: list[dict],
    sql: str | None,
    sql_list: list,
    execution_path: str,
    effective_dataset_id: int | None,
) -> dict:
    """构建前端口径卡片和执行摘要的稳定结构。"""

    sql_result = final_state.get("sql_result") if isinstance(final_state, dict) else None
    if not isinstance(sql_result, dict):
        sql_result = {}
    multiturn_context = final_state.get("multiturn_context") or {}
    delta = multiturn_context.get("delta") or {}
    merge_debug = final_state.get("merge_debug") or {}
    prior_capsule_status = final_state.get("prior_capsule_status") or {}
    row_count = _row_count(sql_result)
    columns = sql_result.get("columns") or []
    sql_elapsed_ms = _last_step_elapsed_ms(
        step_traces,
        "sql_execute",
        "analysis_blueprint_execute",
    )
    stages = _business_execution_stages(step_traces)
    total_elapsed_ms = sum(int(stage.get("elapsed_ms") or 0) for stage in stages)
    inherited = bool(
        merge_debug.get("used_prior")
        or final_state.get("turn_type") in {"continue", "follow_up"}
        or prior_capsule_status.get("status") == "loaded"
    )

    return {
        "version": "v1",
        "question": {
            "original": final_state.get("original_question")
            or lead_agent_context.get("original_question"),
            "resolved": final_state.get("resolved_question")
            or lead_agent_context.get("resolved_question"),
        },
        "route": {
            "execution_path": execution_path,
            "entry_intent": final_state.get("entry_intent"),
            "entry_route": final_state.get("entry_route"),
            "entry_reason": final_state.get("entry_reason"),
            "decision": route_decision.get("decision"),
            "dataset_id": route_decision.get("dataset_id") or effective_dataset_id,
            "dataset_name": route_decision.get("dataset_name"),
            "manifest_version": route_decision.get("manifest_version"),
            "bound_schema_version": route_decision.get("bound_schema_version"),
            "blueprint_id": final_state.get("blueprint_id"),
            "blueprint_match": final_state.get("blueprint_match"),
            "route_payload_kind": (final_state.get("route_payload") or {}).get("kind"),
        },
        "query_context": {
            "time_context": final_state.get("time_context")
            or lead_agent_context.get("time_context"),
            "query_constraints": final_state.get("query_constraints"),
            "merged_query_context": multiturn_context.get("merged_query_context"),
            "prior_query_context": multiturn_context.get("prior_query_context"),
            "delta": delta or None,
            "delta_type": multiturn_context.get("delta_type") or delta.get("delta_type"),
            "inheritance": {
                "inherited": inherited,
                "turn_type": final_state.get("turn_type") or multiturn_context.get("turn_type"),
                "prior_capsule_status": prior_capsule_status,
                "merge_debug": merge_debug,
                "operations": delta.get("operations") or [],
            },
        },
        "semantic": {
            "term_normalization": final_state.get("term_normalization"),
            "semantic_asset_resolution": final_state.get("semantic_asset_resolution"),
            "metric_resolution": final_state.get("metric_resolution"),
            "dataset_context_debug": final_state.get("dataset_context_debug"),
            "schema_status": lead_agent_context.get("schema_status"),
        },
        "sql": {
            "text": sql,
            "statements": sql_list,
            "row_count": row_count,
            "columns": columns,
            "elapsed_ms": sql_elapsed_ms,
            "generation_mode": final_state.get("generation_mode"),
            "diagnosis": final_state.get("sql_diagnosis")
            or final_state.get("sql_audit_result"),
            "retry_trace": final_state.get("sql_retry_trace") or [],
        },
        "execution_summary": {
            "elapsed_ms": total_elapsed_ms,
            "stages": stages,
            "report_owner": final_state.get("report_owner"),
            "subagent_report_skipped": final_state.get("subagent_report_skipped"),
            "lead_agent_report": final_state.get("lead_agent_report"),
        },
    }


def _build_explainability(
    *,
    query_profile: dict,
    answer_explanation: dict | None = None,
) -> dict:
    """统一对外可解释性结构，避免前端依赖分散字段。"""

    return {
        "version": "v1",
        "query_profile": query_profile,
        "answer_explanation": answer_explanation or {},
    }


def _lead_agent_event(lead_agent_context: dict) -> dict:
    """整理 LeadAgent 控制面工具执行摘要，供前端调试和审计使用。"""

    return {
        "type": "lead_agent_tools",
        "time_context": lead_agent_context.get("time_context"),
        "thread_context": lead_agent_context.get("thread_context"),
        "route_decision": lead_agent_context.get("route_decision"),
        "schema_status": lead_agent_context.get("schema_status"),
        "clarification": lead_agent_context.get("clarification"),
        "audit_trace": lead_agent_context.get("audit_trace"),
        "tool_policy": lead_agent_context.get("tool_policy"),
        "original_question": lead_agent_context.get("original_question"),
        "resolved_question": lead_agent_context.get("resolved_question"),
        "selected_skills": lead_agent_context.get("selected_skills") or [],
        "planned_tool_calls": lead_agent_context.get("planned_tool_calls") or [],
        "executed_tool_calls": lead_agent_context.get("executed_tool_calls") or [],
        "system_inferred_tool_calls": lead_agent_context.get("system_inferred_tool_calls") or [],
        "progressive_disclosure": lead_agent_context.get("progressive_disclosure"),
        "disclosed_tools": lead_agent_context.get("disclosed_tools") or [],
        "skill_selection_reasoning_summary": lead_agent_context.get("skill_selection_reasoning_summary"),
        "tool_planning_reasoning_summary": lead_agent_context.get("tool_planning_reasoning_summary"),
        "policy_violations": lead_agent_context.get("policy_violations") or [],
        "planner_fallback": lead_agent_context.get("planner_fallback"),
        "fallback_reason": lead_agent_context.get("fallback_reason"),
        "planner_reasoning_summary": lead_agent_context.get("planner_reasoning_summary"),
        "should_continue": lead_agent_context.get("should_continue"),
    }


def _route_block_answer(route_decision: dict) -> str:
    """路由不明确时生成可直接展示给用户的解释。"""

    candidates = route_decision.get("candidates") or []
    if route_decision.get("decision") == "ambiguous":
        lines = ["我找到了多个可能的数据集，需要你先确认使用哪一个："]
        for index, item in enumerate(candidates[:3], start=1):
            name = item.get("dataset_name") or f"数据集 {item.get('dataset_id')}"
            score = item.get("score", 0)
            reason = "；".join((item.get("reasons") or [])[:2])
            lines.append(f"{index}. {name}（得分 {score}）{('：' + reason) if reason else ''}")
        lines.append("请选择数据集后再继续提问。")
        return "\n".join(lines)

    if candidates:
        top = candidates[0]
        name = top.get("dataset_name") or f"数据集 {top.get('dataset_id')}"
        return (
            "当前问题没有命中足够明确的 SubAgent Manifest，暂时不自动选择数据集。"
            f"最接近的是 {name}（得分 {top.get('score', 0)}），但未达到自动路由阈值。"
            "你可以手动选择数据集，或补充更具体的指标、维度、时间范围。"
        )
    return "当前没有可用于自动路由的 current SubAgent Manifest，请先选择数据集或发布 Manifest 后再提问。"


def _save_route_block_message(
    db: Session,
    *,
    conv: models.Conversation,
    route_decision: dict,
    lead_agent_context: dict,
    answer: str,
) -> models.Message:
    """保存路由阻断场景的助手消息，保持会话历史完整。"""

    route_payload = {
        "kind": "manifest_route",
        "decision": route_decision.get("decision"),
        "candidates": route_decision.get("candidates") or [],
        "reason": route_decision.get("reason"),
    }
    final_state = {
        "original_question": lead_agent_context.get("original_question"),
        "resolved_question": lead_agent_context.get("resolved_question"),
        "entry_intent": "manifest_route",
        "entry_route": route_decision.get("decision"),
        "entry_reason": route_decision.get("reason"),
        "route_payload": route_payload,
        "time_context": lead_agent_context.get("time_context"),
        "sql_result": None,
    }
    query_profile = _build_query_profile(
        final_state=final_state,
        lead_agent_context=lead_agent_context,
        route_decision=route_decision,
        step_traces=[_lead_agent_event(lead_agent_context), _route_decision_event(route_decision)],
        sql=None,
        sql_list=[],
        execution_path="manifest_route",
        effective_dataset_id=route_decision.get("dataset_id"),
    )
    explainability = _build_explainability(query_profile=query_profile)
    response_metadata = jsonable_encoder({
        "lead_agent_context": lead_agent_context,
        "original_question": lead_agent_context.get("original_question"),
        "resolved_question": lead_agent_context.get("resolved_question"),
        "route_decision": route_decision,
        "time_context": lead_agent_context.get("time_context"),
        "schema_status": lead_agent_context.get("schema_status"),
        "route_payload": route_payload,
        "query_profile": query_profile,
        "explainability": explainability,
    })
    assistant_message = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        sql_list=[],
        step_trace=[_lead_agent_event(lead_agent_context), _route_decision_event(route_decision)],
        response_metadata=response_metadata,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return assistant_message


async def _stream_chat_singleturn(
    payload: schemas.ChatRequest,
    db: Session,
    *,
    multiturn_context: dict | None = None,
    conversation_state: models.ConversationState | None = None,
    conversation_store: ConversationStore | None = None,
    observability_session_id: str | None = None,
    trace_context_sink: list | None = None,
    defer_trace_close: bool = False,
):
    """SSE 流式问数：驱动 LangGraph 工作流，逐步发送节点进度事件。"""
    logger.info(f"[_stream_chat] 开始处理问题: {payload.question[:50]}")
    conv_id: int | None = payload.conversation_id
    effective_dataset_id: int | None = payload.dataset_id

    # 查找或创建对话
    if conv_id:
        conv = db.get(models.Conversation, conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        if effective_dataset_id is None:
            effective_dataset_id = conv.dataset_id
        elif conv.dataset_id != effective_dataset_id:
            conv.dataset_id = effective_dataset_id
            db.commit()
            db.refresh(conv)
        # 已存在对话的首条消息：自动用首句作为标题（避免「新对话」/空标题占位）
        existing_msg_count = (
            db.query(models.Message).filter(models.Message.conversation_id == conv_id).count()
        )
        if existing_msg_count == 0 and (not conv.title or conv.title in ("新对话", "")):
            conv.title = payload.question[:40]
            if not conv.thread_id:
                conv.thread_id = f"thread-{payload.question[:20]}"
            db.commit()
            db.refresh(conv)
    else:
        conv = models.Conversation(
            title=payload.question[:40],
            thread_id=f"thread-{payload.question[:20]}",
            user_id=1,
            dataset_id=effective_dataset_id,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conv_id = int(conv.id)

    # 保存用户消息
    db.add(
        models.Message(
            conversation_id=conv_id,
            role="user",
            content=payload.question,
        )
    )
    db.commit()

    tracer = get_observability_tracer()
    trace_context = tracer.create_trace_context(
        conversation_id=conv_id,
        dataset_id=effective_dataset_id,
        user_id=str(conv.user_id or 1),
        tenant_id="default",
        question=payload.question,
        session_id=observability_session_id,
        metadata={
            "thread_id": conv.thread_id,
            "title": conv.title,
            "phase": "lead_agent",
            "business_session_id": observability_session_id,
        },
    )
    if trace_context_sink is not None:
        trace_context_sink.append(trace_context)
    obs_context_manager = set_observability_context(trace_context.request_context())
    obs_context_manager.__enter__()

    tracer.start_span(
        trace_context,
        node="context-assembly",
        display_name="多轮 · 上下文组装",
        input_payload={
            "business_session_id": observability_session_id,
            "conversation_id": conv_id,
            "payload_dataset_id": payload.dataset_id,
            "conversation_dataset_id": conv.dataset_id,
            "has_conversation_state": conversation_state is not None,
        },
    )
    tracer.end_span(
        trace_context,
        node="context-assembly",
        output_payload={
            "active_dataset_id": (multiturn_context or {}).get("active_dataset_id"),
            "turn_index": (multiturn_context or {}).get("turn_index"),
            "pending_clarification_kind": (
                ((multiturn_context or {}).get("pending_clarification") or {}).get("kind")
                if isinstance((multiturn_context or {}).get("pending_clarification"), dict)
                else None
            ),
            "capsule_meta_count": len((multiturn_context or {}).get("capsule_metas") or {}),
            "has_summary": bool((multiturn_context or {}).get("summary")),
        },
    )

    tracer.start_span(
        trace_context,
        node="lead.routing",
        display_name="Lead · 路由决策",
        input_payload={
            "question": payload.question,
            "conversation_id": conv_id,
            "payload_dataset_id": payload.dataset_id,
            "conversation_dataset_id": conv.dataset_id,
        },
        trace_tags=["lead"],
    )
    try:
        lead_agent_context = build_lead_agent_context(
            db,
            question=payload.question,
            conversation=conv,
            payload_dataset_id=payload.dataset_id,
            multiturn_context=multiturn_context,
            tracer=tracer,
            trace_context=trace_context,
        )
    except Exception as exc:
        tracer.end_span(
            trace_context,
            node="lead.routing",
            output_payload={"status": "error", "error": str(exc)},
            error=str(exc),
        )
        raise
    tracer.start_span(
        trace_context,
        node="turn-classification",
        display_name="多轮 · 轮次分类",
        input_payload={
            "question": payload.question,
            "active_dataset_id": (multiturn_context or {}).get("active_dataset_id"),
            "payload_dataset_id": payload.dataset_id,
        },
    )
    tracer.end_span(
        trace_context,
        node="turn-classification",
        output_payload=lead_agent_context.get("multiturn_classification") or {},
    )
    tracer.end_span(
        trace_context,
        node="lead.routing",
        output_payload={
            "route_decision": lead_agent_context.get("route_decision"),
            "schema_status": lead_agent_context.get("schema_status"),
            "selected_skills": lead_agent_context.get("selected_skills") or [],
            "planned_tool_calls": lead_agent_context.get("planned_tool_calls") or [],
            "executed_tool_calls": lead_agent_context.get("executed_tool_calls") or [],
            "policy_violations": lead_agent_context.get("policy_violations") or [],
            "should_continue": lead_agent_context.get("should_continue"),
        },
    )
    route_decision = lead_agent_context["route_decision"]
    lead_event = _lead_agent_event(lead_agent_context)
    route_event = _route_decision_event(route_decision)
    yield _sse_data(lead_event)
    yield _sse_data(route_event)

    if lead_agent_context.get("should_continue"):
        selected_dataset_id = lead_agent_context.get("effective_dataset_id")
        if selected_dataset_id is not None:
            effective_dataset_id = int(selected_dataset_id)
            if conv.dataset_id != effective_dataset_id:
                conv.dataset_id = effective_dataset_id
                db.commit()
                db.refresh(conv)
    else:
        answer = _route_block_answer(route_decision)
        assistant_message = _save_route_block_message(
            db,
            conv=conv,
            route_decision=route_decision,
            lead_agent_context=lead_agent_context,
            answer=answer,
        )
        trace_metadata = {
            "status": "blocked",
            "execution_path": "manifest_route",
            "original_question": payload.question,
            "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
            "entry_route": route_decision.get("decision"),
            "lead_agent_context": lead_agent_context,
            "route_decision": route_decision,
            "schema_status": lead_agent_context.get("schema_status"),
            "manifest_version": route_decision.get("manifest_version"),
            "bound_schema_version": route_decision.get("bound_schema_version"),
            "query_profile": (assistant_message.response_metadata or {}).get("query_profile"),
            "explainability": (assistant_message.response_metadata or {}).get("explainability"),
            "prompt_versions": trace_context.prompt_versions,
        }
        tracer.update_trace_output(trace_context, output=answer, metadata=trace_metadata)
        if trace_context.trace_id:
            db.add(
                models.ObservabilityTraceIndex(
                    langfuse_trace_id=trace_context.trace_id,
                    langfuse_session_id=trace_context.session_id,
                    conversation_id=conv_id,
                    message_id=assistant_message.id,
                    dataset_id=effective_dataset_id,
                    entry_route=route_decision.get("decision") or "manifest_route",
                    status="blocked",
                    total_tokens=0,
                    total_cost=0,
                    metadata_json=jsonable_encoder(trace_metadata),
                )
            )
            db.commit()
        if not defer_trace_close:
            tracer.close_trace(trace_context)
        obs_context_manager.__exit__(None, None, None)
        response_metadata = assistant_message.response_metadata or {}
        yield _sse_data(
            {
                "type": "final",
                "sql": None,
                "sql_list": [],
                "answer": answer,
                "entry_intent": "manifest_route",
                "entry_route": route_decision.get("decision"),
                "entry_reason": route_decision.get("reason"),
                "lead_agent_context": lead_agent_context,
                "original_question": payload.question,
                "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
                "time_context": lead_agent_context.get("time_context"),
                "route_decision": route_decision,
                "schema_status": lead_agent_context.get("schema_status"),
                "clarification": lead_agent_context.get("clarification"),
                "route_payload": response_metadata.get("route_payload"),
                "sql_result": None,
                "query_profile": response_metadata.get("query_profile"),
                "explainability": response_metadata.get("explainability"),
                "response_metadata": response_metadata,
                "conversation_id": conv.id,
                "message_id": assistant_message.id,
                "title": conv.title,
            }
        )
        return

    # 查询历史消息（最近 6 轮，用于意图识别上下文）
    history_msgs = (
        db.query(models.Message)
        .filter(models.Message.conversation_id == conv_id)
        .order_by(models.Message.created_at.desc())
        .limit(12)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in reversed(history_msgs)]

    # 构建初始状态
    resolved_question = lead_agent_context.get("resolved_question") or payload.question
    report_control = _report_control_for_route(route_decision, payload.dataset_id)
    prior_capsule = None
    prior_capsule_status = {"status": "disabled", "reason": "multiturn_store_not_enabled"}
    if conversation_store is not None and conversation_state is not None and effective_dataset_id is not None:
        prior_capsule, prior_capsule_status = conversation_store.valid_prior_capsule(
            conversation_state,
            dataset_id=effective_dataset_id,
            expected_schema_version=route_decision.get("bound_schema_version"),
        )

    # Phase 2: 在 LangGraph 之外完成多轮合并决策
    # - interpret 路径早退，不进 LangGraph
    # - 其他路径把决策字段塞进 initial_state
    merge_state = {
        "question": resolved_question,
        "turn_type": None,
        "turn_index": (multiturn_context or {}).get("turn_index"),
        "dataset_id": effective_dataset_id,
        "prior_capsule": prior_capsule,
        "history": history,
        "lead_agent_context": lead_agent_context,
        "manifest_version": route_decision.get("manifest_version"),
        "bound_schema_version": route_decision.get("bound_schema_version"),
    }
    merge_decision: MergeDecision = merge_multiturn_decision_for_chat(
        state=merge_state,
        out_capsule_factory=_build_out_capsule_for_chat,
        tracer=tracer,
        trace_context=trace_context,
    )
    if merge_decision.interpret_payload is not None:
        async for sse_event in _interpret_early_return(
            db=db,
            conv=conv,
            payload=payload,
            effective_dataset_id=effective_dataset_id,
            lead_agent_context=lead_agent_context,
            route_decision=route_decision,
            trace_context=trace_context,
            defer_trace_close=defer_trace_close,
            obs_context_manager=obs_context_manager,
            interpret_payload=merge_decision.interpret_payload,
            turn_type=merge_decision.turn_type,
            multiturn_context=merge_decision.multiturn_context,
            merge_debug=merge_decision.merge_debug,
        ):
            yield sse_event
        return

    # Phase 4: 先解析挂起 term 澄清，再做入口路由。
    # 用户对 pending 术语澄清通常只回复“第一个”或术语名；若先走入口路由，
    # 这类短句会被普通 clarify 早退截断，导致 pending 永远不能 resolved。
    term_resolution = resolve_term_clarification(
        db,
        question=merge_decision.synthesized_question or resolved_question,
        conversation_id=conv_id,
        dataset_id=effective_dataset_id,
        clarification_response=jsonable_encoder(payload.clarification_response),
        tracer=tracer,
        trace_context=trace_context,
    )
    _resolved_question = term_resolution.get("resolved_question")
    routing_question = (
        _resolved_question
        if (_resolved_question and term_resolution["status"] == "resolved")
        else (merge_decision.synthesized_question or resolved_question)
    )

    # Phase 3: LeadAgent 总入口路由（替代 intent + entry 两个图节点）
    routing = route_query_intent(
        db,
        question=routing_question,
        dataset_id=effective_dataset_id,
        lead_agent_context=lead_agent_context,
        history=history,
        multiturn_context=merge_decision.multiturn_context,
        clarification_response=jsonable_encoder(payload.clarification_response),
        tracer=tracer,
        trace_context=trace_context,
    )
    yield _sse_data(
        {
            "type": "step",
            "node": "lead_agent",
            "display_name": "LeadAgent · 入口路由",
            "status": "done",
            "intent": routing.get("intent"),
            "entities": routing.get("entities") or {},
            "entry_intent": routing.get("entry_intent"),
            "entry_route": routing.get("entry_route"),
            "entry_reason": routing.get("entry_reason"),
            "blueprint_id": routing.get("blueprint_id"),
            "route_payload": routing.get("route_payload") or {},
        }
    )
    if term_resolution["status"] != "none":
        yield _sse_data(
            {
                "type": "step",
                "node": "clarification_resolution",
                "display_name": _NODE_DISPLAY_NAMES.get("clarification_resolution", "澄清解析"),
                "status": "done",
                "elapsed_ms": 0,
                "clarification_resolution": term_resolution.get("clarification_resolution_result") or {},
                "route_payload": term_resolution.get("route_payload") or {},
            }
        )
    term_should_early = term_resolution["status"] in {"missing", "expired", "unresolved"}
    if term_should_early:
        # 合并 term 解析字段到 routing，复用 _early_route_return 早退
        routing = dict(routing)
        routing["entry_intent"] = term_resolution.get("entry_intent") or routing.get("entry_intent")
        routing["entry_route"] = term_resolution.get("entry_route") or routing.get("entry_route")
        routing["entry_reason"] = term_resolution.get("entry_reason") or routing.get("entry_reason")
        routing["answer"] = term_resolution.get("answer") or routing.get("answer")
        routing["route_payload"] = term_resolution.get("route_payload") or routing.get("route_payload")
        async for sse_event in _early_route_return(
            db=db,
            conv=conv,
            payload=payload,
            effective_dataset_id=effective_dataset_id,
            lead_agent_context=lead_agent_context,
            route_decision=route_decision,
            trace_context=trace_context,
            defer_trace_close=defer_trace_close,
            obs_context_manager=obs_context_manager,
            routing=routing,
        ):
            yield sse_event
        return

    if routing.get("entry_route") in {"direct_answer", "reject", "knowledge_qa", "clarify"}:
        async for sse_event in _early_route_return(
            db=db,
            conv=conv,
            payload=payload,
            effective_dataset_id=effective_dataset_id,
            lead_agent_context=lead_agent_context,
            route_decision=route_decision,
            trace_context=trace_context,
            defer_trace_close=defer_trace_close,
            obs_context_manager=obs_context_manager,
            routing=routing,
        ):
            yield sse_event
        return

    # Phase 6: 业务术语归一化（DatasetSubAgent 接管 term_normalize_node）
    # 不依赖 schema_structured，可在 LeadAgent 路由后立即调用；冲突术语走澄清早退。
    sub_agent = DatasetSubAgent(db=db, dataset_id=int(effective_dataset_id) if effective_dataset_id else 0)
    schema_structured_seed = (
        (lead_agent_context.get("schema_status") or {}).get("structured")
        or {}
    )
    seed_terms = (
        schema_structured_seed.get("terms")
        if isinstance(schema_structured_seed, dict)
        else None
    ) or []
    _tc_question = (
        _resolved_question
        if (_resolved_question and term_resolution["status"] == "resolved")
        else (merge_decision.synthesized_question or resolved_question)
    )
    term_conflict_outcome = sub_agent.resolve_term_conflict(
        question=_tc_question,
        terms=seed_terms,
        entities=routing.get("entities") or {},
        selected_term_id=term_resolution.get("selected_term_id"),
        tracer=tracer,
        trace_context=trace_context,
    )
    if term_conflict_outcome.get("status") != "not_applicable":
        yield _sse_data(
            {
                "type": "step",
                "node": "term_conflict_resolve",
                "display_name": _NODE_DISPLAY_NAMES.get("term_conflict_resolve", "术语冲突解析"),
                "status": "done",
                "elapsed_ms": 0,
                "term_conflict_status": term_conflict_outcome["status"],
                "term_normalization": term_conflict_outcome.get("term_normalization") or {},
                "route_payload": term_conflict_outcome.get("route_payload") or {},
            }
        )
    if term_conflict_outcome.get("status") in {"needs_clarification", "missing_term"}:
        # 冲突术语 / 缺配置 → 早退（与 term_clarification 早退风格一致）
        tc_routing = dict(routing)
        tc_routing["entry_intent"] = "clarification"
        tc_routing["entry_route"] = "clarify"
        tc_routing["entry_reason"] = (
            "业务术语同义词命中多个定义或缺配置，需要用户澄清。"
        )
        tc_routing["answer"] = term_conflict_outcome.get("answer")
        tc_routing["route_payload"] = term_conflict_outcome.get("route_payload") or {}
        async for sse_event in _early_route_return(
            db=db,
            conv=conv,
            payload=payload,
            effective_dataset_id=effective_dataset_id,
            lead_agent_context=lead_agent_context,
            route_decision=route_decision,
            trace_context=trace_context,
            defer_trace_close=defer_trace_close,
            obs_context_manager=obs_context_manager,
            routing=tc_routing,
        ):
            yield sse_event
        return

    # Phase 7: 统一语义资产解析（DatasetSubAgent 接管 semantic_asset_resolution_node）
    # 此时 schema_structured 还没完全准备好（schema_recall 节点未跑），传 None 让 metric 走
    # not_applicable 分支；实际 metric 在 schema_recall 后由独立节点驱动（或后续 Phase 上提）。
    metric_outcome = sub_agent.resolve_metric(
        question=_tc_question,
        entities=routing.get("entities") or {},
        schema_structured=None,
        tracer=tracer,
        trace_context=trace_context,
    )
    if metric_outcome.get("status") not in ("not_applicable", "resolved"):
        yield _sse_data(
            {
                "type": "step",
                "node": "metric_resolve",
                "display_name": _NODE_DISPLAY_NAMES.get("metric_resolve", "指标解析"),
                "status": "done",
                "elapsed_ms": 0,
                "metric_resolve_status": metric_outcome["status"],
                "semantic_asset_resolution": metric_outcome.get("semantic_asset_resolution") or {},
                "metric_resolution": metric_outcome.get("metric_resolution") or {},
                "route_payload": metric_outcome.get("route_payload") or {},
            }
        )
    if metric_outcome.get("status") == "needs_clarification":
        m_routing = dict(routing)
        m_routing["entry_intent"] = "clarification"
        m_routing["entry_route"] = "clarify"
        m_routing["entry_reason"] = (
            "多个语义资产置信度接近，需要用户澄清。"
        )
        m_routing["answer"] = metric_outcome.get("answer")
        m_routing["route_payload"] = metric_outcome.get("route_payload") or {}
        async for sse_event in _early_route_return(
            db=db,
            conv=conv,
            payload=payload,
            effective_dataset_id=effective_dataset_id,
            lead_agent_context=lead_agent_context,
            route_decision=route_decision,
            trace_context=trace_context,
            defer_trace_close=defer_trace_close,
            obs_context_manager=obs_context_manager,
            routing=m_routing,
        ):
            yield sse_event
        return

    # Phase 5: 蓝图入口路径决策（LeadAgent 编排 selected subAgent）
    # analysis_blueprint 路径在 chat 层直接执行，避免进入 LangGraph 节点。
    # 注：sub_agent 已在 Phase 6 块上提定义，此处复用。
    entry_route = routing.get("entry_route")
    _bp_original_question = payload.question
    _bp_resolved_question = (
        _resolved_question
        if (_resolved_question and term_resolution["status"] == "resolved")
        else (merge_decision.synthesized_question or resolved_question)
    )
    blueprint_outcome = sub_agent.resolve_analysis_blueprint(
        blueprint_id=routing.get("blueprint_id"),
        question=_bp_resolved_question or _bp_original_question,
        entry_route=entry_route,
        original_question=_bp_original_question,
        resolved_question=_bp_resolved_question,
        time_context=lead_agent_context.get("time_context"),
        tracer=tracer,
        trace_context=trace_context,
    )
    # 仅当 blueprint 被实际处理（status != not_applicable）时，先 emit SSE 步骤事件。
    if blueprint_outcome.get("status") and blueprint_outcome["status"] != "not_applicable":
        bp_result = blueprint_outcome.get("sql_result") or {}
        yield _sse_data(
            {
                "type": "step",
                "node": "analysis_blueprint_execute",
                "display_name": _NODE_DISPLAY_NAMES["analysis_blueprint_execute"],
                "status": "done",
                "elapsed_ms": 0,
                "blueprint_id": blueprint_outcome.get("blueprint_id"),
                "blueprint_outcome_status": blueprint_outcome["status"],
                "sql": blueprint_outcome.get("sql") or "",
                "rows": bp_result.get("row_count", 0) if bp_result else 0,
                "columns": bp_result.get("columns", []) if bp_result else [],
                "route_payload": blueprint_outcome.get("route_payload") or {},
            }
        )
    # 早退判定：executed / clarification / error / not_found 走 _early_route_return
    if blueprint_outcome.get("status") in ("executed", "clarification", "error", "not_found"):
        # 合并蓝图 outcome 字段到 routing（与 term 早退风格一致）
        blueprint_route = dict(routing)
        blueprint_route["route_payload"] = blueprint_outcome.get("route_payload") or {}
        blueprint_route["answer"] = blueprint_outcome.get("answer")
        blueprint_route["blueprint_id"] = blueprint_outcome.get("blueprint_id")
        blueprint_route["blueprint_outcome_status"] = blueprint_outcome["status"]
        async for sse_event in _early_route_return(
            db=db,
            conv=conv,
            payload=payload,
            effective_dataset_id=effective_dataset_id,
            lead_agent_context=lead_agent_context,
            route_decision=route_decision,
            trace_context=trace_context,
            defer_trace_close=defer_trace_close,
            obs_context_manager=obs_context_manager,
            routing=blueprint_route,
        ):
            yield sse_event
        return

    # Phase 4: 注入 term 解析结果（resolved 时把 question 恢复到原问题 + selected_term_id）
    _initial_question = (
        _resolved_question
        if (_resolved_question and term_resolution["status"] == "resolved")
        else (merge_decision.synthesized_question or resolved_question)
    )
    _initial_route_payload = (
        term_resolution.get("route_payload")
        if term_resolution["status"] != "none"
        else routing.get("route_payload")
    )
    initial_state = {
        "question": _initial_question,
        "original_question": payload.question,
        "resolved_question": resolved_question,
        "dataset_id": effective_dataset_id,
        "manifest_version": route_decision.get("manifest_version"),
        "bound_schema_version": route_decision.get("bound_schema_version"),
        "time_context": lead_agent_context.get("time_context"),
        "thread_context": lead_agent_context.get("thread_context"),
        "route_decision": route_decision,
        "schema_status": lead_agent_context.get("schema_status"),
        "lead_agent_context": lead_agent_context,
        "skip_subagent_report": report_control["skip_subagent_report"],
        "report_owner": report_control["report_owner"],
        "subagent_report_skipped": report_control["subagent_report_skipped"],
        "lead_agent_report": report_control["lead_agent_report"],
        "conversation_id": conv_id,
        "history": history,
        "clarification_response": jsonable_encoder(payload.clarification_response),
        "clarification_resolution_result": term_resolution.get("clarification_resolution_result"),
        "prior_capsule": prior_capsule,
        "prior_capsule_status": prior_capsule_status,
        "out_capsule": None,
        "multiturn_context": merge_decision.multiturn_context,
        "turn_type": merge_decision.turn_type,
        "merge_debug": merge_decision.merge_debug,
        "intent": routing.get("intent"),
        "entities": routing.get("entities") or {},
        "entry_intent": routing.get("entry_intent"),
        "entry_route": routing.get("entry_route"),
        "entry_reason": routing.get("entry_reason"),
        "blueprint_id": routing.get("blueprint_id"),
        "blueprint_match": routing.get("blueprint_match"),
        "blueprint_context": blueprint_outcome.get("blueprint_context"),
        "knowledge_term_id": routing.get("knowledge_term_id"),
        "selected_term_id": term_resolution.get("selected_term_id"),
        "route_payload": (
            blueprint_outcome.get("route_payload")
            if blueprint_outcome.get("route_payload")
            else _initial_route_payload
        ),
        "generation_mode": blueprint_outcome.get("generation_mode"),
        "schema_context": None,
        "schema_structured": None,
        "ddl_context": None,
        "query_constraints": None,
        "dataset_context_debug": None,
        "datasource_context": None,
        "term_normalization": (
            term_conflict_outcome.get("term_normalization")
            if term_conflict_outcome and term_conflict_outcome.get("status") != "not_applicable"
            else None
        ),
        "semantic_asset_resolution": (
            metric_outcome.get("semantic_asset_resolution")
            if metric_outcome and metric_outcome.get("status") != "not_applicable"
            else None
        ),
        "metric_resolution": (
            metric_outcome.get("metric_resolution")
            if metric_outcome and metric_outcome.get("status") != "not_applicable"
            else None
        ),
        "dsl": None,
        "dsl_valid": False,
        "sql": None,
        "sql_result": None,
        "datasource_dialect": None,
        "sql_audit_result": None,
        "sql_diagnosis": None,
        "answer_explanation": None,
        "answer": None,
        "sql_list": [],
        "error": None,
        "retry_count": 0,
        "max_retry_count": 3,
        "should_retry": False,
        "sql_retry_trace": [],
        "token_usage": None,
    }

    # 构建并运行工作流
    app_graph = build_workflow(db)
    subagent_request = DatasetSubAgentRequest(
        question=resolved_question,
        dataset_id=int(effective_dataset_id),
        manifest_version=route_decision.get("manifest_version"),
        bound_schema_version=route_decision.get("bound_schema_version"),
        thread_id=conv.thread_id or f"conversation-{conv_id}",
        time_context=lead_agent_context.get("time_context") or {},
        thread_context=lead_agent_context.get("thread_context") or {},
        route_decision=route_decision,
        schema_status=lead_agent_context.get("schema_status") or {},
        lead_agent_context=lead_agent_context,
        prior_capsule=prior_capsule,
        prior_capsule_status=prior_capsule_status,
        trace_id=trace_context.trace_id,
        parent_observation_id=None,
    )
    subagent_runner = InProcessDatasetSubAgentRunner(app_graph, db)
    final_state: dict = dict(initial_state)
    node_start_times: dict[str, float] = {}

    try:
        logger.info("[_stream_chat] 开始 astream_events 工作流...")
        # 去重集合：astream_events v2 中子 chain 也会触发 on_chain_start/end，
        # 同一 langgraph_node 名称可能重复出现，只取每个节点的第一次事件
        reported_running: set[str] = set()
        reported_done: set[str] = set()
        step_traces: list[dict] = []  # 收集推理步骤供历史加载时恢复思维链

        async for event in subagent_runner.run(
            subagent_request,
            trace_context,
            initial_state,
            dataset_name=route_decision.get("dataset_name") or "",
            version="v2",
        ):
            kind: str = event["event"]
            meta: dict = event.get("metadata", {})
            # langgraph_node 元数据标识当前所属顶层图节点
            lg_node: str = meta.get("langgraph_node", "")

            # ── 节点开始（每节点只报一次）────────────────────
            if (
                kind == "on_chain_start"
                and lg_node in _NODE_DISPLAY_NAMES
                and lg_node not in reported_running
            ):
                reported_running.add(lg_node)
                node_start_times[lg_node] = time.monotonic()
                sse_payload = {
                    "type": "step",
                    "node": lg_node,
                    "display_name": _NODE_DISPLAY_NAMES[lg_node],
                    "status": "running",
                }
                logger.info(f"[_stream_chat] step running: {lg_node}")
                tracer.start_span(
                    trace_context,
                    node=lg_node,
                    display_name=_NODE_DISPLAY_NAMES[lg_node],
                    input_payload={
                        "question": payload.question,
                        "dataset_id": effective_dataset_id,
                        "conversation_id": conv_id,
                        "time_context": lead_agent_context.get("time_context"),
                        "route_decision": route_decision,
                        "schema_status": lead_agent_context.get("schema_status"),
                        "lead_agent_audit": lead_agent_context.get("audit_trace"),
                        "prior_capsule_status": prior_capsule_status,
                    },
                )
                yield _sse_data(sse_payload)

            # ── 节点完成（每节点只报一次）────────────────────
            elif kind == "on_chain_end" and lg_node in _NODE_DISPLAY_NAMES:
                output = _extract_node_output(event, lg_node)
                if lg_node in reported_done or not output:
                    continue
                reported_done.add(lg_node)
                elapsed_ms = int((time.monotonic() - node_start_times.get(lg_node, 0)) * 1000)
                # 合并节点输出到 final_state（允许 None 值传播）
                final_state.update(output)

                sse_payload = {
                    "type": "step",
                    "node": lg_node,
                    "display_name": _NODE_DISPLAY_NAMES[lg_node],
                    "status": "done",
                    "elapsed_ms": elapsed_ms,
                }
                # 节点特定数据
                # Phase 6/7：term_normalize_node / semantic_asset_resolution_node / metric_resolution_node 已迁移到 chat 层
                # DatasetSubAgent.resolve_term_conflict / resolve_metric，SSE 步骤事件由 chat 层前置 emit，
                # LangGraph 不再产出这些节点事件，因此不再需要 if 分支处理。
                if lg_node == "dsl_generate":
                    sse_payload["dsl"] = final_state.get("dsl") or {}
                    sse_payload["generation_mode"] = final_state.get("generation_mode") or ""
                elif lg_node == "schema_recall":
                    schema = final_state.get("schema_context", "") or ""
                    lines_ = [l for l in schema.split("\n") if l.strip() and not l.startswith("-")]
                    sse_payload["schema_summary"] = lines_[:3]
                elif lg_node == "dsl_compiler":
                    sse_payload["sql"] = final_state.get("sql") or ""
                elif lg_node == "sql_execute":
                    result = final_state.get("sql_result") or {}
                    sse_payload["rows"] = result.get("row_count", 0)
                    sse_payload["columns"] = result.get("columns", [])
                    sse_payload["column_labels"] = result.get("column_labels") or {}
                    sse_payload["elapsed_ms"] = elapsed_ms
                elif lg_node == "sql_audit":
                    diagnosis = (
                        final_state.get("sql_diagnosis")
                        or final_state.get("sql_audit_result")
                        or {}
                    )
                    sse_payload["sql_diagnosis"] = diagnosis
                    sse_payload["sql_audit_result"] = final_state.get("sql_audit_result") or {}
                    sse_payload["code"] = diagnosis.get("code")
                    sse_payload["severity"] = diagnosis.get("severity")
                    sse_payload["retryable"] = diagnosis.get("retryable")
                    sse_payload["sql_retry_trace"] = final_state.get("sql_retry_trace") or []
                step_traces.append(sse_payload)
                logger.info(f"[_stream_chat] step done: {lg_node} ({elapsed_ms}ms)")
                tracer.end_span(
                    trace_context,
                    node=lg_node,
                    output_payload=sse_payload,
                    elapsed_ms=elapsed_ms,
                    error=final_state.get("error") if lg_node == "sql_audit" else None,
                )
                yield _sse_data(sse_payload)

            # ── 图级结束事件：兜底合并完整最终状态 ───────────────
            elif kind == "on_chain_end" and not lg_node:
                output = _extract_node_output(event, "")
                if output:
                    final_state.update(output)

            # ── LLM token ───────────────────────────────────
            elif kind == "on_chat_model_stream":
                # report_generator 节点推送 token（打字效果）
                # 其他节点输出为结构化 JSON，不推送给前端
                # 注：同步节点在线程池中运行，token 可能无法全部回传；
                # 前端 onDone 会用 finalData.answer 作为完整答案兜底
                if lg_node and lg_node != "report_generator":
                    continue
                chunk = event.get("data", {}).get("chunk")
                token: str = getattr(chunk, "content", "") or ""
                if token:
                    yield _sse_data({"type": "token", "content": token})

        logger.info("[_stream_chat] astream_events 完成")

    except Exception as e:
        logger.exception(f"[_stream_chat] 工作流异常: {e}")
        tracer.update_trace_output(trace_context, output=f"处理出错：{e}", metadata={"status": "failed"})
        tracer.close_trace(trace_context)
        obs_context_manager.__exit__(None, None, None)
        yield _sse_data({"type": "step", "node": "error", "display_name": "错误", "status": "done"})
        yield _sse_data({"type": "final", "sql": None, "sql_list": [], "answer": f"处理出错：{e}"})
        return

    # ── 保存助手消息并发送 final 事件 ────────────────
    route_payload = final_state.get("route_payload") or {}
    if route_payload.get("kind") == "term_conflict_clarification" and conv_id:
        route_payload = _ensure_pending_term_clarification(
            db,
            conversation_id=conv_id,
            dataset_id=effective_dataset_id,
            question=final_state.get("original_question") or payload.question,
            route_payload=route_payload,
        )
        final_state["route_payload"] = route_payload

    if _should_generate_lead_agent_report(final_state):
        final_state["subagent_report_skipped"] = True
        final_state["lead_agent_report"] = {
            "generated": False,
            "reason": "auto_routed_manifest",
        }
        report_node = "lead_agent_report_generator"
        report_started_at = time.monotonic()
        running_payload = {
            "type": "step",
            "node": report_node,
            "display_name": _NODE_DISPLAY_NAMES[report_node],
            "status": "running",
            "report_owner": "lead_agent",
            "subagent_report_skipped": True,
        }
        tracer.start_span(
            trace_context,
            node="lead.narrate",
            display_name="Lead · 报告综合",
            input_payload={
                "question": final_state.get("question"),
                "original_question": final_state.get("original_question"),
                "dataset_id": effective_dataset_id,
                "sql": final_state.get("sql"),
                "sql_result": final_state.get("sql_result"),
                "route_decision": route_decision,
                "reason": "auto_routed_manifest",
            },
            trace_tags=["lead"],
        )
        yield _sse_data(running_payload)
        lead_report_result: dict | None = None
        async for report_event in stream_sql_result_report(
            final_state,
            db=db,
            observation_name="llm.lead_agent_report_generator",
            report_owner="lead_agent",
            metadata={"reason": "auto_routed_manifest"},
        ):
            if report_event.get("type") == "token":
                yield _sse_data({"type": "token", "content": report_event.get("content") or ""})
            elif report_event.get("type") == "result":
                lead_report_result = report_event
        if lead_report_result:
            final_state["answer"] = lead_report_result.get("answer")
            final_state["token_usage"] = lead_report_result.get("token_usage")
            final_state["lead_agent_report"] = {
                "generated": True,
                "reason": "auto_routed_manifest",
            }
        report_elapsed_ms = int((time.monotonic() - report_started_at) * 1000)
        done_payload = {
            "type": "step",
            "node": report_node,
            "display_name": _NODE_DISPLAY_NAMES[report_node],
            "status": "done",
            "elapsed_ms": report_elapsed_ms,
            "report_owner": "lead_agent",
            "subagent_report_skipped": True,
            "lead_agent_report": final_state.get("lead_agent_report") or {},
        }
        step_traces.append(done_payload)
        tracer.end_span(
            trace_context,
            node="lead.narrate",
            output_payload=done_payload,
            elapsed_ms=report_elapsed_ms,
        )
        yield _sse_data(done_payload)

    # 智能兜底：根据失败原因给出具体提示，而非生硬的"抱歉"
    raw_answer = final_state.get("answer")
    error = final_state.get("error")
    generation_mode = final_state.get("generation_mode")
    retry_count = final_state.get("retry_count", 0)
    sql_diagnosis = final_state.get("sql_diagnosis") or final_state.get("sql_audit_result")
    sql_retry_trace = final_state.get("sql_retry_trace") or []

    if raw_answer:
        answer = str(raw_answer)
    elif generation_mode == "inferred":
        if error:
            answer = f"AI 基于表结构推断查询时遇到问题：{error}。建议检查已选表的字段是否正确，或尝试在语义层中定义明确的指标。"
        else:
            answer = "AI 基于表结构推断查询时未能成功，请检查已选表配置或尝试换一种问法。"
    elif error:
        if sql_diagnosis:
            answer = f"查询处理出现问题：{error}。建议复核字段口径、语义层配置或数据源连接。"
        elif retry_count >= 3:
            answer = f"查询多次尝试后仍未能成功：{error}。建议检查语义层配置或数据源连接。"
        else:
            answer = f"查询处理出现问题：{error}。请稍后重试或换一种问法。"
    else:
        answer = "抱歉，暂时无法回答这个问题。请尝试选择数据集后提问，或检查语义层配置。"

    final_state["answer"] = answer
    answer_explanation = jsonable_encoder(build_answer_explanation(final_state))
    final_state["answer_explanation"] = answer_explanation

    sql = final_state.get("sql")
    sql_list = final_state.get("sql_list") or []
    token_usage = final_state.get("token_usage")
    execution_path = (
        final_state.get("entry_route")
        or final_state.get("entry_intent")
        or trace_context.execution_path
        or "unknown"
    )
    trace_context.execution_path = execution_path
    active_obs_context = current_observability_context.get()
    if active_obs_context:
        trace_context.prompt_versions.update(active_obs_context.prompt_versions)
    multiturn_observability_metrics = _multiturn_observability_metrics(
        lead_agent_context=lead_agent_context,
        final_state=final_state,
    )
    query_profile = _build_query_profile(
        final_state=final_state,
        lead_agent_context=lead_agent_context,
        route_decision=route_decision,
        step_traces=step_traces,
        sql=sql,
        sql_list=sql_list,
        execution_path=execution_path,
        effective_dataset_id=effective_dataset_id,
    )
    explainability = _build_explainability(
        query_profile=query_profile,
        answer_explanation=answer_explanation,
    )
    trace_metadata = {
        "status": "failed" if error else "success",
        "execution_path": execution_path,
        "original_question": payload.question,
        "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
        "entry_intent": final_state.get("entry_intent"),
        "entry_route": final_state.get("entry_route"),
        "blueprint_id": final_state.get("blueprint_id"),
        "knowledge_term_id": final_state.get("knowledge_term_id"),
        "selected_term_id": final_state.get("selected_term_id"),
        "lead_agent_context": lead_agent_context,
        "time_context": lead_agent_context.get("time_context"),
        "route_decision": route_decision,
        "schema_status": lead_agent_context.get("schema_status"),
        "manifest_version": route_decision.get("manifest_version"),
        "bound_schema_version": route_decision.get("bound_schema_version"),
        "report_owner": final_state.get("report_owner"),
        "subagent_report_skipped": final_state.get("subagent_report_skipped"),
        "lead_agent_report": final_state.get("lead_agent_report"),
        "prior_capsule_status": final_state.get("prior_capsule_status"),
        "multiturn_context": final_state.get("multiturn_context"),
        "turn_type": final_state.get("turn_type"),
        "merge_debug": final_state.get("merge_debug"),
        "out_capsule": final_state.get("out_capsule"),
        "multiturn_metrics": multiturn_observability_metrics,
        "query_profile": query_profile,
        "explainability": explainability,
        "prompt_versions": trace_context.prompt_versions,
    }
    tracer.update_trace_output(trace_context, output=answer, metadata=trace_metadata)

    # jsonable_encoder 把 datetime / Decimal 等转为 JSON 安全类型，再存 JSON 列
    response_metadata = jsonable_encoder({
        "answer_explanation": answer_explanation,
        "lead_agent_context": lead_agent_context,
        "original_question": payload.question,
        "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
        "time_context": lead_agent_context.get("time_context"),
        "route_decision": route_decision,
        "schema_status": lead_agent_context.get("schema_status"),
        "report_owner": final_state.get("report_owner"),
        "subagent_report_skipped": final_state.get("subagent_report_skipped"),
        "lead_agent_report": final_state.get("lead_agent_report"),
        "prior_capsule_status": final_state.get("prior_capsule_status"),
        "multiturn_context": final_state.get("multiturn_context"),
        "turn_type": final_state.get("turn_type"),
        "merge_debug": final_state.get("merge_debug"),
        "out_capsule": final_state.get("out_capsule"),
        "route_payload": final_state.get("route_payload"),
        "clarification_resolution": final_state.get("clarification_resolution_result"),
        "query_profile": query_profile,
        "explainability": explainability,
        "langfuse": {
            "trace_id": trace_context.trace_id,
            "session_id": trace_context.session_id,
            "release": trace_context.release,
            "environment": trace_context.environment,
            "prompt_label": trace_context.prompt_label,
            "base_url": trace_context.base_url,
            "project_id": trace_context.project_id,
            "trace_url": trace_context.trace_url,
            "enabled": trace_context.enabled,
            "active": trace_context.active,
            "prompt_versions": trace_context.prompt_versions,
        },
        "observability": trace_context.observability_payload(),
    })
    assistant_message = models.Message(
        conversation_id=conv_id,
        role="assistant",
        content=answer,
        sql_list=sql_list,
        token_usage=jsonable_encoder(token_usage),
        step_trace=jsonable_encoder(step_traces),
        response_metadata=response_metadata,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    total_tokens = 0
    if isinstance(token_usage, dict):
        total_tokens = int(token_usage.get("total_tokens") or 0)
    if trace_context.trace_id:
        db.add(
            models.ObservabilityTraceIndex(
                langfuse_trace_id=trace_context.trace_id,
                langfuse_session_id=trace_context.session_id,
                conversation_id=conv_id,
                message_id=assistant_message.id,
                dataset_id=effective_dataset_id,
                entry_route=execution_path,
                status="failed" if error else "success",
                total_tokens=total_tokens,
                total_cost=0,
                metadata_json=jsonable_encoder(trace_metadata),
            )
        )
        if error or sql_retry_trace:
            db.add(
                models.TraceAnnotationCandidate(
                    langfuse_trace_id=trace_context.trace_id,
                    conversation_id=conv_id,
                    message_id=assistant_message.id,
                    dataset_id=effective_dataset_id,
                    reason="sql_failure" if error else "sql_retry",
                    payload=jsonable_encoder({
                        "error": error,
                        "sql_retry_trace": sql_retry_trace,
                        "sql_diagnosis": sql_diagnosis,
                    }),
                )
            )
        db.commit()

    final_payload = {
        "type": "final",
        "sql": sql,
        "sql_list": sql_list,
        "answer": answer,
        "entry_intent": final_state.get("entry_intent"),
        "entry_route": final_state.get("entry_route"),
        "entry_reason": final_state.get("entry_reason"),
        "blueprint_id": final_state.get("blueprint_id"),
        "blueprint_match": final_state.get("blueprint_match"),
        "knowledge_term_id": final_state.get("knowledge_term_id"),
        "selected_term_id": final_state.get("selected_term_id"),
        "lead_agent_context": lead_agent_context,
        "original_question": payload.question,
        "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
        "time_context": lead_agent_context.get("time_context"),
        "route_decision": route_decision,
        "schema_status": lead_agent_context.get("schema_status"),
        "manifest_version": route_decision.get("manifest_version"),
        "bound_schema_version": route_decision.get("bound_schema_version"),
        "report_owner": final_state.get("report_owner"),
        "subagent_report_skipped": final_state.get("subagent_report_skipped"),
        "lead_agent_report": final_state.get("lead_agent_report"),
        "prior_capsule_status": final_state.get("prior_capsule_status"),
        "multiturn_context": final_state.get("multiturn_context"),
        "turn_type": final_state.get("turn_type"),
        "merge_debug": final_state.get("merge_debug"),
        "out_capsule": final_state.get("out_capsule"),
        "route_payload": final_state.get("route_payload"),
        "clarification_resolution": final_state.get("clarification_resolution_result"),
        "term_normalization": final_state.get("term_normalization"),
        "semantic_asset_resolution": final_state.get("semantic_asset_resolution"),
        "metric_resolution": final_state.get("metric_resolution"),
        "dataset_context_debug": final_state.get("dataset_context_debug"),
        "datasource_context": final_state.get("datasource_context"),
        "dsl": final_state.get("dsl"),
        "generation_mode": final_state.get("generation_mode"),
        "sql_result": final_state.get("sql_result"),
        "sql_diagnosis": sql_diagnosis,
        "sql_audit_result": final_state.get("sql_audit_result"),
        "sql_retry_trace": sql_retry_trace,
        "answer_explanation": answer_explanation,
        "query_profile": query_profile,
        "explainability": explainability,
        "response_metadata": response_metadata,
        "schema_tokens": final_state.get("schema_tokens"),
        "conversation_id": conv_id,
        "message_id": assistant_message.id,
        "title": conv.title,
        "langfuse_trace_id": trace_context.trace_id,
        "langfuse_session_id": trace_context.session_id,
        "observability": trace_context.observability_payload(),
        "multiturn_observability_metrics": multiturn_observability_metrics,
    }
    logger.info(
        f"[_stream_chat] final: answer_len={len(answer)}, sql={sql}, error={error}, mode={generation_mode}"
    )
    yield _sse_data(final_payload)
    if not defer_trace_close:
        tracer.close_trace(trace_context)
    obs_context_manager.__exit__(None, None, None)


def _persist_completed_turn(
    *,
    store: ConversationStore,
    state: models.ConversationState,
    user_id: str,
    business_session_id: str,
    effective_payload: schemas.ChatRequest,
    final_payload: dict,
    pending_resolution: dict,
    payload_question: str,
    trace_context_sink: list,
) -> bool:
    """把完成轮的胶囊、状态、澄清和追踪写入 ConversationStore。

    必须在 SSE yield final 事件之前同步调用——SSE 客户端在收到 final 后会
    立即断开，导致 yield 之后的代码因 CancelledError 不执行。
    返回是否成功写入。
    """
    final_session_id = business_session_id
    final_state = state
    if (
        effective_payload.session_id is None
        and effective_payload.conversation_id is None
        and final_payload.get("conversation_id")
    ):
        final_session_id = session_key(None, int(final_payload["conversation_id"]))
        final_state = store.load_or_create(session_id=final_session_id, user_id=user_id)
    active_dataset_id = (
        final_payload.get("route_decision", {}).get("dataset_id")
        or final_payload.get("dataset_id")
        or effective_payload.dataset_id
    )
    updated_capsules = store.with_updated_capsule(
        final_state,
        dataset_id=active_dataset_id,
        capsule=final_payload.get("out_capsule"),
    )
    pending_for_store = pending_clarification_from_final_payload(
        final_payload,
        original_question=payload_question,
    )
    store.append_completed_turn(
        session_id=final_session_id,
        question=payload_question,
        answer=final_payload.get("answer"),
        conversation_id=final_payload.get("conversation_id") or effective_payload.conversation_id,
        active_dataset_id=active_dataset_id,
        resolved_time_context=final_payload.get("time_context"),
        pending_clarification=pending_for_store,
        clear_pending_clarification=bool(
            pending_for_store is None
            and (
                pending_resolution.get("clear_pending")
                or pending_resolution.get("status") in {"resolved", "cleared", "inject"}
            )
        ),
        subagent_capsules=updated_capsules,
        trace_context=trace_context_sink[0] if trace_context_sink else None,
    )
    logger.info(
        "[_stream_chat] 多轮状态已写入: session_id=%s, turn_index=%s, active_dataset_id=%s",
        final_session_id,
        final_state.turn_index,
        active_dataset_id,
    )
    return True


async def _stream_chat(payload: schemas.ChatRequest, db: Session):
    """多轮状态包装层。

    默认 feature flag 关闭时直接走原单轮链路；开启后负责 session 锁和完成轮次写回。
    """

    settings = get_settings()
    if not settings.MULTITURN_ENABLED:
        async for event in _stream_chat_singleturn(payload, db):
            yield event
        return

    store = ConversationStore(db)
    business_session_id = session_key(payload.session_id, payload.conversation_id)
    if business_session_id == "conversation-new":
        business_session_id = f"request-{uuid.uuid4().hex[:16]}"
    user_id = "1"
    lock_owner = f"chat-{uuid.uuid4().hex[:12]}"
    state = store.load_or_create(session_id=business_session_id, user_id=user_id)
    if not store.acquire_turn_lock(
        session_id=business_session_id,
        lock_owner=lock_owner,
        ttl_seconds=settings.MULTITURN_LOCK_TTL_SECONDS,
    ):
        yield _sse_data(
            {
                "type": "final",
                "sql": None,
                "sql_list": [],
                "answer": "同一会话已有一轮问数正在处理中，请稍后再试。",
                "entry_intent": "multiturn_lock",
                "entry_route": "turn_pending",
                "conversation_id": payload.conversation_id,
            }
        )
        return

    final_payload: dict | None = None
    completed = False
    trace_context_sink: list = []
    effective_payload = payload
    pending_resolution = store.resolve_pending_clarification(
        state,
        question=payload.question,
        clarification_response=payload.clarification_response,
    )
    if pending_resolution.get("status") == "resolved" and pending_resolution.get("type") == "dataset":
        effective_payload = payload.model_copy(
            update={
                "dataset_id": int(pending_resolution["dataset_id"]),
                "clarification_response": None,
            }
        )
    elif pending_resolution.get("status") == "inject" and pending_resolution.get("type") == "term":
        updates = {
            "clarification_response": pending_resolution.get("clarification_response") or {},
        }
        if pending_resolution.get("conversation_id") and payload.conversation_id is None:
            updates["conversation_id"] = int(pending_resolution["conversation_id"])
        if pending_resolution.get("dataset_id") and payload.dataset_id is None:
            updates["dataset_id"] = int(pending_resolution["dataset_id"])
        effective_payload = payload.model_copy(update=updates)
    try:
        async for event in _stream_chat_singleturn(
            effective_payload,
            db,
            multiturn_context=store.lead_multiturn_context(state),
            conversation_state=state,
            conversation_store=store,
            observability_session_id=business_session_id,
            trace_context_sink=trace_context_sink,
            defer_trace_close=True,
        ):
            data = event.get("data") if isinstance(event, dict) else None
            if data:
                try:
                    parsed = json.loads(data)
                    if parsed.get("type") == "final":
                        final_payload = parsed
                        # 关键：SSE 在客户端收到 final 后会立即关闭连接，
                        # yield 之后的代码可能因 CancelledError 不执行，
                        # 因此这里在 yield 前同步写入多轮状态，保证下一轮能读上轮胶囊。
                        try:
                            completed = _persist_completed_turn(
                                store=store,
                                state=state,
                                user_id=user_id,
                                business_session_id=business_session_id,
                                effective_payload=effective_payload,
                                final_payload=final_payload,
                                pending_resolution=pending_resolution,
                                payload_question=payload.question,
                                trace_context_sink=trace_context_sink,
                            )
                        except Exception as persist_exc:  # noqa: BLE001
                            logger.exception(
                                "[_stream_chat] 写入多轮状态失败: %s", persist_exc
                            )
                except json.JSONDecodeError:
                    pass
            yield event
    finally:
        if completed and trace_context_sink:
            tracer = get_observability_tracer()
            tracer.close_trace(trace_context_sink[0])
        if not completed:
            logger.info("[_stream_chat] 多轮请求未正常完成，仅释放会话锁: %s", business_session_id)
        store.release_turn_lock(session_id=business_session_id, lock_owner=lock_owner)


@router.post("/stream")
def chat_stream(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    """流式问数接口，返回 SSE 事件流。"""
    logger.info(
        f"[chat_stream] 接收到请求: question={payload.question[:30]}, dataset_id={payload.dataset_id}"
    )
    return EventSourceResponse(_stream_chat(payload, db))


@router.post("/feedback")
def chat_feedback(payload: schemas.ChatFeedback, db: Session = Depends(get_db)):
    """人工反馈接口，对接 LangGraph HumanFeedback 节点（Phase 3 完善）。"""
    return submit_message_feedback(
        db,
        message_id=payload.message_id,
        action=payload.action,
        comment=payload.comment,
        trace_id=payload.trace_id,
        reason=payload.reason,
    )


# ============================================================
# Phase 2: 上提 Merge 阶段到 LeadAgent — chat 层辅助
# ============================================================


def _build_out_capsule_for_chat(
    state: dict, updates: dict | None = None
) -> dict:
    """Phase 2: 把 graph.nodes.build_out_capsule 暴露给 chat.py 的 out_capsule_factory。

    保留与 nodes.py 实现同语义（生成下一轮继续追问所需的 query_context + result_digest）。
    """
    from app.graph.nodes import build_out_capsule

    return build_out_capsule(state, updates)


def _early_trace_status(entry_route: str) -> str:
    """把早退路由映射成 trace index 状态。"""
    return "blocked" if entry_route == "reject" else "success"


def _early_trace_metadata(
    *,
    final_state: dict,
    lead_agent_context: dict,
    route_decision: dict,
    response_metadata: dict,
    trace_context: Any,
) -> dict:
    """组装早退分支的 trace metadata，保持与正常 final 分支字段对齐。"""
    active_obs_context = current_observability_context.get()
    if active_obs_context:
        trace_context.prompt_versions.update(active_obs_context.prompt_versions)
    return {
        "status": _early_trace_status(final_state.get("entry_route") or ""),
        "execution_path": final_state.get("entry_route") or final_state.get("entry_intent"),
        "original_question": final_state.get("original_question"),
        "resolved_question": final_state.get("resolved_question"),
        "entry_intent": final_state.get("entry_intent"),
        "entry_route": final_state.get("entry_route"),
        "entry_reason": final_state.get("entry_reason"),
        "blueprint_id": final_state.get("blueprint_id"),
        "knowledge_term_id": final_state.get("knowledge_term_id"),
        "lead_agent_context": lead_agent_context,
        "time_context": lead_agent_context.get("time_context"),
        "route_decision": route_decision,
        "schema_status": lead_agent_context.get("schema_status"),
        "route_payload": final_state.get("route_payload"),
        "response_metadata": response_metadata,
        "prompt_versions": trace_context.prompt_versions,
    }


def _early_langfuse_payload(trace_context: Any) -> dict:
    """提取前端和审计页需要的 Langfuse trace 信息。"""
    return {
        "trace_id": trace_context.trace_id,
        "session_id": trace_context.session_id,
        "release": trace_context.release,
        "environment": trace_context.environment,
        "prompt_label": trace_context.prompt_label,
        "base_url": trace_context.base_url,
        "project_id": trace_context.project_id,
        "trace_url": trace_context.trace_url,
        "enabled": trace_context.enabled,
        "active": trace_context.active,
        "prompt_versions": trace_context.prompt_versions,
    }


def _finalize_early_trace(
    *,
    db: Session,
    assistant_message: models.Message,
    effective_dataset_id: int | None,
    lead_agent_context: dict,
    route_decision: dict,
    trace_context: Any,
    response_metadata: dict,
    final_state: dict,
    answer: str,
    defer_trace_close: bool,
) -> dict:
    """早退分支在发送 final 前完成 trace 输出、索引落库和可观测 metadata。"""
    tracer = get_observability_tracer()
    trace_metadata = _early_trace_metadata(
        final_state=final_state,
        lead_agent_context=lead_agent_context,
        route_decision=route_decision,
        response_metadata=response_metadata,
        trace_context=trace_context,
    )
    response_metadata["langfuse"] = _early_langfuse_payload(trace_context)
    response_metadata["observability"] = trace_context.observability_payload()
    tracer.update_trace_output(trace_context, output=answer, metadata=trace_metadata)
    assistant_message.response_metadata = jsonable_encoder(response_metadata)

    if trace_context.trace_id:
        db.add(
            models.ObservabilityTraceIndex(
                langfuse_trace_id=trace_context.trace_id,
                langfuse_session_id=trace_context.session_id,
                conversation_id=assistant_message.conversation_id,
                message_id=assistant_message.id,
                dataset_id=effective_dataset_id,
                entry_route=trace_metadata.get("execution_path") or "early_return",
                status=trace_metadata["status"],
                total_tokens=0,
                total_cost=0,
                metadata_json=jsonable_encoder(trace_metadata),
            )
        )
    db.commit()
    db.refresh(assistant_message)
    if not defer_trace_close:
        tracer.close_trace(trace_context)
    return trace_metadata


async def _interpret_early_return(
    *,
    db: Session,
    conv: models.Conversation,
    payload: schemas.ChatRequest,
    effective_dataset_id: int | None,
    lead_agent_context: dict,
    route_decision: dict,
    trace_context: Any,
    defer_trace_close: bool,
    obs_context_manager: Any,
    interpret_payload: dict,
    turn_type: str,
    multiturn_context: dict | None,
    merge_debug: dict,
):
    """interpret_result 早退：保存助手消息、emit SSE final 事件，不走 LangGraph。

    早退前会写入 trace output 和 TraceIndex，避免 SSE final 后断连丢失收尾逻辑。
    """
    answer = interpret_payload.get("answer") or "已生成解释。"
    entry_intent = interpret_payload.get("entry_intent") or "interpret"
    entry_route = interpret_payload.get("entry_route") or "interpret_result"
    route_payload = {
        "kind": "interpret_result",
        "answer": answer,
        "out_capsule": interpret_payload.get("out_capsule"),
    }
    final_state = {
        "original_question": payload.question,
        "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
        "entry_intent": entry_intent,
        "entry_route": entry_route,
        "route_payload": route_payload,
        "time_context": lead_agent_context.get("time_context"),
        "multiturn_context": multiturn_context,
        "merge_debug": merge_debug,
        "turn_type": turn_type,
        "sql_result": None,
    }
    response_metadata = jsonable_encoder({
        "lead_agent_context": lead_agent_context,
        "original_question": payload.question,
        "resolved_question": final_state["resolved_question"],
        "route_decision": route_decision,
        "time_context": lead_agent_context.get("time_context"),
        "schema_status": lead_agent_context.get("schema_status"),
        "route_payload": route_payload,
        "multiturn_context": multiturn_context,
        "merge_debug": merge_debug,
    })
    assistant_message = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        sql_list=[],
        step_trace=[_lead_agent_event(lead_agent_context), _route_decision_event(route_decision)],
        response_metadata=response_metadata,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    trace_metadata = _finalize_early_trace(
        db=db,
        assistant_message=assistant_message,
        effective_dataset_id=effective_dataset_id,
        lead_agent_context=lead_agent_context,
        route_decision=route_decision,
        trace_context=trace_context,
        response_metadata=response_metadata,
        final_state=final_state,
        answer=answer,
        defer_trace_close=defer_trace_close,
    )
    obs_context_manager.__exit__(None, None, None)

    yield _sse_data(
        {
            "type": "step",
            "node": "interpret_result",
            "display_name": "解释上一轮结果",
            "status": "done",
        }
    )
    yield _sse_data(
        {
            "type": "final",
            "sql": None,
            "sql_list": [],
            "answer": answer,
            "entry_intent": entry_intent,
            "entry_route": entry_route,
            "entry_reason": "interpret_result_early_return",
            "lead_agent_context": lead_agent_context,
            "original_question": payload.question,
            "resolved_question": final_state["resolved_question"],
            "time_context": lead_agent_context.get("time_context"),
            "route_decision": route_decision,
            "schema_status": lead_agent_context.get("schema_status"),
            "clarification": None,
            "route_payload": route_payload,
            "sql_result": None,
            "query_profile": None,
            "explainability": None,
            "response_metadata": response_metadata,
            "conversation_id": conv.id,
            "message_id": assistant_message.id,
            "title": conv.title,
            "langfuse_trace_id": trace_context.trace_id,
            "langfuse_session_id": trace_context.session_id,
            "observability": trace_context.observability_payload(),
            "trace_metadata": trace_metadata,
            "out_capsule": interpret_payload.get("out_capsule"),
        }
    )


async def _early_route_return(
    *,
    db: Session,
    conv: models.Conversation,
    payload: schemas.ChatRequest,
    effective_dataset_id: int | None,
    lead_agent_context: dict,
    route_decision: dict,
    trace_context: Any,
    defer_trace_close: bool,
    obs_context_manager: Any,
    routing: dict,
):
    """Phase 3: LeadAgent 入口路由早退（chitchat/reject/knowledge_qa/clarify）。

    直接保存助手消息、emit SSE final 事件，不调 LangGraph。
    """
    entry_intent = routing.get("entry_intent") or "early_return"
    entry_route = routing.get("entry_route") or "direct_answer"
    answer = routing.get("answer") or "已生成回答。"
    route_payload = routing.get("route_payload") or {"kind": entry_route}
    final_state = {
        "original_question": payload.question,
        "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
        "entry_intent": entry_intent,
        "entry_route": entry_route,
        "entry_reason": routing.get("entry_reason"),
        "route_payload": route_payload,
        "time_context": lead_agent_context.get("time_context"),
        "blueprint_id": routing.get("blueprint_id"),
        "knowledge_term_id": routing.get("knowledge_term_id"),
        "sql_result": None,
    }
    response_metadata = jsonable_encoder({
        "lead_agent_context": lead_agent_context,
        "original_question": payload.question,
        "resolved_question": final_state["resolved_question"],
        "route_decision": route_decision,
        "time_context": lead_agent_context.get("time_context"),
        "schema_status": lead_agent_context.get("schema_status"),
        "route_payload": route_payload,
        "routing": routing,
    })
    assistant_message = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        sql_list=[],
        step_trace=[_lead_agent_event(lead_agent_context), _route_decision_event(route_decision)],
        response_metadata=response_metadata,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    trace_metadata = _finalize_early_trace(
        db=db,
        assistant_message=assistant_message,
        effective_dataset_id=effective_dataset_id,
        lead_agent_context=lead_agent_context,
        route_decision=route_decision,
        trace_context=trace_context,
        response_metadata=response_metadata,
        final_state=final_state,
        answer=answer,
        defer_trace_close=defer_trace_close,
    )
    obs_context_manager.__exit__(None, None, None)

    yield _sse_data(
        {
            "type": "final",
            "sql": None,
            "sql_list": [],
            "answer": answer,
            "entry_intent": entry_intent,
            "entry_route": entry_route,
            "entry_reason": routing.get("entry_reason"),
            "lead_agent_context": lead_agent_context,
            "original_question": payload.question,
            "resolved_question": final_state["resolved_question"],
            "time_context": lead_agent_context.get("time_context"),
            "route_decision": route_decision,
            "schema_status": lead_agent_context.get("schema_status"),
            "clarification": None,
            "route_payload": route_payload,
            "sql_result": None,
            "query_profile": None,
            "explainability": None,
            "response_metadata": response_metadata,
            "conversation_id": conv.id,
            "message_id": assistant_message.id,
            "title": conv.title,
            "langfuse_trace_id": trace_context.trace_id,
            "langfuse_session_id": trace_context.session_id,
            "observability": trace_context.observability_payload(),
            "trace_metadata": trace_metadata,
        }
    )
