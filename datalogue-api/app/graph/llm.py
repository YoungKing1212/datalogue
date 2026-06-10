# ============================================================
# File Name   : llm.py
# Description:
#   LLM 客户端工厂和配置辅助函数。
#
# Responsibilities:
#   - 根据应用配置创建聊天模型实例。
#   - 集中维护模型服务商配置。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# LLM 客户端封装 — 统一入口，支持切换模型


import logging

import httpx
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.llm_config import DEFAULT_LLM_ROLE, resolve_llm_config

_settings = get_settings()
logger = logging.getLogger(__name__)


def _http_client(timeout_seconds: float) -> httpx.Client:
    """创建 HTTP 客户端，代理由环境配置控制。"""
    kwargs: dict[str, object] = {
        "verify": False,
        "timeout": timeout_seconds,
    }
    if _settings.OPENAI_PROXY_URL:
        kwargs["proxy"] = _settings.OPENAI_PROXY_URL
    return httpx.Client(**kwargs)


def get_llm(
    temperature: float = 0.0,
    *,
    role: str = DEFAULT_LLM_ROLE,
    db: Session | None = None,
) -> ChatOpenAI:
    """获取配置好的 LLM 实例。

    数据库模型配置优先；未配置或未传入 db 时回退到 .env 中的 OpenAI-compatible
    配置。底层仍使用 ChatOpenAI，因为 LiteLLM Proxy 和多数国产/私有模型网关
    都兼容 OpenAI Chat Completions 协议。
    """
    config = resolve_llm_config(_settings, role=role, db=db)
    logger.info(
        (
            "创建 LLM 客户端: role=%s, source=%s, provider=%s, model=%s, "
            "base_url=%s, temperature=%s, proxy_enabled=%s, timeout_seconds=%s"
        ),
        config.role,
        config.source,
        config.provider,
        config.model,
        config.base_url,
        temperature,
        bool(_settings.OPENAI_PROXY_URL),
        config.request_timeout_seconds,
    )
    return ChatOpenAI(
        model=config.model,
        api_key=config.api_key,  # type: ignore[arg-type]
        base_url=config.base_url,
        temperature=temperature,
        streaming=True,  # 启用 token 级流式，供 astream_events 捕获
        http_client=_http_client(config.request_timeout_seconds),
        timeout=config.request_timeout_seconds,
    )
