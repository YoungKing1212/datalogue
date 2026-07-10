# ============================================================
# File Name   : workbench_view.py
# Description:
#   Agent Team Workbench view facade。
#
# Responsibilities:
#   - 暴露 Agent Team 线程和 artifact 的 Workbench view 构建入口。
#   - 保持视图 payload 脱敏、旧会话只读回放和 artifact 归属校验由 Workbench view model 单点负责。
#   - 让 API 层从 Agent Team 业务域读取对外视图，而不是直接依赖底层实现目录。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.domains.workbench.view_model import (
    WorkbenchViewNotFoundError,
    build_legacy_conversation_view,
    build_workbench_artifact_view,
    build_workbench_thread_view,
    sanitize_workbench_view_payload,
)

__all__ = [
    "WorkbenchViewNotFoundError",
    "build_legacy_conversation_view",
    "build_workbench_artifact_view",
    "build_workbench_thread_view",
    "sanitize_workbench_view_payload",
]
