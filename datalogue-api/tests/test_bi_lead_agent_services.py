# ============================================================
# File Name   : test_bi_lead_agent_services.py
# Description:
#   BI Agent K1 Run 与确认服务测试。
#
# Responsibilities:
#   - 验证 LeadAgent run 创建、用户确认状态流转和确认门禁。
#   - 验证 run 响应只暴露安全 DTO 字段，不泄露 DatasetAgent 内部执行上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

import pytest

from app.core.models.bi_agent import BIAgentHandoff, BIAgentRun
from app.core.schemas.bi_agent import BIAgentHandoffResult
from app.core.schemas.bi_agent import ConfirmBIAgentRunRequest, DatasetCapabilitySummary
from app.domains.bi.agent.confirmation_service import BIAgentConfirmationService
from app.domains.bi.agent.handoff_service import BIAgentHandoffService
from app.domains.bi.agent.run_service import BIAgentRunService


def _confirmation_request(
    dataset_id: int,
    user_decision: str = "approved",
    capability_dataset_id: int | None = None,
) -> ConfirmBIAgentRunRequest:
    return ConfirmBIAgentRunRequest(
        dataset_id=dataset_id,
        confirmed_question="统计 2026 年订单金额",
        task_goal="按确认的数据集执行单数据集问数",
        capability_snapshot=DatasetCapabilitySummary(
            dataset_id=capability_dataset_id or dataset_id,
            name="订单数据集",
            domain="销售",
            supported_questions=["订单金额趋势"],
            key_metrics=["订单金额"],
            key_dimensions=["月份"],
            freshness="T+1",
            availability="ready",
        ),
        routing_rationale="订单金额问题应由订单数据集回答。",
        risk_notice="本次只执行只读聚合查询。",
        user_decision=user_decision,
    )


class FakeHandoffAdapter:
    def __init__(self, result: BIAgentHandoffResult | None = None) -> None:
        self.calls = []
        self.result = result

    async def query_dataset(self, request, task_id: str | None = None):
        self.calls.append({"request": request, "task_id": task_id})
        return self.result or BIAgentHandoffResult(
            handoff_id="handoff-bi-k1-service",
            child_run_id="dataset-run-bi-k1-service",
            dataset_id=request.dataset_id,
            task_id=task_id,
            trace_id=request.trace_id,
            handoff_status="completed",
            answer_summary="订单金额汇总完成。",
            artifact_ref="artifact-bi-k1-service",
            checkpoint_ref="checkpoint-bi-k1-service",
            row_count=8,
            column_count=2,
        )


def test_create_run_persists_created_route_run_with_given_trace_and_task(db_session):
    service = BIAgentRunService(db_session)

    run = service.create_run(
        question="统计 2026 年订单金额",
        trace_id="trace-bi-k1-001",
        task_id="task-bi-k1-001",
    )

    assert run.id is not None
    assert run.status == "created"
    assert run.phase == "route_run"
    assert run.trace_id == "trace-bi-k1-001"
    assert run.task_id == "task-bi-k1-001"


def test_create_run_generates_trace_and_task_when_missing(db_session):
    service = BIAgentRunService(db_session)

    run = service.create_run(question="统计 2026 年订单金额")

    assert run.trace_id.startswith("bi-lead-trace-")
    assert run.task_id.startswith("bi-lead-task-")
    assert len(run.trace_id) > len("bi-lead-trace-")
    assert len(run.task_id) > len("bi-lead-task-")


def test_mark_phase_persists_run_status_fields(db_session):
    service = BIAgentRunService(db_session)
    run = service.create_run(question="统计 2026 年订单金额")
    run_id = run.id

    service.mark_phase(
        run,
        phase="handoff_run",
        status="running",
        status_reason="handoff_started",
    )
    db_session.expunge_all()

    saved = db_session.get(BIAgentRun, run_id)
    assert saved is not None
    assert saved.phase == "handoff_run"
    assert saved.status == "running"
    assert saved.status_reason == "handoff_started"
    assert saved.completed_at is None


