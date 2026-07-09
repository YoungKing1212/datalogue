# ============================================================
# File Name   : projection.py
# Description:
#   AgentScope 与 Datalogue 稳定事件协议之间的投影层。
#
# Responsibilities:
#   - 将 AgentScope reply_stream 事件映射为 task/agent/tool/message/ref 事件族。
#   - 将 Datalogue event envelope 写入 AgentScope Workbench mirror 事件。
#   - 只暴露工具名、状态、摘要和 refs，不泄露工具 input、SQL、schema 或 raw rows。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import json
import re
from typing import Any

from agentscope.event import ExternalExecutionResultEvent, RequireExternalExecutionEvent
from agentscope.message import ToolResultBlock
from sqlalchemy.orm import Session

from app.core.models.agentscope_workbench import AgentScopeEvent
from app.core.schemas.bi_workbench import (
    DatalogueEventEnvelope,
    DatalogueEventType,
    build_datalogue_event_envelope,
)
from app.services.agentscope_mirror import record_agentscope_event, record_agentscope_ref


USER_VISIBLE_EVENT_TYPES = {
    "task.started",
    "route.started",
    "dataset.candidates",
    "dataset.selected",
    "dataset.query.started",
    "dataset.query.completed",
    "repair.evaluated",
    "repair.plan_created",
    "repair.patch_applied",
    "repair.rerun_started",
    "repair.rerun_completed",
    "artifact.created",
    "answer.completed",
    "error",
    "error.blocked",
}
_FORBIDDEN_KEY_FRAGMENTS = ("sql", "schema", "raw", "row", "record", "result", "query_plan", "field_patch")
_SQL_TEXT_RE = re.compile(r"\b(select|insert|update|delete|with)\b[\s\S]{0,120}\b(from|into|set)\b", re.IGNORECASE)
_INTERNAL_TEXT_RE = re.compile(
    r"(\b(select|insert|update|delete|with)\b[\s\S]{0,120}\b(from|into|set)\b)"
    r"|(\b(psycopg2|sqlalchemy|traceback|undefinedcolumn|undefinedtable|programmingerror|operationalerror)\b)"
    r"|(\b(column|table|relation)\s+['\"]?[\w.]+['\"]?\s+(does not exist|not found))",
    re.IGNORECASE,
)
_ARTIFACT_ANSWER_RAW_KEYS = {
    "summary",
    "answer",
    "artifact_ref",
    "checkpoint_ref",
    "repair_plan_ref",
    "primary_ref",
    "related_refs",
    "result_ref",
    "report_ref",
    "subagent_tool_results",
    "artifact_card",
    "retry_checkpoint",
}


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
    """构造 Agent Team task envelope；所有用户可见载荷继续走 bi_workbench 脱敏。"""

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

    if isinstance(event, DatalogueEventEnvelope):
        # 新 runner 已经产出稳定 envelope 时直接透传，避免再走旧 SSE 字典兼容层。
        return event

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
        # agent_message 事件包含 LLM 推理/响应内容，映射为 reasoning.delta
        if legacy_type == "agent_message":
            reasoning_content = str(parsed.get("content") or "")
            phase = str(parsed.get("phase") or "")
            agent_name = str(parsed.get("agent") or "unknown")
            if reasoning_content.strip():
                return build_task_envelope(
                    event_type="reasoning.delta",
                    task_id=task_id,
                    trace_id=parsed.get("trace_id") or trace_id,
                    thread_id=thread_id,
                    message_id=message_id,
                    selected_agent=selected_agent,
                    payload={
                        "content": reasoning_content,
                        "phase": phase,
                        "agent": agent_name,
                    },
                    legacy_payload=parsed,
                )
        # agent.handoff 事件
        if legacy_type == "agent.handoff.started":
            return build_task_envelope(
                event_type="agent.handoff.started",
                task_id=task_id,
                trace_id=parsed.get("trace_id") or trace_id,
                thread_id=thread_id,
                message_id=message_id,
                selected_agent=selected_agent,
                payload={
                    "from_agent": parsed.get("from_agent") or "",
                    "to_agent": parsed.get("to_agent") or "",
                    "reason": parsed.get("reason") or "",
                    "dataset_id": (parsed.get("payload") or {}).get("dataset_id") if isinstance(parsed.get("payload"), dict) else None,
                },
                legacy_payload=parsed,
            )
        # tool_call.* 事件透传
        if legacy_type in {"tool_call.started", "tool_call.completed", "tool_call.failed"}:
            return build_task_envelope(
                event_type=legacy_type,
                task_id=task_id,
                trace_id=parsed.get("trace_id") or trace_id,
                thread_id=thread_id,
                message_id=message_id,
                selected_agent=selected_agent,
                payload={
                    "tool_name": parsed.get("tool_name") or "",
                    "tool_call_id": parsed.get("tool_call_id") or "",
                    "summary": parsed.get("payload", {}).get("summary") if isinstance(parsed.get("payload"), dict) else "",
                    "status": parsed.get("payload", {}).get("status") if isinstance(parsed.get("payload"), dict) else "",
                },
                legacy_payload=parsed,
            )
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
        event_envelope = parsed.get("event_envelope") if isinstance(parsed, dict) else None
        event_type = event_envelope.get("event_type") if isinstance(event_envelope, dict) else parsed.get("event_type")
        if _is_reply_end_event_type(event_type):
            payload = parsed.get("payload") if isinstance(parsed.get("payload"), dict) else {}
            envelope_payload = event_envelope.get("payload") if isinstance(event_envelope, dict) else {}
            final_payload = payload or envelope_payload
            if isinstance(final_payload, dict) and final_payload:
                return build_task_envelope(
                    event_type="message.completed",
                    task_id=task_id,
                    trace_id=parsed.get("trace_id") or trace_id,
                    thread_id=parsed.get("thread_id") or thread_id,
                    message_id=message_id,
                    selected_agent=selected_agent,
                    payload=final_payload,
                    legacy_payload=parsed,
                )
        if legacy_type == "final" or event_type in {"answer.completed", "error.blocked"}:
            envelope_payload = event_envelope.get("payload") if isinstance(event_envelope, dict) else {}
            answer = str(
                parsed.get("answer")
                or parsed.get("summary")
                or (envelope_payload or {}).get("answer")
                or (envelope_payload or {}).get("summary")
                or (envelope_payload or {}).get("error_summary")
                or ""
            )
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


