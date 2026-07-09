# ============================================================
# File Name   : base.py
# Description:
#   数据源适配器基类门面，re-export DatasourceAdapter。
#
# Responsibilities:
#   - 暴露适配器抽象基类，供适配器扩展与依赖注入使用
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""数据源适配器基类兼容导出。

真实实现已由旧入口迁到 `app.domains.data_source.service`；本文件为逐步
拆分保留 adapter 专属导入路径，并复用同一个类对象避免双实现。
"""

from app.domains.data_source.service import DatasourceAdapter  # noqa: F401  兼容迁移中，保留公开导出

# 迁移期保持同一类对象，但让新目录成为可观测归属，方便后续继续下沉实现。
DatasourceAdapter.__module__ = __name__

__all__ = ["DatasourceAdapter"]
