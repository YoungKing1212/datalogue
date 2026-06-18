# ============================================================
# File Name   : test_query_artifact_store.py
# Description:
#   QueryArtifact 持久化与 TTL 清理测试。
#
# Responsibilities:
#   - 验证 SubAgent 大结果可以写入 artifact 引用。
#   - 验证过期 artifact 会按 TTL 清理。
#   - 验证超大 payload 被拒绝，避免污染会话状态。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models import QueryArtifact
from app.services.artifact_store import (
    ArtifactPayloadTooLargeError,
    ArtifactStore,
)


def test_put_json_and_get_roundtrip(db_session):
    store = ArtifactStore(
        db_session,
        ttl_seconds=60,
        max_bytes=2048,
        cleanup_interval_seconds=3600,
    )

    ref = store.put_json(
        kind="sql_result",
        payload={"columns": ["name"], "rows": [{"name": "张三"}], "row_count": 1},
        dataset_id=10,
        conversation_id=20,
        trace_id="trace-1",
    )

    artifact = store.get(ref)

    assert ref.startswith("artifact:")
    assert artifact is not None
    assert artifact.kind == "sql_result"
    assert artifact.dataset_id == 10
    assert artifact.conversation_id == 20
    assert artifact.content_json["row_count"] == 1
    assert artifact.expires_at > datetime.now(UTC)


def test_purge_expired_deletes_only_expired_artifacts(db_session):
    store = ArtifactStore(db_session, ttl_seconds=60, cleanup_interval_seconds=3600)
    expired = QueryArtifact(
        artifact_id="artifact:expired",
        kind="report",
        content_text="old",
        size_bytes=3,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    active = QueryArtifact(
        artifact_id="artifact:active",
        kind="report",
        content_text="new",
        size_bytes=3,
        expires_at=datetime.now(UTC) + timedelta(seconds=60),
    )
    db_session.add_all([expired, active])
    db_session.commit()

    deleted = store.purge_expired(now=datetime.now(UTC), batch_size=100)

    assert deleted == 1
    assert store.get("artifact:expired") is None
    assert store.get("artifact:active") is not None


def test_put_json_rejects_payload_over_size_limit(db_session):
    store = ArtifactStore(db_session, ttl_seconds=60, max_bytes=20)

    with pytest.raises(ArtifactPayloadTooLargeError):
        store.put_json(kind="subagent_result", payload={"large": "x" * 100})
