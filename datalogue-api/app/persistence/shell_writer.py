# ============================================================
# File Name   : shell_writer.py
# Description:
#   AgenticLeadAgent 写回 Workbench 和 AgentScope mirror 的持久化适配器。
#
# Responsibilities:
#   - 将 Shell event/action/checkpoint 写回契约桥接到 AgentScope mirror。
#   - 复用既有 Chat bridge event projection，避免重复实现 Workbench 事件映射。
#   - 保证写回前仍经过 Shell payload sanitizer，阻断内部执行载荷。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.agentic_lead_agent import AgenticShellWriteRecord
from app.schemas.bi_workbench import build_datalogue_event_envelope
from app.services.agentscope_chat_bridge import AgentScopeChatBridgeContext, record_stream_event
from app.services.agentscope_mirror import record_agentscope_event


class AgentScopeMirrorShellWriter:
    """把 AgenticLeadAgent 写回记录投影到 AgentScope mirror；不直接执行 BI 查询。"""

    writer_name = "agentscope_mirror"

    def __init__(
        self,
        db: Session,
        *,
        thread_id: str,
        message_id: str | None = None,
        chat_context: AgentScopeChatBridgeContext | None = None,
    ) -> None:
        self.db = db
        self.thread_id = thread_id
        self.message_id = message_id
        self.chat_context = chat_context

    def write(self, record: AgenticShellWriteRecord) -> AgenticShellWriteRecord:
        if record.write_kind == "event" and record.event_type:
            self._write_event(record)
            return record.model_copy(update={"writer_name": self.writer_name, "persisted": True})
        if record.write_kind == "action" and record.action_id:
            self._write_action(record)
            return record.model_copy(update={"writer_name": self.writer_name, "persisted": True})
        return record.model_copy(update={"writer_name": self.writer_name, "persisted": False})

    def _write_event(self, record: AgenticShellWriteRecord) -> None:
        payload, meta = self._split_event_payload(record.payload)
        if self.chat_context is not None:
            envelope = build_datalogue_event_envelope(
                event_type=record.event_type,  # type: ignore[arg-type]
                visibility=meta["visibility"],  # type: ignore[arg-type]
                payload=payload,
                task_id=meta.get("task_id"),
                trace_id=meta.get("trace_id"),
                conversation_id=meta.get("conversation_id"),
            )
            record_stream_event(self.db, context=self.chat_context, envelope=envelope)
            return
        record_agentscope_event(
            self.db,
            thread_id=self.thread_id,
            message_id=record.message_id or self.message_id,
            event_type=record.event_type,
            payload=payload,
            visibility=str(meta["visibility"]),
            task_id=meta.get("task_id"),
            trace_id=meta.get("trace_id"),
        )

    def _write_action(self, record: AgenticShellWriteRecord) -> None:
        payload = dict(record.payload or {})
        # Workbench retry action 进入 Shell 后仍落为既有 observability contract 事件名，避免前端时间线断裂。
        event_type = "workbench.retry_requested" if record.action_id == "retry_last_step" else record.action_id
        record_agentscope_event(
            self.db,
            thread_id=self.thread_id,
            message_id=record.message_id or self.message_id,
            event_type=event_type,
            payload=payload,
            visibility="user",
            task_id=None,
            trace_id=None,
        )

    @staticmethod
    def _split_event_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        body = dict(payload or {})
        visibility = body.pop("event_visibility", "user_visible")
        meta = {
            "visibility": visibility,
            "task_id": body.pop("event_task_id", None),
            "trace_id": body.pop("event_trace_id", None),
            "conversation_id": body.pop("event_conversation_id", None),
        }
        return body, meta
