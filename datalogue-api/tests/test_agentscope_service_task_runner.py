# ============================================================
# File Name   : test_agentscope_service_task_runner.py
# Description:
#   Agentic Shell 默认 runner 的 AgentScope Service 委托测试。
#
# Responsibilities:
#   - 验证主链 runner 只通过 AgentScope Service bootstrap/client 执行。
#   - 验证固定入口 Agent 为 agentic_lead_agent，且事件会投影为 Datalogue envelope。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from types import SimpleNamespace

import pytest
from agentscope.message import UserMsg

from app.schemas.agentic_shell_task import AgenticShellTaskRequest


class FakeBootstrap:
    def __init__(self):
        self.closed = False

    async def ensure_static_agents(self):
        return {"agentic_lead_agent": "agent-lead-1"}

    async def aclose(self):
        self.closed = True


class FakeClient:
    def __init__(self):
        self.closed = False
        self.created_sessions = []
        self.triggered_chats = []
        self.stream_requests = []

    async def create_session(self, *, agent_id, name, chat_model_config=None):
        self.created_sessions.append(
            {
                "agent_id": agent_id,
                "name": name,
                "chat_model_config": chat_model_config,
            }
        )
        return "session-1"

    async def trigger_chat(self, *, agent_id, session_id, text):
        self.triggered_chats.append(
            {
                "agent_id": agent_id,
                "session_id": session_id,
                "text": text,
            }
        )
        return {"status": "started"}

    async def stream_session(self, session_id, *, agent_id=None):
        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {"type": "message", "payload": {"content": "合同总金额为 100 万元"}}
        yield {"type": "final", "payload": {"summary": "统计完成"}}

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_delegates_to_fixed_agent_service():
    from app.agentscope_service.runner import AgentScopeServiceTaskRunner

    bootstrap = FakeBootstrap()
    client = FakeClient()
    runner = AgentScopeServiceTaskRunner(
        base_url="http://testserver/agentscope",
        bootstrap=bootstrap,
        client=client,
    )
    request = AgenticShellTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="统计合同总金额",
        dataset_id=12,
        conversation_id=34,
    )
    task = SimpleNamespace(
        task_id="task-1",
        trace_id="trace-1",
        thread_id="thread-1",
        message_id="message-1",
        selected_agent="bi_agent",
    )

    events = [
        event
        async for event in runner.stream(
            request=request,
            task=task,
            user_msg=UserMsg(name="user", content=request.question),
        )
    ]

    assert client.created_sessions == [
        {
            "agent_id": "agent-lead-1",
            "name": "统计合同总金额",
            "chat_model_config": None,
        }
    ]
    assert client.triggered_chats[0]["agent_id"] == "agent-lead-1"
    assert client.triggered_chats[0]["session_id"] == "session-1"
    assert "统计合同总金额" in client.triggered_chats[0]["text"]
    assert '"dataset_id":12' in client.triggered_chats[0]["text"]
    assert client.stream_requests == [{"session_id": "session-1", "agent_id": "agent-lead-1"}]
    assert [event.event_type for event in events] == ["message.delta", "message.completed"]
    assert events[-1].payload["summary"] == "统计完成"
    assert bootstrap.closed is False
    assert client.closed is False
