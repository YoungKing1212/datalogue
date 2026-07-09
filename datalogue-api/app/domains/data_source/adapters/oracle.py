# ============================================================
# File Name   : oracle.py
# Description:
#   Oracle 数据源适配器兼容导出。
#
# Responsibilities:
#   - 暴露 OracleAdapter 专属导入路径，支撑数据源 adapter 分目录迁移。
#   - 复用领域 service 中的同一类对象，避免迁移期出现双实现。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.domains.data_source.service import OracleAdapter  # noqa: F401

# 低风险拆分阶段先复用同一类对象，仅调整可观测归属；后续可继续把类体下沉到本文件。
OracleAdapter.__module__ = __name__

__all__ = ["OracleAdapter"]

