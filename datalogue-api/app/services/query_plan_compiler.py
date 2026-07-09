# ============================================================
# File Name   : query_plan_compiler.py
# Description:
#   查询计划编译旧路径兼容门面。
#
# Responsibilities:
#   - re-export 查询执行领域中的 compile_query_plan_to_sql，保持旧调用方导入不变。
#   - 兼容迁移中，不承载新业务逻辑。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

"""查询计划编译旧路径兼容层。

真实实现已下沉到 `app.domains.query_execution.compiler`；旧路径只保留
re-export，避免目录治理过程中一次性改动 BI Toolkit、测试和历史调用方。
"""

from app.domains.query_execution.compiler import (  # noqa: F401  兼容旧调用方导入
    compile_query_plan_to_sql,
)

__all__ = ["compile_query_plan_to_sql"]
