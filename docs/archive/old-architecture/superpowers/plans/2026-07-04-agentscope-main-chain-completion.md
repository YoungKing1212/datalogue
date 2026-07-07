# AgentScope 主链路完成迁移 Implementation Plan

> **状态：已废弃。** 本计划仍保留 `Agentic Shell` 作为主链入口命名，不再符合 2026-07-04 的最新架构定夺。后续执行必须改用 `docs/superpowers/plans/2026-07-04-agentscope-agent-team-main-chain.md`，以 AgentScope Agent Team 为主链设计理念。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前 `main` 的混合态收口为“Chat/Workbench 主执行入口全部走 AgentScope Service 固定智能体主链”，并删除不再使用的旧 direct-query 公开入口和前端客户端。

**Architecture:** Datalogue 只保留 `Agentic Shell Task` 作为业务主入口，`/api/agentic-shell/tasks/stream` 创建 Datalogue task 后调用内嵌 AgentScope Service 的固定 `agentic_lead_agent`。AgentScope Service 负责 Agent session/chat/stream 边界，Datalogue 只做配置、固定 Agent 注册、事件安全投影、artifact/checkpoint 引用和前端 adapter。前端聊天统一通过 `agentic-shell-task-api.js` 发送任务流，不再直接调用 `/api/agentic-lead-agent/direct-query/stream`。

**Tech Stack:** FastAPI、AgentScope 2.0.3 Agent Service、Redis、LocalWorkspaceManager、SSE、assistant-ui 前端适配、Vitest、pytest、Docker Compose。

---

## 当前状态判断

当前 `main/origin/main` 已经存在以下基础件：

- `datalogue-api/app/agentscope_service/*`
- `datalogue-api/app/api/agentic_shell.py` 中的 `AgentScopeServiceTaskRunner`
- `datalogue-web/src/assistant/agentic-shell-task-api.js`
- 根目录 `docker-compose.yml`

但仍未达到完成标准：

- `datalogue-api/app/main.py` 没有挂载 `/agentscope`
- `datalogue-api/app/api/__init__.py` 仍包含 `agentic_lead_agent` 旧路由
- `datalogue-api/app/api/agentic_lead_agent.py` 仍暴露 `/direct-query*`
- `datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py` 仍存在
- `datalogue-api/app/schemas/agentic_direct_query.py` 仍存在
- `datalogue-web/src/assistant/chat-adapter.js` 仍导入 `streamAgenticDirectQuery`
- `datalogue-web/src/assistant/agentic-direct-query-api.js` 仍调用 `/api/agentic-lead-agent/direct-query/stream`

## 完成标准

- Chat UI 只调用 `/api/agentic-shell/tasks/stream`
- `/api/agentic-shell/tasks/stream` 默认 runner 只调用 `AgentScopeServiceTaskRunner`
- FastAPI 主应用按配置挂载 `/agentscope`
- 旧 `/api/agentic-lead-agent/direct-query*` 不再注册为公开 API
- 旧 `AgenticDirectQueryRunner`、`agentic_direct_query` schema、旧前端 direct-query client 删除
- 生产代码扫描不再命中旧 direct-query 主链关键字
- 后端 AgentScope Service 主链测试、前端 adapter 测试、build/lint、compose config 全部通过

---

### Task 1: 用测试锁定“主链只走 AgentScope Service”

**Files:**
- Modify: `datalogue-api/tests/test_agentic_shell_uses_agentscope_service.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`
- Modify: `datalogue-web/src/assistant/chat-adapter.test.js`

- [ ] **Step 1: 增加后端主入口断言**

在 `datalogue-api/tests/test_agentic_shell_uses_agentscope_service.py` 增加断言，确保默认 runner 是 `AgentScopeServiceTaskRunner`，并且 base URL 来自 request/mount path。

```python
def test_agentic_shell_default_runner_is_agentscope_service():
    from app.agentscope_service.runner import AgentScopeServiceTaskRunner
    from app.api.agentic_shell import build_agentic_shell_task_runner

    runner = build_agentic_shell_task_runner(base_url="http://testserver/agentscope")

    assert isinstance(runner, AgentScopeServiceTaskRunner)
    assert runner.base_url == "http://testserver/agentscope"
```

