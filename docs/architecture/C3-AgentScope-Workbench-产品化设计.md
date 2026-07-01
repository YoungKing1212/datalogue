# C3 AgentScope Workbench 产品化设计

## 1. 阶段目标

C3 的目标是把 B-first / C-ready 智能问数能力推进到可感知的 BI 工作台产品形态。

第一阶段不替换现有 Chat 入口，而是在 Chat 内增加 Workbench 右侧详情面板，并预留独立 `/workbench` 页面路由。新 Chat 会话开始使用 Datalogue 本地 AgentScope-compatible Session / Message / Event mirror 作为会话流、消息流和工作台事件流的回放与审计真相源；Datalogue 继续负责 QueryGraph、RepairPatch、Artifact、权限、审计和 SQL 编译执行。

阶段定位：

> C3 Workbench / mirror 是 AS-R0 的 foundation，不是 AgentScope Runtime ownership 完成态。C3 由本地 AgentScope-compatible mirror 管新会话、消息、事件和回放外壳；Datalogue 仍管问数业务 runtime、业务裁决和业务真相源。

AS-R0 的后续迁移会由 Datalogue Agentic Shell 接管主链 Runtime：P0 只建立 Shell Contract 与 Tool Boundary，不替换 `/chat/stream`；P1 才开始让 AgentScope Runtime 驱动 BI 主链；P2 再收敛 legacy runtime 和扩展其他业务 Agent。

## 2. 已确认决策

### 2.1 产品主线

C3 主线选择 BI 工作台产品化。

不继续优先扩展 RepairPatch 错误类型，也不在 P0 让 AgentScope runner 接管工作台 Agent。RepairPatch 能力扩展和 AgentScope runner 深接入作为后续阶段预留。

### 2.2 工作台入口

采用混合入口：

- P0：Chat 内右侧 Workbench Panel。
- P0：新增隐藏路由 `/workbench/:threadId/:artifactRef?`，先不放主导航。
- 后续：稳定后升级为正式独立 BI 工作台页面。

### 2.3 AgentScope 接入深度

采用 Datalogue 本地 AgentScope-compatible Session / Message Bridge。

AgentScope-compatible mirror 模型承接：

- 新会话 session。
- 新消息流。
- 工作台事件流。
- Workbench Panel 回放。
- 未来 AgentScope runtime / runner 的接入口。

本阶段不启动 AgentScope runner，不让 AgentScope 接管 `/chat/stream` 主链，不让 AgentScope 生成 SQL，不让 AgentScope 读取 schema、raw result、query_plan 或 trace-only metadata。

### 2.4 新会话回放与审计来源

新 Chat 会话以本地 AgentScope-compatible mirror 为 session/message/event 的回放与审计真相源。

这只改变 C3 会话、消息、事件和 Workbench 视图的持久化外壳，不改变 Datalogue 主链 Runtime ownership。旧 Datalogue conversation 不再作为新会话消息主源，只作为旧会话回放、兼容镜像和业务执行快照的承接位置。

### 2.5 AS-R0 迁移闸门

C3 到 AS-R0 的迁移必须满足以下闸门：

- P0 阶段只能新增 Datalogue Agentic Shell 契约、Agent Registry、Policy / Tool Whitelist、Context Projection、Output Sanitizer 和 BI atomic tool provider 边界。
- P0 不替换 `/chat/stream` 主链，不把 Workbench retry 改为 Shell action，不启动真实 AgentScope runner。
- P1 才允许把 `/chat/stream` 收缩为 HTTP/SSE 兼容壳，并委托 `DatalogueAgenticShell.run_turn()`。
- P1 的 DatasetAgent 只能生成 DSL，最终 SQL 只能在 `compile_dsl_to_sql` / `execute_compiled_query` 等受控 tool 内部流转。
- P2 才收敛 legacy `_stream_chat`、`AgentScopeShellAdapter` 和 `BIWorkbenchTool(ask_bi)`，并逐个启用 ReportAgent / PythonAgent / AuditAgent。
- 未经正式计划文档审核，不允许把 P1/P2 能力提前计入 P0 完成。

### 2.6 旧会话策略

旧会话只读回放作为 smoke path：

- `/chat/28` 继续兼容，解析为 `conv_28`。
- `/chat/conv_28` 是旧会话显式 thread id。
- 不迁移旧会话。
- 不为旧会话伪造 AgentScope session。
- 旧 ArtifactCard 和历史消息照常回放。

旧会话继续追问不作为 C3-P0 主路径。页面提示用户转为新工作台会话，创建新的 `as_*` session。

旧转新只允许带业务级摘要和 refs：

