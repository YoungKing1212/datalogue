# ============================================================
# File Name   : registry.py
# Description:
#   Agent Team 装配门面，re-export Leader/Worker spec 与模板构建函数。
#
# Responsibilities:
#   - 暴露 build_datalogue_leader_agent_spec / build_datalogue_worker_template_specs
#     / build_datalogue_subagent_templates 等 Agent Team 装配入口
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""AgentScope runtime registry 兼容门面。

新导入边界是 `app.agentscope_runtime.registry`。本文件保留为旧
`app.domains.agent_team.registry` 调用方的兼容层，不承载 Datalogue task 真相源。
"""

from app.runtime.engine.registry import (  # noqa: F401  兼容迁移中，保留公开导出
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
