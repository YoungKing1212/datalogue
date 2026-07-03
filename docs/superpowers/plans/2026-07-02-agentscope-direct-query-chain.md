# AgentScope Direct Query Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 先打通最小闭环 `AgenticLeadAgent -> BI Agent -> Dataset 问数工具链 -> artifact 结果`，并保证 `AgenticLeadAgent` 与 `BI Agent` 都由 AgentScope 2.0 `Agent` 创建。

**Architecture:** 新增一条直连链路，不复用 `AgenticShellTaskRuntime`、AgentScope mirror session/message/ref、BI handoff service 或 Workbench timeline。`AgenticLeadAgent` 先作为 AgentScope Agent 做顶层意图判断与路由提示；`BI Agent` 作为 AgentScope Agent 直接挂 Dataset 工具链 tools，由 prompt 约束工具调用顺序。底层只保留工具链必须的内存态 `AgentScopeDatasetRuntimeSession`，不写 Datalogue session/message/handoff 表。

**Tech Stack:** Python 3.13、FastAPI、SQLAlchemy、AgentScope 2.0 `Agent` / `Toolkit` / `reply_stream`、现有 `DatalogueBIAtomicToolkit`、现有 `AgentScopeDatasetRuntimeBridge`。

---

## Scope

本计划只做最小查询闭环：

- 做：`AgenticLeadAgent` AgentScope Agent 工厂。
- 做：`BI Agent` AgentScope Agent 工厂。
- 做：直连 runner，顺序调用 Lead Agent 和 BI Agent。
- 做：直连 API，例如 `POST /api/agentic-lead-agent/direct-query`。
- 做：返回 `summary`、`artifact_ref`、`checkpoint_ref`、`row_count`、`column_count`、`status`。
- 不做：`AgenticShellTask`。
- 不做：Datalogue `Session` / `Message` / `AgentScopeRef` 写入。
- 不做：`BIAgentHandoffService` / handoff DB。
- 不做：Workbench timeline。
- 不做：Report / Python / Audit 扩展 Agent。
- 不做：前端主入口替换；本轮只提供后端直连入口和测试。

## File Structure

- Create: `datalogue-api/app/agents/agentscope_model.py`
  - 统一创建 AgentScope `OpenAIChatModel`，避免 Lead/BI/Dataset 工厂重复拼 model。
- Create: `datalogue-api/app/agents/agentic_lead_agent/react_factory.py`
  - 创建真正的 AgentScope 2.0 `Agent(name="agentic_lead_agent")`。
  - Prompt 只负责顶层路由，不接触 SQL/schema/raw rows。
- Create: `datalogue-api/app/agents/bi_agent/react_factory.py`
  - 创建真正的 AgentScope 2.0 `Agent(name="bi_agent")`。
  - 直接注册 Dataset 工具链 tools，不经过 `DatasetQuerySkill`。
- Create: `datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py`
  - 最小链路 runner：Lead Agent reply -> BI Agent reply_stream -> Dataset runtime bridge -> safe response。
- Create: `datalogue-api/app/schemas/agentic_direct_query.py`
  - 直连 API request/response DTO。
- Create: `datalogue-api/app/api/agentic_lead_agent.py`
  - 新直连接口，不走 `/agentic-shell/tasks/stream`。
- Modify: `datalogue-api/app/api/__init__.py`
  - 注册新 router。
- Modify: `datalogue-api/app/agents/agentic_lead_agent/__init__.py`
  - 导出 `AgenticLeadAgentFactory` 与 `AgenticDirectQueryRunner`。
- Modify: `datalogue-api/app/agents/bi_agent/__init__.py`
  - 导出 `BIAgentFactory`。
- Test: `datalogue-api/tests/test_agentscope_direct_query_chain.py`
  - 覆盖 AgentScope Agent 工厂、直连 runner、API。

---

## Task 1: 建立 AgentScope model 工厂

**Files:**
- Create: `datalogue-api/app/agents/agentscope_model.py`
- Test: `datalogue-api/tests/test_agentscope_direct_query_chain.py`