- `legacy_conversation_id`
- 旧会话标题
- 最近成功 `artifact_ref`
- `confirmed_dataset_id`
- 业务级 task summary
- 可选 `trace_ref`
- 可选 `checkpoint_ref`

禁止带入 SQL、schema、字段名、表名、raw rows、query_plan、DSL、RepairPatch patch body、trace-only metadata 和完整 `last_success_task`。

## 3. 总体架构

```text
User
  -> Chat page
      -> thread_id resolver
          -> as_* : AgentScope-compatible mirror session
          -> conv_* : legacy conversation readonly replay
      -> Workbench Panel
          -> Workbench View Model API
              -> AgentScope mirror tables
              -> query_artifact / Artifact API
              -> trace refs / checkpoint refs
              -> Datalogue event projection
  -> send message
      -> agentscope_message(user, completed)
      -> agentscope_message(assistant, running)
      -> Datalogue main chain
          -> LeadAgent capability route
          -> DatasetAgent / QueryGraph
          -> SQL compiler / dialect guard / execution
          -> SQL audit / RepairPlan / RepairPatch
          -> Artifact / refs / trace
      -> agentscope_event projection
      -> agentscope_ref projection
      -> agentscope_message(assistant, completed | failed | interrupted)
```

## 4. Thread ID 规则

前端和 API 统一使用 `thread_id`。

```text
conv_<conversation_id>        旧 Datalogue conversation
as_<agentscope_session_id>    新 AgentScope-compatible session
```

兼容规则：

- `/chat/:number` 继续支持，自动解析为 `conv_<number>`。
- 新建会话默认生成 `as_*`。
- Thread list 内部统一展示 `thread_id`。
- 未来 Workbench 页面使用 `/workbench/:threadId/:artifactRef?`。

## 5. 本地 AgentScope Mirror 数据模型

C3-P0 新增四张本地 mirror 表。它们是 AgentScope-compatible session/message/event/ref 的本地实现，也是后续接真实 AgentScope runtime 的审计、回放和兜底层。它们不保存主链执行权，也不表示 AgentScope 已经接管 Datalogue Runtime。

### 5.1 agentscope_session

职责：

- 保存新 Chat / Workbench thread 主体。
- 生成统一 `thread_id = as_<session_id>`。
- 保存 session 状态。
- 保存 runtime 类型。
- 关联旧会话 continuation。

核心字段：

```text
id
thread_id
runtime_type                  local_mirror | agentscope_runtime
status                        active | archived | failed
title
user_id
workspace_id
legacy_conversation_id
business_context_summary
created_at
updated_at
metadata_public
metadata_internal
```

`metadata_public` 只保存业务级摘要。`metadata_internal` 不进入普通用户 payload，并且不得保存 raw SQL、raw rows 或完整 schema。

### 5.2 agentscope_message

职责：

- 保存新 Chat 消息流。
- 表达 user / assistant / system / workbench message。
- 支持 running / completed / failed / interrupted 状态。
- 承载 lease / heartbeat。

核心字段：

```text
id
session_id
message_id
role                          user | assistant | system | workbench
status                        running | completed | failed | interrupted
turn_index
content_public
summary_public
lease_expires_at
heartbeat_at
owner
recoverable
error_code
error_summary_public
created_at
updated_at
metadata_public
metadata_internal
```

普通用户视图只读取 `content_public`、`summary_public`、状态和业务级 metadata。

### 5.3 agentscope_event

职责：

- 保存工作台事件流。
- 承接 `DatalogueEventEnvelope` 的 AgentScope-style projection。
- 支持 timeline、RepairPatch、Artifact action、candidate confirmation 和 retry 回放。

核心字段：

```text
id
session_id
message_id
event_id
event_type
status
sequence
payload_public
diagnostic_summary
created_at
metadata_internal
```

`payload_public` 禁止包含 SQL、schema、字段名、表名、raw rows、query_plan、DSL、RepairPatch patch body 和 trace-only metadata。

### 5.4 agentscope_ref

职责：

- 保存 session/message/event 与业务对象的引用关系。
- 支撑 Workbench Panel、受控 retry、五件套验收和未来独立 Workbench 页面。

核心字段：

```text
id
session_id
message_id
event_id
ref_type                      artifact | trace | task | repair_plan | checkpoint | legacy_conversation | report | export | agentscope_runtime
ref_value
role                          primary | related | source | retry_source | continuation_source
visibility                    user | admin | internal
created_at
metadata_public
metadata_internal
```

## 6. 写入顺序

新 Chat 消息采用“先写本地 AgentScope-compatible mirror message，再执行 Datalogue 主链”。

流程：

