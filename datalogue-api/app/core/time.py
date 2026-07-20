# ============================================================
# File Name   : time.py
# Description:
#   统一生成 UTC 时间，区分带时区的运行时值与旧表的无时区存储值。
#
# Responsibilities:
#   - 为新代码提供带 UTC 时区的当前时间。
#   - 为仍使用 DateTime(timezone=False) 的旧表提供显式无时区兼容值。
#
# Author      : yangkai
# Created On  : 2026-07-17
# ============================================================

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间，适用于协议、日志和 timezone=True 字段。"""

    return datetime.now(timezone.utc)


def utc_now_naive() -> datetime:
    """返回显式去除时区的 UTC 时间，仅兼容尚未迁移的无时区数据库列。"""

    return utc_now().replace(tzinfo=None)


__all__ = ["utc_now", "utc_now_naive"]
