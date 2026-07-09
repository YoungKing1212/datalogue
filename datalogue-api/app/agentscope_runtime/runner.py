# ============================================================
# File Name   : runner.py
# Description:
#   AgentScope Runtime 任务执行门面，re-export AgentScopeServiceTaskRunner。
#
# Responsibilities:
#   - 暴露 AgentScope Service 侧的流式任务 Runner
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""AgentScope Runtime 任务执行门面。

实际的流式合流、任务上下文与失败恢复逻辑仍在
`app.agentscope_service.runner`；本文件只做懒加载 re-export。
"""

__all__ = [
    "DEFAULT_LEADER_AGENT_ID",
    "AgentScopeServiceTaskRunner",
]


def __getattr__(name: str):
    """兼容迁移中按需加载旧 Runner，避免导入 facade 时触发旧运行时循环依赖。"""

    if name in __all__:
        from app.agentscope_service import runner as legacy_runner  # 兼容层只转发旧实现，不承载新逻辑

        return getattr(legacy_runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
