# ============================================================
# File Name   : test_agent_team_stream_api.py
# Description:
#   Agent Team SSE API 入口测试。
#
# Responsibilities:
#   - 验证 /api/agent-team/tasks/stream 能把 runtime envelope 输出为 SSE data。
#   - 验证接口失败流只返回安全错误摘要，不泄露 SQL 或内部表名。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

import json

import pytest
from sse_starlette.sse import AppStatus

from app.core.config import get_settings
from app.core import models


class FakeAgentScopeStreamRunner:
    """模拟 AgentScope Service runner，避免接口测试依赖真实外部服务。"""

    async def stream(self, *, request, task, user_msg):
        yield type("DeltaEvent", (), {"delta": "合同总金额为 100 万元"})()


class FailingAgentScopeStreamRunner:
    """模拟下游执行失败，用于验证 API 层仍保持用户可见安全边界。"""

    async def stream(self, *, request, task, user_msg):
        # 保持 async generator 形态，确保 runtime 走真实的流式消费分支后再进入异常处理。
        if False:
            yield None
        raise RuntimeError("select * from hidden_table")


@pytest.fixture(autouse=True)
def disable_auto_title_for_stream_api_tests(monkeypatch):
    """SSE API 测试只验证任务流协议，关闭后台标题生成避免 DB teardown 并发副作用。"""

    monkeypatch.setenv("DATALOGUE_AUTO_TITLE_ENABLED", "false")
    get_settings.cache_clear()
    # sse-starlette 的退出事件是模块级全局对象；TestClient 每个用例有独立 event loop，必须隔离。
    AppStatus.should_exit = False
    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit = False
    AppStatus.should_exit_event = None
    get_settings.cache_clear()


def _read_sse_payloads(response) -> list[dict]:
    body = "".join(response.iter_text())
    payloads: list[dict] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        raw_payload = line.removeprefix("data: ").strip()
        try:
            payloads.append(json.loads(raw_payload))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"SSE data 不是合法 JSON: {raw_payload}") from exc
    return payloads


def _event_by_type(payloads: list[dict], event_type: str) -> dict:
    for payload in payloads:
        if payload["event_envelope"]["event_type"] == event_type:
            return payload
    raise AssertionError(f"SSE 流缺少事件: {event_type}")


def test_agent_team_tasks_stream_api_emits_sse_events(client, sample_dataset, monkeypatch):
    runner_builds: list[dict] = []

    def fake_build_runner(*, base_url, db):
        # 入口层必须负责把请求上下文转换成 AgentScope runner 依赖；这里记录下来防止绕过 API 装配。
        runner_builds.append({"base_url": base_url, "db": db})
        return FakeAgentScopeStreamRunner()

    monkeypatch.setattr("app.api.agent_team.build_agent_team_task_runner", fake_build_runner)

    with client.stream(
        "POST",
        "/api/agent-team/tasks/stream",
        json={
            "task_source": "chat",
            "task_type": "bi_query",
            "question": "统计合同总金额",
            "dataset_id": sample_dataset.id,
            "session_id": "assistant-thread-api-test",
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        payloads = _read_sse_payloads(response)

    assert payloads, "SSE 流未产生任何事件"
    event_types = [item["event_envelope"]["event_type"] for item in payloads]
    assert event_types == [
        "task.started",
        "agent.selected",
        "message.delta",
        "message.completed",
        "task.completed",
    ]
    assert runner_builds and runner_builds[0]["base_url"].startswith("http")
    assert payloads[0]["task_id"].startswith("task-agent-team-")
    assert _event_by_type(payloads, "message.delta")["event_envelope"]["payload"]["content"] == (
        "合同总金额为 100 万元"
    )
    assert _event_by_type(payloads, "message.completed")["event_envelope"]["legacy_payload"] == {
        "type": "final",
        "answer": "合同总金额为 100 万元",
    }


def test_agent_team_tasks_stream_api_fails_closed(client, sample_dataset, monkeypatch):
    def fake_build_runner(*, base_url, db):
        return FailingAgentScopeStreamRunner()

    monkeypatch.setattr("app.api.agent_team.build_agent_team_task_runner", fake_build_runner)

    with client.stream(
        "POST",
        "/api/agent-team/tasks/stream",
        json={
            "task_source": "chat",
            "task_type": "bi_query",
            "question": "统计合同总金额",
            "dataset_id": sample_dataset.id,
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        payloads = _read_sse_payloads(response)

    assert payloads, "SSE 流未产生任何事件"
    failed_event = _event_by_type(payloads, "task.failed")
    final_payload = failed_event["event_envelope"]["payload"]
    response_text = json.dumps(payloads, ensure_ascii=False).lower()
    assert final_payload == {
        "error_code": "AGENT_TEAM_TASK_FAILED",
        "error_summary": "Agent Team 任务执行失败，内部细节已隐藏。",
        "retryable": True,
    }
    assert "select * from hidden_table" not in response_text
    assert "hidden_table" not in response_text


def test_agent_team_tasks_stream_rejects_foreign_conversation_before_sse(
    client,
    db_session,
    sample_dataset,
):
    """任务入口必须在建立 SSE 前拒绝其他用户的 conversation_id。"""

    foreign_conversation = models.Conversation(
        title="他人任务会话",
        user_id=2,
        archived=False,
    )
    db_session.add(foreign_conversation)
    db_session.commit()

    response = client.post(
        "/api/agent-team/tasks/stream",
        json={
            "task_source": "chat",
            "task_type": "bi_query",
            "question": "读取他人会话",
            "dataset_id": sample_dataset.id,
            "conversation_id": foreign_conversation.id,
        },
    )

    assert response.status_code == 404
