# ============================================================
# File Name   : test_conversation_history_agentscope.py
# Description:
#   get_conversation 从 agentscope_message 读取历史消息的回归测试。
#
# Responsibilities:
#   - 验证有 agentscope 关联消息时返回 agentscope 消息。
#   - 验证一个 conversation 关联多个 as_ session 时聚合全部消息并按时间排序。
#   - 验证无 agentscope 关联时回退 legacy message 表。
#   - 验证既无 agentscope 也无 legacy 时返回空 messages。
#   - 验证 reasoning_summary status completed -> done，artifact_ref -> result_ref。
#
# Author      : yangkai
# Created On  : 2026-07-10
# ============================================================

from datetime import datetime, timedelta, timezone

from app.core.models.agentscope_workbench import AgentScopeMessage, AgentScopeSession
from app.core.models.conversation import Conversation, Message


def _make_conv(db_session, *, title="测试对话", thread_id="t-conv"):
    conv = Conversation(title=title, thread_id=thread_id, user_id=1)
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    return conv


def _make_as_session(db_session, *, thread_id, legacy_conv_id, title="测试"):
    session = AgentScopeSession(
        thread_id=thread_id,
        source_type="agentscope",
        legacy_conversation_id=legacy_conv_id,
        title=title,
        status="active",
        metadata_json={},
    )
    db_session.add(session)
    db_session.commit()
    return session


def _utc(offset_seconds=0):
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


