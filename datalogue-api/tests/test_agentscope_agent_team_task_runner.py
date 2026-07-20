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

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from agentscope.message import UserMsg

from app.core.schemas.agentscope_agent_team_task import AgentTeamTaskRequest
from app.domains.agent_team import progress_bridge


class FakeClient:
    def __init__(self):
        self.closed = False
        self.credentials = []
        self.ensure_agent_requests = []
        self.upserted_credentials = []
        self.created_sessions = []
        self.triggered_chats = []
        self.stream_requests = []
        self.post_final_event_consumed = False

    async def ensure_agent(self, *, name, system_prompt):
        self.ensure_agent_requests.append({"name": name, "system_prompt": system_prompt})
        return "agent-leader-1"

    async def list_credentials(self):
        return self.credentials

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

    async def upsert_credential(self, *, credential_id, name, credential_type, api_key, base_url):
        self.upserted_credentials.append(
            {
                "credential_id": credential_id,
                "name": name,
                "credential_type": credential_type,
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


def test_progress_bridge_uses_redis_when_publisher_has_no_local_subscriber(monkeypatch):
    published = []

    class FakeRedisClient:
        def publish(self, channel, payload):
            published.append((channel, payload))
            return 1

        def close(self):
            return None

    class FakeSyncRedis:
        @staticmethod
        def from_url(*_args, **_kwargs):
            return FakeRedisClient()

    monkeypatch.setattr(progress_bridge, "_redis_url", lambda: "redis://example/0")
    monkeypatch.setattr(progress_bridge, "SyncRedis", FakeSyncRedis)

    delivered = progress_bridge.publish_agent_event(
        leader_session_id="session-cross-process",
        event_type="agent.progress",
        payload={"summary": "跨进程进度"},
    )

    assert delivered == 1
    assert published[0][0].endswith("session-cross-process")
    assert "跨进程进度" in published[0][1]


@pytest.mark.asyncio
async def test_progress_bridge_wakes_subscription_from_worker_thread(monkeypatch):
    monkeypatch.setattr(progress_bridge, "_redis_url", lambda: None)

    async with progress_bridge.agent_progress_subscription(
        leader_session_id="session-thread-worker"
    ) as queue:
        delivered = await asyncio.to_thread(
            progress_bridge.publish_agent_event,
            leader_session_id="session-thread-worker",
            event_type="agent.progress",
            payload={"summary": "线程工具已完成"},
        )
        event = await asyncio.wait_for(queue.get(), timeout=1)

    assert delivered == 1
    assert event["payload"]["summary"] == "线程工具已完成"


class AgentNotFoundThenRecoveredClient(FakeClient):
    def __init__(self):
        super().__init__()
        self._ensure_count = 0

    async def ensure_agent(self, *, name, system_prompt):
        self.ensure_agent_requests.append({"name": name, "system_prompt": system_prompt})
        self._ensure_count += 1
        return f"agent-leader-{self._ensure_count}"

    async def create_session(self, *, agent_id, name, chat_model_config=None):
        self.created_sessions.append(
            {
                "agent_id": agent_id,
                "name": name,
                "chat_model_config": chat_model_config,
            }
        )
        if agent_id == "agent-leader-1":
            request = httpx.Request("POST", "http://testserver/agentscope/sessions/")
            response = httpx.Response(
                404, json={"detail": "Agent 'agent-leader-1' not found."}, request=request
            )
            response.raise_for_status()
        return "session-1"


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_uses_agentscope_model_selection_without_local_config():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = FakeClient()
    client.credentials = [
        {
            "id": "openai_credential:prod-main",
            "data": {
                "id": "openai_credential:prod-main",
                "type": "openai_credential",
            },
        }
    ]
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(
            OPENAI_API_KEY=None,
            OPENAI_BASE_URL="https://example.test/v1",
            LLM_MODEL="fallback-model",
        ),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="用 AgentScope 模型资源查询销售趋势",
        dataset_id=12,
        model_credential_id="openai_credential:prod-main",
        model_name="gpt-4.1-mini",
        model_parameters={
            "thinking_enable": True,
            "temperature": 0,
            "api_key": "must-not-pass",
            "credential_id": "must-not-override",
        },
    )
    task = SimpleNamespace(
        task_id="task-1",
        trace_id="trace-1",
        thread_id="thread-1",
        message_id="message-1",
        selected_agent="agent_team_leader",
    )

    [
        event
        async for event in runner.stream(
            request=request,
            task=task,
            user_msg=UserMsg(name="user", content=request.question),
        )
    ]

    assert client.upserted_credentials == []
    assert client.created_sessions[0]["chat_model_config"] == {
        "type": "openai_credential",
        "credential_id": "openai_credential:prod-main",
        "model": "gpt-4.1-mini",
        "parameters": {
            "thinking_enable": True,
            "temperature": 0,
        },
    }
    assert "model_credential_id" in client.triggered_chats[0]["text"]
    assert ("legacy_model" + "_config_id") not in client.triggered_chats[0]["text"]


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_uses_selected_native_credential_type():
    """显式选择 DeepSeek 时必须将真实 credential type 透传给 AgentScope Service。"""

    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = FakeClient()
    client.credentials = [
        {
            "id": "deepseek-prod-main",
            "data": {
                "id": "deepseek-prod-main",
                "type": "deepseek_credential",
                "name": "DeepSeek · deepseek-v4-pro",
            },
        }
    ]
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(OPENAI_API_KEY=None),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询销售额",
        model_credential_id="deepseek-prod-main",
        model_name="deepseek-v4-pro",
    )
    task = SimpleNamespace(
        task_id="task-1",
        trace_id="trace-1",
        thread_id="thread-1",
        message_id="message-1",
        selected_agent="agent_team_leader",
    )

    [
        event
        async for event in runner.stream(
            request=request,
            task=task,
            user_msg=UserMsg(name="user", content=request.question),
        )
    ]

    assert client.created_sessions[0]["chat_model_config"] == {
        "type": "deepseek_credential",
        "credential_id": "deepseek-prod-main",
        "model": "deepseek-v4-pro",
        "parameters": {},
    }


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_refreshes_default_leader_when_session_agent_missing():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = AgentNotFoundThenRecoveredClient()
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(OPENAI_API_KEY="sk-test"),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询销售额",
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

    assert len(client.ensure_agent_requests) == 2
    assert [item["agent_id"] for item in client.created_sessions] == [
        "agent-leader-1",
        "agent-leader-2",
    ]
    assert client.triggered_chats[0]["agent_id"] == "agent-leader-2"
    assert client.stream_requests[0]["agent_id"] == "agent-leader-2"
    assert events


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_default_model_comes_from_agentscope_credential():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = FakeClient()
    client.credentials = [
        {
            "id": "datalogue-openai-compatible-lead-agent",
            "data": {
                "id": "datalogue-openai-compatible-lead-agent",
                "name": "Datalogue DeepSeek · deepseek-v4-pro",
                "type": "openai_credential",
                "base_url": "https://api.deepseek.com/v1",
            },
        }
    ]
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(
            OPENAI_API_KEY=None,
            OPENAI_BASE_URL="https://api.minimaxi.com/v1",
            LLM_MODEL="MiniMax-M2.7",
        ),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询杨凯2025年工作日志",
    )
    task = SimpleNamespace(
        task_id="task-1",
        trace_id="trace-1",
        thread_id="thread-1",
        message_id="message-1",
        selected_agent="agent_team_leader",
    )

    [
        event
        async for event in runner.stream(
            request=request,
            task=task,
            user_msg=UserMsg(name="user", content=request.question),
        )
    ]

    assert client.created_sessions[0]["chat_model_config"] == {
        "type": "openai_credential",
        "credential_id": "datalogue-openai-compatible-lead-agent",
        "model": "deepseek-v4-pro",
        "parameters": {"thinking_enable": False},
    }


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_default_model_comes_from_database_config(db_session):
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner
    from app.core.models.llm import LLMModelConfig

    config = LLMModelConfig(
        name="设置页默认模型",
        provider="openai-compatible",
        base_url="https://db.example/v1",
        model="db-default-model",
        status="active",
        request_timeout_seconds=45,
        thinking_enabled=True,
    )
    config.credential_id = "db-default-credential"
    config.credential_type = "openai_credential"
    db_session.add(config)
    db_session.commit()
    db_session.refresh(config)
    credential_id = config.credential_id

    client = FakeClient()
    client.credentials = [
        {"id": credential_id, "data": {"id": credential_id, "type": "openai_credential"}}
    ]
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        db=db_session,
        settings=Settings(OPENAI_API_KEY=None, LLM_MODEL="env-should-not-win"),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询销售额",
    )
    task = SimpleNamespace(
        task_id="task-1",
        trace_id="trace-1",
        thread_id="thread-1",
        message_id="message-1",
        selected_agent="agent_team_leader",
    )

    [
        event
        async for event in runner.stream(
            request=request,
            task=task,
            user_msg=UserMsg(name="user", content=request.question),
        )
    ]

    assert client.upserted_credentials == []
    assert client.created_sessions[0]["chat_model_config"] == {
        "type": "openai_credential",
        "credential_id": credential_id,
        "model": "db-default-model",
        "parameters": {"thinking_enable": True},
    }


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_default_model_uses_database_credential_link(
    db_session,
):
    """默认路径只使用数据库保存的原生 DeepSeek credential 关联，不再按名称匹配。"""

    from app.core.config import Settings
    from app.core.models.llm import LLMModelConfig
    from app.runtime.engine.runner import AgentTeamTaskRunner

    config = LLMModelConfig(
        name="DeepSeek · deepseek-v4-pro",
        provider="deepseek",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-v4-pro",
        status="active",
        request_timeout_seconds=45,
        thinking_enabled=True,
        credential_id="native-deepseek-credential",
        credential_type="deepseek_credential",
    )
    db_session.add(config)
    db_session.commit()

    client = FakeClient()
    client.credentials = [
        {
            "id": "native-deepseek-credential",
            "data": {
                "id": "native-deepseek-credential",
                "name": config.name,
                "type": "deepseek_credential",
            },
        }
    ]
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        db=db_session,
        settings=Settings(OPENAI_API_KEY=None, LLM_MODEL="env-should-not-win"),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询销售额",
    )
    task = SimpleNamespace(
        task_id="task-1",
        trace_id="trace-1",
        thread_id="thread-1",
        message_id="message-1",
        selected_agent="agent_team_leader",
    )

    [
        event
        async for event in runner.stream(
            request=request,
            task=task,
            user_msg=UserMsg(name="user", content=request.question),
        )
    ]

    assert client.created_sessions[0]["chat_model_config"] == {
        "type": "deepseek_credential",
        "credential_id": "native-deepseek-credential",
        "model": "deepseek-v4-pro",
        "parameters": {"thinking_enable": True},
    }


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_restores_missing_database_credential_from_local_key(
    db_session,
):
    """运行副本缺失时，必须以本地 AES-GCM 密钥补建原生 DeepSeek credential。"""

    from app.core.config import Settings
    from app.core.models.llm import LLMModelConfig
    from app.core.security import encrypt_password
    from app.runtime.engine.runner import AgentTeamTaskRunner

    config = LLMModelConfig(
        name="DeepSeek · deepseek-v4-pro",
        provider="deepseek",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-v4-pro",
        status="active",
        credential_id="missing-deepseek-credential",
        credential_type="deepseek_credential",
        api_key_enc=encrypt_password("sk-local-deepseek"),
    )
    db_session.add(config)
    db_session.commit()

    client = FakeClient()
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        db=db_session,
        settings=Settings(OPENAI_API_KEY=None),
        client=client,
    )
    request = AgentTeamTaskRequest(task_source="chat", task_type="bi_query", question="查询销售额")
    task = SimpleNamespace(
        task_id="task-restore",
        trace_id="trace-restore",
        thread_id="thread-restore",
        message_id="message-restore",
        selected_agent="agent_team_leader",
    )

    [
        event
        async for event in runner.stream(
            request=request,
            task=task,
            user_msg=UserMsg(name="user", content=request.question),
        )
    ]

    assert client.upserted_credentials == [
        {
            "credential_id": "missing-deepseek-credential",
            "name": "DeepSeek · deepseek-v4-pro",
            "credential_type": "deepseek_credential",
            "api_key": "sk-local-deepseek",
            "base_url": "https://api.deepseek.com/v1",
        }
    ]
    assert client.created_sessions[0]["chat_model_config"] == {
        "type": "deepseek_credential",
        "credential_id": "missing-deepseek-credential",
        "model": "deepseek-v4-pro",
        "parameters": {"thinking_enable": False},
    }


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_upserts_missing_default_credential_from_settings():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = FakeClient()
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(
            OPENAI_API_KEY="sk-default",
            OPENAI_BASE_URL="https://example.test/v1",
            LLM_MODEL="qwen-debug",
        ),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询销售额",
    )
    task = SimpleNamespace(
        task_id="task-1",
        trace_id="trace-1",
        thread_id="thread-1",
        message_id="message-1",
        selected_agent="agent_team_leader",
    )

    [
        event
        async for event in runner.stream(
            request=request,
            task=task,
            user_msg=UserMsg(name="user", content=request.question),
        )
    ]

    assert client.upserted_credentials == [
        {
            "credential_id": "datalogue-openai-compatible-lead-agent",
            "name": "Datalogue 默认模型 · qwen-debug",
            "api_key": "sk-default",
            "base_url": "https://example.test/v1",
        }
    ]
    assert client.created_sessions[0]["chat_model_config"] == {
        "type": "openai_credential",
        "credential_id": "datalogue-openai-compatible-lead-agent",
        "model": "qwen-debug",
        "parameters": {"thinking_enable": False},
    }


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_reports_missing_default_credential_without_api_key():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = FakeClient()
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(OPENAI_API_KEY=None),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询销售额",
    )
    task = SimpleNamespace(
        task_id="task-1",
        trace_id="trace-1",
        thread_id="thread-1",
        message_id="message-1",
        selected_agent="agent_team_leader",
    )

    with pytest.raises(ValueError, match="AGENTSCOPE_DEFAULT_CREDENTIAL_NOT_CONFIGURED"):
        [
            event
            async for event in runner.stream(
                request=request,
                task=task,
                user_msg=UserMsg(name="user", content=request.question),
            )
        ]


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_delegates_to_agent_team_leader_session():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = FakeClient()
    runner = AgentTeamTaskRunner(
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
        selected_agent="bi_worker",
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
            "name": "Datalogue 默认模型 · test-model",
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


@pytest.mark.asyncio
async def test_worker_progress_is_isolated_by_leader_session():
    """同一 AgentScope user 下的并发任务不能互相收到 Worker 进度。"""

    from app.domains.agent_team.progress_bridge import (
        agent_progress_subscription,
        publish_agent_progress,
    )

    async with agent_progress_subscription(leader_session_id="leader-a") as queue_a:
        async with agent_progress_subscription(leader_session_id="leader-b") as queue_b:
            delivered = publish_agent_progress(
                leader_session_id="leader-a",
                payload={"summary": "仅 A 可见"},
            )

            assert delivered == 1
            assert (await queue_a.get())["payload"]["summary"] == "仅 A 可见"
            assert queue_b.empty()


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_treats_selected_dataset_as_confirmed():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = FakeClient()
    runner = AgentTeamTaskRunner(
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
        question="查询杨凯2025年工作日志",
        dataset_id=10,
        clarification_response={
            "selected_dataset_id": 10,
            "selected_text": "生产经营管理系统日志数据集",
            "original_question": "查询杨凯2025年工作日志",
        },
    )
    task = SimpleNamespace(
        task_id="task-1",
        trace_id="trace-1",
        thread_id="thread-1",
        message_id="message-1",
        selected_agent="agent_team_leader",
    )

    [
        event
        async for event in runner.stream(
            request=request,
            task=task,
            user_msg=UserMsg(name="user", content=request.question),
        )
    ]

    trigger_text = client.triggered_chats[0]["text"]
    assert "confirmed_question" in trigger_text
    assert "datalogue_prepare_query_context" in trigger_text
    assert "datalogue_execute_query_plan_bundle" in trigger_text
    assert "dataset_id=10" in trigger_text
    assert "用户问题=查询杨凯2025年工作日志" in trigger_text
    assert "clarification_response" not in trigger_text


class TeamDelegationFakeClient(FakeClient):
    async def stream_session(self, session_id, *, agent_id=None):
        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {
            "type": "ToolCallStartEvent",
            "tool_call_name": "AgentCreate",
            "payload": {"tool_call_name": "AgentCreate"},
        }
        yield {
            "type": "message",
            "payload": {"content": "已创建 BI worker，正在等待 worker 返回结果。"},
        }
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "等待 worker 返回结果"}}
        yield {"type": "message", "payload": {"content": "查询完成：共找到 8 条日志。"}}
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "查询完成：共找到 8 条日志。"}}
        self.post_final_event_consumed = True
        yield {"type": "message", "payload": {"content": "不应消费最终完成后的长连接事件"}}


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_waits_for_worker_report_after_agent_create():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = TeamDelegationFakeClient()
    runner = AgentTeamTaskRunner(
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


class WorkerProgressFakeClient(TeamDelegationFakeClient):
    user_id = "datalogue-agent-team"

    async def stream_session(self, session_id, *, agent_id=None):
        from app.domains.agent_team.progress_bridge import publish_agent_progress

        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {
            "type": "ToolCallStartEvent",
            "tool_call_name": "AgentCreate",
            "payload": {"tool_call_name": "AgentCreate"},
        }
        publish_agent_progress(
            leader_session_id=session_id,
            payload={
                "agent_role": "worker",
                "agent_name": "bi-worker",
                "phase": "tool",
                "status": "running",
                "title": "候选数据集筛选",
                "summary": "BI Worker 正在筛选候选数据集。",
                "worker_agent_id": "worker-bi-1",
                "worker_session_id": "session-bi-1",
                "sql": "select * from hidden_table",
            },
        )
        yield {
            "type": "message",
            "payload": {"content": "已创建 BI worker，正在等待 worker 返回结果。"},
        }
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "等待 worker 返回结果"}}
        yield {"type": "message", "payload": {"content": "查询完成：共找到 8 条日志。"}}
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "查询完成：共找到 8 条日志。"}}


