# ============================================================
# File Name   : llm_config.py
# Description:
#   AgentScope credential 到旧同步 LLM 工厂的兼容解析服务。
#
# Responsibilities:
#   - 从 AgentScope Service credential 资源读取默认模型凭证。
#   - 为尚未迁到 AgentScope session 的旧同步 SDK 调用提供最小连接配置。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import Settings
from app.agentscope_service.client import DEFAULT_AGENTSCOPE_USER_ID

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
    credential_id: str | None = None


def _credential_data(item: dict) -> dict:
    data = item.get("data")
    return data if isinstance(data, dict) else item


def credential_data_from_items(credentials: list[dict], credential_id: str) -> dict | None:
    """从 AgentScope credential 列表中提取指定凭证的数据体。"""
    for item in credentials:
        item_id = item.get("id") or item.get("credential_id") or _credential_data(item).get("id")
        if item_id != credential_id:
            continue
        data = dict(_credential_data(item))
        data.setdefault("id", item_id)
        return data
    return None


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


def resolve_llm_config(
    settings: Settings,
    *,
    role: str = DEFAULT_LLM_ROLE,
    db: object | None = None,
) -> ResolvedLLMConfig:
    """解析旧同步 LLM 工厂配置；AgentScope credential 是唯一持久化来源。"""
    normalized_role = (role or DEFAULT_LLM_ROLE).strip() or DEFAULT_LLM_ROLE
    _ = db  # 兼容旧调用签名；Datalogue 不再读取本地 LLM 配置表。
    credential = credential_data_from_items(_fetch_agentscope_credentials(settings), DEFAULT_MODEL_CREDENTIAL_ID)
    if credential is not None:
        return ResolvedLLMConfig(
            role=normalized_role,
            source="agentscope_credential",
            name=str(credential.get("name") or DEFAULT_MODEL_CREDENTIAL_ID),
            provider=str(credential.get("type") or "openai_credential"),
            base_url=credential.get("base_url") or settings.OPENAI_BASE_URL,
            model=settings.LLM_MODEL,
            # AgentScope Service 是密钥真相源；如果服务端列表已脱敏，旧同步调用才使用环境变量降级。
            api_key=str(credential.get("api_key") or settings.OPENAI_API_KEY or ""),
            request_timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            thinking_enabled=False,
            credential_id=DEFAULT_MODEL_CREDENTIAL_ID,
        )

    return ResolvedLLMConfig(
        role=normalized_role,
        source="env_fallback",
        name="env-default",
        provider="openai-compatible",
        base_url=settings.OPENAI_BASE_URL,
        model=settings.LLM_MODEL,
        api_key=settings.OPENAI_API_KEY or "",
        request_timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        thinking_enabled=False,
        credential_id=None,
    )
