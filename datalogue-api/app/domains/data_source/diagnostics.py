# ============================================================
# File Name   : diagnostics.py
# Description:
#   数据源连接、配置和元数据读取诊断结构与分类逻辑。
#
# Responsibilities:
#   - 定义统一诊断结构和稳定错误码元数据。
#   - 将底层数据库/驱动异常归类为前端和 API 可消费的诊断信息。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.exc import DBAPIError, NoSuchModuleError, OperationalError, SQLAlchemyError


DIAGNOSTIC_META = {
    "UNSUPPORTED_DB_TYPE": ("config", False, "请选择当前系统已注册的数据源类型。"),
    "DRIVER_MISSING": ("driver", False, "安装对应数据库驱动后重试，或改用已安装驱动的数据源。"),
    "CONNECTION_FAILED": ("connection", True, "检查主机、端口、网络、服务状态和连接参数。"),
    "AUTH_FAILED": ("auth", False, "检查用户名、密码和认证方式配置。"),
    "PERMISSION_DENIED": ("permission", False, "确认当前数据源账号具备读取库、schema、表和字段的权限。"),
    "SCHEMA_UNREADABLE": ("schema", False, "检查元数据读取权限，或缩小 schema 范围后重试。"),
    "SAMPLE_UNREADABLE": ("sample", True, "字段结构已同步，样例可稍后按表或字段重新采集。"),
    "DIALECT_UNSUPPORTED": ("dialect", False, "按目标数据源方言调整 SQL 或补充方言适配规则。"),
    "SQL_GUARD_BLOCKED": ("security", False, "仅允许执行当前数据集授权表上的单条只读查询。"),
    "QUERY_TIMEOUT": ("performance", True, "缩小查询范围、增加过滤条件或调大超时时间。"),
    "UNKNOWN_DATASOURCE_ERROR": ("unknown", True, "查看原始错误并按连接、权限或驱动问题继续排查。"),
}


@dataclass(frozen=True)
class DatasourceDiagnostic:
    """数据源链路的统一诊断结构。"""

    code: str
    message: str
    category: str
    retryable: bool
    suggested_action: str
    raw_error: str | None = None


def _diagnostic(code: str, message: str, raw_error: Any = None) -> dict[str, Any]:
    """生成稳定诊断字典；raw_error 只做排障透传，不改变 API 字段。"""
    category, retryable, suggested_action = DIAGNOSTIC_META.get(
        code, DIAGNOSTIC_META["UNKNOWN_DATASOURCE_ERROR"]
    )
    return asdict(
        DatasourceDiagnostic(
            code=code,
            message=message,
            category=category,
            retryable=retryable,
            suggested_action=suggested_action,
            raw_error=str(raw_error) if raw_error not in (None, "") else None,
        )
    )


def _classify_exception(exc: Exception, default_code: str = "UNKNOWN_DATASOURCE_ERROR") -> dict[str, Any]:
    """把常见数据库异常归类为稳定错误码。"""
    message = str(exc)
    lower = message.lower()
    if isinstance(exc, (NoSuchModuleError, ModuleNotFoundError, ImportError)):
        return _diagnostic("DRIVER_MISSING", "数据源驱动未安装或 SQLAlchemy 方言不可用", message)
    if any(marker in lower for marker in ("permission denied", "access denied", "not authorized", "权限")):
        return _diagnostic("PERMISSION_DENIED", "数据源账号权限不足", message)
    if any(marker in lower for marker in ("authentication", "password", "login failed", "ora-01017")):
        return _diagnostic("AUTH_FAILED", "数据源认证失败", message)
    if any(marker in lower for marker in ("timeout", "timed out", "ora-01013", "query execution was interrupted")):
        return _diagnostic("QUERY_TIMEOUT", "数据源请求超时", message)
    if isinstance(exc, (OperationalError, DBAPIError, SQLAlchemyError)):
        return _diagnostic("CONNECTION_FAILED", "数据源连接或执行失败", message)
    return _diagnostic(default_code, "数据源操作失败", message)


__all__ = ["DIAGNOSTIC_META", "DatasourceDiagnostic", "_classify_exception", "_diagnostic"]
