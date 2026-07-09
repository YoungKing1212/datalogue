# ============================================================
# File Name   : projection.py
# Description:
#   AgentScope Service 事件投影 facade。
#
# Responsibilities:
#   - 暴露 project_runtime_event 作为新目录的稳定入口。
#   - 保持事件清洗与 envelope 投影逻辑继续由旧实现单点负责。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.runtime.engine.projection import project_runtime_event

__all__ = ["project_runtime_event"]
