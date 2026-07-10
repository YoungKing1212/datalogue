# ============================================================
# File Name   : registry.py
# Description:
#   Datalogue Agent Team 模板注册 facade。
#
# Responsibilities:
#   - 暴露 leader/worker template 相关入口，作为新目录的稳定导入边界。
#   - 保持 SubAgentTemplate 和 permission_context 构建仍由旧实现单点负责。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.runtime.engine.registry import (
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
