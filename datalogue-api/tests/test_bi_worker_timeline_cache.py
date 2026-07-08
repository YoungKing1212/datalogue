# ============================================================
# File Name   : test_bi_worker_timeline_cache.py
# Description:
#   BI Worker 原始 reply timeline Redis 临时调试缓存的单元测试。
#
#   TODO(后期删除): 随 bi_worker_timeline_cache 模块一同移除。
#
# Author      : yangkai
# Created On  : 2026-07-07
# ============================================================

from __future__ import annotations

import json

import pytest


class FakeRedis:
    """记录 set 调用、按 key 存取值的内存 Redis 替身。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int | None]] = []
        self.set_error: Exception | None = None
        self.get_error: Exception | None = None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        if self.set_error is not None:
            raise self.set_error
        self.set_calls.append((key, value, ex))
        self.store[key] = value

    async def get(self, key: str) -> str | None:
        if self.get_error is not None:
            raise self.get_error
        return self.store.get(key)


class FakeStorage:
    """暴露 get_client() 的 StorageBase 替身，命中 _storage_redis_client 的 duck-typing。"""

    def __init__(self, redis_client: object | None) -> None:
        self._client = redis_client

    def get_client(self) -> object | None:
        return self._client


class _NoClientStorage:
    """无 get_client 方法的 storage，用于 None 降级路径。"""


def test_timeline_key_uses_datalogue_namespace():
    from app.agentscope_service.bi_worker_timeline_cache import _timeline_key

    assert (
        _timeline_key("session-bi-1", "reply-1")
        == "datalogue:bi_worker_timeline:session-bi-1:reply-1"
    )


@pytest.mark.asyncio
async def test_store_bi_worker_timeline_writes_json_payload_with_ttl():
    from app.agentscope_service.bi_worker_timeline_cache import store_bi_worker_timeline

    fake_redis = FakeRedis()
    storage = FakeStorage(fake_redis)
    timeline = [{"step": 1, "type": "text", "text": "回答"}]

    await store_bi_worker_timeline(
        storage,
        worker_session_id="session-bi-1",
        reply_id="reply-1",
        timeline=timeline,
    )

    assert len(fake_redis.set_calls) == 1
    key, value, ex = fake_redis.set_calls[0]
    assert key == "datalogue:bi_worker_timeline:session-bi-1:reply-1"
    assert ex == 3600
    payload = json.loads(value)
    assert payload["worker_session_id"] == "session-bi-1"
    assert payload["reply_id"] == "reply-1"
    assert payload["timeline"] == timeline


@pytest.mark.asyncio
async def test_store_bi_worker_timeline_respects_custom_ttl():
    from app.agentscope_service.bi_worker_timeline_cache import store_bi_worker_timeline

    fake_redis = FakeRedis()
    await store_bi_worker_timeline(
        FakeStorage(fake_redis),
        worker_session_id="s",
        reply_id="r",
        timeline=[],
        ttl=120,
    )
    assert fake_redis.set_calls[0][2] == 120


@pytest.mark.asyncio
async def test_store_bi_worker_timeline_skips_when_storage_has_no_redis_client():
    from app.agentscope_service.bi_worker_timeline_cache import store_bi_worker_timeline

    # storage 无 get_client → 不抛异常、不写入。
    await store_bi_worker_timeline(
        _NoClientStorage(),  # type: ignore[arg-type]
        worker_session_id="s",
        reply_id="r",
        timeline=[{"step": 1}],
    )


@pytest.mark.asyncio
async def test_store_bi_worker_timeline_swallows_redis_errors():
    from app.agentscope_service.bi_worker_timeline_cache import store_bi_worker_timeline

    fake_redis = FakeRedis()
    fake_redis.set_error = RuntimeError("redis down")
    # Redis 异常降级为 debug 日志，不影响调用方。
    await store_bi_worker_timeline(
        FakeStorage(fake_redis),
        worker_session_id="s",
        reply_id="r",
        timeline=[{"step": 1}],
    )


@pytest.mark.asyncio
async def test_read_bi_worker_timeline_returns_stored_timeline():
    from app.agentscope_service.bi_worker_timeline_cache import (
        read_bi_worker_timeline,
        store_bi_worker_timeline,
    )

    fake_redis = FakeRedis()
    storage = FakeStorage(fake_redis)
    timeline = [{"step": 1, "type": "thinking", "thinking": "原始思考"}]
    await store_bi_worker_timeline(
        storage, worker_session_id="session-bi-1", reply_id="reply-1", timeline=timeline
    )

    result = await read_bi_worker_timeline(
        storage, worker_session_id="session-bi-1", reply_id="reply-1"
    )
    assert result == timeline


@pytest.mark.asyncio
async def test_read_bi_worker_timeline_returns_empty_when_missing():
    from app.agentscope_service.bi_worker_timeline_cache import read_bi_worker_timeline

    result = await read_bi_worker_timeline(
        FakeStorage(FakeRedis()), worker_session_id="s", reply_id="r"
    )
    assert result == []


@pytest.mark.asyncio
async def test_read_bi_worker_timeline_returns_empty_on_invalid_json():
    from app.agentscope_service.bi_worker_timeline_cache import read_bi_worker_timeline

    fake_redis = FakeRedis()
    fake_redis.store["datalogue:bi_worker_timeline:s:r"] = "not-json"
    result = await read_bi_worker_timeline(
        FakeStorage(fake_redis), worker_session_id="s", reply_id="r"
    )
    assert result == []


@pytest.mark.asyncio
async def test_read_bi_worker_timeline_returns_empty_when_payload_shape_unexpected():
    from app.agentscope_service.bi_worker_timeline_cache import read_bi_worker_timeline

    fake_redis = FakeRedis()
    # timeline 字段不是 list。
    fake_redis.store["datalogue:bi_worker_timeline:s:r"] = json.dumps({"timeline": "oops"})
    result = await read_bi_worker_timeline(
        FakeStorage(fake_redis), worker_session_id="s", reply_id="r"
    )
    assert result == []


@pytest.mark.asyncio
async def test_read_bi_worker_timeline_swallows_redis_errors():
    from app.agentscope_service.bi_worker_timeline_cache import read_bi_worker_timeline

    fake_redis = FakeRedis()
    fake_redis.get_error = RuntimeError("redis down")
    result = await read_bi_worker_timeline(
        FakeStorage(fake_redis), worker_session_id="s", reply_id="r"
    )
    assert result == []


@pytest.mark.asyncio
async def test_read_bi_worker_timeline_skips_when_storage_has_no_redis_client():
    from app.agentscope_service.bi_worker_timeline_cache import read_bi_worker_timeline

    result = await read_bi_worker_timeline(
        _NoClientStorage(),  # type: ignore[arg-type]
        worker_session_id="s",
        reply_id="r",
    )
    assert result == []
