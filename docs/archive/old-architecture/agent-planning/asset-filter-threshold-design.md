# LeadAgent 候选资产过滤阈值配置设计

> 目标：为 `recall → filter → projection` 流水线中的过滤阶段定义一套可配置、可评估、可运维的阈值策略，确保进入 LeadAgent Planner 的候选资产既不过多（挤占 token、引入噪声），也不过少（丢失关键语义资产）。
>
> 本文档只描述设计，不写实现。实际代码需等待 M1 投影层合入。
>
> 关联文档：
> - `docs/agent-planning/progressive-asset-integration-draft.md` — 整体接入设计
> - `docs/superpowers/plans/2026-06-16-lead-agent-planner-projection-m1.md` — M1 投影层计划

---

## 1. 设计原则

### 1.1 分层过滤思想

过滤不是一次性的，而是三层递进：

```
召回层（asset_recall.py）          →  原始候选资产（可能 50+ 条）
    │
    ▼
置信度硬截断（全局最小阈值）        →  剔除明显不相关的低分资产
    │
    ▼
类型级 Top-K 截断                  →  按资产类型保留最有价值的 N 条
    │
    ▼
全局 Token 预算截断                →  最终保险，确保投影后不超过预算
```

### 1.2 阈值哲学

- **蓝图（blueprint）门槛最高**：蓝图直接决定执行策略（`blueprint_execute` vs `query_graph`），置信度不足会误导 Planner 做错误策略选择。
- **指标/维度（metric/dimension）次之**：它们影响工具参数填充，但即使漏掉也可以在 SubAgent 阶段二次召回。
- **字段/表（field/table）门槛最低但数量限制最严**：字段数量可能很大，必须严格限制 Top-K，否则 token 爆炸。
- **术语（term）居中**：业务术语对意图理解有帮助，但通常不如蓝图关键。

### 1.3 可配置优先于硬编码

所有阈值和限制都应有默认值，同时支持通过环境变量或配置表覆盖，便于线上调参和 A/B 测试。

---

## 2. 默认阈值配置（按资产类型）

### 2.1 置信度阈值（`min_confidence`）

| 资产类型 | 默认阈值 | 理由 |
|---------|---------|------|
| `blueprint` | **0.60** | 蓝图决定执行策略分支，低置信度蓝图会导致 Planner 误判；宁可漏掉也不要错配 |
| `metric` | **0.35** | 指标影响聚合方式，但 SubAgent 可二次补充 |
| `dimension` | **0.35** | 同 metric |
| `term` | **0.30** | 术语匹配相对宽泛，用于意图理解而非精确执行 |
| `field` | **0.25** | 字段数量多、信号分散，阈值过低会引入噪声；但过高会漏掉隐式关联字段 |
| `table` | **0.25** | 同 field，表名匹配通常较粗 |

> **为什么是 0.60 而不是 0.80？**
> 
> 当前 `asset_recall.py` 的评分模型（`candidate_asset_score_v2`）基于规则匹配（exact/contains/alias/synonym 等），不是模型打分。实测中，一个强相关的蓝图通常得分在 0.70~1.00 区间；0.60 能过滤掉明显弱匹配（如只有一个 synonym 命中），同时保留大部分有效蓝图。如果后续升级为模型打分，阈值应重新校准。

### 2.2 Top-K 限制（`max_per_type`）

| 资产类型 | 默认 Top-K | 理由 |
|---------|-----------|------|
| `blueprint` | **3** | 蓝图数量通常很少（1~5 个），限制 3 条足够；超过 3 个蓝图说明问题意图模糊 |
| `metric` | **5** | 一次查询涉及的指标通常不超过 3 个，留 5 个给复合查询 |
| `dimension` | **5** | 同 metric，维度用于分组/筛选 |
| `term` | **5** | 术语用于意图消歧，过多会分散注意力 |
| `field` | **10** | 字段是 token 消耗大户，必须严格限制；但某些分析需要多字段关联 |
| `table` | **8** | 表数量通常不多，但跨表查询可能需要 2~3 个表 |

### 2.3 全局 Token 预算

| 阶段 | 预算 | 说明 |
|-----|------|------|
| `skill_selection` | **600 tokens** | 只需要类型摘要和 top 资产名称，粗粒度 |
| `tool_planning` | **800 tokens** | 需要更多资产详情（match_signals、metadata），细粒度 |
| 合计 | **1400 tokens** | 约占 SubAgent 召回层预算（2500）的 56%，为 LeadAgent 其他上下文留空间 |