- [ ] **Step 2: 增加旧路由不可注册断言**

在 `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py` 增加生产路由扫描，明确禁止旧 direct-query API 回到主路由。

```python
def test_legacy_agentic_lead_agent_direct_query_api_not_registered():
    from app.api import router

    route_paths = {getattr(route, "path", "") for route in router.routes}

    assert "/agentic-lead-agent/direct-query" not in route_paths
    assert "/agentic-lead-agent/direct-query/stream" not in route_paths
```

- [ ] **Step 3: 增加前端旧客户端不可用断言**

在 `datalogue-web/src/assistant/chat-adapter.test.js` 中移除 `agentic-direct-query-api` mock，新增断言：发送消息时调用 `streamAgenticShellTask`，请求 payload 使用 `task_source="chat"`、`task_type="bi_query"`。

```js
vi.mock('./agentic-shell-task-api', () => ({
  streamAgenticShellTask: vi.fn(),
}));

it('sends chat messages through Agentic Shell task stream', async () => {
  streamAgenticShellTask.mockReturnValue(events([
    {
      task_id: 'task-agentic-1',
      event_envelope: {
        event_type: 'task.completed',
        summary: '查询完成',
      },
    },
  ]));

  await adapter.send({
    messages: [{ role: 'user', content: [{ type: 'text', text: '统计合同金额' }] }],
  });

  expect(streamAgenticShellTask).toHaveBeenCalledWith(
    expect.objectContaining({
      task_source: 'chat',
      task_type: 'bi_query',
      question: '统计合同金额',
    }),
    expect.any(Object),
  );
});
```

- [ ] **Step 4: 先运行测试确认当前混合态失败**

Run:

```bash
cd datalogue-api
uv run --python /Users/yangkai/.local/bin/python3.12 pytest tests/test_agentic_shell_uses_agentscope_service.py tests/test_agentic_architecture_p1_boundaries.py -q

cd ../datalogue-web
npm test -- chat-adapter.test.js --run
```

Expected: 至少前端测试或旧路由边界测试失败，证明测试能捕捉当前未完成状态。

- [ ] **Step 5: Commit 测试基线**

```bash
git add datalogue-api/tests/test_agentic_shell_uses_agentscope_service.py datalogue-api/tests/test_agentic_architecture_p1_boundaries.py datalogue-web/src/assistant/chat-adapter.test.js
git commit -m "test: lock agentscope service main chain"
```

---

### Task 2: 挂载 AgentScope Service 子应用

**Files:**
- Modify: `datalogue-api/app/main.py`
- Modify: `datalogue-api/app/core/config.py`
- Modify: `datalogue-api/.env.example`
- Test: `datalogue-api/tests/test_agentscope_service_factory.py`

- [ ] **Step 1: 补主应用挂载测试**

在 `datalogue-api/tests/test_agentscope_service_factory.py` 确认配置开启时挂载 `/agentscope`，关闭时不挂载。

```python
def test_main_mounts_agentscope_service_only_when_enabled(monkeypatch):
    from fastapi import FastAPI
    from app import main as main_module
    from app.core.config import Settings

    mounted = {}

    def fake_create_embedded_agentscope_app(settings):
        mounted["settings"] = settings
        return FastAPI(title="fake-agentscope")

    monkeypatch.setattr(
        main_module,
        "create_embedded_agentscope_app",
        fake_create_embedded_agentscope_app,
        raising=False,
    )

    root_app = FastAPI()
    main_module.mount_agentscope_service(root_app, Settings(AGENTSCOPE_SERVICE_ENABLED=False))
    assert all(route.path != "/agentscope" for route in root_app.routes)

    enabled = Settings(AGENTSCOPE_SERVICE_ENABLED=True, AGENTSCOPE_MOUNT_PATH="/agentscope")
    main_module.mount_agentscope_service(root_app, enabled)

    assert any(route.path == "/agentscope" for route in root_app.routes)
    assert mounted["settings"] is enabled
```

