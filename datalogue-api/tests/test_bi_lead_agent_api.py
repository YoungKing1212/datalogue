# ============================================================
# File Name   : test_bi_lead_agent_api.py
# Description:
#   BI LeadAgent K1 run-centric API 测试。
#
# Responsibilities:
#   - 验证 LeadAgent run 创建、确认和读取的最小 API 生命周期。
#   - 验证 API 响应不会泄露 DatasetAgent 内部工具名和执行字段。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations


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
        "/api/bi-lead-agent/runs",
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


def test_bi_lead_agent_api_lifecycle_create_confirm_get(client, sample_dataset):
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
        f"/api/bi-lead-agent/runs/{created['run_id']}/confirm",
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

    get_response = client.get(f"/api/bi-lead-agent/runs/{created['run_id']}")

    assert get_response.status_code == 200
    _assert_no_dataset_internals(get_response.text)
    assert get_response.json() == confirmed


def test_bi_lead_agent_get_missing_run_returns_404(client):
    response = client.get("/api/bi-lead-agent/runs/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "BI_LEAD_AGENT_RUN_NOT_FOUND"


def test_bi_lead_agent_confirm_dataset_mismatch_returns_400(client, sample_dataset):
    create_response = _create_run(client)
    run_id = create_response.json()["run_id"]

    response = client.post(
        f"/api/bi-lead-agent/runs/{run_id}/confirm",
        json=_confirmation_payload(
            sample_dataset.id,
            capability_dataset_id=sample_dataset.id + 1000,
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "DATASET_CONFIRMATION_MISMATCH"
