# ============================================================
# File Name   : traces.py
# Description:
#   查询审计 Trace 聚合服务。
#
# Responsibilities:
#   - 汇总历史本地索引和消息步骤。
#   - 为 Datalogue 自有查询审计页提供可渲染的链路详情。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.services.observability.tracer import build_observability_trace_url

WORKBENCH_RETRY_REQUIRED_EVENTS = [
    "workbench.retry_requested",
    "retry.started",
    "retry.checkpoint_restored",
    "dataset.query.completed",
    "answer.completed",
]


def list_query_audit_traces(
    db: Session,
    *,
    dataset_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """返回查询审计列表和 KPI。"""

    base_query = db.query(models.ObservabilityTraceIndex)
    if dataset_id is not None:
        base_query = base_query.filter(models.ObservabilityTraceIndex.dataset_id == dataset_id)

    summary = _build_summary(base_query)
    list_query = base_query
    if status and status != "all":
        list_query = list_query.filter(models.ObservabilityTraceIndex.status == status)
    rows = (
        list_query.order_by(models.ObservabilityTraceIndex.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )

    return {
        "summary": summary,
        "items": [_trace_index_item(db, row) for row in rows],
    }


def get_query_audit_trace(db: Session, *, trace_id: str) -> dict[str, Any]:
    """返回单条查询审计详情，Observability 不可用时使用本地 fallback。"""

    index = (
        db.query(models.ObservabilityTraceIndex)
        .filter(models.ObservabilityTraceIndex.trace_id == trace_id)
        .order_by(models.ObservabilityTraceIndex.created_at.desc())
        .first()
    )
    if not index:
        return {
            "found": False,
            "trace_id": trace_id,
            "source": "missing",
            "provider": {"name": "missing", "available": False, "error": "trace index not found"},
            "observability_error": "trace index not found",
            "item": None,
            "trace": None,
            "observations": [],
            "scores": [],
            "fallback_steps": [],
            "local_events": [],
            "observability_contract": _build_observability_contract(
                trace_id=trace_id,
                conversation_id=None,
                metadata={},
                observations=[],
                fallback_steps=[],
                local_events=[],
            ),
        }

    item = _trace_index_item(db, index)
    message = db.get(models.Message, index.message_id) if index.message_id else None
    observability_trace, observability_error = _fetch_observability_trace(trace_id)
    observations = _normalize_observations(observability_trace)
    scores = _normalize_scores(observability_trace)
    fallback_steps = _fallback_steps(message)
    local_events = _local_agentscope_events(db, trace_id=trace_id, metadata=index.metadata_json or {})
    source = "observability" if observability_trace else "local"

    return {
        "found": True,
        "trace_id": trace_id,
        "source": source,
        "provider": {
            "name": source,
            "available": bool(observability_trace) or bool(local_events or fallback_steps),
            "error": observability_error,
        },
        "observability_error": observability_error,
        "item": item,
        "trace": _normalize_trace(observability_trace) if observability_trace else _local_trace(message, item),
        "observations": observations,
        "scores": scores,
        "fallback_steps": fallback_steps,
        "local_events": local_events,
        "observability_contract": _build_observability_contract(
            trace_id=trace_id,
            conversation_id=index.conversation_id,
            metadata=index.metadata_json or {},
            observations=observations,
            fallback_steps=fallback_steps,
            local_events=local_events,
        ),
    }


def _build_summary(query) -> dict[str, Any]:
    total = query.count()
    failed = query.filter(models.ObservabilityTraceIndex.status == "failed").count()
    tokens = query.with_entities(
        func.coalesce(func.sum(models.ObservabilityTraceIndex.total_tokens), 0)
    ).scalar()
    cost = query.with_entities(
        func.coalesce(func.sum(models.ObservabilityTraceIndex.total_cost), 0)
    ).scalar()
    return {
        "total_traces": total,
        "failed_traces": failed,
        "success_rate": round((total - failed) / total, 4) if total else None,
        "total_tokens": int(tokens or 0),
        "total_cost": float(cost or 0),
    }


def _trace_index_item(db: Session, index: models.ObservabilityTraceIndex) -> dict[str, Any]:
    message = db.get(models.Message, index.message_id) if index.message_id else None
    conversation = db.get(models.Conversation, index.conversation_id) if index.conversation_id else None
    metadata = index.metadata_json or {}
    response_metadata = message.response_metadata or {} if message else {}
    observability = response_metadata.get("observability") or {}
    observability = response_metadata.get("observability") or observability
    question = metadata.get("question") or _latest_user_question(db, index.conversation_id)
    sql_list = message.sql_list or [] if message else []
    error_text = _extract_error(response_metadata, index.metadata_json)

    return {
        "id": index.id,
        "trace_id": index.trace_id,
        "session_id": index.trace_session_id,
        "trace_url": observability.get("trace_url")
        or build_observability_trace_url(base_url=None, project_id=None, trace_id=index.trace_id),
        "conversation_id": index.conversation_id,
        "message_id": index.message_id,
        "dataset_id": index.dataset_id,
        "question": question or conversation.title if conversation else question,
        "answer_preview": _truncate(_strip_think(message.content if message else ""), 160),
        "sql_preview": _truncate(sql_list[0] if sql_list else "", 220),
        "entry_route": index.entry_route or "unknown",
        "status": index.status or "unknown",
        "total_tokens": index.total_tokens or 0,
        "total_cost": float(index.total_cost or 0),
        "created_at": _iso(index.created_at),
        "conversation_title": conversation.title if conversation else None,
        "error": error_text,
    }


def _latest_user_question(db: Session, conversation_id: int | None) -> str | None:
    if not conversation_id:
        return None
    msg = (
        db.query(models.Message)
        .filter(models.Message.conversation_id == conversation_id, models.Message.role == "user")
        .order_by(models.Message.created_at.desc())
        .first()
    )
    return msg.content if msg else None


def _fetch_observability_trace(trace_id: str) -> Any | None:
    return None, "Trace disabled"


def _normalize_trace(trace: Any) -> dict[str, Any]:
    data = _to_plain(trace)
    return {
        "id": _get(data, "id"),
        "name": _get(data, "name"),
        "timestamp": _get(data, "timestamp") or _get(data, "startTime"),
        "input": _get(data, "input"),
        "output": _get(data, "output"),
        "metadata": _get(data, "metadata") or {},
        "scores": _get(data, "scores") or [],
        "metrics": _get(data, "metrics") or {},
        "raw": data,
    }


def _normalize_observations(trace: Any) -> list[dict[str, Any]]:
    data = _to_plain(trace)
    observations = _get(data, "observations") or []
    normalized = []
    for obs in observations:
        plain = _to_plain(obs)
        normalized.append(
            {
                "id": _get(plain, "id"),
                "parent_id": _get(plain, "parentObservationId") or _get(plain, "parent_observation_id"),
                "type": _get(plain, "type") or _get(plain, "asType"),
                "name": _get(plain, "name") or "observation",
                "start_time": _get(plain, "startTime") or _get(plain, "start_time"),
                "end_time": _get(plain, "endTime") or _get(plain, "end_time"),
                "latency_ms": _latency_ms(plain),
                "level": _get(plain, "level"),
                "status_message": _get(plain, "statusMessage") or _get(plain, "status_message"),
                "model": _get(plain, "model"),
                "input": _get(plain, "input"),
                "output": _get(plain, "output"),
                "usage": _get(plain, "usage") or _get(plain, "usageDetails") or _get(plain, "usage_details"),
                "metadata": _get(plain, "metadata") or {},
            }
        )
    return sorted(normalized, key=lambda item: item.get("start_time") or "")


def _normalize_scores(trace: Any) -> list[dict[str, Any]]:
    data = _to_plain(trace)
    scores = _get(data, "scores") or []
    return [
        {
            "id": _get(score, "id"),
            "name": _get(score, "name"),
            "value": _get(score, "value"),
            "data_type": _get(score, "dataType") or _get(score, "data_type"),
            "comment": _get(score, "comment"),
        }
        for score in (_to_plain(item) for item in scores)
    ]


def _local_agentscope_events(
    db: Session,
    *,
    trace_id: str,
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    thread_id = metadata.get("thread_id") if isinstance(metadata, dict) else None
    query = db.query(models.AgentScopeEvent)
    if thread_id:
        query = query.filter(
            (models.AgentScopeEvent.trace_id == trace_id)
            | (models.AgentScopeEvent.thread_id == thread_id)
        )
    else:
        query = query.filter(models.AgentScopeEvent.trace_id == trace_id)
    events = query.order_by(models.AgentScopeEvent.id.asc()).all()
    seen: set[int] = set()
    out = []
    for event in events:
        if event.id in seen:
            continue
        seen.add(event.id)
        out.append(
            {
                "id": event.event_id,
                "name": event.event_type,
                "event_type": event.event_type,
                "thread_id": event.thread_id,
                "message_id": event.message_id,
                "task_id": event.task_id,
                "trace_id": event.trace_id,
                "metadata": event.payload_json or {},
                "created_at": _iso(event.created_at),
            }
        )
    return out


def _build_observability_contract(
    *,
    trace_id: str,
    conversation_id: int | None,
    metadata: dict[str, Any],
    observations: list[dict[str, Any]],
    fallback_steps: list[dict[str, Any]],
    local_events: list[dict[str, Any]],
) -> dict[str, Any]:
    # 契约只关心业务事件和 refs，不绑定 Observability/OTel 的内部字段名。
    event_sources = [*observations, *fallback_steps, *local_events]
    matched_events = _matched_contract_events(event_sources)
    missing_events = [event for event in WORKBENCH_RETRY_REQUIRED_EVENTS if event not in matched_events]
    attributes = _contract_attributes(
        trace_id=trace_id,
        conversation_id=conversation_id,
        metadata=metadata,
        event_sources=event_sources,
    )
    return {
        "name": "workbench_retry_v1",
        "passed": not missing_events,
        "required_events": WORKBENCH_RETRY_REQUIRED_EVENTS,
        "matched_events": matched_events,
        "missing_events": missing_events,
        "attributes": attributes,
    }


def _matched_contract_events(items: list[dict[str, Any]]) -> list[str]:
    matched: list[str] = []
    for item in items:
        candidates = [
            item.get("event_type"),
            item.get("name"),
            item.get("id"),
            (item.get("metadata") or {}).get("event_type") if isinstance(item.get("metadata"), dict) else None,
            (item.get("metadata") or {}).get("technical_name") if isinstance(item.get("metadata"), dict) else None,
        ]
        for value in candidates:
            event = _normalize_contract_event_name(value)
            if event in WORKBENCH_RETRY_REQUIRED_EVENTS and event not in matched:
                matched.append(event)
    return matched


def _normalize_contract_event_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    for prefix in ("node.", "event."):
        if text.startswith(prefix):
            text = text.removeprefix(prefix)
    return text


def _contract_attributes(
    *,
    trace_id: str,
    conversation_id: int | None,
    metadata: dict[str, Any],
    event_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    attrs = {
        "trace_id": trace_id,
        "conversation_id": conversation_id,
        "thread_id": metadata.get("thread_id"),
        "checkpoint_ref": metadata.get("checkpoint_ref"),
        "artifact_ref": metadata.get("artifact_ref"),
    }
    for item in event_sources:
        nested = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        for key in ("thread_id", "checkpoint_ref", "artifact_ref"):
            if not attrs.get(key):
                attrs[key] = item.get(key) or nested.get(key)
        if not attrs.get("artifact_ref"):
            primary_ref = nested.get("primary_ref")
            if isinstance(primary_ref, dict):
                attrs["artifact_ref"] = primary_ref.get("ref")
    return attrs


def _fallback_steps(message: models.Message | None) -> list[dict[str, Any]]:
    if not message or not message.step_trace:
        return []
    out = []
    for step in message.step_trace:
        out.append(
            {
                "id": step.get("node"),
                "name": step.get("display_name") or step.get("node"),
                "status": step.get("status"),
                "latency_ms": step.get("elapsed_ms"),
                "metadata": {k: v for k, v in step.items() if k not in {"node", "display_name", "status", "elapsed_ms"}},
            }
        )
    return out


def _local_trace(message: models.Message | None, item: dict[str, Any]) -> dict[str, Any]:
    metadata = message.response_metadata if message else {}
    return {
        "id": item["trace_id"],
        "name": "Datalogue query",
        "timestamp": item["created_at"],
        "input": item.get("question"),
        "output": message.content if message else None,
        "metadata": metadata or {},
        "scores": [],
        "metrics": {
            "total_tokens": item.get("total_tokens", 0),
            "total_cost": item.get("total_cost", 0),
        },
        "raw": {},
    }


def _extract_error(response_metadata: dict[str, Any], index_metadata: dict[str, Any] | None) -> str | None:
    for value in (
        (response_metadata or {}).get("sql_diagnosis"),
        (response_metadata or {}).get("sql_audit_result"),
        (index_metadata or {}).get("error") if index_metadata else None,
    ):
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            for key in ("message", "title", "root_cause", "error", "suggested_action"):
                if value.get(key):
                    return str(value[key])
    return None


def _to_plain(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    for attr in ("model_dump", "dict"):
        fn = getattr(value, attr, None)
        if callable(fn):
            try:
                return _to_plain(fn())
            except Exception:  # noqa: BLE001
                pass
    if hasattr(value, "__dict__"):
        return {
            key: _to_plain(val)
            for key, val in vars(value).items()
            if not key.startswith("_")
        }
    return str(value)


def _get(data: Any, key: str, default: Any = None) -> Any:
    if isinstance(data, dict):
        return data.get(key, default)
    return getattr(data, key, default)


def _latency_ms(observation: dict[str, Any]) -> int | None:
    latency = _get(observation, "latency")
    if isinstance(latency, (int, float)):
        return int(latency * 1000 if latency < 1000 else latency)
    start = _get(observation, "startTime") or _get(observation, "start_time")
    end = _get(observation, "endTime") or _get(observation, "end_time")
    try:
        if not start or not end:
            return None
        start_dt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        return int((end_dt - start_dt).total_seconds() * 1000)
    except Exception:  # noqa: BLE001
        return None


def _truncate(text: Any, max_length: int) -> str:
    value = str(text or "")
    return value if len(value) <= max_length else value[:max_length] + "..."


def _strip_think(text: Any) -> str:
    value = str(text or "")
    return re.sub(r"<think>.*?</think>", "", value, flags=re.DOTALL | re.IGNORECASE).strip()


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None