> **为什么是 1400 而不是 2500？**
> 
> LeadAgent Planner 的输入除了候选资产，还包括 `question`、`conversation_summary`、`tool_policy`、`skills`、`tool_schemas` 等。如果候选资产占用 2500 tokens，总输入可能超过 4000 tokens，导致 LLM 成本上升和注意力稀释。1400 是一个保守起点，可根据在线评估上调。

---

## 3. 配置模型设计（Settings.py 扩展）

### 3.1 新增 BaseSettings 字段

```python
class Settings(BaseSettings):
    # ... 现有字段 ...

    # ============================================================
    # LeadAgent 渐进式资产注入（Progressive Asset Integration）
    # ============================================================

    # 总开关：是否启用候选资产召回并注入 LeadAgent Planner
    LEAD_AGENT_USE_PROGRESSIVE_ASSETS: bool = False

    # --- 按资产类型的 Top-K 限制 ---
    LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_BLUEPRINT: int = 3
    LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_METRIC: int = 5
    LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_DIMENSION: int = 5
    LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_TERM: int = 5
    LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_FIELD: int = 10
    LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_TABLE: int = 8

    # --- 按资产类型的置信度阈值 ---
    LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_BLUEPRINT: float = 0.60
    LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_METRIC: float = 0.35
    LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_DIMENSION: float = 0.35
    LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_TERM: float = 0.30
    LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_FIELD: float = 0.25
    LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_TABLE: float = 0.25

    # --- 全局 Token 预算（按阶段） ---
    LEAD_AGENT_PROGRESSIVE_ASSET_TOKEN_BUDGET_SKILL_SELECTION: int = 600
    LEAD_AGENT_PROGRESSIVE_ASSET_TOKEN_BUDGET_TOOL_PLANNING: int = 800

    # --- 全局最小置信度（兜底，任何类型资产都必须超过此值） ---
    LEAD_AGENT_PROGRESSIVE_ASSET_GLOBAL_MIN_CONFIDENCE: float = 0.20

    # --- 元信息脱敏白名单（逗号分隔的字段名） ---
    # 控制哪些 metadata 字段可以进入投影输出；空字符串表示全部脱敏（只保留 name/display_name）
    LEAD_AGENT_PROGRESSIVE_ASSET_METADATA_WHITELIST: str = "table_name,column_name,parameters,expr"

    # --- match_signals 保留数量 ---
    LEAD_AGENT_PROGRESSIVE_ASSET_MAX_SIGNALS_PER_ASSET: int = 3
```

### 3.2 配置字段命名约定

- 前缀统一为 `LEAD_AGENT_PROGRESSIVE_ASSET_`，便于运维人员通过环境变量批量识别和修改。
- 子类别顺序：`TOPK_` → `MIN_CONFIDENCE_` → `TOKEN_BUDGET_` → `GLOBAL_` → `METADATA_` → `MAX_SIGNALS_`，按使用频率和重要性排序。
- 所有数值字段都有默认值，确保未配置时系统可用。

### 3.3 环境变量示例

```bash
# 生产环境逐步切流
LEAD_AGENT_USE_PROGRESSIVE_ASSETS=true

# 保守策略（高门槛、少数量）
LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_BLUEPRINT=0.75
LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_BLUEPRINT=2
LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_FIELD=5

# 激进策略（探索更多资产）
LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_BLUEPRINT=0.45
LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_FIELD=20
```

---

## 4. 过滤函数设计

### 4.1 函数签名

