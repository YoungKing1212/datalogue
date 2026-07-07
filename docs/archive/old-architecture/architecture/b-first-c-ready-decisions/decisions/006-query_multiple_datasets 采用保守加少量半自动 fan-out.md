# 006 · query_multiple_datasets 采用保守加少量半自动 fan-out

## 状态

- 状态：已敲定
- 时间：2026-06-26 11:23
- 触发：用户确认“可以，按你的建议做”

---

## 决策

第一阶段 `query_multiple_datasets` 采用：

```text
保守为主 + 少量半自动 fan-out
```

默认不主动 fan-out。只有在以下两类场景中，LeadAgent 才允许调用 `query_multiple_datasets`：

1. 用户明确提出跨数据集、跨业务域或多对象对比诉求。
2. 用户问题天然需要多个业务域共同回答，且候选数据集的能力边界清晰、运行态均可用。

其他多个数据集都可能相关但意图不清的情况，优先走候选数据集确认式澄清。

---

## 背景

前面已经确认：

```text
001：capability_manifest 定位为轻量能力广告
002：capability_manifest 采用固化主体 + 运行态叠加
003：static_capability 字段边界只到业务摘要层
004：can_answer 等能力文案采用模型辅助生成 + 人工审核，发布时固化
005：LeadAgent 低置信路由采用候选数据集确认式澄清
```

在此基础上，需要明确 LeadAgent 什么时候可以主动查询多个数据集。如果 fan-out 太积极，会引入多数据集口径拼接风险；如果完全禁止，又会限制用户明确跨域分析的能力。

---

## 选择理由

选择“保守 + 少量半自动”的原因：

- 第一阶段优先保证问数链路可信、可审计、可回放。
- 避免 LeadAgent 因能力描述相似而随意跨数据集组合结果。
- 对用户明确提出的跨域问题保留可用路径。
- 对天然跨域问题保留少量自动化空间，但要求能力边界和运行态都清楚。
- 与 `005` 的低置信澄清策略配套：不确定时先问，不默认扩张执行面。

---

## 被排除方案

### 方案一：只有用户明确要求跨数据集时才 fan-out

未完全采用。

原因：

- 足够安全，但过于保守。
- 有些问题天然需要多个业务域共同回答，用户未必会显式说“跨数据集”。
- 会让系统在明显多域问题上显得不够智能。

### 方案二：LeadAgent 可在高置信多域问题中主动 fan-out

未完全采用。

原因：

- 方向有价值，但第一阶段如果不加限制，容易扩大执行面。
- 多数据集结果合并涉及口径、权限、时间范围和解释一致性，不能只靠模型判断。

### 方案三：只要多个数据集都可能相关，一律先澄清

未采用。

原因：

- 最安全，但会增加交互成本。
- 用户明确跨数据集诉求时没有必要再问一次。
- 会削弱后续 C-ready 外层 Agentic Shell 的任务编排能力。

---

## 对架构的影响

LeadAgent 的 fan-out 判断建议分为三档：

```text
L0：单数据集高置信
  -> query_dataset

L1：多个候选相关但意图不清
  -> candidate dataset clarification

L2：明确跨域或天然多域问题
  -> query_multiple_datasets
```

允许 fan-out 的条件：

```text
用户明确要求对比 / 汇总 / 联合分析多个业务域
或问题语义天然包含多个已知业务域
且每个候选数据集 runtime_overlay 都允许查询
且不需要跨数据集 join，只做结果级汇总或并列解释
```

第一阶段不允许：

```text
跨数据集自由 join
跨数据集 raw SQL 拼接
把多个数据集 schema 合并给 LeadAgent
让 LeadAgent 自行统一不同数据集口径
```

---

## 对开发计划的影响

后续至少需要拆出这些任务：

- 定义 `query_multiple_datasets` 的调用条件。
- 定义 fan-out 触发分类：用户明确跨域、天然多域、候选相近需澄清。
- 定义多数据集调用的入参结构和每个 invocation 的独立 `dataset_id/question/context`。
- 定义多数据集结果汇总协议：只汇总 `llm_visible`，不合并 control plane 主体。
- 增加禁止跨数据集 SQL join 的 guard。
- 增加运行态检查：每个候选数据集都必须通过 runtime overlay。
- 增加测试覆盖：单数据集、高置信多域、候选相近澄清、权限阻断、多数据集结果汇总。

---

## 后续问题

下一个需要敲定的问题：

```text
DatasetAgentToolAdapter 的正式出参 schema 如何定义？
```

可选方向：

```text
只定义 llm_visible/control_plane/trace_metadata 三段
进一步细分 result/artifact/error/clarification
先复用现有 SubAgentToolResult，再逐步迁移
```

当前初始倾向：

```text
定义三段式协议作为目标形态，同时允许第一阶段适配现有 SubAgentToolResult，避免大规模重写。
```
