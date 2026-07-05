# ============================================================
# File Name   : test_agentscope_service_client.py
# Description:
#   Datalogue 到 AgentScope Service 的内部客户端测试。
#
# Responsibilities:
#   - 确认 Datalogue 通过官方 REST 边界创建 session、触发 chat 和订阅 session stream。
#   - 防止 base_url 挂载到 /agentscope 后请求路径丢失前缀。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import json

import httpx
import pytest


@pytest.mark.asyncio
async def test_agentscope_service_client_uses_prefixed_rest_paths_and_payloads():
    requests: list[tuple[str, str, dict, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        requests.append((request.method, request.url.path, payload, request.headers.get("X-User-ID")))
        if request.method == "POST" and request.url.path == "/agentscope/sessions/":
            assert payload == {
                "agent_id": "agent-leader-1",
                "name": "统计合同总金额",
                "chat_model_config": {"model": "gpt-test"},
            }
            return httpx.Response(200, json={"session_id": "session-1"})
        if request.method == "POST" and request.url.path == "/agentscope/chat/":
            assert payload == {
                "agent_id": "agent-leader-1",
                "session_id": "session-1",
                "input": {
                    "name": "user",
                    "role": "user",
                    "content": [{"type": "text", "text": "统计合同总金额"}],
                },
            }
            return httpx.Response(200, json={"status": "started", "session_id": "session-1"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        from app.agentscope_service.client import AgentScopeServiceClient

        client = AgentScopeServiceClient(base_url="http://test/agentscope", http=http)
        session_id = await client.create_session(
            agent_id="agent-leader-1",
            name="统计合同总金额",
            chat_model_config={"model": "gpt-test"},
        )
        await client.trigger_chat(
            agent_id="agent-leader-1",
            session_id=session_id,
            text="统计合同总金额",
        )

    assert [(method, path) for method, path, _payload, _user_id in requests] == [
        ("POST", "/agentscope/sessions/"),
        ("POST", "/agentscope/chat/"),
    ]
    assert {user_id for *_rest, user_id in requests} == {"datalogue-agent-team"}


@pytest.mark.asyncio
async def test_agentscope_service_client_upserts_openai_credential_with_fixed_id():
    requests: list[tuple[str, str, dict, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        requests.append((request.method, request.url.path, payload, request.headers.get("X-User-ID")))
        if request.method == "POST" and request.url.path == "/agentscope/credential/":
            assert payload == {
                "data": {
                    "id": "datalogue-openai-compatible-lead-agent",
                    "name": "Datalogue env-default",
                    "type": "openai_credential",
                    "api_key": "sk-test",
                    "base_url": "https://example.test/v1",
                }
            }
            return httpx.Response(
                201,
                json={"credential_id": "datalogue-openai-compatible-lead-agent"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        from app.agentscope_service.client import AgentScopeServiceClient

        client = AgentScopeServiceClient(base_url="http://test/agentscope", http=http)
        credential_id = await client.upsert_openai_credential(
            credential_id="datalogue-openai-compatible-lead-agent",
            name="Datalogue env-default",
            api_key="sk-test",
            base_url="https://example.test/v1",
        )

    assert credential_id == "datalogue-openai-compatible-lead-agent"
    assert [(method, path) for method, path, _payload, _user_id in requests] == [
        ("POST", "/agentscope/credential/"),
    ]
    assert {user_id for *_rest, user_id in requests} == {"datalogue-agent-team"}


@pytest.mark.asyncio
async def test_agentscope_service_client_streams_session_sse_data_frames():
    requests: list[tuple[str, str, dict]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path, request.extensions.get("timeout") or {}))
        assert request.url.query == b"agent_id=agent-leader-1"
        assert request.headers["X-User-ID"] == "datalogue-agent-team"
        content = "\n".join(
            [
                "event: message",
                'data: {"type": "message", "payload": {"content": "hello"}}',
                "",
                ": keepalive",
                "",
                'data: {"type": "final", "payload": {"summary": "done"}}',
                "",
            ]
        )
        return httpx.Response(200, content=content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        from app.agentscope_service.client import AgentScopeServiceClient

        client = AgentScopeServiceClient(base_url="http://test/agentscope/", http=http)
        events = [
            event
            async for event in client.stream_session(
                session_id="session-1",
                agent_id="agent-leader-1",
            )
        ]

    assert [(method, path) for method, path, _timeout in requests] == [
        ("GET", "/agentscope/sessions/session-1/stream")
    ]
    assert requests[0][2]["read"] is None
    assert events == [
        {"type": "message", "payload": {"content": "hello"}},
        {"type": "final", "payload": {"summary": "done"}},
    ]


@pytest.mark.asyncio
async def test_agentscope_service_client_ensures_leader_agent_via_official_agent_api():
    requests: list[tuple[str, str, dict | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8")) if request.content else None
        requests.append((request.method, request.url.path, payload))
        assert request.headers["X-User-ID"] == "datalogue-agent-team"
        if request.method == "GET" and request.url.path == "/agentscope/agent/":
            return httpx.Response(200, json={"agents": [], "total": 0})
        if request.method == "POST" and request.url.path == "/agentscope/agent/":
            assert payload["name"] == "Datalogue Agent Team Leader"
            assert "TeamCreate" in payload["system_prompt"]
            return httpx.Response(201, json={"agent_id": "agent-created-1"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        from app.agentscope_service.client import AgentScopeServiceClient

        client = AgentScopeServiceClient(base_url="http://test/agentscope", http=http)
        agent_id = await client.ensure_agent(
            name="Datalogue Agent Team Leader",
            system_prompt="use TeamCreate",
        )

    assert agent_id == "agent-created-1"
    assert [(method, path) for method, path, _payload in requests] == [
        ("GET", "/agentscope/agent/"),
        ("POST", "/agentscope/agent/"),
    ]


@pytest.mark.asyncio
async def test_agentscope_service_client_reuses_existing_leader_agent():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "agents": [
                    {
                        "id": "agent-existing-1",
                        "data": {"name": "Datalogue Agent Team Leader"},
                    }
                ],
                "total": 1,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        from app.agentscope_service.client import AgentScopeServiceClient

        client = AgentScopeServiceClient(base_url="http://test/agentscope", http=http)
        agent_id = await client.ensure_agent(
            name="Datalogue Agent Team Leader",
            system_prompt="unused",
        )

    assert agent_id == "agent-existing-1"
