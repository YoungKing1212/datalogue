# ============================================================
# File Name   : llm_config.py
# Description:
#   LLM 模型配置读取和角色解析服务。
#
# Responsibilities:
#   - 统一校验可绑定的 LLM 任务角色。
#   - 按角色解析数据库中的启用模型配置，并提供环境变量兜底。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import decrypt_password
from app.models.llm import LLMModelConfig, LLMRoleBinding

DEFAULT_LLM_ROLE = "default"
LLM_ROLES = (
    DEFAULT_LLM_ROLE,
    "intent",
    "dsl",
    "sql_audit",
    "report",
    "annotation",
    "blueprint",
)


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


def ensure_llm_role(role: str | None) -> str:
    """校验并归一化 LLM 任务角色。"""
    normalized = (role or DEFAULT_LLM_ROLE).strip() or DEFAULT_LLM_ROLE
    if normalized not in LLM_ROLES:
        raise ValueError(f"不支持的 LLM 角色: {normalized}")
    return normalized


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
        "api_key_set": bool(config.api_key_enc),
        "last_test_result": config.last_test_result,
        "last_error_message": config.last_error_message,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


def _active_config_by_role(db: Session, role: str) -> LLMModelConfig | None:
    binding = db.query(LLMRoleBinding).filter(LLMRoleBinding.role == role).first()
    if not binding or not binding.model_config_id:
        return None
    config = db.get(LLMModelConfig, binding.model_config_id)
    if not config or config.status != "active":
        return None
    return config


def resolve_llm_config(
    settings: Settings,
    *,
    role: str = DEFAULT_LLM_ROLE,
    db: Session | None = None,
) -> ResolvedLLMConfig:
    """按角色解析 LLM 配置；数据库优先，环境变量兜底。"""
    normalized_role = ensure_llm_role(role)
    config = None
    if db is not None:
        config = _active_config_by_role(db, normalized_role)
        if config is None and normalized_role != DEFAULT_LLM_ROLE:
            config = _active_config_by_role(db, DEFAULT_LLM_ROLE)

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
    )
