# ============================================================
# File Name   : agentscope_workbench.py
# Description:
#   AgentScope 工作台会话镜像的 Pydantic 契约。
#
# Responsibilities:
#   - 定义 C3 新会话与历史会话的线程归属类型。
#   - 定义 AgentScope mirror 消息状态和线程解析结果。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AgentScopeThreadKind(str, Enum):
    AGENTSCOPE = "agentscope"
    LEGACY_CONVERSATION = "legacy_conversation"


class AgentScopeMessageStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ThreadRef(BaseModel):
    thread_id: str
    kind: AgentScopeThreadKind
    legacy_conversation_id: Optional[int] = None
    read_only: bool = False

    model_config = ConfigDict(use_enum_values=True)
