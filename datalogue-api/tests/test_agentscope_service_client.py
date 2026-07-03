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
    requests: list[tuple[str, str, dict]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        requests.append((request.method, request.url.path, payload))
        if request.method == "POST" and request.url.path == "/agentscope/session":
            assert payload == {
                "agent_id": "agentic_lead_agent",
                "name": "统计合同总金额",
                "chat_model_config": {"model": "gpt-test"},
            }
            return httpx.Response(200, json={"session_id": "session-1"})
        if request.method == "POST" and request.url.path == "/agentscope/chat":
            assert payload == {
                "agent_id": "agentic_lead_agent",
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
            agent_id="agentic_lead_agent",
            name="统计合同总金额",
            chat_model_config={"model": "gpt-test"},
        )
        await client.trigger_chat(
            agent_id="agentic_lead_agent",
            session_id=session_id,
            text="统计合同总金额",
        )

    assert [(method, path) for method, path, _payload in requests] == [
        ("POST", "/agentscope/session"),
        ("POST", "/agentscope/chat"),
    ]


@pytest.mark.asyncio
async def test_agentscope_service_client_streams_session_sse_data_frames():
    requests: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        assert request.url.query == b"agent_id=agentic_lead_agent"
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
                agent_id="agentic_lead_agent",
            )
        ]

    assert requests == [("GET", "/agentscope/session/session-1/stream")]
    assert events == [
        {"type": "message", "payload": {"content": "hello"}},
        {"type": "final", "payload": {"summary": "done"}},
    ]
