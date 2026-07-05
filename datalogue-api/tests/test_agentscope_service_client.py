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
async def test_agentscope_service_client_lists_credential_schemas():
    requests: list[tuple[str, str, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path, request.headers.get("X-User-ID")))
        if request.method == "GET" and request.url.path == "/agentscope/credential/schemas":
            return httpx.Response(
                200,
                json={
                    "openai_credential": {
                        "title": "OpenAI API",
                        "properties": {"api_key": {"type": "string"}},
                    }
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        from app.agentscope_service.client import AgentScopeServiceClient

        client = AgentScopeServiceClient(base_url="http://test/agentscope", http=http)
        schemas = await client.list_credential_schemas()

    assert schemas["openai_credential"]["title"] == "OpenAI API"
    assert requests == [("GET", "/agentscope/credential/schemas", "datalogue-agent-team")]


@pytest.mark.asyncio
async def test_agentscope_service_client_cruds_credentials_with_official_paths():
    requests: list[tuple[str, str, dict | None, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8")) if request.content else None
        requests.append((request.method, request.url.path, payload, request.headers.get("X-User-ID")))
        if request.method == "GET" and request.url.path == "/agentscope/credential/":
            return httpx.Response(200, json={"credentials": [{"id": "cred-1"}]})
        if request.method == "POST" and request.url.path == "/agentscope/credential/":
            assert payload == {"data": {"type": "openai_credential", "api_key": "sk-test"}}
            return httpx.Response(201, json={"credential_id": "cred-1"})
        if request.method == "PATCH" and request.url.path == "/agentscope/credential/cred-1":
            assert payload == {"data": {"name": "更新后的凭证"}}
            return httpx.Response(200, json={"credential_id": "cred-1", "updated": True})
        if request.method == "DELETE" and request.url.path == "/agentscope/credential/cred-1":
            return httpx.Response(200, json={"deleted": True})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        from app.agentscope_service.client import AgentScopeServiceClient

        client = AgentScopeServiceClient(base_url="http://test/agentscope", http=http)
        credentials = await client.list_credentials()
        created = await client.create_credential({"data": {"type": "openai_credential", "api_key": "sk-test"}})
        updated = await client.update_credential("cred-1", {"data": {"name": "更新后的凭证"}})
        deleted = await client.delete_credential("cred-1")

    assert credentials == [{"id": "cred-1"}]
    assert created == {"credential_id": "cred-1"}
    assert updated == {"credential_id": "cred-1", "updated": True}
    assert deleted == {"deleted": True}
    assert [(method, path) for method, path, _payload, _user_id in requests] == [
        ("GET", "/agentscope/credential/"),
        ("POST", "/agentscope/credential/"),
        ("PATCH", "/agentscope/credential/cred-1"),
        ("DELETE", "/agentscope/credential/cred-1"),
    ]
    assert {user_id for *_rest, user_id in requests} == {"datalogue-agent-team"}


@pytest.mark.asyncio
async def test_agentscope_service_client_lists_models_by_provider():
    requests: list[tuple[str, str, bytes, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (request.method, request.url.path, request.url.query, request.headers.get("X-User-ID"))
        )
        if request.method == "GET" and request.url.path == "/agentscope/model":
            assert request.url.query == b"provider=openai_credential"
            return httpx.Response(
                200,
                json={"models": [{"name": "gpt-4.1", "model_type": "chat"}]},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        from app.agentscope_service.client import AgentScopeServiceClient

        client = AgentScopeServiceClient(base_url="http://test/agentscope", http=http)
        models = await client.list_models(provider="openai_credential")

    assert models == [{"name": "gpt-4.1", "model_type": "chat"}]
    assert requests == [
        ("GET", "/agentscope/model", b"provider=openai_credential", "datalogue-agent-team")
    ]


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
