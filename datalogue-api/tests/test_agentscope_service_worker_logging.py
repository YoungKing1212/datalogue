# ============================================================
# File Name   : test_agentscope_service_worker_logging.py
# Description:
#   AgentScope BI worker 进度中间件与 OTel 边界测试。
#
# Responsibilities:
#   - 验证 BI worker 保留前端进度事件和脱敏事件链路日志。
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


class FakeLeaderRecord:
    source = "user"
    id = "agent-leader-1"
    data = SimpleNamespace(
        name="Datalogue Agent Team Leader",
        system_prompt="你是 Datalogue 智能问数主链的 AgentScope 官方 Agent Team Leader。",
    )


class FakeStorage:
    def __init__(self, record):
        self.record = record

    async def get_agent(self, user_id, agent_id):
        assert user_id == "user-1"
        assert agent_id in {"worker-bi-1", "report-worker-1", "agent-leader-1"}
        return self.record


@pytest.mark.asyncio
async def test_extra_agent_middlewares_attaches_tracing_and_phoenix_compatibility():
    from agentscope.middleware import TracingMiddleware

    from app.domains.agent_team.worker_logging import (
        BIWorkerProgressMiddleware,
        LeaderRawDebugMiddleware,
        PhoenixSessionIOMiddleware,
        build_datalogue_extra_agent_middlewares,
    )

    factory = build_datalogue_extra_agent_middlewares(storage=FakeStorage(FakeBIRecord()))

    middlewares = await factory("user-1", "worker-bi-1", "session-bi-1")

    # 原生 Tracing 必须在最外层，Phoenix 兼容层才能把 I/O 写入同一个根 Agent Span。
    assert len(middlewares) == 3
    assert isinstance(middlewares[0], TracingMiddleware)
    assert isinstance(middlewares[1], PhoenixSessionIOMiddleware)
    assert isinstance(middlewares[2], BIWorkerProgressMiddleware)
    assert "on_model_call" not in type(middlewares[2]).__dict__
    assert middlewares[2].worker_context["agent_name"] == "bi-worker"

    factory = build_datalogue_extra_agent_middlewares(storage=FakeStorage(FakeReportRecord()))
    # 非 BI worker 同样补充 Phoenix Session I/O，但不挂 BI 进度中间件。
    non_bi_middlewares = await factory("user-1", "report-worker-1", "session-report-1")
    assert len(non_bi_middlewares) == 2
    assert isinstance(non_bi_middlewares[0], TracingMiddleware)
    assert isinstance(non_bi_middlewares[1], PhoenixSessionIOMiddleware)

    factory = build_datalogue_extra_agent_middlewares(storage=FakeStorage(FakeLeaderRecord()))
    leader_middlewares = await factory("user-1", "agent-leader-1", "session-leader-1")
    assert len(leader_middlewares) == 3
    assert isinstance(leader_middlewares[0], TracingMiddleware)
    assert isinstance(leader_middlewares[1], PhoenixSessionIOMiddleware)
    assert isinstance(leader_middlewares[2], LeaderRawDebugMiddleware)


@pytest.mark.asyncio
async def test_phoenix_session_io_middleware_sets_openinference_root_attributes(monkeypatch):
    """兼容层复用当前 OTel Span，写入 Phoenix Session 能识别的文本字段。"""
    from agentscope.message import AssistantMsg, UserMsg

    from app.domains.agent_team import worker_logging
    from app.domains.agent_team.worker_logging import PhoenixSessionIOMiddleware

    class RecordingSpan:
        def __init__(self):
            self.attributes = {}

        def is_recording(self):
            return True

        def set_attribute(self, name, value):
            self.attributes[name] = value

    span = RecordingSpan()
    monkeypatch.setattr(worker_logging.otel_trace, "get_current_span", lambda: span)

    async def next_handler(**_kwargs):
        yield AssistantMsg(name="assistant", content="已找到 243 条工作日志。")

    middleware = PhoenixSessionIOMiddleware(agent_role="leader")
    events = [
        event
        async for event in middleware.on_reply(
            agent=SimpleNamespace(name="leader"),
            input_kwargs={"inputs": UserMsg(name="user", content="查询杨凯2025年工作日志")},
            next_handler=next_handler,
        )
    ]

    assert len(events) == 1
    assert span.attributes == {
        "input.value": "查询杨凯2025年工作日志",
        "input.mime_type": "text/plain",
        "output.value": "已找到 243 条工作日志。",
        "output.mime_type": "text/plain",
    }


@pytest.mark.asyncio
async def test_phoenix_session_io_middleware_filters_sensitive_text_and_uses_fallback(monkeypatch):
    """SQL、Schema 等内部材料不能因兼容 Phoenix Session 而离开进程。"""
    from agentscope.message import AssistantMsg, UserMsg

    from app.domains.agent_team import worker_logging
    from app.domains.agent_team.worker_logging import PhoenixSessionIOMiddleware

    class RecordingSpan:
        def __init__(self):
            self.attributes = {}

        def is_recording(self):
            return True

        def set_attribute(self, name, value):
            self.attributes[name] = value

    span = RecordingSpan()
    monkeypatch.setattr(worker_logging.otel_trace, "get_current_span", lambda: span)

    async def next_handler(**_kwargs):
        yield AssistantMsg(name="assistant", content="schema: secret_table")

    middleware = PhoenixSessionIOMiddleware(agent_role="bi_worker")
    async for _event in middleware.on_reply(
        agent=SimpleNamespace(name="bi-worker"),
        input_kwargs={"inputs": UserMsg(name="user", content="SELECT * FROM secret_table")},
        next_handler=next_handler,
    ):
        pass

    serialized = str(span.attributes).lower()
    assert span.attributes["input.value"] == "BI Worker继续处理当前任务"
    assert span.attributes["output.value"] == "BI Worker本轮处理已完成"
    assert "select" not in serialized
    assert "schema" not in serialized
    assert "secret_table" not in serialized


