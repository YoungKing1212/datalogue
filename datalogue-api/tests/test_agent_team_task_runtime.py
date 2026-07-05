# ============================================================
# File Name   : test_agent_team_task_runtime.py
# Description:
#   AgentScope Agent Team Task Runtime 生命周期测试。
#
# Responsibilities:
#   - 验证 runtime 创建 task、AgentScope mirror message，并输出 task/message 完成事件。
#   - 验证 runtime 异常时写入 task.failed，且不泄露内部执行态。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

import logging

import pytest

from app.models.agent_team_task import AgentTeamTask
from app.schemas.agentscope_agent_team_task import AgentTeamTaskRequest
from app.runtime import AgentTeamTaskRuntime


class FakeAgentScopeRunner:
    async def stream(self, *, request, task, user_msg):
        yield type("DeltaEvent", (), {"delta": "合同总金额为 100 万元"})()


class FailingAgentScopeRunner:
    async def stream(self, *, request, task, user_msg):
        if False:
            yield None
        raise RuntimeError("select * from hidden_table")


class MissingDatasetAgentScopeRunner:
    def __init__(self):
        self.called = False

    async def stream(self, *, request, task, user_msg):
        self.called = True
        yield {
            "event_type": "ReplyEndEvent",
            "payload": {
                "summary": "BI worker 已筛选候选数据集，请用户确认。",
                "datalogue_event_type": "dataset_candidates",
                "route_decision": {
                    "decision": "ambiguous",
                    "dataset_id": None,
                    "candidates": [
                        {
                            "dataset_id": 1,
                            "dataset_name": "生产经营管理系统日志数据集",
                            "reason": "匹配日志查询",
                            "requires_confirmation": True,
                        }
                    ],
                },
                "clarification": {
                    "kind": "dataset_choice",
                    "candidates": [
                        {
                            "dataset_id": 1,
                            "dataset_name": "生产经营管理系统日志数据集",
                            "reason": "匹配日志查询",
                        }
                    ],
                },
            },
        }


@pytest.mark.asyncio
async def test_agent_team_task_runtime_completes_task(db_session):
    runtime = AgentTeamTaskRuntime(db=db_session, runner=FakeAgentScopeRunner())
    request = AgentTeamTaskRequest(
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
    stored = db_session.query(AgentTeamTask).filter_by(task_id=events[0].task_id).one()
    assert stored.status == "completed"
    assert stored.selected_agent == "agent_team_leader"


@pytest.mark.asyncio
async def test_agent_team_task_runtime_lets_bi_worker_report_dataset_candidates(db_session, sample_datasource):
    from app.models.dataset import SemanticDataset

    db_session.add_all(
        [
            SemanticDataset(
                name="生产经营管理系统日志数据集",
                datasource_id=sample_datasource.id,
                description="用于查询人员工作日志。",
                status="active",
            ),
            SemanticDataset(
                name="运营双周会议数据集",
                datasource_id=sample_datasource.id,
                description="用于统计会议记录。",
                status="active",
            ),
        ]
    )
    db_session.commit()
    runner = MissingDatasetAgentScopeRunner()
    runtime = AgentTeamTaskRuntime(db=db_session, runner=runner)
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询杨凯2025年日志",
        dataset_id=None,
    )

    events = [event async for event in runtime.stream(request)]

    assert runner.called is True
    assert [event.event_type for event in events] == [
        "task.started",
        "agent.selected",
        "message.completed",
        "task.completed",
    ]
    final_payload = events[2].payload
    assert final_payload["summary"] == "BI worker 已筛选候选数据集，请用户确认。"
    assert final_payload["route_decision"]["decision"] == "ambiguous"
    assert final_payload["clarification"]["kind"] == "dataset_choice"
    assert final_payload["route_decision"]["candidates"] == [
        {
            "dataset_id": 1,
            "dataset_name": "生产经营管理系统日志数据集",
            "reason": "匹配日志查询",
            "requires_confirmation": True,
        }
    ]
    stored = db_session.query(AgentTeamTask).filter_by(task_id=events[0].task_id).one()
    assert stored.status == "completed"
    assert stored.final_payload_json["answer_summary"] == "BI worker 已筛选候选数据集，请用户确认。"


@pytest.mark.asyncio
async def test_agent_team_task_runtime_fails_closed(db_session, caplog):
    runtime = AgentTeamTaskRuntime(db=db_session, runner=FailingAgentScopeRunner())
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="统计合同总金额",
        dataset_id=12,
    )

    with caplog.at_level(logging.ERROR, logger="app.runtime.agent_team_runtime"):
        events = [event async for event in runtime.stream(request)]

    assert events[-1].event_type == "task.failed"
    assert "select" not in str(events[-1].payload).lower()
    assert "RuntimeError" in caplog.text
    assert "select * from hidden_table" in caplog.text
    stored = db_session.query(AgentTeamTask).filter_by(task_id=events[0].task_id).one()
    assert stored.status == "failed"
