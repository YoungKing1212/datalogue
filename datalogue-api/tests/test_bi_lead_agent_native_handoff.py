# ============================================================
# File Name   : test_bi_lead_agent_native_handoff.py
# Description:
#   BI Agent AgentScope native handoff 测试。
#
# Responsibilities:
#   - 验证 native event 到 Datalogue handoff 状态的映射。
#   - 验证 native handoff 返回 D2 安全结果，且不暴露 DatasetAgent 内部敏感上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from app.core.models.dataset import AnalysisBlueprint
from app.core.schemas.bi_agent import BIAgentHandoffRequest
from app.services.artifact_store import ArtifactStore
from app.domains.bi.agent.handoff_events import (
    collect_native_handoff_payload,
    map_native_handoff_event,
    safe_native_failure_result_payload,
)
from app.domains.bi.agent.native_handoff import (
    AgentScopeNativeBIHandoff,
    _native_allowed_tables_and_sql_context,
)


def _handoff_request() -> BIAgentHandoffRequest:
    return BIAgentHandoffRequest(
        dataset_id=10,
        confirmed_question="统计 2026 年各渠道 GMV",
        task_goal="执行单数据集问数",
        user_confirmation_id=7,
        routing_rationale="用户已确认订单数据集。",
        trace_id="trace-native",
        parent_run_id="99",
    )


def test_native_allowed_tables_builds_safe_compiler_context():
    dataset = SimpleNamespace(
        selected_tables=[
            SimpleNamespace(
                source_table=SimpleNamespace(
                    schema_name="ods",
                    table_name="plan_task_daily_record",
                    columns=[
                        SimpleNamespace(
                            column_name="rzrq",
                            effective_desc="日志日期",
                            user_description=None,
                            ai_description=None,
                            column_comment=None,
                        )
                    ],
                )
            )
        ]
    )

    allowed_tables, sql_context = _native_allowed_tables_and_sql_context(dataset)

    assert allowed_tables == ["ods.plan_task_daily_record", "plan_task_daily_record"]
    assert sql_context == {
        "table_schemas": [
            {
                "name": "plan_task_daily_record",
                "table_name": "plan_task_daily_record",
                "fields": [
                    {
                        "name": "rzrq",
                        "column_name": "rzrq",
                        "display_name": "日志日期",
                    }
                ],
            }
        ]
    }


class FakeBridge:
    def __init__(self, events=None, session=None) -> None:
        self.events = events or []
        self.session = session or SimpleNamespace(artifact_ref=None, last_error=None)
        self.calls = []

    def start_session(self, **kwargs):
        self.calls.append({"method": "start_session", "kwargs": kwargs})
        return self.session

    async def run_reply_stream(self, agent, *, msg, session, on_tool_call=None):
        self.calls.append({"method": "run_reply_stream", "agent": agent, "msg": msg, "session": session})
        return self.events


class FailingStartBridge(FakeBridge):
    def start_session(self, **kwargs):
        self.calls.append({"method": "start_session", "kwargs": kwargs})
        raise RuntimeError("runtime context failed with secret_table")


class FailingRuntimeContextHandoff(AgentScopeNativeBIHandoff):
    def _build_runtime_context(self, request):
        raise RuntimeError("dataset context failed with secret_table")


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


def test_collect_native_handoff_payload_promotes_session_artifact_to_completed():
    payload = collect_native_handoff_payload(
        [
            {"event_type": "agent.child.accepted", "child_run_id": "dataset-native-001"},
            {"event_type": "agent.child.running", "child_run_id": "dataset-native-001"},
        ],
        fallback_artifact_ref="artifact-native-fallback",
    )

    assert payload["handoff_status"] == "completed"
    assert payload["artifact_ref"] == "artifact-native-fallback"


def test_collect_native_handoff_payload_promotes_session_error_to_blocked():
    payload = collect_native_handoff_payload(
        [{"event_type": "agent.child.running", "child_run_id": "dataset-native-001"}],
        fallback_error={
            "status": "blocked",
            "code": "FIELD_NOT_FOUND",
            "error_summary": "字段缺失，需要修复后重试。",
            "sql": "SELECT * FROM secret_orders",
        },
    )

    assert payload["handoff_status"] == "blocked"
    assert payload["error_code"] == "FIELD_NOT_FOUND"
    assert payload["error_summary"] == "字段缺失，需要修复后重试。"
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

    assert result.parent_agent == "bi_worker"
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
    assert bridge.calls[0]["kwargs"]["agent_name"] == "bi_worker"


