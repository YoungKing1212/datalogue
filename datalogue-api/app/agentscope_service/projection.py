# ============================================================
# File Name   : projection.py
# Description:
#   AgentScope Service 事件到 Datalogue Event Envelope 的投影。
#
# Responsibilities:
#   - 把 AgentScope session stream 转为 Datalogue 稳定事件协议。
#   - 清洗 SQL、schema、raw rows、DSL、query_plan 等敏感载荷。
#   - 保留 artifact_ref、checkpoint_ref 等安全引用。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from typing import Any

from app.agents.agentic_lead_agent import AgenticLeadAgent
from app.events.projection import build_task_envelope
from app.schemas.bi_workbench import DatalogueEventEnvelope, DatalogueEventType


def project_agentscope_service_event(
    event: dict[str, Any],
    *,
    task_id: str,
    trace_id: str | None,
    selected_agent: str,
    thread_id: str | None = None,
    message_id: str | None = None,
) -> DatalogueEventEnvelope:
    """将 AgentScope Service 原始事件投影为 Datalogue envelope。"""

    payload = _payload_from_event(event)
    safe_payload = AgenticLeadAgent().sanitize_output(payload)
    if not isinstance(safe_payload, dict):
        safe_payload = {"summary": str(safe_payload or "")}
    return build_task_envelope(
        event_type=_event_type(event),
        task_id=task_id,
        trace_id=trace_id,
        thread_id=thread_id,
        message_id=message_id,
        selected_agent=selected_agent,
        payload=safe_payload,
    )


def _payload_from_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if isinstance(payload, dict):
        return payload
    message = event.get("message")
    if isinstance(message, dict):
        return message
    content = event.get("content") or event.get("delta") or event.get("text")
    if content is not None:
        return {"content": content}
    return {key: value for key, value in event.items() if key not in {"event_type", "type"}}


def _event_type(event: dict[str, Any]) -> DatalogueEventType:
    raw_type = str(event.get("event_type") or event.get("type") or "").lower()
    if any(marker in raw_type for marker in ("complete", "completed", "final", "finish", "end")):
        return "message.completed"
    if "tool" in raw_type:
        return "tool.result"
    if any(marker in raw_type for marker in ("message", "delta", "token", "chunk")):
        return "message.delta"
    if "error" in raw_type or "fail" in raw_type:
        return "error.blocked"
    return "trace.updated"
