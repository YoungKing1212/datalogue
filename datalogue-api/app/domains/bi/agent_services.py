# ============================================================
# File Name   : agent_services.py
# Description:
#   BI Agent 领域服务兼容入口。
#
# Responsibilities:
#   - 暴露 BIAgentRunService，供旧调用方在迁移期间继续使用。
#   - 保持真实实现源在 app.domains.bi.agent.run_service。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""BI Agent 领域服务门面。

`BIAgentRunService` 的真实实现已经位于 `app.domains.bi.agent.run_service`；
本文件只保留旧聚合入口，避免迁移期出现 import break。
"""

from app.domains.bi.agent.run_service import BIAgentRunService  # noqa: F401  迁移期聚合入口，保留公开导出

__all__ = ["BIAgentRunService"]