def test_mark_phase_rejects_invalid_phase_or_status(db_session):
    service = BIAgentRunService(db_session)
    run = service.create_run(question="统计 2026 年订单金额")

    with pytest.raises(ValueError, match="BI_LEAD_AGENT_PHASE_INVALID"):
        service.mark_phase(run, phase="dataset_runtime", status="running")

    with pytest.raises(ValueError, match="BI_LEAD_AGENT_STATUS_INVALID"):
        service.mark_phase(run, phase="handoff_run", status="querying")


def test_mark_failed_persists_failure_fields(db_session):
    service = BIAgentRunService(db_session)
    run = service.create_run(question="统计 2026 年订单金额")
    run_id = run.id

    service.mark_failed(
        run,
        phase="summarize_run",
        error_code="DATASET_AGENT_FAILED",
        error_summary="DatasetAgent 执行失败",
    )
    db_session.expunge_all()

    saved = db_session.get(BIAgentRun, run_id)
    assert saved is not None
    assert saved.status == "failed"
    assert saved.phase == "summarize_run"
    assert saved.error_code == "DATASET_AGENT_FAILED"
    assert saved.error_summary == "DatasetAgent 执行失败"
    assert saved.completed_at is not None


def test_confirm_approved_saves_snapshot_and_moves_run_to_running(db_session, sample_dataset):
    run_service = BIAgentRunService(db_session)
    confirmation_service = BIAgentConfirmationService(db_session)
    run = run_service.create_run(
        question="统计 2026 年订单金额",
        trace_id="trace-bi-k1-approve",
        task_id="task-bi-k1-approve",
    )

    confirmation = confirmation_service.confirm(run.id, _confirmation_request(sample_dataset.id, "approved"))

    assert confirmation.capability_snapshot_json == {
        "dataset_id": sample_dataset.id,
        "name": "订单数据集",
        "domain": "销售",
        "supported_questions": ["订单金额趋势"],
        "key_metrics": ["订单金额"],
        "key_dimensions": ["月份"],
        "freshness": "T+1",
        "availability": "ready",
    }
    assert confirmation.trace_id == run.trace_id
    assert confirmation.parent_run_id == str(run.id)
    assert confirmation.decided_at is not None
    assert run.status == "running"
    assert run.phase == "confirm_run"
    assert run.status_reason == "confirmation_approved"
    assert confirmation_service.require_approved_confirmation(run.id).id == confirmation.id


def test_confirm_rejects_dataset_snapshot_mismatch(db_session, sample_dataset):
    run_service = BIAgentRunService(db_session)
    confirmation_service = BIAgentConfirmationService(db_session)
    run = run_service.create_run(question="统计 2026 年订单金额")

    with pytest.raises(ValueError, match="DATASET_CONFIRMATION_MISMATCH"):
        confirmation_service.confirm(
            run.id,
            _confirmation_request(
                sample_dataset.id,
                "approved",
                capability_dataset_id=sample_dataset.id + 1000,
            ),
        )


def test_confirm_rejects_duplicate_decision_before_database_unique_error(db_session, sample_dataset):
    run_service = BIAgentRunService(db_session)
    confirmation_service = BIAgentConfirmationService(db_session)
    run = run_service.create_run(question="统计 2026 年订单金额")
    confirmation_service.confirm(run.id, _confirmation_request(sample_dataset.id, "approved"))

    with pytest.raises(ValueError, match="CONFIRMATION_ALREADY_DECIDED"):
        confirmation_service.confirm(run.id, _confirmation_request(sample_dataset.id, "rejected"))


