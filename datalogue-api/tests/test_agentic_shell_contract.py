# ============================================================
# File Name   : test_agentic_shell_contract.py
# Description:
#   Datalogue Agentic Shell-first AS-R0 契约测试。
#
# Responsibilities:
#   - 验证 AS-R0 只启用 BI 主链 Agent，其他业务 Agent 作为 disabled placeholder。
#   - 验证 Agentic Shell 的工具白名单、上下文投影和输出清洗安全边界。
#   - 验证 BI atomic tool provider 第一阶段只暴露安全目录摘要，不泄露 SQL/schema/raw rows。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import subprocess
import sys

from app.models.dataset import AnalysisBlueprint
from app.services.artifact_store import ArtifactStore
from app.services.agentic_bi_tools import BIAtomicToolProvider
from app.services.agentic_shell import DatalogueAgenticShell, InMemoryAgenticShellWriter
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


def test_agentic_shell_as_r0_registry_enables_only_bi_main_chain():
    shell = DatalogueAgenticShell()

    contract = shell.prepare_turn(
        question="查询 GMV 和订单数",
        context={"dataset_id": 12, "thread_id": "thread-1"},
    )

    assert contract.status == "ready"
    assert contract.task_type == "bi_query"
    assert contract.selected_agent == "bi_lead_agent"
    assert contract.enabled_agents == ["bi_lead_agent"]
    assert {"report_agent", "python_agent", "audit_agent"}.issubset(contract.disabled_agents)

    assert contract.tool_policy.allowed_tools == [
        "get_dataset_status",
        "list_candidate_assets",
        "compile_dsl_to_sql",
        "execute_compiled_query",
        "create_query_artifact",
        "get_artifact_summary",
    ]
    assert contract.tool_policy.business_capabilities == ["query_dataset", "query_multiple_datasets"]
    assert "ask_bi" not in contract.tool_policy.allowed_tools
    assert "repair_dsl" in contract.tool_policy.disabled_tools
    assert "create_report_from_artifact" in contract.tool_policy.disabled_tools
    future_tool_status = {
        tool.name: tool.status for tool in contract.tool_policy.disabled_tool_specs
    }
    assert future_tool_status == {
        "repair_dsl": "admin_gated",
        "classify_query_failure": "disabled",
        "create_report_from_artifact": "admin_gated",
        "run_sandboxed_analysis_on_artifact": "admin_gated",
    }


def test_agentic_shell_context_projection_and_output_sanitizer_drop_execution_payloads():
    shell = DatalogueAgenticShell()

    contract = shell.prepare_turn(
        question="查询销售额",
        context={
            "dataset_id": 12,
            "conversation_id": 7,
            "sql": "select * from orders",
            "schema_context": {"tables": ["orders"]},
            "raw_rows": [{"amount": 1}],
            "query_plan": {"steps": ["internal"]},
            "blueprint": {"raw_sql": "select 1"},
            "safe_note": "保留业务上下文",
        },
    )

    dumped_context = contract.projected_context.model_dump()
    assert dumped_context == {
        "conversation_id": 7,
        "dataset_id": 12,
        "question": "查询销售额",
        "safe_note": "保留业务上下文",
    }

    sanitized = shell.sanitize_output(
        {
            "answer": "已生成查询结果",
            "sql": "select * from orders",
            "artifact": {
                "artifact_ref": "artifact:query:1",
                "raw_rows": [{"amount": 1}],
                "schema": {"orders": ["amount"]},
            },
            "events": [{"type": "checkpoint", "repair_patch": {"body": "internal"}}],
            "debug": {
                "queryPlan": {"steps": ["internal"]},
                "repairPatch": {"body": "internal"},
                "rows": [{"n": 1}],
                "fields": ["orders.amount"],
                "safe_label": "GMV",
            },
        }
    )

    assert sanitized == {
        "answer": "已生成查询结果",
        "artifact": {"artifact_ref": "artifact:query:1"},
        "events": [{"type": "checkpoint"}],
        "debug": {"safe_label": "GMV"},
    }


