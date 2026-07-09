# ============================================================
# File Name   : __init__.py
# Description:
#   Agent Team 领域门面包，聚合 AgentScope Agent Team 相关的门面。
#
# Responsibilities:
#   - 指向 `app.agentscope_service` 与 `app.agents` 中的既有 Agent Team 实现
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""Agent Team 领域门面包。

本包只暴露 Agent Team 的既有能力（团队装配、Leader/Worker 编排等），
实现全部保留在 `app.agentscope_service` 与 `app.agents.bi_agent` 中；
不承载新业务逻辑。
"""

__all__: list[str] = []