```python
from typing import Any

from pydantic import BaseModel, Field


class AssetFilterConfig(BaseModel):
    """资产过滤配置，从 Settings 派生或按数据集覆盖。"""

    # Top-K 限制
    topk_blueprint: int = 3
    topk_metric: int = 5
    topk_dimension: int = 5
    topk_term: int = 5
    topk_field: int = 10
    topk_table: int = 8

    # 置信度阈值
    min_confidence_blueprint: float = 0.60
    min_confidence_metric: float = 0.35
    min_confidence_dimension: float = 0.35
    min_confidence_term: float = 0.30
    min_confidence_field: float = 0.25
    min_confidence_table: float = 0.25

    # 全局兜底
    global_min_confidence: float = 0.20

    # 元信息白名单
    metadata_whitelist: set[str] = Field(default_factory=lambda: {"table_name", "column_name", "parameters", "expr"})

    # 信号保留数量
    max_signals_per_asset: int = 3

    def get_topk(self, asset_type: str) -> int:
        return getattr(self, f"topk_{asset_type}", 10)

    def get_min_confidence(self, asset_type: str) -> float:
        return getattr(self, f"min_confidence_{asset_type}", 0.25)


def filter_lead_planner_assets(
    candidate_assets: dict[str, Any],
    *,
    config: AssetFilterConfig | None = None,
) -> list[dict[str, Any]]:
    """过滤候选资产，按置信度阈值和 Top-K 限制截断。

    Args:
        candidate_assets: recall_candidate_assets 的原始输出（含 assets 列表）。
        config: 过滤配置；None 时使用默认配置。

    Returns:
        过滤后的资产列表，按 confidence 降序排列。
    """
```

### 4.2 过滤流程

```
输入: raw_assets (来自 recall_candidate_assets)

Step 1: 去重
  - 按 (asset_type, asset_id) 去重，保留 confidence 最高的一条

Step 2: 类型白名单
  - 只保留 CANDIDATE_ASSET_TYPES = {"blueprint", "metric", "dimension", "term", "field", "table"}

Step 3: 全局置信度硬截断
  - 剔除 confidence < config.global_min_confidence 的资产

Step 4: 按类型分组 + 类型级阈值截断
  - 对每组资产：
    a. 剔除 confidence < config.get_min_confidence(asset_type)
    b. 按 confidence 降序取前 config.get_topk(asset_type) 条

Step 5: 元信息脱敏
  - metadata 只保留白名单字段
  - match_signals 只保留前 config.max_signals_per_asset 条

Step 6: 合并输出
  - 所有类型资产合并，按 confidence 全局降序排列
```

### 4.3 关键设计决策

- **去重先于阈值截断**：避免同一资产的低分副本被阈值过滤掉，而高分副本被 Top-K 截断的异常情况。
- **类型阈值先于 Top-K**：先过滤低置信度，再取 Top-K，确保保留的都是"该类型内相对可信"的。
- **全局阈值兜底**：即使某类型的 min_confidence 配置错误（如设为 0.0），global_min_confidence 仍能阻止无意义资产进入。
- **脱敏最后执行**：脱敏不改变资产数量，只影响单条资产的体积，放在最后不影响前面的数量决策。

---

## 5. 按数据集覆盖策略

### 5.1 需求场景

不同数据集对资产过滤的需求不同：

- **电商数据集**：字段极多（100+ 字段），需要更严格的 field Top-K（如 5）。
- **财务数据集**：指标精度要求高，metric 阈值可能需要提高到 0.50。
- **小型数据集**：资产总数不足 10 个，阈值和 Top-K 应该放宽或禁用。

### 5.2 覆盖层级（优先级从高到低）

```
1. 运行时显式参数（函数调用时传入）
      ↓
2. 数据集级配置（dataset_settings 表 / 数据集元数据）
      ↓
3. 租户/组织级配置（organization_settings 表）
      ↓
4. 环境变量（Settings.py）
      ↓
5. 代码默认值
```

### 5.3 数据集级配置存储方案

**推荐方案：数据集元数据 JSON 字段（轻量）**

在 `semantic_dataset` 表（或相关配置表）中增加一个 JSON 字段 `planner_config`：

```json
{
  "asset_filter": {
    "topk_field": 5,
    "min_confidence_blueprint": 0.75,
    "token_budget_skill_selection": 400
  }
}
```

**优点**：
- 无需新增表，改动最小。
- 与数据集生命周期绑定，迁移/复制数据集时配置一起带走。
- 适合配置量小的场景（每个数据集只有少量覆盖项）。

**备选方案：独立配置表（重度）**

如果未来需要更复杂的规则（如按用户角色、按问题类型动态调整），可新增 `dataset_planner_config` 表：

```sql
CREATE TABLE dataset_planner_config (
    id SERIAL PRIMARY KEY,
    dataset_id INT NOT NULL REFERENCES semantic_dataset(id),
    config_key VARCHAR(64) NOT NULL,      -- 如 "topk_field"
    config_value VARCHAR(256) NOT NULL,   -- 如 "5"
    effective_from TIMESTAMP DEFAULT NOW(),
    effective_until TIMESTAMP,
    created_by VARCHAR(64),
    UNIQUE(dataset_id, config_key)
);
```

