# ============================================================
# File Name   : prompts.py
# Description:
#   本地 Prompt 模板访问封装。
#
# Responsibilities:
#   - 始终使用代码内 fallback prompt。
#   - 记录 prompt 来源，避免业务层依赖远端 Prompt 管理服务。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.services.observability.context import current_observability_context


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
    """本地 prompt manager；不访问外部 Prompt 管理服务。"""

    def __init__(self):
        pass

    def get_text_prompt(self, name: str, *, fallback: str) -> PromptTemplate:
        """读取 text prompt；当前只允许本地 fallback 作为真相源。"""

        prompt = PromptTemplate(name=name, content=fallback, version="local", source="local")
        self._record_prompt_version(prompt)
        return prompt

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
