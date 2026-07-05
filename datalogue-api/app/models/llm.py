# ============================================================
# File Name   : llm.py
# Description:
#   LLM 模型配置持久化模型。
#
# Responsibilities:
#   - 存储可由前端维护的 AgentScope/OpenAI-compatible 模型连接配置。
#   - 保存连接测试结果和运行时所需的模型参数。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

from sqlalchemy import Boolean, Column, Float, Integer, JSON, String, Text

from app.core.database import Base
from app.models.base import TimestampMixin


class LLMModelConfig(Base, TimestampMixin):
    """可由前端维护的 LLM 连接配置；密钥由 AgentScope credential 承载。"""

    __tablename__ = "llm_model_config"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False, default="openai-compatible", server_default="openai-compatible")
    base_url = Column(String(500), nullable=False)
    model = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    description = Column(Text, nullable=True)
    request_timeout_seconds = Column(Float, nullable=False, default=60.0, server_default="60")
    thinking_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    last_test_result = Column(JSON, nullable=True)
    last_error_message = Column(Text, nullable=True)