- [ ] **Step 1: Write the failing test**

Add this test file:

```python
# ============================================================
# File Name   : test_agentscope_direct_query_chain.py
# Description:
#   AgentScope 2.0 直连问数链路测试。
#
# Responsibilities:
#   - 验证 AgenticLeadAgent 与 BI Agent 都由 AgentScope Agent 创建。
#   - 验证最小直连链路不依赖 AgenticShellTask、Session/Message 和 Handoff。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from agentscope.agent import Agent

from app.agents.agentscope_model import build_agentscope_chat_model


def test_agentscope_model_factory_builds_streaming_model(db_session):
    model = build_agentscope_chat_model(db=db_session, role="lead_agent", stream=True)

    assert model is not None
    assert hasattr(model, "stream")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py::test_agentscope_model_factory_builds_streaming_model -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.agentscope_model'`.

- [ ] **Step 3: Write minimal implementation**

Create `datalogue-api/app/agents/agentscope_model.py`:

```python
# ============================================================
# File Name   : agentscope_model.py
# Description:
#   AgentScope 2.0 Agent 使用的模型工厂。
#
# Responsibilities:
#   - 基于当前 LLM 配置创建 AgentScope OpenAIChatModel。
#   - 让 Lead Agent、BI Agent 和 DatasetAgent 复用同一套 SDK 模型创建逻辑。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from pydantic import SecretStr
from sqlalchemy.orm import Session

from agentscope.credential import OpenAICredential
from agentscope.model import OpenAIChatModel

from app.core.config import get_settings
from app.services.llm_config import resolve_llm_config


def build_agentscope_chat_model(
    *,
    db: Session,
    role: str = "lead_agent",
    stream: bool = True,
) -> OpenAIChatModel:
    """创建 AgentScope 2.0 OpenAIChatModel；不在这里注入任何业务 prompt。"""

    config = resolve_llm_config(get_settings(), role=role, db=db)
    credential = OpenAICredential(
        name=config.name,
        api_key=SecretStr(config.api_key or ""),
        base_url=config.base_url,
    )
    return OpenAIChatModel(
        credential,
        config.model,
        stream=stream,
        client_kwargs={"timeout": config.request_timeout_seconds},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py::test_agentscope_model_factory_builds_streaming_model -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/agents/agentscope_model.py datalogue-api/tests/test_agentscope_direct_query_chain.py
git commit -m "feat: add agentscope model factory"
```

---

## Task 2: 创建 AgenticLeadAgent 的 AgentScope Agent 工厂

**Files:**
- Create: `datalogue-api/app/agents/agentic_lead_agent/react_factory.py`
- Modify: `datalogue-api/app/agents/agentic_lead_agent/__init__.py`
- Test: `datalogue-api/tests/test_agentscope_direct_query_chain.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agentscope_direct_query_chain.py`:

```python
from app.agents.agentic_lead_agent.react_factory import AgenticLeadAgentFactory


def test_agentic_lead_agent_factory_creates_agentscope_agent(db_session):
    agent = AgenticLeadAgentFactory(db=db_session).create()

    assert isinstance(agent, Agent)
    assert agent.name == "agentic_lead_agent"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py::test_agentic_lead_agent_factory_creates_agentscope_agent -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.agentic_lead_agent.react_factory'`.

- [ ] **Step 3: Write minimal implementation**

Create `datalogue-api/app/agents/agentic_lead_agent/react_factory.py`:

```python
# ============================================================
# File Name   : react_factory.py
# Description:
#   AgenticLeadAgent 的 AgentScope 2.0 Agent 工厂。
#
# Responsibilities:
#   - 创建真正的 AgentScope AgenticLeadAgent。
#   - 用 prompt 约束它只做顶层路由和安全策略判断。
#   - 不向 Lead Agent 暴露 SQL、schema、raw rows 或 Dataset 原子工具。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from agentscope.agent import Agent
from agentscope.tool import Toolkit
from sqlalchemy.orm import Session

from app.agents.agentscope_model import build_agentscope_chat_model


AGENTIC_LEAD_AGENT_DIRECT_PROMPT = """
你是 Datalogue AgenticLeadAgent，负责最小直连链路的顶层路由。

当前阶段只启用 BI Agent。

你必须遵守：
- 如果用户问题是问数、指标、数据查询、统计分析，选择 BI Agent。
- 不生成 SQL。
- 不读取 schema。
- 不输出 raw rows。
- 不调用 Dataset 查询工具。
- 只输出简短 JSON：{"selected_agent":"bi_agent","task_type":"bi_query","reason":"..."}。
""".strip()


class AgenticLeadAgentFactory:
    """创建 AgentScope 2.0 AgenticLeadAgent；暂不注册工具，避免顶层越权执行查询。"""

    def __init__(self, *, db: Session) -> None:
        self.db = db

    def create(self) -> Agent:
        return Agent(
            name="agentic_lead_agent",
            system_prompt=AGENTIC_LEAD_AGENT_DIRECT_PROMPT,
            model=build_agentscope_chat_model(db=self.db, role="lead_agent", stream=False),
            toolkit=Toolkit(tools=[]),
        )
```

Modify `datalogue-api/app/agents/agentic_lead_agent/__init__.py`:

```python
from app.agents.agentic_lead_agent.shell import (
    AgenticLeadAgent,
    DatalogueAgenticShell,
    InMemoryAgenticShellWriter,
)
from app.agents.agentic_lead_agent.react_factory import AgenticLeadAgentFactory

__all__ = [
    "AgenticLeadAgent",
    "DatalogueAgenticShell",
    "InMemoryAgenticShellWriter",
    "AgenticLeadAgentFactory",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py::test_agentic_lead_agent_factory_creates_agentscope_agent -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/agents/agentic_lead_agent/react_factory.py datalogue-api/app/agents/agentic_lead_agent/__init__.py datalogue-api/tests/test_agentscope_direct_query_chain.py
git commit -m "feat: add agentscope agentic lead agent factory"
```

---

## Task 3: 创建 BI Agent 的 AgentScope Agent 工厂

**Files:**
- Create: `datalogue-api/app/agents/bi_agent/react_factory.py`
- Modify: `datalogue-api/app/agents/bi_agent/__init__.py`
- Test: `datalogue-api/tests/test_agentscope_direct_query_chain.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agentscope_direct_query_chain.py`:

```python
from app.agents.bi_agent.react_factory import BIAgentFactory
from app.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge
from app.bi.toolkit import build_bi_atomic_toolkit


def test_bi_agent_factory_creates_agentscope_agent_with_dataset_tools(db_session):
    toolkit = build_bi_atomic_toolkit(db_session, query_executor=lambda sql: [])
    bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
    session = bridge.start_session(dataset_id=12, question="统计合同总金额")

    agent = BIAgentFactory(db=db_session).create(session=session)

    assert isinstance(agent, Agent)
    assert agent.name == "bi_agent"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py::test_bi_agent_factory_creates_agentscope_agent_with_dataset_tools -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.bi_agent.react_factory'`.

- [ ] **Step 3: Write minimal implementation**

Create `datalogue-api/app/agents/bi_agent/react_factory.py`:

```python
# ============================================================
# File Name   : react_factory.py
# Description:
#   BI Agent 的 AgentScope 2.0 Agent 工厂。
#
# Responsibilities:
#   - 创建真正的 AgentScope BI Agent。
#   - 直接注册 Dataset 工具链 tools，不经过 DatasetQuerySkill。
#   - 用 prompt 约束问数工具调用顺序和安全输出。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from agentscope.agent import Agent
from agentscope.tool import Toolkit
from sqlalchemy.orm import Session

from app.agents.agentscope_model import build_agentscope_chat_model
from app.bi.skill.runtime_bridge import (
    AgentScopeDatasetRuntimeSession,
    build_dataset_agentscope_tools,
)


BI_AGENT_DIRECT_QUERY_PROMPT = """
你是 Datalogue BI Agent，负责执行最小直连问数链路。

你必须按顺序使用已注册工具：
1. get_dataset_status
2. list_candidate_assets
3. compile_dsl_to_sql
4. execute_compiled_query
5. create_query_artifact
6. get_artifact_summary

如果 execute_compiled_query 返回 FIELD_NOT_FOUND，并且工具链允许 repair，则调用 repair_dsl 后再次 execute_compiled_query。

你必须遵守：
- 不向最终回答输出 SQL。
- 不向最终回答输出 schema。
- 不向最终回答输出 raw rows。
- 不向最终回答输出 compiled_query_ref。
- 最终只总结业务结果，并引用 artifact_ref、checkpoint_ref、row_count、column_count。
""".strip()


class BIAgentFactory:
    """创建 AgentScope 2.0 BI Agent；Dataset tools 直接挂在 BI Agent 上。"""

    def __init__(self, *, db: Session) -> None:
        self.db = db

    def create(self, *, session: AgentScopeDatasetRuntimeSession) -> Agent:
        tools = build_dataset_agentscope_tools(session=session, agent_name="bi_agent")
        return Agent(
            name="bi_agent",
            system_prompt=BI_AGENT_DIRECT_QUERY_PROMPT,
            model=build_agentscope_chat_model(db=self.db, role="lead_agent", stream=True),
            toolkit=Toolkit(tools=tools),
        )
```

Modify `datalogue-api/app/agents/bi_agent/__init__.py`:

```python
from app.agents.bi_agent.agent import BIAgent
from app.agents.bi_agent.capabilities import BIAgentCapabilityCatalog
from app.agents.bi_agent.confirmation_service import BIAgentConfirmationService
from app.agents.bi_agent.handoff_service import BIAgentHandoffService
from app.agents.bi_agent.run_service import BIAgentRunService
from app.agents.bi_agent.react_factory import BIAgentFactory

__all__ = [
    "BIAgent",
    "BIAgentCapabilityCatalog",
    "BIAgentConfirmationService",
    "BIAgentHandoffService",
    "BIAgentRunService",
    "BIAgentFactory",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py::test_bi_agent_factory_creates_agentscope_agent_with_dataset_tools -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/agents/bi_agent/react_factory.py datalogue-api/app/agents/bi_agent/__init__.py datalogue-api/tests/test_agentscope_direct_query_chain.py
git commit -m "feat: add agentscope bi agent factory"
```

---

## Task 4: 实现直连 runner

**Files:**
- Create: `datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py`
- Modify: `datalogue-api/app/agents/agentic_lead_agent/__init__.py`
- Test: `datalogue-api/tests/test_agentscope_direct_query_chain.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agentscope_direct_query_chain.py`:

```python
import pytest

from app.agents.agentic_lead_agent.direct_query_runner import AgenticDirectQueryRunner


class FakeLeadAgent:
    name = "agentic_lead_agent"

    async def reply(self, msg):
        return {"selected_agent": "bi_agent", "task_type": "bi_query"}


class FakeBIAgent:
    name = "bi_agent"


class FakeLeadFactory:
    def __init__(self, *, db):
        self.db = db

    def create(self):
        return FakeLeadAgent()


class FakeBIFactory:
    def __init__(self, *, db):
        self.db = db

    def create(self, *, session):
        return FakeBIAgent()


class FakeBridge:
    def start_session(self, **kwargs):
        return type(
            "FakeSession",
            (),
            {
                "artifact_ref": "artifact:direct",
                "checkpoint_ref": "checkpoint:direct",
                "tool_results": [],
                **kwargs,
            },
        )()

    async def run_reply_stream(self, agent, *, msg, session):
        session.artifact_ref = "artifact:direct"
        session.checkpoint_ref = "checkpoint:direct"
        session.tool_results = [
            {"name": "execute_compiled_query", "row_count": 1, "column_count": 2},
            {"name": "get_artifact_summary", "summary": "合同总金额为 100 万元"},
        ]
        return []


@pytest.mark.asyncio
async def test_direct_query_runner_links_lead_agent_to_bi_agent_without_task_or_handoff(db_session):
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=FakeLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: FakeBridge(),
    )

    result = await runner.run(question="统计合同总金额", dataset_id=12)

    assert result["status"] == "completed"
    assert result["selected_agent"] == "bi_agent"
    assert result["artifact_ref"] == "artifact:direct"
    assert result["checkpoint_ref"] == "checkpoint:direct"
    assert result["row_count"] == 1
    assert result["column_count"] == 2
    assert "handoff_id" not in result
    assert "task_id" not in result
    assert "message_id" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py::test_direct_query_runner_links_lead_agent_to_bi_agent_without_task_or_handoff -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.agentic_lead_agent.direct_query_runner'`.

