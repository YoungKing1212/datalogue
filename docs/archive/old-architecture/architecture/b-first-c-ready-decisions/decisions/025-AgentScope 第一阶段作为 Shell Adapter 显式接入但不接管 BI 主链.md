# 025 · AgentScope 第一阶段作为 Shell Adapter 显式接入但不接管 BI 主链

## 状态

- 状态：已敲定
- 时间：2026-06-26 16:02
- 触发：用户指出当前改造计划看不到 AgentScope 2.0 技术落点，并确认需要补充

## 决策

第一阶段需要显式补入 AgentScope 2.0 技术路线：新增 `AgentScope Shell Adapter` 验证层，用 AgentScope 2.0 承接外层 Agentic Shell 的最小编排验证；但 AgentScope 不接管 BI 主链 runtime，不替换 `/chat/stream`，也不能绕过 `BIWorkbenchTool / ask_bi` 访问 schema、SQL、数据库或 `control_plane`。

## 背景

当前计划已经明确 C 产品形态优先，但文档中的 AgentScope 主要落在 P6 后续验证线，导致第一阶段技术计划看起来仍是 Datalogue 自研协议改造，没有体现 AgentScope 2.0 框架。这个问题需要修正：C 形态如果长期目标包含 AgentScope 2.0，就应该在第一阶段保留一个真实、可验收、但不破坏 BI 内核的技术落点。

## 选择理由

- `ask_bi`、event envelope、ArtifactCard、引用句柄和 ToolAdapter 都是 AgentScope 外层编排可以复用的标准接口。
- 用 AgentScope 2.0 做外层 Shell Adapter，可以验证 tool calling、event adapter、task orchestration 和标准引用消费，而不需要改 BI 主链 runtime。
- 不让 AgentScope 第一阶段接管 `/chat/stream`，可以避免 conversation_state、query_artifact、Manifest、SQL Guard 和 Langfuse trace 的真相源被提前打散。
- 这个决策让计划同时满足两个目标：第一阶段核心问数链路稳住，技术路线又明确朝 AgentScope 2.0 演进。

## 被排除方案

### 方案 A：第一阶段完全不使用 AgentScope

不采用。虽然实现最稳，但会让 C 形态的 AgentScope 技术路线停留在口头预留，后续接入风险被推迟。

### 方案 B：第一阶段直接让 AgentScope 接管 BI 主链 runtime

不采用。它会让 `/chat/stream`、状态写入、artifact、Manifest guard、SQL Guard、Langfuse observation 和历史回放同时变动，风险过高，不符合先跑通智能问数核心链路的目标。

### 方案 C：第一阶段新增 AgentScope Shell Adapter，但 BI 主链仍由 Datalogue 管控

采用。AgentScope 只作为外层 Shell 编排验证层，工具面只允许调用 `ask_bi` 和消费标准事件 / 引用，不接触 BI 内部执行主体。

## 对架构的影响

- 新增 `AgentScopeShellAdapter` 作为 C 产品形态的第一阶段技术落点。
- AgentScope 可见工具只有 `ask_bi` / `BIWorkbenchTool` 以及后续白名单动作，不暴露 schema、SQL、raw result、capsule 或 `control_plane`。
- `AgentScopeEventAdapter` 第一阶段把 `DatalogueEventEnvelope` 映射为 AgentScope event stream 验证事件，但不替换 Web Chat SSE。
- AgentScope session / memory 只能保存外层任务状态和引用句柄，不能替代 Datalogue 的 conversation_state、query_artifact、Manifest、SQL Guard 和业务审计真相源。
- AgentScope 相关验收要证明：外层 Agent 能调用 BI 能力，但不能突破 B-governed BI core。

## 对开发计划的影响

- 正式开发计划新增 `Task P1.5：AgentScope Shell Adapter 最小验证`。
- P1.5 依赖 `ask_bi`、event envelope、ArtifactCard 和引用句柄。
- P1.5 验收只要求最小 AgentScope 2.0 编排验证，不要求接管 `/chat/stream`，不要求 ReportAgent / PythonAgent / AuditAgent 全量实现。
- P6 从“第一阶段唯一 AgentScope 验证线”调整为“主链 runtime 接入预备”，负责后续是否让 AgentScope 更深进入主链的闸门评估。

## 后续问题

- AgentScope Shell Adapter 第一阶段运行在测试目录、后端服务模块，还是独立 runner 进程？
- AgentScope 事件验证第一阶段是否只做后端 contract test，还是要在前端 Chat 时间线中展示来源标记？
- AgentScope Shell Adapter 的最小任务类型是否只覆盖 `ask_bi`，还是同时覆盖 `explain` / `retry` 这类白名单动作？
