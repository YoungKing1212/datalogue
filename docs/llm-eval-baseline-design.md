# LLM 渐进式资产注入评估基线设计

> 目标：建立可复现的评估体系，衡量在 LeadAgent Planner 中注入「渐进式语义资产」后，LLM 的选择质量是否保持与「全量资产」基准一致。
>
> 核心原则：Skill 数量减少 >= 20% 是虚荣指标；我们只关心 **selection quality**（执行策略 / 工具调用选择正确率）。

---

## 1. 评估数据集构建

### 1.1 复用现有基准

复用 `capture_phase5_fixtures.py` 生成的 25 条 fixture（`tests/fixtures/phase5_analysis_blueprint_fixtures.jsonl`）作为**基线数据集**。

这些 fixture 覆盖 6 类状态：
- `not_applicable` × 2
- `not_found` × 2
- `semantic_plan` × 2
- `executed` × 5
- `clarification` × 3
- `error` × 4
- 边界 × 5
- `safe_sql` 拦截 × 1
- `semantic_plan_blueprint_context` 格式 × 1

**复用方式**：将每条 fixture 的 `input.question` 作为 LeadAgent Planner 的输入，记录 `execution_strategy` 和 `tool_calls` 输出作为基准。

### 1.2 新增渐进式资产召回专项场景（5-10 条）

| 场景类别 | 数量 | 说明 |
|---------|------|------|
| **Miss-recall**（漏召回） | 2-3 | 问题与资产只有模糊关键词匹配（如用户问「销售额」但资产名是「GMV」），测试 LLM 在召回不完整时是否仍能正确选择 `query_graph` 而非强匹配 `blueprint_execute` |
| **Multi-intent**（多意图） | 2-3 | 问题同时命中多个候选资产（如「对比本月和上月的 GMV 与订单量」），测试 LLM 在资产列表截断后是否仍能正确选择 `blueprint_as_reference` 或 `query_graph` |
| **Empty-recall**（空召回） | 1-2 | 问题完全不匹配任何语义资产（如「系统状态如何」），测试 LLM 是否优雅降级到 `clarify` 或 `reject`，而非 hallucinate 资产 |
| **Threshold-edge**（阈值边缘） | 2 | 构造置信度刚好在阈值上下（0.04 vs 0.06）的资产，测试过滤阈值敏感性对选择结果的影响 |

**每条新增场景需包含**：
- `question`: 用户问题文本
- `locked_dataset_id`: 锁定数据集 ID
- `full_assets`: 全量资产列表（基准运行用）
- `filtered_assets`: 渐进式召回后的过滤资产列表（实验运行用）
- `expected_strategy`: 期望的执行策略（由全量资产运行结果确定）
- `expected_tools`: 期望的工具调用序列
- `is_adversarial`: 是否为对抗性案例（用于监控鲁棒性）

### 1.3 数据集 seed 策略

1. **从真实对话日志提取（脱敏）**
   - 来源：历史 Langfuse trace 归档、当前后端结构化日志或可脱敏的 fixture 捕获结果中的 `llm.lead_agent_tool_planner` 输入输出
   - 筛选条件：
     - `tool_policy.locked_dataset_id` 不为空
     - 最终执行策略为 `blueprint_execute` 或 `query_graph` 的 case
     - 问题长度 10-100 字符
   - 脱敏：去除用户 ID、企业名称、具体数值，替换为占位符

2. **手工构造对抗案例**
   - 由领域专家编写，专门针对渐进式资产召回的弱点
   - 覆盖：同义词歧义、多表关联意图、时间范围模糊、指标别名

3. **负向测试（1-2 条）**
   - 构造应触发 `clarify` 或 `reject` 的问题，验证在资产过滤后 LLM 不会错误地选择执行策略
   - 示例：「帮我看看」→ 应 `clarify`（缺意图）；「删除所有数据」→ 应 `reject`（危险操作）

---

## 2. 评估指标

### 2.1 核心质量指标

| 指标 | 定义 | 计算方式 |
|------|------|---------|
| **Selection accuracy** | 选择准确率 | `% of cases where LLM picks the same execution_strategy / tool_calls with filtered assets as with full assets` |
| **Fallback rate** | 降级率 | `% of cases that fall back to clarify/reject when full-asset path would not` |
| **Clarification rate** | 澄清率 | `% of cases that ask for clarification when full-asset path would not` |
| **SQL success rate** | SQL 成功率（如适用） | `% of cases where final SQL query succeeds`（仅针对 `blueprint_execute` / `query_graph` 路线） |
| **TTFT delta** | 首 token 时间差 | `time to first token with progressive assets vs without progressive assets` |

### 2.2 指标说明与容忍度

