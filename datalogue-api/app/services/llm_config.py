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

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import decrypt_password
from app.models.llm import LLMModelConfig
from app.agentscope_service.client import DEFAULT_AGENTSCOPE_USER_ID

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


def credential_id_for_model_config(config_id: int | None) -> str:
    """生成 Datalogue 模型配置在 AgentScope credential 存储中的稳定 ID。"""

    if config_id is None:
        return "datalogue-openai-compatible-lead-agent"
    return f"datalogue-openai-compatible-model-{config_id}"


def _credential_data(item: dict) -> dict:
    data = item.get("data")
    return data if isinstance(data, dict) else item


def credential_api_key_from_items(credentials: list[dict], credential_id: str) -> str:
    """从 AgentScope credential 列表中提取指定凭证的 API Key。"""

    for item in credentials:
        item_id = item.get("id") or item.get("credential_id") or _credential_data(item).get("id")
        if item_id != credential_id:
            continue
        api_key = _credential_data(item).get("api_key")
        return str(api_key or "")
    return ""


def _fetch_agentscope_credentials(settings: Settings) -> list[dict]:
    """同步读取 AgentScope credential；旧同步 get_llm 链路用它摆脱本地密钥表依赖。"""

    base_url = (settings.AGENTSCOPE_SERVICE_BASE_URL or "").rstrip("/")
    if not base_url:
        return []
    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            response = client.get("/credential/", headers={"X-User-ID": DEFAULT_AGENTSCOPE_USER_ID})
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("credentials", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def api_key_set_for_model_config(config: LLMModelConfig, credential_ids: set[str] | None = None) -> bool:
    """判断配置是否已有可用密钥；优先看 AgentScope credential，兼容旧加密列。"""

    if credential_ids and credential_id_for_model_config(config.id) in credential_ids:
        return True
    return bool(config.api_key_enc)


def model_config_to_dict(config: LLMModelConfig, credential_ids: set[str] | None = None) -> dict:
    """返回前端可见的模型配置，不暴露明文 API Key。"""
    return {
        "id": config.id,
        "credential_id": credential_id_for_model_config(config.id),
        "name": config.name,
        "provider": config.provider,
        "base_url": config.base_url,
        "model": config.model,
        "status": config.status,
        "description": config.description,
        "request_timeout_seconds": config.request_timeout_seconds,
        "thinking_enabled": bool(config.thinking_enabled),
        "api_key_set": api_key_set_for_model_config(config, credential_ids),
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
    """解析 LLM 配置；数据库模型配置优先。"""
    normalized_role = (role or DEFAULT_LLM_ROLE).strip() or DEFAULT_LLM_ROLE
    config = None
    if db is not None:
        if model_config_id is not None:
            # 用户在聊天框显式选择模型时，只覆盖本轮模型配置；角色名只作为审计标签保留。
            config = _active_config_by_id(db, model_config_id)
        else:
            # 未显式选择时只能走默认启用模型或环境变量兜底，不能再按任务角色隐式切模型。
            config = _default_active_config(db)

    if config is not None:
        # 新配置的密钥以 AgentScope credential 为真相源；旧 api_key_enc 只作为迁移兼容。
        api_key = credential_api_key_from_items(
            _fetch_agentscope_credentials(settings),
            credential_id_for_model_config(config.id),
        )
        if not api_key and config.api_key_enc:
            api_key = decrypt_password(config.api_key_enc)
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
