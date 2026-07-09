# ============================================================
# File Name   : compiler.py
# Description:
#   查询计划到 SQL 的编译门面，re-export `app.services.query_plan_compiler`。
#
# Responsibilities:
#   - 暴露 compile_query_plan_to_sql，供上层调用查询编排结果生成执行 SQL
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""查询计划编译门面。

只做 re-export，实际编译逻辑仍在 `app.services.query_plan_compiler`；
本文件不承载新业务逻辑。
"""

from app.services.query_plan_compiler import (  # noqa: F401  兼容迁移中，保留公开导出
    compile_query_plan_to_sql,
)

__all__ = ["compile_query_plan_to_sql"]
