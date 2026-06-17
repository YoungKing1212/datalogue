# LeadAgent 渐进式语义资产注入设计草案

> 目标：把 DatasetSubAgent 已有的轻量候选资产召回层（`asset_recall.py`）接入到 LeadAgent 的 `plan_tool_calls_with_llm`，让 LLM Planner 在 Skill 选择和工具规划阶段就能看到“数据集语义资产摘要”，从而把 `subagent_dispatch` 的时机和后续执行策略（ExecutionStrategy）前置预判得更准。
>
> 本文档只描述设计，不写实现。

---

## 1. 现状速览

### 1.1 候选资产召回层（已存在）

`datalogue-api/app/services/subagent_planning/asset_recall.py` 提供：

- `recall_candidate_assets(db, *, dataset_id, question, manifest_version, bound_schema_version)`
- 输出结构 `{dataset_id, question, assets, summary, recall_debug, context}`
- 支持 **6 类资产**：`blueprint / metric / dimension / term / field / table`
- 基于 `build_dataset_query_context` 做轻量 Schema 召回，单数据集 token 预算约 `2500`

### 1.2 SubAgent Planner（已存在）

`datalogue-api/app/services/subagent_planning/planner.py` 已消费候选资产，并定义 **5 种执行策略**：

- `blueprint_execute`
- `blueprint_as_reference`
- `query_graph`
- `clarify`
- `reject`

### 1.3 LeadAgent Planner（当前不消费资产）

`datalogue-api/app/services/lead_agent.py::plan_tool_calls_with_llm` 当前 LLM 输入只包含：

- `question`
- `conversation_summary`
- `tool_policy`
- `skills / selected_skills`
- `tool_schemas`

它不知道数据集内部有哪些蓝图、指标、字段。因此 `subagent_dispatch` 只能按“数据集已锁定”这个粗粒度触发，无法提前判断更适合 `blueprint_execute` 还是 `query_graph`。

### 1.4 M1 投影层（尚未合入）

设计里提到的 `lead_agent_planner_projection.py` 在 `codex-lead-agent-planner-projection-m1` 分支尚未出现，因此本草案只约定接口契约；具体投影实现必须等 M1 合入后才能落地。

---

## 2. 接入位置

### 2.1 拦截点：Skill 选择之前

在 `plan_tool_calls_with_llm` 中，最合适的位置是**确定性快路径返回之后、构建 `skill_input` 之前**：

```python
# 1. 确定性快路径仍然不触发资产召回，保持零开销
# 2. 进入 LLM 规划链路后，先判断是否有锁定数据集
# 3. 如果有，调用候选资产召回并投影成 LeadAgent 可用的轻量上下文
# 4. 把投影结果分别注入 skill_input 和 planner_input
```

为什么选择这里：

- `tool_policy["locked_dataset_id"]` 此时已经确定，满足召回的最小条件。
- Skill Selector 需要知道“有没有语义资产”来决定是否启用 `SubAgentDelegationSkill` 或 `SchemaFreshnessSkill` 的侧重点。
- Tool Planner 需要知道“有哪些蓝图/指标/字段”来决定是否直接 `subagent_dispatch` 或先生成澄清。
- 失败时不影响主链路，直接降级为空资产列表。

### 2.2 数据流

```
User Question
    │
    ▼
build_lead_agent_context
    │
    ▼
plan_tool_calls_with_llm
    │
    ├── 确定性快路径？ ──→ 返回，不召回
    │
    └── LLM 规划链路
            │
            ▼
    ┌───────────────────┐
    │  recall_candidate_assets(dataset_id=locked_dataset_id) │  ← 复用 SubAgent 召回层
    └───────────────────┘
            │
            ▼
    ┌───────────────────┐
    │  filter_lead_planner_assets()                          │  ← 按置信度/类型/数量截断
    └───────────────────┘
            │
            ▼
    ┌───────────────────┐
    │  project_assets_for_lead_planner(stage=skill_selection│  ← M1 投影层
    │                                 |tool_planning)        │
    └───────────────────┘
            │
            ▼
    skill_input / planner_input 增加 candidate_assets 字段
            │
            ▼
    LLM 输出工具计划
```

---

## 3. 从 LeadAgent 上下文调用召回

LeadAgent 当前只有 `tool_policy`，没有 `manifest_version` / `bound_schema_version`。因此首次召回可以只传 `dataset_id` 和 `question`，版本字段传 `None`：

```python
# 仅当锁定数据集时才召回，避免在数据集未定时浪费 token
def _maybe_recall_assets_for_lead_planner(
    db: Session,
    *,
    question: str,
    tool_policy: dict[str, Any],
) -> dict[str, Any]:
    locked_dataset_id = tool_policy.get("locked_dataset_id")
    if not locked_dataset_id:
        return {"assets": []}

    try:
        return recall_candidate_assets(
            db,
            dataset_id=locked_dataset_id,
            question=question,
            manifest_version=None,
            bound_schema_version=None,
        )
    except Exception:
        # 召回失败不得阻塞控制面规划
        logger.exception("LeadAgent 候选资产召回失败，降级为空资产")
        return {"assets": []}
```

