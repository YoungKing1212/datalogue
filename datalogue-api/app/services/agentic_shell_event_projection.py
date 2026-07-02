# ============================================================
# File Name   : agentic_shell_event_projection.py
# Description:
#   AgentScope 原生事件到 Datalogue 稳定事件 envelope 的投影。
#
# Responsibilities:
#   - 将 AgentScope reply_stream 事件映射为 task/agent/tool/message/ref 事件族。
#   - 只暴露工具名、状态、摘要和 refs，不泄露工具 input、SQL、schema 或 raw rows。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import json
from typing import Any

from agentscope.event import ExternalExecutionResultEvent, RequireExternalExecutionEvent
from agentscope.message import ToolResultBlock

from app.schemas.bi_workbench import (
    DatalogueEventEnvelope,
    DatalogueEventType,
    build_datalogue_event_envelope,
)


def build_task_envelope(
    *,
    event_type: DatalogueEventType,
    task_id: str,
    trace_id: str | None = None,
    thread_id: str | None = None,
    message_id: str | None = None,
    selected_agent: str | None = None,
    payload: dict[str, Any] | None = None,
    legacy_payload: dict[str, Any] | None = None,
    visibility: str = "user_visible",
) -> DatalogueEventEnvelope:
    """构造 Agentic Shell task envelope；所有用户可见载荷继续走 bi_workbench 脱敏。"""

    return build_datalogue_event_envelope(
        event_type=event_type,
        visibility=visibility,
        payload=payload or {},
        task_id=task_id,
        trace_id=trace_id,
        thread_id=thread_id,
        message_id=message_id,
        selected_agent=selected_agent,
        legacy_payload=legacy_payload or {},
    )


def project_agentscope_event(
    event: Any,
    *,
    task_id: str,
    trace_id: str | None,
    thread_id: str | None,
    message_id: str | None,
    selected_agent: str | None,
) -> DatalogueEventEnvelope:
    """把 AgentScope event 投影成 Datalogue envelope；未知事件降级为 trace.updated。"""

    if isinstance(event, RequireExternalExecutionEvent):
        return build_task_envelope(
            event_type="tool.external_required",
            task_id=task_id,
            trace_id=trace_id,
            thread_id=thread_id,
            message_id=message_id,
            selected_agent=selected_agent,
            payload={
                "summary": "AgentScope 请求执行外部工具。",
                "tool_calls": [
                    {"id": call.id, "name": call.name}
                    for call in event.tool_calls
                ],
            },
        )

    if isinstance(event, ExternalExecutionResultEvent):
        return build_task_envelope(
            event_type="tool.result",
            task_id=task_id,
            trace_id=trace_id,
            thread_id=thread_id,
            message_id=message_id,
            selected_agent=selected_agent,
            payload={
                "summary": "外部工具结果已安全回填。",
                "results": [_safe_tool_result(block) for block in event.execution_results],
            },
        )

    if isinstance(event, dict):
        parsed = _parse_legacy_sse_payload(event)
        legacy_type = parsed.get("type")
        if legacy_type == "token":
            content = str(parsed.get("content") or parsed.get("token") or "")
            return build_task_envelope(
                event_type="message.delta",
                task_id=task_id,
                trace_id=trace_id,
                thread_id=thread_id,
                message_id=message_id,
                selected_agent=selected_agent,
                payload={"content": content},
                legacy_payload=parsed,
            )
        if legacy_type == "final":
            answer = str(parsed.get("answer") or parsed.get("summary") or "")
            return build_task_envelope(
                event_type="message.completed",
                task_id=task_id,
                trace_id=parsed.get("trace_id") or trace_id,
                thread_id=parsed.get("thread_id") or thread_id,
                message_id=message_id,
                selected_agent=selected_agent,
                payload={"summary": answer or "任务已完成。"},
                legacy_payload=parsed,
            )
        event_envelope = parsed.get("event_envelope") if isinstance(parsed, dict) else None
        event_type = event_envelope.get("event_type") if isinstance(event_envelope, dict) else parsed.get("event_type")
        if isinstance(event_type, str) and event_type.startswith("retry."):
            return build_task_envelope(
                event_type=event_type,
                task_id=task_id,
                trace_id=trace_id,
                thread_id=thread_id,
                message_id=message_id,
                selected_agent=selected_agent,
                payload=parsed,
                legacy_payload=parsed,
            )

    delta = getattr(event, "delta", None)
    if isinstance(delta, str) and delta:
        return build_task_envelope(
            event_type="message.delta",
            task_id=task_id,
            trace_id=trace_id,
            thread_id=thread_id,
            message_id=message_id,
            selected_agent=selected_agent,
            payload={"content": delta},
            legacy_payload={"type": "token", "content": delta},
        )

    return build_task_envelope(
        event_type="trace.updated",
        task_id=task_id,
        trace_id=trace_id,
        thread_id=thread_id,
        message_id=message_id,
        selected_agent=selected_agent,
        payload={"summary": event.__class__.__name__},
        visibility="trace_only",
    )


def _parse_legacy_sse_payload(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data") if isinstance(event, dict) else None
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, dict) else {"summary": str(parsed)}
        except json.JSONDecodeError:
            return {"summary": data[:300]}
    return event


def _safe_tool_result(block: ToolResultBlock) -> dict[str, Any]:
    state = getattr(block.state, "value", str(block.state)).lower()
    output_summary = "工具执行完成。"
    output = block.output
    output_items = output if isinstance(output, list) else [output]
    for item in output_items:
        text = getattr(item, "text", None) if not isinstance(item, str) else item
        if isinstance(text, str) and text.strip():
            output_summary = text.strip()[:300]
            break
    return {
        "id": block.id,
        "name": block.name,
        "state": state,
        "summary": output_summary,
    }
