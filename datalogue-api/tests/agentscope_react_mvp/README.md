# AgentScope ReAct MVP 真实集成测试

这个目录用于验证 AgentScope 2.0 能否承接 Hermes Skill 的最小问数执行逻辑：由 AgentScope `Agent` 自主选择工具，先请求数语平台的语义资产，再通过只读 SQL preview 调用平台执行能力。

## 验证边界

- 真实请求当前部署的 Datalogue API，不使用 mock HTTP。
- 不调用 `/api/chat/stream` 和 `/api/conversation`，避免把完整 LeadAgent 主链路误当成 AgentScope 自主能力。
- 工具面保持最小：`DataloguePlanQueryTool` 负责获取数据集、已选表、已选字段和语义资产；`DatalogueExecuteSqlTool` 负责调用 `/api/dataset/{id}/sql/preview`。
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

执行真实 MVP 测试：

```bash
cd datalogue-api
RUN_AGENTSCOPE_REACT_MVP=1 DATALOGUE_BASE_URL=http://127.0.0.1:8000 \
  .venv/bin/python -m pytest tests/agentscope_react_mvp/test_live_react_agent.py -q -s
```

不设置 `RUN_AGENTSCOPE_REACT_MVP=1` 时，该测试会跳过，避免普通测试套件请求真实 LLM 和真实服务。

## 当前判断

如果测试通过，说明 AgentScope 2.0 在最小 MVP 上可以做到类似 Hermes 的 ReAct 自主决策与平台能力调用：Agent 自己调用 plan 工具获取真实上下文，生成 SQL，再调用 SQL preview 工具执行，并且测试只信后端 preview 的结构化结果。

这个目录仍是实验性验证，不是正式生产 Agent 运行时。后续如果要产品化，需要把工具注册、权限策略、观测 trace、失败重试和 SQL 修复策略纳入主链路设计。
