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
async def test_agentscope_service_task_runner_uses_agentscope_model_selection_without_local_config():
    from app.core.config import Settings
    from app.agentscope_service.runner import AgentScopeServiceTaskRunner

    client = FakeClient()
    runner = AgentScopeServiceTaskRunner(
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
async def test_agentscope_service_task_runner_default_model_comes_from_agentscope_credential():
    from app.core.config import Settings
    from app.agentscope_service.runner import AgentScopeServiceTaskRunner

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
    runner = AgentScopeServiceTaskRunner(
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
    assert client.upserted_credentials == []
    assert len(client.ensure_agent_requests) == 1
    assert client.ensure_agent_requests[0]["name"] == "Datalogue Agent Team Leader"
    assert "AgentCreate" in client.ensure_agent_requests[0]["system_prompt"]
    assert client.triggered_chats[0]["agent_id"] == "agent-leader-1"
    assert client.triggered_chats[0]["session_id"] == "session-1"
    assert "统计合同总金额" in client.triggered_chats[0]["text"]
    assert '"dataset_id":12' in client.triggered_chats[0]["text"]
    assert "严禁再次调用 datalogue_select_candidate_datasets" in client.triggered_chats[0]["text"]
    assert client.stream_requests == [{"session_id": "session-1", "agent_id": "agent-leader-1"}]
    assert [event.event_type for event in events] == ["message.delta", "message.completed"]
    assert events[-1].payload["summary"] == "统计完成"
    assert client.post_final_event_consumed is False
    assert client.closed is False


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_treats_selected_dataset_as_confirmed():
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
    assert "datalogue_query_dataset(dataset_id=10" in trigger_text
    assert "严禁再次调用 datalogue_select_candidate_datasets" in trigger_text
    assert "clarification_response" not in trigger_text


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


class WorkerProgressFakeClient(TeamDelegationFakeClient):
    user_id = "datalogue-agent-team"

    async def stream_session(self, session_id, *, agent_id=None):
        from app.agentscope_service.progress_bridge import publish_agent_progress

        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {
            "type": "ToolCallStartEvent",
            "tool_call_name": "AgentCreate",
            "payload": {"tool_call_name": "AgentCreate"},
        }
        publish_agent_progress(
            user_id=self.user_id,
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
        yield {"type": "message", "payload": {"content": "已创建 BI worker，正在等待 worker 返回结果。"}}
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "等待 worker 返回结果"}}
        yield {"type": "message", "payload": {"content": "查询完成：共找到 8 条日志。"}}
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "查询完成：共找到 8 条日志。"}}


class WorkerCandidateFallbackFakeClient(TeamDelegationFakeClient):
    user_id = "datalogue-agent-team"

    async def stream_session(self, session_id, *, agent_id=None):
        from app.agentscope_service.progress_bridge import publish_agent_event

        self.stream_requests.append({"session_id": session_id, "agent_id": agent_id})
        yield {
            "type": "ToolCallStartEvent",
            "tool_call_name": "AgentCreate",
            "payload": {"tool_call_name": "AgentCreate"},
        }
        publish_agent_event(
            user_id=self.user_id,
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
        yield {"type": "message", "payload": {"content": "已创建 BI worker，正在等待 worker 返回结果。"}}
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "等待 worker 返回结果"}}
        yield {"type": "message", "payload": {"content": "查询未完成，未生成可展示结果。"}}
        yield {"event_type": "ReplyEndEvent", "payload": {"summary": "查询未完成，未生成可展示结果。"}}
        self.post_final_event_consumed = True
        yield {"type": "message", "payload": {"content": "不应消费兜底完成后的长连接事件"}}


@pytest.mark.asyncio
async def test_agentscope_service_task_runner_merges_worker_progress_before_final():
    from app.core.config import Settings
    from app.agentscope_service.runner import AgentScopeServiceTaskRunner

    client = WorkerProgressFakeClient()
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
    from app.agentscope_service.runner import AgentScopeServiceTaskRunner

    client = WorkerCandidateFallbackFakeClient()
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
async def test_agentscope_service_task_runner_falls_back_when_confirmed_dataset_has_no_artifact(monkeypatch):
    from app.core.config import Settings
    from app.agentscope_service import runner as runner_module
    from app.agentscope_service.runner import AgentScopeServiceTaskRunner

    async def fake_execute_dataset_query_for_agent_team(**kwargs):
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

    monkeypatch.setattr(runner_module, "execute_dataset_query_for_agent_team", fake_execute_dataset_query_for_agent_team)
    client = ConfirmedDatasetMissingArtifactFakeClient()
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
    assert events[-1].payload["datalogue_event_type"] == "dataset_query_result"
    assert events[-1].payload["artifact_ref"] == "artifact:test"
    assert events[-1].payload["artifact_card"]["preview_payload"] == {"row_count": 100, "column_count": 48}
    assert client.post_final_event_consumed is False
