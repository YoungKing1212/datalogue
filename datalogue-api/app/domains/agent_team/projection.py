# ============================================================
# File Name   : projection.py
# Description:
#   Agent Team 事件投影门面，re-export project_runtime_event。
#
# Responsibilities:
#   - 暴露 AgentScope Service 事件到 Datalogue 事件的投影函数
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""Agent Team 事件投影门面。

实际的事件解析、类型映射、HITL 判定仍在
`app.agentscope_service.projection`；本文件只做懒加载 re-export。
"""

__all__ = ["project_runtime_event"]


def __getattr__(name: str):
    """兼容迁移中按需加载旧投影函数，避免导入领域包时触发旧运行时循环依赖。"""

    if name in __all__:
        from app.runtime.engine import projection as legacy_projection  # 兼容层只转发旧实现，不承载新逻辑

        return getattr(legacy_projection, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
