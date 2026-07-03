# ============================================================
# File Name   : test_agentscope_service_bootstrap.py
# Description:
#   AgentScope Service 中固定 Agent 启动配置测试。
#
# Responsibilities:
#   - 确认 bootstrap 基于固定 Agent 注册表准备 Agent。
#   - 确认 bootstrap 只依赖 AgentScope Service /agent 边界。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx


def test_bootstrap_static_agent_keys_match_registry():
    from app.agentscope_service.bootstrap import STATIC_AGENT_KEYS
    from app.agentscope_service.registry import build_datalogue_static_agent_specs

    registry_keys = tuple(item.key for item in build_datalogue_static_agent_specs())

    assert STATIC_AGENT_KEYS == registry_keys


def test_bootstrap_service_finds_existing_and_creates_missing_static_agents():
    from app.agentscope_service.bootstrap import AgentScopeBootstrapService

    captured_posts: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/agent":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "agent-lead-existing",
                            "metadata": {
                                "datalogue_static_agent_key": "agentic_lead_agent",
                            },
                        }
                    ]
                },
            )
        if request.method == "POST" and request.url.path == "/agent":
            payload = json.loads(request.content.decode("utf-8"))
            captured_posts.append(payload)
            key = payload["metadata"]["datalogue_static_agent_key"]
            return httpx.Response(200, json={"id": f"agent-created-{key}"})
        return httpx.Response(404, json={"detail": "unexpected request"})

    client = httpx.AsyncClient(
        base_url="https://agentscope.example",
        transport=httpx.MockTransport(handler),
    )
    service = AgentScopeBootstrapService(
        base_url="https://agentscope.example",
        client=client,
    )

    mapping = asyncio.run(service.ensure_static_agents())
    asyncio.run(client.aclose())

    assert mapping == {
        "agentic_lead_agent": "agent-lead-existing",
        "bi_agent": "agent-created-bi_agent",
        "report_agent": "agent-created-report_agent",
        "python_agent": "agent-created-python_agent",
        "audit_agent": "agent-created-audit_agent",
    }
    assert [item["metadata"]["datalogue_static_agent_key"] for item in captured_posts] == [
        "bi_agent",
        "report_agent",
        "python_agent",
        "audit_agent",
    ]
    assert all("system_prompt" in item for item in captured_posts)


def test_bootstrap_service_can_be_constructed_by_main_entry_without_client():
    from app.agentscope_service.bootstrap import AgentScopeBootstrapService

    service = AgentScopeBootstrapService(base_url="http://localhost:8001")

    assert service.base_url == "http://localhost:8001"
    assert callable(service.ensure_static_agents)
