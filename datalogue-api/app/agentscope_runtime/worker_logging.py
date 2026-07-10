# ============================================================
# File Name   : worker_logging.py
# Description:
#   AgentScope worker middleware / logging facade。
#
# Responsibilities:
#   - 暴露 build_datalogue_extra_agent_middlewares 作为新目录的稳定入口。
#   - 当前阶段只转发旧实现，避免同时维护两套 worker 观测与脱敏逻辑。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.domains.agent_team.worker_logging import build_datalogue_extra_agent_middlewares

__all__ = ["build_datalogue_extra_agent_middlewares"]
