# ============================================================
# File Name   : bi_workbench.py
# Description:
#   BI 工作台外层工具契约与统一事件 envelope Schema。
#
# Responsibilities:
#   - 定义 ask_bi 请求、响应、事件信封和产物引用结构。
#   - 为 SSE 与未来 AgentScope event stream 复用同一业务事件协议。
#   - 约束用户可见协议，避免 SQL、schema、capsule 和 control_plane 泄露。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DatalogueEventType = Literal[
    "route.started",
    "dataset.selected",
    "clarification.required",
    "dataset.query.started",
    "dataset.query.completed",
    "repair.evaluated",
    "repair.plan_created",
    "repair.confirmation_required",
    "repair.patch_applied",
    "repair.rerun_started",
    "repair.rerun_completed",
    "repair.failed",
    "repair.blocked",
    "artifact.created",
    "answer.completed",
    "error.blocked",
]

DatalogueEventVisibility = Literal["user_visible", "trace_only", "control_plane"]

# 用户可见协议禁止承载内部执行面；字段名和字符串值都要扫描，避免 adapter 误把主链
# final_state 原样塞进 event payload / ArtifactCard。
FORBIDDEN_VISIBLE_KEYS = {
    "capsule",
    "control_plane",
    "data",
    "direct_sql",
    "dsl",
    "out_capsule",
    "patch",
    "query_task_capsule",
    "raw",
    "raw_result",
    "raw_sql",
    "records",
    "result",
    "result_rows",
    "rows",
    "sample_rows",
    "schema",
    "schema_context",
    "sql",
    "sql_list",
    "sql_result",
    "subagent_control_plane",
}

_SQL_TEXT_RE = re.compile(
    r"(?is)\b(select|insert|update|delete|drop|alter|create|with)\b"
    r".{0,200}\b(from|into|set|table|join|where|values)\b"
)


def _is_blocked_user_visible_key(key: str) -> bool:
    key_lower = key.lower()
    return key_lower in FORBIDDEN_VISIBLE_KEYS or "sql" in key_lower


def sanitize_event_payload(value: Any, *, key_name: str = "") -> Any:
    """递归清理 user_visible 事件，避免把执行明细和控制面主体下发给前端。"""

    if _is_blocked_user_visible_key(key_name):
        return None
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or _is_blocked_user_visible_key(key):
                continue
            safe_item = sanitize_event_payload(item, key_name=key)
            if safe_item in (None, "", [], {}):
                continue
            sanitized[key] = safe_item
        return sanitized
    if isinstance(value, list):
        # user_visible 只保留小型摘要列表，完整结果集必须通过 artifact/ref 访问。
        return [
            item
            for item in (sanitize_event_payload(item, key_name=key_name) for item in value[:8])
            if item not in (None, "", [], {})
        ]
    if isinstance(value, str):
        text = value.strip()
        if _SQL_TEXT_RE.search(text):
            return None
        return text[:1000]
    return value


