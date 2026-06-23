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
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.llm_config import DEFAULT_LLM_ROLE, resolve_llm_config

_settings = get_settings()
logger = logging.getLogger(__name__)
LITELLM_SDK_PROVIDERS = {"litellm_sdk", "litellm-sdk"}
STRUCTURED_OUTPUT_RESPONSE_FORMAT = {"type": "json_object"}
ROLE_CALL_POLICIES: dict[str, dict[str, Any]] = {
    "intent": {
        "max_tokens": 20480,
        "response_format": STRUCTURED_OUTPUT_RESPONSE_FORMAT,
        "structured_output": True,
    },
    "lead_agent": {
        "max_tokens": 20480,
        "response_format": STRUCTURED_OUTPUT_RESPONSE_FORMAT,
        "structured_output": True,
    },
    "dsl": {
        "max_tokens": 20480,
        "response_format": STRUCTURED_OUTPUT_RESPONSE_FORMAT,
        "structured_output": True,
    },
    "sql_audit": {
        "max_tokens": 20480,
        "structured_output": False,
    },
}


def build_llm_model_kwargs(config: Any) -> dict[str, Any]:
    """按模型配置生成 OpenAI-compatible 扩展参数，默认尽量关闭 Think 输出。"""
    if bool(getattr(config, "thinking_enabled", False)):
        return {}

    provider = str(getattr(config, "provider", "") or "").lower()
    model = str(getattr(config, "model", "") or "").lower()
    extra_body: dict[str, Any] = {}

    if provider in {"qwen", "dashscope", "aliyun"} or "qwen" in model:
        extra_body["enable_thinking"] = False
    if provider == "anthropic" or "claude" in model:
        extra_body["thinking"] = {"type": "disabled"}

    return {"extra_body": extra_body} if extra_body else {}


def _litellm_model_name(config: Any) -> str:
    """把现有数据库 provider/model 配置归一成 LiteLLM SDK 的模型名。"""

    model = str(getattr(config, "model", "") or "").strip()
    provider = str(getattr(config, "provider", "") or "").strip().lower()
    if not model or "/" in model:
        return model
    if provider in {"openai", "openai-compatible", "litellm", *LITELLM_SDK_PROVIDERS}:
        return f"openai/{model}"
    return f"{provider}/{model}" if provider else model


def _llm_call_policy(role: str) -> dict[str, Any]:
    """返回角色级调用策略，集中控制 token 封顶和结构化输出。"""

    return dict(ROLE_CALL_POLICIES.get(role, {}))


def _message_role(message: Any) -> str:
    """把 LangChain message 类型映射为 LiteLLM/OpenAI chat role。"""

    role = getattr(message, "role", None) or getattr(message, "type", None)
    if role in {"human", "user"}:
        return "user"
    if role in {"ai", "assistant"}:
        return "assistant"
    if role == "system":
        return "system"
    return "user"


def _to_litellm_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """将 LangChain messages 转为 LiteLLM SDK 接收的 OpenAI 消息结构。"""

    converted: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, dict):
            converted.append(message)
            continue
        converted.append(
            {
                "role": _message_role(message),
                "content": getattr(message, "content", message),
            }
        )
    return converted


def _object_or_dict_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _litellm_usage_metadata(response: Any) -> dict[str, int]:
    usage = _object_or_dict_get(response, "usage", {}) or {}
    prompt = _object_or_dict_get(usage, "prompt_tokens", 0) or 0
    completion = _object_or_dict_get(usage, "completion_tokens", 0) or 0
    total = _object_or_dict_get(usage, "total_tokens", prompt + completion) or 0
    return {
        "input_tokens": int(prompt),
        "output_tokens": int(completion),
        "total_tokens": int(total),
    }


def _litellm_response_content(response: Any) -> str:
    choices = _object_or_dict_get(response, "choices", []) or []
    if not choices:
        return ""
    first = choices[0]
    message = _object_or_dict_get(first, "message", {}) or {}
    return str(_object_or_dict_get(message, "content", "") or "")


