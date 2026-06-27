# 主链路五件套验收记录模板

用途：记录真实环境 P0 主链路验收结果，自动化测试覆盖结构契约，真实链路验收补充运行时证据。

## 基本信息

- 验收时间：
- 环境：
- 用例类型：单数据集问数成功 / 低置信候选确认 / 无法回答拒答 / 受控失败 retry / 历史回放
- 问题：
- dataset_id：
- conversation_id：
- message_id：
- task_id / result_artifact.result_ref：
- trace_id：
- artifact_ref：

## SSE 关键事件

| 顺序 | type | node / route | status | 关键字段 |
| --- | --- | --- | --- | --- |
| 1 |  |  |  |  |

## 后端 Checkpoint

| checkpoint | 必须核对字段 | 实际值 |
| --- | --- | --- |
| wrapper_start | session_id / conversation_id / multiturn_enabled |  |
| trace_context_created | trace_id / session_id / active |  |
| lead_context_ready | route_decision / should_continue |  |
| subagent_query_plan | query_plan_type / execution_strategy / planner_source |  |
| assistant_message_saved | message_id / response_metadata_keys |  |
| final_payload_ready | conversation_id / message_id / trace_id / artifact_ref |  |

## Langfuse / 本地 Trace

- `observability_trace_index.langfuse_trace_id`：
- `observability_trace_index.message_id`：
- `observability_trace_index.status`：
- Langfuse observation 名称：
- Langfuse 不可用时的 no-op / 本地 trace 证据：

## 数据库状态

- `message.response_metadata.langfuse.trace_id`：
- `message.step_trace` 是否包含关键 node：
- `query_artifact.artifact_id`：
- `query_artifact.message_id`：
- `conversation_state.session_id`：
- `thread_state.last_success_task.result_ref`：

## 验收结论

- 通过 / 失败：
- 失败命令或日志：
- 失败升级规则：
