# ============================================================
# File Name   : test_message_feedback_authorization.py
# Description:
#   消息反馈资源归属校验回归测试。
#
# Responsibilities:
#   - 验证登录用户不能对其他用户会话中的消息提交反馈。
#
# Author      : yangkai
# Created On  : 2026-07-17
# ============================================================

from app.api.deps import require_api_user
from app.core import models


def test_message_feedback_rejects_foreign_conversation_message(client, db_session):
    foreign_conversation = models.Conversation(
        title="他人会话",
        user_id=3,
        archived=False,
    )
    db_session.add(foreign_conversation)
    db_session.flush()
    foreign_message = models.Message(
        conversation_id=foreign_conversation.id,
        role="assistant",
        content="他人的回答",
    )
    db_session.add(foreign_message)
    db_session.commit()
    normal_user = models.User(
        id=2,
        username="feedback-owner",
        role="user",
        is_superuser=False,
        is_active=True,
    )
    client.app.dependency_overrides[require_api_user] = lambda: normal_user

    response = client.post(
        f"/api/messages/{foreign_message.id}/feedback",
        json={"message_id": foreign_message.id, "action": "approve"},
    )

    assert response.status_code == 404
