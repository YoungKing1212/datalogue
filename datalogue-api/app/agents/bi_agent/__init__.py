# ============================================================
# File Name   : __init__.py
# Description:
#   BI Agent 公开入口。
#
# Responsibilities:
#   - 暴露 BI Agent façade、Dataset 查询 Skill 和应用服务出口。
#   - 让上层 runtime、API 和测试统一依赖 `app.agents.bi_agent`。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from app.agents.bi_agent.agent import BIAgent
from app.agents.bi_agent.capabilities import build_bi_agent_capabilities, sanitize_dataset_capability
from app.agents.bi_agent.react_factory import BIAgentFactory
from app.agents.bi_agent.services import (
    BIAgentConfirmationService,
    BIAgentHandoffService,
    BIAgentRunService,
)
from app.bi.skill import DatasetQuerySkill

__all__ = [
    "BIAgent",
    "BIAgentConfirmationService",
    "BIAgentFactory",
    "BIAgentHandoffService",
    "BIAgentRunService",
    "DatasetQuerySkill",
    "build_bi_agent_capabilities",
    "sanitize_dataset_capability",
]
