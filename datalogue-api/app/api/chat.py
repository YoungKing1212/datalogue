# ============================================================
# File Name   : chat.py
# Description:
#   聊天问数 API 端点。
#
# Responsibilities:
#   - 流式输出 NL2SQL 工作流事件和最终回答。
#   - 持久化聊天消息、SQL 和执行轨迹元数据。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# 问数对话路由 — SSE 流式输出 + LangGraph Agent 工作流

import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app import schemas, models
from app.graph.workflow import build_workflow
from app.schemas.bi_workbench import (
    ArtifactAction,
    ArtifactCard,
    ArtifactRef,
    DatalogueEventType,
    DatalogueEventVisibility,
    build_datalogue_event_envelope,
)
from app.services.answer_explanation import (
    build_answer_explanation,
)
from app.services.observability.context import (
    current_observability_context,
    set_observability_context,
)
from app.services.observability.feedback import submit_message_feedback
from app.services.observability.tracer import get_observability_tracer
from app.services.lead_agent import (
    build_lead_agent_context,
    merge_multiturn_decision_for_chat,
)
from app.services.lead_agent_routing import (
    resolve_term_clarification,
    route_query_intent,
)
from app.services.dataset_subagent import DatasetSubAgent
from app.services.multiturn_context import MergeDecision
from app.services.report_generation import stream_sql_result_report
from app.services.runner import DatasetSubAgentRequest, RemoteDatasetSubAgentRunner
from app.services.artifact_store import ArtifactStore
from app.schemas.repair_plan import RepairPlan
from app.services.repair_plan import sanitize_repair_plan_for_artifact
from app.services.subagent_tool_adapter import (
    SubAgentInvocation,
    SubAgentToolAdapter,
)
from app.services.subagent_fanout import (
    SubAgentFanOutAnswerSynthesizer,
    SubAgentFanOutInvocation,
    SubAgentFanOutOrchestrator,
    parse_dataset_fanout_invocations,
)
from app.services.conversation_store import (
    ConversationStore,
    THREAD_STATE_KEY,
    pending_clarification_from_final_payload,
    session_key,
)
from app.services.message_gateway import classify_turn_event
from app.services.task_capsule import (
    build_query_task_capsule,
    build_success_task_state,
    has_query_target,
)
from app.services.multiturn.last_success_task import (
    CapsuleSizeExceededError,
    evaluate_last_success_task,
)
from app.services.multiturn.query_artifacts import (
    build_query_result_artifact,
    evaluate_query_artifact,
)
from app.services.multiturn.refinement_fast_path import plan_refinement_fast_path
from app.utils.think import (
    filter_think_stream_chunk,
    flush_think_stream_state,
    new_think_stream_state,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# 节点名称到前端/Trace 展示名的映射；展示名统一使用原始节点名，便于按节点检索 trace。
# Phase 3-7 改造中已从 Graph 删除的节点同步清理：
#   merge_prior_context, clarification_resolution, intent_recognition,
#   entry_intent_classification, analysis_blueprint_execute,
#   term_conflict_resolve, metric_resolve
_NODE_DISPLAY_NAMES = {
    # Chat 层
    "message_gateway": "message_gateway",
    # Graph 节点（build_workflow 注册的 9 个节点）
    "lead_agent": "lead_agent",
    "schema_recall": "schema_recall",
    "dsl_generate": "dsl_generate",
    "dsl_validate": "dsl_validate",
    "dsl_compiler": "dsl_compiler",
    "sql_execute": "sql_execute",
    "sql_audit": "sql_audit",
    "report_generator": "report_generator",
    "increment_retry": "increment_retry",
    # SubAgent 事件（SSE 展示用）
    "candidate_assets": "subagent.candidate_assets",
    "query_plan": "subagent.query_plan",
    # LeadAgent 自动路由报告
    "lead_agent_report_generator": "lead_agent_report_generator",
}

_TRACE_CAPSULE_BLOCKED_KEYS = {
    "data",
    "direct_sql",
    "dsl",
    "raw",
    "raw_sql",
    "records",
    "result",
    "result_rows",
    "rows",
    "sample_rows",
    "sql",
    "sql_result",
}
_TRACE_CAPSULE_SQL_VALUE_RE = re.compile(
    r"(?is)\b(select|insert|update|delete|drop|alter|create|with)\b"
    r".{0,200}\b(from|into|set|table|join|where|values)\b"
)

_PUBLIC_SSE_BLOCKED_KEYS = {
    "candidate_assets",
    "column",
    "column_labels",
    "columns",
    "control_plane",
    "data",
    "dataset_context_debug",
    "datasource_context",
    "direct_sql",
    "dsl",
    "explainability",
    "field",
    "fields",
    "lead_agent_context",
    "merge_debug",
    "out_capsule",
    "patch",
    "query_plan",
    "query_plan_debug",
    "query_profile",
    "query_task_capsule",
    "raw",
    "raw_result",
    "raw_sql",
    "records",
    "result",
    "result_artifact",
    "result_rows",
    "response_metadata",
    "rows",
    "sample_rows",
    "schema",
    "schema_context",
    "schema_summary",
    "sql",
    "sql_audit_result",
    "sql_diagnosis",
    "sql_list",
    "sql_result",
    "sql_retry_trace",
    "subagent_control_plane",
    "table",
    "tables",
}


def _safe_trace_capsule_value(value: Any, *, key_name: str = "") -> Any:
    key_lower = key_name.lower()
    if key_lower in _TRACE_CAPSULE_BLOCKED_KEYS or "sql" in key_lower:
        return None
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            safe_item = _safe_trace_capsule_value(item, key_name=key)
            if safe_item in (None, "", [], {}):
                continue
            sanitized[key] = safe_item
        return sanitized
    if isinstance(value, list):
        return [
            item
            for item in (_safe_trace_capsule_value(item, key_name=key_name) for item in value[:8])
            if item not in (None, "", [], {})
        ]
    if isinstance(value, str):
        text = value.strip()
        if _TRACE_CAPSULE_SQL_VALUE_RE.search(text):
            return None
        return text[:500]
    return value


def _safe_query_task_capsule_for_trace(capsule: Any) -> dict | None:
    """返回可用于 SSE、落库和前端展示的 QueryTaskCapsule 安全视图。"""
    if not isinstance(capsule, dict):
        return None
    safe_capsule = _safe_trace_capsule_value(capsule)
    return safe_capsule if isinstance(safe_capsule, dict) and safe_capsule else None


def _is_public_sse_blocked_key(key: str) -> bool:
    """判断 SSE 用户可见兼容层字段是否属于内部执行面。"""

    key_lower = key.lower()
    return (
        key_lower in _PUBLIC_SSE_BLOCKED_KEYS
        or "sql" in key_lower
        or key_lower.endswith("_schema")
        or key_lower.endswith("_table")
        or key_lower.endswith("_field")
        or key_lower.endswith("_column")
    )


def _safe_public_sse_value(value: Any, *, key_name: str = "") -> Any:
    """递归清理 SSE 顶层兼容 payload，避免旧字段旁路泄露执行细节。"""

    if _is_public_sse_blocked_key(key_name):
        return None
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or _is_public_sse_blocked_key(key):
                continue
            safe_item = _safe_public_sse_value(item, key_name=key)
            if safe_item in (None, "", [], {}):
                continue
            sanitized[key] = safe_item
        return sanitized
    if isinstance(value, list):
        return [
            item
            for item in (_safe_public_sse_value(item, key_name=key_name) for item in value[:8])
            if item not in (None, "", [], {})
        ]
    if isinstance(value, str):
        text = value.strip()
        if _TRACE_CAPSULE_SQL_VALUE_RE.search(text):
            return None
        return text[:1000]
    return value


def _public_sse_payload(payload: dict) -> dict:
    """生成浏览器可见 SSE payload；trace/store 仍使用未裁剪的内部 final_state。"""

    safe_payload = _safe_public_sse_value(payload)
    return safe_payload if isinstance(safe_payload, dict) else {}


_STATE_OUTPUT_KEYS = {
    "conversation_id",
    "original_question",
    "resolved_question",
    "manifest_version",
    "bound_schema_version",
    "time_context",
    "thread_context",
    "route_decision",
    "schema_status",
    "lead_agent_context",
    "skip_subagent_report",
    "report_owner",
    "subagent_report_skipped",
    "lead_agent_report",
    "intent",
    "entities",
    "entry_intent",
    "entry_route",
    "entry_reason",
    "blueprint_id",
    "blueprint_match",
    "blueprint_context",
    "knowledge_term_id",
    "route_payload",
    "clarification_response",
    "clarification_resolution_result",
    "prior_capsule",
    "prior_capsule_status",
    "out_capsule",
    "multiturn_context",
    "turn_type",
    "merge_debug",
    "selected_term_id",
    "schema_context",
    "query_constraints",
    "dataset_context_debug",
    "datasource_context",
    "term_normalization",
    "semantic_asset_resolution",
    "metric_resolution",
    "candidate_assets",
    "query_plan",
    "query_plan_debug",
    "dsl",
    "dsl_valid",
    "sql",
    "sql_result",
    "datasource_dialect",
    "sql_audit_result",
    "sql_diagnosis",
    "sql_retry_trace",
    "answer",
    "answer_explanation",
    "sql_list",
    "error",
    "generation_mode",
    "should_retry",
    "token_usage",
    "turn_event",
    "query_task_capsule",
}

TERM_CLARIFICATION_TTL_MINUTES = 30


def _sse_data(payload: dict) -> dict:
    """将 SSE payload 转成 JSON 字符串，兼容 datetime/date/Decimal 等对象。"""
    return {"data": json.dumps(jsonable_encoder(payload), ensure_ascii=False)}


def _event_metadata_from_payload(payload: dict) -> dict[str, Any]:
    """从旧 SSE payload 提取稳定索引字段，避免 envelope 复制大 payload。"""

    metadata: dict[str, Any] = {}
    for key in (
        "conversation_id",
        "message_id",
        "entry_route",
        "entry_reason",
        "langfuse_trace_id",
        "langfuse_session_id",
    ):
        if payload.get(key) is not None:
            metadata[key] = payload[key]
    route_decision = payload.get("route_decision")
    if isinstance(route_decision, dict):
        dataset_id = route_decision.get("dataset_id")
        if dataset_id is not None:
            metadata["dataset_id"] = dataset_id
        metadata["route_decision"] = {
            key: route_decision[key]
            for key in ("decision", "dataset_id", "dataset_name", "reason")
            if route_decision.get(key) is not None
        }
    elif payload.get("dataset_id") is not None:
        metadata["dataset_id"] = payload["dataset_id"]
    return metadata


def _with_event_envelope(
    payload: dict,
    *,
    event_type: DatalogueEventType,
    visibility: DatalogueEventVisibility,
    payload_fields: tuple[str, ...] = (),
    event_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """给 SSE payload 追加统一 envelope，并裁剪浏览器可见旧字段。"""

    envelope_payload = (
        dict(event_payload)
        if event_payload is not None
        else {key: payload.get(key) for key in payload_fields if payload.get(key) is not None}
    )
    safe_envelope_payload = _public_sse_payload(envelope_payload)
    for internal_step_key in ("node", "display_name"):
        safe_envelope_payload.pop(internal_step_key, None)
    envelope_metadata = _event_metadata_from_payload(payload)
    if metadata:
        envelope_metadata.update({key: value for key, value in metadata.items() if value is not None})
    envelope = build_datalogue_event_envelope(
        event_type=event_type,
        visibility=visibility,
        payload=safe_envelope_payload,
        metadata=envelope_metadata,
        task_id=payload.get("task_id") or envelope_metadata.get("task_id"),
        conversation_id=payload.get("conversation_id") or envelope_metadata.get("conversation_id"),
        trace_id=(
            payload.get("trace_id")
            or payload.get("langfuse_trace_id")
            or envelope_metadata.get("trace_id")
        ),
    )
    enriched = _public_sse_payload(payload)  # 旧字段只保留业务摘要，内部执行面留在 trace/store。
    # event_envelope 是新增兼容字段，不能覆盖旧 type；未来 AgentScope 可直接消费这里。
    enriched["event_envelope"] = envelope.model_dump(mode="json")
    return enriched


def _safe_public_ref_value(value: Any) -> str | None:
    """只接受公开引用句柄；raw SQL/raw result 等内部内容不能进入 ArtifactCard。"""

    if isinstance(value, str):
        ref = value.strip()
    elif isinstance(value, dict):
        ref = str(
            value.get("ref_id")
            or value.get("ref")
            or value.get("artifact_ref")
            or ""
        ).strip()
    else:
        return None
    if ref.startswith(("artifact:", "trace:", "checkpoint://")):
        return ref
    return None


def _artifact_ref_dict(
    ref_value: Any,
    *,
    ref_type: str = "artifact",
    label: str | None = None,
) -> dict | None:
    """构造前端/Agent 可见的轻量引用，避免携带 artifact body。"""

    ref_id = _safe_public_ref_value(ref_value)
    if not ref_id:
        return None
    artifact_ref = ArtifactRef(ref_id=ref_id, ref_type=ref_type, label=label)
    return artifact_ref.model_dump(mode="json", exclude_none=True)


def _iter_result_refs_from_payload(final_payload: dict) -> list[dict]:
    """从 final payload 中提取可公开的查询产物引用，不读取产物内容。"""

    refs: list[dict] = []
    direct_result = _artifact_ref_dict(
        final_payload.get("result_ref"),
        ref_type="result",
        label="主查询结果",
    )
    if direct_result:
        refs.append(direct_result)
    direct_report = _artifact_ref_dict(
        final_payload.get("report_ref"),
        ref_type="report",
        label="报告占位",
    )
    if direct_report:
        refs.append(direct_report)
    for item in final_payload.get("subagent_tool_results") or []:
        if not isinstance(item, dict):
            continue
        result_ref = _artifact_ref_dict(
            item.get("result_ref"),
            ref_type="result",
            label=f"数据集 {item.get('dataset_id')} 查询结果"
            if item.get("dataset_id") is not None
            else "查询结果",
        )
        if result_ref:
            refs.append(result_ref)
        report_ref = _artifact_ref_dict(
            item.get("report_ref"),
            ref_type="report",
            label=f"数据集 {item.get('dataset_id')} 报告占位"
            if item.get("dataset_id") is not None
            else "报告占位",
        )
        if report_ref:
            refs.append(report_ref)
    seen: set[str] = set()
    unique_refs: list[dict] = []
    for ref in refs:
        ref_id = ref.get("ref_id")
        if ref_id and ref_id not in seen:
            seen.add(ref_id)
            unique_refs.append(ref)
    return unique_refs


def _checkpoint_ref_from_payload(final_payload: dict) -> str | None:
    checkpoint = final_payload.get("retry_checkpoint")
    if not isinstance(checkpoint, dict):
        return None
    return _safe_public_ref_value(checkpoint.get("checkpoint_ref"))


def _build_related_artifact_refs(final_payload: dict, primary_ref: dict | None) -> list[dict]:
    """收集 trace/report/checkpoint 等相关引用，保持 raw SQL/raw result 不出现在引用层。"""

    primary_id = primary_ref.get("ref_id") if isinstance(primary_ref, dict) else None
    related: list[dict] = [
        ref for ref in _iter_result_refs_from_payload(final_payload) if ref.get("ref_id") != primary_id
    ]
    trace_id = (
        final_payload.get("trace_id")
        or final_payload.get("langfuse_trace_id")
        or (final_payload.get("response_metadata") or {}).get("trace_id")
    )
    if trace_id:
        trace_ref = _artifact_ref_dict(f"trace:{trace_id}", ref_type="trace", label="Langfuse Trace")
        if trace_ref:
            related.append(trace_ref)
    checkpoint_ref = _checkpoint_ref_from_payload(final_payload)
    if checkpoint_ref:
        related.append(
            ArtifactRef(
                ref_id=checkpoint_ref,
                ref_type="checkpoint",
                label="重试 checkpoint",
            ).model_dump(mode="json", exclude_none=True)
        )
    repair_plan_ref = _artifact_ref_dict(
        final_payload.get("repair_plan_ref"),
        ref_type="repair_plan",
        label="RepairPlan",
    )
    if repair_plan_ref:
        related.append(repair_plan_ref)  # RepairPlan 只作为 artifact:<uuid> 引用暴露，不泄露 patch 主体。
    seen: set[str] = set()
    deduped: list[dict] = []
    for ref in related:
        ref_id = ref.get("ref_id")
        if ref_id and ref_id not in seen:
            seen.add(ref_id)
            deduped.append(ref)
    return deduped


def _final_payload_task_id(final_payload: dict) -> str:
    """生成稳定 task_id，让页面、SSE、trace 和 artifact refs 可以互相对齐。"""

    existing = str(final_payload.get("task_id") or "").strip()
    if existing:
        return existing
    conversation_id = final_payload.get("conversation_id") or "unknown"
    message_id = final_payload.get("message_id") or "pending"
    return f"conv-{conversation_id}-msg-{message_id}"


def _build_artifact_card(final_payload: dict, primary_ref: dict, related_refs: list[dict]) -> dict:
    """构造用户可见产物卡；第一阶段只暴露摘要、引用和安全动作。"""

    checkpoint_ref = _checkpoint_ref_from_payload(final_payload)
    retry_action = ArtifactAction(
        action_id="retry",
        label="重试",
        enabled=bool(checkpoint_ref),
        disabled_reason=None if checkpoint_ref else "缺少可恢复的 checkpoint",
        payload_ref=checkpoint_ref,
    )
    card = ArtifactCard(
        artifact_type="bi_answer",
        title="BI 查询结果",
        status="error" if final_payload.get("error") else "ready",
        summary="查询产物已生成，明细通过 artifact 引用按需读取。",
        preview_payload={
            "status_label": "ready" if not final_payload.get("error") else "error",
        },
        primary_ref=primary_ref,
        related_refs=related_refs,
        actions=[
            retry_action,
            ArtifactAction(
                action_id="export",
                label="导出",
                enabled=False,
                disabled_reason="第一阶段不启动 ReportAgent 导出链路。",
            ),
            ArtifactAction(
                action_id="continue_edit",
                label="继续编辑",
                enabled=False,
                disabled_reason="第一阶段只打开详情面板，不启动 ReportAgent。",
            ),
        ],
    )
    return card.model_dump(mode="json", exclude_none=True)


def _repair_plan_summary(final_state: dict) -> dict | None:
    """提取 RepairPlan 用户可见摘要；字段级 action 只留在 artifact 内部和 trace-only 面。"""

    summary = final_state.get("repair_plan_summary")
    return summary if isinstance(summary, dict) else None


def _ensure_repair_plan_artifact(
    *,
    final_state: dict,
    artifact_store: ArtifactStore,
    dataset_id: int | None,
    conversation_id: int | None,
    trace_id: str | None,
    checkpoint_ref: str | None = None,
) -> dict | None:
    """把 RepairPlan 内部主体保存为 artifact，并把用户可见面收敛为安全摘要/ref。"""

    if final_state.get("repair_plan_ref") and _repair_plan_summary(final_state):
        return _repair_plan_summary(final_state)
    raw_plan = final_state.get("repair_plan")
    if not isinstance(raw_plan, dict):
        return None
    try:
        plan = RepairPlan(**raw_plan)
    except Exception as exc:  # noqa: BLE001
        logger.warning("RepairPlan 解析失败，跳过 artifact 持久化: %s", exc)
        return None

    artifact_payload = plan.model_dump(mode="json")
    # 先保存内部主体，拿到 artifact:<uuid> 后再回填 ref；读取 API 会脱敏 action 主体。
    repair_plan_ref = artifact_store.put_json(
        kind="repair_plan",
        payload=artifact_payload,
        dataset_id=dataset_id,
        conversation_id=conversation_id,
        trace_id=trace_id,
    )
    safe_summary = sanitize_repair_plan_for_artifact(
        plan,
        repair_plan_ref=repair_plan_ref,
        checkpoint_ref=checkpoint_ref,
        trace_id=trace_id,
        attempts=int(final_state.get("repair_attempts") or plan.attempts or 0),
    )
    artifact = artifact_store.get(repair_plan_ref)
    if artifact is not None and isinstance(artifact.content_json, dict):
        artifact.content_json.update(safe_summary)  # 回填 ref 和脱敏摘要，便于 Artifact API 直接读取。
        artifact_store.db.add(artifact)
        artifact_store.db.flush()
    final_state["repair_plan_ref"] = repair_plan_ref
    final_state["repair_plan_summary"] = safe_summary
    final_state["repair_failure_class"] = safe_summary.get("failure_class")
    final_state["repair_status"] = final_state.get("repair_status") or safe_summary.get("status")
    final_state["repair_attempts"] = safe_summary.get("attempts")
    final_state["repair_requires_user_confirmation"] = safe_summary.get(
        "requires_user_confirmation"
    )
    return safe_summary


def _repair_event_payload(
    *,
    final_state: dict,
    status: str,
    summary: dict | None = None,
) -> dict:
    """构造 repair.* 用户可见事件 payload，只包含业务摘要、状态和引用。"""

    safe = dict(summary or _repair_plan_summary(final_state) or {})
    return {
        "summary": safe.get("business_summary")
        or "已评估查询失败原因，正在尝试自动修复。",
        "status": status,
        "requires_user_confirmation": bool(
            safe.get("requires_user_confirmation")
            or final_state.get("repair_requires_user_confirmation")
        ),
        "repair_plan_ref": final_state.get("repair_plan_ref") or safe.get("repair_plan_ref"),
        "checkpoint_ref": safe.get("checkpoint_ref"),
    }


def _attach_artifact_card_refs_to_final_payload(
    final_payload: dict,
    *,
    include_card: bool = True,
) -> None:
    """把 final payload 补齐 C-ready refs；没有查询产物时不伪造 ArtifactCard。"""

    task_id = _final_payload_task_id(final_payload)
    trace_id = final_payload.get("trace_id") or final_payload.get("langfuse_trace_id")
    final_payload["task_id"] = task_id
    final_payload["trace_id"] = trace_id
    result_refs = _iter_result_refs_from_payload(final_payload)
    primary_ref = result_refs[0] if result_refs else None
    related_refs = _build_related_artifact_refs(final_payload, primary_ref)
    final_payload["primary_ref"] = primary_ref
    final_payload["related_refs"] = related_refs
    final_payload["artifact_card"] = (
        _build_artifact_card(final_payload, primary_ref, related_refs)
        if include_card and primary_ref
        else None
    )
    response_metadata = final_payload.setdefault("response_metadata", {})
    if isinstance(response_metadata, dict):
        response_metadata["task_id"] = task_id
        response_metadata["trace_id"] = trace_id
        response_metadata["primary_ref"] = primary_ref
        response_metadata["related_refs"] = related_refs
        if final_payload.get("artifact_card") is not None:
            response_metadata["artifact_card"] = final_payload["artifact_card"]


def _artifact_refs_for_query_artifact(final_payload: dict) -> list[str]:
    """query_artifact 只接受 artifact:<uuid>，trace/checkpoint 不参与回填。"""

    refs: list[str] = []
    for ref in [final_payload.get("primary_ref"), *(final_payload.get("related_refs") or [])]:
        ref_id = _safe_public_ref_value(ref)
        if ref_id and ref_id.startswith("artifact:"):
            refs.append(ref_id)
    return refs


def _sync_artifact_metadata_to_assistant_message(
    *,
    db: Session,
    assistant_message: models.Message,
    final_payload: dict,
) -> None:
    """把新产物引用写回消息 metadata；旧消息不迁移、不补造 ArtifactCard。"""

    metadata = dict(assistant_message.response_metadata or {})
    for key in (
        "task_id",
        "trace_id",
        "primary_ref",
        "related_refs",
        "artifact_card",
        "retry_checkpoint",
        "repair_plan_ref",
        "repair_failure_class",
        "repair_status",
        "repair_attempts",
        "repair_requires_user_confirmation",
        "repair_plan",
    ):
        if key in final_payload:
            metadata[key] = final_payload.get(key)
    assistant_message.response_metadata = jsonable_encoder(metadata)
    final_payload["response_metadata"] = assistant_message.response_metadata
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)


def _route_decision_event_type(route_decision: dict) -> DatalogueEventType:
    """把 LeadAgent 路由决策归一到业务事件类型。"""

    decision = route_decision.get("decision")
    if decision in {"selected", "locked"}:
        return "dataset.selected"
    if decision == "ambiguous":
        return "clarification.required"
    return "error.blocked"


def _final_event_type(final_payload: dict) -> DatalogueEventType:
    """根据 final payload 选择用户可见业务事件，供 SSE 和未来 AgentScope 复用。"""

    entry_route = final_payload.get("entry_route")
    route_payload = final_payload.get("route_payload") if isinstance(final_payload, dict) else {}
    if final_payload.get("error") or entry_route in {"reject", "no_match", "turn_pending"}:
        return "error.blocked"
    if entry_route == "clarify" or (isinstance(route_payload, dict) and "clarification" in str(route_payload.get("kind") or "")):
        return "clarification.required"
    return "answer.completed"


def _step_event_type(step_payload: dict) -> DatalogueEventType:
    """将技术 step 粗粒度映射到查询生命周期事件。"""

    node = step_payload.get("node")
    status = step_payload.get("status")
    if status == "running":
        return "dataset.query.started"
    if node in {"sql_execute", "subagent_fanout"} and status == "done":
        return "dataset.query.completed"
    if node == "lead_agent_report_generator" and status == "done":
        return "answer.completed"
    return "route.started"


def _retry_sse_event(
    event_type: str,
    *,
    checkpoint_ref: str | None,
    retry_scope: str | None = None,
    reason: str | None = None,
) -> dict:
    """构造 retry 业务事件，只暴露 checkpoint_ref 与降级原因。"""

    payload = {
        "type": event_type,
        "checkpoint_ref": checkpoint_ref,
    }
    if retry_scope:
        payload["retry_scope"] = retry_scope
    if reason:
        payload["reason"] = reason
    return _sse_data(payload)


def _chat_stream_log_summary(payload: dict | None) -> dict[str, Any]:
    """提取 /chat/stream 排障日志中的稳定关键字段，避免日志被完整 payload 淹没。"""

    payload = payload or {}
    # final / subagent result payload 很大，只保留能对齐 Network、Langfuse 和后端状态的字段。
    query_plan = payload.get("query_plan") if isinstance(payload.get("query_plan"), dict) else {}
    sql_list = payload.get("sql_list") if isinstance(payload.get("sql_list"), list) else []
    answer = payload.get("answer")
    error = payload.get("error")
    return {
        "payload_type": payload.get("type"),
        "conversation_id": payload.get("conversation_id"),
        "message_id": payload.get("message_id"),
        "result_ref": payload.get("result_ref"),
        "report_ref": payload.get("report_ref"),
        "langfuse_trace_id": payload.get("langfuse_trace_id"),
        "langfuse_session_id": payload.get("langfuse_session_id"),
        "entry_route": payload.get("entry_route"),
        "entry_reason": payload.get("entry_reason"),
        "query_plan_type": query_plan.get("query_type"),
        "planner_source": query_plan.get("planner_source"),
        "fallback_reason": query_plan.get("fallback_reason"),
        "has_sql": bool(payload.get("sql")) or bool(sql_list),
        "sql_count": len(sql_list),
        "has_error": bool(error),
        "error": str(error)[:500] if error else None,
        "answer_len": len(str(answer)) if answer is not None else 0,
    }


def _log_chat_stream_checkpoint(checkpoint: str, **fields: Any) -> None:
    """统一 /chat/stream 行级日志格式，便于按 checkpoint 串起一次请求。"""

    # checkpoint 用作 grep 入口，fields 保持 JSON，方便后续脚本化比对同一轮问数。
    logger.info(
        "[chat.stream.%s] %s",
        checkpoint,
        json.dumps(jsonable_encoder(fields), ensure_ascii=False, default=str),
    )


def _subagent_event_type(sub_event: Any) -> str:
    if isinstance(sub_event, dict):
        return str(sub_event.get("event_type") or "")
    return str(getattr(sub_event, "event_type", ""))


def _subagent_event_payload(sub_event: Any) -> dict:
    if isinstance(sub_event, dict):
        payload = sub_event.get("payload")
        return payload if isinstance(payload, dict) else {}
    payload = getattr(sub_event, "payload", None)
    return payload if isinstance(payload, dict) else {}


def _subagent_event_to_sse_payload(sub_event: Any) -> dict:
    if hasattr(sub_event, "to_sse_payload"):
        return sub_event.to_sse_payload()
    payload = _subagent_event_payload(sub_event)
    return jsonable_encoder({**payload, "type": _subagent_event_type(sub_event)})


def _is_state_output(value: dict) -> bool:
    """判断字典是否像 AgentState 节点输出。"""
    return bool(_STATE_OUTPUT_KEYS.intersection(value.keys()))


def _find_state_output(value: object, lg_node: str = "", depth: int = 0) -> dict:
    """递归查找 LangGraph/LCEL 事件中的 AgentState 输出片段。"""
    if depth > 5 or not isinstance(value, dict):
        return {}

    if lg_node and isinstance(value.get(lg_node), dict):
        nested = _find_state_output(value[lg_node], lg_node, depth + 1)
        return nested or value[lg_node]

    if _is_state_output(value):
        return value

    for key in ("output", "__end__", "state", "result"):
        nested = _find_state_output(value.get(key), lg_node, depth + 1)
        if nested:
            return nested

    if len(value) == 1:
        nested = _find_state_output(next(iter(value.values())), lg_node, depth + 1)
        if nested:
            return nested

    return {}


def _extract_node_output(event: dict, lg_node: str) -> dict:
    """从 LangGraph 事件中提取当前节点的真实输出。

    astream_events(version="v2") 在不同 LangGraph 版本/事件层级下可能返回两类结构：
    1. {"output": {"entry_intent": "..."}}
    2. {"output": {"entry_intent_classification": {"entry_intent": "..."}}}
    前端 step 事件需要的是节点真实输出，而不是外层节点名包装。
    """
    return _find_state_output(event.get("data", {}).get("output", {}) or {}, lg_node)


@asynccontextmanager
async def _managed_subagent_events(
    *,
    db: Session,
    dataset_id: int,
    request: DatasetSubAgentRequest,
    trace_context: Any,
    initial_state: dict,
    route_decision: dict,
    app_graph: Any,
):
    """管理 SubAgent 事件流生命周期，remote 模式下自动关闭 httpx client。"""

    dataset_name = route_decision.get("dataset_name") or ""
    if getattr(get_settings(), "SUBAGENT_RUNNER_MODE", "in_process") == "remote":
        runner = RemoteDatasetSubAgentRunner()
        try:
            yield runner.run(
                request,
                trace_context,
                initial_state,
                dataset_name=dataset_name,
                version="v2",
            )
        finally:
            await runner.aclose()
    else:
        sub_agent = DatasetSubAgent(db=db, dataset_id=dataset_id)
        yield sub_agent.run(
            request,
            trace_context,
            graph=app_graph,
            initial_state=initial_state,
            graph_kwargs={
                "dataset_name": dataset_name,
                "version": "v2",
            },
        )


async def _collect_subagent_final_state(
    *,
    db: Session,
    dataset_id: int,
    request: DatasetSubAgentRequest,
    trace_context: Any,
    initial_state: dict,
    route_decision: dict,
    app_graph: Any,
) -> dict:
    """fan-out 子调用专用：运行 SubAgent 并只收集完成态，不暴露子流式事件。"""

    final_state = dict(initial_state)
    async with _managed_subagent_events(
        db=db,
        dataset_id=dataset_id,
        request=request,
        trace_context=trace_context,
        initial_state=initial_state,
        route_decision=route_decision,
        app_graph=app_graph,
    ) as subagent_events:
        async for sub_event in subagent_events:
            sub_event_type = _subagent_event_type(sub_event)
            sub_event_payload = _subagent_event_payload(sub_event)
            if sub_event_type == "result":
                final_state.update(sub_event_payload.get("final_state") or {})
                continue
            if sub_event_type == "candidate_assets":
                sse_payload = _subagent_event_to_sse_payload(sub_event)
                final_state["candidate_assets"] = sse_payload.get("candidate_assets")
                continue
            if sub_event_type == "query_plan":
                sse_payload = _subagent_event_to_sse_payload(sub_event)
                final_state["query_plan"] = sse_payload.get("query_plan") or {}
                continue
            if sub_event_type == "graph_event":
                event = sub_event_payload.get("event") or {}
                output = _extract_node_output(
                    event,
                    str((event.get("metadata") or {}).get("langgraph_node") or ""),
                )
                if output:
                    final_state.update(output)
    return final_state


def _term_candidate_display(candidate: dict, term: models.BusinessTerm | None = None) -> dict:
    """归一化术语候选展示字段，兼容历史 payload 和前端字段命名。"""

    name = (
        candidate.get("name")
        or candidate.get("term_name")
        or candidate.get("termName")
        or (term.name if term else None)
    )
    display_name = (
        candidate.get("display_name")
        or candidate.get("displayName")
        or candidate.get("label")
        or candidate.get("title")
        or (term.display_name if term else None)
        or name
    )
    return {
        **candidate,
        "name": name,
        "display_name": display_name,
        "definition": candidate.get("definition") or (term.definition if term else None),
        "term_type": candidate.get("term_type")
        or candidate.get("termType")
        or (term.term_type if term else None),
        "aliases": candidate.get("aliases") or (term.aliases if term else []),
    }


def _business_term_by_id(db: Session | None, term_id: object) -> models.BusinessTerm | None:
    """按候选 term_id 回查业务术语，历史 payload 不合法时静默降级。"""

    if not db or term_id is None:
        return None
    try:
        return db.get(models.BusinessTerm, int(term_id))
    except (TypeError, ValueError):
        return None


def _term_conflict_candidates(route_payload: dict, db: Session | None = None) -> list[dict]:
    """从术语冲突 payload 里整理可展示候选。"""
    existing = route_payload.get("candidates")
    if existing:
        candidates: list[dict] = []
        for index, candidate in enumerate(existing, start=1):
            if not isinstance(candidate, dict):
                continue
            term_id = candidate.get("term_id") or candidate.get("id")
            term = _business_term_by_id(db, term_id)
            normalized = _term_candidate_display(candidate, term)
            normalized["index"] = normalized.get("index") or index
            candidates.append(normalized)
        return candidates
    candidates: list[dict] = []
    seen: set[int] = set()
    for conflict in route_payload.get("conflicts") or []:
        token = conflict.get("token")
        for term in conflict.get("terms") or []:
            term_id = term.get("id") or term.get("term_id")
            if term_id is None or term_id in seen:
                continue
            seen.add(term_id)
            db_term = _business_term_by_id(db, term_id)
            candidates.append(
                _term_candidate_display(
                    {
                        "index": len(candidates) + 1,
                        "term_id": term_id,
                        "name": term.get("name"),
                        "display_name": term.get("display_name") or term.get("name"),
                        "definition": term.get("definition"),
                        "term_type": term.get("term_type"),
                        "aliases": term.get("aliases") or [],
                        "matched_text": token,
                    },
                    db_term,
                )
            )
    return candidates


def _ensure_pending_term_clarification(
    db: Session,
    *,
    conversation_id: int,
    dataset_id: int | None,
    question: str,
    route_payload: dict,
) -> dict:
    """为术语冲突创建 pending clarification，并回填前端需要的字段。"""
    if route_payload.get("clarification_id"):
        return route_payload
    candidates = _term_conflict_candidates(route_payload, db)
    expires_at = datetime.utcnow() + timedelta(minutes=TERM_CLARIFICATION_TTL_MINUTES)
    pending = models.PendingClarification(
        conversation_id=conversation_id,
        dataset_id=dataset_id,
        clarification_type="term_conflict",
        status="pending",
        original_question=question,
        conflict_payload=jsonable_encoder(route_payload),
        candidates=jsonable_encoder(candidates),
        expires_at=expires_at,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    enriched = dict(route_payload)
    enriched.update(
        {
            "clarification_id": pending.id,
            "candidates": candidates,
            "expires_at": expires_at.isoformat(),
        }
    )
    return enriched


def _route_decision_event(route_decision: dict) -> dict:
    """整理路由决策 SSE 事件，供前端和审计复用。"""

    return {
        "type": "route_decision",
        "decision": route_decision.get("decision"),
        "dataset_id": route_decision.get("dataset_id"),
        "dataset_name": route_decision.get("dataset_name"),
        "manifest_version": route_decision.get("manifest_version"),
        "bound_schema_version": route_decision.get("bound_schema_version"),
        "score": route_decision.get("score"),
        "candidates": route_decision.get("candidates") or [],
        "reason": route_decision.get("reason"),
    }


def _report_control_for_route(route_decision: dict, payload_dataset_id: int | None) -> dict:
    """根据路由来源决定报告生成归属。"""

    auto_routed = route_decision.get("decision") == "selected" and payload_dataset_id is None
    return {
        "skip_subagent_report": auto_routed,
        "report_owner": "lead_agent" if auto_routed else "subagent",
        "subagent_report_skipped": False,
        "lead_agent_report": {"generated": False},
    }


def _should_generate_lead_agent_report(final_state: dict) -> bool:
    """工作流结束后判断是否由 LeadAgent 接管报告生成。"""

    if final_state.get("report_owner") != "lead_agent":
        return False
    if not final_state.get("skip_subagent_report"):
        return False
    if final_state.get("answer"):
        return False
    if final_state.get("error"):
        return False
    return final_state.get("sql_result") is not None


def _multiturn_observability_metrics(
    *,
    lead_agent_context: dict,
    final_state: dict,
) -> dict:
    """整理多轮链路轻量指标，供 trace metadata 后续聚合。"""

    classification = lead_agent_context.get("multiturn_classification") or {}
    prior_capsule_status = final_state.get("prior_capsule_status") or {}
    multiturn_context = final_state.get("multiturn_context") or {}
    merge_debug = final_state.get("merge_debug") or {}
    blueprint_shortcut = multiturn_context.get("blueprint_shortcut") or {}
    capsule_status = prior_capsule_status.get("status")
    return {
        "turn_intent": classification.get("intent"),
        "turn_confidence": classification.get("confidence"),
        "turn_classifier_source": classification.get("source"),
        "continued_with_active_dataset": bool(classification.get("should_inherit_dataset")),
        "delta_type": multiturn_context.get("delta_type")
        or (multiturn_context.get("delta") or {}).get("delta_type"),
        "delta_operations": (multiturn_context.get("delta") or {}).get("operations") or [],
        "delta_merge_used_prior": bool(merge_debug.get("used_prior")),
        "delta_merge_conflict": merge_debug.get("reason")
        == "merged_metrics_empty_downgraded_to_new_query",
        "blueprint_shortcut_candidate": bool(blueprint_shortcut),
        "blueprint_shortcut_hit": final_state.get("entry_route") == "analysis_blueprint"
        and bool(blueprint_shortcut),
        "capsule_status": capsule_status,
        "capsule_invalidated": capsule_status in {"invalid", "stale"},
    }


_BUSINESS_STAGE_META = {
    "understand": {
        "name": "理解问题与上下文",
        "nodes": {
            "merge_prior_context",
            "clarification_resolution",
            "intent_recognition",
            "entry_intent_classification",
        },
    },
    "route": {
        "name": "选择数据集与分析路径",
        "nodes": {"analysis_blueprint_execute"},
    },
    "semantic": {
        "name": "确认业务口径",
        "nodes": {
            "schema_recall",
            "term_conflict_resolve",
            "metric_resolve",
        },
    },
    "plan_query": {
        "name": "生成查询计划",
        "nodes": {"dsl_generate", "dsl_validate", "dsl_compiler"},
    },
    "execute_query": {
        "name": "执行查询与诊断",
        "nodes": {"sql_execute", "sql_audit"},
    },
    "narrate": {
        "name": "生成业务回答",
        "nodes": {"report_generator", "lead_agent_report_generator"},
    },
}


def _business_stage_for_node(node: str | None) -> str:
    """将技术节点归并为前端右侧展示用的业务阶段。"""

    if not node:
        return "other"
    for stage_key, stage_meta in _BUSINESS_STAGE_META.items():
        if node in stage_meta["nodes"]:
            return stage_key
    return "other"


def _row_count(sql_result: dict | None) -> int | None:
    """从 SQL 执行结果中稳定提取行数。"""

    if not isinstance(sql_result, dict):
        return None
    if sql_result.get("row_count") is not None:
        return sql_result.get("row_count")
    rows = sql_result.get("rows")
    if isinstance(rows, list):
        return len(rows)
    return None


def _last_step_elapsed_ms(step_traces: list[dict], *nodes: str) -> int | None:
    """读取最后一个指定节点的耗时，避免前端从 step_trace 自行推断。"""

    node_set = set(nodes)
    for step in reversed(step_traces or []):
        if step.get("node") in node_set and step.get("elapsed_ms") is not None:
            return step.get("elapsed_ms")
    return None


def _business_execution_stages(step_traces: list[dict]) -> list[dict]:
    """把 step_trace 压缩成业务化执行阶段，完整 trace 仍保留在 step_trace。"""

    stages: dict[str, dict] = {}
    for step in step_traces or []:
        node = step.get("node")
        stage_key = _business_stage_for_node(node)
        stage_meta = _BUSINESS_STAGE_META.get(stage_key, {"name": "其他处理", "nodes": set()})
        stage = stages.setdefault(
            stage_key,
            {
                "key": stage_key,
                "name": stage_meta["name"],
                "status": "pending",
                "elapsed_ms": 0,
                "nodes": [],
            },
        )
        if node and node not in stage["nodes"]:
            stage["nodes"].append(node)
        status = step.get("status")
        if status:
            stage["status"] = status
        if step.get("elapsed_ms") is not None:
            stage["elapsed_ms"] += int(step.get("elapsed_ms") or 0)

    ordered_keys = [*list(_BUSINESS_STAGE_META.keys()), "other"]
    return [stages[key] for key in ordered_keys if key in stages]


def _build_query_profile(
    *,
    final_state: dict,
    lead_agent_context: dict,
    route_decision: dict,
    step_traces: list[dict],
    sql: str | None,
    sql_list: list,
    execution_path: str,
    effective_dataset_id: int | None,
) -> dict:
    """构建前端口径卡片和执行摘要的稳定结构。"""

    sql_result = final_state.get("sql_result") if isinstance(final_state, dict) else None
    if not isinstance(sql_result, dict):
        sql_result = {}
    multiturn_context = final_state.get("multiturn_context") or {}
    multiturn_fast_path = final_state.get("multiturn_fast_path") or {}
    delta = multiturn_context.get("delta") or {}
    merge_debug = final_state.get("merge_debug") or {}
    prior_capsule_status = final_state.get("prior_capsule_status") or {}
    row_count = _row_count(sql_result)
    columns = sql_result.get("columns") or []
    sql_elapsed_ms = _last_step_elapsed_ms(
        step_traces,
        "sql_execute",
        "analysis_blueprint_execute",
    )
    stages = _business_execution_stages(step_traces)
    total_elapsed_ms = sum(int(stage.get("elapsed_ms") or 0) for stage in stages)
    inherited = bool(
        merge_debug.get("used_prior")
        or final_state.get("turn_type") in {"continue", "follow_up"}
        or prior_capsule_status.get("status") == "loaded"
    )

    return {
        "version": "v1",
        "question": {
            "original": final_state.get("original_question")
            or lead_agent_context.get("original_question"),
            "resolved": final_state.get("resolved_question")
            or lead_agent_context.get("resolved_question"),
        },
        "route": {
            "execution_path": execution_path,
            "entry_intent": final_state.get("entry_intent"),
            "entry_route": final_state.get("entry_route"),
            "entry_reason": final_state.get("entry_reason"),
            "decision": route_decision.get("decision"),
            "dataset_id": route_decision.get("dataset_id") or effective_dataset_id,
            "dataset_name": route_decision.get("dataset_name"),
            "manifest_version": route_decision.get("manifest_version"),
            "bound_schema_version": route_decision.get("bound_schema_version"),
            "blueprint_id": final_state.get("blueprint_id"),
            "blueprint_match": final_state.get("blueprint_match"),
            "route_payload_kind": (final_state.get("route_payload") or {}).get("kind"),
        },
        "query_context": {
            "time_context": final_state.get("time_context")
            or lead_agent_context.get("time_context"),
            "query_constraints": final_state.get("query_constraints"),
            "merged_query_context": multiturn_context.get("merged_query_context"),
            "prior_query_context": multiturn_context.get("prior_query_context"),
            "delta": delta or None,
            "delta_type": multiturn_context.get("delta_type") or delta.get("delta_type"),
            "inheritance": {
                "inherited": inherited,
                "turn_type": final_state.get("turn_type") or multiturn_context.get("turn_type"),
                "prior_capsule_status": prior_capsule_status,
                "merge_debug": merge_debug,
                "operations": delta.get("operations") or [],
                "fast_path": multiturn_fast_path,
            },
        },
        "semantic": {
            "term_normalization": final_state.get("term_normalization"),
            "semantic_asset_resolution": final_state.get("semantic_asset_resolution"),
            "metric_resolution": final_state.get("metric_resolution"),
            "dataset_context_debug": final_state.get("dataset_context_debug"),
            "schema_status": lead_agent_context.get("schema_status"),
        },
        "sql": {
            "text": sql,
            "statements": sql_list,
            "row_count": row_count,
            "columns": columns,
            "elapsed_ms": sql_elapsed_ms,
            "generation_mode": final_state.get("generation_mode"),
            "diagnosis": final_state.get("sql_diagnosis") or final_state.get("sql_audit_result"),
            "retry_trace": final_state.get("sql_retry_trace") or [],
            "result_artifact": final_state.get("result_artifact"),
        },
        "execution_summary": {
            "elapsed_ms": total_elapsed_ms,
            "stages": stages,
            "report_owner": final_state.get("report_owner"),
            "subagent_report_skipped": final_state.get("subagent_report_skipped"),
            "lead_agent_report": final_state.get("lead_agent_report"),
        },
    }


def _build_explainability(
    *,
    query_profile: dict,
    answer_explanation: dict | None = None,
) -> dict:
    """统一对外可解释性结构，避免前端依赖分散字段。"""

    return {
        "version": "v1",
        "query_profile": query_profile,
        "answer_explanation": answer_explanation or {},
    }


def _lead_agent_event(lead_agent_context: dict) -> dict:
    """整理 LeadAgent 控制面工具执行摘要，供前端调试和审计使用。"""

    return {
        "type": "lead_agent_tools",
        "time_context": lead_agent_context.get("time_context"),
        "thread_context": lead_agent_context.get("thread_context"),
        "route_decision": lead_agent_context.get("route_decision"),
        "schema_status": lead_agent_context.get("schema_status"),
        "clarification": lead_agent_context.get("clarification"),
        "audit_trace": lead_agent_context.get("audit_trace"),
        "tool_policy": lead_agent_context.get("tool_policy"),
        "original_question": lead_agent_context.get("original_question"),
        "resolved_question": lead_agent_context.get("resolved_question"),
        "multiturn_refinement": lead_agent_context.get("multiturn_refinement"),
        "selected_skills": lead_agent_context.get("selected_skills") or [],
        "planned_tool_calls": lead_agent_context.get("planned_tool_calls") or [],
        "executed_tool_calls": lead_agent_context.get("executed_tool_calls") or [],
        "system_inferred_tool_calls": lead_agent_context.get("system_inferred_tool_calls") or [],
        "progressive_disclosure": lead_agent_context.get("progressive_disclosure"),
        "disclosed_tools": lead_agent_context.get("disclosed_tools") or [],
        "skill_selection_reasoning_summary": lead_agent_context.get(
            "skill_selection_reasoning_summary"
        ),
        "tool_planning_reasoning_summary": lead_agent_context.get(
            "tool_planning_reasoning_summary"
        ),
        "policy_violations": lead_agent_context.get("policy_violations") or [],
        "planner_fallback": lead_agent_context.get("planner_fallback"),
        "fallback_reason": lead_agent_context.get("fallback_reason"),
        "planner_reasoning_summary": lead_agent_context.get("planner_reasoning_summary"),
        "should_continue": lead_agent_context.get("should_continue"),
    }


def _route_block_answer(route_decision: dict) -> str:
    """路由不明确时生成可直接展示给用户的解释。"""

    candidates = route_decision.get("candidates") or []
    if route_decision.get("decision") == "ambiguous":
        lines = ["我找到了多个可能的数据集，需要你先确认使用哪一个："]
        for index, item in enumerate(candidates[:3], start=1):
            name = item.get("dataset_name") or f"数据集 {item.get('dataset_id')}"
            confidence = item.get("confidence", 0)
            reason = item.get("reason")  # Capability Router 候选已瘦身，只展示可暴露摘要。
            lines.append(
                f"{index}. {name}（置信度 {confidence}）{('：' + reason) if reason else ''}"
            )
        lines.append("请选择数据集后再继续提问。")
        return "\n".join(lines)

    if candidates:
        top = candidates[0]
        name = top.get("dataset_name") or f"数据集 {top.get('dataset_id')}"
        return (
            "当前问题没有命中足够明确的 SubAgent Manifest，暂时不自动选择数据集。"
            f"最接近的是 {name}（置信度 {top.get('confidence', 0)}），但未达到自动路由阈值。"
            "你可以手动选择数据集，或补充更具体的指标、维度、时间范围。"
        )
    return "当前没有可用于自动路由的 current SubAgent Manifest，请先选择数据集或发布 Manifest 后再提问。"


def _coerce_int(value: object) -> int | None:
    """把会话状态中的 dataset_id 兼容转成 int，无法转换时返回 None。"""

    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_dataset_by_name(db: Session, dataset_name: str) -> models.SemanticDataset | None:
    """按展示名称查找数据集，供 Message Gateway 的选择事件使用。"""

    name = (dataset_name or "").strip()
    if not name:
        return None
    return (
        db.query(models.SemanticDataset)
        .filter(models.SemanticDataset.name == name)
        .order_by(models.SemanticDataset.id.asc())
        .first()
    )


def _current_manifest_versions(db: Session, dataset_id: int | None) -> dict[str, str | None]:
    """读取当前数据集 manifest 版本，用于 Message Gateway 前的继承预校验。"""

    if dataset_id is None:
        return {"manifest_version": None, "schema_version": None}
    manifest = (
        db.query(models.DatasetSubAgentManifest)
        .filter(
            models.DatasetSubAgentManifest.dataset_id == dataset_id,
            models.DatasetSubAgentManifest.is_current.is_(True),
        )
        .order_by(models.DatasetSubAgentManifest.created_at.desc())
        .first()
    )
    if manifest is None:
        return {"manifest_version": None, "schema_version": None}
    return {
        "manifest_version": manifest.manifest_version,
        "schema_version": manifest.bound_schema_version,
    }


def _thread_last_success_task(multiturn_context: dict | None) -> dict | None:
    context = multiturn_context or {}
    task = context.get("last_success_task")
    return task if isinstance(task, dict) else None


def _has_last_success_task(
    multiturn_context: dict | None,
    last_success_task_status: dict | None = None,
) -> bool:
    """判断当前线程是否有可承接的上一轮成功查询。"""

    if isinstance(last_success_task_status, dict):
        return last_success_task_status.get("status") == "loaded"
    return has_query_target(_thread_last_success_task(multiturn_context))


def _summarize_last_success_task(task: dict | None) -> dict:
    """生成 last_success_task 日志摘要，避免输出完整 SQL、结果集或大字段。"""

    if not isinstance(task, dict):
        return {"present": False}
    selected_fields = task.get("selected_field_refs") or task.get("fields") or []
    filters = task.get("filters_applied") or task.get("filters") or []
    metrics = task.get("metrics_applied") or task.get("metrics") or []
    result_digest = task.get("result_digest") if isinstance(task.get("result_digest"), dict) else {}
    return {
        "present": True,
        "query_type": task.get("query_type"),
        "dataset_id": task.get("dataset_id"),
        "schema_version": task.get("schema_version"),
        "manifest_version": task.get("manifest_version"),
        "turn_index": task.get("turn_index"),
        "main_table": task.get("main_table"),
        "has_query_target": has_query_target(task),
        "selected_field_count": len(selected_fields) if isinstance(selected_fields, list) else 0,
        "filter_count": len(filters) if isinstance(filters, list) else 0,
        "metric_count": len(metrics) if isinstance(metrics, list) else 0,
        "has_blueprint_hit": bool(task.get("blueprint_hit")),
        "has_result_ref": bool(task.get("result_ref")),
        "result_row_count": result_digest.get("row_count"),
    }


def _summarize_conversation_state(
    state: models.ConversationState | None,
    *,
    lead_context: dict | None = None,
) -> dict:
    """生成 ConversationState 日志摘要，便于排查跨轮状态是否写入/读取成功。"""

    if state is None:
        return {"present": False}
    capsules = dict(state.subagent_capsules or {})
    thread_state = capsules.get(THREAD_STATE_KEY)
    thread_state = thread_state if isinstance(thread_state, dict) else {}
    context = lead_context if isinstance(lead_context, dict) else {}
    task = context.get("last_success_task") or thread_state.get("last_success_task")
    messages = state.messages if isinstance(state.messages, list) else []
    capsule_metas = context.get("capsule_metas") if isinstance(context, dict) else None
    return {
        "present": True,
        "session_id": state.session_id,
        "user_id": state.user_id,
        "turn_index": state.turn_index,
        "active_dataset_id": state.active_dataset_id,
        "message_count": len(messages),
        "has_summary": bool(state.compacted_summary),
        "pending_clarification_kind": (
            state.pending_clarification.get("kind")
            if isinstance(state.pending_clarification, dict)
            else None
        ),
        "thread_keys": sorted(thread_state.keys()),
        "last_success_task_write_status": thread_state.get("last_success_task_write_status"),
        "last_success_task": _summarize_last_success_task(task),
        "capsule_meta_keys": (
            sorted(capsule_metas.keys())
            if isinstance(capsule_metas, dict)
            else sorted(k for k in capsules.keys() if k != THREAD_STATE_KEY)
        ),
    }


def _gateway_lead_context(
    *,
    payload: schemas.ChatRequest,
    route_decision: dict,
    multiturn_context: dict | None,
) -> dict:
    """构造早退分支需要的最小 LeadAgent 上下文，避免触发 LeadAgent 路由。"""

    return {
        "route_decision": route_decision,
        "schema_status": {},
        "time_context": {},
        "thread_context": multiturn_context or {},
        "clarification": None,
        "audit_trace": [],
        "tool_policy": {},
        "original_question": payload.question,
        "resolved_question": payload.question,
        "selected_skills": [],
        "planned_tool_calls": [],
        "executed_tool_calls": [],
        "system_inferred_tool_calls": [],
        "progressive_disclosure": None,
        "disclosed_tools": [],
        "skill_selection_reasoning_summary": None,
        "tool_planning_reasoning_summary": None,
        "policy_violations": [],
        "planner_fallback": None,
        "fallback_reason": None,
        "planner_reasoning_summary": None,
        "should_continue": False,
    }


def _gateway_route_decision(
    *,
    turn_event: dict,
    dataset: models.SemanticDataset | None,
    effective_dataset_id: int | None,
) -> dict:
    """把 Message Gateway 事件映射到现有 route_decision 结构。"""

    event_type = turn_event.get("event_type")
    if event_type == "dataset_select" and dataset is not None:
        return {
            "decision": "selected",
            "dataset_id": int(dataset.id),
            "dataset_name": dataset.name,
            "score": 1.0,
            "reason": "message_gateway_dataset_select",
        }
    return {
        "decision": "blocked",
        "dataset_id": effective_dataset_id,
        "dataset_name": turn_event.get("dataset_name"),
        "score": None,
        "reason": f"message_gateway_{event_type}",
    }


def _gateway_routing(turn_event: dict, *, dataset_found: bool = True) -> dict:
    """把 Message Gateway 事件转成 _early_route_return 可复用的 routing。"""

    event_type = str(turn_event.get("event_type") or "message_gateway")
    route_payload = {
        "kind": "message_gateway",
        "event_type": event_type,
        "turn_event": turn_event,
    }
    answer = turn_event.get("answer")
    entry_route = event_type
    if event_type == "dataset_select" and not dataset_found:
        dataset_name = turn_event.get("dataset_name") or "指定数据集"
        answer = f"没有找到数据集「{dataset_name}」，请重新选择可用数据集。"
        entry_route = "clarify"
        route_payload["dataset_lookup"] = "not_found"
    return {
        "entry_intent": "message_gateway",
        "entry_route": entry_route,
        "entry_reason": f"message_gateway_{event_type}",
        "answer": answer or "请告诉我要查询的数据、筛选条件或分析目标。",
        "route_payload": route_payload,
        "turn_event": turn_event,
    }


def _save_route_block_message(
    db: Session,
    *,
    conv: models.Conversation,
    route_decision: dict,
    lead_agent_context: dict,
    answer: str,
) -> models.Message:
    """保存路由阻断场景的助手消息，保持会话历史完整。"""

    route_payload = {
        "kind": "manifest_route",
        "decision": route_decision.get("decision"),
        "candidates": route_decision.get("candidates") or [],
        "reason": route_decision.get("reason"),
    }
    final_state = {
        "original_question": lead_agent_context.get("original_question"),
        "resolved_question": lead_agent_context.get("resolved_question"),
        "entry_intent": "manifest_route",
        "entry_route": route_decision.get("decision"),
        "entry_reason": route_decision.get("reason"),
        "route_payload": route_payload,
        "time_context": lead_agent_context.get("time_context"),
        "sql_result": None,
    }
    query_profile = _build_query_profile(
        final_state=final_state,
        lead_agent_context=lead_agent_context,
        route_decision=route_decision,
        step_traces=[_lead_agent_event(lead_agent_context), _route_decision_event(route_decision)],
        sql=None,
        sql_list=[],
        execution_path="manifest_route",
        effective_dataset_id=route_decision.get("dataset_id"),
    )
    explainability = _build_explainability(query_profile=query_profile)
    response_metadata = jsonable_encoder(
        {
            "lead_agent_context": lead_agent_context,
            "original_question": lead_agent_context.get("original_question"),
            "resolved_question": lead_agent_context.get("resolved_question"),
            "route_decision": route_decision,
            "time_context": lead_agent_context.get("time_context"),
            "schema_status": lead_agent_context.get("schema_status"),
            "route_payload": route_payload,
            "query_profile": query_profile,
            "explainability": explainability,
        }
    )
    assistant_message = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        sql_list=[],
        step_trace=[_lead_agent_event(lead_agent_context), _route_decision_event(route_decision)],
        response_metadata=response_metadata,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return assistant_message


async def _stream_chat_singleturn(
    payload: schemas.ChatRequest,
    db: Session,
    *,
    multiturn_context: dict | None = None,
    conversation_state: models.ConversationState | None = None,
    conversation_store: ConversationStore | None = None,
    pending_resolution: dict | None = None,
    observability_session_id: str | None = None,
    trace_context_sink: list | None = None,
    subagent_control_plane_sink: list | None = None,
    defer_trace_close: bool = False,
):
    """SSE 流式问数：驱动 LangGraph 工作流，逐步发送节点进度事件。"""
    _log_chat_stream_checkpoint(  # 单轮链路入口，后续 checkpoint 都以此为起点。
        "singleturn_start",
        question_preview=payload.question[:80],
        payload_dataset_id=payload.dataset_id,
        conversation_id=payload.conversation_id,
        has_multiturn_context=bool(multiturn_context),
        has_conversation_state=conversation_state is not None,
        pending_resolution_status=(pending_resolution or {}).get("status")
        if isinstance(pending_resolution, dict)
        else None,
    )
    conv_id: int | None = payload.conversation_id
    effective_dataset_id: int | None = payload.dataset_id

    # 查找或创建对话
    if conv_id:
        conv = db.get(models.Conversation, conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        if effective_dataset_id is None:
            effective_dataset_id = conv.dataset_id
        elif conv.dataset_id != effective_dataset_id:
            conv.dataset_id = effective_dataset_id
            db.commit()
            db.refresh(conv)
        # 已存在对话的首条消息：自动用首句作为标题（避免「新对话」/空标题占位）
        existing_msg_count = (
            db.query(models.Message).filter(models.Message.conversation_id == conv_id).count()
        )
        if existing_msg_count == 0 and (not conv.title or conv.title in ("新对话", "")):
            conv.title = payload.question[:40]
            if not conv.thread_id:
                conv.thread_id = f"thread-{payload.question[:20]}"
            db.commit()
            db.refresh(conv)
    else:
        conv = models.Conversation(
            title=payload.question[:40],
            thread_id=f"thread-{payload.question[:20]}",
            user_id=1,
            dataset_id=effective_dataset_id,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conv_id = int(conv.id)

    db.add(  # 用户消息先落库，后续日志和 trace 才能稳定回查 conversation。
        models.Message(
            conversation_id=conv_id,
            role="user",
            content=payload.question,
        )
    )
    db.commit()
    _log_chat_stream_checkpoint(  # 会话和用户消息已落库，conversation_id 可用于查 DB。
        "conversation_ready",
        conversation_id=conv_id,
        effective_dataset_id=effective_dataset_id,
        conversation_dataset_id=conv.dataset_id,
        title=conv.title,
        thread_id=conv.thread_id,
    )

    if (
        isinstance(pending_resolution, dict)
        and pending_resolution.get("status") == "resolved"
        and pending_resolution.get("type") == "dataset"
    ):
        restored_question = str(pending_resolution.get("original_question") or "").strip()
        restored_dataset_id = _coerce_int(pending_resolution.get("dataset_id"))
        if restored_dataset_id is not None:
            effective_dataset_id = restored_dataset_id
            if conv.dataset_id != effective_dataset_id:
                conv.dataset_id = effective_dataset_id
                db.commit()
                db.refresh(conv)
        if restored_question:
            multiturn_context = dict(multiturn_context or {})
            multiturn_context["pending_clarification"] = None
            multiturn_context["active_dataset_id"] = effective_dataset_id
            payload = payload.model_copy(
                update={
                    "question": restored_question,
                    "dataset_id": effective_dataset_id,
                    "clarification_response": None,
                }
            )
            _log_chat_stream_checkpoint(  # dataset 澄清恢复会改写本轮问题和 dataset_id。
                "pending_dataset_restored",
                conversation_id=conv_id,
                restored_dataset_id=effective_dataset_id,
                restored_question_preview=restored_question[:80],
            )

    tracer = get_observability_tracer()
    trace_context = tracer.create_trace_context(  # 创建 Langfuse/session 上下文，后续 span 共享。
        conversation_id=conv_id,
        dataset_id=effective_dataset_id,
        user_id=str(conv.user_id or 1),
        tenant_id="default",
        question=payload.question,
        session_id=observability_session_id,
        metadata={
            "thread_id": conv.thread_id,
            "title": conv.title,
            "phase": "lead_agent",
            "business_session_id": observability_session_id,
        },
    )
    if trace_context_sink is not None:
        trace_context_sink.append(trace_context)
    obs_context_manager = set_observability_context(trace_context.request_context())
    obs_context_manager.__enter__()
    _log_chat_stream_checkpoint(  # 记录 trace/session，便于从 app.log 反查 Langfuse。
        "trace_context_created",
        conversation_id=conv_id,
        effective_dataset_id=effective_dataset_id,
        trace_id=trace_context.trace_id,
        session_id=trace_context.session_id,
        observability_enabled=trace_context.enabled,
        observability_active=trace_context.active,
    )

    tracer.start_span(
        trace_context,
        node="context-assembly",
        display_name="context-assembly",
        input_payload={
            "business_session_id": observability_session_id,
            "conversation_id": conv_id,
            "payload_dataset_id": payload.dataset_id,
            "conversation_dataset_id": conv.dataset_id,
            "has_conversation_state": conversation_state is not None,
        },
    )
    tracer.end_span(
        trace_context,
        node="context-assembly",
        output_payload={
            "active_dataset_id": (multiturn_context or {}).get("active_dataset_id"),
            "turn_index": (multiturn_context or {}).get("turn_index"),
            "pending_clarification_kind": (
                ((multiturn_context or {}).get("pending_clarification") or {}).get("kind")
                if isinstance((multiturn_context or {}).get("pending_clarification"), dict)
                else None
            ),
            "capsule_meta_count": len((multiturn_context or {}).get("capsule_metas") or {}),
            "has_summary": bool((multiturn_context or {}).get("summary")),
        },
    )

    active_dataset_id = (
        _coerce_int((multiturn_context or {}).get("active_dataset_id")) or effective_dataset_id
    )
    thread_last_success_task = _thread_last_success_task(multiturn_context)
    current_manifest_versions = _current_manifest_versions(db, active_dataset_id)
    _, last_success_task_status = evaluate_last_success_task(
        thread_last_success_task,
        active_dataset_id=active_dataset_id,
        current_schema_version=current_manifest_versions.get("schema_version"),
        current_manifest_version=current_manifest_versions.get("manifest_version"),
    )
    turn_event = classify_turn_event(
        payload.question,
        active_dataset_id=active_dataset_id,
        has_pending_clarification=bool((multiturn_context or {}).get("pending_clarification")),
        has_last_success_task=_has_last_success_task(
            multiturn_context,
            last_success_task_status,
        ),
    )
    # gateway_classified 是进入 LeadAgent 前的本地判定，常用于区分 clarify/dataset_select/继续问数。
    _log_chat_stream_checkpoint(
        "gateway_classified",
        conversation_id=conv_id,
        active_dataset_id=active_dataset_id,
        turn_event=turn_event,
        last_success_task_status=last_success_task_status,
    )
    tracer.start_span(
        trace_context,
        node="message-gateway",
        display_name="message-gateway",
        input_payload={
            "question": payload.question,
            "active_dataset_id": active_dataset_id,
            "payload_dataset_id": payload.dataset_id,
        },
        trace_tags=["gateway"],
    )
    tracer.end_span(
        trace_context,
        node="message-gateway",
        output_payload=turn_event,
    )
    if turn_event.get("event_type") == "dataset_select":
        selected_dataset = _find_dataset_by_name(db, str(turn_event.get("dataset_name") or ""))
        if selected_dataset is not None:
            effective_dataset_id = int(selected_dataset.id)
            if conv.dataset_id != effective_dataset_id:
                conv.dataset_id = effective_dataset_id
                db.commit()
                db.refresh(conv)
        route_decision = _gateway_route_decision(
            turn_event=turn_event,
            dataset=selected_dataset,
            effective_dataset_id=effective_dataset_id,
        )
        lead_agent_context = _gateway_lead_context(
            payload=payload,
            route_decision=route_decision,
            multiturn_context=multiturn_context,
        )
        async for sse_event in _early_route_return(
            db=db,
            conv=conv,
            payload=payload,
            effective_dataset_id=effective_dataset_id,
            lead_agent_context=lead_agent_context,
            route_decision=route_decision,
            trace_context=trace_context,
            defer_trace_close=defer_trace_close,
            obs_context_manager=obs_context_manager,
            routing=_gateway_routing(turn_event, dataset_found=selected_dataset is not None),
        ):
            yield sse_event
        return
    if turn_event.get("event_type") == "clarify":
        route_decision = _gateway_route_decision(
            turn_event=turn_event,
            dataset=None,
            effective_dataset_id=effective_dataset_id,
        )
        lead_agent_context = _gateway_lead_context(
            payload=payload,
            route_decision=route_decision,
            multiturn_context=multiturn_context,
        )
        async for sse_event in _early_route_return(
            db=db,
            conv=conv,
            payload=payload,
            effective_dataset_id=effective_dataset_id,
            lead_agent_context=lead_agent_context,
            route_decision=route_decision,
            trace_context=trace_context,
            defer_trace_close=defer_trace_close,
            obs_context_manager=obs_context_manager,
            routing=_gateway_routing(turn_event),
        ):
            yield sse_event
        return

    tracer.start_span(
        trace_context,
        node="lead.routing",
        display_name="lead.routing",
        input_payload={
            "question": payload.question,
            "conversation_id": conv_id,
            "payload_dataset_id": payload.dataset_id,
            "conversation_dataset_id": conv.dataset_id,
            "turn_event": turn_event,
        },
        trace_tags=["lead"],
    )
    try:
        lead_agent_context = build_lead_agent_context(
            db,
            question=payload.question,
            conversation=conv,
            payload_dataset_id=payload.dataset_id,
            multiturn_context=multiturn_context,
            tracer=tracer,
            trace_context=trace_context,
        )
    except Exception as exc:
        tracer.end_span(
            trace_context,
            node="lead.routing",
            output_payload={"status": "error", "error": str(exc)},
            error=str(exc),
        )
        raise
    tracer.start_span(
        trace_context,
        node="turn-classification",
        display_name="turn-classification",
        input_payload={
            "question": payload.question,
            "active_dataset_id": (multiturn_context or {}).get("active_dataset_id"),
            "payload_dataset_id": payload.dataset_id,
        },
    )
    tracer.end_span(
        trace_context,
        node="turn-classification",
        output_payload=lead_agent_context.get("multiturn_classification") or {},
    )
    tracer.end_span(
        trace_context,
        node="lead.routing",
        output_payload={
            "route_decision": lead_agent_context.get("route_decision"),
            "schema_status": lead_agent_context.get("schema_status"),
            "selected_skills": lead_agent_context.get("selected_skills") or [],
            "planned_tool_calls": lead_agent_context.get("planned_tool_calls") or [],
            "executed_tool_calls": lead_agent_context.get("executed_tool_calls") or [],
            "policy_violations": lead_agent_context.get("policy_violations") or [],
            "should_continue": lead_agent_context.get("should_continue"),
        },
    )
    route_decision = lead_agent_context["route_decision"]
    # LeadAgent 的 route_decision 决定是否能继续到 SubAgent，失败时先看这个 checkpoint。
    _log_chat_stream_checkpoint(
        "lead_context_ready",
        conversation_id=conv_id,
        effective_dataset_id=effective_dataset_id,
        should_continue=lead_agent_context.get("should_continue"),
        route_decision=route_decision,
        schema_status=lead_agent_context.get("schema_status"),
        selected_skills=lead_agent_context.get("selected_skills") or [],
        planned_tool_calls=lead_agent_context.get("planned_tool_calls") or [],
    )
    lead_event = _lead_agent_event(lead_agent_context)
    route_event = _route_decision_event(route_decision)
    yield _sse_data(
        _with_event_envelope(
            lead_event,
            event_type="route.started",
            visibility="trace_only",
            payload_fields=("route_decision", "schema_status", "selected_skills"),
            metadata={"conversation_id": conv_id, "dataset_id": effective_dataset_id},
        )
    )
    yield _sse_data(
        _with_event_envelope(
            route_event,
            event_type=_route_decision_event_type(route_decision),
            visibility="user_visible",
            payload_fields=("decision", "dataset_id", "dataset_name", "reason", "candidates"),
            metadata={"conversation_id": conv_id},
        )
    )

    if lead_agent_context.get("should_continue"):
        selected_dataset_id = lead_agent_context.get("effective_dataset_id")
        if selected_dataset_id is not None:
            effective_dataset_id = int(selected_dataset_id)
            if conv.dataset_id != effective_dataset_id:
                conv.dataset_id = effective_dataset_id
                db.commit()
                db.refresh(conv)
    else:
        answer = _route_block_answer(route_decision)
        assistant_message = _save_route_block_message(
            db,
            conv=conv,
            route_decision=route_decision,
            lead_agent_context=lead_agent_context,
            answer=answer,
        )
        trace_metadata = {
            "status": "blocked",
            "execution_path": "manifest_route",
            "original_question": payload.question,
            "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
            "entry_route": route_decision.get("decision"),
            "lead_agent_context": lead_agent_context,
            "route_decision": route_decision,
            "schema_status": lead_agent_context.get("schema_status"),
            "manifest_version": route_decision.get("manifest_version"),
            "bound_schema_version": route_decision.get("bound_schema_version"),
            "query_profile": (assistant_message.response_metadata or {}).get("query_profile"),
            "explainability": (assistant_message.response_metadata or {}).get("explainability"),
            "prompt_versions": trace_context.prompt_versions,
        }
        tracer.update_trace_output(trace_context, output=answer, metadata=trace_metadata)
        if trace_context.trace_id:
            db.add(
                models.ObservabilityTraceIndex(
                    langfuse_trace_id=trace_context.trace_id,
                    langfuse_session_id=trace_context.session_id,
                    conversation_id=conv_id,
                    message_id=assistant_message.id,
                    dataset_id=effective_dataset_id,
                    entry_route=route_decision.get("decision") or "manifest_route",
                    status="blocked",
                    total_tokens=0,
                    total_cost=0,
                    metadata_json=jsonable_encoder(trace_metadata),
                )
            )
            db.commit()
        if not defer_trace_close:
            tracer.close_trace(trace_context)
        obs_context_manager.__exit__(None, None, None)
        response_metadata = assistant_message.response_metadata or {}
        final_payload = {
                "type": "final",
                "sql": None,
                "sql_list": [],
                "answer": answer,
                "entry_intent": "manifest_route",
                "entry_route": route_decision.get("decision"),
                "entry_reason": route_decision.get("reason"),
                "lead_agent_context": lead_agent_context,
                "original_question": payload.question,
                "resolved_question": lead_agent_context.get("resolved_question")
                or payload.question,
                "time_context": lead_agent_context.get("time_context"),
                "route_decision": route_decision,
                "schema_status": lead_agent_context.get("schema_status"),
                "clarification": lead_agent_context.get("clarification"),
                "route_payload": response_metadata.get("route_payload"),
                "sql_result": None,
                "query_profile": response_metadata.get("query_profile"),
                "explainability": response_metadata.get("explainability"),
                "response_metadata": response_metadata,
                "conversation_id": conv.id,
                "message_id": assistant_message.id,
                "task_id": f"conv-{conv.id}-msg-{assistant_message.id}",
                "trace_id": trace_context.trace_id,
                "title": conv.title,
            }
        _attach_artifact_card_refs_to_final_payload(final_payload, include_card=False)
        _sync_artifact_metadata_to_assistant_message(
            db=db,
            assistant_message=assistant_message,
            final_payload=final_payload,
        )
        yield _sse_data(
            _with_event_envelope(
                final_payload,
                event_type="error.blocked",
                visibility="user_visible",
                payload_fields=(
                    "answer",
                    "entry_route",
                    "entry_reason",
                    "route_decision",
                    "primary_ref",
                    "related_refs",
                    "task_id",
                    "trace_id",
                ),
            )
        )
        _log_chat_stream_checkpoint(
            "lead_route_blocked",
            # manifest/schema/permission 类阻断不会进入 SubAgent，用 final 摘要统一记录可见结果。
            **_chat_stream_log_summary(
                {
                    "type": "final",
                    "answer": answer,
                    "entry_route": route_decision.get("decision"),
                    "entry_reason": route_decision.get("reason"),
                    "conversation_id": conv.id,
                    "message_id": assistant_message.id,
                    "query_plan": None,
                    "sql": None,
                    "sql_list": [],
                    "error": None,
                }
            ),
        )
        return

    # 查询历史消息（最近 6 轮，用于意图识别上下文）
    history_msgs = (
        db.query(models.Message)
        .filter(models.Message.conversation_id == conv_id)
        .order_by(models.Message.created_at.desc())
        .limit(12)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in reversed(history_msgs)]

    # 构建初始状态
    resolved_question = lead_agent_context.get("resolved_question") or payload.question
    report_control = _report_control_for_route(route_decision, payload.dataset_id)
    prior_capsule = None
    prior_capsule_status = {"status": "disabled", "reason": "multiturn_store_not_enabled"}
    if (
        conversation_store is not None
        and conversation_state is not None
        and effective_dataset_id is not None
    ):
        prior_capsule, prior_capsule_status = conversation_store.valid_prior_capsule(
            conversation_state,
            dataset_id=effective_dataset_id,
            expected_schema_version=route_decision.get("bound_schema_version"),
        )
    query_task_capsule = build_query_task_capsule(
        question=resolved_question,
        turn_event=turn_event,
        active_dataset_id=effective_dataset_id,
        last_success_task=thread_last_success_task,
        last_success_task_status=last_success_task_status,
    )
    artifact_payload = (
        thread_last_success_task.get("result_artifact")
        if isinstance(thread_last_success_task, dict)
        else None
    )
    query_artifact_store = ArtifactStore(db)
    _, artifact_status = evaluate_query_artifact(
        artifact_payload,
        artifact_store=query_artifact_store,
    )
    settings = get_settings()
    multiturn_fast_path = plan_refinement_fast_path(
        question=payload.question,
        turn_event=turn_event,
        query_task_capsule=query_task_capsule,
        last_success_task_status=last_success_task_status,
        artifact_status=artifact_status,
        fast_path_enabled=bool(getattr(settings, "MULTITURN_REFINEMENT_FAST_PATH_ENABLED", False)),
        local_filter_enabled=bool(
            getattr(settings, "MULTITURN_RESULT_LOCAL_FILTER_ENABLED", False)
        ),
        sql_ast_patch_enabled=bool(getattr(settings, "MULTITURN_SQL_AST_PATCH_ENABLED", False)),
    )
    query_task_capsule["multiturn_fast_path"] = multiturn_fast_path
    trace_query_task_capsule = _safe_query_task_capsule_for_trace(query_task_capsule)
    step_traces: list[dict] = []  # 收集推理步骤供历史加载时恢复思维链
    gateway_step_payload = {
        "type": "step",
        "node": "message_gateway",
        "display_name": _NODE_DISPLAY_NAMES["message_gateway"],
        "status": "done",
        "turn_event": turn_event,
        "query_task_capsule": trace_query_task_capsule,
        "payload": {
            "turn_event": turn_event,
            "query_task_capsule": trace_query_task_capsule,
            "last_success_task_status": last_success_task_status,
            "multiturn_fast_path": multiturn_fast_path,
        },
    }
    step_traces.append(gateway_step_payload)
    yield _sse_data(
        _with_event_envelope(
            gateway_step_payload,
            event_type="route.started",
            visibility="trace_only",
            payload_fields=("node", "status", "turn_event"),
            metadata={"conversation_id": conv_id, "dataset_id": effective_dataset_id},
        )
    )

    # Phase 2: 在 LangGraph 之外完成多轮合并决策
    # - interpret 路径早退，不进 LangGraph
    # - 其他路径把决策字段塞进 initial_state
    merge_state = {
        "question": resolved_question,
        "turn_type": None,
        "turn_index": (multiturn_context or {}).get("turn_index"),
        "dataset_id": effective_dataset_id,
        "prior_capsule": prior_capsule,
        "history": history,
        "lead_agent_context": lead_agent_context,
        "turn_event": turn_event,
        "query_task_capsule": query_task_capsule,
        "last_success_task_status": last_success_task_status,
        "multiturn_fast_path": multiturn_fast_path,
        "manifest_version": route_decision.get("manifest_version"),
        "bound_schema_version": route_decision.get("bound_schema_version"),
    }
    merge_decision: MergeDecision = merge_multiturn_decision_for_chat(
        state=merge_state,
        out_capsule_factory=_build_out_capsule_for_chat,
        tracer=tracer,
        trace_context=trace_context,
    )
    if merge_decision.interpret_payload is not None:
        # interpret_result 是多轮本地解释早退，不进入 Graph；这里标记可避免误查 SQL 生成链路。
        _log_chat_stream_checkpoint(
            "merge_interpret_early_return",
            conversation_id=conv_id,
            effective_dataset_id=effective_dataset_id,
            turn_type=merge_decision.turn_type,
            merge_debug=merge_decision.merge_debug,
        )
        async for sse_event in _interpret_early_return(
            db=db,
            conv=conv,
            payload=payload,
            effective_dataset_id=effective_dataset_id,
            lead_agent_context=lead_agent_context,
            route_decision=route_decision,
            trace_context=trace_context,
            defer_trace_close=defer_trace_close,
            obs_context_manager=obs_context_manager,
            interpret_payload=merge_decision.interpret_payload,
            turn_type=merge_decision.turn_type,
            multiturn_context=merge_decision.multiturn_context,
            merge_debug=merge_decision.merge_debug,
            gateway_step_payload=gateway_step_payload,
            query_task_capsule=trace_query_task_capsule,
        ):
            yield sse_event
        return

    # Phase 4: 先解析挂起 term 澄清，再做入口路由。
    # 用户对 pending 术语澄清通常只回复“第一个”或术语名；若先走入口路由，
    # 这类短句会被普通 clarify 早退截断，导致 pending 永远不能 resolved。
    term_resolution = resolve_term_clarification(
        db,
        question=merge_decision.synthesized_question or resolved_question,
        conversation_id=conv_id,
        dataset_id=effective_dataset_id,
        clarification_response=jsonable_encoder(payload.clarification_response),
        tracer=tracer,
        trace_context=trace_context,
    )
    _resolved_question = term_resolution.get("resolved_question")
    routing_question = (
        _resolved_question
        if (_resolved_question and term_resolution["status"] == "resolved")
        else (merge_decision.synthesized_question or resolved_question)
    )

    # Phase 3: LeadAgent 总入口路由（替代 intent + entry 两个图节点）
    routing = route_query_intent(
        db,
        question=routing_question,
        dataset_id=effective_dataset_id,
        lead_agent_context=lead_agent_context,
        history=history,
        multiturn_context=merge_decision.multiturn_context,
        clarification_response=jsonable_encoder(payload.clarification_response),
        tracer=tracer,
        trace_context=trace_context,
    )
    # entry_routing_done 是 LeadAgent 总入口路由的最终结论，后续早退或 SubAgent 都从这里分流。
    _log_chat_stream_checkpoint(
        "entry_routing_done",
        conversation_id=conv_id,
        effective_dataset_id=effective_dataset_id,
        routing_question_preview=routing_question[:80],
        term_resolution_status=term_resolution.get("status"),
        entry_intent=routing.get("entry_intent"),
        entry_route=routing.get("entry_route"),
        entry_reason=routing.get("entry_reason"),
        route_payload_kind=(routing.get("route_payload") or {}).get("kind")
        if isinstance(routing.get("route_payload"), dict)
        else None,
    )
    yield _sse_data(
        {
            "type": "step",
            "node": "lead_agent",
            "display_name": "lead_agent",
            "status": "done",
            "intent": routing.get("intent"),
            "entities": routing.get("entities") or {},
            "entry_intent": routing.get("entry_intent"),
            "entry_route": routing.get("entry_route"),
            "entry_reason": routing.get("entry_reason"),
            "blueprint_id": routing.get("blueprint_id"),
            "route_payload": routing.get("route_payload") or {},
        }
    )
    if term_resolution["status"] != "none":
        yield _sse_data(
            {
                "type": "step",
                "node": "clarification_resolution",
                "display_name": _NODE_DISPLAY_NAMES.get(
                    "clarification_resolution", "clarification_resolution"
                ),
                "status": "done",
                "elapsed_ms": 0,
                "clarification_resolution": term_resolution.get("clarification_resolution_result")
                or {},
                "route_payload": term_resolution.get("route_payload") or {},
            }
        )
    term_should_early = term_resolution["status"] in {"missing", "expired", "unresolved"}
    if term_should_early:
        # 合并 term 解析字段到 routing，复用 _early_route_return 早退
        routing = dict(routing)
        routing["entry_intent"] = term_resolution.get("entry_intent") or routing.get("entry_intent")
        routing["entry_route"] = term_resolution.get("entry_route") or routing.get("entry_route")
        routing["entry_reason"] = term_resolution.get("entry_reason") or routing.get("entry_reason")
        routing["answer"] = term_resolution.get("answer") or routing.get("answer")
        routing["route_payload"] = term_resolution.get("route_payload") or routing.get(
            "route_payload"
        )
        # term 澄清未解决时直接早退；日志保留 status，方便判断是过期、缺失还是未匹配。
        _log_chat_stream_checkpoint(
            "term_resolution_early_return",
            conversation_id=conv_id,
            effective_dataset_id=effective_dataset_id,
            term_resolution_status=term_resolution.get("status"),
            entry_route=routing.get("entry_route"),
            entry_reason=routing.get("entry_reason"),
        )
        async for sse_event in _early_route_return(
            db=db,
            conv=conv,
            payload=payload,
            effective_dataset_id=effective_dataset_id,
            lead_agent_context=lead_agent_context,
            route_decision=route_decision,
            trace_context=trace_context,
            defer_trace_close=defer_trace_close,
            obs_context_manager=obs_context_manager,
            routing=routing,
            gateway_step_payload=gateway_step_payload,
            query_task_capsule=trace_query_task_capsule,
        ):
            yield sse_event
        return

    if routing.get("entry_route") in {"direct_answer", "reject", "knowledge_qa", "clarify"}:
        # direct/reject/knowledge/clarify 都是非 SQL 路径，记录 entry_route 后交给统一早退收尾。
        _log_chat_stream_checkpoint(
            "entry_route_early_return",
            conversation_id=conv_id,
            effective_dataset_id=effective_dataset_id,
            entry_route=routing.get("entry_route"),
            entry_reason=routing.get("entry_reason"),
            entry_intent=routing.get("entry_intent"),
        )
        async for sse_event in _early_route_return(
            db=db,
            conv=conv,
            payload=payload,
            effective_dataset_id=effective_dataset_id,
            lead_agent_context=lead_agent_context,
            route_decision=route_decision,
            trace_context=trace_context,
            defer_trace_close=defer_trace_close,
            obs_context_manager=obs_context_manager,
            routing=routing,
            gateway_step_payload=gateway_step_payload,
            query_task_capsule=trace_query_task_capsule,
        ):
            yield sse_event
        return

    # Phase 4: 注入 term 解析结果（resolved 时把 question 恢复到原问题 + selected_term_id）
    _initial_question = (
        _resolved_question
        if (_resolved_question and term_resolution["status"] == "resolved")
        else (merge_decision.synthesized_question or resolved_question)
    )
    _initial_route_payload = (
        term_resolution.get("route_payload")
        if term_resolution["status"] != "none"
        else routing.get("route_payload")
    )
    initial_state = {
        "question": _initial_question,
        "original_question": payload.question,
        "resolved_question": resolved_question,
        "dataset_id": effective_dataset_id,
        "manifest_version": route_decision.get("manifest_version"),
        "bound_schema_version": route_decision.get("bound_schema_version"),
        "time_context": lead_agent_context.get("time_context"),
        "thread_context": lead_agent_context.get("thread_context"),
        "route_decision": route_decision,
        "schema_status": lead_agent_context.get("schema_status"),
        "lead_agent_context": lead_agent_context,
        "skip_subagent_report": report_control["skip_subagent_report"],
        "report_owner": report_control["report_owner"],
        "subagent_report_skipped": report_control["subagent_report_skipped"],
        "lead_agent_report": report_control["lead_agent_report"],
        "conversation_id": conv_id,
        "history": history,
        "clarification_response": jsonable_encoder(payload.clarification_response),
        "clarification_resolution_result": term_resolution.get("clarification_resolution_result"),
        "prior_capsule": prior_capsule,
        "prior_capsule_status": prior_capsule_status,
        "last_success_task_status": last_success_task_status,
        "multiturn_fast_path": multiturn_fast_path,
        "out_capsule": None,
        "multiturn_context": merge_decision.multiturn_context,
        "turn_type": merge_decision.turn_type,
        "merge_debug": merge_decision.merge_debug,
        "intent": routing.get("intent"),
        "entities": routing.get("entities") or {},
        "entry_intent": routing.get("entry_intent"),
        "entry_route": routing.get("entry_route"),
        "entry_reason": routing.get("entry_reason"),
        "blueprint_id": routing.get("blueprint_id"),
        "blueprint_match": routing.get("blueprint_match"),
        "blueprint_context": None,
        "knowledge_term_id": routing.get("knowledge_term_id"),
        "selected_term_id": term_resolution.get("selected_term_id"),
        "route_payload": _initial_route_payload,
        "generation_mode": None,
        "schema_context": None,
        "schema_structured": None,
        "ddl_context": None,
        "query_constraints": None,
        "dataset_context_debug": None,
        "datasource_context": None,
        "term_normalization": None,
        "semantic_asset_resolution": None,
        "metric_resolution": None,
        "candidate_assets": None,
        "query_plan": None,
        "query_plan_debug": None,
        "dsl": None,
        "dsl_valid": False,
        "sql": None,
        "sql_result": None,
        "datasource_dialect": None,
        "sql_audit_result": None,
        "sql_diagnosis": None,
        "answer_explanation": None,
        "answer": None,
        "sql_list": [],
        "error": None,
        "retry_count": 0,
        "max_retry_count": 3,
        "should_retry": False,
        "sql_retry_trace": [],
        "token_usage": None,
        "turn_event": turn_event,
        "query_task_capsule": query_task_capsule,
    }

    fanout_invocations = []
    if getattr(get_settings(), "LEAD_AGENT_ENABLE_DATASET_FANOUT", False):
        fanout_invocations = parse_dataset_fanout_invocations(
            lead_agent_context.get("planned_tool_calls") or [],
            fallback_question=payload.question,
            resolved_question=lead_agent_context.get("resolved_question") or resolved_question,
            turn_index=getattr(conversation_state, "turn_index", None),
            prior_capsule_status=prior_capsule_status,
    )
    if fanout_invocations:
        fanout_step_started_at = time.monotonic()
        # fanout 是 LeadAgent 规划出的多数据集分支，单独打点避免和普通单数据集 SubAgent 混淆。
        _log_chat_stream_checkpoint(
            "fanout_start",
            conversation_id=conv_id,
            effective_dataset_id=effective_dataset_id,
            dataset_ids=[item.dataset_id for item in fanout_invocations],
            invocation_count=len(fanout_invocations),
        )
        fanout_step = {
            "type": "step",
            "node": "subagent_fanout",
            "display_name": "subagent.fanout",
            "status": "running",
            "dataset_ids": [item.dataset_id for item in fanout_invocations],
        }
        yield _sse_data(
            _with_event_envelope(
                fanout_step,
                event_type="dataset.query.started",
                visibility="trace_only",
                payload_fields=("node", "status", "dataset_ids"),
                metadata={"conversation_id": conv_id, "dataset_id": effective_dataset_id},
            )
        )
        app_graph = build_workflow(db)

        async def _invoke_fanout(invocation: SubAgentFanOutInvocation) -> dict[str, Any]:
            dataset_route_decision = dict(route_decision)
            dataset_route_decision["dataset_id"] = invocation.dataset_id
            dataset_initial_state = dict(initial_state)
            dataset_initial_state.update(
                {
                    "question": invocation.resolved_question or invocation.question,
                    "resolved_question": invocation.resolved_question or invocation.question,
                    "dataset_id": invocation.dataset_id,
                    "route_decision": dataset_route_decision,
                    "prior_capsule": None,
                    "prior_capsule_status": invocation.prior_capsule_status or {},
                    "out_capsule": None,
                    "sql": None,
                    "sql_result": None,
                    "answer": None,
                    "error": None,
                }
            )
            dataset_request = DatasetSubAgentRequest(
                question=invocation.resolved_question or invocation.question,
                dataset_id=invocation.dataset_id,
                manifest_version=dataset_route_decision.get("manifest_version"),
                bound_schema_version=dataset_route_decision.get("bound_schema_version"),
                thread_id=conv.thread_id or f"conversation-{conv_id}",
                time_context=lead_agent_context.get("time_context") or {},
                thread_context=lead_agent_context.get("thread_context") or {},
                route_decision=dataset_route_decision,
                schema_status=lead_agent_context.get("schema_status") or {},
                lead_agent_context=lead_agent_context,
                prior_capsule=None,
                prior_capsule_status=invocation.prior_capsule_status or {},
                query_task_capsule=query_task_capsule,
                turn_event=turn_event,
                trace_id=trace_context.trace_id,
                parent_observation_id=None,
            )
            return await _collect_subagent_final_state(
                db=db,
                dataset_id=invocation.dataset_id,
                request=dataset_request,
                trace_context=trace_context,
                initial_state=dataset_initial_state,
                route_decision=dataset_route_decision,
                app_graph=app_graph,
            )

        fanout_result = await SubAgentFanOutOrchestrator(
            invoke_final_state=_invoke_fanout,
            adapter=SubAgentToolAdapter(artifact_store=ArtifactStore(db)),
        ).run(fanout_invocations)
        fanout_answer = SubAgentFanOutAnswerSynthesizer().synthesize(fanout_result)
        # fanout_done 只记录各子任务状态和答案长度，不展开每个子任务的大 payload。
        _log_chat_stream_checkpoint(
            "fanout_done",
            conversation_id=conv_id,
            effective_dataset_id=effective_dataset_id,
            result_count=len(fanout_result.results),
            statuses=[item.llm_visible.status.value for item in fanout_result.results],
            answer_len=len(fanout_answer),
        )
        subagent_tool_results = jsonable_encoder(
            [item.llm_visible.model_dump(mode="json") for item in fanout_result.results]
        )
        if subagent_control_plane_sink is not None:
            subagent_control_plane_sink.clear()
            subagent_control_plane_sink.extend(jsonable_encoder(fanout_result.control_planes))

        elapsed_ms = int((time.monotonic() - fanout_step_started_at) * 1000)
        fanout_done_step = {
            "type": "step",
            "node": "subagent_fanout",
            "display_name": "subagent.fanout",
            "status": "done",
            "elapsed_ms": elapsed_ms,
            "dataset_ids": [item.dataset_id for item in fanout_invocations],
            "statuses": [item.llm_visible.status.value for item in fanout_result.results],
        }
        step_traces.append(fanout_done_step)
        yield _sse_data(
            _with_event_envelope(
                fanout_done_step,
                event_type="dataset.query.completed",
                visibility="user_visible",
                payload_fields=("node", "status", "elapsed_ms", "dataset_ids", "statuses"),
                metadata={"conversation_id": conv_id, "dataset_id": effective_dataset_id},
            )
        )

        trace_metadata = {
            "status": "success",
            "execution_path": "dataset_fanout",
            "original_question": payload.question,
            "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
            "lead_agent_context": lead_agent_context,
            "route_decision": route_decision,
            "subagent_tool_results": subagent_tool_results,
            "fanout_trace": jsonable_encoder(fanout_result.trace_metadata),
            "prompt_versions": trace_context.prompt_versions,
        }
        tracer.update_trace_output(trace_context, output=fanout_answer, metadata=trace_metadata)
        response_metadata = jsonable_encoder(
            {
                "lead_agent_context": lead_agent_context,
                "original_question": payload.question,
                "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
                "route_decision": route_decision,
                "schema_status": lead_agent_context.get("schema_status"),
                "subagent_tool_results": subagent_tool_results,
                "fanout_trace": fanout_result.trace_metadata,
                "langfuse": {
                    "trace_id": trace_context.trace_id,
                    "session_id": trace_context.session_id,
                    "release": trace_context.release,
                    "environment": trace_context.environment,
                    "prompt_label": trace_context.prompt_label,
                    "base_url": trace_context.base_url,
                    "project_id": trace_context.project_id,
                    "trace_url": trace_context.trace_url,
                    "enabled": trace_context.enabled,
                    "active": trace_context.active,
                    "prompt_versions": trace_context.prompt_versions,
                },
                "observability": trace_context.observability_payload(),
            }
        )
        assistant_message = models.Message(
            conversation_id=conv_id,
            role="assistant",
            content=fanout_answer,
            sql_list=[],
            step_trace=jsonable_encoder(step_traces),
            response_metadata=response_metadata,
        )
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)
        ArtifactStore(db).attach_message_id(
            [
                ref
                for item in subagent_tool_results
                for ref in (item.get("result_ref"), item.get("report_ref"))
            ],
            message_id=int(assistant_message.id),
        )
        if trace_context.trace_id:
            db.add(
                models.ObservabilityTraceIndex(
                    langfuse_trace_id=trace_context.trace_id,
                    langfuse_session_id=trace_context.session_id,
                    conversation_id=conv_id,
                    message_id=assistant_message.id,
                    dataset_id=effective_dataset_id,
                    entry_route="dataset_fanout",
                    status="success",
                    total_tokens=0,
                    total_cost=0,
                    metadata_json=jsonable_encoder(trace_metadata),
                )
            )
            db.commit()
        final_payload = {
            "type": "final",
            "sql": None,
            "sql_list": [],
            "answer": fanout_answer,
            "entry_intent": "dataset_fanout",
            "entry_route": "dataset_fanout",
            "entry_reason": "lead_agent_multi_dataset_tool_calls",
            "lead_agent_context": lead_agent_context,
            "original_question": payload.question,
            "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
            "time_context": lead_agent_context.get("time_context"),
            "route_decision": route_decision,
            "schema_status": lead_agent_context.get("schema_status"),
            "sql_result": None,
            "subagent_tool_results": subagent_tool_results,
            "response_metadata": response_metadata,
            "conversation_id": conv_id,
            "message_id": assistant_message.id,
            "task_id": f"conv-{conv_id}-msg-{assistant_message.id}",
            "trace_id": trace_context.trace_id,
            "title": conv.title,
            "langfuse_trace_id": trace_context.trace_id,
            "langfuse_session_id": trace_context.session_id,
            "observability": trace_context.observability_payload(),
        }
        _attach_artifact_card_refs_to_final_payload(final_payload)  # fanout 也只暴露多数据集产物引用，不携带结果 body。
        _sync_artifact_metadata_to_assistant_message(
            db=db,
            assistant_message=assistant_message,
            final_payload=final_payload,
        )
        query_artifact_store.attach_message_id(
            _artifact_refs_for_query_artifact(final_payload),
            message_id=int(assistant_message.id),
        )
        # fanout final 也走同一摘要格式，便于和普通 final_payload_ready 横向对比。
        _log_chat_stream_checkpoint("fanout_final_payload_ready", **_chat_stream_log_summary(final_payload))
        yield _sse_data(
            _with_event_envelope(
                final_payload,
                event_type="answer.completed",
                visibility="user_visible",
                payload_fields=(
                    "answer",
                    "entry_route",
                    "entry_reason",
                    "subagent_tool_results",
                    "artifact_card",
                    "primary_ref",
                    "related_refs",
                    "task_id",
                    "trace_id",
                ),
            )
        )
        if not defer_trace_close:
            tracer.close_trace(trace_context)
        obs_context_manager.__exit__(None, None, None)
        return

    # 构建并运行工作流
    app_graph = build_workflow(db)
    subagent_request = DatasetSubAgentRequest(
        question=resolved_question,
        dataset_id=int(effective_dataset_id),
        manifest_version=route_decision.get("manifest_version"),
        bound_schema_version=route_decision.get("bound_schema_version"),
        thread_id=conv.thread_id or f"conversation-{conv_id}",
        time_context=lead_agent_context.get("time_context") or {},
        thread_context=lead_agent_context.get("thread_context") or {},
        route_decision=route_decision,
        schema_status=lead_agent_context.get("schema_status") or {},
        lead_agent_context=lead_agent_context,
        prior_capsule=prior_capsule,
        prior_capsule_status=prior_capsule_status,
        query_task_capsule=query_task_capsule,
        turn_event=turn_event,
        trace_id=trace_context.trace_id,
        parent_observation_id=None,
    )
    final_state: dict = dict(initial_state)
    node_start_times: dict[str, float] = {}
    _log_chat_stream_checkpoint(  # 只有走到这里才会调用 DatasetSubAgent。
        "subagent_request_ready",
        conversation_id=conv_id,
        effective_dataset_id=effective_dataset_id,
        request_dataset_id=subagent_request.dataset_id,
        entry_route=routing.get("entry_route"),
        manifest_version=route_decision.get("manifest_version"),
        bound_schema_version=route_decision.get("bound_schema_version"),
        prior_capsule_status=prior_capsule_status,
    )

    try:
        _log_chat_stream_checkpoint(  # Graph 开始前打点，后续由 SubAgent 事件补齐结果。
            "graph_stream_start",
            conversation_id=conv_id,
            effective_dataset_id=effective_dataset_id,
            entry_route=routing.get("entry_route"),
        )
        # 去重集合：astream_events v2 中子 chain 也会触发 on_chain_start/end，
        # 同一 langgraph_node 名称可能重复出现，只取每个节点的第一次事件
        reported_running: set[str] = set()
        reported_done: set[str] = set()
        graph_report_think_state = new_think_stream_state()

        async with _managed_subagent_events(
            db=db,
            dataset_id=effective_dataset_id,
            request=subagent_request,
            trace_context=trace_context,
            initial_state=initial_state,
            route_decision=route_decision,
            app_graph=app_graph,
        ) as subagent_events:
            async for sub_event in subagent_events:
                sub_event_type = _subagent_event_type(sub_event)
                sub_event_payload = _subagent_event_payload(sub_event)
                if sub_event_type in {"candidate_assets", "query_plan"}:
                    sse_payload = _subagent_event_to_sse_payload(sub_event)
                    sse_payload["type"] = "step"
                    if sub_event_type == "candidate_assets":
                        final_state["candidate_assets"] = sse_payload.get("candidate_assets")
                        candidate_assets = sse_payload.get("candidate_assets")
                        _log_chat_stream_checkpoint(  # 候选资产数量用于区分召回不足和规划失败。
                            "subagent_candidate_assets",
                            conversation_id=conv_id,
                            effective_dataset_id=effective_dataset_id,
                            asset_count=len(candidate_assets)
                            if isinstance(candidate_assets, list)
                            else None,
                            payload_keys=sorted(sse_payload.keys()),
                        )
                    elif sub_event_type == "query_plan":
                        query_plan = sse_payload.get("query_plan") or {}
                        final_state["query_plan"] = query_plan
                        if final_state.get("query_plan_debug") is None:
                            final_state["query_plan_debug"] = {
                                "planner_source": query_plan.get("planner_source"),
                                "fallback_reason": query_plan.get("fallback_reason"),
                                "decision_factors": query_plan.get("decision_factors") or [],
                                "planner_warnings": query_plan.get("planner_warnings") or [],
                                "governance_suggestions": query_plan.get("governance_suggestions") or [],
                            }
                        _log_chat_stream_checkpoint(  # query_plan 摘要用于定位 fallback/unsupported 分支。
                            "subagent_query_plan",
                            conversation_id=conv_id,
                            effective_dataset_id=effective_dataset_id,
                            query_plan_type=query_plan.get("query_type"),
                            execution_strategy=query_plan.get("execution_strategy"),
                            planner_source=query_plan.get("planner_source"),
                            fallback_reason=query_plan.get("fallback_reason"),
                            has_sql_template=bool(query_plan.get("sql_template")),
                            decision_factor_count=len(query_plan.get("decision_factors") or []),
                            warning_count=len(query_plan.get("planner_warnings") or []),
                        )
                    sse_payload = _with_event_envelope(
                        sse_payload,
                        event_type="dataset.query.started"
                        if sub_event_type == "query_plan"
                        else "route.started",
                        visibility="trace_only",
                        payload_fields=("type", "node", "query_plan", "candidate_assets"),
                        metadata={"conversation_id": conv_id, "dataset_id": effective_dataset_id},
                    )
                    step_traces.append(sse_payload)
                    yield _sse_data(sse_payload)
                    continue

                if sub_event_type == "result":
                    final_state.update(sub_event_payload.get("final_state") or {})  # SubAgent result 写回最终状态。
                    if final_state.get("query_plan_debug") is None:
                        query_plan = final_state.get("query_plan") or {}
                        final_state["query_plan_debug"] = {
                            "planner_source": query_plan.get("planner_source"),
                            "fallback_reason": query_plan.get("fallback_reason"),
                            "decision_factors": query_plan.get("decision_factors") or [],
                            "planner_warnings": query_plan.get("planner_warnings") or [],
                            "governance_suggestions": query_plan.get("governance_suggestions")
                            or [],
                        }
                    _log_chat_stream_checkpoint(  # result 与最终 SSE 可能有二次加工，需单独留证。
                        "subagent_result",
                        conversation_id=conv_id,
                        effective_dataset_id=effective_dataset_id,
                        summary=_chat_stream_log_summary(
                            {
                                "type": "subagent_result",
                                "answer": final_state.get("answer"),
                                "entry_route": final_state.get("entry_route"),
                                "entry_reason": final_state.get("entry_reason"),
                                "query_plan": final_state.get("query_plan"),
                                "sql": final_state.get("sql"),
                                "sql_list": final_state.get("sql_list") or [],
                                "error": final_state.get("error"),
                                "conversation_id": conv_id,
                            }
                        ),
                    )
                    continue

                if sub_event_type == "graph_event":
                    event = sub_event_payload["event"]
                else:
                    sse_payload = _subagent_event_to_sse_payload(sub_event)
                    sse_payload.setdefault("node", sub_event_type)
                    node_name = str(sse_payload.get("node"))
                    sse_payload.setdefault(
                        "display_name",
                        _NODE_DISPLAY_NAMES.get(node_name, node_name),
                    )
                    sse_payload["type"] = "step"
                    sse_payload.setdefault("status", "done")
                    sse_payload = _with_event_envelope(
                        sse_payload,
                        event_type="dataset.query.completed",
                        visibility="trace_only",
                        payload_fields=("node", "status"),
                        metadata={"conversation_id": conv_id, "dataset_id": effective_dataset_id},
                    )
                    step_traces.append(sse_payload)
                    yield _sse_data(sse_payload)
                    continue

                kind: str = event["event"]
                meta: dict = event.get("metadata", {})
                # langgraph_node 元数据标识当前所属顶层图节点
                lg_node: str = meta.get("langgraph_node", "")

                # ── 节点开始（每节点只报一次）────────────────────
                if (
                    kind == "on_chain_start"
                    and lg_node in _NODE_DISPLAY_NAMES
                    and lg_node not in reported_running
                ):
                    reported_running.add(lg_node)
                    node_start_times[lg_node] = time.monotonic()
                    sse_payload = {
                        "type": "step",
                        "node": lg_node,
                        "display_name": _NODE_DISPLAY_NAMES[lg_node],
                        "status": "running",
                    }
                    logger.info(f"[_stream_chat] step running: {lg_node}")
                    tracer.start_span(
                        trace_context,
                        node=lg_node,
                        display_name=_NODE_DISPLAY_NAMES[lg_node],
                        input_payload={
                            "question": payload.question,
                            "dataset_id": effective_dataset_id,
                            "conversation_id": conv_id,
                            "time_context": lead_agent_context.get("time_context"),
                            "route_decision": route_decision,
                            "schema_status": lead_agent_context.get("schema_status"),
                            "lead_agent_audit": lead_agent_context.get("audit_trace"),
                            "prior_capsule_status": prior_capsule_status,
                        },
                    )
                    yield _sse_data(
                        _with_event_envelope(
                            sse_payload,
                            event_type=_step_event_type(sse_payload),
                            visibility="trace_only",
                            payload_fields=("node", "status"),
                            metadata={
                                "conversation_id": conv_id,
                                "dataset_id": effective_dataset_id,
                            },
                        )
                    )

                # ── 节点完成（每节点只报一次）────────────────────
                elif kind == "on_chain_end" and lg_node in _NODE_DISPLAY_NAMES:
                    output = _extract_node_output(event, lg_node)
                    if lg_node in reported_done or not output:
                        continue
                    reported_done.add(lg_node)
                    elapsed_ms = int((time.monotonic() - node_start_times.get(lg_node, 0)) * 1000)
                    # 合并节点输出到 final_state（允许 None 值传播）
                    final_state.update(output)
                    if lg_node == "report_generator":
                        visible_tail = flush_think_stream_state(graph_report_think_state)
                        if visible_tail:
                            yield _sse_data({"type": "token", "content": visible_tail})

                    sse_payload = {
                        "type": "step",
                        "node": lg_node,
                        "display_name": _NODE_DISPLAY_NAMES[lg_node],
                        "status": "done",
                        "elapsed_ms": elapsed_ms,
                    }
                    # 节点特定数据
                    # 旧语义解析节点不再作为 LangGraph 顶层节点处理，SubAgent.run 统一输出规划事件。
                    if lg_node == "dsl_generate":
                        sse_payload["dsl"] = final_state.get("dsl") or {}
                        sse_payload["generation_mode"] = final_state.get("generation_mode") or ""
                    elif lg_node == "schema_recall":
                        schema = final_state.get("schema_context", "") or ""
                        lines_ = [
                            line
                            for line in schema.split("\n")
                            if line.strip() and not line.startswith("-")
                        ]
                        sse_payload["schema_summary"] = lines_[:3]
                    elif lg_node == "dsl_compiler":
                        sse_payload["sql"] = final_state.get("sql") or ""
                    elif lg_node == "sql_execute":
                        result = final_state.get("sql_result") or {}
                        sse_payload["row_count"] = result.get("row_count", 0)
                        sse_payload["column_count"] = len(result.get("columns") or [])
                        sse_payload["elapsed_ms"] = elapsed_ms
                    elif lg_node == "sql_audit":
                        diagnosis = (
                            final_state.get("sql_diagnosis")
                            or final_state.get("sql_audit_result")
                            or {}
                        )
                        sse_payload["sql_diagnosis"] = diagnosis
                        sse_payload["sql_audit_result"] = final_state.get("sql_audit_result") or {}
                        sse_payload["code"] = diagnosis.get("code")
                        sse_payload["severity"] = diagnosis.get("severity")
                        sse_payload["retryable"] = diagnosis.get("retryable")
                        sse_payload["sql_retry_trace"] = final_state.get("sql_retry_trace") or []
                    step_traces.append(sse_payload)
                    logger.info(f"[_stream_chat] step done: {lg_node} ({elapsed_ms}ms)")
                    tracer.end_span(
                        trace_context,
                        node=lg_node,
                        output_payload=sse_payload,
                        elapsed_ms=elapsed_ms,
                        error=final_state.get("error") if lg_node == "sql_audit" else None,
                    )
                    step_visibility: DatalogueEventVisibility = (
                        "user_visible" if lg_node == "sql_execute" else "trace_only"
                    )
                    step_payload_fields = (
                        ("node", "status", "elapsed_ms", "row_count", "column_count")
                        if lg_node == "sql_execute"
                        else ("node", "status", "elapsed_ms")
                    )
                    yield _sse_data(
                        _with_event_envelope(
                            sse_payload,
                            event_type=_step_event_type(sse_payload),
                            visibility=step_visibility,
                            payload_fields=step_payload_fields,
                            metadata={
                                "conversation_id": conv_id,
                                "dataset_id": effective_dataset_id,
                            },
                        )
                    )
                    if lg_node == "sql_audit":
                        repair_summary = _ensure_repair_plan_artifact(
                            final_state=final_state,
                            artifact_store=query_artifact_store,
                            dataset_id=effective_dataset_id,
                            conversation_id=conv_id,
                            trace_id=trace_context.trace_id,
                        )
                        if repair_summary:
                            _log_chat_stream_checkpoint(  # RepairPlan 已落为 artifact ref，后续 final/状态只传 ref。
                                "repair_plan_created",
                                conversation_id=conv_id,
                                effective_dataset_id=effective_dataset_id,
                                repair_plan_ref=final_state.get("repair_plan_ref"),
                                failure_class=final_state.get("repair_failure_class"),
                                attempts=final_state.get("repair_attempts"),
                            )
                            tracer.start_span(
                                trace_context,
                                node="repair_plan",
                                display_name="repair.plan_created",
                                input_payload=repair_summary,
                                trace_tags=["repair_plan"],
                            )
                            tracer.end_span(
                                trace_context,
                                node="repair_plan",
                                output_payload=repair_summary,
                            )
                            for repair_event_type, repair_status in (
                                ("repair.evaluated", "evaluated"),
                                ("repair.plan_created", "plan_created"),
                                ("repair.rerun_started", "rerun_started"),
                            ):
                                yield _sse_data(
                                    _with_event_envelope(
                                        {
                                            "type": "repair",
                                            "status": repair_status,
                                            "repair_plan_ref": final_state.get("repair_plan_ref"),
                                        },
                                        event_type=repair_event_type,
                                        visibility="user_visible",
                                        event_payload=_repair_event_payload(
                                            final_state=final_state,
                                            status=repair_status,
                                            summary=repair_summary,
                                        ),
                                        metadata={
                                            "conversation_id": conv_id,
                                            "dataset_id": effective_dataset_id,
                                        },
                                    )
                                )
                        elif final_state.get("repair_status") in {"blocked", "failed"}:
                            blocked_status = str(final_state.get("repair_status") or "blocked")
                            _log_chat_stream_checkpoint(  # 不可修复类也必须进入 repair envelope，便于前端/审计对齐。
                                "repair_plan_blocked",
                                conversation_id=conv_id,
                                effective_dataset_id=effective_dataset_id,
                                failure_class=final_state.get("repair_failure_class"),
                                repair_status=blocked_status,
                            )
                            for repair_event_type, repair_status in (
                                ("repair.evaluated", "evaluated"),
                                (f"repair.{blocked_status}", blocked_status),
                            ):
                                yield _sse_data(
                                    _with_event_envelope(
                                        {
                                            "type": "repair",
                                            "status": repair_status,
                                        },
                                        event_type=repair_event_type,
                                        visibility="user_visible",
                                        event_payload=_repair_event_payload(
                                            final_state=final_state,
                                            status=repair_status,
                                        ),
                                        metadata={
                                            "conversation_id": conv_id,
                                            "dataset_id": effective_dataset_id,
                                        },
                                    )
                                )
                    elif (
                        lg_node == "sql_execute"
                        and final_state.get("repair_plan_ref")
                        and final_state.get("sql_result")
                        and not final_state.get("error")
                    ):
                        final_state["repair_status"] = "rerun_completed"
                        _log_chat_stream_checkpoint(  # 自动修复重跑成功，和后续 answer.completed 使用同一 trace/task。
                            "repair_rerun_completed",
                            conversation_id=conv_id,
                            effective_dataset_id=effective_dataset_id,
                            repair_plan_ref=final_state.get("repair_plan_ref"),
                            row_count=(final_state.get("sql_result") or {}).get("row_count"),
                        )
                        yield _sse_data(
                            _with_event_envelope(
                                {
                                    "type": "repair",
                                    "status": "rerun_completed",
                                    "repair_plan_ref": final_state.get("repair_plan_ref"),
                                },
                                event_type="repair.rerun_completed",
                                visibility="user_visible",
                                event_payload=_repair_event_payload(
                                    final_state=final_state,
                                    status="rerun_completed",
                                ),
                                metadata={
                                    "conversation_id": conv_id,
                                    "dataset_id": effective_dataset_id,
                                },
                            )
                        )

                # ── 图级结束事件：兜底合并完整最终状态 ───────────────
                elif kind == "on_chain_end" and not lg_node:
                    output = _extract_node_output(event, "")
                    if output:
                        final_state.update(output)

                # ── LLM token ───────────────────────────────────
                elif kind == "on_chat_model_stream":
                    # report_generator 节点推送 token（打字效果）
                    # 其他节点输出为结构化 JSON，不推送给前端
                    # 注：同步节点在线程池中运行，token 可能无法全部回传；
                    # 前端 onDone 会用 finalData.answer 作为完整答案兜底
                    if lg_node and lg_node != "report_generator":
                        continue
                    chunk = event.get("data", {}).get("chunk")
                    token: str = getattr(chunk, "content", "") or ""
                    if token:
                        visible_token = filter_think_stream_chunk(token, graph_report_think_state)
                        if visible_token:
                            yield _sse_data({"type": "token", "content": visible_token})

        _log_chat_stream_checkpoint(  # Graph 完成摘要用于和最终 payload 对比。
            "graph_stream_done",
            conversation_id=conv_id,
            effective_dataset_id=effective_dataset_id,
            reported_nodes=sorted(reported_done),
            summary=_chat_stream_log_summary(
                {
                    "type": "graph_done",
                    "answer": final_state.get("answer"),
                    "entry_route": final_state.get("entry_route"),
                    "entry_reason": final_state.get("entry_reason"),
                    "query_plan": final_state.get("query_plan"),
                    "sql": final_state.get("sql"),
                    "sql_list": final_state.get("sql_list") or [],
                    "error": final_state.get("error"),
                    "conversation_id": conv_id,
                }
            ),
        )

    except Exception as e:
        _log_chat_stream_checkpoint(
            "graph_stream_exception",
            conversation_id=conv_id,
            effective_dataset_id=effective_dataset_id,
            error=str(e),
        )
        logger.exception("[_stream_chat] 工作流异常: %s", e)
        tracer.update_trace_output(
            trace_context, output=f"处理出错：{e}", metadata={"status": "failed"}
        )
        tracer.close_trace(trace_context)
        obs_context_manager.__exit__(None, None, None)
        error_step = {"type": "step", "node": "error", "display_name": "error", "status": "done"}
        yield _sse_data(
            _with_event_envelope(
                error_step,
                event_type="error.blocked",
                visibility="trace_only",
                payload_fields=("node", "status"),
                metadata={"conversation_id": conv_id, "dataset_id": effective_dataset_id},
            )
        )
        error_final = {"type": "final", "sql": None, "sql_list": [], "answer": f"处理出错：{e}"}
        yield _sse_data(
            _with_event_envelope(
                error_final,
                event_type="error.blocked",
                visibility="user_visible",
                payload_fields=("answer",),
                metadata={"conversation_id": conv_id, "dataset_id": effective_dataset_id},
            )
        )
        return

    # ── 保存助手消息并发送 final 事件 ────────────────
    route_payload = final_state.get("route_payload") or {}
    if route_payload.get("kind") == "term_conflict_clarification" and conv_id:
        route_payload = _ensure_pending_term_clarification(
            db,
            conversation_id=conv_id,
            dataset_id=effective_dataset_id,
            question=final_state.get("original_question") or payload.question,
            route_payload=route_payload,
        )
        final_state["route_payload"] = route_payload

    if _should_generate_lead_agent_report(final_state):
        final_state["subagent_report_skipped"] = True
        final_state["lead_agent_report"] = {
            "generated": False,
            "reason": "auto_routed_manifest",
        }
        report_node = "lead_agent_report_generator"
        report_started_at = time.monotonic()
        running_payload = {
            "type": "step",
            "node": report_node,
            "display_name": _NODE_DISPLAY_NAMES[report_node],
            "status": "running",
            "report_owner": "lead_agent",
            "subagent_report_skipped": True,
        }
        tracer.start_span(
            trace_context,
            node="lead.narrate",
            display_name="lead.narrate",
            input_payload={
                "question": final_state.get("question"),
                "original_question": final_state.get("original_question"),
                "dataset_id": effective_dataset_id,
                "sql": final_state.get("sql"),
                "sql_result": final_state.get("sql_result"),
                "route_decision": route_decision,
                "reason": "auto_routed_manifest",
            },
            trace_tags=["lead"],
        )
        yield _sse_data(
            _with_event_envelope(
                running_payload,
                event_type="dataset.query.started",
                visibility="trace_only",
                payload_fields=("node", "status", "report_owner"),
                metadata={"conversation_id": conv_id, "dataset_id": effective_dataset_id},
            )
        )
        lead_report_result: dict | None = None
        async for report_event in stream_sql_result_report(
            final_state,
            db=db,
            observation_name="llm.lead_agent_report_generator",
            report_owner="lead_agent",
            metadata={"reason": "auto_routed_manifest"},
        ):
            if report_event.get("type") == "token":
                yield _sse_data({"type": "token", "content": report_event.get("content") or ""})
            elif report_event.get("type") == "result":
                lead_report_result = report_event
        if lead_report_result:
            final_state["answer"] = lead_report_result.get("answer")
            final_state["token_usage"] = lead_report_result.get("token_usage")
            final_state["lead_agent_report"] = {
                "generated": True,
                "reason": "auto_routed_manifest",
            }
        report_elapsed_ms = int((time.monotonic() - report_started_at) * 1000)
        done_payload = {
            "type": "step",
            "node": report_node,
            "display_name": _NODE_DISPLAY_NAMES[report_node],
            "status": "done",
            "elapsed_ms": report_elapsed_ms,
            "report_owner": "lead_agent",
            "subagent_report_skipped": True,
            "lead_agent_report": final_state.get("lead_agent_report") or {},
        }
        step_traces.append(done_payload)
        tracer.end_span(
            trace_context,
            node="lead.narrate",
            output_payload=done_payload,
            elapsed_ms=report_elapsed_ms,
        )
        yield _sse_data(
            _with_event_envelope(
                done_payload,
                event_type="answer.completed",
                visibility="user_visible",
                payload_fields=(
                    "node",
                    "status",
                    "elapsed_ms",
                    "report_owner",
                    "lead_agent_report",
                ),
                metadata={"conversation_id": conv_id, "dataset_id": effective_dataset_id},
            )
        )

    # 智能兜底：根据失败原因给出具体提示，而非生硬的"抱歉"
    raw_answer = final_state.get("answer")
    error = final_state.get("error")
    generation_mode = final_state.get("generation_mode")
    retry_count = final_state.get("retry_count", 0)
    sql_diagnosis = final_state.get("sql_diagnosis") or final_state.get("sql_audit_result")
    sql_retry_trace = final_state.get("sql_retry_trace") or []

    if raw_answer:
        answer = str(raw_answer)
    elif generation_mode == "inferred":
        if error:
            answer = f"AI 基于表结构推断查询时遇到问题：{error}。建议检查已选表的字段是否正确，或尝试在语义层中定义明确的指标。"
        else:
            answer = "AI 基于表结构推断查询时未能成功，请检查已选表配置或尝试换一种问法。"
    elif error:
        if sql_diagnosis:
            answer = f"查询处理出现问题：{error}。建议复核字段口径、语义层配置或数据源连接。"
        elif retry_count >= 3:
            answer = f"查询多次尝试后仍未能成功：{error}。建议检查语义层配置或数据源连接。"
        else:
            answer = f"查询处理出现问题：{error}。请稍后重试或换一种问法。"
    else:
        answer = "抱歉，暂时无法回答这个问题。请尝试选择数据集后提问，或检查语义层配置。"

    final_state["answer"] = answer
    _log_chat_stream_checkpoint(  # 记录 answer 来源，区分模型结果、错误分支和本地兜底。
        "answer_resolved",
        conversation_id=conv_id,
        effective_dataset_id=effective_dataset_id,
        generation_mode=generation_mode,
        retry_count=retry_count,
        has_error=bool(error),
        answer_len=len(answer),
        sql_diagnosis_code=sql_diagnosis.get("code")
        if isinstance(sql_diagnosis, dict)
        else None,
    )
    result_artifact = build_query_result_artifact(  # 生成多轮可引用的结果 artifact。
        question=final_state.get("resolved_question")
        or lead_agent_context.get("resolved_question")
        or payload.question,
        dataset_id=effective_dataset_id,
        sql=final_state.get("sql"),
        sql_result=final_state.get("sql_result"),
        answer=answer,
        schema_version=route_decision.get("bound_schema_version")
        or final_state.get("bound_schema_version"),
        manifest_version=route_decision.get("manifest_version")
        or final_state.get("manifest_version"),
        ttl_seconds=int(getattr(settings, "MULTITURN_ARTIFACT_CACHE_TTL_SECONDS", 1800) or 1800),
        artifact_store=query_artifact_store,
        conversation_id=conv_id,
        trace_id=trace_context.trace_id,
    )
    if result_artifact:
        final_state["result_artifact"] = result_artifact
    answer_explanation = jsonable_encoder(build_answer_explanation(final_state))
    final_state["answer_explanation"] = answer_explanation
    subagent_tool_result = SubAgentToolAdapter(
        artifact_store=query_artifact_store,
    ).assemble_from_final_state(
        SubAgentInvocation(
            dataset_id=int(effective_dataset_id) if effective_dataset_id is not None else 0,
            question=payload.question,
            resolved_question=lead_agent_context.get("resolved_question") or payload.question,
            turn_index=getattr(conversation_state, "turn_index", None),
            prior_capsule_status=final_state.get("prior_capsule_status") or prior_capsule_status,
        ),
        final_state,
        conversation_id=conv_id,
        trace_id=trace_context.trace_id,
    )
    subagent_tool_visible = jsonable_encoder(
        subagent_tool_result.llm_visible.model_dump(mode="json")
    )
    subagent_tool_trace = jsonable_encoder(subagent_tool_result.trace_metadata)
    subagent_control_plane = jsonable_encoder(
        subagent_tool_result.control_plane.model_dump(
            mode="json",
            exclude={"raw_error"},
        )
    )
    if subagent_control_plane_sink is not None:
        subagent_control_plane_sink.clear()
        subagent_control_plane_sink.append(subagent_control_plane)
    if subagent_control_plane.get("result_ref"):
        final_state["result_ref"] = subagent_control_plane.get("result_ref")
    if subagent_control_plane.get("report_ref"):
        final_state["report_ref"] = subagent_control_plane.get("report_ref")

    sql = final_state.get("sql")
    sql_list = final_state.get("sql_list") or []
    token_usage = final_state.get("token_usage")
    execution_path = (
        final_state.get("entry_route")
        or final_state.get("entry_intent")
        or trace_context.execution_path
        or "unknown"
    )
    trace_context.execution_path = execution_path
    active_obs_context = current_observability_context.get()
    if active_obs_context:
        trace_context.prompt_versions.update(active_obs_context.prompt_versions)
    multiturn_observability_metrics = _multiturn_observability_metrics(
        lead_agent_context=lead_agent_context,
        final_state=final_state,
    )
    query_profile = _build_query_profile(
        final_state=final_state,
        lead_agent_context=lead_agent_context,
        route_decision=route_decision,
        step_traces=step_traces,
        sql=sql,
        sql_list=sql_list,
        execution_path=execution_path,
        effective_dataset_id=effective_dataset_id,
    )
    explainability = _build_explainability(
        query_profile=query_profile,
        answer_explanation=answer_explanation,
    )
    trace_query_task_capsule = _safe_query_task_capsule_for_trace(
        final_state.get("query_task_capsule")
    )
    trace_metadata = {
        "status": "failed" if error else "success",
        "execution_path": execution_path,
        "original_question": payload.question,
        "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
        "entry_intent": final_state.get("entry_intent"),
        "entry_route": final_state.get("entry_route"),
        "blueprint_id": final_state.get("blueprint_id"),
        "knowledge_term_id": final_state.get("knowledge_term_id"),
        "selected_term_id": final_state.get("selected_term_id"),
        "lead_agent_context": lead_agent_context,
        "time_context": lead_agent_context.get("time_context"),
        "route_decision": route_decision,
        "schema_status": lead_agent_context.get("schema_status"),
        "manifest_version": route_decision.get("manifest_version"),
        "bound_schema_version": route_decision.get("bound_schema_version"),
        "report_owner": final_state.get("report_owner"),
        "subagent_report_skipped": final_state.get("subagent_report_skipped"),
        "lead_agent_report": final_state.get("lead_agent_report"),
        "prior_capsule_status": final_state.get("prior_capsule_status"),
        "multiturn_context": final_state.get("multiturn_context"),
        "multiturn_refinement": lead_agent_context.get("multiturn_refinement"),
        "turn_type": final_state.get("turn_type"),
        "turn_event": final_state.get("turn_event"),
        "query_task_capsule": trace_query_task_capsule,
        "multiturn_fast_path": final_state.get("multiturn_fast_path"),
        "merge_debug": final_state.get("merge_debug"),
        "out_capsule": final_state.get("out_capsule"),
        "result_artifact": final_state.get("result_artifact"),
        "candidate_assets": final_state.get("candidate_assets"),
        "query_plan": final_state.get("query_plan"),
        "query_plan_debug": final_state.get("query_plan_debug"),
        "subagent_tool_result": subagent_tool_visible,
        "subagent_tool_trace": subagent_tool_trace,
        "repair_plan": _repair_plan_summary(final_state),
        "multiturn_metrics": multiturn_observability_metrics,
        "query_profile": query_profile,
        "explainability": explainability,
        "prompt_versions": trace_context.prompt_versions,
    }
    tracer.update_trace_output(trace_context, output=answer, metadata=trace_metadata)

    # jsonable_encoder 把 datetime / Decimal 等转为 JSON 安全类型，再存 JSON 列
    response_metadata = jsonable_encoder(  # 存 JSON 列前清理 datetime/Decimal 等类型。
        {
            "answer_explanation": answer_explanation,
            "lead_agent_context": lead_agent_context,
            "original_question": payload.question,
            "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
            "time_context": lead_agent_context.get("time_context"),
            "route_decision": route_decision,
            "schema_status": lead_agent_context.get("schema_status"),
            "report_owner": final_state.get("report_owner"),
            "subagent_report_skipped": final_state.get("subagent_report_skipped"),
            "lead_agent_report": final_state.get("lead_agent_report"),
            "prior_capsule_status": final_state.get("prior_capsule_status"),
            "multiturn_context": final_state.get("multiturn_context"),
            "multiturn_refinement": lead_agent_context.get("multiturn_refinement"),
            "turn_type": final_state.get("turn_type"),
            "turn_event": final_state.get("turn_event"),
            "query_task_capsule": trace_query_task_capsule,
            "multiturn_fast_path": final_state.get("multiturn_fast_path"),
            "merge_debug": final_state.get("merge_debug"),
            "out_capsule": final_state.get("out_capsule"),
            "result_artifact": final_state.get("result_artifact"),
            "candidate_assets": final_state.get("candidate_assets"),
            "query_plan": final_state.get("query_plan"),
            "query_plan_debug": final_state.get("query_plan_debug"),
            "subagent_tool_result": subagent_tool_visible,
            "repair_plan": _repair_plan_summary(final_state),
            "route_payload": final_state.get("route_payload"),
            "clarification_resolution": final_state.get("clarification_resolution_result"),
            "query_profile": query_profile,
            "explainability": explainability,
            "langfuse": {
                "trace_id": trace_context.trace_id,
                "session_id": trace_context.session_id,
                "release": trace_context.release,
                "environment": trace_context.environment,
                "prompt_label": trace_context.prompt_label,
                "base_url": trace_context.base_url,
                "project_id": trace_context.project_id,
                "trace_url": trace_context.trace_url,
                "enabled": trace_context.enabled,
                "active": trace_context.active,
                "prompt_versions": trace_context.prompt_versions,
            },
            "observability": trace_context.observability_payload(),
        }
    )
    assistant_message = models.Message(
        conversation_id=conv_id,
        role="assistant",
        content=answer,
        sql_list=sql_list,
        token_usage=jsonable_encoder(token_usage),
        step_trace=jsonable_encoder(step_traces),
        response_metadata=response_metadata,
    )
    db.add(assistant_message)  # assistant 消息落库后，历史回放才能拿到完整 step_trace。
    db.commit()
    db.refresh(assistant_message)
    _log_chat_stream_checkpoint(  # DB 落库确认点，message_id 可用于回查历史消息。
        "assistant_message_saved",
        conversation_id=conv_id,
        message_id=assistant_message.id,
        effective_dataset_id=effective_dataset_id,
        step_trace_count=len(step_traces),
        response_metadata_keys=sorted(response_metadata.keys())
        if isinstance(response_metadata, dict)
        else [],
    )
    total_tokens = 0
    if isinstance(token_usage, dict):
        total_tokens = int(token_usage.get("total_tokens") or 0)
    if trace_context.trace_id:
        db.add(
            models.ObservabilityTraceIndex(
                langfuse_trace_id=trace_context.trace_id,
                langfuse_session_id=trace_context.session_id,
                conversation_id=conv_id,
                message_id=assistant_message.id,
                dataset_id=effective_dataset_id,
                entry_route=execution_path,
                status="failed" if error else "success",
                total_tokens=total_tokens,
                total_cost=0,
                metadata_json=jsonable_encoder(trace_metadata),
            )
        )
        if error or sql_retry_trace:
            db.add(
                models.TraceAnnotationCandidate(
                    langfuse_trace_id=trace_context.trace_id,
                    conversation_id=conv_id,
                    message_id=assistant_message.id,
                    dataset_id=effective_dataset_id,
                    reason="sql_failure" if error else "sql_retry",
                    payload=jsonable_encoder(
                        {
                            "error": error,
                            "sql_retry_trace": sql_retry_trace,
                            "sql_diagnosis": sql_diagnosis,
                        }
                    ),
                )
            )
        db.commit()

    final_payload = {
        "type": "final",
        "sql": sql,
        "sql_list": sql_list,
        "answer": answer,
        "entry_intent": final_state.get("entry_intent"),
        "entry_route": final_state.get("entry_route"),
        "entry_reason": final_state.get("entry_reason"),
        "blueprint_id": final_state.get("blueprint_id"),
        "blueprint_match": final_state.get("blueprint_match"),
        "knowledge_term_id": final_state.get("knowledge_term_id"),
        "selected_term_id": final_state.get("selected_term_id"),
        "lead_agent_context": lead_agent_context,
        "original_question": payload.question,
        "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
        "time_context": lead_agent_context.get("time_context"),
        "route_decision": route_decision,
        "schema_status": lead_agent_context.get("schema_status"),
        "manifest_version": route_decision.get("manifest_version"),
        "bound_schema_version": route_decision.get("bound_schema_version"),
        "report_owner": final_state.get("report_owner"),
        "subagent_report_skipped": final_state.get("subagent_report_skipped"),
        "lead_agent_report": final_state.get("lead_agent_report"),
        "prior_capsule_status": final_state.get("prior_capsule_status"),
        "multiturn_context": final_state.get("multiturn_context"),
        "multiturn_refinement": lead_agent_context.get("multiturn_refinement"),
        "turn_type": final_state.get("turn_type"),
        "turn_event": final_state.get("turn_event"),
        "query_task_capsule": trace_query_task_capsule,
        "multiturn_fast_path": final_state.get("multiturn_fast_path"),
        "merge_debug": final_state.get("merge_debug"),
        "out_capsule": final_state.get("out_capsule"),
        "result_artifact": final_state.get("result_artifact"),
        "candidate_assets": final_state.get("candidate_assets"),
        "query_plan": final_state.get("query_plan"),
        "query_plan_debug": final_state.get("query_plan_debug"),
        "route_payload": final_state.get("route_payload"),
        "clarification_resolution": final_state.get("clarification_resolution_result"),
        "term_normalization": final_state.get("term_normalization"),
        "semantic_asset_resolution": final_state.get("semantic_asset_resolution"),
        "metric_resolution": final_state.get("metric_resolution"),
        "dataset_context_debug": final_state.get("dataset_context_debug"),
        "datasource_context": final_state.get("datasource_context"),
        "dsl": final_state.get("dsl"),
        "generation_mode": final_state.get("generation_mode"),
        "sql_result": None,
        "result_ref": final_state.get("result_ref"),
        "report_ref": final_state.get("report_ref"),
        "repair_plan_ref": final_state.get("repair_plan_ref"),
        "repair_failure_class": final_state.get("repair_failure_class"),
        "repair_status": final_state.get("repair_status"),
        "repair_attempts": final_state.get("repair_attempts"),
        "repair_requires_user_confirmation": final_state.get(
            "repair_requires_user_confirmation"
        ),
        "repair_plan": _repair_plan_summary(final_state),
        "sql_diagnosis": sql_diagnosis,
        "sql_audit_result": final_state.get("sql_audit_result"),
        "sql_retry_trace": sql_retry_trace,
        "answer_explanation": answer_explanation,
        "query_profile": query_profile,
        "explainability": explainability,
        "response_metadata": response_metadata,
        "schema_tokens": final_state.get("schema_tokens"),
        "conversation_id": conv_id,
        "message_id": assistant_message.id,
        "task_id": f"conv-{conv_id}-msg-{assistant_message.id}",
        "trace_id": trace_context.trace_id,
        "title": conv.title,
        "langfuse_trace_id": trace_context.trace_id,
        "langfuse_session_id": trace_context.session_id,
        "observability": trace_context.observability_payload(),
        "multiturn_observability_metrics": multiturn_observability_metrics,
    }
    _attach_retry_checkpoint_to_final_payload(  # final 发出前注册安全 retry ref，前端只拿 ref 发起重试。
        final_payload,
        conversation_store=conversation_store,
        business_session_id=observability_session_id,
        user_id=str(conv.user_id or 1),
        conversation_id=conv_id,
        message_id=assistant_message.id,
    )
    _attach_artifact_card_refs_to_final_payload(final_payload)  # 统一生成 ArtifactCard/refs，不把 raw 结果放进 final。
    _sync_artifact_metadata_to_assistant_message(  # assistant message metadata 作为历史回放真相源。
        db=db,
        assistant_message=assistant_message,
        final_payload=final_payload,
    )
    query_artifact_store.attach_message_id(  # 只把 artifact:<uuid> 反连到 assistant message，trace/checkpoint 不进 query_artifact。
        _artifact_refs_for_query_artifact(final_payload),
        message_id=int(assistant_message.id),
    )
    _log_chat_stream_checkpoint("final_payload_ready", **_chat_stream_log_summary(final_payload))  # 对齐 DevTools final。
    yield _sse_data(
        _with_event_envelope(
            final_payload,
            event_type=_final_event_type(final_payload),
            visibility="user_visible",
            payload_fields=(
                "answer",
                "entry_route",
                "entry_reason",
                "result_ref",
                "report_ref",
                "artifact_card",
                "primary_ref",
                "related_refs",
                "task_id",
                "trace_id",
                "retry_checkpoint",
                "repair_plan_ref",
                "repair_failure_class",
                "repair_status",
                "repair_attempts",
                "repair_requires_user_confirmation",
                "repair_plan",
            ),
        )
    )  # final 发出后客户端可能立即断开。
    if not defer_trace_close:
        tracer.close_trace(trace_context)
    obs_context_manager.__exit__(None, None, None)


def _persist_dataset_confirmation_fact(
    *,
    store: ConversationStore,
    state: models.ConversationState,
    pending_resolution: dict,
) -> None:
    """把用户确认的数据集写入 conversation_state.facts，供后续同一 task 继续执行。"""

    if not (
        isinstance(pending_resolution, dict)
        and pending_resolution.get("status") == "resolved"
        and pending_resolution.get("type") == "dataset"
    ):
        return
    confirmed_dataset_id = _coerce_int(
        pending_resolution.get("confirmed_dataset_id") or pending_resolution.get("dataset_id")
    )
    if confirmed_dataset_id is None:
        return
    facts = [
        item
        for item in (state.facts or [])
        if not (isinstance(item, dict) and item.get("kind") == "dataset_confirmation")
    ]
    facts.append(
        {
            "kind": "dataset_confirmation",
            "confirmed_dataset_id": confirmed_dataset_id,
            "retry_checkpoint": pending_resolution.get("retry_checkpoint") or {},
        }
    )
    state.facts = facts
    store.db.add(state)
    store.db.commit()
    store.db.refresh(state)


def _persist_artifact_refs_fact(
    *,
    store: ConversationStore,
    state: models.ConversationState,
    final_payload: dict,
) -> None:
    """把本轮公开 artifact refs 写入 conversation_state；不迁移旧会话、不保存 raw 结果。"""

    task_id = final_payload.get("task_id")
    primary_ref = final_payload.get("primary_ref")
    related_refs = final_payload.get("related_refs") or []
    if not (task_id or primary_ref or related_refs):
        return
    refs_fact = {
        "kind": "artifact_refs",
        "task_id": task_id,
        "message_id": final_payload.get("message_id"),
        "trace_id": final_payload.get("trace_id") or final_payload.get("langfuse_trace_id"),
        "primary_ref": primary_ref,
        "related_refs": related_refs,
    }
    facts = [
        item
        for item in (state.facts or [])
        if not (
            isinstance(item, dict)
            and item.get("kind") == "artifact_refs"
            and item.get("task_id") == task_id
        )
    ]
    facts.append(jsonable_encoder(refs_fact))
    state.facts = facts
    store.db.add(state)
    store.db.commit()
    store.db.refresh(state)


def _persist_repair_plan_fact(
    *,
    store: ConversationStore,
    state: models.ConversationState,
    final_payload: dict,
) -> None:
    """把 RepairPlan 公开 ref 写入 conversation_state；不保存字段级 patch 或 SQL。"""

    repair_plan_ref = final_payload.get("repair_plan_ref")
    if not repair_plan_ref:
        return
    task_id = final_payload.get("task_id")
    repair_fact = {
        "kind": "repair_plan",
        "task_id": task_id,
        "message_id": final_payload.get("message_id"),
        "trace_id": final_payload.get("trace_id") or final_payload.get("langfuse_trace_id"),
        "repair_plan_ref": repair_plan_ref,
        "failure_class": final_payload.get("repair_failure_class"),
        "repair_status": final_payload.get("repair_status"),
        "attempts": final_payload.get("repair_attempts") or 0,
        "requires_user_confirmation": bool(
            final_payload.get("repair_requires_user_confirmation")
        ),
        "checkpoint_ref": _checkpoint_ref_from_payload(final_payload),
    }
    facts = [
        item
        for item in (state.facts or [])
        if not (
            isinstance(item, dict)
            and item.get("kind") == "repair_plan"
            and item.get("task_id") == task_id
        )
    ]
    facts.append(jsonable_encoder(repair_fact))
    state.facts = facts
    store.db.add(state)
    store.db.commit()
    store.db.refresh(state)


def _attach_retry_checkpoint_to_final_payload(
    final_payload: dict,
    *,
    conversation_store: ConversationStore | None,
    business_session_id: str | None,
    user_id: str,
    conversation_id: int | None,
    message_id: int | None,
) -> None:
    """为 final payload 挂载安全 checkpoint_ref，避免前端携带内部执行状态。"""

    if conversation_store is None or not business_session_id or not conversation_id:
        return
    dataset_id = _coerce_int(
        (final_payload.get("route_decision") or {}).get("dataset_id")
        or final_payload.get("dataset_id")
    )
    if dataset_id is None:
        return
    checkpoint_kind = (
        "artifact_generation_failed"
        if final_payload.get("error") and final_payload.get("result_ref")
        else "query_context_ready"
    )
    task_id = _final_payload_task_id(final_payload)
    try:
        checkpoint_ref = conversation_store.register_retry_checkpoint(
            session_id=business_session_id,
            checkpoint_kind=checkpoint_kind,
            user_id=user_id,
            conversation_id=conversation_id,
            task_id=task_id,
            permission_scope=f"dataset:{dataset_id}",
            context={
                "question": final_payload.get("original_question")
                or final_payload.get("resolved_question"),
                "dataset_id": dataset_id,
                "route_decision": final_payload.get("route_decision"),
                "time_context": final_payload.get("time_context"),
                "query_plan": final_payload.get("query_plan"),
                "result_ref": final_payload.get("result_ref"),
                "report_ref": final_payload.get("report_ref"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("retry checkpoint 注册失败，跳过 final 引用: %s", exc)
        return
    checkpoint_payload = {
        "checkpoint_ref": checkpoint_ref,
        "checkpoint_kind": checkpoint_kind,
    }
    final_payload["retry_checkpoint"] = checkpoint_payload
    response_metadata = final_payload.setdefault("response_metadata", {})
    if isinstance(response_metadata, dict):
        response_metadata["retry_checkpoint"] = checkpoint_payload


def _final_payload_last_success_gate(final_payload: dict) -> tuple[bool, str | None]:
    """判断 final 是否可写 last_success_task；只有真实成功查询才进入多轮承接。"""
    if final_payload.get("error"):
        return False, "unsuccessful_final"
    route_payload = (
        final_payload.get("route_payload")
        if isinstance(final_payload.get("route_payload"), dict)
        else {}
    )
    route_kind = str(route_payload.get("kind") or "")
    if route_kind in {
        "clarification",
        "query_plan_clarification",
        "query_plan_reject",
        "analysis_blueprint_error",
        "not_found",
        "not_applicable",
    }:
        return False, "unsuccessful_final"
    if route_payload.get("missing"):
        return False, "unsuccessful_final"
    if final_payload.get("sql_diagnosis"):
        return False, "unsuccessful_final"
    repair_status = str(final_payload.get("repair_status") or "").lower()
    if repair_status in {"failed", "blocked"}:
        return False, "unsuccessful_final"
    blueprint_status = str(final_payload.get("blueprint_outcome_status") or "").lower()
    if blueprint_status in {"clarification", "error", "not_found", "not_applicable"}:
        return False, "unsuccessful_final"
    query_plan = (
        final_payload.get("query_plan")
        if isinstance(final_payload.get("query_plan"), dict)
        else {}
    )
    if query_plan.get("execution_strategy") in {"clarify", "reject"}:
        return False, "unsuccessful_final"
    if final_payload.get("entry_route") in {"clarify", "reject"}:
        return False, "unsuccessful_final"
    return True, None


def _persist_completed_turn(
    *,
    store: ConversationStore,
    state: models.ConversationState,
    user_id: str,
    business_session_id: str,
    effective_payload: schemas.ChatRequest,
    final_payload: dict,
    pending_resolution: dict,
    payload_question: str,
    trace_context_sink: list,
    subagent_control_plane: dict | None = None,
) -> bool:
    """把完成轮的胶囊、状态、澄清和追踪写入 ConversationStore。

    必须在 SSE yield final 事件之前同步调用——SSE 客户端在收到 final 后会
    立即断开，导致 yield 之后的代码因 CancelledError 不执行。
    返回是否成功写入。
    """
    final_session_id = business_session_id
    final_state = state
    if (
        effective_payload.session_id is None
        and effective_payload.conversation_id is None
        and final_payload.get("conversation_id")
    ):
        final_session_id = session_key(None, int(final_payload["conversation_id"]))
        final_state = store.load_or_create(session_id=final_session_id, user_id=user_id)
    active_dataset_id = (
        final_payload.get("route_decision", {}).get("dataset_id")
        or final_payload.get("dataset_id")
        or effective_payload.dataset_id
    )
    settings = get_settings()
    if isinstance(subagent_control_plane, list):
        control_planes = [item for item in subagent_control_plane if isinstance(item, dict)]
    elif isinstance(subagent_control_plane, dict):
        control_planes = [subagent_control_plane]
    else:
        control_planes = []
    updated_capsules = None
    for item in control_planes:
        capsule = item.get("capsule") if isinstance(item.get("capsule"), dict) else None
        capsule_dataset_id = (
            capsule.get("dataset_id")
            if isinstance(capsule, dict)
            else item.get("dataset_id")
        )
        candidate_capsules = store.with_updated_capsule(  # 将 SubAgent 返回 capsule 写入对应 dataset 桶。
            final_state,
            dataset_id=capsule_dataset_id,
            capsule=capsule,
        )
        if candidate_capsules is not None:
            final_state.subagent_capsules = candidate_capsules
            updated_capsules = candidate_capsules
    if updated_capsules is None:
        updated_capsules = store.with_updated_capsule(  # 无控制面 capsule 时回退使用 final payload。
            final_state,
            dataset_id=active_dataset_id,
            capsule=final_payload.get("out_capsule"),
        )
    pending_for_store = pending_clarification_from_final_payload(  # 从 final payload 提取下一轮 pending 澄清。
        final_payload,
        original_question=payload_question,
    )
    executed_question = (
        final_payload.get("original_question")
        or final_payload.get("resolved_question")
        or payload_question
    )
    logger.info(
        "[ConversationState] 准备写入完成轮: session_id=%s, active_dataset_id=%s, "
        "final_error=%s, entry_route=%s, query_plan_type=%s, has_sql=%s, "
        "subagent_control_planes=%s",
        final_session_id,
        active_dataset_id,
        final_payload.get("error"),
        final_payload.get("entry_route"),
        (final_payload.get("query_plan") or {}).get("query_type")
        if isinstance(final_payload.get("query_plan"), dict)
        else None,
        bool(final_payload.get("sql")),
        len(control_planes),
    )
    persisted_state = store.append_completed_turn(  # SSE final 前同步写入完成轮，保证下一轮读到状态。
        session_id=final_session_id,
        question=payload_question,
        answer=final_payload.get("answer"),
        conversation_id=final_payload.get("conversation_id") or effective_payload.conversation_id,
        active_dataset_id=active_dataset_id,
        resolved_time_context=final_payload.get("time_context"),
        pending_clarification=pending_for_store,
        clear_pending_clarification=bool(
            pending_for_store is None
            and (
                pending_resolution.get("clear_pending")
                or pending_resolution.get("status") in {"resolved", "cleared", "inject"}
            )
        ),
        subagent_capsules=updated_capsules,
        trace_context=trace_context_sink[0] if trace_context_sink else None,
    )
    _persist_dataset_confirmation_fact(  # 用户选择候选数据集后，记录确认结果和 checkpoint 供同一任务重试。
        store=store,
        state=persisted_state,
        pending_resolution=pending_resolution,
    )
    _persist_artifact_refs_fact(  # 保存本轮公开 refs，后续计划/验收可按 task_id 追溯，不写 raw 结果。
        store=store,
        state=persisted_state,
        final_payload=final_payload,
    )
    _persist_repair_plan_fact(  # RepairPlan 只记录脱敏 ref 和状态，字段级 patch 不进入 conversation_state。
        store=store,
        state=persisted_state,
        final_payload=final_payload,
    )
    last_success_task = None
    last_success_task_write_status: dict[str, Any] = {"status": "not_built"}
    last_success_allowed, last_success_block_reason = _final_payload_last_success_gate(final_payload)
    route_decision = final_payload.get("route_decision") or {}
    control_plane_task = next(
        (
            item.get("last_success_task")
            for item in control_planes
            if isinstance(item.get("last_success_task"), dict)
        ),
        None,
    )
    if not last_success_allowed:
        last_success_task_write_status = {
            "status": "skipped",
            "reason": last_success_block_reason or "unsuccessful_final",
        }
    elif isinstance(control_plane_task, dict):
        last_success_task = control_plane_task
        last_success_task_write_status = {"status": "ready", "source": "subagent_control_plane"}
    else:
        try:
            last_success_task = build_success_task_state(
                question=executed_question,
                dataset_id=_coerce_int(active_dataset_id),
                query_plan=final_payload.get("query_plan"),
                dsl=final_payload.get("dsl"),
                sql=final_payload.get("sql"),
                sql_result=final_payload.get("sql_result"),
                schema_version=route_decision.get("bound_schema_version")
                or final_payload.get("bound_schema_version"),
                manifest_version=route_decision.get("manifest_version")
                or final_payload.get("manifest_version"),
                turn_index=getattr(final_state, "turn_index", None),
                result_artifact=final_payload.get("result_artifact"),
                max_tokens=int(
                    getattr(settings, "MULTITURN_LAST_SUCCESS_TASK_MAX_TOKENS", 2000)
                    or 2000
                ),
            )
            last_success_task_write_status = {"status": "ready", "source": "final_payload"}
        except CapsuleSizeExceededError as exc:
            last_success_task_write_status = {
                "status": "skipped",
                "reason": "size_exceeded",
                "estimated_tokens": exc.estimated_tokens,
                "max_tokens": exc.max_tokens,
            }
            logger.warning(
                "[_stream_chat] last_success_task 超出预算，跳过写入: session_id=%s, estimated_tokens=%s, max_tokens=%s",
                final_session_id,
                exc.estimated_tokens,
                exc.max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            last_success_task_write_status = {
                "status": "skipped",
                "reason": "build_failed",
                "error": str(exc),
            }
            logger.warning(
                "[_stream_chat] last_success_task 构造失败，跳过写入: session_id=%s, error=%s",
                final_session_id,
                exc,
            )
    logger.info(
        "[ConversationState] last_success_task 构造结果: session_id=%s, "
        "write_status=%s, task=%s",
        final_session_id,
        json.dumps(last_success_task_write_status, ensure_ascii=False, default=str),
        json.dumps(
            _summarize_last_success_task(last_success_task),
            ensure_ascii=False,
            default=str,
        ),
    )
    has_last_success_query_target = has_query_target(last_success_task)
    if last_success_allowed and has_last_success_query_target:
        thread_state = store.update_thread_state(
            final_session_id,
            {
                "last_success_task": last_success_task,
                "active_task": None,
                "last_success_task_write_status": last_success_task_write_status,
            },
            user_id=user_id,
        )
        logger.info(
            "[ConversationState] thread_state 已写入 last_success_task: "
            "session_id=%s, thread_keys=%s, last_success_task=%s, write_status=%s",
            final_session_id,
            sorted(thread_state.keys()),
            json.dumps(
                _summarize_last_success_task(thread_state.get("last_success_task")),
                ensure_ascii=False,
                default=str,
            ),
            json.dumps(
                thread_state.get("last_success_task_write_status"),
                ensure_ascii=False,
                default=str,
            ),
        )
    else:
        if last_success_task_write_status.get("status") == "ready":
            last_success_task_write_status = {
                "status": "skipped",
                "reason": "no_query_target",
                "source": last_success_task_write_status.get("source"),
            }
        thread_state = store.update_thread_state(
            final_session_id,
            {
                "active_task": None,
                "last_success_task_write_status": last_success_task_write_status,
            },
            user_id=user_id,
        )
        logger.info(
            "[ConversationState] thread_state 未写入 last_success_task: "
            "session_id=%s, reason=%s, thread_keys=%s, write_status=%s",
            final_session_id,
            last_success_task_write_status.get("reason")
            or last_success_task_write_status.get("status"),
            sorted(thread_state.keys()),
            json.dumps(
                thread_state.get("last_success_task_write_status"),
                ensure_ascii=False,
                default=str,
            ),
        )
    logger.info(
        "[_stream_chat] 多轮状态已写入: session_id=%s, turn_index=%s, active_dataset_id=%s",
        final_session_id,
        final_state.turn_index,
        active_dataset_id,
    )
    return True


async def _stream_chat(payload: schemas.ChatRequest, db: Session):
    """多轮状态包装层。

    默认 feature flag 关闭时直接走原单轮链路；开启后负责 session 锁和完成轮次写回。
    """

    settings = get_settings()
    # wrapper_start 记录 feature flag 和 session 输入，先判断本轮是否会进入多轮状态包装。
    _log_chat_stream_checkpoint(
        "wrapper_start",
        question_preview=payload.question[:80],
        payload_dataset_id=payload.dataset_id,
        conversation_id=payload.conversation_id,
        session_id=payload.session_id,
        multiturn_enabled=bool(settings.MULTITURN_ENABLED),
    )
    if not settings.MULTITURN_ENABLED:
        # 关闭多轮时直接下钻单轮链路，后续不会出现锁和 ConversationState 写回日志。
        _log_chat_stream_checkpoint(
            "multiturn_disabled",
            conversation_id=payload.conversation_id,
            payload_dataset_id=payload.dataset_id,
        )
        async for event in _stream_chat_singleturn(payload, db):
            yield event
        return

    store = ConversationStore(db)
    business_session_id = session_key(payload.session_id, payload.conversation_id)
    if business_session_id == "conversation-new":
        business_session_id = f"request-{uuid.uuid4().hex[:16]}"
    user_id = "1"
    lock_owner = f"chat-{uuid.uuid4().hex[:12]}"
    state = store.load_or_create(session_id=business_session_id, user_id=user_id)
    lead_multiturn_context = store.lead_multiturn_context(state)
    logger.info(
        "[ConversationState] 读取会话状态: session_id=%s, summary=%s",
        business_session_id,
        json.dumps(
            _summarize_conversation_state(state, lead_context=lead_multiturn_context),
            ensure_ascii=False,
            default=str,
        ),
    )
    if not store.acquire_turn_lock(
        session_id=business_session_id,
        lock_owner=lock_owner,
        ttl_seconds=settings.MULTITURN_LOCK_TTL_SECONDS,
    ):
        # 锁冲突会直接返回 final，不进入单轮链路；这里记录 owner 和 TTL 便于排查并发请求。
        _log_chat_stream_checkpoint(
            "turn_lock_rejected",
            business_session_id=business_session_id,
            lock_owner=lock_owner,
            ttl_seconds=settings.MULTITURN_LOCK_TTL_SECONDS,
        )
        lock_payload = {
            "type": "final",
            "sql": None,
            "sql_list": [],
            "answer": "同一会话已有一轮问数正在处理中，请稍后再试。",
            "entry_intent": "multiturn_lock",
            "entry_route": "turn_pending",
            "conversation_id": payload.conversation_id,
        }
        _attach_artifact_card_refs_to_final_payload(lock_payload, include_card=False)
        yield _sse_data(
            _with_event_envelope(
                lock_payload,
                event_type="error.blocked",
                visibility="user_visible",
                payload_fields=("answer", "entry_route", "primary_ref", "related_refs", "task_id", "trace_id"),
            )
        )
        return
    # 锁获取成功后才解析 pending clarification，保证同一 session 只有一轮在改状态。
    _log_chat_stream_checkpoint(
        "turn_lock_acquired",
        business_session_id=business_session_id,
        lock_owner=lock_owner,
        ttl_seconds=settings.MULTITURN_LOCK_TTL_SECONDS,
    )

    final_payload: dict | None = None
    completed = False
    trace_context_sink: list = []
    subagent_control_plane_sink: list = []
    effective_payload = payload
    retry_restore = None
    if payload.retry_checkpoint_ref:
        yield _retry_sse_event(
            "retry.started",
            checkpoint_ref=payload.retry_checkpoint_ref,
        )
        retry_restore = store.restore_retry_checkpoint(
            payload.retry_checkpoint_ref,
            user_id=user_id,
            conversation_id=payload.conversation_id,
        )
        if retry_restore.retry_scope == "last_safe_checkpoint":
            restored_context = retry_restore.context or {}
            lead_multiturn_context = dict(lead_multiturn_context or {})
            lead_multiturn_context["retry_checkpoint"] = {
                "checkpoint_ref": retry_restore.checkpoint_ref,
                "checkpoint_kind": retry_restore.checkpoint_kind,
                "task_id": retry_restore.task_id,
                "retry_scope": retry_restore.retry_scope,
            }
            effective_payload = payload.model_copy(
                update={
                    "question": retry_restore.question or payload.question,
                    "dataset_id": retry_restore.dataset_id or payload.dataset_id,
                    "clarification_response": None,
                }
            )
            _log_chat_stream_checkpoint(  # retry 恢复只写业务上下文，不回放 SQL/schema/control_plane。
                "retry_checkpoint_restored",
                business_session_id=business_session_id,
                checkpoint_ref=retry_restore.checkpoint_ref,
                checkpoint_kind=retry_restore.checkpoint_kind,
                restored_dataset_id=retry_restore.dataset_id,
                restored_context_keys=sorted(restored_context.keys()),
            )
            yield _retry_sse_event(
                "retry.checkpoint_restored",
                checkpoint_ref=payload.retry_checkpoint_ref,
                retry_scope=retry_restore.retry_scope,
            )
        else:
            _log_chat_stream_checkpoint(  # checkpoint 失效时显式降级整任务，避免客户端误以为恢复成功。
                "retry_fallback_to_whole_task",
                business_session_id=business_session_id,
                checkpoint_ref=payload.retry_checkpoint_ref,
                reason=retry_restore.fallback_reason,
            )
            yield _retry_sse_event(
                "retry.fallback_to_whole_task",
                checkpoint_ref=payload.retry_checkpoint_ref,
                retry_scope=retry_restore.retry_scope,
                reason=retry_restore.fallback_reason,
            )
    if retry_restore and retry_restore.retry_scope == "last_safe_checkpoint":
        pending_resolution = {"status": "none", "reason": "retry_checkpoint_restored"}
    else:
        pending_resolution = store.resolve_pending_clarification(
            state,
            question=payload.question,
            clarification_response=payload.clarification_response,
        )
    logger.info(
        "[ConversationState] 澄清解析结果: session_id=%s, pending_resolution=%s",
        business_session_id,
        json.dumps(pending_resolution, ensure_ascii=False, default=str),
    )
    if (
        pending_resolution.get("status") == "resolved"
        and pending_resolution.get("type") == "dataset"
    ):
        effective_payload = payload.model_copy(
            update={
                "dataset_id": int(pending_resolution["dataset_id"]),
                "clarification_response": None,
            }
        )
    elif pending_resolution.get("status") == "inject" and pending_resolution.get("type") == "term":
        updates = {
            "clarification_response": pending_resolution.get("clarification_response") or {},
        }
        if pending_resolution.get("conversation_id") and payload.conversation_id is None:
            updates["conversation_id"] = int(pending_resolution["conversation_id"])
        if pending_resolution.get("dataset_id") and payload.dataset_id is None:
            updates["dataset_id"] = int(pending_resolution["dataset_id"])
        effective_payload = payload.model_copy(update=updates)
    try:
        async for event in _stream_chat_singleturn(
            effective_payload,
            db,
            multiturn_context=lead_multiturn_context,
            conversation_state=state,
            conversation_store=store,
            pending_resolution=pending_resolution,
            observability_session_id=business_session_id,
            trace_context_sink=trace_context_sink,
            subagent_control_plane_sink=subagent_control_plane_sink,
            defer_trace_close=True,
        ):
            data = event.get("data") if isinstance(event, dict) else None
            if data:
                try:
                    parsed = json.loads(data)
                    if parsed.get("type") == "final":
                        final_payload = parsed
                        _log_chat_stream_checkpoint(  # yield final 前的多轮状态写回触发点。
                            "wrapper_final_seen",
                            business_session_id=business_session_id,
                            summary=_chat_stream_log_summary(final_payload),
                        )
                        try:
                            completed = _persist_completed_turn(  # 必须在 yield final 前写库。
                                store=store,
                                state=state,
                                user_id=user_id,
                                business_session_id=business_session_id,
                                effective_payload=effective_payload,
                                final_payload=final_payload,
                                pending_resolution=pending_resolution,
                                payload_question=payload.question,
                                trace_context_sink=trace_context_sink,
                                subagent_control_plane=(
                                    subagent_control_plane_sink[0]
                                    if subagent_control_plane_sink
                                    else None
                                ),
                            )
                        except Exception as persist_exc:  # noqa: BLE001
                            logger.exception("[_stream_chat] 写入多轮状态失败: %s", persist_exc)
                        if payload.retry_checkpoint_ref:
                            if parsed.get("error"):
                                yield _retry_sse_event(
                                    "retry.failed",
                                    checkpoint_ref=payload.retry_checkpoint_ref,
                                    reason=str(parsed.get("error")),
                                )
                            else:
                                yield _retry_sse_event(
                                    "retry.completed",
                                    checkpoint_ref=payload.retry_checkpoint_ref,
                                )
                except json.JSONDecodeError:
                    pass
            yield event
    finally:
        if completed and trace_context_sink:
            tracer = get_observability_tracer()
            tracer.close_trace(trace_context_sink[0])
        if not completed:
            _log_chat_stream_checkpoint(
                "wrapper_incomplete",
                business_session_id=business_session_id,
                final_seen=final_payload is not None,
            )
        _log_chat_stream_checkpoint(  # finally 中留锁释放日志，避免会话长期 pending 难查。
            "turn_lock_released",
            business_session_id=business_session_id,
            lock_owner=lock_owner,
            completed=completed,
        )
        store.release_turn_lock(session_id=business_session_id, lock_owner=lock_owner)  # 客户端断开也必须释放锁。


@router.post("/stream")
def chat_stream(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    """流式问数接口，返回 SSE 事件流。"""
    _log_chat_stream_checkpoint(  # HTTP 入口只记录轻量请求面，细节由下游 checkpoint 补齐。
        "request_received",
        question_preview=payload.question[:80],
        payload_dataset_id=payload.dataset_id,
        conversation_id=payload.conversation_id,
        session_id=payload.session_id,
        has_clarification_response=payload.clarification_response is not None,
    )
    return EventSourceResponse(_stream_chat(payload, db))


@router.post("/feedback")
def chat_feedback(payload: schemas.ChatFeedback, db: Session = Depends(get_db)):
    """人工反馈接口，对接 LangGraph HumanFeedback 节点（Phase 3 完善）。"""
    return submit_message_feedback(
        db,
        message_id=payload.message_id,
        action=payload.action,
        comment=payload.comment,
        trace_id=payload.trace_id,
        reason=payload.reason,
    )


# ============================================================
# Phase 2: 上提 Merge 阶段到 LeadAgent — chat 层辅助
# ============================================================


def _build_out_capsule_for_chat(state: dict, updates: dict | None = None) -> dict:
    """Phase 2: 把 graph.nodes.build_out_capsule 暴露给 chat.py 的 out_capsule_factory。

    保留与 nodes.py 实现同语义（生成下一轮继续追问所需的 query_context + result_digest）。
    """
    from app.graph.nodes import build_out_capsule

    return build_out_capsule(state, updates)


def _early_trace_status(entry_route: str) -> str:
    """把早退路由映射成 trace index 状态。"""
    return "blocked" if entry_route == "reject" else "success"


def _early_trace_metadata(
    *,
    final_state: dict,
    lead_agent_context: dict,
    route_decision: dict,
    response_metadata: dict,
    trace_context: Any,
) -> dict:
    """组装早退分支的 trace metadata，保持与正常 final 分支字段对齐。"""
    active_obs_context = current_observability_context.get()
    if active_obs_context:
        trace_context.prompt_versions.update(active_obs_context.prompt_versions)
    return {
        "status": _early_trace_status(final_state.get("entry_route") or ""),
        "execution_path": final_state.get("entry_route") or final_state.get("entry_intent"),
        "original_question": final_state.get("original_question"),
        "resolved_question": final_state.get("resolved_question"),
        "entry_intent": final_state.get("entry_intent"),
        "entry_route": final_state.get("entry_route"),
        "entry_reason": final_state.get("entry_reason"),
        "blueprint_id": final_state.get("blueprint_id"),
        "knowledge_term_id": final_state.get("knowledge_term_id"),
        "lead_agent_context": lead_agent_context,
        "time_context": lead_agent_context.get("time_context"),
        "route_decision": route_decision,
        "schema_status": lead_agent_context.get("schema_status"),
        "route_payload": final_state.get("route_payload"),
        "turn_event": final_state.get("turn_event"),
        "response_metadata": response_metadata,
        "prompt_versions": trace_context.prompt_versions,
    }


def _early_langfuse_payload(trace_context: Any) -> dict:
    """提取前端和审计页需要的 Langfuse trace 信息。"""
    return {
        "trace_id": trace_context.trace_id,
        "session_id": trace_context.session_id,
        "release": trace_context.release,
        "environment": trace_context.environment,
        "prompt_label": trace_context.prompt_label,
        "base_url": trace_context.base_url,
        "project_id": trace_context.project_id,
        "trace_url": trace_context.trace_url,
        "enabled": trace_context.enabled,
        "active": trace_context.active,
        "prompt_versions": trace_context.prompt_versions,
    }


def _finalize_early_trace(
    *,
    db: Session,
    assistant_message: models.Message,
    effective_dataset_id: int | None,
    lead_agent_context: dict,
    route_decision: dict,
    trace_context: Any,
    response_metadata: dict,
    final_state: dict,
    answer: str,
    defer_trace_close: bool,
) -> dict:
    """早退分支在发送 final 前完成 trace 输出、索引落库和可观测 metadata。"""
    tracer = get_observability_tracer()
    trace_metadata = _early_trace_metadata(
        final_state=final_state,
        lead_agent_context=lead_agent_context,
        route_decision=route_decision,
        response_metadata=response_metadata,
        trace_context=trace_context,
    )
    response_metadata["langfuse"] = _early_langfuse_payload(trace_context)
    response_metadata["observability"] = trace_context.observability_payload()
    tracer.update_trace_output(trace_context, output=answer, metadata=trace_metadata)
    assistant_message.response_metadata = jsonable_encoder(response_metadata)

    if trace_context.trace_id:
        db.add(
            models.ObservabilityTraceIndex(
                langfuse_trace_id=trace_context.trace_id,
                langfuse_session_id=trace_context.session_id,
                conversation_id=assistant_message.conversation_id,
                message_id=assistant_message.id,
                dataset_id=effective_dataset_id,
                entry_route=trace_metadata.get("execution_path") or "early_return",
                status=trace_metadata["status"],
                total_tokens=0,
                total_cost=0,
                metadata_json=jsonable_encoder(trace_metadata),
            )
        )
    db.commit()
    db.refresh(assistant_message)
    if not defer_trace_close:
        tracer.close_trace(trace_context)
    return trace_metadata


async def _interpret_early_return(
    *,
    db: Session,
    conv: models.Conversation,
    payload: schemas.ChatRequest,
    effective_dataset_id: int | None,
    lead_agent_context: dict,
    route_decision: dict,
    trace_context: Any,
    defer_trace_close: bool,
    obs_context_manager: Any,
    interpret_payload: dict,
    turn_type: str,
    multiturn_context: dict | None,
    merge_debug: dict,
    gateway_step_payload: dict | None = None,
    query_task_capsule: dict | None = None,
):
    """interpret_result 早退：保存助手消息、emit SSE final 事件，不走 LangGraph。

    早退前会写入 trace output 和 TraceIndex，避免 SSE final 后断连丢失收尾逻辑。
    """
    answer = interpret_payload.get("answer") or "已生成解释。"
    entry_intent = interpret_payload.get("entry_intent") or "interpret"
    entry_route = interpret_payload.get("entry_route") or "interpret_result"
    route_payload = {
        "kind": "interpret_result",
        "answer": answer,
        "out_capsule": interpret_payload.get("out_capsule"),
    }
    final_state = {
        "original_question": payload.question,
        "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
        "entry_intent": entry_intent,
        "entry_route": entry_route,
        "route_payload": route_payload,
        "time_context": lead_agent_context.get("time_context"),
        "multiturn_context": multiturn_context,
        "merge_debug": merge_debug,
        "turn_type": turn_type,
        "turn_event": (
            gateway_step_payload.get("turn_event")
            if isinstance(gateway_step_payload, dict)
            else None
        ),
        "query_task_capsule": query_task_capsule,
        "sql_result": None,
    }
    response_metadata = jsonable_encoder(
        {
            "lead_agent_context": lead_agent_context,
            "original_question": payload.question,
            "resolved_question": final_state["resolved_question"],
            "route_decision": route_decision,
            "time_context": lead_agent_context.get("time_context"),
            "schema_status": lead_agent_context.get("schema_status"),
            "route_payload": route_payload,
            "multiturn_context": multiturn_context,
            "merge_debug": merge_debug,
            "turn_event": final_state.get("turn_event"),
            "query_task_capsule": query_task_capsule,
        }
    )
    step_trace = [
        step
        for step in (
            gateway_step_payload,
            _lead_agent_event(lead_agent_context),
            _route_decision_event(route_decision),
        )
        if step
    ]
    assistant_message = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        sql_list=[],
        step_trace=step_trace,
        response_metadata=response_metadata,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    trace_metadata = _finalize_early_trace(
        db=db,
        assistant_message=assistant_message,
        effective_dataset_id=effective_dataset_id,
        lead_agent_context=lead_agent_context,
        route_decision=route_decision,
        trace_context=trace_context,
        response_metadata=response_metadata,
        final_state=final_state,
        answer=answer,
        defer_trace_close=defer_trace_close,
    )
    obs_context_manager.__exit__(None, None, None)

    interpret_step = {
        "type": "step",
        "node": "interpret_result",
        "display_name": "interpret_result",
        "status": "done",
    }
    yield _sse_data(
        _with_event_envelope(
            interpret_step,
            event_type="answer.completed",
            visibility="trace_only",
            payload_fields=("node", "status"),
            metadata={"conversation_id": conv.id, "dataset_id": effective_dataset_id},
        )
    )
    # interpret early return 直接构造 final，需在 yield 前打点，否则客户端断开后可能看不到收尾。
    final_payload = {
        "type": "final",
        "sql": None,
        "sql_list": [],
        "answer": answer,
        "entry_intent": entry_intent,
        "entry_route": entry_route,
        "entry_reason": "interpret_result_early_return",
        "lead_agent_context": lead_agent_context,
        "original_question": payload.question,
        "resolved_question": final_state["resolved_question"],
        "time_context": lead_agent_context.get("time_context"),
        "route_decision": route_decision,
        "schema_status": lead_agent_context.get("schema_status"),
        "clarification": None,
        "route_payload": route_payload,
        "turn_event": final_state.get("turn_event"),
        "query_task_capsule": query_task_capsule,
        "sql_result": None,
        "query_profile": None,
        "explainability": None,
        "response_metadata": response_metadata,
        "conversation_id": conv.id,
        "message_id": assistant_message.id,
        "task_id": f"conv-{conv.id}-msg-{assistant_message.id}",
        "trace_id": trace_context.trace_id,
        "title": conv.title,
        "langfuse_trace_id": trace_context.trace_id,
        "langfuse_session_id": trace_context.session_id,
        "observability": trace_context.observability_payload(),
        "trace_metadata": trace_metadata,
        "out_capsule": interpret_payload.get("out_capsule"),
    }
    _attach_artifact_card_refs_to_final_payload(final_payload, include_card=False)
    _sync_artifact_metadata_to_assistant_message(
        db=db,
        assistant_message=assistant_message,
        final_payload=final_payload,
    )
    _log_chat_stream_checkpoint("interpret_final_payload_ready", **_chat_stream_log_summary(final_payload))
    yield _sse_data(
        _with_event_envelope(
            final_payload,
            event_type="answer.completed",
            visibility="user_visible",
            payload_fields=(
                "answer",
                "entry_route",
                "entry_reason",
                "out_capsule",
                "primary_ref",
                "related_refs",
                "task_id",
                "trace_id",
            ),
        )
    )


async def _early_route_return(
    *,
    db: Session,
    conv: models.Conversation,
    payload: schemas.ChatRequest,
    effective_dataset_id: int | None,
    lead_agent_context: dict,
    route_decision: dict,
    trace_context: Any,
    defer_trace_close: bool,
    obs_context_manager: Any,
    routing: dict,
    gateway_step_payload: dict | None = None,
    query_task_capsule: dict | None = None,
):
    """Phase 3: LeadAgent 入口路由早退（chitchat/reject/knowledge_qa/clarify）。

    直接保存助手消息、emit SSE final 事件，不调 LangGraph。
    """
    entry_intent = routing.get("entry_intent") or "early_return"
    entry_route = routing.get("entry_route") or "direct_answer"
    answer = routing.get("answer") or "已生成回答。"
    route_payload = routing.get("route_payload") or {"kind": entry_route}
    final_state = {
        "original_question": payload.question,
        "resolved_question": lead_agent_context.get("resolved_question") or payload.question,
        "entry_intent": entry_intent,
        "entry_route": entry_route,
        "entry_reason": routing.get("entry_reason"),
        "route_payload": route_payload,
        "turn_event": routing.get("turn_event") or route_payload.get("turn_event"),
        "query_task_capsule": query_task_capsule,
        "time_context": lead_agent_context.get("time_context"),
        "blueprint_id": routing.get("blueprint_id"),
        "knowledge_term_id": routing.get("knowledge_term_id"),
        "sql_result": None,
    }
    response_metadata = jsonable_encoder(
        {
            "lead_agent_context": lead_agent_context,
            "original_question": payload.question,
            "resolved_question": final_state["resolved_question"],
            "route_decision": route_decision,
            "time_context": lead_agent_context.get("time_context"),
            "schema_status": lead_agent_context.get("schema_status"),
            "route_payload": route_payload,
            "routing": routing,
            "turn_event": final_state.get("turn_event"),
            "query_task_capsule": query_task_capsule,
        }
    )
    step_trace = [
        step
        for step in (
            gateway_step_payload,
            _lead_agent_event(lead_agent_context),
            _route_decision_event(route_decision),
        )
        if step
    ]
    assistant_message = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        sql_list=[],
        step_trace=step_trace,
        response_metadata=response_metadata,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    trace_metadata = _finalize_early_trace(
        db=db,
        assistant_message=assistant_message,
        effective_dataset_id=effective_dataset_id,
        lead_agent_context=lead_agent_context,
        route_decision=route_decision,
        trace_context=trace_context,
        response_metadata=response_metadata,
        final_state=final_state,
        answer=answer,
        defer_trace_close=defer_trace_close,
    )
    obs_context_manager.__exit__(None, None, None)

    # 普通早退覆盖 reject/clarify/direct_answer/knowledge_qa，统一在 yield 前记录最终可见 payload。
    final_payload = {
        "type": "final",
        "sql": None,
        "sql_list": [],
        "answer": answer,
        "entry_intent": entry_intent,
        "entry_route": entry_route,
        "entry_reason": routing.get("entry_reason"),
        "lead_agent_context": lead_agent_context,
        "original_question": payload.question,
        "resolved_question": final_state["resolved_question"],
        "time_context": lead_agent_context.get("time_context"),
        "route_decision": route_decision,
        "schema_status": lead_agent_context.get("schema_status"),
        "clarification": None,
        "route_payload": route_payload,
        "turn_event": final_state.get("turn_event"),
        "query_task_capsule": query_task_capsule,
        "sql_result": None,
        "query_profile": None,
        "explainability": None,
        "response_metadata": response_metadata,
        "conversation_id": conv.id,
        "message_id": assistant_message.id,
        "task_id": f"conv-{conv.id}-msg-{assistant_message.id}",
        "trace_id": trace_context.trace_id,
        "title": conv.title,
        "langfuse_trace_id": trace_context.trace_id,
        "langfuse_session_id": trace_context.session_id,
        "observability": trace_context.observability_payload(),
        "trace_metadata": trace_metadata,
    }
    _attach_artifact_card_refs_to_final_payload(final_payload, include_card=False)
    _sync_artifact_metadata_to_assistant_message(
        db=db,
        assistant_message=assistant_message,
        final_payload=final_payload,
    )
    _log_chat_stream_checkpoint("early_final_payload_ready", **_chat_stream_log_summary(final_payload))
    yield _sse_data(
        _with_event_envelope(
            final_payload,
            event_type=_final_event_type(final_payload),
            visibility="user_visible",
            payload_fields=(
                "answer",
                "entry_route",
                "entry_reason",
                "route_payload",
                "primary_ref",
                "related_refs",
                "task_id",
                "trace_id",
            ),
        )
    )
