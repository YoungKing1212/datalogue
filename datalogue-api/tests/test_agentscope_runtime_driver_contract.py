# ============================================================
# File Name   : test_agentscope_runtime_driver_contract.py
# Description:
#   AgentScope Runtime driver AS-R0 边界契约测试。
#
# Responsibilities:
#   - 验证 Runtime driver 只消费 Agentic Shell 生成的受控回合契约。
#   - 验证 Runtime 可见工具 registry 只包含已实现的 BI atomic tools。
#   - 验证 disabled placeholder 任务 fail-closed，不触发旧 ask_bi 外层桥接。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import pytest

from app.runtime import DatalogueAgentScopeRuntimeDriver
from app.agents.agentic_lead_agent import AgenticLeadAgent


def test_agentscope_runtime_driver_accepts_only_agentic_shell_contract():
    driver = DatalogueAgentScopeRuntimeDriver()
    shell = AgenticLeadAgent()
    shell_contract = shell.prepare_turn(
        question="查询 GMV",
        context={"dataset_id": 12, "sql": "select * from orders"},
    )

    runtime_contract = driver.from_shell_contract(shell_contract)

    assert runtime_contract.status == "ready"
    assert runtime_contract.driver_name == "agentscope_runtime_boundary"
    assert runtime_contract.contract_version == "as-r0-runtime-boundary"
    assert runtime_contract.projected_context == {"question": "查询 GMV", "dataset_id": 12}

    with pytest.raises(TypeError):
        driver.from_shell_contract({"question": "raw chat payload"})


def test_agentscope_runtime_driver_registers_bi_atomic_tools_without_ask_bi():
    runtime_contract = DatalogueAgentScopeRuntimeDriver().prepare_runtime(
        question="查询 GMV",
        context={"dataset_id": 12},
    )

    assert [tool.name for tool in runtime_contract.tool_registry] == [
        "get_dataset_status",
        "list_candidate_assets",
        "compile_dsl_to_sql",
        "execute_compiled_query",
        "create_query_artifact",
        "get_artifact_summary",
    ]
    assert [tool.provider for tool in runtime_contract.tool_registry] == [
        "DatalogueBIAtomicToolkit",
        "DatalogueBIAtomicToolkit",
        "DatalogueBIAtomicToolkit",
        "DatalogueBIAtomicToolkit",
        "DatalogueBIAtomicToolkit",
        "DatalogueBIAtomicToolkit",
    ]
    assert runtime_contract.business_capabilities == ["query_dataset", "query_multiple_datasets"]
    assert runtime_contract.lead_agent_action.status == "ready"
    assert runtime_contract.lead_agent_action.selected_agent == "bi_agent"
    assert runtime_contract.lead_agent_action.capability == "query_dataset"
    assert runtime_contract.lead_agent_action.allowed_capabilities == [
        "query_dataset",
        "query_multiple_datasets",
    ]

    dumped = runtime_contract.model_dump_json()
    for forbidden in (
        "ask_bi",
        "AgentScopeShellAdapter",
        "plan_bi_query",
        "schema",
        "database",
        "sql_preview",
        "control_plane",
    ):
        assert forbidden not in dumped


def test_agentscope_runtime_driver_exposes_future_tools_only_as_disabled_or_admin_gated():
    runtime_contract = DatalogueAgentScopeRuntimeDriver().prepare_runtime(
        question="查询 GMV",
        context={"dataset_id": 12},
    )

    assert {
        tool.name: tool.status for tool in runtime_contract.disabled_tool_specs
    } == {
        "classify_query_failure": "disabled",
        "create_report_from_artifact": "admin_gated",
        "run_sandboxed_analysis_on_artifact": "admin_gated",
    }
    assert all(tool.gate in {"admin_only", "not_enabled"} for tool in runtime_contract.disabled_tool_specs)
    registered = {tool.name for tool in runtime_contract.tool_registry}
    assert registered.isdisjoint({tool.name for tool in runtime_contract.disabled_tool_specs})


def test_agentscope_runtime_driver_projects_context_without_execution_payloads():
    runtime_contract = DatalogueAgentScopeRuntimeDriver().prepare_runtime(
        question="查询销售额",
        context={
            "conversation_id": 7,
            "dataset_id": 12,
            "thread_id": "as_thread",
            "schema_context": {"tables": ["orders"]},
            "queryPlan": {"steps": ["internal"]},
            "rawRows": [{"amount": 1}],
            "fields": ["orders.amount"],
            "safe_note": "保留",
        },
    )

    assert runtime_contract.projected_context == {
        "question": "查询销售额",
        "conversation_id": 7,
        "dataset_id": 12,
        "thread_id": "as_thread",
        "safe_note": "保留",
    }
    dumped = runtime_contract.model_dump_json()
    for forbidden in ("schema_context", "queryPlan", "rawRows", "orders.amount"):
        assert forbidden not in dumped


def test_agentscope_runtime_driver_rejects_disabled_placeholder_without_tools():
    runtime_contract = DatalogueAgentScopeRuntimeDriver().prepare_runtime(
        question="根据查询结果生成一份经营报告",
        context={"dataset_id": 12},
    )

    assert runtime_contract.status == "disabled"
    assert runtime_contract.selected_agent == "report_agent"
    assert runtime_contract.tool_registry == []
    assert "get_dataset_status" in runtime_contract.disabled_tools
    assert "query_dataset" in runtime_contract.disabled_tools
    assert runtime_contract.lead_agent_action.status == "disabled"
    assert runtime_contract.lead_agent_action.action_type == "report_agent.disabled"
    assert runtime_contract.lead_agent_action.disabled_reason == "agent_disabled_placeholder"


def test_agentscope_runtime_driver_registers_only_enabled_optional_agent_whitelist():
    shell = AgenticLeadAgent(enabled_optional_agents=["report_agent"])
    runtime_contract = DatalogueAgentScopeRuntimeDriver(shell=shell).prepare_runtime(
        question="根据 artifact 生成报告",
        context={"artifact_ref": "artifact:query-result"},
        capability="create_report_from_artifact",
    )

    assert runtime_contract.status == "ready"
    assert runtime_contract.selected_agent == "report_agent"
    assert [tool.name for tool in runtime_contract.tool_registry] == ["create_report_from_artifact"]
    assert runtime_contract.business_capabilities == ["create_report_from_artifact"]
    assert runtime_contract.lead_agent_action.status == "ready"
    assert runtime_contract.lead_agent_action.capability == "create_report_from_artifact"
    assert "run_sandboxed_analysis_on_artifact" in runtime_contract.disabled_tools
    assert "classify_query_failure" in runtime_contract.disabled_tools
