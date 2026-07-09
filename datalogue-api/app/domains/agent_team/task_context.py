# ============================================================
# File Name   : task_context.py
# Description:
#   Datalogue 侧 Redis 存储 task context + AgentScope TeamRecord 反查逻辑。
#
#   由于 AgentScope Service 调用链是 REST/HTTP（跨进程），无法使用
#   ContextVar 传递 task 上下文。本模块提供两阶段方案：
#
#   1. Datalogue Runner 在创建 leader session 后，将 task context 写入
#      Redis（keyed by leader session_id）。
#   2. Worker 中间件通过 AgentScope TeamRecord 反查 leader session，
#      再从 Redis 读取 task context 合并到 worker_context。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis

from agentscope.app.storage import StorageBase

logger = logging.getLogger(__name__)

# Datalogue 侧 Redis key 前缀，与 AgentScope 内置 key 命名空间隔离。
_TASK_CONTEXT_KEY_PREFIX = "datalogue:task_context"
_DEFAULT_TTL_SECONDS = 3600  # 1 小时


def _task_context_key(leader_session_id: str) -> str:
    return f"{_TASK_CONTEXT_KEY_PREFIX}:{leader_session_id}"


async def store_task_context(
    redis_client: Redis,
    *,
    leader_session_id: str,
    task_id: str,
    thread_id: str | None = None,
    message_id: str | None = None,
    trace_id: str | None = None,
    ttl: int = _DEFAULT_TTL_SECONDS,
) -> None:
    """Datalogue Runner 侧：将 task context 写入 Redis。

    写入时机：create_session() 返回 service_session_id 之后、trigger_chat() 之前。
    依赖 TTL 自动过期，无需手动清理。
    """
    payload: dict[str, Any] = {
        "task_id": task_id,
        "thread_id": thread_id,
        "message_id": message_id,
        "trace_id": trace_id,
        "leader_session_id": leader_session_id,
    }
    key = _task_context_key(leader_session_id)
    await redis_client.set(key, json.dumps(payload, ensure_ascii=False), ex=ttl)
    logger.debug("Stored task context in Redis: key=%s task_id=%s", key, task_id)


async def resolve_task_context(
    storage: StorageBase,
    *,
    user_id: str | None,
    agent_id: str | None,
    session_id: str | None,
) -> dict[str, str | None]:
    """Worker 中间件侧：解析 task context。

    解析策略（按优先级）：
    1. 直接用 session_id 查 Redis（leader agent 场景）。
    2. 通过 AgentScope TeamRecord 反查 leader session_id 再查 Redis。
    3. 都失败返回空 dict，不影响中间件正常工作。

    Returns:
        dict with keys: task_id, thread_id, message_id, trace_id, leader_session_id。
        所有值可能为 None。
    """
    if not user_id or not agent_id or not session_id:
        return {}

    # 获取 AgentScope 内部的 Redis 客户端用于读取。
    redis_client = _storage_redis_client(storage)
    if redis_client is None:
        return {}

    # 策略 1：直接命中（leader agent 的 session_id == leader_session_id）。
    ctx = await _read_task_context(redis_client, session_id)
    if ctx:
        return ctx

    # 策略 2：通过 TeamRecord 反查。
    try:
        teams = await storage.list_teams(user_id)
    except Exception:
        logger.debug("Failed to list teams for user_id=%s", user_id, exc_info=True)
        return {}

    for team in teams:
        if agent_id not in team.data.member_ids:
            continue
        leader_sid = team.session_id
        if leader_sid:
            ctx = await _read_task_context(redis_client, leader_sid)
            if ctx:
                return ctx

    return {}


def _storage_redis_client(storage: StorageBase) -> Redis | None:
    """从 AgentScope StorageBase 获取底层 Redis 客户端。

    AgentScope RedisStorage 通过 get_client() 暴露内部的 aioredis.Redis 实例。
    使用 duck-typing（检测 get/coro 方法）而非 isinstance 以支持测试 mock。
    """
    get_client = getattr(storage, "get_client", None)
    if not callable(get_client):
        return None
    try:
        client = get_client()
    except Exception:
        logger.debug("Failed to get Redis client from storage", exc_info=True)
        return None
    # duck-typing：只要对象有 async-capable get 方法即可。
    if callable(getattr(client, "get", None)):
        return client  # type: ignore[return-value]
    return None


async def _read_task_context(redis_client: Redis, session_id: str) -> dict[str, str | None]:
    """从 Redis 读取单个 session 对应的 task context。"""
    try:
        raw = await redis_client.get(_task_context_key(session_id))
    except Exception:
        logger.debug("Redis read failed for key=%s", _task_context_key(session_id), exc_info=True)
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return {
        "task_id": data.get("task_id"),
        "thread_id": data.get("thread_id"),
        "message_id": data.get("message_id"),
        "trace_id": data.get("trace_id"),
        "leader_session_id": data.get("leader_session_id"),
    }
