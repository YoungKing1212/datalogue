# ============================================================
# File Name   : __init__.py
# Description:
#   Datalogue Agent 统一出口。
#
# Responsibilities:
#   - 暴露当前 AgenticLeadAgent 入口。
#   - 为后续 BI Agent、ReportAgent、PythonAgent 和 AuditAgent 预留清晰包边界。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from app.agents.agentic_lead_agent import AgenticLeadAgent

__all__ = ["AgenticLeadAgent"]
