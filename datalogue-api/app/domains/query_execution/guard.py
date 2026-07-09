# ============================================================
# File Name   : guard.py
# Description:
#   SQL 只读守卫门面，re-export `app.utils.sql_guard` 中的守卫能力。
#
# Responsibilities:
#   - 暴露 guard_readonly_sql 与 SQLGuardResult，用于禁止写操作与危险语句
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""SQL 只读守卫门面。

只做 re-export，实际守卫解析与模式匹配仍在 `app.utils.sql_guard`；
本文件不承载新业务逻辑。
"""

from app.utils.sql_guard import (  # noqa: F401  兼容迁移中，保留公开导出
    SQLGuardResult,
    guard_readonly_sql,
)

__all__ = [
    "SQLGuardResult",
    "guard_readonly_sql",
]
