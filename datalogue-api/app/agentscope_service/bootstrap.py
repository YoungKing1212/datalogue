# ============================================================
# File Name   : bootstrap.py
# Description:
#   AgentScope Service 中 Datalogue 固定 Agent 的启动配置。
#
# Responsibilities:
#   - 基于固定 Agent 注册表幂等创建或查找 AgentScope Agent。
#   - 为主链提供稳定 key -> agent_id 映射。
#   - 禁止把运行时动态创建 Agent 作为主链依赖。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpx

from app.agentscope_service.registry import StaticAgentSpec, build_datalogue_static_agent_specs


STATIC_AGENT_KEYS = tuple(item.key for item in build_datalogue_static_agent_specs())


class AgentScopeBootstrapService:
    """幂等准备 AgentScope Service 中的 Datalogue 固定 Agent。"""

    def __init__(
        self,
        *,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
        user_id: str = "datalogue-bootstrap",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None

    async def aclose(self) -> None:
        """关闭 bootstrap 自建的 HTTP client；外部传入 client 时由调用方管理。"""

        if self._owns_client:
            await self.client.aclose()

    async def ensure_static_agents(self) -> dict[str, str]:
        """确保固定 Agent 已在 AgentScope Service 注册，并返回 key -> agent_id。

        当前只使用 AgentScope Service REST `/agent` 边界：先查找带
        `datalogue_static_agent_key` 元数据的 Agent，缺失时再创建。
        """

        specs = build_datalogue_static_agent_specs()
        existing = await self._list_existing_static_agents()
        resolved: dict[str, str] = {}
        for spec in specs:
            if spec.key in existing:
                resolved[spec.key] = existing[spec.key]
                continue
            resolved[spec.key] = await self._create_static_agent(spec)
        return resolved

    async def _list_existing_static_agents(self) -> dict[str, str]:
        response = await self.client.get(self._agent_url(), headers=self._headers())
        response.raise_for_status()
        payload = response.json()
        result: dict[str, str] = {}
        for item in _extract_agent_items(payload):
            metadata = item.get("metadata") if isinstance(item, dict) else None
            if not isinstance(metadata, dict):
                continue
            key = metadata.get("datalogue_static_agent_key")
            agent_id = item.get("id") or item.get("agent_id")
            if isinstance(key, str) and isinstance(agent_id, str):
                # 固定 key 命中时才复用，避免用展示名误匹配到人工创建的 Agent。
                result[key] = agent_id
        return result

    async def _create_static_agent(self, spec: StaticAgentSpec) -> str:
        response = await self.client.post(
            self._agent_url(),
            json=spec.to_agent_payload(),
            headers=self._headers(),
        )
        response.raise_for_status()
        payload = response.json()
        agent_id = payload.get("id") or payload.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id:
            raise RuntimeError(f"AgentScope /agent response missing agent id for {spec.key}")
        return agent_id

    def _agent_url(self) -> str:
        return f"{self.base_url}/agent"

    def _headers(self) -> dict[str, str]:
        # AgentScope 文档中的示例使用 X-User-ID 做租户边界；真实鉴权由部署层替换。
        return {"X-User-ID": self.user_id}


def _extract_agent_items(payload: Any) -> Iterable[dict[str, Any]]:
    """兼容常见列表响应形态，避免把真实 upsert 细节写死到业务入口。"""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "agents", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []
