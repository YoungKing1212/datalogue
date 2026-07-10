# ============================================================
# File Name   : __init__.py
# Description:
#   查询执行领域包入口，提供 SQL 预览、SQL 守卫、方言适配和查询编译的懒加载门面。
#
# Responsibilities:
#   - 暴露 query_execution 领域的稳定公开入口。
#   - 避免包初始化时急切导入 compiler/preview，防止迁移期循环导入。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""查询执行领域包。

目录治理期间，子模块之间仍存在旧 service 与新 domain 的双向兼容关系；
因此包入口只声明公开符号，并通过 ``__getattr__`` 懒加载，避免 import
``app.domains.query_execution.dialect.names`` 时提前加载 query_plan_compiler。
"""

from typing import Any

__all__ = [
    "compile_query_plan_to_sql",
    "guard_readonly_sql",
    "preview_dataset_sql",
]


def __getattr__(name: str) -> Any:
    """按需加载公开能力，避免包初始化阶段触发旧服务循环导入。"""
    if name == "compile_query_plan_to_sql":
        from .compiler import compile_query_plan_to_sql

        return compile_query_plan_to_sql
    if name == "guard_readonly_sql":
        from .guard import guard_readonly_sql

        return guard_readonly_sql
    if name == "preview_dataset_sql":
        from .preview import preview_dataset_sql

        return preview_dataset_sql
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
