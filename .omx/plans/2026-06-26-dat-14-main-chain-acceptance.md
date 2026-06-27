# DAT-14 P0 主链路五件套验收计划

## Requirements Summary

- 来源：DAT-14 / Task P2.1，目标是在 `b-first-c` 基线上建立 P0 主链路五件套验收。
- 范围文件：新增 `datalogue-api/tests/test_bi_main_chain_acceptance.py`，修改 `datalogue-api/tests/test_chat.py`，新增或修改 `datalogue-web/src/assistant/chat-adapter.test.js`，补充验收记录模板。
- 五件套必须能互相核对：页面/前端 metadata、SSE event envelope、后端日志 checkpoint、Langfuse/local trace、`query_artifact` / `conversation_state`。
- 旧会话缺少 ArtifactCard 时必须不回填、不伪造、不报错。

## Codebase Evidence

- SSE 节点名、状态输出字段、日志摘要由 `datalogue-api/app/api/chat.py:97`、`datalogue-api/app/api/chat.py:178`、`datalogue-api/app/api/chat.py:249` 定义。
- 主链路最终落库、artifact 反连、trace index 和 final SSE 输出集中在 `datalogue-api/app/api/chat.py:2755`、`datalogue-api/app/api/chat.py:2813`、`datalogue-api/app/api/chat.py:2823`、`datalogue-api/app/api/chat.py:2831`、`datalogue-api/app/api/chat.py:2865`。
- `QueryArtifact` 存储和 message_id 回填由 `datalogue-api/app/services/artifact_store.py:72`、`datalogue-api/app/services/artifact_store.py:139` 负责。
- 前端 final payload 到页面 metadata 的映射在 `datalogue-web/src/assistant/chat-adapter.js:420`，历史回放 metadata 映射在 `datalogue-web/src/assistant/thread-list-adapter.js`。
- 后端现有 SSE 测试辅助位于 `datalogue-api/tests/test_chat.py:57`。

## Acceptance Matrix

| 用例 | 触发方式 | 必须核对的证据 |
| --- | --- | --- |
| 单数据集问数成功 | 固定 `dataset_id`，SubAgent 返回 `query_plan -> sql_execute -> report_generator -> final` | `conversation_id`、`message_id`、`task_id`、`trace_id`、`result_ref`、`report_ref`、`candidate_assets`、`query_plan`、`step_trace`、`ObservabilityTraceIndex`、`QueryArtifact.message_id`、`conversation_state.last_success_task` |
| 低置信候选确认 | Manifest 路由返回 `ambiguous` / `clarify`，用户确认后继续 | route decision / clarification SSE、pending clarification state、确认后的 final 与同一 conversation 对齐 |
| 无法回答拒答 | `query_plan.query_type=unsupported` 或 `entry_route=reject` | final 不含伪造 SQL/artifact，response metadata 保留 reject reason，trace index 状态可查 |
| 受控失败 retry | SQL 执行触发 `sql_audit` / `should_retry` / `increment_retry` | SSE step 顺序含 retry 诊断，日志摘要保留 error，metadata 含 `sql_retry_trace` / `sql_diagnosis` |
| 历史回放 | 从历史 message `response_metadata` 构造前端 message | 有 artifact refs 时展示 ArtifactCard 入口；旧会话缺失 refs 时不补 ref、不报错、不伪造 ArtifactCard |

## Evidence Locations

- 后端自动化证据：`datalogue-api/tests/test_bi_main_chain_acceptance.py` 中的 acceptance record fixture / assertions。
- 前端自动化证据：`datalogue-web/src/assistant/chat-adapter.test.js` 覆盖 final metadata 与旧历史回放边界。
- 人工真实链路模板：`docs/main-chain-acceptance-record-template.md`，用于记录真实环境的 `conversation_id`、`task_id`、`trace_id`、`artifact_ref`、SSE 关键事件、后端 checkpoint、Langfuse observation、数据库状态。
- 临时运行日志如需保存放 `/private/tmp`，不写入仓库。

## Verification Steps

1. 先写后端/前端失败测试，运行目标测试确认 RED。
2. 最小实现或补测试辅助，运行目标测试确认 GREEN。
3. 运行后端目标集：`cd datalogue-api && pytest tests/test_bi_main_chain_acceptance.py tests/test_chat.py -q`。
4. 运行前端目标集：`cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js`。
5. 前端改动完成后运行：`cd datalogue-web && npm run lint && npm run build`。
6. 若依赖齐备，补充更宽回归：`cd datalogue-api && pytest tests/test_observability.py tests/test_artifact_api.py -q`。

## Failure Escalation Rules

- 测试环境或依赖缺失：记录精确命令、退出码、首个关键错误，不用大范围重跑掩盖根因。
- 观测字段缺失：先定位是 SSE envelope、message metadata、trace index、artifact store 还是前端映射断裂，再做最小修复。
- 真实 Langfuse 不可用：使用本地 trace index / no-op trace payload 证明主流程不阻塞，并在结果中列为残留风险。
- 若必须修改业务链路，保持变更局限在 chat/observability/artifact 映射边界，并用新增验收测试证明。