def _is_reply_end_event_type(event_type: Any) -> bool:
    raw_type = str(event_type or "").lower()
    return any(marker in raw_type for marker in ("replyendevent", "reply.end", "reply_end", "final", "finish"))


def sanitize_event_payload_for_workbench(event_type: str, payload: dict) -> dict:
    if event_type.startswith("repair."):
        allowed = {"summary", "status", "requires_user_confirmation", "repair_plan_ref", "checkpoint_ref"}
        safe_payload = {key: value for key, value in payload.items() if key in allowed and value is not None}
        _assert_no_internal_details(safe_payload)
        return safe_payload
    if event_type.startswith("artifact.") or event_type == "answer.completed":
        return _sanitize_artifact_or_answer_payload(payload)
    safe_payload = _sanitize_generic_payload(payload)
    _assert_no_internal_details(safe_payload)
    return safe_payload


def project_event_envelope_to_agentscope(
    db: Session,
    *,
    thread_id: str,
    assistant_message_id: str | None,
    envelope: DatalogueEventEnvelope,
) -> AgentScopeEvent:
    event_type = str(envelope.event_type)
    visibility = _map_visibility(str(envelope.visibility))
    safe_payload = sanitize_event_payload_for_workbench(event_type, envelope.payload or {})
    event = record_agentscope_event(  # mirror event 是工作台时间线素材，写入前由 mirror 层再次 fail-closed。
        db,
        thread_id=thread_id,
        message_id=assistant_message_id,
        event_type=event_type,
        payload=safe_payload,
        visibility=visibility,
        task_id=envelope.task_id,
        trace_id=envelope.trace_id,
    )
    for ref_type, ref_value, relation in extract_refs_from_payload(safe_payload, trace_id=envelope.trace_id):
        try:
            record_agentscope_ref(
                db,
                thread_id=thread_id,
                message_id=assistant_message_id,
                ref_type=ref_type,
                ref_value=ref_value,
                relation=relation,
            )
        except ValueError as exc:
            if str(exc) != "AGENTSCOPE_REF_ALREADY_EXISTS":
                raise
    return event


def extract_refs_from_envelope(envelope: DatalogueEventEnvelope) -> list[tuple[str, str, str]]:
    return extract_refs_from_payload(envelope.payload or {}, trace_id=envelope.trace_id)


def extract_refs_from_payload(payload: dict, *, trace_id: str | None = None) -> list[tuple[str, str, str]]:
    refs: list[tuple[str, str, str]] = []
    _append_ref(refs, "artifact", payload.get("artifact_ref"), "primary")
    _append_ref(refs, "checkpoint", payload.get("checkpoint_ref"), "checkpoint")
    _append_ref(refs, "repair_plan", payload.get("repair_plan_ref"), "related")
    if trace_id:
        _append_ref(refs, "trace", trace_id, "trace")
    primary_ref = payload.get("primary_ref")
    if isinstance(primary_ref, dict):
        _append_ref(refs, str(primary_ref.get("ref_type") or "artifact"), _ref_value_from_ref_dict(primary_ref), "primary")
    for item in payload.get("related_refs") or []:
        if isinstance(item, dict):
            relation = "checkpoint" if item.get("ref_type") == "checkpoint" else "related"
            _append_ref(refs, str(item.get("ref_type") or "artifact"), _ref_value_from_ref_dict(item), relation)
    artifact_card = payload.get("artifact_card")
    if isinstance(artifact_card, dict):
        card_primary = artifact_card.get("primary_ref")
        if isinstance(card_primary, dict):
            _append_ref(refs, str(card_primary.get("ref_type") or "artifact"), _ref_value_from_ref_dict(card_primary), "primary")
        for item in artifact_card.get("related_refs") or []:
            if isinstance(item, dict):
                relation = "checkpoint" if item.get("ref_type") == "checkpoint" else "related"
                _append_ref(refs, str(item.get("ref_type") or "artifact"), _ref_value_from_ref_dict(item), relation)
    return refs


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


