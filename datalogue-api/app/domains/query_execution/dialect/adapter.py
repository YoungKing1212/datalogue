# ============================================================
# File Name   : adapter.py
# Description:
#   SQL 方言适配器门面，re-export `app.services.sql_dialect_adapter` 能力。
#
# Responsibilities:
#   - 暴露 adapt_sql_for_execution / normalize_supported_dialect / quote_identifier
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""SQL 方言适配器门面。

只做 re-export，实际重写/归一化逻辑仍在 `app.services.sql_dialect_adapter`；
本文件不承载新业务逻辑。
"""

from app.services.sql_dialect_adapter import (  # noqa: F401  兼容迁移中，保留公开导出
    EXECUTION_SOURCE_TOOL_COMPILER,
    adapt_sql_for_execution,
    normalize_supported_dialect,
    quote_identifier,
)

__all__ = [
    "EXECUTION_SOURCE_TOOL_COMPILER",
    "adapt_sql_for_execution",
    "normalize_supported_dialect",
    "quote_identifier",
]
