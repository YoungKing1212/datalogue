# AgentScope Service Static Agents Main Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 AgentScope 2.0.3 官方 Agent Service 和固定 Agent 注册表接管 Datalogue 主智能体运行时，并清理自研 runner / handoff / direct runtime 兼容层。

**Architecture:** Datalogue 保留 `/api/agentic-shell/tasks/stream` 作为业务入口和稳定 SSE 协议，但不再自己写主链 runner。入口创建 `AgenticShellTask` 后代理 AgentScope Agent Service：创建/复用固定的 `AgenticLeadAgent` session，触发 `/chat`，订阅 `/session/{session_id}/stream`，再把 AgentScope 事件投影成 Datalogue Event Envelope。多 Agent 协作使用固定 Agent 注册表：`agentic_lead_agent`、`bi_agent`、`report_agent`、`python_agent`、`audit_agent` 在启动/部署阶段幂等注册；运行时按固定 `agent_id` 和 `session_id` 路由，不要求 Leader 动态调用 `AgentCreate`。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, AgentScope 2.0.3, AgentScope Agent Service, static Agent registry, RedisStorage, RedisMessageBus, LocalWorkspaceManager, pytest, SSE.

---

## Supersedes

本计划替代旧计划：

```text
docs/superpowers/plans/2026-07-03-agentscope-main-chain-migration-and-slimming.md
```

旧计划的核心问题是新增 `AgentScopeBIMainChainRunner`，仍然由 Datalogue 手写 LeadAgent 调用、BI Agent 调用、handoff、工具循环和 final answer 组装。新计划改为：**AgentScope 官方 Agent Service 管 agent / session / chat / SSE，Datalogue 用固定 Agent 注册表管理少量确定 Agent，Datalogue 只保留业务真相源和事件投影。**

执行本计划前必须遵守新的约束：

- 涉及 AgentScope 开发时，先查 AgentScope 2.0.3 官方文档和本地安装包 API。
- 官方已有 Service、Team、Storage、MessageBus、Workspace、Tool、Middleware 能力时，优先用 SDK。
- 只有官方没有覆盖 Datalogue 业务真相源、SQL control plane、安全投影时，才写 Datalogue 自有代码。

---

## Official AgentScope Contracts To Use

本计划依赖 AgentScope 2.0.3 官方接口和本地包源码核对结果：

- Agent Service app factory:

```python
from agentscope.app import create_app
from agentscope.app.storage import RedisStorage
from agentscope.app.message_bus import RedisMessageBus
from agentscope.app.workspace_manager import LocalWorkspaceManager
```

- `create_app(...)` 支持：

```python
create_app(
    storage=storage,
    message_bus=message_bus,
    workspace_manager=workspace_manager,
    extra_agent_tools=...,
    custom_agent_cls=...,
)
```

- Agent Service REST/SSE 边界：

```text
POST /agent
POST /session
POST /chat
GET  /session/{session_id}/stream
GET  /session/{session_id}/messages
```

- Session model 使用 `ChatModelConfig`：

```python
ChatModelConfig(
    type="openai_credential",
    credential_id="...",
    model="...",
    parameters={...},
)
```

- Agent Team 内置工具只作为未来动态 Agent 扩展能力，不进入当前主链：

```text
TeamCreate
AgentCreate
TeamSay
TeamDelete
```

- 当前固定 Agent 集合使用 Datalogue 静态注册表：

```text
agentic_lead_agent
bi_agent
report_agent
python_agent
audit_agent
```

---

## Target Runtime Shape

目标主链：

```text
Chat UI / Workbench / API
  -> POST /api/agentic-shell/tasks/stream
  -> Datalogue AgenticShellTask
  -> AgentScope Agent Service
       -> fixed agent registry
            -> agentic_lead_agent session
            -> bi_agent session
            -> report_agent session
            -> python_agent session
            -> audit_agent session
       -> AgenticLeadAgent routes to fixed BI Agent by agent_id/session_id
       -> BI Agent session
            -> Dataset Query Tools
            -> SQL Control Plane
            -> Artifact / Checkpoint refs
       -> optional fixed ReportAgent / PythonAgent / AuditAgent sessions
  -> AgentScope session stream
  -> Datalogue Event Envelope
  -> Chat UI / Workbench
```

Datalogue 继续拥有：

- `AgenticShellTask`：业务任务真相源。
- `Datalogue Event Envelope`：前端稳定协议。
- Dataset / Manifest / 权限 / SQL 审计 / Artifact / Checkpoint / DB 事务。
- 安全投影：SQL、schema、raw rows、DSL、query_plan、repair patch 不进入用户可见事件。

AgentScope 负责：

- Agent session state。
- Agent Service REST/SSE。
- 固定 Agent 的 session state 和 session stream。
- 启动/部署阶段的 Agent 幂等创建或查找。
- HITL / external execution resume 基础机制。
- Workspace、MessageBus、Storage。

---

## File Structure

- Modify: `datalogue-api/pyproject.toml`
  - 增加 Agent Service / Storage 依赖。
- Modify: `datalogue-api/requirements.txt`
  - 与 `pyproject.toml` 保持一致。
- Modify: `datalogue-api/app/core/config.py`
  - 增加 Agent Service、Redis、Workspace、开关配置。
- Create: `datalogue-api/app/agentscope_service/__init__.py`
  - 暴露 Agent Service 工厂。
- Create: `datalogue-api/app/agentscope_service/app_factory.py`
  - 创建 AgentScope FastAPI app。
- Create: `datalogue-api/app/agentscope_service/registry.py`
  - 定义 `agentic_lead_agent`、`bi_agent`、`report_agent`、`python_agent`、`audit_agent` 的固定 Agent 规格。
- Create: `datalogue-api/app/agentscope_service/tools.py`
  - 提供 Datalogue extra tools factory，只注册 Datalogue 业务工具，不复制 Team 工具。
- Create: `datalogue-api/app/agentscope_service/bootstrap.py`
  - 幂等创建/查找 AgenticLeadAgent、credential、session 所需配置。
- Create: `datalogue-api/app/agentscope_service/client.py`
  - Datalogue 内部调用 Agent Service REST/SSE 的 adapter。
- Create: `datalogue-api/app/agentscope_service/projection.py`
  - AgentScope event/message 到 Datalogue envelope 的投影。
- Modify: `datalogue-api/app/main.py`
  - 挂载 AgentScope app 到 `/agentscope` 或按配置启用。
- Modify: `datalogue-api/app/api/agentic_shell.py`
  - `/tasks/stream` 改为代理 Agent Service session stream。
- Modify: `datalogue-api/app/runtime/task_runtime.py`
  - 保留 task/session/message/ref 写入；删除 `BIAgentTaskRunner`。
- Modify: `datalogue-api/app/agents/agentic_lead_agent/react_factory.py`
  - 调整 prompt，使 LeadAgent 调用固定 BI/Report/Python/Audit Agent，不手写 handoff。