def _litellm_chunk_content(chunk: Any) -> str:
    choices = _object_or_dict_get(chunk, "choices", []) or []
    if not choices:
        return ""
    first = choices[0]
    delta = _object_or_dict_get(first, "delta", {}) or {}
    return str(_object_or_dict_get(delta, "content", "") or "")


class LiteLLMChatClient:
    """LiteLLM SDK 适配器，让现有链路继续使用 invoke/stream 接口。"""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        api_base: str | None,
        temperature: float,
        timeout: float,
        model_kwargs: dict[str, Any],
        thinking_enabled: bool,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        call_policy: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.model_name = model
        self.api_key = api_key
        self.api_base = api_base
        self.temperature = temperature
        self.timeout = timeout
        self.model_kwargs = model_kwargs
        self.max_tokens = max_tokens
        self.response_format = response_format
        self.streaming = True
        self.datalogue_thinking_enabled = thinking_enabled
        self.datalogue_thinking_request = model_kwargs
        self.datalogue_call_policy = call_policy or {}

    def _completion_kwargs(self, messages: list[Any], *, stream: bool) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": _to_litellm_messages(messages),
            "temperature": self.temperature,
            "stream": stream,
            "timeout": self.timeout,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        if self.response_format:
            kwargs["response_format"] = self.response_format
        kwargs.update(self.model_kwargs)
        return kwargs

    def invoke(self, messages: list[BaseMessage] | list[Any]) -> AIMessage:
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover - 依赖缺失时由运行环境暴露
            raise RuntimeError("当前环境未安装 litellm，无法创建 LLM 客户端") from exc

        response = litellm.completion(**self._completion_kwargs(messages, stream=False))
        content = _litellm_response_content(response)
        return AIMessage(
            content=content,
            response_metadata={"provider": "litellm_sdk", "model": self.model},
            usage_metadata=_litellm_usage_metadata(response),
        )

    def stream(self, messages: list[BaseMessage] | list[Any]):
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover - 依赖缺失时由运行环境暴露
            raise RuntimeError("当前环境未安装 litellm，无法创建 LLM 客户端") from exc

        for chunk in litellm.completion(**self._completion_kwargs(messages, stream=True)):
            content = _litellm_chunk_content(chunk)
            if content:
                yield AIMessageChunk(
                    content=content,
                    response_metadata={"provider": "litellm_sdk", "model": self.model},
                )

    async def astream(self, messages: list[BaseMessage] | list[Any]):
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover - 依赖缺失时由运行环境暴露
            raise RuntimeError("当前环境未安装 litellm，无法创建 LLM 客户端") from exc

        stream = await litellm.acompletion(**self._completion_kwargs(messages, stream=True))
        async for chunk in stream:
            content = _litellm_chunk_content(chunk)
            if content:
                yield AIMessageChunk(
                    content=content,
                    response_metadata={"provider": "litellm_sdk", "model": self.model},
                )


def get_llm(
    temperature: float = 0.0,
    *,
    role: str = DEFAULT_LLM_ROLE,
    db: Session | None = None,
) -> Any:
    """获取配置好的 LLM 实例。

    数据库模型配置优先；未配置或未传入 db 时回退到 .env 中的 OpenAI-compatible
    配置。所有角色统一通过 LiteLLM SDK 调用，保留 invoke/stream 接口以兼容
    现有 LangGraph / Langfuse 链路。
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
    model_kwargs = build_llm_model_kwargs(config)
    call_policy = _llm_call_policy(config.role)
    llm = LiteLLMChatClient(
        model=_litellm_model_name(config),
        api_key=config.api_key,
        api_base=config.base_url,
        temperature=temperature,
        timeout=config.request_timeout_seconds,
        model_kwargs=model_kwargs,
        thinking_enabled=config.thinking_enabled,
        max_tokens=call_policy.get("max_tokens"),
        response_format=call_policy.get("response_format"),
        call_policy=call_policy,
    )
    return llm
