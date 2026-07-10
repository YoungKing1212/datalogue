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

from app.core.config import get_settings
from app.core.models.agent_team_task import AgentTeamTask
from app.core.schemas.agentscope_agent_team_task import AgentTeamTaskRequest
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


class InternalPlanningDatasetAgentScopeRunner:
    async def stream(self, *, request, task, user_msg):
        yield {
            "event_type": "ReplyEndEvent",
            "payload": {
                "summary": (
                    "TheuserwantstoqueryYangKai's2025worklogs(工作日志)."
                    "ThisisaBI(BusinessIntelligence)querytask."
                    "Letmebreakthisdown:1.ThetaskisaBIquery-查询杨凯2025年的工作日志"
                    "2.IneedtocreateateamwithaBIworkertohandlethisquery."
                ),
                "datalogue_event_type": "dataset_candidates",
                "route_decision": {
                    "decision": "ambiguous",
                    "dataset_id": None,
                    "candidates": [
                        {
                            "dataset_id": 12,
                            "dataset_name": "运营双周会议数据集",
                            "reason": "名称或描述与「工作日志」匹配",
                            "requires_confirmation": True,
                        },
                        {
                            "dataset_id": 10,
                            "dataset_name": "生产经营管理系统日志数据集",
                            "reason": "名称或描述与「工作日志」匹配",
                            "requires_confirmation": True,
                        },
                    ],
                },
                "clarification": {
                    "kind": "dataset_choice",
                    "candidates": [
                        {
                            "dataset_id": 12,
                            "dataset_name": "运营双周会议数据集",
                            "reason": "名称或描述与「工作日志」匹配",
                        },
                        {
                            "dataset_id": 10,
                            "dataset_name": "生产经营管理系统日志数据集",
                            "reason": "名称或描述与「工作日志」匹配",
                        },
                    ],
                },
            },
        }


class ArtifactFinalAgentScopeRunner:
    async def stream(self, *, request, task, user_msg):
        yield {
            "event_type": "ReplyEndEvent",
            "payload": {
                "summary": "查询已完成，共 100 行、48 列。",
                "row_count": 100,
                "column_count": 48,
                "artifact_card": {
                    "title": "查询结果",
                    "status": "completed",
                    "summary_for_chat": "查询已完成，共 100 行、48 列。",
                    "primary_ref": {
                        "ref_id": "artifact:worker-1",
                        "ref_type": "result",
                        "label": "查询结果",
                    },
                },
            },
        }


@pytest.fixture(autouse=True)
def disable_auto_title_for_runtime_unit_tests(monkeypatch):
    """Runtime 单元测试不验证标题生成，默认关闭后台 DB 线程以避免 teardown 并发副作用。"""

    monkeypatch.setenv("DATALOGUE_AUTO_TITLE_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
    final_payload = events[3].payload
    assert final_payload["reasoning_summary"] == [
        {
            "title": "识别任务",
            "summary": "已识别为「BI 查询」任务，问题为「统计合同总金额」。",
            "status": "completed",
        },
        {
            "title": "整理回答",
            "summary": "合同总金额为 100 万元",
            "status": "completed",
        },
    ]
    stored = db_session.query(AgentTeamTask).filter_by(task_id=events[0].task_id).one()
    assert stored.status == "completed"
    assert stored.selected_agent == "agent_team_leader"
    assert stored.final_payload_json["reasoning_summary"][0]["title"] == "识别任务"


@pytest.mark.asyncio
async def test_agent_team_task_runtime_skips_auto_title_when_disabled(
    db_session,
    monkeypatch,
):
    calls: list[tuple[str, str, str]] = []

    def fake_auto_title(thread_id, user_message, assistant_response, **_kwargs):
        calls.append((thread_id, user_message, assistant_response))

    monkeypatch.setenv("DATALOGUE_AUTO_TITLE_ENABLED", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.domains.agent_team.title_generator.maybe_auto_title_async",
        fake_auto_title,
    )
    runtime = AgentTeamTaskRuntime(db=db_session, runner=FakeAgentScopeRunner())
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="统计合同总金额",
        dataset_id=12,
    )

    try:
        events = [event async for event in runtime.stream(request)]
    finally:
        get_settings.cache_clear()

    assert events[-1].event_type == "task.completed"
    assert calls == []


@pytest.mark.asyncio
async def test_agent_team_task_runtime_lets_bi_worker_report_dataset_candidates(db_session, sample_datasource):
    from app.core.models.dataset import SemanticDataset

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
    assert final_payload["summary"].startswith("已筛选出可能匹配的候选数据集")
    assert final_payload["original_question"] == "查询杨凯2025年日志"
    assert "数据集 1：生产经营管理系统日志数据集" in final_payload["summary"]
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
    assert stored.final_payload_json["answer_summary"] == final_payload["summary"]


@pytest.mark.asyncio
async def test_agent_team_task_runtime_sanitizes_internal_planning_final_answer(db_session):
    runtime = AgentTeamTaskRuntime(db=db_session, runner=InternalPlanningDatasetAgentScopeRunner())
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询杨凯2025年日志",
        dataset_id=None,
    )

    events = [event async for event in runtime.stream(request)]

    final_event = next(event for event in events if event.event_type == "message.completed")
    final_payload = final_event.payload
    final_text = final_payload["summary"]
    reasoning_text = str(final_payload["reasoning_summary"])
    assert "Theuserwantstoquery" not in final_text
    assert "Ineedtocreate" not in final_text
    assert "Theuserwantstoquery" not in reasoning_text
    assert "Ineedtocreate" not in reasoning_text
    assert "已筛选出可能匹配的候选数据集" in final_text
    assert "数据集 10：生产经营管理系统日志数据集" in final_text
    assert final_payload["route_decision"]["decision"] == "ambiguous"
    assert final_payload["clarification"]["kind"] == "dataset_choice"
    assert final_event.legacy_payload == {"type": "final", "answer": final_text}
    stored = db_session.query(AgentTeamTask).filter_by(task_id=events[0].task_id).one()
    assert stored.final_payload_json["answer_summary"] == final_text


@pytest.mark.asyncio
async def test_agent_team_task_runtime_adds_reasoning_summary_for_final_artifact(db_session):
    runtime = AgentTeamTaskRuntime(db=db_session, runner=ArtifactFinalAgentScopeRunner())
    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="查询杨凯2025年日志",
        dataset_id=10,
    )

    events = [event async for event in runtime.stream(request)]

    final_payload = next(event.payload for event in events if event.event_type == "message.completed")
    assert final_payload["reasoning_summary"] == [
        {
            "title": "识别任务",
            "summary": "已识别为「BI 查询」任务，问题为「查询杨凯2025年日志」。",
            "status": "completed",
        },
        {
            "title": "生成结果",
            "summary": "已生成可查看的查询结果。",
            "status": "completed",
            "ref": "artifact:worker-1",
            "row_count": 100,
            "column_count": 48,
        },
        {
            "title": "整理回答",
            "summary": "查询已完成，共 100 行、48 列。",
            "status": "completed",
        },
    ]


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
