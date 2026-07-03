# ============================================================
# File Name   : test_conversation.py
# Description:
#   会话 API 行为测试。
#
# Responsibilities:
#   - 验证会话创建、更新、归档和删除。
#   - 验证消息持久化和排序逻辑。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""
对话管理 API 测试
"""

import pytest


class TestConversationAPI:
    """测试 /api/conversation 路由"""

    def test_list_conversations_empty(self, client):
        """空对话列表"""
        resp = client.get("/api/conversation")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_conversations_orders_newest_first(self, client):
        """最近对话按最新会话排在顶部。"""
        first = client.post("/api/conversation", json={"title": "第一条"}).json()
        second = client.post("/api/conversation", json={"title": "第二条"}).json()

        resp = client.get("/api/conversation")

        assert resp.status_code == 200
        data = resp.json()
        assert [item["id"] for item in data[:2]] == [second["id"], first["id"]]

    def test_get_conversation_not_found(self, client):
        """获取不存在的对话"""
        resp = client.get("/api/conversation/99999")
        assert resp.status_code == 404

    def test_delete_conversation_not_found(self, client):
        """删除不存在的对话"""
        resp = client.delete("/api/conversation/99999")
        assert resp.status_code == 404

    def test_legacy_chat_stream_does_not_create_conversation(self, client, sample_dataset):
        """旧 chat stream HTTP 入口下线后，不应再承担创建对话的副作用。"""
        payload = {
            "question": "测试问题",
            "dataset_id": sample_dataset.id,
        }

        resp = client.post("/api/chat/stream", json=payload)
        convs = client.get("/api/conversation").json()

        assert resp.status_code == 404
        assert convs == []

    def test_conversation_detail_structure(self, client, sample_dataset, monkeypatch):
        """验证对话详情返回结构"""
        # 创建对话
        from app.models.conversation import Conversation, Message
        from app.core.config import Settings

        monkeypatch.setattr(
            "app.api.conversation.get_settings",
            lambda: Settings(
                LANGFUSE_BASE_URL="http://localhost:3000",
                LANGFUSE_PROJECT_ID="project-test",
            ),
        )

        # 使用 override 的 db_session
        db = None
        for dep in client.app.dependency_overrides.values():
            # 找到 generator
            try:
                gen = dep()
                db = next(gen)
                break
            except Exception:
                continue

        if db is None:
            pytest.skip("无法获取测试数据库 session")

        conv = Conversation(
            title="测试对话",
            thread_id="t-001",
            user_id=1,
            dataset_id=sample_dataset.id,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        msg1 = Message(conversation_id=conv.id, role="user", content="你好")
        msg2 = Message(
            conversation_id=conv.id,
            role="assistant",
            content="你好！",
            response_metadata={
                "answer_explanation": {
                    "confidence": {"level": "high", "score": 0.92},
                },
                "langfuse": {"trace_id": "trace-test", "session_id": "session-test"},
            },
        )
        db.add(msg1)
        db.add(msg2)
        db.commit()

        resp = client.get(f"/api/conversation/{conv.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "conversation" in data
        assert "messages" in data
        assert data["conversation"]["title"] == "测试对话"
        assert data["conversation"]["dataset_id"] == sample_dataset.id
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"
        assert data["messages"][1]["response_metadata"]["answer_explanation"]["confidence"][
            "level"
        ] == "high"
        assert (
            data["messages"][1]["response_metadata"]["langfuse"]["trace_url"]
            == "http://localhost:3000/project/project-test/traces/trace-test"
        )
        assert (
            data["messages"][1]["response_metadata"]["observability"]["trace_url"]
            == "http://localhost:3000/project/project-test/traces/trace-test"
        )