def test_get_conversation_reads_agentscope_messages(client, db_session):
    """有 agentscope 关联消息时，get_conversation 返回 agentscope 消息。"""

    conv = _make_conv(db_session)
    _make_as_session(db_session, thread_id="as_hist_1", legacy_conv_id=conv.id)

    db_session.add(
        AgentScopeMessage(
            message_id="msg_hist_u1",
            thread_id="as_hist_1",
            role="user",
            status="completed",
            content_summary="查询杨凯2025年日志",
            business_payload_json={
                "task_id": "task-1",
                "question": "查询杨凯2025年日志",
                "dataset_id": 10,
            },
            completed_at=_utc(),
        )
    )
    db_session.add(
        AgentScopeMessage(
            message_id="msg_hist_a1",
            thread_id="as_hist_1",
            role="assistant",
            status="completed",
            content_summary="查询已完成",
            business_payload_json={
                "task_id": "task-1",
                "artifact_ref": "artifact:abc123",
                "answer_summary": "查询已完成",
                "checkpoint_ref": None,
                "reasoning_summary": [
                    {"title": "识别任务", "status": "completed", "summary": "已识别为 BI 查询"},
                    {
                        "title": "生成结果",
                        "status": "completed",
                        "summary": "已生成可查看的查询结果",
                        "ref": "artifact:abc123",
                    },
                ],
            },
            completed_at=_utc(1),
        )
    )
    db_session.commit()

    resp = client.get(f"/api/conversation/{conv.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["conversation"]["id"] == conv.id
    assert len(data["messages"]) == 2

    user_msg = data["messages"][0]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "查询杨凯2025年日志"
    assert user_msg["conversation_id"] == conv.id

    assistant = data["messages"][1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "查询已完成"
    # artifact_ref 映射到 result_ref 与 artifact_card.primary_ref，前端据此渲染 ArtifactCard。
    assert assistant["response_metadata"]["result_ref"] == "artifact:abc123"
    assert assistant["response_metadata"]["artifact_card"]["primary_ref"] == "artifact:abc123"
    assert assistant["response_metadata"]["task_id"] == "task-1"
    # reasoning_summary status completed 必须映射为 done，否则前端不渲染 reasoning part。
    assert [s["status"] for s in assistant["step_trace"]] == ["done", "done"]
    assert assistant["step_trace"][0]["display_name"] == "识别任务"
    assert assistant["step_trace"][1]["ref"] == "artifact:abc123"


def test_get_conversation_aggregates_multiple_agentscope_sessions(client, db_session):
    """一个 conversation 关联多个 as_ session 时，聚合全部消息并按时间排序。"""

    conv = _make_conv(db_session, title="多 session 会话")
    _make_as_session(db_session, thread_id="as_multi_1", legacy_conv_id=conv.id, title="首轮")
    _make_as_session(db_session, thread_id="as_multi_2", legacy_conv_id=conv.id, title="次轮")

    base = _utc()
    # session1 两条消息（早）
    db_session.add(
        AgentScopeMessage(
            message_id="msg_multi_u1",
            thread_id="as_multi_1",
            role="user",
            status="completed",
            content_summary="第一轮问题",
            business_payload_json={"task_id": "t-a", "question": "第一轮问题"},
            created_at=base,
            completed_at=base,
        )
    )
    db_session.add(
        AgentScopeMessage(
            message_id="msg_multi_a1",
            thread_id="as_multi_1",
            role="assistant",
            status="completed",
            content_summary="第一轮回答",
            business_payload_json={
                "task_id": "t-a",
                "artifact_ref": "artifact:first",
                "answer_summary": "第一轮回答",
                "reasoning_summary": [
                    {"title": "生成结果", "status": "completed", "summary": "已生成"}
                ],
            },
            created_at=base + timedelta(seconds=1),
            completed_at=base + timedelta(seconds=1),
        )
    )
    # session2 两条消息（晚）
    db_session.add(
        AgentScopeMessage(
            message_id="msg_multi_u2",
            thread_id="as_multi_2",
            role="user",
            status="completed",
            content_summary="第二轮问题",
            business_payload_json={"task_id": "t-b", "question": "第二轮问题"},
            created_at=base + timedelta(seconds=60),
            completed_at=base + timedelta(seconds=60),
        )
    )
    db_session.add(
        AgentScopeMessage(
            message_id="msg_multi_a2",
            thread_id="as_multi_2",
            role="assistant",
            status="completed",
            content_summary="第二轮回答",
            business_payload_json={
                "task_id": "t-b",
                "artifact_ref": "artifact:second",
                "answer_summary": "第二轮回答",
                "reasoning_summary": [
                    {"title": "生成结果", "status": "completed", "summary": "已生成"}
                ],
            },
            created_at=base + timedelta(seconds=61),
            completed_at=base + timedelta(seconds=61),
        )
    )
    db_session.commit()

    resp = client.get(f"/api/conversation/{conv.id}")
    assert resp.status_code == 200
    msgs = resp.json()["messages"]
    # 4 条消息跨两个 session 聚合后按 created_at 升序。
    assert len(msgs) == 4
    assert [m["content"] for m in msgs] == [
        "第一轮问题",
        "第一轮回答",
        "第二轮问题",
        "第二轮回答",
    ]
    assert msgs[1]["response_metadata"]["result_ref"] == "artifact:first"
    assert msgs[3]["response_metadata"]["result_ref"] == "artifact:second"


def test_get_conversation_falls_back_to_legacy_message(client, db_session):
    """无 agentscope 关联的老会话，回退 legacy message 表。"""

    conv = _make_conv(db_session, title="老会话")
    db_session.add(
        Message(
            conversation_id=conv.id,
            role="user",
            content="legacy 问题",
        )
    )
    db_session.add(
        Message(
            conversation_id=conv.id,
            role="assistant",
            content="legacy 回答",
        )
    )
    db_session.commit()

    resp = client.get(f"/api/conversation/{conv.id}")
    assert resp.status_code == 200
    msgs = resp.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "legacy 问题"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "legacy 回答"


def test_get_conversation_empty_when_no_messages(client, db_session):
    """既无 agentscope 也无 legacy 消息时返回空 messages，不报错。"""

    conv = _make_conv(db_session, title="空会话")
    resp = client.get(f"/api/conversation/{conv.id}")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []
