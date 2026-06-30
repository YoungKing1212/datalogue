# ============================================================
# File Name   : workbench_actions.py
# Description:
#   C3 Workbench 受控动作服务。
#
# Responsibilities:
#   - 回收超时 running assistant message，并写入业务级中断状态。
#   - 基于 checkpoint/ref 受理 Workbench retry 请求。
#   - 保证 retry 只写 AgentScope mirror，不直接执行 SQL 或 QueryGraph。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.agentscope_workbench import AgentScopeMessage, AgentScopeRef, AgentScopeSession
from app.schemas.agentscope_workbench import (
    WorkbenchRetryRequest,
    WorkbenchRetryResponse,
    WorkbenchRetryRunRequest,
)
from app.services.agentscope_mirror import (
    create_running_assistant_message,
    find_expired_running_messages,
    record_agentscope_event,
    record_agentscope_ref,
)
from app.services.agentscope_thread_resolver import normalize_thread_id


_INTERNAL_RETRY_TEXT_RE = re.compile(
    r"\b(select|insert|update|delete|from|join|where|union|with)\b|raw_sql|schema|raw_rows|query_plan|hidden_table",
    re.IGNORECASE,
)


class WorkbenchActionNotFoundError(LookupError):
    """Workbench action 目标不存在；API 层映射为 404。"""


class WorkbenchActionConflictError(ValueError):
    """Workbench action 状态冲突；API 层映射为 409。"""


def run_lease_recovery(db: Session, *, now: datetime) -> list[AgentScopeMessage]:
    """将超时 running message 收口为 interrupted，避免前端永久显示执行中。"""

    recovered: list[AgentScopeMessage] = []
    for message in find_expired_running_messages(db, now=now):
        checkpoint_ref = _message_checkpoint_ref(message) or _fallback_checkpoint_ref(message)
        payload = dict(message.business_payload_json or {})
        payload["checkpoint_ref"] = checkpoint_ref
        payload["recovery_status"] = "interrupted"
        message.status = "interrupted"
        message.content_summary = "问数任务超时中断，可从检查点安全重试。"
        message.business_payload_json = payload  # recovery 只写业务级 checkpoint，不写 SQL/schema/raw rows。
        message.completed_at = now
        message.lease_expires_at = None
        db.add(message)
        _ensure_checkpoint_ref(db, message=message, checkpoint_ref=checkpoint_ref)
        recovered.append(message)
    if recovered:
        db.commit()
        for message in recovered:
            db.refresh(message)
    return recovered


def request_controlled_retry(db: Session, *, request: WorkbenchRetryRequest) -> WorkbenchRetryResponse:
    """受理 Workbench retry；创建新 running message，真实重跑仍交给后续 chat/checkpoint 链路。"""

    normalized_thread_id = _normalize_action_thread_id(request.thread_id)
    if normalized_thread_id.startswith("conv_"):
        return WorkbenchRetryResponse(
            thread_id=normalized_thread_id,
            retry_message_id=None,
            accepted=False,
            disabled_reason="旧会话为只读模式，不能直接发起 Workbench 重试。",
            run_request=None,
        )
    if request.selected_action != "retry_last_step":
        raise WorkbenchActionConflictError("unsupported retry action")

    session = db.query(AgentScopeSession).filter(AgentScopeSession.thread_id == normalized_thread_id).one_or_none()
    if session is None:
        raise WorkbenchActionNotFoundError("workbench thread not found")
    source_message = (
        db.query(AgentScopeMessage)
        .filter(AgentScopeMessage.thread_id == normalized_thread_id)
        .filter(AgentScopeMessage.message_id == request.message_id)
        .one_or_none()
    )
    if source_message is None:
        raise WorkbenchActionNotFoundError("workbench message not found")
    if source_message.status not in {"failed", "interrupted"}:
        raise WorkbenchActionConflictError("message is not retryable")
    validate_retry_checkpoint(db, thread_id=normalized_thread_id, checkpoint_ref=request.checkpoint_ref)

    retry_message = create_running_assistant_message(db, thread_id=normalized_thread_id, lease_seconds=300)
    retry_message.business_payload_json = {
        "checkpoint_ref": request.checkpoint_ref,
        "selected_action": request.selected_action,
    }
    db.add(retry_message)
    db.commit()
    db.refresh(retry_message)
    record_agentscope_ref(
        db,
        thread_id=normalized_thread_id,
        message_id=retry_message.message_id,
        ref_type="checkpoint",
        ref_value=request.checkpoint_ref,
        relation="checkpoint",
    )
    record_agentscope_event(
        db,
        thread_id=normalized_thread_id,
        message_id=retry_message.message_id,
        event_type="workbench.retry_requested",
        payload={
            "summary": "已接收重试请求，准备从检查点恢复。",
            "checkpoint_ref": request.checkpoint_ref,
            "selected_action": request.selected_action,
        },
        visibility="user",
        task_id=None,
        trace_id=None,
    )
    run_request = WorkbenchRetryRunRequest(
        # C3-P1 只把 Workbench retry 转成 Chat 主链恢复请求；真实执行上下文必须由 checkpoint 恢复。
        question=_retry_run_question(session=session, source_message=source_message),
        conversation_id=session.legacy_conversation_id,
        thread_id=normalized_thread_id,
        retry_checkpoint_ref=request.checkpoint_ref,
        dataset_id=_retry_dataset_id(source_message),
        display_text="重试上一步",
    )
    return WorkbenchRetryResponse(
        thread_id=normalized_thread_id,
        retry_message_id=retry_message.message_id,
        accepted=True,
        disabled_reason=None,
        run_request=run_request,
    )


