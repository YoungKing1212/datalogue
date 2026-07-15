# Datalogue 数语设计开发方案

版本：v2026.07.03
状态：历史归档（原文件在 2026-07-03 时标记为当前版）
适用范围：记录 2026-07-03 时点的产品架构、后端主链、AgentScope 2.0 ReAct Agent 目标架构、BI Agent、Dataset Query Skill、数据治理、验收与实施计划。
历史边界：旧 `/api/chat/stream`、LangGraph 主链、Langfuse 运行时和 QueryGraph 中心化口径只作为历史背景，不再作为当前设计开发依据。

## 1. 项目定位

数语是面向企业数据资产的 AI 原生智能问数平台。用户通过自然语言提出业务问题，系统在受控 Agent 链路中完成数据集识别、候选确认、查询规划、只读执行、结果产物生成、证据引用和最终回答。

本项目的核心不是让大模型直接生成 SQL，而是把“自然语言问数”变成可治理、可审计、可恢复的业务任务。所有执行结果必须能通过页面、SSE 事件、后端日志、数据库 refs、Artifact 和最终 answer 互相核对。

## 2. 当前目标架构

当前目标架构为：

```text
用户入口
  -> Datalogue Runtime
  -> AgenticLeadAgent
  -> BI Agent
  -> Dataset Query Skill
  -> BI Toolkit
  -> Dataset Toolchain
  -> Datalogue 真相源与企业数据源
```

核心边界如下：

- 用户入口：Chat / Workbench，统一调用 `POST /api/agentic-shell/tasks/stream`。
- Datalogue Runtime：只维护 task、event、session、message、refs 生命周期，不做业务推理。
- AgenticLeadAgent：目标态是 AgentScope 2.0 ReAct Agent，负责任务分类、子 Agent 选择、工具白名单、上下文投影和输出清洗。
- BI Agent：目标态是 AgentScope 2.0 ReAct Agent，负责理解问数目标、管理 run / confirmation / handoff、选择 Dataset Query Skill / Toolkit，并返回业务摘要与 artifact 引用。
- Dataset Query Skill：注册到 BI Agent 内部，只暴露受控问数能力，不泄露执行态。
- BI Toolkit：以 AgentScope ToolBase / Toolkit 形式承接 `get_status`、`list_assets`、`compile_dsl`、`execute_query`、`repair_dsl`、`create_artifact` 等工具。
- Dataset Toolchain：读取安全 catalog / manifest，生成 DSL，编译为 SQL，执行只读查询，产出 artifact，并返回 summary / refs / row_count。
- Datalogue 真相源：Datalogue DB、ArtifactStore、Checkpoint/Refs、Manifest 和治理资产仍是业务事实裁决层。

## 3. 设计原则

### 3.1 SDK-first

AgentScope 能力优先使用官方 SDK 实现。AgenticLeadAgent 与 BI Agent 的目标态都应 SDK 化为 AgentScope 2.0 ReAct Agent，不私自重造运行时。

### 3.2 Runtime 不做业务推理

Datalogue Runtime 只负责生命周期和真相源写入。任务分类、问数目标理解、工具选择和输出清洗分别由 AgenticLeadAgent 与 BI Agent 承担。

### 3.3 SQL 留在控制面

SQL、schema、raw rows、query_plan、repair patch 默认只存在于 BI Agent / Dataset Toolchain / Artifact control plane 内部。用户可见层和 AgenticLeadAgent 上下文只接收安全摘要、row_count、column_count、artifact_ref、checkpoint_ref。

### 3.4 历史证据不改写

旧方案、旧验收记录和旧测试报告按历史事实保留。当前文档只负责给它们标注历史状态，不把历史验收改写为当前能力。

## 4. 功能范围

### 4.1 当前主范围

当前阶段覆盖以下能力：

- 自然语言问数。
- 数据集候选确认。
- Agentic Shell 统一任务入口。
- AgenticLeadAgent 任务路由与最终回答。
- BI Agent 问数控制面。
- Dataset Query Skill / Toolkit / Toolchain。
- Artifact 详情、Markdown 表格和安全 refs。
- 多轮上下文恢复。
- 模型选择。
- 数据集治理，包括数据表、字段、指标、维度、术语、蓝图、Manifest、权限和版本历史。

