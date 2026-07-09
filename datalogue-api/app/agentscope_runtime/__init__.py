# ============================================================
# File Name   : __init__.py
# Description:
#   AgentScope Runtime 门面包，聚合内嵌 AgentScope 服务的入口。
#
# Responsibilities:
#   - 通过 app_factory / registry / runner / projection 子模块 re-export
#     现有 `app.agentscope_service` 能力
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""AgentScope Runtime 门面包。

本包只对既有 `app.agentscope_service.*` 模块做 re-export，为未来把
AgentScope Runtime 相关代码统一沉淀到独立包做兼容层；当前不承载新
业务逻辑。
"""

from .app_factory import create_embedded_agentscope_app  # noqa: F401  兼容迁移中，保留公开导出

__all__ = ["create_embedded_agentscope_app"]
