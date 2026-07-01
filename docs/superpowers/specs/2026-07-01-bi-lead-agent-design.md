# BI LeadAgent 第一版设计规格

## 1. 背景

DatasetAgent Runtime 基础设施已经搭好，下一步目标是让 BI LeadAgent 进入 AgentScope 直接成型方向。

第一版选择：

- 采用 AgentScope BI LeadAgent。
- 采用业务级 handoff tools。
- 契约按 B-ready 设计，后续可替换为 AgentScope native agent-to-agent handoff。
- Datalogue DB 继续作为业务状态真相源。

本文中的 `handoff` 指“任务交接”：BI LeadAgent 把用户确认后的查询任务正式交给 DatasetAgent Runtime 执行，并留下可追踪的交接记录。它不是普通工具调用，因为它包含父子智能体身份、子运行、状态、trace、artifact 和 checkpoint 引用。

## 2. 总体链路

```text
用户问题
  -> Agentic Shell
      -> 创建 AgentScope BI LeadAgent run
      -> 加载 BI LeadAgent Skill / SOUL 边界
      -> 投影安全上下文
  -> AgentScope BI LeadAgent
      -> 做业务路由、候选数据集、确认闭环
      -> 调用 query_dataset handoff capability
  -> Datalogue Host Handoff Adapter
      -> 启动现有 DatasetAgent Runtime
      -> 写 handoff_id / child_agent / child_run_id / refs
  -> DatasetAgent Runtime
      -> 调 BI 原子工具
      -> 产出 artifact / summary / final answer
  -> BI LeadAgent
      -> 接收 DatasetAgent 安全结果
      -> 汇总最终回答
```

## 3. 非目标和硬边界

BI LeadAgent 第一版不直接调用 Dataset 原子工具。以下能力只属于 DatasetAgent Runtime：

- `list_candidate_assets`
- `compile_dsl_to_sql`
- `execute_compiled_query`
- `repair_dsl`
- `create_query_artifact`

BI LeadAgent 不读取、不生成、不传递：

- SQL
- schema
- DSL
- raw rows
- 字段映射详情
- 候选资产详情
- 蓝图正文
- compiled query ref
- repair patch

`query_dataset` 是 handoff capability，不是普通数据工具。第一版由 Datalogue Host Handoff Adapter 承接，后续只替换内部实现为 AgentScope native sub-agent handoff。

## 4. 第一版能力面

BI LeadAgent 第一版能力面采用“三开一藏”。

启用：

- `list_dataset_capabilities`
- `request_dataset_confirmation`
- `query_dataset`

预留但禁用：

- `query_multiple_datasets`

`query_multiple_datasets` 在 capability manifest 中保留 disabled 记录：

```text
name: query_multiple_datasets
status: disabled
disabled_reason: B_READY_AGENT_TO_AGENT_HANDOFF_RESERVED
replacement: query_dataset
```

## 5. 数据集能力摘要

`list_dataset_capabilities` 只返回路由级能力目录。

允许字段：

- `dataset_id`
- `name`
- `domain`
- `supported_questions`
- `key_metrics`
- `key_dimensions`
- `freshness`
- `availability`

禁止返回：

- schema
- SQL
- DSL
- 候选资产详情
- 字段映射详情
- 蓝图正文

BI LeadAgent 可以据此判断“建议查哪个数据集、为什么”，但不能据此做查询规划。

## 6. 用户确认

`request_dataset_confirmation` 第一版采用显式确认优先。

只要 BI LeadAgent 准备调用 `query_dataset`，必须先让用户确认：

- 数据集
- 问题理解
- 查询目标
- 可能产出的 artifact
- 路由理由
- 风险提示

后续代办：

- B2：高置信度自动执行、低置信度确认。
- H3：完整 UI 交互记录。

## 7. query_dataset 契约

### 7.1 输入

`query_dataset` 入参采用业务任务包加路由理由。

```text
dataset_id
confirmed_question
task_goal
user_confirmation_id
routing_rationale
trace_id
parent_run_id
```

