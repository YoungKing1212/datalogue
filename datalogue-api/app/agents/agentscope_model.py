# ============================================================
# File Name   : agentscope_model.py
# Description:
#   AgentScope 2.0 Agent 使用的模型工厂。
#
# Responsibilities:
#   - 基于当前 LLM 配置创建 AgentScope OpenAIChatModel。
#   - 让 Lead Agent、BI Agent 和 DatasetAgent 复用同一套 SDK 模型创建逻辑。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from pydantic import SecretStr
from sqlalchemy.orm import Session

from agentscope.credential import OpenAICredential
from agentscope.model import OpenAIChatModel

from app.core.config import get_settings
from app.services.llm_config import resolve_llm_config


def build_agentscope_chat_model(
    *,
    db: Session,
    role: str = "lead_agent",
    stream: bool = True,
) -> OpenAIChatModel:
    """创建 AgentScope 2.0 OpenAIChatModel；不在这里注入任何业务 prompt。"""

    config = resolve_llm_config(
        get_settings(),
        role=role,
        db=db,
    )
    credential = OpenAICredential(
        name=config.name,
        api_key=SecretStr(config.api_key or ""),
        base_url=config.base_url,
    )
    return OpenAIChatModel(
        credential,
        config.model,
        stream=stream,
        client_kwargs={"timeout": config.request_timeout_seconds},
    )