class WorkerPendingToolCallFakeClient(TeamDelegationFakeClient):
    async def stream_session(self, session_id, *, agent_id=None):
        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {
            "event_type": "message.completed",
            "payload": {
                "summary": "BI Worker 准备读取数据集能力摘要。",
                "tool_calls": [
                    {
                        "id": "call-l0",
                        "name": "datalogue_describe_dataset_capability",
                        "state": "pending",
                    }
                ],
            },
        }
        yield {
            "type": "ToolCallStartEvent",
            "tool_call_name": "datalogue_describe_dataset_capability",
            "payload": {"tool_call_name": "datalogue_describe_dataset_capability"},
        }
        yield {
            "type": "ToolResultEndEvent",
            "tool_call_name": "datalogue_describe_dataset_capability",
            "payload": {"summary": "L0 已完成"},
        }
        yield {"type": "message", "payload": {"content": "查询完成：共找到 8 条日志。"}}
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "查询完成：共找到 8 条日志。"}}
        self.post_final_event_consumed = True
        yield {"type": "message", "payload": {"content": "不应消费最终完成后的长连接事件"}}


class WorkerCandidateFallbackFakeClient(TeamDelegationFakeClient):
    user_id = "datalogue-agent-team"

    async def stream_session(self, session_id, *, agent_id=None):
        from app.domains.agent_team.progress_bridge import publish_agent_event

        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {
            "type": "ToolCallStartEvent",
            "tool_call_name": "AgentCreate",
            "payload": {"tool_call_name": "AgentCreate"},
        }
        publish_agent_event(
            leader_session_id=session_id,
            event_type="message.completed",
            payload={
                "datalogue_event_type": "dataset_candidates",
                "summary": "BI worker 已筛选候选数据集，请用户确认。",
                "route_decision": {
                    "decision": "ambiguous",
                    "candidates": [
                        {
                            "dataset_id": 10,
                            "dataset_name": "生产经营管理系统日志数据集",
                            "score": 2,
                            "reason": "名称或描述与「工作日志」匹配",
                        }
                    ],
                },
                "clarification": {"kind": "dataset_choice"},
                "requires_user_confirmation": True,
            },
        )
        yield {
            "event_type": "ReplyEndEvent",
            "payload": {
                "summary": "用户想要查询杨凯2025年工作日志，我需要创建团队和 BI worker 处理。"
            },
        }
        self.post_final_event_consumed = True
        yield {"type": "message", "payload": {"content": "不应消费候选确认后的长连接事件"}}


