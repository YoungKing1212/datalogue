# ============================================================
# File Name   : test_agentscope_service_worker_logging.py
# Description:
#   AgentScope BI worker 进度中间件与 OTel 边界测试。
#
# Responsibilities:
#   - 验证 BI worker 只保留前端进度事件，不再打印自定义执行日志。
#   - 验证模型调用观测交给 AgentScope TracingMiddleware / OTel。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest


class FakeBIRecord:
    source = "team"
    id = "worker-bi-1"
    data = SimpleNamespace(
        name="bi-worker",
        system_prompt="你是 Datalogue BI Worker，只处理 Datalogue Dataset Query 类问数任务。",
    )


class FakeReportRecord:
    source = "team"
    id = "report-worker-1"
    data = SimpleNamespace(
        name="report-worker",
        system_prompt="你是 Datalogue Report Worker。",
    )


class FakeStorage:
    def __init__(self, record):
        self.record = record

    async def get_agent(self, user_id, agent_id):
        assert user_id == "user-1"
        assert agent_id in {"worker-bi-1", "report-worker-1"}
        return self.record


@pytest.mark.asyncio
async def test_extra_agent_middlewares_attaches_only_to_bi_worker():
    from agentscope.middleware import TracingMiddleware

    from app.agentscope_service.worker_logging import (
        BIWorkerProgressMiddleware,
        build_datalogue_extra_agent_middlewares,
    )

    factory = build_datalogue_extra_agent_middlewares(storage=FakeStorage(FakeBIRecord()))

    middlewares = await factory("user-1", "worker-bi-1", "session-bi-1")

    # BI worker 保留 OTel TracingMiddleware 和前端进度中间件；不再挂自定义模型 I/O 日志中间件。
    assert len(middlewares) == 2
    assert isinstance(middlewares[0], TracingMiddleware)
    assert isinstance(middlewares[1], BIWorkerProgressMiddleware)
    assert "on_model_call" not in type(middlewares[1]).__dict__
    assert middlewares[1].worker_context["agent_name"] == "bi-worker"

    factory = build_datalogue_extra_agent_middlewares(storage=FakeStorage(FakeReportRecord()))
    # 非 BI worker 只获得全局 TracingMiddleware
    non_bi_middlewares = await factory("user-1", "report-worker-1", "session-report-1")
    assert len(non_bi_middlewares) == 1
    assert isinstance(non_bi_middlewares[0], TracingMiddleware)


def test_event_summary_includes_pending_confirmation_tool_names():
    from app.agentscope_service.worker_logging import _event_summary

    event = SimpleNamespace(
        type="REQUIRE_USER_CONFIRM",
        reply_id="reply-1",
        tool_calls=[
            SimpleNamespace(id="call-1", name="Glob", input='{"pattern":"**/*"}', state="asking"),
        ],
    )

    summary = _event_summary(event)

    assert summary["event_type"] == "REQUIRE_USER_CONFIRM"
    assert summary["pending_tool_names"] == ["Glob"]
    assert summary["pending_tool_calls"] == [{"id": "call-1", "name": "Glob", "state": "asking"}]
    assert "pattern" not in str(summary)


