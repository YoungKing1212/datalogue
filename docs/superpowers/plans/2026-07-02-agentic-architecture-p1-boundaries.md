# Agentic Architecture P1 Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重建 AgentScope P1 的目录边界，把 middleware、event projection、lifecycle/tracing 横切能力迁出 `app/services/`，并保留旧入口兼容。

**Architecture:** P1 只做“新目录拥有实现、旧目录薄 adapter 兼容”，不迁移 SQL 编译、执行、repair 和 BI 主链。新代码从 `app.middlewares`、`app.events`、`app.runtime` 导入；旧 `app.services.*` 路径短期 re-export，避免 API 和测试一次性断裂。

**Tech Stack:** Python 3、pytest、AgentScope 2.0 SDK、FastAPI 后端包结构。

---

## File Structure

- Create: `datalogue-api/app/middlewares/__init__.py`
  - 导出 `DatasetRuntimeToolLoggingMiddleware`、`log_lifecycle`、`log_output`、OTel bootstrap。
- Create: `datalogue-api/app/middlewares/safe_log_summary.py`
  - 持有 ToolMiddleware 安全日志摘要工具。
- Create: `datalogue-api/app/middlewares/dataset_tool_logging.py`
  - 持有 AgentScope ToolMiddleware 实现。
- Create: `datalogue-api/app/middlewares/lifecycle.py`
  - 持有 Agentic Shell 生命周期日志与输出摘要日志。
- Create: `datalogue-api/app/middlewares/tracing.py`
  - 持有 AgentScope OTel bootstrap。
- Create: `datalogue-api/app/events/__init__.py`
  - 导出 task envelope、AgentScope event projection、Workbench mirror projection。
- Create: `datalogue-api/app/events/projection.py`
  - 持有 `build_task_envelope`、`project_agentscope_event`、`project_event_envelope_to_agentscope` 等事件投影函数。
- Create: `datalogue-api/app/runtime/__init__.py`
  - 导出 AgentScope runtime boundary contract 和 driver。
- Create: `datalogue-api/app/runtime/boundary.py`
  - 持有 `AgentScopeRuntimeBoundaryContract`、`AgentScopeRuntimeToolSpec` 和 `DatalogueAgentScopeRuntimeDriver`。
- Create: `datalogue-api/app/agents/__init__.py`
  - 暴露 Datalogue Agent 包。
- Create: `datalogue-api/app/agents/agentic_lead_agent/__init__.py`
  - 导出正式名 `AgenticLeadAgent` 和迁移期兼容名 `DatalogueAgenticShell`。
- Create: `datalogue-api/app/agents/agentic_lead_agent/shell.py`
  - 持有 AgenticLeadAgent/Shell 契约、registry、tool policy、writer 和 sanitizer 实现。
- Modify: `datalogue-api/app/services/agentscope_middlewares/__init__.py`
  - 改为从 `app.middlewares` re-export。
- Modify: `datalogue-api/app/services/agentscope_middlewares/safe_log_summary.py`
  - 改为从 `app.middlewares.safe_log_summary` re-export。
- Modify: `datalogue-api/app/services/agentscope_middlewares/dataset_tool_logging.py`
  - 改为从 `app.middlewares.dataset_tool_logging` re-export。
- Modify: `datalogue-api/app/services/agentic_shell_event_projection.py`
  - 改为从 `app.events.projection` re-export task envelope 相关函数。
- Modify: `datalogue-api/app/services/agentscope_event_projection.py`
  - 改为从 `app.events.projection` re-export Workbench mirror 相关函数。
- Modify: `datalogue-api/app/services/agentic_shell_logging.py`
  - 改为从 `app.middlewares.lifecycle` re-export。
- Modify: `datalogue-api/app/services/observability/agentscope_otel.py`
  - 改为从 `app.middlewares.tracing` re-export。
- Modify: `datalogue-api/app/services/agentscope_runtime_driver.py`
  - 改为从 `app.runtime.boundary` re-export。
- Modify: `datalogue-api/app/services/agentic_shell.py`
  - 改为从 `app.agents.agentic_lead_agent.shell` re-export。
