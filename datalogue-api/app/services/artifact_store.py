# ============================================================
# File Name   : artifact_store.py
# Description:
#   查询产物持久化旧路径兼容门面。
#
# Responsibilities:
#   - re-export 查询执行领域中的 ArtifactStore，保持旧调用方导入不变。
#   - 兼容迁移中，不承载新业务逻辑。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

"""ArtifactStore 旧路径兼容层。

真实实现已下沉到 `app.domains.query_execution.artifact_store`；旧路径只保留
re-export，避免目录治理过程中一次性改动 API、Workbench 和测试调用方。
"""

from app.domains.query_execution.artifact_store import (  # noqa: F401  兼容旧调用方导入
    ArtifactKind,
    ArtifactPayloadTooLargeError,
    ArtifactStore,
)

__all__ = ["ArtifactKind", "ArtifactPayloadTooLargeError", "ArtifactStore"]