def test_confirm_rejected_blocks_run_and_confirmation_gate_rejects(db_session, sample_dataset):
    run_service = BIAgentRunService(db_session)
    confirmation_service = BIAgentConfirmationService(db_session)
    run = run_service.create_run(
        question="统计 2026 年订单金额",
        trace_id="trace-bi-k1-reject",
        task_id="task-bi-k1-reject",
    )

    confirmation = confirmation_service.confirm(run.id, _confirmation_request(sample_dataset.id, "rejected"))

    assert confirmation.user_decision == "rejected"
    assert confirmation.decided_at is not None
    assert run.status == "blocked"
    assert run.phase == "confirm_run"
    assert run.status_reason == "confirmation_rejected"
    with pytest.raises(ValueError, match="USER_CONFIRMATION_REQUIRED"):
        confirmation_service.require_approved_confirmation(run.id)


def test_confirm_rejects_missing_run(db_session, sample_dataset):
    confirmation_service = BIAgentConfirmationService(db_session)

    with pytest.raises(ValueError, match="BI_LEAD_AGENT_RUN_NOT_FOUND"):
        confirmation_service.confirm(999999, _confirmation_request(sample_dataset.id, "approved"))


def test_require_approved_confirmation_rejects_missing_confirmation(db_session):
    run = BIAgentRunService(db_session).create_run(question="统计 2026 年订单金额")

    with pytest.raises(ValueError, match="USER_CONFIRMATION_REQUIRED"):
        BIAgentConfirmationService(db_session).require_approved_confirmation(run.id)


def test_require_approved_confirmation_rejects_missing_run(db_session):
    with pytest.raises(ValueError, match="BI_LEAD_AGENT_RUN_NOT_FOUND"):
        BIAgentConfirmationService(db_session).require_approved_confirmation(999999)


def test_get_response_returns_safe_confirmation_and_handoff_dto(db_session, sample_dataset):
    run_service = BIAgentRunService(db_session)
    confirmation_service = BIAgentConfirmationService(db_session)
    run = run_service.create_run(
        question="统计 2026 年订单金额",
        trace_id="trace-bi-k1-safe-response",
        task_id="task-bi-k1-safe-response",
    )
    confirmation = confirmation_service.confirm(run.id, _confirmation_request(sample_dataset.id, "approved"))
    handoff = BIAgentHandoff(
        run_id=run.id,
        handoff_id="handoff-bi-k1-safe",
        parent_agent="bi_worker",
        child_agent="dataset_agent",
        child_run_id="dataset-run-bi-k1-safe",
        dataset_id=sample_dataset.id,
        task_id=run.task_id,
        trace_id=run.trace_id,
        handoff_status="completed",
        answer_summary="订单金额汇总完成。",
        artifact_ref="artifact-bi-k1-safe",
        checkpoint_ref="checkpoint-bi-k1-safe",
        row_count=10,
        column_count=3,
    )
    handoff.sql = "select * from secret_orders"
    handoff.schema = {"secret_orders": ["secret_amount"]}
    handoff.raw_rows = [{"secret_amount": 100}]
    handoff.dsl = {"metric": "secret_amount"}
    handoff.result_rows = [{"secret_amount": 100}]
    db_session.add(handoff)
    db_session.commit()

    response = run_service.get_response(run.id)
    payload = response.model_dump()
    payload_text = response.model_dump_json()

    assert payload["confirmation_id"] == confirmation.id
    assert payload["handoff"] == {
        "handoff_id": "handoff-bi-k1-safe",
        "parent_agent": "bi_worker",
        "child_agent": "dataset_agent",
        "child_run_id": "dataset-run-bi-k1-safe",
        "dataset_id": sample_dataset.id,
        "task_id": run.task_id,
        "trace_id": run.trace_id,
        "handoff_status": "completed",
        "answer_summary": "订单金额汇总完成。",
        "artifact_ref": "artifact-bi-k1-safe",
        "checkpoint_ref": "checkpoint-bi-k1-safe",
        "row_count": 10,
        "column_count": 3,
        "status_reason": None,
        "error_code": None,
        "error_summary": None,
    }
    assert "select * from secret_orders" not in payload_text
    assert "schema" not in payload_text
    assert "raw_rows" not in payload_text
    assert "dsl" not in payload_text
    assert "result_rows" not in payload_text


