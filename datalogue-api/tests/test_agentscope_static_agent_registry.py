# ============================================================
# File Name   : test_agentscope_static_agent_registry.py
# Description:
#   AgentScope Service 固定 Agent 注册表测试。
#
# Responsibilities:
#   - 确认 Datalogue 固定注册 Lead/BI/Report/Python/Audit Agent。
#   - 防止主链 prompt 回退到动态 Agent 创建或自研 handoff/runner。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import pytest


EXPECTED_STATIC_AGENT_KEYS = (
    "agentic_lead_agent",
    "bi_agent",
    "report_agent",
    "python_agent",
    "audit_agent",
)

FORBIDDEN_PROMPT_TOKENS = (
    "AgentCreate",
    "TeamCreate",
    "TeamSay",
    "native_handoff",
    "AgenticDirectQueryRunner",
)


def test_static_agent_registry_contains_fixed_agents():
    from app.agentscope_service.registry import build_datalogue_static_agent_specs

    specs = build_datalogue_static_agent_specs()
    by_key = {item.key: item for item in specs}

    assert tuple(by_key) == EXPECTED_STATIC_AGENT_KEYS
    assert by_key["agentic_lead_agent"].service_name == "Datalogue Agentic Lead Agent"
    assert by_key["bi_agent"].service_name == "Datalogue BI Agent"
    assert "Dataset Query" in by_key["bi_agent"].description


def test_static_agent_prompts_lock_fixed_agent_boundaries():
    from app.agentscope_service.registry import build_datalogue_static_agent_specs

    specs = build_datalogue_static_agent_specs()
    combined = "\n".join(item.system_prompt for item in specs)

    assert "固定 Agent" in combined
    assert "运行时动态创建" in combined
    assert "自研直接查询执行器" in combined
    for forbidden in FORBIDDEN_PROMPT_TOKENS:
        assert forbidden not in combined


def test_static_agent_spec_payload_is_agent_service_ready():
    from app.agentscope_service.registry import build_datalogue_static_agent_specs

    spec = build_datalogue_static_agent_specs()[0]
    payload = spec.to_agent_payload()

    assert payload["name"] == spec.service_name
    assert payload["display_name"] == spec.service_name
    assert payload["description"] == spec.description
    assert payload["system_prompt"] == spec.system_prompt
    assert payload["metadata"]["datalogue_static_agent_key"] == spec.key
    assert payload["metadata"]["datalogue_role"] == spec.role


@pytest.mark.asyncio
async def test_extra_agent_tools_registers_non_read_only_dataset_function_tool(monkeypatch):
    import json
    from typing import Any

    from agentscope.message import TextBlock, ToolResultState
    from agentscope.tool import FunctionTool, ToolChunk

    from app.agentscope_service import tools as datalogue_tools
    from app.agentscope_service.dataset_query_executor import AgentTeamDatasetQueryResult

    async def fake_execute_dataset_query_for_agent_team(**kwargs: Any) -> AgentTeamDatasetQueryResult:
        assert kwargs["dataset_id"] == 42
        assert kwargs["confirmed_question"] == "统计合同总金额"
        assert "db" not in kwargs
        return AgentTeamDatasetQueryResult(
            answer_summary="合同总金额为 100。",
            artifact_ref="artifact:query:1",
            checkpoint_ref="checkpoint:query:1",
            row_count=1,
            column_count=2,
        )

    monkeypatch.setattr(
        datalogue_tools,
        "execute_dataset_query_for_agent_team",
        fake_execute_dataset_query_for_agent_team,
    )

    factory = datalogue_tools.build_datalogue_extra_agent_tools()
    registered_tools = await factory(user_id="user-1", agent_id="bi_agent", session_id="session-1")

    assert len(registered_tools) == 1
    tool = registered_tools[0]
    assert isinstance(tool, FunctionTool)
    assert tool.name == "datalogue_query_dataset"
    assert tool.is_read_only is False

    chunk = await tool(
        dataset_id=42,
        confirmed_question="统计合同总金额",
        task_goal="回答用户确认后的问数问题",
        user_confirmation_id="confirm-1",
        routing_rationale="已确认进入固定 BI Agent",
        trace_id="trace-1",
        parent_run_id="run-1",
    )
    assert isinstance(chunk, ToolChunk)
    assert chunk.state == ToolResultState.SUCCESS
    assert isinstance(chunk.content[0], TextBlock)
    assert json.loads(chunk.content[0].text) == {
        "answer_summary": "合同总金额为 100。",
        "artifact_ref": "artifact:query:1",
        "checkpoint_ref": "checkpoint:query:1",
        "row_count": 1,
        "column_count": 2,
    }


def test_prompt_and_tool_boundary_forbid_private_tokens():
    from pathlib import Path

    from app.agents.agentic_lead_agent.react_factory import AGENTIC_LEAD_AGENT_DIRECT_PROMPT
    from app.agents.bi_agent.react_factory import BI_AGENT_DIRECT_QUERY_PROMPT
    from app.agentscope_service import dataset_query_executor

    prompt_text = "\n".join([AGENTIC_LEAD_AGENT_DIRECT_PROMPT, BI_AGENT_DIRECT_QUERY_PROMPT])
    for forbidden in (
        "TeamCreate",
        "AgentCreate",
        "TeamSay",
        "native_handoff",
        "compile_dsl_to_sql",
        "execute_compiled_query",
        "repair_dsl",
        "get_dataset_status",
        "list_candidate_assets",
        "SQL",
        "schema",
        "raw rows",
    ):
        assert forbidden not in prompt_text
    assert "bi_agent" in AGENTIC_LEAD_AGENT_DIRECT_PROMPT
    assert "datalogue_query_dataset" in BI_AGENT_DIRECT_QUERY_PROMPT

    source = Path(dataset_query_executor.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "AgenticDirectQueryRunner",
        "AgentScopeNativeBIHandoff",
        "AgentScopeBIHandoffAdapter",
    ):
        assert forbidden not in source
    for expected in (
        "build_bi_atomic_toolkit",
        "AgentScopeDatasetRuntimeBridge",
        "build_bi_runtime_context",
    ):
        assert expected in source


def test_tools_module_does_not_return_accepted_placeholder():
    from pathlib import Path

    from app.agentscope_service import tools as datalogue_tools

    source = Path(datalogue_tools.__file__).read_text(encoding="utf-8")
    assert '"status": "accepted"' not in source