class ConfirmedDatasetMissingArtifactFakeClient(TeamDelegationFakeClient):
    async def stream_session(self, session_id, *, agent_id=None):
        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {
            "type": "ToolCallStartEvent",
            "tool_call_name": "AgentCreate",
            "payload": {"tool_call_name": "AgentCreate"},
        }
        yield {
            "type": "message",
            "payload": {"content": "已创建 BI worker，正在等待 worker 返回结果。"},
        }
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "等待 worker 返回结果"}}
        yield {"type": "message", "payload": {"content": "查询未完成，未生成可展示结果。"}}
        yield {
            "event_type": "ReplyEndEvent",
            "payload": {"summary": "查询未完成，未生成可展示结果。"},
        }
        self.post_final_event_consumed = True
        yield {"type": "message", "payload": {"content": "不应消费兜底完成后的长连接事件"}}


class MandatoryReportFakeClient(FakeClient):
    async def stream_session(self, session_id, *, agent_id=None):
        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {
            "event_type": "artifact.created",
            "payload": {
                "datalogue_event_type": "dataset_query_result",
                "summary": "查询结果已生成。",
                "artifact_ref": "artifact:query-runner-1",
            },
        }
        yield {
            "event_type": "ReplyEndEvent",
            "payload": {"summary": "查询已经完成。"},
        }
        yield {
            "event_type": "report_worker_result",
            "payload": {
                "datalogue_event_type": "report_worker_result",
                "status": "completed",
                "source_artifact_ref": "artifact:query-runner-1",
                "report_ref": "artifact:report:runner-1",
                "report_markdown": "# 报告\n\n查询结果正常。",
                "summary": "报告已生成。",
                "report_worker_agent_id": "report-agent-runner-1",
                "report_worker_session_id": "report-session-runner-1",
                "report_attempts": 1,
            },
        }
        self.post_final_event_consumed = True
        yield {"type": "message", "payload": {"content": "不应消费报告完成后的事件"}}


