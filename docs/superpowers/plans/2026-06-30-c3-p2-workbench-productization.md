# C3-P2 Workbench Productization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 C3 Workbench 从“Chat 右侧 Panel 可用”推进到“可长期承载 BI 工作台”的产品化第一阶段，同时把 C3-P1 的真实链路验收作为发布闸门嵌入。

**Architecture:** C3-P2 PR1 继续保持双主路径：AgentScope-compatible mirror / Workbench View Model 负责会话、消息、事件和引用视图；Datalogue Chat 主链负责真实 BI 执行和 retry checkpoint 恢复。这里的双主路径是 C3 foundation 口径，不表示 AgentScope Runtime ownership 已完成；AS-R0 P1 才开始让 AgentScope Runtime 驱动 BI 主链。后端只输出业务级状态摘要、Artifact preview 和 refs；前端只消费 View Model，不拼接 SQL、schema、raw rows、query_plan 或字段级 patch。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、pytest、React、Vitest、Testing Library、Vite。

---

## Scope

C3-P2 PR1 做方案 1，并把方案 2 作为验收闸门：

- Workbench Panel 产品化状态模型。
- Artifact 详情抽屉，继续只显示业务级 preview 和 refs。
- retry 后结果定位和状态回放一致性。
- legacy `conv_*` 保持只读，不启动 retry。
- 成功问数、failed retry、旧会话只读回放三条路径作为自动化和真实浏览器验收闸门。

不纳入 C3-P2 PR1：

- 独立 Workbench 正式入口。
- ReportAgent / PythonAgent / AuditAgent 动作链路。
- AgentScope runner 接管 Datalogue BI 主链。
- Datalogue Agentic Shell 接管 `/chat/stream`。
- 管理员字段级调试 UI。

## Multi-Agent Coordination

- Backend lane：检查并实现 Workbench View Model 状态摘要、Artifact detail 脱敏和 retry action 状态。
- Frontend lane：检查并实现 Chat 右侧 Panel 的状态空态、Artifact 详情抽屉和 retry 结果定位。
- Test lane：检查并实现 C3-P2 验收闸门，覆盖自动化测试和真实浏览器证据。
- Main coordinator：维护分支、计划、冲突整合、最终测试、项目记忆和提交。

## PR1 File Map

- Modify: `datalogue-api/app/schemas/agentscope_workbench.py`
  - 增加 Workbench 状态摘要 schema，例如 `WorkbenchStatusSummary`。
- Modify: `datalogue-api/app/services/workbench_view_model.py`
  - 生成 thread-level 状态、actionability、latest artifact/ref 摘要。
- Modify: `datalogue-api/tests/test_workbench_view_api.py`
  - 覆盖状态摘要、Artifact 脱敏、legacy 只读和 retry action 状态。
- Modify: `datalogue-web/src/components/workbench-panel.jsx`
  - 增加状态摘要、空态、失败诊断摘要、Artifact detail drawer 和 retry 后结果定位。
- Modify: `datalogue-web/src/components/workbench-panel.test.jsx`
  - 覆盖 Panel 产品化状态、详情抽屉、安全脱敏和 retry 刷新。
- Modify: `datalogue-web/src/components/workbench-route.jsx`
  - 确认隐藏 route 复用同一 Panel，不做第二套状态逻辑。
- Modify: `docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md`
  - 补 C3-P2 PR1 验收记录。
- Modify: `.codex/project-memory.md`
  - 记录完成情况、验证命令和残留风险。

## Task 1: Backend Workbench Status Summary

**Files:**
- Modify: `datalogue-api/app/schemas/agentscope_workbench.py`
- Modify: `datalogue-api/app/services/workbench_view_model.py`
- Modify: `datalogue-api/tests/test_workbench_view_api.py`

- [ ] Write failing backend tests for thread-level status summary.

Expected cases:

```python
def test_workbench_thread_view_exposes_status_summary_for_completed_thread(...):
    view = build_workbench_thread_view(db, thread_id="as_completed")
    assert view.status_summary.status == "completed"
    assert view.status_summary.actionable is False
    assert view.status_summary.primary_artifact_ref.startswith("artifact:")

def test_workbench_thread_view_exposes_retryable_failed_state(...):
    view = build_workbench_thread_view(db, thread_id="as_failed")
    assert view.status_summary.status == "failed"
    assert view.status_summary.actionable is True
    assert view.status_summary.retry_checkpoint_ref.startswith("checkpoint://")

def test_legacy_workbench_thread_view_is_read_only(...):
    view = build_workbench_thread_view(db, thread_id="conv_25")
    assert view.status_summary.status == "read_only"
    assert view.status_summary.actionable is False
```

