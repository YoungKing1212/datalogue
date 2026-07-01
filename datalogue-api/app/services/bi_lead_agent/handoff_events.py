# ============================================================
# File Name   : handoff_events.py
# Description:
#   BI LeadAgent AgentScope native handoff 事件投影。
#
# Responsibilities:
#   - 将 AgentScope native 子运行事件映射为 Datalogue handoff 安全状态。
#   - 过滤 SQL/schema/raw rows/DSL 等 DatasetAgent 执行层内部字段。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from agentscope.message import TextBlock, ToolResultBlock

from app.schemas.bi_lead_agent import BIHandoffStatus
from app.services.agentic_shell import DatalogueAgenticShell


_ALLOWED_NATIVE_EVENT_FIELDS = {
    "child_run_id",
    "artifact_ref",
    "checkpoint_ref",
    "answer_summary",
    "row_count",
    "column_count",
    "status_reason",
    "error_code",
    "error_summary",
}
_EVENT_STATUS_MAP: dict[str, BIHandoffStatus] = {
    "agent.child.created": "accepted",
    "agent.child.accepted": "accepted",
    "agent.child.running": "running",
    "agent.child.waiting": "waiting_child",
    "agent.child.completed": "completed",
    "agent.child.blocked": "blocked",
    "agent.child.failed": "failed",
    "agent.child.cancelled": "cancelled",
}
_SAFE_NATIVE_FAILURE_SUMMARY = "AgentScope native DatasetAgent 执行失败，已停止 handoff。"


def map_native_handoff_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """把 native child-agent 事件投影为 Datalogue 安全 handoff payload。"""

    # event_type 是内部控制字段，通用输出 sanitizer 会裁掉；状态映射必须先从原始 envelope 读取。
    event_type = _safe_str(event.get("event_type") or event.get("type"))
    raw_status = event.get("handoff_status") or event.get("status")
    sanitized = DatalogueAgenticShell().sanitize_output(dict(event))
    if not isinstance(sanitized, dict):
        return {}

    mapped: dict[str, Any] = {}
    event_status = _EVENT_STATUS_MAP.get(event_type or "")
    explicit_status = _safe_status(raw_status)
    status = event_status or explicit_status
    if status:
        mapped["handoff_status"] = status

    for field in _ALLOWED_NATIVE_EVENT_FIELDS:
        value = sanitized.get(field)
        if value is None:
            continue
        if field in {"row_count", "column_count"}:
            coerced = _safe_int(value)
            if coerced is not None:
                mapped[field] = coerced
            continue
        safe_value = _safe_str(value)
        if safe_value:
            mapped[field] = safe_value

    return mapped


def collect_native_handoff_payload(
    events: list[Any],
    *,
    fallback_artifact_ref: str | None = None,
    fallback_error: Any = None,
) -> dict[str, Any]:
    """从 AgentScope native 事件流中收敛最后一份安全 handoff payload。"""

    payload: dict[str, Any] = {}
    for candidate in _payload_candidates(events):
        mapped = map_native_handoff_event(candidate)
        for key, value in mapped.items():
            payload[key] = value  # native event 以后续事件为准，最终 child.completed 覆盖中间 running。

    if fallback_artifact_ref:
        payload.setdefault("artifact_ref", fallback_artifact_ref)
        payload.setdefault("handoff_status", "completed")

    if fallback_error:
        error_payload = map_native_handoff_event(_fallback_error_payload(fallback_error))
        payload.setdefault("handoff_status", "blocked")
        payload.setdefault("error_code", error_payload.get("error_code"))
        payload.setdefault("error_summary", error_payload.get("error_summary"))

    return payload


def native_status_or_default(payload: Mapping[str, Any]) -> BIHandoffStatus:
    status = _safe_status(payload.get("handoff_status"))
    if status:
        return status
    if payload.get("artifact_ref"):
        return "completed"
    if payload.get("error_code") or payload.get("error_summary"):
        return "blocked"
    return "blocked"


def safe_native_failure_result_payload(error_code: str = "AGENTSCOPE_NATIVE_HANDOFF_FAILED") -> dict[str, Any]:
    return {
        "handoff_status": "failed",
        "status_reason": "agentscope_native_handoff_failed",
        "error_code": error_code,
        "error_summary": _SAFE_NATIVE_FAILURE_SUMMARY,
    }


def _payload_candidates(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _payload_candidates(nested)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _payload_candidates(item)
        return
    if isinstance(value, ToolResultBlock):
        for block in value.output or []:
            yield from _payload_candidates(block)
        return
    if isinstance(value, TextBlock):
        yield from _payload_from_text(value.text)
        return
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            yield from _payload_candidates(dumped)


def _payload_from_text(text: str | None) -> Iterable[dict[str, Any]]:
    if not text:
        return []
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return [{"event_type": "agent.child.completed", "answer_summary": text}]
    return [loaded] if isinstance(loaded, dict) else []


def _fallback_error_payload(error: Any) -> dict[str, Any]:
    if isinstance(error, dict):
        return error
    return {
        "event_type": "agent.child.blocked",
        "error_code": getattr(error, "code", None) or "DATASET_AGENT_BLOCKED",
        "error_summary": getattr(error, "error_summary", None) or str(error),
    }


def _safe_status(value: Any) -> BIHandoffStatus | None:
    text = _safe_str(value)
    if text in {"created", "accepted", "running", "waiting_child", "completed", "blocked", "failed", "cancelled"}:
        return text  # type: ignore[return-value]
    return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
