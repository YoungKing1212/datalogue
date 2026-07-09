# ============================================================
# File Name   : sql_dialect.py
# Description:
#   SQL 方言规范化兼容门面。
#
# Responsibilities:
#   - re-export 查询执行领域中的方言基础能力，保持旧调用方导入不变。
#   - 兼容迁移中，不承载新业务逻辑。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""SQL 方言工具旧路径兼容层。

真实实现已下沉到 `app.domains.query_execution.dialect.names`；旧路径只保留
re-export，避免目录治理过程中一次性改动所有调用方。
"""

from app.domains.query_execution.dialect.names import (  # noqa: F401  兼容旧调用方导入
    FORBIDDEN_SQL_KEYWORDS,
    contains_forbidden_keyword,
    quote_ident,
    resolve_dialect,
    sanitize_filter_sql,
)

__all__ = [
    "FORBIDDEN_SQL_KEYWORDS",
    "contains_forbidden_keyword",
    "quote_ident",
    "resolve_dialect",
    "sanitize_filter_sql",
]