@pytest.mark.asyncio
async def test_agentscope_native_handoff_returns_safe_failure_when_session_start_fails(caplog):
    bridge = FailingStartBridge()
    native = AgentScopeNativeBIHandoff(bridge=bridge, dataset_agent_factory=FakeFactory())

    with caplog.at_level(logging.DEBUG, logger="app.domains.bi.agent.native_handoff"):
        result = await native.query_dataset(_handoff_request(), task_id="task-native")

    assert result.handoff_status == "failed"
    assert result.error_code == "AGENTSCOPE_NATIVE_HANDOFF_FAILED"
    assert result.artifact_ref is None
    assert bridge.calls[0]["method"] == "start_session"
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "BI Agent native handoff failed at start_session; internal details are hidden." in logs
    assert "secret_table" not in logs


@pytest.mark.asyncio
async def test_agentscope_native_handoff_logs_build_runtime_context_failure_stage(caplog):
    bridge = FakeBridge()
    native = FailingRuntimeContextHandoff(bridge=bridge, dataset_agent_factory=FakeFactory())

    with caplog.at_level(logging.DEBUG, logger="app.domains.bi.agent.native_handoff"):
        result = await native.query_dataset(_handoff_request(), task_id="task-native")

    assert result.handoff_status == "failed"
    assert result.error_code == "AGENTSCOPE_NATIVE_HANDOFF_FAILED"
    assert bridge.calls == []
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "BI Agent native handoff failed at build_runtime_context; internal details are hidden." in logs
    assert "secret_table" not in logs


@pytest.mark.asyncio
async def test_agentscope_native_handoff_uses_session_artifact_when_final_event_is_missing():
    bridge = FakeBridge(
        events=[],
        session=SimpleNamespace(artifact_ref="artifact-session-fallback", last_error=None),
    )
    native = AgentScopeNativeBIHandoff(bridge=bridge, dataset_agent_factory=FakeFactory())

    result = await native.query_dataset(_handoff_request(), task_id="task-native")

    assert result.handoff_status == "completed"
    assert result.artifact_ref == "artifact-session-fallback"


@pytest.mark.asyncio
async def test_agentscope_native_handoff_blocks_when_agent_stops_without_artifact():
    bridge = FakeBridge(
        events=[{"event_type": "agent.child.running", "child_run_id": "dataset-native-running"}],
        session=SimpleNamespace(artifact_ref=None, last_error=None),
    )
    native = AgentScopeNativeBIHandoff(bridge=bridge, dataset_agent_factory=FakeFactory())

    result = await native.query_dataset(_handoff_request(), task_id="task-native")

    assert result.handoff_status == "blocked"
    assert result.status_reason == "native_handoff_missing_terminal_event"
    assert result.error_code == "NATIVE_HANDOFF_MISSING_ARTIFACT"
    assert result.error_summary == "DatasetAgent native handoff 未生成安全结果引用，已停止补执行。"
    assert result.artifact_ref is None
    assert result.row_count is None
    assert result.column_count is None
    assert all(call["method"] != "run_direct_query" for call in bridge.calls)


@pytest.mark.asyncio
async def test_agentscope_native_handoff_logs_missing_terminal_evidence_blocked(caplog):
    bridge = FakeBridge(
        events=[{"event_type": "agent.child.running", "child_run_id": "dataset-native-running"}],
        session=SimpleNamespace(
            artifact_ref=None,
            last_error=None,
            expected_tool_name="list_candidate_assets",
            expected_tool_index=1,
            tool_results=[{"name": "get_dataset_status", "status": "draft"}],
        ),
    )
    native = AgentScopeNativeBIHandoff(bridge=bridge, dataset_agent_factory=FakeFactory())

    with caplog.at_level(logging.DEBUG, logger="app.domains.bi.agent.native_handoff"):
        result = await native.query_dataset(_handoff_request(), task_id="task-native")

    assert result.handoff_status == "blocked"
    assert result.error_code == "NATIVE_HANDOFF_MISSING_ARTIFACT"
    logs = "\n".join(record.getMessage() for record in caplog.records)
    for stage in (
        '"stage": "bi_agent.native_handoff.terminal_evidence.missing"',
        '"stage": "bi_agent.native_handoff.controlled_blueprint.skipped"',
    ):
        assert stage in logs
    assert '"terminal_diagnosis": "agent_stopped_before_expected_tool"' in logs
    assert '"expected_tool_at_stop": "list_candidate_assets"' in logs
    assert '"last_tool_name": "get_dataset_status"' in logs
    assert '"executed_tool_count": 1' in logs
    assert '"skip_reason": "db_missing"' in logs
    assert '"tool_results_digest": [{"column_count": null, "error_code": null, "has_artifact_ref": false, "name": "get_dataset_status", "row_count": null, "status": "draft"}]' in logs
    assert "direct_fallback" not in logs
    assert "SELECT" not in logs
    assert "secret_table" not in logs


