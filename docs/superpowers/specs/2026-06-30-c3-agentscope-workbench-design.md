# C3 AgentScope Workbench 设计规格

## 1. 背景

B 阶段已经完成 capability manifest、event envelope、ask_bi、Artifact refs、候选确认、C-ready Chat Shell 和五件套验收基础。C1/C2 进一步完成 RepairPlan / RepairPatch 主链，当前 Datalogue 已具备可观测、可追溯、可受控修复的智能问数内核。

C3 的目标是把这些能力推进到更完整的 BI 工作台产品形态，同时开始真实引入 AgentScope Session / Message / Event 模型，承接新会话流和工作台事件流。

## 2. 阶段定位

C3 P0 定义为：

> AgentScope-compatible 新会话真相源 + Chat 内 Workbench Panel 产品化。

本阶段不做：

- 不让 AgentScope runner 接管 QueryGraph、RepairPatch 或 SQL 执行。
- 不开放 ReportAgent / PythonAgent / AuditAgent 真实链路。
- 不开放自由编辑 SQL。
- 不迁移旧会话。
- 不把旧 `conversation_state` 直接搬进 AgentScope Session。
- 不在普通用户界面展示 SQL、schema、表名、字段名、raw rows、query_plan 或 trace-only metadata。

## 3. 已确认决策

### 3.1 C3 主线

选择 BI 工作台产品化。

### 3.2 工作台入口

采用混合模式：

- 第一阶段做 Chat 右侧 Workbench Panel。
- 同时预留隐藏路由 `/workbench/:threadId/:artifactRef?`。
- 后续再升级成独立 BI 工作台页面。

### 3.3 AgentScope 接入

采用 Session / Message Bridge。

### 3.4 新会话真相源

新 Chat 会话使用 AgentScope Session 作为 session / message / event 真相源。

### 3.5 旧会话策略

旧会话只读回放，不迁移，不伪造 AgentScope session。旧会话继续追问时提示转为新的 `as_*` 工作台会话。

旧转新只带业务级摘要和 refs。

### 3.6 URL

统一 thread id：

```text
as_<session_id>        新 AgentScope-compatible session
conv_<conversation_id> 旧 Datalogue conversation
```

### 3.7 存储

Datalogue 本地新增 AgentScope mirror 表：

- `agentscope_session`
- `agentscope_message`
- `agentscope_event`
- `agentscope_ref`

### 3.8 写入顺序

新消息先写 AgentScope message，再执行 Datalogue 主链。

### 3.9 失败恢复

assistant running message 使用 Lease / timeout。

### 3.10 Workbench 面板

采用普通视图 + 管理员诊断抽屉。

### 3.11 Workbench Action

第一阶段只做只读 action + 受控 retry。

### 3.12 Workbench API

后端提供 Workbench View Model API，前端不自行拼接底层 session/message/event/artifact。

## 4. 核心概念

### 4.1 AgentScope Session

C3 的 AgentScope Session 是 Datalogue 本地实现的 AgentScope-compatible mirror。它是新 Chat 会话的 session/message/event 真相源，也是后续接真实 AgentScope runtime 的桥。

### 4.2 Datalogue 主链

Datalogue 主链是问数业务执行链，继续负责：

- LeadAgent 路由。
- 数据集确认。
- QueryGraph / DSL / query plan。
- SQL 编译和方言适配。
- 权限、manifest、dialect guard。
- SQL 执行。
- SQL Audit / RepairPlan / RepairPatch。
- query_artifact / Artifact refs。
- trace / Langfuse / 后端 checkpoint。

AgentScope Session 不接管这些业务裁决。

### 4.3 Workbench View Model

Workbench View Model 是前端工作台消费的统一 DTO，由后端从 mirror 表、query_artifact、trace refs 和 event projection 组装。

## 5. 数据模型

### 5.1 agentscope_session

用于保存新工作台会话。

字段建议：

- `id`
- `thread_id`
- `runtime_type`
- `status`
- `title`
- `user_id`
- `workspace_id`
- `legacy_conversation_id`
- `business_context_summary`
- `metadata_public`
- `metadata_internal`
- `created_at`
- `updated_at`

### 5.2 agentscope_message

用于保存新消息流。

字段建议：

- `id`
- `session_id`
- `message_id`
- `role`
- `status`
- `turn_index`
- `content_public`
- `summary_public`
- `lease_expires_at`
- `heartbeat_at`
- `owner`
- `recoverable`
- `error_code`
- `error_summary_public`
- `metadata_public`
- `metadata_internal`
- `created_at`
- `updated_at`

状态枚举：

- `running`
- `completed`
- `failed`
- `interrupted`

### 5.3 agentscope_event

用于保存工作台事件流。

字段建议：

- `id`
- `session_id`
- `message_id`
- `event_id`
- `event_type`
- `status`
- `sequence`
- `payload_public`
- `diagnostic_summary`
- `metadata_internal`
- `created_at`

### 5.4 agentscope_ref

用于保存 refs。

字段建议：

- `id`
- `session_id`
- `message_id`
- `event_id`
- `ref_type`
- `ref_value`
- `role`
- `visibility`
- `metadata_public`
- `metadata_internal`
- `created_at`

`ref_type` 第一阶段支持：

- `artifact`
- `trace`
- `task`
- `repair_plan`
- `checkpoint`
- `legacy_conversation`

预留：

- `report`
- `export`
- `agentscope_runtime`

## 6. API 契约

### 6.1 GET /api/workbench/thread/{thread_id}

返回 thread 级 Workbench View Model。

对 `as_*`：

- 读取 AgentScope mirror session。
- 返回 message stream。
- 返回 event timeline。
- 返回 refs。
- 返回 action states。

对 `conv_*`：

- 读取 legacy conversation。
- 返回只读回放 view。
- 不创建 AgentScope session。

