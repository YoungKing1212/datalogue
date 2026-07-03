# ============================================================
# File Name   : client.py
# Description:
#   Datalogue 调用 AgentScope Agent Service 的内部客户端。
#
# Responsibilities:
#   - 通过官方 REST 接口创建 session、触发 chat、订阅 session stream。
#   - 隔离 AgentScope HTTP 协议，避免 Chat UI 直接依赖 AgentScope SDK 对象。
#   - 不执行任何 Agent loop；运行时由 Agent Service 接管。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


class AgentScopeServiceClient:
    """AgentScope Agent Service 的 REST/SSE adapter。"""

    def __init__(self, *, base_url: str, http: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.AsyncClient(base_url=self.base_url)
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self.http.aclose()

    async def __aenter__(self) -> "AgentScopeServiceClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def create_session(
        self,
        agent_id: str,
        name: str,
        chat_model_config: dict[str, Any] | None = None,
    ) -> str:
        """创建绑定固定 Agent 的 Service session，并返回官方 session_id。"""

        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "name": name,
            "chat_model_config": chat_model_config,
        }
        response = await self.http.post(self._url("/session"), json=payload)
        response.raise_for_status()
        session_id = response.json().get("session_id")
        if not session_id:
            raise ValueError("AGENTSCOPE_SERVICE_SESSION_ID_MISSING")
        return str(session_id)

    async def trigger_chat(self, agent_id: str, session_id: str, text: str) -> dict[str, Any]:
        """触发一次 AgentScope Service chat；事件由 session stream 异步返回。"""

        response = await self.http.post(
            self._url("/chat"),
            json={
                "agent_id": agent_id,
                "session_id": session_id,
                # 官方 Msg 内容在这里显式包成 text block，避免调用方传入未清洗结构体。
                "input": {
                    "name": "user",
                    "role": "user",
                    "content": [{"type": "text", "text": text}],
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def stream_session(
        self,
        session_id: str,
        *,
        agent_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """订阅 AgentScope session SSE，仅向上游返回 data 帧里的 JSON/dict 内容。"""

        params = {"agent_id": agent_id} if agent_id else None
        async with self.http.stream(
            "GET",
            self._url(f"/session/{session_id}/stream"),
            params=params,
            headers={"Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                yield self._parse_sse_data(data)

    def _url(self, path: str) -> str:
        normalized_path = "/" + path.lstrip("/")
        return f"{self.base_url}{normalized_path}"

    @staticmethod
    def _parse_sse_data(data: str) -> dict[str, Any]:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return {"raw": data}
        return parsed if isinstance(parsed, dict) else {"data": parsed}