### 4.2 当前非范围

当前阶段不做以下事项：

- 不恢复旧 `/api/chat/stream` 作为执行入口。
- 不把 Langfuse 作为当前验收前提。
- 不让 AgenticLeadAgent 获取 SQL、schema、raw rows 或 DatasetAgent 内部执行态。
- 不默认启用 ReportAgent、PythonAgent、AuditAgent；这些子 Agent 后续显式启用。
- 不一次性删除所有 legacy API；删除必须依赖引用扫描和回归验收。

## 5. 系统分层设计

### 5.1 前端层

前端由 datalogue-web 承接，核心页面包括：

- Chat：用户主问数入口，发送 AgenticShellTaskRequest，消费 SSE envelope。
- Workbench：展示 task 状态、artifact、checkpoint refs、retry/action。
- 数据集治理页：维护数据表、字段标注、指标、维度、术语、蓝图、Manifest、权限和版本历史。
- 设置页：维护 LLM 模型配置、成员权限、数据源和业务字典。

前端不得依赖 AgentScope 内部消息对象，只消费 DatalogueEventEnvelope 和 Artifact API。

### 5.2 API 层

主要 API 设计如下：

| 方法 | 路径 | 当前角色 |
| --- | --- | --- |
| `POST` | `/api/agentic-shell/tasks/stream` | 当前统一任务入口 |
| `POST` | `/api/agentic-lead-agent/direct-query/stream` | direct-query 渐进验证入口 |
| `GET/POST` | `/api/conversation` | 对话列表与创建 |
| `GET/PATCH` | `/api/conversation/{id}` | 对话详情与重命名 |
| `POST` | `/api/messages/{id}/feedback` | 消息反馈 |
| `GET/POST/PATCH` | `/api/dataset/*` | 数据集治理 |
| `GET/POST/PATCH` | `/api/datasource/*` | 数据源管理 |

旧 Chat stream route 已从执行链路删除，不再作为兼容执行入口。

### 5.3 Agent 层

Agent 层分为三类：

- AgenticLeadAgent：用户任务控制面，负责任务分类、子 Agent 选择、工具白名单、上下文投影和最终输出清洗。
- BI Agent：问数业务 Agent，理解问数目标和数据集上下文，管理 run、confirmation、handoff，并选择 Dataset Query Skill。
- 可选子 Agent：ReportAgent、PythonAgent、AuditAgent，默认 disabled，后续按产品能力显式启用。

当前代码缺口必须明确：现在需要落地的是正式 AgentScope 版 AgenticLeadAgent 和 BI Agent，并接入 Agentic Shell 主链；现有 direct-query / Dataset 查询桥接只能作为渐进验证和过渡路径，不能当作目标态完成。后续应先完成 AgenticLeadAgent，再完成 BI Agent，最后删除 façade 直连 handoff 的过渡路径。

### 5.4 Skill / Toolkit / Toolchain 层

BI Agent 内部受控问数链路分三层：

1. Dataset Query Skill：只注册能力，构造 runtime bridge，不直接泄露执行态。
2. BI Toolkit：封装 AgentScope Tools，包括状态查询、资产列表、DSL 编译、查询执行、DSL 修复和 Artifact 创建。
3. Dataset Toolchain：确定性执行状态机，负责读取 manifest、生成 DSL、编译 SQL、执行只读查询、生成 artifact、返回摘要和 refs。

### 5.5 数据治理层

数据治理围绕 SemanticDataset 展开：

- 数据源：Datasource、SourceTable、SourceColumn。
- 数据集：SemanticDataset。
- 语义资产：SemanticMetric、SemanticDimension、Term、Blueprint。
- 路由资产：DatasetSubAgentManifest、capability_manifest。
- 运行资产：Artifact、Checkpoint、ConversationState、AgenticShellTask。

治理资产必须优先服务安全问数链路，而不是简单堆叠 schema 明细给模型。

## 6. 主执行链路

主链路如下：

1. 用户在 Chat 或 Workbench 发起自然语言问题。
2. 前端调用 `POST /api/agentic-shell/tasks/stream`。
3. Datalogue Runtime 创建 AgenticShellTask、message、refs，并输出 task.started。
4. AgenticLeadAgent 分类任务，选择 BI Agent。
5. BI Agent 判断是否已确认数据集；未确认时返回候选数据集确认卡片。
6. 用户确认数据集后，BI Agent 调用 Dataset Query Skill。
7. Dataset Query Skill 构造 Toolkit 和 Toolchain runtime。
8. Dataset Toolchain 读取安全 manifest，生成 DSL，编译 SQL，执行 SQL Guard 和只读查询。
9. Toolchain 写入 Artifact 和 checkpoint refs。
10. BI Agent 接收安全摘要和 refs。
11. AgenticLeadAgent 生成最终 Markdown 答复。
12. Datalogue Runtime 写入 message / final payload，并通过 SSE 返回 task.completed。

## 7. 事件与输出协议

对外事件统一使用 DatalogueEventEnvelope。

关键字段包括：

- `event_type`
- `visibility`
- `task_id`
- `trace_id`
- `thread_id`
- `message_id`
- `selected_agent`
- `payload`
- `legacy_payload`

事件类型包括：

- `task.started`
- `agent.selected`
- `tool.external_required`
- `tool.result`
- `checkpoint.created`
- `artifact.ready`
- `message.delta`
- `message.completed`
- `task.completed`
- `task.failed`

安全要求：

- 用户可见事件不包含 SQL、schema、DSL、raw rows、query_plan、repair patch。
- Trace-only 字段也必须脱敏，不记录凭据、连接串和私有原始结果。
- legacy_payload 只服务迁移期 view model，不作为新协议主字段。

## 8. 安全与治理设计

### 8.1 工具白名单

AgenticLeadAgent 只看到业务能力摘要和子 Agent 选择，不直接持有 Dataset 原子工具。BI Agent 内部工具必须通过白名单注册。

### 8.2 SQL Guard

SQL 只能由 toolchain 生成和执行。所有查询必须经过只读校验、方言适配、数据源权限校验和结果规模限制。

### 8.3 用户输出清洗

最终 answer 只能包含：

- 业务摘要。
- Markdown 表格或受控 Artifact 详情。
- row_count / column_count。
- artifact_ref / checkpoint_ref。
- 可解释但不泄露内部执行态的错误摘要。

### 8.4 日志与调试

普通日志默认脱敏。需要定位内部执行态时，使用受控 DEBUG 日志，并避免打印 SQL、schema、raw rows、完整 query_plan 和完整 tool payload。

## 9. 当前实现状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| Agentic Shell 统一入口 | 已完成 | Chat / Workbench 统一进入 AgenticShellTask |
| Dataset Query Skill | 已完成 | 已迁入 BI Agent 内部受控能力边界 |
| BI Toolkit / Dataset Toolchain | 已完成 | 承接 compile / execute / repair / artifact |
| AgentScope 多轮上下文恢复 | 已完成 | direct-query 链路恢复 AgentState.context |
| Artifact 详情与表格展示 | 已完成 | 支持 Markdown 表格、详情展开、固定表头 |
| 数据集候选确认 | 已完成 | 前端使用统一候选确认卡片 |
| 模型选择 | 已完成 | Composer 支持本轮模型覆盖 |
| AgenticLeadAgent SDK 化 | 待推进 | 下一阶段优先事项 |
| BI Agent SDK 化 | 待推进 | 在 AgenticLeadAgent SDK 化之后推进 |
| 旧 handoff/API 收口 | 待推进 | 删除前需引用扫描和回归验收 |

## 10. 开发计划

### 10.1 P0：当前链路稳定

目标：确保当前 Agentic Shell 主链可稳定问数。

关键任务：

- 聚合语义增强，优先处理统计数量、按年份统计、合同总金额等问题。
- 明确 QueryPlan 与 summary 的聚合口径。
- 补充真实浏览器验收：页面、Network、后端日志、DB refs、Artifact、最终 answer 六方对齐。

### 10.2 P1：AgenticLeadAgent SDK 化

