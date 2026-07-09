# ============================================================
# File Name   : event_projection.py
# Description:
#   Agent Team 事件 envelope 投影 facade。
#
# Responsibilities:
#   - 暴露 DatalogueEventEnvelope 与 build_task_envelope，统一 Agent Team SSE 输出外层协议。
#   - 暴露 project_agentscope_event，把 AgentScope Service 事件投影为 Datalogue 业务事件。
#   - 保持用户可见 payload 的 SQL/schema/raw rows 泄露防护由 core event/schema 实现单点负责。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.core.events.projection import build_task_envelope, project_agentscope_event
from app.core.schemas.bi_workbench import (
    DatalogueEventEnvelope,
    DatalogueEventType,
    build_datalogue_event_envelope,
)

__all__ = [
    "DatalogueEventEnvelope",
    "DatalogueEventType",
    "build_datalogue_event_envelope",
    "build_task_envelope",
    "project_agentscope_event",
]
