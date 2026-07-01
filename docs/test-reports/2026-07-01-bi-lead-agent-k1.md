# BI LeadAgent K1 Test Report

## Scope

- BI LeadAgent capability manifest.
- H2 用户确认快照。
- D2 `query_dataset` handoff 安全结果。
- AgentScope 2.0 SDK external tool event adapter。
- M2 run-centric API 与 `/handoff` endpoint。
- W2 安全回归测试包。

## Commands

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_models.py \
  tests/test_bi_lead_agent_capabilities.py \
  tests/test_bi_lead_agent_services.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_bi_lead_agent_api.py \
  tests/test_agentscope_dataset_runtime_bridge.py \
  tests/test_as_r0_security_matrix.py \
  -q
```

## Result

`46 passed, 2 warnings in 0.26s`

Warnings are existing framework deprecations:

- `pytest_asyncio` default fixture loop scope warning.
- Pydantic class-based `Config` deprecation warning on `app/core/config.py`.

## Residual Risk

- K2 需要继续接入真实前端确认卡片、run polling、Workbench refs 和页面端到端验收。
- K3 需要在 K1/K2 稳定后抽象 `BIHandoffPort`，再切换为 AgentScope native handoff 实现。
- Live LLM DatasetAgent handoff 仍应在具备真实凭据后单独跑 live smoke，不纳入默认 CI。
