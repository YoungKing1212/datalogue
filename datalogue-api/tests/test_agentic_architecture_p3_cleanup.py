# ============================================================
# File Name   : test_agentic_architecture_p3_cleanup.py
# Description:
#   AgentScope 架构瘦身 P3 旧兼容壳删除测试。
#
# Responsibilities:
#   - 验证 Dataset AgentScope bridge 已迁入 BI Skill 边界。
#   - 验证已迁移的旧 services 兼容壳不再作为业务入口存在。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import importlib

import pytest


def test_p3_dataset_bridge_owned_by_bi_skill_runtime_bridge():
    from app.bi.skill import AgentScopeDatasetRuntimeBridge, build_dataset_agentscope_tools
    from app.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge as DirectBridge

    assert AgentScopeDatasetRuntimeBridge is DirectBridge
    assert build_dataset_agentscope_tools.__module__ == "app.bi.skill.runtime_bridge"
    assert DirectBridge.__module__ == "app.bi.skill.runtime_bridge"


@pytest.mark.parametrize(
    "module_name",
    [
        "app.services.agentic_shell",
        "app.services.agentic_shell_task_runtime",
        "app.services.agentic_shell_writers",
        "app.services.agentscope_thread_resolver",
        "app.services.agentscope_runtime_driver",
        "app.services.agentic_dataset_runtime",
        "app.services.bi_tools",
        "app.services.bi_tools.atomic",
        "app.services.agentscope_middlewares",
        "app.services.agentscope_middlewares.dataset_tool_logging",
        "app.services.agentscope_middlewares.safe_log_summary",
        "app.services.agentic_shell_event_projection",
        "app.services.agentscope_event_projection",
        "app.services.agentic_shell_logging",
        "app.services.observability.agentscope_otel",
        "app.services.agentscope_dataset_runtime",
    ],
)
def test_p3_removed_services_compatibility_modules_are_not_importable(module_name):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)
