# ============================================================
# File Name   : agentscope_mirror.py
# Description:
#   AgentScope 工作台本地镜像写入服务。
#
# Responsibilities:
#   - 为 C3 新会话写入 session/message/event/ref 镜像记录。
#   - 提供 assistant running lease 查询和消息状态收口能力。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from datetime import datetime, timedelta, timezone
import re
import uuid

from sqlalchemy.orm import Session

from app.models.agentscope_workbench import (
    AgentScopeEvent,
    AgentScopeMessage,
    AgentScopeRef,
    AgentScopeSession,
)
from app.runtime.thread_resolver import new_agentscope_thread_id, normalize_thread_id
from app.schemas.agentscope_workbench import AgentScopeMessageStatus

_FORBIDDEN_KEY_FRAGMENTS = (
    "sql",
    "schema",
    "raw",
    "row",
    "rows",
    "record",
    "records",
    "result",
    "query_plan",
    "field_patch",
    "repair_patch",
    "repairpatch",
    "patch_body",
    "patchbody",
    "blueprint_body",
    "blueprintbody",
    "table_name",
    "column_name",
)
_SQL_TEXT_RE = re.compile(
    r"\b(select|insert|update|delete|with)\b[\s\S]{0,120}\b(from|into|set)\b", re.IGNORECASE
)
_INTERNAL_TEXT_RE = re.compile(
    r"(\b(select|insert|update|delete|with)\b[\s\S]{0,120}\b(from|into|set)\b)"
    r"|(\b(psycopg2|sqlalchemy|traceback|undefinedcolumn|undefinedtable|programmingerror|operationalerror)\b)"
    r"|(\b(column|table|relation)\s+['\"]?[\w.]+['\"]?\s+(does not exist|not found))",
    re.IGNORECASE,
)
_TERMINAL_MESSAGE_STATUSES = {
    AgentScopeMessageStatus.COMPLETED.value,
    AgentScopeMessageStatus.FAILED.value,
    AgentScopeMessageStatus.INTERRUPTED.value,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _message_id() -> str:
    return f"msg_{uuid.uuid4().hex}"


def _event_id() -> str:
    return f"evt_{uuid.uuid4().hex}"


def _require_agentscope_thread(thread_id: str) -> str:
    normalized = normalize_thread_id(thread_id)
    if normalized is None or not normalized.startswith("as_"):
        raise ValueError("AGENTSCOPE_MIRROR_REQUIRES_AS_THREAD")
    return normalized


def _sanitize_business_payload(payload: dict | None) -> dict:
    payload = payload or {}
    _scan_forbidden_payload_keys(payload)
    return payload


def _safe_content_summary(summary: str | None, *, fallback: str) -> str:
    text = (summary or "").strip()
    if not text:
        return fallback
    if _INTERNAL_TEXT_RE.search(text):
        return fallback
    try:
        _scan_forbidden_payload_keys(text)
    except ValueError:
        return fallback  # message summary 未来会进入 Workbench 可见层，疑似内部细节时用业务级兜底文案。
    return text


def _scan_forbidden_payload_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise ValueError("AGENTSCOPE_MIRROR_PAYLOAD_LEAK_DETECTED")
            _scan_forbidden_payload_keys(nested)
    elif isinstance(value, list):
        for item in value:
            _scan_forbidden_payload_keys(item)
    elif isinstance(value, str) and (_SQL_TEXT_RE.search(value) or _INTERNAL_TEXT_RE.search(value)):
        raise ValueError("AGENTSCOPE_MIRROR_PAYLOAD_LEAK_DETECTED")


def create_agentscope_session(
    db: Session,
    *,
    thread_id: str | None,
    title: str | None,
    legacy_conversation_id: int | None = None,
    metadata: dict | None = None,
) -> AgentScopeSession:
    normalized = normalize_thread_id(thread_id) if thread_id else new_agentscope_thread_id()
    if normalized is None or not normalized.startswith("as_"):
        raise ValueError("AGENTSCOPE_SESSION_REQUIRES_AS_THREAD")

    existing = (
        db.query(AgentScopeSession).filter(AgentScopeSession.thread_id == normalized).one_or_none()
    )
    if existing:
        changed = False
        if legacy_conversation_id is not None and existing.legacy_conversation_id is None:
            existing.legacy_conversation_id = legacy_conversation_id
            changed = True
        if metadata:
            existing_metadata = dict(existing.metadata_json or {})
            for key, value in _sanitize_business_payload(metadata).items():
                if value is not None and existing_metadata.get(key) != value:
                    existing_metadata[key] = value
                    changed = True
            existing.metadata_json = existing_metadata
        if changed:
            db.commit()
            db.refresh(existing)
        return existing  # as_* 是 C3 新会话真相源，重复 begin turn 时复用同一 session。

    session = AgentScopeSession(
        thread_id=normalized,
        source_type="agentscope",
        legacy_conversation_id=legacy_conversation_id,
        title=title,
        status="active",
        metadata_json=_sanitize_business_payload(metadata),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def append_user_message(
    db: Session,
    *,
    thread_id: str,
    content_summary: str,
    payload: dict,
) -> AgentScopeMessage:
    message = AgentScopeMessage(
        message_id=_message_id(),
        thread_id=_require_agentscope_thread(thread_id),
        role="user",
        status=AgentScopeMessageStatus.COMPLETED.value,
        content_summary=content_summary,
        business_payload_json=_sanitize_business_payload(
            payload
        ),  # mirror 层兜底阻断内部执行细节落库。
        completed_at=_utcnow(),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def create_running_assistant_message(
    db: Session, *, thread_id: str, lease_seconds: int
) -> AgentScopeMessage:
    now = _utcnow()
    message = AgentScopeMessage(
        message_id=_message_id(),
        thread_id=_require_agentscope_thread(thread_id),
        role="assistant",
        status=AgentScopeMessageStatus.RUNNING.value,
        business_payload_json={},
        lease_expires_at=now + timedelta(seconds=lease_seconds),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def mark_message_completed(
    db: Session,
    *,
    message_id: str,
    content_summary: str,
    payload: dict,
) -> AgentScopeMessage:
    message = _get_message(db, message_id)
    if message.status in _TERMINAL_MESSAGE_STATUSES:
        return message  # SSE finally 可能二次收口；终态不可被后续 complete/fail 覆盖。
    message.status = AgentScopeMessageStatus.COMPLETED.value
    message.content_summary = _safe_content_summary(
        content_summary,
        fallback="查询已完成，结果请通过引用查看。",
    )
    message.business_payload_json = _sanitize_business_payload(payload)
    message.completed_at = _utcnow()
    message.lease_expires_at = None  # 完成态释放 lease，避免后续 recovery 误判。
    db.commit()
    db.refresh(message)
    return message


def mark_message_failed(
    db: Session,
    *,
    message_id: str,
    error_summary: str,
    payload: dict,
) -> AgentScopeMessage:
    message = _get_message(db, message_id)
    if message.status in _TERMINAL_MESSAGE_STATUSES:
        return message  # complete 后的异常清理不能把成功 final 覆盖成 failed。
    message.status = AgentScopeMessageStatus.FAILED.value
    message.content_summary = _safe_content_summary(
        error_summary,
        fallback="问数执行失败，内部细节已隐藏。",
    )
    message.business_payload_json = _sanitize_business_payload(payload)
    message.completed_at = _utcnow()
    message.lease_expires_at = (
        None  # 失败态只能通过 checkpoint/ref 受控 retry，不保留 running lease。
    )
    db.commit()
    db.refresh(message)
    return message


def mark_message_interrupted(db: Session, *, message_id: str, reason: str) -> AgentScopeMessage:
    message = _get_message(db, message_id)
    if message.status in _TERMINAL_MESSAGE_STATUSES:
        return message
    message.status = AgentScopeMessageStatus.INTERRUPTED.value
    message.content_summary = _safe_content_summary(
        reason,
        fallback="问数链路已中断，内部细节已隐藏。",
    )
    message.completed_at = _utcnow()
    message.lease_expires_at = None
    db.commit()
    db.refresh(message)
    return message


def record_agentscope_event(
    db: Session,
    *,
    thread_id: str,
    message_id: str | None,
    event_type: str,
    payload: dict,
    visibility: str,
    task_id: str | None,
    trace_id: str | None,
) -> AgentScopeEvent:
    event = AgentScopeEvent(
        event_id=_event_id(),
        thread_id=_require_agentscope_thread(thread_id),
        message_id=message_id,
        event_type=event_type,
        task_id=task_id,
        trace_id=trace_id,
        payload_json=_sanitize_business_payload(
            payload
        ),  # event 是 Workbench 产品素材，字段级调试细节不应写入 user visibility。
        visibility=visibility,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def record_agentscope_ref(
    db: Session,
    *,
    thread_id: str,
    message_id: str | None,
    ref_type: str,
    ref_value: str,
    relation: str,
) -> AgentScopeRef:
    normalized_thread_id = _require_agentscope_thread(thread_id)
    existing = (
        db.query(AgentScopeRef)
        .filter(AgentScopeRef.thread_id == normalized_thread_id)
        .filter(
            AgentScopeRef.message_id.is_(None)
            if message_id is None
            else AgentScopeRef.message_id == message_id
        )
        .filter(AgentScopeRef.ref_type == ref_type)
        .filter(AgentScopeRef.ref_value == ref_value)
        .filter(AgentScopeRef.relation == relation)
        .one_or_none()
    )
    if existing is not None:
        raise ValueError(
            "AGENTSCOPE_REF_ALREADY_EXISTS"
        )  # DB 唯一约束覆盖非空 message_id；None 场景由服务层兜底。
    ref = AgentScopeRef(
        thread_id=normalized_thread_id,
        message_id=message_id,
        ref_type=ref_type,
        ref_value=ref_value,
        relation=relation,
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)
    return ref


def find_expired_running_messages(db: Session, *, now: datetime) -> list[AgentScopeMessage]:
    return (
        db.query(AgentScopeMessage)
        .filter(AgentScopeMessage.status == AgentScopeMessageStatus.RUNNING.value)
        .filter(AgentScopeMessage.lease_expires_at.isnot(None))
        .filter(AgentScopeMessage.lease_expires_at <= now)
        .order_by(AgentScopeMessage.lease_expires_at.asc(), AgentScopeMessage.id.asc())
        .all()
    )


def update_session_title(db: Session, *, thread_id: str, title: str) -> None:
    """更新 AgentScope 工作台会话标题。"""
    session = (
        db.query(AgentScopeSession).filter(AgentScopeSession.thread_id == thread_id).one_or_none()
    )
    if session and (session.title is None or session.title == "" or len(session.title) <= 80):
        session.title = title[:200]
        db.commit()


def _get_message(db: Session, message_id: str) -> AgentScopeMessage:
    message = (
        db.query(AgentScopeMessage).filter(AgentScopeMessage.message_id == message_id).one_or_none()
    )
    if message is None:
        raise ValueError("AGENTSCOPE_MESSAGE_NOT_FOUND")
    return message
