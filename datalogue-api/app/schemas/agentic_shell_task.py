# ============================================================
# File Name   : agentic_shell_task.py
# Description:
#   Agentic Shell 统一任务入口 API 契约。
#
# Responsibilities:
#   - 定义统一 task 请求、task 状态响应和 SSE envelope 输出。
#   - 在 API 边界阻断 SQL/schema/raw rows/DSL/repair patch 等内部执行态。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.bi_workbench import DatalogueEventEnvelope

AgenticShellTaskSource = Literal["chat", "workbench", "api"]
AgenticShellTaskType = Literal["bi_query", "report", "python_analysis", "audit", "unsupported"]
AgenticShellTaskStatus = Literal["created", "running", "completed", "failed", "cancelled"]

_FORBIDDEN_TASK_KEYS = {
    "capsule",
    "control_plane",
    "data",
    "direct_sql",
    "dsl",
    "patch",
    "patch_body",
    "query_plan",
    "raw",
    "raw_result",
    "records",
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
_FORBIDDEN_TASK_KEY_FRAGMENTS = (
    "sql",
    "schema",
    "raw",
    "rows",
    "record",
    "queryplan",
    "repairpatch",
    "patchbody",
    "blueprintbody",
)
_SQL_TEXT_RE = re.compile(
    r"(?is)\b(select|insert|update|delete|drop|alter|create|with)\b"
    r".{0,200}\b(from|into|set|table|join|where|values)\b"
)


def _normalize_key(key: str) -> str:
    return "".join(char for char in str(key).lower() if char.isalnum())


def _is_forbidden_task_key(key: str) -> bool:
    normalized = _normalize_key(key)
    exact = {_normalize_key(item) for item in _FORBIDDEN_TASK_KEYS}
    return normalized in exact or any(fragment in normalized for fragment in _FORBIDDEN_TASK_KEY_FRAGMENTS)


def _contains_internal_payload(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if _is_forbidden_task_key(str(key)):
                return True
            if _contains_internal_payload(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_internal_payload(item) for item in value)
    if isinstance(value, str):
        return _SQL_TEXT_RE.search(value) is not None
    return False


class AgenticShellTaskRequest(BaseModel):
    """所有 Chat/Workbench/API 执行入口统一提交的 task 请求。"""

    model_config = ConfigDict(extra="forbid")

    task_source: AgenticShellTaskSource
    task_type: AgenticShellTaskType = "bi_query"
    question: str
    dataset_id: int | None = None
    conversation_id: int | None = None
    session_id: str | None = None
    thread_id: str | None = None
    model_config_id: int | None = Field(default=None, gt=0)
    clarification_response: dict[str, Any] | None = None
    retry_checkpoint_ref: str | None = None
    artifact_ref: str | None = None
    user_confirmation: dict[str, Any] | None = None
    client_context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_internal_payload(self) -> "AgenticShellTaskRequest":
        if _contains_internal_payload(self.model_dump()):
            raise ValueError("AGENTIC_SHELL_TASK_INTERNAL_PAYLOAD_REJECTED")
        return self


class AgenticShellTaskOut(BaseModel):
    """面向 API/Workbench 的 task 状态摘要。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    task_source: AgenticShellTaskSource
    task_type: AgenticShellTaskType
    status: AgenticShellTaskStatus
    selected_agent: str
    thread_id: str | None = None
    message_id: str | None = None
    trace_id: str | None = None
    artifact_refs: list[str] = Field(default_factory=list)
    checkpoint_refs: list[str] = Field(default_factory=list)


class AgenticShellTaskStreamEvent(BaseModel):
    """SSE data JSON 的外层结构；event_envelope 是稳定事件协议。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    event_envelope: DatalogueEventEnvelope
    legacy_payload: dict[str, Any] = Field(default_factory=dict)
