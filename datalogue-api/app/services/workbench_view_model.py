# ============================================================
# File Name   : workbench_view_model.py
# Description:
#   C3 Workbench 后端视图模型构建服务。
#
# Responsibilities:
#   - 将 AgentScope mirror 会话转换成 Chat 详情面板可用的业务级视图。
#   - 将旧 conversation 以 conv_* 形式只读回放，不迁移、不补造新产物卡。
#   - 读取 artifact:<uuid> 时只返回脱敏摘要，避免原始结果和执行面细节进入工作台。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from __future__ import annotations

import re
from typing import Any, cast

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.models import (
    AgentScopeEvent,
    AgentScopeMessage,
    AgentScopeRef,
    AgentScopeSession,
    Conversation,
    Message,
)
from app.schemas.agentscope_workbench import (
    WorkbenchActionView,
    WorkbenchArtifactView,
    WorkbenchMessageView,
    WorkbenchStatusSummary,
    WorkbenchThreadView,
    WorkbenchTimelineItem,
)
from app.domains.query_execution.artifact_store import ArtifactStore
from app.domains.query_execution.repair_plan import sanitize_repair_plan_artifact_payload


class WorkbenchViewNotFoundError(LookupError):
    """工作台视图资源不存在；API 层统一映射为 404。"""


_FORBIDDEN_OUTPUT_KEYS = {
    "sql",
    "raw_sql",
    "llm_sql",
    "direct_sql",
    "query_sql",
    "schema",
    "schema_context",
    "raw_result",
    "raw_rows",
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
    "columns",
    "rows",
    "content_json",
    "content_text",
    "control_plane",
}
_SQL_TEXT_RE = re.compile(
    r"(?is)\b(select|insert|update|delete|drop|alter|create|with)\b"
    r".{0,200}\b(from|into|set|table|join|where|values)\b"
)
_INTERNAL_TEXT_RE = re.compile(
    r"(?is)\b(psycopg2|sqlalchemy|traceback|undefinedcolumn|undefinedtable|programmingerror|operationalerror)\b"
)


def sanitize_workbench_view_payload(payload: Any) -> Any:
    """扫描工作台最终输出；命中执行面字段名或 SQL 文本时 fail-closed。"""

    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key).lower()
            if key_text in _FORBIDDEN_OUTPUT_KEYS or "sql" in key_text:
                raise ValueError("WORKBENCH_VIEW_PAYLOAD_LEAK_DETECTED")
            sanitize_workbench_view_payload(value)
        return payload
    if isinstance(payload, list):
        for item in payload:
            sanitize_workbench_view_payload(item)
        return payload
    if isinstance(payload, str):
        if _SQL_TEXT_RE.search(payload) or _INTERNAL_TEXT_RE.search(payload):
            raise ValueError("WORKBENCH_VIEW_PAYLOAD_LEAK_DETECTED")
    return payload


def build_workbench_thread_view(db: Session, *, thread_id: str) -> WorkbenchThreadView:
    """按线程 id 构建工作台视图；as_* 走 AgentScope mirror，conv_* 走旧会话只读回放。"""

    normalized = (thread_id or "").strip()
    if normalized.startswith("conv_"):
        return build_legacy_conversation_view(db, legacy_conversation_id=_parse_legacy_conversation_id(normalized))
    if not normalized.startswith("as_"):
        raise WorkbenchViewNotFoundError("workbench thread not found")

    session = db.query(AgentScopeSession).filter(AgentScopeSession.thread_id == normalized).one_or_none()
    if session is None:
        raise WorkbenchViewNotFoundError("workbench thread not found")

    messages = (
        db.query(AgentScopeMessage)
        .filter(AgentScopeMessage.thread_id == session.thread_id)
        .order_by(AgentScopeMessage.created_at.asc(), AgentScopeMessage.id.asc())
        .all()
    )
    events = (
        db.query(AgentScopeEvent)
        .filter(AgentScopeEvent.thread_id == session.thread_id)
        .filter(AgentScopeEvent.visibility == "user")
        .order_by(AgentScopeEvent.created_at.asc(), AgentScopeEvent.id.asc())
        .all()
    )
    refs = (
        db.query(AgentScopeRef)
        .filter(AgentScopeRef.thread_id == session.thread_id)
        .order_by(AgentScopeRef.created_at.asc(), AgentScopeRef.id.asc())
        .all()
    )
    primary_ref = _select_primary_artifact_ref(refs)
    related_refs = [_ref_to_view(ref) for ref in refs if not (ref.relation == "primary" and ref.ref_value == primary_ref)]
    available_actions = _build_agentscope_actions(messages, refs)
    view = WorkbenchThreadView(
        thread_id=session.thread_id,
        read_only=False,
        messages=[_agentscope_message_to_view(message) for message in messages],
        timeline=[_event_to_timeline_item(event) for event in events],
        primary_artifact_ref=primary_ref,
        related_refs=related_refs,
        available_actions=available_actions,
        legacy_notice=None,
        status_summary=_build_agentscope_status_summary(
            messages=messages,
            refs=refs,
            primary_artifact_ref=primary_ref,
            actions=available_actions,
        ),
    )
    return _validated_thread_view(view)