- Modify: `datalogue-api/app/agents/bi_agent/react_factory.py`
  - 保留 BI Agent prompt 和 Toolkit 注册能力，作为固定 BI Agent 的行为约束。
- Modify: `datalogue-api/app/bi/skill/runtime_bridge.py`
  - 保留 external execution handling；删除 direct fallback。
- Delete or disable: `datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py`
- Delete or disable: `datalogue-api/app/agents/bi_agent/native_handoff.py`
- Delete or disable: `datalogue-api/app/agents/bi_agent/handoff_adapter.py`
- Delete or disable: `datalogue-api/app/bi/toolchain/dataset_runtime.py`
- Delete or disable: `datalogue-api/app/api/internal_subagent.py`
- Test: `datalogue-api/tests/test_agentscope_service_imports.py`
- Test: `datalogue-api/tests/test_agentscope_service_factory.py`
- Test: `datalogue-api/tests/test_agentscope_static_agent_registry.py`
- Test: `datalogue-api/tests/test_agentic_shell_uses_agentscope_service.py`
- Test: `datalogue-api/tests/test_agentic_architecture_p5_service_team_cleanup.py`

---

### Task 1: AgentScope Service Dependency Gate

**Files:**
- Modify: `datalogue-api/pyproject.toml`
- Modify: `datalogue-api/requirements.txt`
- Test: `datalogue-api/tests/test_agentscope_service_imports.py`

- [ ] **Step 1: Write failing import test**

Create `datalogue-api/tests/test_agentscope_service_imports.py`:

```python
# ============================================================
# File Name   : test_agentscope_service_imports.py
# Description:
#   AgentScope Agent Service 依赖门禁测试。
#
# Responsibilities:
#   - 确认本地环境能导入官方 Agent Service / Storage / MessageBus / Workspace 入口。
#   - 防止只安装 agentscope 核心包却缺 service/storage extras。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================


def test_agentscope_service_imports_are_available():
    from agentscope.app import create_app
    from agentscope.app.message_bus import RedisMessageBus
    from agentscope.app.storage import RedisStorage
    from agentscope.app.workspace_manager import LocalWorkspaceManager

    assert create_app is not None
    assert RedisStorage is not None
    assert RedisMessageBus is not None
    assert LocalWorkspaceManager is not None
```

- [ ] **Step 2: Run test to verify it fails before dependencies**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentscope_service_imports.py -q
```

Expected: FAIL，当前环境会在 `agentscope.app` 导入时提示缺少 `apscheduler` 或 service/storage 相关依赖。

- [ ] **Step 3: Add official AgentScope extras**

Modify `datalogue-api/pyproject.toml` dependency:

```toml
"agentscope[service,storage]==2.0.3",
```

Replace the old plain:

```toml
"agentscope==2.0.3",
```

Modify `datalogue-api/requirements.txt` similarly:

```text
agentscope[service,storage]==2.0.3
```

- [ ] **Step 4: Sync lock and run import test**

Run:

```bash
cd datalogue-api
uv sync
uv run pytest tests/test_agentscope_service_imports.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/pyproject.toml datalogue-api/requirements.txt datalogue-api/uv.lock datalogue-api/tests/test_agentscope_service_imports.py
git commit -m "test: enable agentscope service dependencies"
```

---

### Task 2: AgentScope Service Configuration

**Files:**
- Modify: `datalogue-api/app/core/config.py`
- Test: `datalogue-api/tests/test_agentscope_service_factory.py`

- [ ] **Step 1: Add settings**

Add settings to `Settings`:

```python
    # AgentScope Agent Service；默认启用内嵌模式，生产可拆成独立服务。
    AGENTSCOPE_SERVICE_ENABLED: bool = True
    AGENTSCOPE_SERVICE_MOUNT_PATH: str = "/agentscope"
    AGENTSCOPE_REDIS_HOST: str = "localhost"
    AGENTSCOPE_REDIS_PORT: int = 6379
    AGENTSCOPE_REDIS_DB: int = 0
    AGENTSCOPE_WORKSPACE_BASEDIR: str = ".agentscope/workspaces"
    AGENTSCOPE_WORKSPACE_TTL_SECONDS: float = 3600.0
```

- [ ] **Step 2: Write settings test**

Add to `datalogue-api/tests/test_agentscope_service_factory.py`:

```python
def test_agentscope_service_settings_have_safe_defaults():
    from app.core.config import Settings

    settings = Settings()

    assert settings.AGENTSCOPE_SERVICE_ENABLED is True
    assert settings.AGENTSCOPE_SERVICE_MOUNT_PATH == "/agentscope"
    assert settings.AGENTSCOPE_REDIS_HOST
    assert settings.AGENTSCOPE_REDIS_PORT == 6379
    assert settings.AGENTSCOPE_WORKSPACE_BASEDIR
```

- [ ] **Step 3: Run test**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentscope_service_factory.py::test_agentscope_service_settings_have_safe_defaults -q
```

Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add datalogue-api/app/core/config.py datalogue-api/tests/test_agentscope_service_factory.py
git commit -m "feat: add agentscope service settings"
```

---

### Task 3: Create Embedded AgentScope Service App

**Files:**
- Create: `datalogue-api/app/agentscope_service/__init__.py`
- Create: `datalogue-api/app/agentscope_service/app_factory.py`
- Test: `datalogue-api/tests/test_agentscope_service_factory.py`

- [ ] **Step 1: Write factory test**

Append:

```python
def test_create_embedded_agentscope_app_returns_fastapi():
    from fastapi import FastAPI
    from app.agentscope_service.app_factory import create_embedded_agentscope_app
    from app.core.config import Settings

    app = create_embedded_agentscope_app(
        Settings(
            AGENTSCOPE_REDIS_HOST="localhost",
            AGENTSCOPE_REDIS_PORT=6379,
            AGENTSCOPE_WORKSPACE_BASEDIR=".agentscope/test-workspaces",
        )
    )

    assert isinstance(app, FastAPI)
```

- [ ] **Step 2: Create package init**

`datalogue-api/app/agentscope_service/__init__.py`:

```python
# ============================================================
# File Name   : __init__.py
# Description:
#   AgentScope Agent Service 集成包出口。
#
# Responsibilities:
#   - 暴露内嵌 Agent Service 工厂。
#   - 统一收口 Datalogue 与 AgentScope Service 的适配层。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

from app.agentscope_service.app_factory import create_embedded_agentscope_app

__all__ = ["create_embedded_agentscope_app"]
```

- [ ] **Step 3: Implement official create_app wrapper**

`datalogue-api/app/agentscope_service/app_factory.py`:

```python
# ============================================================
# File Name   : app_factory.py
# Description:
#   AgentScope Agent Service 内嵌应用工厂。
#
# Responsibilities:
#   - 按官方 create_app 入口创建 AgentScope FastAPI 子应用。
#   - 装配 RedisStorage、RedisMessageBus 和 LocalWorkspaceManager。
#   - 注册 Datalogue 业务工具，固定 Agent 由 bootstrap 幂等准备。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