- [ ] **Step 3: Write minimal implementation**

Create `datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py`:

```python
# ============================================================
# File Name   : direct_query_runner.py
# Description:
#   AgenticLeadAgent 到 BI Agent 的最小直连问数 runner。
#
# Responsibilities:
#   - 顺序驱动 AgentScope AgenticLeadAgent 与 AgentScope BI Agent。
#   - 直接进入 Dataset 工具链，不创建 AgenticShellTask、Session、Message 或 Handoff。
#   - 返回安全业务结果与 artifact/checkpoint 引用。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentscope.message import UserMsg
from sqlalchemy.orm import Session

from app.agents.agentic_lead_agent.react_factory import AgenticLeadAgentFactory
from app.agents.bi_agent.react_factory import BIAgentFactory
from app.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge
from app.bi.toolkit import build_bi_atomic_toolkit
from app.middlewares.lifecycle import log_lifecycle, log_raw


class AgenticDirectQueryRunner:
    """最小直连链路：Lead Agent 只路由，BI Agent 直接调用 Dataset 工具链。"""

    def __init__(
        self,
        *,
        db: Session,
        lead_agent_factory: type[AgenticLeadAgentFactory] = AgenticLeadAgentFactory,
        bi_agent_factory: type[BIAgentFactory] = BIAgentFactory,
        bridge_factory: Callable[[Session], Any] | None = None,
    ) -> None:
        self.db = db
        self.lead_agent_factory = lead_agent_factory
        self.bi_agent_factory = bi_agent_factory
        self.bridge_factory = bridge_factory or self._default_bridge_factory

    async def run(
        self,
        *,
        question: str,
        dataset_id: int,
        conversation_id: int | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        log_lifecycle(
            "agentic_direct_query.started",
            dataset_id=dataset_id,
            question_length=len(question or ""),
            trace_id=trace_id,
        )
        log_raw(
            "agentic_direct_query.raw.input",
            question=question,
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )

        lead_agent = self.lead_agent_factory(db=self.db).create()
        await lead_agent.reply(
            UserMsg(
                name="user",
                content=f"请判断该问题应交给哪个 Agent：{question}",
            )
        )

        bridge = self.bridge_factory(self.db)
        session = bridge.start_session(
            dataset_id=dataset_id,
            question=question,
            agent_name="bi_agent",
            conversation_id=conversation_id,
            trace_id=trace_id,
        )
        bi_agent = self.bi_agent_factory(db=self.db).create(session=session)
        await bridge.run_reply_stream(
            bi_agent,
            msg=UserMsg(name="user", content=question),
            session=session,
        )

        result = self._result_from_session(session=session)
        log_lifecycle(
            "agentic_direct_query.completed",
            dataset_id=dataset_id,
            trace_id=trace_id,
            status=result["status"],
            selected_agent=result["selected_agent"],
            has_artifact=bool(result.get("artifact_ref")),
            row_count=result.get("row_count"),
            column_count=result.get("column_count"),
        )
        log_raw("agentic_direct_query.raw.output", result=result)
        return result

    @staticmethod
    def _default_bridge_factory(db: Session) -> AgentScopeDatasetRuntimeBridge:
        return AgentScopeDatasetRuntimeBridge(toolkit=build_bi_atomic_toolkit(db))

    @staticmethod
    def _result_from_session(*, session: Any) -> dict[str, Any]:
        row_count = None
        column_count = None
        summary = "BI Agent 查询已完成。"
        for item in getattr(session, "tool_results", []) or []:
            if item.get("row_count") is not None:
                row_count = item.get("row_count")
            if item.get("column_count") is not None:
                column_count = item.get("column_count")
            if item.get("summary"):
                summary = str(item["summary"])

        artifact_ref = getattr(session, "artifact_ref", None)
        checkpoint_ref = getattr(session, "checkpoint_ref", None)
        return {
            "status": "completed" if artifact_ref else "blocked",
            "selected_agent": "bi_agent",
            "summary": summary,
            "artifact_ref": artifact_ref,
            "checkpoint_ref": checkpoint_ref,
            "row_count": row_count,
            "column_count": column_count,
        }
```

