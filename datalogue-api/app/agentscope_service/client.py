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
from urllib.parse import quote

import httpx


DEFAULT_AGENTSCOPE_USER_ID = "datalogue-agent-team"
AGENTSCOPE_SSE_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)


class AgentScopeServiceClient:
    """AgentScope Agent Service 的 REST/SSE adapter。"""

    def __init__(
        self,
        *,
        base_url: str,
        http: httpx.AsyncClient | None = None,
        user_id: str = DEFAULT_AGENTSCOPE_USER_ID,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.AsyncClient(base_url=self.base_url)
        self.user_id = user_id
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self.http.aclose()

    async def __aenter__(self) -> "AgentScopeServiceClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def ensure_agent(self, *, name: str, system_prompt: str) -> str:
        """用 AgentScope 官方 /agent 接口幂等准备 leader Agent，并返回真实 agent_id。"""

        existing = await self.list_agents()
        for item in existing:
            data = item.get("data") if isinstance(item, dict) else None
            if not isinstance(data, dict):
                continue
            agent_name = data.get("name")
            agent_id = item.get("id") or item.get("agent_id") or data.get("id")
            if agent_name == name and isinstance(agent_id, str) and agent_id:
                return agent_id
        return await self.create_agent(name=name, system_prompt=system_prompt)

    async def list_agents(self) -> list[dict[str, Any]]:
        """读取当前用户下 AgentScope Agent 列表。"""

        response = await self.http.get(self._url("/agent/"), headers=self._headers())
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("agents", "items", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    async def create_agent(self, *, name: str, system_prompt: str) -> str:
        """创建 AgentScope Agent；worker 不在这里创建，仍交给官方 AgentCreate。"""

        response = await self.http.post(
            self._url("/agent/"),
            json={"name": name, "system_prompt": system_prompt},
            headers=self._headers(),
        )
        response.raise_for_status()
        payload = response.json()
        agent_id = payload.get("agent_id") or payload.get("id")
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("AGENTSCOPE_SERVICE_AGENT_ID_MISSING")
        return agent_id

    async def list_credential_schemas(self) -> dict[str, Any]:
        """读取 AgentScope 官方 credential schema；前端据此动态渲染凭证表单。"""

        response = await self.http.get(self._url("/credential/schemas"), headers=self._headers())
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"schemas": payload}

    async def list_credentials(self) -> list[dict[str, Any]]:
        """读取当前 AgentScope 用户下的 credential 列表，不映射成 Datalogue 旧 DTO。"""

        response = await self.http.get(self._url("/credential/"), headers=self._headers())
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("credentials", "items", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    async def create_credential(self, payload: dict[str, Any]) -> dict[str, Any]:
        """创建 AgentScope credential；payload 原样透传给官方 Service。"""

        response = await self.http.post(
            self._url("/credential/"),
            json=payload,
            headers=self._headers(),
        )
        response.raise_for_status()
        parsed = response.json()
        return parsed if isinstance(parsed, dict) else {"data": parsed}

    async def update_credential(self, credential_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """更新 AgentScope credential；credential_id 只做路径编码，不进入 Datalogue DB。"""

        response = await self.http.patch(
            self._url(f"/credential/{quote(credential_id, safe='')}"),
            json=payload,
            headers=self._headers(),
        )
        response.raise_for_status()
        parsed = response.json()
        return parsed if isinstance(parsed, dict) else {"data": parsed}

    async def delete_credential(self, credential_id: str) -> dict[str, Any]:
        """删除 AgentScope credential；Datalogue 不维护对应 role binding 清理逻辑。"""

        response = await self.http.delete(
            self._url(f"/credential/{quote(credential_id, safe='')}"),
            headers=self._headers(),
        )
        response.raise_for_status()
        if not response.content:
            return {"deleted": True}
        parsed = response.json()
        return parsed if isinstance(parsed, dict) else {"data": parsed}

    async def list_models(self, *, provider: str) -> list[dict[str, Any]]:
        """按 AgentScope provider 读取 ModelCard 列表。"""

        response = await self.http.get(
            self._url("/model"),
            params={"provider": provider},
            headers=self._headers(),
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("models", "items", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    async def upsert_openai_credential(
        self,
        *,
        credential_id: str,
        name: str,
        api_key: str,
        base_url: str | None,
    ) -> str:
        """把 Datalogue 当前 OpenAI-compatible 配置同步到 AgentScope credential 存储。"""

        response = await self.http.post(
            self._url("/credential/"),
            json={
                "data": {
                    "id": credential_id,
                    "name": name,
                    "type": "openai_credential",
                    "api_key": api_key,
                    "base_url": base_url,
                },
            },
            headers=self._headers(),
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("credential_id") or credential_id
        if not isinstance(result, str) or not result:
            raise ValueError("AGENTSCOPE_SERVICE_CREDENTIAL_ID_MISSING")
        return result

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
        # AgentScope 2.0.3 官方 Service 创建会话端点注册为 /sessions/；缺少尾斜杠会触发 307。
        response = await self.http.post(self._url("/sessions/"), json=payload, headers=self._headers())
        response.raise_for_status()
        session_id = response.json().get("session_id")
        if not session_id:
            raise ValueError("AGENTSCOPE_SERVICE_SESSION_ID_MISSING")
        return str(session_id)

    async def trigger_chat(self, agent_id: str, session_id: str, text: str) -> dict[str, Any]:
        """触发一次 AgentScope Service chat；事件由 session stream 异步返回。"""

        response = await self.http.post(
            # AgentScope chat router 同样注册为 /chat/；显式使用规范路径，避免 httpx raise 307。
            self._url("/chat/"),
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
            headers=self._headers(),
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
            # SSE 订阅同样走官方复数 /sessions/{session_id}/stream。
            self._url(f"/sessions/{session_id}/stream"),
            params=params,
            headers={**self._headers(), "Accept": "text/event-stream"},
            # SSE 是长连接，模型推理期间可能数十秒没有新行；禁用 read timeout，保留连接/写入/连接池超时。
            timeout=AGENTSCOPE_SSE_TIMEOUT,
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

    def _headers(self) -> dict[str, str]:
        # AgentScope Service 当前用 X-User-ID 做用户边界；Datalogue 内部调用固定使用主链租户。
        return {"X-User-ID": self.user_id}

    @staticmethod
    def _parse_sse_data(data: str) -> dict[str, Any]:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return {"raw": data}
        return parsed if isinstance(parsed, dict) else {"data": parsed}
