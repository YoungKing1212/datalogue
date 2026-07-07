# SubAgent Planner 资产详情受控循环设计

## 背景

当前 SubAgent 查询规划链路先通过 `recall_candidate_assets()` 从轻量数据集上下文中召回候选资产，再把候选资产交给 `plan_query()` 判断查询类型和执行策略。候选资产已经覆盖 `blueprint`、`metric`、`dimension`、`term`、`field`、`table` 等类型，但 planner 输入仍容易在“召回目录”和“SQL 生成上下文”之间混用：如果提前塞入过多字段、蓝图、SQL 模板或 schema 元信息，token 成本高，也会让跨轮状态、trace、SSE 和 final payload 膨胀；如果只给轻量目录，又可能缺少生成 SQL 所需的字段、join、时间字段和指标口径。

本设计将候选资产链路拆成两阶段：第一阶段只给 SubAgent planner 轻量资产目录；第二阶段由 SubAgent planner 在受控循环中请求资产详情，后端负责校验、限流和水合详情。目标是减少默认上下文体积，同时让 SQL 生成前能够拿到必要、可审计的资产细节。

## 目标

- SubAgent planner 首次只消费轻量资产目录，不默认接收完整字段 schema、完整蓝图或完整 SQL 上下文。
- SubAgent planner 可以主动请求资产详情，但最多 3 轮。
- 资产详情请求只允许命中本轮召回目录中的资产。
- 普通表可以返回整表 schema；超宽表不强行返回全字段，而是返回 `coverage=too_large`，引导 planner 使用自然语言字段搜索补齐。
- 字段搜索默认 `top_k=30`，最大不超过 `50`。
- 字段搜索允许关键字段 boost，但必须返回 `boosted`、`boost_reason`、`text_score` 和 `final_score`。
- 3 轮后上下文仍不足时，不允许硬生成 SQL，必须输出 `clarify` 或 `reject`。
- 后续 SQL/DSL/QueryGraph 节点消费明确的 `sql_generation_context`，不直接从候选资产 metadata 中散取上下文。

## 非目标

- 不在首版改造 LeadAgent 侧的渐进式资产注入。
- 不开放 LLM 自由 tool loop；工具请求由后端状态机执行和校验。
- 不支持跨数据集资产详情请求。
- 不在首版实现字段分页、字段分组或全局字段检索。
- 不把完整资产详情写入 `last_success_task`、SSE final payload 或跨轮状态。

## 架构

### 主要模块

- `AssetDetailService`
  - 根据资产类型和 `detail_level` 返回资产详情。
  - 支持 `table.full_schema`、`table.field_search`、`metric.detail`、`dimension.detail`、`blueprint.detail`。
  - 负责超宽表判定、字段搜索、关键字段 boost、coverage 和 risk flags。

- `PlannerDetailLoop`
  - 包装现有 `plan_query()` 的 planner 调用。
  - 管理最多 3 轮 `asset_detail_requests`。
  - 校验请求范围、类型、轮次、top-k 和 detail level。
  - 将详情结果喂回 planner，直到产出最终 `QueryPlan` 或失败计划。

- `AssetDetailRequest`
  - 记录 planner 请求的资产类型、资产 ID、详情级别、用途、原因、字段搜索 query 和 top-k。

- `AssetDetailResult`
  - 记录详情内容、coverage、risk flags、完整性声明、补请求建议和错误码。

- `sql_generation_context`
  - 后端组装的 SQL 生成上下文。
  - 后续 QueryGraph/DSL/SQL 生成节点只消费该结构，而不是直接依赖原始 candidate assets。

### 链路位置

该机制只放在 SubAgent 查询规划层：

1. `DatasetSubAgent.run()` 调用候选资产召回。
2. 候选资产投影成轻量目录。
3. `PlannerDetailLoop` 调用 planner。
4. planner 输出详情请求或最终计划。
5. 后端校验并水合详情，最多 3 轮。
6. 最终 `QueryPlan` 和 `sql_generation_context` 驱动后续执行策略。

## 轻量资产目录

第一阶段目录只保留 planner 判断是否需要详情的必要信息。首版目录类型控制为：

- `metric`
- `dimension`
- `table`
- `blueprint`

示例：