Modify `datalogue-api/app/agents/agentic_lead_agent/__init__.py`:

```python
from app.agents.agentic_lead_agent.direct_query_runner import AgenticDirectQueryRunner
from app.agents.agentic_lead_agent.react_factory import AgenticLeadAgentFactory
from app.agents.agentic_lead_agent.shell import (
    AgenticLeadAgent,
    DatalogueAgenticShell,
    InMemoryAgenticShellWriter,
)

__all__ = [
    "AgenticLeadAgent",
    "DatalogueAgenticShell",
    "InMemoryAgenticShellWriter",
    "AgenticLeadAgentFactory",
    "AgenticDirectQueryRunner",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py::test_direct_query_runner_links_lead_agent_to_bi_agent_without_task_or_handoff -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py datalogue-api/app/agents/agentic_lead_agent/__init__.py datalogue-api/tests/test_agentscope_direct_query_chain.py
git commit -m "feat: add direct agentscope query runner"
```

---

## Task 5: 增加直连 API

**Files:**
- Create: `datalogue-api/app/schemas/agentic_direct_query.py`
- Create: `datalogue-api/app/api/agentic_lead_agent.py`
- Modify: `datalogue-api/app/api/__init__.py`
- Test: `datalogue-api/tests/test_agentscope_direct_query_chain.py`

- [ ] **Step 1: Write the failing API test**

Append to `tests/test_agentscope_direct_query_chain.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_agentic_lead_agent_direct_query_api_returns_safe_result(monkeypatch):
    class FakeRunner:
        def __init__(self, *, db):
            self.db = db

        async def run(self, **kwargs):
            return {
                "status": "completed",
                "selected_agent": "bi_agent",
                "summary": "合同总金额为 100 万元",
                "artifact_ref": "artifact:direct",
                "checkpoint_ref": "checkpoint:direct",
                "row_count": 1,
                "column_count": 2,
            }

    monkeypatch.setattr(
        "app.api.agentic_lead_agent.AgenticDirectQueryRunner",
        FakeRunner,
    )
    client = TestClient(app)

    response = client.post(
        "/api/agentic-lead-agent/direct-query",
        json={"question": "统计合同总金额", "dataset_id": 12},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "selected_agent": "bi_agent",
        "summary": "合同总金额为 100 万元",
        "artifact_ref": "artifact:direct",
        "checkpoint_ref": "checkpoint:direct",
        "row_count": 1,
        "column_count": 2,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py::test_agentic_lead_agent_direct_query_api_returns_safe_result -q
```

Expected: FAIL with `AttributeError` or HTTP 404 because `app.api.agentic_lead_agent` is not registered.

- [ ] **Step 3: Create request/response schemas**

Create `datalogue-api/app/schemas/agentic_direct_query.py`:

```python
# ============================================================
# File Name   : agentic_direct_query.py
# Description:
#   AgenticLeadAgent 直连问数 API DTO。
#
# Responsibilities:
#   - 定义最小直连链路的请求和安全响应。
#   - 避免 API 返回 SQL、schema、raw rows、compiled_query_ref 或 handoff/task/message 内部 ID。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AgenticDirectQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    dataset_id: int = Field(gt=0)
    conversation_id: int | None = None
    trace_id: str | None = None


class AgenticDirectQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    selected_agent: str
    summary: str
    artifact_ref: str | None = None
    checkpoint_ref: str | None = None
    row_count: int | None = None
    column_count: int | None = None
```

- [ ] **Step 4: Create API router**

Create `datalogue-api/app/api/agentic_lead_agent.py`:

```python
# ============================================================
# File Name   : agentic_lead_agent.py
# Description:
#   AgenticLeadAgent 最小直连问数 API。
#
# Responsibilities:
#   - 暴露 AgenticLeadAgent -> BI Agent -> Dataset 工具链直连入口。
#   - 不创建 AgenticShellTask、Session、Message 或 Handoff。
#   - 只返回安全业务结果和 artifact/checkpoint 引用。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.agentic_lead_agent import AgenticDirectQueryRunner
from app.db.session import get_db
from app.schemas.agentic_direct_query import (
    AgenticDirectQueryRequest,
    AgenticDirectQueryResponse,
)

router = APIRouter()


@router.post("/direct-query", response_model=AgenticDirectQueryResponse)
async def direct_query(
    request: AgenticDirectQueryRequest,
    db: Session = Depends(get_db),
) -> AgenticDirectQueryResponse:
    result = await AgenticDirectQueryRunner(db=db).run(
        question=request.question,
        dataset_id=request.dataset_id,
        conversation_id=request.conversation_id,
        trace_id=request.trace_id,
    )
    return AgenticDirectQueryResponse(**result)
```

- [ ] **Step 5: Register router**

Modify `datalogue-api/app/api/__init__.py`:

```python
from app.api import (
    agentic_lead_agent,
    agentic_shell,
    artifacts,
    bi_agent,
    chat,
    conversation,
    datasource,
    dataset,
    internal_subagent,
    llm,
    messages,
    workbench,
)

router.include_router(agentic_lead_agent.router, prefix="/agentic-lead-agent", tags=["AgenticLeadAgent"])
```

- [ ] **Step 6: Run test to verify it passes**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py::test_agentic_lead_agent_direct_query_api_returns_safe_result -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add datalogue-api/app/schemas/agentic_direct_query.py datalogue-api/app/api/agentic_lead_agent.py datalogue-api/app/api/__init__.py datalogue-api/tests/test_agentscope_direct_query_chain.py
git commit -m "feat: expose direct agentic lead query api"
```

---

## Task 6: 增加安全边界回归测试

**Files:**
- Modify: `datalogue-api/tests/test_agentscope_direct_query_chain.py`

- [ ] **Step 1: Write failing security test**

Append to `tests/test_agentscope_direct_query_chain.py`:

```python
def test_direct_query_response_does_not_expose_internal_execution_payload():
    response = {
        "status": "completed",
        "selected_agent": "bi_agent",
        "summary": "完成",
        "artifact_ref": "artifact:direct",
        "checkpoint_ref": "checkpoint:direct",
        "row_count": 1,
        "column_count": 2,
    }

    dumped = str(response).lower()

    for forbidden in (
        "select ",
        " from ",
        "schema_context",
        "raw_rows",
        "compiled_query_ref",
        "handoff_id",
        "task_id",
        "message_id",
        "session_id",
    ):
        assert forbidden not in dumped
```

- [ ] **Step 2: Run test to verify it passes**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py::test_direct_query_response_does_not_expose_internal_execution_payload -q
```

Expected: PASS. This test documents the response contract and should stay simple.

- [ ] **Step 3: Run full direct chain test file**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py -q
```

Expected: all tests in this file PASS.

- [ ] **Step 4: Commit**

```bash
git add datalogue-api/tests/test_agentscope_direct_query_chain.py
git commit -m "test: lock direct query response boundary"
```

---

## Task 7: 验证真实链路与现有回归

**Files:**
- Modify: `.codex/project-memory.md`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_direct_query_chain.py tests/test_agentscope_dataset_runtime_bridge.py tests/test_agentic_shell_contract.py tests/test_agentic_architecture_p4_bi_agent_legacy_cleanup.py -q
```

