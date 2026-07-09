# ============================================================
# File Name   : __init__.py
# Description:
#   SQL 方言子包入口，聚合方言基础工具与执行前适配能力。
#
# Responsibilities:
#   - 暴露 names 与 adapter 子模块的稳定公开入口。
#   - 避免包初始化时急切导入 adapter，防止旧 service 迁移期循环导入。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""SQL 方言子包。

``names`` 是 G040 下沉后的方言基础工具真实实现源；``adapter`` 仍承接执行前
SQL 适配能力。包入口使用懒加载，保证任一子模块可被旧 service 安全导入。
"""

from typing import Any

__all__ = [
    "FORBIDDEN_SQL_KEYWORDS",
    "adapt_sql_for_execution",
    "contains_forbidden_keyword",
    "normalize_execution_dialect",
    "normalize_supported_dialect",
    "quote_ident",
    "quote_identifier",
    "resolve_dialect",
    "sanitize_filter_sql",
]


def __getattr__(name: str) -> Any:
    """按需加载方言工具，避免 adapter 与旧 service 之间形成初始化环。"""
    if name in {
        "FORBIDDEN_SQL_KEYWORDS",
        "contains_forbidden_keyword",
        "quote_ident",
        "resolve_dialect",
        "sanitize_filter_sql",
    }:
        from . import names

        return getattr(names, name)
    if name in {
        "adapt_sql_for_execution",
        "normalize_execution_dialect",
        "normalize_supported_dialect",
        "quote_identifier",
    }:
        from . import adapter

        return getattr(adapter, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
