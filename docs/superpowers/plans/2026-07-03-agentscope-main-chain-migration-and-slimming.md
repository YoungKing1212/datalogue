# AgentScope Main Chain Migration And Slimming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将数语主问数链路迁到 AgentScope-owned runtime，并删除不再使用的旧 direct/compat 编排代码，让架构收敛到轻量主链。

**Architecture:** `/api/agentic-shell/tasks/stream` 继续作为唯一主入口，`AgenticShellTaskRuntime` 只负责 task、session、message、envelope 和 DB 真相源。真正执行链收敛为 AgentScope `AgenticLeadAgent -> BI Agent -> Dataset external tools`，不再通过 `BIAgentTaskRunner -> AgenticDirectQueryRunner` 二次编排。Datalogue 保留 Manifest、SQL 编译/审计、artifact、checkpoint 和安全摘要作为业务真相源。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, AgentScope 2.0.3, pytest, SSE, Datalogue BI atomic Toolkit.

---

## Target Ownership

迁移后的主链 ownership：

- API 入口：`datalogue-api/app/api/agentic_shell.py`
- Task 真相源与事件投影：`datalogue-api/app/runtime/task_runtime.py`
- AgentScope 执行 runner：新增 `datalogue-api/app/runtime/agentscope_bi_runner.py`
- Agent 工厂：`datalogue-api/app/agents/agentic_lead_agent/react_factory.py`、`datalogue-api/app/agents/bi_agent/react_factory.py`
- Dataset 工具事件桥：`datalogue-api/app/bi/skill/runtime_bridge.py`
- BI 原子工具：`datalogue-api/app/bi/toolkit/atomic.py`
- 保留业务内核：`compile_query_plan_to_sql`、`preview_dataset_sql`、`ArtifactStore`、Manifest/权限/安全摘要

迁移后应删除或从生产路径移除：

- `BIAgentTaskRunner` 里的数据集路由、自动 confirm、direct query 转调逻辑
- `AgenticDirectQueryRunner` 作为主链依赖
- direct-query API 如果只剩调试价值，降级到开发开关或删除
- `AgentScopeDatasetRuntimeBridge.run_direct_query()` 的主链尾段兜底
- `DatasetAgentToolCallRuntime` 兼容 runtime，如果没有测试或生产引用则删除
- `internal_subagent.py` + `build_workflow()` 的旧 remote subagent 入口，如果确认不再被环境变量和服务调用

---

## File Structure

- Modify: `datalogue-api/app/api/agentic_shell.py`
  - 只构造生产默认 AgentScope runner，不再返回 `BIAgentTaskRunner`。
- Modify: `datalogue-api/app/runtime/task_runtime.py`
  - 保留 `AgenticShellTaskRuntime` 的 task/session/message/envelope 职责。
  - 删除或迁出 `BIAgentTaskRunner`。
- Create: `datalogue-api/app/runtime/agentscope_bi_runner.py`
  - 实现 `AgentScopeBIMainChainRunner.stream(...)`，直接驱动 AgentScope LeadAgent、BI Agent 和 Dataset external tools。
- Modify: `datalogue-api/app/runtime/__init__.py`
  - 导出新 runner，停止导出被删除的 `BIAgentTaskRunner`。
- Modify: `datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py`
  - 第一阶段不删，先改为非生产兼容路径；最后确认无引用后删除。
- Modify: `datalogue-api/app/api/agentic_lead_agent.py`
  - direct-query API 降级为开发调试入口或删除。
- Modify: `datalogue-api/app/bi/skill/runtime_bridge.py`
  - 保留 `run_reply_stream()` 和 external event 处理。
  - 删除主链不再需要的 `run_direct_query()` 或移到测试 helper。
- Modify: `datalogue-api/app/bi/toolchain/dataset_runtime.py`
  - 若主链和测试不再引用，整文件删除。
- Modify: `datalogue-api/app/api/internal_subagent.py`
  - 若 `SUBAGENT_RUNNER_MODE=remote` 退役，删除内部 old SubAgent route。
- Modify: `datalogue-api/app/graph/workflow.py`
  - 若无生产引用，删除旧 `build_workflow()` 出口；如果 SQL/repair 仍需底层函数，迁到明确的 service/tool 文件。
- Test: `datalogue-api/tests/test_agentic_shell_agentscope_main_chain.py`
- Test: `datalogue-api/tests/test_agentic_architecture_p5_main_chain_cleanup.py`
- Test: 更新 `datalogue-api/tests/test_agentic_shell_chat_stream_removed.py`

---

### Task 1: 锁定主链所有权测试

