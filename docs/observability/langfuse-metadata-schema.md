# 渐进式资产注入（Progressive Asset Injection）Langfuse 元数据 Schema 设计

## 1. 背景与目标

### 1.1 背景
- M1 已在 `llm.lead_agent_skill_selector` 和 `llm.lead_agent_tool_planner` 两个 generation 上记录 `projection_enabled`、`raw_chars`、`projected_chars`、`projection_saved_chars` 等投影压缩指标。
- Codex 外部评审指出：仅记录 `skills_count` 和 `projection_saved_chars` 无法观测到**资产召回遗漏**、**降级触发**、**最终执行策略**等关键决策链路。
- 渐进式资产注入（Progressive Asset Injection）是 LeadAgent Planner 的核心机制：按问题意图动态召回语义资产（指标、维度、术语、蓝图等），经阈值/TopK 过滤后注入 LLM prompt，失败时降级到全量或安全计划。

### 1.2 目标
- 在现有 M1 metadata 基础上**追加**渐进式资产注入专项字段，不重复、不破坏已有数据。
- 支持按 generation 追溯：是否启用资产注入、召回策略、召回耗时、召回数量、过滤原因、降级触发、降级原因。
- 支持 Dashboard 聚合查询：资产类型召回命中率、过滤原因分布、降级率趋势、遗漏-降级相关性。

---

## 2. 逐 generation 追加字段

以下字段仅当 `progressive_assets_enabled=true` 时写入；`false` 或 flag-off 时不写，保持 metadata 精简。

### 2.1 字段总表

| 字段名 | 类型 | 写入时机 | 说明 |
|--------|------|----------|------|
| `progressive_assets_enabled` | `bool` | `start_generation` | 是否启用渐进式资产注入（feature flag） |
| `asset_recall_strategy` | `str` | `start_generation` | 召回策略版本，如 `"rule_v1"`、`"rule_plus_llm_v1"` |
| `asset_recall_latency_ms` | `int` | `end_generation` | 资产召回总耗时（毫秒），含 embedding 检索 + 重排序 |
| `assets_recalled_count` | `int` | `end_generation` | 召回阶段原始返回的资产总数 |
| `assets_filtered_count` | `int` | `end_generation` | 经阈值/TopK 过滤后剩余资产数 |
| `assets_injected_count` | `int` | `end_generation` | 最终实际注入 prompt 的资产数（含 always_include 强制注入） |
| `asset_types_recalled` | `dict[str, int]` | `end_generation` | 各资产类型召回数量，如 `{"metric": 5, "dimension": 3, "term": 2, "blueprint": 1}` |
| `asset_filter_reason` | `str` | `end_generation` | 主过滤原因，如 `"below_threshold"`、`"topk_exceeded"`、`"always_include"` |
| `fallback_triggered` | `bool` | `end_generation` | 是否触发降级（recall_empty 或 timeout 时走全量/安全计划） |
| `fallback_reason` | `str \| None` | `end_generation` | 降级原因，如 `"recall_empty"`、`"llm_recall_timeout"`、`"filter_all_excluded"` |

### 2.2 字段详细语义

#### `progressive_assets_enabled`
- 来源：配置中心 `LEAD_AGENT_PLANNER_USE_PROGRESSIVE_ASSETS`（或同类 feature flag）。
- 用途：Dashboard 区分"启用组"与"对照组"，做 A/B 质量对比。

#### `asset_recall_strategy`
- 枚举值：
  - `"rule_v1"`：纯规则召回（关键词匹配 + 向量相似度）。
  - `"rule_plus_llm_v1"`：规则召回后由 LLM 做二次重排序/筛选。
  - `"embedding_knn_v1"`：纯 embedding 近邻召回。
- 用途：评估不同策略的召回命中率与延迟 trade-off。

#### `asset_recall_latency_ms`
- 计时范围：从发起召回请求到拿到最终候选列表。
- 不包含：LLM generation 本身的耗时（已在 Langfuse generation 自动记录）。
- 用途：识别召回瓶颈，优化 embedding 服务或索引。

#### `assets_recalled_count` vs `assets_filtered_count` vs `assets_injected_count`
- 三者关系：`assets_recalled_count >= assets_filtered_count >= assets_injected_count`。
- 典型场景：
  - 召回 20 个 → 阈值过滤剩 8 个 → always_include 强制加 2 个 → 最终注入 10 个。
  - 此时 `assets_recalled_count=20`，`assets_filtered_count=8`，`assets_injected_count=10`。