- Modify: `datalogue-api/app/main.py`
  - 改为从 `app.middlewares.tracing` 导入 OTel bootstrap。
- Modify: `datalogue-api/app/api/agentic_shell.py`
  - 改为从 `app.middlewares.lifecycle` 导入日志。
- Modify: `datalogue-api/app/services/agentic_shell_task_runtime.py`
  - 改为从 `app.events.projection` 和 `app.middlewares.lifecycle` 导入。
- Modify: `datalogue-api/app/services/agentscope_dataset_runtime.py`
  - 改为从 `app.middlewares` 导入 ToolMiddleware 和 lifecycle 日志。
- Test: `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`
  - 验证新目录导入、旧目录兼容、核心对象 identity、日志脱敏和 event projection 不变。

## Task 1: P1 Structure Tests

**Files:**
- Create: `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`

- [ ] **Step 1: Write the failing test**

```python
# ============================================================
# File Name   : test_agentic_architecture_p1_boundaries.py
# Description:
#   AgentScope 架构瘦身 P1 目录边界测试。
#
# Responsibilities:
#   - 验证 middleware 与 event projection 已由新目录持有。
#   - 验证旧 services 路径仍保持迁移期兼容，不破坏现有调用方。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import logging


def test_p1_middlewares_new_paths_own_runtime_logging():
    from app.middlewares import DatasetRuntimeToolLoggingMiddleware
    from app.middlewares.dataset_tool_logging import DatasetRuntimeToolLoggingMiddleware as DirectMiddleware
    from app.services.agentscope_middlewares import DatasetRuntimeToolLoggingMiddleware as LegacyMiddleware

    assert DatasetRuntimeToolLoggingMiddleware is DirectMiddleware
    assert LegacyMiddleware is DirectMiddleware
    assert DirectMiddleware.__module__ == "app.middlewares.dataset_tool_logging"


def test_p1_lifecycle_logging_new_path_sanitizes_sensitive_payload(caplog):
    from app.middlewares.lifecycle import log_lifecycle
    from app.services.agentic_shell_logging import log_lifecycle as legacy_log_lifecycle

    assert legacy_log_lifecycle is log_lifecycle
    with caplog.at_level(logging.INFO, logger="app.middlewares.lifecycle"):
        log_lifecycle(
            "dataset.query.completed",
            trace_id="trace-1",
            sql="SELECT * FROM secret_table",
            schema_context="secret schema",
            artifact_ref="artifact:1",
        )

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[agentic_shell.lifecycle]" in logs
    assert "trace-1" in logs
    assert "artifact:1" in logs
    assert "<redacted>" in logs
    assert "SELECT" not in logs
    assert "secret schema" not in logs


def test_p1_events_projection_new_path_preserves_legacy_task_projection():
    from app.events.projection import build_task_envelope, project_agentscope_event
    from app.services.agentic_shell_event_projection import (
        build_task_envelope as legacy_build_task_envelope,
        project_agentscope_event as legacy_project_agentscope_event,
    )

    assert legacy_build_task_envelope is build_task_envelope
    assert legacy_project_agentscope_event is project_agentscope_event

    envelope = project_agentscope_event(
        {"data": "{\"type\":\"token\",\"content\":\"hello\"}"},
        task_id="task-1",
        trace_id="trace-1",
        thread_id="thread-1",
        message_id="message-1",
        selected_agent="bi_agent",
    )

    assert envelope.event_type == "message.delta"
    assert envelope.payload == {"content": "hello"}
    assert envelope.task_id == "task-1"
    assert envelope.trace_id == "trace-1"


def test_p1_workbench_projection_new_path_preserves_legacy_sanitizer():
    from app.events.projection import sanitize_event_payload_for_workbench
    from app.services.agentscope_event_projection import (
        sanitize_event_payload_for_workbench as legacy_sanitize_event_payload_for_workbench,
    )

    assert legacy_sanitize_event_payload_for_workbench is sanitize_event_payload_for_workbench
    safe_payload = sanitize_event_payload_for_workbench(
        "answer.completed",
        {
            "summary": "完成",
            "artifact_ref": "artifact:1",
            "sql": "SELECT * FROM secret_table",
        },
    )

    assert safe_payload == {"summary": "完成", "artifact_ref": "artifact:1"}


def test_p1_tracing_new_path_keeps_legacy_observability_import():
    from app.middlewares import tracing
    from app.services.observability import agentscope_otel

    assert agentscope_otel.configure_agentscope_otel is tracing.configure_agentscope_otel
    assert agentscope_otel.shutdown_agentscope_otel is tracing.shutdown_agentscope_otel
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.middlewares'` or `No module named 'app.events'`.

