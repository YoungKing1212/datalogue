# ============================================================
# File Name   : __init__.py
# Description:
#   数据源领域门面包，聚合 datasource 相关的连接、能力、上下文和元数据能力。
#
# Responsibilities:
#   - 通过 re-export 提供数据源引擎构建、连接测试、库表同步等公开入口
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""数据源领域包。

Phase C 起由本目录承载 datasource 领域入口；`app.services.datasource`
仅作为历史导入路径兼容导出，避免迁移期破坏旧调用方。
"""

from .service import (  # noqa: F401  兼容迁移中，保留公开导出
    create_engine_for_datasource,
    sync_source_tables,
    test_connection,
)

__all__ = [
    "create_engine_for_datasource",
    "sync_source_tables",
    "test_connection",
]
