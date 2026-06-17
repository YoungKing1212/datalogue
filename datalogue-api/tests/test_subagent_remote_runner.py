# ============================================================
# File Name   : test_subagent_remote_runner.py
# Description:
#   RemoteDatasetSubAgentRunner A2A 协议测试。
#
# Responsibilities:
#   - 验证远端 SubAgent Runner 请求契约和事件流解析。
#   - 验证远端错误会映射为安全内部事件。
#   - 验证认证和 trace context 会透传到远端请求。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.services.runner import DatasetSubAgentRequest, RemoteDatasetSubAgentRunner


class FakeTraceContext:
    trace_id = "trace-test"
    root_observation_id = "obs-root"


def _request() -> DatasetSubAgentRequest:
    return DatasetSubAgentRequest(
        question="查询销售额",
        dataset_id=10,
        manifest_version="manifest-v1",
        bound_schema_version="schema-v1",
        thread_id="thread-1",
        time_context={"today": "2026-06-17"},
        thread_context={"turn_index": 2},
        route_decision={"decision": "selected"},
        schema_status={"status": "ready"},
        lead_agent_context={"resolved_question": "查询销售额"},
        trace_id="trace-test",
        parent_observation_id="obs-parent",
    )


async def _collect(runner: RemoteDatasetSubAgentRunner):
    return [
        event
        async for event in runner.run(
            _request(),
            FakeTraceContext(),
            {"question": "查询销售额"},
            dataset_name="销售数据集",
        )
    ]


def test_remote_runner_posts_request_and_streams_events():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        body = "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "result",
                        "payload": {"final_state": {"answer": "ok"}},
                    }
                ),
                "",
            ]
        )
        return httpx.Response(200, content=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runner = RemoteDatasetSubAgentRunner(
        base_url="https://sub.example/api",
        api_key="secret",
        client=client,
    )

    events = asyncio.run(_collect(runner))
    asyncio.run(client.aclose())

    assert events == [
        {
            "event_type": "result",
            "payload": {"final_state": {"answer": "ok"}},
        }
    ]
    assert captured["headers"]["x-datalogue-internal-token"] == "secret"
    assert captured["url"] == "https://sub.example/api/internal/subagent/run"
    assert captured["payload"]["request"]["dataset_id"] == 10
    assert captured["payload"]["request"]["trace_id"] == "trace-test"
    assert captured["payload"]["request"]["parent_observation_id"] == "obs-parent"
    assert captured["payload"]["initial_state"] == {"question": "查询销售额"}
    assert captured["payload"]["dataset_name"] == "销售数据集"


def test_remote_runner_maps_http_error_to_safe_event():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"internal_table stacktrace")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runner = RemoteDatasetSubAgentRunner(
        base_url="https://sub.example/api",
        client=client,
    )

    events = asyncio.run(_collect(runner))
    asyncio.run(client.aclose())

    assert events[0]["event_type"] == "result"
    final_state = events[0]["payload"]["final_state"]
    assert final_state["error"] == "remote_subagent_error"
    assert final_state["raw_error"] == "remote subagent request failed with status 500"
    assert "internal_table" not in json.dumps(events, ensure_ascii=False)


def test_remote_runner_requires_api_base_url():
    try:
        RemoteDatasetSubAgentRunner(base_url="https://sub.example")
    except ValueError as exc:
        assert "must include /api" in str(exc)
    else:
        raise AssertionError("expected base_url validation error")
