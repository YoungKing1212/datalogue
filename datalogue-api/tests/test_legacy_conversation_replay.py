# ============================================================
# File Name   : test_legacy_conversation_replay.py
# Description:
#   旧会话回放兼容测试。
#
# Responsibilities:
#   - 验证历史消息缺少 ArtifactCard 时，后端不迁移、不回填、不伪造卡片。
#   - 验证新消息已有 artifact refs 时，conversation API 原样返回 metadata。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

from app import models


def test_legacy_conversation_replay_does_not_backfill_artifact_card(client, db_session, sample_dataset):
    conv = models.Conversation(
        title="旧会话",
        thread_id="legacy-thread",
        user_id=1,
        dataset_id=sample_dataset.id,
    )
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)

    legacy_message = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content="旧回答",
        response_metadata={
            "result_ref": "artifact:legacy-result",
            "report_ref": "artifact:legacy-report",
        },
    )
    db_session.add(legacy_message)
    db_session.commit()

    response = client.get(f"/api/conversation/{conv.id}")

    assert response.status_code == 200
    metadata = response.json()["messages"][0]["response_metadata"]
    assert metadata["result_ref"] == "artifact:legacy-result"
    assert "artifact_card" not in metadata
    assert "primary_ref" not in metadata
    assert "related_refs" not in metadata


def test_conversation_replay_returns_existing_artifact_refs(client, db_session, sample_dataset):
    conv = models.Conversation(
        title="新会话",
        thread_id="new-thread",
        user_id=1,
        dataset_id=sample_dataset.id,
    )
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)

    artifact_card = {
        "title": "BI 查询结果",
        "primary_ref": {"ref_id": "artifact:result-1", "ref_type": "result"},
        "related_refs": [{"ref_id": "trace:trace-1", "ref_type": "trace"}],
    }
    message = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content="新回答",
        response_metadata={
            "task_id": "conv-1-msg-2",
            "trace_id": "trace-1",
            "artifact_card": artifact_card,
            "primary_ref": artifact_card["primary_ref"],
            "related_refs": artifact_card["related_refs"],
        },
    )
    db_session.add(message)
    db_session.commit()

    response = client.get(f"/api/conversation/{conv.id}")

    assert response.status_code == 200
    metadata = response.json()["messages"][0]["response_metadata"]
    assert metadata["artifact_card"] == artifact_card
    assert metadata["primary_ref"]["ref_id"] == "artifact:result-1"
    assert metadata["related_refs"][0]["ref_id"] == "trace:trace-1"