**当前建议**：先采用 JSON 字段方案，等覆盖需求复杂化后再考虑独立表。

### 5.4 配置合并逻辑

```python
def build_filter_config(
    *,
    settings: Settings,
    dataset_id: int | None = None,
    db: Session | None = None,
    explicit_overrides: dict[str, Any] | None = None,
) -> AssetFilterConfig:
    """按优先级合并配置。"""
    # 1. 从 Settings 构建基础配置
    config = AssetFilterConfig(
        topk_blueprint=settings.LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_BLUEPRINT,
        # ... 其他字段 ...
    )

    # 2. 如果提供了数据集 ID，从数据库读取数据集级覆盖
    if dataset_id and db:
        dataset_overrides = _load_dataset_filter_overrides(db, dataset_id)
        for key, value in dataset_overrides.items():
            if hasattr(config, key) and value is not None:
                setattr(config, key, value)

    # 3. 应用运行时显式覆盖（最高优先级）
    if explicit_overrides:
        for key, value in explicit_overrides.items():
            if hasattr(config, key) and value is not None:
                setattr(config, key, value)

    return config
```

---

## 6. Fallback 策略

### 6.1 问题定义

过滤后资产为空（或关键类型缺失）时，Planner 应该如何处理？

### 6.2 场景分类

| 场景 | 定义 | 策略 |
|-----|------|------|
| **A. 全部过滤为空** | 所有资产都被阈值过滤掉 | 降级为无资产模式（当前行为） |
| **B. 蓝图缺失** | 有其他资产但无蓝图 | 正常注入，Planner 按无蓝图路径处理（query_graph / clarify） |
| **C. 字段/表缺失** | 有蓝图和指标但无字段 | 正常注入，SubAgent 阶段二次召回补充 |
| **D. 关键技能资产缺失** | 如 ConversationContinuitySkill 所需的蓝图被过滤 | 需要特殊处理（见 6.3） |

### 6.3 推荐 Fallback 策略：分层降级

```
过滤结果评估
    │
    ├── 全部为空？
    │       ├── YES → 尝试一次"宽松重试"
    │       │              ├── 全局阈值降至 0.10，Top-K 翻倍
    │       │              ├── 若仍为空 → 彻底降级为无资产模式
    │       │              └── 记录 "fallback_loose_retry_empty" 到 trace
    │       └── NO → 继续
    │
    └── 关键类型缺失？（如蓝图缺失但问题明显需要蓝图）
            ├── YES → 不自动补救，让 Planner 自行判断
            │          （Planner 的 clarify 路径可以引导用户细化问题）
            └── NO → 正常注入
```

### 6.4 为什么不用"硬编码 must-have 列表"？

- **反模式**：硬编码列表（如强制保留 ConversationContinuitySkill）会引入隐式依赖，导致配置和代码脱节。
- **替代方案**：如果某些资产确实"必须保留"，应该在召回阶段就给它们更高的 confidence（如加分），而不是在过滤阶段开后门。
- **当前决策**：不实现 must-have 列表；如果后续评估证明需要，再作为配置项加入 `AssetFilterConfig`。

### 6.5 Fallback 观测指标

```python
# 在 tracer metadata 中记录
{
    "asset_filter_fallback_triggered": True,
    "asset_filter_fallback_reason": "all_empty_after_loose_retry",  # 或 "blueprint_missing"
    "asset_filter_loose_retry_count": 5,  # 宽松重试后保留的资产数
}
```

---

## 7. 评估与调优计划

### 7.1 评估维度

| 维度 | 指标 | 目标 |
|-----|------|------|
| **召回率** | 过滤后是否保留了"应该保留"的关键资产 | ≥ 95%（关键资产不丢失） |
| **精确率** | 过滤后是否剔除了"应该剔除"的噪声资产 | ≥ 80%（无显著噪声干扰 Planner） |
| **Token 效率** | 投影后资产占用的 token 数 | ≤ 1400（预算内） |
| **Planner 效果** | 注入资产后 Planner 的 Skill 选择准确率 | 对比无资产基线，提升 ≥ 10% |
| **端到端延迟** | 召回 + 过滤 + 投影的总耗时 | ≤ 200ms（P99） |

### 7.2 离线评估：Replay 数据集

