# ============================================================
# File Name   : test_agentic_dataset_runtime.py
# Description:
#   AS-R0 PR1.3 DatasetAgent tool-call runtime 测试。
#
# Responsibilities:
#   - 验证 DatasetAgent Runtime 只能通过 BI atomic tools 完成查询链路。
#   - 验证 DSL 编译、执行和 artifact summary 响应不暴露 SQL/schema/raw rows/query_plan。
#   - 验证 compile 失败时 fail-closed，不调用 execute 工具。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import logging
from typing import Any

from app.services.agentic_bi_tools import BIAtomicToolProvider
from app.services.agentic_dataset_runtime import (
    DatasetAgentNextToolCall,
    DatasetAgentToolCallRuntime,
)
from app.services.artifact_store import ArtifactStore
from app.services.subagent_planning import CandidateAsset, QueryPlan


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


def test_dataset_agent_tool_runtime_runs_atomic_tool_chain_to_artifact_summary(
    db_session,
    sample_dataset,
):
    executed_sql: list[str] = []
    generator_inputs: list[dict[str, Any]] = []

    def fake_executor(sql: str) -> dict[str, Any]:
        executed_sql.append(sql)
        return {"columns": ["账号"], "rows": [{"账号": "alice"}], "row_count": 1}

    def fake_dsl_generator(**kwargs: Any) -> QueryPlan:
        generator_inputs.append(kwargs)
        return QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.91,
            selected_assets=[_field_asset("账号", "user_logs", "account")],
            debug={"selected_main_table": "user_logs"},
        )

    provider = BIAtomicToolProvider(db_session, query_executor=fake_executor)
    runtime = DatasetAgentToolCallRuntime(provider=provider, dsl_generator=fake_dsl_generator)

    result = runtime.run_query(
        dataset_id=sample_dataset.id,
        question="查询账号明细",
        sql_generation_context={"table_schemas": [{"table_name": "user_logs"}]},
        dialect="sqlite",
        allowed_tables=["user_logs"],
        conversation_id=7,
        trace_id="trace-pr1-3",
    )

    assert [call["name"] for call in result["tool_calls"]] == [
        "get_dataset_status",
        "list_candidate_assets",
        "generate_dsl",
        "compile_dsl_to_sql",
        "execute_compiled_query",
        "get_artifact_summary",
    ]
    assert result["status"] == "completed"
    assert result["artifact_ref"].startswith("artifact:")
    assert result["artifact_summary"]["artifact_ref"] == result["artifact_ref"]
    assert result["row_count"] == 1
    assert result["column_count"] == 1
    assert executed_sql and "SELECT" in executed_sql[0]
    assert generator_inputs[0]["dataset_status"]["dataset_id"] == sample_dataset.id
    assert generator_inputs[0]["candidate_assets"]["question_used"] is False

    artifact = ArtifactStore(db_session).get(result["artifact_ref"])
    assert artifact is not None
    assert artifact.content_json["rows"] == [{"账号": "alice"}]

    dumped = repr(result)
    for forbidden in ("SELECT", "user_logs", "account", "alice", "raw_rows", "query_plan", "schema"):
        assert forbidden.lower() not in dumped.lower()


def test_dataset_agent_runtime_logs_safe_runtime_steps_without_legacy_langgraph_terms(
    db_session,
    sample_dataset,
    caplog,
):
    def fake_executor(_sql: str) -> dict[str, Any]:
        return {"columns": ["账号"], "rows": [{"账号": "alice"}], "row_count": 1}

    def fake_dsl_generator(**_kwargs: Any) -> QueryPlan:
        return QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.91,
            selected_assets=[_field_asset("账号", "user_logs", "account")],
            debug={"selected_main_table": "user_logs"},
        )

    provider = BIAtomicToolProvider(db_session, query_executor=fake_executor)
    runtime = DatasetAgentToolCallRuntime(provider=provider, dsl_generator=fake_dsl_generator)

    with caplog.at_level(logging.INFO, logger="app.services.agentic_dataset_runtime"):
        result = runtime.run_query(
            dataset_id=sample_dataset.id,
            question="查询账号明细",
            sql_generation_context={"table_schemas": [{"table_name": "user_logs"}]},
            allowed_tables=["user_logs"],
            conversation_id=7,
            trace_id="trace-runtime-log",
        )

    assert result["status"] == "completed"
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[dataset_agent.runtime.start]" in logs
    assert "[dataset_agent.runtime.tool]" in logs
    assert "[dataset_agent.runtime.result]" in logs
    for expected_tool in DatasetAgentToolCallRuntime.TOOL_SEQUENCE:
        assert f'"tool": "{expected_tool}"' in logs
    for forbidden in (
        "LangGraph",
        "build_workflow",
        "DatasetSubAgent",
        "SELECT",
        "user_logs",
        "account",
        "alice",
        "raw_rows",
        "query_plan",
        "schema",
    ):
        assert forbidden.lower() not in logs.lower()


