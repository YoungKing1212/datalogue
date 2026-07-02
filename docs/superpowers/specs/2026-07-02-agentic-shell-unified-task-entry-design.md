# Agentic Shell 统一任务入口设计规格

## 1. 背景

当前 Datalogue 已经完成 BI LeadAgent K1/K2/K3：后端 handoff、页面原型、AgentScope native handoff、真实成功链路都已经闭环。现有 `Agentic Shell` 也已经具备契约、registry、工具白名单、上下文投影和输出清洗能力。

但当前主问数入口仍然带有明显的旧链路痕迹：

- Chat UI 的历史主入口是 `/api/chat/stream`。
- `DatalogueAgenticShell.run_turn()` 目前只是先生成 Shell 契约，再委托旧 `stream_delegate` 执行。
- Workbench retry/action 仍围绕旧 chat stream 恢复链路和 thread view 投影。
- LangGraph / legacy runner 仍是部分主链执行依赖，只能按 strangler 迁移，不能再被误认为目标 runtime。

本设计的目标是把主语切换为 `AgenticShellTask`：Chat UI 和 Workbench 都围绕同一个任务运行视图工作，AgentScope 负责主运行时，Datalogue 负责业务真相源、稳定事件协议、artifact/checkpoint/trace refs 和审计闭环。

## 2. 目标态

新增唯一主执行入口：

```text
POST /api/agentic-shell/tasks/stream
```

所有新的 Chat 主问数、Workbench 执行动作、retry、后续 Report/Python/Audit 任务都从这个入口创建 `AgenticShellTask`。

目标态链路：

```text
Chat UI / Workbench / BI LeadAgent Panel
  -> AgenticShellTaskRequest
  -> /api/agentic-shell/tasks/stream
  -> Agentic Shell Task Runtime
      -> 创建 Datalogue task 真相源
      -> 选择 Agent
      -> 投影安全上下文
      -> 创建 AgentScope session/message
      -> 发送 AgentScope UserMsg
      -> 消费 AgentScope reply_stream() events
      -> 投影 Datalogue Event Envelope
      -> 写入 refs / task 状态 / trace / Workbench view
  -> SSE 返回稳定 envelope
```

`/api/chat/stream` 从执行链路中删除。完成态不允许它转发到新入口，也不允许它直接或间接进入旧 runtime。若实现过程中为排查漏迁调用临时保留结构化废弃错误 guard，该 guard 只能返回错误，不能执行、不能转发，且不能作为最终主链验收口径。

## 3. 非目标和硬边界

第一阶段不是一次性删除所有旧 graph 文件，也不是立刻启用所有可选 Agent。第一阶段只完成主入口 ownership 替换。

非目标：

- 不在第一阶段启用 `query_multiple_datasets`。
- 不在第一阶段启用 Report/Python/Audit 的真实执行能力。
- 不把前端或 DB 绑定到 AgentScope Python SDK 对象结构。
- 不把 SQL、schema、DSL、raw rows、repair patch body、候选资产详情暴露给 Agentic Shell 上下文、SSE、Workbench 或 API response。
- 不让 `/api/chat/stream` 继续承担任何执行职责。

硬边界：

- AgentScope Message/Event 是内部运行时事实。
- Datalogue Event Envelope 是外部稳定协议。
- Datalogue DB、artifact store、checkpoint refs、observability contract 是业务审计真相源。
- LegacyWorkflowAdapter 只能作为过渡执行器，不拥有新主入口语义。

## 4. 阶段拆分

### 4.1 第一阶段：新主入口和 Runtime spine

第一阶段必须交付：

- 新增 `/api/agentic-shell/tasks/stream`。
- 新增 `AgenticShellTaskRequest`、`AgenticShellTask`、task event envelope。
- Chat UI 直接调用新入口。
- Workbench retry/action 直接调用新入口。
- `/api/chat/stream` 从执行路径中移除。
- 新 SSE 事件能同时支撑 Chat answer 和 Workbench running/completed/failed/refs。
- 新链路的真实页面、后端日志、DB refs、trace、最终 answer 能用同一个 `task_id` 对齐。

### 4.2 第二阶段：BI 执行迁入 AgentScope-owned runtime

第二阶段把 BI 执行本体收进 AgentScope-owned DatasetAgent run。旧 LangGraph / runner 能删除的删除，不能删除的降为 `LegacyWorkflowAdapter`。

第二阶段完成后，BI 主链不应再以 LangGraph 为中心解释执行生命周期。

### 4.3 第三阶段：扩展 Agent 生态并清理旧主链

