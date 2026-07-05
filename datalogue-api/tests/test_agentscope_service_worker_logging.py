# ============================================================
# File Name   : test_agentscope_service_worker_logging.py
# Description:
#   AgentScope BI worker 流式日志中间件测试。
#
# Responsibilities:
#   - 验证 BI worker reply 事件流会打印安全工作日志。
#   - 验证显式开启 raw debug 时会打印 LLM 输入和流式输出。
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
    from app.agentscope_service.worker_logging import build_datalogue_extra_agent_middlewares

    factory = build_datalogue_extra_agent_middlewares(storage=FakeStorage(FakeBIRecord()))

    middlewares = await factory("user-1", "worker-bi-1", "session-bi-1")

    assert len(middlewares) == 1
    assert middlewares[0].worker_context["agent_name"] == "bi-worker"

    factory = build_datalogue_extra_agent_middlewares(storage=FakeStorage(FakeReportRecord()))
    assert await factory("user-1", "report-worker-1", "session-report-1") == []


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
async def test_bi_worker_reply_logs_streaming_work_events(caplog):
    from app.agentscope_service.worker_logging import BIWorkerStreamingLogMiddleware

    middleware = BIWorkerStreamingLogMiddleware(
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
    assert "[agentscope.bi_worker.reply.started]" in logs
    assert "[agentscope.bi_worker.reply.event]" in logs
    assert "[agentscope.bi_worker.reply.completed]" in logs
    assert '"agent_id": "worker-bi-1"' in logs
    assert '"event_type": "tool_call_start"' in logs
    assert '"tool_call_name": "datalogue_query_dataset"' in logs
    assert "查询杨凯2025年日志" not in logs


@pytest.mark.asyncio
async def test_bi_worker_model_call_logs_raw_llm_io_when_debug_enabled(monkeypatch, caplog):
    from app.agentscope_service.worker_logging import BIWorkerStreamingLogMiddleware

    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "true")
    middleware = BIWorkerStreamingLogMiddleware(
        worker_context={
            "user_id": "user-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    agent = SimpleNamespace(name="bi-worker")

    async def next_handler(**_kwargs):
        async def stream():
            yield SimpleNamespace(content="第一段输出", is_last=False)
            yield SimpleNamespace(content="最终输出", is_last=True)

        return stream()

    with caplog.at_level(logging.INFO, logger="app.agentscope_service.worker_logging"):
        result = await middleware.on_model_call(
            agent=agent,
            input_kwargs={
                "messages": ["LLM输入: 查询杨凯2025年日志"],
                "tools": [{"function": {"name": "datalogue_query_dataset"}}],
                "tool_choice": None,
                "current_model": SimpleNamespace(model="test-model"),
            },
            next_handler=next_handler,
        )
        chunks = [chunk async for chunk in result]

    assert [chunk.content for chunk in chunks] == ["第一段输出", "最终输出"]
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[agentscope.bi_worker.llm.input.raw]" in logs
    assert "[agentscope.bi_worker.llm.output.raw]" in logs
    assert "LLM输入: 查询杨凯2025年日志" in logs
    assert "第一段输出" in logs
    assert "最终输出" in logs
