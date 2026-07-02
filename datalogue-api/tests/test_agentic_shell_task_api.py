# ============================================================
# File Name   : test_agentic_shell_task_api.py
# Description:
#   Agentic Shell task stream API 测试。
#
# Responsibilities:
#   - 验证 /api/agentic-shell/tasks/stream 返回 SSE envelope。
#   - 验证 API response 使用 task_id 而不是旧 /chat/stream final payload 作为主语。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

import json


class FakeApiRunner:
    async def stream(self, *, request, task, user_msg):
        yield type("DeltaEvent", (), {"delta": "合同总金额为 100 万元"})()


def _sse_payloads(response):
    payloads = []
    for line in response.text.splitlines():
        if line.startswith("data:"):
            payloads.append(json.loads(line.removeprefix("data:").strip()))
    return payloads


def test_agentic_shell_task_stream_returns_task_envelopes(client, monkeypatch):
    from app.api import agentic_shell

    monkeypatch.setattr(agentic_shell, "build_agentic_shell_task_runner", lambda db: FakeApiRunner())

    response = client.post(
        "/api/agentic-shell/tasks/stream",
        json={
            "task_source": "chat",
            "task_type": "bi_query",
            "question": "统计合同总金额",
            "dataset_id": 12,
        },
    )

    assert response.status_code == 200
    payloads = _sse_payloads(response)
    event_types = [payload["event_envelope"]["event_type"] for payload in payloads]
    assert "task.started" in event_types
    assert "agent.selected" in event_types
    assert "task.completed" in event_types
    assert payloads[0]["task_id"].startswith("task-agentic-")


def test_agentic_shell_default_runner_is_not_legacy_chat_runtime(db_session):
    from app.api.agentic_shell import build_agentic_shell_task_runner
    from app.services.agentic_shell_task_runtime import BILeadAgentTaskRunner

    runner = build_agentic_shell_task_runner(db_session)

    assert isinstance(runner, BILeadAgentTaskRunner)