## Task 2: Move Middleware Implementations

**Files:**
- Create: `datalogue-api/app/middlewares/__init__.py`
- Create: `datalogue-api/app/middlewares/safe_log_summary.py`
- Create: `datalogue-api/app/middlewares/dataset_tool_logging.py`
- Create: `datalogue-api/app/middlewares/lifecycle.py`
- Modify: `datalogue-api/app/services/agentscope_middlewares/__init__.py`
- Modify: `datalogue-api/app/services/agentscope_middlewares/safe_log_summary.py`
- Modify: `datalogue-api/app/services/agentscope_middlewares/dataset_tool_logging.py`
- Modify: `datalogue-api/app/services/agentic_shell_logging.py`

- [ ] **Step 1: Add new middleware package and move implementations**

Create `datalogue-api/app/middlewares/__init__.py`:

```python
# ============================================================
# File Name   : __init__.py
# Description:
#   AgentScope middleware 统一出口。
#
# Responsibilities:
#   - 暴露 Datalogue AgentScope 横切 middleware。
#   - 让新代码不再从 app.services 导入 middleware 能力。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from app.middlewares.dataset_tool_logging import DatasetRuntimeToolLoggingMiddleware
from app.middlewares.lifecycle import log_lifecycle, log_output

__all__ = [
    "DatasetRuntimeToolLoggingMiddleware",
    "log_lifecycle",
    "log_output",
]
```

Move current `safe_log_summary.py` source into `datalogue-api/app/middlewares/safe_log_summary.py`, keeping the same functions and forbidden-key behavior.

Move current `dataset_tool_logging.py` source into `datalogue-api/app/middlewares/dataset_tool_logging.py`, changing only this import:

```python
from app.middlewares.safe_log_summary import (
    extract_text_outputs,
    parse_json_object,
    summarize_mapping,
)
```

Move current `agentic_shell_logging.py` source into `datalogue-api/app/middlewares/lifecycle.py`, preserving logger names under `app.middlewares.lifecycle`.

- [ ] **Step 2: Turn legacy middleware paths into adapters**

Replace `datalogue-api/app/services/agentscope_middlewares/__init__.py` with:

```python
# ============================================================
# File Name   : __init__.py
# Description:
#   AgentScope middleware 旧路径兼容出口。
#
# Responsibilities:
#   - 迁移期从 app.middlewares re-export ToolMiddleware。
#   - 避免旧 services 路径继续承载新实现。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from app.middlewares import DatasetRuntimeToolLoggingMiddleware

__all__ = ["DatasetRuntimeToolLoggingMiddleware"]
```

Replace `datalogue-api/app/services/agentscope_middlewares/safe_log_summary.py` with imports from `app.middlewares.safe_log_summary`.

Replace `datalogue-api/app/services/agentscope_middlewares/dataset_tool_logging.py` with imports from `app.middlewares.dataset_tool_logging`.

Replace `datalogue-api/app/services/agentic_shell_logging.py` with imports from `app.middlewares.lifecycle`.

