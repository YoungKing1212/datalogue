# ============================================================
# File Name   : artifact_store.py
# Description:
#   查询执行领域的查询产物持久化服务。
#
# Responsibilities:
#   - 将 SQL 结果、报告和 SubAgent 完成态保存为轻量引用。
#   - 按 TTL 清理过期产物，避免多轮状态和消息 metadata 承载大结果。
#   - 对 artifact payload 做大小护栏，失败时 fail-closed。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import QueryArtifact

ArtifactKind = Literal["sql_result", "report", "subagent_result", "repair_plan"]


class ArtifactPayloadTooLargeError(ValueError):
    """artifact payload 超过单条存储预算。"""

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(f"query artifact payload too large: {size_bytes}>{max_bytes}")
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


class ArtifactStore:
    """基于数据库表的查询产物存储，v1 不引入外部对象存储。"""

    _last_cleanup_monotonic: float = 0.0

    def __init__(
        self,
        db: Session,
        *,
        ttl_seconds: int | None = None,
        max_bytes: int | None = None,
        cleanup_interval_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self.db = db
        self.ttl_seconds = int(
            ttl_seconds
            if ttl_seconds is not None
            else getattr(settings, "QUERY_ARTIFACT_TTL_SECONDS", 7 * 24 * 60 * 60)
        )
        self.max_bytes = int(
            max_bytes
            if max_bytes is not None
            else getattr(settings, "QUERY_ARTIFACT_MAX_BYTES", 2 * 1024 * 1024)
        )
        self.cleanup_interval_seconds = int(
            cleanup_interval_seconds
            if cleanup_interval_seconds is not None
            else getattr(settings, "QUERY_ARTIFACT_CLEANUP_INTERVAL_SECONDS", 300)
        )

    def put_json(
        self,
        *,
        kind: ArtifactKind,
        payload: Any,
        dataset_id: int | None = None,
        conversation_id: int | None = None,
        message_id: int | None = None,
        trace_id: str | None = None,
    ) -> str:
        encoded = jsonable_encoder(payload)
        size_bytes = self._json_size(encoded)
        self._ensure_size(size_bytes)
        return self._insert(
            kind=kind,
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            message_id=message_id,
            trace_id=trace_id,
            content_json=encoded,
            content_text=None,
            content_mime="application/json",
            size_bytes=size_bytes,
        )

    def put_text(
        self,
        *,
        kind: ArtifactKind,
        text: str,
        dataset_id: int | None = None,
        conversation_id: int | None = None,
        message_id: int | None = None,
        trace_id: str | None = None,
        content_mime: str = "text/plain",
    ) -> str:
        value = str(text or "")
        size_bytes = len(value.encode("utf-8"))
        self._ensure_size(size_bytes)
        return self._insert(
            kind=kind,
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            message_id=message_id,
            trace_id=trace_id,
            content_json=None,
            content_text=value,
            content_mime=content_mime,
            size_bytes=size_bytes,
        )

    def get(self, artifact_ref: str) -> QueryArtifact | None:
        if not artifact_ref:
            return None
        artifact = (
            self.db.query(QueryArtifact)
            .filter(QueryArtifact.artifact_id == artifact_ref)
            .one_or_none()
        )
        if artifact is None:
            return None
        if artifact.expires_at.tzinfo is None:
            artifact.expires_at = artifact.expires_at.replace(tzinfo=UTC)
        if artifact.expires_at <= datetime.now(UTC):
            return None
        return artifact

    def attach_message_id(self, artifact_refs: list[str | None], *, message_id: int) -> int:
        """把已落库消息 id 回填到 artifact，便于按消息追踪产物。"""

        refs = [ref for ref in artifact_refs if isinstance(ref, str) and ref.startswith("artifact:")]
        if not refs:
            return 0
        rows = (
            self.db.query(QueryArtifact)
            .filter(QueryArtifact.artifact_id.in_(refs))
            .all()
        )
        for row in rows:
            row.message_id = message_id
            self.db.add(row)
        if rows:
            self.db.flush()
        return len(rows)

    def purge_expired(
        self,
        *,
        now: datetime | None = None,
        batch_size: int | None = None,
    ) -> int:
        cutoff = now or datetime.now(UTC)
        limit = int(
            batch_size
            if batch_size is not None
            else getattr(get_settings(), "QUERY_ARTIFACT_CLEANUP_BATCH_SIZE", 500)
        )
        rows = (
            self.db.query(QueryArtifact)
            .filter(QueryArtifact.expires_at <= cutoff)
            .order_by(QueryArtifact.expires_at.asc())
            .limit(limit)
            .all()
        )
        for row in rows:
            self.db.delete(row)
        if rows:
            self.db.flush()
        return len(rows)

    def _insert(
        self,
        *,
        kind: ArtifactKind,
        dataset_id: int | None,
        conversation_id: int | None,
        message_id: int | None,
        trace_id: str | None,
        content_json: Any | None,
        content_text: str | None,
        content_mime: str,
        size_bytes: int,
    ) -> str:
        self._maybe_purge_expired()
        artifact_ref = f"artifact:{uuid4().hex}"
        artifact = QueryArtifact(
            artifact_id=artifact_ref,
            kind=kind,
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            message_id=message_id,
            trace_id=trace_id,
            content_json=content_json,
            content_text=content_text,
            content_mime=content_mime,
            size_bytes=size_bytes,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
        )
        self.db.add(artifact)
        self.db.flush()
        return artifact_ref

    def _maybe_purge_expired(self) -> None:
        if self.cleanup_interval_seconds <= 0:
            return
        current = time.monotonic()
        if current - self._last_cleanup_monotonic < self.cleanup_interval_seconds:
            return
        self.__class__._last_cleanup_monotonic = current
        self.purge_expired()

    def _ensure_size(self, size_bytes: int) -> None:
        if size_bytes > self.max_bytes:
            raise ArtifactPayloadTooLargeError(size_bytes, self.max_bytes)

    @staticmethod
    def _json_size(payload: Any) -> int:
        return len(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        )
