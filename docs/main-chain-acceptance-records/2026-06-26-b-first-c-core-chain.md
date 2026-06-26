# 2026-06-26 B-first C-ready 主链路五件套验收记录

用途：记录 B-first C-ready P0 主链路在当前集成分支上的可执行验收结果。本文档区分“自动化可重复证据”和“真实页面 / Langfuse 手工补录项”，避免把测试替身误记为生产链路证据。

## 基本信息

- 验收时间：2026-06-26 21:20
- 集成分支：`integration/b-first-c-core-chain`
- 用例类型：单数据集问数成功 / 低置信候选确认 / 无法回答拒答 / 受控失败 retry / 历史回放
- 自动化代表问题：`最近30日GMV趋势如何`
- 计划真实业务问题：`查询杨凯 2024 年工作日志`
- 真实补录时间：2026-06-27 00:12-00:26
- 真实补录分支：`codex/dat-18-five-piece-acceptance`
- 真实补录结论：页面回放、SSE/event envelope、Artifact API、`query_artifact` / `conversation_state` 已核对；Langfuse SDK 在本地后端未激活；真实业务 SQL 因数据集语义映射错误受控失败。
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

## 2026-06-27 真实链路补录

本次补录启动本地服务后，用真实问题 `查询杨凯 2024 年工作日志` 验证页面、SSE、Artifact、DB 状态和本地 trace 的一致性。

| 验收面 | 证据 | 结果 |
| --- | --- | --- |
| 后端服务 | `uvicorn app.main:app --reload --port 8000`，`GET /health` 返回 `{"status":"ok"}` | 通过 |
| 前端服务 | `cd datalogue-web && npm run dev`，访问 `http://localhost:5173/chat/16` | 通过 |
| 首次真实请求 | `session_id=dat18-live-20260627`，`conversation_id=15`，`trace_id=dlg-45cf7e0a4c8a4be584302d6a2615378c` | 被 Manifest stale fail-closed 阻断，符合门禁 |
| Manifest 修复 | 发布 dataset 10 当前 Manifest，`manifest_version=v3`，`bound_schema_version=566389a4886bc384`，`review_status=current` | 通过 |
| 第二次真实请求 | `session_id=dat18-live-20260627-v2`，`conversation_id=16`，`message_id=34`，`task_id=conv-16-msg-34`，`trace_id=dlg-a85416ec39724384b5aa992a23641bb7` | 主链完成但业务 SQL 受控失败 |
| Artifact refs | `primary_ref=artifact:e668a634847a41a4b5489d11092da363`，`related_refs` 包含 trace 与 checkpoint | 通过 |
| Artifact API | `GET /api/artifacts/artifact:e668a634847a41a4b5489d11092da363` 返回 report artifact，关联 `conversation_id=16` / `message_id=34` | 通过 |
| DB 状态 | `query_artifact` 存在 `artifact:e668a634847a41a4b5489d11092da363`；`conversation_state.facts` 写入 `kind=artifact_refs`；本地 trace index 记录同一 `trace_id` | 通过 |
| 页面回放 | 直接打开 `/chat/16` 能看到历史问题、错误诊断回答、`BI 查询结果` ArtifactCard、`artifact:e668a634847a41a4b5489d11092da363` 和重试按钮 | 通过 |
| Langfuse | Langfuse 页面服务可达，但后端日志显示 `Langfuse SDK v4 初始化失败，已降级: No module named 'langfuse'` | 未完成，需补 SDK/环境后重验 |

真实业务请求的最终诊断为 `FIELD_NOT_FOUND`：SQL 生成引用了 `eas_personofile.create_time`，但真实数据源中该列不存在。当前链路能把失败诊断、ArtifactCard、trace/ref、checkpoint 和历史回放串起来；但这不是“业务查询成功”，语义资产需要修正后才能作为完整五件套通过证据。

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
- Langfuse observation 名称：自动化使用 `LANGFUSE_ENABLED=False` 验证 no-op / 本地 trace index 兜底；2026-06-27 手工补录时 Langfuse 页面服务可达，但后端 Python 环境缺少 `langfuse` SDK，真实 observation 未写入。
- Langfuse 后续补录项：补齐后端 SDK/环境后，用真实问题 `查询杨凯 2024 年工作日志` 或语义修复后的等价问题，核对 Langfuse UI 中同一 `trace_id` 的 observation 链路。

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
- 手工补录项：2026-06-27 已用 Playwright 直接打开 `/chat/16`，确认页面展示历史问题、错误诊断回答、`BI 查询结果` ArtifactCard、同一 `artifact_ref` 和重试按钮；截图只作为临时验收证据保存在 Playwright 输出目录，不写入仓库。

## 低置信与不可回答边界

- 低置信候选：`test_low_confidence_candidate_confirmation_records_clarification_without_artifacts` 验证 `entry_route=ambiguous`，不构建 graph，不产生 SQL / SQL result / artifact。
- 不可回答拒答：`test_unsupported_question_rejects_without_fabricating_artifacts` 验证导出类问题停在 reject，不伪造 `result_ref/report_ref`。
- 受控失败 retry：`test_controlled_failure_retry_keeps_diagnosis_and_does_not_fabricate_sql_result` 验证失败诊断和 retry trace 保留，失败结果不伪造成查询结果。

## 验收结论

- 自动化主链路验收：通过。
- 协议与持久化验收：通过。
- 真实页面手工验收：通过，已确认 `/chat/:id` 历史回放和 ArtifactCard 真实渲染。
- Langfuse UI 手工验收：未通过，当前后端环境缺少 `langfuse` SDK，只能验证本地 trace index 兜底。
- 真实业务查询成功验收：未通过，dataset 10 语义层错误引用不存在字段 `eas_personofile.create_time`，需要修正语义资产后重跑。
- 发布前闸门：DAT-18 可以作为“协议、页面回放、受控失败和本地持久化闭环”的证据；不能作为“真实业务成功查询 + Langfuse observation 完整五件套”的最终通过证据。
