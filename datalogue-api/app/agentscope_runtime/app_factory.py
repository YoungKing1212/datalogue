# ============================================================
# File Name   : app_factory.py
# Description:
#   AgentScope Service FastAPI 子应用 factory 的目标 facade。
#
# Responsibilities:
#   - 暴露 create_embedded_runtime_app 作为新目录的稳定入口。
#   - 继续复用旧实现，保证 facade-first 阶段不改变 Service 创建语义。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.runtime.engine.app_factory import create_embedded_runtime_app

__all__ = ["create_embedded_runtime_app"]
