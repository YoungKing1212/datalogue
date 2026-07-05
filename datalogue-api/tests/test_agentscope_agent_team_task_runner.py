# ============================================================
# File Name   : test_agentscope_agent_team_task_runner.py
# Description:
#   AgentScope Agent Team 默认 runner 的 AgentScope Service 委托测试。
#
# Responsibilities:
#   - 验证主链 runner 只通过 AgentScope Service leader session 执行。
#   - 验证 leader agent_id 来自 AgentScope 官方 /agent，worker 由官方 Team 工具创建。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from types import SimpleNamespace

import pytest
from agentscope.message import UserMsg

from app.schemas.agentscope_agent_team_task import AgentTeamTaskRequest


class FakeClient:
    def __init__(self):
        self.closed = False
        self.ensure_agent_requests = []
        self.upserted_credentials = []
        self.created_sessions = []
        self.triggered_chats = []
        self.stream_requests = []
        self.post_final_event_consumed = False

    async def ensure_agent(self, *, name, system_prompt):
        self.ensure_agent_requests.append({"name": name, "system_prompt": system_prompt})
        return "agent-leader-1"

    async def upsert_openai_credential(self, *, credential_id, name, api_key, base_url):
        self.upserted_credentials.append(
            {
                "credential_id": credential_id,
                "name": name,
                "api_key": api_key,
                "base_url": base_url,
            }
        )
        return credential_id

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
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "统计完成"}}
        self.post_final_event_consumed = True
        yield {"type": "message", "payload": {"content": "不应消费下一轮长连接事件"}}

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_delegates_to_agent_team_leader_session():
    from app.core.config import Settings
    from app.agentscope_service.runner import AgentScopeServiceTaskRunner

    client = FakeClient()
    runner = AgentScopeServiceTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(
            OPENAI_API_KEY="sk-test",
            OPENAI_BASE_URL="https://example.test/v1",
            LLM_MODEL="test-model",
        ),
        client=client,
    )
    request = AgentTeamTaskRequest(
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
            "agent_id": "agent-leader-1",
            "name": "统计合同总金额",
            "chat_model_config": {
                "type": "openai_credential",
                "credential_id": "datalogue-openai-compatible-lead-agent",
                "model": "test-model",
                "parameters": {"thinking_enable": False},
            },
        }
    ]
    assert client.upserted_credentials == [
        {
            "credential_id": "datalogue-openai-compatible-lead-agent",
            "name": "Datalogue env-default",
            "api_key": "sk-test",
            "base_url": "https://example.test/v1",
        }
    ]
    assert len(client.ensure_agent_requests) == 1
    assert client.ensure_agent_requests[0]["name"] == "Datalogue Agent Team Leader"
    assert "AgentCreate" in client.ensure_agent_requests[0]["system_prompt"]
    assert client.triggered_chats[0]["agent_id"] == "agent-leader-1"
    assert client.triggered_chats[0]["session_id"] == "session-1"
    assert "统计合同总金额" in client.triggered_chats[0]["text"]
    assert '"dataset_id":12' in client.triggered_chats[0]["text"]
    assert client.stream_requests == [{"session_id": "session-1", "agent_id": "agent-leader-1"}]
    assert [event.event_type for event in events] == ["message.delta", "message.completed"]
    assert events[-1].payload["summary"] == "统计完成"
    assert client.post_final_event_consumed is False
    assert client.closed is False


class TeamDelegationFakeClient(FakeClient):
    async def stream_session(self, session_id, *, agent_id=None):
        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {
            "type": "ToolCallStartEvent",
            "tool_call_name": "AgentCreate",
            "payload": {"tool_call_name": "AgentCreate"},
        }
        yield {"type": "message", "payload": {"content": "已创建 BI worker，正在等待 worker 返回结果。"}}
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "等待 worker 返回结果"}}
        yield {"type": "message", "payload": {"content": "查询完成：共找到 8 条日志。"}}
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "查询完成：共找到 8 条日志。"}}
        self.post_final_event_consumed = True
        yield {"type": "message", "payload": {"content": "不应消费最终完成后的长连接事件"}}


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_waits_for_worker_report_after_agent_create():
    from app.core.config import Settings
    from app.agentscope_service.runner import AgentScopeServiceTaskRunner

    client = TeamDelegationFakeClient()
    runner = AgentScopeServiceTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(
            OPENAI_API_KEY="sk-test",
            OPENAI_BASE_URL="https://example.test/v1",
            LLM_MODEL="test-model",
        ),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询杨凯2025年日志",
        dataset_id=12,
    )
    task = SimpleNamespace(
        task_id="task-1",
        trace_id="trace-1",
        thread_id="thread-1",
        message_id="message-1",
        selected_agent="agent_team_leader",
    )

    events = [
        event
        async for event in runner.stream(
            request=request,
            task=task,
            user_msg=UserMsg(name="user", content=request.question),
        )
    ]

    assert [event.event_type for event in events] == [
        "tool.result",
        "message.delta",
        "message.delta",
        "message.completed",
    ]
    assert events[-1].payload["summary"] == "查询完成：共找到 8 条日志。"
    assert client.post_final_event_consumed is False