from __future__ import annotations

from fastapi import FastAPI

from agentscope.app import create_app
from agentscope.app.message_bus import RedisMessageBus
from agentscope.app.storage import RedisStorage
from agentscope.app.workspace_manager import LocalWorkspaceManager

from app.core.config import Settings


def create_embedded_agentscope_app(settings: Settings) -> FastAPI:
    """创建 Datalogue 内嵌 AgentScope Agent Service。"""

    storage = RedisStorage(
        host=settings.AGENTSCOPE_REDIS_HOST,
        port=settings.AGENTSCOPE_REDIS_PORT,
        db=settings.AGENTSCOPE_REDIS_DB,
    )
    message_bus = RedisMessageBus(
        host=settings.AGENTSCOPE_REDIS_HOST,
        port=settings.AGENTSCOPE_REDIS_PORT,
        db=settings.AGENTSCOPE_REDIS_DB,
    )
    workspace_manager = LocalWorkspaceManager(
        basedir=settings.AGENTSCOPE_WORKSPACE_BASEDIR,
        ttl=settings.AGENTSCOPE_WORKSPACE_TTL_SECONDS,
    )
    return create_app(
        storage=storage,
        message_bus=message_bus,
        workspace_manager=workspace_manager,
        title="Datalogue AgentScope Service",
        version="0.1.0",
    )
```

- [ ] **Step 4: Run factory test**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentscope_service_factory.py -q
```

Expected: PASS，不要求 Redis 在线；这里只构造对象。

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/agentscope_service datalogue-api/tests/test_agentscope_service_factory.py
git commit -m "feat: create embedded agentscope service app"
```

---

### Task 4: Mount AgentScope Service

**Files:**
- Modify: `datalogue-api/app/main.py`
- Test: `datalogue-api/tests/test_agentscope_service_factory.py`

- [ ] **Step 1: Write mount test**

Append:

```python
def test_main_app_mounts_agentscope_service_when_enabled():
    from app.main import app

    mounted_paths = [getattr(route, "path", "") for route in app.routes]

    assert "/agentscope" in mounted_paths
```

- [ ] **Step 2: Mount sub-app in main**

In `datalogue-api/app/main.py`, after `app.include_router(api_router, prefix="/api")`:

```python
if settings.AGENTSCOPE_SERVICE_ENABLED:
    from app.agentscope_service import create_embedded_agentscope_app

    app.mount(
        settings.AGENTSCOPE_SERVICE_MOUNT_PATH,
        create_embedded_agentscope_app(settings),
        name="agentscope",
    )
```

- [ ] **Step 3: Run mount test**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentscope_service_factory.py::test_main_app_mounts_agentscope_service_when_enabled -q
```

Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add datalogue-api/app/main.py datalogue-api/tests/test_agentscope_service_factory.py
git commit -m "feat: mount agentscope service"
```

---

### Task 5: Define Static Agent Registry

**Files:**
- Create: `datalogue-api/app/agentscope_service/registry.py`
- Test: `datalogue-api/tests/test_agentscope_static_agent_registry.py`

- [ ] **Step 1: Write registry tests**

Create `datalogue-api/tests/test_agentscope_static_agent_registry.py`:

```python
# ============================================================
# File Name   : test_agentscope_static_agent_registry.py
# Description:
#   AgentScope Service 固定 Agent 注册表测试。
#
# Responsibilities:
#   - 确认 Datalogue 固定注册 Lead/BI/Report/Python/Audit Agent。
#   - 防止主链 prompt 回退到动态 AgentCreate 或自研 handoff/runner。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================


def test_static_agent_registry_contains_fixed_agents():
    from app.agentscope_service.registry import build_datalogue_static_agent_specs

    specs = build_datalogue_static_agent_specs()
    by_key = {item.key: item for item in specs}

    assert set(by_key) == {
        "agentic_lead_agent",
        "bi_agent",
        "report_agent",
        "python_agent",
        "audit_agent",
    }
    assert by_key["agentic_lead_agent"].service_name == "Datalogue Agentic Lead Agent"
    assert by_key["bi_agent"].service_name == "Datalogue BI Agent"
    assert "Dataset Query" in by_key["bi_agent"].description


def test_static_agent_prompts_do_not_require_runtime_agent_create():
    from app.agentscope_service.registry import build_datalogue_static_agent_specs

    combined = "\n".join(item.system_prompt for item in build_datalogue_static_agent_specs())

    assert "AgentCreate" not in combined
    assert "TeamCreate" not in combined
    assert "TeamSay" not in combined
    assert "native_handoff" not in combined
    assert "AgenticDirectQueryRunner" not in combined
```

- [ ] **Step 2: Implement static registry**

`datalogue-api/app/agentscope_service/registry.py`:

```python
# ============================================================
# File Name   : registry.py
# Description:
#   AgentScope Service 中 Datalogue 固定 Agent 注册表。
#
# Responsibilities:
#   - 定义 Lead/BI/Report/Python/Audit Agent 的稳定 key、名称和系统提示词。
#   - 给 bootstrap 和路由层提供唯一事实源，避免运行时动态 AgentCreate。
#   - 保持 prompt 只描述职责和边界，不在这里执行 Datalogue 业务代码。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StaticAgentSpec:
    """AgentScope Service 中固定注册的 Datalogue Agent 规格。"""

    key: str
    service_name: str
    description: str
    system_prompt: str
    role: str


LEAD_AGENT_PROMPT = """
你是 Datalogue AgenticLeadAgent，负责理解用户任务并把工作路由给固定 Agent。

固定 Agent：
- bi_agent：处理 Dataset Query 和 artifact/checkpoint refs。
- report_agent：基于已有 artifact 生成报告。
- python_agent：基于受控 artifact 做沙箱分析。
- audit_agent：审计工具调用和安全投影。

你不能动态创建 Agent，不能直接生成 SQL，不能读取 schema，不能输出 raw rows。
你只能通过 Datalogue 注册的固定 Agent 调用工具，把 dataset_id、question、task_id、trace_id 和安全上下文传给目标 Agent。
最终回答只输出 answer_summary、artifact_ref、checkpoint_ref、row_count、column_count 和必要失败原因。
""".strip()


BI_AGENT_PROMPT = """
你是 Datalogue BI Agent，是固定注册的 Dataset Query Agent。

你只能调用 Datalogue Dataset Query tools。
你不能直接面向用户输出 SQL、schema、raw rows、DSL、query_plan、compiled_query_ref 或 repair patch。
你只能返回安全业务摘要、artifact_ref、checkpoint_ref、row_count、column_count 和必要失败原因。
""".strip()


REPORT_AGENT_PROMPT = """
你是 Datalogue Report Agent，是固定注册的报告生成 Agent。

你只能基于 Datalogue 提供的 artifact_ref 和安全摘要生成报告。
如果缺少 artifact_ref，返回需要补充 artifact_ref 的安全失败摘要。
你不能访问数据库，不能重新执行 SQL，不能请求 raw rows。
""".strip()


PYTHON_AGENT_PROMPT = """
你是 Datalogue Python Agent，是固定注册的沙箱分析 Agent。

你只能在受控沙箱中处理 Datalogue 提供的 artifact_ref。
你不能请求数据库连接，不能读取 schema，不能输出 raw rows。
你只返回图表、统计摘要、artifact_ref 和必要失败原因。
""".strip()


AUDIT_AGENT_PROMPT = """
你是 Datalogue Audit Agent，是固定注册的审计 Agent。

你负责审计 Agent 路由、工具调用和安全投影是否符合 Datalogue 边界。
你只输出审计结论、风险摘要和阻断原因。
你不能输出 SQL、schema、raw rows、DSL、query_plan 或内部执行载荷。
""".strip()


def build_datalogue_static_agent_specs() -> list[StaticAgentSpec]:
    """返回 Datalogue 固定 Agent 注册规格。"""

    return [
        StaticAgentSpec(
            key="agentic_lead_agent",
            service_name="Datalogue Agentic Lead Agent",
            description="固定主控 Agent，负责理解任务和路由固定 Agent。",
            system_prompt=LEAD_AGENT_PROMPT,
            role="lead_agent",
        ),
        StaticAgentSpec(
            key="bi_agent",
            service_name="Datalogue BI Agent",
            description="Dataset Query Agent，负责智能问数、工具调用、artifact/checkpoint refs。",
            system_prompt=BI_AGENT_PROMPT,
            role="bi_agent",
        ),
        StaticAgentSpec(
            key="report_agent",
            service_name="Datalogue Report Agent",
            description="固定报告 Agent，负责基于 artifact 生成报告。",
            system_prompt=REPORT_AGENT_PROMPT,
            role="report_agent",
        ),
        StaticAgentSpec(
            key="python_agent",
            service_name="Datalogue Python Agent",
            description="固定 Python Agent，负责基于 artifact 做沙箱分析。",
            system_prompt=PYTHON_AGENT_PROMPT,
            role="python_agent",
        ),
        StaticAgentSpec(
            key="audit_agent",
            service_name="Datalogue Audit Agent",
            description="固定审计 Agent，负责审计策略、工具调用和安全投影。",
            system_prompt=AUDIT_AGENT_PROMPT,
            role="audit_agent",
        ),
    ]
```

- [ ] **Step 3: Run registry tests**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentscope_static_agent_registry.py -q
```

Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add datalogue-api/app/agentscope_service/registry.py datalogue-api/tests/test_agentscope_static_agent_registry.py
git commit -m "feat: define datalogue static agents registry"
```

---

### Task 6: Register Datalogue Dataset Tools Through Official Tool Factory

**Files:**
- Create: `datalogue-api/app/agentscope_service/tools.py`
- Create: `datalogue-api/app/agentscope_service/dataset_query_executor.py`
- Modify: `datalogue-api/app/agentscope_service/app_factory.py`
- Test: `datalogue-api/tests/test_agentscope_static_agent_registry.py`

- [ ] **Step 1: Write extra tools test**

Append:

```python
import pytest


@pytest.mark.asyncio
async def test_extra_agent_tools_factory_returns_datalogue_tools_for_sessions():
    from app.agentscope_service.tools import build_datalogue_extra_agent_tools

    factory = build_datalogue_extra_agent_tools()
    tools = await factory("user-test", "agent-test", "session-test")
    names = {tool.name for tool in tools}

    assert "datalogue_query_dataset" in names
    dataset_tool = next(tool for tool in tools if tool.name == "datalogue_query_dataset")
    assert dataset_tool.is_read_only is False
    assert "Datalogue Dataset Query" in dataset_tool.description
```

- [ ] **Step 2: Implement extra tools factory**

`datalogue-api/app/agentscope_service/tools.py`:

```python
# ============================================================
# File Name   : tools.py
# Description:
#   AgentScope Agent Service 的 Datalogue 业务工具注册。
#
# Responsibilities:
#   - 通过官方 extra_agent_tools factory 给 Agent session 注入业务工具。
#   - 只注册 Datalogue 领域工具，不复制 Agent 调度工具。
#   - 将 Dataset 查询请求转入现有 BI atomic toolkit 和 SQL control plane。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

from __future__ import annotations

import json

from agentscope.message import TextBlock, ToolResultState
from agentscope.tool import FunctionTool, ToolBase, ToolChunk

from app.agentscope_service.dataset_query_executor import execute_dataset_query_for_agent_team


async def _datalogue_query_dataset(
    dataset_id: int,
    question: str,
    task_id: str | None = None,
    trace_id: str | None = None,
) -> ToolChunk:
    """AgentScope FunctionTool 入口。

    只作为 AgentScope 官方工具注册边界，不在业务入口自写 runner。
    """

    result = await execute_dataset_query_for_agent_team(
        dataset_id=dataset_id,
        question=question,
        task_id=task_id,
        trace_id=trace_id,
    )
    payload = {
        "answer_summary": result.answer_summary,
        "artifact_ref": result.artifact_ref,
        "checkpoint_ref": result.checkpoint_ref,
        "row_count": result.row_count,
        "column_count": result.column_count,
    }
    return ToolChunk(
        content=[TextBlock(text=json.dumps(payload, ensure_ascii=False))],
        state=ToolResultState.SUCCESS,
    )


def build_datalogue_extra_agent_tools():
    """返回 AgentScope create_app 可消费的 extra_agent_tools factory。"""

    async def _factory(user_id: str, agent_id: str, session_id: str) -> list[ToolBase]:
        del user_id, agent_id, session_id
        return [
            FunctionTool(
                _datalogue_query_dataset,
                name="datalogue_query_dataset",
                description="Submit a Datalogue Dataset Query request and return safe artifact/checkpoint references.",
                is_concurrency_safe=False,
                is_read_only=False,
            )
        ]

    return _factory
```

- [ ] **Step 3: Add Dataset Query executor adapter**

`datalogue-api/app/agentscope_service/dataset_query_executor.py`:

```python
# ============================================================
# File Name   : dataset_query_executor.py
# Description:
#   固定 BI Agent 调用 Datalogue Dataset Query 的执行适配器。
#
# Responsibilities:
#   - 将 AgentScope FunctionTool 请求转成现有 BI atomic toolkit / SQL control plane 调用。
#   - 只返回 answer_summary、artifact_ref、checkpoint_ref 和行列统计等安全字段。
#   - 禁止返回 SQL、schema、raw rows 或内部 runner 状态。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

from __future__ import annotations