def build_legacy_conversation_view(db: Session, *, legacy_conversation_id: int) -> WorkbenchThreadView:
    """构建旧会话只读视图；不做数据迁移，也不把旧 result_ref/report_ref 伪造成 ArtifactCard。"""

    conversation = db.query(Conversation).filter(Conversation.id == legacy_conversation_id).one_or_none()
    if conversation is None:
        raise WorkbenchViewNotFoundError("legacy conversation not found")
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    primary_ref, related_refs = _extract_existing_artifact_card_refs(messages)
    view = WorkbenchThreadView(
        thread_id=f"conv_{conversation.id}",
        read_only=True,
        messages=[_legacy_message_to_view(message) for message in messages],
        timeline=[],
        primary_artifact_ref=primary_ref,
        related_refs=related_refs,
        available_actions=[],
        legacy_notice="旧会话以只读方式展示；不会迁移、回填或伪造 Workbench 产物卡。",
        status_summary=_build_legacy_status_summary(
            messages=messages,
            primary_artifact_ref=primary_ref,
        ),
    )
    return _validated_thread_view(view)


def build_workbench_artifact_view(
    db: Session,
    *,
    artifact_ref: str,
    thread_id: str | None = None,
) -> WorkbenchArtifactView:
    """读取 artifact 工作台摘要；只接受 artifact:<uuid> 句柄，其他 ref 统一 fail-closed。"""

    if not artifact_ref or not artifact_ref.startswith("artifact:"):
        raise WorkbenchViewNotFoundError("artifact not found")
    if thread_id and not _thread_owns_artifact_ref(db, thread_id=thread_id, artifact_ref=artifact_ref):
        raise WorkbenchViewNotFoundError("artifact not found")
    artifact = ArtifactStore(db).get(artifact_ref)
    if artifact is None:
        raise WorkbenchViewNotFoundError("artifact not found")

    preview_payload = _artifact_preview_payload(artifact.kind, artifact.content_json, artifact.content_text)
    view = WorkbenchArtifactView(
        artifact_ref=artifact.artifact_id,
        kind=_public_artifact_kind(artifact.kind),
        dataset_id=artifact.dataset_id,
        conversation_id=artifact.conversation_id,
        message_id=artifact.message_id,
        trace_id=artifact.trace_id,
        content_mime=artifact.content_mime,
        preview_payload=preview_payload,
        related_refs=_artifact_related_refs(artifact.trace_id),
        expires_at=artifact.expires_at,
    )
    encoded = cast(dict[str, Any], jsonable_encoder(view.model_dump()))
    sanitize_workbench_view_payload(encoded)
    return view


def _thread_owns_artifact_ref(db: Session, *, thread_id: str, artifact_ref: str) -> bool:
    normalized = (thread_id or "").strip()
    if normalized.startswith("as_"):
        return (
            db.query(AgentScopeRef)
            .filter(AgentScopeRef.thread_id == normalized)
            # Workbench 对外统一使用 artifact:<uuid> 句柄；内部 ref_type 仍保留 result/report 等业务语义。
            # 因此归属校验必须按 ref_value 精确匹配，而不是要求 ref_type 固定为 artifact。
            .filter(AgentScopeRef.ref_value == artifact_ref)
            .first()
            is not None
        )
    if normalized.startswith("conv_"):
        legacy_view = build_legacy_conversation_view(db, legacy_conversation_id=_parse_legacy_conversation_id(normalized))
        if legacy_view.primary_artifact_ref == artifact_ref:
            return True
        return any(ref.get("ref") == artifact_ref for ref in legacy_view.related_refs)
    return False


def _validated_thread_view(view: WorkbenchThreadView) -> WorkbenchThreadView:
    encoded = cast(dict[str, Any], jsonable_encoder(view.model_dump()))
    sanitize_workbench_view_payload(encoded)
    return view


