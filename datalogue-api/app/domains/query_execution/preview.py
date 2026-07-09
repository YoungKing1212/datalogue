# ============================================================
# File Name   : preview.py
# Description:
#   数据集 SQL 预览门面，re-export `app.services.sql_preview` 中的公开能力。
#
# Responsibilities:
#   - 暴露 preview_dataset_sql，用于数据集只读预览查询
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""数据集 SQL 预览门面。

只做 re-export，实际预览执行/清洗逻辑仍在 `app.services.sql_preview`；
本文件不承载新业务逻辑。
"""

from app.services.sql_preview import preview_dataset_sql  # noqa: F401  兼容迁移中，保留公开导出

__all__ = ["preview_dataset_sql"]