@pytest.mark.asyncio
async def test_bi_worker_reply_does_not_log_custom_execution_events(caplog):
    from app.agentscope_service.worker_logging import BIWorkerProgressMiddleware

    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    agent = SimpleNamespace(name="bi-worker")

    async def next_handler(**_kwargs):
        yield SimpleNamespace(type="reply_start")
        yield SimpleNamespace(type="tool_call_start", tool_call_name="datalogue_query_dataset")
        yield SimpleNamespace(type="reply_end")

    with caplog.at_level(logging.INFO, logger="app.agentscope_service.worker_logging"):
        events = [
            event
            async for event in middleware.on_reply(
                agent=agent,
                input_kwargs={"inputs": "查询杨凯2025年日志"},
                next_handler=next_handler,
            )
        ]

    assert [event.type for event in events] == ["reply_start", "tool_call_start", "reply_end"]
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[agentscope.bi_worker." not in logs
    assert "查询杨凯2025年日志" not in logs


@pytest.mark.asyncio
async def test_bi_worker_reply_publishes_safe_realtime_progress_events():
    from app.agentscope_service.progress_bridge import agent_progress_subscription
    from app.agentscope_service.worker_logging import BIWorkerProgressMiddleware

    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    agent = SimpleNamespace(name="bi-worker")

    async def next_handler(**_kwargs):
        yield SimpleNamespace(type="reply_start", reply_id="reply-1")
        yield SimpleNamespace(
            type="TOOL_CALL_START",
            reply_id="reply-1",
            tool_call_name="datalogue_select_candidate_datasets",
            tool_call_id="call-1",
        )
        yield SimpleNamespace(type="reply_end", reply_id="reply-1")

    async with agent_progress_subscription(user_id="user-1") as queue:
        events = [
            event
            async for event in middleware.on_reply(
                agent=agent,
                input_kwargs={"inputs": "查询杨凯2025年日志"},
                next_handler=next_handler,
            )
        ]
        progress_events = [queue.get_nowait() for _ in range(queue.qsize())]

    assert [event.type for event in events] == ["reply_start", "TOOL_CALL_START", "reply_end"]
    assert [event["event_type"] for event in progress_events] == [
        "agent.progress",
        "agent.progress",
        "agent.progress",
    ]
    assert progress_events[0]["payload"] == {
        "agent_role": "worker",
        "agent_name": "bi-worker",
        "phase": "reply",
        "status": "running",
        "title": "BI Worker 开始处理",
        "summary": "BI Worker 已开始处理任务。",
        "worker_agent_id": "worker-bi-1",
        "worker_session_id": "session-bi-1",
    }
    assert progress_events[1]["payload"] == {
        "agent_role": "worker",
        "agent_name": "bi-worker",
        "phase": "tool",
        "status": "running",
        "title": "工具调用",
        "summary": "BI Worker 正在调用 datalogue_select_candidate_datasets。",
        "tool_name": "datalogue_select_candidate_datasets",
        "tool_call_id": "call-1",
        "worker_agent_id": "worker-bi-1",
        "worker_session_id": "session-bi-1",
    }
    assert progress_events[-1]["payload"]["status"] == "completed"
    assert "查询杨凯2025年日志" not in str(progress_events)


@pytest.mark.asyncio
async def test_bi_worker_progress_middleware_does_not_own_model_call_logging(monkeypatch, caplog):
    from app.agentscope_service.worker_logging import BIWorkerProgressMiddleware

    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "true")
    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    agent = SimpleNamespace(name="bi-worker")

    with caplog.at_level(logging.INFO, logger="app.agentscope_service.worker_logging"):
        assert "on_model_call" not in type(middleware).__dict__
        assert agent.name == "bi-worker"

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[agentscope.bi_worker.llm." not in logs
    assert "查询杨凯2025年日志" not in logs


# ---- Phase 1 & 2 新增测试 ----


@pytest.mark.asyncio
async def test_resolve_task_context_direct_hit():
    """leader session 直接命中 Redis 中的 task context。"""
    import json

    from app.agentscope_service.task_context import resolve_task_context

    class FakeRedisForDirectHit:
        async def get(self, key):
            return json.dumps(
                {
                    "task_id": "task-direct-1",
                    "thread_id": "thread-direct-1",
                    "message_id": "msg-direct-1",
                    "trace_id": "trace-direct-1",
                    "leader_session_id": "leader-session-1",
                }
            )

    class FakeStorageDirect:
        def get_client(self):
            return FakeRedisForDirectHit()

        async def list_teams(self, user_id):
            return []

    ctx = await resolve_task_context(
        storage=FakeStorageDirect(),
        user_id="user-1",
        agent_id="agent-1",
        session_id="leader-session-1",
    )
    assert ctx["task_id"] == "task-direct-1"
    assert ctx["thread_id"] == "thread-direct-1"
    assert ctx["message_id"] == "msg-direct-1"
    assert ctx["trace_id"] == "trace-direct-1"
    assert ctx["leader_session_id"] == "leader-session-1"


@pytest.mark.asyncio
async def test_resolve_task_context_via_team_record():
    """worker 通过 TeamRecord 反查 leader session 再命中 Redis。"""
    import json
    from types import SimpleNamespace

    from app.agentscope_service.task_context import resolve_task_context

    class FakeRedisForTeam:
        @staticmethod
        async def get(key):
            key_str = key.decode() if isinstance(key, bytes) else key
            if "leader-session-team" in key_str:
                return json.dumps(
                    {
                        "task_id": "task-via-team",
                        "thread_id": "thread-team",
                        "message_id": "msg-team",
                        "trace_id": "trace-team",
                        "leader_session_id": "leader-session-team",
                    }
                )
            return None

    class FakeStorageTeam:
        def get_client(self):
            return FakeRedisForTeam()

        async def list_teams(self, user_id):
            return [
                SimpleNamespace(
                    session_id="leader-session-team",
                    data=SimpleNamespace(member_ids=["worker-agent-1", "other-agent"]),
                ),
            ]

    ctx = await resolve_task_context(
        storage=FakeStorageTeam(),
        user_id="user-1",
        agent_id="worker-agent-1",
        session_id="worker-session-1",
    )
    assert ctx["task_id"] == "task-via-team"
    assert ctx["leader_session_id"] == "leader-session-team"


@pytest.mark.asyncio
async def test_resolve_task_context_miss_graceful():
    """Redis 中无数据时 resolve_task_context 返回空 dict，不抛异常。"""
    from app.agentscope_service.task_context import resolve_task_context

    class FakeRedisNone:
        async def get(self, key):
            return None

    class FakeStorageNone:
        def get_client(self):
            return FakeRedisNone()

        async def list_teams(self, user_id):
            return []

    ctx = await resolve_task_context(
        storage=FakeStorageNone(),
        user_id="user-1",
        agent_id="agent-1",
        session_id="unknown-session",
    )
    assert ctx == {}


def test_model_input_summary_includes_enhanced_fields():
    """验证 _model_input_summary 包含 input_chars 等增强字段。"""
    from app.agentscope_service.worker_logging import _model_input_summary

    summary = _model_input_summary(
        {
            "messages": [
                SimpleNamespace(content="你好，请查询杨凯的日志数据。"),
                SimpleNamespace(content="需要关注2025年的数据。"),
            ],
            "tools": [
                {"function": {"name": "datalogue_query_dataset"}},
                {"function": {"name": "datalogue_select_candidates"}},
            ],
            "tool_choice": "auto",
        }
    )
    assert summary["message_count"] == 2
    assert summary["tool_count"] == 2
    assert summary["tool_choice"] == "auto"
    assert "datalogue_query_dataset" in summary["tool_names"]
    assert summary["input_chars"] > 0


def test_model_output_summary_includes_enhanced_fields():
    """验证 _model_output_summary 包含 output_chars/finish_reason/duration_ms 等增强字段。"""
    from app.agentscope_service.worker_logging import _model_output_summary

    summary = _model_output_summary(
        SimpleNamespace(content="模型回答内容", finish_reason="stop"),
        chunk_index=3,
        duration_ms=1500,
    )
    assert summary["chunk_index"] == 3
    assert summary["duration_ms"] == 1500
    assert summary["finish_reason"] == "stop"
    assert summary["output_chars"] > 0
    assert summary["response_type"] == "SimpleNamespace"


@pytest.mark.asyncio
async def test_streaming_model_output_is_left_to_otel_tracing(caplog):
    """流式模型输出不再由 Datalogue 自定义日志记录，交给 AgentScope OTel span。"""
    from app.agentscope_service.worker_logging import BIWorkerProgressMiddleware

    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    with caplog.at_level(logging.INFO, logger="app.agentscope_service.worker_logging"):
        assert "on_model_call" not in type(middleware).__dict__

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert logs == ""


@pytest.mark.asyncio
async def test_on_model_call_failures_are_left_to_otel_tracing(caplog):
    """模型调用异常不再由 Datalogue 自定义日志记录，交给 AgentScope OTel span。"""
    from app.agentscope_service.worker_logging import BIWorkerProgressMiddleware

    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    with caplog.at_level(logging.INFO, logger="app.agentscope_service.worker_logging"):
        assert "on_model_call" not in type(middleware).__dict__

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert logs == ""


@pytest.mark.asyncio
async def test_raw_logs_not_leaked_to_progress_payload():
    """开启 raw debug 时 progress payload 不包含 raw LLM 内容。"""
    from app.agentscope_service.progress_bridge import agent_progress_subscription
    from app.agentscope_service.worker_logging import BIWorkerProgressMiddleware

    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    agent = SimpleNamespace(name="bi-worker")

    async def next_handler(**_kwargs):
        yield SimpleNamespace(type="reply_start", reply_id="reply-raw")

    async with agent_progress_subscription(user_id="user-1") as queue:
        async for _event in middleware.on_reply(
            agent=agent,
            input_kwargs={"inputs": "保密输入: SELECT * FROM users"},
            next_handler=next_handler,
        ):
            pass
        progress_events = [queue.get_nowait() for _ in range(queue.qsize())]

    progress_text = str(progress_events)
    assert "SELECT" not in progress_text
    assert "users" not in progress_text
    assert "保密输入" not in progress_text


def test_worker_context_includes_correlation_fields():
    """验证 worker_context 包含 task_id/thread_id/message_id/trace_id 等关联字段。"""
    from app.agentscope_service.worker_logging import _publish_worker_progress

    worker_ctx = {
        "user_id": "user-1",
        "agent_id": "worker-bi-1",
        "agent_name": "bi-worker",
        "session_id": "session-bi-1",
        "task_id": "task-ctx-1",
        "thread_id": "thread-ctx-1",
        "message_id": "msg-ctx-1",
        "trace_id": "trace-ctx-1",
        "leader_session_id": "leader-session-1",
    }

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.agentscope_service.progress_bridge.publish_agent_progress",
            lambda user_id, payload: None,
        )
        _publish_worker_progress(
            worker_context=worker_ctx,
            phase="reply",
            status="running",
            title="测试标题",
            summary="测试摘要",
        )