- 用途：计算过滤率 `(20-8)/20=60%`，评估过滤策略是否过严。

#### `asset_types_recalled`
- 键值：资产类型 → 召回数量。
- 标准类型：`metric`、`dimension`、`term`、`blueprint`、`scenario`、`dataset_context`。
- 用途：Dashboard 按类型分析召回覆盖率，发现某类资产系统性遗漏。

#### `asset_filter_reason`
- 枚举值：
  - `"below_threshold"`：相似度/分数低于阈值被过滤。
  - `"topk_exceeded"`：超出 TopK 限制被截断。
  - `"always_include"`：命中 always_include 规则，未经过滤直接注入。
  - `"duplicate_merged"`：重复资产被合并。
- 用途：分析过滤原因分布，调整阈值或 TopK。

#### `fallback_triggered` & `fallback_reason`
- 降级触发条件：
  - `recall_empty`：召回结果为空，无法注入任何资产。
  - `llm_recall_timeout`：LLM 重排序/筛选超时。
  - `filter_all_excluded`：全部召回资产被过滤，无可用资产。
  - `injection_format_error`：资产序列化注入 prompt 时格式错误。
- 降级行为：走全量资产注入（不召回，直接塞全部）或安全降级计划（如 `build_fallback_plan`）。
- 用途：计算降级率，定位召回链路薄弱环节。

---

## 3. 聚合查询指标（Dashboard 口径）

以下查询基于 Langfuse trace/generation metadata，供产品/算法/研发做趋势分析。

### 3.1 资产类型召回命中率（Recall Hit Rate）

```sql
-- 伪代码：按 asset_type 统计有召回的 generation 占比
SELECT
  asset_type,
  COUNT(*) FILTER (WHERE assets_recalled_count > 0) AS hit_count,
  COUNT(*) AS total_count,
  hit_count / total_count AS hit_rate
FROM generation_metadata
WHERE progressive_assets_enabled = true
  AND name IN ('llm.lead_agent_skill_selector', 'llm.lead_agent_tool_planner')
GROUP BY asset_type
```

- 口径：某类型资产 `assets_recalled_count > 0` 的 generation 占全部启用渐进式资产的 generation 比例。
- 用途：发现某类资产（如 blueprint）长期未被召回，需检查索引或召回策略。

### 3.2 过滤原因分布（Filter-out Rate by Reason）

```sql
SELECT
  asset_filter_reason,
  COUNT(*) AS count,
  COUNT(*) * 1.0 / SUM(COUNT(*)) OVER () AS ratio
FROM generation_metadata
WHERE progressive_assets_enabled = true
GROUP BY asset_filter_reason
```

- 口径：各过滤原因占比。
- 用途：若 `below_threshold` 占比过高，说明阈值设置过严或 embedding 质量差；若 `topk_exceeded` 过高，说明 TopK 限制过紧。

### 3.3 降级率趋势（Fallback Rate Over Time）

```sql
SELECT
  DATE_TRUNC('day', timestamp) AS day,
  COUNT(*) FILTER (WHERE fallback_triggered = true) AS fallback_count,
  COUNT(*) AS total_count,
  fallback_count * 1.0 / total_count AS fallback_rate
FROM generation_metadata
WHERE progressive_assets_enabled = true
GROUP BY day
ORDER BY day
```

- 口径：每日降级 generation 数 / 每日总 generation 数。
- 用途：监控渐进式资产注入稳定性，降级率突增时告警。

### 3.4 遗漏-降级相关性（Miss-then-fallback Correlation）

```sql
SELECT
  CASE
    WHEN assets_recalled_count = 0 THEN 'recall_empty'
    WHEN assets_filtered_count = 0 THEN 'all_filtered'
    ELSE 'partial_filtered'
  END AS miss_stage,
  COUNT(*) FILTER (WHERE fallback_triggered = true) AS fallback_count,
  COUNT(*) AS total_count,
  fallback_count * 1.0 / total_count AS correlation_rate
FROM generation_metadata
WHERE progressive_assets_enabled = true
GROUP BY miss_stage
```

