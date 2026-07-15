# ============================================================
# File Name   : llm.py
# Description:
#   LLM 模型配置持久化模型。
#
# Responsibilities:
#   - 存储前端设置页维护的模型连接配置。
#   - 保存运行时模型参数和最近一次连接测试结果。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

from sqlalchemy import Boolean, Column, Float, Integer, JSON, String, Text

from app.core.database import Base
from app.core.models.base import TimestampMixin


class LLMModelConfig(Base, TimestampMixin):
    """数据库中的 LLM 配置真相源；密钥仍只由 AgentScope credential 保存。"""

    __tablename__ = "llm_model_config"

    id = Column(Integer, primary_key=True, index=True)
    # 真实 credential ID 由 AgentScope 创建后回写；运行时不得再根据本地主键自行拼接。
    credential_id = Column(String(200), nullable=True, unique=True, index=True)
    # credential type 决定 AgentScope 采用的 ChatModel，例如 deepseek_credential。
    credential_type = Column(String(100), nullable=True)
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