class MissingMandatoryReportFakeClient(FakeClient):
    async def stream_session(self, session_id, *, agent_id=None):
        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {
            "event_type": "artifact.created",
            "payload": {
                "datalogue_event_type": "dataset_query_result",
                "summary": "查询结果已生成。",
                "artifact_ref": "artifact:query-runner-failed",
            },
        }
        for _ in range(3):
            yield {
                "event_type": "ReplyEndEvent",
                "payload": {"summary": "跳过报告并完成任务。"},
            }


class ReportArrivesAfterLeaderEofFakeClient(FakeClient):
    async def stream_session(self, session_id, *, agent_id=None):
        from app.domains.agent_team.progress_bridge import publish_agent_event

        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {
            "event_type": "artifact.created",
            "payload": {
                "datalogue_event_type": "dataset_query_result",
                "artifact_ref": "artifact:query-after-eof",
                "summary": "查询结果已生成。",
            },
        }

        async def publish_after_eof():
            await asyncio.sleep(0.01)
            publish_agent_event(
                leader_session_id=session_id,
                event_type="report_worker_result",
                payload={
                    "datalogue_event_type": "report_worker_result",
                    "status": "completed",
                    "source_artifact_ref": "artifact:query-after-eof",
                    "report_ref": "artifact:report:after-eof",
                    "report_markdown": "# 报告\n\n跨进程事件已收到。",
                    "summary": "报告已生成。",
                    "report_worker_agent_id": "report-agent-after-eof",
                    "report_worker_session_id": "report-session-after-eof",
                    "report_attempts": 1,
                },
            )

        asyncio.create_task(publish_after_eof())


