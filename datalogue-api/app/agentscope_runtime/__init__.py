# ============================================================
# File Name   : __init__.py
# Description:
#   AgentScope Service 嵌入运行时的目标 facade 包。
#
# Responsibilities:
#   - 为目录治理提供稳定的新导入边界。
#   - 只 re-export AgentScope Service 嵌入、runner、registry、projection、OTel、worker logging、client 与 credential 入口。
#   - 保持旧 app.runtime.engine 实现不搬移，避免当前阶段产生大面积 import break。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.runtime.engine.app_factory import create_embedded_runtime_app
from app.runtime.engine.client import AgentScopeServiceClient
from app.runtime.engine.credentials import DatalogueLLMCredential
from app.runtime.engine.otel_setup import setup_runtime_tracing
from app.runtime.engine.projection import project_runtime_event
from app.runtime.engine.registry import (
    LEADER_AGENT_NAME,
    AgentTeamLeaderSpec,
    AgentTeamWorkerTemplateSpec,
    build_datalogue_leader_agent_spec,
    build_datalogue_subagent_templates,
    build_datalogue_worker_template_specs,
)
from app.runtime.engine.runner import DEFAULT_LEADER_AGENT_ID, AgentTeamTaskRunner
from app.domains.agent_team.worker_logging import build_datalogue_extra_agent_middlewares

__all__ = [
    "create_embedded_runtime_app",
    "AgentScopeServiceClient",
    "DatalogueLLMCredential",
    "setup_runtime_tracing",
    "project_runtime_event",
    "LEADER_AGENT_NAME",
    "AgentTeamLeaderSpec",
    "AgentTeamWorkerTemplateSpec",
    "build_datalogue_leader_agent_spec",
    "build_datalogue_subagent_templates",
    "build_datalogue_worker_template_specs",
    "DEFAULT_LEADER_AGENT_ID",
    "AgentTeamTaskRunner",
    "build_datalogue_extra_agent_middlewares",
]