- **Selection accuracy**：比较两个运行结果的 `execution_strategy` 字符串和 `tool_calls` 列表（忽略 `reason` 字段的文本差异，只比较 `tool` 名和参数结构）。
- **Fallback rate**：渐进式资产运行结果为 `clarify`/`reject`，但全量资产运行结果为 `blueprint_execute`/`query_graph`/`blueprint_as_reference` 的 case 占比。
- **Clarification rate**：渐进式资产运行结果为 `clarify`，但全量资产运行结果为非 `clarify` 的 case 占比。
- **SQL success rate**：对于最终进入 SubAgent 执行的 case，对比 SQL 执行是否成功（通过 mock DB 或实际数据源验证）。
- **TTFT delta**：通过本地计时器、后端结构化日志或历史 trace 归档测量 `llm.lead_agent_skill_selector` 和 `llm.lead_agent_tool_planner` 的首 token 返回时间差。

---

## 3. 评估 Harness

### 3.1 文件位置

`datalogue-api/tests/evals/test_progressive_assets.py`

### 3.2 复用 helper

复用 T6 中的 `assert_planner_outputs_equivalent` 辅助函数（若 T6 尚未实现，则在本 harness 中内联定义最小版本）：

```python
def assert_planner_outputs_equivalent(
    full_output: dict,
    filtered_output: dict,
    *,
    ignore_reason_text: bool = True,
    strategy_field: str = "execution_strategy",
    tools_field: str = "tool_calls",
) -> bool:
    """比较两个 planner 输出是否等价。

    等价规则：
    1. execution_strategy 必须完全相同
    2. tool_calls 的 tool 名和参数结构必须相同（忽略 reason 文本差异）
    3. 如果任一为 clarify/reject，另一方必须一致
    """
    ...
```

### 3.3 运行模式

评估脚本支持两种运行模式：

1. **基准模式**：`LEAD_AGENT_PLANNER_USE_PROJECTION=false`（或环境变量未设置）
   - 运行全量资产路径，记录输出为基准

2. **实验模式**：`LEAD_AGENT_PLANNER_USE_PROJECTION=true`
   - 运行渐进式资产路径，与基准对比

### 3.4 评估流程

```python
def run_eval_case(case: dict, db: Session) -> dict:
    # 1. 基准运行（全量资产）
    baseline = plan_tool_calls_with_llm(
        db,
        question=case["question"],
        conversation_summary=case.get("conversation_summary", {}),
        tool_policy=case["tool_policy"],
        skills=case["skills"],
    )

    # 2. 实验运行（渐进式资产）
    with mock_env("LEAD_AGENT_PLANNER_USE_PROJECTION", "true"):
        experiment = plan_tool_calls_with_llm(
            db,
            question=case["question"],
            conversation_summary=case.get("conversation_summary", {}),
            tool_policy=case["tool_policy"],
            skills=case["skills"],
        )

    # 3. 计算指标
    return {
        "case_name": case["name"],
        "selection_match": assert_planner_outputs_equivalent(baseline, experiment),
        "baseline_strategy": baseline["execution_strategy"],
        "experiment_strategy": experiment["execution_strategy"],
        "fallback_occurred": _is_fallback(baseline, experiment),
        "clarification_delta": _is_clarification_delta(baseline, experiment),
        "ttft_delta_ms": _measure_ttft_delta(baseline, experiment),
    }
```

### 3.5 输出格式

评估结果输出为 JSON Lines 文件，每条记录包含：
- `case_name`: 场景名称
- `selection_match`: bool
- `baseline_strategy`: str
- `experiment_strategy`: str
- `fallback_occurred`: bool
- `clarification_delta`: bool
- `ttft_delta_ms`: float
- `sql_success_match`: bool | None（仅当适用）

汇总报告输出到 stdout：
```
=== Progressive Asset Injection Eval Report ===
Total cases: 35
Selection accuracy: 97.1% (34/35)
Fallback rate: 0.0% (0/35)
Clarification rate: 2.9% (1/35)
Mean TTFT delta: +120ms (filtered: 340ms vs full: 460ms)
SQL success rate match: 100% (12/12)

Failed cases:
  - multi_intent_gmv_vs_orders: expected=query_graph, got=blueprint_execute
```

---

## 4. 验收标准

| 指标 | 阈值 | 说明 |
|------|------|------|
| **Selection accuracy** | >= 95% | 允许 5% 的 delta 容忍（因为资产过滤本身会引入信息损失） |
| **Fallback rate** | <= baseline + 2% | 不能显著增加降级率 |
| **Clarification rate** | <= baseline + 2% | 不能显著增加澄清率 |
| **TTFT delta** | <= 500ms | 渐进式资产注入不能显著增加首 token 延迟 |
| **SQL success rate** | >= baseline - 2% | 最终执行成功率不能显著下降 |

**注**：baseline 指 `LEAD_AGENT_PLANNER_USE_PROJECTION=false` 时的指标值。

---

## 5. 数据集 seed 详细指南

### 5.1 从真实对话日志提取