class ReportFailureThenSuccessFakeClient(FakeClient):
    async def stream_session(self, session_id, *, agent_id=None):
        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {
            "event_type": "artifact.created",
            "payload": {
                "datalogue_event_type": "dataset_query_result",
                "artifact_ref": "artifact:query-report-retry",
                "summary": "查询结果已生成。",
            },
        }
        yield {
            "event_type": "report_worker_result",
            "payload": {
                "datalogue_event_type": "report_worker_result",
                "status": "failed",
                "source_artifact_ref": "artifact:query-report-retry",
                "code": "REPORT_TRUNCATION_NOTICE_REQUIRED",
            },
        }
        yield {
            "event_type": "report_worker_result",
            "payload": {
                "datalogue_event_type": "report_worker_result",
                "status": "completed",
                "source_artifact_ref": "artifact:query-report-retry",
                "report_ref": "artifact:report:retry-success",
                "report_markdown": "# 报告\n\n已补充限制说明。",
                "summary": "报告重试成功。",
                "report_worker_agent_id": "report-agent-retry",
                "report_worker_session_id": "report-session-retry",
                "report_attempts": 2,
            },
        }


@pytest.mark.asyncio
async def test_runner_requires_structured_report_result_before_final():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = MandatoryReportFakeClient()
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(
            OPENAI_API_KEY="sk-test",
            OPENAI_BASE_URL="https://example.test/v1",
            LLM_MODEL="test-model",
            DATALOGUE_REPORT_WORKER_ENABLED=True,
        ),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询并整理报告",
        dataset_id=10,
    )
    task = SimpleNamespace(
        task_id="task-report-gate",
        trace_id="trace-report-gate",
        thread_id="thread-report-gate",
        message_id="message-report-gate",
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
        "artifact.created",
        "agent.progress",
        "message.completed",
    ]
    assert events[-1].payload["datalogue_event_type"] == "report_worker_result"
    assert len(client.triggered_chats) == 2
    assert "禁止重新执行 BI" in client.triggered_chats[-1]["text"]
    assert "datalogue_submit_report" in client.triggered_chats[-1]["text"]
    assert client.post_final_event_consumed is False