def _sanitize_generic_payload(payload: dict) -> dict:
    sanitized = _sanitize_generic_value(payload)
    return sanitized if isinstance(sanitized, dict) else {}


def _sanitize_generic_value(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict = {}
        for key, nested in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                continue  # 通用事件只保留业务摘要，内部 schema/query/raw/result 等字段直接裁剪。
            safe_key = "error_summary" if key == "error" and isinstance(nested, str) else str(key)
            safe[safe_key] = _sanitize_generic_value(nested)
        return safe
    if isinstance(value, list):
        return [_sanitize_generic_value(item) for item in value[:8]]
    if isinstance(value, str):
        return _safe_event_text(value, fallback="问数执行失败，内部细节已隐藏。")
    return value


def _safe_event_text(text: str, *, fallback: str) -> str:
    if _INTERNAL_TEXT_RE.search(text):
        return fallback
    return text


def _sanitize_artifact_or_answer_payload(payload: dict) -> dict:
    for key in payload:
        key_text = str(key).lower()
        if key_text not in _ARTIFACT_ANSWER_RAW_KEYS and any(
            fragment in key_text for fragment in _FORBIDDEN_KEY_FRAGMENTS
        ):
            raise ValueError("AGENTSCOPE_MIRROR_PAYLOAD_LEAK_DETECTED")

    safe: dict = {}
    for key in ("summary", "answer", "artifact_ref", "checkpoint_ref", "repair_plan_ref"):
        if payload.get(key) is not None:
            safe[key] = payload[key]

    primary_ref = _normalize_ref_dict(payload.get("primary_ref"))
    related_refs = [_normalize_ref_dict(item) for item in payload.get("related_refs") or []]

    result_ref = _public_ref_value(payload.get("result_ref"))
    if result_ref and primary_ref is None:
        primary_ref = {"ref_type": "result", "ref": result_ref}
    report_ref = _public_ref_value(payload.get("report_ref"))
    if report_ref:
        related_refs.append({"ref_type": "report", "ref": report_ref})
    for item in payload.get("subagent_tool_results") or []:
        if not isinstance(item, dict):
            continue
        item_result_ref = _public_ref_value(item.get("result_ref"))
        if item_result_ref:
            related_refs.append({"ref_type": "result", "ref": item_result_ref})
        item_report_ref = _public_ref_value(item.get("report_ref"))
        if item_report_ref:
            related_refs.append({"ref_type": "report", "ref": item_report_ref})

    artifact_card = payload.get("artifact_card")
    if isinstance(artifact_card, dict):
        card_primary = _normalize_ref_dict(artifact_card.get("primary_ref"))
        if card_primary and primary_ref is None:
            primary_ref = card_primary
        for item in artifact_card.get("related_refs") or []:
            related_refs.append(_normalize_ref_dict(item))

    if primary_ref:
        safe["primary_ref"] = primary_ref
    safe_related_refs = _dedupe_ref_dicts(ref for ref in related_refs if ref)
    if safe_related_refs:
        safe["related_refs"] = safe_related_refs
    _assert_no_internal_details(safe)
    return safe


def _assert_no_internal_details(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise ValueError("AGENTSCOPE_MIRROR_PAYLOAD_LEAK_DETECTED")
            _assert_no_internal_details(nested)
    elif isinstance(value, list):
        for item in value:
            _assert_no_internal_details(item)
    elif isinstance(value, str) and (_SQL_TEXT_RE.search(value) or _INTERNAL_TEXT_RE.search(value)):
        raise ValueError("AGENTSCOPE_MIRROR_PAYLOAD_LEAK_DETECTED")


def _append_ref(refs: list[tuple[str, str, str]], ref_type: str, ref_value: Any, relation: str) -> None:
    if isinstance(ref_value, str) and ref_value:
        refs.append((ref_type, ref_value, relation))


def _normalize_ref_dict(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    ref_value = _ref_value_from_ref_dict(value)
    if not ref_value:
        return None
    return {
        "ref_type": str(value.get("ref_type") or "artifact"),
        "ref": ref_value,
    }


def _ref_value_from_ref_dict(value: dict) -> str | None:
    return _public_ref_value(value.get("ref") or value.get("ref_id"))


def _public_ref_value(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if value.startswith(("artifact:", "trace:", "checkpoint:", "checkpoint://")):
        return value
    return None


def _dedupe_ref_dicts(refs: Any) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        ref_type = str(ref.get("ref_type") or "artifact")
        ref_value = _public_ref_value(ref.get("ref"))
        if not ref_value:
            continue
        key = (ref_type, ref_value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"ref_type": ref_type, "ref": ref_value})
    return deduped


def _map_visibility(visibility: str) -> str:
    if visibility == "user_visible":
        return "user"
    if visibility == "control_plane":
        return "trace_only"
    return visibility