**Files:**
- Create: `datalogue-api/tests/test_agentic_shell_agentscope_main_chain.py`
- Modify: `datalogue-api/tests/test_agentic_shell_chat_stream_removed.py`

- [ ] **Step 1: 写失败测试，证明生产入口不能再依赖 direct query runner**

```python
def test_agentic_shell_default_runner_is_agentscope_main_chain(db_session):
    from app.api.agentic_shell import build_agentic_shell_task_runner
    from app.runtime.agentscope_bi_runner import AgentScopeBIMainChainRunner

    runner = build_agentic_shell_task_runner(db_session)

    assert isinstance(runner, AgentScopeBIMainChainRunner)
```

- [ ] **Step 2: 写架构扫描测试，禁止主入口回调旧 direct runner**

```python
def test_task_runtime_does_not_import_direct_query_runner():
    from pathlib import Path

    source = Path("app/runtime/task_runtime.py").read_text(encoding="utf-8")

    assert "AgenticDirectQueryRunner" not in source
    assert "direct_query_runner" not in source
    assert "BIAgentTaskRunner" not in source
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd datalogue-api && uv run pytest tests/test_agentic_shell_agentscope_main_chain.py -q`

Expected: FAIL，原因是 `app.runtime.agentscope_bi_runner` 还不存在，且默认 runner 仍是 `BIAgentTaskRunner`。

- [ ] **Step 4: Commit**

```bash
git add datalogue-api/tests/test_agentic_shell_agentscope_main_chain.py datalogue-api/tests/test_agentic_shell_chat_stream_removed.py
git commit -m "test: lock agentscope main chain ownership"
```

---

### Task 2: 新增 AgentScope 主链 Runner

**Files:**
- Create: `datalogue-api/app/runtime/agentscope_bi_runner.py`
- Modify: `datalogue-api/app/runtime/__init__.py`
- Test: `datalogue-api/tests/test_agentic_shell_agentscope_main_chain.py`

- [ ] **Step 1: 创建 runner 骨架**

`AgentScopeBIMainChainRunner` 必须实现现有 `AgentScopeTaskRunner.stream(...)` 协议，输入仍是 `request/task/user_msg`，输出仍是可被 `project_agentscope_event(...)` 投影的事件或 Datalogue envelope。

核心代码形态：

```python
class AgentScopeBIMainChainRunner:
    """生产主链 runner：用 AgentScope Agent 驱动 LeadAgent -> BI Agent -> Dataset tools。"""

    def __init__(self, *, db: Session) -> None:
        self.db = db

    async def stream(self, *, request: AgenticShellTaskRequest, task: AgenticShellTask, user_msg: UserMsg) -> AsyncIterator[Any]:
        lead_agent = AgenticLeadAgentFactory(db=self.db).create(model_config_id=request.model_config_id)
        lead_reply = await lead_agent.reply(self._lead_route_message(request))
        decision = self._parse_route_decision(lead_reply)
        if decision.get("selected_agent") != "bi_agent":
            yield build_task_envelope(
                event_type="message.completed",
                task_id=task.task_id,
                trace_id=task.trace_id,
                thread_id=task.thread_id,
                message_id=task.message_id,
                selected_agent=task.selected_agent,
                payload={"summary": "当前仅启用 BI Agent。", "route_decision": decision},
            )
            return
        async for event in self._run_bi_agent(request=request, task=task):
            yield event
```

- [ ] **Step 2: 保留 task/envelope 边界**

新 runner 不能写 `AgenticShellTask` 状态，不能创建 `AgentScope mirror session`，不能提交事务；这些仍由 `AgenticShellTaskRuntime` 统一负责。

- [ ] **Step 3: 更新导出**

`datalogue-api/app/runtime/__init__.py` 导出：

```python
from app.runtime.agentscope_bi_runner import AgentScopeBIMainChainRunner
from app.runtime.task_runtime import AgenticShellTaskRuntime, AgentScopeTaskRunner

__all__ = ["AgenticShellTaskRuntime", "AgentScopeTaskRunner", "AgentScopeBIMainChainRunner"]
```

- [ ] **Step 4: 运行测试**

Run: `cd datalogue-api && uv run pytest tests/test_agentic_shell_agentscope_main_chain.py::test_agentic_shell_default_runner_is_agentscope_main_chain -q`

