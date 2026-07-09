# ============================================================
# File Name   : worker_query.py
# Description:
#   BI Worker 数据集查询执行门面，re-export dataset_query_executor 中的能力。
#
# Responsibilities:
#   - 暴露 execute_dataset_query_for_agent_team_direct_fallback 与 result 结构
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""BI Worker 数据集查询执行门面。

实际的降级查询执行逻辑仍在
`app.agentscope_service.dataset_query_executor`；本文件只做 re-export。
"""

from app.domains.bi.worker.dataset_query import (  # noqa: F401  兼容迁移中，保留公开导出
    AgentTeamDatasetQueryResult,
    execute_dataset_query_for_agent_team_direct_fallback,
)

__all__ = [
    "AgentTeamDatasetQueryResult",
    "execute_dataset_query_for_agent_team_direct_fallback",
]
