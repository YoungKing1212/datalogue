# ============================================================
# File Name   : progress_bridge.py
# Description:
#   AgentScope Worker 到 Datalogue SSE 的实时进度桥。
#
# Responsibilities:
#   - 在嵌入式 AgentScope Service 场景下按 user_id 注册实时进度订阅。
#   - 接收 AgentScope middleware / Datalogue 安全工具发布的用户可见事件。
#   - 为 runner 合流 Lead Agent session stream 与 Worker 进度提供轻量队列。
#
# Author      : yangkai
# Created On  : 2026-07-05
# ============================================================

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)

_SUBSCRIPTIONS: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)


@asynccontextmanager
async def agent_progress_subscription(
    *,
    user_id: str,
    max_events: int = 100,
) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
    """注册当前 Datalogue runner 对某个 AgentScope user 的实时进度订阅。"""

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_events)
    _SUBSCRIPTIONS[user_id].append(queue)
    try:
        yield queue
    finally:
        subscriptions = _SUBSCRIPTIONS.get(user_id) or []
        if queue in subscriptions:
            subscriptions.remove(queue)
        if not subscriptions:
            _SUBSCRIPTIONS.pop(user_id, None)


def publish_agent_progress(*, user_id: str | None, payload: dict[str, Any]) -> int:
    """把 middleware 侧安全进度发布给当前活动 runner；返回成功投递的订阅数。"""

    return publish_agent_event(user_id=user_id, event_type="agent.progress", payload=payload)


def publish_agent_event(*, user_id: str | None, event_type: str, payload: dict[str, Any]) -> int:
    """把 AgentScope worker 侧安全事件发布给当前活动 runner；payload 必须已完成业务脱敏。"""

    if not user_id:
        return 0
    event = {"event_type": event_type, "payload": payload}
    delivered = 0
    for queue in list(_SUBSCRIPTIONS.get(user_id) or []):
        try:
            queue.put_nowait(event)
            delivered += 1
        except asyncio.QueueFull:
            # 实时进度是辅助 UI，不允许反压阻塞 AgentScope worker；队列满时丢弃并记录。
            logger.warning("agent_progress_queue_full user_id=%s", user_id)
    return delivered