目标：把 AgenticLeadAgent 改造成 AgentScope 2.0 ReAct Agent。

关键任务：

- 用 AgentScope SDK 构造 AgenticLeadAgent。
- 固化工具白名单、Policy、Guard 和上下文投影。
- 保证 AgenticLeadAgent 上下文不包含 SQL、schema、raw rows、query_plan。
- 保持 Datalogue Runtime 只做生命周期和 envelope 投影。

### 10.3 P2：BI Agent SDK 化

目标：把 BI Agent 改造成 AgentScope 2.0 ReAct Agent。

关键任务：

- 将 Dataset Query Skill 注册为 BI Agent 内部能力。
- 将 BI Toolkit 接入 AgentScope ToolBase / Toolkit。
- 明确 run、confirmation、handoff 和 artifact refs 的写入边界。
- 迁移旧 façade / native_handoff 过渡路径。

### 10.4 P3：历史兼容层收口

目标：删除不再服务当前主链的旧 adapter 和旧 API。

关键任务：

- 扫描 `/api/bi-agent/runs/{id}/handoff`、native_handoff、legacy QueryGraph / runner 的真实引用。
- 将仍需要的内部能力重命名为 toolchain 组件。
- 删除无引用路径并补回归测试。

### 10.5 P4：可选子 Agent 启用

目标：在 BI Agent 稳定后，按产品路线启用 ReportAgent、PythonAgent、AuditAgent。

关键任务：

- 定义每个子 Agent 的白名单工具。
- 明确 artifact 输入输出协议。
- 对用户可见层继续只暴露安全摘要和 refs。

## 11. 验收标准

一次问数验收必须至少覆盖：

- 浏览器 Network 主请求为 `/api/agentic-shell/tasks/stream` 或明确 direct-query 验证入口。
- SSE 包含 task.started、agent.selected、message.delta、message.completed、task.completed。
- 后端日志可看到 AgenticLeadAgent、BI Agent、Dataset Query Skill 和 Toolchain 阶段推进。
- 数据库中 message、conversation_state、artifact、checkpoint refs 能按同一会话关联。
- 用户可见 answer 不泄露 SQL、schema、raw rows、query_plan。
- Artifact 详情可按 refs 读取，并与最终回答一致。
- 失败场景有明确 error_code、error_summary 和可恢复/不可恢复判断。

## 12. 风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| AgenticLeadAgent / BI Agent 尚未完全 SDK 化 | 目标架构与实现仍有差距 | 按 P1/P2 分阶段迁移，不再新增旧 façade 能力 |
| 聚合语义不足 | 统计类问题可能返回明细表 | 优先增强 QueryPlan、summary 和聚合测试 |
| 旧 API 仍被引用 | 删除可能破坏兼容路径 | 删除前做引用扫描、测试覆盖和灰度替换 |
| 历史文档误导 | 后续实现可能回到旧 `/api/chat/stream` / LangGraph 口径 | 活跃文档重写，历史目录加状态说明 |
| 调试日志泄露内部执行态 | 可能暴露 SQL 或 schema | 普通日志脱敏，DEBUG 日志只记录安全摘要 |

## 13. 交付物

当前阶段交付物包括：

- 当前设计开发方案：`assets/documents/Datalogue_设计开发方案_当前版_20260703.docx`。
- Markdown 源稿：`assets/documents/Datalogue_设计开发方案_当前版_20260703.md`。
- 当前系统设计：`docs/architecture/数语系统设计方案.md`。
- 当前执行链路图：`docs/architecture/后期完整执行节点链路图.md`。
- 项目总结与计划：`docs/product/当前项目工作总结与下步计划.md`。
- 文档总览：`docs/README.md`。

## 14. 总结

数语当前应坚持 Agentic Shell-first、AgentScope SDK-first、BI Agent 内部受控问数链路和 Datalogue 真相源四条主线。短期重点是补齐 AgenticLeadAgent 与 BI Agent 的 SDK 化缺口，并让 Dataset Query Skill / Toolkit / Toolchain 成为唯一可治理的问数执行面。长期再逐步启用 ReportAgent、PythonAgent、AuditAgent 等可选子 Agent。
