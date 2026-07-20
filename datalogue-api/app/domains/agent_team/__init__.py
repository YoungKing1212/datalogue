# ============================================================
# File Name   : __init__.py
# Description:
#   Datalogue Agent Team 业务域包。
#
# Responsibilities:
#   - 声明对外 Agent Team task 真相源、Workbench view/retry 和事件 envelope 投影边界。
#   - 保持 AgentScope Service runtime / registry / runner 归 `app.runtime.engine` 所有。
#   - 本包只承载 Agent Team 业务契约与领域能力，不转发运行时引擎入口。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""Datalogue Agent Team 业务域包。

本包的 canonical 入口只覆盖 Datalogue 对外 task 真相源、Workbench 视图/重试
动作，以及 AgentScope event 到 Datalogue event envelope 的投影。AgentScope
官方 Service 的 app factory、registry、runner、worker middleware 等运行时能力归
`app.runtime.engine` 与本域对应模块，避免运行时框架接入与业务状态真相源混在同一层。
"""

__all__ = [
    "contracts",
    "event_projection",
    "retry_actions",
    "task_runtime",
    "workbench_view",
]
