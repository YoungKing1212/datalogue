# ============================================================
# File Name   : test_agentic_shell_task_runtime.py
# Description:
#   Agentic Shell Task Runtime 生命周期测试。
#
# Responsibilities:
#   - 验证 runtime 创建 task、AgentScope mirror message，并输出 task/message 完成事件。
#   - 验证 runtime 异常时写入 task.failed，且不泄露内部执行态。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

import pytest

from app.models.agentic_shell_task import AgenticShellTask
from app.schemas.agentic_shell_task import AgenticShellTaskRequest
from app.runtime import AgenticShellTaskRuntime


class FakeAgentScopeRunner:
    async def stream(self, *, request, task, user_msg):
        yield type("DeltaEvent", (), {"delta": "合同总金额为 100 万元"})()


class FailingAgentScopeRunner:
    async def stream(self, *, request, task, user_msg):
        if False:
            yield None
        raise RuntimeError("select * from hidden_table")


@pytest.mark.asyncio
async def test_agentic_shell_task_runtime_completes_task(db_session):
    runtime = AgenticShellTaskRuntime(db=db_session, runner=FakeAgentScopeRunner())
    request = AgenticShellTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="统计合同总金额",
        dataset_id=12,
        session_id="assistant-thread-1",
    )

    events = [event async for event in runtime.stream(request)]

    assert [event.event_type for event in events] == [
        "task.started",
        "agent.selected",
        "message.delta",
        "message.completed",
        "task.completed",
    ]
    stored = db_session.query(AgenticShellTask).filter_by(task_id=events[0].task_id).one()
    assert stored.status == "completed"
    assert stored.selected_agent == "bi_agent"


@pytest.mark.asyncio
async def test_agentic_shell_task_runtime_fails_closed(db_session):
    runtime = AgenticShellTaskRuntime(db=db_session, runner=FailingAgentScopeRunner())
    request = AgenticShellTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="统计合同总金额",
        dataset_id=12,
    )

    events = [event async for event in runtime.stream(request)]

    assert events[-1].event_type == "task.failed"
    assert "select" not in str(events[-1].payload).lower()
    stored = db_session.query(AgenticShellTask).filter_by(task_id=events[0].task_id).one()
    assert stored.status == "failed"
