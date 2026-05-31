# LLM 客户端封装 — 统一入口，支持切换模型


import httpx
from langchain_openai import ChatOpenAI

from app.core.config import get_settings

_settings = get_settings()


def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    """获取配置好的 LLM 实例，兼容 OpenAI 格式接口。"""
    return ChatOpenAI(
        model=_settings.LLM_MODEL,
        api_key=_settings.OPENAI_API_KEY or "",  # type: ignore[arg-type]
        base_url=_settings.OPENAI_BASE_URL,
        temperature=temperature,
        streaming=True,          # 启用 token 级流式，供 astream_events 捕获
        http_client=httpx.Client(
            proxy="http://127.0.0.1:7897",
            verify=False,
            timeout=60.0,
        ),
    )
