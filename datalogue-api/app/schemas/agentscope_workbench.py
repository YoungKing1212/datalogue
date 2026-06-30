# ============================================================
# File Name   : agentscope_workbench.py
# Description:
#   AgentScope 工作台会话镜像的 Pydantic 契约。
#
# Responsibilities:
#   - 定义 C3 新会话与历史会话的线程归属类型。
#   - 定义 AgentScope mirror 消息状态和线程解析结果。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentScopeThreadKind(str, Enum):
    AGENTSCOPE = "agentscope"
    LEGACY_CONVERSATION = "legacy_conversation"


class AgentScopeMessageStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ThreadRef(BaseModel):
    thread_id: str
    kind: AgentScopeThreadKind
    legacy_conversation_id: Optional[int] = None
    read_only: bool = False

    model_config = ConfigDict(use_enum_values=True)


class WorkbenchTimelineItem(BaseModel):
    """工作台时间线条目；只承载业务级阶段摘要和引用，不承载执行面明细。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    message_id: str | None = None
    task_id: str | None = None
    trace_id: str | None = None
    summary: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class WorkbenchMessageView(BaseModel):
    """工作台消息视图；用于 Chat 详情面板读取 AgentScope/旧会话统一摘要。"""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    role: str
    status: str
    content_summary: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    completed_at: datetime | None = None


class WorkbenchArtifactView(BaseModel):
    """工作台 artifact 摘要；只返回脱敏 preview，不返回 content_json/content_text 原文。"""

    model_config = ConfigDict(extra="forbid")

    artifact_ref: str
    kind: str
    dataset_id: int | None = None
    conversation_id: int | None = None
    message_id: int | None = None
    trace_id: str | None = None
    content_mime: str | None = None
    preview_payload: dict[str, Any] = Field(default_factory=dict)
    related_refs: list[dict[str, Any]] = Field(default_factory=list)
    expires_at: datetime | None = None


class WorkbenchActionView(BaseModel):
    """工作台动作声明；PR3 只读，真实 retry 在后续 PR 受控接入。"""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    label: str
    enabled: bool = False
    disabled_reason: str | None = None
    checkpoint_ref: str | None = None
    message_id: str | None = None


class WorkbenchThreadView(BaseModel):
    """工作台线程 View Model，供 Chat 详情面板和后续独立 Workbench 页面复用。"""

    model_config = ConfigDict(extra="forbid")

    thread_id: str
    read_only: bool
    messages: list[WorkbenchMessageView] = Field(default_factory=list)
    timeline: list[WorkbenchTimelineItem] = Field(default_factory=list)
    primary_artifact_ref: str | None = None
    related_refs: list[dict[str, Any]] = Field(default_factory=list)
    available_actions: list[WorkbenchActionView] = Field(default_factory=list)
    legacy_notice: str | None = None