1. 用户发送消息。
2. 创建或读取 `agentscope_session`。
3. 写入 `agentscope_message(role=user, status=completed)`。
4. 写入 `agentscope_message(role=assistant, status=running)`。
5. 写入 `agentscope_event(type=message.received)`。
6. 调用 Datalogue 主链。C3 阶段这里仍是 legacy Datalogue runtime，不是 AgentScope Runtime。
7. 主链阶段事件投影为 `agentscope_event`。
8. Artifact、trace、repair、checkpoint refs 写入 `agentscope_ref`。
9. 成功时 assistant message 更新为 `completed`。
10. 失败时 assistant message 更新为 `failed`。
11. 中断或 lease 过期时 assistant message 更新为 `interrupted`。

## 7. Datalogue 主链边界

Datalogue 主链指当前智能问数业务执行链：

- `/chat/stream` 入口与 task / trace 创建。
- LeadAgent capability route。
- 候选数据集确认。
- DatasetAgent / QueryGraph / DSL / query plan。
- SQL 编译、方言适配、权限和安全门禁。
- SQL 执行。
- SQL Audit / RepairPlan / RepairPatch。
- query_artifact / ArtifactCard / refs。
- DatalogueEventEnvelope。
- Langfuse observation 和后端 checkpoint 日志。

C3 不重写这条业务执行链。AgentScope-compatible mirror 只成为新会话、消息、事件、refs 和工作台回放的审计真相源。

## 8. Lease / Timeout

assistant running message 创建时写入：

```text
status = running
lease_expires_at = now + 5min
heartbeat_at = now
owner = current_request_id
recoverable = true
```

主链每个关键阶段更新 `heartbeat_at` 并写入事件。

请求内失败：

- assistant message 更新为 `failed`。
- 写 `agentscope_event(type=message.failed)`。
- 保存业务级失败摘要。
- 不暴露 SQL、schema、raw rows 或 query_plan。

请求中断或服务崩溃：

- 页面加载或下一次请求时检查 `lease_expires_at`。
- 过期 running message 标记为 `interrupted`。
- 前端展示“任务中断，可重试”。
- C3-P0 不自动 resume，只支持用户手动 retry。

## 9. Workbench View Model API

C3-P0 提供后端 view model，前端不自行拼装底层 session/message/event/artifact 数据。

### 9.1 GET /api/workbench/thread/{thread_id}

返回当前 thread 的工作台视图。

支持：

- `as_*` 新 AgentScope mirror session。
- `conv_*` 旧 Datalogue conversation 只读回放视图。
- `/chat/:number` 的 legacy 兼容解析。

返回内容：

- thread summary
- messages
- task timeline
- workbench timeline
- artifact cards
- repair summary
- action states
- disabled reasons
- admin diagnostic summary

### 9.2 GET /api/workbench/artifact/{artifact_ref}

返回 Artifact 详情视图。

包含：

- Artifact preview
- primary ref
- related refs
- action states
- repair summary
- diagnostic summary

普通用户只返回业务级信息。管理员可返回脱敏诊断摘要。

### 9.3 POST /api/workbench/actions/retry

发起受控 retry。

请求只允许包含：

- `thread_id`
- `message_id`
- `checkpoint_ref`
- `action_id`

禁止前端传入：

- SQL
- schema
- table / field
- raw result
- query_plan
- DSL
- RepairPatch patch body

后端校验：

- message 状态必须是 `failed` 或 `interrupted`。
- `checkpoint_ref` 必须存在且属于当前 thread。
- 当前用户仍有 dataset / artifact / thread 权限。
- retry 未超过预算。
- checkpoint 不含对用户不可见的执行 payload。

retry 成功发起后：

- 创建新的 assistant running message。
- 写入 `action.retry_requested` event。
- 从 checkpoint 恢复 last safe state。
- 重新进入 Datalogue 主链。

## 10. Workbench Panel

P0 在 Chat 页面增加右侧 Workbench Panel。

触发入口：

- ArtifactCard。
- timeline 节点。
- RepairPatch 摘要。
- “查看详情”动作。

Panel 视图：

- 普通用户业务视图。
- 管理员诊断抽屉。

隐藏路由：

- `/workbench/:threadId/:artifactRef?`
- 先不放主导航。
- 复用 Workbench Panel / Workbench View 组件。

## 11. 普通视图与管理员诊断抽屉

### 11.1 普通用户视图

展示：

- 任务理解。
- 数据集匹配。
- 用户确认。
- 查询执行。
- RepairPatch 自动修复摘要。
- 结果产物。
- Artifact refs 的业务摘要。
- 可用动作和禁用原因。

禁止展示：

- SQL。
- schema。
- 字段名。
- 表名。
- raw rows。
- query_plan。
- DSL。
- trace-only metadata。
- RepairPatch patch body。

