# ============================================================
# File Name   : sql_guard.py
# Description:
#   SQL 执行前静态安全校验兼容门面。
#
# Responsibilities:
#   - re-export 查询执行领域中的 SQL 只读守卫能力，保持旧调用方导入不变。
#   - 兼容迁移中，不承载新业务逻辑。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

"""SQL Guard 旧路径兼容层。

真实实现已下沉到 `app.domains.query_execution.guard`；旧路径只保留
re-export，避免目录治理过程中一次性改动 API、测试和历史调用方。
"""

from app.domains.query_execution.guard import (  # noqa: F401  兼容旧调用方导入
    SQLGuardResult,
    guard_readonly_sql,
)

__all__ = [
    "SQLGuardResult",
    "guard_readonly_sql",
]
