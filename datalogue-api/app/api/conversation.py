from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app import schemas, models

router = APIRouter()


@router.get("", response_model=List[schemas.ConversationOut])
def list_conversations(db: Session = Depends(get_db)):
    return db.query(models.Conversation).order_by(models.Conversation.updated_at.desc()).all()


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
    return {"conversation": conv, "messages": messages}


@router.delete("/{conv_id}")
def delete_conversation(conv_id: int, db: Session = Depends(get_db)):
    conv = db.get(models.Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    db.query(models.Message).filter(models.Message.conversation_id == conv_id).delete()
    db.delete(conv)
    db.commit()
    return {"ok": True}