```json
{
  "asset_type": "table",
  "asset_id": "plan_task_daily_record",
  "name": "plan_task_daily_record",
  "display_name": "任务日报",
  "description": "记录用户每日任务填报情况",
  "confidence": 0.82,
  "match_signals": [],
  "schema_version": "schema-v1",
  "manifest_version": "manifest-v1"
}
```

目录中不包含完整字段列表、完整蓝图参数、完整 SQL 模板或样例行。

## 详情请求协议

planner 可以输出 `asset_detail_requests`：

```json
{
  "asset_detail_requests": [
    {
      "asset_type": "table",
      "asset_id": "plan_task_daily_record",
      "detail_level": "full_schema",
      "purpose": "sql_generation",
      "reason": "需要确认时间字段、用户字段和任务状态字段"
    }
  ]
}
```

硬约束：

- `asset_id` 必须来自本轮轻量目录。
- `asset_type` 必须与目录中资产类型一致。
- `purpose` 首版只支持 `sql_generation`。
- 单轮请求数需要受限，首版建议最多 5 个资产详情请求。
- 请求非法或越界时返回结构化错误，并写入 planner warning。

## 表详情

### 普通表

如果表字段数不超过普通表阈值，返回整表 schema：

```json
{
  "asset_type": "table",
  "asset_id": "plan_task_daily_record",
  "detail_level": "full_schema",
  "coverage": "full",
  "field_count": 86,
  "returned_field_count": 86,
  "table": {
    "name": "plan_task_daily_record",
    "display_name": "任务日报",
    "comment": "记录每日任务填报",
    "selected_by_dataset": true
  },
  "fields": [
    {
      "name": "created_at",
      "data_type": "datetime",
      "comment": "创建时间",
      "business_desc": "记录生成时间",
      "is_time_candidate": true,
      "is_filter_candidate": true,
      "is_join_candidate": false
    }
  ],
  "risk_flags": [],
  "suggested_next_requests": []
}
```

建议阈值：

- `field_count <= 120`：返回完整字段，`coverage=full`。
- `120 < field_count <= 300`：返回完整字段但压缩字段说明，`coverage=full_compacted`。
- `field_count > 300`：不返回全字段，`coverage=too_large`。

### 超宽表

超宽表不强行返回完整字段：

```json
{
  "asset_type": "table",
  "asset_id": "wide_table",
  "detail_level": "full_schema",
  "coverage": "too_large",
  "field_count": 812,
  "returned_field_count": 0,
  "risk_flags": ["wide_table"],
  "available_detail_requests": ["field_search"],
  "suggested_next_requests": [
    {
      "detail_level": "field_search",
      "query": "时间 用户 部门 状态 金额",
      "top_k": 30
    }
  ]
}
```

## 自然语言字段搜索

超宽表或 planner 需要补齐字段时，使用自然语言字段搜索：

```json
{
  "asset_type": "table",
  "asset_id": "wide_table",
  "detail_level": "field_search",
  "query": "用户 部门 时间 状态 金额",
  "top_k": 30,
  "purpose": "sql_generation"
}
```

规则：

- 默认 `top_k=30`。
- planner 可以请求更小值。
- 最大不超过 `50`，超过时后端强制截断。
- 搜索范围只限该表资产，不允许跨表、跨数据集或跨未召回资产搜索。
- 返回 `returned_count`、`requested_top_k`、`capped_top_k` 和 `total_matched_estimate`。

字段结果示例：

```json
{
  "coverage": "partial",
  "requested_top_k": 30,
  "capped_top_k": 30,
  "returned_count": 30,
  "total_matched_estimate": 96,
  "fields": [
    {
      "name": "created_at",
      "data_type": "datetime",
      "comment": "创建时间",
      "text_score": 0.18,
      "final_score": 0.72,
      "boosted": true,
      "boost_reason": "time_field_candidate"
    }
  ]
}
```

允许 boost 的字段类型：

- 主键或唯一键候选。
- 时间字段候选。
- join 字段候选。
- 常用过滤字段。
- 与已选 metric、dimension 或 blueprint 依赖相关的字段。

所有 boost 必须可解释，不允许只改排序不暴露原因。

## Planner 循环

每次 planner 调用有两种合法输出：

1. 最终 `QueryPlan`。
2. `asset_detail_requests`。

循环规则：

