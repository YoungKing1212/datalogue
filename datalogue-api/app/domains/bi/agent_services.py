# ============================================================
# File Name   : agent_services.py
# Description:
#   BI Agent 领域服务门面，re-export BI Agent 相关运行/交接服务。
#
# Responsibilities:
#   - 暴露 BIAgentRunService 等已有服务对象，供领域视角调用
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""BI Agent 领域服务门面。

`BIAgentRunService` 等具体服务实现仍在 `app.agents.bi_agent`；本文件只做
re-export，不承载新业务逻辑。
"""

from app.domains.bi.agent.run_service import BIAgentRunService  # noqa: F401  兼容迁移中，保留公开导出

__all__ = ["BIAgentRunService"]
