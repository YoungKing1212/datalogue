# ============================================================
# File Name   : test_bi_lead_agent_services.py
# Description:
#   BI LeadAgent K1 Run 与确认服务测试。
#
# Responsibilities:
#   - 验证 LeadAgent run 创建、用户确认状态流转和确认门禁。
#   - 验证 run 响应只暴露安全 DTO 字段，不泄露 DatasetAgent 内部执行上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

import pytest

from app.models.bi_lead_agent import BIAgentHandoff
from app.schemas.bi_lead_agent import ConfirmBILeadAgentRunRequest, DatasetCapabilitySummary
from app.services.bi_lead_agent.confirmation_service import BILeadAgentConfirmationService
from app.services.bi_lead_agent.run_service import BILeadAgentRunService


def _confirmation_request(dataset_id: int, user_decision: str = "approved") -> ConfirmBILeadAgentRunRequest:
    return ConfirmBILeadAgentRunRequest(
        dataset_id=dataset_id,
        confirmed_question="统计 2026 年订单金额",
        task_goal="按确认的数据集执行单数据集问数",
        capability_snapshot=DatasetCapabilitySummary(
            dataset_id=dataset_id,
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


def test_create_run_persists_created_route_run_with_given_trace_and_task(db_session):
    service = BILeadAgentRunService(db_session)

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
    service = BILeadAgentRunService(db_session)

    run = service.create_run(question="统计 2026 年订单金额")

    assert run.trace_id.startswith("bi-lead-trace-")
    assert run.task_id.startswith("bi-lead-task-")
    assert len(run.trace_id) > len("bi-lead-trace-")
    assert len(run.task_id) > len("bi-lead-task-")


def test_confirm_approved_saves_snapshot_and_moves_run_to_running(db_session, sample_dataset):
    run_service = BILeadAgentRunService(db_session)
    confirmation_service = BILeadAgentConfirmationService(db_session)
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


def test_confirm_rejected_blocks_run_and_confirmation_gate_rejects(db_session, sample_dataset):
    run_service = BILeadAgentRunService(db_session)
    confirmation_service = BILeadAgentConfirmationService(db_session)
    run = run_service.create_run(
        question="统计 2026 年订单金额",
        trace_id="trace-bi-k1-reject",
        task_id="task-bi-k1-reject",
    )

    confirmation = confirmation_service.confirm(run.id, _confirmation_request(sample_dataset.id, "rejected"))

    assert confirmation.user_decision == "rejected"
    assert run.status == "blocked"
    assert run.phase == "confirm_run"
    assert run.status_reason == "confirmation_rejected"
    with pytest.raises(ValueError, match="USER_CONFIRMATION_REQUIRED"):
        confirmation_service.require_approved_confirmation(run.id)


def test_require_approved_confirmation_rejects_missing_confirmation(db_session):
    run = BILeadAgentRunService(db_session).create_run(question="统计 2026 年订单金额")

    with pytest.raises(ValueError, match="USER_CONFIRMATION_REQUIRED"):
        BILeadAgentConfirmationService(db_session).require_approved_confirmation(run.id)


def test_get_response_returns_safe_confirmation_and_handoff_dto(db_session, sample_dataset):
    run_service = BILeadAgentRunService(db_session)
    confirmation_service = BILeadAgentConfirmationService(db_session)
    run = run_service.create_run(
        question="统计 2026 年订单金额",
        trace_id="trace-bi-k1-safe-response",
        task_id="task-bi-k1-safe-response",
    )
    confirmation = confirmation_service.confirm(run.id, _confirmation_request(sample_dataset.id, "approved"))
    handoff = BIAgentHandoff(
        run_id=run.id,
        handoff_id="handoff-bi-k1-safe",
        parent_agent="bi_lead_agent",
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
        "parent_agent": "bi_lead_agent",
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
        BILeadAgentRunService(db_session).get_response(999999)
