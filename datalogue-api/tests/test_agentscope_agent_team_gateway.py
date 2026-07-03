# ============================================================
# File Name   : test_agentscope_agent_team_gateway.py
# Description:
#   AgentScope Agent Team 主链网关的结构性守护测试。
#
# Responsibilities:
#   - 验证公开 API 主入口使用 Agent Team 命名。
#   - 防止后端主链重新依赖 fixed agent bootstrap、handoff 或旧 direct-query。
#   - 明确允许 TeamCreate/AgentCreate/TeamSay 仅作为 AgentScope 官方 Team 工具出现。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_agent_team_public_api_replaces_agentic_shell_entrypoint():
    from app.api import router

    public_paths = {route.path for route in router.routes}

    assert "/agent-team/tasks/stream" in public_paths
    assert not any(path.startswith("/bi-agent") for path in public_paths)
    assert "/agentic-shell/tasks/stream" not in public_paths
    assert "/agentic-lead-agent/direct-query" not in public_paths
    assert "/agentic-lead-agent/direct-query/stream" not in public_paths


def test_agent_team_gateway_defaults_to_agentscope_service_runner():
    source = (API_ROOT / "api" / "agent_team.py").read_text(encoding="utf-8")

    assert "AgentScopeServiceTaskRunner" in source
    assert "AGENTSCOPE_SERVICE_BASE_URL" in source
    assert "build_agent_team_task_runner" in source
    assert "build_agentic_shell_task_runner" not in source


def test_agent_team_main_chain_does_not_bootstrap_fixed_agents():
    checked_files = [
        API_ROOT / "api" / "agent_team.py",
        API_ROOT / "runtime" / "agent_team_runtime.py",
        API_ROOT / "agentscope_service" / "runner.py",
        API_ROOT / "agentscope_service" / "registry.py",
    ]

    source = "\n".join(path.read_text(encoding="utf-8") for path in checked_files)

    assert "ensure_static_agents" not in source
    assert "STATIC_AGENT_KEYS" not in source
    assert "datalogue_static_agent_key" not in source
    assert "BIAgentTaskRunner" not in source
    assert "AgenticDirectQueryRunner" not in source
    assert "direct_query_runner" not in source


def test_official_team_tools_are_allowed_without_datalogue_reimplementation():
    from app.agentscope_service.registry import build_datalogue_worker_template_specs

    combined = "\n".join(spec.system_prompt_template for spec in build_datalogue_worker_template_specs())

    for official_tool in ("TeamCreate", "AgentCreate", "TeamSay"):
        assert official_tool in combined
    assert "AgentScope 官方内置 Team 工具" in combined
    assert "class TeamCreate" not in combined
    assert "def AgentCreate" not in combined
    assert "自写 handoff" not in combined