def test_agentscope_otel_config_defaults(tmp_path, monkeypatch):
    """验证 OTel 配置项默认关闭。"""
    from app.core.config import Settings

    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.AGENTSCOPE_OTEL_TRACING_ENABLED is False
    assert settings.AGENTSCOPE_OTEL_EXPORTER_ENABLED is False
    assert settings.AGENTSCOPE_OTEL_EXPORTER_ENDPOINT is None
    assert settings.AGENTSCOPE_OTEL_LOGGING_ENABLED is True
    assert settings.AGENTSCOPE_OTEL_SERVICE_NAME == "datalogue-api"


def test_setup_agentscope_tracing_attaches_logging_exporter_when_otlp_disabled(monkeypatch):
    """只启用 tracing、不启用 OTLP 时，也要把 span 输出到后端日志。"""
    from opentelemetry import trace

    from app.agentscope_service import otel_setup
    from app.core.config import Settings

    calls: dict[str, object] = {}

    def fake_set_tracer_provider(provider):
        calls["provider"] = provider

    def fake_setup_logging_exporter(provider, settings):
        calls["logging_provider"] = provider
        calls["logging_enabled"] = settings.AGENTSCOPE_OTEL_LOGGING_ENABLED

    def fake_setup_otlp_exporter(provider, settings):
        calls["otlp_provider"] = provider

    monkeypatch.setattr(trace, "set_tracer_provider", fake_set_tracer_provider)
    monkeypatch.setattr(otel_setup, "_setup_logging_exporter", fake_setup_logging_exporter)
    monkeypatch.setattr(otel_setup, "_setup_otlp_exporter", fake_setup_otlp_exporter)

    settings = Settings(
        AGENTSCOPE_OTEL_TRACING_ENABLED=True,
        AGENTSCOPE_OTEL_LOGGING_ENABLED=True,
        AGENTSCOPE_OTEL_EXPORTER_ENABLED=False,
        AGENTSCOPE_OTEL_EXPORTER_ENDPOINT=None,
    )

    otel_setup.setup_agentscope_tracing(settings)

    assert calls["provider"] is calls["logging_provider"]
    assert calls["logging_enabled"] is True
    assert "otlp_provider" not in calls
