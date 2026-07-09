# ============================================================
# File Name   : app_factory.py
# Description:
#   AgentScope 内嵌应用工厂门面，re-export create_embedded_agentscope_app。
#
# Responsibilities:
#   - 暴露 create_embedded_agentscope_app，用于装配内嵌的 AgentScope FastAPI 应用
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""AgentScope 内嵌应用工厂门面。

实际的应用装配、依赖注入、Redis 初始化仍在
`app.agentscope_service.app_factory`；本文件只做 re-export。
"""

from app.agentscope_service.app_factory import (  # noqa: F401  兼容迁移中，保留公开导出
    create_embedded_agentscope_app,
)

__all__ = ["create_embedded_agentscope_app"]