def test_dataset_agent_tool_runtime_compile_failure_blocks_execute(db_session, sample_dataset):
    executed = False

    def fail_executor(_sql: str) -> dict[str, Any]:
        nonlocal executed
        executed = True
        return {"rows": []}

    def invalid_dsl_generator(**_kwargs: Any) -> dict[str, Any]:
        return {
            "query_type": "invalid",
            "execution_strategy": "query_graph",
            "confidence": 0.1,
            "sql": "select * from user_logs",
        }

    provider = BIAtomicToolProvider(db_session, query_executor=fail_executor)
    runtime = DatasetAgentToolCallRuntime(provider=provider, dsl_generator=invalid_dsl_generator)

    result = runtime.run_query(
        dataset_id=sample_dataset.id,
        question="查询账号明细",
        sql_generation_context={"table_schemas": [{"table_name": "user_logs"}]},
        allowed_tables=["user_logs"],
    )

    assert result["status"] == "blocked"
    assert result["code"] == "DSL_INVALID"
    assert [call["name"] for call in result["tool_calls"]] == [
        "get_dataset_status",
        "list_candidate_assets",
        "generate_dsl",
        "compile_dsl_to_sql",
    ]
    assert executed is False

    dumped = repr(result)
    for forbidden in ("select *", "user_logs", "raw_rows", "query_plan", "schema"):
        assert forbidden.lower() not in dumped.lower()


def test_dataset_agent_runtime_allows_agent_next_tool_calls_but_enforces_order_and_handles(
    db_session,
    sample_dataset,
):
    executed_sql: list[str] = []

    def fake_executor(sql: str) -> dict[str, Any]:
        executed_sql.append(sql)
        return {"columns": ["账号"], "rows": [{"账号": "alice"}], "row_count": 1}

    def fake_dsl_generator(**_kwargs: Any) -> QueryPlan:
        return QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.91,
            selected_assets=[_field_asset("账号", "user_logs", "account")],
            debug={"selected_main_table": "user_logs"},
        )

    provider = BIAtomicToolProvider(db_session, query_executor=fake_executor)
    runtime = DatasetAgentToolCallRuntime(provider=provider, dsl_generator=fake_dsl_generator)
    session = runtime.start_tool_call_session(
        dataset_id=sample_dataset.id,
        question="查询账号明细",
        sql_generation_context={"table_schemas": [{"table_name": "user_logs"}]},
        allowed_tables=["user_logs"],
        conversation_id=7,
        trace_id="trace-agent-loop",
    )

    outputs: list[dict[str, Any]] = []
    for name in (
        "get_dataset_status",
        "list_candidate_assets",
        "generate_dsl",
        "compile_dsl_to_sql",
    ):
        outputs.append(runtime.handle_agent_tool_call(session, DatasetAgentNextToolCall(name=name)))

    compile_output = outputs[-1]
    assert compile_output["status"] == "compiled"
    assert compile_output["agent_context"] == {
        "compiled_query_ref": compile_output["compiled_query_ref"]
    }

    execute_output = runtime.handle_agent_tool_call(
        session,
        DatasetAgentNextToolCall(
            name="execute_compiled_query",
            arguments={"compiled_query_ref": compile_output["compiled_query_ref"]},
        ),
    )
    summary_output = runtime.handle_agent_tool_call(
        session,
        DatasetAgentNextToolCall(name="get_artifact_summary"),
    )

    assert execute_output["status"] == "completed"
    assert summary_output["status"] == "ready"
    assert summary_output["artifact_ref"] == execute_output["artifact_ref"]
    assert executed_sql and "SELECT" in executed_sql[0]
    assert session.status == "completed"

    dumped = repr(outputs + [execute_output, summary_output])
    for forbidden in ("SELECT", "user_logs", "account", "alice", "raw_rows", "query_plan", "schema"):
        assert forbidden.lower() not in dumped.lower()