- [ ] **Step 2: 在 `main.py` 实现挂载函数**

在 `datalogue-api/app/main.py` 增加：

```python
from app.agentscope_service.app_factory import create_embedded_agentscope_app
```

并在 `app.include_router(...)` 前后增加：

```python
def mount_agentscope_service(root_app: FastAPI, current_settings) -> None:
    """按配置挂载官方 AgentScope Service 子应用，主链 runner 通过该服务边界执行固定 Agent。"""

    if not current_settings.AGENTSCOPE_SERVICE_ENABLED:
        return
    root_app.mount(
        current_settings.AGENTSCOPE_MOUNT_PATH,
        create_embedded_agentscope_app(current_settings),
    )


mount_agentscope_service(app, settings)
```

- [ ] **Step 3: 确认配置默认值和示例完整**

检查 `datalogue-api/app/core/config.py` 和 `datalogue-api/.env.example` 至少包含：

```env
AGENTSCOPE_SERVICE_ENABLED=true
AGENTSCOPE_MOUNT_PATH=/agentscope
AGENTSCOPE_SERVICE_BASE_URL=http://127.0.0.1:8000/agentscope
AGENTSCOPE_REDIS_HOST=localhost
AGENTSCOPE_REDIS_PORT=6379
AGENTSCOPE_REDIS_DB=0
AGENTSCOPE_REDIS_PASSWORD=
AGENTSCOPE_REDIS_URL=redis://localhost:6379/0
AGENTSCOPE_WORKSPACE_BASEDIR=data/agentscope/workspaces
AGENTSCOPE_WORKSPACE_TTL_SECONDS=3600
```

- [ ] **Step 4: 运行挂载测试**

```bash
cd datalogue-api
uv run --python /Users/yangkai/.local/bin/python3.12 pytest tests/test_agentscope_service_factory.py -q
```

