# ============================================================
# File Name   : progress_bridge.py
# Description:
#   AgentScope Worker 到 Datalogue SSE 的实时进度桥。
#
# Responsibilities:
#   - 在嵌入式 AgentScope Service 场景下按 leader_session_id 注册实时进度订阅。
#   - 接收 AgentScope middleware / Datalogue 安全工具发布的用户可见事件。
#   - 为 runner 合流 Lead Agent session stream 与 Worker 进度提供轻量队列。
#
# Author      : yangkai
# Created On  : 2026-07-05
# ============================================================

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SUBSCRIPTIONS: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
_SUBSCRIPTION_LOOPS: dict[int, asyncio.AbstractEventLoop] = {}
_CHANNEL_PREFIX = "datalogue:agent-progress:"


def _redis_url() -> str | None:
    settings = get_settings()
    if settings.AGENTSCOPE_REDIS_URL:
        return settings.AGENTSCOPE_REDIS_URL
    password = (
        f":{settings.AGENTSCOPE_REDIS_PASSWORD}@" if settings.AGENTSCOPE_REDIS_PASSWORD else ""
    )
    return (
        f"redis://{password}{settings.AGENTSCOPE_REDIS_HOST}:"
        f"{settings.AGENTSCOPE_REDIS_PORT}/{settings.AGENTSCOPE_REDIS_DB}"
    )


def _channel(leader_session_id: str) -> str:
    return f"{_CHANNEL_PREFIX}{leader_session_id}"


async def _forward_redis_events(
    *,
    leader_session_id: str,
    queue: asyncio.Queue[dict[str, Any]],
    ready: asyncio.Event,
) -> None:
    """把 Redis pub/sub 帧转入当前 runner 队列，支撑 Service 与 API 分进程部署。"""

    redis_url = _redis_url()
    if not redis_url:
        ready.set()
        return
    client = AsyncRedis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=1.0,
    )
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    try:
        await pubsub.subscribe(_channel(leader_session_id))
        ready.set()
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                event = json.loads(str(message.get("data") or "{}"))
            except (TypeError, ValueError):
                logger.warning(
                    "agent_progress_redis_invalid_event leader_session_id=%s", leader_session_id
                )
                continue
            if event.get("leader_session_id") != leader_session_id:
                continue
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("agent_progress_queue_full leader_session_id=%s", leader_session_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        ready.set()
        logger.warning(
            "agent_progress_redis_subscription_failed leader_session_id=%s",
            leader_session_id,
            exc_info=True,
        )
    finally:
        await pubsub.aclose()
        await client.aclose()


@asynccontextmanager
async def agent_progress_subscription(
    *,
    leader_session_id: str,
    max_events: int = 100,
) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
    """注册当前 Datalogue runner 对单个 leader session 的实时进度订阅。"""

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_events)
    _SUBSCRIPTIONS[leader_session_id].append(queue)
    _SUBSCRIPTION_LOOPS[id(queue)] = asyncio.get_running_loop()
    redis_ready = asyncio.Event()
    redis_forwarder = asyncio.create_task(
        _forward_redis_events(
            leader_session_id=leader_session_id,
            queue=queue,
            ready=redis_ready,
        )
    )
    try:
        # 跨进程发布前尽量完成订阅；Redis 不可用时短暂等待后降级到进程内队列并显式告警。
        try:
            await asyncio.wait_for(redis_ready.wait(), timeout=0.75)
        except TimeoutError:
            logger.warning(
                "agent_progress_redis_subscription_timeout leader_session_id=%s", leader_session_id
            )
        yield queue
    finally:
        redis_forwarder.cancel()
        try:
            await redis_forwarder
        except asyncio.CancelledError:
            pass
        subscriptions = _SUBSCRIPTIONS.get(leader_session_id) or []
        if queue in subscriptions:
            subscriptions.remove(queue)
        _SUBSCRIPTION_LOOPS.pop(id(queue), None)
        if not subscriptions:
            _SUBSCRIPTIONS.pop(leader_session_id, None)


def publish_agent_progress(*, leader_session_id: str | None, payload: dict[str, Any]) -> int:
    """把 middleware 侧安全进度发布给当前活动 runner；返回成功投递的订阅数。"""

    return publish_agent_event(
        leader_session_id=leader_session_id,
        event_type="agent.progress",
        payload=payload,
    )


def publish_agent_event(
    *,
    leader_session_id: str | None,
    event_type: str,
    payload: dict[str, Any],
) -> int:
    """把 AgentScope worker 侧安全事件发布给当前活动 runner；payload 必须已完成业务脱敏。"""

    if not leader_session_id:
        return 0
    # 路由键保留到 runner 合流边界做二次核验，投影给前端前会被剥离。
    event = {
        "event_id": f"progress_{uuid.uuid4().hex}",
        "leader_session_id": leader_session_id,
        "event_type": event_type,
        "payload": payload,
    }
    delivered = 0
    for queue in list(_SUBSCRIPTIONS.get(leader_session_id) or []):
        target_loop = _SUBSCRIPTION_LOOPS.get(id(queue))
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if target_loop is not None and target_loop is not current_loop:
            # Worker SQL 可能运行在线程池；跨线程只能让订阅所属事件循环安全唤醒队列。
            target_loop.call_soon_threadsafe(
                _put_local_event,
                queue,
                event,
                leader_session_id,
            )
            delivered += 1
            continue
        delivered += _put_local_event(queue, event, leader_session_id)
    if delivered:
        return delivered

    # 发布进程看不到本地订阅时写入 Redis；这正是 AgentScope Service 与 API 拆分部署的常态。
    redis_url = _redis_url()
    if not redis_url:
        logger.warning("agent_progress_no_transport leader_session_id=%s", leader_session_id)
        return 0
    try:
        asyncio.get_running_loop().run_in_executor(None, _publish_redis_event, redis_url, event)
        return 1  # 已提交到独立线程；真实失败会由发布 helper 记录，不能阻塞 AgentScope 事件循环。
    except RuntimeError:
        return _publish_redis_event(redis_url, event)


def _publish_redis_event(redis_url: str, event: dict[str, Any]) -> int:
    """在线程或同步上下文中执行 Redis 发布，避免阻塞 AgentScope 事件循环。"""

    leader_session_id = str(event.get("leader_session_id") or "")
    try:
        client = SyncRedis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=1.0,
        )
        try:
            return int(
                client.publish(_channel(leader_session_id), json.dumps(event, ensure_ascii=False))
            )
        finally:
            client.close()
    except Exception:
        logger.warning(
            "agent_progress_redis_publish_failed leader_session_id=%s",
            leader_session_id,
            exc_info=True,
        )
    return 0


def _put_local_event(
    queue: asyncio.Queue[dict[str, Any]],
    event: dict[str, Any],
    leader_session_id: str,
) -> int:
    """无阻塞投递本地事件；队列满只丢辅助进度，不反压业务任务。"""

    try:
        queue.put_nowait(event)
        return 1
    except asyncio.QueueFull:
        logger.warning("agent_progress_queue_full leader_session_id=%s", leader_session_id)
        return 0