Expected: 仍可能 FAIL，因为 API 默认 runner 尚未切换；下一任务处理。

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/runtime/agentscope_bi_runner.py datalogue-api/app/runtime/__init__.py
git commit -m "feat: add agentscope main chain runner"
```

---

### Task 3: 切换 `/agentic-shell/tasks/stream` 生产默认 Runner

**Files:**
- Modify: `datalogue-api/app/api/agentic_shell.py`
- Modify: `datalogue-api/app/runtime/task_runtime.py`
- Test: `datalogue-api/tests/test_agentic_shell_agentscope_main_chain.py`

- [ ] **Step 1: API 默认 runner 改成 AgentScope 主链**

将 `build_agentic_shell_task_runner(db)` 改为：

```python
def build_agentic_shell_task_runner(db: Session) -> AgentScopeBIMainChainRunner:
    """生产默认 runner：Shell 直接进入 AgentScope-owned BI 主链。"""

    return AgentScopeBIMainChainRunner(db=db)
```

- [ ] **Step 2: `AgenticShellTaskRuntime` 删除本地 `AgenticLeadAgent().prepare_turn()` 决策**

`AgenticShellTaskRuntime` 只保留安全 fallback：默认 `selected_agent="bi_agent"`，真实路由由 runner 内 AgentScope LeadAgent 事件输出。

- [ ] **Step 3: 运行主链 ownership 测试**

Run: `cd datalogue-api && uv run pytest tests/test_agentic_shell_agentscope_main_chain.py -q`

Expected: PASS。

- [ ] **Step 4: 运行旧 stream 删除测试**

Run: `cd datalogue-api && uv run pytest tests/test_agentic_shell_chat_stream_removed.py -q`

Expected: PASS，`/api/chat/stream` 仍是 404/405。

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/api/agentic_shell.py datalogue-api/app/runtime/task_runtime.py datalogue-api/tests/test_agentic_shell_agentscope_main_chain.py
git commit -m "feat: route shell task stream through agentscope runner"
```

---

### Task 4: 用 Native Handoff 替代 Direct Query 主链

**Files:**
- Modify: `datalogue-api/app/runtime/agentscope_bi_runner.py`
- Modify: `datalogue-api/app/agents/bi_agent/handoff_service.py`
- Test: `datalogue-api/tests/test_agentic_shell_agentscope_main_chain.py`

- [ ] **Step 1: 在新 runner 中创建 BI run 并调用 handoff service**

主链语义改为：AgentScope LeadAgent 选中 BI Agent 后，BI Agent 通过 `query_dataset` 这个 handoff capability 调用 `AgentScopeNativeBIHandoff`，不再进入 `AgenticDirectQueryRunner.run()`。

关键断言：返回给外层的 payload 只包含 `handoff_status`、`answer_summary`、`artifact_ref`、`checkpoint_ref`、`child_run_id`、`row_count`、`column_count`。

- [ ] **Step 2: 写测试防止 direct runner 回流**

```python
def test_shell_task_runner_never_constructs_direct_query_runner(monkeypatch, db_session):
    import app.agents.agentic_lead_agent.direct_query_runner as direct_module

    def _blocked(*args, **kwargs):
        raise AssertionError("AgenticDirectQueryRunner must not be used by shell task stream")

    monkeypatch.setattr(direct_module, "AgenticDirectQueryRunner", _blocked)
    from app.api.agentic_shell import build_agentic_shell_task_runner

    runner = build_agentic_shell_task_runner(db_session)

    assert runner.__class__.__name__ == "AgentScopeBIMainChainRunner"
```

- [ ] **Step 3: 运行测试**

Run: `cd datalogue-api && uv run pytest tests/test_agentic_shell_agentscope_main_chain.py -q`

Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add datalogue-api/app/runtime/agentscope_bi_runner.py datalogue-api/app/agents/bi_agent/handoff_service.py datalogue-api/tests/test_agentic_shell_agentscope_main_chain.py
git commit -m "feat: use native handoff in shell main chain"
```

---

### Task 5: 收敛 Dataset External Tool Runtime

**Files:**
- Modify: `datalogue-api/app/bi/skill/runtime_bridge.py`
- Modify: `datalogue-api/app/agents/bi_agent/native_handoff.py`
- Test: `datalogue-api/tests/test_agentscope_dataset_runtime_bridge.py`

- [ ] **Step 1: 保留 `run_reply_stream()` 作为唯一主链工具事件驱动**

主链只允许 AgentScope 的 `RequireExternalExecutionEvent -> ExternalExecutionResultEvent`，不允许绕过为 deterministic `run_direct_query()`。

- [ ] **Step 2: 删除或测试隔离 `run_direct_query()`**

如果仍有测试需要 deterministic 工具链，迁到测试 helper，不保留在生产 `AgentScopeDatasetRuntimeBridge`。

- [ ] **Step 3: 补扫描测试**

```python
def test_dataset_runtime_bridge_has_no_direct_query_main_path():
    from pathlib import Path

    source = Path("app/bi/skill/runtime_bridge.py").read_text(encoding="utf-8")

    assert "async def run_direct_query" not in source
    assert "dataset-runtime-direct" not in source
