# ============================================================
# File Name   : __init__.py
# Description:
#   数据源元数据门面子包，聚合库表探查与列取样能力。
#
# Responsibilities:
#   - 通过 inspector / sampling 子模块 re-export 元数据查询函数
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""数据源元数据门面子包。

对应库表结构探查、样本值抽取等既有能力，仅通过 re-export 暴露，
不承载新业务逻辑。
"""

from .inspector import (  # noqa: F401  兼容迁移中，保留公开导出
    get_schema,
    get_schemas,
    sync_source_tables,
)
from .sampling import preview_table  # noqa: F401  兼容迁移中，保留公开导出

__all__ = [
    "get_schema",
    "get_schemas",
    "preview_table",
    "sync_source_tables",
]
