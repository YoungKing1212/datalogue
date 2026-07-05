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


import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from agentscope.credential import (
    AnthropicCredential,
    DashScopeCredential,
    DeepSeekCredential,
    GeminiCredential,
    MoonshotCredential,
    OpenAICredential,
    XAICredential,
)
from agentscope.message import AssistantMsg, Msg, SystemMsg, UserMsg
from agentscope.model import (
    AnthropicChatModel,
    DashScopeChatModel,
    DeepSeekChatModel,
    GeminiChatModel,
    MoonshotChatModel,
    OpenAIChatModel,
    XAIChatModel,
)
from agentscope.model._model_response import ChatResponse
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.llm_config import DEFAULT_LLM_ROLE, resolve_llm_config

_settings = get_settings()
logger = logging.getLogger(__name__)
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


def _llm_call_policy(role: str) -> dict[str, Any]:
    """返回角色级调用策略，集中控制 token 封顶和结构化输出。"""

    return dict(ROLE_CALL_POLICIES.get(role, {}))


def _message_role(message: Any) -> str:
    """把 LangChain message 类型映射为 AgentScope chat role。"""

    role = getattr(message, "role", None) or getattr(message, "type", None)
    if role in {"human", "user"}:
        return "user"
    if role in {"ai", "assistant"}:
        return "assistant"
    if role == "system":
        return "system"
    return "user"


def _to_agentscope_messages(messages: list[Any]) -> list[Msg]:
    """将现有 LangChain/OpenAI 风格消息转换为 AgentScope Msg。"""

    converted: list[Msg] = []
    for index, message in enumerate(messages):
        if isinstance(message, dict):
            role = str(message.get("role") or "user")
            content = str(message.get("content") or "")
        else:
            role = _message_role(message)
            content = str(getattr(message, "content", message) or "")
        name = f"datalogue_{role}_{index}"
        if role == "system":
            converted.append(SystemMsg(name=name, content=content))
        elif role == "assistant":
            converted.append(AssistantMsg(name=name, content=content))
        else:
            converted.append(UserMsg(name=name, content=content))
    return converted


def _agentscope_response_text(response: ChatResponse) -> str:
    """提取 AgentScope ChatResponse 中可见文本块。"""

    chunks: list[str] = []
    for block in response.content or []:
        text = getattr(block, "text", None)
        if text:
            chunks.append(str(text))
    return "".join(chunks)


def _agentscope_usage_metadata(response: ChatResponse) -> dict[str, int]:
    usage = response.usage
    prompt = getattr(usage, "input_tokens", 0) or 0
    completion = getattr(usage, "output_tokens", 0) or 0
    total = prompt + completion
    return {
        "input_tokens": int(prompt),
        "output_tokens": int(completion),
        "total_tokens": int(total),
    }


async def _collect_async_stream(stream: AsyncIterator[ChatResponse]) -> list[ChatResponse]:
    responses: list[ChatResponse] = []
    async for response in stream:
        responses.append(response)
    return responses