- 最多 3 轮详情请求。
- 每轮详情请求由后端执行，planner 不直接访问数据库。
- 每轮输入包含：
  - 用户问题。
  - routing。
  - 多轮上下文摘要。
  - 轻量资产目录。
  - 已获取的 `asset_details`。
  - `previous_detail_requests`。
  - 上一轮错误或 warning。
- 第 3 轮结束后必须输出最终 `QueryPlan`。
- 如果仍缺少 SQL 生成条件，必须 `clarify` 或 `reject`，不允许进入 `query_graph`、`blueprint_execute` 或 SQL 生成。

## QueryPlan 扩展

建议扩展 QueryPlan 审计字段：

- `detail_rounds`
- `attempted_detail_requests`
- `asset_detail_coverage`
- `missing_context`
- `why_not_generate_sql`
- `risk_flags`

这些字段只用于审计、trace 和失败解释，不应把完整字段 schema 写入 QueryPlan。

## SQL 生成上下文

最终计划可执行时，由后端组装 `sql_generation_context`：

```json
{
  "selected_assets": [],
  "reference_assets": [],
  "table_schemas": [],
  "field_search_results": [],
  "metric_definitions": [],
  "dimension_definitions": [],
  "blueprint_references": [],
  "coverage": {},
  "risk_flags": [],
  "schema_version": "schema-v1",
  "manifest_version": "manifest-v1"
}
```

原则：

- 下游节点只读 `sql_generation_context`。
- 不从原始 candidate assets metadata 中隐式读取 SQL 上下文。
- `last_success_task` 只记录轻量摘要或引用，不记录完整详情。
- SSE final payload 不输出完整字段 schema。

## 失败处理

- `asset_not_in_recall_scope`：请求目录外资产，拒绝并记录 warning。
- `invalid_detail_level`：请求非法详情级别，拒绝。
- `request_limit_exceeded`：单轮请求过多，拒绝本轮请求并要求 planner 重试。
- `coverage=too_large`：表太宽，不返回完整字段，引导 `field_search`。
- `coverage=empty`：字段搜索无结果，返回 `suggested_next_queries`。
- `detail_service_error`：详情服务异常，进入 fallback；不可硬生成 SQL。
- `max_detail_rounds_exceeded`：达到 3 轮后仍不足，必须 `clarify` 或 `reject`。

`clarify` 用于缺少用户输入，例如时间范围、业务口径或主体对象不明确。

`reject` 用于系统侧上下文不足，例如表结构缺失、字段无法定位、join 关系不足或权限不允许。

## 观测

- 新增或复用 SSE step：`subagent.asset_detail`。
- SSE 只展示轮次、请求数量、coverage、risk flags、错误码和摘要。
- Langfuse trace 可记录 planner 输入输出和详情摘要，但需受 size guard。
- final payload 只返回摘要，不返回整表字段详情。
- planner warnings 记录越界请求、超宽表、字段搜索为空和 3 轮后仍不足的原因。

## 灰度开关

新增开关：

```text
SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED=false
```

默认关闭。关闭时保留当前 `plan_query()` 行为。开启后才走轻量目录和详情循环。

## 测试计划

- 轻量目录不包含完整字段 schema。
- planner 请求目录内表详情成功。
- planner 请求目录外资产返回 `asset_not_in_recall_scope`。
- 普通表返回 `coverage=full`。
- 中等表返回 `coverage=full_compacted`。
- 超宽表返回 `coverage=too_large`，且不返回字段列表。
- 字段搜索默认 `top_k=30`。
- 字段搜索请求超过 50 时强制截断到 50。
- boost 字段包含 `boosted`、`boost_reason`、`text_score`、`final_score`。
- planner 最多 3 轮详情请求。
- 3 轮后上下文不足时只能输出 `clarify` 或 `reject`。
- `query_graph` 只有在详情 coverage 足够时才允许执行。
- SSE、trace 和 final payload 不泄露大字段详情。
- `last_success_task` 不写入完整 asset details。

## 风险与后续

- planner 协议变复杂，需要严格 JSON 校验和强 fallback。
- 超宽表字段搜索质量会影响 SQL 准确率，需要后续用真实问数样例评估。
- 字段 boost 的规则需要可解释，避免误导 planner。
- 首版不做 field pagination；如果自然语言搜索覆盖不足，再补字段分页或字段分组。
- LeadAgent 侧仍保持当前渐进式资产注入，后续可复用同一套详情服务，但不在本设计范围内。
