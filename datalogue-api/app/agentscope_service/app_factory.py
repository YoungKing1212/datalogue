# ============================================================
# File Name   : app_factory.py
# Description:
#   构造嵌入 Datalogue 主应用的 AgentScope Service 子应用。
#
# Responsibilities:
#   - 使用官方 agentscope.app.create_app 创建 Service FastAPI 应用。
#   - 按 Settings 装配 RedisStorage、RedisMessageBus 与 LocalWorkspaceManager。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlparse

from fastapi import FastAPI

from agentscope.app import create_app as agentscope_create_app
from agentscope.app.message_bus import RedisMessageBus
from agentscope.app.storage import RedisStorage
from agentscope.app.workspace_manager import LocalWorkspaceManager

from app.agentscope_service.tools import build_datalogue_extra_agent_tools
from app.core.config import Settings


def _redis_kwargs(settings: Settings) -> dict[str, Any]:
    """把 Datalogue Settings 归一成 AgentScope Redis 组件可接受的连接参数。"""

    if settings.AGENTSCOPE_REDIS_URL:
        parsed = urlparse(settings.AGENTSCOPE_REDIS_URL)
        if parsed.scheme not in {"redis", "rediss"}:
            raise ValueError("AGENTSCOPE_REDIS_URL must use redis:// or rediss://")

        path_db = parsed.path.lstrip("/")
        kwargs: dict[str, Any] = {
            "host": parsed.hostname or settings.AGENTSCOPE_REDIS_HOST,
            "port": parsed.port or settings.AGENTSCOPE_REDIS_PORT,
            "db": int(path_db) if path_db else settings.AGENTSCOPE_REDIS_DB,
            "password": (
                unquote(parsed.password) if parsed.password else settings.AGENTSCOPE_REDIS_PASSWORD
            ),
        }
        if parsed.username:
            # redis-py ConnectionPool 支持 username；只在连接串显式提供时透传。
            kwargs["username"] = unquote(parsed.username)
        if parsed.scheme == "rediss":
            # TLS 连接串需要把 ssl 标记透传给 redis-py，AgentScope 会在 lifespan 中创建连接池。
            kwargs["ssl"] = True
        return kwargs

    return {
        "host": settings.AGENTSCOPE_REDIS_HOST,
        "port": settings.AGENTSCOPE_REDIS_PORT,
        "db": settings.AGENTSCOPE_REDIS_DB,
        "password": settings.AGENTSCOPE_REDIS_PASSWORD,
    }


def create_embedded_agentscope_app(settings: Settings) -> FastAPI:
    """创建可挂载到 Datalogue 主应用下的官方 AgentScope Service 子应用。"""

    redis_kwargs = _redis_kwargs(settings)
    storage = RedisStorage(**redis_kwargs)
    message_bus = RedisMessageBus(**redis_kwargs)
    workspace_manager = LocalWorkspaceManager(
        basedir=settings.AGENTSCOPE_WORKSPACE_BASEDIR,
        ttl=settings.AGENTSCOPE_WORKSPACE_TTL_SECONDS,
    )

    return agentscope_create_app(
        storage=storage,
        message_bus=message_bus,
        workspace_manager=workspace_manager,
        extra_agent_tools=build_datalogue_extra_agent_tools(),
    )