```

- [ ] **Step 4: 运行 bridge 测试**

Run: `cd datalogue-api && uv run pytest tests/test_agentscope_dataset_runtime_bridge.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/bi/skill/runtime_bridge.py datalogue-api/app/agents/bi_agent/native_handoff.py datalogue-api/tests/test_agentscope_dataset_runtime_bridge.py
git commit -m "refactor: remove direct dataset runtime fallback"
```

---

### Task 6: 删除 Direct Query API 或降级为开发开关

**Files:**
- Modify: `datalogue-api/app/api/agentic_lead_agent.py`
- Modify: `datalogue-api/app/core/config.py`
- Test: `datalogue-api/tests/test_agentic_shell_agentscope_main_chain.py`

- [ ] **Step 1: 决策规则**

生产代码默认删除 `/api/agentic-lead-agent/direct-query` 和 `/direct-query/stream`。如果需要临时保留，必须新增 `AGENTIC_DIRECT_QUERY_DEBUG_ENABLED: bool = False`，默认返回 410。

- [ ] **Step 2: 测试默认禁用**

```python
def test_direct_query_debug_route_is_disabled_by_default(client):
    response = client.post("/api/agentic-lead-agent/direct-query", json={"question": "统计合同总金额", "dataset_id": 1})

    assert response.status_code == 410
```

- [ ] **Step 3: 删除主链引用**

确认 `app/runtime`、`app/api/agentic_shell.py`、`app/agents/bi_agent` 不再 import `AgenticDirectQueryRunner`。

- [ ] **Step 4: 运行测试**

Run: `cd datalogue-api && uv run pytest tests/test_agentic_shell_agentscope_main_chain.py tests/test_agentic_shell_chat_stream_removed.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add datalogue-api/app/api/agentic_lead_agent.py datalogue-api/app/core/config.py datalogue-api/tests/test_agentic_shell_agentscope_main_chain.py
git commit -m "refactor: retire direct query api from production path"
```

---

### Task 7: 删除旧 Runtime 与 LangGraph 兼容入口

**Files:**
- Delete: `datalogue-api/app/agents/agentic_lead_agent/direct_query_runner.py`
- Delete: `datalogue-api/app/bi/toolchain/dataset_runtime.py`
- Delete or archive: `datalogue-api/app/api/internal_subagent.py`
- Modify: `datalogue-api/app/graph/__init__.py`
- Modify: `datalogue-api/app/graph/workflow.py`
- Test: `datalogue-api/tests/test_agentic_architecture_p5_main_chain_cleanup.py`

- [ ] **Step 1: 写 cleanup 扫描测试**

```python
def test_removed_legacy_main_chain_files_do_not_exist():
    from pathlib import Path

    app_root = Path("app")
    removed = [
        app_root / "agents" / "agentic_lead_agent" / "direct_query_runner.py",
        app_root / "bi" / "toolchain" / "dataset_runtime.py",
        app_root / "api" / "internal_subagent.py",
    ]

    for path in removed:
        assert not path.exists(), f"legacy main chain file still exists: {path}"
```

- [ ] **Step 2: 写 forbidden import 测试**

```python
def test_no_legacy_main_chain_symbols_remain():
    from pathlib import Path

    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("app").rglob("*.py")
        if "__pycache__" not in path.parts
    )
    forbidden = [
        "AgenticDirectQueryRunner",
        "DatasetAgentToolCallRuntime",
        "RemoteDatasetSubAgentRunner",
        "build_workflow(db)",
        "SUBAGENT_RUNNER_MODE",
    ]

    for term in forbidden:
        assert term not in source
