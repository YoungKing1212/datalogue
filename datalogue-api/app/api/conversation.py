# ============================================================
# File Name   : conversation.py
# Description:
#   会话管理 API 端点。
#
# Responsibilities:
#   - 创建、列出、重命名、归档和删除会话。
#   - 为 assistant-ui 线程提供持久化消息历史。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services.observability.tracer import build_langfuse_trace_url
from app import schemas, models

router = APIRouter()


def _with_observability_links(message: models.Message) -> models.Message:
    """为历史消息动态补齐 Langfuse trace 深链，不回写数据库。"""

    metadata = dict(message.response_metadata or {})
    langfuse = dict(metadata.get("langfuse") or {})
    trace_id = langfuse.get("trace_id")
    if not trace_id:
        return message

    settings = get_settings()
    base_url = (
        langfuse.get("base_url")
        or metadata.get("observability", {}).get("base_url")
        or settings.LANGFUSE_BASE_URL
        or settings.LANGFUSE_HOST
    )
    project_id = (
        langfuse.get("project_id")
        or metadata.get("observability", {}).get("project_id")
        or settings.LANGFUSE_PROJECT_ID
    )
    trace_url = (
        langfuse.get("trace_url")
        or metadata.get("observability", {}).get("trace_url")
        or build_langfuse_trace_url(
            base_url=base_url,
            project_id=project_id,
            trace_id=trace_id,
        )
    )
    langfuse.update({
        "base_url": base_url,
        "project_id": project_id,
        "trace_url": trace_url,
    })
    metadata["langfuse"] = langfuse
    observability = dict(metadata.get("observability") or {})
    observability.update({
        "base_url": base_url,
        "project_id": project_id,
        "trace_url": trace_url,
        "environment": observability.get("environment") or langfuse.get("environment"),
        "release": observability.get("release") or langfuse.get("release"),
        "prompt_label": observability.get("prompt_label") or langfuse.get("prompt_label"),
    })
    metadata["observability"] = observability
    message.response_metadata = metadata
    return message


@router.get("", response_model=List[schemas.ConversationOut])
def list_conversations(
    archived: bool = Query(default=False, description="true 取归档列表，false 取常规列表"),
    db: Session = Depends(get_db),
):
    """列出对话，默认仅返回未归档。"""
    return (
        db.query(models.Conversation)
        .filter(models.Conversation.archived == archived)
        .order_by(models.Conversation.updated_at.desc())
        .all()
    )


@router.post("", response_model=schemas.ConversationOut, status_code=201)
def create_conversation(payload: schemas.ConversationCreate, db: Session = Depends(get_db)):
    """创建空会话（assistant-ui initialize 流程使用，title 缺省为「新对话」）。"""
    import uuid

    conv = models.Conversation(
        title=payload.title,
        thread_id=payload.thread_id or f"thread-{uuid.uuid4().hex[:12]}",
        user_id=1,
        dataset_id=payload.dataset_id,
        archived=False,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/{conv_id}", response_model=schemas.ConversationDetailOut)
def get_conversation(conv_id: int, db: Session = Depends(get_db)):
    conv = db.get(models.Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    messages = (
        db.query(models.Message)
        .filter(models.Message.conversation_id == conv_id)
        .order_by(models.Message.created_at)
        .all()
    )
    messages = [_with_observability_links(message) for message in messages]
    return {"conversation": conv, "messages": messages}


@router.patch("/{conv_id}", response_model=schemas.ConversationOut)
def rename_conversation(
    conv_id: int,
    payload: schemas.ConversationRename,
    db: Session = Depends(get_db),
):
    """重命名对话。"""
    conv = db.get(models.Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    conv.title = payload.title
    db.commit()
    db.refresh(conv)
    return conv


@router.post("/{conv_id}/archive", response_model=schemas.ConversationOut)
def archive_conversation(conv_id: int, db: Session = Depends(get_db)):
    """归档对话。"""
    conv = db.get(models.Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    conv.archived = True
    db.commit()
    db.refresh(conv)
    return conv


@router.post("/{conv_id}/unarchive", response_model=schemas.ConversationOut)
def unarchive_conversation(conv_id: int, db: Session = Depends(get_db)):
    """取消归档。"""
    conv = db.get(models.Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    conv.archived = False
    db.commit()
    db.refresh(conv)
    return conv


@router.delete("/{conv_id}")
def delete_conversation(conv_id: int, db: Session = Depends(get_db)):
    conv = db.get(models.Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    db.query(models.Message).filter(models.Message.conversation_id == conv_id).delete()
    db.delete(conv)
    db.commit()
    return {"ok": True}
