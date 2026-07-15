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

# 此处必须依赖底层客户端，避免导入 facade 时回引 runner，导致默认模型解析阶段循环导入。
from app.runtime.engine.client import DEFAULT_AGENTSCOPE_USER_ID
from app.core.config import Settings
from app.core.models.llm import LLMModelConfig
from app.core.security import decrypt_password

DEFAULT_LLM_ROLE = "default"
DEFAULT_MODEL_CREDENTIAL_ID = "datalogue-openai-compatible-lead-agent"


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
    model_config_id: int | None = None
    credential_id: str | None = None
    credential_type: str | None = None


def credential_id_for_model_config(config_id: int | None) -> str:
    """生成 Datalogue 模型配置在 AgentScope credential 存储中的稳定 ID。"""

    if config_id is None:
        return DEFAULT_MODEL_CREDENTIAL_ID
    return f"datalogue-openai-compatible-model-{config_id}"


def credential_type_for_provider(provider: str | None) -> str:
    """把 Datalogue 供应商标识映射为 AgentScope 原生 credential 类型。"""

    normalized = (provider or "").strip().lower()
    return {
        "deepseek": "deepseek_credential",
        "qwen": "dashscope_credential",
        "dashscope": "dashscope_credential",
        "aliyun": "dashscope_credential",
        "anthropic": "anthropic_credential",
        "gemini": "gemini_credential",
        "moonshot": "moonshot_credential",
        "xai": "xai_credential",
        "grok": "xai_credential",
    }.get(normalized, "openai_credential")


def _credential_data(item: dict) -> dict:
    data = item.get("data")
    return data if isinstance(data, dict) else item


def credential_data_from_items(credentials: list[dict], credential_id: str) -> dict | None:
    """从 AgentScope credential 列表中提取指定凭证的数据体。"""

    for item in credentials:
        data = _credential_data(item)
        item_id = item.get("id") or item.get("credential_id") or data.get("id")
        if item_id != credential_id:
            continue
        result = dict(data)
        result.setdefault("id", item_id)
        return result
    return None


def credential_api_key_from_items(credentials: list[dict], credential_id: str | None) -> str:
    """从 AgentScope credential 列表中提取指定凭证的 API Key。"""

    data = credential_data_from_items(credentials, credential_id)
    if data is None:
        return ""
    return str(data.get("api_key") or "")


def _fetch_agentscope_credentials(settings: Settings) -> list[dict]:
    """同步读取 AgentScope credential；DB 配置只通过它拿运行时密钥。"""

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


def api_key_set_for_model_config(
    config: LLMModelConfig, credential_ids: set[str] | None = None
) -> bool:
    """判断配置是否已有可用密钥；本地加密字段优先，兼容迁移中的远端旧凭据。"""

    if bool(config.api_key_enc):
        return True
    if config.credential_id and credential_ids and config.credential_id in credential_ids:
        return True
    return False


def decrypt_model_api_key(config: LLMModelConfig) -> str:
    """解密本地模型密钥，仅供服务端同步 AgentScope 或直接模型调用使用。"""

    if not config.api_key_enc:
        return ""
    try:
        return decrypt_password(config.api_key_enc)
    except Exception as exc:
        raise ValueError(f"LLM 模型配置 '{config.name}' 的本地密钥无法解密") from exc


def model_config_to_dict(config: LLMModelConfig, credential_ids: set[str] | None = None) -> dict:
    """返回前端可见的模型配置，不暴露明文 API Key。"""

    return {
        "id": config.id,
        "credential_id": config.credential_id,
        "credential_type": config.credential_type,
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
    """解析 LLM 配置；数据库模型配置优先，环境变量只做无表配置时兜底。"""

    normalized_role = (role or DEFAULT_LLM_ROLE).strip() or DEFAULT_LLM_ROLE
    config = None
    if db is not None:
        if model_config_id is not None:
            # 显式选择模型时只覆盖本轮模型配置；角色名仅作为审计标签。
            config = _active_config_by_id(db, model_config_id)
        else:
            # 未显式选择时使用页面配置中的最新启用模型，避免绕过设置页。
            config = _default_active_config(db)

    if config is not None:
        # 优先使用本地加密密钥；旧记录未完成回填时才临时从 AgentScope 读取，保证平滑升级。
        credential_id = config.credential_id
        api_key = decrypt_model_api_key(config)
        if not api_key:
            api_key = credential_api_key_from_items(
                _fetch_agentscope_credentials(settings), credential_id
            )
        return ResolvedLLMConfig(
            role=normalized_role,
            source="database",
            name=config.name,
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            api_key=api_key,
            request_timeout_seconds=float(
                config.request_timeout_seconds or settings.LLM_TIMEOUT_SECONDS
            ),
            thinking_enabled=bool(config.thinking_enabled),
            model_config_id=config.id,
            credential_id=credential_id,
            credential_type=config.credential_type,
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
        credential_id=None,
        credential_type=None,
    )