- [ ] **Step 3: Run middleware boundary test**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_middlewares_new_paths_own_runtime_logging tests/test_agentic_architecture_p1_boundaries.py::test_p1_lifecycle_logging_new_path_sanitizes_sensitive_payload -q
```

Expected: PASS.

### Task 11: Move Agentic Shell task runtime to `app/runtime/`

Move the unified Agentic Shell task runtime out of generic services. This runtime owns task truth-source creation, AgentScope mirror session/message wiring, lifecycle events and runner handoff, so it belongs under `app/runtime/`.

Files:

- Create: `datalogue-api/app/runtime/task_runtime.py`
- Modify: `datalogue-api/app/runtime/__init__.py`
- Modify: `datalogue-api/app/services/agentic_shell_task_runtime.py`
- Modify: `datalogue-api/app/api/agentic_shell.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`
- Modify: `datalogue-api/tests/test_agentic_shell_task_runtime.py`

- [x] **Step 1: Write the failing task runtime boundary test**

Add to `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`:

```python
def test_p1_runtime_new_path_owns_agentic_shell_task_runtime():
    from app.runtime import AgenticShellTaskRuntime, BILeadAgentTaskRunner
    from app.runtime.task_runtime import AgenticShellTaskRuntime as DirectRuntime
    from app.runtime.task_runtime import BILeadAgentTaskRunner as DirectRunner
    from app.services.agentic_shell_task_runtime import AgenticShellTaskRuntime as LegacyRuntime

    assert AgenticShellTaskRuntime is DirectRuntime
    assert BILeadAgentTaskRunner is DirectRunner
    assert LegacyRuntime is DirectRuntime
    assert DirectRuntime.__module__ == "app.runtime.task_runtime"
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_runtime_new_path_owns_agentic_shell_task_runtime -q
```

Expected: FAIL because `app.runtime.task_runtime` does not exist yet or is not exported.

- [x] **Step 3: Move runtime implementation**

Move `AgentScopeTaskRunner`, `BILeadAgentTaskRunner`, `AgenticShellTaskRuntime` and helper functions into `datalogue-api/app/runtime/task_runtime.py`, and export them from `datalogue-api/app/runtime/__init__.py`.

- [x] **Step 4: Keep legacy services runtime as adapter**

Replace `datalogue-api/app/services/agentic_shell_task_runtime.py` with a re-export import from `app.runtime.task_runtime`.

- [x] **Step 5: Update active API import**

Change `datalogue-api/app/api/agentic_shell.py` and tests to import task runtime classes from `app.runtime`.

- [x] **Step 6: Run task runtime verification**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_runtime_new_path_owns_agentic_shell_task_runtime tests/test_agentic_shell_task_runtime.py -q
```

Expected: PASS.

### Task 10: Move AgentScope thread resolver to `app/runtime/`

Move AgentScope Workbench thread ID normalization out of generic services. Thread resolution is part of the runtime boundary because it decides whether a request is an editable AgentScope thread or a read-only legacy conversation.

Files:

- Create: `datalogue-api/app/runtime/thread_resolver.py`
- Modify: `datalogue-api/app/runtime/__init__.py`
- Modify: `datalogue-api/app/services/agentscope_thread_resolver.py`
- Modify: `datalogue-api/app/services/agentscope_mirror.py`
- Modify: `datalogue-api/app/services/workbench_actions.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`

- [x] **Step 1: Write the failing thread resolver boundary test**

Add to `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`:

```python
def test_p1_runtime_new_path_owns_thread_resolver():
    from app.runtime import new_agentscope_thread_id, normalize_thread_id, resolve_thread_ref
    from app.runtime.thread_resolver import normalize_thread_id as direct_normalize_thread_id
    from app.services.agentscope_thread_resolver import normalize_thread_id as legacy_normalize_thread_id

    assert normalize_thread_id is direct_normalize_thread_id
    assert legacy_normalize_thread_id is direct_normalize_thread_id
    assert direct_normalize_thread_id.__module__ == "app.runtime.thread_resolver"
    assert normalize_thread_id(123) == "conv_123"
    assert resolve_thread_ref("conv_123").read_only is True
    assert new_agentscope_thread_id().startswith("as_")
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_runtime_new_path_owns_thread_resolver -q
```

Expected: FAIL because `app.runtime.thread_resolver` does not exist yet or is not exported.

- [x] **Step 3: Move resolver implementation**

