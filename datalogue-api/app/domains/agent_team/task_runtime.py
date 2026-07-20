# ============================================================
# File Name   : task_runtime.py
# Description:
#   Datalogue Agent Team task runtime facade。
#
# Responsibilities:
#   - 暴露 AgentTeamTaskRuntime 作为对外 task 真相源和 AgentScope stream 投影的运行入口。
#   - 保持实际实现仍在 app.runtime.agent_team_runtime，避免本阶段移动高风险主链文件。
#   - 明确本 facade 不拥有 AgentScope Service runner / registry，那些能力属于 app.runtime.engine。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.runtime.agent_team_runtime import AgentTeamTaskRunner, AgentTeamTaskRuntime

__all__ = ["AgentTeamTaskRunner", "AgentTeamTaskRuntime"]
