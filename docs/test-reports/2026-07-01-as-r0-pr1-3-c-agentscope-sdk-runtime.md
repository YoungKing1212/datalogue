# AS-R0 PR1.3-c AgentScope 2.0 SDK Runtime Bridge 测试报告

## 范围

- PR1.3-c：把 DatasetAgent Runtime 补成真正的 AgentScope 2.0 SDK 形态。
- 使用 AgentScope 2.0 SDK 模块：
  - `agentscope.tool.ToolBase`
  - `agentscope.tool.ToolMiddlewareBase`
  - `agentscope.middleware.MiddlewareBase`
  - `agentscope.permission.PermissionContext / PermissionDecision / PermissionBehavior`
  - `agentscope.event.RequireExternalExecutionEvent / ExternalExecutionResultEvent`
  - `agentscope.message.ToolResultBlock / TextBlock / ToolResultState`
- Datalogue 继续负责真实工具执行、SQL 隔离、artifact 写入和输出清洗。

## 实现摘要

- 新增 `AgentScopeDatasetRuntimeBridge`：
  - 监听 `RequireExternalExecutionEvent`。
  - 解析 `ToolCallBlock.input`。
  - 执行 Datalogue BI 原子工具。
  - 生成 `ToolResultBlock`。
  - 封装 `ExternalExecutionResultEvent` 回填给 Agent。
- 新增 `DatasetAgentScopeExternalTool(ToolBase)`：
  - 六个 BI 工具均为 `is_external_tool=True`。
  - 工具本身不执行 SQL，不访问 DB。
  - `check_permissions()` 只做 Datalogue fail-closed 门禁。
- 新增 `app.services.agentscope_middlewares` middleware 包：
  - `dataset_tool_logging.py` 中的 `DatasetRuntimeToolLoggingMiddleware(ToolMiddlewareBase)`：拦截 `ToolBase.__call__()` 工具调用链。
  - `safe_log_summary.py`：为工具日志提供安全摘要 helper，不输出 SQL、schema、raw rows 或物理字段明细。
  - `DatasetAgentScopeExternalTool` 默认挂载 `DatasetRuntimeToolLoggingMiddleware`，后续真实 AgentScope toolkit 注册时不需要散落日志逻辑。
- 新增 `run_reply_stream()`：
  - 驱动 `agent.reply_stream(msg)`。
  - 捕获外部工具事件。
  - 执行安全工具结果回填。
  - 调用 `agent.reply(ExternalExecutionResultEvent)` 让 AgentScope 继续。

## 工具清单

- `get_dataset_status`
- `list_candidate_assets`
- `compile_dsl_to_sql`
- `execute_compiled_query`
- `repair_dsl`
- `create_query_artifact`
- `get_artifact_summary`

## 安全边界

- `execute_compiled_query` 必须在 `compile_dsl_to_sql` 成功后调用。
- `execute_compiled_query` 只能接收当前会话的 `compiled_query_ref`。
- `compile_dsl_to_sql` 回填给 Agent 的结果只包含 `compiled_query_ref` 和安全状态。
- 非 `bi_lead_agent` 调 BI 工具会被 `PermissionDecision(DENY)` 拦截。
- SQL、schema 全量、raw rows、物理字段明细、`query_plan` 主体、RepairPatch 主体、blueprint 主体不会进入 `ToolResultBlock`。

## 验证

- `cd datalogue-api && python3 -m pytest tests/test_agentscope_dataset_runtime_bridge.py -q`
  - 结果：7 passed，2 warnings。
  - 覆盖：
    - ToolBase external tool 注册。
    - ToolMiddlewareBase 挂载与工具调用安全日志。
    - PermissionContext / PermissionDecision / PermissionBehavior 拦截非 BI Agent、敏感入参、compile 前 execute、伪造 compiled ref。
    - RequireExternalExecutionEvent 到 ExternalExecutionResultEvent 的安全转换。
    - ToolResultBlock / TextBlock / ToolResultState 回填。
    - agent.reply_stream -> external execution -> agent.reply resume loop。
    - FIELD_NOT_FOUND 后的 `repair_dsl` 受控修复链路。
- `cd datalogue-api && python3 -m pytest tests/test_agentscope_dataset_runtime_bridge.py tests/test_agentic_dataset_runtime.py tests/test_as_r0_atomic_runtime_cutover.py tests/test_agentscope_chat_bridge.py tests/test_agentic_shell_contract.py tests/test_as_r0_security_matrix.py -q`
  - 结果：58 passed，6 warnings。
  - 说明：同步把 AS-R0 atomic cutover 测试调整为兼容 AgentScope bridge direct 入口；`trace_id` 在关闭 Trace 后允许缺失或为空，但 artifact/final/Workbench 安全契约保持不变。

## 依赖说明

- 新增 `agentscope==2.0.3`。
- AgentScope 2.0.3 经 `mcp` 依赖要求较新的 Pydantic，因此后端依赖声明调整为：
  - `pydantic>=2.11,<3`
  - `pydantic-settings>=2.6,<3`
- 本地 Python 3.13 下，旧 `pydantic==2.7.4` 无可用 wheel，会触发 `pydantic-core` 源码构建失败；新范围避免 fresh install 时和 AgentScope resolver 冲突。
- 本地验证环境最终保持 `starlette==0.37.2`、`sse-starlette==2.1.0`，避免 AgentScope 安装过程把 Starlette 升级到 FastAPI 不兼容版本。

## 残留风险

- 当前 `/chat/stream` 主链仍使用 Datalogue 直接 atomic runtime 执行；本 PR1.3-c 提供 AgentScope SDK bridge 和测试 fake agent loop，尚未把真实 LLM DatasetAgent 实例接入生产流。
- `create_query_artifact` 在 bridge 中只发布当前 execute 已生成的 artifact ref，不允许 Agent 提交 raw payload 绕过 SQL/raw rows 安全边界。
