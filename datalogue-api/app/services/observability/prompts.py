# ============================================================
# File Name   : prompts.py
# Description:
#   Langfuse Prompt Manager 访问封装。
#
# Responsibilities:
#   - 按 prompt label 拉取远程 prompt，并提供本地兜底。
#   - 记录 prompt 版本信息到当前观测上下文。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.services.observability.context import current_observability_context

logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    """运行期 prompt 模板。"""

    name: str
    content: str
    version: str | int | None = None
    source: str = "local"

    def compile(self, **variables: Any) -> str:
        text = self.content
        for key, value in variables.items():
            text = text.replace("{{" + key + "}}", str(value))
            text = text.replace("{" + key + "}", str(value))
        return text


class PromptManager:
    """Langfuse Prompt Manager 客户端封装。"""

    def __init__(self):
        self.settings = get_settings()
        self._client = None

    def get_text_prompt(self, name: str, *, fallback: str) -> PromptTemplate:
        """读取 text prompt；失败时使用 fallback。"""

        if not self.settings.LANGFUSE_ENABLED:
            prompt = PromptTemplate(name=name, content=fallback, version="local", source="local")
            self._record_prompt_version(prompt)
            return prompt
        try:
            client = self._get_client()
            if client is None:
                raise RuntimeError("Langfuse client unavailable")
            remote = client.get_prompt(name, label=self.settings.LANGFUSE_PROMPT_LABEL)
            content = getattr(remote, "prompt", None) or getattr(remote, "content", None)
            if isinstance(content, list):
                content = "\n".join(
                    str(item.get("content", item)) if isinstance(item, dict) else str(item)
                    for item in content
                )
            if not content:
                raise RuntimeError("remote prompt is empty")
            prompt = PromptTemplate(
                name=name,
                content=str(content),
                version=getattr(remote, "version", None),
                source="langfuse",
            )
        except Exception as exc:
            logger.warning("Langfuse prompt 拉取失败 name=%s，使用本地兜底: %s", name, exc)
            prompt = PromptTemplate(name=name, content=fallback, version="local", source="fallback")
        self._record_prompt_version(prompt)
        return prompt

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from langfuse import get_client  # noqa: PLC0415

            self._client = get_client()
            return self._client
        except Exception as exc:
            logger.debug("Langfuse prompt client 初始化失败: %s", exc)
            return None

    @staticmethod
    def _record_prompt_version(prompt: PromptTemplate) -> None:
        context = current_observability_context.get()
        if not context:
            return
        context.prompt_versions[prompt.name] = {
            "version": prompt.version,
            "source": prompt.source,
        }


@lru_cache
def get_prompt_manager() -> PromptManager:
    return PromptManager()
