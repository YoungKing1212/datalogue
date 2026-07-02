# Agentic Shell Unified Task Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/api/chat/stream` with `/api/agentic-shell/tasks/stream` as the only execution entry for Chat UI and Workbench actions.

**Architecture:** Add a Datalogue-owned `AgenticShellTask` truth source, run AgentScope-native message/event flow inside `AgenticShellTaskRuntime`, and project every runtime event to stable `DatalogueEventEnvelope` SSE events. Chat UI and Workbench consume the same task stream from different views; `/api/chat/stream` is removed from execution.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, AgentScope 2.0.3, Server-Sent Events, React/Vite/Vitest, pytest.

---

## File Structure

Backend files to create:

- `datalogue-api/app/models/agentic_shell_task.py` - SQLAlchemy model for the Datalogue task truth source.
- `datalogue-api/alembic/versions/u1v2w3x4y5z6_add_agentic_shell_task.py` - migration for `agentic_shell_task`.
- `datalogue-api/app/schemas/agentic_shell_task.py` - request, response, task status, and SSE envelope DTOs.
- `datalogue-api/app/services/agentic_shell_event_projection.py` - AgentScope event to Datalogue envelope projection.
- `datalogue-api/app/services/agentic_shell_task_runtime.py` - task lifecycle runtime and runner protocol.
- `datalogue-api/app/api/agentic_shell.py` - `/api/agentic-shell/tasks/stream` route.
- `datalogue-api/tests/test_agentic_shell_task_contracts.py`
- `datalogue-api/tests/test_agentic_shell_event_projection.py`
- `datalogue-api/tests/test_agentic_shell_task_runtime.py`
- `datalogue-api/tests/test_agentic_shell_task_api.py`
- `datalogue-api/tests/test_agentic_shell_chat_stream_removed.py`
- `datalogue-api/tests/test_workbench_agentic_task_actions.py`

Backend files to modify:

- `datalogue-api/app/models/__init__.py` - export `AgenticShellTask`.
- `datalogue-api/app/schemas/__init__.py` - export Agentic Shell task schemas.
- `datalogue-api/app/schemas/bi_workbench.py` - extend `DatalogueEventType` with task/agent/tool/message/ref events and envelope fields.
- `datalogue-api/app/api/__init__.py` - include `agentic_shell.router`.
- `datalogue-api/app/api/chat.py` - remove `/stream` execution route.
- `datalogue-api/app/services/workbench_actions.py` - return task request semantics for retry.
- `datalogue-api/app/schemas/agentscope_workbench.py` - replace retry run request schema with task request fields.

Frontend files to create:

- `datalogue-web/src/assistant/agentic-shell-task-api.js` - task stream client and SSE parser.
- `datalogue-web/src/assistant/agentic-shell-task-api.test.js`
- `datalogue-web/src/assistant/agentic-shell-event-adapter.js` - converts task envelopes to chat adapter events.
- `datalogue-web/src/assistant/agentic-shell-event-adapter.test.js`

Frontend files to modify:

- `datalogue-web/src/api/client.js` - remove `/api/chat/stream` fetch helpers or make them throw local migration errors.
- `datalogue-web/src/assistant/chat-adapter.js` - consume `streamAgenticShellTask`.
- `datalogue-web/src/components/chat-page.jsx` - pass task retry request through the new stream path.
- `datalogue-web/src/components/workbench-panel.jsx` - call task retry flow directly instead of `onRetryRun` old chat runner.
- Existing frontend tests that assert `/api/chat/stream` need to assert `/api/agentic-shell/tasks/stream`.

Docs to modify after implementation:

- `docs/上下文入口.md`
- `.codex/project-memory.md`
- `docs/test-reports/2026-07-02-agentic-shell-unified-task-entry.md`

---

### Task 1: Backend Contracts, Model, and Migration

**Files:**
- Create: `datalogue-api/tests/test_agentic_shell_task_contracts.py`
- Create: `datalogue-api/app/models/agentic_shell_task.py`
- Create: `datalogue-api/alembic/versions/u1v2w3x4y5z6_add_agentic_shell_task.py`
- Create: `datalogue-api/app/schemas/agentic_shell_task.py`
- Modify: `datalogue-api/app/models/__init__.py`
- Modify: `datalogue-api/app/schemas/__init__.py`
- Modify: `datalogue-api/app/schemas/bi_workbench.py`

- [ ] **Step 1: Write failing contract tests**

Create `datalogue-api/tests/test_agentic_shell_task_contracts.py`:

```python
# ============================================================
# File Name   : test_agentic_shell_task_contracts.py
# Description:
#   Agentic Shell 统一任务入口的模型与 DTO 契约测试。
#
# Responsibilities:
#   - 验证 task request 拒绝 SQL/schema/raw rows 等内部执行态。
#   - 验证 Datalogue event envelope 支持 task/agent/tool/message/ref 事件族。
#   - 验证 AgenticShellTask 模型字段能保存 task 真相源。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

import pytest

from app.models.agentic_shell_task import AgenticShellTask
from app.schemas.agentic_shell_task import AgenticShellTaskRequest
from app.schemas.bi_workbench import build_datalogue_event_envelope


def test_agentic_shell_task_request_rejects_internal_payload_keys():
    with pytest.raises(ValueError, match="AGENTIC_SHELL_TASK_INTERNAL_PAYLOAD_REJECTED"):
        AgenticShellTaskRequest(
            task_source="chat",
            task_type="bi_query",
            question="统计合同总金额",
            dataset_id=12,
            client_context={"schema_context": {"tables": ["hidden_table"]}},
        )


def test_agentic_shell_task_request_allows_workbench_retry_refs():
    request = AgenticShellTaskRequest(
        task_source="workbench",
        task_type="bi_query",
        question="重试上一步",
        dataset_id=12,
        thread_id="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        retry_checkpoint_ref="checkpoint://as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/msg-1/query_context_ready",
        artifact_ref="artifact:abc123",
        client_context={"action": "retry_last_step"},
    )

    assert request.task_source == "workbench"
    assert request.retry_checkpoint_ref.startswith("checkpoint://")
    assert request.client_context == {"action": "retry_last_step"}


def test_datalogue_event_envelope_supports_agentic_shell_event_types():
    for event_type in (
        "task.started",
        "task.completed",
        "task.failed",
        "agent.selected",
        "agent.handoff.failed",
        "message.delta",
        "tool.external_required",
        "tool.result",
        "tool.blocked",
        "checkpoint.created",
        "artifact.ready",
        "trace.updated",
    ):
        envelope = build_datalogue_event_envelope(
            event_type=event_type,
            visibility="user_visible",
            payload={"summary": "安全摘要"},
            task_id="task_agentic_1",
            trace_id="trace_agentic_1",
        )
        assert envelope.event_type == event_type
        assert envelope.task_id == "task_agentic_1"


def test_agentic_shell_task_model_persists_truth_source(db_session):
    task = AgenticShellTask(
        task_id="task_agentic_contract",
        task_source="chat",
        task_type="bi_query",
        status="running",
        selected_agent="bi_lead_agent",
        agent_scope_session_id="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        thread_id="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        message_id="msg-agentic-1",
        trace_id="trace-agentic-1",
        artifact_refs_json=["artifact:abc"],
        checkpoint_refs_json=["checkpoint://abc"],
        request_payload_json={"question": "统计合同总金额"},
    )
    db_session.add(task)
    db_session.commit()

    stored = db_session.query(AgenticShellTask).filter_by(task_id="task_agentic_contract").one()
    assert stored.status == "running"
    assert stored.artifact_refs_json == ["artifact:abc"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_agentic_shell_task_contracts.py -q
```

Expected: FAIL because `app.models.agentic_shell_task` and `app.schemas.agentic_shell_task` do not exist, and `DatalogueEventType` does not include new task events.

- [ ] **Step 3: Add the task model**

Create `datalogue-api/app/models/agentic_shell_task.py`:

```python
# ============================================================
# File Name   : agentic_shell_task.py
# Description:
#   Agentic Shell 统一任务入口的服务端任务真相源模型。
#
# Responsibilities:
#   - 保存一次 AgenticShellTask 的生命周期、AgentScope session/message 关联和安全 refs。
#   - 为 Chat UI、Workbench、trace 和 artifact 审计提供 task_id 聚合主键。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.sql import func

from app.models.base import Base


class AgenticShellTask(Base):
    """Datalogue 对外 task 真相源；不等同于 AgentScope SDK Message。"""

    __tablename__ = "agentic_shell_task"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(80), unique=True, nullable=False, index=True)
    task_source = Column(String(40), nullable=False, index=True)
    task_type = Column(String(40), nullable=False, index=True)
    status = Column(String(40), nullable=False, default="created", index=True)
    selected_agent = Column(String(80), nullable=False, default="bi_lead_agent", index=True)
    parent_task_id = Column(String(80), nullable=True, index=True)
    agent_scope_session_id = Column(String(120), nullable=True, index=True)
    thread_id = Column(String(120), nullable=True, index=True)
    message_id = Column(String(120), nullable=True, index=True)
    trace_id = Column(String(120), nullable=True, index=True)
    artifact_refs_json = Column(SQLiteJSON, nullable=False, default=list)
    checkpoint_refs_json = Column(SQLiteJSON, nullable=False, default=list)
    request_payload_json = Column(SQLiteJSON, nullable=False, default=dict)
    final_payload_json = Column(SQLiteJSON, nullable=False, default=dict)
    error_payload_json = Column(SQLiteJSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

Modify `datalogue-api/app/models/__init__.py`:

```python
from .agentic_shell_task import AgenticShellTask
```

Add `"AgenticShellTask"` to `__all__`.

- [ ] **Step 4: Add the Alembic migration**

Create `datalogue-api/alembic/versions/u1v2w3x4y5z6_add_agentic_shell_task.py`:

```python
"""add agentic shell task

Revision ID: u1v2w3x4y5z6
Revises: r2s3t4u5v6w7
Create Date: 2026-07-02 10:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "u1v2w3x4y5z6"
down_revision = "r2s3t4u5v6w7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agentic_shell_task",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=80), nullable=False),
        sa.Column("task_source", sa.String(length=40), nullable=False),
        sa.Column("task_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("selected_agent", sa.String(length=80), nullable=False),
        sa.Column("parent_task_id", sa.String(length=80), nullable=True),
        sa.Column("agent_scope_session_id", sa.String(length=120), nullable=True),
        sa.Column("thread_id", sa.String(length=120), nullable=True),
        sa.Column("message_id", sa.String(length=120), nullable=True),
        sa.Column("trace_id", sa.String(length=120), nullable=True),
        sa.Column("artifact_refs_json", sa.JSON(), nullable=False),
        sa.Column("checkpoint_refs_json", sa.JSON(), nullable=False),
        sa.Column("request_payload_json", sa.JSON(), nullable=False),
        sa.Column("final_payload_json", sa.JSON(), nullable=False),
        sa.Column("error_payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    for column in (
        "task_id",
        "task_source",
        "task_type",
        "status",
        "selected_agent",
        "parent_task_id",
        "agent_scope_session_id",
        "thread_id",
        "message_id",
        "trace_id",
    ):
        op.create_index(f"ix_agentic_shell_task_{column}", "agentic_shell_task", [column])


def downgrade() -> None:
    for column in (
        "trace_id",
        "message_id",
        "thread_id",
        "agent_scope_session_id",
        "parent_task_id",
        "selected_agent",
        "status",
        "task_type",
        "task_source",
        "task_id",
    ):
        op.drop_index(f"ix_agentic_shell_task_{column}", table_name="agentic_shell_task")
    op.drop_table("agentic_shell_task")
```

Current repo scan shows `r2s3t4u5v6w7_add_bi_lead_agent_handoff.py` as the latest migration file, so the plan uses `down_revision = "r2s3t4u5v6w7"`. At implementation time, run this once before creating the migration; only change `down_revision` if another migration has landed after this plan:

```bash
cd datalogue-api
python3 -m alembic heads
```

- [ ] **Step 5: Add task schemas**

Create `datalogue-api/app/schemas/agentic_shell_task.py`:

```python
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


AgenticShellTaskSource = Literal["chat", "workbench", "bi_lead_agent_panel", "api"]
AgenticShellTaskType = Literal["bi_query", "report", "python_analysis", "audit"]
AgenticShellTaskStatus = Literal["created", "running", "completed", "failed", "cancelled"]

_FORBIDDEN_TASK_KEYS = {
    "sql",
    "raw_sql",
    "schema",
    "schema_context",
    "dsl",
    "raw_rows",
    "result_rows",
    "repair_patch",
    "patch_body",
    "query_plan",
    "candidate_assets",
}
_SQL_TEXT_RE = re.compile(r"(?is)\\b(select|insert|update|delete|drop|alter|create|with)\\b.{0,200}\\b(from|join|where|table|set|into)\\b")


def _contains_internal_payload(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in _FORBIDDEN_TASK_KEYS or "sql" in key_text:
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
    """新 SSE 主协议；event_envelope 是前端和 Workbench 的稳定消费面。"""

    model_config = ConfigDict(extra="forbid")

    type: str = "agentic_shell_event"
    task_id: str
    event_envelope: DatalogueEventEnvelope
    legacy_payload: dict[str, Any] = Field(default_factory=dict)
```

Modify `datalogue-api/app/schemas/__init__.py`:

```python
from .agentic_shell_task import (
    AgenticShellTaskOut,
    AgenticShellTaskRequest,
    AgenticShellTaskSource,
    AgenticShellTaskStatus,
    AgenticShellTaskStreamEvent,
    AgenticShellTaskType,
)
```

Add the same names to `__all__`.

- [ ] **Step 6: Extend Datalogue event types and envelope fields**

Modify `datalogue-api/app/schemas/bi_workbench.py`.

Add the following event types to `DatalogueEventType` while keeping existing values:

```python
    "task.completed",
    "task.failed",
    "task.cancelled",
    "agent.selected",
    "agent.handoff.started",
    "agent.handoff.completed",
    "agent.handoff.failed",
    "message.delta",
    "message.completed",
    "tool.external_required",
    "tool.result",
    "tool.blocked",
    "checkpoint.created",
    "artifact.ready",
    "trace.updated",
```

Add fields to `DatalogueEventEnvelope`:

```python
    thread_id: str | None = None
    message_id: str | None = None
    selected_agent: str | None = None
    legacy_payload: dict[str, Any] = Field(default_factory=dict)
```

Extend `build_datalogue_event_envelope(...)` signature and constructor with:

```python
    thread_id: str | None = None,
    message_id: str | None = None,
    selected_agent: str | None = None,
    legacy_payload: dict[str, Any] | None = None,
```

and pass them to `DatalogueEventEnvelope`.

- [ ] **Step 7: Run contract tests**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_agentic_shell_task_contracts.py tests/test_event_envelope.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add datalogue-api/app/models/agentic_shell_task.py \
  datalogue-api/alembic/versions/u1v2w3x4y5z6_add_agentic_shell_task.py \
  datalogue-api/app/schemas/agentic_shell_task.py \
  datalogue-api/app/models/__init__.py \
  datalogue-api/app/schemas/__init__.py \
  datalogue-api/app/schemas/bi_workbench.py \
  datalogue-api/tests/test_agentic_shell_task_contracts.py
git commit -m "feat: add Agentic Shell task contracts"
```

---

### Task 2: AgentScope Event Projection

**Files:**
- Create: `datalogue-api/tests/test_agentic_shell_event_projection.py`
- Create: `datalogue-api/app/services/agentic_shell_event_projection.py`

- [ ] **Step 1: Write failing projection tests**

Create `datalogue-api/tests/test_agentic_shell_event_projection.py`:

```python
# ============================================================
# File Name   : test_agentic_shell_event_projection.py
# Description:
#   AgentScope 原生事件到 Datalogue envelope 的投影测试。
#
# Responsibilities:
#   - 验证 external tool required/result 事件映射到稳定 tool.* envelope。
#   - 验证文本增量和终态事件不泄露 AgentScope SDK 对象结构。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from agentscope.event import ExternalExecutionResultEvent, RequireExternalExecutionEvent
from agentscope.message import TextBlock, ToolCallBlock, ToolResultBlock, ToolResultState

from app.services.agentic_shell_event_projection import (
    build_task_envelope,
    project_agentscope_event,
)


def test_project_require_external_execution_event_to_tool_required():
    event = RequireExternalExecutionEvent(
        id="evt-require-1",
        tool_calls=[
            ToolCallBlock(id="call-1", name="get_dataset_status", input={"dataset_id": 12})
        ],
    )

    envelope = project_agentscope_event(
        event,
        task_id="task-1",
        trace_id="trace-1",
        thread_id="as_1",
        message_id="msg-1",
        selected_agent="bi_lead_agent",
    )

    assert envelope.event_type == "tool.external_required"
    assert envelope.payload["tool_calls"][0]["name"] == "get_dataset_status"
    assert "input" not in envelope.payload["tool_calls"][0]


def test_project_external_execution_result_event_to_tool_result():
    event = ExternalExecutionResultEvent(
        id="evt-result-1",
        execution_results=[
            ToolResultBlock(
                id="call-1",
                name="get_dataset_status",
                state=ToolResultState.SUCCESS,
                output=[TextBlock(text='{"status":"ready","summary":"可查询"}')],
            )
        ],
    )

    envelope = project_agentscope_event(
        event,
        task_id="task-1",
        trace_id="trace-1",
        thread_id="as_1",
        message_id="msg-1",
        selected_agent="bi_lead_agent",
    )

    assert envelope.event_type == "tool.result"
    assert envelope.payload["results"][0]["name"] == "get_dataset_status"
    assert envelope.payload["results"][0]["state"] == "success"


def test_build_task_envelope_rejects_visible_internal_payload():
    envelope = build_task_envelope(
        event_type="task.failed",
        task_id="task-1",
        trace_id="trace-1",
        payload={"error_summary": "select * from hidden_table"},
    )

    assert "select" not in str(envelope.payload).lower()


def test_project_legacy_sse_final_to_message_completed():
    envelope = project_agentscope_event(
        {"data": '{"type":"final","answer":"合同总金额为 100 万元","trace_id":"trace-legacy"}'},
        task_id="task-1",
        trace_id="trace-1",
        thread_id="as_1",
        message_id="msg-1",
        selected_agent="bi_lead_agent",
    )

    assert envelope.event_type == "message.completed"
    assert envelope.legacy_payload["answer"] == "合同总金额为 100 万元"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_agentic_shell_event_projection.py -q
```

Expected: FAIL because `agentic_shell_event_projection.py` does not exist.

- [ ] **Step 3: Implement projection service**

Create `datalogue-api/app/services/agentic_shell_event_projection.py`:

```python
# ============================================================
# File Name   : agentic_shell_event_projection.py
# Description:
#   AgentScope 原生事件到 Datalogue 稳定事件 envelope 的投影。
#
# Responsibilities:
#   - 将 AgentScope reply_stream 事件映射为 task/agent/tool/message/ref 事件族。
#   - 只暴露工具名、状态、摘要和 refs，不泄露工具 input、SQL、schema 或 raw rows。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import json
from typing import Any

from agentscope.event import ExternalExecutionResultEvent, RequireExternalExecutionEvent
from agentscope.message import ToolResultBlock

from app.schemas.bi_workbench import DatalogueEventEnvelope, DatalogueEventType, build_datalogue_event_envelope


def build_task_envelope(
    *,
    event_type: DatalogueEventType,
    task_id: str,
    trace_id: str | None = None,
    thread_id: str | None = None,
    message_id: str | None = None,
    selected_agent: str | None = None,
    payload: dict[str, Any] | None = None,
    legacy_payload: dict[str, Any] | None = None,
    visibility: str = "user_visible",
) -> DatalogueEventEnvelope:
    """构造 Agentic Shell task envelope；所有用户可见载荷继续走 bi_workbench 脱敏。"""

    return build_datalogue_event_envelope(
        event_type=event_type,
        visibility=visibility,
        payload=payload or {},
        task_id=task_id,
        trace_id=trace_id,
        thread_id=thread_id,
        message_id=message_id,
        selected_agent=selected_agent,
        legacy_payload=legacy_payload or {},
    )


def project_agentscope_event(
    event: Any,
    *,
    task_id: str,
    trace_id: str | None,
    thread_id: str | None,
    message_id: str | None,
    selected_agent: str | None,
) -> DatalogueEventEnvelope:
    """把 AgentScope event 投影成 Datalogue envelope；未知事件降级为 trace.updated。"""

    if isinstance(event, RequireExternalExecutionEvent):
        return build_task_envelope(
            event_type="tool.external_required",
            task_id=task_id,
            trace_id=trace_id,
            thread_id=thread_id,
            message_id=message_id,
            selected_agent=selected_agent,
            payload={
                "summary": "AgentScope 请求执行外部工具。",
                "tool_calls": [
                    {"id": call.id, "name": call.name}
                    for call in event.tool_calls
                ],
            },
        )

    if isinstance(event, ExternalExecutionResultEvent):
        return build_task_envelope(
            event_type="tool.result",
            task_id=task_id,
            trace_id=trace_id,
            thread_id=thread_id,
            message_id=message_id,
            selected_agent=selected_agent,
            payload={
                "summary": "外部工具结果已安全回填。",
                "results": [_safe_tool_result(block) for block in event.execution_results],
            },
        )

    if isinstance(event, dict):
        parsed = _parse_legacy_sse_payload(event)
        legacy_type = parsed.get("type")
        if legacy_type == "token":
            content = str(parsed.get("content") or parsed.get("token") or "")
            return build_task_envelope(
                event_type="message.delta",
                task_id=task_id,
                trace_id=trace_id,
                thread_id=thread_id,
                message_id=message_id,
                selected_agent=selected_agent,
                payload={"content": content},
                legacy_payload=parsed,
            )
        if legacy_type == "final":
            answer = str(parsed.get("answer") or parsed.get("summary") or "")
            return build_task_envelope(
                event_type="message.completed",
                task_id=task_id,
                trace_id=parsed.get("trace_id") or trace_id,
                thread_id=parsed.get("thread_id") or thread_id,
                message_id=message_id,
                selected_agent=selected_agent,
                payload={"summary": answer or "任务已完成。"},
                legacy_payload=parsed,
            )
        event_envelope = parsed.get("event_envelope") if isinstance(parsed, dict) else None
        event_type = event_envelope.get("event_type") if isinstance(event_envelope, dict) else parsed.get("event_type")
        if isinstance(event_type, str) and event_type.startswith("retry."):
            return build_task_envelope(
                event_type=event_type,
                task_id=task_id,
                trace_id=trace_id,
                thread_id=thread_id,
                message_id=message_id,
                selected_agent=selected_agent,
                payload=parsed,
                legacy_payload=parsed,
            )

    delta = getattr(event, "delta", None)
    if isinstance(delta, str) and delta:
        return build_task_envelope(
            event_type="message.delta",
            task_id=task_id,
            trace_id=trace_id,
            thread_id=thread_id,
            message_id=message_id,
            selected_agent=selected_agent,
            payload={"content": delta},
            legacy_payload={"type": "token", "content": delta},
        )

    return build_task_envelope(
        event_type="trace.updated",
        task_id=task_id,
        trace_id=trace_id,
        thread_id=thread_id,
        message_id=message_id,
        selected_agent=selected_agent,
        payload={"summary": event.__class__.__name__},
        visibility="trace_only",
    )


def _parse_legacy_sse_payload(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data") if isinstance(event, dict) else None
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, dict) else {"summary": str(parsed)}
        except json.JSONDecodeError:
            return {"summary": data[:300]}
    return event


def _safe_tool_result(block: ToolResultBlock) -> dict[str, Any]:
    state = getattr(block.state, "value", str(block.state)).lower()
    output_summary = "工具执行完成。"
    for item in block.output or []:
        text = getattr(item, "text", None)
        if isinstance(text, str) and text.strip():
            output_summary = text.strip()[:300]
            break
    return {
        "id": block.id,
        "name": block.name,
        "state": state,
        "summary": output_summary,
    }
```

- [ ] **Step 4: Run projection tests**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_agentic_shell_event_projection.py tests/test_event_envelope.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/services/agentic_shell_event_projection.py \
  datalogue-api/tests/test_agentic_shell_event_projection.py
git commit -m "feat: project AgentScope events to Agentic Shell envelopes"
```

---

### Task 3: Agentic Shell Task Runtime Spine

**Files:**
- Create: `datalogue-api/tests/test_agentic_shell_task_runtime.py`
- Create: `datalogue-api/app/services/agentic_shell_task_runtime.py`

- [ ] **Step 1: Write failing runtime tests**

Create `datalogue-api/tests/test_agentic_shell_task_runtime.py`:

```python
# ============================================================
# File Name   : test_agentic_shell_task_runtime.py
# Description:
#   Agentic Shell Task Runtime 生命周期测试。
#
# Responsibilities:
#   - 验证 runtime 创建 task、AgentScope mirror message，并输出 task/message 完成事件。
#   - 验证 runtime 异常时写入 task.failed，且不泄露内部执行态。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

import pytest

from app.models.agentic_shell_task import AgenticShellTask
from app.schemas.agentic_shell_task import AgenticShellTaskRequest
from app.services.agentic_shell_task_runtime import AgenticShellTaskRuntime


class FakeAgentScopeRunner:
    async def stream(self, *, request, task, user_msg):
        yield type("DeltaEvent", (), {"delta": "合同总金额为 100 万元"})()


class FailingAgentScopeRunner:
    async def stream(self, *, request, task, user_msg):
        raise RuntimeError("select * from hidden_table")


@pytest.mark.asyncio
async def test_agentic_shell_task_runtime_completes_task(db_session):
    runtime = AgenticShellTaskRuntime(db=db_session, runner=FakeAgentScopeRunner())
    request = AgenticShellTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="统计合同总金额",
        dataset_id=12,
        session_id="assistant-thread-1",
    )

    events = [event async for event in runtime.stream(request)]

    assert [event.event_type for event in events] == [
        "task.started",
        "agent.selected",
        "message.delta",
        "message.completed",
        "task.completed",
    ]
    stored = db_session.query(AgenticShellTask).filter_by(task_id=events[0].task_id).one()
    assert stored.status == "completed"
    assert stored.selected_agent == "bi_lead_agent"


@pytest.mark.asyncio
async def test_agentic_shell_task_runtime_fails_closed(db_session):
    runtime = AgenticShellTaskRuntime(db=db_session, runner=FailingAgentScopeRunner())
    request = AgenticShellTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="统计合同总金额",
        dataset_id=12,
    )

    events = [event async for event in runtime.stream(request)]

    assert events[-1].event_type == "task.failed"
    assert "select" not in str(events[-1].payload).lower()
    stored = db_session.query(AgenticShellTask).filter_by(task_id=events[0].task_id).one()
    assert stored.status == "failed"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_agentic_shell_task_runtime.py -q
```

Expected: FAIL because `agentic_shell_task_runtime.py` does not exist.

- [ ] **Step 3: Implement runtime spine**

Create `datalogue-api/app/services/agentic_shell_task_runtime.py`:

```python
# ============================================================
# File Name   : agentic_shell_task_runtime.py
# Description:
#   Agentic Shell 统一任务入口运行时。
#
# Responsibilities:
#   - 创建 AgenticShellTask 真相源、AgentScope mirror session/message 和 task 生命周期事件。
#   - 驱动 AgentScope runner，并将原生事件投影为 Datalogue envelope。
#   - 在异常路径写入安全失败状态，禁止回退到 /api/chat/stream。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any, Callable, Protocol

from agentscope.message import UserMsg
from sqlalchemy.orm import Session

from app.models.agentic_shell_task import AgenticShellTask
from app import schemas
from app.schemas.agentic_shell_task import AgenticShellTaskRequest
from app.schemas.bi_workbench import DatalogueEventEnvelope
from app.services.agentic_shell import DatalogueAgenticShell
from app.services.agentic_shell_event_projection import build_task_envelope, project_agentscope_event
from app.services.agentscope_mirror import (
    append_user_message,
    create_agentscope_session,
    create_running_assistant_message,
    mark_message_completed,
    mark_message_failed,
)
from app.services.agentscope_thread_resolver import new_agentscope_thread_id


class AgentScopeTaskRunner(Protocol):
    async def stream(self, *, request: AgenticShellTaskRequest, task: AgenticShellTask, user_msg: UserMsg) -> AsyncIterator[Any]:
        ...


class LegacyWorkflowTaskRunner:
    """迁移期执行适配器：入口 ownership 归 Agentic Shell，真实 BI 执行体临时复用现有 service runtime。"""

    def __init__(self, *, legacy_stream_factory: Callable[[schemas.ChatRequest], AsyncIterator[dict[str, Any]]]) -> None:
        self.legacy_stream_factory = legacy_stream_factory

    async def stream(self, *, request: AgenticShellTaskRequest, task: AgenticShellTask, user_msg: UserMsg) -> AsyncIterator[Any]:
        chat_payload = schemas.ChatRequest(
            question=request.question,
            thread_id=request.thread_id,
            session_id=request.session_id,
            conversation_id=request.conversation_id,
            dataset_id=request.dataset_id,
            clarification_response=request.clarification_response,
            retry_checkpoint_ref=request.retry_checkpoint_ref,
        )
        async for legacy_event in self.legacy_stream_factory(chat_payload):
            yield legacy_event


class AgenticShellTaskRuntime:
    """统一任务入口 runtime；调用方只消费 Datalogue envelope。"""

    def __init__(self, *, db: Session, runner: AgentScopeTaskRunner) -> None:
        self.db = db
        self.runner = runner

    async def stream(self, request: AgenticShellTaskRequest) -> AsyncIterator[DatalogueEventEnvelope]:
        shell = DatalogueAgenticShell()
        contract = shell.prepare_turn(question=request.question, context=request.model_dump())
        selected_agent = contract.selected_agent
        thread_id = request.thread_id or new_agentscope_thread_id()
        trace_id = f"trace-agentic-{uuid.uuid4().hex}"
        task = self._create_task(request, selected_agent=selected_agent, thread_id=thread_id, trace_id=trace_id)
        session = create_agentscope_session(
            self.db,
            thread_id=thread_id,
            title=request.question[:80],
            legacy_conversation_id=request.conversation_id,
            metadata={"task_id": task.task_id, "task_source": request.task_source},
        )
        user_message = append_user_message(
            self.db,
            thread_id=session.thread_id,
            content_summary=request.question,
            payload={"task_id": task.task_id, "question": request.question, "dataset_id": request.dataset_id},
        )
        assistant_message = create_running_assistant_message(self.db, thread_id=session.thread_id, lease_seconds=300)
        task.agent_scope_session_id = session.thread_id
        task.thread_id = session.thread_id
        task.message_id = assistant_message.message_id
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        yield build_task_envelope(
            event_type="task.started",
            task_id=task.task_id,
            trace_id=trace_id,
            thread_id=session.thread_id,
            message_id=assistant_message.message_id,
            selected_agent=selected_agent,
            payload={"summary": "Agentic Shell 任务已启动。"},
        )
        yield build_task_envelope(
            event_type="agent.selected",
            task_id=task.task_id,
            trace_id=trace_id,
            thread_id=session.thread_id,
            message_id=assistant_message.message_id,
            selected_agent=selected_agent,
            payload={"selected_agent": selected_agent, "task_type": request.task_type},
        )

        accumulated_text = ""
        message_completed_emitted = False
        try:
            user_msg = UserMsg(name="user", content=request.question)
            async for event in self.runner.stream(request=request, task=task, user_msg=user_msg):
                envelope = project_agentscope_event(
                    event,
                    task_id=task.task_id,
                    trace_id=trace_id,
                    thread_id=session.thread_id,
                    message_id=assistant_message.message_id,
                    selected_agent=selected_agent,
                )
                if envelope.event_type == "message.delta":
                    accumulated_text += str(envelope.payload.get("content") or "")
                if envelope.event_type == "message.completed":
                    message_completed_emitted = True
                    accumulated_text = str(envelope.payload.get("summary") or accumulated_text)
                yield envelope
            mark_message_completed(
                self.db,
                message_id=assistant_message.message_id,
                content_summary=accumulated_text or "Agentic Shell 任务已完成。",
                payload={"task_id": task.task_id, "answer": accumulated_text},
            )
            task.status = "completed"
            task.final_payload_json = {"answer": accumulated_text}
            self.db.add(task)
            self.db.commit()
            if not message_completed_emitted:
                yield build_task_envelope(
                    event_type="message.completed",
                    task_id=task.task_id,
                    trace_id=trace_id,
                    thread_id=session.thread_id,
                    message_id=assistant_message.message_id,
                    selected_agent=selected_agent,
                    payload={"summary": accumulated_text or "任务已完成。"},
                    legacy_payload={"type": "final", "answer": accumulated_text},
                )
            yield build_task_envelope(
                event_type="task.completed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                payload={"summary": "Agentic Shell 任务已完成。"},
            )
        except Exception:
            mark_message_failed(
                self.db,
                message_id=assistant_message.message_id,
                error_summary="Agentic Shell 任务执行失败，内部细节已隐藏。",
                payload={"task_id": task.task_id, "error_code": "AGENTIC_SHELL_TASK_FAILED"},
            )
            task.status = "failed"
            task.error_payload_json = {"error_code": "AGENTIC_SHELL_TASK_FAILED"}
            self.db.add(task)
            self.db.commit()
            yield build_task_envelope(
                event_type="task.failed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                payload={
                    "error_code": "AGENTIC_SHELL_TASK_FAILED",
                    "error_summary": "Agentic Shell 任务执行失败，内部细节已隐藏。",
                    "retryable": True,
                },
            )

    def _create_task(
        self,
        request: AgenticShellTaskRequest,
        *,
        selected_agent: str,
        thread_id: str,
        trace_id: str,
    ) -> AgenticShellTask:
        task = AgenticShellTask(
            task_id=f"task-agentic-{uuid.uuid4().hex}",
            task_source=request.task_source,
            task_type=request.task_type,
            status="running",
            selected_agent=selected_agent,
            thread_id=thread_id,
            trace_id=trace_id,
            artifact_refs_json=[request.artifact_ref] if request.artifact_ref else [],
            checkpoint_refs_json=[request.retry_checkpoint_ref] if request.retry_checkpoint_ref else [],
            request_payload_json=request.model_dump(),
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task
```

- [ ] **Step 4: Run runtime tests**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_agentic_shell_task_runtime.py tests/test_agentic_shell_event_projection.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/services/agentic_shell_task_runtime.py \
  datalogue-api/tests/test_agentic_shell_task_runtime.py
git commit -m "feat: add Agentic Shell task runtime spine"
```

---

### Task 4: New API Route and `/api/chat/stream` Removal

**Files:**
- Create: `datalogue-api/tests/test_agentic_shell_task_api.py`
- Create: `datalogue-api/tests/test_agentic_shell_chat_stream_removed.py`
- Create: `datalogue-api/app/api/agentic_shell.py`
- Modify: `datalogue-api/app/api/__init__.py`
- Modify: `datalogue-api/app/api/chat.py`
- Modify: `datalogue-api/app/services/bi_workbench_tool.py`

- [ ] **Step 1: Write failing API tests**

Create `datalogue-api/tests/test_agentic_shell_task_api.py`:

```python
# ============================================================
# File Name   : test_agentic_shell_task_api.py
# Description:
#   Agentic Shell task stream API 测试。
#
# Responsibilities:
#   - 验证 /api/agentic-shell/tasks/stream 返回 SSE envelope。
#   - 验证 API response 使用 task_id 而不是旧 /chat/stream final payload 作为主语。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

import json


class FakeApiRunner:
    async def stream(self, *, request, task, user_msg):
        yield type("DeltaEvent", (), {"delta": "合同总金额为 100 万元"})()


def _sse_payloads(response):
    payloads = []
    for line in response.text.splitlines():
        if line.startswith("data:"):
            payloads.append(json.loads(line.removeprefix("data:").strip()))
    return payloads


def test_agentic_shell_task_stream_returns_task_envelopes(client, monkeypatch):
    from app.api import agentic_shell

    monkeypatch.setattr(agentic_shell, "build_agentic_shell_task_runner", lambda db: FakeApiRunner())

    response = client.post(
        "/api/agentic-shell/tasks/stream",
        json={
            "task_source": "chat",
            "task_type": "bi_query",
            "question": "统计合同总金额",
            "dataset_id": 12,
        },
    )

    assert response.status_code == 200
    payloads = _sse_payloads(response)
    event_types = [payload["event_envelope"]["event_type"] for payload in payloads]
    assert "task.started" in event_types
    assert "agent.selected" in event_types
    assert "task.completed" in event_types
    assert payloads[0]["task_id"].startswith("task-agentic-")
```

Create `datalogue-api/tests/test_agentic_shell_chat_stream_removed.py`:

```python
# ============================================================
# File Name   : test_agentic_shell_chat_stream_removed.py
# Description:
#   /api/chat/stream 硬切删除测试。
#
# Responsibilities:
#   - 确认旧 chat stream 不再是执行入口。
#   - 防止后续改动重新把 /api/chat/stream 接回 runtime。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================


def test_chat_stream_route_is_removed(client):
    response = client.post("/api/chat/stream", json={"question": "统计合同总金额"})

    assert response.status_code in {404, 405}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_agentic_shell_task_api.py tests/test_agentic_shell_chat_stream_removed.py -q
```

Expected: FAIL because the new route does not exist and old `/api/chat/stream` still exists.

- [ ] **Step 3: Add new API route**

Create `datalogue-api/app/api/agentic_shell.py`:

```python
# ============================================================
# File Name   : agentic_shell.py
# Description:
#   Agentic Shell 统一任务入口 API。
#
# Responsibilities:
#   - 暴露 /tasks/stream SSE 主入口。
#   - 将 AgenticShellTaskRequest 交给 AgenticShellTaskRuntime。
#   - 保证 Chat UI 和 Workbench 不再从 /api/chat/stream 执行。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import get_settings
from app.api.chat import _chat_stream_runtime_hooks
from app.schemas.agentic_shell_task import AgenticShellTaskRequest, AgenticShellTaskStreamEvent
from app.services.agentic_chat_runtime import DatalogueChatStreamRuntime
from app.services.agentic_shell_task_runtime import AgenticShellTaskRuntime, LegacyWorkflowTaskRunner

router = APIRouter()


def _sse_data(payload: dict) -> dict:
    return {"data": json.dumps(payload, ensure_ascii=False)}


def build_agentic_shell_task_runner(db: Session) -> LegacyWorkflowTaskRunner:
    """生产默认 runner：新入口创建 task，BI 执行体通过 LegacyWorkflowAdapter 复用现有 service runtime。"""

    async def legacy_stream_factory(chat_payload):
        runtime = DatalogueChatStreamRuntime(
            db=db,
            settings=get_settings(),
            hooks=_chat_stream_runtime_hooks(),
        )
        async for event in runtime.stream(chat_payload):
            yield event

    return LegacyWorkflowTaskRunner(legacy_stream_factory=legacy_stream_factory)


@router.post("/tasks/stream")
def stream_agentic_shell_task(payload: AgenticShellTaskRequest, db: Session = Depends(get_db)):
    """唯一主执行入口；所有 Chat/Workbench 执行都从 AgenticShellTask 开始。"""

    async def event_generator():
        runtime = AgenticShellTaskRuntime(db=db, runner=build_agentic_shell_task_runner(db))
        async for envelope in runtime.stream(payload):
            event = AgenticShellTaskStreamEvent(
                task_id=envelope.task_id or "",
                event_envelope=envelope,
                legacy_payload=envelope.legacy_payload,
            )
            yield _sse_data(event.model_dump(mode="json"))

    return EventSourceResponse(event_generator())
```

Modify `datalogue-api/app/api/__init__.py`:

```python
from app.api import agentic_shell
router.include_router(agentic_shell.router, prefix="/agentic-shell", tags=["Agentic Shell"])
```

- [ ] **Step 4: Remove old chat stream route**

Modify `datalogue-api/app/api/chat.py`:

Remove this route entirely:

```python
@router.post("/stream")
def chat_stream(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    ...
```

Keep helper functions only if other tests still import them during this task. Do not leave any FastAPI route that accepts `/api/chat/stream`.

Modify `datalogue-api/app/services/bi_workbench_tool.py`.

Replace `_resolve_stream_chat` with:

```python
    def _resolve_stream_chat(self) -> ChatStreamCallable:
        if self._stream_chat is not None:
            return self._stream_chat
        raise RuntimeError("CHAT_STREAM_REMOVED_USE_AGENTIC_SHELL_TASKS")
```

This removes the dynamic `from app.api.chat import _stream_chat` fallback. Existing `BIWorkbenchTool` unit tests that still exercise `ask()` must inject a fake `stream_chat` callable; production task execution must use `/api/agentic-shell/tasks/stream`.

- [ ] **Step 5: Run API tests**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_agentic_shell_task_api.py tests/test_agentic_shell_chat_stream_removed.py tests/test_agentic_shell_task_runtime.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add datalogue-api/app/api/agentic_shell.py \
  datalogue-api/app/api/__init__.py \
  datalogue-api/app/api/chat.py \
  datalogue-api/app/services/bi_workbench_tool.py \
  datalogue-api/tests/test_agentic_shell_task_api.py \
  datalogue-api/tests/test_agentic_shell_chat_stream_removed.py
git commit -m "feat: add Agentic Shell task stream API"
```

---

### Task 5: Workbench Retry Produces Task Requests

**Files:**
- Create: `datalogue-api/tests/test_workbench_agentic_task_actions.py`
- Modify: `datalogue-api/app/schemas/agentscope_workbench.py`
- Modify: `datalogue-api/app/services/workbench_actions.py`

- [ ] **Step 1: Write failing Workbench retry test**

Create `datalogue-api/tests/test_workbench_agentic_task_actions.py`:

```python
# ============================================================
# File Name   : test_workbench_agentic_task_actions.py
# Description:
#   Workbench action 迁移到 AgenticShellTaskRequest 的契约测试。
#
# Responsibilities:
#   - 验证 retry action 返回 task_request，而不是旧 chat run_request。
#   - 验证 retry task_request 带 task_source=workbench 和 retry_checkpoint_ref。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from datetime import datetime, timezone

from app.models.agentscope_workbench import AgentScopeMessage
from app.schemas.agentscope_workbench import WorkbenchRetryRequest
from app.services.agentscope_mirror import create_agentscope_session, record_agentscope_ref
from app.services.workbench_actions import request_controlled_retry


def test_workbench_retry_returns_agentic_shell_task_request(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        title="统计合同总金额",
        legacy_conversation_id=7,
        metadata={"dataset_id": 12},
    )
    failed = AgentScopeMessage(
        message_id="msg-failed",
        thread_id=session.thread_id,
        role="assistant",
        status="failed",
        content_summary="查询失败",
        business_payload_json={"question": "统计合同总金额", "dataset_id": 12},
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(failed)
    db_session.commit()
    record_agentscope_ref(
        db_session,
        thread_id=session.thread_id,
        message_id=failed.message_id,
        ref_type="checkpoint",
        ref_value="checkpoint://as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/msg-failed/query_context_ready",
        relation="checkpoint",
    )

    response = request_controlled_retry(
        db_session,
        request=WorkbenchRetryRequest(
            thread_id=session.thread_id,
            message_id=failed.message_id,
            checkpoint_ref="checkpoint://as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/msg-failed/query_context_ready",
            selected_action="retry_last_step",
        ),
    )

    assert response.accepted is True
    assert response.task_request is not None
    assert response.task_request.task_source == "workbench"
    assert response.task_request.retry_checkpoint_ref.startswith("checkpoint://")
    assert response.run_request is None
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_workbench_agentic_task_actions.py -q
```

Expected: FAIL because `WorkbenchRetryResponse` does not expose `task_request`.

- [ ] **Step 3: Update Workbench schemas**

Modify `datalogue-api/app/schemas/agentscope_workbench.py`:

Import:

```python
from app.schemas.agentic_shell_task import AgenticShellTaskRequest
```

Change `WorkbenchRetryResponse` to include:

```python
    task_request: AgenticShellTaskRequest | None = None
    run_request: WorkbenchRetryRunRequest | None = None
```

Keep `run_request` temporarily for response backward compatibility, but all new service responses must set it to `None`.

- [ ] **Step 4: Update Workbench action service**

Modify `datalogue-api/app/services/workbench_actions.py`.

Import:

```python
from app.schemas.agentic_shell_task import AgenticShellTaskRequest
```

Add helper:

```python
def _build_retry_task_request(
    *,
    session: AgentScopeSession,
    source_message: AgentScopeMessage,
    checkpoint_ref: str,
) -> AgenticShellTaskRequest:
    return AgenticShellTaskRequest(
        task_source="workbench",
        task_type="bi_query",
        question=_retry_run_question(session=session, source_message=source_message),
        conversation_id=session.legacy_conversation_id,
        thread_id=session.thread_id,
        retry_checkpoint_ref=checkpoint_ref,
        dataset_id=_retry_dataset_id(source_message),
        client_context={"action": "retry_last_step"},
    )
```

In every accepted `WorkbenchRetryResponse`, replace:

```python
run_request=_build_retry_run_request(...)
```

with:

```python
task_request=_build_retry_task_request(...),
run_request=None,
```

Leave `_build_retry_run_request` in place only until frontend tests are migrated in Task 7; mark it unused by no call sites after this task.

- [ ] **Step 5: Run Workbench tests**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_workbench_agentic_task_actions.py tests/test_agentic_shell_retry_writer.py tests/test_workbench_retry_actions.py -q
```

Expected: PASS. If an existing test still asserts `run_request`, update that test to assert `task_request` with the same fields.

- [ ] **Step 6: Commit**

```bash
git add datalogue-api/app/schemas/agentscope_workbench.py \
  datalogue-api/app/services/workbench_actions.py \
  datalogue-api/tests/test_workbench_agentic_task_actions.py \
  datalogue-api/tests/test_agentic_shell_retry_writer.py \
  datalogue-api/tests/test_workbench_retry_actions.py
git commit -m "feat: return Agentic Shell task requests from Workbench retry"
```

---

### Task 6: Frontend Task Stream Client and Event Adapter

**Files:**
- Create: `datalogue-web/src/assistant/agentic-shell-task-api.js`
- Create: `datalogue-web/src/assistant/agentic-shell-task-api.test.js`
- Create: `datalogue-web/src/assistant/agentic-shell-event-adapter.js`
- Create: `datalogue-web/src/assistant/agentic-shell-event-adapter.test.js`
- Modify: `datalogue-web/src/api/client.js`

- [ ] **Step 1: Write failing frontend API tests**

Create `datalogue-web/src/assistant/agentic-shell-task-api.test.js`:

```javascript
import { describe, expect, it, vi, afterEach } from 'vitest';
import { streamAgenticShellTask } from './agentic-shell-task-api.js';

function sseStream(lines) {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(lines.join('\n')));
      controller.close();
    },
  });
}

describe('streamAgenticShellTask', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('posts to the new Agentic Shell task stream endpoint', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      body: sseStream([
        'data: {"task_id":"task-1","event_envelope":{"event_type":"task.started","payload":{}}}',
        '',
      ]),
    });

    const events = [];
    for await (const event of streamAgenticShellTask({ task_source: 'chat', task_type: 'bi_query', question: '统计合同总金额' })) {
      events.push(event);
    }

    expect(fetchSpy).toHaveBeenCalledWith('/api/agentic-shell/tasks/stream', expect.objectContaining({ method: 'POST' }));
    expect(events[0].event_envelope.event_type).toBe('task.started');
  });
});
```

Create `datalogue-web/src/assistant/agentic-shell-event-adapter.test.js`:

```javascript
import { describe, expect, it } from 'vitest';
import { agenticEnvelopeToChatEvent } from './agentic-shell-event-adapter.js';

describe('agenticEnvelopeToChatEvent', () => {
  it('maps message.delta to token event', () => {
    const event = agenticEnvelopeToChatEvent({
      event_envelope: {
        event_type: 'message.delta',
        payload: { content: '合同总金额' },
      },
    });

    expect(event).toEqual({ type: 'token', content: '合同总金额' });
  });

  it('maps task.completed to final event', () => {
    const event = agenticEnvelopeToChatEvent({
      task_id: 'task-1',
      event_envelope: {
        event_type: 'task.completed',
        payload: { summary: '完成' },
        legacy_payload: { type: 'final', answer: '完成' },
      },
    });

    expect(event.type).toBe('final');
    expect(event.task_id).toBe('task-1');
  });
});
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd datalogue-web
npx vitest run src/assistant/agentic-shell-task-api.test.js src/assistant/agentic-shell-event-adapter.test.js
```

Expected: FAIL because files do not exist.

- [ ] **Step 3: Add task stream client**

Create `datalogue-web/src/assistant/agentic-shell-task-api.js`:

```javascript
// Agentic Shell task stream client - Chat UI 和 Workbench 的唯一执行流入口。

export async function* streamAgenticShellTask(payload, { signal } = {}) {
  const res = await fetch('/api/agentic-shell/tasks/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith('data:')) continue;
      const body = line.slice(5).trim();
      if (!body) continue;
      try {
        yield JSON.parse(body);
      } catch {
        // 后端 SSE 可能包含 keepalive 或非 JSON 行，前端执行流忽略。
      }
    }
  }
}
```

- [ ] **Step 4: Add event adapter**

Create `datalogue-web/src/assistant/agentic-shell-event-adapter.js`:

```javascript
// Agentic Shell envelope 到旧 ChatModelAdapter 内部事件的迁移适配。

export function agenticEnvelopeToChatEvent(streamEvent = {}) {
  const envelope = streamEvent.event_envelope || {};
  const payload = envelope.payload || {};
  const legacy = streamEvent.legacy_payload || envelope.legacy_payload || {};

  if (envelope.event_type === 'message.delta') {
    return { type: 'token', content: payload.content || '' };
  }
  if (envelope.event_type === 'message.completed' || envelope.event_type === 'task.completed') {
    return {
      type: 'final',
      answer: legacy.answer || payload.summary || '',
      task_id: streamEvent.task_id || envelope.task_id,
      trace_id: envelope.trace_id || null,
      thread_id: envelope.thread_id || null,
      event_envelope: envelope,
    };
  }
  if (envelope.event_type === 'task.failed') {
    return {
      type: 'final',
      answer: payload.error_summary || '任务执行失败，内部细节已隐藏。',
      task_id: streamEvent.task_id || envelope.task_id,
      trace_id: envelope.trace_id || null,
      entry_route: 'agentic_shell_failed',
      event_envelope: envelope,
    };
  }
  return {
    type: 'step',
    node: envelope.event_type || 'agentic_shell',
    display_name: payload.summary || envelope.event_type || 'Agentic Shell',
    task_id: streamEvent.task_id || envelope.task_id,
    event_envelope: envelope,
  };
}
```

- [ ] **Step 5: Disable old `/api/chat/stream` frontend helpers**

Modify `datalogue-web/src/api/client.js`:

Replace `streamChat` body with:

```javascript
export function streamChat() {
  throw new Error('CHAT_STREAM_REMOVED_USE_AGENTIC_SHELL_TASKS');
}
```

Replace `streamChatEvents` body with:

```javascript
export async function* streamChatEvents() {
  throw new Error('CHAT_STREAM_REMOVED_USE_AGENTIC_SHELL_TASKS');
}
```

Do not leave any `fetch('/api/chat/stream'...)` in this file.

- [ ] **Step 6: Run frontend API tests**

Run:

```bash
cd datalogue-web
npx vitest run src/assistant/agentic-shell-task-api.test.js src/assistant/agentic-shell-event-adapter.test.js
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add datalogue-web/src/assistant/agentic-shell-task-api.js \
  datalogue-web/src/assistant/agentic-shell-task-api.test.js \
  datalogue-web/src/assistant/agentic-shell-event-adapter.js \
  datalogue-web/src/assistant/agentic-shell-event-adapter.test.js \
  datalogue-web/src/api/client.js
git commit -m "feat: add frontend Agentic Shell task stream client"
```

---

### Task 7: Migrate Chat UI and Workbench to Task Stream

**Files:**
- Modify: `datalogue-web/src/assistant/chat-adapter.js`
- Modify: `datalogue-web/src/assistant/chat-adapter.test.js`
- Modify: `datalogue-web/src/components/workbench-panel.jsx`
- Modify: `datalogue-web/src/components/workbench-panel.test.jsx`
- Modify: `datalogue-web/src/components/chat-page.jsx`

- [ ] **Step 1: Write failing migration assertions**

In `datalogue-web/src/assistant/chat-adapter.test.js`, add an assertion to the main streaming test:

```javascript
expect(fetchSpy).toHaveBeenCalledWith('/api/agentic-shell/tasks/stream', expect.objectContaining({ method: 'POST' }));
expect(fetchSpy).not.toHaveBeenCalledWith('/api/chat/stream', expect.anything());
```

In `datalogue-web/src/components/workbench-panel.test.jsx`, update the retry test so `requestWorkbenchRetry` resolves:

```javascript
requestWorkbenchRetry.mockResolvedValueOnce({
  accepted: true,
  retry_message_id: 'msg_retry',
  task_request: {
    task_source: 'workbench',
    task_type: 'bi_query',
    question: '重试上一步',
    thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    retry_checkpoint_ref: 'checkpoint://as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/msg/query_context_ready',
    client_context: { action: 'retry_last_step' },
  },
  run_request: null,
});
```

Assert:

```javascript
expect(onRetryRun).toHaveBeenCalledWith(expect.objectContaining({ task_source: 'workbench' }));
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd datalogue-web
npx vitest run src/assistant/chat-adapter.test.js src/components/workbench-panel.test.jsx
```

Expected: FAIL because Chat still imports `streamChatEvents` and Workbench still expects `run_request`.

- [ ] **Step 3: Migrate chat adapter import and loop**

Modify `datalogue-web/src/assistant/chat-adapter.js`.

Replace:

```javascript
import { streamChatEvents } from '../api/client';
```

with:

```javascript
import { streamAgenticShellTask } from './agentic-shell-task-api';
import { agenticEnvelopeToChatEvent } from './agentic-shell-event-adapter';
```

Find the call around the existing `streamChatEvents(...)` loop and replace the stream creation with:

```javascript
stream = streamAgenticShellTask(
  {
    task_source: 'chat',
    task_type: 'bi_query',
    question: userText,
    conversation_id: remoteConversationId,
    dataset_id: selectedDatasetId,
    session_id: businessSessionId,
    thread_id: unstable_threadId || null,
  },
  { signal: abortController.signal },
);
```

Immediately inside the `for await` loop, normalize:

```javascript
const ev = agenticEnvelopeToChatEvent(rawEvent);
```

Keep the rest of the existing `token` / `step` / `final` handling as-is by using `ev` instead of the raw event.

- [ ] **Step 4: Migrate Workbench retry invocation**

Modify `datalogue-web/src/components/workbench-panel.jsx`.

Replace:

```jsx
if (response?.accepted && response?.run_request) {
  onRetryRun?.(response.run_request);
}
```

with:

```jsx
if (response?.accepted && response?.task_request) {
  // Workbench retry 创建新的 AgenticShellTask，不再绕回旧 chat stream。
  onRetryRun?.(response.task_request);
}
```

Do not call `run_request`.

- [ ] **Step 5: Migrate ChatPage retry runner**

Modify `datalogue-web/src/components/chat-page.jsx`.

Find the callback passed to `WorkbenchPanel` as `onRetryRun`. Change its payload name from run request to task request and send it through the same assistant adapter path that now calls `streamAgenticShellTask`. The callback must not construct `/api/chat/stream` payloads.

Add a public adapter method in `datalogue-web/src/assistant/chat-adapter.js`:

```javascript
async runAgenticShellTask(taskRequest) {
  return this.runTaskStream(taskRequest);
}
```

`runTaskStream` is the extracted shared implementation used by normal chat sends and Workbench retry. It accepts a complete `AgenticShellTaskRequest`, calls `streamAgenticShellTask`, maps each envelope through `agenticEnvelopeToChatEvent`, and then executes the existing `token` / `step` / `final` handlers.

Replace the `onRetryRun` callback body with:

```javascript
await chatModelAdapter.runAgenticShellTask(taskRequest);
```

- [ ] **Step 6: Run frontend migration tests**

Run:

```bash
cd datalogue-web
npx vitest run src/assistant/agentic-shell-task-api.test.js \
  src/assistant/agentic-shell-event-adapter.test.js \
  src/assistant/chat-adapter.test.js \
  src/components/workbench-panel.test.jsx
```

Expected: PASS.

- [ ] **Step 7: Search for old frontend execution URL**

Run:

```bash
rg -n "/api/chat/stream|streamChatEvents\\(|streamChat\\(" datalogue-web/src
```

Expected: no execution call sites. Allowed matches are local throw helpers or tests asserting migration errors.

- [ ] **Step 8: Commit**

```bash
git add datalogue-web/src/assistant/chat-adapter.js \
  datalogue-web/src/assistant/chat-adapter.test.js \
  datalogue-web/src/components/workbench-panel.jsx \
  datalogue-web/src/components/workbench-panel.test.jsx \
  datalogue-web/src/components/chat-page.jsx
git commit -m "feat: route Chat and Workbench through Agentic Shell tasks"
```

---

### Task 8: Full Regression, Documentation, and Project Memory

**Files:**
- Create: `docs/test-reports/2026-07-02-agentic-shell-unified-task-entry.md`
- Modify: `docs/上下文入口.md`
- Modify: `.codex/project-memory.md`

- [ ] **Step 1: Run backend regression**

Run:

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_agentic_shell_task_contracts.py \
  tests/test_agentic_shell_event_projection.py \
  tests/test_agentic_shell_task_runtime.py \
  tests/test_agentic_shell_task_api.py \
  tests/test_agentic_shell_chat_stream_removed.py \
  tests/test_workbench_agentic_task_actions.py \
  tests/test_agentscope_mirror_models.py \
  tests/test_workbench_view_api.py \
  tests/test_as_r0_security_matrix.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend regression**

Run:

```bash
cd datalogue-web
npx vitest run src/assistant/agentic-shell-task-api.test.js \
  src/assistant/agentic-shell-event-adapter.test.js \
  src/assistant/chat-adapter.test.js \
  src/components/workbench-panel.test.jsx
npm run build
```

Expected: Vitest PASS and build PASS. Existing Vite chunk-size warning is acceptable.

- [ ] **Step 3: Hard-cut search checks**

Run:

```bash
rg -n "/api/chat/stream|@router\\.post\\(\\\"/stream\\\"\\)|streamChatEvents\\(|streamChat\\(" datalogue-api/app datalogue-web/src datalogue-api/tests datalogue-web/src
```

Expected: no backend route and no frontend execution call sites. Allowed matches:

- `test_agentic_shell_chat_stream_removed.py`
- local helper throwing `CHAT_STREAM_REMOVED_USE_AGENTIC_SHELL_TASKS`
- documentation or test report text.

- [ ] **Step 4: Write test report**

Create `docs/test-reports/2026-07-02-agentic-shell-unified-task-entry.md`:

```markdown
# Agentic Shell Unified Task Entry Test Report

## Scope

- Added `/api/agentic-shell/tasks/stream` as the only execution entry.
- Removed `/api/chat/stream` from execution.
- Routed Chat UI and Workbench retry through `AgenticShellTaskRequest`.
- Projected AgentScope runtime events to Datalogue stable envelopes.

## Verification

Backend:

```bash
python3 -m pytest \
  tests/test_agentic_shell_task_contracts.py \
  tests/test_agentic_shell_event_projection.py \
  tests/test_agentic_shell_task_runtime.py \
  tests/test_agentic_shell_task_api.py \
  tests/test_agentic_shell_chat_stream_removed.py \
  tests/test_workbench_agentic_task_actions.py \
  tests/test_agentscope_mirror_models.py \
  tests/test_workbench_view_api.py \
  tests/test_as_r0_security_matrix.py -q
```

Frontend:

```bash
npx vitest run src/assistant/agentic-shell-task-api.test.js \
  src/assistant/agentic-shell-event-adapter.test.js \
  src/assistant/chat-adapter.test.js \
  src/components/workbench-panel.test.jsx
npm run build
```

Hard-cut search:

```bash
rg -n "/api/chat/stream|@router\\.post\\(\\\"/stream\\\"\\)|streamChatEvents\\(|streamChat\\(" datalogue-api/app datalogue-web/src datalogue-api/tests datalogue-web/src
```

## Residual Risk

- First-stage runtime moves Chat/Workbench ownership to `AgenticShellTask`; BI execution still runs through `LegacyWorkflowTaskRunner` until DatasetAgent run is fully AgentScope-owned.
- Report/Python/Audit remain disabled until their AgentScope-owned runners are explicitly implemented.
```

报告必须记录实际命令输出中的通过数量、warning 数量和失败详情；不要写推测结果。

- [ ] **Step 5: Update context docs**

Modify `docs/上下文入口.md` with a short current-entry note:

```markdown
## 当前主执行入口

- Chat UI 和 Workbench 执行动作统一从 `/api/agentic-shell/tasks/stream` 创建 `AgenticShellTask`。
- `/api/chat/stream` 已从执行链路删除，不再转发、不再作为兼容执行入口。
- AgentScope Message/Event 是内部运行时事实；Datalogue Event Envelope 是前端、Workbench 和审计查询的稳定协议。
```

- [ ] **Step 6: Update project memory**

Before editing `.codex/project-memory.md`, capture the actual completion time:

```bash
date '+%Y-%m-%d %H:%M'
```

Append to `.codex/project-memory.md` using the required chronological format. Replace `2026-07-02 10:30` below with the command output if implementation completes at a different minute:

```markdown
### 2026-07-02 10:30 · Agentic Shell 统一任务入口硬切

- 涉及文件：`datalogue-api/app/api/agentic_shell.py`、`datalogue-api/app/services/agentic_shell_task_runtime.py`、`datalogue-api/app/services/agentic_shell_event_projection.py`、`datalogue-api/app/schemas/agentic_shell_task.py`、`datalogue-api/app/models/agentic_shell_task.py`、`datalogue-web/src/assistant/agentic-shell-task-api.js`、`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/components/workbench-panel.jsx`、`docs/test-reports/2026-07-02-agentic-shell-unified-task-entry.md`、`.codex/project-memory.md`
- 关键改动：新增 `/api/agentic-shell/tasks/stream` 作为唯一执行入口；Chat UI 和 Workbench retry/action 改为创建 `AgenticShellTask`；AgentScope 原生 Message/Event 投影为 Datalogue 稳定 envelope；`/api/chat/stream` 从执行链路删除。
- 安全边界：前端和 DB 不依赖 AgentScope Python 对象；用户可见 SSE/API response 不暴露 SQL、schema、DSL、raw rows、repair patch body、tool internal payload。
- 验证方式：记录后端 pytest、前端 vitest/build、`rg /api/chat/stream` 硬切检查和真实页面验收结果；如果真实页面验收尚未执行，明确写“真实页面验收未执行”。
- 残留风险：第一阶段完成入口 ownership 替换，真实 BI 问数通过 `LegacyWorkflowTaskRunner` 临时承接；BI 执行本体完全收进 AgentScope-owned DatasetAgent run、Report/Python/Audit 启用和 LegacyWorkflowAdapter 清理留到后续阶段。
```

- [ ] **Step 7: Commit docs and report**

```bash
git add docs/test-reports/2026-07-02-agentic-shell-unified-task-entry.md \
  docs/上下文入口.md \
  .codex/project-memory.md
git commit -m "docs: record Agentic Shell task entry validation"
```

---

## Plan Self-Review

Spec coverage:

- New endpoint `/api/agentic-shell/tasks/stream`: Task 4.
- `AgenticShellTaskRequest` and `AgenticShellTask`: Task 1.
- AgentScope native event projection to stable Datalogue envelope: Task 2.
- Task runtime spine and safe failures: Task 3.
- Workbench retry creates task request: Task 5.
- Chat UI and Workbench frontend migration: Tasks 6 and 7.
- `/api/chat/stream` hard removal: Tasks 4, 7, and 8.
- Verification and project memory: Task 8.

Placeholder scan:

- No incomplete task descriptions are intentionally present.
- Every created file has a concrete path and concrete purpose.
- Every task includes exact commands and expected outcomes.

Type consistency:

- `AgenticShellTaskRequest` is used by backend API, Workbench retry response, frontend task client, and Chat adapter.
- `AgenticShellTaskStreamEvent` wraps `DatalogueEventEnvelope` and carries `legacy_payload`.
- `task_id`, `trace_id`, `thread_id`, `message_id`, and `selected_agent` are consistently passed through projection, runtime, and SSE.
