# ============================================================
# File Name   : llm.py
# Description:
#   LLM 模型配置和任务角色绑定持久化模型。
#
# Responsibilities:
#   - 存储 OpenAI-compatible / LiteLLM 模型连接配置。
#   - 维护问数链路中不同任务角色到模型配置的绑定关系。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

from sqlalchemy import Column, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class LLMModelConfig(Base, TimestampMixin):
    """可由前端维护的 LLM 连接配置，API Key 加密后存储。"""

    __tablename__ = "llm_model_config"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False, default="litellm", server_default="litellm")
    base_url = Column(String(500), nullable=False)
    model = Column(String(200), nullable=False)
    api_key_enc = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    description = Column(Text, nullable=True)
    request_timeout_seconds = Column(Float, nullable=False, default=60.0, server_default="60")
    last_test_result = Column(JSON, nullable=True)
    last_error_message = Column(Text, nullable=True)

    role_bindings = relationship("LLMRoleBinding", back_populates="model_config")


class LLMRoleBinding(Base, TimestampMixin):
    """任务角色到 LLM 模型配置的绑定。"""

    __tablename__ = "llm_role_binding"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(50), nullable=False, unique=True, index=True)
    model_config_id = Column(Integer, ForeignKey("llm_model_config.id"), nullable=True)

    model_config = relationship("LLMModelConfig", back_populates="role_bindings")
