# 026 · AgentScopeShellAdapter 放入后端正式 service 但第一阶段不开放 API

## 状态

- 状态：已敲定
- 时间：2026-06-26 16:07
- 触发：用户在 AgentScopeShellAdapter 放置位置三个方案中确认选择方案 2

## 决策

`AgentScopeShellAdapter` 第一阶段放入后端正式 service：`datalogue-api/app/services/agentscope_shell_adapter.py`，配套 `agentscope_event_adapter.py` 和 contract test；但第一阶段只做内部调用与测试验证，不新增公开 API、不接前端入口、不替换 `/chat/stream`。

## 背景

第 025 个决策已经敲定：AgentScope 2.0 第一阶段需要作为 Shell Adapter 显式进入方案，但不能接管 BI 主链。随后需要确定它放在哪里：

1. 放在 `tests/agentscope_*` 实验目录。
2. 放在后端正式 service，但只内部验证，不开放 API。
3. 做成独立 runner 进程。

用户确认选择方案 2。

## 选择理由

- 放正式 service 能让 AgentScope 2.0 技术路线成为真实工程模块，而不是停留在实验目录。
- 不开放公开 API，可以避免第一阶段引入新用户入口和权限面。
- 通过 contract test 验证 `ask_bi`、event envelope、ArtifactCard、引用句柄和防泄露边界，足够支撑架构可行性判断。
- 后续如果要接独立 runner、BI 工作台或 AgentScope runtime，可以复用同一 service 外壳，而不是从测试目录迁移。

## 被排除方案

### 方案 1：继续放在测试实验目录

不采用。它最快，但会让 AgentScopeShellAdapter 继续像 MVP 验证，而不是正式架构计划中的一层。

### 方案 3：第一阶段做独立 runner 进程

不采用。它更接近未来 runtime，但会提前引入进程生命周期、部署、认证、观测和失败恢复问题，不利于当前先跑通核心问数链路。

### 方案 2：后端正式 service，第一阶段只内部验证

采用。它在工程结构上正式承认 AgentScope 2.0 接入层，同时把外部暴露面控制在最低。

## 对架构的影响

- `datalogue-api/app/services/agentscope_shell_adapter.py` 成为 AgentScope 2.0 外层 Shell 接入的正式模块。
- `datalogue-api/app/services/agentscope_event_adapter.py` 负责将 `DatalogueEventEnvelope` 映射为 AgentScope event stream 验证事件。
- 第一阶段不新增 `app/api/agentscope.py` 或任何公开路由。
- 第一阶段不接前端入口，不改变现有 Chat 用户路径。
- AgentScopeShellAdapter 的依赖只能是 `ask_bi` / `BIWorkbenchTool`、event envelope、ArtifactCard 和引用句柄。
- 后续是否开放 API、独立 runner 或主链 runtime，由 P6 接入闸门决定。

## 对开发计划的影响

- `Task P1.5` 的文件范围明确为正式 service + tests。
- P1.5 验收必须证明：
  - adapter 模块位于 `app/services`。
  - 没有新增公开 API route。
  - AgentScope 只调用 `ask_bi`。
  - user-visible 输出不包含 SQL、schema、raw result、capsule 或 `control_plane`。
- 后续如果要做 runner，只能基于这个 service 外壳再扩展。

## 后续问题

- `AgentScopeShellAdapter` 的测试是使用真实 AgentScope 2.0 依赖，还是先做薄封装 mock + 单条 live optional test？
- 第一阶段是否需要把 AgentScope adapter 的运行结果写入 Langfuse trace，还是只保留 pytest 级别的验证日志？
- `AgentScopeShellAdapter` 是否需要独立 schema，还是直接复用 `AskBIRequest` / `AskBIResponse`？