Move `normalize_thread_id`, `resolve_thread_ref` and `new_agentscope_thread_id` into `datalogue-api/app/runtime/thread_resolver.py`, and export them from `datalogue-api/app/runtime/__init__.py`.

- [x] **Step 4: Keep legacy services resolver as adapter**

Replace `datalogue-api/app/services/agentscope_thread_resolver.py` with a re-export import from `app.runtime.thread_resolver`.

- [x] **Step 5: Update active imports**

Change runtime callers in `agentscope_mirror.py` and `workbench_actions.py` to import thread resolver functions from `app.runtime`.

- [x] **Step 6: Run thread resolver verification**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_runtime_new_path_owns_thread_resolver tests/test_agentic_shell_retry_writer.py -q
```

Expected: PASS.

### Task 9: Move Agentic Shell writer persistence to `app/persistence/`

Move `AgentScopeMirrorShellWriter` out of `app/services/agentic_shell_writers.py` into the persistence boundary. This writer owns durable Workbench/mirror writeback, so it should not stay under generic services after `AgenticLeadAgent` has become a first-class agent package.

Files:

- Create: `datalogue-api/app/persistence/__init__.py`
- Create: `datalogue-api/app/persistence/shell_writer.py`
- Modify: `datalogue-api/app/services/agentic_shell_writers.py`
- Modify: `datalogue-api/app/services/workbench_actions.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`

- [x] **Step 1: Write the failing persistence boundary test**

Add to `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`:

```python
def test_p1_persistence_new_path_owns_agentic_shell_writer():
    from app.persistence import AgentScopeMirrorShellWriter
    from app.persistence.shell_writer import AgentScopeMirrorShellWriter as DirectWriter
    from app.services.agentic_shell_writers import AgentScopeMirrorShellWriter as LegacyWriter

    assert AgentScopeMirrorShellWriter is DirectWriter
    assert LegacyWriter is DirectWriter
    assert DirectWriter.__module__ == "app.persistence.shell_writer"
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_persistence_new_path_owns_agentic_shell_writer -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.persistence'`.

- [x] **Step 3: Move writer implementation**

Move `AgentScopeMirrorShellWriter` implementation into `datalogue-api/app/persistence/shell_writer.py`, and export it from `datalogue-api/app/persistence/__init__.py`.

- [x] **Step 4: Keep legacy services writer as adapter**

Replace `datalogue-api/app/services/agentic_shell_writers.py` with a re-export import from `app.persistence.shell_writer`.

- [x] **Step 5: Update active Workbench retry import**

Change `datalogue-api/app/services/workbench_actions.py` to import `AgentScopeMirrorShellWriter` from `app.persistence`.

- [x] **Step 6: Run writer boundary verification**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_persistence_new_path_owns_agentic_shell_writer tests/test_agentic_shell_retry_writer.py -q
```

Expected: PASS.

## Task 3: Move Event Projection Implementations

**Files:**
- Create: `datalogue-api/app/events/__init__.py`
- Create: `datalogue-api/app/events/projection.py`
- Modify: `datalogue-api/app/services/agentic_shell_event_projection.py`
- Modify: `datalogue-api/app/services/agentscope_event_projection.py`

- [ ] **Step 1: Add event package and combined projection module**

Create `datalogue-api/app/events/__init__.py`:

```python
# ============================================================
# File Name   : __init__.py
# Description:
#   Datalogue 对外事件协议出口。
#
# Responsibilities:
#   - 暴露 AgentScope event 到 Datalogue envelope 的投影能力。
#   - 暴露 Workbench mirror 事件投影能力。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from app.events.projection import (
    build_task_envelope,
    extract_refs_from_envelope,
    extract_refs_from_payload,
    project_agentscope_event,
    project_event_envelope_to_agentscope,
    sanitize_event_payload_for_workbench,
)