- [ ] Extend `agentscope_workbench.py` with `WorkbenchStatusSummary`.

Required fields:

```python
class WorkbenchStatusSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    label: str
    tone: str = "neutral"
    actionable: bool = False
    read_only: bool = False
    latest_message_id: str | None = None
    primary_artifact_ref: str | None = None
    retry_checkpoint_ref: str | None = None
    trace_ref: str | None = None
    summary: str | None = None
```

Add `status_summary: WorkbenchStatusSummary | None = None` to `WorkbenchThreadView`.

- [ ] Build status summary in `workbench_view_model.py`.

Rules:

- Latest assistant `running` -> `status="running"`, `tone="pending"`, `actionable=False`.
- Latest assistant `completed` -> `status="completed"`, `tone="success"`, `actionable=False`.
- Latest assistant `failed` or `interrupted` with checkpoint -> `status` same as message, `tone="warning"`, `actionable=True`.
- `conv_*` legacy -> `status="read_only"`, `tone="neutral"`, `read_only=True`, `actionable=False`.
- Never include SQL/schema/raw rows/query_plan/field_patch in summary or payload.

- [ ] Run backend targeted tests.

```bash
cd datalogue-api
python3 -m pytest tests/test_workbench_view_api.py tests/test_workbench_retry_actions.py -q
python3 -m py_compile app/schemas/agentscope_workbench.py app/services/workbench_view_model.py
```

## Task 2: Frontend Productized Panel States

**Files:**
- Modify: `datalogue-web/src/components/workbench-panel.jsx`
- Modify: `datalogue-web/src/components/workbench-panel.test.jsx`

- [ ] Write failing frontend tests for status summary UI.

Expected cases:

- Completed thread shows a compact success state and primary artifact ref.
- Running thread shows processing state and keeps polling.
- Failed or interrupted thread shows retryable state and checkpoint-based retry action.
- Legacy thread shows read-only state and no retry button.
- Empty thread shows a clear empty state without throwing.

- [ ] Implement status summary rendering.

Implementation notes:

- Use `view.status_summary` when available.
- Fall back to latest message status for backward compatibility.
- Keep text sanitized with `safeText`.
- Do not expose hidden payload keys even if backend accidentally returns them.

- [ ] Run frontend targeted tests.

```bash
cd datalogue-web
npm run test -- src/components/workbench-panel.test.jsx
```

## Task 3: Artifact Detail Drawer And Result Focus

**Files:**
- Modify: `datalogue-web/src/components/workbench-panel.jsx`
- Modify: `datalogue-web/src/components/workbench-panel.test.jsx`
- Modify: `datalogue-web/src/components/workbench-route.jsx`

- [ ] Write failing tests for Artifact detail drawer.

Expected cases:

- Clicking `artifact:*` opens a drawer-like detail area with sanitized summary.
- Drawer shows related trace/checkpoint refs when provided.
- Drawer hides raw SQL, schema, raw rows, query_plan and field_patch text.
- `initialArtifactRef` opens the same detail view through hidden route.

- [ ] Implement detail drawer using existing `fetchWorkbenchArtifact()`.

Rules:

- Reuse Workbench Panel state; do not create route-specific parsing logic.
- Keep the drawer inside the Panel surface.
- Prefer business labels over internal artifact kinds.
- Show non-artifact refs as disabled reference chips only.

- [ ] Run route and panel tests.

```bash
cd datalogue-web
npm run test -- src/components/workbench-panel.test.jsx src/components/workbench-route.test.jsx
```

## Task 4: C3-P2 Acceptance Gate

**Files:**
- Modify: `datalogue-api/tests/test_c3_workbench_acceptance.py`
- Modify: `datalogue-web/src/components/chat-page.test.jsx`
- Modify: `docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md`

- [ ] Add or extend acceptance tests for three paths.

Paths:

- Successful `as_*` BI question: Chat answer, Workbench status completed, primary artifact ref exists.
- Failed/interrupted retry: Workbench retry action goes through `/chat/stream`, events include `retry.checkpoint_restored -> answer.completed`, Panel refreshes completed.
- Legacy `conv_*`: read-only view, no retry execution, no fabricated ArtifactCard.

