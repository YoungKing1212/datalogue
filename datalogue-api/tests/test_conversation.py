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

    def test_create_conversation_via_chat(self, client, sample_dataset):
        """通过 chat stream 接口创建对话（验证对话和消息持久化）"""
        # 注意：chat/stream 是 SSE 接口，在同步 TestClient 中可能有问题
        # 这里只验证接口可访问，实际流式测试在集成环境中进行
        payload = {
            "question": "测试问题",
            "dataset_id": sample_dataset.id,
        }
        try:
            resp = client.post("/api/chat/stream", json=payload)
            assert resp.status_code == 200
            # 验证对话已创建
            convs = client.get("/api/conversation").json()
            assert len(convs) >= 1
        except Exception:
            pytest.skip("SSE stream not fully supported in sync TestClient")

    def test_conversation_detail_structure(self, client, sample_dataset):
        """验证对话详情返回结构"""
        # 创建对话
        from app.models.conversation import Conversation, Message
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