def test_event_summary_includes_pending_confirmation_tool_names():
    from app.domains.agent_team.worker_logging import _event_summary

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
async def test_bi_worker_reply_logs_safe_event_chain_without_raw_inputs(monkeypatch, caplog):
    from agentscope.event import (
        ReplyEndEvent,
        ReplyStartEvent,
        ThinkingBlockDeltaEvent,
        ThinkingBlockEndEvent,
        ThinkingBlockStartEvent,
        ToolCallDeltaEvent,
        ToolCallEndEvent,
        ToolCallStartEvent,
    )

    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "false")
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
        yield ReplyStartEvent(session_id="session-bi-1", reply_id="reply-1", name="bi-worker")
        yield ThinkingBlockStartEvent(reply_id="reply-1", block_id="think-1")
        yield ThinkingBlockDeltaEvent(
            reply_id="reply-1",
            block_id="think-1",
            delta="先分析用户问题，再选择数据集。",
        )
        yield ThinkingBlockEndEvent(reply_id="reply-1", block_id="think-1")
        yield ToolCallStartEvent(
            reply_id="reply-1",
            tool_call_id="call-1",
            tool_call_name="datalogue_execute_query_plan",
        )
        yield ToolCallDeltaEvent(
            reply_id="reply-1",
            tool_call_id="call-1",
            delta='{"sql":"SELECT * FROM users"}',
        )
        yield ToolCallEndEvent(reply_id="reply-1", tool_call_id="call-1")
        yield ReplyEndEvent(session_id="session-bi-1", reply_id="reply-1")

    with caplog.at_level(logging.INFO, logger="app.domains.agent_team.worker_logging"):
        events = [
            event
            async for event in middleware.on_reply(
                agent=agent,
                input_kwargs={"inputs": "查询杨凯2025年日志"},
                next_handler=next_handler,
            )
        ]

    assert [str(event.type) for event in events] == [
        "REPLY_START",
        "THINKING_BLOCK_START",
        "THINKING_BLOCK_DELTA",
        "THINKING_BLOCK_END",
        "TOOL_CALL_START",
        "TOOL_CALL_DELTA",
        "TOOL_CALL_END",
        "REPLY_END",
    ]
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[agentscope.bi_worker.event]" in logs
    assert '"category": "thinking"' not in logs
    assert '"category": "tool_call"' not in logs
    assert '"tool_call_name": "datalogue_execute_query_plan"' not in logs
    assert '"delta_length":' not in logs
    assert "查询杨凯2025年日志" not in logs
    assert "先分析用户问题" not in logs
    assert "SELECT" not in logs
    assert "users" not in logs


@pytest.mark.asyncio
async def test_bi_worker_reply_publishes_safe_realtime_progress_events():
    from app.domains.agent_team.progress_bridge import agent_progress_subscription
    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "leader_session_id": "leader-session-1",
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

    async with agent_progress_subscription(leader_session_id="leader-session-1") as queue:
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
async def test_bi_worker_thinking_events_publish_safe_reasoning_progress(monkeypatch):
    from agentscope.event import (
        ReplyEndEvent,
        ReplyStartEvent,
        ThinkingBlockDeltaEvent,
        ThinkingBlockEndEvent,
        ThinkingBlockStartEvent,
    )

    from app.domains.agent_team.progress_bridge import agent_progress_subscription
    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

    monkeypatch.setenv("DATALOGUE_DEBUG_STREAM_RAW_THINKING", "false")
    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "leader_session_id": "leader-session-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    agent = SimpleNamespace(name="bi-worker")

    async def next_handler(**_kwargs):
        yield ReplyStartEvent(session_id="session-bi-1", reply_id="reply-1", name="bi-worker")
        yield ThinkingBlockStartEvent(reply_id="reply-1", block_id="think-1")
        yield ThinkingBlockDeltaEvent(
            reply_id="reply-1",
            block_id="think-1",
            delta="先分析用户问题，并考虑 SELECT * FROM hidden_schema.raw_rows",
        )
        yield ThinkingBlockEndEvent(reply_id="reply-1", block_id="think-1")
        yield ReplyEndEvent(session_id="session-bi-1", reply_id="reply-1")

    async with agent_progress_subscription(leader_session_id="leader-session-1") as queue:
        events = [
            event
            async for event in middleware.on_reply(
                agent=agent,
                input_kwargs={"inputs": "查询杨凯2025年日志"},
                next_handler=next_handler,
            )
        ]
        progress_events = [queue.get_nowait() for _ in range(queue.qsize())]

    assert [str(event.type) for event in events] == [
        "REPLY_START",
        "THINKING_BLOCK_START",
        "THINKING_BLOCK_DELTA",
        "THINKING_BLOCK_END",
        "REPLY_END",
    ]
    thinking_payloads = [
        event["payload"] for event in progress_events if event["payload"]["phase"] == "thinking"
    ]
    assert [payload["status"] for payload in thinking_payloads] == ["running", "completed"]
    assert {payload["reasoning_kind"] for payload in thinking_payloads} == {
        "bi_worker_thinking_summary"
    }
    assert thinking_payloads[0]["summary"] == "正在分析问题与可用数据证据。"
    assert thinking_payloads[-1]["summary"] == "已完成一段安全推理摘要。"
    assert thinking_payloads[0]["stream_group_id"] == "agent-worker-thinking:reply-1:think-1"
    assert [payload["sequence"] for payload in thinking_payloads] == [1, 2]
    serialized = str(progress_events)
    assert "先分析用户问题" not in serialized
    assert "SELECT" not in serialized
    assert "hidden_schema" not in serialized
    assert "raw_rows" not in serialized
    assert "raw_delta" not in serialized
    assert "查询杨凯2025年日志" not in serialized