def test_agentic_shell_non_bi_task_routes_to_disabled_placeholder_without_tools():
    shell = DatalogueAgenticShell()

    contract = shell.prepare_turn(question="根据查询结果生成一份经营报告")

    assert contract.status == "disabled"
    assert contract.task_type == "report"
    assert contract.selected_agent == "report_agent"
    assert contract.enabled_agents == ["bi_lead_agent"]
    assert "report_agent" in contract.disabled_agents
    assert contract.tool_policy.allowed_tools == []


def test_agentic_shell_bi_lead_agent_routes_only_query_capabilities():
    shell = DatalogueAgenticShell()

    action = shell.route_agent_action(
        question="查询 GMV",
        context={"dataset_id": 12, "sql": "select * from orders"},
        capability="query_dataset",
    )

    assert action.status == "ready"
    assert action.selected_agent == "bi_lead_agent"
    assert action.action_type == "bi_lead_agent.capability_route"
    assert action.capability == "query_dataset"
    assert action.allowed_capabilities == ["query_dataset", "query_multiple_datasets"]
    assert action.payload == {"question": "查询 GMV", "dataset_id": 12}

    blocked = shell.route_agent_action(
        question="查询 GMV",
        context={"dataset_id": 12},
        capability="create_report_from_artifact",
    )

    assert blocked.status == "disabled"
    assert blocked.selected_agent == "bi_lead_agent"
    assert blocked.action_type == "bi_lead_agent.disabled"
    assert blocked.capability == "create_report_from_artifact"
    assert blocked.allowed_capabilities == ["query_dataset", "query_multiple_datasets"]
    assert blocked.disabled_reason == "capability_not_whitelisted"


def test_agentic_shell_report_python_audit_return_disabled_actions():
    shell = DatalogueAgenticShell()

    report_action = shell.route_agent_action(question="根据查询结果生成一份经营报告")
    python_action = shell.route_agent_action(question="用 python 分析查询结果")
    audit_action = shell.route_agent_action(question="审计这次查询")

    assert [action.status for action in (report_action, python_action, audit_action)] == [
        "disabled",
        "disabled",
        "disabled",
    ]
    assert [action.selected_agent for action in (report_action, python_action, audit_action)] == [
        "report_agent",
        "python_agent",
        "audit_agent",
    ]
    assert [action.action_type for action in (report_action, python_action, audit_action)] == [
        "report_agent.disabled",
        "python_agent.disabled",
        "audit_agent.disabled",
    ]
    assert all(action.capability is None for action in (report_action, python_action, audit_action))
    assert all(action.allowed_capabilities == [] for action in (report_action, python_action, audit_action))
    assert all(action.disabled_reason == "agent_disabled_placeholder" for action in (report_action, python_action, audit_action))


def test_agentic_shell_writer_interface_sanitizes_event_action_and_checkpoint_payloads():
    writer = InMemoryAgenticShellWriter()
    shell = DatalogueAgenticShell(writer=writer)

    event_record = shell.record_event(
        event_type="dataset.query.completed",
        thread_id="as_thread",
        message_id="msg-1",
        payload={
            "artifact_ref": "artifact:query:1",
            "sql": "select * from orders",
            "raw_rows": [{"amount": 1}],
            "query_plan": {"steps": ["internal"]},
        },
    )
    action_record = shell.record_action(
        action_id="retry_last_step",
        thread_id="as_thread",
        message_id="msg-1",
        payload={
            "checkpoint_ref": "checkpoint://task/query_context_ready",
            "selected_action": "retry_last_step",
            "schema": {"orders": ["amount"]},
            "repairPatch": {"body": "internal"},
        },
    )
    checkpoint_record = shell.record_checkpoint(
        checkpoint_ref="checkpoint://task/query_context_ready",
        thread_id="as_thread",
        message_id="msg-1",
        payload={
            "checkpoint_kind": "query_context_ready",
            "dataset_id": 12,
            "fields": ["orders.amount"],
            "raw_result": [{"amount": 1}],
        },
    )

    assert [record.write_kind for record in writer.records] == ["event", "action", "checkpoint"]
    assert event_record.payload == {"artifact_ref": "artifact:query:1"}
    assert action_record.payload == {
        "checkpoint_ref": "checkpoint://task/query_context_ready",
        "selected_action": "retry_last_step",
    }
    assert checkpoint_record.payload == {"checkpoint_kind": "query_context_ready", "dataset_id": 12}
    assert all(record.persisted is False for record in writer.records)

    dumped = repr([record.model_dump(mode="json") for record in writer.records])
    for forbidden in ("select *", "raw_rows", "query_plan", "orders.amount", "repairPatch", "raw_result"):
        assert forbidden not in dumped


