# DAT-13 LeadAgent Capability Router 计划

## Requirements Summary

- 将 LeadAgent 数据集自动路由收窄为 Hermes-style Capability Router。
- 自动路由只基于 current `DatasetSubAgentManifest.manifest_json` 中的 capability 摘要字段，不读取 schema、SQL、候选资产详情或完整结果。
- 路由候选对外只暴露 `dataset_id`、`dataset_name`、`reason`、`confidence`、`requires_confirmation`。
- 低置信或候选接近时只返回数据集确认，不进入 DatasetAgent/SubAgent dispatch。

## Routing Strategy

- 在 `app/services/dataset_router.py` 中把 manifest 打分和候选序列化合并为 capability-only 视图。
- 输入证据仅使用 `manual_fields.description`、`manual_fields.business_domain`、`manual_fields.sample_questions`、`manual_fields.routing_negative_examples`、`auto_fields.name`、`auto_fields.key_metrics/display_name/name/synonyms`、`auto_fields.key_dimensions/display_name/name/synonyms`。
- 候选 `confidence` 使用 0-1 归一化分数；`reason` 汇总命中证据，负例命中追加降权原因。

## Low Confidence Clarification

- `score < DATASET_ROUTER_AUTO_SELECT_THRESHOLD` 返回 `decision=no_match`，候选均标记 `requires_confirmation=true`。
- `top_score >= threshold` 但与第二名 margin 不足时返回 `decision=ambiguous`，候选均标记 `requires_confirmation=true`。
- 只有 `top_score >= threshold` 且 `margin >= DATASET_ROUTER_AUTO_SELECT_MARGIN` 时返回 `decision=selected`，首候选 `requires_confirmation=false`。

## Fan-out Boundary

- 现有 `build_subagent_dispatch()` 只允许 `decision in {"selected", "locked"}` 进入 dispatch，保持不放宽。
- 在 `lead_agent_routing.py` 增加未确认数据集时的 query_graph 门禁，防止指标/明细问法绕过 Capability Router 直接 fan-out。

## Acceptance Criteria

- 单数据集明确命中时 selected，候选字段严格等于 `dataset_id/dataset_name/reason/confidence/requires_confirmation`。
- 跨数据集近似命中时 ambiguous，返回多个需要确认候选且不 dispatch。
- 低置信单候选时 no_match，返回确认候选且不 dispatch。
- 无 current manifest 时 no_match，候选为空。

## Verification Steps

- `cd datalogue-api && python3 -m pytest tests/test_lead_agent_capability_router.py -q`
- `cd datalogue-api && python3 -m pytest tests/test_lead_agent_routing.py tests/test_lead_agent_tools.py -q`
- `cd datalogue-api && python3 -m py_compile app/services/dataset_router.py app/services/lead_agent_routing.py app/api/chat.py`

## Risks And Mitigations

- 风险：旧调用方仍读取 `score/reasons/manifest_version`。缓解：路由决策顶层保留执行所需的 manifest/schema 字段，只收窄候选列表。
- 风险：低置信候选完全消失导致用户无从确认。缓解：no_match 保留 Top N 候选并统一 `requires_confirmation=true`。
