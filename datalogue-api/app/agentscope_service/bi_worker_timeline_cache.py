# ============================================================
# File Name   : bi_worker_timeline_cache.py
# Description:
#   BI Worker 原始 reply timeline 的 Redis 临时调试缓存。
#
#   TODO(后期删除): 本模块为临时调试观测手段，BI Worker 的完整模型调用观测
#   后续统一交给 AgentScope TracingMiddleware / OpenTelemetry；在该能力落地后
#   删除本缓存及其写入点（见 worker_logging.py 的 _cache_bi_worker_timeline_if_enabled）。
#
#   - 复用 AgentScope RedisStorage 底层 Redis 客户端，与 task_context 共享连接池。
#   - 写入受 raw_agent_logs_enabled() 开关控制（调用方判断），默认关闭，避免生产
#     写入含 SQL/表结构/原始思维链的 raw 内容。
#   - 依赖 TTL 自动过期，无需手动清理。
#
# Author      : yangkai
# Created On  : 2026-07-07
# ============================================================

from __future__ import annotations

import json
import logging
from typing import Any

from agentscope.app.storage import StorageBase
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# TODO(后期删除): 与 task_context 同前缀命名空间，便于统一清理。
_TIMELINE_KEY_PREFIX = "datalogue:bi_worker_timeline"
_DEFAULT_TTL_SECONDS = 3600  # 1 小时，与 task_context 一致


def _timeline_key(worker_session_id: str, reply_id: str) -> str:
    return f"{_TIMELINE_KEY_PREFIX}:{worker_session_id}:{reply_id}"


def _storage_redis_client(storage: StorageBase) -> Redis | None:
    """从 AgentScope StorageBase 获取底层 Redis 客户端。

    TODO(后期删除): 与 task_context._storage_redis_client 重复，提取前先就地复制；
    复用 RedisStorage.get_client()，duck-typing 检测 get 方法以兼容测试 mock。
    """
    get_client = getattr(storage, "get_client", None)
    if not callable(get_client):
        return None
    try:
        client = get_client()
    except Exception:
        logger.debug("Failed to get Redis client from storage", exc_info=True)
        return None
    if callable(getattr(client, "get", None)):
        return client  # type: ignore[no-any-return]
    return None


async def store_bi_worker_timeline(
    storage: StorageBase,
    *,
    worker_session_id: str,
    reply_id: str,
    timeline: list[dict[str, Any]],
    ttl: int = _DEFAULT_TTL_SECONDS,
) -> None:
    """TODO(后期删除): 将 BI worker 单次 reply 的原始 timeline 暂存 Redis，供调试排查。

    写入受 raw_agent_logs_enabled() 控制（由调用方判断）；TTL 自动过期，无需手动清理。
    任何 Redis 异常都降级为 debug 日志，绝不影响 worker 主链。

    Args:
        storage: AgentScope StorageBase（RedisStorage），用于获取底层 Redis 客户端。
        worker_session_id: BI worker 的 session_id，作为 key 主体。
        reply_id: 本次 reply 的 msg.id，区分同一 session 的多次 reply。
        timeline: _raw_debug_blocks_from_msg 生成的原始块序列。
        ttl: 缓存过期秒数，默认 1 小时。
    """
    redis_client = _storage_redis_client(storage)
    if redis_client is None:
        return
    key = _timeline_key(worker_session_id, reply_id)
    payload = {
        "worker_session_id": worker_session_id,
        "reply_id": reply_id,
        "timeline": timeline,
    }
    try:
        await redis_client.set(key, json.dumps(payload, ensure_ascii=False), ex=ttl)
        logger.debug("Stored bi_worker timeline in Redis: key=%s", key)
    except Exception:
        logger.debug("Failed to store bi_worker timeline key=%s", key, exc_info=True)


async def read_bi_worker_timeline(
    storage: StorageBase,
    *,
    worker_session_id: str,
    reply_id: str,
) -> list[dict[str, Any]]:
    """TODO(后期删除): 从 Redis 读取 BI worker 单次 reply 的 timeline；缺失或异常返回空列表。

    供后续调试接口或排查工具消费；本模块删除时一并移除。
    """
    redis_client = _storage_redis_client(storage)
    if redis_client is None:
        return []
    key = _timeline_key(worker_session_id, reply_id)
    try:
        raw = await redis_client.get(key)
    except Exception:
        logger.debug("Redis read failed for key=%s", key, exc_info=True)
        return []
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    timeline = data.get("timeline") if isinstance(data, dict) else None
    return list(timeline) if isinstance(timeline, list) else []