### 6.2 GET /api/workbench/artifact/{artifact_ref}

返回 Artifact 详情 view。

普通用户返回：

- artifact summary。
- preview payload。
- primary ref。
- related refs。
- action states。
- disabled reasons。

管理员诊断抽屉额外返回：

- trace refs。
- task refs。
- failure class。
- repair status。
- checkpoint refs。
- lease / heartbeat / interrupted 状态。

### 6.3 POST /api/workbench/actions/retry

请求字段：

- `thread_id`
- `message_id`
- `checkpoint_ref`
- `action_id`

后端校验：

- message 属于当前 thread。
- message 状态是 `failed` 或 `interrupted`。
- checkpoint ref 属于当前 thread。
- 用户仍有权限。
- retry budget 未耗尽。
- 请求 payload 不含 SQL、schema、字段、表、raw result、query_plan 或 DSL。

执行：

- 创建新的 assistant running message。
- 写 `action.retry_requested` event。
- 从 checkpoint 恢复 last safe state。
- 重新进入 Datalogue 主链。

## 7. 新消息写入流程

```text
POST chat message
  -> resolve thread_id
  -> create/read agentscope_session
  -> insert user message completed
  -> insert assistant message running with lease
  -> insert message.received event
  -> run Datalogue main chain
      -> project DatalogueEventEnvelope to agentscope_event
      -> write refs to agentscope_ref
  -> update assistant message completed | failed
```

中断恢复：

- 页面加载或下一次请求扫描过期 running message。
- 过期后标记为 `interrupted`。
- P0 不自动 resume。
- 用户通过受控 retry 继续。

## 8. 前端设计

### 8.1 Chat 右侧 Workbench Panel

Chat 页面保留现有主体验。

Panel 打开入口：

- ArtifactCard。
- Timeline 节点。
- RepairPatch 摘要。
- 查看详情 action。

Panel 消费：

- `GET /api/workbench/thread/{thread_id}`
- `GET /api/workbench/artifact/{artifact_ref}`
- `POST /api/workbench/actions/retry`

### 8.2 隐藏 Workbench 路由

新增：

```text
/workbench/:threadId/:artifactRef?
```

第一阶段不放主导航。该页面复用 Workbench Panel / Workbench View 组件。

### 8.3 旧会话提示

旧会话继续提问时提示：

```text
这是旧会话，继续提问将创建新的工作台会话。
```

主按钮：

```text
转为新工作台会话
```

## 9. 安全模型

普通用户不可见：

- SQL。
- schema。
- 表名。
- 字段名。
- raw rows。
- raw result。
- query_plan。
- DSL。
- RepairPatch patch body。
- trace-only metadata。
- control-plane 内部对象。

管理员诊断抽屉也不展示：

- raw SQL。
- raw result。
- full schema。
- 未脱敏字段级 patch 主体。

管理员诊断只看脱敏摘要、状态和 refs。

## 10. 验收用例

### 10.1 新会话成功问数

用例：

1. 新建 `as_*` thread。
2. 发送真实问数问题。
3. user message 写入 completed。
4. assistant message 写入 running。
5. Datalogue 主链成功。
6. assistant message 更新 completed。
7. `agentscope_event` 有主链事件投影。
8. `agentscope_ref` 有 artifact / trace / task refs。
9. Chat Workbench Panel 展示 timeline 和 Artifact。
10. 普通用户 payload 不含安全红线内容。

### 10.2 failed / interrupted + retry

用例：

1. 构造 failed 或 lease 过期 running message。
2. 页面展示 failed / interrupted。
3. retry action 可用。
4. 点击 retry。
5. 创建新的 assistant running message。
6. 写入 `action.retry_requested` event。
7. 从 checkpoint 恢复。
8. Datalogue 主链重新执行。
9. 成功后写 completed message 和 refs。
10. 原 message、retry message、checkpoint、artifact、trace 可串联。

### 10.3 旧会话只读回放

用例：

1. 打开 `/chat/28`。
2. resolver 解析为 `conv_28`。
3. 页面按旧 conversation 回放。
4. 不创建 AgentScope session。
5. ArtifactCard 正常显示。
6. 继续提问时提示转新工作台会话。

## 11. P0 任务拆分

### 后端

- Alembic 迁移新增四张 mirror 表。
- 新增 schema / DTO。
- 新增 thread resolver。
- 新增 AgentScope mirror service。
- 新增 event projection service。
- 新增 Workbench View Model API。
- 新增 retry action API。
- 接入 `/chat/stream` 新会话写入顺序。
- 旧 conversation 只读 resolver。
- lease timeout 标记逻辑。
- 安全扫描测试。

### 前端

- Thread id namespace 支持。
- 新建会话默认 `as_*`。
- 旧 `/chat/:number` 兼容。
- Chat 右侧 Workbench Panel。
- 隐藏 `/workbench/:threadId/:artifactRef?` 路由。
- 普通视图。
- 管理员诊断抽屉。
- retry action UI。
- 旧会话转新工作台提示。

### 测试

- mirror 表 schema 测试。
- thread resolver 测试。
- 新消息写入顺序测试。
- event projection 测试。
- Workbench View Model API 测试。
- retry action 测试。
- lease interrupted 测试。
- 旧会话只读回放测试。
- 前端 panel / hidden route / retry UI 测试。
- 安全红线扫描。

## 12. 后续阶段

### P1

- 正式开放独立 Workbench 页面。
- 强化 Artifact 详情。
- 补真实页面 retry E2E。
- 增加 action execution state。

### P2

- 接真实 AgentScope runtime。
- mirror 作为审计和回放兜底。
- 评估 DatasetAgent / ReportAgent 受控 runner。
- 保持 Datalogue 业务内核裁决权。