class AgentScopeChatClient:
    """AgentScope ChatModel 适配器，让现有链路继续使用 invoke/stream 接口。"""

    def __init__(
        self,
        *,
        provider: str,
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
        self.provider = provider
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
        self.thinking_enabled = thinking_enabled
        self.datalogue_thinking_enabled = thinking_enabled
        self.datalogue_thinking_request = model_kwargs
        self.datalogue_call_policy = call_policy or {}

    def _parameters(self) -> OpenAIChatModel.Parameters:
        """生成 AgentScope 参数；结构化输出后续用原生 structured output 单独接入。"""

        return OpenAIChatModel.Parameters(
            max_tokens=self.max_tokens,
            thinking_enable=bool(self.thinking_enabled),
            temperature=self.temperature,
        )

    def _client_kwargs(self) -> dict[str, Any]:
        # 连接超时是模型配置的运行边界，交给 AgentScope 底层 HTTP client 消费。
        return {"timeout": self.timeout}

    def _extra_body(self) -> dict[str, Any] | None:
        extra_body = self.model_kwargs.get("extra_body")
        return extra_body if isinstance(extra_body, dict) and extra_body else None

    def _build_model(self, *, stream: bool):
        provider = (self.provider or "openai-compatible").strip().lower()
        secret = SecretStr(self.api_key or "")
        parameters = self._parameters()
        client_kwargs = self._client_kwargs()
        if provider in {"dashscope", "qwen", "aliyun"}:
            return DashScopeChatModel(
                credential=DashScopeCredential(api_key=secret, base_url=self.api_base or "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                model=self.model,
                parameters=parameters,
                stream=stream,
                client_kwargs=client_kwargs,
            )
        if provider == "deepseek":
            return DeepSeekChatModel(
                credential=DeepSeekCredential(api_key=secret, base_url=self.api_base or "https://api.deepseek.com"),
                model=self.model,
                parameters=parameters,
                stream=stream,
                client_kwargs=client_kwargs,
            )
        if provider == "moonshot":
            return MoonshotChatModel(
                credential=MoonshotCredential(api_key=secret, base_url=self.api_base or "https://api.moonshot.cn/v1"),
                model=self.model,
                parameters=parameters,
                stream=stream,
                client_kwargs=client_kwargs,
            )
        if provider == "anthropic":
            return AnthropicChatModel(
                credential=AnthropicCredential(api_key=secret, base_url=self.api_base),
                model=self.model,
                parameters=parameters,
                stream=stream,
                client_kwargs=client_kwargs,
            )
        if provider == "gemini":
            return GeminiChatModel(
                credential=GeminiCredential(api_key=secret),
                model=self.model,
                parameters=parameters,
                stream=stream,
                client_kwargs=client_kwargs,
            )
        if provider in {"xai", "grok"}:
            return XAIChatModel(
                credential=XAICredential(api_key=secret),
                model=self.model,
                parameters=parameters,
                stream=stream,
                client_kwargs=client_kwargs,
            )
        return OpenAIChatModel(
            credential=OpenAICredential(api_key=secret, base_url=self.api_base),
            model=self.model,
            parameters=parameters,
            stream=stream,
            client_kwargs=client_kwargs,
            extra_body=self._extra_body(),
        )

    def invoke(self, messages: list[BaseMessage] | list[Any]) -> AIMessage:
        model = self._build_model(stream=False)
        response = model(_to_agentscope_messages(messages))
        content = _agentscope_response_text(response)
        return AIMessage(
            content=content,
            response_metadata={"provider": "agentscope", "model": self.model},
            usage_metadata=_agentscope_usage_metadata(response),
        )

    def stream(self, messages: list[BaseMessage] | list[Any]):
        model = self._build_model(stream=True)
        stream = model(_to_agentscope_messages(messages))
        for response in asyncio.run(_collect_async_stream(stream)):
            content = _agentscope_response_text(response)
            if content:
                yield AIMessageChunk(
                    content=content,
                    response_metadata={"provider": "agentscope", "model": self.model},
                )

    async def astream(self, messages: list[BaseMessage] | list[Any]):
        model = self._build_model(stream=True)
        stream = model(_to_agentscope_messages(messages))
        async for response in stream:
            content = _agentscope_response_text(response)
            if content:
                yield AIMessageChunk(
                    content=content,
                    response_metadata={"provider": "agentscope", "model": self.model},
                )


def get_llm(
    temperature: float = 0.0,
    *,
    role: str = DEFAULT_LLM_ROLE,
    db: Session | None = None,
) -> Any:
    """获取配置好的 LLM 实例。

    数据库模型配置优先；未配置或未传入 db 时回退到 .env 中的 OpenAI-compatible
    配置。所有调用统一通过 AgentScope ChatModel，保留 invoke/stream 接口以兼容
    现有 LangGraph / Observability 链路。
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
    llm = AgentScopeChatClient(
        provider=config.provider,
        model=config.model,
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