Expected: PASS, while only pytest warnings from existing dependencies may remain.

- [ ] **Step 2: Run compile and whitespace checks**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m compileall app -q
cd /Users/yangkai/code_place/study/python/Datalogue
git diff --check
```

Expected: both commands exit 0.

- [ ] **Step 3: Optional local smoke with raw logs**

Run backend:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
AGENT_DEBUG_RAW_LOGS=true python3 -m uvicorn app.main:app --reload --port 8000
```

Call API:

```bash
curl -s http://localhost:8000/api/agentic-lead-agent/direct-query \
  -H 'Content-Type: application/json' \
  -d '{"question":"统计合同总金额","dataset_id":12}' | python3 -m json.tool
```

Expected response shape:

```json
{
  "status": "completed",
  "selected_agent": "bi_agent",
  "summary": "BI Agent 查询已完成。",
  "artifact_ref": "artifact:...",
  "checkpoint_ref": null,
  "row_count": 1,
  "column_count": 2
}
```

- [ ] **Step 4: Update project memory**

Append to `.codex/project-memory.md`:

```markdown
### 2026-07-02 HH:mm · AgentScope 直连问数最小链路

- 涉及文件：`datalogue-api/app/agents/agentscope_model.py`、`datalogue-api/app/agents/agentic_lead_agent/react_factory.py`、`datalogue-api/app/agents/bi_agent/react_factory.py`、`datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py`、`datalogue-api/app/api/agentic_lead_agent.py`、`datalogue-api/app/schemas/agentic_direct_query.py`、`datalogue-api/tests/test_agentscope_direct_query_chain.py`
- 关键改动：新增最小直连链路 `AgenticLeadAgent -> BI Agent -> Dataset 工具链`，Lead/BI 均由 AgentScope 2.0 `Agent` 创建；直连 API 不创建 AgenticShellTask、Session/Message、AgentScopeRef 或 BI handoff。
- 验证方式：记录实际执行的 pytest、compileall、git diff --check 和本地 smoke 结果。
- 残留风险：该入口尚未替换主页面和 `/agentic-shell/tasks/stream`；Report/Python/Audit、Workbench timeline、session/message/ref、handoff 和前端集成后续分阶段补。
```

- [ ] **Step 5: Commit**

```bash
git add .codex/project-memory.md
git commit -m "docs: record direct agentscope query chain"
```

---

## Self-Review

**Spec coverage:**
- `AgenticLeadAgent -> BI Agent -> 问数链路`：Task 2、Task 3、Task 4。
- `AgenticLeadAgent 和 BI Agent 都用 AgentScope 2.0 Agent`：Task 2、Task 3 的 `isinstance(agent, Agent)` 测试。
- `可以不用 Skill，直接在 Prompt 里写`：Task 3 直接在 `BI_AGENT_DIRECT_QUERY_PROMPT` 写工具顺序，并直接注册 tools，不使用 `DatasetQuerySkill`。
- `先不要 AgenticShellTask、Session、Message、Handoff`：Task 4 和 Task 5 的 runner/API 不创建这些对象，Task 4 测试断言 response 不含 `task_id/message_id/handoff_id`。
- `入口到整个链路查询打通`：Task 5 直连 API，Task 7 本地 smoke。

**Placeholder scan:** 本计划没有使用待补实现占位词；每个新增文件都有完整代码骨架和验证命令。

**Type consistency:**
- `AgenticLeadAgentFactory.create()` 返回 AgentScope `Agent`。
- `BIAgentFactory.create(session=...)` 返回 AgentScope `Agent`。
- `AgenticDirectQueryRunner.run(...)` 返回 `dict[str, Any]`，API 层用 `AgenticDirectQueryResponse` 收敛输出。
- API 路径固定为 `/api/agentic-lead-agent/direct-query`。

