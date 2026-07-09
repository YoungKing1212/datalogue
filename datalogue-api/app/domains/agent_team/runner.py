# ============================================================
# File Name   : runner.py
# Description:
#   Agent Team 任务运行门面，re-export AgentTeamTaskRunner。
#
# Responsibilities:
#   - 暴露 AgentScope Service 侧的 Agent Team 流式任务 Runner
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""AgentScope runtime runner 兼容门面。

新导入边界是 `app.agentscope_runtime.runner`。Datalogue 对外 task runtime
入口请使用 `app.domains.agent_team.task_runtime`。
"""

__all__ = [
    "DEFAULT_LEADER_AGENT_ID",
    "AgentTeamTaskRunner",
]


def __getattr__(name: str):
    """兼容迁移中按需加载旧 Runner，避免导入领域包时触发旧运行时循环依赖。"""

    if name in __all__:
        from app.runtime.engine import runner as legacy_runner  # 兼容层只转发 runtime 实现，不承载业务真相源。

        return getattr(legacy_runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