`routing_rationale` 只表达“为什么 BI LeadAgent 认为这个数据集适合回答用户问题”。它不能包含 schema、字段映射、SQL、DSL、候选资产详情，也不能要求 DatasetAgent 按某个字段或 SQL 路径执行。

### 7.2 输出

`query_dataset` 返回安全摘要和 handoff refs。

```text
handoff_id
parent_agent = bi_lead_agent
child_agent = dataset_agent
child_run_id
dataset_id
task_id
trace_id
handoff_status
answer_summary
artifact_ref
checkpoint_ref
row_count
column_count
```

禁止返回：

- SQL
- schema
- raw rows
- DSL
- candidate assets detail
- compiled_query_ref
- repair_patch
- blueprint body

## 8. handoff 状态机

`handoff_status` 采用 B-ready 状态集。

```text
created        交接单已创建
accepted       DatasetAgent 已接收
running        DatasetAgent 正在执行
waiting_child  等待子智能体返回
completed      已完成
blocked        被阻塞，需要用户或系统补充条件
failed         执行失败，当前不可恢复
cancelled      已取消
```

`blocked` 表示缺少用户确认、数据集不可用、权限不足、问题不清楚等条件，补上条件后可能继续。

`failed` 表示本次查询链路已经失败，不能靠用户补一句话直接恢复，需要修复系统、数据或运行时问题。

## 9. BI LeadAgent 运行方式

第一版采用 F2：多阶段 run。最终形态预留 F3：长生命周期会话 agent。

第一版阶段：

```text
route_run        理解问题、选择候选数据集
confirm_run      生成确认请求，等待用户确认
handoff_run      发起 query_dataset 任务交接
summarize_run    接收 DatasetAgent 安全结果并汇总最终回答
```

Datalogue DB 是状态真相源，保存 run、confirmation、handoff、artifact/checkpoint refs 和最终摘要。AgentScope run/event 作为运行时证据和投影，不直接裁决业务状态。

后续代办：

- F3：长生命周期会话 agent。

## 10. 用户确认记录

确认记录采用 H2：确认快照记录。

字段：

```text
confirmation_id
dataset_id
confirmed_question
task_goal
dataset_capability_snapshot
routing_rationale
risk_notice
user_decision
created_at
confirmed_at
trace_id
parent_run_id
```

只保存路由级快照：

- 数据集名称
- 业务域
- 可回答问题类型
- 关键指标名
- 关键维度名
- 数据可用性和新鲜度

不保存 schema、SQL、DSL、raw rows、字段映射详情、候选资产详情或蓝图正文。

## 11. 最终回答职责

BI LeadAgent 最终回答采用 I2：基于安全摘要做轻量汇总。

BI LeadAgent 可以使用：

- `answer_summary`
- `artifact_ref`
- `checkpoint_ref`
- `row_count`
- `column_count`
- `dataset_id`
- `routing_rationale`
- `handoff_status`

BI LeadAgent 不可以：

- 新增 DatasetAgent 没给出的数值结论
- 解释 SQL
- 推断字段映射
- 基于行列数量臆造业务洞察
- 重新规划查询
- 读取 artifact 内部明细

## 12. 失败和阻塞回答

第一版采用 J2：区分 `blocked` 和 `failed`。

`blocked` 用户回答说明：

- 当前缺什么条件
- 用户可以做什么
- 是否需要重新确认

`failed` 用户回答说明：

- 失败类型
- `trace_id`
- 是否可重试

用户回答不得暴露内部异常、SQL、schema、堆栈或敏感数据路径。

后续代办：

- J3：细分错误码到用户文案映射。

## 13. 开发阶段

完整路线包含 K1、K2、K3，按顺序推进。

```text
K1：后端契约优先
K2：端到端原型
K3：AgentScope 原生形态
```

K1 采用 L2：后端契约加最小 API。

K1 做：

- BI LeadAgent capability manifest
- `list_dataset_capabilities` A1 路由级摘要
- `request_dataset_confirmation` B1 显式确认
- H2 确认快照记录
- `query_dataset` C2 输入和 D2 输出
- E2 handoff 状态机
- F2 多阶段 run 状态
- Datalogue DB 真相源
- M2 run-centric 最小 API
- W2 测试范围

