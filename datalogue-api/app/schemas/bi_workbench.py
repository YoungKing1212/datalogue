# ============================================================
# File Name   : bi_workbench.py
# Description:
#   BI 工作台外层工具与事件 envelope Schema。
#
# Responsibilities:
#   - 定义 ask_bi 请求、响应、ArtifactCard 和产物引用结构。
#   - 定义可被 SSE 与未来 AgentScope event stream 复用的业务事件协议。
#   - 统一处理用户可见协议的敏感字段脱敏边界。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DatalogueEventType = Literal[
    "route.started",
    "dataset.selected",
    "clarification.required",
    "dataset.query.started",
    "dataset.query.completed",
    "artifact.created",
    "answer.completed",
    "error.blocked",
]
DatalogueEventVisibility = Literal["user_visible", "trace_only", "control_plane"]


class EventVisibility(str, Enum):
    """统一事件可见性；AgentScope Shell 只消费 user_visible 和 trace_only 的安全映射。"""

    USER_VISIBLE = "user_visible"
    TRACE_ONLY = "trace_only"
    CONTROL_PLANE = "control_plane"


FORBIDDEN_VISIBLE_KEYS = {
    "capsule",
    "control_plane",
    "data",
    "database",
    "direct_sql",
    "dsl",
    "out_capsule",
    "query_task_capsule",
    "raw",
    "raw_result",
    "raw_results",
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


def _contains_forbidden_visible_detail(value: Any, *, key_name: str = "") -> bool:
    """扫描用户可见对象，字段名和典型 SQL 文本命中即视为内部细节泄漏。"""

    if _is_blocked_user_visible_key(key_name):
        return True
    if isinstance(value, dict):
        return any(
            not isinstance(key, str)
            or _is_blocked_user_visible_key(key)
            or _contains_forbidden_visible_detail(item, key_name=key)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_visible_detail(item, key_name=key_name) for item in value)
    if isinstance(value, str):
        return bool(_SQL_TEXT_RE.search(value.strip()))
    return False


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
        # 用户可见事件只保留小型摘要列表；完整结果集必须通过 artifact/ref 按需读取。
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


def sanitize_outer_payload(value: Any) -> Any:
    """AgentScope / ask_bi 外层响应兜底脱敏，语义上等同 user_visible payload 清理。"""

    return sanitize_event_payload(value)


class ArtifactRef(BaseModel):
    """外层 Agent 只能拿引用句柄，不能拿 artifact body 或执行结果明细。"""

    model_config = ConfigDict(extra="forbid")

    ref_id: str | None = None
    ref: str | None = None
    ref_type: Literal["result", "report", "artifact", "checkpoint", "answer", "trace", "unknown"] = "artifact"
    kind: str | None = None
    label: str | None = None
    title: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_ref_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if data.get("ref_id") is None and data.get("ref") is not None:
            data["ref_id"] = data["ref"]
        if data.get("ref") is None and data.get("ref_id") is not None:
            data["ref"] = data["ref_id"]
        if data.get("kind") is None and data.get("ref_type") is not None:
            data["kind"] = data["ref_type"]
        if data.get("label") is None and data.get("title") is not None:
            data["label"] = data["title"]
        if data.get("title") is None and data.get("label") is not None:
            data["title"] = data["label"]
        return data

    @model_validator(mode="after")
    def _require_public_ref(self) -> "ArtifactRef":
        if not self.ref_id:
            raise ValueError("artifact ref requires ref_id/ref")
        return self


class ArtifactAction(BaseModel):
    """ArtifactCard 上的动作声明；第一阶段只表达可用性，不直接执行副作用。"""

    model_config = ConfigDict(extra="forbid")

    action_id: str | None = None
    action_type: str | None = None
    label: str
    enabled: bool = True
    disabled_reason: str | None = None
    payload_ref: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_action_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if data.get("action_id") is None and data.get("action_type") is not None:
            data["action_id"] = data["action_type"]
        if data.get("action_type") is None and data.get("action_id") is not None:
            data["action_type"] = data["action_id"]
        return data

    @model_validator(mode="after")
    def _require_action_type(self) -> "ArtifactAction":
        if not self.action_id:
            raise ValueError("artifact action requires action_id/action_type")
        return self


class ArtifactCard(BaseModel):
    """用户可见的轻量产物卡，只展示摘要、动作和引用。"""

    model_config = ConfigDict(extra="forbid")

    artifact_type: str = "bi_answer"
    title: str = "BI 查询结果"
    status: Literal["ready", "pending", "blocked", "error"] = "ready"
    summary: str = ""
    summary_for_chat: str = ""
    preview_payload: dict[str, Any] = Field(default_factory=dict)
    actions: list[ArtifactAction] = Field(default_factory=list)
    refs: list[ArtifactRef] = Field(default_factory=list)
    primary_ref: ArtifactRef | None = None
    related_refs: list[ArtifactRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_internal_details(self) -> "ArtifactCard":
        if _contains_forbidden_visible_detail(self.preview_payload):
            raise ValueError("artifact_card contains forbidden internal details")
        if not self.summary_for_chat and self.summary:
            self.summary_for_chat = self.summary
        if self.primary_ref is None and self.refs:
            self.primary_ref = self.refs[0]
        if not self.refs:
            self.refs = [ref for ref in [self.primary_ref, *self.related_refs] if ref is not None]
        return self


class DatalogueEventEnvelope(BaseModel):
    """统一事件信封，Chat、AgentScope 和工作台复用同一外层事件面。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex}")
    event_type: str
    visibility: EventVisibility = EventVisibility.USER_VISIBLE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    task_id: str = Field(default_factory=lambda: f"task-{uuid.uuid4().hex}")
    conversation_id: int | None = None
    trace_id: str | None = None

    @model_validator(mode="after")
    def _reject_user_visible_internal_details(self) -> "DatalogueEventEnvelope":
        validate_event_visibility(self)
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
    envelope_payload: dict[str, Any] = {
        "event_type": event_type,
        "visibility": visibility,
        "payload": safe_payload if isinstance(safe_payload, dict) else {},
        "metadata": safe_metadata if isinstance(safe_metadata, dict) else {},
        "conversation_id": conversation_id,
        "trace_id": trace_id,
    }
    if task_id:
        envelope_payload["task_id"] = task_id
    return DatalogueEventEnvelope(**envelope_payload)


class AskBIRequest(BaseModel):
    """ask_bi 唯一入口请求；caller 用于审计外层来源，不改变 BI 主链授权边界。"""

    model_config = ConfigDict(extra="forbid")

    question: str
    conversation_id: int | None = None
    caller: str = "agentscope_shell"
    confirmed_dataset_id: int | None = None
    context_refs: list[str | ArtifactRef] = Field(default_factory=list)
    request_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("question")
    @classmethod
    def _question_required(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("question is required")
        return text


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
    status: Literal["completed", "waiting_user", "blocked", "error"]
    error: str | None = None

    @model_validator(mode="after")
    def _reject_internal_details(self) -> "AskBIResponse":
        safe_payload = self.model_dump(mode="json")
        if _contains_forbidden_visible_detail(safe_payload):
            raise ValueError("ask_bi response contains forbidden internal details")
        return self


def validate_event_visibility(event: DatalogueEventEnvelope) -> DatalogueEventEnvelope:
    """显式校验事件可见性，供测试和后续 chat 映射复用。"""

    visibility = event.visibility.value if isinstance(event.visibility, EventVisibility) else event.visibility
    if visibility == "user_visible" and _contains_forbidden_visible_detail(event.payload):
        raise ValueError("user_visible event contains forbidden internal details")
    return event
