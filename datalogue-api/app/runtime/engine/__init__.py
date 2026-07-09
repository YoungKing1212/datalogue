# 运行时引擎入口 — 框架无关的 Agent 运行时基础设施
# 实体从 app.agentscope_service/ 迁入

from app.runtime.engine.app_factory import create_embedded_runtime_app
from app.runtime.engine.client import AgentScopeServiceClient
from app.runtime.engine.registry import (
    LEADER_AGENT_NAME,
    AgentTeamLeaderSpec,
    AgentTeamWorkerTemplateSpec,
    build_datalogue_leader_agent_spec,
    build_datalogue_subagent_templates,
    build_datalogue_worker_template_specs,
)
from app.runtime.engine.runner import DEFAULT_LEADER_AGENT_ID, AgentTeamTaskRunner
from app.runtime.engine.projection import project_runtime_event
from app.runtime.engine.tools import build_datalogue_extra_agent_tools
from app.runtime.engine.otel_setup import setup_runtime_tracing

__all__ = [
    "create_embedded_runtime_app",
    "AgentScopeServiceClient",
    "LEADER_AGENT_NAME",
    "AgentTeamLeaderSpec",
    "AgentTeamWorkerTemplateSpec",
    "build_datalogue_leader_agent_spec",
    "build_datalogue_subagent_templates",
    "build_datalogue_worker_template_specs",
    "DEFAULT_LEADER_AGENT_ID",
    "AgentTeamTaskRunner",
    "project_runtime_event",
    "build_datalogue_extra_agent_tools",
    "setup_runtime_tracing",
]