1. 从历史 Langfuse trace 归档或当前后端结构化日志中提取 planner 样本。旧 Langfuse 表可按以下 SQL 追溯；当前运行时不再写入这些表：
   ```sql
   SELECT
     t.id as trace_id,
     o.input as question,
     o.output as planner_output,
     o.metadata->>'tool_policy' as tool_policy
   FROM traces t
   JOIN observations o ON t.id = o.trace_id
   WHERE o.name = 'llm.lead_agent_tool_planner'
     AND o.metadata->>'locked_dataset_id' IS NOT NULL
     AND o.start_time > NOW() - INTERVAL '7 days'
   LIMIT 100;
   ```

2. 人工筛选 20-30 条高质量 case，按以下规则标注：
   - 问题意图明确
   - 有明确的 `execution_strategy` 结果
   - 覆盖 `blueprint_execute`、`query_graph`、`clarify` 三类

3. 脱敏处理：
   - 替换企业名称为 `{{company_name}}`
   - 替换具体数值为 `{{value}}`
   - 移除用户 ID、会话 ID

### 5.2 手工对抗案例模板

```yaml
miss_recall_1:
  question: "最近销售额怎么样"
  locked_dataset_id: 1
  full_assets:
    - asset_type: blueprint
      name: "GMV 概览"
      confidence: 0.95
  filtered_assets:
    - asset_type: blueprint
      name: "GMV 概览"
      confidence: 0.15  # 关键词不匹配导致置信度低，被过滤
  expected_strategy: "query_graph"
  is_adversarial: true

multi_intent_1:
  question: "对比本月和上月的 GMV 与订单量"
  locked_dataset_id: 1
  full_assets:
    - asset_type: blueprint
      name: "GMV 趋势"
      confidence: 0.90
    - asset_type: blueprint
      name: "订单量统计"
      confidence: 0.85
  filtered_assets:
    - asset_type: blueprint
      name: "GMV 趋势"
      confidence: 0.90
    # 订单量被截断，只剩 1 个 blueprint
  expected_strategy: "query_graph"  # 或 blueprint_as_reference
  is_adversarial: true

empty_recall_1:
  question: "系统状态如何"
  locked_dataset_id: 1
  full_assets: []
  filtered_assets: []
  expected_strategy: "clarify"
  is_adversarial: true

threshold_edge_1:
  question: "查一下 GMV"
  locked_dataset_id: 1
  full_assets:
    - asset_type: blueprint
      name: "GMV 概览"
      confidence: 0.06
  filtered_assets:
    - asset_type: blueprint
      name: "GMV 概览"
      confidence: 0.06  # 刚好在阈值上（0.05）
  expected_strategy: "blueprint_execute"
  is_adversarial: true

threshold_edge_2:
  question: "查一下 GMV"
  locked_dataset_id: 1
  full_assets:
    - asset_type: blueprint
      name: "GMV 概览"
      confidence: 0.04
  filtered_assets: []  # 低于阈值 0.05，被过滤
  expected_strategy: "query_graph"  # 没有 blueprint 时 fallback
  is_adversarial: true
```

### 5.3 负向测试案例

```yaml
negative_clarify:
  question: "帮我看看"
  locked_dataset_id: 1
  full_assets: []
  filtered_assets: []
  expected_strategy: "clarify"
  reason: "意图不明确，应澄清而非 hallucinate"

negative_reject:
  question: "删除所有数据"
  locked_dataset_id: 1
  full_assets: []
  filtered_assets: []
  expected_strategy: "reject"
  reason: "危险操作，应拒绝"
```

---

## 6. 实施计划

| 阶段 | 任务 | 负责人 | 时间 |
|------|------|--------|------|
| P1 | 提取真实对话日志并脱敏 | 数据团队 | 1d |
| P2 | 编写手工对抗案例（5-10 条） | 领域专家 | 0.5d |
| P3 | 实现 `assert_planner_outputs_equivalent` helper | 开发 | 0.5d |
| P4 | 编写 `test_progressive_assets.py` harness | 开发 | 1d |
| P5 | 运行基准测试并记录 baseline 指标 | QA | 0.5d |
| P6 | 运行渐进式资产测试并对比 | QA | 0.5d |
| P7 | 分析失败 case，决定是否调优阈值 | 开发+领域专家 | 1d |

---

## 7. 附录：与现有测试的关系

| 现有测试 | 关系 | 说明 |
|---------|------|------|
| `test_phase5_equivalence.py` | 基线数据源 | 复用其 fixture 作为 selection accuracy 的输入 |
| `capture_phase5_fixtures.py` | 基线数据源 | 25 条 fixture 覆盖 6 类状态 |
| `test_lead_agent_tools.py` | 参考 | 参考其 LeadAgent 工具调用断言方式 |
| `test_query_plan_prompting.py` | 参考 | 参考其 prompt 注入和 mock LLM 方式 |

---

> 文档版本：v1.0
> 创建日期：2026-06-17
> 作者：yangkai
> 适用范围：LeadAgent Planner 渐进式资产注入 M1 阶段
