# ============================================================
# File Name   : __init__.py
# Description:
#   AgentScope 2.0 Middleware 集中导出入口。
#
# Responsibilities:
#   - 统一管理 Datalogue 接入 AgentScope 2.0 时使用的 Middleware。
#   - 避免 Middleware 分散在业务 Runtime 或工具实现文件中。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from app.services.agentscope_middlewares.dataset_tool_logging import DatasetRuntimeToolLoggingMiddleware

__all__ = ["DatasetRuntimeToolLoggingMiddleware"]