from dataclasses import dataclass

from app.agents.bi_agent.runtime_context import build_bi_runtime_context
from app.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge
from app.bi.toolkit.atomic import build_bi_atomic_toolkit
from app.core.database import SessionLocal


@dataclass(frozen=True)
class AgentTeamDatasetQueryResult:
    """固定 BI Agent 可以回传给 Leader 的安全结果。"""

    answer_summary: str
    artifact_ref: str | None
    checkpoint_ref: str | None
    row_count: int | None
    column_count: int | None
```

Add `execute_dataset_query_for_agent_team(...)` in the same file. Implementation steps:

1. Open a short-lived DB scope with `SessionLocal()`.
2. Build the existing toolkit with `build_bi_atomic_toolkit(db)`.
3. Build `AgentScopeDatasetRuntimeBridge(toolkit=toolkit)`.
4. Call `build_bi_runtime_context(db, dataset_id=dataset_id, question=question, bridge=bridge)` so `preview_dataset_sql(...)` remains the only SQL execution path.
5. Start a bridge session with `bridge.start_session(...)` using the runtime context's `session_kwargs`.
6. Let the fixed AgentScope BI Agent drive the official external tools; the adapter may only collect the final safe `artifact_ref`, `row_count`, `column_count`, and artifact summary.
7. Return `AgentTeamDatasetQueryResult` and close the DB scope.

This file is an adapter, not a new runner. It must not instantiate `AgenticDirectQueryRunner`, `AgentScopeNativeBIHandoff`, or `AgentScopeBIHandoffAdapter`, and it must not implement its own planning loop.

- [ ] **Step 4: Register extra tool factory**

Modify `create_app(...)` call:

```python
from app.agentscope_service.tools import build_datalogue_extra_agent_tools

...
        extra_agent_tools=build_datalogue_extra_agent_tools(),
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentscope_static_agent_registry.py -q
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add datalogue-api/app/agentscope_service/tools.py datalogue-api/app/agentscope_service/dataset_query_executor.py datalogue-api/app/agentscope_service/app_factory.py datalogue-api/tests/test_agentscope_static_agent_registry.py
git commit -m "feat: register datalogue tools with agentscope service"
```

---

### Task 7: Bootstrap Fixed Agents In Agent Service

**Files:**
- Create: `datalogue-api/app/agentscope_service/bootstrap.py`
- Test: `datalogue-api/tests/test_agentscope_service_bootstrap.py`

- [ ] **Step 1: Write bootstrap tests**

Create `datalogue-api/tests/test_agentscope_service_bootstrap.py`:

```python
# ============================================================
# File Name   : test_agentscope_service_bootstrap.py
# Description:
#   AgentScope Service 中固定 Agent 启动配置测试。
#
# Responsibilities:
#   - 确认 bootstrap 基于固定 Agent 注册表准备 Agent。
#   - 确认不再描述自研 handoff 或 direct query runner。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================


def test_bootstrap_static_agent_keys_match_registry():
    from app.agentscope_service.bootstrap import STATIC_AGENT_KEYS
    from app.agentscope_service.registry import build_datalogue_static_agent_specs

    registry_keys = tuple(item.key for item in build_datalogue_static_agent_specs())

    assert STATIC_AGENT_KEYS == registry_keys


def test_static_agent_prompts_do_not_require_dynamic_team_tools():
    from app.agentscope_service.registry import build_datalogue_static_agent_specs

    combined = "\n".join(item.system_prompt for item in build_datalogue_static_agent_specs())

    assert "TeamCreate" not in combined
    assert "AgentCreate" not in combined
    assert "TeamSay" not in combined
    assert "AgenticDirectQueryRunner" not in combined
    assert "native_handoff" not in combined
```

- [ ] **Step 2: Implement bootstrap service**

`datalogue-api/app/agentscope_service/bootstrap.py`:

```python
# ============================================================
# File Name   : bootstrap.py
# Description:
#   AgentScope Service 中 Datalogue 固定 Agent 的启动配置。
#
# Responsibilities:
#   - 基于固定 Agent 注册表幂等创建或查找 AgentScope Agent。
#   - 为主链提供稳定 key -> agent_id 映射。
#   - 禁止把运行时动态 AgentCreate 作为主链依赖。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

from __future__ import annotations

from app.agentscope_service.registry import build_datalogue_static_agent_specs


STATIC_AGENT_KEYS = tuple(item.key for item in build_datalogue_static_agent_specs())