@pytest.mark.asyncio
async def test_bi_worker_thinking_debug_flag_streams_raw_delta(monkeypatch):
    from agentscope.event import (
        ReplyEndEvent,
        ReplyStartEvent,
        ThinkingBlockDeltaEvent,
        ThinkingBlockEndEvent,
        ThinkingBlockStartEvent,
    )

    from app.domains.agent_team.progress_bridge import agent_progress_subscription
    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

    monkeypatch.setenv("DATALOGUE_DEBUG_STREAM_RAW_THINKING", "true")
    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "leader_session_id": "leader-session-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    agent = SimpleNamespace(name="bi-worker")
    raw_delta = "原始 thinking delta：SELECT * FROM hidden_schema.raw_rows"

    async def next_handler(**_kwargs):
        yield ReplyStartEvent(session_id="session-bi-1", reply_id="reply-1", name="bi-worker")
        yield ThinkingBlockStartEvent(reply_id="reply-1", block_id="think-1")
        yield ThinkingBlockDeltaEvent(reply_id="reply-1", block_id="think-1", delta=raw_delta)
        yield ThinkingBlockEndEvent(reply_id="reply-1", block_id="think-1")
        yield ReplyEndEvent(session_id="session-bi-1", reply_id="reply-1")

    async with agent_progress_subscription(leader_session_id="leader-session-1") as queue:
        async for _event in middleware.on_reply(
            agent=agent,
            input_kwargs={"inputs": "查询杨凯2025年日志"},
            next_handler=next_handler,
        ):
            pass
        progress_events = [queue.get_nowait() for _ in range(queue.qsize())]

    raw_payloads = [
        event["payload"]
        for event in progress_events
        if event["payload"].get("reasoning_kind") == "bi_worker_raw_thinking_delta"
    ]
    assert len(raw_payloads) == 1
    assert raw_payloads[0]["debug_raw"] is True
    assert raw_payloads[0]["raw_delta"] == raw_delta
    assert raw_payloads[0]["title"] == "BI Worker 调试原文"
    assert raw_payloads[0]["stream_group_id"] == "agent-worker-thinking:reply-1:think-1"
    safe_payloads = [
        event["payload"]
        for event in progress_events
        if event["payload"].get("reasoning_kind") == "bi_worker_thinking_summary"
    ]
    assert [payload["status"] for payload in safe_payloads] == ["running", "completed"]
    assert "raw_delta" not in str(safe_payloads)


@pytest.mark.asyncio
async def test_bi_worker_thinking_debug_merges_tokenizer_split_deltas(monkeypatch):
    """LLM 供应商按 tokenizer 边界切碎的 delta 应先在后端合并到自然停顿再 emit。"""

    from agentscope.event import (
        ReplyEndEvent,
        ReplyStartEvent,
        ThinkingBlockDeltaEvent,
        ThinkingBlockEndEvent,
        ThinkingBlockStartEvent,
    )

    from app.domains.agent_team.progress_bridge import agent_progress_subscription
    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

    monkeypatch.setenv("DATALOGUE_DEBUG_STREAM_RAW_THINKING", "true")
    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "leader_session_id": "leader-session-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    agent = SimpleNamespace(name="bi-worker")

    # 前两段没有触发 flush 的字符，应该被缓冲；第三段以句号收尾，触发一次 emit。
    # 结束事件负责兜底 flush 掉最后一段无标点的 tail。
    fragments = ["plan_task_d", "aily_record ", "202", "5 finished. ", "tail"]

    async def next_handler(**_kwargs):
        yield ReplyStartEvent(session_id="session-bi-1", reply_id="reply-1", name="bi-worker")
        yield ThinkingBlockStartEvent(reply_id="reply-1", block_id="think-1")
        for frag in fragments:
            yield ThinkingBlockDeltaEvent(reply_id="reply-1", block_id="think-1", delta=frag)
        yield ThinkingBlockEndEvent(reply_id="reply-1", block_id="think-1")
        yield ReplyEndEvent(session_id="session-bi-1", reply_id="reply-1")

    async with agent_progress_subscription(leader_session_id="leader-session-1") as queue:
        async for _event in middleware.on_reply(
            agent=agent,
            input_kwargs={"inputs": "查询杨凯2025年日志"},
            next_handler=next_handler,
        ):
            pass
        progress_events = [queue.get_nowait() for _ in range(queue.qsize())]

    raw_payloads = [
        event["payload"]
        for event in progress_events
        if event["payload"].get("reasoning_kind") == "bi_worker_raw_thinking_delta"
    ]
    # 期望三次 emit：前两段合并到 `aily_record ` 末尾空格触发 flush；`202`+`5 finished. `
    # 空格再触发；`tail` 走 end 兜底。所有词根 identifier / 数字都不再被拆开。
    raw_deltas = [payload["raw_delta"] for payload in raw_payloads]
    assert raw_deltas == [
        "plan_task_daily_record ",
        "2025 finished. ",
        "tail",
    ]
    assert "plan_task_d aily_record" not in "".join(raw_deltas)
    for payload in raw_payloads:
        assert payload["debug_raw"] is True
        assert payload["stream_group_id"] == "agent-worker-thinking:reply-1:think-1"


def test_bi_worker_thinking_debug_flag_reads_settings_when_env_not_exported(monkeypatch, tmp_path):
    """写在 .env 但未导出到 os.environ 时，也要能开启前端 raw delta 调试通道。"""
    from app.domains.agent_team.worker_logging import _debug_stream_raw_thinking_enabled
    from app.core.config import get_settings

    monkeypatch.delenv("DATALOGUE_DEBUG_STREAM_RAW_THINKING", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "DATALOGUE_DEBUG_STREAM_RAW_THINKING=true\n",
        encoding="utf-8",
    )
    get_settings.cache_clear()
    try:
        assert _debug_stream_raw_thinking_enabled() is True
    finally:
        get_settings.cache_clear()


