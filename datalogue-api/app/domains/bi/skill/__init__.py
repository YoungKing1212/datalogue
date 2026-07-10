# ============================================================
# File Name   : __init__.py
# Description:
#   BI Skill 与 AgentScope Dataset runtime bridge 公开入口。
#
# Responsibilities:
#   - 暴露 DatasetQuerySkill 与 AgentScope 外部工具 bridge。
#   - 让 BI Skill 只依赖 BI Toolkit 和安全 runtime session，不承载通用 AgentScope Service 基础设施。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from app.domains.bi.skill.dataset_query import DatasetQuerySkill
from app.domains.bi.skill.runtime_bridge import (
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
