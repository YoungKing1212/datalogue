# ============================================================
# File Name   : navigation.py
# Description:
#   侧栏导航统计 API。
#
# Responsibilities:
#   - 为前端左侧功能栏提供数据库真实数量。
#   - 对没有持久化真相源的功能项返回空值，避免前端显示演示假数字。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core import models
from app.core.database import get_db

router = APIRouter()


def _count(db: Session, model) -> int:
    """统一封装 count，后续切换到更复杂的筛选口径时只改调用点。"""

    return db.query(model).count()


@router.get("/counts")
def get_navigation_counts(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    """返回左侧功能栏 badge 所需的真实数据数量。"""

    knowledge_count = (
        _count(db, models.BusinessTerm)
        + _count(db, models.AnalysisBlueprint)
    )
    review_count = (
        db.query(models.SemanticValidationCase)
        .filter(models.SemanticValidationCase.status != "passed")
        .count()
    )
    history_count = (
        db.query(models.Conversation)
        .filter(models.Conversation.archived == False)  # noqa: E712 - 与会话列表 API 的未归档口径保持一致。
        .count()
    )

    return {
        "dashboard": _count(db, models.AgentTeamTask),
        "history": history_count,
        "datasets": _count(db, models.SemanticDataset),
        "knowledge": knowledge_count,
        "review": review_count,
        "datasources": _count(db, models.Datasource),
        # API 发布当前仍是前端演示页，尚无持久化接口表；返回 None 表示不展示数量。
        "apis": None,
    }