def test_summarize_tool_progress_maps_progressive_bi_tools_to_safe_summaries():
    from app.domains.agent_team.worker_logging import summarize_tool_progress

    assert summarize_tool_progress("datalogue_prepare_query_context") == {
        "summary": "BI Worker 正在准备查询上下文。"
    }
    assert summarize_tool_progress("datalogue_request_schema_slice") == {
        "summary": "BI Worker 正在申请相关数据结构切片。"
    }
    assert summarize_tool_progress("datalogue_execute_query_plan_bundle") == {
        "summary": "BI Worker 正在校验并执行受控查询计划。"
    }
    assert summarize_tool_progress("datalogue_repair_query_plan") == {
        "summary": "BI Worker 正在生成查询修复建议。"
    }


@pytest.mark.asyncio
async def test_bi_worker_progress_middleware_does_not_own_model_call_logging(monkeypatch, caplog):
    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

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

    with caplog.at_level(logging.INFO, logger="app.domains.agent_team.worker_logging"):
        assert "on_model_call" not in type(middleware).__dict__
        assert agent.name == "bi-worker"

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[agentscope.bi_worker.llm." not in logs
    assert "查询杨凯2025年日志" not in logs


@pytest.mark.asyncio
async def test_bi_worker_event_log_includes_model_call_token_usage(caplog):
    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
            "task_id": "task-1",
            "trace_id": "trace-1",
        },
    )
    agent = SimpleNamespace(name="bi-worker")

    async def next_handler(**_kwargs):
        yield SimpleNamespace(
            type="model_call_start",
            reply_id="reply-1",
            model_name="qwen-test",
        )
        yield SimpleNamespace(
            type="model_call_end",
            reply_id="reply-1",
            input_tokens=12,
            output_tokens=34,
        )

    with caplog.at_level(logging.INFO, logger="app.domains.agent_team.worker_logging"):
        events = [
            event
            async for event in middleware.on_reply(
                agent=agent,
                input_kwargs={"inputs": "敏感问题不应进入日志"},
                next_handler=next_handler,
            )
        ]

    assert [event.type for event in events] == ["model_call_start", "model_call_end"]
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert '"category": "model_call"' not in logs
    assert '"model_name": "qwen-test"' not in logs
    assert '"input_tokens": 12' not in logs
    assert '"output_tokens": 34' not in logs
    assert '"task_id": "task-1"' in logs
    assert '"trace_id": "trace-1"' in logs
    assert "敏感问题" not in logs


@pytest.mark.asyncio
async def test_bi_worker_raw_debug_log_requires_debug_flag(monkeypatch, caplog):
    from agentscope.event import ReplyStartEvent, ThinkingBlockDeltaEvent, ThinkingBlockStartEvent

    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "false")
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
        yield ReplyStartEvent(session_id="session-bi-1", reply_id="reply-1", name="bi-worker")
        yield ThinkingBlockStartEvent(reply_id="reply-1", block_id="think-1")
        yield ThinkingBlockDeltaEvent(
            reply_id="reply-1",
            block_id="think-1",
            delta="这是模型原始 thinking delta",
        )

    with caplog.at_level(logging.DEBUG, logger="app.domains.agent_team.worker_logging"):
        async for _event in middleware.on_reply(
            agent=agent,
            input_kwargs={"inputs": "敏感问题不应进入日志"},
            next_handler=next_handler,
        ):
            pass

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[agentscope.bi_worker.raw_debug]" not in logs
    assert "这是模型原始 thinking delta" not in logs


