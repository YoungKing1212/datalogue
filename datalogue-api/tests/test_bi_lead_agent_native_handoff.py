# ============================================================
# File Name   : test_bi_lead_agent_native_handoff.py
# Description:
#   BI LeadAgent AgentScope native handoff 测试。
#
# Responsibilities:
#   - 验证 native event 到 Datalogue handoff 状态的映射。
#   - 验证 native handoff 返回 D2 安全结果，且不暴露 DatasetAgent 内部敏感上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.bi_lead_agent import BILeadAgentHandoffRequest
from app.services.bi_lead_agent.handoff_events import (
    collect_native_handoff_payload,
    map_native_handoff_event,
    safe_native_failure_result_payload,
)
from app.services.bi_lead_agent.native_handoff import AgentScopeNativeBIHandoff


def _handoff_request() -> BILeadAgentHandoffRequest:
    return BILeadAgentHandoffRequest(
        dataset_id=10,
        confirmed_question="统计 2026 年各渠道 GMV",
        task_goal="执行单数据集问数",
        user_confirmation_id=7,
        routing_rationale="用户已确认订单数据集。",
        trace_id="trace-native",
        parent_run_id="99",
    )


class FakeBridge:
    def __init__(self, events=None, session=None) -> None:
        self.events = events or []
        self.session = session or SimpleNamespace(artifact_ref=None, last_error=None)
        self.calls = []

    def start_session(self, **kwargs):
        self.calls.append({"method": "start_session", "kwargs": kwargs})
        return self.session

    async def run_reply_stream(self, agent, *, msg, session):
        self.calls.append({"method": "run_reply_stream", "agent": agent, "msg": msg, "session": session})
        return self.events


class FakeFactory:
    def __init__(self) -> None:
        self.sessions = []

    def create(self, session):
        self.sessions.append(session)
        return SimpleNamespace(name="dataset_agent")


def test_native_handoff_event_maps_to_safe_datalogue_status():
    result = map_native_handoff_event(
        {
            "event_type": "agent.child.completed",
            "child_run_id": "dataset-native-001",
            "artifact_ref": "artifact-native-001",
            "checkpoint_ref": "checkpoint-native-001",
            "answer_summary": "查询完成。",
            "row_count": "12",
            "column_count": 4,
            "sql": "select * from orders",
            "schema": {"orders": ["amount"]},
            "raw_rows": [{"amount": 1}],
            "dsl": {"query": "hidden"},
        },
    )

    assert result == {
        "handoff_status": "completed",
        "child_run_id": "dataset-native-001",
        "artifact_ref": "artifact-native-001",
        "checkpoint_ref": "checkpoint-native-001",
        "answer_summary": "查询完成。",
        "row_count": 12,
        "column_count": 4,
    }
    assert "sql" not in result
    assert "schema" not in result
    assert "raw_rows" not in result
    assert "dsl" not in result


def test_collect_native_handoff_payload_uses_final_safe_event():
    payload = collect_native_handoff_payload(
        [
            {"event_type": "agent.child.running", "child_run_id": "dataset-native-001"},
            {
                "event_type": "agent.child.completed",
                "child_run_id": "dataset-native-001",
                "artifact_ref": "artifact-native-001",
                "answer_summary": "查询完成。",
                "sql": "select * from orders",
            },
        ],
    )

    assert payload["handoff_status"] == "completed"
    assert payload["child_run_id"] == "dataset-native-001"
    assert payload["artifact_ref"] == "artifact-native-001"
    assert payload["answer_summary"] == "查询完成。"
    assert "sql" not in payload


@pytest.mark.asyncio
async def test_agentscope_native_handoff_returns_safe_d2_result():
    events = [
        {
            "event_type": "agent.child.completed",
            "child_run_id": "dataset-native-001",
            "artifact_ref": "artifact-native-001",
            "checkpoint_ref": "checkpoint-native-001",
            "answer_summary": "线上渠道贡献最高。",
            "row_count": 9,
            "column_count": 3,
            "schema": {"orders": ["amount"]},
            "raw_rows": [{"amount": 100}],
        },
    ]
    bridge = FakeBridge(events=events)
    factory = FakeFactory()
    native = AgentScopeNativeBIHandoff(bridge=bridge, dataset_agent_factory=factory)

    result = await native.query_dataset(_handoff_request(), task_id="task-native")

    assert result.parent_agent == "bi_lead_agent"
    assert result.child_agent == "dataset_agent"
    assert result.child_run_id == "dataset-native-001"
    assert result.dataset_id == 10
    assert result.task_id == "task-native"
    assert result.trace_id == "trace-native"
    assert result.handoff_status == "completed"
    assert result.answer_summary == "线上渠道贡献最高。"
    assert result.artifact_ref == "artifact-native-001"
    assert result.checkpoint_ref == "checkpoint-native-001"
    assert result.row_count == 9
    assert result.column_count == 3
    assert "schema" not in result.model_dump()
    assert "raw_rows" not in result.model_dump()
    assert factory.sessions == [bridge.session]
    assert bridge.calls[0]["kwargs"]["agent_name"] == "bi_lead_agent"


@pytest.mark.asyncio
async def test_agentscope_native_handoff_fails_closed_without_exception_detail():
    bridge = FakeBridge()

    async def boom(*args, **kwargs):
        raise RuntimeError("SELECT * FROM secret_orders")

    bridge.run_reply_stream = boom
    native = AgentScopeNativeBIHandoff(bridge=bridge, dataset_agent_factory=FakeFactory())

    result = await native.query_dataset(_handoff_request(), task_id="task-native")

    assert result.handoff_status == "failed"
    assert result.status_reason == "agentscope_native_handoff_failed"
    assert result.error_code == "AGENTSCOPE_NATIVE_HANDOFF_FAILED"
    assert result.error_summary == safe_native_failure_result_payload()["error_summary"]
    assert "SELECT" not in result.error_summary
    assert "secret_orders" not in result.error_summary
