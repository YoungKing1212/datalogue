# BI LeadAgent K3 AgentScope Native Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 K1/K2 已验证的业务契约上，把内部 handoff 实现演进为更接近 AgentScope native run、event 和 agent-to-agent handoff 的形态，同时继续保留 Datalogue DB 为业务状态真相源。

**Architecture:** K3 不把 AgentScope session/event 升级为业务真相源；Datalogue DB 仍裁决 run、confirmation、handoff、artifact/checkpoint refs。K3 增加 AgentScope native handoff port 和实现，BIHandoffService 只依赖 port，内部可在 Host Adapter 与 native handoff 间切换。AgentScope native 事件必须投影成 Datalogue 可审计的 handoff event，不向 BI LeadAgent 暴露 Dataset 原子工具。

**Tech Stack:** AgentScope 2.0 SDK、FastAPI、SQLAlchemy、pytest、Datalogue AgentScope mirror、Datalogue BI LeadAgent K1/K2 contracts。

---

## 0. Scope And Dependencies

K3 依赖：

- K1：后端契约、DB 模型、AgentScope 2.0 SDK DatasetAgent tool-calling adapter。
- K2：页面确认和端到端原型已验证。

K3 做：

- 抽象 handoff port。
- 新增 AgentScope native handoff 实现。
- 将 AgentScope native run/event 投影到 Datalogue handoff record。
- 增加 native handoff feature flag。
- 增加双实现一致性测试。
- 为 F3 长生命周期会话 agent 留稳定迁移入口。

K3 不做：

- 让 AgentScope session/event 取代 Datalogue DB 真相源。
- 启用多数据集查询。
- 启用 ReportAgent/PythonAgent/AuditAgent。
- 完整 F3 长生命周期会话 agent。

## 1. File Structure

Create:

- `datalogue-api/app/services/bi_lead_agent/handoff_port.py`
  定义 BI handoff port 协议和标准 request/result。

- `datalogue-api/app/services/bi_lead_agent/native_handoff.py`
  AgentScope native handoff 实现，承接 BI LeadAgent -> DatasetAgent 子运行。

- `datalogue-api/app/services/bi_lead_agent/handoff_events.py`
  将 AgentScope native run/event 映射为 Datalogue handoff 状态和安全事件摘要。

- `datalogue-api/tests/test_bi_lead_agent_handoff_port.py`
  验证 BIHandoffService 只依赖 port。

- `datalogue-api/tests/test_bi_lead_agent_native_handoff.py`
  验证 native handoff 返回 D2 安全结果、状态映射和禁露边界。

- `datalogue-api/tests/test_bi_lead_agent_handoff_parity.py`
  验证 Host Adapter 和 native handoff 在同一输入下输出同构 D2 结果。

- `docs/test-reports/2026-07-01-bi-lead-agent-k3.md`
  K3 验收报告。

Modify:

- `datalogue-api/app/core/config.py`
  增加 `BI_LEAD_AGENT_HANDOFF_MODE=host_adapter|agentscope_native`，默认 `host_adapter`。

- `datalogue-api/app/services/bi_lead_agent/handoff_service.py`
  改为依赖 `BIHandoffPort`，不直接依赖具体 adapter 类。

- `datalogue-api/app/services/bi_lead_agent/handoff_adapter.py`
  标记为 host adapter implementation，保持 K1/K2 兼容。

- `datalogue-api/app/services/bi_lead_agent/dataset_agent_factory.py`
  提供 native handoff 复用的 DatasetAgent 构造入口。

- `.codex/project-memory.md`
  K3 完成后记录功能与验证。

## 2. Task List

### Task 1: Handoff port 抽象

**Files:**

- Create: `datalogue-api/app/services/bi_lead_agent/handoff_port.py`
- Modify: `datalogue-api/app/services/bi_lead_agent/handoff_service.py`
- Test: `datalogue-api/tests/test_bi_lead_agent_handoff_port.py`