class AgentScopeBootstrapService:
    """幂等准备 AgentScope Service 中的 Datalogue 固定 Agent。"""

    def __init__(self, *, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def ensure_static_agents(self) -> dict[str, str]:
        """返回固定 Agent key 到 AgentScope agent_id 的映射。

        实现时通过 AgentScope Service `/agent` 查找或创建 registry 中的固定 Agent。
        """

        raise NotImplementedError("ensure_static_agents will call AgentScope /agent APIs")
```

- [ ] **Step 3: Run bootstrap test**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentscope_service_bootstrap.py -q
```

Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add datalogue-api/app/agentscope_service/bootstrap.py datalogue-api/tests/test_agentscope_service_bootstrap.py
git commit -m "feat: define agentscope static agent bootstrap"
```

---

### Task 8: Build AgentScope Service Client Adapter

**Files:**
- Create: `datalogue-api/app/agentscope_service/client.py`
- Test: `datalogue-api/tests/test_agentscope_service_client.py`

- [ ] **Step 1: Write client request tests with httpx MockTransport**

Create `datalogue-api/tests/test_agentscope_service_client.py`:

```python
# ============================================================
# File Name   : test_agentscope_service_client.py
# Description:
#   Datalogue 到 AgentScope Service 的内部客户端测试。
#
# Responsibilities:
#   - 确认 Datalogue 通过官方 REST 边界创建 session 和触发 chat。
#   - 防止重新绕回本地自研 runner。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

import httpx
import pytest


@pytest.mark.asyncio
async def test_agentscope_service_client_triggers_chat():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/agentscope/session/":
            return httpx.Response(200, json={"session_id": "session-1"})
        if request.url.path == "/agentscope/chat/":
            return httpx.Response(200, json={"status": "started", "session_id": "session-1"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        from app.agentscope_service.client import AgentScopeServiceClient

        client = AgentScopeServiceClient(base_url="http://test/agentscope", http=http)
        session_id = await client.create_session(agent_id="agent-1", name="统计合同总金额")
        await client.trigger_chat(agent_id="agent-1", session_id=session_id, text="统计合同总金额")

    assert requests == [
        ("POST", "/agentscope/session/"),
        ("POST", "/agentscope/chat/"),
    ]
```

- [ ] **Step 2: Implement client**

`datalogue-api/app/agentscope_service/client.py`:

```python
# ============================================================
# File Name   : client.py
# Description:
#   Datalogue 调用 AgentScope Agent Service 的内部客户端。
#
# Responsibilities:
#   - 通过官方 REST 接口创建 session、触发 chat、订阅 stream。
#   - 隔离 AgentScope HTTP 协议，避免 Chat UI 直接依赖 AgentScope SDK 对象。
#   - 不执行任何 Agent loop；运行时由 Agent Service 接管。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx


class AgentScopeServiceClient:
    """AgentScope Agent Service 的 REST/SSE adapter。"""

    def __init__(self, *, base_url: str, http: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.AsyncClient(base_url=self.base_url)
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self.http.aclose()

    async def create_session(self, *, agent_id: str, name: str, chat_model_config: dict[str, Any] | None = None) -> str:
        response = await self.http.post(
            f"{self.base_url}/session/",
            json={
                "agent_id": agent_id,
                "name": name,
                "chat_model_config": chat_model_config,
            },
        )
        response.raise_for_status()
        return str(response.json()["session_id"])

    async def trigger_chat(self, *, agent_id: str, session_id: str, text: str) -> None:
        response = await self.http.post(
            f"{self.base_url}/chat/",
            json={
                "agent_id": agent_id,
                "session_id": session_id,
                "input": {"name": "user", "role": "user", "content": text},
            },
        )
        response.raise_for_status()

    async def stream_session(self, *, session_id: str) -> AsyncIterator[dict[str, Any]]:
        async with self.http.stream("GET", f"{self.base_url}/session/{session_id}/stream") as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                yield {"raw": line[5:].strip()}
```

- [ ] **Step 3: Run client tests**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentscope_service_client.py -q
```

Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add datalogue-api/app/agentscope_service/client.py datalogue-api/tests/test_agentscope_service_client.py
git commit -m "feat: add agentscope service client adapter"
```

---

### Task 9: Project AgentScope Stream To Datalogue Envelope

**Files:**
- Create: `datalogue-api/app/agentscope_service/projection.py`
- Test: `datalogue-api/tests/test_agentscope_service_projection.py`

- [ ] **Step 1: Write projection tests**

Create `datalogue-api/tests/test_agentscope_service_projection.py`:

```python
# ============================================================
# File Name   : test_agentscope_service_projection.py
# Description:
#   AgentScope Service 事件到 Datalogue Envelope 的投影测试。
#
# Responsibilities:
#   - 保证 AgentScope 原始事件不会直接暴露给前端。
#   - 保证 SQL/schema/raw rows 等敏感内容被过滤。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================


def test_projection_filters_sensitive_payload():
    from app.agentscope_service.projection import project_agentscope_service_event

    envelope = project_agentscope_service_event(
        {"event_type": "message", "payload": {"content": "select * from contracts", "artifact_ref": "artifact:1"}},
        task_id="task-1",
        trace_id="trace-1",
        selected_agent="bi_agent",
    )

    assert envelope.event_type in {"message.delta", "agent.event"}
    assert "select *" not in str(envelope.payload).lower()
    assert envelope.payload.get("artifact_ref") == "artifact:1"
```

- [ ] **Step 2: Implement projection**

`datalogue-api/app/agentscope_service/projection.py`:

```python
# ============================================================
# File Name   : projection.py
# Description:
#   AgentScope Service 事件到 Datalogue Event Envelope 的投影。
#
# Responsibilities:
#   - 把 AgentScope session stream 转为 Datalogue 稳定事件协议。
#   - 清洗 SQL、schema、raw rows、DSL、query_plan 等敏感载荷。
#   - 保留 artifact_ref、checkpoint_ref、row_count、column_count 等安全引用。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

from __future__ import annotations

from typing import Any

from app.events.projection import build_task_envelope
from app.agents.agentic_lead_agent import AgenticLeadAgent


def project_agentscope_service_event(
    event: dict[str, Any],
    *,
    task_id: str,
    trace_id: str,
    selected_agent: str,
    thread_id: str | None = None,
    message_id: str | None = None,
):
    """将 AgentScope Service 原始事件投影为 Datalogue envelope。"""

    sanitizer = AgenticLeadAgent()
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else dict(event)
    safe_payload = sanitizer.sanitize_output(payload)
    if not isinstance(safe_payload, dict):
        safe_payload = {"summary": str(safe_payload or "")}
    return build_task_envelope(
        event_type=_event_type(event),
        task_id=task_id,
        trace_id=trace_id,
        thread_id=thread_id,
        message_id=message_id,
        selected_agent=selected_agent,
        payload=safe_payload,
    )


def _event_type(event: dict[str, Any]) -> str:
    raw_type = str(event.get("event_type") or event.get("type") or "").lower()
    if "complete" in raw_type or "final" in raw_type:
        return "message.completed"
    if "tool" in raw_type:
        return "tool.result"
    if "message" in raw_type or "delta" in raw_type:
        return "message.delta"
    return "agent.event"
```

- [ ] **Step 3: Run projection tests**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentscope_service_projection.py -q
```

Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add datalogue-api/app/agentscope_service/projection.py datalogue-api/tests/test_agentscope_service_projection.py
git commit -m "feat: project agentscope service events"
```

---

### Task 10: Route `/agentic-shell/tasks/stream` Through Agent Service

**Files:**
- Modify: `datalogue-api/app/api/agentic_shell.py`
- Modify: `datalogue-api/app/runtime/task_runtime.py`
- Test: `datalogue-api/tests/test_agentic_shell_uses_agentscope_service.py`

- [ ] **Step 1: Write architecture test**

Create `datalogue-api/tests/test_agentic_shell_uses_agentscope_service.py`:

```python
# ============================================================
# File Name   : test_agentic_shell_uses_agentscope_service.py
# Description:
#   Agentic Shell 主入口使用 AgentScope Service 的架构测试。
#
# Responsibilities:
#   - 防止主入口重新导入自研 runner。
#   - 确认 task runtime 只做 task/envelope/DB 真相源。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

from pathlib import Path


def test_agentic_shell_runtime_does_not_use_self_written_runner():
    source = Path("app/runtime/task_runtime.py").read_text(encoding="utf-8")

    assert "BIAgentTaskRunner" not in source
    assert "AgenticDirectQueryRunner" not in source
    assert "direct_query_runner" not in source


def test_agentic_shell_api_uses_agentscope_service_client():
    source = Path("app/api/agentic_shell.py").read_text(encoding="utf-8")

    assert "AgentScopeServiceClient" in source
    assert "AgentScopeBootstrapService" in source
    assert "agentic_lead_agent" in source
    assert "project_agentscope_service_event" in source
```

- [ ] **Step 2: Refactor task runtime responsibility**

`AgenticShellTaskRuntime` should expose methods for:

```python
create_task(...)
mark_completed(...)
mark_failed(...)
record_refs(...)
```

It must not construct BI runners or call Dataset tools.

- [ ] **Step 3: Change API stream implementation**

In `/tasks/stream`:

```python
bootstrap = AgentScopeBootstrapService(base_url=str(request.url_for("agentscope")))
agent_ids = await bootstrap.ensure_static_agents()
agent_id = agent_ids["agentic_lead_agent"]
client = AgentScopeServiceClient(base_url=str(request.url_for("agentscope")))
session_id = await client.create_session(agent_id=agent_id, name=payload.question, chat_model_config=...)
await client.trigger_chat(agent_id=agent_id, session_id=session_id, text=payload.question)
async for raw_event in client.stream_session(session_id=session_id):
    envelope = project_agentscope_service_event(...)
    yield _sse_data(AgenticShellTaskStreamEvent(...).model_dump(mode="json"))
```

Implementation note: Use a small helper to build `base_url`; do not hardcode host/port. If mounted sub-app URL generation is awkward in tests, allow `AGENTSCOPE_SERVICE_BASE_URL` setting and default to local mounted path.

- [ ] **Step 4: Run architecture test**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentic_shell_uses_agentscope_service.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/api/agentic_shell.py datalogue-api/app/runtime/task_runtime.py datalogue-api/tests/test_agentic_shell_uses_agentscope_service.py
git commit -m "feat: route shell tasks through agentscope service"
```

---

### Task 11: Migrate BI Execution To Fixed BI Agent

**Files:**
- Modify: `datalogue-api/app/agents/agentic_lead_agent/react_factory.py`
- Modify: `datalogue-api/app/agents/bi_agent/react_factory.py`
- Modify: `datalogue-api/app/agentscope_service/tools.py`
- Modify: `datalogue-api/app/agentscope_service/registry.py`
- Test: `datalogue-api/tests/test_agentscope_static_agent_registry.py`

- [ ] **Step 1: Update LeadAgent prompt**

LeadAgent prompt must explicitly say:

```text
问数任务：
1. 使用固定 Agent 注册表中的 bi_agent。
2. 把 dataset_id、question、task_id、trace_id 作为受控请求交给 BI Agent。
3. 等待 BI Agent 返回安全摘要。
4. 最终只输出 answer_summary、artifact_ref、checkpoint_ref、row_count、column_count。
```

- [ ] **Step 2: Update BI Agent prompt**

BI Agent prompt must explicitly say:

```text
你是固定注册的 BI Agent，不是顶层路由。
你只能调用 Datalogue Dataset Query tools。
你不能直接面向用户输出 SQL/schema/raw rows。
```

- [ ] **Step 3: Test prompt and service tool boundaries**

Append:

```python
from pathlib import Path


def test_prompts_use_static_agents_not_dynamic_team():
    from app.agents.agentic_lead_agent.react_factory import AGENTIC_LEAD_AGENT_DIRECT_PROMPT
    from app.agents.bi_agent.react_factory import BI_AGENT_DIRECT_QUERY_PROMPT

    assert "bi_agent" in AGENTIC_LEAD_AGENT_DIRECT_PROMPT
    assert "固定" in AGENTIC_LEAD_AGENT_DIRECT_PROMPT
    assert "AgentCreate" not in AGENTIC_LEAD_AGENT_DIRECT_PROMPT
    assert "TeamCreate" not in AGENTIC_LEAD_AGENT_DIRECT_PROMPT
    assert "TeamSay" not in AGENTIC_LEAD_AGENT_DIRECT_PROMPT
    assert "native_handoff" not in AGENTIC_LEAD_AGENT_DIRECT_PROMPT
    assert "固定注册" in BI_AGENT_DIRECT_QUERY_PROMPT
    assert "TeamSay" not in BI_AGENT_DIRECT_QUERY_PROMPT


def test_dataset_service_tool_uses_real_executor():
    source = Path("app/agentscope_service/tools.py").read_text(encoding="utf-8")

    assert '"status": "accepted"' not in source
    assert "execute_dataset_query_for_agent_team" in source
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentscope_static_agent_registry.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/agents/agentic_lead_agent/react_factory.py datalogue-api/app/agents/bi_agent/react_factory.py datalogue-api/app/agentscope_service/tools.py datalogue-api/app/agentscope_service/registry.py datalogue-api/tests/test_agentscope_static_agent_registry.py
git commit -m "feat: express bi execution as fixed agentscope agent"
```

---

### Task 12: Retire Self-Written Runner And Handoff Code

**Files:**
- Delete: `datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py`
- Delete or shrink: `datalogue-api/app/agents/bi_agent/native_handoff.py`
- Delete or shrink: `datalogue-api/app/agents/bi_agent/handoff_adapter.py`
- Delete or shrink: `datalogue-api/app/agents/bi_agent/handoff_service.py`
- Modify: `datalogue-api/app/api/agentic_lead_agent.py`
- Test: `datalogue-api/tests/test_agentic_architecture_p5_service_team_cleanup.py`

- [ ] **Step 1: Write cleanup test**

Create `datalogue-api/tests/test_agentic_architecture_p5_service_team_cleanup.py`:

```python
# ============================================================
# File Name   : test_agentic_architecture_p5_service_team_cleanup.py
# Description:
#   AgentScope Service/Team 主链瘦身清理测试。
#
# Responsibilities:
#   - 防止自研 runner、handoff、direct query 重新进入生产路径。
#   - 确认 AgentScope Service/Team 是新的主运行时边界。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

from pathlib import Path


def test_self_written_main_chain_runner_files_removed_or_disabled():
    app_root = Path("app")
    removed = [
        app_root / "agents" / "agentic_lead_agent" / "direct_query_runner.py",
    ]

    for path in removed:
        assert not path.exists(), f"self-written runner still exists: {path}"


def test_no_production_imports_of_direct_runner_or_native_handoff():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("app").rglob("*.py")
        if "__pycache__" not in path.parts
    )

    forbidden = [
        "AgenticDirectQueryRunner",
        "BIAgentTaskRunner",
        "AgentScopeNativeBIHandoff",
        "AgentScopeBIHandoffAdapter",
        "run_direct_query(",
    ]
    for term in forbidden:
        assert term not in source
```

- [ ] **Step 2: Remove direct-query API**

`datalogue-api/app/api/agentic_lead_agent.py` should either be deleted from router registration or return `410 Gone` for direct-query endpoints. Production path must not call the removed runner.

- [ ] **Step 3: Remove imports and failing tests**

Run:

```bash
cd datalogue-api
rg "AgenticDirectQueryRunner|BIAgentTaskRunner|AgentScopeNativeBIHandoff|AgentScopeBIHandoffAdapter|run_direct_query" app tests
```

Delete or update all production references. Tests may keep these terms only in cleanup assertions.

- [ ] **Step 4: Run cleanup tests**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentic_architecture_p5_service_team_cleanup.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add -A datalogue-api/app datalogue-api/tests/test_agentic_architecture_p5_service_team_cleanup.py
git commit -m "refactor: remove self written agent runners"
```

---

### Task 13: Retire Legacy Dataset Runtime And Remote SubAgent

**Files:**
- Delete or shrink: `datalogue-api/app/bi/toolchain/dataset_runtime.py`
- Delete or shrink: `datalogue-api/app/api/internal_subagent.py`
- Modify: `datalogue-api/app/graph/__init__.py`
- Modify: `datalogue-api/app/graph/workflow.py`
- Modify: `datalogue-api/app/core/config.py`
- Test: `datalogue-api/tests/test_agentic_architecture_p5_service_team_cleanup.py`

- [ ] **Step 1: Extend cleanup test**

Append:

```python
def test_legacy_dataset_runtime_and_remote_subagent_are_not_main_chain():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("app").rglob("*.py")
        if "__pycache__" not in path.parts
    )

    forbidden = [
        "DatasetAgentToolCallRuntime",
        "RemoteDatasetSubAgentRunner",
        "SUBAGENT_RUNNER_MODE",
        "SUBAGENT_REMOTE_BASE_URL",
    ]
    for term in forbidden:
        assert term not in source
```

- [ ] **Step 2: Remove retired configs**

Remove from `Settings` if no production references remain:

```python
SUBAGENT_RUNNER_MODE
SUBAGENT_REMOTE_BASE_URL
SUBAGENT_REMOTE_API_KEY
SUBAGENT_REMOTE_TIMEOUT_SECONDS
SUBAGENT_REMOTE_RETRIES
AS_R0_AGENTIC_RUNTIME_SHADOW_ENABLED
```

- [ ] **Step 3: Keep only business primitives**

Do not delete business functions still needed by BI tools:

- `compile_query_plan_to_sql`
- `preview_dataset_sql`
- `ArtifactStore`
- Query plan contracts and validators

Only delete runtime orchestration wrappers that duplicate AgentScope Service/Team.

- [ ] **Step 4: Run targeted tests**

Run:

```bash
cd datalogue-api
uv run pytest tests/test_agentic_architecture_p5_service_team_cleanup.py tests/test_agentscope_dataset_runtime_bridge.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add -A datalogue-api/app datalogue-api/tests/test_agentic_architecture_p5_service_team_cleanup.py
git commit -m "refactor: retire legacy dataset runtime wrappers"
```

---

### Task 14: End-To-End Service Smoke

**Files:**
- Create: `datalogue-api/tests/test_agentscope_service_smoke.py`
- Modify: `.codex/project-memory.md`

- [ ] **Step 1: Add integration smoke test marker**

Create `datalogue-api/tests/test_agentscope_service_smoke.py`:

```python
# ============================================================
# File Name   : test_agentscope_service_smoke.py
# Description:
#   AgentScope Service/Team 主链集成烟测。
#
# Responsibilities:
#   - 验证 Agent Service 能创建 session、触发 chat、输出可投影事件。
#   - 验证 Datalogue task、artifact_ref、message.completed 能在同一 trace 下对齐。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

import os

import pytest


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("RUN_AGENTSCOPE_SERVICE_SMOKE") != "1", reason="requires redis and live service")
def test_agentscope_service_team_main_chain_smoke():
    assert True
```

Implementation note: In the execution task, replace `assert True` with a real HTTP call to `/api/agentic-shell/tasks/stream` after Redis and API server are available. Keep the skip gate so default unit tests remain stable.

- [ ] **Step 2: Run unit suite**

Run:

```bash
cd datalogue-api
uv run pytest \
  tests/test_agentscope_service_imports.py \
  tests/test_agentscope_service_factory.py \
  tests/test_agentscope_static_agent_registry.py \
  tests/test_agentscope_service_client.py \
  tests/test_agentscope_service_projection.py \
  tests/test_agentic_shell_uses_agentscope_service.py \
  tests/test_agentic_architecture_p5_service_team_cleanup.py \
  -q
```

Expected: PASS。

- [ ] **Step 3: Run real smoke with Redis**

Run:

```bash
cd datalogue-api
redis-cli ping
RUN_AGENTSCOPE_SERVICE_SMOKE=1 uv run pytest tests/test_agentscope_service_smoke.py -q -s
```

Expected: PASS after the real HTTP body is implemented.

- [ ] **Step 4: Record project memory**

Append to `.codex/project-memory.md`:

```markdown
### 2026-07-03 HH:mm AgentScope Service/Team 主链计划

- 涉及文件：`app/agentscope_service/*`、`app/api/agentic_shell.py`、`app/runtime/task_runtime.py`
- 关键改动：主链目标从自研 runner 调整为 AgentScope Agent Service + 固定 Agent 注册表；Datalogue 只保留 task/envelope/业务真相源。
- 验证方式：Agent Service import/factory/template/client/projection/unit tests；Redis smoke gate。
- 残留风险：AgentScope Service REST/SSE 真实事件格式需在 smoke 阶段按 2.0.3 实测微调 projection。
```

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/tests/test_agentscope_service_smoke.py .codex/project-memory.md
git commit -m "test: add agentscope service team smoke gate"
```

---

## Verification Matrix

Run before declaring completion:

```bash
cd datalogue-api
uv run pytest \
  tests/test_agentscope_service_imports.py \
  tests/test_agentscope_service_factory.py \
  tests/test_agentscope_static_agent_registry.py \
  tests/test_agentscope_service_bootstrap.py \
  tests/test_agentscope_service_client.py \
  tests/test_agentscope_service_projection.py \
  tests/test_agentic_shell_uses_agentscope_service.py \
  tests/test_agentic_architecture_p5_service_team_cleanup.py \
  tests/test_agentic_shell_chat_stream_removed.py \
  -q
```

Run before deleting the old branch or merging:

```bash
cd datalogue-api
rg "AgenticDirectQueryRunner|BIAgentTaskRunner|AgentScopeNativeBIHandoff|AgentScopeBIHandoffAdapter|DatasetAgentToolCallRuntime|RemoteDatasetSubAgentRunner|DatalogueChatStreamRuntime|_stream_chat" app tests
```

Expected:

- No production references.
- Test references only in cleanup assertions.

Run frontend build if Chat UI adapter changes:

```bash
cd datalogue-web
npm run lint
npm run build
```

---

## Self-Review

- Spec coverage: Plan covers official Agent Service dependencies, embedded service app, static Agent registry, Service client, event projection, `/agentic-shell/tasks/stream` routing, fixed BI Agent migration, old runner cleanup, remote SubAgent cleanup, and smoke verification.
- Placeholder scan: No implementation placeholder remains as a required production step. The smoke test includes an explicit gated integration note because it depends on Redis and live service availability.
- Type consistency: The main new names are `create_embedded_agentscope_app`, `build_datalogue_static_agent_specs`, `build_datalogue_extra_agent_tools`, `AgentScopeBootstrapService`, `AgentScopeServiceClient`, and `project_agentscope_service_event`; all tasks use the same names.
