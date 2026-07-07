# AgentScope OTel 模型调用日志方案

> **当前决策:** 模型调用日志由 AgentScope 原生 `TracingMiddleware` / OpenTelemetry 负责。Datalogue 自定义生命周期、BI Worker、Dataset Tool 和模型 I/O 执行日志不再写普通后端 logger；用户可见层只保留安全业务事件和进度事件。

## 背景

- Datalogue 模型调用路径已经从 LiteLLM 迁到 AgentScope-native，后续可观测性不能再围绕 LiteLLM adapter 设计。
- AgentScope 2.0.3 官方 `TracingMiddleware` 已覆盖 reply、model_call、tool_execution 等 span，位置比 Datalogue 自定义 logger 更贴近运行时。
- 当前代码已收口为 `BIWorkerProgressMiddleware`：只发布前端进度事件，不再持有 `on_model_call` 或自定义模型 I/O 日志。
- OTel exporter 由运行环境决定；未配置 `TracerProvider` 时 AgentScope tracing 保持低开销短路。

## 目标

- 打通 AgentScope OTel 观测入口，按 task、session、agent、model 和 worker 定位一次请求。
- 去除 Datalogue 自定义执行日志，避免 SQL、schema、raw rows、query plan 等内部执行态进入普通日志。
- 用户可见 SSE、Workbench View Model、artifact 摘要和最终 answer 继续只承载安全业务 payload。
- 后续需要 Trace 平台时，只配置 OTel exporter，不重写模型调用链路。

## 非目标

- 不恢复 Langfuse。
- 不重新引入 LiteLLM 作为模型调用核心。
- 不把 raw prompt、SQL、schema、raw rows、query plan 写入聊天消息、Workbench 用户可见 payload、artifact card 或前端状态。
- 不再新增本地 raw 执行日志入口；排障优先看 OTel span、后端异常栈和业务 artifact。

## 分层设计

### 1. 用户可见层：始终安全摘要

用户可见面包括聊天 SSE、Agent progress bridge、Workbench View Model、artifact 摘要和最终 answer。

这些位置只允许出现：

- `task_id`
- `thread_id`
- `message_id`
- `agent_name`
- `model_name`
- `tool_name`
- `artifact_ref`
- `row_count`
- `column_count`
- 业务级状态和错误码

禁止出现：

- prompt 全文
- messages 全文
- tools schema 全文
- SQL
- schema
- raw rows
- query plan
- RepairPatch
- blueprint body
- credential 或 API Key

### 2. 观测层：OTel span

默认观测走 AgentScope `TracingMiddleware` 生成的 span，用于日常定位：

- `task_id`
- `thread_id`
- `session_id`
- `agent_id`
- `agent_name`
- `model`
- `message_count`
- `tool_count`
- `tool_names`
- `input_chars`
- `output_chars`
- `finish_reason`
- `chunk_index`
- `duration_ms`
- `error_type`
- `error_code`

这些字段应作为 OTel span attribute 或事件附加信息，而不是普通业务 logger 文本。

## OTel 接入策略

### 阶段 1：保留 AgentScope TracingMiddleware

- 在 AgentScope Agent 创建处挂 `TracingMiddleware()`。
- FastAPI lifespan 中调用 `setup_agentscope_tracing(settings)`，按配置创建 `TracerProvider`。
- `AGENTSCOPE_OTEL_TRACING_ENABLED=true` 且 `AGENTSCOPE_OTEL_LOGGING_ENABLED=true` 时，使用本地 logging span exporter 输出 `[agentscope.otel.span]`，不外发到 collector。
- BI worker 额外中间件只保留 `BIWorkerProgressMiddleware`，用于前端进度，不做执行日志。

### 阶段 2：可选接 OTLP exporter

- 配置 OTLP exporter 后，由 AgentScope 生成的 `reply/model_call/tool_execution` span 树可外发到 collector。
- 后端普通 logger 不恢复 `[agentscope.bi_worker.*]`、`[agentscope.dataset_tool.*]`、`[datalogue.lifecycle]` 或 `[datalogue.output]`。

### 阶段 3：Datalogue 自定义 span 属性

如果内置 span 不够用，再补自定义属性，不替换 AgentScope 中间件：

- `datalogue.task_id`
- `datalogue.thread_id`
- `datalogue.message_id`
- `datalogue.artifact_ref`
- `datalogue.dataset_id`
- `datalogue.agent_role`
- `datalogue.worker_agent_id`

自定义属性默认只放 ID、状态和 ref；raw prompt、SQL、schema 和 raw rows 不进入普通 logger。

## 实施清单

- [x] 移除 `worker_logging.py` 的自定义 `on_model_call` 模型 I/O 日志。
- [x] 让 `DatasetRuntimeToolLoggingMiddleware` 变为透传兼容壳，不再输出 `[agentscope.dataset_tool.*]`。
- [x] 让 `log_lifecycle()`、`log_output()` 静默，保留函数签名兼容旧调用方。
- [x] 移除 AgentScope Service 工具层 `[agentscope.bi_worker.*]` 执行日志。
- [x] 当前阶段挂 AgentScope `TracingMiddleware()`，并在无 OTLP exporter 时用本地 logging span exporter 打印 `[agentscope.otel.span]`。
- [ ] 若接 OTel exporter，新增独立配置项，例如 `AGENTSCOPE_OTEL_ENABLED`、`AGENTSCOPE_OTEL_EXPORTER_ENDPOINT`。

## 验收口径

后端测试：

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_agentic_architecture_p1_boundaries.py tests/test_agentscope_service_worker_logging.py tests/test_agentscope_service_factory.py tests/test_agentscope_service_tools.py tests/test_agentscope_dataset_runtime_bridge.py -q
cd datalogue-api && .venv/bin/python -m compileall app -q
```

静态扫描：

```bash
rg -n "\\[datalogue\\.(lifecycle|output)|\\[agentscope\\.(bi_worker|dataset_tool)|BIWorkerStreamingLogMiddleware|on_model_call\\(" datalogue-api/app datalogue-api/tests
```

真实链路排障验证：

1. 跑一次 `/chat` 问数，确认普通后端日志不再出现 Datalogue 自定义执行日志 marker。
2. 确认日志中出现 `[agentscope.otel.span]`，并可用 `trace_id/span_id/name` 对齐 AgentScope span 与 artifact API。
3. 检查页面、SSE payload、Workbench 和 artifact 摘要不显示 raw prompt、tools schema、SQL、schema 或 raw rows。

## 风险与边界

- OTel span 属性不适合承载大段 prompt；不要把完整 prompt、SQL、schema 或 raw rows 放进 attribute。
- OTel 本地日志会带 span attributes；排障时可以短时间开启，定位后关闭 `AGENTSCOPE_OTEL_TRACING_ENABLED`。
