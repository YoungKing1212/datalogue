# ============================================================
# File Name   : __init__.py
# Description:
#   数据源适配器门面子包，负责聚合各方言适配器的兼容导出。
#
# Responsibilities:
#   - 通过 re-export 暴露 DatasourceAdapter 及其注册表
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""数据源适配器门面子包。

暴露 `app.services.datasource` 中的适配器基类与注册结构，供下游按
领域视角引用；本子包不承载新业务逻辑。
"""

from .base import DatasourceAdapter  # noqa: F401  兼容迁移中，保留公开导出
from .registry import ADAPTERS, get_adapter  # noqa: F401  兼容迁移中，保留公开导出

__all__ = [
    "ADAPTERS",
    "DatasourceAdapter",
    "get_adapter",
]