- [ ] **Step 1: Write failing port test**

Create `datalogue-api/tests/test_bi_lead_agent_handoff_port.py`:

```python
# ============================================================
# File Name   : test_bi_lead_agent_handoff_port.py
# Description:
#   BI LeadAgent handoff port 抽象测试。
#
# Responsibilities:
#   - 验证 BIHandoffService 只依赖 query_dataset port。
#   - 确保后续 Host Adapter 与 AgentScope native handoff 可互换。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

import pytest

from app.schemas.bi_lead_agent import BILeadAgentHandoffResult
from app.services.bi_lead_agent.handoff_port import BIHandoffPort


class FakePort:
    async def query_dataset(self, request, *, task_id):
        return BILeadAgentHandoffResult(
            handoff_id="handoff-port-001",
            child_run_id="dataset-run-port-001",
            dataset_id=request.dataset_id,
            task_id=task_id,
            trace_id=request.trace_id,
            handoff_status="completed",
            answer_summary="native 和 host adapter 输出同构。",
            artifact_ref="artifact-port-001",
            checkpoint_ref="checkpoint-port-001",
        )


@pytest.mark.asyncio
async def test_fake_port_satisfies_bi_handoff_port_protocol():
    port: BIHandoffPort = FakePort()
    assert hasattr(port, "query_dataset")
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_handoff_port.py -q
```

Expected: FAIL with missing `handoff_port`.

- [ ] **Step 3: Implement handoff port**

Create `datalogue-api/app/services/bi_lead_agent/handoff_port.py`:

```python
# ============================================================
# File Name   : handoff_port.py
# Description:
#   BI LeadAgent handoff 可替换端口。
#
# Responsibilities:
#   - 定义 Host Adapter 与 AgentScope native handoff 的共同接口。
#   - 让 BIHandoffService 只依赖 D2 安全结果契约，不依赖具体运行时实现。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from typing import Protocol

from app.schemas.bi_lead_agent import BILeadAgentHandoffRequest, BILeadAgentHandoffResult


class BIHandoffPort(Protocol):
    async def query_dataset(self, request: BILeadAgentHandoffRequest, *, task_id: str | None) -> BILeadAgentHandoffResult:
        """执行 BI LeadAgent 到 DatasetAgent 的任务交接，并返回 D2 安全结果。"""
```

- [ ] **Step 4: Update handoff service type**

Modify `datalogue-api/app/services/bi_lead_agent/handoff_service.py`:

```python
from app.services.bi_lead_agent.handoff_port import BIHandoffPort
```

Change constructor:

```python
class BIHandoffService:
    def __init__(self, db: Session, *, adapter: BIHandoffPort) -> None:
        self.db = db
        self.adapter = adapter
```

- [ ] **Step 5: Run port and existing service tests**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_handoff_port.py tests/test_bi_lead_agent_services.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add datalogue-api/app/services/bi_lead_agent/handoff_port.py datalogue-api/app/services/bi_lead_agent/handoff_service.py datalogue-api/tests/test_bi_lead_agent_handoff_port.py
git commit -m "refactor: add BI LeadAgent handoff port"
```

### Task 2: Native handoff event mapping

**Files:**

- Create: `datalogue-api/app/services/bi_lead_agent/handoff_events.py`
- Test: `datalogue-api/tests/test_bi_lead_agent_native_handoff.py`

- [ ] **Step 1: Write failing event mapping test**

Create `datalogue-api/tests/test_bi_lead_agent_native_handoff.py`:

```python
# ============================================================
# File Name   : test_bi_lead_agent_native_handoff.py
# Description:
#   BI LeadAgent AgentScope native handoff 测试。
#
# Responsibilities:
#   - 验证 native event 到 Datalogue handoff 状态的映射。
#   - 验证映射结果不暴露 DatasetAgent 内部敏感上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from app.services.bi_lead_agent.handoff_events import map_native_handoff_event