- 口径：分阶段（召回空、全过滤、部分过滤）统计降级率。
- 用途：定位降级根因是"召不回"还是"过滤过严"。

### 3.5 资产注入压缩率（Injection Compression Rate）

```sql
SELECT
  AVG(1.0 - assets_injected_count / NULLIF(assets_recalled_count, 0)) AS compression_rate,
  AVG(asset_recall_latency_ms) AS avg_latency_ms
FROM generation_metadata
WHERE progressive_assets_enabled = true
  AND fallback_triggered = false
```

- 口径：`(recalled - injected) / recalled`，排除降级 case（降级时 injected 可能等于全量）。
- 用途：评估渐进式资产注入的压缩效果与延迟 trade-off。

---

## 4. 向后兼容性

### 4.1 字段追加原则
- 所有渐进式资产字段为**纯追加**（additive），不修改、不删除 M1 已有字段。
- M1 已有字段：`projection_enabled`、`raw_chars`、`projected_chars`、`projection_saved_chars`、`projection_schema_version`、`projection_metrics`。

### 4.2 Flag-off 行为
- 当 `progressive_assets_enabled=false` 或配置未开启时：
  - **不写**任何 `progressive_assets_*` 字段。
  - **不写** `asset_recall_*`、`assets_*`、`fallback_*` 字段。
  - metadata 保持 M1 形态，避免污染。

### 4.3 旧数据兼容
- Langfuse 中已有 trace/generation 不会回溯补写新字段。
- Dashboard 查询时需用 `WHERE progressive_assets_enabled IS NOT NULL` 或 `= true` 区分新旧数据。

---

## 5. 实现位置草图

### 5.1 目标文件
`datalogue-api/app/services/lead_agent.py`

### 5.2 资产召回与注入逻辑（新增函数草图）

```python
# 在 lead_agent.py 中新增或扩展的函数草图

def _recall_assets_for_planner(
    *,
    question: str,
    selected_skills: list[str],
    strategy: str = "rule_v1",
    db: Session,
) -> dict[str, Any]:
    """资产召回：按策略召回语义资产，返回召回结果和耗时。

    Returns:
        {
            "assets": [...],           # 原始召回资产列表
            "latency_ms": 45,          # 召回耗时
            "types_recalled": {"metric": 5, ...},  # 类型分布
            "strategy": "rule_v1",
        }
    """
    ...


def _filter_assets_for_injection(
    *,
    assets: list[dict[str, Any]],
    threshold: float = 0.75,
    top_k: int = 10,
    always_include_types: tuple[str, ...] = ("dataset_context",),
) -> dict[str, Any]:
    """资产过滤：按阈值、TopK、强制包含规则过滤资产。

    Returns:
        {
            "filtered_assets": [...],   # 过滤后资产
            "injected_assets": [...],   # 最终注入资产（含 always_include）
            "filter_reason": "below_threshold",  # 主过滤原因
            "recalled_count": 20,
            "filtered_count": 8,
            "injected_count": 10,
        }
    """
    ...


def _build_asset_injection_metadata(
    recall_result: dict[str, Any],
    filter_result: dict[str, Any],
    fallback_triggered: bool,
    fallback_reason: str | None,
) -> dict[str, Any]:
    """构建渐进式资产注入的 metadata 字典，供 tracer.start_generation/end_generation 使用。"""
    return {
        "progressive_assets_enabled": True,
        "asset_recall_strategy": recall_result["strategy"],
        "asset_recall_latency_ms": recall_result["latency_ms"],
        "assets_recalled_count": filter_result["recalled_count"],
        "assets_filtered_count": filter_result["filtered_count"],
        "assets_injected_count": filter_result["injected_count"],
        "asset_types_recalled": recall_result["types_recalled"],
        "asset_filter_reason": filter_result["filter_reason"],
        "fallback_triggered": fallback_triggered,
        "fallback_reason": fallback_reason,
    }
```

### 5.3 注入到 `plan_tool_calls_with_llm` 的 metadata 写入点