- [ ] Run minimum C3-P2 gate.

```bash
cd datalogue-api
python3 -m pytest tests/test_c3_workbench_acceptance.py tests/test_workbench_view_api.py tests/test_workbench_retry_actions.py tests/test_event_envelope.py tests/test_agentscope_event_projection.py -q

cd ../datalogue-web
npm run test -- src/components/workbench-panel.test.jsx src/components/workbench-route.test.jsx src/components/chat-page.test.jsx src/assistant/workbench-api.test.js
npm run lint
npm run build

git diff --check
```

- [ ] Run real browser gate when local services are available.

Manual evidence to record:

- Page click: Chat right Panel retry button.
- Network/SSE: `POST /api/workbench/actions/retry`, `POST /api/chat/stream`.
- Event sequence: `retry.checkpoint_restored -> answer.completed`.
- Panel refresh: failed/running -> completed.
- Observability: same `trace_id` is visible through `/api/observability/traces/{trace_id}`; Langfuse UI requires login if browser lacks access.
- Persistence: `query_artifact` and AgentScope mirror refs contain the same artifact/checkpoint/trace refs.

## C3-P2 Release Checklist

> 本 checklist 是 C3-P2 Workbench 发布前闸门。自动化项必须在 PR 合入前通过；人工项只记录真实核对结论，不用浏览器登录状态伪造成通过。

### 1. 数据源容器依赖

- [ ] 本地 PostgreSQL 可用，API 能连接主业务库。
  - 通过条件：`datalogue-api` 启动后无 `localhost:5432` connection refused；Workbench API、observability API 能正常读写。
  - 失败判定：如果 `/api/workbench/actions/retry` 返回 500 且日志为数据库连接拒绝，先恢复 PostgreSQL/OrbStack，不先改业务代码。
- [ ] 真实业务 MySQL 数据源可用。
  - 通过条件：`retail_test_mysql` 或当前验收数据源容器为 running，`localhost:3306` 正常监听。
  - 失败判定：如果 retry 主链进入数据查询但真实数据源不可达，只能记为环境未满足，不能声称业务 retry completed。
- [ ] 数据集 seed 与 checkpoint 上下文匹配。
  - 通过条件：发布前浏览器 retry 使用的 failed sample 具备 `dataset_id`、原始问题、`checkpoint://.../query_context_ready` 和可恢复业务上下文。

### 2. 本地服务端口

- [ ] API 服务运行在 `http://127.0.0.1:8000` 或明确记录的替代端口。
  - 建议命令：`cd datalogue-api && uvicorn app.main:app --reload --port 8000`。
  - 核对点：真实浏览器 Network 中 `/api/workbench/*` 和 `/api/chat/stream` 指向同一 API 端口。
- [ ] Web 服务运行在 `http://127.0.0.1:5173` 或明确记录的替代端口。
  - 建议命令：`cd datalogue-web && npm run dev -- --host 127.0.0.1`。
  - 核对点：如果 Vite 自动切到 `5174/5180`，验收记录必须写真实 URL，避免页面和 API worktree 不一致。
- [ ] Observability 服务可选运行。
  - Langfuse 默认 `http://localhost:3000`；未来 OTel collector 端口以实际 adapter 配置为准。
  - 自动化只要求 `/api/observability/traces/{trace_id}` 返回 provider-neutral contract；UI 登录核对是人工 checklist，不阻塞无 UI 权限的自动化闸门。

### 3. 浏览器 Retry 手工闸门

- [ ] 真实浏览器打开 Chat 右侧 Workbench failed/interrupted 线程。
  - 通过条件：Panel 显示失败摘要、retry 可用性、checkpoint ref 和唯一可点击 `重试`。
- [ ] 点击 `重试` 后 Network 出现 `POST /api/workbench/actions/retry`。
  - 通过条件：响应 `accepted=true`，`run_request` 只包含 `question/conversation_id/thread_id/dataset_id/retry_checkpoint_ref/display_text` 等业务恢复字段。
- [ ] 前端继续发起 `POST /api/chat/stream`。
  - 通过条件：SSE 或后端日志出现 `retry.started`、`retry.checkpoint_restored`、`dataset.query.completed`、`retry.completed`、`answer.completed`。
- [ ] Workbench Panel 从 failed/running 刷新到 completed。
  - 通过条件：`status_summary.status=completed`，primary artifact ref 与最终 payload、AgentScope refs 一致。
