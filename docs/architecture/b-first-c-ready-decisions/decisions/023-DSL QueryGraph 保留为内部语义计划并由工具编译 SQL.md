# 023 · DSL / QueryGraph 保留为内部语义计划并由工具编译 SQL

## 状态

- 状态：已敲定
- 时间：2026-06-26 13:29
- 触发：用户确认使用方案 C，并确认 DSL 转 SQL 由 Tools 承担方言适配

## 决策

在 C 产品形态下，继续保留 `DSL / QueryGraph / query_plan` 作为 DatasetAgent 内部语义计划层；LLM 不直接生成最终 SQL 作为执行依据，DSL / QueryGraph 到 SQL 的转换、SQL Guard、预览执行和方言适配全部由 Tools 完成。

## 背景

当前路线已经确定为：

```text
C-shaped product, B-governed BI core
```

也就是产品体验直接朝 Agentic Shell、BI 工作台、报告、分析和审计解释演进，但智能问数主链仍要保持高可信、可审计、可回放。用户进一步确认：C 产品形态下仍然需要解决“是否继续生成 DSL、由 LLM 生成 SQL，还是直接由工具生成 SQL”的边界问题。

## 选择理由

- `DSL / QueryGraph` 适合作为语义计划层，能够表达指标、维度、过滤、时间范围、分组、排序、聚合和查询意图，比直接 SQL 更适合作为 Agent 内部可校验协议。
- SQL 是执行层产物，包含数据源方言、权限、安全限制、表字段映射和执行细节，不适合由外层 Agent 或自由 LLM 直接生成并执行。
- 方言适配属于确定性工程能力，应该沉到 Tools 中处理，不应该依赖模型每次猜测不同数据库的 SQL 写法。
- 这样可以保留现有 QueryGraph、Manifest、SQL Guard、preview、ArtifactStore 和 trace 的治理资产，同时为 C 形态的 Agentic Shell 提供稳定工具能力。

## 被排除方案

### 方案 A：完全不生成 DSL，直接让 LLM 生成 SQL

不采用。原因是 SQL 直接生成会把语义规划、方言适配、安全校验和执行细节混在一起，难以做稳定审计，也容易让外层 Agent 绕过 DatasetAgent 的治理边界。

### 方案 B：让 Tools 完全自行从自然语言生成 SQL

不作为第一阶段主方案。原因是自然语言到查询意图仍需要模型参与理解，完全工具化会让复杂问题、追问和业务语义归一化成本过高。更稳的方式是让 LLM 在 DatasetAgent 内部辅助产出语义计划，再由 Tools 编译和校验。

### 方案 C：保留 DSL / QueryGraph，由 Tools 编译 SQL 并做方言适配

采用。LLM 只在 DatasetAgent 内部辅助生成或修复语义计划，最终 SQL 由工具链根据 manifest、语义资产、数据源类型和 SQL Guard 生成。

## 对架构的影响

- LeadAgent、Agentic Shell、ReportAgent、PythonAgent、AuditAgent 都不能直接生成 SQL，也不能消费 raw SQL。
- DatasetAgent 内部可以调用 LLM 生成或补全语义计划，但不能把 LLM 输出的 SQL 直接作为执行依据。
- Tools 需要承担以下职责：
  - DSL / QueryGraph schema 校验。
  - 指标、维度、过滤、时间范围和聚合意图归一化。
  - 语义资产到物理字段 / 表的受控映射。
  - 数据源 SQL 方言适配。
  - SQL 生成。
  - SQL Guard。
  - preview / execute。
  - query_artifact 持久化。
- 最终 SQL 属于 `control_plane`，不得进入 LeadAgent context、Agentic Shell context、用户可见 event、`ArtifactCard`、`preview_payload` 或普通 Chat message body。

## 对开发计划的影响

- P0 后端核心链路需要补一项 `QueryGraph Compiler / Dialect Adapter`。
- `BIWorkbenchTool` / `ask_bi` 只能返回轻量摘要、引用和产物卡，不能返回 SQL。
- `DatalogueEventEnvelope` 需要把 SQL 编译、方言适配、SQL Guard 等内部事件标记为 `trace_only` 或 `control_plane`。
- 测试需要覆盖：
  - LLM 输出 SQL 不会直接进入执行。
  - 不同数据源方言由工具层适配。
  - user-visible payload、SSE、ArtifactCard 不泄露 raw SQL。
  - SQL Guard 和 query_artifact 仍能追溯最终执行 SQL。

## 后续问题

- QueryGraph Compiler 第一阶段是改造现有 QueryGraph 执行链，还是新增独立 `query_plan_compiler.py` 作为外壳？
- 方言适配第一阶段支持哪些数据源类型，是否先按当前项目真实数据源收敛最小集合？
- LLM 生成的语义计划失败时，repair 是修 DSL / QueryGraph，还是允许工具返回候选修复建议后再由模型补全？
