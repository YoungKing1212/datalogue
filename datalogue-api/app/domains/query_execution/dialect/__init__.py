# ============================================================
# File Name   : __init__.py
# Description:
#   SQL 方言适配门面子包，聚合方言归一化与执行前重写能力。
#
# Responsibilities:
#   - 通过 adapter 子模块 re-export 方言归一化与 SQL 执行适配
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""SQL 方言适配门面子包。

暴露 `app.services.sql_dialect_adapter` 中的既有函数，用于在执行前
按目标数据源方言重写 SQL；不承载新业务逻辑。
"""

from .adapter import (  # noqa: F401  兼容迁移中，保留公开导出
    adapt_sql_for_execution,
    normalize_supported_dialect,
    quote_identifier,
)

__all__ = [
    "adapt_sql_for_execution",
    "normalize_supported_dialect",
    "quote_identifier",
]
