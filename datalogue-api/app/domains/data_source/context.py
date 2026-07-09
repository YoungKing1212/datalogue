# ============================================================
# File Name   : context.py
# Description:
#   问数链路使用的数据源上下文结构。
#
# Responsibilities:
#   - 定义跨数据集、SQL 预览和问数链路透传的数据源上下文。
#   - 保持上下文字段稳定，避免迁移期影响下游消费方。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasourceContext:
    """问数链路使用的规范化数据源上下文。"""

    datasource_id: int | None
    db_type: str
    dialect: str
    driver: str | None
    default_schema: str | None
    allowed_tables: list[str]
    query_timeout_seconds: int
    schema_version: str | None = None


__all__ = ["DatasourceContext"]
