# AgentScope Agent Team 主链迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Datalogue 主链从旧 `Agentic Shell` / direct-query / 自研 runner 思路，收口为 AgentScope 2.0.3 官方 Agent Service + Agent Team 模式。

**Architecture:** Datalogue 挂载 AgentScope Agent Service，并通过官方 Agent Team 能力运行主链。Leader 智能体是用户会话的主控 Agent；BI、Report、Python、Audit 是固定 worker 类型/模板，由 AgentScope Team 内置 `TeamCreate`、`AgentCreate`、`TeamSay`、`TeamDelete` 工具协调。Datalogue 不实现自己的 Agent runner，不实现自己的 handoff 编排，不把 `Agentic Shell` 作为架构概念；Datalogue 只保留业务工具、安全投影、artifact/checkpoint refs、数据库事务和前端展示适配。

**Tech Stack:** Python 3.12, FastAPI, AgentScope 2.0.3 Agent Service, AgentScope Agent Team, `custom_subagent_templates`, RedisStorage, RedisMessageBus, LocalWorkspaceManager, SSE, pytest, Vitest, Docker Compose。

---

## Supersedes

本计划替代以下旧计划：

```text
docs/superpowers/plans/2026-07-03-agentscope-service-team-main-chain.md
docs/superpowers/plans/2026-07-04-agentscope-main-chain-completion.md
```

旧计划的问题：

- 继续保留 `/api/agentic-shell/tasks/stream` 作为主链 API 主语。
- 继续保留 `AgenticShellTask` / `AgenticShellTaskRuntime` 作为运行时归属。
- 把 AgentScope Team 内置 `TeamCreate` / `AgentCreate` / `TeamSay` 定义为未来能力，而不是当前主链。
- 用 Datalogue 自己的 fixed agent registry + bootstrap + runner 做路由，仍然有自研编排味道。

新的原则：

- `Agentic Shell` 只能作为历史兼容名出现，不能作为新主链架构名。
- 固定 Agent 的含义是固定 worker 类型/模板和固定业务边界，不是 Datalogue 预注册固定 Agent 实例并自写路由。
- `AgentCreate` / `TeamCreate` 允许出现，但只能是 AgentScope 官方 Team 内置工具，不允许 Datalogue 自己实现同名替代品。

---

## Official AgentScope Contracts

来自 AgentScope 2.0.3 官方文档和本地包 API：

- Agent Service 是 FastAPI 服务，接管请求路由、会话状态、持久化、调度、工具卸载、Workspace、MessageBus 和 Session Stream。
- Agent Team 是 Agent Service 之上的多智能体层，Leader 会话通过内置 team 工具创建团队、派生 worker、交换消息、解散团队。
- `create_app(...)` 支持 `custom_subagent_templates`：

```python
from agentscope.app import create_app, SubAgentTemplate

create_app(
    storage=storage,
    message_bus=message_bus,
    workspace_manager=workspace_manager,
    extra_agent_tools=build_datalogue_extra_agent_tools(),
    custom_subagent_templates=[
        SubAgentTemplate(
            type="bi",
            description="Datalogue BI worker，只能调用安全 Dataset Query 工具。",
            system_prompt_template="...",
            permission_context=...,
        ),
    ],
)
```

- `SubAgentTemplate` 的 `type` 会成为 AgentScope 内置 `AgentCreate` 的 `subagent_type` 枚举，Leader 只能从 Datalogue 暴露的固定 worker 类型中选择。

---

## Target Runtime Shape

```text
Chat UI / Workbench / API
  -> Datalogue Agent Team Gateway（命名必须是 Agent Team，不再叫 Agentic Shell）
  -> AgentScope Agent Service session/chat/stream
      -> Leader Agent session
      -> TeamCreate（官方内置工具）
      -> AgentCreate(subagent_type="bi" | "report" | "python" | "audit")
      -> TeamSay / TeamDelete
      -> worker session stream
      -> Datalogue Dataset Query / Artifact / Checkpoint tools
  -> Datalogue 安全投影
  -> Chat UI / Workbench
```