第三阶段启用 Report/Python/Audit 等可选 Agent，并清理旧入口、旧测试名和旧文档入口。清理必须以当前代码引用和真实验收证据为准，不能重写历史验收事实。

## 5. 核心对象

### 5.1 AgenticShellTaskRequest

`AgenticShellTaskRequest` 是所有执行入口的统一请求 DTO。

建议字段：

```text
task_source: "chat" | "workbench" | "bi_lead_agent_panel" | "api"
task_type: "bi_query" | "report" | "python_analysis" | "audit"
question: string
dataset_id: number | null
conversation_id: number | null
session_id: string | null
thread_id: string | null
retry_checkpoint_ref: string | null
artifact_ref: string | null
user_confirmation: object | null
client_context: object
```

安全要求：

- `client_context` 只能携带 UI 状态、动作来源、轻量选择项。
- 禁止携带 SQL、schema、DSL、raw rows、repair patch、候选资产详情。
- Workbench retry 必须携带 `retry_checkpoint_ref`，不能伪造成普通 chat message。

### 5.2 AgenticShellTask

`AgenticShellTask` 是 Datalogue 服务端任务真相源。

建议字段：

```text
task_id: string
task_source: string
task_type: string
status: "created" | "running" | "completed" | "failed" | "cancelled"
selected_agent: string
parent_task_id: string | null
agent_scope_session_id: string | null
thread_id: string | null
message_id: string | null
trace_id: string | null
artifact_refs: string[]
checkpoint_refs: string[]
created_at: datetime
updated_at: datetime
```

`AgenticShellTask` 不等同于 AgentScope Message。AgentScope Message 是运行时通信单元；`AgenticShellTask` 是 Datalogue 对外审计、Workbench 聚合和前端状态的业务单元。

## 6. AgentScope Message/Event 使用方式

内部运行时使用 AgentScope 2.0 原生对象：

- `UserMsg` 作为用户任务输入。
- `agent.reply_stream(UserMsg(...))` 作为主运行流。
- `RequireExternalExecutionEvent` 表达外部工具执行请求。
- `ExternalExecutionResultEvent` 回填外部工具结果。
- `ToolResultBlock` 表达安全工具结果块。

映射关系：

```text
AgenticShellTaskRequest
  -> AgenticShellTask
  -> AgentScope UserMsg
  -> AgentScope reply_stream() AgentEvent
  -> Datalogue Event Envelope
  -> SSE / Workbench / DB refs / trace
```

禁止将 AgentScope Python 类名、对象 dump 或 SDK 内部结构作为前端和 DB 查询协议。SDK 版本变化只能影响 adapter，不能影响 Chat UI、Workbench 和审计查询。

## 7. Datalogue Event Envelope

新入口对外只输出 Datalogue 稳定 envelope。

第一版事件族：

```text
task.started
task.completed
task.failed
task.cancelled

agent.selected
agent.handoff.started
agent.handoff.completed
agent.handoff.failed

message.delta
message.completed

tool.external_required
tool.result
tool.blocked

checkpoint.created
artifact.ready
trace.updated
```

每个 envelope 至少包含：

```text
event_type
visibility
task_id
trace_id
thread_id
message_id
selected_agent
payload
legacy_payload
```

`legacy_payload` 只允许作为迁移期字段，用于承接尚未完全改造的 Chat/Workbench view model。主协议必须使用 task/agent/tool/message/artifact/checkpoint 语义。

安全要求：

- `user_visible` 事件不能包含 SQL、schema、DSL、raw rows、repair patch body。
- `trace_only` 事件仍必须过滤凭据、连接串、私有原始结果。
- `control_plane` 事件只用于内部状态机，不直接进入用户可见 UI。

## 8. Chat UI 和 Workbench 的关系

Chat UI 和 Workbench 是同一个 `AgenticShellTask` 的两个视角。

```text
AgenticShellTask
  ├─ Chat UI 视角：用户提问、流式回答、最终 answer
  └─ Workbench 视角：运行态、tool/agent 事件、checkpoint、artifact、retry
```

Chat UI 负责：

- 创建 `task_source=chat` 的任务。
- 展示 `message.delta`、`message.completed`、`task.completed`。
- 使用 `task_id` 关联会话、最终 answer 和 trace。

Workbench 负责：

- 展示同一个 task 的 running/completed/failed。
- 展示 `agent.*`、`tool.*`、`checkpoint.created`、`artifact.ready`。
- 基于 `retry_checkpoint_ref` 创建新的 `task_source=workbench` 任务。
- 不再通过历史 thread 假消息触发模型。