K1 不做：

- 完整前端确认卡片
- 多数据集自动查询
- 高置信度自动执行
- AgentScope 长生命周期会话 agent
- 完整 UI 交互埋点
- 细分所有错误码文案

## 14. 最小 API

K1 API 采用 M2：run-centric API。

```text
POST /api/bi-lead-agent/runs
  创建 route_run，返回候选数据集能力摘要和确认请求

POST /api/bi-lead-agent/runs/{run_id}/confirm
  写入 H2 确认快照，进入 confirm_run 完成状态

POST /api/bi-lead-agent/runs/{run_id}/handoff
  发起 query_dataset handoff，启动 DatasetAgent Runtime

GET /api/bi-lead-agent/runs/{run_id}
  查询当前 run 状态、handoff refs、最终摘要或阻塞/失败信息
```

`run` 是一次 BI LeadAgent 多阶段运行的业务链路编号，可关联：

- `route_run_id`
- `confirm_run_id`
- `handoff_run_id`
- `summarize_run_id`
- `handoff_id`
- `confirmation_id`
- `trace_id`
- `task_id`
- `artifact_ref`
- `checkpoint_ref`

## 15. 数据模型

K1 数据模型采用 N1：三张表。

```text
bi_lead_agent_run
bi_lead_agent_confirmation
bi_agent_handoff
```

关系：

```text
bi_lead_agent_run 1 -> 0/1 bi_lead_agent_confirmation
bi_lead_agent_run 1 -> 0/1 bi_agent_handoff
bi_agent_handoff 1 -> 1 DatasetAgent child_run
```

第一版按单数据集查询设计，一个 BI LeadAgent run 最多一个 confirmation、一个 handoff。后续启用 `query_multiple_datasets` 后，再扩成一对多 handoff。

### 15.1 bi_lead_agent_run

```text
id
status
phase
question
trace_id
task_id
status_reason
error_code
error_summary
created_at
updated_at
```

### 15.2 bi_lead_agent_confirmation

```text
id
run_id
dataset_id
confirmed_question
task_goal
capability_snapshot_json
routing_rationale
risk_notice
user_decision
created_at
confirmed_at
```

### 15.3 bi_agent_handoff

```text
id
run_id
handoff_id
parent_agent
child_agent
child_run_id
dataset_id
task_id
trace_id
checkpoint_ref
artifact_ref
handoff_status
answer_summary
row_count
column_count
status_reason
error_code
error_summary
created_at
updated_at
```

错误字段只保存简短错误码、原因和摘要，不保存 SQL、schema、DSL、raw rows、堆栈、数据库连接信息、字段映射详情或候选资产详情。

## 16. 服务层模块

K1 服务层采用 Q2：三个服务模块。

```text
BILeadAgentRunService
BILeadAgentConfirmationService
BIHandoffService
```

职责：

- `BILeadAgentRunService` 创建 run、推进 phase/status、记录 blocked/failed/completed、汇总 GET run 状态响应。
- `BILeadAgentConfirmationService` 生成确认请求、保存 H2 确认快照、校验用户确认、防止未确认直接 handoff。
- `BIHandoffService` 创建 handoff_id、调用 Datalogue Host Handoff Adapter、启动 DatasetAgent Runtime、写 child_agent/child_run_id/refs、映射 handoff_status。

`BIHandoffService` 是未来 B 方案替换点。第一版内部调用 Host Adapter，后续升级 AgentScope native agent-to-agent handoff 时，优先只替换该模块内部实现。

## 17. Host Handoff Adapter

K1 Host Handoff Adapter 采用 R2：新增正式 Host Adapter，内部复用 DatasetAgent Runtime 组件。

建议模块名：

```text
DatalogueBIHandoffAdapter
```

职责：

- 承接 `query_dataset`
- 创建 `handoff_id`
- 创建 `child_run_id`
- 启动 DatasetAgent Runtime
- 复用现有 DatasetAgent Runtime bridge、toolkit 和 sanitizer
- 写 `artifact_ref`、`checkpoint_ref`、`trace_id`
- 返回 D2 安全结果

