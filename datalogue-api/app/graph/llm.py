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


from functools import lru_cache
import logging

import httpx
from langchain_openai import ChatOpenAI

from app.core.config import get_settings

_settings = get_settings()
logger = logging.getLogger(__name__)


def _http_client() -> httpx.Client:
    """创建 HTTP 客户端，代理由环境配置控制。"""
    kwargs: dict[str, object] = {
        "verify": False,
        "timeout": _settings.LLM_TIMEOUT_SECONDS,
    }
    if _settings.OPENAI_PROXY_URL:
        kwargs["proxy"] = _settings.OPENAI_PROXY_URL
    return httpx.Client(**kwargs)


@lru_cache(maxsize=8)
def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    """获取配置好的 LLM 实例，兼容 OpenAI 格式接口。"""
    logger.info(
        "创建 LLM 客户端: model=%s, base_url=%s, temperature=%s, proxy_enabled=%s, timeout_seconds=%s",
        _settings.LLM_MODEL,
        _settings.OPENAI_BASE_URL,
        temperature,
        bool(_settings.OPENAI_PROXY_URL),
        _settings.LLM_TIMEOUT_SECONDS,
    )
    return ChatOpenAI(
        model=_settings.LLM_MODEL,
        api_key=_settings.OPENAI_API_KEY or "",  # type: ignore[arg-type]
        base_url=_settings.OPENAI_BASE_URL,
        temperature=temperature,
        streaming=True,  # 启用 token 级流式，供 astream_events 捕获
        http_client=_http_client(),
    )
