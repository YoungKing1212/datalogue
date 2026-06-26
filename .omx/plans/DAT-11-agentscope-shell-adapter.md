# DAT-11 AgentScope Shell Adapter 最小验证计划

## Requirements Summary

- 只在后端 service 层新增 AgentScope Shell Adapter 验证线，不新增公开 API route、不接前端入口、不启动独立 runner。
- 第一阶段 AgentScope 可见工具白名单只允许 `ask_bi`，不得暴露 schema、SQL、数据库、artifact body、raw result、capsule 或 `control_plane`。
- 复用现有 `SubAgentToolAdapter` 的 `llm_visible/control_plane/trace_metadata` 分层思想，新增最小 `ask_bi`、event envelope、ArtifactCard/refs 契约用于验证边界。
- `control_plane` visibility 事件不能进入 AgentScope 可见事件；`trace_only` 只能进入 trace 验证事件。

## Acceptance Criteria

- `AgentScopeShellAdapter(allowed_tools=["ask_bi"]).run(...)` 的 `used_tools` 恒为 `["ask_bi"]`，响应 JSON 不包含 `raw_sql`、`raw_result`、`capsule`、`schema`、`control_plane`。
- 尝试配置除 `ask_bi` 之外的工具时直接拒绝，避免第一阶段能力面扩散。
- `DatalogueEventEnvelope(visibility="user_visible", payload={"raw_sql": ...})` 校验失败；`control_plane` 事件可构造但不会进入 shell visible events。
- `ask_bi` 返回稳定外层契约：`task_id/status/event_envelope/answer/artifact_card/primary_ref/related_refs`，不泄漏内部控制面字段。
- 聚焦测试命令通过：`tests/test_agentscope_shell_adapter.py`、`tests/test_agentscope_event_adapter.py`、`tests/test_bi_workbench_tool.py`、`tests/test_event_envelope.py`。

## Implementation Steps

1. 新增 `app/schemas/bi_workbench.py`：定义 `ArtifactRef`、`ArtifactAction`、`ArtifactCard`、`DatalogueEventEnvelope`、`AskBIRequest`、`AskBIResponse`，并提供 `validate_event_visibility` / `sanitize_outer_payload`。
2. 新增 `app/services/bi_workbench_tool.py`：实现最小 `ask_bi` 和 `BIWorkbenchTool`，第一阶段只生成安全摘要、event envelope、ArtifactCard 和 refs，不触达 Chat 主链或数据库。
3. 新增 `app/services/agentscope_event_adapter.py`：把统一 envelope 映射为 AgentScope 验证事件，`control_plane` 只进入内部 dropped 计数，不进入可见列表。
4. 新增 `app/services/agentscope_shell_adapter.py`：封装 AgentScope Shell 最小调用，工具白名单固定为 `ask_bi`，输出只包含 ask_bi 安全外层契约。
5. 新增四个聚焦测试文件覆盖 shell、event、ask_bi、envelope 安全边界。
6. 更新 `.codex/project-memory.md` 完成记录。

## Risks and Mitigations

- 风险：P0.5/P0.6/P1.1 在当前分支未完整落地，直接接 Chat 主链会扩大本 issue 范围。
  缓解：本 issue 只做 contract-first 最小 service 验证线，不改 `app/api/chat.py`，不接真实 SSE。
- 风险：AgentScope 依赖未安装或版本不稳定。
  缓解：Shell Adapter 不直接导入 AgentScope runtime，保留后续 runtime 接入点，用内部 contract tests 验证边界。
- 风险：外层响应误带控制面字段。
  缓解：schema 使用 `extra="forbid"`，并在 payload/JSON 级测试敏感关键词。

## Verification Steps

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_agentscope_shell_adapter.py tests/test_agentscope_event_adapter.py tests/test_bi_workbench_tool.py tests/test_event_envelope.py -q
.venv/bin/python -m pytest tests/test_subagent_tool_adapter.py -q
git diff --check -- app/schemas/bi_workbench.py app/services/bi_workbench_tool.py app/services/agentscope_shell_adapter.py app/services/agentscope_event_adapter.py tests/test_agentscope_shell_adapter.py tests/test_agentscope_event_adapter.py tests/test_bi_workbench_tool.py tests/test_event_envelope.py ../.codex/project-memory.md
```

## Stop Conditions

- 不修改公开 API 路由。
- 不新增前端入口。
- 不启动 AgentScope runner 进程。
- 不让 AgentScope Shell 访问 `ask_bi` 之外的工具。
