# ============================================================
# File Name   : registry.py
# Description:
#   数据源适配器注册表门面，re-export ADAPTERS / get_adapter 等。
#
# Responsibilities:
#   - 暴露已注册的数据源方言适配器与查找入口
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""数据源适配器注册表兼容导出。

真实注册表已由旧入口迁到 `app.domains.data_source.service`；本文件保留
registry 专属导入路径，并确保旧入口与新入口共享同一批对象。
"""

from app.domains.data_source.service import (  # noqa: F401  兼容迁移中，保留公开导出
    ADAPTERS,
    ALIASES,
    CAPABILITIES,
    get_adapter,
    normalize_db_type,
)

# 迁移期不复制注册表，只调整函数归属便于验证统一目录已成为新入口。
get_adapter.__module__ = __name__
normalize_db_type.__module__ = __name__

__all__ = [
    "ADAPTERS",
    "ALIASES",
    "CAPABILITIES",
    "get_adapter",
    "normalize_db_type",
]
