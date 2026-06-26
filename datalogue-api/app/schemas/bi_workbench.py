# ============================================================
# File Name   : bi_workbench.py
# Description:
#   BI 工作台外层工具契约 Schema。
#
# Responsibilities:
#   - 定义 ask_bi 请求、响应、事件信封和产物引用结构。
#   - 约束用户可见协议，避免 SQL、schema、capsule 和 control_plane 泄露。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# 用户可见协议禁止承载内部执行面；字段名和字符串值都要扫描，避免 adapter 误把主链
# final_state 原样塞进 event payload / ArtifactCard。
FORBIDDEN_VISIBLE_KEYS = {
    "capsule",
    "control_plane",
    "dsl",
    "out_capsule",
    "raw_result",
    "raw_sql",
    "schema",
    "schema_context",
    "sql",
    "sql_list",
    "sql_result",
    "subagent_control_plane",
}


def _contains_forbidden_visible_detail(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in FORBIDDEN_VISIBLE_KEYS or any(
                token in key_text for token in ("raw_sql", "raw_result", "control_plane", "capsule")
            ):
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
        )
    return False


class ArtifactRef(BaseModel):
    """外层 Agent 只能拿引用句柄，不能拿 artifact body 或执行结果明细。"""

    model_config = ConfigDict(extra="forbid")

    ref_id: str
    ref_type: Literal["result", "report", "artifact", "checkpoint", "unknown"] = "artifact"
    label: str | None = None


class ArtifactAction(BaseModel):
    """ArtifactCard 上的动作声明；第一阶段只表达可用性，不直接执行副作用。"""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    label: str
    enabled: bool = True
    disabled_reason: str | None = None


class ArtifactCard(BaseModel):
    """用户可见的轻量产物卡，只展示摘要、动作和引用。"""

    model_config = ConfigDict(extra="forbid")

    artifact_type: str = "bi_answer"
    title: str = "BI 查询结果"
    summary: str = ""
    preview_payload: dict[str, Any] = Field(default_factory=dict)
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
    event_type: str
    task_id: str
    conversation_id: int | None = None
    visibility: Literal["user_visible", "trace_only", "control_plane"] = "user_visible"
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _reject_user_visible_internal_details(self) -> "DatalogueEventEnvelope":
        if self.visibility == "user_visible" and _contains_forbidden_visible_detail(self.payload):
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


def validate_event_visibility(event: DatalogueEventEnvelope) -> DatalogueEventEnvelope:
    """显式校验事件可见性，供 P0.5/P0.6 测试和后续 chat 映射复用。"""

    return event.model_validate(event.model_dump())
