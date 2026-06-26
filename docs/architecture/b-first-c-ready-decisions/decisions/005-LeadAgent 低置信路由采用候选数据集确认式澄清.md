# 005 · LeadAgent 低置信路由采用候选数据集确认式澄清

## 状态

- 状态：已敲定
- 时间：2026-06-26 11:11
- 触发：用户确认“我选择先给出候选数据集和简短理由，再让用户确认；不暴露 schema、字段、资产细节。”

---

## 决策

当 LeadAgent 对数据集路由低置信，或多个候选数据集置信度接近时，采用候选数据集确认式澄清：

```text
给出候选数据集
+ 给出每个候选的简短业务理由
+ 让用户确认选择
+ 不暴露 schema、字段、资产细节
```

澄清信息只基于 `capability_manifest` 中的轻量能力广告，不进入 DatasetAgent 内部执行资产层。

---

## 背景

前面已经确认：

```text
001：capability_manifest 定位为轻量能力广告
002：capability_manifest 采用固化主体 + 运行态叠加
003：static_capability 字段边界只到业务摘要层
004：can_answer 等能力文案采用模型辅助生成 + 人工审核，发布时固化
```

在此基础上，需要明确 LeadAgent 低置信路由时如何与用户交互。如果系统直接猜一个数据集，容易误路由；如果把 schema、字段或资产细节暴露给用户，又会破坏能力路由边界。

---

## 选择理由

选择候选数据集确认式澄清的原因：

- 能把低置信路由变成用户可理解的业务选择。
- 不需要暴露 schema、字段、SQL 或候选资产详情。
- 可以保留 LeadAgent 的受控边界，只使用 capability manifest 做解释。
- 用户确认后的选择可以写入 conversation_state，支持后续多轮追问。
- 比“直接拒答”更友好，比“直接猜测”更安全。

---

## 被排除方案

### 方案一：LeadAgent 直接选择最高分数据集

未采用。

原因：

- 多个数据集能力相近时容易误路由。
- 误路由后的 SQL 和答案可能看起来合理，但业务含义错误。
- 不利于用户理解系统为什么选择该数据集。

### 方案二：直接向用户询问开放式问题

未采用。

原因：

- 用户不知道系统有哪些候选数据集，容易继续回答模糊业务词。
- 会增加澄清轮次。
- 不利于把澄清结果结构化写入状态。

### 方案三：展示 schema、字段或资产详情让用户选择

未采用。

原因：

- 会暴露 DatasetAgent 内部执行资产层。
- 对业务用户不友好。
- 容易把 LeadAgent 拉回 schema/asset 级别的开放规划。

---

## 对架构的影响

LeadAgent 低置信时的澄清输出应保持在业务层：

```text
我找到几个可能相关的数据集：

1. 运营双周会议：覆盖双周会、工作日志、参会和运营协同问题。
2. 合同项目管理：覆盖合同、项目、金额和回款问题。

你想基于哪个数据集继续查询？
```

禁止展示：

```text
表名
字段名
SQL
blueprint 主体
候选资产详情
完整指标公式
完整维度绑定
```

状态写入建议：

```text
pending_clarification:
  type: dataset_selection
  candidates:
    - dataset_id
    - dataset_name
    - reason
    - confidence
  source: lead_agent_capability_router
```

用户确认后，后续调用：

```text
query_dataset(dataset_id, question, context)
```

---

## 对开发计划的影响

后续至少需要拆出这些任务：

- 定义低置信路由阈值和多个候选接近时的判定规则。
- 定义候选数据集澄清 payload。
- 定义用户确认后的状态回放和恢复逻辑。
- 调整前端澄清展示，支持候选数据集选择。
- 增加不泄露 schema、字段、资产细节的内容扫描测试。
- 增加多轮回归：用户确认数据集后，下一轮能继续使用确认结果。
- 增加 Langfuse trace / checkpoint 日志，记录候选数据集、原因和最终选择。

---

## 后续问题

下一个需要敲定的问题：

```text
query_multiple_datasets 的 fan-out 决策边界是什么？
```

可选方向：

```text
只在用户明确要求跨数据集时 fan-out
LeadAgent 可在高置信多域问题中主动 fan-out
先澄清再 fan-out
```

当前初始倾向：

```text
第一阶段默认保守：只有用户明确跨数据集诉求，或问题天然需要多个业务域时，才允许 query_multiple_datasets；否则先澄清。
```
