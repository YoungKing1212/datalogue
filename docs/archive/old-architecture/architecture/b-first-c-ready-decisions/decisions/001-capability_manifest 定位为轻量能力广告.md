# 001 · capability_manifest 定位为轻量能力广告

## 状态

- 状态：已敲定
- 时间：2026-06-26 10:55
- 触发：用户确认“我也倾向于前者”

---

## 决策

`capability_manifest` 定位为给 LeadAgent 和未来外层 Agentic Shell 使用的轻量能力广告，不作为 DatasetAgent 的完整执行说明书，也不替代 Manifest、语义资产、QueryGraph 或 SQL 执行上下文。

---

## 背景

当前整体方向已经确定为：

```text
B-first, C-ready
```

也就是先做 Hermes-style BI Capability Router，后续为 Agentic Shell 预留调用口。这个方向要求 LeadAgent 只面对稳定、轻量、可审计的数据集能力，而不是直接接触数据集内部执行细节。

因此需要先明确 `capability_manifest` 的定位：它到底是给 LeadAgent 路由用，还是给 DatasetAgent 执行用。

---

## 选择理由

选择“轻量能力广告”的原因：

- 可以让 LeadAgent 基于数据集能力做路由，而不是被 schema、字段、候选资产和 SQL 细节污染。
- 可以保持 DatasetAgent 的执行面边界，避免 LeadAgent 抢走资产召回、查询规划和 SQL 生成职责。
- 可以降低 LeadAgent context 体积，提升路由稳定性。
- 可以作为未来 Agentic Shell 发现 BI 能力的安全入口。
- 可以让 Manifest、语义资产、QueryGraph、SQL Guard、Artifact 和 Trace 继续留在 Datalogue 业务内核里。

---

## 被排除方案

### 方案一：把 capability_manifest 做成完整执行说明书

未采用。

原因：

- 字段会过重，容易把 schema、指标、维度、blueprint、SQL 生成细节重新暴露给 LeadAgent。
- 会削弱 DatasetAgent 的边界。
- 未来外层 Agentic Shell 也可能拿到过多内部信息，破坏 C-ready 的安全隔离。

### 方案二：不单独定义 capability_manifest，继续让 LeadAgent 读现有上下文

未采用。

原因：

- 现有上下文混合了路由、执行、资产和结果状态，边界不够清晰。
- 不利于后续把 BI 能力包装成稳定工具。
- 不利于外层 Agentic Shell 复用。

---

## 对架构的影响

LeadAgent 可见内容收窄为：

```text
dataset_id
dataset_name
description
availability
can_answer
cannot_answer
routing_hints
query_capabilities
clarification_policy
```

DatasetAgent 内部继续持有：

```text
schema 明细
候选资产详情
指标/维度绑定
blueprint
QueryGraph
SQL 生成上下文
SQL Guard 细节
完整执行结果
capsule 主体
```

---

## 对开发计划的影响

后续至少需要拆出这些任务：

- 定义 `CapabilityManifest` schema。
- 明确哪些字段来自发布态，哪些字段来自运行态。
- 建立 `list_datasets()` 的轻量返回协议。
- 建立 `describe_dataset_capability(dataset_id)` 的详细返回协议。
- 调整 LeadAgent 路由输入，让它优先使用 `capability_manifest`。
- 增加能力清单快照或 API 输出，便于人工审查。
- 补真实数据集样例，验证能力清单能支持路由和澄清。

---

## 后续问题

下一个需要敲定的问题：

```text
capability_manifest 是发布时固化，还是运行时动态生成？
```

当前倾向：

```text
发布时固化能力主体
+ 运行时叠加状态 / 权限 / 健康度
```
