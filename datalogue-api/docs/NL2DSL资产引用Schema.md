# NL2DSL 资产引用 Schema

> 状态：T-015 实施中
> 日期：2026-06-09
> 范围：NL2DSL 生成、校验、编译、前端类型和旧 DSL 兼容

## 目标

NL2DSL v2 的目标是让 DSL 不只表达“要查哪个字符串名称”，还要显式表达该名称引用了哪类语义资产、资产 ID、置信度以及歧义候选。这样后续可以审计 AI 到底命中了业务术语、指标、维度、字段还是分析蓝图，也能在前端展示“AI 理解卡片”和澄清入口。

## 资产引用对象

```json
{
  "name": "gmv",
  "asset_type": "metric",
  "asset_id": 12,
  "display_name": "GMV",
  "matched_text": "销售额",
  "confidence": 0.92,
  "reason": "命中指标同义词"
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `name` | 是 | 编译时使用的稳定名称，通常是语义层 `name` |
| `asset_type` | 是 | `term`、`metric`、`dimension`、`column`、`field`、`blueprint` |
| `asset_id` | 否 | 对应数据库资产 ID；旧 DSL 或未命中时可以为 `null` |
| `display_name` | 否 | 用户可读名称 |
| `matched_text` | 否 | 用户原始问题中命中的文本 |
| `confidence` | 否 | 0 到 1 的匹配置信度 |
| `reason` | 否 | 匹配原因，供审计和前端展示 |

## DSL 根结构

```json
{
  "version": "2.0",
  "metrics": [
    {
      "name": "gmv",
      "asset_type": "metric",
      "asset_id": 12,
      "confidence": 0.92
    }
  ],
  "dimensions": [
    {
      "name": "region",
      "asset_type": "dimension",
      "asset_id": 31,
      "confidence": 0.88
    }
  ],
  "terms": [
    {
      "name": "paid_order",
      "asset_type": "term",
      "asset_id": 7,
      "confidence": 0.8
    }
  ],
  "blueprints": [],
  "filters": [
    {
      "field": {
        "name": "region",
        "asset_type": "dimension",
        "asset_id": 31,
        "confidence": 0.88
      },
      "op": "in",
      "values": ["华东", "华南"],
      "confidence": 0.86
    }
  ],
  "time_range": {
    "field": "created_at",
    "start": "2026-05-10",
    "end": "2026-06-09"
  },
  "order_by": [
    {
      "field": {
        "name": "gmv",
        "asset_type": "metric",
        "asset_id": 12
      },
      "direction": "DESC"
    }
  ],
  "limit": 100,
  "confidence": 0.9,
  "ambiguities": []
}
```

## 歧义结构

```json
{
  "text": "销售",
  "reason": "同时命中销售额指标和销售部门维度",
  "candidates": [
    {
      "name": "gmv",
      "asset_type": "metric",
      "asset_id": 12,
      "confidence": 0.61
    },
    {
      "name": "sales_dept",
      "asset_type": "dimension",
      "asset_id": 44,
      "confidence": 0.58
    }
  ],
  "resolution_hint": "请确认销售是指销售额还是销售部门"
}
```

## 兼容策略

旧 DSL 继续有效：

```json
{
  "metrics": ["gmv"],
  "dimensions": ["region"],
  "filters": [{"field": "region", "op": "in", "values": ["华东"]}]
}
```

进入校验和编译前会被规范化为：

```json
{
  "version": "2.0",
  "metrics": [{"name": "gmv", "asset_type": "metric"}],
  "dimensions": [{"name": "region", "asset_type": "dimension"}],
  "filters": [{"field": "region", "op": "in", "values": ["华东"]}]
}
```

兼容原则：

- `direct_sql` 路径保留，不强制要求资产引用。
- 编译器只使用 `name` 字段生成 SQL，不把 `asset_id` 或置信度写入 SQL。
- `asset_id` 缺失时不阻塞旧链路；但新 DSL 应尽量携带。
- `ambiguities` 不直接改变 SQL 编译结果，先作为审计和前端澄清的结构化信息。