@pytest.mark.asyncio
async def test_bi_worker_raw_debug_log_prints_thinking_text_and_tool_io_at_debug_level(
    monkeypatch, caplog
):
    from agentscope.event import (
        ReplyStartEvent,
        TextBlockDeltaEvent,
        TextBlockEndEvent,
        TextBlockStartEvent,
        ThinkingBlockDeltaEvent,
        ThinkingBlockEndEvent,
        ThinkingBlockStartEvent,
        ToolCallDeltaEvent,
        ToolCallEndEvent,
        ToolCallStartEvent,
        ToolResultEndEvent,
        ToolResultStartEvent,
        ToolResultTextDeltaEvent,
    )
    from agentscope.message import ToolResultState

    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "true")
    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
            "task_id": "task-1",
            "trace_id": "trace-1",
        },
    )
    agent = SimpleNamespace(name="bi-worker")

    async def next_handler(**_kwargs):
        yield ReplyStartEvent(session_id="session-bi-1", reply_id="reply-1", name="bi-worker")
        yield ThinkingBlockStartEvent(reply_id="reply-1", block_id="think-1")
        yield ThinkingBlockDeltaEvent(
            reply_id="reply-1",
            block_id="think-1",
            delta="这是模型原始",
        )
        yield ThinkingBlockDeltaEvent(
            reply_id="reply-1",
            block_id="think-1",
            delta=" thinking delta",
        )
        yield ThinkingBlockEndEvent(reply_id="reply-1", block_id="think-1")
        yield TextBlockStartEvent(reply_id="reply-1", block_id="text-1")
        yield TextBlockDeltaEvent(
            reply_id="reply-1",
            block_id="text-1",
            delta="这是最终回答文本",
        )
        yield TextBlockEndEvent(reply_id="reply-1", block_id="text-1")
        yield ToolCallStartEvent(
            reply_id="reply-1",
            tool_call_id="call-1",
            tool_call_name="datalogue_execute_query_plan",
        )
        yield ToolCallDeltaEvent(
            reply_id="reply-1",
            tool_call_id="call-1",
            delta='{"dataset_id":1,',
        )
        yield ToolCallDeltaEvent(
            reply_id="reply-1",
            tool_call_id="call-1",
            delta='"question":"原始工具参数 delta"}',
        )
        yield ToolCallEndEvent(reply_id="reply-1", tool_call_id="call-1")
        yield ToolResultStartEvent(
            reply_id="reply-1",
            tool_call_id="call-1",
            tool_call_name="datalogue_execute_query_plan",
        )
        yield ToolResultTextDeltaEvent(
            reply_id="reply-1",
            tool_call_id="call-1",
            delta='{"status":"completed","rows":[{"name":"原始出参"}]}',
        )
        yield ToolResultEndEvent(
            reply_id="reply-1", tool_call_id="call-1", state=ToolResultState.SUCCESS
        )

    with caplog.at_level(logging.DEBUG, logger="app.domains.agent_team.worker_logging"):
        async for _event in middleware.on_reply(
            agent=agent,
            input_kwargs={"inputs": "敏感问题只允许 raw debug 时按 delta 输出"},
            next_handler=next_handler,
        ):
            pass

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert logs.count("[agentscope.bi_worker.raw_debug]") == 1
    assert "[agentscope.bi_worker.raw_tool_io]" not in logs
    assert "[agentscope.bi_worker.raw_blocks]" not in logs
    assert "[agentscope.bi_worker.raw_delta]" not in logs
    raw_line = next(
        line for line in logs.splitlines() if "[agentscope.bi_worker.raw_debug]" in line
    )
    assert '"delta":' not in logs
    assert '"timeline"' in raw_line
    assert '"step": 1' in raw_line
    assert '"type": "thinking"' in raw_line
    assert '"thinking": "这是模型原始 thinking delta"' in raw_line
    assert '"step": 2' in raw_line
    assert '"type": "text"' in raw_line
    assert '"text": "这是最终回答文本"' in raw_line
    assert '"step": 3' in raw_line
    assert '"type": "tool_call"' in raw_line
    assert '"tool_name": "datalogue_execute_query_plan"' in raw_line
    assert '"input":' in raw_line
    assert '"step": 4' in raw_line
    assert '"type": "tool_result"' in raw_line
    assert '"output":' in raw_line
    assert '"blocks":' not in raw_line
    assert '"content":' not in raw_line
    assert '"reply_id":' not in raw_line
    assert '"task_id":' not in raw_line
    assert '"trace_id":' not in raw_line
    assert "敏感问题只允许 raw debug 时按 delta 输出" not in raw_line


@pytest.mark.asyncio
async def test_leader_raw_debug_log_prints_thinking_when_debug_enabled(monkeypatch, caplog):
    from agentscope.event import (
        ReplyStartEvent,
        ThinkingBlockDeltaEvent,
        ThinkingBlockEndEvent,
        ThinkingBlockStartEvent,
    )

    from app.domains.agent_team.worker_logging import LeaderRawDebugMiddleware

    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "true")
    middleware = LeaderRawDebugMiddleware()
    agent = SimpleNamespace(name="Datalogue Agent Team Leader")

    async def next_handler(**_kwargs):
        yield ReplyStartEvent(
            session_id="session-leader-1", reply_id="reply-leader-1", name="leader"
        )
        yield ThinkingBlockStartEvent(reply_id="reply-leader-1", block_id="think-leader-1")
        yield ThinkingBlockDeltaEvent(
            reply_id="reply-leader-1",
            block_id="think-leader-1",
            delta="用户想要查询杨凯2025年日志，我需要创建BIworker。",
        )
        yield ThinkingBlockEndEvent(reply_id="reply-leader-1", block_id="think-leader-1")

    with caplog.at_level(logging.DEBUG, logger="app.domains.agent_team.worker_logging"):
        async for _event in middleware.on_reply(
            agent=agent,
            input_kwargs={"inputs": "用户原始问题不直接记录"},
            next_handler=next_handler,
        ):
            pass

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[agentscope.leader.raw_debug]" in logs
    assert "[agentscope.bi_worker.raw_debug]" not in logs
    assert "用户想要查询杨凯2025年日志，我需要创建BIworker。" in logs
    assert "用户原始问题不直接记录" not in logs


def test_raw_debug_blocks_outputs_timeline_in_msg_content_order():
    """timeline 按 msg.content 原始顺序输出全部 block。"""
    from types import SimpleNamespace

    from app.domains.agent_team.worker_logging import _raw_debug_blocks_from_msg

    msg = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="第一步思考"),
            SimpleNamespace(type="text", text="最终回复文本"),
            SimpleNamespace(type="tool_call", name="query_db", input='{"sql":"SELECT 1"}'),
            SimpleNamespace(
                type="tool_result",
                name="query_db",
                state="success",
                output='{"rows": [{"a": 1}]}',
            ),
        ]
    )
    timeline = _raw_debug_blocks_from_msg(msg)
    assert len(timeline) == 4
    assert timeline[0] == {"step": 1, "type": "thinking", "thinking": "第一步思考"}
    assert timeline[1] == {"step": 2, "type": "text", "text": "最终回复文本"}
    assert timeline[2] == {
        "step": 3,
        "type": "tool_call",
        "tool_name": "query_db",
        "input": '{"sql":"SELECT 1"}',
    }
    assert timeline[3] == {
        "step": 4,
        "type": "tool_result",
        "tool_name": "query_db",
        "state": "success",
        "output": '{"rows": [{"a": 1}]}',
    }


