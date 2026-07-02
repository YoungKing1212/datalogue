# 003 · static_capability 字段边界只到业务摘要层

## 状态

- 状态：已敲定
- 时间：2026-06-26 11:05
- 触发：用户确认“我确定先定为：只到业务能力、典型问题、指标/维度名称摘要、路由提示和不可回答范围；不进入字段、表、SQL、blueprint 主体和完整语义资产详情。”

---

## 决策

`static_capability` 的字段边界只到业务摘要层，用于支持 LeadAgent 和未来外层 Agentic Shell 做能力发现、数据集路由、澄清判断和拒答判断。

它包含：

```text
业务能力
典型问题
指标/维度名称摘要
路由提示
不可回答范围
```

它不包含：

```text
字段
表
SQL
blueprint 主体
完整语义资产详情
```

---

## 背景

前两个决策已经确认：

```text
001：capability_manifest 定位为轻量能力广告
002：capability_manifest 采用固化主体 + 运行态叠加
```

因此需要继续明确固化主体 `static_capability` 到底详细到什么程度。如果字段过粗，LeadAgent 路由能力不足；如果字段过细，会把 DatasetAgent 执行面细节重新泄露到 LeadAgent context。

---

## 选择理由

选择业务摘要层的原因：

- 足够支持 LeadAgent 判断“这个数据集能不能回答这个问题”。
- 足够支持未来 Agentic Shell 发现 BI 能力。
- 不会让 LeadAgent 接触表、字段、SQL 和 blueprint 主体。
- 保持 DatasetAgent 对 schema、资产召回、查询规划和 SQL 执行的独占边界。
- 避免 capability manifest 变成另一个膨胀版数据集上下文。

---

## 被排除方案

### 方案一：只保留数据集名称和一句描述

未采用。

原因：

- 对 LeadAgent 路由帮助不足。
- 无法表达不可回答范围。
- 无法支撑低置信澄清和多数据集 fan-out 判断。

### 方案二：暴露完整指标、维度、字段、表和 blueprint 详情

未采用。

原因：

- 会把 DatasetAgent 的执行细节前移到 LeadAgent。
- 容易导致 LeadAgent 自己推断 SQL 或绕过 DatasetAgent。
- 会增加上下文体积和幻觉风险。
- 不利于未来外层 Agentic Shell 的安全隔离。

---

## 对架构的影响

`static_capability` 建议字段保持在以下层级：

```yaml
static_capability:
  dataset:
    id: 12
    name: 运营双周会议
    description: 用于分析双周会议、工作日志、参会和运营协同情况
  can_answer:
    - 会议数量统计
    - 工作日志明细查询
    - 按时间查看会议或日志趋势
    - 按人员或部门查看协同情况
  cannot_answer:
    - 财务收入
    - 合同金额
    - 销售回款
  metric_summaries:
    - 会议数
    - 工作日志数
  dimension_summaries:
    - 时间
    - 人员
    - 部门
  routing_hints:
    business_domains:
      - 会议管理
      - 工作日志
      - 运营协同
    keywords:
      - 双周会
      - 工作日志
      - 参会
      - 杨凯
  typical_questions:
    - 2024 年杨凯有哪些工作日志？
    - 今年双周会议开了多少次？
```

禁止进入 `static_capability` 的内容：

```text
source_tables
selected_columns
column lineage
join graph
blueprint steps body
raw SQL
sample rows
full metric formula
full dimension binding
```

---

## 对开发计划的影响

后续至少需要拆出这些任务：

- 定义 `static_capability` 字段 schema。
- 建立字段白名单，防止 schema、表字段、SQL、blueprint 主体进入能力清单。
- 为 `metric_summaries` 和 `dimension_summaries` 定义摘要生成规则。
- 为 `can_answer` / `cannot_answer` 定义人工维护、规则生成或模型辅助审核流程。
- 增加 capability manifest 体积预算和内容扫描测试。
- 增加快照测试，确认能力清单不泄露字段、表、SQL 和 blueprint 主体。

---

## 后续问题

下一个需要敲定的问题：

```text
can_answer / cannot_answer / typical_questions 由谁生成和审核？
```

可选方向：

```text
人工维护
规则聚合生成
模型辅助生成 + 人工审核
```

当前倾向：

```text
模型辅助生成 + 人工审核，发布时固化。
```
