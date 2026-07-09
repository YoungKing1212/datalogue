# ============================================================
# File Name   : test_artifact_api.py
# Description:
#   Artifact 读取与 TTL API 测试。
#
# Responsibilities:
#   - 验证 artifact ref 可按需读取 JSON/Text 内容。
#   - 验证过期、缺失和内部清理接口的 fail-closed 行为。
#   - 验证 chat 落库后可回填 artifact message_id。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core import models
from app.domains.query_execution.artifact_store import ArtifactStore


def test_get_artifact_api_returns_json_payload(client, db_session, sample_dataset):
    ref = ArtifactStore(db_session).put_json(
        kind="sql_result",
        payload={"columns": ["id"], "rows": [{"id": 1}]},
        dataset_id=sample_dataset.id,
        conversation_id=123,
    )

    response = client.get(f"/api/artifacts/{ref}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_ref"] == ref
    assert payload["kind"] == "sql_result"
    assert payload["dataset_id"] == sample_dataset.id
    assert payload["conversation_id"] == 123
    assert payload["content_mime"] == "application/json"
    assert payload["content_json"]["rows"] == [{"id": 1}]
    assert payload["content_text"] is None
    assert payload["expires_at"]


def test_get_artifact_api_returns_text_payload(client, db_session, sample_dataset):
    ref = ArtifactStore(db_session).put_text(
        kind="report",
        text="报告正文",
        dataset_id=sample_dataset.id,
        content_mime="text/markdown",
    )

    response = client.get(f"/api/artifacts/{ref}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "report"
    assert payload["content_mime"] == "text/markdown"
    assert payload["content_json"] is None
    assert payload["content_text"] == "报告正文"


def test_get_artifact_api_404_for_missing_or_expired(client, db_session, sample_dataset):
    missing = client.get("/api/artifacts/artifact:not-found")
    assert missing.status_code == 404

    ref = ArtifactStore(db_session).put_json(
        kind="sql_result",
        payload={"rows": []},
        dataset_id=sample_dataset.id,
    )
    artifact = db_session.query(models.QueryArtifact).filter_by(artifact_id=ref).one()
    artifact.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(artifact)
    db_session.commit()

    expired = client.get(f"/api/artifacts/{ref}")

    assert expired.status_code == 404


def test_internal_purge_expired_artifacts(client, db_session, sample_dataset, monkeypatch):
    store = ArtifactStore(db_session)
    expired_ref = store.put_json(kind="sql_result", payload={"rows": []}, dataset_id=sample_dataset.id)
    active_ref = store.put_json(kind="sql_result", payload={"rows": [1]}, dataset_id=sample_dataset.id)
    expired = db_session.query(models.QueryArtifact).filter_by(artifact_id=expired_ref).one()
    expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(expired)
    db_session.commit()

    from app.core.config import Settings

    monkeypatch.setattr(
        "app.api.artifacts.get_settings",
        lambda: Settings(QUERY_ARTIFACT_MAINTENANCE_API_KEY="test-internal-token"),
    )
    response = client.post(
        "/api/artifacts/purge-expired",
        headers={"X-Datalogue-Internal-Token": "test-internal-token"},
    )

    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    assert store.get(expired_ref) is None
    assert store.get(active_ref) is not None


def test_artifact_store_attach_message_id(db_session, sample_dataset):
    store = ArtifactStore(db_session)
    ref = store.put_json(kind="sql_result", payload={"rows": []}, dataset_id=sample_dataset.id)

    updated = store.attach_message_id([ref, "artifact:not-found", None], message_id=987)

    assert updated == 1
    artifact = store.get(ref)
    assert artifact.message_id == 987


def test_get_repair_plan_artifact_returns_sanitized_summary(client, db_session, sample_dataset):
    ref = ArtifactStore(db_session).put_json(
        kind="repair_plan",
        payload={
            "schema_version": "repair_plan.v1",
            "failure_class": "FIELD_NOT_FOUND",
            "status": "plan_created",
            "business_summary": "字段口径不匹配，已生成自动修复方案。",
            "attempts": 1,
            "requires_user_confirmation": False,
            "repair_plan_ref": "artifact:repair-1",
            "checkpoint_ref": "checkpoint://conv-1-msg-2/repair",
            "trace_ref": "trace:trace-1",
            "actions": [
                {
                    "action_type": "replace_field",
                    "target": {"table": "work_log", "field": "bad_col"},
                    "replacement": {"table": "work_log", "field": "work_date"},
                }
            ],
            "raw_sql": "select bad_col from work_log",
            "raw_result": {"rows": []},
            "schema": {"tables": ["work_log"]},
        },
        dataset_id=sample_dataset.id,
        conversation_id=123,
        trace_id="trace-1",
    )

    response = client.get(f"/api/artifacts/{ref}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "repair_plan"
    assert payload["content_json"] == {
        "schema_version": "repair_plan.v1",
        "failure_class": "FIELD_NOT_FOUND",
        "status": "plan_created",
        "business_summary": "字段口径不匹配，已生成自动修复方案。",
        "attempts": 1,
        "requires_user_confirmation": False,
        "repair_plan_ref": "artifact:repair-1",
        "checkpoint_ref": "checkpoint://conv-1-msg-2/repair",
        "trace_ref": "trace:trace-1",
    }
    rendered = str(payload).lower()
    assert "bad_col" not in rendered
    assert "work_log" not in rendered
    assert "raw_sql" not in rendered
    assert "raw_result" not in rendered
    assert "actions" not in rendered
