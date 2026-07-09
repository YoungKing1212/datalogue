# ============================================================
# File Name   : contracts.py
# Description:
#   Datalogue Agent Team 对外 task 真相源和 DTO 契约 facade。
#
# Responsibilities:
#   - 暴露 AgentTeamTask 持久化模型作为 Datalogue task 真相源。
#   - 暴露 AgentTeamTaskRequest / AgentTeamTaskStreamEvent 作为 Chat、Workbench 和 API 入口统一 DTO。
#   - 保持 SQL/schema/raw rows 等执行面安全校验仍由原 schema 单点负责。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.core.models.agent_team_task import AgentTeamTask
from app.core.schemas.agentscope_agent_team_task import (
    AgentTeamTaskRequest,
    AgentTeamTaskSource,
    AgentTeamTaskStreamEvent,
    AgentTeamTaskType,
)

__all__ = [
    "AgentTeamTask",
    "AgentTeamTaskRequest",
    "AgentTeamTaskSource",
    "AgentTeamTaskStreamEvent",
    "AgentTeamTaskType",
]