@pytest.mark.asyncio
async def test_runner_corrects_at_most_twice_and_never_reexecutes_bi():
    from app.core.config import Settings
    from app.domains.agent_team.report_execution import (
        ReportWorkerRequiredNotCompletedError,
    )
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = MissingMandatoryReportFakeClient()
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(
            OPENAI_API_KEY="sk-test",
            OPENAI_BASE_URL="https://example.test/v1",
            LLM_MODEL="test-model",
            DATALOGUE_REPORT_WORKER_ENABLED=True,
        ),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询但跳过报告",
        dataset_id=10,
    )
    task = SimpleNamespace(
        task_id="task-report-gate-failed",
        trace_id="trace-report-gate-failed",
        thread_id="thread-report-gate-failed",
        message_id="message-report-gate-failed",
        selected_agent="agent_team_leader",
    )
    emitted = []

    with pytest.raises(ReportWorkerRequiredNotCompletedError):
        async for event in runner.stream(
            request=request,
            task=task,
            user_msg=UserMsg(name="user", content=request.question),
        ):
            emitted.append(event)

    assert [event.event_type for event in emitted].count("artifact.created") == 1
    assert all(event.event_type != "message.completed" for event in emitted)
    assert len(client.triggered_chats) == 3  # 首次任务 + 两次纠偏
    correction_texts = [item["text"] for item in client.triggered_chats[1:]]
    assert all("禁止重新执行 BI" in text for text in correction_texts)