def validate_retry_checkpoint(db: Session, *, thread_id: str, checkpoint_ref: str) -> None:
    """确认 checkpoint ref 属于当前 thread；不接受客户端自带执行上下文。"""

    if not checkpoint_ref.startswith(("checkpoint://", "checkpoint:")):
        raise WorkbenchActionConflictError("checkpoint unavailable")
    exists = (
        db.query(AgentScopeRef)
        .filter(AgentScopeRef.thread_id == thread_id)
        .filter(AgentScopeRef.ref_type == "checkpoint")
        .filter(AgentScopeRef.ref_value == checkpoint_ref)
        .one_or_none()
    )
    if exists is None:
        raise WorkbenchActionConflictError("checkpoint unavailable")


def _normalize_action_thread_id(thread_id: str) -> str:
    try:
        normalized = normalize_thread_id(thread_id)
    except ValueError as exc:
        raise WorkbenchActionNotFoundError("workbench thread not found") from exc
    if normalized is None:
        raise WorkbenchActionNotFoundError("workbench thread not found")
    return normalized


def _message_checkpoint_ref(message: AgentScopeMessage) -> str | None:
    payload = message.business_payload_json if isinstance(message.business_payload_json, dict) else {}
    checkpoint_ref = payload.get("checkpoint_ref")
    return checkpoint_ref if isinstance(checkpoint_ref, str) and checkpoint_ref else None


def _fallback_checkpoint_ref(message: AgentScopeMessage) -> str:
    return f"checkpoint://{message.thread_id}/{message.message_id}/lease"


def _retry_run_question(*, session: AgentScopeSession, source_message: AgentScopeMessage) -> str:
    payload = source_message.business_payload_json if isinstance(source_message.business_payload_json, dict) else {}
    question = payload.get("question") or payload.get("original_question") or session.title or source_message.content_summary
    text = str(question or "").strip()[:500]
    if not text or _INTERNAL_RETRY_TEXT_RE.search(text):
        return "重试上一步"
    return text


def _retry_dataset_id(message: AgentScopeMessage) -> int | None:
    payload = message.business_payload_json if isinstance(message.business_payload_json, dict) else {}
    value = payload.get("dataset_id")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _ensure_checkpoint_ref(db: Session, *, message: AgentScopeMessage, checkpoint_ref: str) -> None:
    existing = (
        db.query(AgentScopeRef)
        .filter(AgentScopeRef.thread_id == message.thread_id)
        .filter(AgentScopeRef.message_id == message.message_id)
        .filter(AgentScopeRef.ref_type == "checkpoint")
        .filter(AgentScopeRef.ref_value == checkpoint_ref)
        .one_or_none()
    )
    if existing is not None:
        return
    db.add(
        AgentScopeRef(
            thread_id=message.thread_id,
            message_id=message.message_id,
            ref_type="checkpoint",
            ref_value=checkpoint_ref,
            relation="checkpoint",
        )
    )