Datalogue 保留：

- Datalogue 业务工具：Dataset Query、Report、Python sandbox、Audit 工具。
- 安全投影：SQL、schema、raw rows、DSL、query_plan、repair patch 不进入用户可见事件。
- Artifact / Checkpoint refs。
- 与现有 Chat UI / Workbench 的展示协议适配。

AgentScope 负责：

- Leader / worker 会话。
- Team 创建、worker 创建、团队消息、团队清理。
- RedisStorage、RedisMessageBus、Workspace、Session Stream。
- Agent 状态和多智能体协调。

---

## Task 1: 把计划和测试目标从 Agentic Shell 改为 Agent Team

**Files:**
- Modify: `datalogue-api/tests/test_agentscope_service_factory.py`
- Modify: `datalogue-api/tests/test_agentscope_static_agent_registry.py`
- Modify: `datalogue-api/tests/test_agentic_shell_uses_agentscope_service.py` or replace with `test_agentscope_agent_team_gateway.py`
- Modify: `datalogue-web/src/assistant/chat-adapter.test.js`

- [ ] 新增测试：`create_embedded_agentscope_app()` 必须把 `custom_subagent_templates` 传给 `agentscope_create_app`。
- [ ] 新增测试：模板类型只能是固定集合：`bi`、`report`、`python`、`audit`。
- [ ] 新增测试：prompt 中允许出现 `TeamCreate`、`AgentCreate`、`TeamSay`，但必须明确这些是 AgentScope 官方内置 Team 工具，不允许 Datalogue 自写 runner/handoff。
- [ ] 新增测试：生产代码中不允许把 `Agentic Shell` 作为主链 API / runtime / frontend client 命名。

验证：

```bash
cd datalogue-api
uv run --python /Users/yangkai/.local/bin/python3.12 pytest tests/test_agentscope_service_factory.py tests/test_agentscope_static_agent_registry.py -q
```

---

## Task 2: 用 SubAgentTemplate 替代 fixed agent bootstrap

**Files:**
- Create or replace: `datalogue-api/app/agentscope_service/team_templates.py`
- Modify: `datalogue-api/app/agentscope_service/app_factory.py`
- Delete or retire: `datalogue-api/app/agentscope_service/bootstrap.py`
- Modify: `datalogue-api/app/agentscope_service/registry.py`

- [ ] 新增 `build_datalogue_subagent_templates()`。
- [ ] 为 `bi`、`report`、`python`、`audit` 创建 `SubAgentTemplate`。
- [ ] `app_factory.create_embedded_agentscope_app()` 调用 `agentscope_create_app(..., custom_subagent_templates=build_datalogue_subagent_templates())`。
- [ ] 删除通过 `/agent` 预注册固定 Agent 的 bootstrap 主链依赖。

验收标准：

```bash
rg "ensure_static_agents|STATIC_AGENT_KEYS|/agent|datalogue_static_agent_key" datalogue-api/app -n
```

Expected: 无生产主链依赖；如保留兼容代码，必须标记 deprecated 且不被主入口调用。

---

## Task 3: 入口命名从 Agentic Shell 改为 Agent Team Gateway

**Files:**
- Create: `datalogue-api/app/api/agent_team.py`
- Create: `datalogue-api/app/schemas/agentscope_agent_team_task.py`
- Create or rename: `datalogue-api/app/runtime/agent_team_runtime.py`
- Modify: `datalogue-api/app/api/__init__.py`
- Retire: `datalogue-api/app/api/agentic_shell.py`
- Retire: `datalogue-api/app/schemas/agentic_shell_task.py`
- Retire: `datalogue-api/app/runtime/task_runtime.py` Agentic Shell naming

