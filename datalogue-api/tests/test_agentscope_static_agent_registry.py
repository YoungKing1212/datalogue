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

from types import SimpleNamespace

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
    from agentscope.permission import PermissionBehavior, PermissionMode
    from app.agentscope_service.registry import build_datalogue_worker_template_specs

    template = build_datalogue_worker_template_specs()[0].to_subagent_template()
    expected_allow_rules = {
        "TeamSay",
        "datalogue_describe_dataset_capability",
        "datalogue_execute_query_plan",
        "datalogue_profile_candidate_values",
        "datalogue_query_dataset",
        "datalogue_recall_query_assets",
        "datalogue_request_schema_slice",
        "datalogue_select_candidate_datasets",
        "datalogue_validate_query_support",
    }

    assert isinstance(template, SubAgentTemplate)
    assert template.type == "bi"
    assert "TeamSay" in template.system_prompt_template
    assert "Datalogue BI Worker" in template.description
    assert template.permission_context.mode == PermissionMode.DONT_ASK
    assert template.override_leader_mode is True
    assert template.extend_leader_permission_rules is False
    assert template.extend_leader_working_directories is False
    assert set(template.permission_context.allow_rules) == expected_allow_rules
    for tool_name in expected_allow_rules:
        [rule] = template.permission_context.allow_rules[tool_name]
        assert rule.tool_name == tool_name
        assert rule.behavior == PermissionBehavior.ALLOW
        assert rule.source == "datalogue-bi-worker-template"


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

    class FakeStorage:
        async def get_agent(self, user_id, agent_id):
            assert user_id == "user-1"
            assert agent_id == "agent-created-by-agentcreate"
            return SimpleNamespace(source="team", data=SimpleNamespace(name="bi-worker"))

    factory = datalogue_tools.build_datalogue_extra_agent_tools(storage=FakeStorage())
    registered_tools = await factory(user_id="user-1", agent_id="agent-created-by-agentcreate", session_id="session-1")

    assert [tool.name for tool in registered_tools] == [
        "datalogue_select_candidate_datasets",
        "datalogue_describe_dataset_capability",
        "datalogue_recall_query_assets",
        "datalogue_request_schema_slice",
        "datalogue_profile_candidate_values",
        "datalogue_validate_query_support",
        "datalogue_execute_query_plan",
        "datalogue_query_dataset",
    ]
    tool = next(item for item in registered_tools if item.name == "datalogue_query_dataset")
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
    payload = json.loads(chunk.content[0].text)
    assert payload == {
        "datalogue_event_type": "dataset_query_result",
        "summary": "合同总金额为 100。",
        "answer_summary": "合同总金额为 100。",
        "artifact_ref": "artifact:query:1",
        "result_ref": "artifact:query:1",
        "checkpoint_ref": "checkpoint:query:1",
        "row_count": 1,
        "column_count": 2,
        "artifact_card": {
            "artifact_type": "bi_answer",
            "title": "查询结果",
            "status": "completed",
            "summary_for_chat": "合同总金额为 100。",
            "preview_payload": {
                "row_count": 1,
                "column_count": 2,
            },
            "primary_ref": {
                "ref_id": "artifact:query:1",
                "ref_type": "result",
                "label": "查询结果",
            },
            "related_refs": [
                {
                    "ref_id": "checkpoint:query:1",
                    "ref_type": "checkpoint",
                    "label": "查询检查点",
                }
            ],
            "actions": [
                {
                    "action_type": "view",
                    "label": "查看详情",
                    "ref": "artifact:query:1",
                    "disabled": False,
                },
                {
                    "action_type": "export",
                    "label": "导出",
                    "ref": "artifact:query:1",
                    "disabled": True,
                },
            ],
        },
    }
    assert "SELECT" not in chunk.content[0].text
    assert "schema" not in chunk.content[0].text
    assert "raw_rows" not in chunk.content[0].text


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
    assert "datalogue_select_candidate_datasets" in BI_WORKER_PROMPT
    assert "datalogue_describe_dataset_capability" in BI_WORKER_PROMPT
    assert "datalogue_recall_query_assets" in BI_WORKER_PROMPT
    assert "datalogue_execute_query_plan" in BI_WORKER_PROMPT
    assert "L0/L1/L5" in BI_WORKER_PROMPT
    assert "L2/L3" in BI_WORKER_PROMPT
    assert "Query Plan JSON" in BI_WORKER_PROMPT
    assert "不得生成 SQL" in BI_WORKER_PROMPT
    assert "严禁再次调用 datalogue_select_candidate_datasets" in BI_WORKER_PROMPT
    assert "不得仅用自然语言声称已汇报" in BI_WORKER_PROMPT
    assert "dataset_query_result" in BI_WORKER_PROMPT
    assert "dataset_id" in BI_WORKER_PROMPT
    assert "Glob" in BI_WORKER_PROMPT

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