def test_native_handoff_event_maps_to_safe_datalogue_status():
    result = map_native_handoff_event(
        {
            "event_type": "agent.child.completed",
            "child_run_id": "dataset-native-001",
            "artifact_ref": "artifact-native-001",
            "checkpoint_ref": "checkpoint-native-001",
            "answer_summary": "查询完成。",
            "sql": "select * from orders",
            "schema": {"orders": ["amount"]},
        }
    )

    assert result["handoff_status"] == "completed"
    assert result["child_run_id"] == "dataset-native-001"
    assert result["artifact_ref"] == "artifact-native-001"
    assert "sql" not in result
    assert "schema" not in result
```

- [ ] **Step 2: Run mapping test to verify failure**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_native_handoff.py -q
```

Expected: FAIL with missing module.

- [ ] **Step 3: Implement event mapping**

Create `datalogue-api/app/services/bi_lead_agent/handoff_events.py`:

```python
# ============================================================
# File Name   : handoff_events.py
# Description:
#   AgentScope native handoff event 到 Datalogue handoff 状态的映射。
#
# Responsibilities:
#   - 将 AgentScope 子运行事件转换为 E2 handoff_status。
#   - 只保留 D2 安全摘要和 refs，丢弃 SQL/schema/raw rows/DSL。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from typing import Any


FORBIDDEN_NATIVE_EVENT_KEYS = {
    "sql",
    "schema",
    "schema_context",
    "raw_rows",
    "dsl",
    "compiled_query_ref",
    "repair_patch",
    "candidate_assets",
    "blueprint_body",
}


def map_native_handoff_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "")
    if event_type.endswith(".completed"):
        status = "completed"
    elif event_type.endswith(".blocked"):
        status = "blocked"
    elif event_type.endswith(".failed"):
        status = "failed"
    elif event_type.endswith(".cancelled"):
        status = "cancelled"
    else:
        status = "running"

    mapped = {
        "handoff_status": status,
        "child_run_id": event.get("child_run_id"),
        "artifact_ref": event.get("artifact_ref"),
        "checkpoint_ref": event.get("checkpoint_ref"),
        "answer_summary": event.get("answer_summary"),
        "row_count": event.get("row_count"),
        "column_count": event.get("column_count"),
        "status_reason": event.get("status_reason"),
        "error_code": event.get("error_code"),
        "error_summary": event.get("error_summary"),
    }
    return {key: value for key, value in mapped.items() if value is not None and key not in FORBIDDEN_NATIVE_EVENT_KEYS}
```

- [ ] **Step 4: Run mapping test**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_native_handoff.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add datalogue-api/app/services/bi_lead_agent/handoff_events.py datalogue-api/tests/test_bi_lead_agent_native_handoff.py
git commit -m "feat: map AgentScope native handoff events"
```

### Task 3: AgentScope native handoff implementation

**Files:**

- Create: `datalogue-api/app/services/bi_lead_agent/native_handoff.py`
- Modify: `datalogue-api/tests/test_bi_lead_agent_native_handoff.py`

- [ ] **Step 1: Add failing native handoff result test**

Append to `datalogue-api/tests/test_bi_lead_agent_native_handoff.py`:

```python
import pytest

from app.schemas.bi_lead_agent import BILeadAgentHandoffRequest
from app.services.bi_lead_agent.native_handoff import AgentScopeNativeBIHandoff


class FakeNativeRuntime:
    async def handoff(self, payload):
        return {
            "event_type": "agent.child.completed",
            "child_run_id": "dataset-native-002",
            "artifact_ref": "artifact-native-002",
            "checkpoint_ref": "checkpoint-native-002",
            "answer_summary": "native handoff 查询完成。",
            "row_count": 8,
            "column_count": 2,
            "raw_rows": [{"amount": 1}],
        }


