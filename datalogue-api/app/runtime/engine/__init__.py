# ============================================================
# File Name   : __init__.py
# Description:
#   AgentScope Service runtime engine 的 canonical 延迟加载入口。
#
# Responsibilities:
#   - 暴露 app factory、client、registry、runner、projection、tools 与 tracing 公共能力。
#   - 允许调用方直接导入具体子模块，而不触发完整引擎依赖图。
#
# Author      : yangkai
# Created On  : 2026-07-17
# ============================================================

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "create_embedded_runtime_app": "app.runtime.engine.app_factory",
    "DEFAULT_AGENTSCOPE_USER_ID": "app.runtime.engine.client",
    "AgentScopeServiceClient": "app.runtime.engine.client",
    "DatalogueLLMCredential": "app.runtime.engine.credentials",
    "setup_runtime_tracing": "app.runtime.engine.otel_setup",
    "project_runtime_event": "app.runtime.engine.projection",
    "LEADER_AGENT_NAME": "app.runtime.engine.registry",
    "AgentTeamLeaderSpec": "app.runtime.engine.registry",
    "AgentTeamWorkerTemplateSpec": "app.runtime.engine.registry",
    "build_datalogue_leader_agent_spec": "app.runtime.engine.registry",
    "build_datalogue_subagent_templates": "app.runtime.engine.registry",
    "build_datalogue_worker_template_specs": "app.runtime.engine.registry",
    "DEFAULT_LEADER_AGENT_ID": "app.runtime.engine.runner",
    "AgentTeamTaskRunner": "app.runtime.engine.runner",
    "build_datalogue_extra_agent_tools": "app.runtime.engine.tools",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    """按符号加载引擎能力，避免 client 等轻量模块被 runner 反向拖入。"""

    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
