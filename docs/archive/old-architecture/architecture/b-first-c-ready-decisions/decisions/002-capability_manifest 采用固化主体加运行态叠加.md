# 002 · capability_manifest 采用固化主体加运行态叠加

## 状态

- 状态：已敲定
- 时间：2026-06-26 11:02
- 触发：用户确认“这个混合模式可以定”

---

## 决策

`capability_manifest` 采用混合生成模式：

```text
发布时固化能力主体
+ 运行时叠加状态 / 权限 / 健康度
```

也就是说，数据集“能回答什么、不能回答什么、典型问题、路由提示、查询能力”等相对稳定的能力描述在发布阶段固化；Manifest 状态、权限状态、质量状态、schema freshness、当前用户可读性等运行态信息在请求时动态叠加。

---

## 背景

第 `001` 个决策已经确认：`capability_manifest` 是给 LeadAgent 和未来外层 Agentic Shell 使用的轻量能力广告，不是 DatasetAgent 的完整执行说明书。

在这个前提下，需要继续明确能力清单的生成方式。如果完全固化，可能无法反映实时权限和 Manifest 状态；如果完全运行时生成，又会让能力描述不稳定、不易审计，也增加每轮路由成本。

---

## 选择理由

选择混合模式的原因：

- 能力主体稳定，方便审查、发布、回滚和测试。
- 运行时状态真实，避免 LeadAgent 被过期权限或失效 Manifest 误导。
- 可将业务能力与执行准入分开治理。
- 适合未来外层 Agentic Shell 做能力发现，同时保持实际调用前的 fail-closed 门禁。
- 可以降低每轮动态生成成本，避免把语义资产全量聚合放到请求路径上。

---

## 被排除方案

### 方案一：完全发布时固化

未采用。

原因：

- 无法表达当前用户是否可读。
- 无法反映 Manifest stale、quality failed、schema 变化等运行态风险。
- 外层 Agent 可能看到“能力可用”，但实际执行已经被治理状态阻断。

### 方案二：完全运行时动态生成

未采用。

原因：

- 每轮请求都重新聚合能力描述，成本更高。
- 能力清单不稳定，不利于审查、测试和回放。
- 容易把过多语义资产细节重新卷入 LeadAgent context。

---

## 对架构的影响

`capability_manifest` 可以拆成两层：

```text
static_capability:
  dataset identity
  can_answer
  cannot_answer
  routing_hints
  typical_questions
  query_capabilities
  clarification_policy

runtime_overlay:
  current_user_permission
  manifest_status
  quality_status
  schema_freshness
  availability
  block_reasons
```

LeadAgent 路由时应同时看到这两层，但不能因为 `static_capability` 显示“能回答”就绕过 `runtime_overlay` 的阻断。

---

## 对开发计划的影响

后续至少需要拆出这些任务：

- 定义 `static_capability` schema。
- 定义 `runtime_overlay` schema。
- 明确静态能力生成时机：数据集发布、Manifest 发布或语义资产审核通过后。
- 明确运行态叠加时机：每次 LeadAgent 路由前或 `describe_dataset_capability` 调用时。
- 定义 `availability.status` 和 `block_reasons` 的枚举。
- 增加能力清单发布态快照，用于审查和回归测试。
- 增加运行态 overlay 的单元测试，覆盖权限不足、Manifest stale、quality failed、schema stale 等阻断场景。

---

## 后续问题

下一个需要敲定的问题：

```text
static_capability 的字段边界具体到哪一级？
```

当前倾向：

```text
只到业务能力、典型问题、指标/维度名称摘要、路由提示和不可回答范围；
不进入字段、表、SQL、blueprint 主体和完整语义资产详情。
```