Expected: `passed`。

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/main.py datalogue-api/app/core/config.py datalogue-api/.env.example datalogue-api/tests/test_agentscope_service_factory.py
git commit -m "feat: mount embedded agentscope service"
```

---

### Task 3: 后端删除旧 direct-query 公开入口

**Files:**
- Modify: `datalogue-api/app/api/__init__.py`
- Delete: `datalogue-api/app/api/agentic_lead_agent.py`
- Delete: `datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py`
- Delete: `datalogue-api/app/schemas/agentic_direct_query.py`
- Delete or rewrite: `datalogue-api/tests/test_agentscope_direct_query_chain.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p1_boundaries.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p2_bi_boundaries.py`

- [ ] **Step 1: 从 API router 移除旧路由**

在 `datalogue-api/app/api/__init__.py` 删除：

```python
from app.api import agentic_lead_agent
router.include_router(agentic_lead_agent.router, prefix="/agentic-lead-agent", tags=["AgenticLeadAgent"])
```

- [ ] **Step 2: 删除旧直连 API 和 runner**

删除以下文件：

```bash
rm datalogue-api/app/api/agentic_lead_agent.py
rm datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py
rm datalogue-api/app/schemas/agentic_direct_query.py
```

- [ ] **Step 3: 删除或迁移旧测试**

如果 `datalogue-api/tests/test_agentscope_direct_query_chain.py` 只覆盖旧 direct-query runner，删除该测试文件。若其中存在仍有价值的安全投影断言，迁移到：

```text
datalogue-api/tests/test_agentscope_service_projection.py
datalogue-api/tests/test_agentscope_service_task_runner.py
```

迁移后的断言必须以 `AgentScopeServiceTaskRunner` 或 `project_agentscope_service_event()` 为主语，不再 import `AgenticDirectQueryRunner`。

- [ ] **Step 4: 跑后端边界测试**

```bash
cd datalogue-api
uv run --python /Users/yangkai/.local/bin/python3.12 pytest tests/test_agentic_architecture_p1_boundaries.py tests/test_agentic_architecture_p2_bi_boundaries.py tests/test_agentic_shell_task_api.py tests/test_agentic_shell_task_runtime.py tests/test_agentic_shell_uses_agentscope_service.py -q
```

Expected: 全部通过。

- [ ] **Step 5: 扫描旧引用**

```bash
rg "agentic-lead-agent|AgenticDirectQueryRunner|direct_query_runner|agentic_direct_query" datalogue-api/app datalogue-api/tests -n
```

Expected: 生产代码无命中；测试中只允许出现“禁止旧链路”的边界断言。

- [ ] **Step 6: Commit**

```bash
git add -A datalogue-api/app datalogue-api/tests
git commit -m "chore: remove legacy agentic direct query backend"
```

---

### Task 4: 前端聊天入口切到 Agentic Shell task stream

**Files:**
- Modify: `datalogue-web/src/assistant/chat-adapter.js`
- Modify: `datalogue-web/src/assistant/chat-adapter.test.js`
- Delete: `datalogue-web/src/assistant/agentic-direct-query-api.js`
- Keep: `datalogue-web/src/assistant/agentic-shell-task-api.js`
- Keep: `datalogue-web/src/assistant/agentic-shell-event-adapter.js`

- [ ] **Step 1: 移除旧 direct-query import**

在 `datalogue-web/src/assistant/chat-adapter.js` 删除：

```js
import { streamAgenticDirectQuery } from './agentic-direct-query-api';
```

改为使用：

```js
import { streamAgenticShellTask } from './agentic-shell-task-api';
import { adaptAgenticShellEvent } from './agentic-shell-event-adapter';
```

- [ ] **Step 2: 把发送链路改为 task stream**

把旧：

```js
const stream = streamAgenticDirectQuery({
  question,
  dataset_id: datasetId,
  conversation_id: conversationId,
  model_config_id: selectedModelConfigId,
}, { signal });
```

改为：

```js
const stream = streamAgenticShellTask({
  task_source: 'chat',
  task_type: 'bi_query',
  question,
  dataset_id: datasetId,
  conversation_id: conversationId,
  model_config_id: selectedModelConfigId,
}, { signal });
```

并对每个后端事件调用既有 adapter：

```js
for await (const event of stream) {
  const messageEvent = adaptAgenticShellEvent(event);
  if (!messageEvent) continue;
  // 复用当前 chat-adapter 已有的 message/artifact 状态写入逻辑。
}
```

- [ ] **Step 3: 删除旧前端客户端**

```bash
rm datalogue-web/src/assistant/agentic-direct-query-api.js
```

- [ ] **Step 4: 跑前端测试**

```bash
cd datalogue-web
npm test -- chat-adapter.test.js agentic-shell-task-api.test.js agentic-shell-event-adapter.test.js --run
```

Expected: 全部通过。

- [ ] **Step 5: 扫描旧前端引用**

```bash
rg "agentic-direct-query-api|streamAgenticDirectQuery|runAgenticDirectQuery|agentic-lead-agent" datalogue-web/src -n
```

Expected: 无命中。

- [ ] **Step 6: Commit**

```bash
git add -A datalogue-web/src/assistant
git commit -m "feat: route chat adapter through agentic shell task stream"
```

---

### Task 5: 保留固定 Agent 注册，不引入动态 AgentCreate

**Files:**
- Modify: `datalogue-api/app/agentscope_service/registry.py`
- Modify: `datalogue-api/app/agentscope_service/bootstrap.py`
- Modify: `datalogue-api/tests/test_agentscope_static_agent_registry.py`
- Modify: `datalogue-api/tests/test_agentscope_service_bootstrap.py`

- [ ] **Step 1: 锁定固定 Agent registry 行为**

在 `test_agentscope_static_agent_registry.py` 断言只暴露固定 ID：

```python
def test_static_agent_registry_contains_only_fixed_agents():
    from app.agentscope_service.registry import build_static_agent_registry

    registry = build_static_agent_registry()

    assert set(registry) == {"agentic_lead_agent"}
    assert registry["agentic_lead_agent"].agent_id == "agentic_lead_agent"