def _contains_forbidden_visible_detail(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if _is_blocked_user_visible_key(key_text):
                return True
            if _contains_forbidden_visible_detail(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden_visible_detail(item) for item in value)
    if isinstance(value, str):
        text = value.lower()
        return any(
            token in text
            for token in (
                "raw_sql",
                "raw_result",
                "sql_result",
                "schema_context",
                "control_plane",
                "out_capsule",
            )
        ) or _SQL_TEXT_RE.search(text) is not None
    return False


class ArtifactRef(BaseModel):
    """外层 Agent 只能拿引用句柄，不能拿 artifact body 或执行结果明细。"""

    model_config = ConfigDict(extra="forbid")

    ref_id: str
    ref_type: Literal["result", "report", "artifact", "trace", "checkpoint", "repair_plan", "unknown"] = "artifact"
    label: str | None = None


class ArtifactAction(BaseModel):
    """ArtifactCard 上的动作声明；第一阶段只表达可用性，不直接执行副作用。"""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    label: str
    enabled: bool = True
    disabled_reason: str | None = None
    payload_ref: str | None = None


class ArtifactCard(BaseModel):
    """用户可见的轻量产物卡，只展示摘要、动作和引用。"""

    model_config = ConfigDict(extra="forbid")

    artifact_type: str = "bi_answer"
    title: str = "BI 查询结果"
    status: Literal["ready", "completed", "generating", "error", "partial", "unknown"] = "ready"
    summary: str = ""
    preview_payload: dict[str, Any] = Field(default_factory=dict)
    primary_ref: ArtifactRef | None = None
    related_refs: list[ArtifactRef] = Field(default_factory=list)
    actions: list[ArtifactAction] = Field(default_factory=list)
    refs: list[ArtifactRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_internal_details(self) -> "ArtifactCard":
        if _contains_forbidden_visible_detail(self.model_dump()):
            raise ValueError("artifact_card contains forbidden internal details")
        return self


class DatalogueEventEnvelope(BaseModel):
    """统一事件信封，后续 Chat、AgentScope 和工作台复用同一外层事件面。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex}")
    event_type: DatalogueEventType
    visibility: DatalogueEventVisibility = "user_visible"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None
    conversation_id: int | None = None
    trace_id: str | None = None

    @model_validator(mode="after")
    def _reject_user_visible_internal_details(self) -> "DatalogueEventEnvelope":
        if self.visibility == "user_visible" and (
            _contains_forbidden_visible_detail(self.payload)
            or _contains_forbidden_visible_detail(self.metadata)
        ):
            raise ValueError("user_visible event contains forbidden internal details")
        return self


class AskBIRequest(BaseModel):
    """ask_bi 唯一入口请求；caller 用于审计外层来源，不改变 BI 主链授权边界。"""

    model_config = ConfigDict(extra="forbid")

    question: str
    conversation_id: int | None = None
    caller: str
    confirmed_dataset_id: int | None = None
    context_refs: list[str | ArtifactRef] = Field(default_factory=list)
    request_options: dict[str, Any] = Field(default_factory=dict)


class AskBIResponse(BaseModel):
    """ask_bi 外层响应；只包含稳定摘要、事件、候选数据集和引用句柄。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    event_envelope: DatalogueEventEnvelope
    candidate_datasets: list[dict[str, Any]] = Field(default_factory=list)
    answer: str | None = None
    artifact_card: ArtifactCard | None = None
    primary_ref: ArtifactRef | None = None
    related_refs: list[ArtifactRef] = Field(default_factory=list)
    status: Literal["completed", "waiting_user", "blocked"]
    error: str | None = None

    @model_validator(mode="after")
    def _reject_internal_details(self) -> "AskBIResponse":
        if _contains_forbidden_visible_detail(self.model_dump()):
            raise ValueError("ask_bi response contains forbidden internal details")
        return self


def build_datalogue_event_envelope(
    *,
    event_type: DatalogueEventType,
    visibility: DatalogueEventVisibility,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    task_id: str | None = None,
    conversation_id: int | None = None,
    trace_id: str | None = None,
) -> DatalogueEventEnvelope:
    """构造统一事件 envelope；用户可见事件在这里集中执行脱敏。"""

    raw_payload = payload or {}
    raw_metadata = metadata or {}
    if visibility == "user_visible":
        safe_payload = sanitize_event_payload(raw_payload)
        safe_metadata = sanitize_event_payload(raw_metadata)
    else:
        safe_payload = raw_payload
        safe_metadata = raw_metadata
    return DatalogueEventEnvelope(
        event_type=event_type,
        visibility=visibility,
        payload=safe_payload if isinstance(safe_payload, dict) else {},
        metadata=safe_metadata if isinstance(safe_metadata, dict) else {},
        task_id=task_id,
        conversation_id=conversation_id,
        trace_id=trace_id,
    )


def validate_event_visibility(event: DatalogueEventEnvelope) -> DatalogueEventEnvelope:
    """显式校验事件可见性，供 P0.5/P0.6 测试和后续 chat 映射复用。"""

    return event.model_validate(event.model_dump())