@pytest.mark.asyncio
async def test_agent_scope_native_handoff_returns_d2_safe_result():
    handoff = AgentScopeNativeBIHandoff(native_runtime=FakeNativeRuntime())
    result = await handoff.query_dataset(
        BILeadAgentHandoffRequest(
            dataset_id=12,
            confirmed_question="统计订单金额",
            task_goal="执行单数据集问数",
            user_confirmation_id=3,
            routing_rationale="订单金额问题应由订单数据集回答。",
            trace_id="trace-native-002",
            parent_run_id="7",
        ),
        task_id="task-native-002",
    )

    assert result.handoff_status == "completed"
    assert result.child_run_id == "dataset-native-002"
    assert result.answer_summary == "native handoff 查询完成。"
    assert "raw_rows" not in result.model_dump_json()
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_native_handoff.py -q
```

Expected: FAIL with missing `native_handoff`.

- [ ] **Step 3: Implement native handoff**

Create `datalogue-api/app/services/bi_lead_agent/native_handoff.py`:

```python
# ============================================================
# File Name   : native_handoff.py
# Description:
#   BI LeadAgent 的 AgentScope native handoff 实现。
#
# Responsibilities:
#   - 将 query_dataset 业务任务包提交给 AgentScope native 子运行。
#   - 把 native child agent event 映射为 D2 安全 handoff 结果。
#   - 保持 Datalogue DB 为业务状态真相源，不让 AgentScope event 直接裁决业务状态。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from typing import Any
from uuid import uuid4

from app.schemas.bi_lead_agent import BILeadAgentHandoffRequest, BILeadAgentHandoffResult
from app.services.bi_lead_agent.handoff_events import map_native_handoff_event


class AgentScopeNativeBIHandoff:
    def __init__(self, *, native_runtime: Any) -> None:
        self.native_runtime = native_runtime

    async def query_dataset(self, request: BILeadAgentHandoffRequest, *, task_id: str | None) -> BILeadAgentHandoffResult:
        handoff_id = f"handoff-native-{uuid4().hex}"
        event = await self.native_runtime.handoff(
            {
                "handoff_id": handoff_id,
                "parent_agent": "bi_lead_agent",
                "child_agent": "dataset_agent",
                "dataset_id": request.dataset_id,
                "confirmed_question": request.confirmed_question,
                "task_goal": request.task_goal,
                "routing_rationale": request.routing_rationale,
                "trace_id": request.trace_id,
                "task_id": task_id,
            }
        )
        mapped = map_native_handoff_event(event)
        return BILeadAgentHandoffResult(
            handoff_id=handoff_id,
            child_run_id=mapped.get("child_run_id"),
            dataset_id=request.dataset_id,
            task_id=task_id,
            trace_id=request.trace_id,
            handoff_status=mapped["handoff_status"],
            answer_summary=mapped.get("answer_summary"),
            artifact_ref=mapped.get("artifact_ref"),
            checkpoint_ref=mapped.get("checkpoint_ref"),
            row_count=mapped.get("row_count"),
            column_count=mapped.get("column_count"),
            status_reason=mapped.get("status_reason"),
            error_code=mapped.get("error_code"),
            error_summary=mapped.get("error_summary"),
        )
```

- [ ] **Step 4: Run native handoff tests**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_native_handoff.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add datalogue-api/app/services/bi_lead_agent/native_handoff.py datalogue-api/tests/test_bi_lead_agent_native_handoff.py
git commit -m "feat: add AgentScope native BI handoff"
```

### Task 4: Feature flag and factory selection

**Files:**

- Modify: `datalogue-api/app/core/config.py`
- Modify: `datalogue-api/app/services/bi_lead_agent/handoff_adapter.py`
- Test: `datalogue-api/tests/test_bi_lead_agent_handoff_parity.py`

- [ ] **Step 1: Write failing selection test**

Create `datalogue-api/tests/test_bi_lead_agent_handoff_parity.py`:

```python
# ============================================================
# File Name   : test_bi_lead_agent_handoff_parity.py
# Description:
#   BI LeadAgent Host Adapter 与 AgentScope native handoff 一致性测试。
#
# Responsibilities:
#   - 验证两种 handoff 实现都返回 D2 安全结果。
#   - 验证 feature flag 只切换内部实现，不改变外部 API 契约。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from app.schemas.bi_lead_agent import BILeadAgentHandoffResult


def assert_d2_handoff_shape(result: BILeadAgentHandoffResult):
    payload = result.model_dump()
    assert payload["parent_agent"] == "bi_lead_agent"
    assert payload["child_agent"] == "dataset_agent"
    assert "sql" not in payload
    assert "schema" not in payload
    assert "raw_rows" not in payload
    assert "dsl" not in payload
```

- [ ] **Step 2: Run parity test to verify baseline**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_handoff_parity.py -q
```

Expected: PASS because helper file imports.

- [ ] **Step 3: Add config flag**

Modify `datalogue-api/app/core/config.py` settings:

```python
BI_LEAD_AGENT_HANDOFF_MODE: str = "host_adapter"
```

Valid values:

```text
host_adapter
agentscope_native
```

- [ ] **Step 4: Add handoff factory selector**

Append to `datalogue-api/app/services/bi_lead_agent/handoff_adapter.py`:

```python
from app.services.bi_lead_agent.native_handoff import AgentScopeNativeBIHandoff


class AgentScopeNativeRuntimeNotConfigured:
    async def handoff(self, payload):
        raise RuntimeError("AGENTSCOPE_NATIVE_HANDOFF_NOT_CONFIGURED")


def build_bi_handoff_port(db: Any):
    settings = get_settings()
    if settings.BI_LEAD_AGENT_HANDOFF_MODE == "agentscope_native":
        return AgentScopeNativeBIHandoff(native_runtime=AgentScopeNativeRuntimeNotConfigured())
    return build_bi_handoff_adapter(db)
```

Production wiring must keep default `host_adapter` until native runtime is backed by a real AgentScope native child-run implementation.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_handoff_port.py \
  tests/test_bi_lead_agent_native_handoff.py \
  tests/test_bi_lead_agent_handoff_parity.py \
  -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add datalogue-api/app/core/config.py datalogue-api/app/services/bi_lead_agent/handoff_adapter.py datalogue-api/tests/test_bi_lead_agent_handoff_parity.py
git commit -m "feat: add BI handoff mode selector"
```

### Task 5: API uses handoff port selector

**Files:**

- Modify: `datalogue-api/app/api/bi_lead_agent.py`
- Test: `datalogue-api/tests/test_bi_lead_agent_api.py`

- [ ] **Step 1: Write failing import expectation**

Add to `datalogue-api/tests/test_bi_lead_agent_api.py`:

```python
def test_bi_lead_agent_api_uses_handoff_port_selector():
    import inspect
    from app.api import bi_lead_agent

    source = inspect.getsource(bi_lead_agent)
    assert "build_bi_handoff_port" in source
    assert "build_bi_handoff_adapter" not in source
```

- [ ] **Step 2: Run API selector test**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_api.py::test_bi_lead_agent_api_uses_handoff_port_selector -q
```

Expected: FAIL because API still imports host adapter factory.

- [ ] **Step 3: Update API to use selector**

Modify `datalogue-api/app/api/bi_lead_agent.py`:

```python
from app.services.bi_lead_agent.handoff_adapter import build_bi_handoff_port
```

Change handoff endpoint:

```python
port = build_bi_handoff_port(db)
await BIHandoffService(db, adapter=port).query_dataset(run_id=run_id)
```

- [ ] **Step 4: Run API tests**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add datalogue-api/app/api/bi_lead_agent.py datalogue-api/tests/test_bi_lead_agent_api.py
git commit -m "refactor: route BI handoff through port selector"
```

### Task 6: K3 verification and documentation

**Files:**

- Create: `docs/test-reports/2026-07-01-bi-lead-agent-k3.md`
- Modify: `.codex/project-memory.md`

- [ ] **Step 1: Run K3 backend tests**

