# ============================================================
# File Name   : agentscope_event_projection.py
# Description:
#   Datalogue event envelope 到 AgentScope 工作台事件镜像的投影服务。
#
# Responsibilities:
#   - 将主链 SSE event envelope 写入 AgentScope mirror event。
#   - 从事件中抽取 artifact/checkpoint/trace 等业务级 refs。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.agentscope_workbench import AgentScopeEvent
from app.schemas.bi_workbench import DatalogueEventEnvelope
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


def _sanitize_generic_payload(payload: dict) -> dict:
    safe: dict = {}
    for key, value in payload.items():
        if key in {"answer", "summary"} and isinstance(value, str):
            safe[key] = _safe_event_text(value, fallback="问数执行失败，内部细节已隐藏。")
        elif key == "error" and isinstance(value, str):
            safe["error_summary"] = _safe_event_text(value, fallback="问数执行失败，内部细节已隐藏。")
        else:
            safe[key] = value
    return safe


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
