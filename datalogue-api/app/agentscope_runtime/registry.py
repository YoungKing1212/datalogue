# ============================================================
# File Name   : registry.py
# Description:
#   AgentScope Runtime 装配注册表门面，re-export 团队/模板构建函数。
#
# Responsibilities:
#   - 暴露 Datalogue Leader/Worker spec 与 SubAgent 模板构建入口
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""AgentScope Runtime 装配注册表门面。

只做 re-export，实际注册与权限装配仍在
`app.agentscope_service.registry` 与 `app.agentscope_service.team_templates`。
"""

from app.agentscope_service.registry import (  # noqa: F401  兼容迁移中，保留公开导出
    LEADER_AGENT_NAME,
    AgentTeamLeaderSpec,
    AgentTeamWorkerTemplateSpec,
    build_datalogue_leader_agent_spec,
    build_datalogue_subagent_templates,
    build_datalogue_worker_template_specs,
)

__all__ = [
    "LEADER_AGENT_NAME",
    "AgentTeamLeaderSpec",
    "AgentTeamWorkerTemplateSpec",
    "build_datalogue_leader_agent_spec",
    "build_datalogue_subagent_templates",
    "build_datalogue_worker_template_specs",
]