```

- [ ] **Step 3: 删除文件并修正 import**

删除文件后运行 `rg "AgenticDirectQueryRunner|DatasetAgentToolCallRuntime|internal_subagent|build_workflow|SUBAGENT_RUNNER_MODE" datalogue-api/app datalogue-api/tests`，逐个删除或迁移引用。

- [ ] **Step 4: 运行 cleanup 测试**

Run: `cd datalogue-api && uv run pytest tests/test_agentic_architecture_p5_main_chain_cleanup.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add -A datalogue-api/app datalogue-api/tests/test_agentic_architecture_p5_main_chain_cleanup.py
git commit -m "refactor: remove legacy main chain runtime"
```

---

### Task 8: 清理配置、文档和依赖边界

**Files:**
- Modify: `datalogue-api/app/core/config.py`
- Modify: `datalogue-api/README.md`
- Modify: `datalogue-api/docs/LiteLLM多模型接入说明.md`
- Modify: `.codex/project-memory.md`

- [ ] **Step 1: 删除退役配置**

如果 Task 7 已删除 remote subagent 和旧 runner，删除：

```python
SUBAGENT_RUNNER_MODE
SUBAGENT_REMOTE_BASE_URL
SUBAGENT_REMOTE_API_KEY
SUBAGENT_REMOTE_TIMEOUT_SECONDS
SUBAGENT_REMOTE_RETRIES
AS_R0_AGENTIC_RUNTIME_SHADOW_ENABLED
```

- [ ] **Step 2: 文档改口径**

README 中主链说明改为：

```markdown
主问数入口为 `/api/agentic-shell/tasks/stream`。运行时由 AgentScope 2.0 Agent 驱动：AgenticLeadAgent 负责顶层路由，BI Agent 通过 Dataset external tools 执行查询。Datalogue 仅保留 Manifest、SQL 审计、artifact 和 checkpoint 作为业务真相源。
```

- [ ] **Step 3: 项目记忆新增完成记录**

`.codex/project-memory.md` 按 `YYYY-MM-DD HH:mm` 追加：

```markdown
### 2026-07-03 HH:mm AgentScope 主链迁移与轻量化

- 涉及文件：`app/api/agentic_shell.py`、`app/runtime/agentscope_bi_runner.py`、`app/runtime/task_runtime.py`、`app/bi/skill/runtime_bridge.py`
- 关键改动：主入口切到 AgentScope-owned runner，删除 direct query 和旧 Dataset runtime 兼容入口。
- 验证方式：`uv run pytest tests/test_agentic_shell_agentscope_main_chain.py tests/test_agentic_architecture_p5_main_chain_cleanup.py -q`
- 残留风险：模型供应商兼容性仍由 `build_agentscope_chat_model` 和 LLM 配置验证覆盖。
```

- [ ] **Step 4: Commit**

```bash
git add datalogue-api/app/core/config.py datalogue-api/README.md datalogue-api/docs/LiteLLM多模型接入说明.md .codex/project-memory.md
git commit -m "docs: record agentscope main chain migration"
```

---

### Task 9: 端到端验收

**Files:**
- No production edits expected.

- [ ] **Step 1: 静态引用扫描**

Run:

```bash
cd datalogue-api
rg "AgenticDirectQueryRunner|DatasetAgentToolCallRuntime|DatalogueChatStreamRuntime|BIWorkbenchTool|AgentScopeShellAdapter|_stream_chat|LegacyWorkflowTaskRunner" app tests
```

Expected: 无生产引用；如果测试中保留 forbidden-term 测试，命中必须只出现在测试断言里。

- [ ] **Step 2: 后端回归**

Run:

```bash
cd datalogue-api
uv run pytest \
  tests/test_agentic_shell_agentscope_main_chain.py \
  tests/test_agentic_shell_chat_stream_removed.py \
  tests/test_agentscope_dataset_runtime_bridge.py \
  tests/test_bi_lead_agent_native_handoff.py \
  tests/test_agentic_architecture_p5_main_chain_cleanup.py \
  -q
```

Expected: PASS。

- [ ] **Step 3: 前端构建**

Run:

```bash
cd datalogue-web
npm run lint
npm run build
```

Expected: PASS。

- [ ] **Step 4: 真实链路 smoke**

启动服务后调用 `/api/agentic-shell/tasks/stream`，验证 SSE 中至少出现：

- `task.started`
- `agent.selected`
- `dataset.query.started` 或等价 BI Agent 开始事件
- `artifact.created`
- `message.completed`

同时检查 DB 中存在：

- `agentic_shell_task.status=completed`
- assistant message completed
- `query_artifact` 可通过 `artifact_ref` 查到

- [ ] **Step 5: Commit or tag verification evidence**

```bash
git status --short
git log --oneline -5
```

Expected: 只剩预期改动；所有迁移提交按阶段可回滚。

---

## Self-Review

- Spec coverage: 计划覆盖主入口、AgentScope runner、native handoff、Dataset external tools、direct query 退役、旧 runtime 删除、配置文档收口和真实验收。
- Placeholder scan: 本计划不使用待补占位语义；每个任务给出明确文件、测试、命令和期望结果。
- Type consistency: 新 runner 统一命名为 `AgentScopeBIMainChainRunner`，实现现有 `AgentScopeTaskRunner.stream(...)` 协议；API 默认 runner、runtime 导出和测试均使用同一名称。
