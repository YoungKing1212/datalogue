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

import logging

import pytest

from app import models
from app.models.agentscope_workbench import AgentScopeRef
from app.models.agentic_shell_task import AgenticShellTask
from app.schemas.agentic_shell_task import AgenticShellTaskRequest
from app.runtime import AgenticShellTaskRuntime, BIAgentTaskRunner


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


class FakeAgenticDirectQueryRunner:
    def __init__(self, db):
        self.db = db

    async def run(self, *, question, dataset_id, conversation_id=None, trace_id=None):
        return {
            "status": "completed",
            "selected_agent": "bi_agent",
            "summary": "合同总金额为 100 万元",
            "artifact_ref": "artifact:safe",
            "checkpoint_ref": "checkpoint:safe",
            "row_count": 1,
            "column_count": 2,
        }


def _add_dataset(db_session, sample_datasource, name: str):
    dataset = models.SemanticDataset(
        name=name,
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "orders"}], "joins": []},
        description=f"{name} 测试数据集",
        status="active",
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset


def _add_current_manifest(
    db_session,
    *,
    dataset_id: int,
    dataset_name: str,
    domain: str,
    sample_questions: list[str] | None = None,
):
    manifest = models.DatasetSubAgentManifest(
        dataset_id=dataset_id,
        manifest_version="v1",
        bound_schema_version=f"schema-{dataset_id}",
        review_status="current",
        is_current=True,
        manifest_json={
            "auto_fields": {
                "name": dataset_name,
                "permission_scope": {"status": "allowed"},
                "key_metrics": [
                    {"name": "gmv", "display_name": "GMV", "synonyms": ["销售额"]},
                    {"name": "order_count", "display_name": "订单数", "synonyms": ["订单量"]},
                ],
                "key_dimensions": [
                    {"name": "region", "display_name": "地区", "synonyms": ["区域"]},
                ],
            },
            "manual_fields": {
                "description": f"{dataset_name} 用于 {domain} 问数。",
                "business_domain": [domain],
                "sample_questions": sample_questions or [],
                "routing_negative_examples": [],
            },
            "quality": {"status": "passed", "lint": [], "schema_hash": f"schema-{dataset_id}"},
        },
    )
    db_session.add(manifest)
    db_session.commit()
    db_session.refresh(manifest)
    return manifest


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


@pytest.mark.asyncio
async def test_bi_lead_agent_task_runner_queries_dataset_directly_without_native_handoff(db_session):
    confirmation_service = FakeBIConfirmationService(db_session)
    runner = BIAgentTaskRunner(
        db=db_session,
        run_service_factory=FakeBIRunService,
        confirmation_service_factory=lambda db: confirmation_service,
        direct_query_runner_factory=FakeAgenticDirectQueryRunner,
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
        "dataset.query.started",
        "artifact.created",
        "message.completed",
        "task.completed",
    ]
    assert events[-2].payload["summary"] == "合同总金额为 100 万元"
    assert events[-2].payload["artifact_ref"] == "artifact:safe"
    assert "tool_planner" not in str([event.payload for event in events])
    assert "skill_selector" not in str([event.payload for event in events])
    assert "handoff_status" not in str([event.payload for event in events])
    assert confirmation_service.requests[0][1].capability_snapshot.dataset_id == 12
    refs = db_session.query(AgentScopeRef).filter_by(thread_id=events[0].thread_id).all()
    assert {(ref.ref_type, ref.ref_value, ref.relation, ref.message_id) for ref in refs} >= {
        ("artifact", "artifact:safe", "primary", events[0].message_id),
        ("checkpoint", "checkpoint:safe", "latest", events[0].message_id),
    }


