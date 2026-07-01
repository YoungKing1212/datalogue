# BI LeadAgent K3 AgentScope Native Handoff 验收记录

## 范围

- 新增 `BIHandoffPort`，让 `BIHandoffService` 只依赖 `query_dataset` 端口。
- 新增 `AgentScopeNativeBIHandoff`，作为 `BI_LEAD_AGENT_HANDOFF_MODE=agentscope_native` 时的可切换实现。
- 新增 native handoff event 投影，把 AgentScope child-run 事件收敛为 Datalogue `BILeadAgentHandoffResult`。
- 默认模式仍为 `host_adapter`，保证 K1/K2 API 和页面原型兼容。

## 安全边界

- BI LeadAgent 仍不直接调用 Dataset 原子工具。
- native handoff 内部可创建 AgentScope 2.0 DatasetAgent 子运行，但对外只返回 D2 安全结果：`handoff_id`、`parent_agent`、`child_agent`、`child_run_id`、`dataset_id`、`task_id`、`trace_id`、`checkpoint_ref`、`artifact_ref`、`handoff_status`、安全摘要和结果规模。
- `schema`、`sql`、`dsl`、`raw_rows`、`result_rows`、`result_columns` 等执行层内部字段不会进入 handoff DTO、API response 或测试断言可见 payload。
- Datalogue DB 仍是 run / confirmation / handoff 的业务状态真相源；AgentScope native event 只是执行形态和事件来源。

## 验证

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_handoff_port.py \
  tests/test_bi_lead_agent_native_handoff.py \
  tests/test_bi_lead_agent_handoff_parity.py \
  tests/test_bi_lead_agent_services.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_bi_lead_agent_api.py \
  -q
```

结果：`35 passed, 2 warnings in 0.20s`。

## 残留风险

- K3 仍是 B-ready/F3-ready 的内部实现演进，不启用完整长生命周期 F3 会话 Agent。
- 真实 LLM / AgentScope native live handoff 需要凭据和运行环境后再做 smoke。
- `BI_LEAD_AGENT_HANDOFF_MODE=agentscope_native` 默认不打开，生产切换前需要额外发布闸门和真实链路观察。
