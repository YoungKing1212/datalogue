# ============================================================
# File Name   : __init__.py
# Description:
#   Datalogue 持久化边界出口。
#
# Responsibilities:
#   - 暴露 AgenticLeadAgent 写回 Workbench/mirror 所需的持久化适配器。
#   - 将 durable writeback 能力从通用 services 目录中收口到 persistence 边界。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from app.persistence.shell_writer import AgentScopeMirrorShellWriter

__all__ = ["AgentScopeMirrorShellWriter"]
