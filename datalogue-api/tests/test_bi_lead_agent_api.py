# ============================================================
# File Name   : test_bi_agent_api.py
# Description:
#   BI Agent K1 run-centric API 测试。
#
# Responsibilities:
#   - 验证 BI Agent run 创建、确认和读取的最小 API 生命周期。
#   - 验证 API 响应不会泄露 DatasetAgent 内部工具名和执行字段。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import logging

from app.models.bi_agent import BIAgentHandoff, BIAgentRun


FORBIDDEN_DATASET_INTERNALS = (
    "list_candidate_assets",
    "compile_dsl_to_sql",
    "execute_compiled_query",
    "raw_rows",
    "schema",
    "dsl",
)


def _assert_no_dataset_internals(response_text: str) -> None:
    for forbidden in FORBIDDEN_DATASET_INTERNALS:
        assert forbidden not in response_text


def _create_run(client):
    return client.post(
        "/api/bi-agent/runs",
        json={
            "question": "统计 2026 年订单金额",
            "trace_id": "trace-bi-k1-api",
            "task_id": "task-bi-k1-api",
        },
    )


def _confirmation_payload(dataset_id: int, capability_dataset_id: int | None = None) -> dict:
    return {
        "dataset_id": dataset_id,
        "confirmed_question": "统计 2026 年订单金额",
        "task_goal": "按确认的数据集执行单数据集问数",
        "capability_snapshot": {
            "dataset_id": capability_dataset_id or dataset_id,
            "name": "订单数据集",
            "domain": "销售",
            "supported_questions": ["订单金额趋势"],
            "key_metrics": ["订单金额"],
            "key_dimensions": ["月份"],
            "freshness": "T+1",
            "availability": "ready",
        },
        "routing_rationale": "订单金额问题应由订单数据集回答。",
        "risk_notice": "本次只执行只读聚合查询。",
        "user_decision": "approved",
    }


def test_bi_agent_api_lifecycle_create_confirm_get(client, sample_dataset, caplog):
    caplog.set_level(logging.INFO)
    create_response = _create_run(client)

    assert create_response.status_code == 200
    _assert_no_dataset_internals(create_response.text)
    created = create_response.json()
    assert created["status"] == "waiting_confirmation"
    assert created["phase"] == "confirm_run"
    assert created["status_reason"] == "confirmation_required"
    assert created["trace_id"] == "trace-bi-k1-api"
    assert created["task_id"] == "task-bi-k1-api"

    confirm_response = client.post(
        f"/api/bi-agent/runs/{created['run_id']}/confirm",
        json=_confirmation_payload(sample_dataset.id),
    )

    assert confirm_response.status_code == 200
    _assert_no_dataset_internals(confirm_response.text)
    confirmed = confirm_response.json()
    assert confirmed["run_id"] == created["run_id"]
    assert confirmed["confirmation_id"] is not None
    assert confirmed["status"] == "running"
    assert confirmed["phase"] == "confirm_run"
    assert confirmed["status_reason"] == "confirmation_approved"

    get_response = client.get(f"/api/bi-agent/runs/{created['run_id']}")

    assert get_response.status_code == 200
    _assert_no_dataset_internals(get_response.text)
    assert get_response.json() == confirmed


def test_bi_agent_get_missing_run_returns_404(client):
    response = client.get("/api/bi-agent/runs/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "BI_LEAD_AGENT_RUN_NOT_FOUND"


def test_bi_agent_confirm_dataset_mismatch_returns_400(client, sample_dataset):
    create_response = _create_run(client)
    run_id = create_response.json()["run_id"]

    response = client.post(
        f"/api/bi-agent/runs/{run_id}/confirm",
        json=_confirmation_payload(
            sample_dataset.id,
            capability_dataset_id=sample_dataset.id + 1000,
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "DATASET_CONFIRMATION_MISMATCH"


def test_bi_agent_handoff_requires_confirmed_run(client):
    create_response = _create_run(client)
    run_id = create_response.json()["run_id"]

    response = client.post(f"/api/bi-agent/runs/{run_id}/handoff")

    assert response.status_code == 400
    assert response.json()["detail"] == "USER_CONFIRMATION_REQUIRED"


def test_bi_agent_handoff_endpoint_returns_safe_refs(client, sample_dataset, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    class FakeBIHandoffService:
        def __init__(self, db):
            self.db = db

        async def query_dataset(self, *, run_id: int):
            run = self.db.get(BIAgentRun, run_id)
            handoff = BIAgentHandoff(
                run_id=run_id,
                handoff_id="handoff-api-safe",
                parent_agent="bi_agent",
                child_agent="dataset_agent",
                child_run_id="dataset-run-api-safe",
                dataset_id=sample_dataset.id,
                task_id=run.task_id,
                trace_id=run.trace_id,
                checkpoint_ref="checkpoint-api-safe",
                artifact_ref="artifact-api-safe",
                handoff_status="completed",
                answer_summary="订单金额汇总完成。",
                row_count=12,
                column_count=3,
            )
            # 模拟底层对象意外带有内部字段，API response 仍必须经 DTO 白名单裁剪。
            handoff.sql = "SELECT * FROM secret_orders"
            handoff.raw_rows = [{"secret_amount": 100}]
            run.phase = "summarize_run"
            run.status = "completed"
            run.status_reason = "handoff_completed"
            self.db.add(handoff)
            self.db.add(run)
            self.db.commit()
            return handoff

    monkeypatch.setattr("app.api.bi_agent.BIAgentHandoffService", FakeBIHandoffService)
    create_response = _create_run(client)
    run_id = create_response.json()["run_id"]
    confirm_response = client.post(
        f"/api/bi-agent/runs/{run_id}/confirm",
        json=_confirmation_payload(sample_dataset.id),
    )
    assert confirm_response.status_code == 200

    response = client.post(f"/api/bi-agent/runs/{run_id}/handoff")

    assert response.status_code == 200, response.text
    _assert_no_dataset_internals(response.text)
    payload = response.json()
    assert payload["phase"] == "summarize_run"
    assert payload["status"] == "completed"
    assert payload["handoff"]["handoff_id"] == "handoff-api-safe"
    assert payload["handoff"]["artifact_ref"] == "artifact-api-safe"
    assert payload["handoff"]["checkpoint_ref"] == "checkpoint-api-safe"
    assert payload["handoff"]["row_count"] == 12
    assert payload["handoff"]["column_count"] == 3