@pytest.mark.asyncio
async def test_runner_waits_for_report_progress_after_leader_stream_eof():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = ReportArrivesAfterLeaderEofFakeClient()
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(
            OPENAI_API_KEY="sk-test",
            OPENAI_BASE_URL="https://example.test/v1",
            LLM_MODEL="test-model",
            DATALOGUE_REPORT_WORKER_ENABLED=True,
        ),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询并等待跨进程报告",
        dataset_id=10,
    )
    task = SimpleNamespace(
        task_id="task-report-after-eof",
        trace_id="trace-report-after-eof",
        thread_id="thread-report-after-eof",
        message_id="message-report-after-eof",
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
        "artifact.created",
        "message.completed",
    ]
    assert events[-1].payload["report_ref"] == "artifact:report:after-eof"


@pytest.mark.asyncio
async def test_runner_corrects_failed_report_submission_without_rerunning_bi():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = ReportFailureThenSuccessFakeClient()
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(
            OPENAI_API_KEY="sk-test",
            OPENAI_BASE_URL="https://example.test/v1",
            LLM_MODEL="test-model",
            DATALOGUE_REPORT_WORKER_ENABLED=True,
        ),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询并在报告失败后纠偏",
        dataset_id=10,
    )
    task = SimpleNamespace(
        task_id="task-report-retry",
        trace_id="trace-report-retry",
        thread_id="thread-report-retry",
        message_id="message-report-retry",
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
        "artifact.created",
        "agent.progress",
        "message.completed",
    ]
    assert events[-1].payload["report_attempts"] == 2
    assert len(client.triggered_chats) == 2
    assert "禁止重新执行 BI" in client.triggered_chats[-1]["text"]


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_merges_worker_progress_before_final():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = WorkerProgressFakeClient()
    runner = AgentTeamTaskRunner(
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
        task_id="task-progress",
        trace_id="trace-progress",
        thread_id="thread-progress",
        message_id="message-progress",
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

    event_types = [event.event_type for event in events]
    assert "agent.progress" in event_types
    assert event_types.index("agent.progress") < event_types.index("message.completed")
    progress = next(event for event in events if event.event_type == "agent.progress")
    assert progress.payload == {
        "agent_role": "worker",
        "agent_name": "bi-worker",
        "phase": "tool",
        "status": "running",
        "title": "候选数据集筛选",
        "summary": "BI Worker 正在筛选候选数据集。",
        "worker_agent_id": "worker-bi-1",
        "worker_session_id": "session-bi-1",
    }


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_uses_worker_candidate_fallback_as_final():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = WorkerCandidateFallbackFakeClient()
    runner = AgentTeamTaskRunner(
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
    )
    task = SimpleNamespace(
        task_id="task-candidates",
        trace_id="trace-candidates",
        thread_id="thread-candidates",
        message_id="message-candidates",
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

    assert [event.event_type for event in events] == ["tool.result", "message.completed"]
    assert events[-1].payload["datalogue_event_type"] == "dataset_candidates"
    assert events[-1].payload["requires_user_confirmation"] is True
    assert events[-1].payload["route_decision"]["candidates"][0]["dataset_id"] == 10
    assert client.post_final_event_consumed is False


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_keeps_stream_open_for_pending_worker_tool_call():
    from app.core.config import Settings
    from app.runtime.engine.runner import AgentTeamTaskRunner

    client = WorkerPendingToolCallFakeClient()
    runner = AgentTeamTaskRunner(
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
        dataset_id=10,
    )
    task = SimpleNamespace(
        task_id="task-pending-tool",
        trace_id="trace-pending-tool",
        thread_id="thread-pending-tool",
        message_id="message-pending-tool",
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

    event_types = [event.event_type for event in events]
    assert event_types == ["tool.result", "tool.result", "message.delta", "message.completed"]
    assert events[-1].payload["summary"] == "查询完成：共找到 8 条日志。"
    assert client.post_final_event_consumed is False


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_falls_back_when_confirmed_dataset_has_no_artifact(
    monkeypatch,
):
    from app.core.config import Settings
    from app.runtime.engine import runner as runner_module
    from app.runtime.engine.runner import AgentTeamTaskRunner

    async def fake_execute_dataset_query_for_agent_team_direct_fallback(**kwargs):
        assert kwargs["dataset_id"] == 10
        assert kwargs["confirmed_question"] == "查询杨凯2025年工作日志"
        return SimpleNamespace(
            to_tool_payload=lambda: {
                "datalogue_event_type": "dataset_query_result",
                "summary": "查询已完成，结果已生成 artifact_ref=artifact:test，共 100 行、48 列。",
                "answer_summary": "查询已完成，结果已生成 artifact_ref=artifact:test，共 100 行、48 列。",
                "artifact_ref": "artifact:test",
                "result_ref": "artifact:test",
                "checkpoint_ref": None,
                "row_count": 100,
                "column_count": 48,
                "artifact_card": {
                    "artifact_type": "bi_answer",
                    "title": "查询结果",
                    "status": "completed",
                    "summary_for_chat": "查询已完成，结果已生成 artifact_ref=artifact:test，共 100 行、48 列。",
                    "preview_payload": {"row_count": 100, "column_count": 48},
                    "primary_ref": {
                        "ref_id": "artifact:test",
                        "ref_type": "result",
                        "label": "查询结果",
                    },
                    "related_refs": [],
                    "actions": [
                        {
                            "action_type": "view",
                            "label": "查看详情",
                            "ref": "artifact:test",
                            "disabled": False,
                        }
                    ],
                },
            }
        )

    monkeypatch.setattr(
        runner_module,
        "execute_dataset_query_for_agent_team_direct_fallback",
        fake_execute_dataset_query_for_agent_team_direct_fallback,
    )
    client = ConfirmedDatasetMissingArtifactFakeClient()
    runner = AgentTeamTaskRunner(
        base_url="http://testserver/agentscope",
        settings=Settings(
            OPENAI_API_KEY="sk-test",
            OPENAI_BASE_URL="https://example.test/v1",
            LLM_MODEL="test-model",
            DATALOGUE_REPORT_WORKER_ENABLED=False,
        ),
        client=client,
    )
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询杨凯2025年工作日志",
        dataset_id=10,
    )
    task = SimpleNamespace(
        task_id="task-confirmed-fallback",
        trace_id="trace-confirmed-fallback",
        thread_id="thread-confirmed-fallback",
        message_id="message-confirmed-fallback",
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

    event_types = [event.event_type for event in events]
    assert event_types[-3:] == ["tool_call.started", "tool_call.completed", "message.completed"]
    assert events[-3].payload["tool_name"] == "datalogue_execute_query_plan"
    assert events[-2].payload["tool_name"] == "datalogue_execute_query_plan"
    assert events[-1].payload["datalogue_event_type"] == "dataset_query_result"
    assert events[-1].payload["artifact_ref"] == "artifact:test"
    assert events[-1].payload["artifact_card"]["preview_payload"] == {
        "row_count": 100,
        "column_count": 48,
    }
    assert client.post_final_event_consumed is False
