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

import json

import pytest

from app.api.deps import require_api_user
from app.core import models


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

    def test_conversation_page_uses_opaque_cursor(self, client):
        """线程列表按 next_cursor 增量加载，且不会重复上一页会话。"""

        created = [
            client.post("/api/conversation", json={"title": f"会话 {index}"}).json()
            for index in range(3)
        ]

        first_page = client.get("/api/conversation/page?limit=2")
        assert first_page.status_code == 200
        first_data = first_page.json()
        assert [item["id"] for item in first_data["items"]] == [created[2]["id"], created[1]["id"]]
        assert first_data["next_cursor"]

        second_page = client.get(
            "/api/conversation/page",
            params={"limit": 2, "after": first_data["next_cursor"]},
        )
        assert second_page.status_code == 200
        second_data = second_page.json()
        assert [item["id"] for item in second_data["items"]] == [created[0]["id"]]
        assert second_data["next_cursor"] is None

    def test_conversation_page_rejects_invalid_cursor(self, client):
        response = client.get("/api/conversation/page?after=not-a-cursor")
        assert response.status_code == 400

    def test_get_conversation_not_found(self, client):
        """获取不存在的对话"""
        resp = client.get("/api/conversation/99999")
        assert resp.status_code == 404

    def test_delete_conversation_not_found(self, client):
        """删除不存在的对话"""
        resp = client.delete("/api/conversation/99999")
        assert resp.status_code == 404

    def test_conversation_endpoints_hide_other_users_resources(self, client, db_session):
        """顺序会话 ID 对其他登录用户统一不可见，也不能被修改。"""

        own = models.Conversation(title="我的会话", user_id=2, archived=False)
        other = models.Conversation(title="他人会话", user_id=3, archived=False)
        db_session.add_all([own, other])
        db_session.commit()
        normal_user = models.User(
            id=2,
            username="owner-user",
            role="user",
            is_superuser=False,
            is_active=True,
        )
        client.app.dependency_overrides[require_api_user] = lambda: normal_user

        listed = client.get("/api/conversation")
        foreign_get = client.get(f"/api/conversation/{other.id}")
        foreign_delete = client.delete(f"/api/conversation/{other.id}")

        assert [item["id"] for item in listed.json()] == [own.id]
        assert foreign_get.status_code == 404
        assert foreign_delete.status_code == 404

    def test_delete_conversation_cleans_agentscope_primary_storage(self, client, db_session):
        """删除会话时同步清理 AgentScope session/message/event/ref，避免孤儿数据。"""

        from app.services.runtime_mirror import (
            append_user_message,
            create_agentscope_session,
            record_agentscope_event,
            record_agentscope_ref,
        )

        conversation = client.post("/api/conversation", json={"title": "待删除"}).json()
        session = create_agentscope_session(
            db_session,
            thread_id="as_00000000-0000-0000-0000-000000000001",
            title="待删除",
            legacy_conversation_id=conversation["id"],
            metadata={"user_id": 1},
        )
        message = append_user_message(
            db_session,
            thread_id=session.thread_id,
            content_summary="敏感会话内容",
            payload={},
        )
        record_agentscope_event(
            db_session,
            thread_id=session.thread_id,
            message_id=message.message_id,
            event_type="task.started",
            payload={"summary": "开始"},
            visibility="user",
            task_id="task-delete",
            trace_id="trace-delete",
        )
        record_agentscope_ref(
            db_session,
            thread_id=session.thread_id,
            message_id=message.message_id,
            ref_type="checkpoint",
            ref_value="checkpoint://delete",
            relation="checkpoint",
        )
        deleted_thread_id = session.thread_id

        response = client.delete(f"/api/conversation/{conversation['id']}")

        assert response.status_code == 200
        assert db_session.query(models.AgentScopeSession).filter_by(thread_id=deleted_thread_id).count() == 0
        assert db_session.query(models.AgentScopeMessage).filter_by(thread_id=deleted_thread_id).count() == 0
        assert db_session.query(models.AgentScopeEvent).filter_by(thread_id=deleted_thread_id).count() == 0
        assert db_session.query(models.AgentScopeRef).filter_by(thread_id=deleted_thread_id).count() == 0

    def test_conversation_detail_structure(self, client, sample_dataset):
        """验证对话详情返回结构"""
        # 创建对话
        from app.core.models.conversation import Conversation, Message
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
            step_trace=[
                {
                    "node": "query_plan",
                    "status": "done",
                    "elapsed_ms": 12,
                    "query_plan": {"debug": {"sql_template": "SELECT secret_col FROM hidden_table"}},
                    "candidate_assets": {"fields": [{"column_name": "secret_col"}]},
                }
            ],
            sql_list=["SELECT secret_col FROM hidden_table"],
            response_metadata={
                "answer_explanation": {
                    "confidence": {"level": "high", "score": 0.92},
                },
                "query_plan": {"debug": {"sql_template": "SELECT secret_col FROM hidden_table"}},
                "candidate_assets": {"fields": [{"table_name": "hidden_table"}]},
                "dsl": {"direct_sql": "SELECT secret_col FROM hidden_table"},
                "query_profile": {"sql": {"statement": "SELECT secret_col FROM hidden_table"}},
                "explainability": {"query_profile": {"sql": {"row_count": 1}}},
                "result_artifact": {"rows": [{"secret_col": "private"}]},
                "artifact_card": {
                    "title": "BI 查询结果",
                    "summary_for_chat": "查询完成",
                    "preview_payload": {
                        "rows": [{"secret_col": "private"}],
                        "columns": ["secret_col"],
                    },
                    "primary_ref": "artifact:result-1",
                    "related_refs": ["artifact:report-1", "trace:trace-test"],
                    "actions": [{"action_type": "view", "label": "查看详情", "ref": "artifact:result-1"}],
                },
                "primary_ref": "artifact:result-1",
                "related_refs": ["artifact:report-1", "trace:trace-test"],
                "observability": {"trace_id": "trace-test", "session_id": "session-test"},
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
        assert data["message_page"] == {
            "has_more": False,
            "next_before_message_id": None,
            "limit": 200,
        }
        assert data["conversation"]["title"] == "测试对话"
        assert data["conversation"]["dataset_id"] == sample_dataset.id
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"
        assistant = data["messages"][1]
        encoded_assistant = json.dumps(assistant, ensure_ascii=False).lower()
        assert assistant["sql_list"] is None
        assert assistant["step_trace"][0]["node"] == "business_step"
        assert assistant["step_trace"][0]["display_name"] == "查询规划"
        assert assistant["response_metadata"]["artifact_card"]["preview_payload"] is None
        assert assistant["response_metadata"]["artifact_card"]["primary_ref"] == "artifact:result-1"
        assert assistant["response_metadata"]["primary_ref"] == "artifact:result-1"
        assert "query_plan" not in assistant["response_metadata"]
        assert "candidate_assets" not in assistant["response_metadata"]
        assert "dsl" not in assistant["response_metadata"]
        assert "query_profile" not in assistant["response_metadata"]
        assert "explainability" not in assistant["response_metadata"]
        assert "result_artifact" not in assistant["response_metadata"]
        assert "select" not in encoded_assistant
        assert "secret_col" not in encoded_assistant
        assert "hidden_table" not in encoded_assistant
        assert "private" not in encoded_assistant
        assert data["messages"][1]["response_metadata"]["answer_explanation"]["confidence"][
            "level"
        ] == "high"
        observability = data["messages"][1]["response_metadata"]["observability"]
        assert observability["trace_id"] == "trace-test"
        assert "trace_url" not in observability

    def test_conversation_messages_are_bounded_and_pageable(self, client, db_session):
        """详情默认可有界加载，并通过 before_message_id 继续读取更早消息。"""

        conversation = models.Conversation(title="长会话", user_id=1, archived=False)
        db_session.add(conversation)
        db_session.flush()
        messages = [
            models.Message(
                conversation_id=conversation.id,
                role="user" if index % 2 == 0 else "assistant",
                content=f"消息 {index}",
            )
            for index in range(5)
        ]
        db_session.add_all(messages)
        db_session.commit()

        latest = client.get(f"/api/conversation/{conversation.id}?message_limit=2")
        assert latest.status_code == 200
        latest_data = latest.json()
        assert [item["content"] for item in latest_data["messages"]] == ["消息 3", "消息 4"]
        assert latest_data["message_page"]["has_more"] is True

        older = client.get(
            f"/api/conversation/{conversation.id}",
            params={
                "message_limit": 2,
                "before_message_id": latest_data["message_page"]["next_before_message_id"],
            },
        )
        assert older.status_code == 200
        assert [item["content"] for item in older.json()["messages"]] == ["消息 1", "消息 2"]