def _parse_legacy_conversation_id(thread_id: str) -> int:
    try:
        return int(thread_id.removeprefix("conv_"))
    except (TypeError, ValueError) as exc:
        raise WorkbenchViewNotFoundError("legacy conversation not found") from exc


def _agentscope_message_to_view(message: AgentScopeMessage) -> WorkbenchMessageView:
    return WorkbenchMessageView(
        message_id=message.message_id,
        role=message.role,
        status=message.status,
        content_summary=_safe_text(message.content_summary, fallback="消息摘要已隐藏。"),
        payload=_safe_payload(message.business_payload_json),
        created_at=message.created_at,
        completed_at=message.completed_at,
    )


def _legacy_message_to_view(message: Message) -> WorkbenchMessageView:
    return WorkbenchMessageView(
        message_id=f"conv_msg_{message.id}",
        role=message.role,
        status="completed",
        content_summary=_safe_text(message.content, fallback="历史消息摘要已隐藏。"),
        payload={},
        created_at=message.created_at,
        completed_at=None,
    )


def _event_to_timeline_item(event: AgentScopeEvent) -> WorkbenchTimelineItem:
    payload = _safe_payload(event.payload_json)
    return WorkbenchTimelineItem(
        event_id=event.event_id,
        event_type=event.event_type,
        message_id=event.message_id,
        task_id=event.task_id,
        trace_id=event.trace_id,
        summary=_safe_text(payload.get("summary") if isinstance(payload, dict) else None, fallback=None),
        payload=payload,
        created_at=event.created_at,
    )


def _select_primary_artifact_ref(refs: list[AgentScopeRef]) -> str | None:
    for ref in refs:
        if ref.relation == "primary" and str(ref.ref_value).startswith("artifact:"):
            return ref.ref_value
    return None


def _ref_to_view(ref: AgentScopeRef) -> dict[str, Any]:
    return {
        "ref_type": ref.ref_type,
        "ref": ref.ref_value,
        "relation": ref.relation,
    }


def _latest_assistant_message(messages: list[AgentScopeMessage]) -> AgentScopeMessage | None:
    return next((message for message in reversed(messages) if message.role == "assistant"), None)


def _checkpoint_ref_for_message(refs: list[AgentScopeRef], message_id: str | None) -> str | None:
    if not message_id:
        return None
    for ref in reversed(refs):
        if ref.message_id == message_id and ref.ref_type == "checkpoint" and str(ref.ref_value).startswith(("checkpoint://", "checkpoint:")):
            return ref.ref_value
    return None


def _trace_ref_from_refs(refs: list[AgentScopeRef]) -> str | None:
    for ref in reversed(refs):
        if ref.ref_type == "trace" and ref.ref_value:
            value = str(ref.ref_value)
            return value if value.startswith("trace:") else f"trace:{value}"
    return None


def _build_agentscope_status_summary(
    *,
    messages: list[AgentScopeMessage],
    refs: list[AgentScopeRef],
    primary_artifact_ref: str | None,
    actions: list[WorkbenchActionView],
) -> WorkbenchStatusSummary:
    """生成线程级产品态；前端只按该摘要渲染，不推断内部执行状态。"""

    latest = _latest_assistant_message(messages)
    if latest is None:
        return WorkbenchStatusSummary(
            status="empty",
            label="等待问数",
            tone="neutral",
            actionable=False,
            read_only=False,
            primary_artifact_ref=primary_artifact_ref,
            trace_ref=_trace_ref_from_refs(refs),
            summary="当前线程还没有可展示的 BI 结果。",
        )

    checkpoint_ref = _checkpoint_ref_for_message(refs, latest.message_id)
    retry_action = next((action for action in actions if action.action_id == "retry"), None)
    actionable = bool(retry_action and retry_action.enabled)
    labels = {
        "running": ("执行中", "pending"),
        "completed": ("已完成", "success"),
        "failed": ("执行失败", "warning"),
        "interrupted": ("已中断", "warning"),
        "created": ("已创建", "neutral"),
    }
    label, tone = labels.get(str(latest.status), ("处理中", "neutral"))
    return WorkbenchStatusSummary(
        status=str(latest.status),
        label=label,
        tone=tone,
        actionable=actionable,
        read_only=False,
        latest_message_id=latest.message_id,
        primary_artifact_ref=primary_artifact_ref,
        retry_checkpoint_ref=checkpoint_ref if actionable else None,
        trace_ref=_trace_ref_from_refs(refs),
        summary=_safe_text(latest.content_summary, fallback=label),
    )