@pytest.mark.asyncio
async def test_bi_lead_agent_task_runner_auto_selects_dataset_from_manifest(
    db_session,
    sample_dataset,
):
    """未显式选数据集时，BI Agent 基于 Manifest 高置信路由后继续直连查询。"""

    _add_current_manifest(
        db_session,
        dataset_id=sample_dataset.id,
        dataset_name="订单销售",
        domain="销售运营",
        sample_questions=["最近30日GMV趋势如何"],
    )
    confirmation_service = FakeBIConfirmationService(db_session)
    runner = BIAgentTaskRunner(
        db=db_session,
        run_service_factory=FakeBIRunService,
        confirmation_service_factory=lambda db: confirmation_service,
        direct_query_runner_factory=FakeAgenticDirectQueryRunner,
    )
    runtime = AgenticShellTaskRuntime(db=db_session, runner=runner)
    request = AgenticShellTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="最近30日GMV趋势如何",
        dataset_id=None,
    )

    events = [event async for event in runtime.stream(request)]

    event_types = [event.event_type for event in events]
    assert event_types[:4] == [
        "task.started",
        "agent.selected",
        "dataset.selected",
        "dataset.query.started",
    ]
    assert events[2].payload["route_decision"]["decision"] == "selected"
    assert events[2].payload["route_decision"]["dataset_id"] == sample_dataset.id
    assert confirmation_service.requests[0][1].dataset_id == sample_dataset.id
    assert confirmation_service.requests[0][1].capability_snapshot.name == "订单销售"
    assert events[-2].payload["artifact_ref"] == "artifact:safe"


@pytest.mark.asyncio
async def test_bi_lead_agent_task_runner_requires_user_dataset_choice_when_ambiguous(
    db_session,
    sample_dataset,
    sample_datasource,
):
    """多候选接近时发出 AgentScope 人机交互候选卡片，不调用 DatasetAgent。"""

    supplier_dataset = _add_dataset(db_session, sample_datasource, "供应商采购")
    for dataset_id, name, domain in (
        (sample_dataset.id, "订单销售", "销售运营"),
        (supplier_dataset.id, "供应商采购", "采购管理"),
    ):
        _add_current_manifest(
            db_session,
            dataset_id=dataset_id,
            dataset_name=name,
            domain=domain,
            sample_questions=["最近30日GMV趋势如何"],
        )
    runner = BIAgentTaskRunner(
        db=db_session,
        run_service_factory=FakeBIRunService,
        confirmation_service_factory=FakeBIConfirmationService,
        direct_query_runner_factory=FakeAgenticDirectQueryRunner,
    )
    runtime = AgenticShellTaskRuntime(db=db_session, runner=runner)
    request = AgenticShellTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="最近30日GMV趋势如何",
        dataset_id=None,
    )

    events = [event async for event in runtime.stream(request)]

    assert [event.event_type for event in events] == [
        "task.started",
        "agent.selected",
        "clarification.required",
        "message.completed",
        "task.completed",
    ]
    clarification_payload = events[2].payload
    assert clarification_payload["clarification"]["kind"] == "dataset_choice"
    assert len(clarification_payload["clarification"]["candidates"]) == 2
    assert all("schema" not in candidate for candidate in clarification_payload["clarification"]["candidates"])
    assert all("sql" not in str(candidate).lower() for candidate in clarification_payload["clarification"]["candidates"])
    assert events[3].payload["route_decision"]["decision"] == "ambiguous"


@pytest.mark.asyncio
async def test_bi_lead_agent_task_runner_keeps_raw_debug_payloads_without_lifecycle_logs(
    db_session,
    caplog,
    monkeypatch,
):
    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "true")
    confirmation_service = FakeBIConfirmationService(db_session)
    runner = BIAgentTaskRunner(
        db=db_session,
        run_service_factory=FakeBIRunService,
        confirmation_service_factory=lambda db: confirmation_service,
        direct_query_runner_factory=FakeAgenticDirectQueryRunner,
    )
    runtime = AgenticShellTaskRuntime(db=db_session, runner=runner)
    request = AgenticShellTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="统计合同总金额",
        dataset_id=12,
    )

    with caplog.at_level(logging.INFO, logger="app.middlewares.lifecycle"):
        events = [event async for event in runtime.stream(request)]

    assert events[-1].event_type == "task.completed"
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert '"dataset_id": 12' in logs
    assert '"query_status": "completed"' in logs
    assert "[datalogue.lifecycle]" not in logs
    assert "[datalogue.output]" in logs
    assert "[datalogue.raw]" in logs
    assert '"stage": "bi_agent.raw.input"' in logs
    assert '"stage": "bi_agent.raw.output"' in logs
    assert '"question": "统计合同总金额"' in logs
    assert '"artifact_ref": "artifact:safe"' in logs
    assert '"event_type": "message.completed"' in logs
    assert '"summary": "合同总金额为 100 万元"' in logs
    for forbidden in ("SELECT *", " FROM ", "schema_context", "raw_rows", "compiled_query_ref", "tool_planner", "skill_selector"):
        assert forbidden.lower() not in logs.lower()
