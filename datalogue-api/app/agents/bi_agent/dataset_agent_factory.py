# ============================================================
# File Name   : dataset_agent_factory.py
# Description:
#   BI Agent handoff 使用的 AgentScope DatasetAgent 工厂。
#
# Responsibilities:
#   - 基于 AgentScope 2.0 SDK 创建 DatasetAgent。
#   - 注册 DatasetAgent external tools，并把 SQL/schema/raw rows 等内部执行态挡在 Agent 输出边界内。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from pydantic import SecretStr
from sqlalchemy.orm import Session

from agentscope.agent import Agent
from agentscope.credential import OpenAICredential
from agentscope.middleware import TracingMiddleware
from agentscope.model import OpenAIChatModel
from agentscope.tool import Toolkit

from app.core.config import get_settings
from app.bi.skill.runtime_bridge import (
    AgentScopeDatasetRuntimeSession,
    build_dataset_agentscope_tools,
)
from app.services.llm_config import resolve_llm_config


from app.prompts import DATASET_AGENT_SYSTEM_PROMPT


class AgentScopeDatasetAgentFactory:
    """创建 AgentScope 2.0 DatasetAgent；每个 handoff session 绑定自己的 external tools。"""

    def __init__(self, db: Session):
        self.db = db

    def create(self, session: AgentScopeDatasetRuntimeSession) -> Agent:
        config = resolve_llm_config(get_settings(), role="lead_agent", db=self.db)
        credential = OpenAICredential(
            name=config.name,
            api_key=SecretStr(config.api_key or ""),
            base_url=config.base_url,
        )
        model = OpenAIChatModel(
            credential,
            config.model,
            stream=True,
            client_kwargs={"timeout": config.request_timeout_seconds},
        )
        tools = build_dataset_agentscope_tools(
            session=session,
            agent_name="bi_worker",
        )  # DatasetAgent external tools 绑定当前 session，避免跨 handoff 复用内部执行态。
        return Agent(
            name="dataset_agent",
            system_prompt=DATASET_AGENT_SYSTEM_PROMPT,
            model=model,
            toolkit=Toolkit(tools=tools),
            # AgentScope 原生 OpenTelemetry tracing；未配置 TracerProvider 时 SDK 会短路为近零开销。
            middlewares=[TracingMiddleware()],
        )