@pytest.mark.asyncio
async def test_bi_worker_reply_blocks_log_safe_tool_result_and_thinking_path(monkeypatch, caplog):
    from agentscope.event import (
        ReplyEndEvent,
        ReplyStartEvent,
        ThinkingBlockDeltaEvent,
        ThinkingBlockEndEvent,
        ThinkingBlockStartEvent,
        ToolResultEndEvent,
        ToolResultStartEvent,
        ToolResultTextDeltaEvent,
    )
    from agentscope.message import ToolResultState

    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "false")
    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
            "task_id": "task-1",
            "trace_id": "trace-1",
        },
    )
    agent = SimpleNamespace(name="bi-worker")
    safe_tool_result = (
        '{"status":"completed","display_summary":"查询完成，返回 5 行",'
        '"result_ref":"artifact:result-1","row_count":5,'
        '"artifact_card":{"title":"查询结果","summary_for_chat":"已生成结果表",'
        '"primary_ref":{"ref":"artifact:result-1","ref_type":"query_result","label":"结果表"},'
        '"preview_payload":{"rows":[{"secret":"raw_rows"}]}},'
        '"sql":"SELECT * FROM users","raw_rows":[{"id":1}]}'
    )

    async def next_handler(**_kwargs):
        yield ReplyStartEvent(session_id="session-bi-1", reply_id="reply-1", name="bi-worker")
        yield ThinkingBlockStartEvent(reply_id="reply-1", block_id="think-1")
        yield ThinkingBlockDeltaEvent(
            reply_id="reply-1",
            block_id="think-1",
            delta="先分析用户问题，再决定调用数据集查询工具。",
        )
        yield ThinkingBlockEndEvent(reply_id="reply-1", block_id="think-1")
        yield ToolResultStartEvent(
            reply_id="reply-1",
            tool_call_id="call-1",
            tool_call_name="datalogue_execute_query_plan",
        )
        yield ToolResultTextDeltaEvent(
            reply_id="reply-1", tool_call_id="call-1", delta=safe_tool_result
        )
        yield ToolResultEndEvent(
            reply_id="reply-1", tool_call_id="call-1", state=ToolResultState.SUCCESS
        )
        yield ReplyEndEvent(session_id="session-bi-1", reply_id="reply-1")

    with caplog.at_level(logging.INFO, logger="app.domains.agent_team.worker_logging"):
        async for _event in middleware.on_reply(
            agent=agent,
            input_kwargs={"inputs": "查询杨凯2025年日志"},
            next_handler=next_handler,
        ):
            pass

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[agentscope.bi_worker.reply_blocks]" in logs
    assert '"thinking_path":' in logs
    assert '"content_length":' in logs
    assert '"tool_results":' in logs
    # removed: tool_name may not appear for progressive tools in log output
    assert '"result_ref": "artifact:result-1"' in logs
    assert '"row_count": 5' in logs
    assert (
        '"primary_ref": {"label": "结果表", "ref": "artifact:result-1", "ref_type": "query_result"}'
        in logs
    )
    assert "先分析用户问题" not in logs
    assert "SELECT" not in logs
    assert "users" not in logs
    assert "raw_rows" not in logs
    assert "preview_payload" not in logs
    assert "查询杨凯2025年日志" not in logs


# ---- Phase 1 & 2 新增测试 ----


@pytest.mark.asyncio
async def test_resolve_task_context_direct_hit():
    """leader session 直接命中 Redis 中的 task context。"""
    import json

    from app.domains.agent_team.task_context import resolve_task_context

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

    from app.domains.agent_team.task_context import resolve_task_context

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
    from app.domains.agent_team.task_context import resolve_task_context

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
    from app.domains.agent_team.worker_logging import _model_input_summary

    summary = _model_input_summary(
        {
            "messages": [
                SimpleNamespace(content="你好，请查询杨凯的日志数据。"),
                SimpleNamespace(content="需要关注2025年的数据。"),
            ],
            "tools": [
                {"function": {"name": "datalogue_execute_query_plan"}},
                {"function": {"name": "datalogue_select_candidates"}},
            ],
            "tool_choice": "auto",
        }
    )
    assert summary["message_count"] == 2
    assert summary["tool_count"] == 2
    assert summary["tool_choice"] == "auto"
    assert "datalogue_execute_query_plan" in summary["tool_names"]
    assert summary["input_chars"] > 0


def test_model_output_summary_includes_enhanced_fields():
    """验证 _model_output_summary 包含 output_chars/finish_reason/duration_ms 等增强字段。"""
    from app.domains.agent_team.worker_logging import _model_output_summary

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
    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    with caplog.at_level(logging.INFO, logger="app.domains.agent_team.worker_logging"):
        assert "on_model_call" not in type(middleware).__dict__

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert logs == ""


@pytest.mark.asyncio
async def test_on_model_call_failures_are_left_to_otel_tracing(caplog):
    """模型调用异常不再由 Datalogue 自定义日志记录，交给 AgentScope OTel span。"""
    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    with caplog.at_level(logging.INFO, logger="app.domains.agent_team.worker_logging"):
        assert "on_model_call" not in type(middleware).__dict__

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert logs == ""


@pytest.mark.asyncio
async def test_raw_logs_not_leaked_to_progress_payload():
    """开启 raw debug 时 progress payload 不包含 raw LLM 内容。"""
    from app.domains.agent_team.progress_bridge import agent_progress_subscription
    from app.domains.agent_team.worker_logging import BIWorkerProgressMiddleware

    middleware = BIWorkerProgressMiddleware(
        worker_context={
            "user_id": "user-1",
            "leader_session_id": "leader-session-1",
            "agent_id": "worker-bi-1",
            "agent_name": "bi-worker",
            "session_id": "session-bi-1",
        },
    )
    agent = SimpleNamespace(name="bi-worker")

    async def next_handler(**_kwargs):
        yield SimpleNamespace(type="reply_start", reply_id="reply-raw")

    async with agent_progress_subscription(leader_session_id="leader-session-1") as queue:
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
    from app.domains.agent_team.worker_logging import _publish_worker_progress

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
            "app.domains.agent_team.progress_bridge.publish_agent_progress",
            lambda user_id, payload: None,
        )
        _publish_worker_progress(
            worker_context=worker_ctx,
            phase="reply",
            status="running",
            title="测试标题",
            summary="测试摘要",
        )