> **说明**：`manifest_version` / `bound_schema_version` 在 SubAgent 实际调度前由 `route_decision` 给出。如果后续需要更精确的召回，可以在 `execute_tool_plan` 的 `manifest_router` 执行后再补一次召回；但本草案只聚焦“前置注入”这一层。

---

## 4. 过滤规则

召回层返回的原始资产包含完整 `metadata` 和 `match_signals`，不能直接塞进 LeadAgent Prompt。过滤阶段需要：

1. **去重**：按 `(asset_type, asset_id)` 去重。
2. **类型白名单**：只保留 `blueprint / metric / dimension / term / field / table`（与 `CANDIDATE_ASSET_TYPES` 一致）。
3. **置信度截断**：
   - 蓝图类保留 `confidence > 0.05`（沿用 `BLUEPRINT_MIN_CONFIDENCE`）。
   - 其他类型保留 `confidence > 0.1` 或保留 top-K。
4. **数量截断（按类型）**：建议初始值
   - `blueprint`: top 3
   - `metric / dimension`: 各 top 5
   - `term`: top 5
   - `field / table`: 各 top 8（字段过多容易挤占 prompt）
5. **全局 token 预算**：对投影后的轻量资产序列做二次截断，保证总 token 不超过预算。
6. **元信息脱敏**：剔除 `metadata` 中除 `table_name / column_name / parameters` 外的字段，避免把 QueryGraph 内部上下文、SQL 片段等泄漏给 LeadAgent。

```python
# 过滤函数签名示例（供 M1 投影层消费）
def filter_lead_planner_assets(
    candidate_assets: dict[str, Any],
    *,
    min_confidence: float = 0.05,
    max_per_type: dict[str, int] | None = None,
    allowed_types: set[str] | None = None,
) -> list[CandidateAsset]:
    ...
```

---

## 5. M1 投影层接口契约

`lead_agent_planner_projection.py`（M1）应该暴露一个稳定的投影函数，把过滤后的 `CandidateAsset` 列表转换成 LeadAgent Planner 可消费的 Prompt 片段。

### 5.1 建议接口

```python
# lead_agent_planner_projection.py（M1 待实现）
from typing import Any, Literal

LeadPlannerStage = Literal["skill_selection", "tool_planning"]


def project_assets_for_lead_planner(
    assets: list[CandidateAsset],
    *,
    stage: LeadPlannerStage,
    token_budget: int = 1200,
    question: str | None = None,
) -> dict[str, Any]:
    """把候选资产投影成 LeadAgent Planner 可消费的轻量上下文。

    Args:
        assets: 已经过 filter_lead_planner_assets 过滤后的候选资产。
        stage:  skill_selection 阶段需要类型摘要；tool_planning 阶段需要 top 资产详情。
        token_budget: 投影结果建议占用的最大 token 数。
        question: 用于计算问题相关片段，可选。

    Returns:
        {
            "assets": [...],           # 轻量资产列表
            "summary": {...},          # 类型统计、覆盖率、top_asset_types
            "stage": stage,
            "token_budget": token_budget,
            "projected_at": "...",
        }
    """
    ...
```

### 5.2 投影输出字段

- `assets`: 每个元素只保留
  - `asset_type`, `asset_id`, `name`, `display_name`
  - `source`, `confidence`, `usage`, `match_reason`
  - `match_signals`: 最多 3 条，每条只保留 `type / value / score`
  - `metadata`: 仅保留 `table_name / column_name / parameters` 等最轻量键
- `summary`:
  - `total`: 投影后资产总数
  - `counts_by_type`: 各类型数量
  - `top_asset_types`: 置信度最高的 3 类资产
  - `coverage`: 有置信度的资产占比、signal_types
- `stage`: 标识当前处于哪一阶段，便于 prompt 差异化描述

### 5.3 与现有 `_lightweight_asset` 的关系

SubAgent Planner 里已经有 `_lightweight_asset`（`planner.py`）。M1 投影层可以借鉴，但要进一步收紧：

- 不输出 `reject_reason`（LeadAgent 阶段还没有 reject 概念）。
- `metadata` 白名单更严格。
- 按 `stage` 做差异化（skill_selection 更粗，tool_planning 稍细）。

---

## 6. 在 `plan_tool_calls_with_llm` 里的修改点

### 6.1 新增局部变量

