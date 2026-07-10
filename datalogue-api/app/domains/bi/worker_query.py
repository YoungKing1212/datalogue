# ============================================================
# File Name   : worker_query.py
# Description:
#   BI Worker 数据集查询执行兼容入口。
#
# Responsibilities:
#   - 暴露 execute_dataset_query_for_agent_team_direct_fallback 与 result 结构。
#   - 保持真实实现源在 app.domains.bi.worker.dataset_query。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""BI Worker 数据集查询执行门面。

真实的降级查询执行逻辑已经位于 `app.domains.bi.worker.dataset_query`；
本文件只保留旧聚合入口，避免迁移期出现 import break。
"""

from app.domains.bi.worker.dataset_query import (  # noqa: F401  迁移期聚合入口，保留公开导出
    AgentTeamDatasetQueryResult,
    execute_dataset_query_for_agent_team_direct_fallback,
)

__all__ = [
    "AgentTeamDatasetQueryResult",
    "execute_dataset_query_for_agent_team_direct_fallback",
]