第一版采用 S2：真实 AgentScope DatasetAgent tool-calling。

```text
DatalogueBIHandoffAdapter
  -> 创建 DatasetAgent child_run
  -> 启动 AgentScope DatasetAgent
  -> DatasetAgent 发起 external tool event
  -> Host Adapter 执行白名单 Dataset 原子工具
  -> 回填安全 tool result
  -> DatasetAgent 产出安全摘要 / artifact refs
  -> BI LeadAgent 接收 D2 安全结果
```

失败兜底采用 T2：只允许测试/开发环境兜底。

```text
正式链路：
  S2 失败后记录 failed 或 blocked，不自动切确定性 Runtime。

测试/开发开关：
  S2 失败后可 fallback 到确定性 Runtime 编排。
  handoff/trace 必须标记 fallback_used = true。
```

建议配置：

```text
BI_LEAD_AGENT_DATASET_FALLBACK_MODE = off | dev_only
```

## 18. DatasetAgent 工具白名单和顺序

DatasetAgent Runtime 内部工具白名单采用 U1：

```text
get_dataset_status
list_candidate_assets
compile_dsl_to_sql
execute_compiled_query
repair_dsl
create_query_artifact
get_artifact_summary
```

这些工具只属于 DatasetAgent Runtime。BI LeadAgent 不能看到、不能调用、不能写进自己的 capability manifest。

工具调用顺序采用 V1：强制固定状态机。

主路径：

```text
get_dataset_status
-> list_candidate_assets
-> compile_dsl_to_sql
-> execute_compiled_query
-> create_query_artifact
-> get_artifact_summary
```

字段缺失修复分支：

```text
execute_compiled_query
  -> 如果返回 FIELD_NOT_FOUND
  -> 允许 repair_dsl 一次
  -> 再回到 execute_compiled_query
```

工具顺序不符合状态机时，Host Adapter 必须拒绝调用，并写入 handoff blocked 或 failed。

## 19. 测试范围

K1 测试范围采用 W2：契约测试、服务单测、集成测试。

契约测试：

- capability manifest 只暴露三开一藏
- BI LeadAgent 不暴露 Dataset 原子工具
- `list_dataset_capabilities` 只返回 A1 路由级摘要
- `query_dataset` 入参采用 C2
- `query_dataset` 返回采用 D2
- disabled `query_multiple_datasets` 可见但不可调用

服务单测：

- run phase/status 推进
- H2 confirmation 保存和复用校验
- 未确认禁止 handoff
- blocked/failed 字段写入
- final answer synthesis I2 不新增数值结论

集成测试：

- Host Adapter 创建 `handoff_id` 和 `child_run_id`
- AgentScope DatasetAgent external tool event 被 Host Adapter 承接
- U1 工具白名单生效
- V1 工具顺序违规会拒绝
- DatasetAgent 返回 D2 安全摘要和 refs
- 不返回 SQL、schema、raw rows、DSL、compiled_query_ref

Live LLM 测试不进入默认 K1 CI，作为手动验收项保留：

```text
RUN_BI_LEAD_AGENT_LIVE=1 pytest ...
```

## 20. 后续代办

已进入飞书代办：

- B2：高置信度自动执行、低置信度确认。
- F3：长生命周期会话 agent。
- H3：完整 UI 交互记录。
- J3：细分错误码到用户文案映射。

后续路线：

- K2：基于 K1 API 打通页面确认到最终回答的端到端原型。
- K3：在不破坏 Datalogue DB 真相源的前提下，把内部实现逐步升级为 AgentScope native run、handoff 和 event 形态。

## 21. 验收口径

K1 完成时必须证明：

- BI LeadAgent capability manifest 没有暴露 Dataset 原子工具。
- 未确认不能发起 `query_dataset`。
- `query_dataset` 入参不含 SQL、schema、DSL 或候选资产详情。
- handoff 记录包含 B-ready refs。
- DatasetAgent Runtime 内部工具白名单和顺序强制生效。
- 返回给 BI LeadAgent 的结果只包含安全摘要和 refs。
- blocked/failed 能写入最小错误字段并返回安全用户信息。
- 测试覆盖 W2 范围。
