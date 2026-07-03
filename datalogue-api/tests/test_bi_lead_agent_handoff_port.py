# ============================================================
# File Name   : test_bi_lead_agent_handoff_port.py
# Description:
#   BI Agent handoff port 抽象测试。
#
# Responsibilities:
#   - 验证 BIAgentHandoffService 只依赖 query_dataset port。
#   - 确保默认 handoff 入口固定走 AgentScope native handoff。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import pytest

from app.schemas.bi_agent import (
    BIAgentHandoffResult,
    ConfirmBIAgentRunRequest,
    DatasetCapabilitySummary,
)
from app.agents.bi_agent.confirmation_service import BIAgentConfirmationService
from app.agents.bi_agent.handoff_port import BIHandoffPort
from app.agents.bi_agent.handoff_service import BIAgentHandoffService, _default_handoff_port
from app.agents.bi_agent.run_service import BIAgentRunService


class FakePort:
    def __init__(self) -> None:
        self.calls = []

    async def query_dataset(self, request, *, task_id):
        self.calls.append({"request": request, "task_id": task_id})
        return BIAgentHandoffResult(
            handoff_id="handoff-port-001",
            child_run_id="dataset-run-port-001",
            dataset_id=request.dataset_id,
            task_id=task_id,
            trace_id=request.trace_id,
            handoff_status="completed",
            answer_summary="native handoff 输出安全结果。",
            artifact_ref="artifact-port-001",
            checkpoint_ref="checkpoint-port-001",
            row_count=3,
            column_count=2,
        )


def _confirmation_request(dataset_id: int) -> ConfirmBIAgentRunRequest:
    return ConfirmBIAgentRunRequest(
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
        user_decision="approved",
    )


@pytest.mark.asyncio
async def test_fake_port_satisfies_bi_handoff_port_protocol():
    port: BIHandoffPort = FakePort()
    assert hasattr(port, "query_dataset")


@pytest.mark.asyncio
async def test_bi_handoff_service_uses_injected_port(db_session, sample_dataset):
    run_service = BIAgentRunService(db_session)
    confirmation_service = BIAgentConfirmationService(db_session)
    run = run_service.create_run(
        question="统计 2026 年订单金额",
        trace_id="trace-port",
        task_id="task-port",
    )
    confirmation_service.confirm(run.id, _confirmation_request(sample_dataset.id))
    port = FakePort()

    result = await BIAgentHandoffService(db_session, adapter=port).query_dataset(run_id=run.id)

    assert result.handoff_id == "handoff-port-001"
    assert len(port.calls) == 1
    assert port.calls[0]["task_id"] == "task-port"
    assert port.calls[0]["request"].dataset_id == sample_dataset.id
    assert run.status == "completed"
    assert run.phase == "summarize_run"
    assert run.handoff.handoff_id == "handoff-port-001"


def test_default_handoff_port_uses_native_by_default(db_session, monkeypatch):
    native_port = FakePort()

    class FakeNativeHandoff:
        @classmethod
        def from_db(cls, db):
            return native_port

    monkeypatch.setattr("app.agents.bi_agent.native_handoff.AgentScopeNativeBIHandoff", FakeNativeHandoff)

    assert _default_handoff_port(db_session) is native_port