**构建方法**：
1. 从历史对话日志中抽取 500 条有锁定数据集的问题。
2. 人工标注每条问题"应该触发哪些资产"（蓝图、指标、字段等）。
3. 运行召回 + 过滤流水线，对比输出与人工标注。

**评估脚本输出**：

```
Asset Type    Recall    Precision    Top-K Hit Rate    Avg Confidence
----------    ------    ---------    --------------    ---------------
blueprint     0.94      0.88         0.92 (top3)       0.72
metric        0.91      0.85         0.89 (top5)       0.58
dimension     0.89      0.82         0.87 (top5)       0.55
term          0.85      0.78         0.83 (top5)       0.48
field         0.82      0.75         0.80 (top10)      0.42
table         0.88      0.80         0.85 (top8)       0.45
```

**调参方法**：
- 如果某类型 Recall 过低 → 降低该类型的 min_confidence 或提高 Top-K。
- 如果某类型 Precision 过低 → 提高 min_confidence 或降低 Top-K。
- 如果 Token 超标 → 降低全局预算或收紧 Top-K。

### 7.3 在线评估：Langfuse 指标

**需要追踪的指标**：

```python
# 在 plan_tool_calls_with_llm 的 tracer metadata 中
{
    "asset_filter_config": {
        "min_confidence_blueprint": 0.60,
        "topk_blueprint": 3,
        # ... 当前使用的完整配置快照
    },
    "asset_filter_input_count": 45,        # 召回层原始资产数
    "asset_filter_output_count": 12,       # 过滤后资产数
    "asset_filter_by_type": {
        "blueprint": {"input": 3, "output": 2, "max_confidence": 0.85},
        "metric": {"input": 8, "output": 4, "max_confidence": 0.62},
        # ...
    },
    "asset_filter_fallback_triggered": False,
    "asset_filter_token_estimate": 520,    # 投影后的预估 token 数
}
```

**分析维度**：
- 按数据集维度聚合：哪些数据集的过滤效果差？
- 按问题类型维度聚合：分析类问题 vs 查询类问题的过滤差异。
- 按时间维度追踪：调参前后的指标变化。

### 7.4 A/B 测试设计

**实验组划分**：

| 组 | 配置 | 目的 |
|---|------|------|
| 控制组 | `LEAD_AGENT_USE_PROGRESSIVE_ASSETS=false` | 基线 |
| 实验组 A | 保守策略（高阈值、低 Top-K） | 验证"少而精"是否更好 |
| 实验组 B | 激进策略（低阈值、高 Top-K） | 验证"多而全"是否更好 |
| 实验组 C | 动态策略（按数据集大小自适应） | 验证自适应逻辑的价值 |

**评估指标**：
- 主要：Planner 的 Skill 选择准确率（人工抽样评估）。
- 次要：端到端响应时间、LLM token 消耗、用户满意度（是否减少澄清轮数）。

**动态自适应策略（实验组 C）**：

```python
def adaptive_topk(asset_type: str, total_assets_of_type: int) -> int:
    """按数据集实际资产数量自适应调整 Top-K。"""
    base = config.get_topk(asset_type)
    # 小型数据集：资产总数 < 20，放宽限制
    if total_assets_of_type < 20:
        return min(total_assets_of_type, base * 2)
    # 中型数据集：正常限制
    if total_assets_of_type < 100:
        return base
    # 大型数据集：收紧限制
    return max(3, base // 2)
```

---

## 8. 与 M1 投影层的协作边界

### 8.1 职责划分

| 模块 | 职责 | 输入 | 输出 |
|-----|------|------|------|
| `asset_recall.py` | 召回原始候选资产 | dataset_id, question | 原始资产列表（含 confidence） |
| `asset_filter.py`（本文档） | 阈值过滤 + Top-K 截断 | 原始资产 + AssetFilterConfig | 过滤后的资产列表 |
| `lead_agent_planner_projection.py`（M1） | 投影成 Prompt 片段 | 过滤后资产 + stage + token_budget | 轻量上下文字典 |

### 8.2 数据契约

过滤层输出到投影层的资产格式：

```python
{
    "asset_type": "blueprint",
    "asset_id": "bp_123",
    "name": "月度销售分析",
    "display_name": "月度销售分析",
    "source": "analysis_blueprint",
    "confidence": 0.85,
    "match_signals": [
        {"type": "exact", "value": "月度销售", "score": 0.55, "match": "phrase_in_question", "fragments": ["月度销售"]},
        # 最多 3 条
    ],
    "metadata": {
        "table_name": "sales",      # 白名单保留
        "parameters": [...],          # 白名单保留
        # 其他字段已脱敏
    },
    "usage": "candidate",
    "match_reason": "exact+contains"
}
```

