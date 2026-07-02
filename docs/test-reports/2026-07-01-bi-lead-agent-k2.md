# BI LeadAgent K2 页面原型与端到端契约验收记录

## 范围

- 新增 BI LeadAgent Web API client，封装 create / get / confirm / handoff / capabilities。
- 新增确认卡片、运行状态面板和 `BILeadAgentFlow` 页面容器，串起 `create -> confirmation -> handoff -> final run`。
- 在 ChatPage 右侧接入 BI LeadAgent 原型工作区，同时保留现有 WorkbenchPanel。
- 新增后端端到端契约测试，覆盖页面依赖的 create / confirm / handoff / get 生命周期和 refs 返回。

## 安全边界

- 前端确认 payload 只包含数据集能力摘要字段，不携带 `schema`、`sql`、`dsl`、`raw_rows`。
- 运行面板只展示安全摘要、artifact/checkpoint refs 和结果规模，不展示 DatasetAgent 执行层内部字段。
- 后端端到端测试只替换 DatasetAgent runtime adapter，仍走真实 FastAPI endpoint、service、DB 写入和 response DTO。

## 验证

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_models.py \
  tests/test_bi_lead_agent_capabilities.py \
  tests/test_bi_lead_agent_services.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_bi_lead_agent_api.py \
  tests/test_bi_lead_agent_e2e_contract.py \
  tests/test_agentscope_dataset_runtime_bridge.py \
  tests/test_as_r0_security_matrix.py \
  -q
```

结果：`47 passed, 2 warnings in 0.33s`。

```bash
cd datalogue-web
npm run test -- \
  src/assistant/bi-lead-agent-api.test.js \
  src/components/bi-lead-confirmation-card.test.jsx \
  src/components/bi-lead-run-panel.test.jsx \
  src/components/bi-lead-agent-flow.test.jsx \
  src/components/chat-page.test.jsx
```

结果：`5 passed (5), 42 passed (42)`。

```bash
npm run lint
npm run build
```

结果：lint 通过，保留 13 个既有 warning；build 通过，保留 Vite chunk size warning。

## Review

K2 只读 code review 结论：未发现阻断问题；`BILeadAgentFlow`、ChatPage 接入、后端 E2E contract 和 handoff 硬边界均通过检查。

## 残留风险

- K2 是页面原型闭环，尚未做真实浏览器截图验收。
- 真实 LLM DatasetAgent live handoff 需要凭据后单独 smoke。
- 多数据集 `query_multiple_datasets` 仍是 disabled capability，后续按 B-ready/F3 计划演进。