- [ ] 页面安全扫描不泄露执行面字段。
  - 禁止用户可见层出现 raw SQL、raw rows、schema、query_plan、field_patch、direct_sql、llm_sql。

### 4. 自动化 Harness

- [ ] 后端 C3-P2 acceptance gate。

```bash
cd datalogue-api
python3 -m pytest tests/test_c3_workbench_acceptance.py -q
```

- [ ] Observability provider-neutral contract gate。

```bash
cd datalogue-api
python3 -m pytest tests/test_observability.py -q
```

- [ ] Workbench API/action/event 回归。

```bash
cd datalogue-api
python3 -m pytest tests/test_workbench_view_api.py tests/test_workbench_retry_actions.py tests/test_event_envelope.py tests/test_agentscope_event_projection.py tests/test_retry_checkpoint.py -q
```

- [ ] 前端 Workbench/Chat 回归。

```bash
cd datalogue-web
npm run test -- src/components/workbench-panel.test.jsx src/components/workbench-route.test.jsx src/components/chat-page.test.jsx src/components/artifact-card.test.jsx src/assistant/chat-adapter.test.js src/assistant/thread-list-adapter.test.js src/assistant/workbench-api.test.js
npm run lint
npm run build
```

- [ ] 静态检查。

```bash
git diff --check
git diff | rg -n "raw_rows|raw_result|query_plan|field_patch|schema|SELECT|direct_sql|llm_sql|sql\\b"
```

允许命中范围：安全正则、测试断言、文档中明确说明禁止暴露的语句。

### 5. 旧会话只读策略

- [ ] `conv_*` / 数字旧会话只读展示。
  - 通过条件：Workbench Panel 显示 read-only/legacy notice，不展示可执行 retry。
- [ ] 旧会话不迁移、不回填、不伪造 `as_*` mirror。
  - 通过条件：旧会话 artifact detail 可读但带 thread scope；没有新 AgentScope running message 被创建。
- [ ] `as_*` route 不调用旧 `GET /api/conversation/{id}` 恢复数据集。
  - 通过条件：浏览器 console 无旧会话 422，数据集上下文只来自 Workbench View Model 和 Chat 主链 payload。

### 6. Workbench Route 隐藏策略

- [ ] `/workbench/:threadId/:artifactRef?` 继续作为隐藏 route。
  - 通过条件：route 可复用同一 Workbench Panel 和 artifact drawer，但不在导航、菜单、公开入口中暴露。
- [ ] 隐藏 route 不实现第二套业务状态逻辑。
  - 通过条件：状态、artifact 权限、retry action 都走与 Chat 右侧 Panel 相同的 API 和组件。
- [ ] 不开放独立 Workbench 页面发布口径。
  - 通过条件：发布说明中只说 Chat 右侧 Workbench Panel；独立 Workbench 正式入口留到后续阶段。

### 7. Observability 发布口径

- [ ] 自动化闸门使用 provider-neutral contract。
  - 通过条件：`/api/observability/traces/{trace_id}` 返回 `observability_contract.name=workbench_retry_v1` 且 `passed=true`。
  - 必要事件：`workbench.retry_requested -> retry.started -> retry.checkpoint_restored -> dataset.query.completed -> answer.completed`。
  - 必要 refs：`thread_id/conversation_id/checkpoint_ref/artifact_ref/trace_id` 对齐。
- [ ] Langfuse UI 人工核对保留为发布前 checklist。
  - 通过条件：有登录权限时，用同一 `trace_id` 打开 UI 并核对关键 observation；无权限时记录未完成，不把后端 API 成功写成 UI 通过。
- [ ] OTel 切换边界明确。
  - 通过条件：未来只替换 provider adapter；发布 harness 和前端只依赖 `observability_contract`，不依赖 Langfuse 内部字段名。

## Final Review Gate

- [ ] Safety scan diff for leaks.

```bash
git diff | rg -n "raw_rows|raw_result|query_plan|field_patch|schema|SELECT|direct_sql|llm_sql|sql\\b"
```

Expected allowed matches only:

- Safety regexes.
- Test assertions proving forbidden text is hidden.
- Documentation statements that explicitly say those details are not exposed.

- [ ] Update `.codex/project-memory.md`.
- [ ] Confirm C3-P2 Release Checklist has an owner/status for every item.
- [ ] Commit on `codex/c3-p2-workbench-productization`.
- [ ] Open or merge PR according to current branch policy.