def test_agentic_shell_default_writer_is_noop_interface_only():
    shell = DatalogueAgenticShell()

    record = shell.record_event(
        event_type="answer.completed",
        thread_id="as_thread",
        payload={"artifact_ref": "artifact:query:1"},
    )

    assert record.write_kind == "event"
    assert record.persisted is False
    assert record.writer_name == "noop"
    assert record.payload == {"artifact_ref": "artifact:query:1"}


def test_bi_atomic_tool_provider_and_runtime_driver_import_in_clean_process():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib;"
                "importlib.import_module('app.services.agentic_bi_tools');"
                "importlib.import_module('app.services.agentscope_runtime_driver')"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_bi_atomic_tool_provider_exposes_safe_dataset_status_and_full_catalog(
    db_session,
    sample_dataset,
):
    blueprint = AnalysisBlueprint(
        dataset_id=sample_dataset.id,
        name="区域销售诊断",
        description="按区域定位销售变化",
        trigger_keywords=["区域", "销售"],
        when_to_use="需要解释区域销售变化时使用",
        raw_sql="select * from secret_orders",
        status="active",
    )
    db_session.add(blueprint)
    db_session.commit()
    db_session.refresh(blueprint)

    provider = BIAtomicToolProvider(db_session)

    status = provider.get_dataset_status(sample_dataset.id)
    catalog = provider.list_candidate_assets(sample_dataset.id, question="这个参数第一阶段保留但不参与召回")

    assert status == {
        "dataset_id": sample_dataset.id,
        "name": "测试数据集",
        "status": "active",
        "metric_count": 2,
        "dimension_count": 2,
        "blueprint_count": 1,
        "metadata_schema_summary": {"selected_table_count": 0},
    }
    assert catalog["dataset_id"] == sample_dataset.id
    assert catalog["question_used"] is False
    assert [item["name"] for item in catalog["metric"]] == ["GMV", "订单数"]
    assert [item["name"] for item in catalog["dimension"]] == ["地区", "品类"]
    assert catalog["blueprint"] == [
        {
            "id": blueprint.id,
            "name": "区域销售诊断",
            "description": "按区域定位销售变化",
            "trigger_keywords": ["区域", "销售"],
            "when_to_use": "需要解释区域销售变化时使用",
        }
    ]

    dumped = repr(catalog) + repr(status)
    for forbidden in ("raw_sql", "select *", "schema_context", "raw_rows", "orders.amount"):
        assert forbidden not in dumped


def test_bi_atomic_tool_provider_compiles_dsl_to_private_handle_without_sql(
    db_session,
    sample_dataset,
):
    provider = BIAtomicToolProvider(db_session)
    dsl = QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.86,
        selected_assets=[
            _field_asset("日志ID", "user_logs", "id"),
            _field_asset("账号", "user_logs", "account"),
        ],
        debug={"selected_main_table": "user_logs"},
    ).to_dict()

    response = provider.compile_dsl_to_sql(
        dataset_id=sample_dataset.id,
        dsl=dsl,
        sql_generation_context={"table_schemas": [{"table_name": "user_logs"}]},
        dialect="sqlite",
        query_constraints={"enabled": True, "default_limit": 10, "max_limit": 100},
        allowed_tables=["user_logs"],
    )

    assert response["status"] == "compiled"
    assert response["compiled_query_ref"].startswith("compiled_query:")
    assert response["dataset_id"] == sample_dataset.id
    assert response["execution_source"] == "tool_compiler"
    assert response["execution_guard"]["ok"] is True
    assert response["execution_guard"]["warning_count"] == response["warning_count"]
    assert isinstance(response["warning_count"], int)

    dumped = repr(response)
    for forbidden in ("select ", "user_logs", "account", "query_plan", "sql_generation_context", "sql_guard"):
        assert forbidden not in dumped.lower()


