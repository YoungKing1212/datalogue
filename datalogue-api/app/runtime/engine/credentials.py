# ============================================================
# File Name   : credentials.py
# Description:
#   Datalogue 专用 AgentScope credential 类型定义。
#
# Responsibilities:
#   - 注册可由设置页持久化的 LLM 配置字段。
#   - 复用 AgentScope OpenAI-compatible ChatModel 接管实际模型调用。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

from typing import Literal

from agentscope.credential import OpenAICredential
from pydantic import ConfigDict, Field


class DatalogueLLMCredential(OpenAICredential):
    """Datalogue 设置页专用的 AgentScope credential，承载模型配置入口的持久化字段。"""

    model_config = ConfigDict(title="Datalogue LLM Credential")

    type: Literal["datalogue_llm_credential"] = "datalogue_llm_credential"
    model: str = Field(default="", description="Default chat model name selected in Datalogue settings.")
    status: Literal["active", "disabled"] = Field(
        default="active",
        description="Datalogue-side enablement flag for this credential.",
    )
    description: str | None = Field(default=None, description="Human readable usage note.")
    request_timeout_seconds: int = Field(
        default=60,
        ge=1,
        description="Default request timeout used by Datalogue when creating chat sessions.",
    )
