# ============================================================
# File Name   : test_agentscope_static_agent_registry.py
# Description:
#   AgentScope Agent Team 固定 worker 模板注册表测试。
#
# Responsibilities:
#   - 确认 Datalogue 暴露固定 BI/Report/Python/Audit worker 类型。
#   - 防止 worker prompt 回退到 Datalogue 自研 handoff/runner。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import pytest


EXPECTED_WORKER_TEMPLATE_TYPES = (
    "bi",
    "report",
    "python",
    "audit",
)

FORBIDDEN_DATALOGUE_ORCHESTRATION_TOKENS = (
    "native_handoff",
    "AgenticDirectQueryRunner",
    "Datalogue 自研 runner",
    "Datalogue 自写 handoff",
)


def test_agent_team_registry_contains_fixed_worker_templates():
    from app.agentscope_service.registry import build_datalogue_worker_template_specs

    specs = build_datalogue_worker_template_specs()
    by_type = {item.worker_type: item for item in specs}

    assert tuple(by_type) == EXPECTED_WORKER_TEMPLATE_TYPES
    assert by_type["bi"].display_name == "Datalogue BI Worker"
    assert "Dataset Query" in by_type["bi"].description
    assert "artifact_ref" in by_type["report"].system_prompt_template


def test_agent_team_prompts_allow_official_team_tools_only():
    from app.agentscope_service.registry import build_datalogue_worker_template_specs

    specs = build_datalogue_worker_template_specs()
    combined = "\n".join(item.system_prompt_template for item in specs)

    assert "AgentScope 官方 Agent Team" in combined
    assert "TeamCreate" in combined
    assert "AgentCreate" in combined
    assert "TeamSay" in combined
    assert "自研直接查询执行器" in combined
    for forbidden in FORBIDDEN_DATALOGUE_ORCHESTRATION_TOKENS:
        assert forbidden not in combined


def test_worker_template_specs_convert_to_agentscope_subagent_templates():
    from agentscope.app import SubAgentTemplate
    from app.agentscope_service.registry import build_datalogue_worker_template_specs

    template = build_datalogue_worker_template_specs()[0].to_subagent_template()

    assert isinstance(template, SubAgentTemplate)
    assert template.type == "bi"
    assert "TeamSay" in template.system_prompt_template
    assert "Datalogue BI Worker" in template.description


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
    registered_tools = await factory(user_id="user-1", agent_id="agent-created-by-agentcreate", session_id="session-1")

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
        routing_rationale="已确认进入 BI worker",
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

    from app.agentscope_service.registry import BI_WORKER_PROMPT, LEADER_AGENT_SYSTEM_PROMPT
    from app.agentscope_service import dataset_query_executor

    prompt_text = f"{LEADER_AGENT_SYSTEM_PROMPT}\n{BI_WORKER_PROMPT}"
    for forbidden in (
        "native_handoff",
        "compile_dsl_to_sql",
        "execute_compiled_query",
        "repair_dsl",
        "get_dataset_status",
        "list_candidate_assets",
    ):
        assert forbidden not in prompt_text
    for safety_boundary in ("SQL", "schema", "raw rows"):
        assert safety_boundary in prompt_text
    assert "TeamCreate" in LEADER_AGENT_SYSTEM_PROMPT
    assert "AgentCreate" in LEADER_AGENT_SYSTEM_PROMPT
    assert "TeamSay" in LEADER_AGENT_SYSTEM_PROMPT
    assert "安全 Dataset Query 工具" in BI_WORKER_PROMPT

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
