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
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

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
from app.services.lead_agent import build_lead_agent_context
from app.services.report_generation import stream_sql_result_report

router = APIRouter()
logger = logging.getLogger(__name__)


# 节点名称到前端展示名的映射
_NODE_DISPLAY_NAMES = {
    "clarification_resolution": "澄清解析",
    "intent_recognition": "意图识别",
    "entry_intent_classification": "入口分类",
    "analysis_blueprint_execute": "蓝图执行",
    "schema_recall": "Schema 召回",
    "term_normalize_node": "术语归一化",
    "semantic_asset_resolution_node": "语义资产解析",
    "metric_resolution_node": "指标解析",
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

    assistant_message = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        sql_list=[],
        step_trace=[_lead_agent_event(lead_agent_context), _route_decision_event(route_decision)],
        response_metadata=jsonable_encoder({
            "lead_agent_context": lead_agent_context,
            "original_question": lead_agent_context.get("original_question"),
            "resolved_question": lead_agent_context.get("resolved_question"),
            "route_decision": route_decision,
            "time_context": lead_agent_context.get("time_context"),
            "schema_status": lead_agent_context.get("schema_status"),
            "route_payload": {
                "kind": "manifest_route",
                "decision": route_decision.get("decision"),
                "candidates": route_decision.get("candidates") or [],
                "reason": route_decision.get("reason"),
            },
        }),
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return assistant_message


async def _stream_chat(payload: schemas.ChatRequest, db: Session):
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
        metadata={
            "thread_id": conv.thread_id,
            "title": conv.title,
            "phase": "lead_agent",
        },
    )
    obs_context_manager = set_observability_context(trace_context.request_context())
    obs_context_manager.__enter__()

    lead_agent_context = build_lead_agent_context(
        db,
        question=payload.question,
        conversation=conv,
        payload_dataset_id=payload.dataset_id,
        tracer=tracer,
        trace_context=trace_context,
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
        tracer.close_trace(trace_context)
        obs_context_manager.__exit__(None, None, None)
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
                "route_payload": {
                    "kind": "manifest_route",
                    "decision": route_decision.get("decision"),
                    "candidates": route_decision.get("candidates") or [],
                    "reason": route_decision.get("reason"),
                },
                "sql_result": None,
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
    initial_state = {
        "question": resolved_question,
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
        "clarification_resolution_result": None,
        "intent": None,
        "entities": None,
        "entry_intent": None,
        "entry_route": None,
        "entry_reason": None,
        "blueprint_id": None,
        "blueprint_match": None,
        "blueprint_context": None,
        "knowledge_term_id": None,
        "selected_term_id": None,
        "route_payload": None,
        "schema_context": None,
        "schema_structured": None,
        "ddl_context": None,
        "query_constraints": None,
        "dataset_context_debug": None,
        "datasource_context": None,
        "term_normalization": None,
        "semantic_asset_resolution": None,
        "metric_resolution": None,
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
    final_state: dict = dict(initial_state)
    node_start_times: dict[str, float] = {}

    try:
        logger.info("[_stream_chat] 开始 astream_events 工作流...")
        # 去重集合：astream_events v2 中子 chain 也会触发 on_chain_start/end，
        # 同一 langgraph_node 名称可能重复出现，只取每个节点的第一次事件
        reported_running: set[str] = set()
        reported_done: set[str] = set()
        step_traces: list[dict] = []  # 收集推理步骤供历史加载时恢复思维链

        async for event in app_graph.astream_events(initial_state, version="v2"):
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
                if lg_node == "intent_recognition":
                    sse_payload["intent"] = final_state.get("intent") or ""
                    sse_payload["entities"] = final_state.get("entities") or {}
                elif lg_node == "clarification_resolution":
                    sse_payload["clarification_resolution"] = (
                        final_state.get("clarification_resolution_result") or {}
                    )
                    sse_payload["route_payload"] = final_state.get("route_payload") or {}
                elif lg_node == "entry_intent_classification":
                    sse_payload["entry_intent"] = final_state.get("entry_intent") or ""
                    sse_payload["entry_route"] = final_state.get("entry_route") or ""
                    sse_payload["entry_reason"] = final_state.get("entry_reason") or ""
                    sse_payload["blueprint_id"] = final_state.get("blueprint_id")
                    sse_payload["route_payload"] = final_state.get("route_payload") or {}
                elif lg_node == "analysis_blueprint_execute":
                    result = final_state.get("sql_result") or {}
                    sse_payload["blueprint_id"] = final_state.get("blueprint_id")
                    sse_payload["sql"] = final_state.get("sql") or ""
                    sse_payload["rows"] = result.get("row_count", 0)
                    sse_payload["columns"] = result.get("columns", [])
                    sse_payload["route_payload"] = final_state.get("route_payload") or {}
                elif lg_node in ("semantic_asset_resolution_node", "metric_resolution_node"):
                    sse_payload["semantic_asset_resolution"] = (
                        final_state.get("semantic_asset_resolution") or {}
                    )
                    sse_payload["metric_resolution"] = final_state.get("metric_resolution") or {}
                elif lg_node == "term_normalize_node":
                    sse_payload["term_normalization"] = (
                        final_state.get("term_normalization") or {}
                    )
                    sse_payload["entry_route"] = final_state.get("entry_route") or ""
                    sse_payload["route_payload"] = final_state.get("route_payload") or {}
                elif lg_node == "dsl_generate":
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
            node=report_node,
            display_name=_NODE_DISPLAY_NAMES[report_node],
            input_payload={
                "question": final_state.get("question"),
                "original_question": final_state.get("original_question"),
                "dataset_id": effective_dataset_id,
                "sql": final_state.get("sql"),
                "sql_result": final_state.get("sql_result"),
                "route_decision": route_decision,
                "reason": "auto_routed_manifest",
            },
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
            node=report_node,
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
            retry_suffix = ""
            if sql_retry_trace:
                retry_suffix = f"。系统已尝试自动修复 {len(sql_retry_trace)} 次"
                failed_reasons = [
                    item.get("result") or item.get("error")
                    for item in sql_retry_trace
                    if item.get("status") == "failed"
                ]
                if failed_reasons:
                    retry_suffix += f"，最后结果：{failed_reasons[-1]}"
            answer = f"查询处理出现问题：{error}{retry_suffix}"
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
        "prompt_versions": trace_context.prompt_versions,
    }
    tracer.update_trace_output(trace_context, output=answer, metadata=trace_metadata)

    # jsonable_encoder 把 datetime / Decimal 等转为 JSON 安全类型，再存 JSON 列
    assistant_message = models.Message(
        conversation_id=conv_id,
        role="assistant",
        content=answer,
        sql_list=sql_list,
        token_usage=jsonable_encoder(token_usage),
        step_trace=jsonable_encoder(step_traces),
        response_metadata=jsonable_encoder({
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
            "route_payload": final_state.get("route_payload"),
            "clarification_resolution": final_state.get("clarification_resolution_result"),
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
        }),
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
        "schema_tokens": final_state.get("schema_tokens"),
        "conversation_id": conv_id,
        "message_id": assistant_message.id,
        "title": conv.title,
        "langfuse_trace_id": trace_context.trace_id,
        "langfuse_session_id": trace_context.session_id,
        "observability": trace_context.observability_payload(),
    }
    logger.info(
        f"[_stream_chat] final: answer_len={len(answer)}, sql={sql}, error={error}, mode={generation_mode}"
    )
    yield _sse_data(final_payload)
    tracer.close_trace(trace_context)
    obs_context_manager.__exit__(None, None, None)


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
