# AgentScope Hermes-style DatasetAgent MVP 真实集成测试

这个目录用于验证 AgentScope 2.0 能否承接 Hermes Skill 的最小问数执行逻辑：由 AgentScope `Agent` 自主选择受控工具，加载 `hermes-skills/datalogue/SOUL.md` / `SKILL.md` 生成 system prompt，再通过 capability manifest 暴露 DatasetAgent 内部工具。

## 验证边界

- 真实请求当前部署的 Datalogue API，不使用 mock HTTP。
- 不调用 `/api/chat/stream` 和 `/api/conversation`，避免把完整 LeadAgent 主链路误当成 AgentScope 自主能力。
- LeadAgent 工具面只作为边界写入 prompt：`list_datasets`、`describe_dataset_capability`、`query_dataset`、`query_multiple_datasets`。
- DatasetAgent 内部工具由 `capability_manifest` 控制：`recall_assets`、`plan_query`、`guard_sql`、`preview_sql`、`execute_query`、`persist_artifact`、`summarize_result`。
- 真正请求后端执行的路径仍然只有 `/api/dataset/{id}/sql/preview`；`execute_query` 在 MVP 中也会走同一个 guarded preview。
- 工具结果返回 Datalogue 风格协议：`result_ref`、`artifact`、`summary`、`sql_guard`、`tool_trace`。
- LLM 配置复用 Datalogue 数据库中的 `lead_agent` 配置，避免在测试里维护第二套密钥。

## 运行方式

先确保本地 API 服务可访问，例如：

```bash
curl http://127.0.0.1:8000/health
```

安装 AgentScope 2.0 依赖：

```bash
uv pip install agentscope==2.0.2
```

执行默认测试，确认 manifest 过滤逻辑通过，并运行当前真实请求用例：

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/agentscope_react_mvp/test_live_react_agent.py -q
```

执行真实 DatasetAgent MVP 测试并把过程日志打印到控制台：

```bash
cd datalogue-api
RUN_AGENTSCOPE_REACT_MVP=1 DATALOGUE_BASE_URL=http://127.0.0.1:8000 \
  .venv/bin/python -m pytest tests/agentscope_react_mvp/test_live_react_agent.py -q -s
```

`-s` 会把测试中的日志直接输出到终端。你可以看到 Agent 启动、加载后的工具列表、每一轮 LLM request/response、assistant 可见文本、tool_call 名称与入参、工具 observation、每个真实 HTTP 路径、生成的 SQL、SQL preview 返回摘要、`result_ref`、`artifact`、最终中文回答和 `preview_result` 前 5 行。

默认日志会打印最近 12 条 `react_trace`，用于观察 AgentScope ReAct 的可见执行链路。如果要打印完整 `react_trace`，额外加上：

```bash
AGENTSCOPE_MVP_LOG_FULL_REACT_TRACE=1
```

如果要把每轮 LLM 请求的消息尾部也写入 `react_trace`，额外加上：

```bash
AGENTSCOPE_MVP_LOG_REACT_MESSAGES=1
```

`AGENTSCOPE_MVP_LOG_REACT_MESSAGES=1` 会显著增加日志体积，适合排查 prompt、历史 observation 和工具 schema 如何进入下一轮请求；不要把它当作生产默认日志。

如果要打印完整 preview 结果，额外加上：

```bash
AGENTSCOPE_MVP_LOG_FULL_RESULT=1
```

`RUN_AGENTSCOPE_REACT_MVP=1` 保留为显式标记，表示本次是在主动执行真实 LLM 和真实 Datalogue 服务链路。

## 当前判断

如果测试通过，说明 AgentScope 2.0 在最小 MVP 上可以做到类似 Hermes 的受控 ReAct 自主决策与平台能力调用：Agent 自己在 manifest 暴露的工具面内获取真实上下文，生成 SQL，再调用 SQL preview 工具执行，并且测试只信后端 preview 的结构化结果和 MVP artifact。

这个目录仍是实验性验证，不是正式生产 Agent 运行时。后续如果要产品化，需要把工具注册、权限策略、观测 trace、失败重试和 SQL 修复策略纳入主链路设计。
