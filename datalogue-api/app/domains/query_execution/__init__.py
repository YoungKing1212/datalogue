# ============================================================
# File Name   : __init__.py
# Description:
#   查询执行领域门面包，聚合 SQL 预览、SQL 守卫、方言适配和查询编译。
#
# Responsibilities:
#   - 通过 preview / guard / compiler / dialect 子模块 re-export 相关能力
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""查询执行领域门面包。

聚合 `app.services.sql_preview` / `app.utils.sql_guard` /
`app.services.sql_dialect_adapter` / `app.services.query_plan_compiler`
等既有实现的公开入口；本包不承载新业务逻辑。
"""

from .compiler import compile_query_plan_to_sql  # noqa: F401  兼容迁移中，保留公开导出
from .guard import guard_readonly_sql  # noqa: F401  兼容迁移中，保留公开导出
from .preview import preview_dataset_sql  # noqa: F401  兼容迁移中，保留公开导出

__all__ = [
    "compile_query_plan_to_sql",
    "guard_readonly_sql",
    "preview_dataset_sql",
]
