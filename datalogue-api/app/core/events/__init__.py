# ============================================================
# File Name   : __init__.py
# Description:
#   Datalogue 对外事件协议出口。
#
# Responsibilities:
#   - 暴露 AgentScope event 到 Datalogue envelope 的投影能力。
#   - 暴露 Workbench mirror 事件投影能力。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from app.core.events.projection import (
    build_task_envelope,
    extract_refs_from_envelope,
    extract_refs_from_payload,
    project_agentscope_event,
    project_event_envelope_to_agentscope,
    sanitize_event_payload_for_workbench,
)

__all__ = [
    "build_task_envelope",
    "extract_refs_from_envelope",
    "extract_refs_from_payload",
    "project_agentscope_event",
    "project_event_envelope_to_agentscope",
    "sanitize_event_payload_for_workbench",
]
