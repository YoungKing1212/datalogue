# ============================================================
# File Name   : agentscope_chat_bridge.py
# Description:
#   Chat turn 到 AgentScope 工作台会话镜像的桥接服务。
#
# Responsibilities:
#   - 在新会话主链执行前写入 user message 和 assistant running message。
#   - 在 stream 过程中投影事件，并在完成或失败时收口 assistant message。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

import re

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.schemas.bi_workbench import DatalogueEventEnvelope
from app.events.projection import project_event_envelope_to_agentscope
from app.services.agentscope_mirror import (
    append_user_message,
    create_agentscope_session,
    create_running_assistant_message,
    mark_message_completed,
    mark_message_failed,
    mark_message_interrupted,
)
from app.runtime.thread_resolver import resolve_thread_ref

_INTERNAL_TEXT_RE = re.compile(
    r"(\b(select|insert|update|delete|with)\b[\s\S]{0,120}\b(from|into|set)\b)"
    r"|(\b(psycopg2|sqlalchemy|traceback|undefinedcolumn|undefinedtable|programmingerror|operationalerror)\b)"
    r"|(\b(column|table|relation)\s+['\"]?[\w.]+['\"]?\s+(does not exist|not found))",
    re.IGNORECASE,
)


class AgentScopeChatBridgeContext(BaseModel):
    thread_id: str
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    is_legacy_read_only: bool = False


def begin_chat_turn(
    db: Session,
    *,
    raw_thread_id: str | int | None,
    user_text: str,
    metadata: dict,
) -> AgentScopeChatBridgeContext:
    thread_text = str(raw_thread_id).strip() if raw_thread_id is not None else None
    # Chat active path 只把显式 conv_* 视为旧会话只读；纯数字属于历史 resolver 兼容，不用于新主链 mirror。
    if thread_text and thread_text.startswith("conv_"):
        thread_ref = resolve_thread_ref(thread_text)
        return AgentScopeChatBridgeContext(  # conv_* 只读回放，不伪造 AgentScope session/message。
            thread_id=thread_ref.thread_id,
            is_legacy_read_only=True,
        )
    if thread_text and not thread_text.startswith("as_"):
        thread_text = None
    thread_ref = resolve_thread_ref(thread_text)

    session = create_agentscope_session(
        db,
        thread_id=thread_ref.thread_id if thread_ref else None,
        title=user_text[:80] or "新对话",
        legacy_conversation_id=metadata.get("legacy_conversation_id"),
        metadata=_safe_initial_payload(metadata),
    )
    user_message = append_user_message(
        db,
        thread_id=session.thread_id,
        content_summary=_safe_payload_text(
            user_text[:500],
            fallback="用户发起了一次问数请求。",
        ),
        payload=_safe_initial_payload(metadata),
    )
    assistant_message = create_running_assistant_message(
        db,
        thread_id=session.thread_id,
        lease_seconds=300,
    )
    return AgentScopeChatBridgeContext(
        thread_id=session.thread_id,
        user_message_id=user_message.message_id,
        assistant_message_id=assistant_message.message_id,
        is_legacy_read_only=False,
    )


def record_stream_event(
    db: Session,
    *,
    context: AgentScopeChatBridgeContext,
    envelope: DatalogueEventEnvelope,
) -> None:
    if context.is_legacy_read_only or not context.assistant_message_id:
        return
    project_event_envelope_to_agentscope(
        db,
        thread_id=context.thread_id,
        assistant_message_id=context.assistant_message_id,
        envelope=envelope,
    )


def complete_chat_turn(
    db: Session,
    *,
    context: AgentScopeChatBridgeContext,
    final_summary: str,
    final_payload: dict,
):
    if context.is_legacy_read_only or not context.assistant_message_id:
        return None
    return mark_message_completed(
        db,
        message_id=context.assistant_message_id,
        content_summary=final_summary[:1000],
        payload=_safe_final_payload(final_payload),
    )


def fail_chat_turn(
    db: Session,
    *,
    context: AgentScopeChatBridgeContext,
    error_summary: str,
    error_payload: dict,
):
    if context.is_legacy_read_only or not context.assistant_message_id:
        return None
    return mark_message_failed(
        db,
        message_id=context.assistant_message_id,
        error_summary=error_summary[:1000],
        payload=_safe_final_payload(error_payload),
    )


def interrupt_chat_turn(
    db: Session,
    *,
    context: AgentScopeChatBridgeContext,
    reason: str,
):
    if context.is_legacy_read_only or not context.assistant_message_id:
        return None
    return mark_message_interrupted(
        db,
        message_id=context.assistant_message_id,
        reason=reason[:1000],
    )


def _safe_initial_payload(metadata: dict) -> dict:
    payload: dict = {}
    for key in ("dataset_id", "candidate_id", "checkpoint_ref", "legacy_conversation_id"):
        if metadata.get(key) is not None:
            payload[key] = metadata[key]
    if isinstance(metadata.get("agentic_runtime_boundary"), dict):
        # 安全边界已在上游投影处理；这里只允许整块业务安全契约进入 mirror metadata。
        payload["agentic_runtime_boundary"] = metadata["agentic_runtime_boundary"]
    return payload


def _safe_final_payload(payload: dict) -> dict:
    safe: dict = {}
    for key in ("answer", "summary"):
        if payload.get(key) is not None:
            safe[key] = _safe_payload_text(str(payload[key]), fallback="查询已完成，结果请通过引用查看。")
    for key in ("artifact_ref", "checkpoint_ref", "repair_plan_ref", "trace_ref", "thread_id"):
        if payload.get(key) is not None:
            safe[key] = payload[key]
    if payload.get("error"):
        safe["error_summary"] = "问数执行失败，内部细节已隐藏。"
    return safe


def _safe_payload_text(text: str, *, fallback: str) -> str:
    if _INTERNAL_TEXT_RE.search(text):
        return fallback
    return text
