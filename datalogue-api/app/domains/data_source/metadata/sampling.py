# ============================================================
# File Name   : sampling.py
# Description:
#   数据源样本抽取门面，re-export preview_table 等取样能力。
#
# Responsibilities:
#   - 暴露表数据预览 / 列值取样等入口
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""数据源样本抽取门面。

只做 re-export，实际读取逻辑仍在 `app.services.datasource`；
本文件不承载新业务逻辑。
"""

from app.domains.data_source.service import preview_table  # noqa: F401  兼容迁移中，保留公开导出

__all__ = ["preview_table"]
