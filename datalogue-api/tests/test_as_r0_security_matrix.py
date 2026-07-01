# ============================================================
# File Name   : test_as_r0_security_matrix.py
# Description:
#   AS-R0 安全测试矩阵。
#
# Responsibilities:
#   - 验证 Agent context、BI tool response、SSE payload、AgentScope mirror 和 Workbench View Model 的禁露边界。
#   - 固化 SQL/schema/物理字段/raw rows/query_plan/RepairPatch/blueprint body 不进入用户或 Agent 可见层。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import json

import pytest
from fastapi.encoders import jsonable_encoder

from app.api.chat import _with_event_envelope
from app.models.agentscope_workbench import AgentScopeMessage, AgentScopeSession
from app.services.agentic_shell import DatalogueAgenticShell
from app.services.agentscope_mirror import (
    create_agentscope_session,
    record_agentscope_event,
)
from app.services.bi_tools import build_bi_atomic_toolkit
from app.services.subagent_planning.contracts import CandidateAsset, QueryPlan
from app.services.workbench_view_model import build_workbench_thread_view


FORBIDDEN_VISIBLE_TOKENS = (
    "select ",
    "hidden_table",
    "secret_col",
    "schema_context",
    "raw_rows",
    "private_row",
    "query_plan",
    "repair_patch",
    "repairpatch",
    "patch_body",
    "blueprint_body",
    "blueprintbody",
    "work_log.work_date",
)


def _assert_no_forbidden_visible_tokens(value) -> None:
    dumped = json.dumps(jsonable_encoder(value), ensure_ascii=False).lower()
    for token in FORBIDDEN_VISIBLE_TOKENS:
        assert token not in dumped


def _field_asset(name: str, table_name: str, column_name: str) -> CandidateAsset:
    return CandidateAsset(
        asset_type="field",
        asset_id=f"{table_name}.{column_name}",
        name=name,
        display_name=name,
        source="schema",
        confidence=0.9,
        metadata={"table_name": table_name, "column_name": column_name},
        usage="selected",
    )


def test_as_r0_agent_context_and_bi_tool_responses_hide_execution_payloads(
    db_session,
    sample_dataset,
):
    shell = DatalogueAgenticShell()
    contract = shell.prepare_turn(
        question="查询账号明细",
        context={
            "dataset_id": sample_dataset.id,
            "schema_context": {"tables": ["hidden_table"]},
            "raw_rows": [{"secret_col": "private_row"}],
            "query_plan": {"debug": "SELECT secret_col FROM hidden_table"},
            "repair_patch": {"patch_body": "work_log.work_date"},
            "blueprint_body": {"sql": "SELECT secret_col FROM hidden_table"},
        },
    )

    toolkit = build_bi_atomic_toolkit(
        db_session,
        query_executor=lambda _sql: {
            "columns": ["账号"],
            "rows": [{"账号": "private_row"}],
            "row_count": 1,
        },
    )
    compiled = toolkit.execute_tool(
        "compile_dsl_to_sql",
        dataset_id=sample_dataset.id,
        dsl=QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.86,
            selected_assets=[
                _field_asset("账号", "hidden_table", "secret_col"),
            ],
            debug={"selected_main_table": "hidden_table"},
        ),
        sql_generation_context={"table_schemas": [{"table_name": "hidden_table"}]},
        dialect="sqlite",
        allowed_tables=["hidden_table"],
    )
    executed = toolkit.execute_tool(
        "execute_compiled_query",
        compiled_query_ref=compiled["compiled_query_ref"],
        dataset_id=sample_dataset.id,
    )
    artifact_summary = toolkit.execute_tool("get_artifact_summary", artifact_ref=executed["artifact_ref"])

    _assert_no_forbidden_visible_tokens(contract.model_dump(mode="json"))
    _assert_no_forbidden_visible_tokens(compiled)
    _assert_no_forbidden_visible_tokens(executed)
    _assert_no_forbidden_visible_tokens(artifact_summary)


def test_as_r0_sse_payload_matrix_hides_execution_payloads():
    visible = _with_event_envelope(
        {
            "type": "final",
            "answer": "查询完成",
            "sql": "SELECT secret_col FROM hidden_table",
            "schema_context": {"tables": ["hidden_table"]},
            "raw_rows": [{"secret_col": "private_row"}],
            "query_plan": {"debug": "SELECT secret_col FROM hidden_table"},
            "repair_patch": {"patch_body": "work_log.work_date"},
            "blueprint_body": {"sql": "SELECT secret_col FROM hidden_table"},
            "result_ref": "artifact:result-1",
        },
        event_type="answer.completed",
        visibility="user_visible",
        payload_fields=(
            "answer",
            "result_ref",
            "schema_context",
            "raw_rows",
            "query_plan",
            "repair_patch",
            "blueprint_body",
        ),
    )

    trace_only = _with_event_envelope(
        {
            "type": "step",
            "node": "query_plan",
            "query_plan": {"debug": "SELECT secret_col FROM hidden_table"},
            "repair_patch": {"patch_body": "work_log.work_date"},
            "blueprint_body": {"sql": "SELECT secret_col FROM hidden_table"},
        },
        event_type="dataset.query.started",
        visibility="trace_only",
        payload_fields=("type", "node", "query_plan", "repair_patch", "blueprint_body"),
    )

    _assert_no_forbidden_visible_tokens(visible)
    _assert_no_forbidden_visible_tokens(trace_only)


def test_as_r0_agentscope_mirror_rejects_forbidden_metadata_and_event_payloads(db_session):
    with pytest.raises(ValueError, match="AGENTSCOPE_MIRROR_PAYLOAD_LEAK_DETECTED"):
        create_agentscope_session(
            db_session,
            thread_id="as_99999999-9999-9999-9999-999999999999",
            title="安全矩阵",
            metadata={"agentic_runtime_boundary": {"blueprint_body": {"body": "private"}}},
        )

    session = create_agentscope_session(
        db_session,
        thread_id="as_98989898-9898-9898-9898-989898989898",
        title="安全矩阵",
    )
    for payload in (
        {"repair_patch": {"patch_body": "work_log.work_date"}},
        {"blueprint_body": {"body": "private"}},
    ):
        with pytest.raises(ValueError, match="AGENTSCOPE_MIRROR_PAYLOAD_LEAK_DETECTED"):
            record_agentscope_event(
                db_session,
                thread_id=session.thread_id,
                message_id=None,
                event_type="answer.completed",
                payload=payload,
                visibility="user",
                task_id=None,
                trace_id=None,
            )


def test_as_r0_workbench_view_model_fails_closed_for_forbidden_stored_payload(db_session):
    session = AgentScopeSession(
        thread_id="as_97979797-9797-9797-9797-979797979797",
        source_type="agentscope",
        title="污染数据",
        status="active",
        metadata_json={},
    )
    message = AgentScopeMessage(
        message_id="msg_security_matrix",
        thread_id=session.thread_id,
        role="assistant",
        status="completed",
        content_summary="查询完成",
        business_payload_json={"repair_patch": {"patch_body": "work_log.work_date"}},
    )
    db_session.add_all([session, message])
    db_session.commit()

    with pytest.raises(ValueError, match="WORKBENCH_VIEW_PAYLOAD_LEAK_DETECTED"):
        build_workbench_thread_view(db_session, thread_id=session.thread_id)