__all__ = [
    "build_task_envelope",
    "extract_refs_from_envelope",
    "extract_refs_from_payload",
    "project_agentscope_event",
    "project_event_envelope_to_agentscope",
    "sanitize_event_payload_for_workbench",
]
```

Create `datalogue-api/app/events/projection.py` by moving the current source of `agentic_shell_event_projection.py` and `agentscope_event_projection.py` into one module. Keep function names unchanged.

- [ ] **Step 2: Turn legacy event paths into adapters**

Replace `datalogue-api/app/services/agentic_shell_event_projection.py` with imports from `app.events.projection`.

Replace `datalogue-api/app/services/agentscope_event_projection.py` with imports from `app.events.projection`.

- [ ] **Step 3: Run event boundary tests**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_events_projection_new_path_preserves_legacy_task_projection tests/test_agentic_architecture_p1_boundaries.py::test_p1_workbench_projection_new_path_preserves_legacy_sanitizer -q
```

Expected: PASS.

## Task 4: Move Tracing Bootstrap

**Files:**
- Create: `datalogue-api/app/middlewares/tracing.py`
- Modify: `datalogue-api/app/services/observability/agentscope_otel.py`
- Modify: `datalogue-api/app/main.py`

- [ ] **Step 1: Move OTel implementation**

Move current `datalogue-api/app/services/observability/agentscope_otel.py` source into `datalogue-api/app/middlewares/tracing.py`. Keep function and class names unchanged.

- [ ] **Step 2: Turn legacy observability module into adapter**

Replace `datalogue-api/app/services/observability/agentscope_otel.py` with:

```python
# ============================================================
# File Name   : agentscope_otel.py
# Description:
#   AgentScope OTel 旧路径兼容出口。
#
# Responsibilities:
#   - 迁移期从 app.middlewares.tracing re-export OTel bootstrap。
#   - 避免 app.services.observability 继续承载 AgentScope middleware 实现。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from app.middlewares.tracing import (
    LoggingSpanExporter,
    SpanExportResult,
    configure_agentscope_otel,
    shutdown_agentscope_otel,
)

__all__ = [
    "LoggingSpanExporter",
    "SpanExportResult",
    "configure_agentscope_otel",
    "shutdown_agentscope_otel",
]
```

Update `datalogue-api/app/main.py` to import `configure_agentscope_otel` and `shutdown_agentscope_otel` from `app.middlewares.tracing`.

- [ ] **Step 3: Run tracing boundary tests**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_tracing_new_path_keeps_legacy_observability_import tests/test_agentscope_otel.py -q
```

Expected: PASS.

## Task 5: Move Active Import Sites To New Paths

**Files:**
- Modify: `datalogue-api/app/api/agentic_shell.py`
- Modify: `datalogue-api/app/services/agentic_shell_task_runtime.py`
- Modify: `datalogue-api/app/services/agentscope_dataset_runtime.py`
- Modify: `datalogue-api/app/services/bi_lead_agent/handoff_service.py`
- Modify: `datalogue-api/app/services/bi_lead_agent/native_handoff.py`
- Modify tests that assert logger names when they intentionally cover new ownership.

- [ ] **Step 1: Update runtime imports**

Change active runtime code to import from:

```python
from app.events.projection import build_task_envelope, project_agentscope_event
from app.middlewares import DatasetRuntimeToolLoggingMiddleware
from app.middlewares.lifecycle import log_lifecycle, log_output
```

- [ ] **Step 2: Update tests that assert logger namespace**

Where tests intentionally capture lifecycle or ToolMiddleware logs, use:

```python
logger="app.middlewares.lifecycle"
logger="app.middlewares.dataset_tool_logging"
```

Keep old-path compatibility tests in `test_agentic_architecture_p1_boundaries.py`.

- [ ] **Step 3: Run focused behavior tests**

Run:

```bash
cd datalogue-api && python3 -m pytest \
  tests/test_agentic_architecture_p1_boundaries.py \
  tests/test_agentic_shell_event_projection.py \
  tests/test_agentscope_event_projection.py \
  tests/test_agentic_shell_task_runtime.py \
  tests/test_agentscope_dataset_runtime_bridge.py \
  tests/test_bi_lead_agent_native_handoff.py \
  tests/test_agentscope_otel.py \
  -q
