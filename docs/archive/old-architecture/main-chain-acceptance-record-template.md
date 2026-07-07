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
- trace_id（历史记录可填；当前可为空）：
- artifact_ref：

## SSE 关键事件

| 顺序 | type | node / route | status | 关键字段 |
| --- | --- | --- | --- | --- |
| 1 |  |  |  |  |

## 后端 Checkpoint

| checkpoint | 必须核对字段 | 实际值 |
| --- | --- | --- |
| wrapper_start | session_id / conversation_id / multiturn_enabled |  |
| runtime_context_created | session_id / thread_id / active |  |
| lead_context_ready | route_decision / should_continue |  |
| subagent_query_plan | query_plan_type / execution_strategy / planner_source |  |
| assistant_message_saved | message_id / response_metadata_keys |  |
| final_payload_ready | conversation_id / message_id / artifact_ref / workbench_thread_id |  |

## 运行证据

- SSE step 顺序：
- `response_metadata` 关键字段：
- Workbench thread / event / ref：
- 后端日志 checkpoint：
- 历史 trace_id（如旧记录存在）：

## 数据库状态

- `message.step_trace` 是否包含关键 node：
- `query_artifact.artifact_id`：
- `query_artifact.message_id`：
- `conversation_state.session_id`：
- `thread_state.last_success_task.result_ref`：

## 验收结论

- 通过 / 失败：
- 失败命令或日志：
- 失败升级规则：
