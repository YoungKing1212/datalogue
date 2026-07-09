# ============================================================
# File Name   : datasource.py
# Description:
#   数据源服务旧入口兼容导出。
#
# Responsibilities:
#   - 保持 app.services.datasource 历史导入路径可用。
#   - 将真实实现统一转发到 app.domains.data_source.service，避免迁移期出现双实现。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

from __future__ import annotations

# 兼容层只做 re-export：旧 API 调用方继续拿到新领域 service 中的同一批对象。
from app.domains.data_source.service import *  # noqa: F401,F403

