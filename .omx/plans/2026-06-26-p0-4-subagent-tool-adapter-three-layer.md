# P0.4 DatasetAgentToolAdapter 三层出参协议计划

## Requirements Summary

- 将 `datalogue-api/app/services/subagent_tool_adapter.py` 的 `SubAgentToolResult` 固化为 `llm_visible`、`control_plane`、`trace_metadata` 三层。
- `llm_visible` 只承载安全摘要和引用，禁止包含 `raw_sql`、`raw_result`、`capsule`、`schema`、trace body 等控制面/内部字段。
- `control_plane` 继续承载后端持久化、conversation_state、artifact、日志和 trace 所需的 SQL、结果、capsule、last_success_task 等内部对象。
- `trace_metadata` 提供稳定追踪字段：`schema_version`、`dataset_id`、`tool_name`、`guard_status`、`artifact_id`、`status` 等。
- 调用点迁移后，LeadAgent / Chat / fanout 的 LLM context 和用户可见 metadata 只消费 `llm_visible`，`control_plane` 只进入后端 sink 或 trace/状态写入路径。

## Compatibility Migration Strategy

- 保持现有 `LLMVisiblePart`、`ControlPlanePart`、`SubAgentToolResult` 名称不变，避免大面积调用点重命名。
- `SubAgentToolResult` 继续允许以 dict 构造三层对象，兼容文档示例和现有测试；`control_plane` 增加受控 raw payload 字段，而不是开放任意 extra。
- `llm_visible` 使用 Pydantic `extra="forbid"` 和 adapter 级泄露扫描双重约束：模型层拒绝未知字段，扫描层防止安全字段值里夹带 raw/control 内容。
- `trace_metadata` 增加 schema version 和追踪字段，旧调用点读取 `status` / `dataset_id` 不受影响。
- 对 `control_plane.model_dump(exclude={"raw_error"})` 等既有调用保持兼容，只扩展字段，不改变返回类型。

## Call-Site Migration Order

1. `tests/test_subagent_tool_adapter.py`：先补红灯测试，覆盖 dict 构造、`assemble_from_final_state()` 生成 trace metadata、`llm_visible` 敏感字段扫描。
2. `app/services/subagent_tool_adapter.py`：实现模型字段、trace metadata builder、control plane raw payload、visible 扫描。
3. `app/services/subagent_fanout.py`：确认 fanout 只渲染/合成 `llm_visible`，control plane 只进入 `control_planes` sink。
4. `app/api/chat.py`：确认单 SubAgent 与 fanout 路径用户可见 metadata 使用 `subagent_tool_result` 的 `llm_visible`，control plane 只写 sink、refs、conversation_state。
5. `tests/test_subagent_run.py`：跑现有集成回归，确保 SubAgent final_state 不因协议收紧而破坏。

## Leak Scan Rules

- 对 `llm_visible.model_dump(mode="json")` 递归扫描 key 和字符串值。
- 禁止 key 或内容命中：`raw_sql`、`raw_result`、`sql_result`、`capsule`、`schema`、`trace_body`、`control_plane`、`out_capsule`、`query_task_capsule`。
- 允许 `result_ref`、`report_ref`、`dataset_id`、`status` 等引用/摘要字段；SQL 与结果明细必须转入 `control_plane` 或 artifact 引用。
- `render_for_llm()` 只读取 `llm_visible`，测试用控制面 secret、SQL 和 raw result 做回归扫描。

## Acceptance Criteria

- `SubAgentToolResult(llm_visible=dict, control_plane=dict, trace_metadata=dict)` 可构造，且 `llm_visible` 不泄露 raw/control 字段。
- `assemble_from_final_state()` 的 `trace_metadata` 至少包含 `schema_version="subagent_tool_result.v1"`、`tool_name="dataset_subagent"`、`dataset_id`、`status`、`guard_status`、`artifact_id`。
- `control_plane` 可保存 `raw_sql` 和 `raw_result`，但 `render_for_llm()`、chat/fanout 用户可见 metadata 不包含这些内容。
- `tests/test_subagent_tool_adapter.py` 和 `tests/test_subagent_run.py` 通过。

## Risks and Mitigations

- 风险：`llm_visible` 扫描过严误伤普通业务摘要。缓解：扫描聚焦 raw/control 关键字和 SQL 形态，不扫描通用词。
- 风险：`control_plane` 增加 raw 字段后被误传给 LLM。缓解：调用点维持只读 `llm_visible`，测试覆盖 `render_for_llm()` 和 chat/fanout metadata。
- 风险：artifact id 命名来源不一致。缓解：优先使用 `result_ref`，其次 `report_ref`，缺失时为 `None`，不伪造引用。

## Verification Steps

- `cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_tool_adapter.py -q`
- `cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_run.py -q`
- `cd datalogue-api && .venv/bin/python -m py_compile app/services/subagent_tool_adapter.py app/services/subagent_fanout.py app/api/chat.py`