- [ ] 新 API 使用 `/api/agent-team/tasks/stream` 或更直接的 `/api/agentscope/team/stream`，最终只保留一种。
- [ ] DTO 命名为 `AgentTeamTaskRequest` / `AgentTeamTaskStreamEvent`。
- [ ] Runtime 命名为 `AgentTeamTaskRuntime`，职责是 Datalogue task 真相源 + AgentScope Service stream 投影，不执行 Agent loop。
- [ ] 前端和 Workbench 不再调用 `/api/agentic-shell/tasks/stream`。

验收扫描：

```bash
rg "AgenticShell|agentic_shell|Agentic Shell|agentic-shell" datalogue-api/app datalogue-web/src -n
```

Expected: 生产主链无命中；允许历史文档/迁移测试中出现“禁止旧命名”的断言。

---

## Task 4: 前端 client 改为 Agent Team 命名

**Files:**
- Create: `datalogue-web/src/assistant/agent-team-task-api.js`
- Create: `datalogue-web/src/assistant/agent-team-event-adapter.js`
- Modify: `datalogue-web/src/assistant/chat-adapter.js`
- Modify: `datalogue-web/src/assistant/chat-adapter.test.js`
- Retire: `datalogue-web/src/assistant/agentic-shell-task-api.js`
- Retire: `datalogue-web/src/assistant/agentic-shell-event-adapter.js`

- [ ] `chat-adapter` 调用 Agent Team task stream，不再导入 `agentic-shell-*`。
- [ ] 测试用例描述和 mock 名称改为 Agent Team。
- [ ] 保留当前 artifact、candidate dataset、model_config_id、conversation_id 行为。

验证：

```bash
cd datalogue-web
npm test -- chat-adapter.test.js agent-team-task-api.test.js agent-team-event-adapter.test.js --run
npm run lint
npm run build
```

---

## Task 5: 清理旧 direct-query 和旧 Agentic Shell 残留

**Files:**
- Delete: `datalogue-api/app/api/agentic_lead_agent.py`
- Delete: `datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py`
- Delete: `datalogue-api/app/schemas/agentic_direct_query.py`
- Delete: `datalogue-web/src/assistant/agentic-direct-query-api.js`
- Delete or migrate old tests tied to direct-query / Agentic Shell runtime

扫描：

```bash
rg "agentic-lead-agent|agentic-direct-query|direct-query|AgenticDirectQueryRunner|agentic_direct_query|AgenticShell|agentic-shell|agentic_shell" datalogue-api/app datalogue-web/src -n
```

Expected: 生产主链无命中。

---

## Task 6: 部署和项目记忆

**Files:**
- Modify: `docker-compose.yml`
- Modify: `datalogue-api/.env.example`
- Modify: `.codex/project-memory.md`

- [ ] Compose 继续挂载 `/agentscope` 并启用 Redis/Workspace。
- [ ] `.env.example` 使用 AgentScope Service/Team 命名，不出现 Agentic Shell 主链描述。
- [ ] 项目记忆写入 Agent Team 设计理念：后续开发遵从 AgentScope 官方 Team，不自写 runner/handoff，不以 Agentic Shell 命名主链。

验证：

```bash
docker compose -f docker-compose.yml config
docker compose -f datalogue-api/docker-compose.yml config
git diff --check
```

---

## Final Verification

```bash
cd datalogue-api
uv run --python /Users/yangkai/.local/bin/python3.12 pytest tests/test_agentscope_service_factory.py tests/test_agentscope_static_agent_registry.py tests/test_agentscope_service_client.py tests/test_agentscope_service_projection.py tests/test_agentscope_dependency_compat.py tests/test_agentscope_dataset_runtime_bridge.py -q

cd ../datalogue-web
npm test -- chat-adapter.test.js --run
npm run lint
npm run build

cd ..
docker compose -f docker-compose.yml config
git diff --check
```

---

## Decision Record

本计划的核心决策已经写入 `.codex/project-memory.md`：

- AgentScope Agent Team 是后续主链设计理念。
- 固定 Agent 表达为固定 worker 模板/能力边界，而不是 Datalogue 自己预注册固定 Agent 实例并手写路由。
- `Agentic Shell` 只能作为历史兼容名处理，不能作为新开发目标。