def test_dataset_agent_runtime_rejects_unwhitelisted_or_out_of_order_agent_tool_calls(
    db_session,
    sample_dataset,
):
    provider = BIAtomicToolProvider(db_session, query_executor=lambda _sql: {"rows": []})
    runtime = DatasetAgentToolCallRuntime(provider=provider, dsl_generator=lambda **_kwargs: {})
    session = runtime.start_tool_call_session(dataset_id=sample_dataset.id, question="查询账号明细")

    unknown = runtime.handle_agent_tool_call(
        session,
        DatasetAgentNextToolCall(name="drop_table", arguments={"sql": "DROP TABLE user_logs"}),
    )
    assert unknown["status"] == "blocked"
    assert unknown["code"] == "TOOL_NOT_WHITELISTED"

    out_of_order = runtime.handle_agent_tool_call(
        session,
        DatasetAgentNextToolCall(name="execute_compiled_query", arguments={"compiled_query_ref": "compiled_query:fake"}),
    )
    assert out_of_order["status"] == "blocked"
    assert out_of_order["code"] == "TOOL_ORDER_VIOLATION"

    dumped = repr([unknown, out_of_order])
    for forbidden in ("DROP TABLE", "user_logs", "sql"):
        assert forbidden.lower() not in dumped.lower()


def test_dataset_agent_runtime_execute_accepts_only_compile_produced_handle(
    db_session,
    sample_dataset,
):
    provider = BIAtomicToolProvider(db_session, query_executor=lambda _sql: {"rows": []})
    runtime = DatasetAgentToolCallRuntime(
        provider=provider,
        dsl_generator=lambda **_kwargs: QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.91,
            selected_assets=[_field_asset("账号", "user_logs", "account")],
            debug={"selected_main_table": "user_logs"},
        ),
    )
    session = runtime.start_tool_call_session(
        dataset_id=sample_dataset.id,
        question="查询账号明细",
        sql_generation_context={"table_schemas": [{"table_name": "user_logs"}]},
        allowed_tables=["user_logs"],
    )

    for name in (
        "get_dataset_status",
        "list_candidate_assets",
        "generate_dsl",
        "compile_dsl_to_sql",
    ):
        runtime.handle_agent_tool_call(session, DatasetAgentNextToolCall(name=name))

    forged = runtime.handle_agent_tool_call(
        session,
        DatasetAgentNextToolCall(
            name="execute_compiled_query",
            arguments={"compiled_query_ref": "compiled_query:forged"},
        ),
    )

    assert forged["status"] == "blocked"
    assert forged["code"] == "COMPILED_QUERY_REF_MISMATCH"
    dumped = repr(forged)
    for forbidden in ("SELECT", "user_logs", "account", "schema"):
        assert forbidden.lower() not in dumped.lower()


def test_dataset_agent_runtime_rejects_sensitive_arguments_even_for_whitelisted_tool(
    db_session,
    sample_dataset,
):
    provider = BIAtomicToolProvider(db_session, query_executor=lambda _sql: {"rows": []})
    runtime = DatasetAgentToolCallRuntime(provider=provider, dsl_generator=lambda **_kwargs: {})
    session = runtime.start_tool_call_session(dataset_id=sample_dataset.id, question="查询账号明细")

    result = runtime.handle_agent_tool_call(
        session,
        DatasetAgentNextToolCall(
            name="get_dataset_status",
            arguments={"sql": "SELECT * FROM user_logs", "schema_context": {"table": "user_logs"}},
        ),
    )

    assert result["status"] == "blocked"
    assert result["code"] == "SENSITIVE_TOOL_ARGUMENT"
    dumped = repr(result)
    for forbidden in ("SELECT", "user_logs", "schema_context", "sql"):
        assert forbidden.lower() not in dumped.lower()