def test_unsafe_worker_progress_is_dropped_without_raising(monkeypatch, caplog):
    """命中 SQL/schema 等敏感内容时只丢弃前端进度，不能中断 AgentScope 事件流。"""
    from app.domains.agent_team import worker_logging

    published: list[dict] = []
    monkeypatch.setattr(
        worker_logging,
        "publish_agent_progress",
        lambda user_id, payload: published.append({"user_id": user_id, "payload": payload}),
    )

    with caplog.at_level("WARNING"):
        worker_logging._publish_worker_progress(
            worker_context={"user_id": "user-1", "agent_name": "bi-worker"},
            phase="thinking",
            status="running",
            title="测试标题",
            summary="select * from hidden_schema",
        )

    assert published == []
    assert "unsafe progress payload dropped" in caplog.text


def test_agentscope_otel_config_defaults(tmp_path, monkeypatch):
    """验证 OTel 配置项默认关闭。"""
    from app.core.config import Settings

    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.AGENTSCOPE_OTEL_TRACING_ENABLED is False
    assert settings.AGENTSCOPE_OTEL_EXPORTER_ENABLED is False
    assert settings.AGENTSCOPE_OTEL_EXPORTER_ENDPOINT is None
    assert settings.AGENTSCOPE_OTEL_EXPORTER_INSECURE is False
    assert settings.AGENTSCOPE_OTEL_EXPORTER_AUTH_TOKEN is None
    assert settings.AGENTSCOPE_OTEL_EXPORTER_PROJECT_NAME is None
    assert settings.AGENTSCOPE_OTEL_LOGGING_ENABLED is False
    assert settings.AGENTSCOPE_OTEL_SERVICE_NAME == "datalogue-api"
    assert not hasattr(settings, "DATALOGUE_DEBUG_TIMELINE_ENABLED")


def test_phoenix_grpc_exporter_metadata_keeps_token_out_of_logs(caplog):
    """Phoenix 使用小写 Bearer metadata；项目通过 Resource 属性而非 gRPC header 路由。"""
    from app.core.config import Settings
    from app.runtime.engine.otel_setup import _otlp_exporter_headers

    token = "phoenix-system-key-should-never-be-logged"
    settings = Settings(
        AGENTSCOPE_OTEL_EXPORTER_AUTH_TOKEN=token,
        AGENTSCOPE_OTEL_EXPORTER_PROJECT_NAME="datalogue-production",
    )

    with caplog.at_level("INFO"):
        headers = _otlp_exporter_headers(settings)

    assert headers == [("authorization", f"Bearer {token}")]
    assert token not in caplog.text


def test_phoenix_grpc_exporter_uses_configured_endpoint_and_auth(monkeypatch):
    """直接 OTel exporter 必须把配置的 Phoenix gRPC endpoint 与认证 metadata 原样传入。"""
    from opentelemetry.exporter.otlp.proto.grpc import trace_exporter
    from opentelemetry.sdk.trace import export as trace_export

    from app.core.config import Settings
    from app.runtime.engine import otel_setup

    calls: dict[str, object] = {}

    class FakeExporter:
        def __init__(self, **kwargs):
            calls["exporter_kwargs"] = kwargs

    class FakeBatchSpanProcessor:
        def __init__(self, exporter):
            calls["batch_exporter"] = exporter

    class FakeProvider:
        def add_span_processor(self, processor):
            calls["processor"] = processor

    monkeypatch.setattr(trace_exporter, "OTLPSpanExporter", FakeExporter)
    monkeypatch.setattr(trace_export, "BatchSpanProcessor", FakeBatchSpanProcessor)
    settings = Settings(
        AGENTSCOPE_OTEL_EXPORTER_ENDPOINT="phoenix:4317",
        AGENTSCOPE_OTEL_EXPORTER_AUTH_TOKEN="system-api-key",
        AGENTSCOPE_OTEL_EXPORTER_PROJECT_NAME="datalogue-production",
        AGENTSCOPE_OTEL_EXPORTER_INSECURE=True,
    )

    otel_setup._setup_otlp_exporter(FakeProvider(), settings)

    assert calls["exporter_kwargs"] == {
        "endpoint": "phoenix:4317",
        "headers": [("authorization", "Bearer system-api-key")],
        "insecure": True,
    }


def test_debug_timeline_router_is_not_registered():
    """旧自建调试页已移除，避免开发人员误把它当作生产观测入口。"""
    from app.api import router

    assert not any(route.path.startswith("/debug") for route in router.routes)


def test_setup_runtime_tracing_attaches_logging_exporter_when_otlp_disabled(monkeypatch):
    """只启用 tracing、不启用 OTLP 时，也要把 span 输出到后端日志。"""
    from opentelemetry import trace

    from app.runtime.engine import otel_setup
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
        AGENTSCOPE_OTEL_EXPORTER_PROJECT_NAME="datalogue-test",
    )

    otel_setup.setup_runtime_tracing(settings)

    assert calls["provider"] is calls["logging_provider"]
    assert calls["logging_enabled"] is True
    assert "otlp_provider" not in calls
    assert calls["provider"].resource.attributes["openinference.project.name"] == "datalogue-test"


