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
    from app.runtime.engine.registry import build_datalogue_worker_template_specs

    specs = build_datalogue_worker_template_specs()
    by_type = {item.worker_type: item for item in specs}

    assert tuple(by_type) == EXPECTED_WORKER_TEMPLATE_TYPES
    assert by_type["bi"].display_name == "Datalogue BI Worker"
    assert "Dataset Query" in by_type["bi"].description
    assert "artifact_ref" in by_type["report"].system_prompt_template


def test_agent_team_prompts_allow_official_team_tools_only():
    from app.runtime.engine.registry import build_datalogue_worker_template_specs

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
    from app.runtime.engine.registry import build_datalogue_worker_template_specs

    template = build_datalogue_worker_template_specs()[0].to_subagent_template()
    expected_allow_rules = {
        "TeamSay",
        "datalogue_prepare_query_context",
        "datalogue_search_assets",
        "datalogue_execute_query_plan_bundle",
        "datalogue_repair_query_plan",
        "datalogue_request_schema_slice",
        "datalogue_select_candidate_datasets",
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


def test_bi_worker_prompt_template_is_agentscope_format_safe():
    from app.runtime.engine.registry import build_datalogue_worker_template_specs

    template = build_datalogue_worker_template_specs()[0].to_subagent_template()

    rendered = template.system_prompt_template.format(
        member_name="bi-worker",
        leader_name="Datalogue Agent Team Leader",
        team_description="查询杨凯2025年日志",
        member_description="Datalogue BI Worker",
    )

    assert '"target"' in rendered
    assert '"display_name"' in rendered
    assert "{member_name}" not in rendered
    assert "{leader_name}" not in rendered


@pytest.mark.asyncio
async def test_extra_agent_tools_registers_progressive_tools_without_legacy_dataset_query():
    from app.runtime.engine import tools as datalogue_tools

    class FakeStorage:
        async def get_agent(self, user_id, agent_id):
            assert user_id == "user-1"
            assert agent_id == "agent-created-by-agentcreate"
            return SimpleNamespace(source="team", data=SimpleNamespace(name="bi-worker"))

    factory = datalogue_tools.build_datalogue_extra_agent_tools(storage=FakeStorage())
    registered_tools = await factory(
        user_id="user-1", agent_id="agent-created-by-agentcreate", session_id="session-1"
    )

    assert [tool.name for tool in registered_tools] == [
        "datalogue_search_assets",
        "datalogue_select_candidate_datasets",
        "datalogue_prepare_query_context",
        "datalogue_request_schema_slice",
        "datalogue_describe_tables",
        "datalogue_execute_query_plan_bundle",
        "datalogue_repair_query_plan",
    ]


def test_prompt_and_tool_boundary_forbid_private_tokens():
    from pathlib import Path

    from app.runtime.engine.registry import BI_WORKER_PROMPT, LEADER_AGENT_SYSTEM_PROMPT
    from app.domains.bi.worker import dataset_query as dataset_query_executor

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
    assert "datalogue_select_candidate_datasets" in BI_WORKER_PROMPT
    assert "datalogue_prepare_query_context" in BI_WORKER_PROMPT
    assert "datalogue_execute_query_plan_bundle" in BI_WORKER_PROMPT
    assert "datalogue_repair_query_plan" in BI_WORKER_PROMPT
    assert "datalogue_request_schema_slice" in BI_WORKER_PROMPT
    assert "Query Plan JSON" in BI_WORKER_PROMPT
    assert '"selects"' in BI_WORKER_PROMPT
    assert '"metrics"' in BI_WORKER_PROMPT
    assert '"target"' in BI_WORKER_PROMPT
    assert '"display_name"' in BI_WORKER_PROMPT
    assert "不得生成 SQL" in BI_WORKER_PROMPT
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
    for expected in ("BIWorkerQueryRuntime",):
        assert expected in source


def test_tools_module_does_not_return_accepted_placeholder():
    from pathlib import Path

    from app.runtime.engine import tools as datalogue_tools

    source = Path(datalogue_tools.__file__).read_text(encoding="utf-8")
    assert '"status": "accepted"' not in source