@pytest.mark.asyncio
async def test_agentscope_native_handoff_completes_with_controlled_blueprint_when_agent_stops(
    db_session,
    sample_dataset,
    monkeypatch,
):
    blueprint = AnalysisBlueprint(
        dataset_id=sample_dataset.id,
        name="个人计划任务日报查询",
        status="active",
        implementation_type="sql_template",
        trigger_keywords=["日志", "工作日志"],
        parameters=[
            {"name": "person_name", "type": "string", "required": True},
            {"name": "start_date", "type": "date", "required": True},
            {"name": "end_date", "type": "date", "required": True},
        ],
        call_template="SELECT 1",
    )
    db_session.add(blueprint)
    db_session.commit()
    db_session.refresh(blueprint)
    bridge = FakeBridge(
        events=[{"event_type": "agent.child.running", "child_run_id": "dataset-native-running"}],
        session=SimpleNamespace(
            artifact_ref=None,
            last_error=None,
            expected_tool_name="list_candidate_assets",
            expected_tool_index=1,
            tool_results=[{"name": "get_dataset_status", "status": "draft"}],
        ),
    )

    def fake_execute(_db, bp, **kwargs):
        assert bp.id == blueprint.id
        assert kwargs["question"] == "查询杨凯2025年的工作日志"
        return {
            "ok": True,
            "params": {
                "person_name": "杨凯",
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
            },
            "sql_result": {
                "columns": ["person_name", "rzrq", "jtgznr"],
                "rows": [{"person_name": "杨凯", "rzrq": "2025-12-31", "jtgznr": "中心库代码架构优化"}],
                "row_count": 1,
                "sql_template": "SELECT hidden",
                "sql_preview": "SELECT hidden",
            },
            "row_count": 1,
            "execution_time_ms": 12,
        }

    monkeypatch.setattr("app.domains.bi.agent.native_handoff.execute_analysis_blueprint", fake_execute)
    native = AgentScopeNativeBIHandoff(bridge=bridge, dataset_agent_factory=FakeFactory(), db=db_session)
    request = _handoff_request().model_copy(
        update={"dataset_id": sample_dataset.id, "confirmed_question": "查询杨凯2025年的工作日志"}
    )

    result = await native.query_dataset(request, task_id="task-native")

    assert result.handoff_status == "completed"
    assert result.error_code is None
    assert result.artifact_ref and result.artifact_ref.startswith("artifact:")
    assert result.row_count == 1
    assert result.column_count == 3
    artifact = ArtifactStore(db_session).get(result.artifact_ref)
    assert artifact is not None
    assert artifact.content_json["rows"][0]["person_name"] == "杨凯"
    assert "sql_template" not in artifact.content_json
    assert "sql_preview" not in artifact.content_json


@pytest.mark.asyncio
async def test_agentscope_native_handoff_uses_session_error_when_final_event_is_missing():
    bridge = FakeBridge(
        events=[],
        session=SimpleNamespace(
            artifact_ref=None,
            last_error={
                "status": "blocked",
                "code": "FIELD_NOT_FOUND",
                "error_summary": "字段缺失，需要修复后重试。",
                "schema": {"orders": ["secret"]},
            },
        ),
    )
    native = AgentScopeNativeBIHandoff(bridge=bridge, dataset_agent_factory=FakeFactory())

    result = await native.query_dataset(_handoff_request(), task_id="task-native")

    assert result.handoff_status == "blocked"
    assert result.error_code == "FIELD_NOT_FOUND"
    assert result.error_summary == "字段缺失，需要修复后重试。"
    assert "schema" not in result.model_dump()


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