def test_get_response_rejects_missing_run(db_session):
    with pytest.raises(ValueError, match="BI_LEAD_AGENT_RUN_NOT_FOUND"):
        BIAgentRunService(db_session).get_response(999999)


@pytest.mark.asyncio
async def test_handoff_service_persists_safe_result_after_approved_confirmation(db_session, sample_dataset):
    run_service = BIAgentRunService(db_session)
    confirmation_service = BIAgentConfirmationService(db_session)
    run = run_service.create_run(
        question="统计 2026 年订单金额",
        trace_id="trace-bi-k1-handoff-service",
        task_id="task-bi-k1-handoff-service",
    )
    confirmation = confirmation_service.confirm(run.id, _confirmation_request(sample_dataset.id, "approved"))
    dataset_id = sample_dataset.id
    run_id = run.id
    task_id = run.task_id
    trace_id = run.trace_id
    confirmation_id = confirmation.id
    confirmed_question = confirmation.confirmed_question
    adapter = FakeHandoffAdapter()
    service = BIAgentHandoffService(db_session, adapter=adapter)

    result = await service.query_dataset(run_id=run.id)
    db_session.expunge_all()

    saved_run = db_session.get(BIAgentRun, run_id)
    saved_handoff = db_session.query(BIAgentHandoff).filter_by(run_id=run_id).one()
    assert result.handoff_status == "completed"
    assert adapter.calls[0]["request"].dataset_id == dataset_id
    assert adapter.calls[0]["request"].confirmed_question == confirmed_question
    assert adapter.calls[0]["request"].user_confirmation_id == confirmation_id
    assert adapter.calls[0]["request"].trace_id == trace_id
    assert adapter.calls[0]["request"].parent_run_id == str(run_id)
    assert adapter.calls[0]["task_id"] == task_id
    assert saved_run.phase == "summarize_run"
    assert saved_run.status == "completed"
    assert saved_handoff.handoff_id == "handoff-bi-k1-service"
    assert saved_handoff.parent_agent == "bi_worker"
    assert saved_handoff.child_agent == "dataset_agent"
    assert saved_handoff.child_run_id == "dataset-run-bi-k1-service"
    assert saved_handoff.dataset_id == dataset_id
    assert saved_handoff.task_id == "task-bi-k1-handoff-service"
    assert saved_handoff.trace_id == "trace-bi-k1-handoff-service"
    assert saved_handoff.checkpoint_ref == "checkpoint-bi-k1-service"
    assert saved_handoff.artifact_ref == "artifact-bi-k1-service"
    assert saved_handoff.handoff_status == "completed"
    assert saved_handoff.answer_summary == "订单金额汇总完成。"


@pytest.mark.asyncio
async def test_handoff_service_rejected_confirmation_does_not_call_adapter(db_session, sample_dataset):
    run_service = BIAgentRunService(db_session)
    confirmation_service = BIAgentConfirmationService(db_session)
    run = run_service.create_run(question="统计 2026 年订单金额")
    confirmation_service.confirm(run.id, _confirmation_request(sample_dataset.id, "rejected"))
    adapter = FakeHandoffAdapter()

    with pytest.raises(ValueError, match="USER_CONFIRMATION_REQUIRED"):
        await BIAgentHandoffService(db_session, adapter=adapter).query_dataset(run_id=run.id)

    assert adapter.calls == []
    assert db_session.query(BIAgentHandoff).filter_by(run_id=run.id).first() is None


@pytest.mark.asyncio
async def test_handoff_service_missing_confirmation_does_not_call_adapter(db_session):
    run = BIAgentRunService(db_session).create_run(question="统计 2026 年订单金额")
    adapter = FakeHandoffAdapter()

    with pytest.raises(ValueError, match="USER_CONFIRMATION_REQUIRED"):
        await BIAgentHandoffService(db_session, adapter=adapter).query_dataset(run_id=run.id)

    assert adapter.calls == []
    assert db_session.query(BIAgentHandoff).filter_by(run_id=run.id).first() is None