## 9. 入口删除策略

完成态必须满足：

- Chat UI 不再调用 `/api/chat/stream`。
- Workbench 不再直接或间接调用 `/api/chat/stream`。
- 后端不再提供 `/api/chat/stream` 执行 route。
- 任何旧 `streamChatEvents` 调用都必须迁到 `streamAgenticShellTask` 或删除。
- `rg "/chat/stream"` 只允许命中迁移说明、历史文档或明确废弃测试，不允许命中执行路径。

如果第一阶段实现为了查漏保留废弃错误 guard，错误码必须固定为：

```text
CHAT_STREAM_REMOVED_USE_AGENTIC_SHELL_TASKS
```

该 guard 只能返回错误，不允许转发到新入口，也不允许调用旧 runtime。

## 10. 错误处理

新入口失败时，以 task 为主语返回安全失败事件：

```text
task.failed
agent.handoff.failed
tool.blocked
```

失败 payload 允许字段：

- `task_id`
- `trace_id`
- `checkpoint_ref`
- `artifact_ref`
- `error_code`
- `error_summary`
- `status_reason`
- `retryable`

失败 payload 禁止字段：

- SQL
- schema
- DSL
- raw rows
- physical table/field detail
- repair patch body
- tool internal payload
- model provider credential detail

AgentScope runtime 异常时，必须写入 task 失败状态和可追踪 refs。Workbench 应展示失败诊断和可恢复动作，而不是让前端停在 running。

## 11. 回滚与安全降级

本设计不允许回滚到 `/api/chat/stream` 执行链路。

允许的降级方式：

- 配置关闭新入口执行能力，返回 `task.failed` + `AGENTIC_SHELL_TASKS_DISABLED`。
- AgentScope runtime 初始化失败时，返回 `task.failed` + 安全摘要。
- DatasetAgent 子运行失败时，返回 `agent.handoff.failed`，并保留 checkpoint/ref。
- 工具权限拒绝时，返回 `tool.blocked`，并记录 control-plane 原因。

降级必须可被 `task_id + trace_id + checkpoint_ref/artifact_ref` 串起来排查。

## 12. 验收标准

后端验收：

- `/api/agentic-shell/tasks/stream` 能创建 task 并返回 SSE envelope。
- `/api/chat/stream` 不再进入任何执行 runtime。
- AgentScope `UserMsg/reply_stream()` 事件能投影成 Datalogue envelope。
- `RequireExternalExecutionEvent` 能投影为 `tool.external_required`。
- `ExternalExecutionResultEvent/ToolResultBlock` 能投影为 `tool.result`。
- 失败路径返回 `task.failed`，并过滤内部执行态。

前端验收：

- Chat UI 发起问数只请求 `/api/agentic-shell/tasks/stream`。
- Workbench retry/action 只请求 `/api/agentic-shell/tasks/stream`。
- Chat UI 能展示流式回答和最终 answer。
- Workbench 能展示同一 task 的 running/completed/failed、artifact、checkpoint、retry。

真实链路验收：

- 浏览器 Network 中没有 `/api/chat/stream` 执行请求。
- 后端日志、DB task、AgentScope event/ref、trace、最终 answer 使用同一个 `task_id` 对齐。
- artifact 落库后，Workbench 能通过 `artifact_ref` 打开。
- checkpoint 出现后，Workbench retry 能创建新的 task。
- 安全扫描确认 SSE/API response 不含 SQL/schema/DSL/raw rows/repair patch body。

## 13. 测试建议

后端测试：

- `test_agentic_shell_task_api.py`
- `test_agentic_shell_task_runtime.py`
- `test_agentic_shell_event_projection.py`
- `test_agentic_shell_chat_stream_removed.py`
- `test_workbench_agentic_task_actions.py`

前端测试：

- `agentic-shell-task-api.test.js`
- `chat-page-agentic-task.test.jsx`
- `workbench-agentic-task-actions.test.jsx`

真实验收：

- 启动后端和前端。
- 在 Chat UI 提问并确认只命中新入口。
- 在 Workbench 触发 retry 并确认只命中新入口。
- 对照 Network、后端日志、DB refs、trace、artifact、最终 answer。

## 14. 文档与迁移清理

实施完成后需要同步更新：

- `docs/上下文入口.md`
- `.codex/project-memory.md`
- OpenAPI / API 使用说明
- Workbench/Chat 相关测试报告

清理 `/api/chat/stream` 相关文档时，只删除当前入口指引；历史验收事实保留在历史记录中，不重写过去的证据。
