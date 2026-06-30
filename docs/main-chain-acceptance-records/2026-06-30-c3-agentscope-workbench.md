# 2026-06-30 C3 AgentScope Workbench 验收记录

## 基本信息

- 测试日期：2026-06-30
- 分支：`b-first-c`
- 基线 commit：`3ace2283`
- PR6 commit：当前提交，使用 `git log -1 --oneline` 查看；本记录不自嵌 hash，避免 amend 后 hash 变化。
- 验收范围：C3-P0 AgentScope mirror、Chat Session Bridge、Workbench View Model API、受控 retry、Chat 右侧 Workbench Panel、隐藏 Workbench route。

## 路径 A：新会话成功问数

- 自动化用例：`datalogue-api/tests/test_c3_workbench_acceptance.py::test_new_chat_stream_creates_agentscope_workbench_view`
- 问题：`查询杨凯 2024 年工作日志`
- thread_id：自动断言 `as_*`
- task_id：`task-c3-path-a`
- trace_id：`trace-c3-path-a`
- artifact_ref：测试运行时由 `ArtifactStore.put_json()` 生成 `artifact:<uuid>`
- SSE/event envelope：stub stream 依次发出 `task.started -> answer.completed`，并通过 `_stream_chat` 进入 AgentScope bridge。
- AgentScope mirror 证据：断言存在 `agentscope_session`、user completed message、assistant completed message、`task.started/answer.completed` 两条 user-visible event，以及 primary artifact ref。
- Workbench API 证据：`GET /api/workbench/thread/{as_*}` 返回 `read_only=false`、timeline、primary artifact ref 和业务级消息摘要。
- 安全证据：final payload 与 Workbench View Model 均递归扫描，不包含 `sql/schema/raw_rows/raw_result/query_plan/field_patch` 等执行面字段。

## 路径 B：中断 + 受控 retry

- 自动化用例：`datalogue-api/tests/test_c3_workbench_acceptance.py::test_interrupted_workbench_thread_can_request_controlled_retry`
- thread_id：`as_ffffffff-ffff-ffff-ffff-ffffffffffff`
- message_id：测试运行时生成的过期 running assistant message id
- checkpoint_ref：`checkpoint://c3-acceptance`
- lease recovery 证据：`run_lease_recovery()` 将过期 running message 标为 `interrupted`，写入业务级中断提示和 checkpoint ref。
- retry 证据：带 `sql` 的 retry payload 返回 `400`；只带 `thread_id/message_id/checkpoint_ref/selected_action` 的 payload 返回 accepted，并创建新的 assistant running message。
- event/ref 证据：mirror 写入 `workbench.retry_requested` event，并为新 running message 记录 checkpoint ref。
- 安全证据：retry response 与 Workbench View Model 递归扫描，不包含执行面字段。

## 路径 C：旧会话只读回放

- 自动化用例：`datalogue-api/tests/test_c3_workbench_acceptance.py::test_legacy_conversation_workbench_view_is_read_only_without_mirror`
- legacy conversation id：`250`
- thread_id：`conv_250`
- Workbench API 证据：`GET /api/workbench/thread/conv_250` 返回 `read_only=true`，保留旧消息摘要，不创建 ArtifactCard。
- retry 证据：`POST /api/workbench/actions/retry` 对 `conv_*` 返回 `accepted=false` 和只读禁用原因。
- mirror 证据：断言 legacy view/retry 期间 `agentscope_session` 数量不增加，不伪造 AgentScope session。

## 前端验收覆盖

- `datalogue-web/src/assistant/thread-list-adapter.test.js`
  - `datalogue:thread-resolved` 后本地 draft thread remap 到 `as_*`。
  - `DatalogueThreadListAdapter.fetch()` 对 `as_*` 读取 Workbench View Model。
  - Workbench View Model 消息转换为 assistant-ui history，并保留 artifact refs。
- `datalogue-web/src/components/chat-page.test.jsx`
  - `/chat/as_<uuid>` 使用 `as_*` 作为 Workbench Panel source。
  - `/chat/25` 解析为 `conv_25` legacy read-only source。
  - route 优先于 runtime remote id，避免会话切换时 Panel 跟随旧 thread。
- `datalogue-web/src/components/workbench-panel.test.jsx`
  - Panel 展示业务级消息、timeline、refs、禁用 action reason。
  - 旧会话 notice 只读展示。
  - artifact 详情读取只展示摘要，不展示 SQL/schema/raw rows。

## 验证命令

```bash
cd datalogue-api
python3 -m pytest tests/test_c3_workbench_acceptance.py -q
```

结果：`3 passed`。

```bash
cd datalogue-web
npm run test -- src/assistant/thread-list-adapter.test.js src/components/chat-page.test.jsx src/components/workbench-panel.test.jsx src/assistant/workbench-api.test.js
```

结果：`4 passed / 22 passed`。

## 五件套状态

- 页面 Chat / Workbench Panel：已补真实浏览器 E2E。`/chat` 提交 `查询杨凯 2024 年工作日志` 后先出现候选数据集确认，点击 `生产经营管理系统日志数据集` 后同一 legacy conversation 继续生成查询结果；主 Chat 显示最终回答和 Artifact refs，右侧 Workbench Panel 从第一轮 failed mirror 切到第二轮 completed mirror。
- SSE/event envelope：由 `_stream_chat` stub 事件进入真实 AgentScope bridge，覆盖 `task.started -> answer.completed`。
- 后端日志/checkpoint：真实浏览器 E2E 通过 DB 状态补证，`conversation_id=31`、`thread_id=as_60b44ad7-cd95-4b2e-a765-c2e82e189c2d`、`trace_id=22b163778f0bbdb422c691997ae6eb60`、`checkpoint_ref=checkpoint://conv-31-msg-74/query_context_ready`。
- Langfuse：本次未打开 Langfuse UI；C3-P0 只验证 mirror 与 Workbench，不新增 Langfuse observation 语义。
- query_artifact / conversation_state / AgentScope mirror：真实浏览器 E2E 生成 `primary_ref=artifact:e1c094ea0d2242a681345f70a2404284`、`report_ref=artifact:5d40ec7b33b04ab199b8d3dc3b46f53f`，AgentScope mirror refs 中记录 result/report/trace/checkpoint；C3 新真相源以 `agentscope_session/message/event/ref` 为准。

## 真实浏览器补证

- 测试入口：`http://127.0.0.1:5173/chat`
- API：`http://127.0.0.1:8000`
- 问题：`查询杨凯 2024 年工作日志`
- 路由行为：第一轮 `no_match`，页面展示候选 `生产经营管理系统日志数据集`，未直接执行 SQL；候选确认后继续 `conversation_id=31`。
- AgentScope mirror：
  - 第一轮候选 thread：`as_d3d041ee-864b-482e-ab27-6f1b5cc720c6`，assistant `failed`，events 为 `error.blocked`，refs 只包含 trace。
  - 第二轮完成 thread：`as_60b44ad7-cd95-4b2e-a765-c2e82e189c2d`，assistant `completed`，events 包含 `dataset.selected` 和 `answer.completed`。
- 结果 refs：`artifact:e1c094ea0d2242a681345f70a2404284`、`artifact:5d40ec7b33b04ab199b8d3dc3b46f53f`、`trace:22b163778f0bbdb422c691997ae6eb60`、`checkpoint://conv-31-msg-74/query_context_ready`。
- 页面证据：主 Chat 最终回答可见，包含“杨凯2024年全年共登记 100条 工作日志”；右侧 Workbench Panel 显示 `助手 · completed`、同一 artifact/trace/checkpoint refs，且无 `只读` 提示。
- 隐藏 Workbench route：`/workbench/as_60b44ad7-cd95-4b2e-a765-c2e82e189c2d/artifact%3Ae1c094ea0d2242a681345f70a2404284` 可打开，显示 completed 消息、产物详情和同一 refs，非只读。
- 旧会话回放：`/chat/25` 显示 Workbench `只读` notice，回放历史消息和 artifact refs，不迁移、不回填、不伪造新 mirror。
- 浏览器安全扫描：真实页面未命中 `SELECT`、`query_plan`、`raw_result`、`schema_summary`、`field_patch`；console error/warn 为空。
- 本轮发现并修复：
  - 新会话 final 后右侧 Panel 未切到 `as_*`，已修复为 `/chat` route-less 场景接受最新 AgentScope mirror。
  - 候选阻断事件投影时 `bound_schema_version` 触发 mirror payload 泄露拦截，已修复为通用 user-visible payload 递归裁剪内部键后再 fail-closed。

## 残留风险

- 本次已补真实浏览器页面、SSE/mirror、DB refs 和旧会话/隐藏路由证据；仍未打开 Langfuse UI 做人工核对。
- retry action 当前只创建新的 running message 并记录 checkpoint/event，不在 PR6 内直接驱动真实 Datalogue 主链重跑；后续需要把 checkpoint restore 与 Workbench action 编排打通。
