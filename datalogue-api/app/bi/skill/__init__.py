# ============================================================
# File Name   : __init__.py
# Description:
#   BI Agent Skill 公开入口。
#
# Responsibilities:
#   - 暴露 BI Agent 可注册的 Dataset 查询 Skill。
#   - 将 Toolkit、Toolchain 和 AgentScope bridge 组装从旧 service 工厂中收口。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from app.bi.skill.dataset_query import DatasetQuerySkill
from app.bi.skill.runtime_bridge import (
    AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE,
    AgentScopeDatasetRuntimeBridge,
    AgentScopeDatasetRuntimeSession,
    DatasetAgentScopeExternalTool,
    build_dataset_agentscope_tools,
)

__all__ = [
    "AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE",
    "AgentScopeDatasetRuntimeBridge",
    "AgentScopeDatasetRuntimeSession",
    "DatasetAgentScopeExternalTool",
    "DatasetQuerySkill",
    "build_dataset_agentscope_tools",
]
