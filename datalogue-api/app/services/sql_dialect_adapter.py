# ============================================================
# File Name   : sql_dialect_adapter.py
# Description:
#   SQL 方言适配旧路径兼容门面。
#
# Responsibilities:
#   - re-export 查询执行领域中的 SQL 方言适配能力，保持旧调用方导入不变。
#   - 兼容迁移中，不承载新业务逻辑。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

"""SQL 方言适配旧路径兼容层。

真实实现已下沉到 `app.domains.query_execution.dialect.adapter`；旧路径只保留
re-export，避免目录治理过程中一次性改动 BI Toolkit、测试和历史调用方。
"""

from app.domains.query_execution.dialect.adapter import (  # noqa: F401  兼容旧调用方导入
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
