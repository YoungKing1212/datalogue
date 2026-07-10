# ============================================================
# File Name   : inspector.py
# Description:
#   数据源库表元数据探查门面，re-export schema 相关函数。
#
# Responsibilities:
#   - 暴露 get_schemas / get_schema / sync_source_tables 入口
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""数据源库表探查门面。

只做 re-export，实际探查/同步逻辑仍在 `app.services.datasource`；
本文件不承载新业务逻辑。
"""

from app.domains.data_source.service import (  # noqa: F401  兼容迁移中，保留公开导出
    get_schema,
    get_schemas,
    sync_source_tables,
)

__all__ = [
    "get_schema",
    "get_schemas",
    "sync_source_tables",
]
