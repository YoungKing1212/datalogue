# 2026-07-02 Agentic Shell 统一任务入口验证记录

## 范围

- 新增 `POST /api/agentic-shell/tasks/stream`，作为 Chat UI、Workbench retry/action 和数据集试问的统一流式执行入口。
- 删除 `/api/chat/stream` HTTP route，不再保留公开兼容转发入口。
- 新增 `AgenticShellTask` 真相源、AgentScope/legacy event projection、运行时 task lifecycle 和 Workbench `task_request`。
- 前端统一消费 Datalogue Event Envelope，不直接依赖 AgentScope SDK 原始事件。

## 验证命令

### 后端回归

```bash
cd datalogue-api && python3 -m pytest \
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

结果：`32 passed, 2 warnings`

### 前端单测

```bash
cd datalogue-web && npx vitest run \
  src/assistant/agentic-shell-task-api.test.js \
  src/assistant/agentic-shell-event-adapter.test.js \
  src/assistant/chat-adapter.test.js \
  src/components/workbench-panel.test.jsx \
  src/components/chat-page.test.jsx
```

结果：`5 passed (5), 49 passed (49)`

### 前端构建

```bash
cd datalogue-web && npm run build
```

结果：构建通过，`built in 616ms`；保留既有 Vite chunk size warning。

### 前端 lint

```bash
cd datalogue-web && npm run lint
```

结果：通过，`0 errors, 13 warnings`；warnings 为既有 unused/react-hooks 类问题。

### 硬切搜索

```bash
rg -n "/api/chat/stream|@router\.post\(\"/stream\"\)|streamChatEvents\(|streamChat\(" \
  datalogue-api/app datalogue-api/tests datalogue-web/src
```

结果：只剩允许项：

- `datalogue-web/src/api/client.js` 中旧入口下线说明和主动抛错 helper。
- `datalogue-api/tests/test_agentic_shell_chat_stream_removed.py` 中删除旧 route 的回归测试。

## 安全边界

- 用户可见事件不暴露 SQL、schema、raw rows、DSL、query_plan、repair patch 或 tool input。
- `LegacyWorkflowTaskRunner` 仅作为迁移期内部执行适配器，服务于新 task runtime；不保留旧 HTTP route。
- Workbench retry 返回 `AgenticShellTaskRequest.task_request`，前端不再从 Workbench 直接调用旧 chat stream。

## 未执行项和残留风险

- 本次未做真实浏览器页面验收；后续如要发布前确认，需要打开 `/chat` 和 Workbench retry 跑一次真实页面链路。
- BI 执行体仍由 `LegacyWorkflowTaskRunner` 临时承接，完整 DatasetAgent AgentScope-owned stream run、Report/Python/Audit agent 仍是后续任务。
- Vite chunk size warning 和 13 个 lint warning 是既有问题，未在本次入口切换中处理。