```python
def plan_tool_calls_with_llm(...):
    # ... 现有逻辑 ...

    # 1. 在 skill_selector 和 tool_planner 的 start_generation metadata 中追加
    #    progressive_assets_enabled 和 asset_recall_strategy
    use_progressive_assets = bool(get_settings().LEAD_AGENT_PLANNER_USE_PROGRESSIVE_ASSETS)

    # 2. 在 LLM 调用前执行资产召回与过滤（仅当启用时）
    asset_meta = {}
    if use_progressive_assets:
        recall_result = _recall_assets_for_planner(
            question=question,
            selected_skills=selected_skill_names,  # skill_selector 后才有
            strategy=get_settings().LEAD_AGENT_ASSET_RECALL_STRATEGY or "rule_v1",
            db=db,
        )
        filter_result = _filter_assets_for_injection(
            assets=recall_result["assets"],
            threshold=get_settings().LEAD_AGENT_ASSET_THRESHOLD or 0.75,
            top_k=get_settings().LEAD_AGENT_ASSET_TOPK or 10,
        )
        fallback_triggered = filter_result["injected_count"] == 0
        fallback_reason = "recall_empty" if filter_result["recalled_count"] == 0 else "filter_all_excluded" if fallback_triggered else None
        asset_meta = _build_asset_injection_metadata(
            recall_result, filter_result, fallback_triggered, fallback_reason
        )

    # 3. 将 asset_meta 合并到 start_generation 和 end_generation 的 metadata 中
    #    注意：skill_selector 阶段尚无 selected_skills，asset_meta 可部分为空或只写 enabled/strategy
    #    tool_planner 阶段可写完整 asset_meta

    # 4. 若 fallback_triggered，可决定是否走全量注入或安全降级计划
    #    （与现有 build_fallback_plan 衔接）
```

### 5.4 与现有 M1 projection 字段的共存

```python
# metadata 合并示例（tool_planner 的 start_generation）
metadata={
    # --- M1 已有字段 ---
    "path": "lead_agent_tool_planner",
    "prompt_name": LEAD_AGENT_TOOL_PLANNER_PROMPT_NAME,
    "prompt_version": tool_prompt.version,
    "projection_enabled": use_projection,
    "projection_metrics": planner_projection_metrics,
    **(planner_projection_metrics or {}),  # raw_chars, projected_chars, etc.

    # --- 渐进式资产注入新增字段 ---
    **asset_meta,  # 仅当 use_progressive_assets=true 时有值
}
```

---

## 6. 字段校验与约束

| 校验项 | 规则 |
|--------|------|
| `progressive_assets_enabled` | 必须为 `bool`，不可为字符串 |
| `asset_recall_strategy` | 长度 <= 32，只允许 `[a-z0-9_]+` 格式 |
| `asset_recall_latency_ms` | >= 0，单位毫秒 |
| `assets_recalled_count` | >= 0，且 >= `assets_filtered_count` |
| `assets_filtered_count` | >= 0，且 >= `assets_injected_count` |
| `assets_injected_count` | >= 0 |
| `asset_types_recalled` | 键只允许标准类型，值 >= 0 |
| `asset_filter_reason` | 只允许预定义枚举值 |
| `fallback_triggered` | `bool` |
| `fallback_reason` | 当 `fallback_triggered=true` 时必填，长度 <= 64 |

---

## 7. 验收标准

- [ ] `llm.lead_agent_skill_selector` 和 `llm.lead_agent_tool_planner` 的 generation metadata 在启用渐进式资产时包含全部 10 个新增字段。
- [ ] Flag-off 时 metadata 不出现任何 `progressive_assets_*` 或 `asset_*` 字段。
- [ ] Langfuse Dashboard 可按 `asset_recall_strategy` 分组对比召回命中率。
- [ ] 可按 `fallback_triggered=true` 筛选并查看降级原因分布。
- [ ] 旧 M1 trace 数据不受新字段影响，可正常查询。

---

## 8. 附录：与现有文档的关联

| 文档 | 关联点 |
|------|--------|
| `docs/agent-planning/progressive-asset-integration-draft.md` | 渐进式资产注入流程设计（本文 Schema 基于该流程定义） |
| `docs/observability/Langfuse可观测能力需求设计文档.md` | Langfuse 整体可观测能力规划（本文是其中 generation metadata 的细化） |
| `datalogue-api/app/services/lead_agent.py` | 实际写入 metadata 的代码位置 |
| `datalogue-api/app/services/lead_agent_planner_projection.py` | M1 projection 指标计算（本文追加字段与其共存） |
