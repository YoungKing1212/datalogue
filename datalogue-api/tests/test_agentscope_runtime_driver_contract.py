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

from app.services.agentic_shell import DatalogueAgenticShell
from app.services.agentscope_runtime_driver import DatalogueAgentScopeRuntimeDriver


def test_agentscope_runtime_driver_accepts_only_agentic_shell_contract():
    driver = DatalogueAgentScopeRuntimeDriver()
    shell = DatalogueAgenticShell()
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
        "BIAtomicToolProvider",
        "BIAtomicToolProvider",
        "BIAtomicToolProvider",
        "BIAtomicToolProvider",
        "BIAtomicToolProvider",
        "BIAtomicToolProvider",
    ]
    assert runtime_contract.business_capabilities == ["query_dataset", "query_multiple_datasets"]

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
