# ============================================================
# File Name   : bi_workbench.py
# Description:
#   BI 工作台外层能力契约。
#
# Responsibilities:
#   - 定义 ask_bi、ArtifactCard 和统一事件 envelope 的最小稳定出参。
#   - 约束 user-visible payload 的字段边界，避免 SQL、schema 和 control_plane 泄漏。
#   - 为 AgentScope Shell Adapter 第一阶段验证提供只读协议对象。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EventVisibility(str, Enum):
    """统一事件可见性；AgentScope Shell 只消费 user_visible 和 trace_only 的安全映射。"""

    USER_VISIBLE = "user_visible"
    TRACE_ONLY = "trace_only"
    CONTROL_PLANE = "control_plane"


class ArtifactRef(BaseModel):
    """外层可引用的产物句柄，不承载产物正文。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str
    kind: str = "artifact"
    title: str | None = None


class ArtifactAction(BaseModel):
    """ArtifactCard 可展示动作；第一阶段允许禁用动作表达后续能力边界。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_type: str
    label: str
    enabled: bool = False
    disabled_reason: str | None = None
    payload_ref: str | None = None


class ArtifactCard(BaseModel):
    """面向 Chat / Shell 的轻量产物卡，只放摘要和引用。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_type: str = "bi_answer"
    title: str
    status: Literal["ready", "pending", "blocked", "error"] = "ready"
    summary_for_chat: str = ""
    primary_ref: ArtifactRef | None = None
    related_refs: list[ArtifactRef] = Field(default_factory=list)
    preview_payload: dict[str, Any] = Field(default_factory=dict)
    actions: list[ArtifactAction] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_preview_visibility(self) -> "ArtifactCard":
        _assert_no_public_sensitive_keys(self.preview_payload, path="artifact.preview_payload")
        return self


class DatalogueEventEnvelope(BaseModel):
    """Datalogue 业务事件 envelope；不替代现有 SSE，只提供统一协议壳。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    event_type: str
    task_id: str
    conversation_id: int | None = None
    visibility: EventVisibility = EventVisibility.USER_VISIBLE
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _validate_visibility_boundary(self) -> "DatalogueEventEnvelope":
        validate_event_visibility(self)
        return self


class AskBIRequest(BaseModel):
    """ask_bi 的最小入参；第一阶段作为 Shell Adapter 内部调用契约。"""

    model_config = ConfigDict(extra="forbid")

    question: str
    conversation_id: int | None = None
    caller: str = "agentscope_shell"
    confirmed_dataset_id: int | None = None
    context_refs: list[str] = Field(default_factory=list)
    request_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("question")
    @classmethod
    def _question_required(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("question is required")
        return text


class AskBIResponse(BaseModel):
    """ask_bi 对外稳定响应；控制面状态必须留在 Datalogue 内部。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    event_envelope: DatalogueEventEnvelope
    candidate_datasets: list[dict[str, Any]] = Field(default_factory=list)
    answer: str | None = None
    artifact_card: ArtifactCard | None = None
    primary_ref: ArtifactRef | None = None
    related_refs: list[ArtifactRef] = Field(default_factory=list)
    status: Literal["completed", "waiting_user", "blocked", "error"] = "completed"
    error: str | None = None

    @model_validator(mode="after")
    def _validate_outer_contract(self) -> "AskBIResponse":
        # 外层响应是 AgentScope 可见能力面，必须再次校验所有摘要 payload 的安全边界。
        for item in self.candidate_datasets:
            _assert_no_public_sensitive_keys(item, path="candidate_datasets")
        return self


PUBLIC_SENSITIVE_KEYS = {
    "control_plane",
    "capsule",
    "database",
    "raw_result",
    "raw_results",
    "raw_sql",
    "schema",
    "sql",
}


def validate_event_visibility(event: DatalogueEventEnvelope) -> DatalogueEventEnvelope:
    """校验事件可见性边界；仅 user_visible payload 需要强制公开面脱敏。"""

    if event.visibility == EventVisibility.USER_VISIBLE:
        _assert_no_public_sensitive_keys(event.payload, path="payload")
    return event


def sanitize_outer_payload(value: Any) -> Any:
    """递归移除外层响应禁用字段，用于接入旧 payload 时的保守兜底。"""

    if isinstance(value, dict):
        return {
            key: sanitize_outer_payload(item)
            for key, item in value.items()
            if str(key).lower() not in PUBLIC_SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [sanitize_outer_payload(item) for item in value]
    return value


def _assert_no_public_sensitive_keys(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in PUBLIC_SENSITIVE_KEYS:
                raise ValueError(f"{path}.{key_text} is not allowed in user-visible payload")
            _assert_no_public_sensitive_keys(item, path=f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_public_sensitive_keys(item, path=f"{path}[{index}]")