Run:

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_handoff_port.py \
  tests/test_bi_lead_agent_native_handoff.py \
  tests/test_bi_lead_agent_handoff_parity.py \
  tests/test_bi_lead_agent_api.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_agentscope_dataset_runtime_bridge.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Create test report**

Create `docs/test-reports/2026-07-01-bi-lead-agent-k3.md`:

```markdown
# BI LeadAgent K3 Test Report

## Scope

- BIHandoffPort abstraction.
- AgentScope native handoff event mapping.
- AgentScope native handoff D2 result shape.
- Feature flag selector.
- Host adapter and native handoff contract parity.

## Commands

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_handoff_port.py \
  tests/test_bi_lead_agent_native_handoff.py \
  tests/test_bi_lead_agent_handoff_parity.py \
  tests/test_bi_lead_agent_api.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_agentscope_dataset_runtime_bridge.py \
  -q
```

## Result

执行时写入真实 pytest 结果。

## Residual Risk

- 默认仍应保持 `BI_LEAD_AGENT_HANDOFF_MODE=host_adapter`，直到 native runtime 由真实 AgentScope child-run 服务支撑。
- F3 长生命周期会话 agent 仍是独立后续工作。
```

- [ ] **Step 3: Update project memory**

Append to `.codex/project-memory.md`:

```markdown
### 2026-07-01 20:30 BI LeadAgent K3 AgentScope native handoff 演进

- 涉及文件：`datalogue-api/app/services/bi_lead_agent/handoff_port.py`、`native_handoff.py`、`handoff_events.py`、`handoff_adapter.py`、`datalogue-api/app/api/bi_lead_agent.py`、`datalogue-api/tests/test_bi_lead_agent_handoff_*.py`。
- 关键改动：抽象 handoff port，新增 AgentScope native handoff 实现和事件映射，增加 handoff mode selector，并保持 Datalogue DB 为业务真相源。
- 验证方式：记录 K3 test report 中的 pytest 结果。
- 残留风险：真实 AgentScope native child-run 服务和 F3 长生命周期会话 agent 仍需后续独立推进。
```

- [ ] **Step 4: Commit Task 6**

```bash
git add docs/test-reports/2026-07-01-bi-lead-agent-k3.md .codex/project-memory.md
git commit -m "docs: record BI LeadAgent K3 validation"
```

## 3. Final Verification

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_models.py \
  tests/test_bi_lead_agent_capabilities.py \
  tests/test_bi_lead_agent_services.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_bi_lead_agent_handoff_port.py \
  tests/test_bi_lead_agent_native_handoff.py \
  tests/test_bi_lead_agent_handoff_parity.py \
  tests/test_bi_lead_agent_api.py \
  tests/test_agentscope_dataset_runtime_bridge.py \
  -q
```

Expected: PASS.

Manual config verification:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
BI_LEAD_AGENT_HANDOFF_MODE=host_adapter python3 -m pytest tests/test_bi_lead_agent_api.py -q
BI_LEAD_AGENT_HANDOFF_MODE=agentscope_native python3 -m pytest tests/test_bi_lead_agent_native_handoff.py -q
```

Expected: PASS. The `agentscope_native` mode test must not require a production native runtime unless a fake runtime is injected.

## 4. Self-Review

Spec coverage:

- K3 AgentScope native shape: Task 3 and Task 4.
- Datalogue DB remains truth source: Task 1 and Task 5 keep `BIHandoffService` persistence path.
- Host Adapter replacement boundary: Task 1 and Task 4.
- Native event projection: Task 2.
- Contract parity: Task 4.
- No Dataset atomic tools exposed to BI LeadAgent: Task 3 result shape and existing K1 tests.

Consistency checks:

- Default mode remains `host_adapter`.
- Native mode is behind feature flag.
- Native event mapping removes SQL/schema/raw rows/DSL.
- API still returns D2 handoff result shape.
- F3 long-lived session agent is not implemented in K3.
