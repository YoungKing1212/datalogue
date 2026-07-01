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

from typing import Any

from app.services.agentic_bi_tools import BIAtomicToolProvider
from app.services.agentic_dataset_runtime import DatasetAgentToolCallRuntime
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
