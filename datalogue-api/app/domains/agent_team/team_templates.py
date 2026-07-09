# ============================================================
# File Name   : team_templates.py
# Description:
#   AgentScope Agent Team worker 模板构造入口。
#
# Responsibilities:
#   - 向 app_factory 暴露 build_datalogue_subagent_templates。
#   - 保持模板事实源在 registry.py，避免多个文件重复定义 worker 边界。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from agentscope.app import SubAgentTemplate

from app.runtime.engine.registry import build_datalogue_subagent_templates

__all__ = ["SubAgentTemplate", "build_datalogue_subagent_templates"]
