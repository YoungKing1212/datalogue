# ============================================================
# File Name   : artifacts.py
# Description:
#   查询产物按需读取 API。
#
# Responsibilities:
#   - 按 artifact:<uuid> 引用读取 SQL 结果、报告和 SubAgent 产物。
#   - 对缺失和过期 artifact fail-closed 返回 404。
#   - 避免聊天 final payload 自动携带大结果。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.artifact_store import ArtifactStore

router = APIRouter()


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    value = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)


@router.get("/{artifact_ref}")
def get_artifact(artifact_ref: str, db: Session = Depends(get_db)):
    """按需读取 artifact 内容；过期或不存在统一 404。"""

    if not artifact_ref.startswith("artifact:"):
        raise HTTPException(status_code=404, detail="artifact not found")
    artifact = ArtifactStore(db).get(artifact_ref)
    if artifact is None or _is_expired(artifact.expires_at):
        raise HTTPException(status_code=404, detail="artifact not found")
    return jsonable_encoder(
        {
            "artifact_ref": artifact.artifact_id,
            "kind": artifact.kind,
            "dataset_id": artifact.dataset_id,
            "conversation_id": artifact.conversation_id,
            "message_id": artifact.message_id,
            "content_mime": artifact.content_mime,
            "content_json": artifact.content_json,
            "content_text": artifact.content_text,
            "expires_at": artifact.expires_at,
        }
    )
