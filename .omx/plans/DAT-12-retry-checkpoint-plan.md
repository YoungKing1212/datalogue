# DAT-12 Retry Checkpoint 开发计划

## Requirements Summary

- 来源：`docs/architecture/B-first C-ready 正式开发计划.md` Task P1.4 与 issue DAT-12。
- 范围：`datalogue-api/app/services/conversation_store.py`、`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_retry_checkpoint.py`、`datalogue-web/src/components/artifact-card.jsx`、`datalogue-web/src/components/artifact-card.test.jsx`。
- 目标：支持第一阶段受控 retry，只通过 `checkpoint_ref` 恢复最后安全 checkpoint；恢复失败时降级整任务重试；不向前端暴露 graph node、SQL、schema、control_plane。

## Acceptance Criteria

- 后端只允许 `dataset_confirmed`、`query_context_ready`、`artifact_generation_failed` 三类 checkpoint。
- retry 校验覆盖 `user_id`、`conversation_id`、`task_id`、`permission_scope`、`expires_at`。
- retry 请求对外只需要 `retry_checkpoint_ref`；前端 ArtifactCard 的 retry action 只发送 `checkpoint_ref`。
- SSE 输出 `retry.started`、`retry.checkpoint_restored`、`retry.fallback_to_whole_task`、`retry.completed`、`retry.failed`。
- 聚焦验证通过：`datalogue-api/tests/test_retry_checkpoint.py`、`datalogue-api/tests/test_chat.py`、`npm run test -- artifact-card`。

## Implementation Steps

1. 后端 RED：新增 `tests/test_retry_checkpoint.py`，覆盖 checkpoint 注册/恢复、权限或过期失效、非法 kind 降级、stream retry 事件。
2. 存储实现：在 `ConversationStore` 的 `_thread` 状态中维护 `retry_checkpoints`，新增注册、恢复、降级 helper；checkpoint payload 只保存安全恢复上下文和业务引用。
3. Chat 协议：给 `ChatRequest` 增加 `retry_checkpoint_ref`；在 `_stream_chat` 包装层抢锁后执行 retry 恢复，恢复成功时改写 `dataset_id/question/multiturn_context`，恢复失败时发送 fallback 事件并按原问题整任务重试。
4. Final 写回：在 `_persist_completed_turn` 中按 final payload 的安全状态注册 checkpoint，并把 `checkpoint_ref` 放进 final payload/response metadata 的 llm-visible 区域供前端 action 使用。
5. 前端 RED/GREEN：新增 `ArtifactCard` 和测试，渲染 ArtifactCard 的可见字段；retry 按钮触发 `datalogue:artifact-action` 事件，detail 只包含 `{ actionType: "retry", checkpointRef }`。
6. 回归验证：运行指定后端 pytest 与前端 Vitest；如失败先定位原因，再最小修复。

## Risks And Mitigations

- 风险：checkpoint 中误带 SQL/schema/control_plane。缓解：集中清洗 `context`，测试断言 JSON 中不含敏感关键词。
- 风险：过期或权限错误 checkpoint 导致 retry 静默失败。缓解：恢复函数返回结构化 `fallback_reason`，SSE 明确输出 fallback 或 failed 事件。
- 风险：现有 chat 流式测试依赖旧 ChatRequest。缓解：新增字段为可选，默认不改变旧路径。

## Verification Steps

- `cd datalogue-api && .venv/bin/python -m pytest tests/test_retry_checkpoint.py -q`
- `cd datalogue-api && .venv/bin/python -m pytest tests/test_chat.py -q`
- `cd datalogue-web && npm run test -- artifact-card`
