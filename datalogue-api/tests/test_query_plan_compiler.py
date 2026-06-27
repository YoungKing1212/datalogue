from app.services.query_plan_compiler import compile_query_plan_to_sql
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


def test_query_plan_compiler_outputs_tool_compiler_sql():
    plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.87,
        selected_assets=[
            _field_asset("日志ID", "user_logs", "id"),
            _field_asset("账号", "user_logs", "account"),
        ],
        debug={"selected_main_table": "user_logs"},
    )

    result = compile_query_plan_to_sql(
        query_plan=plan,
        sql_generation_context={"table_schemas": [{"table_name": "user_logs"}]},
        dialect="sqlite",
        query_constraints={"enabled": True, "default_limit": 10, "max_limit": 100},
        allowed_tables=["user_logs"],
    )

    assert result["ok"] is True
    assert result["execution_source"] == "tool_compiler"
    assert result["sql_guard"]["ok"] is True
    assert "user_logs" in result["sql"]
    assert "account" in result["sql"]
    assert result["control_plane"]["execution_source"] == "tool_compiler"
    assert result["query_artifact"]["sql"] == result["sql"]


def test_query_plan_compiler_rejects_llm_sql_as_execution_basis():
    plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.8,
        selected_assets=[_field_asset("日志ID", "user_logs", "id")],
    )

    result = compile_query_plan_to_sql(
        query_plan=plan,
        sql_generation_context={"llm_sql": "SELECT * FROM user_logs"},
        dialect="sqlite",
        allowed_tables=["user_logs"],
    )

    assert result["ok"] is False
    assert result["code"] == "LLM_SQL_NOT_EXECUTABLE"
    assert result["sql"] is None
    assert result["execution_source"] == "tool_compiler"


def test_query_plan_compiler_fails_closed_for_unknown_dialect():
    plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.8,
        selected_assets=[_field_asset("日志ID", "user_logs", "id")],
    )

    result = compile_query_plan_to_sql(
        query_plan=plan,
        sql_generation_context={},
        dialect="snowflake",
        allowed_tables=["user_logs"],
    )

    assert result["ok"] is False
    assert result["code"] == "DIALECT_UNSUPPORTED_FOR_CURRENT_DATASOURCE"
    assert result["sql"] is None


def test_query_plan_compiler_rejects_dialect_mismatch_with_current_datasource():
    plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.8,
        selected_assets=[_field_asset("日志ID", "user_logs", "id")],
    )

    result = compile_query_plan_to_sql(
        query_plan=plan,
        sql_generation_context={},
        dialect="mysql",
        current_datasource_dialect="sqlite",
        allowed_tables=["user_logs"],
    )

    assert result["ok"] is False
    assert result["code"] == "DIALECT_UNSUPPORTED_FOR_CURRENT_DATASOURCE"
    assert result["sql"] is None
