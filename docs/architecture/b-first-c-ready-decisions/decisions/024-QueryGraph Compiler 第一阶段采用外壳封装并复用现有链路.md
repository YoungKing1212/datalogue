# 024 · QueryGraph Compiler 第一阶段采用外壳封装并复用现有链路

## 状态

- 状态：已敲定
- 时间：2026-06-26 15:55
- 触发：用户在 QueryGraph Compiler 三个落地方案中确认选择方案 2

## 决策

`QueryGraph Compiler` 第一阶段采用独立外壳封装方案：新增或改造 `query_plan_compiler.py` 作为语义计划到 SQL 的稳定边界，新增或改造 `sql_dialect_adapter.py` 作为方言适配边界；内部先复用现有 QueryGraph、SQL context、SQL 生成、Guard 和 preview 链路，不第一阶段重写完整 compiler。

## 背景

第 023 个决策已经敲定：保留 `DSL / QueryGraph / query_plan` 作为 DatasetAgent 内部语义计划层，SQL 编译和方言适配由 Tools 完成。随后的问题是第一阶段如何落地 compiler 边界：

1. 直接改造现有 QueryGraph 执行链。
2. 新增 compiler / dialect adapter 外壳，内部复用现有链路。
3. 重写完整 compiler。

用户确认选择方案 2。

## 选择理由

- 能最快固定 `语义计划 -> 方言 SQL -> Guard -> preview / execute -> artifact` 的工程边界。
- 不要求第一阶段重写现有 QueryGraph 和 SQL 生成细节，降低主链路回归风险。
- 外壳可以先承接契约、trace、泄露扫描、方言适配、fail-closed 和测试，后续再逐步替换内部实现。
- 与当前 “先跑通智能问数核心链路，C-ready 但不大改前端和 runtime” 的节奏一致。

## 被排除方案

### 方案 1：直接改造现有 QueryGraph 执行链

暂不采用。它改动少，但 compiler、方言适配、Guard、执行和 artifact 边界仍容易散在旧链路里，不利于后续 C 形态复用和 AgentScope adapter 接入。

### 方案 3：第一阶段重写完整 compiler

暂不采用。它架构最干净，但第一阶段工作量和回归风险过高，容易拖慢 `capability_manifest`、`ask_bi`、event envelope、ArtifactCard、候选数据集确认和五件套验收这些 P0 主链任务。

## 对架构的影响

- `query_plan_compiler.py` 成为 DatasetAgent 内部语义计划编译的唯一入口。
- `sql_dialect_adapter.py` 成为数据源方言适配的唯一入口。
- 现有 QueryGraph / SQL context / SQL 生成 / Guard / preview 链路可以继续作为内部实现，但上层只能依赖 compiler 外壳契约。
- 编译结果必须明确分层：
  - `control_plane`：最终 SQL、编译诊断、方言信息、Guard 输入摘要。
  - `trace_metadata`：schema version、compiler version、dialect、guard status、artifact id。
  - `llm_visible`：只允许业务摘要、阻断摘要和引用句柄，不包含 SQL。
- 后续替换内部实现时，LeadAgent、BIWorkbenchTool、ArtifactCard 和 event envelope 不应感知内部变化。

## 对开发计划的影响

- P0.3 的实现顺序固定为：
  1. 先写 `test_query_plan_compiler.py` 和 `test_sql_dialect_adapter.py`。
  2. 建立 `query_plan_compiler.py` 和 `sql_dialect_adapter.py` 外壳。
  3. 外壳内部复用现有 QueryGraph / SQL 生成 / Guard / preview 链路。
  4. 补齐 user-visible 防泄露、trace-only 编译事件和 query_artifact 追溯。
  5. 后续再逐步替换内部 compiler 实现。
- 正式开发计划中，P0.3 不再表达为“新增或改造即可”，而是明确外壳优先。
- 后续 C-ready 改造记录需要把“内部实现可替换”作为 AgentScope adapter 和多数据源扩展的接口前提。

## 后续问题

- 第一阶段方言适配的最小数据源集合是只覆盖当前真实数据源，还是同时预留 PostgreSQL / MySQL / SQLite 三类？
- compiler 外壳输出的 `CompiledQueryPlan` 结构是否需要现在就固化 schema version？
- 失败修复链路中，`repair_sql` 是否应改名或拆分为 `repair_query_plan` 与 `repair_compiled_sql`？
