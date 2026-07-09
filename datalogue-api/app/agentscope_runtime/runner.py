# ============================================================
# File Name   : runner.py
# Description:
#   Agent Team 到 AgentScope Service runner 的目标 facade。
#
# Responsibilities:
#   - 暴露 AgentTeamTaskRunner 和默认 leader agent 配置。
#   - 保持 Service chat/stream 驱动逻辑继续由旧实现单点负责。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.runtime.engine.runner import DEFAULT_LEADER_AGENT_ID, AgentTeamTaskRunner

__all__ = ["DEFAULT_LEADER_AGENT_ID", "AgentTeamTaskRunner"]