def _build_legacy_status_summary(
    *,
    messages: list[Message],
    primary_artifact_ref: str | None,
) -> WorkbenchStatusSummary:
    latest = messages[-1] if messages else None
    return WorkbenchStatusSummary(
        status="read_only",
        label="只读回放",
        tone="neutral",
        actionable=False,
        read_only=True,
        latest_message_id=f"conv_msg_{latest.id}" if latest is not None else None,
        primary_artifact_ref=primary_artifact_ref,
        summary="旧会话以只读方式展示，不会迁移、回填或发起 Workbench 重试。",
    )


def _build_agentscope_actions(messages: list[AgentScopeMessage], refs: list[AgentScopeRef]) -> list[WorkbenchActionView]:
    latest_terminal = next(
        (
            message
            for message in reversed(messages)
            if message.role == "assistant" and message.status in {"failed", "interrupted", "completed"}
        ),
        None,
    )
    checkpoint_ref = _checkpoint_ref_for_message(refs, latest_terminal.message_id if latest_terminal is not None else None)
    retryable = bool(latest_terminal and latest_terminal.status in {"failed", "interrupted"} and checkpoint_ref)
    # View Model 只声明动作可见性；真实重跑交给 Workbench action 和 Chat checkpoint 主链。
    return [
        WorkbenchActionView(
            action_id="retry",
            label="重试",
            enabled=retryable,
            disabled_reason=None
            if retryable
            else ("当前消息缺少可用检查点。" if latest_terminal and latest_terminal.status in {"failed", "interrupted"} else "当前消息不需要重试。"),
            checkpoint_ref=checkpoint_ref,
            message_id=latest_terminal.message_id if latest_terminal is not None else None,
        )
    ]


def _extract_existing_artifact_card_refs(messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
    for message in reversed(messages):
        metadata = message.response_metadata if isinstance(message.response_metadata, dict) else {}
        artifact_card = metadata.get("artifact_card")
        if not isinstance(artifact_card, dict):
            continue
        primary = metadata.get("primary_ref") if isinstance(metadata.get("primary_ref"), dict) else artifact_card.get("primary_ref")
        primary_ref = primary.get("ref_id") if isinstance(primary, dict) and str(primary.get("ref_id", "")).startswith("artifact:") else None
        raw_related = metadata.get("related_refs") or artifact_card.get("related_refs") or []
        related_refs = [_legacy_ref_to_view(ref) for ref in raw_related if isinstance(ref, dict)]
        return primary_ref, related_refs
    return None, []


def _legacy_ref_to_view(ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref_type": str(ref.get("ref_type") or "artifact"),
        "ref": str(ref.get("ref_id") or ""),
        "relation": str(ref.get("relation") or ref.get("ref_type") or "related"),
    }


def _artifact_preview_payload(kind: str, content_json: Any, content_text: str | None) -> dict[str, Any]:
    if kind == "repair_plan":
        safe = sanitize_repair_plan_artifact_payload(content_json)
        summary = _safe_text(safe.get("business_summary"), fallback="修复方案摘要已生成。")
        return {
            key: value
            for key, value in {
                "failure_class": safe.get("failure_class"),
                "status": safe.get("status"),
                "summary": summary,
                "attempts": safe.get("attempts"),
                "requires_user_confirmation": safe.get("requires_user_confirmation"),
                "repair_plan_ref": safe.get("repair_plan_ref"),
                "checkpoint_ref": safe.get("checkpoint_ref"),
                "trace_ref": safe.get("trace_ref"),
            }.items()
            if value is not None
        }
    if isinstance(content_json, dict):
        return {"summary": _safe_text(content_json.get("summary"), fallback="查询产物已生成。")}
    return {"summary": _safe_text(content_text, fallback="查询产物已生成。")}


def _artifact_related_refs(trace_id: str | None) -> list[dict[str, Any]]:
    if not trace_id:
        return []
    trace_ref = trace_id if str(trace_id).startswith("trace:") else f"trace:{trace_id}"
    return [{"ref_type": "trace", "ref": trace_ref, "relation": "trace"}]


def _public_artifact_kind(kind: str) -> str:
    if kind == "sql_result":
        return "query_result"
    return kind


def _safe_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    encoded = cast(dict[str, Any], jsonable_encoder(payload))
    sanitize_workbench_view_payload(encoded)
    return encoded


def _safe_text(value: Any, *, fallback: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return fallback
    if _SQL_TEXT_RE.search(text) or _INTERNAL_TEXT_RE.search(text):
        return fallback
    return text[:500]
