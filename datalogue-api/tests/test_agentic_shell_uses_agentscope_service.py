# ============================================================
# File Name   : test_agentic_shell_uses_agentscope_service.py
# Description:
#   Agentic Shell 主链迁移到 AgentScope Service 的结构性守护测试。
#
# Responsibilities:
#   - 防止旧 BIAgentTaskRunner / AgenticDirectQueryRunner 重新进入主入口。
#   - 验证 API 默认入口引用 AgentScope Service runner，而不是自写执行循环。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_agentic_shell_main_chain_no_longer_imports_legacy_direct_runner():
    checked_files = [
        API_ROOT / "api" / "agentic_shell.py",
        API_ROOT / "runtime" / "task_runtime.py",
        API_ROOT / "runtime" / "__init__.py",
    ]

    source = "\n".join(path.read_text(encoding="utf-8") for path in checked_files)

    assert "BIAgentTaskRunner" not in source
    assert "AgenticDirectQueryRunner" not in source
    assert "direct_query_runner" not in source


def test_agentic_shell_api_defaults_to_agentscope_service_runner():
    source = (API_ROOT / "api" / "agentic_shell.py").read_text(encoding="utf-8")

    assert "AgentScopeServiceTaskRunner" in source
    assert "AGENTSCOPE_SERVICE_BASE_URL" in source
    assert "build_agentic_shell_task_runner" in source
