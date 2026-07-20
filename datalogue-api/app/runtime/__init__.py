# ============================================================
# File Name   : __init__.py
# Description:
#   Datalogue runtime 公共能力延迟加载入口。
#
# Responsibilities:
#   - 暴露 Agent Team task runtime 与 thread resolver 稳定接口。
#   - 避免导入 runtime.engine 子模块时提前加载完整 Agent Team 主链。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "AgentTeamTaskRuntime": "app.runtime.agent_team_runtime",
    "AgentTeamTaskRunner": "app.runtime.agent_team_runtime",
    "new_runtime_thread_id": "app.runtime.thread_resolver",
    "normalize_thread_id": "app.runtime.thread_resolver",
    "resolve_thread_ref": "app.runtime.thread_resolver",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    """按符号加载 runtime 能力，阻断包导入阶段的反向依赖。"""

    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
