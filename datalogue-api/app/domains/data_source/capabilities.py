# ============================================================
# File Name   : capabilities.py
# Description:
#   数据源能力结构定义。
#
# Responsibilities:
#   - 描述一种数据源类型在当前系统中的能力边界。
#   - 为注册表和 capabilities API 提供稳定的数据结构。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasourceCapability:
    """描述一种数据源类型在当前系统中的能力边界。"""

    db_type: str
    label: str
    dialect: str
    driver: str | None
    driver_module: str | None
    sqlalchemy_driver: str
    default_port: int
    default_schema: str | None = None
    stable: bool = False
    required_options: tuple[str, ...] = ()
    optional_options: tuple[str, ...] = ()
    supports_sqlalchemy: bool = True
    test_sql: str = "SELECT 1"


__all__ = ["DatasourceCapability"]
