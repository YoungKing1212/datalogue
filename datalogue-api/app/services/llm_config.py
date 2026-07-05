# ============================================================
# File Name   : llm_config.py
# Description:
#   LLM 模型配置读取服务。
#
# Responsibilities:
#   - 按显式模型配置解析启用的 LLM 连接配置。
#   - 在未选择模型时提供默认启用配置或环境变量兜底。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import decrypt_password
from app.models.llm import LLMModelConfig

DEFAULT_LLM_ROLE = "default"


@dataclass(frozen=True)
class ResolvedLLMConfig:
    """LLM 客户端工厂消费的连接配置。"""

    role: str
    source: str
    name: str
    provider: str
    base_url: Optional[str]
    model: str
    api_key: str
    request_timeout_seconds: float
    thinking_enabled: bool


def model_config_to_dict(config: LLMModelConfig) -> dict:
    """返回前端可见的模型配置，不暴露明文 API Key。"""
    return {
        "id": config.id,
        "name": config.name,
        "provider": config.provider,
        "base_url": config.base_url,
        "model": config.model,
        "status": config.status,
        "description": config.description,
        "request_timeout_seconds": config.request_timeout_seconds,
        "thinking_enabled": bool(config.thinking_enabled),
        "api_key_set": bool(config.api_key_enc),
        "last_test_result": config.last_test_result,
        "last_error_message": config.last_error_message,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


def _active_config_by_id(db: Session, config_id: int) -> LLMModelConfig:
    config = db.get(LLMModelConfig, config_id)
    if not config or config.status != "active":
        raise ValueError(f"LLM 模型配置不存在或未启用: {config_id}")
    return config


def _default_active_config(db: Session) -> LLMModelConfig | None:
    """未显式选择模型时，使用最新启用配置作为 Datalogue 默认模型。"""

    return (
        db.query(LLMModelConfig)
        .filter(LLMModelConfig.status == "active")
        .order_by(LLMModelConfig.id.desc())
        .first()
    )


def resolve_llm_config(
    settings: Settings,
    *,
    role: str = DEFAULT_LLM_ROLE,
    db: Session | None = None,
    model_config_id: int | None = None,
) -> ResolvedLLMConfig:
    """解析 LLM 配置；不再读取 role binding，数据库模型配置优先。"""
    normalized_role = (role or DEFAULT_LLM_ROLE).strip() or DEFAULT_LLM_ROLE
    config = None
    if db is not None:
        if model_config_id is not None:
            # 用户在聊天框显式选择模型时，只覆盖本轮模型配置；角色名只作为审计标签保留。
            config = _active_config_by_id(db, model_config_id)
        else:
            # role binding 已删除；未显式选择时只能走默认启用模型或环境变量兜底。
            config = _default_active_config(db)

    if config is not None:
        api_key = decrypt_password(config.api_key_enc) if config.api_key_enc else ""
        return ResolvedLLMConfig(
            role=normalized_role,
            source="database",
            name=config.name,
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            api_key=api_key,
            request_timeout_seconds=float(config.request_timeout_seconds or settings.LLM_TIMEOUT_SECONDS),
            thinking_enabled=bool(config.thinking_enabled),
        )

    return ResolvedLLMConfig(
        role=normalized_role,
        source="env",
        name="env-default",
        provider="openai-compatible",
        base_url=settings.OPENAI_BASE_URL,
        model=settings.LLM_MODEL,
        api_key=settings.OPENAI_API_KEY or "",
        request_timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        thinking_enabled=False,
    )
