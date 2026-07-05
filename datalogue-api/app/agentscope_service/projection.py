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

from app.events.projection import build_task_envelope
from app.schemas.bi_workbench import DatalogueEventEnvelope, DatalogueEventType, sanitize_event_payload


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
    safe_payload = sanitize_event_payload(payload)
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
    if _is_subagent_hitl_require_event(event):
        return _subagent_hitl_confirmation_payload(event.get("value") or {})
    if _is_subagent_hitl_result_event(event):
        value = event.get("value") if isinstance(event.get("value"), dict) else {}
        worker_name = _safe_text(value.get("worker_agent_name") or value.get("worker_agent_id"), "worker")
        return {
            "summary": f"{worker_name} 的工具确认已处理。",
            "agent": worker_name,
            "worker_session_id": _safe_text(value.get("worker_session_id")),
            "reply_id": _safe_text(value.get("reply_id")),
        }
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
    if _is_subagent_hitl_require_event(event):
        return "confirmation.required"
    raw_type = str(event.get("event_type") or event.get("type") or "").lower()
    # AgentScope 原生事件里 TextBlockEnd/ThinkingBlockEnd/ModelCallEnd 只是分段结束；
    # 只有 ReplyEnd/final/finish 才代表本轮助手回复完成，避免重复投成 message.completed。
    if any(marker in raw_type for marker in ("replyendevent", "reply.end", "reply_end", "final", "finish")):
        return "message.completed"
    if "tool" in raw_type:
        return "tool.result"
    if any(marker in raw_type for marker in ("message", "delta", "token", "chunk")):
        return "message.delta"
    if "error" in raw_type or "fail" in raw_type:
        return "error.blocked"
    return "trace.updated"


def _is_subagent_hitl_require_event(event: dict[str, Any]) -> bool:
    return str(event.get("name") or "") == "subagent_require_user_confirm"


def _is_subagent_hitl_result_event(event: dict[str, Any]) -> bool:
    return str(event.get("name") or "") == "subagent_user_confirm_result"


def _subagent_hitl_confirmation_payload(value: dict[str, Any]) -> dict[str, Any]:
    """把 AgentScope worker HITL mirror 事件转成用户可见确认摘要，严禁透出 tool input。"""

    worker_name = _safe_text(value.get("worker_agent_name") or value.get("worker_agent_id"), "worker")
    event_payload = value.get("event") if isinstance(value.get("event"), dict) else {}
    tool_calls = _safe_tool_calls(event_payload.get("tool_calls"))
    first_tool = tool_calls[0] if tool_calls else {}
    tool_name = _safe_text(first_tool.get("name"), "工具")
    return {
        "summary": f"{worker_name} 正在等待确认工具调用 {tool_name}。",
        "title": "Worker 需要确认",
        "agent": worker_name,
        "agent_name": worker_name,
        "worker_session_id": _safe_text(value.get("worker_session_id")),
        "worker_agent_id": _safe_text(value.get("worker_agent_id")),
        "reply_id": _safe_text(value.get("reply_id")),
        "tool_name": tool_name,
        "tool_call_id": _safe_text(first_tool.get("id")),
        "tool_calls": tool_calls,
        "requires_user_confirmation": True,
        "confirmation_kind": _safe_text(value.get("event_type"), "require_user_confirm"),
    }


def _safe_tool_calls(tool_calls: Any) -> list[dict[str, str]]:
    if not isinstance(tool_calls, list):
        return []
    safe_calls: list[dict[str, str]] = []
    for item in tool_calls[:8]:
        if not isinstance(item, dict):
            continue
        safe_call = {
            "id": _safe_text(item.get("id")),
            "name": _safe_text(item.get("name"), "工具"),
            "state": _safe_text(item.get("state")),
        }
        safe_calls.append({key: value for key, value in safe_call.items() if value})
    return safe_calls


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return (text or fallback)[:160]
