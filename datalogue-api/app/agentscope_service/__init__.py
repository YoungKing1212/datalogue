# ============================================================
# File Name   : __init__.py
# Description:
#   Datalogue 嵌入式 AgentScope Service 包入口。
#
# Responsibilities:
#   - 暴露创建 AgentScope Service FastAPI 子应用的稳定 factory。
#   - 隔离官方 AgentScope Service 基础层与主业务路由的集成边界。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from app.agentscope_service.app_factory import create_embedded_agentscope_app

__all__ = ["create_embedded_agentscope_app"]
