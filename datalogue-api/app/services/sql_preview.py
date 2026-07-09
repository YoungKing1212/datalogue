# ============================================================
# File Name   : sql_preview.py
# Description:
#   数据集 SQL 预览旧路径兼容门面。
#
# Responsibilities:
#   - re-export 查询执行领域中的 preview_dataset_sql，保持旧调用方导入不变。
#   - 兼容迁移中，不承载新业务逻辑。
#
# Author      : yangkai
# Created On  : 2026-06-23
# ============================================================

"""SQL Preview 旧路径兼容层。

真实实现已下沉到 `app.domains.query_execution.preview`；旧路径只保留
re-export，避免目录治理过程中一次性改动 API、测试和历史调用方。
"""

from app.domains.data_source.service import create_engine_for_datasource  # noqa: F401  兼容历史 monkeypatch/import
from app.domains.query_execution.preview import preview_dataset_sql  # noqa: F401  兼容旧调用方导入

__all__ = ["create_engine_for_datasource", "preview_dataset_sql"]
