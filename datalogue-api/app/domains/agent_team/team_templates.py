# ============================================================
# File Name   : team_templates.py
# Description:
#   AgentScope Agent Team worker 模板兼容入口。
#
# Responsibilities:
#   - 为旧 app.domains.agent_team.team_templates 调用方转发模板构造函数。
#   - 避免 app_factory 与 registry 之间形成 bootstrap 循环。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from agentscope.app import SubAgentTemplate

from app.runtime.engine.registry import build_datalogue_subagent_templates

__all__ = ["SubAgentTemplate", "build_datalogue_subagent_templates"]
