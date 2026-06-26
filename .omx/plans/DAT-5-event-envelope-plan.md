# DAT-5 DatalogueEventEnvelope 与 SSE 映射开发计划

## Requirements Summary

- 新增 `datalogue-api/app/schemas/bi_workbench.py`，定义统一 `DatalogueEventEnvelope`，让现有 `/api/chat/stream` SSE 和未来 AgentScope event stream 能复用同一批业务事件。
- 保持现有 SSE payload 的 `type` 与业务字段不变，仅追加 `event_envelope`，避免现有前端流式体验退化。
- 支持事件类型：`route.started`、`dataset.selected`、`clarification.required`、`dataset.query.started`、`dataset.query.completed`、`artifact.created`、`answer.completed`、`error.blocked`。
- 支持可见性：`user_visible`、`trace_only`、`control_plane`。
- `user_visible` envelope 不能包含 raw SQL、完整结果集、schema、capsule 或 control_plane 主体。
- 观测字段需要能关联 `conversation_id`、`message_id`、`trace_id`、`dataset_id`、`route_decision`、`entry_route` 等稳定排障字段。

## Current Code Facts

- `datalogue-api/app/api/chat.py` 的 `_sse_data()` 是 SSE JSON 序列化入口，可保持旧 payload 原样序列化。
- `_lead_agent_event()` 和 `_route_decision_event()` 负责 LeadAgent/路由事件；`gateway_step_payload` 负责 message gateway step。
- 正常查询 final 在 `final_payload` 构造后通过 `_sse_data(final_payload)` 发出；早退分支由 `_early_route_return()` / `_interpret_early_return()` 构造 final。
- `datalogue-api/app/schemas/bi_workbench.py` 当前不存在，本任务需要新增。
- 现有 `tests/test_chat.py` 已有 `_collect_stream_events()`、`_find_event()` 和 `_stream_chat` 近真实测试，可复用验证 SSE 兼容性。

## Decisions

- `event_type`：使用独立 envelope 字段，不覆盖旧 `type` 字段；旧 `type` 继续服务现有前端，`event_type` 服务新 AgentScope 语义事件。
- `visibility`：构建器默认按事件语义选择，用户可见事件用 `user_visible`；仅排障用 `trace_only`；未来控制面事件保留 `control_plane`，但本次不把控制面主体下发为 user-visible。
- SSE 兼容策略：每条需要映射的旧 SSE payload 追加 `event_envelope`，顶层旧字段保持不变。前端若未识别新字段可以忽略。
- 观测字段：envelope 包含 `event_id`、`event_type`、`visibility`、`created_at`、`payload`、`metadata`。`metadata` 存稳定索引字段，`payload` 存清洗后的用户可见摘要。
- 安全清洗：构建器对 `user_visible` payload/metadata 递归移除 `sql`、`raw_sql`、`sql_result`、`rows`、`records`、`schema`、`capsule`、`control_plane` 等字段，并用 SQL 关键词正则拦截疑似 SQL 字符串。

## Implementation Steps

1. 新增 `app/schemas/bi_workbench.py`：
   - 定义 `DatalogueEventType`、`DatalogueEventVisibility`、`DatalogueEventEnvelope`。
   - 提供 `build_datalogue_event_envelope()` 与 `sanitize_event_payload()`，集中处理事件 ID、时间戳和 user_visible 清洗。
2. 修改 `app/schemas/__init__.py`：
   - 导出 envelope 相关类型和构建函数。
3. 修改 `app/api/chat.py`：
   - 引入 envelope 构建函数。
   - 新增 `_with_event_envelope()` 和小型 mapper，给路由、查询开始/完成、artifact、answer、error/clarification 等 SSE payload 追加 envelope。
   - 不移除任何旧顶层字段。
4. 新增 `tests/test_event_envelope.py`：
   - 验证 schema 支持全部 event_type/visibility。
   - 验证 user_visible 不泄露 raw SQL、结果行、schema、capsule、control_plane。
   - 验证旧 SSE payload 字段保留且含 `event_envelope`。
5. 补充 `tests/test_chat.py` 针对 `/chat/stream` 代表路径的断言：
   - 正常 final 有 `answer.completed`。
   - route event 有 `dataset.selected` 或阻断分支有 `error.blocked`。

## Acceptance Criteria

- 新测试 `tests/test_event_envelope.py` 通过。
- 目标回归 `tests/test_chat.py` 通过或至少 issue 相关聚焦用例通过；若全量耗时或环境阻塞，记录阻塞原因和已跑用例。
- 任一 `user_visible` envelope 中不含 raw SQL、完整结果集、schema、capsule、control_plane 主体。
- 旧 SSE payload 的 `type`、`answer`、`sql`、`sql_list`、`response_metadata` 等字段不因 envelope 改造被删除或改名。

## Risks and Mitigations

- 风险：清洗规则过严导致用户可见摘要过少。缓解：只清洗高风险字段，保留 dataset、answer、route、artifact ref 等摘要。
- 风险：旧前端依赖顶层字段。缓解：仅追加字段，不改变旧 payload。
- 风险：查询执行中间节点较多，逐点映射可能过大。缓解：本任务先覆盖业务事件关键节点，保留未来 AgentScope 扩展入口。

## Verification Steps

- `pytest tests/test_event_envelope.py`
- `pytest tests/test_chat.py`
- 如全量 `test_chat.py` 受环境耗时影响，至少运行新增/改动相关的 `test_chat.py` 聚焦用例并说明未覆盖范围。