```

- [ ] **Step 2: 锁定 bootstrap 不创建动态 Agent**

在 `test_agentscope_service_bootstrap.py` 断言 bootstrap 使用固定 registry，不接受用户传入任意 agent class/name。

```python
def test_bootstrap_registers_static_agents_only(monkeypatch):
    from app.agentscope_service import bootstrap

    registered = []

    def fake_register_agent(agent_id, agent_factory):
        registered.append(agent_id)

    monkeypatch.setattr(bootstrap, "register_agent", fake_register_agent, raising=False)

    bootstrap.bootstrap_static_agents()

    assert registered == ["agentic_lead_agent"]
```

- [ ] **Step 3: 若测试暴露缺口，收口实现**

实现应保持：

```python
STATIC_AGENT_IDS = ("agentic_lead_agent",)
```

并且所有 session 创建只允许从该集合中取 agent。

- [ ] **Step 4: 运行 Service registry/bootstrap 测试**

```bash
cd datalogue-api
uv run --python /Users/yangkai/.local/bin/python3.12 pytest tests/test_agentscope_static_agent_registry.py tests/test_agentscope_service_bootstrap.py -q
```

Expected: 全部通过。

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/agentscope_service/registry.py datalogue-api/app/agentscope_service/bootstrap.py datalogue-api/tests/test_agentscope_static_agent_registry.py datalogue-api/tests/test_agentscope_service_bootstrap.py
git commit -m "test: enforce static agentscope service registry"
```

---

### Task 6: 部署配置与本地环境收口

**Files:**
- Modify: `docker-compose.yml`
- Modify: `datalogue-api/docker-compose.yml`
- Modify: `datalogue-api/.env.example`
- Optional local only: `datalogue-api/.env`

- [ ] **Step 1: 根 compose 确认包含完整服务**

`docker-compose.yml` 必须包含：

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
  redis:
    image: redis:7-alpine
  api:
    environment:
      AGENTSCOPE_SERVICE_ENABLED: "true"
      AGENTSCOPE_MOUNT_PATH: /agentscope
      AGENTSCOPE_SERVICE_BASE_URL: http://api:8000/agentscope
      AGENTSCOPE_REDIS_URL: redis://redis:6379/0
      AGENTSCOPE_WORKSPACE_BASEDIR: /data/agentscope/workspaces
      LANGFUSE_ENABLED: "false"
  web:
    environment:
      VITE_API_PROXY_TARGET: http://api:8000
```

- [ ] **Step 2: 后端 infra compose 确认包含 Redis**

`datalogue-api/docker-compose.yml` 保留 infra-only 定位，至少有 `db` 和 `redis`。

- [ ] **Step 3: 本地 `.env` 保持宿主机地址**

本地 `datalogue-api/.env` 如果需要修改，使用：

```env
AGENTSCOPE_SERVICE_ENABLED=true
AGENTSCOPE_MOUNT_PATH=/agentscope
AGENTSCOPE_SERVICE_BASE_URL=http://127.0.0.1:8000/agentscope
AGENTSCOPE_REDIS_URL=redis://localhost:6379/0
AGENTSCOPE_WORKSPACE_BASEDIR=data/agentscope/workspaces
LANGFUSE_ENABLED=false
```

不要提交 `.env`。

- [ ] **Step 4: 验证 compose config**

```bash
docker compose -f docker-compose.yml config >/tmp/datalogue-root-compose-config.out
docker compose -f datalogue-api/docker-compose.yml config >/tmp/datalogue-api-compose-config.out
```

Expected: exit code 0。

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml datalogue-api/docker-compose.yml datalogue-api/.env.example
git commit -m "chore: align compose with agentscope service runtime"
```

---

### Task 7: 最终清理、验证和项目记忆

**Files:**
- Modify: `.codex/project-memory.md`
- Verify: all files touched above

- [ ] **Step 1: 生产代码旧链路扫描**

```bash
rg "agentic-lead-agent|agentic-direct-query-api|streamAgenticDirectQuery|runAgenticDirectQuery|AgenticDirectQueryRunner|agentic_direct_query|direct_query_runner" datalogue-api/app datalogue-web/src -n
```

