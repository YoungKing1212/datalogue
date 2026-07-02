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
from app.schemas.bi_lead_agent import BILeadAgentHandoffResult
from app.services.agentic_shell_task_runtime import AgenticShellTaskRuntime, BILeadAgentTaskRunner


class FakeAgentScopeRunner:
    async def stream(self, *, request, task, user_msg):
        yield type("DeltaEvent", (), {"delta": "合同总金额为 100 万元"})()


class FailingAgentScopeRunner:
    async def stream(self, *, request, task, user_msg):
        if False:
            yield None
        raise RuntimeError("select * from hidden_table")


class FakeBIRunService:
    def __init__(self, db):
        self.db = db

    def create_run(self, question, trace_id=None, task_id=None):
        return type(
            "FakeBILeadRun",
            (),
            {
                "id": 88,
                "question": question,
                "trace_id": trace_id,
                "task_id": task_id,
            },
        )()


class FakeBIConfirmationService:
    def __init__(self, db):
        self.db = db
        self.requests = []

    def confirm(self, run_id, request):
        self.requests.append((run_id, request))
        return type("FakeBIConfirmation", (), {"id": 99})()


class FakeBIHandoffService:
    async def query_dataset(self, *, run_id):
        return BILeadAgentHandoffResult(
            handoff_id="handoff-1",
            dataset_id=12,
            task_id="task-agentic-test",
            trace_id="trace-agentic-test",
            handoff_status="completed",
            answer_summary="合同总金额为 100 万元",
            artifact_ref="artifact:safe",
            checkpoint_ref="checkpoint:safe",
            row_count=1,
            column_count=2,
        )


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
    assert stored.selected_agent == "bi_lead_agent"


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


@pytest.mark.asyncio
async def test_bi_lead_agent_task_runner_handoffs_dataset_without_legacy_planner(db_session):
    confirmation_service = FakeBIConfirmationService(db_session)
    runner = BILeadAgentTaskRunner(
        db=db_session,
        run_service_factory=FakeBIRunService,
        confirmation_service_factory=lambda db: confirmation_service,
        handoff_service_factory=lambda db: FakeBIHandoffService(),
    )
    runtime = AgenticShellTaskRuntime(db=db_session, runner=runner)
    request = AgenticShellTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="统计合同总金额",
        dataset_id=12,
    )

    events = [event async for event in runtime.stream(request)]

    event_types = [event.event_type for event in events]
    assert event_types == [
        "task.started",
        "agent.selected",
        "agent.handoff.started",
        "artifact.created",
        "message.completed",
        "task.completed",
    ]
    assert events[-2].payload["summary"] == "合同总金额为 100 万元"
    assert events[-2].payload["artifact_ref"] == "artifact:safe"
    assert "tool_planner" not in str([event.payload for event in events])
    assert "skill_selector" not in str([event.payload for event in events])
    assert confirmation_service.requests[0][1].capability_snapshot.dataset_id == 12
