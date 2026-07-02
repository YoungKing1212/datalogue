# BI LeadAgent K3 AgentScope Native Handoff 验收记录

## 范围

- 新增 `BIHandoffPort`，让 `BIHandoffService` 只依赖 `query_dataset` 端口。
- 新增 `AgentScopeNativeBIHandoff`，作为 K3 默认启用的 handoff 实现；`BI_LEAD_AGENT_HANDOFF_MODE=host_adapter` 仅保留为显式回退开关。
- 新增 native handoff event 投影，把 AgentScope child-run 事件收敛为 Datalogue `BILeadAgentHandoffResult`。
- 默认模式已切为 `agentscope_native`，K1/K2 API 和页面原型继续通过同一 D2 安全 DTO 兼容。
- K3 live 路径绑定 DatasetAgent Runtime 的 SQL executor、compiler context 和 direct fallback；当 AgentScope 子运行没有继续产出 artifact 时，仍由 DatasetAgent Runtime 状态机执行 compile/execute/artifact 收口。

## 安全边界

- BI LeadAgent 仍不直接调用 Dataset 原子工具。
- native handoff 内部可创建 AgentScope 2.0 DatasetAgent 子运行，但对外只返回 D2 安全结果：`handoff_id`、`parent_agent`、`child_agent`、`child_run_id`、`dataset_id`、`task_id`、`trace_id`、`checkpoint_ref`、`artifact_ref`、`handoff_status`、安全摘要和结果规模。
- `schema`、`sql`、`dsl`、`raw_rows`、`result_rows`、`result_columns` 等执行层内部字段不会进入 handoff DTO、API response 或测试断言可见 payload。
- Datalogue DB 仍是 run / confirmation / handoff 的业务状态真相源；AgentScope native event 只是执行形态和事件来源。
- direct fallback 只在 native child run 停留在 accepted/running/waiting 且没有 artifact/error 时触发，仍不让 BI LeadAgent 直接调用 Dataset 原子工具。

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

结果：`62 passed, 2 warnings`；前端 BI LeadAgent 相关 vitest `21 passed`；`npm run build` 通过，仅保留既有 chunk size warning。

## Live Smoke

- 时间：2026-07-02 09:31。
- 服务：`127.0.0.1:8002`，默认 `BI_LEAD_AGENT_HANDOFF_MODE=agentscope_native`。
- 请求链路：`POST /api/bi-lead-agent/runs -> confirm -> handoff -> GET run`。
- 数据集：`dataset_id=12`，问题：`统计合同总金额`。
- 结果：`run.status=completed`、`handoff.handoff_status=completed`、`child_run_id=dataset-native-run-f677382456d542f885b04a2225c068e6`、`artifact_ref=artifact:b630734eabb14351a17a6b70db4c8c55`、`row_count=100`、`column_count=8`。
- Artifact 校验：`query_artifact` 存在，`dataset_id=12`，`trace_id=live-bi-lead-native-trace-1782955885`，`kind=sql_result`，`size_bytes=26809`。

## 残留风险

- K3 仍是 B-ready/F3-ready 的内部实现演进，不启用完整长生命周期 F3 会话 Agent。
- K3 已直接启用 `agentscope_native` 默认模式，真实 handoff/artifact 链路已完成一次 live smoke。
- 当前 live fallback 证明的是成功链路和 artifact 闭环；`统计合同总金额` 仍走 QueryGraph 结果引用，后续应增强 metric compiler，把语义指标 `合同总金额 = SUM(ht_amount)` 编译为严格聚合结果。
