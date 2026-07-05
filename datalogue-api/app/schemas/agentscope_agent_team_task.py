# ============================================================
# File Name   : agentscope_agent_team_task.py
# Description:
#   AgentScope Agent Team 任务入口 API 契约。
#
# Responsibilities:
#   - 定义 Agent Team task 请求和 SSE envelope 输出。
#   - 复用既有安全校验，阻断 SQL/schema/raw rows/DSL/repair patch 等内部执行态。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.bi_workbench import DatalogueEventEnvelope
from app.safety import contains_internal_task_payload

AgentTeamTaskSource = Literal["chat", "workbench", "api"]
AgentTeamTaskType = Literal["bi_query", "report", "python_analysis", "audit", "unsupported"]


class AgentTeamTaskRequest(BaseModel):
    """Chat/Workbench/API 进入 AgentScope Agent Team 主链的统一 task 请求。"""

    model_config = ConfigDict(extra="forbid")

    task_source: AgentTeamTaskSource
    task_type: AgentTeamTaskType = "bi_query"
    question: str
    dataset_id: int | None = None
    conversation_id: int | None = None
    session_id: str | None = None
    thread_id: str | None = None
    model_credential_id: str | None = Field(default=None, min_length=1, max_length=200)
    model_name: str | None = Field(default=None, min_length=1, max_length=200)
    model_parameters: dict[str, Any] = Field(default_factory=dict)
    model_config_id: int | None = Field(default=None, gt=0)
    clarification_response: dict[str, Any] | None = None
    retry_checkpoint_ref: str | None = None
    artifact_ref: str | None = None
    user_confirmation: dict[str, Any] | None = None
    client_context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_internal_payload(self) -> "AgentTeamTaskRequest":
        if contains_internal_task_payload(self.model_dump()):
            raise ValueError("AGENT_TEAM_TASK_INTERNAL_PAYLOAD_REJECTED")
        if bool(self.model_credential_id) != bool(self.model_name):
            # AgentScope session 创建必须同时拿到 credential 和 model；半截配置会导致 service 端用错默认模型。
            raise ValueError("AGENTSCOPE_MODEL_SELECTION_REQUIRES_CREDENTIAL_AND_MODEL")
        return self


class AgentTeamTaskStreamEvent(BaseModel):
    """SSE data JSON 的外层结构；event_envelope 是稳定事件协议。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    event_envelope: DatalogueEventEnvelope
    legacy_payload: dict[str, Any] = Field(default_factory=dict)