Expected: 无命中。

- [ ] **Step 2: 后端主链测试**

```bash
cd datalogue-api
uv run --python /Users/yangkai/.local/bin/python3.12 pytest \
  tests/test_agentscope_service_imports.py \
  tests/test_agentscope_service_factory.py \
  tests/test_agentscope_static_agent_registry.py \
  tests/test_agentscope_service_bootstrap.py \
  tests/test_agentscope_service_client.py \
  tests/test_agentscope_service_projection.py \
  tests/test_agentscope_service_task_runner.py \
  tests/test_agentic_shell_task_runtime.py \
  tests/test_agentic_shell_task_api.py \
  tests/test_agentic_shell_uses_agentscope_service.py \
  tests/test_agentic_architecture_p1_boundaries.py \
  tests/test_agentic_architecture_p2_bi_boundaries.py \
  -q
```

Expected: 全部通过。

- [ ] **Step 3: AgentScope 兼容测试**

```bash
cd datalogue-api
uv run --python /Users/yangkai/.local/bin/python3.12 pytest tests/test_agentscope_dependency_compat.py tests/test_agentscope_dataset_runtime_bridge.py -q
```

Expected: 全部通过。

- [ ] **Step 4: 前端测试、lint、build**

```bash
cd datalogue-web
npm test -- chat-adapter.test.js agentic-shell-task-api.test.js agentic-shell-event-adapter.test.js --run
npm run lint
npm run build
```

Expected: 测试通过；lint 0 errors；build 通过，允许既有 chunk size warning。

- [ ] **Step 5: Docker 配置验证**

```bash
docker compose -f docker-compose.yml config
docker compose -f datalogue-api/docker-compose.yml config
```

Expected: exit code 0。

- [ ] **Step 6: 更新项目记忆**

在 `.codex/project-memory.md` 增加记录，至少包含：

```markdown
### 2026-07-04 HH:mm · AgentScope Service 主链路完成迁移

- 涉及文件：`datalogue-api/app/agentscope_service/*`、`datalogue-api/app/api/agentic_shell.py`、`datalogue-api/app/main.py`、`datalogue-web/src/assistant/chat-adapter.js`、`docker-compose.yml` 等
- 关键改动：Chat/Workbench 主入口统一到 `/api/agentic-shell/tasks/stream`，后端 runner 只调用 AgentScope Service 固定 Agent，删除旧 direct-query 公开入口和前端 direct-query client。
- 验证方式：记录 Task 7 中通过的 pytest、vitest、lint、build、compose config 命令。
- 残留风险：如果尚未做真实浏览器和 Docker up 验收，明确写入。
```

- [ ] **Step 7: 最终提交**

```bash
git add -A
git commit -m "feat: complete agentscope service main chain migration"
```

---

## 执行建议

推荐使用隔离 worktree 执行，避免污染当前 detached/main 工作区：

```bash
git worktree add .worktrees/agentscope-main-chain-completion -b codex/agentscope-main-chain-completion main
cd .worktrees/agentscope-main-chain-completion
```

如果当前环境已经是 Codex 托管 worktree，则不再创建嵌套 worktree，直接在当前工作区执行任务。

## 风险控制

- 不删除 `.env`，只改 `.env.example`
- 不把 raw rows、SQL、schema、query_plan 放入前端消息 metadata
- 旧 direct-query 删除前必须先让 Agentic Shell task stream 测试通过
- 如果真实页面仍走旧接口，优先排查前端 dev server 是否指向旧 worktree 或旧端口
- 如果 Redis/Workspace 相关测试失败，先看 `AGENTSCOPE_REDIS_URL` 是否被本地 `.env` 覆盖测试构造的 `Settings(...)`

## 自检清单

- [ ] 每个完成标准都有对应任务
- [ ] 每个删除动作都有扫描验证
- [ ] 每个主链行为都有测试锁定
- [ ] 没有要求使用动态 `AgentCreate`
- [ ] 没有要求 Datalogue 自写 Agent runner
- [ ] 最终验证覆盖后端、前端、compose 和项目记忆