```

Expected: PASS.

## Task 6: Verification And Project Memory

**Files:**
- Modify: `.codex/project-memory.md`

- [ ] **Step 1: Compile backend package**

Run:

```bash
python3 -m compileall datalogue-api/app -q
```

Expected: exits 0.

- [ ] **Step 2: Check import ownership**

Run:

```bash
rg -n "from app.services\\.(agentic_shell_logging|agentic_shell_event_projection|agentscope_event_projection)|app.services.agentscope_middlewares|app.services.observability.agentscope_otel" datalogue-api/app
```

Expected: only legacy adapter files or intentionally compatibility-scoped references remain.

- [ ] **Step 3: Update project memory**

Append one detailed record to `.codex/project-memory.md` with:

```text
2026-07-02 HH:mm · AgentScope P1 runtime/middleware/events 目录边界迁移

- 涉及文件：app/middlewares/*、app/events/*、旧 services adapter、相关测试。
- 关键改动：middleware/event/tracing 实现迁入新目录，旧路径 re-export 兼容，运行时代码改用新路径。
- 验证方式：列出本计划中实际通过的 pytest 和 compileall 命令。
- 残留风险或后续事项：P2 仍需迁移 BI Agent、Dataset Skill、BI Toolkit 和 SQL Control Plane。
```

- [ ] **Step 4: Final diff check**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; status shows P1 files plus pre-existing unrelated dirty files.

## Task 7: Move Runtime Boundary Driver

**Files:**
- Create: `datalogue-api/app/runtime/__init__.py`
- Create: `datalogue-api/app/runtime/boundary.py`
- Modify: `datalogue-api/app/services/agentscope_runtime_driver.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`
- Modify: `datalogue-api/tests/test_agentscope_runtime_driver_contract.py`
- Modify: `datalogue-api/tests/test_agentic_shell_contract.py`

- [ ] **Step 1: Write the failing runtime boundary test**

Add to `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`:

```python
def test_p1_runtime_boundary_new_path_owns_agentscope_runtime_driver():
    from app.runtime import DatalogueAgentScopeRuntimeDriver
    from app.runtime.boundary import DatalogueAgentScopeRuntimeDriver as DirectDriver
    from app.services.agentscope_runtime_driver import DatalogueAgentScopeRuntimeDriver as LegacyDriver

    assert DatalogueAgentScopeRuntimeDriver is DirectDriver
    assert LegacyDriver is DirectDriver
    assert DirectDriver.__module__ == "app.runtime.boundary"

    runtime_contract = DirectDriver().prepare_runtime(
        question="查询 GMV",
        context={"dataset_id": 12, "sql": "select * from orders"},
    )

    assert runtime_contract.driver_name == "agentscope_runtime_boundary"
    assert runtime_contract.projected_context == {"question": "查询 GMV", "dataset_id": 12}
    assert all(tool.provider == "DatalogueBIAtomicToolkit" for tool in runtime_contract.tool_registry)
    assert "select * from orders" not in runtime_contract.model_dump_json()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_runtime_boundary_new_path_owns_agentscope_runtime_driver -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.runtime'`.

- [ ] **Step 3: Move runtime boundary implementation**

Move current `datalogue-api/app/services/agentscope_runtime_driver.py` implementation into `datalogue-api/app/runtime/boundary.py`. Create `datalogue-api/app/runtime/__init__.py` to export:

```python
from app.runtime.boundary import (
    AgentScopeRuntimeBoundaryContract,
    AgentScopeRuntimeToolSpec,
    DatalogueAgentScopeRuntimeDriver,
    RuntimeToolStatus,
)
```

- [ ] **Step 4: Turn legacy runtime driver into adapter**

Replace `datalogue-api/app/services/agentscope_runtime_driver.py` with re-export imports from `app.runtime.boundary`.

- [ ] **Step 5: Update primary tests to new path**

Change `datalogue-api/tests/test_agentscope_runtime_driver_contract.py` to import:

```python
from app.runtime import DatalogueAgentScopeRuntimeDriver
```

Change the clean-process import test in `datalogue-api/tests/test_agentic_shell_contract.py` to import `app.runtime`.

- [ ] **Step 6: Run runtime verification**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_runtime_boundary_new_path_owns_agentscope_runtime_driver tests/test_agentscope_runtime_driver_contract.py tests/test_agentic_shell_contract.py::test_bi_atomic_toolkit_and_runtime_driver_import_in_clean_process -q
```

Expected: PASS.

## Task 8: Move AgenticLeadAgent Shell Boundary

**Files:**
- Create: `datalogue-api/app/agents/__init__.py`
- Create: `datalogue-api/app/agents/agentic_lead_agent/__init__.py`
- Create: `datalogue-api/app/agents/agentic_lead_agent/shell.py`
- Modify: `datalogue-api/app/services/agentic_shell.py`
- Modify: `datalogue-api/app/runtime/boundary.py`
- Modify: `datalogue-api/app/services/agentic_shell_task_runtime.py`
- Modify: `datalogue-api/app/services/agentscope_dataset_runtime.py`
- Modify: `datalogue-api/app/services/bi_tools/atomic.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`
- Modify: `datalogue-api/tests/test_agentic_shell_contract.py`
- Modify: `datalogue-api/tests/test_agentscope_runtime_driver_contract.py`

- [ ] **Step 1: Write the failing AgenticLeadAgent boundary test**

Add to `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`:

```python
def test_p1_agentic_lead_agent_new_path_owns_shell_contracts():
    from app.agents.agentic_lead_agent import AgenticLeadAgent, DatalogueAgenticShell
    from app.agents.agentic_lead_agent.shell import AgenticLeadAgent as DirectAgenticLeadAgent
    from app.services.agentic_shell import DatalogueAgenticShell as LegacyShell

    assert AgenticLeadAgent is DirectAgenticLeadAgent
    assert DatalogueAgenticShell is AgenticLeadAgent
    assert LegacyShell is AgenticLeadAgent
    assert AgenticLeadAgent.__module__ == "app.agents.agentic_lead_agent.shell"

    contract = AgenticLeadAgent().prepare_turn(
        question="查询 GMV",
        context={"dataset_id": 12, "sql": "select * from orders"},
    )

    assert contract.selected_agent == "bi_lead_agent"
    assert contract.projected_context.model_dump() == {"question": "查询 GMV", "dataset_id": 12}
    assert "select * from orders" not in contract.model_dump_json()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_agentic_lead_agent_new_path_owns_shell_contracts -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents'`.

- [ ] **Step 3: Move shell implementation**

Move the implementation from `datalogue-api/app/services/agentic_shell.py` into `datalogue-api/app/agents/agentic_lead_agent/shell.py`.

Add this alias after the class definition:

```python
AgenticLeadAgent = DatalogueAgenticShell
```

Create `datalogue-api/app/agents/agentic_lead_agent/__init__.py` to export both names and the contract DTOs. Create `datalogue-api/app/agents/__init__.py` to export `AgenticLeadAgent`.

- [ ] **Step 4: Turn legacy services shell into adapter**

Replace `datalogue-api/app/services/agentic_shell.py` with re-export imports from `app.agents.agentic_lead_agent.shell`.

- [ ] **Step 5: Update active runtime imports to new path**

Use `app.agents.agentic_lead_agent` or `app.agents.agentic_lead_agent.shell` in:

```python
datalogue-api/app/runtime/boundary.py
datalogue-api/app/services/agentic_shell_task_runtime.py
datalogue-api/app/services/agentscope_dataset_runtime.py
datalogue-api/app/services/bi_tools/atomic.py
```

Keep old-path compatibility coverage only in `test_agentic_architecture_p1_boundaries.py`.

- [ ] **Step 6: Run shell boundary verification**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p1_boundaries.py::test_p1_agentic_lead_agent_new_path_owns_shell_contracts tests/test_agentic_shell_contract.py tests/test_agentscope_runtime_driver_contract.py -q
```

Expected: PASS.