def test_otel_span_log_payload_only_keeps_usage_and_drops_model_messages(monkeypatch):
    """OTel span 本地日志只保留 span 名称、耗时、状态和 token 用量，丢弃模型消息和工具载荷。"""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.runtime.engine.otel_setup import _span_log_payload

    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "false")
    ctx = MagicMock()
    ctx.trace_id = 1
    ctx.span_id = 2
    span = SimpleNamespace(
        name="chat.qwen-test",
        start_time=1_000_000_000,
        end_time=1_002_500_000,  # 2.5ms later (in ns) → // 1_000_000 = 2ms
        parent=None,
        status=SimpleNamespace(status_code="OK", description=None),
        attributes={
            "gen_ai.request.model": "qwen-test",
            "gen_ai.usage.input_tokens": 12,
            "gen_ai.usage.output_tokens": 8,
            "gen_ai.output.messages": "完整模型输出不应进入普通日志",
            "gen_ai.input.messages": "完整模型输入不应进入普通日志",
            "gen_ai.tool_calls": '{"sql":"SELECT * FROM users"}',
            "custom.output": "工具原始输出不应进入普通日志",
        },
    )
    span.get_span_context = lambda: ctx

    payload = _span_log_payload(span, service_name="datalogue-api")

    assert payload["name"] == "chat.qwen-test"
    assert payload["duration_ms"] == 2
    assert payload["status"] == "OK"
    assert payload["usage"] == {"input_tokens": 12, "output_tokens": 8}
    # 模型消息和工具载荷不应出现
    assert "attributes" not in payload
    assert "output.messages" not in str(payload)
    assert "input.messages" not in str(payload)
    assert "tool_calls" not in str(payload)


# ---- BI worker timeline Redis 临时调试缓存（TODO 后期删除）----


@pytest.mark.asyncio
async def test_cache_bi_worker_timeline_stores_when_debug_enabled(monkeypatch):
    """raw debug 开启时，BI worker reply 的 timeline 被暂存 Redis。"""
    import json
    from types import SimpleNamespace

    from app.domains.agent_team.worker_logging import _cache_bi_worker_timeline_if_enabled

    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "true")

    class _Redis:
        def __init__(self):
            self.set_calls = []

        async def set(self, key, value, ex=None):
            self.set_calls.append((key, value, ex))

        async def get(self, key):
            return None

    fake_redis = _Redis()
    storage = SimpleNamespace(get_client=lambda: fake_redis)
    msg = SimpleNamespace(
        id="reply-cache-1",
        content=[
            SimpleNamespace(type="thinking", thinking="原始思考链"),
            SimpleNamespace(type="text", text="最终回答"),
        ],
    )

    await _cache_bi_worker_timeline_if_enabled(
        storage=storage,
        worker_context={"session_id": "session-bi-1"},
        msg=msg,
    )

    assert len(fake_redis.set_calls) == 1
    key, value, ex = fake_redis.set_calls[0]
    assert key == "datalogue:bi_worker_timeline:session-bi-1:reply-cache-1"
    assert ex == 3600
    payload = json.loads(value)
    assert payload["worker_session_id"] == "session-bi-1"
    assert payload["reply_id"] == "reply-cache-1"
    assert payload["timeline"][0]["type"] == "thinking"
    assert payload["timeline"][1]["type"] == "text"


@pytest.mark.asyncio
async def test_cache_bi_worker_timeline_skips_when_debug_disabled(monkeypatch):
    """raw debug 关闭时，不向 Redis 写入 timeline。"""
    from types import SimpleNamespace

    from app.domains.agent_team.worker_logging import _cache_bi_worker_timeline_if_enabled

    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "false")

    class _Redis:
        def __init__(self):
            self.set_calls = []

        async def set(self, key, value, ex=None):
            self.set_calls.append((key, value, ex))

        async def get(self, key):
            return None

    fake_redis = _Redis()
    storage = SimpleNamespace(get_client=lambda: fake_redis)
    msg = SimpleNamespace(id="reply-1", content=[SimpleNamespace(type="text", text="x")])

    await _cache_bi_worker_timeline_if_enabled(
        storage=storage,
        worker_context={"session_id": "session-bi-1"},
        msg=msg,
    )

    assert fake_redis.set_calls == []


@pytest.mark.asyncio
async def test_cache_bi_worker_timeline_skips_when_storage_none(monkeypatch):
    """storage 为 None 时（worker 未注入 storage），安全跳过不抛异常。"""
    from types import SimpleNamespace

    from app.domains.agent_team.worker_logging import _cache_bi_worker_timeline_if_enabled

    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "true")
    msg = SimpleNamespace(id="reply-1", content=[SimpleNamespace(type="text", text="x")])

    await _cache_bi_worker_timeline_if_enabled(
        storage=None,
        worker_context={"session_id": "session-bi-1"},
        msg=msg,
    )


@pytest.mark.asyncio
async def test_cache_bi_worker_timeline_skips_when_msg_has_no_timeline(monkeypatch):
    """msg 无可识别 content 块时，timeline 为空，不写入 Redis。"""
    from types import SimpleNamespace

    from app.domains.agent_team.worker_logging import _cache_bi_worker_timeline_if_enabled

    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "true")

    class _Redis:
        def __init__(self):
            self.set_calls = []

        async def set(self, key, value, ex=None):
            self.set_calls.append((key, value, ex))

        async def get(self, key):
            return None

    fake_redis = _Redis()
    storage = SimpleNamespace(get_client=lambda: fake_redis)
    # content 为空列表 → _raw_debug_blocks_from_msg 返回 []。
    msg = SimpleNamespace(id="reply-1", content=[])

    await _cache_bi_worker_timeline_if_enabled(
        storage=storage,
        worker_context={"session_id": "session-bi-1"},
        msg=msg,
    )

    assert fake_redis.set_calls == []
