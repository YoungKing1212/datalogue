# 010 · C 产品形态优先且 BI 内核保持 B-governed

## 状态

- 状态：已敲定
- 时间：2026-06-26 11:55
- 触发：用户确认“按照你的建议来，要给出 C-ready 的工作规划”

## 决策

产品目标直接采用 C 形态，但 BI 查询内核保持 B-governed；Agentic Shell、ReportAgent、PythonAgent、AuditAgent 都必须通过 `BIWorkbenchTool` / `ask_bi` 使用 BI 能力，不得绕过 BI 工具访问 schema、SQL、数据库或 `control_plane` 主体。

## 背景

前面已经确认 LeadAgent 不适合直接改成自由 ReActAgent，而应先按 Hermes-style 最小能力暴露方式收窄为能力路由。随后继续讨论时，用户明确希望产品形态不要只停留在 B 的 ChatBI 主链，而是从一开始就朝 C 的 Agentic Shell 产品体验设计。

因此本轮决策不是把 B 推翻，而是调整产品叙事和规划顺序：

```text
产品形态直接 C；
BI 查询内核仍按 B-governed 管控。
```

## 选择理由

- C 形态更贴近最终产品：用户不是只要一次问数回答，还会自然期待报告生成、图表分析、Python 分析、审计解释和多步骤任务编排。
- B-governed 内核能守住企业问数边界：外层 Agent 可以更会编排，但 schema、SQL、权限、Manifest、Artifact 和审计真相源不能被绕开。
- Hermes-style 最小能力暴露已经验证效果好，适合作为 BI 能力对外开放的稳定接口，而不是让外层 Agent 直接进入数据集内部。
- 先定义 C 的产品入口，可以避免后续接口只服务 ChatBI，导致未来接 ReportAgent / PythonAgent / AuditAgent 时大面积返工。

## 被排除方案

- 继续采用纯 B-first 产品形态：虽然实现最稳，但产品体验会被限制为“智能问数对话”，后续再补 Agentic Shell 时容易重新设计入口、事件、权限和引用协议。
- 直接做完整 C runtime：风险过高，容易让外层 AgentScope runtime、自由 ReAct、跨工具编排过早进入主链，反而削弱 BI 查询内核的安全边界和可审计性。
- 让 ReportAgent / PythonAgent 直接访问数据库或 schema：违反 B-governed 内核原则，会让权限、口径、SQL Guard 和 QueryArtifact 失去统一真相源。

## 对架构的影响

- 总路线从 `B-first, C-ready` 升级为 `C-shaped product, B-governed BI core`。
- LeadAgent 仍承担受控 BI Capability Router，不升级为自由 ReAct Supervisor。
- 外层新增或规划 `Agentic Shell`，作为产品级任务编排入口。
- `BIWorkbenchTool` / `ask_bi` 成为外层 Agent 调用 BI 能力的唯一入口。
- ReportAgent、PythonAgent、AuditAgent 只能消费 `llm_visible`、`result_ref`、`report_ref` 等受控输出，不能读取 `control_plane` 主体。
- `DatalogueEventEnvelope` 需要同时支持 ChatBI 流式体验和未来 C 形态的任务级事件聚合。
- AgentScope 仍先保留验证线，不能因为产品形态转 C 就第一阶段接管主链 runtime。

## 对开发计划的影响

- P0-P4 继续作为 BI 内核治理工作包：能力清单、Capability Router、DatasetAgent Runtime、ToolAdapter、EventEnvelope。
- P5 从“C-ready 预留口”升级为“C 产品形态入口规划”，需要拆出 Agentic Shell、BIWorkbenchTool、ReportAgent、PythonAgent、AuditAgent、任务级 trace 和产物引用协议。
- P6 继续作为 AgentScope 后续验证线，验证 AgentScope 如何承接标准工具、事件和 runner，而不是绕过 Datalogue 业务内核。
- 里程碑需要从“先 B 后 C”改成“双轨并行”：先让 C 的产品骨架存在，同时优先把 B-governed BI 内核做稳。

## 后续问题

- 第一版 Agentic Shell 的 UI 入口是复用现有 `/chat`，还是新增工作台形态。
- ReportAgent 第一阶段只生成文字报告，还是同时生成图表和可下载产物。
- PythonAgent 第一阶段是否只允许读取 `result_ref` 对应的受控数据切片。
- AuditAgent 面向用户解释、管理员审计和开发排障是否需要拆成不同可见层级。
- `BIWorkbenchTool` 与现有 LeadAgent 工具面的命名、接口和事件如何统一。
