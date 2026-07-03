# ============================================================
# File Name   : test_bi_lead_agent_dataset_agent_factory.py
# Description:
#   BI Agent DatasetAgent 工厂的 AgentScope SDK 装配测试。
#
# Responsibilities:
#   - 验证 DatasetAgent 创建时挂载 AgentScope OpenTelemetry tracing middleware。
#   - 避免真实模型请求参与测试，只校验 SDK 边界参数。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from types import SimpleNamespace

from agentscope.middleware import TracingMiddleware

from app.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeSession
from app.agents.bi_agent import dataset_agent_factory
from app.agents.bi_agent.dataset_agent_factory import AgentScopeDatasetAgentFactory


def test_dataset_agent_factory_attaches_agentscope_tracing_middleware(monkeypatch, db_session):
    captured_agent_kwargs: dict = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured_agent_kwargs.update(kwargs)

    class FakeOpenAIChatModel:
        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(dataset_agent_factory, "Agent", FakeAgent)
    monkeypatch.setattr(dataset_agent_factory, "OpenAIChatModel", FakeOpenAIChatModel)
    monkeypatch.setattr(dataset_agent_factory, "build_dataset_agentscope_tools", lambda **_kwargs: [])
    monkeypatch.setattr(
        dataset_agent_factory,
        "resolve_llm_config",
        lambda *_args, **_kwargs: SimpleNamespace(
            name="test-provider",
            api_key="test-key",
            base_url="http://llm.test",
            model="test-model",
            request_timeout_seconds=3,
        ),
    )

    factory = AgentScopeDatasetAgentFactory(db_session)
    factory.create(AgentScopeDatasetRuntimeSession(dataset_id=10, question="查询日志"))

    middlewares = captured_agent_kwargs.get("middlewares")
    assert middlewares is not None
    assert any(isinstance(middleware, TracingMiddleware) for middleware in middlewares)