def test_bi_atomic_tool_provider_executes_private_handle_to_artifact_without_rows_in_response(
    db_session,
    sample_dataset,
):
    executed_sql: list[str] = []

    def fake_executor(sql: str):
        executed_sql.append(sql)
        return {
            "columns": ["账号"],
            "rows": [{"账号": "alice"}],
            "row_count": 1,
        }

    provider = BIAtomicToolProvider(db_session, query_executor=fake_executor)
    compiled = provider.compile_dsl_to_sql(
        dataset_id=sample_dataset.id,
        dsl=QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.86,
            selected_assets=[_field_asset("账号", "user_logs", "account")],
            debug={"selected_main_table": "user_logs"},
        ),
        sql_generation_context={"table_schemas": [{"table_name": "user_logs"}]},
        dialect="sqlite",
        allowed_tables=["user_logs"],
    )

    response = provider.execute_compiled_query(
        compiled_query_ref=compiled["compiled_query_ref"],
        dataset_id=sample_dataset.id,
        conversation_id=7,
        trace_id="trace-pr0-3",
    )

    assert executed_sql and "SELECT" in executed_sql[0]
    assert response["status"] == "completed"
    assert response["row_count"] == 1
    assert response["column_count"] == 1
    assert response["artifact_ref"].startswith("artifact:")

    dumped_response = repr(response)
    for forbidden in ("SELECT", "user_logs", "alice", "rows", "sql"):
        assert forbidden.lower() not in dumped_response.lower()

    artifact = ArtifactStore(db_session).get(response["artifact_ref"])
    assert artifact is not None
    assert artifact.dataset_id == sample_dataset.id
    assert artifact.conversation_id == 7
    assert artifact.trace_id == "trace-pr0-3"
    assert artifact.content_json["rows"] == [{"账号": "alice"}]


def test_bi_atomic_tool_provider_executes_unknown_handle_fail_closed(db_session):
    provider = BIAtomicToolProvider(db_session, query_executor=lambda _sql: {"rows": []})

    response = provider.execute_compiled_query(compiled_query_ref="compiled_query:missing")

    assert response == {
        "status": "not_found",
        "compiled_query_ref": "compiled_query:missing",
        "artifact_ref": None,
    }


def test_bi_atomic_tool_provider_execute_rejects_dataset_mismatch_without_executor(
    db_session,
    sample_dataset,
):
    executed_sql: list[str] = []

    def fake_executor(sql: str):
        executed_sql.append(sql)
        return {"rows": [{"账号": "alice"}]}

    provider = BIAtomicToolProvider(db_session, query_executor=fake_executor)
    compiled = provider.compile_dsl_to_sql(
        dataset_id=sample_dataset.id,
        dsl=QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.86,
            selected_assets=[_field_asset("账号", "user_logs", "account")],
            debug={"selected_main_table": "user_logs"},
        ),
        sql_generation_context={"table_schemas": [{"table_name": "user_logs"}]},
        dialect="sqlite",
        allowed_tables=["user_logs"],
    )

    response = provider.execute_compiled_query(
        compiled_query_ref=compiled["compiled_query_ref"],
        dataset_id=sample_dataset.id + 999,
    )

    assert response == {
        "status": "blocked",
        "code": "DATASET_MISMATCH",
        "compiled_query_ref": compiled["compiled_query_ref"],
        "artifact_ref": None,
    }
    assert executed_sql == []
