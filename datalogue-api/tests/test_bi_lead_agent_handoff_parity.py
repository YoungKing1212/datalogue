# ============================================================
# File Name   : test_bi_lead_agent_handoff_parity.py
# Description:
#   BI Agent Host Adapter 与 AgentScope native handoff 同构测试。
#
# Responsibilities:
#   - 验证两种 handoff 实现对同一输入输出相同的 D2 安全字段形态。
#   - 确认 native 演进不会改变父子 agent、refs、状态和安全摘要契约。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.bi_agent import BIAgentHandoffRequest
from app.agents.bi_agent.handoff_adapter import DatalogueBIHandoffAdapter
from app.agents.bi_agent.native_handoff import AgentScopeNativeBIHandoff


def _handoff_request() -> BIAgentHandoffRequest:
    return BIAgentHandoffRequest(
        dataset_id=10,
        confirmed_question="统计 2026 年各渠道 GMV",
        task_goal="执行单数据集问数",
        user_confirmation_id=7,
        routing_rationale="用户已确认订单数据集。",
        trace_id="trace-parity",
        parent_run_id="99",
    )


class FakeBridge:
    def __init__(self, host_events=None, native_events=None) -> None:
        self.host_session = SimpleNamespace(artifact_ref="artifact-parity", last_error=None)
        self.native_session = SimpleNamespace(artifact_ref="artifact-parity", last_error=None)
        self.host_events = host_events or [
            {
                "status": "completed",
                "answer_summary": "渠道 GMV 汇总完成。",
                "artifact_ref": "artifact-parity",
                "checkpoint_ref": "checkpoint-parity",
                "row_count": 12,
                "column_count": 4,
                "sql": "SELECT * FROM secret_orders",
                "raw_rows": [{"secret": 1}],
            },
        ]
        self.native_events = native_events or [
            {
                "event_type": "agent.child.completed",
                "child_run_id": "dataset-native-parity",
                "answer_summary": "渠道 GMV 汇总完成。",
                "artifact_ref": "artifact-parity",
                "checkpoint_ref": "checkpoint-parity",
                "row_count": 12,
                "column_count": 4,
                "schema": {"orders": ["amount"]},
            },
        ]
        self._session_index = 0

    def start_session(self, **kwargs):
        self._session_index += 1
        if self._session_index == 1:
            return self.host_session
        return self.native_session

    async def run_reply_stream(self, agent, *, msg, session):
        if session is self.host_session:
            return self.host_events
        return self.native_events


class FakeFactory:
    def create(self, session):
        return SimpleNamespace(name="dataset_agent")


def _contract_projection(result) -> dict:
    return {
        "parent_agent": result.parent_agent,
        "child_agent": result.child_agent,
        "dataset_id": result.dataset_id,
        "task_id": result.task_id,
        "trace_id": result.trace_id,
        "handoff_status": result.handoff_status,
        "answer_summary": result.answer_summary,
        "artifact_ref": result.artifact_ref,
        "checkpoint_ref": result.checkpoint_ref,
        "row_count": result.row_count,
        "column_count": result.column_count,
        "status_reason": result.status_reason,
        "error_code": result.error_code,
        "error_summary": result.error_summary,
    }


@pytest.mark.asyncio
async def test_host_adapter_and_native_handoff_return_isomorphic_d2_contracts():
    bridge = FakeBridge()
    factory = FakeFactory()
    host = DatalogueBIHandoffAdapter(bridge=bridge, dataset_agent_factory=factory)
    native = AgentScopeNativeBIHandoff(bridge=bridge, dataset_agent_factory=factory)
    request = _handoff_request()

    host_result = await host.query_dataset(request, task_id="task-parity")
    native_result = await native.query_dataset(request, task_id="task-parity")

    assert _contract_projection(host_result) == _contract_projection(native_result)
    assert host_result.child_run_id is not None
    assert native_result.child_run_id == "dataset-native-parity"
    assert "sql" not in host_result.model_dump()
    assert "raw_rows" not in host_result.model_dump()
    assert "schema" not in native_result.model_dump()