### 11.2 管理员诊断抽屉

展示脱敏诊断：

- event envelope 摘要。
- trace refs。
- task refs。
- artifact refs。
- failure class。
- repair status。
- checkpoint refs。
- action state。
- message/event 状态。
- lease / heartbeat / interrupted 信息。

仍然禁止展示：

- raw SQL。
- raw result。
- full schema。
- 未脱敏字段级 patch 主体。

## 12. Workbench Action

C3-P0 动作范围是只读 + 受控 retry。

只读动作：

- 查看 Artifact 详情。
- 查看 RepairPatch 摘要。
- 查看 trace refs。
- 打开管理员诊断抽屉。
- 查看 message/event 状态。
- 查看 action disabled reason。

受控 retry：

- 仅允许 `failed` 或 `interrupted` assistant message。
- 必须有合法 `checkpoint_ref`。
- 必须通过权限、预算和归属校验。
- retry 仍走 Datalogue 主链。
- 不允许自由编辑 SQL 或 query_plan。

保留禁用态：

- report。
- export。
- continue_edit。
- PythonAgent。
- AuditAgent。
- ReportAgent。
- 自由编辑 SQL。

## 13. 安全红线

用户可见 payload、Workbench View Model、SSE 顶层兼容字段、ArtifactCard、历史回放和前端状态均禁止出现：

- SQL / raw_sql / direct_sql / llm_sql。
- schema / full schema。
- 表名。
- 字段名。
- raw rows / raw result。
- query_plan。
- DSL。
- RepairPatch patch body。
- trace-only metadata。
- control-plane 内部对象。

管理员诊断抽屉只允许脱敏摘要和 refs，不开放 raw SQL、raw result、full schema 或字段级 patch 主体。

## 14. C3-P0 验收路径

### 14.1 新会话成功问数路径

必须覆盖：

- 新建 `as_*` thread。
- 写入 `agentscope_session`。
- 写入 user message。
- 写入 assistant running message。
- Datalogue 主链成功执行。
- 写入 assistant completed message。
- 写入 `agentscope_event`。
- 写入 `agentscope_ref`。
- Chat 内 Workbench Panel 展示 timeline + Artifact。
- 普通用户不暴露 SQL、schema、字段、raw rows 或 query_plan。
- 管理员诊断抽屉只展示脱敏诊断。

### 14.2 failed / interrupted + retry 路径

必须覆盖：

- 构造 failed 或 lease 过期 running message。
- 页面展示 interrupted / failed。
- 受控 retry 可用。
- 点击 retry 后创建新的 assistant running message。
- 写入 `action.retry_requested`。
- 后端从合法 `checkpoint_ref` 恢复。
- Datalogue 主链重新执行。
- 成功后写 completed message。
- refs 串联原 message、retry message、checkpoint、artifact 和 trace。

### 14.3 旧会话只读回放路径

必须覆盖：

- `/chat/28` 旧 URL 仍能打开。
- 自动解析为 `conv_28`。
- 不创建假的 AgentScope session。
- 旧 ArtifactCard 和历史消息照常回放。
- 旧会话继续追问提示转为新工作台会话。

## 15. 历史 C3 产品化拆分

以下 P0 / P1 / P2 是 C3 Workbench 产品化历史拆分，不作为 AS-R0 正式 PR plan 的分期依据。AS-R0 以后续正式计划为准：PR0 做 Shell Contract 与 Tool Boundary，PR1 才进入 AgentScope Runtime 驱动 BI 主链，PR2 收敛 legacy runtime 并扩展业务 Agent。

### P0：AgentScope Mirror + Chat Workbench Panel

- 新增四张 mirror 表。
- 实现 thread resolver。
- 实现新会话写入顺序。
- 实现 Lease / timeout。
- 实现 Workbench View Model API。
- 实现 Chat 右侧 Workbench Panel。
- 实现隐藏 `/workbench/:threadId/:artifactRef?` 路由。
- 实现只读 action + 受控 retry。
- 完成三条验收路径。

### P1：Workbench 产品体验增强

- 将隐藏路由升级为可访问的独立 Workbench 页面。
- 扩展 Artifact 详情视图。
- 增强管理员诊断抽屉。
- 补真实页面 retry 验收。
- 加强 action state 可视化。

### C3 后续：AgentScope Runtime 接入准备

- 为正式 AS-R0 P1 接真实 AgentScope runtime / runner 做准备。
- mirror 表作为审计、回放和兜底层。
- 评估 DatasetAgent / ReportAgent 的受控 runner 接入。
- 保持 Datalogue 业务内核真相源不变。
