# ============================================================
# File Name   : __init__.py
# Description:
#   Datalogue 后端按业务域组织的门面包根目录。
#
# Responsibilities:
#   - 聚合 data_source / query_execution / agent_team / bi 等业务域 facade
#   - 保留兼容迁移期的 re-export 通道，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""Datalogue 领域门面包（facade-first）。

本包处于兼容迁移中，仅通过 re-export 暴露既有 `app.services` / `app.utils`
里的公开能力，不承载新业务逻辑；新业务代码请继续落地在原实现模块中，
待完成迁移后再逐步将实现迁入本包。
"""

__all__: list[str] = []
