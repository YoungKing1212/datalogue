# ============================================================
# File Name   : test_bi_lead_agent_handoff_adapter.py
# Description:
#   BI LeadAgent K1 Host Handoff Adapter 测试。
#
# Responsibilities:
#   - 验证 handoff adapter 只走 AgentScope run_reply_stream 主路径。
#   - 验证 DatasetAgent 返回的 SQL、schema、raw rows、DSL 等内部字段不会进入安全结果。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from typing import Any

import pytest
from agentscope.message import Msg

from app.schemas.bi_lead_agent import BILeadAgentHandoffRequest
from app.services.bi_lead_agent.handoff_adapter import DatalogueBIHandoffAdapter


class FakeBridge:
    def __init__(self, events: list[Any] | None = None, fail: bool = False) -> None:
        self.events = events or []
        self.fail = fail
        self.run_reply_stream_called = False
        self.run_direct_query_called = False
        self.started_session = None

    def start_session(self, **kwargs: Any) -> dict[str, Any]:
        self.started_session = kwargs
        return {"session": "dataset-runtime-session", **kwargs}

    async def run_reply_stream(self, agent: Any, *, msg: Any, session: Any) -> list[Any]:
        self.run_reply_stream_called = True
        self.agent = agent
        self.msg = msg
        self.session = session
        if self.fail:
            raise RuntimeError(
                "dataset agent exploded: SELECT * FROM secret_orders schema_context compiled_query_ref raw_rows"
            )
        return self.events

    async def run_direct_query(self, **_kwargs: Any) -> dict[str, Any]:
        self.run_direct_query_called = True
        return {"status": "completed"}


class FakeDatasetAgentFactory:
    def __init__(self) -> None:
        self.sessions: list[Any] = []

    def create(self, session: Any) -> object:
        self.sessions.append(session)
        return object()


def _handoff_request(dataset_id: int = 101) -> BILeadAgentHandoffRequest:
    return BILeadAgentHandoffRequest(
        dataset_id=dataset_id,
        confirmed_question="统计 2026 年订单金额",
        task_goal="按确认的数据集执行单数据集问数",
        user_confirmation_id=7,
        routing_rationale="订单金额问题应由订单数据集回答。",
        trace_id="trace-bi-k1-handoff",
        parent_run_id="123",
    )


@pytest.mark.asyncio
async def test_query_dataset_uses_run_reply_stream_and_never_direct_query() -> None:
    bridge = FakeBridge(
        events=[
            {
                "status": "completed",
                "answer_summary": "订单金额汇总完成。",
                "artifact_ref": "artifact-bi-k1-001",
                "checkpoint_ref": "checkpoint-bi-k1-001",
                "row_count": 12,
                "column_count": 3,
                "sql": "select * from secret_orders",
                "schema": {"secret_orders": ["amount"]},
                "raw_rows": [{"amount": 100}],
                "dsl": {"metric": "amount"},
                "result_rows": [{"amount": 100}],
                "compiled_query_ref": "compiled-query-secret",
            }
        ]
    )
    factory = FakeDatasetAgentFactory()
    adapter = DatalogueBIHandoffAdapter(bridge=bridge, dataset_agent_factory=factory)

    result = await adapter.query_dataset(_handoff_request(), task_id="task-bi-k1-001")

    assert bridge.run_reply_stream_called is True
    assert bridge.run_direct_query_called is False
    assert bridge.started_session == {
        "dataset_id": 101,
        "question": "统计 2026 年订单金额",
        "agent_name": "bi_lead_agent",
        "trace_id": "trace-bi-k1-handoff",
    }
    assert isinstance(bridge.msg, Msg)
    assert bridge.msg.name == "user"
    assert factory.sessions == [bridge.session]
    assert result.handoff_id.startswith("handoff-")
    assert result.child_run_id.startswith("dataset-run-")
    assert result.task_id == "task-bi-k1-001"
    assert result.handoff_status == "completed"
    assert result.answer_summary == "订单金额汇总完成。"
    assert result.artifact_ref == "artifact-bi-k1-001"
    assert result.checkpoint_ref == "checkpoint-bi-k1-001"
    assert result.row_count == 12
    assert result.column_count == 3


@pytest.mark.asyncio
async def test_query_dataset_result_does_not_expose_dataset_agent_internal_fields() -> None:
    bridge = FakeBridge(
        events=[
            {
                "status": "completed",
                "answer_summary": "订单金额汇总完成。",
                "artifact_ref": "artifact-bi-k1-safe",
                "checkpoint_ref": "checkpoint-bi-k1-safe",
                "row_count": 1,
                "column_count": 2,
                "sql": "SELECT * FROM secret_orders",
                "schema": {"secret_orders": ["secret_amount"]},
                "raw_rows": [{"secret_amount": 100}],
                "dsl": {"metric": "secret_amount"},
                "result_rows": [{"secret_amount": 100}],
                "compiled_query_ref": "compiled-query-secret",
                "schema_context": {"tables": ["secret_orders"]},
                "candidate_assets": [{"name": "secret_amount"}],
                "blueprint_body": {"query": "secret"},
                "repair_patch": {"op": "replace"},
            }
        ]
    )
    adapter = DatalogueBIHandoffAdapter(bridge=bridge, dataset_agent_factory=FakeDatasetAgentFactory())

    result = await adapter.query_dataset(_handoff_request())
    payload = result.model_dump()
    payload_json = result.model_dump_json()

    assert set(payload) == {
        "handoff_id",
        "parent_agent",
        "child_agent",
        "child_run_id",
        "dataset_id",
        "task_id",
        "trace_id",
        "handoff_status",
        "answer_summary",
        "artifact_ref",
        "checkpoint_ref",
        "row_count",
        "column_count",
        "status_reason",
        "error_code",
        "error_summary",
    }
    for forbidden in (
        "sql",
        "schema",
        "raw_rows",
        "dsl",
        "result_rows",
        "compiled_query_ref",
        "schema_context",
        "candidate_assets",
        "blueprint_body",
        "repair_patch",
        "SELECT * FROM secret_orders",
        "secret_amount",
    ):
        assert forbidden not in payload_json


@pytest.mark.asyncio
async def test_query_dataset_returns_failed_result_when_agentscope_dataset_agent_fails() -> None:
    bridge = FakeBridge(fail=True)
    adapter = DatalogueBIHandoffAdapter(bridge=bridge, dataset_agent_factory=FakeDatasetAgentFactory())

    result = await adapter.query_dataset(_handoff_request(), task_id="task-bi-k1-failed")

    assert bridge.run_reply_stream_called is True
    assert bridge.run_direct_query_called is False
    assert result.handoff_status == "failed"
    assert result.error_code == "AGENTSCOPE_DATASET_AGENT_FAILED"
    assert result.error_summary == "DatasetAgent 执行失败，已停止 handoff。"
    payload_json = result.model_dump_json()
    for forbidden in (
        "dataset agent exploded",
        "SELECT * FROM secret_orders",
        "schema_context",
        "compiled_query_ref",
        "raw_rows",
    ):
        assert forbidden not in payload_json
