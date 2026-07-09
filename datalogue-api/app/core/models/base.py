# ============================================================
# File Name   : base.py
# Description:
#   共享 SQLAlchemy 基础模型定义。
#
# Responsibilities:
#   - 定义通用时间戳 mixin。
#   - 提供可复用的模型基础工具。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from sqlalchemy import Column, DateTime, func


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