### 8.3 被 M1 阻塞的代码清单

以下代码必须等 `lead_agent_planner_projection.py` 合入后才能实现：

1. `filter_lead_planner_assets` 的导入和调用（当前可先写空壳函数）。
2. `AssetFilterConfig` 的 Pydantic 模型定义（可独立实现）。
3. `build_filter_config` 的配置合并逻辑（可独立实现）。
4. `plan_tool_calls_with_llm` 中注入 `candidate_assets` 的改动（需等投影层接口确定）。

---

## 9. 实施路线图

### Phase 1：配置层（可立即开始）

- [ ] 在 `config.py` 的 `Settings` 中新增所有 `LEAD_AGENT_PROGRESSIVE_ASSET_*` 字段。
- [ ] 编写 `AssetFilterConfig` Pydantic 模型（`app/services/lead_agent_planning/asset_filter_config.py`）。
- [ ] 实现 `build_filter_config` 配置合并函数（支持 Settings → 数据集级覆盖 → 显式覆盖）。
- [ ] 编写单元测试：验证配置默认值、环境变量覆盖、配置合并优先级。

### Phase 2：过滤层（M1 合入后）

- [ ] 实现 `filter_lead_planner_assets` 函数（`app/services/lead_agent_planning/asset_filter.py`）。
- [ ] 实现元信息脱敏逻辑（metadata 白名单、signals 截断）。
- [ ] 实现 Fallback 策略（宽松重试 + 降级观测）。
- [ ] 编写单元测试：覆盖去重、阈值截断、Top-K 截断、脱敏、Fallback 场景。

### Phase 3：集成层（M1 合入后）

- [ ] 在 `plan_tool_calls_with_llm` 中调用 `_maybe_recall_assets_for_lead_planner`。
- [ ] 调用 `filter_lead_planner_assets` 和 `project_assets_for_lead_planner`。
- [ ] 注入 `candidate_assets` 到 `skill_input` 和 `planner_input`。
- [ ] 在 tracer metadata 中增加过滤观测字段。
- [ ] 编写集成测试：验证端到端数据流。

### Phase 4：评估与调优（上线后）

- [ ] 构建离线 Replay 数据集（500 条标注）。
- [ ] 运行离线评估，输出 Recall / Precision / Token 效率报告。
- [ ] 配置 Langfuse 在线追踪字段和仪表盘。
- [ ] 设计并执行 A/B 测试（保守 vs 激进 vs 动态自适应）。
- [ ] 根据评估结果调整默认阈值，更新本文档。

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|-----|------|---------|
| 阈值过高导致关键蓝图丢失 | Planner 误判执行策略 | Fallback 宽松重试；离线评估监控 Recall |
| 阈值过低导致噪声资产过多 | Planner 注意力稀释、token 浪费 | 全局 Token 预算截断；在线监控 token 效率 |
| 数据集级配置滥用 | 配置碎片化、难以维护 | 限制覆盖字段数量；提供配置模板；审计日志 |
| 环境变量配置错误 | 服务启动失败或行为异常 | Pydantic 类型校验；默认值兜底；配置加载日志 |
| 与 M1 投影层接口不匹配 | 集成失败 | 本文档已定义数据契约；M1 合入前做接口对齐评审 |
| 性能退化（过滤耗时） | 端到端延迟增加 | 过滤是纯内存操作，目标 < 10ms；P99 监控 |

---

## 11. 待确认问题

1. **数据集级配置存储**：是否同意在 `semantic_dataset` 表中增加 JSON 字段 `planner_config`？还是需要独立表？
2. **动态自适应策略**：是否需要在首次上线时就实现自适应 Top-K，还是先固定阈值观察一段时间？
3. **must-have 列表**：是否有明确的"某些资产绝对不能被过滤"的业务场景？当前设计不保留 must-have 机制。
4. **Blueprint 阈值**：0.60 的初始值是否偏保守？是否需要根据历史数据重新校准？
5. **Prompt 兼容性**：当 `LEAD_AGENT_USE_PROGRESSIVE_ASSETS=false` 时，Prompt 模板是否需要同时兼容有/无 `candidate_assets` 字段？
