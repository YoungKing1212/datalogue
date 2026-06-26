# 2026-06-26 B-first C-ready 主链路五件套验收记录

用途：记录 B-first C-ready P0 主链路在当前集成分支上的可执行验收结果。本文档区分“自动化可重复证据”和“真实页面 / Langfuse 手工补录项”，避免把测试替身误记为生产链路证据。

## 基本信息

- 验收时间：2026-06-26 21:20
- 集成分支：`integration/b-first-c-core-chain`
- 用例类型：单数据集问数成功 / 低置信候选确认 / 无法回答拒答 / 受控失败 retry / 历史回放
- 自动化代表问题：`最近30日GMV趋势如何`
- 计划真实业务问题：`查询杨凯 2024 年工作日志`
- dataset_id：自动化 fixture `sample_dataset.id`
- conversation_id：由 `tests/test_bi_main_chain_acceptance.py` 运行时创建并和 message / trace 交叉断言
- session_id：`acceptance-success`
- task_id：final payload / event envelope 生成的主任务 ID
- trace_id：final payload `langfuse_trace_id` 与 `response_metadata.langfuse.trace_id` 一致
- artifact_ref：final payload `result_ref` / `report_ref` 与 `query_artifact.artifact_id` 一致

## 自动化验收结论

当前已完成可重复自动化验收，通过标准是同一轮问数能在 SSE、消息 metadata、trace index、query artifact 和 conversation_state 中互相核对。

| 验收面 | 证据 | 结果 |
| --- | --- | --- |
| API 主链路 / 观测 / Artifact | `cd datalogue-api && python3 -m pytest tests/test_bi_main_chain_acceptance.py tests/test_chat.py tests/test_observability.py tests/test_artifact_api.py -q` | 142 passed |
| 前端 Chat metadata | `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js` | 5 passed |
| Artifact refs / 旧会话 | `cd datalogue-api && python3 -m pytest tests/test_artifact_card_contract.py tests/test_legacy_conversation_replay.py tests/test_conversation.py tests/test_artifact_api.py -q` | 15 passed |
| 前端 ArtifactCard / 历史回放 | `cd datalogue-web && npm run test -- src/components/artifact-card.test.jsx tests/unit/assistant/artifact-custom.test.js src/assistant/chat-adapter.test.js` | 14 passed |
| 前端质量门禁 | `cd datalogue-web && npm run lint`；`cd datalogue-web && npm run build` | 通过，保留既有 15 个 lint warning 和 Vite chunk warning |
| 空白检查 | `git diff --check` | 通过 |

## SSE 关键事件

自动化成功用例通过 `_stream_chat()` 直接收集 SSE 事件，关键断言如下。

| 顺序 | type | node / route | status | 关键字段 |
| --- | --- | --- | --- | --- |
| 1 | step | `query_plan` | done | 出现在事件流中，证明 DatasetAgent 规划阶段进入主链 |
| 2 | step | `sql_execute` | done | 出现在事件流中，证明 QueryGraph 执行阶段进入主链 |
| 3 | final | `query_graph` | completed | `conversation_id`、`message_id`、`langfuse_trace_id`、`query_plan`、`candidate_assets`、`result_ref`、`report_ref` 可和落库记录互相核对 |

## 后端 Checkpoint

| checkpoint | 必须核对字段 | 当前自动化证据 |
| --- | --- | --- |
| wrapper_start | session_id / conversation_id / multiturn_enabled | `session_id=acceptance-success`，开启 `MULTITURN_ENABLED=True` |
| trace_context_created | trace_id / session_id / active | `langfuse_trace_id` 写入 final 与 message metadata |
| lead_context_ready | route_decision / should_continue | 成功用例 `decision=selected` 且 `should_continue=True`；低置信用例 `decision=ambiguous` 且不 build graph |
| subagent_query_plan | query_plan_type / execution_strategy / planner_source | `metric_query / query_graph / deterministic` |
| assistant_message_saved | message_id / response_metadata_keys | final `message_id` 等于 message 表 assistant 记录 ID |
| final_payload_ready | conversation_id / message_id / trace_id / artifact_ref | final、message metadata、trace index、query artifact 交叉一致 |

## Langfuse / 本地 Trace

- `observability_trace_index.langfuse_trace_id`：与 final `langfuse_trace_id` 一致。
- `observability_trace_index.message_id`：与 final `message_id` 和 assistant message ID 一致。
- `observability_trace_index.status`：成功链路为 completed；低置信 / 拒答为 blocked；受控失败为 failed。
- Langfuse observation 名称：本轮未启动真实 Langfuse 页面核验，自动化使用 `LANGFUSE_ENABLED=False` 验证 no-op / 本地 trace index 兜底。
- Langfuse 手工补录项：启动本地 API 与前端后，用真实问题 `查询杨凯 2024 年工作日志` 核对 Langfuse UI 中同一 `trace_id` 的 observation 链路。

## 数据库状态

| 数据面 | 当前自动化证据 |
| --- | --- |
| `message.response_metadata.langfuse.trace_id` | 等于 final `langfuse_trace_id` |
| `message.step_trace` | 包含 `query_plan`、`sql_execute` 等关键节点 |
| `query_artifact.artifact_id` | 包含 final `result_ref` 和 `report_ref` |
| `query_artifact.message_id` | 等于 final `message_id` |
| `conversation_state.session_id` | `acceptance-success` |
| `thread_state.last_success_task.result_ref` | 等于 final `result_artifact.result_ref` |
| `conversation_state.facts.artifact_refs` | DAT-17 已用 artifact refs 持久化测试覆盖，旧会话不迁移、不回填 |

## 前端页面状态

- Chat adapter 已能把 final SSE 的 `result_ref`、`report_ref`、`langfuse_trace_id`、`observability`、`stepTrace` 映射进页面 metadata。
- `artifact_card`、`primary_ref`、`related_refs` 只来自后端真实 payload；历史回放缺少 ArtifactCard 时只展示原回答，不伪造卡片。
- 候选数据集确认卡只提交 `candidate_id / checkpoint_ref / selected_dataset_id / selected_text`，不提交 schema、字段、SQL 或资产细节。
- 手工补录项：本轮未启动浏览器做真实页面截图；需要在后续本地服务联调时补同一 `task_id / trace_id / artifact_ref` 的页面截图或录屏证据。

## 低置信与不可回答边界

- 低置信候选：`test_low_confidence_candidate_confirmation_records_clarification_without_artifacts` 验证 `entry_route=ambiguous`，不构建 graph，不产生 SQL / SQL result / artifact。
- 不可回答拒答：`test_unsupported_question_rejects_without_fabricating_artifacts` 验证导出类问题停在 reject，不伪造 `result_ref/report_ref`。
- 受控失败 retry：`test_controlled_failure_retry_keeps_diagnosis_and_does_not_fabricate_sql_result` 验证失败诊断和 retry trace 保留，失败结果不伪造成查询结果。

## 验收结论

- 自动化主链路验收：通过。
- 协议与持久化验收：通过。
- 真实页面 / Langfuse UI 手工验收：未在本轮执行，需在本地服务启动后补录。
- 发布前闸门：只有完成真实问题 `查询杨凯 2024 年工作日志` 的页面 Chat、SSE/event envelope、后端日志 checkpoint、Langfuse trace、query_artifact / conversation_state 五件套一致性记录后，才能把 DAT-18 标为完整通过。