```python
# 在 plan_tool_calls_with_llm 内、skill_input 之前
raw_candidate_assets = _maybe_recall_assets_for_lead_planner(
    db, question=question, tool_policy=tool_policy
)
filtered_assets = filter_lead_planner_assets(raw_candidate_assets)
# M1 合入后才能导入：
# asset_projection = project_assets_for_lead_planner(
#     filtered_assets, stage="skill_selection", token_budget=600
# )
asset_projection = {"assets": [], "summary": {}}  # M1 占位
```

### 6.2 注入 `skill_input`

```python
skill_input = {
    "question": question,
    "conversation": conversation_summary,
    "tool_policy": tool_policy,
    "skills": skills,
    "candidate_assets": asset_projection,  # 新增
}
```

### 6.3 注入 `planner_input`

Tool Planner 阶段需要重新投影（stage 更细）：

```python
planner_input = {
    "question": question,
    "conversation": conversation_summary,
    "tool_policy": tool_policy,
    "selected_skills": selected_skill_payloads,
    "tool_schemas": disclosed_tool_schemas,
    "candidate_assets": project_assets_for_lead_planner(
        filtered_assets, stage="tool_planning", token_budget=800
    ),  # M1 后启用
}
```

### 6.4 追踪字段

`tracer.start_generation` 的 `metadata` 中可以增加：

```python
"candidate_asset_recall_called": bool(locked_dataset_id),
"candidate_asset_count": len(asset_projection.get("assets", [])),
"candidate_asset_summary": asset_projection.get("summary", {}),
```

---

## 7. 被 M1 阻塞的变更

以下改动必须等 `lead_agent_planner_projection.py` 合入后才能写代码：

1. **投影函数导入**：`from app.services.lead_agent_planner_projection import project_assets_for_lead_planner`
2. **Prompt 模板升级**：`LEAD_AGENT_SKILL_SELECTOR_PROMPT_NAME` 和 `LEAD_AGENT_TOOL_PLANNER_PROMPT_NAME` 需要增加 `candidate_assets` 字段说明，否则 LLM 不会利用这些资产。
3. **Token 预算校准**：目前 `LIGHTWEIGHT_CONTEXT_TOKEN_BUDGET = 2500` 是 SubAgent 召回层的预算；LeadAgent Planner 需要独立的 `LEAD_PLANNER_ASSET_TOKEN_BUDGET`，避免把 SubAgent 的上下文预算耗尽。
4. **Prompt 版本与观测字段**：需要在 `metadata` 中记录 `disclosed_asset_count`、`asset_projection_stage` 等字段，用于后续 Langfuse 分析。
5. **确定性快路径评估**：当前 `_deterministic_tool_plan` 绕过两次 LLM。M1 后需要评估：当锁定数据集且候选资产显示高度匹配的 `blueprint_execute` 机会时，是否应让确定性快路径直接命中 `subagent_dispatch` 并附带 `entry_intent` 提示。
6. **重复召回消除**：SubAgent.run 内部仍然会调用 `recall_candidate_assets`。M1 后需要考虑把 LeadAgent 召回结果通过 `capsule` 或 `lead_agent_context` 透传给 SubAgent，避免同一问题两次 DB 召回。

---

## 8. 风险与建议

1. **LeadAgent 不应变成语义资产执行者**：投影层只给 Planner 提供“摘要证据”，不能让它直接输出 `metric_resolution` / `analysis_blueprint_execute` 等被 `BLOCKED_LEAD_TOOLS` 禁止的工具。
2. **召回失败不能阻塞控制面**：必须 try/except 并降级为空资产，保证 `build_fallback_plan` 仍可工作。
3. **token 爆炸**：字段/表资产数量可能很大，过滤层必须严格执行 top-K 和全局预算。
4. **版本字段缺失**：当前 LeadAgent 阶段没有 `manifest_version` / `bound_schema_version`，召回精度可能低于 SubAgent 阶段；M1 合入后应评估是否值得在 `execute_tool_plan` 的 `manifest_router` 之后补一次精确召回。
5. **Prompt 兼容性**：如果直接给旧版 Prompt 注入 `candidate_assets` 但不更新 system prompt，LLM 可能忽略它。因此 Prompt 升级要和本改动一起发。

---

## 9. 待确认问题

1. M1 投影层是否计划提供 `project_assets_for_lead_planner` 这个函数名？如果不是，本契约需要按实际函数名调整。
2. LeadAgent 的 `locked_dataset_id` 是否足够作为召回触发条件？还是需要在 `manifest_router` 执行后再召回？
3. Skill Selector 阶段是否真的需要候选资产，还是只给 Tool Planner 阶段即可？本草案按“两阶段都注入”设计，若 M1 只支持单阶段可简化。
4. 是否需要新增一个 Lead Skill（例如 `SemanticAssetAwarenessSkill`）来显式表达“利用语义资产做规划”？
