# ============================================================
# File Name   : test_bi_lead_agent_e2e_contract.py
# Description:
#   BI LeadAgent K2 端到端页面契约测试。
#
# Responsibilities:
#   - 验证 create -> confirm -> handoff -> get 的 API 生命周期可支撑 K2 页面原型。
#   - 验证 response 只暴露 handoff 安全 refs 和摘要，不泄露 DatasetAgent 执行层内部字段。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from app.models.bi_lead_agent import BIAgentHandoff
from app.schemas.bi_lead_agent import BILeadAgentHandoffResult


FORBIDDEN_DATASET_INTERNALS = (
    "list_candidate_assets",
    "compile_dsl_to_sql",
    "execute_compiled_query",
    "raw_rows",
    "schema",
    "dsl",
    "SELECT * FROM secret_orders",
)


class FakeDatasetHandoffAdapter:
    """替换真实 DatasetAgent Runtime；保留 BI LeadAgent 服务层和 DB 写入的真实路径。"""

    def __init__(self) -> None:
        self.calls = []

    async def query_dataset(self, request, task_id: str | None = None):
        self.calls.append({"request": request, "task_id": task_id})
        return BILeadAgentHandoffResult(
            handoff_id="handoff-k2-e2e",
            parent_agent="bi_lead_agent",
            child_agent="dataset_agent",
            child_run_id="dataset-run-k2-e2e",
            dataset_id=request.dataset_id,
            task_id=task_id,
            trace_id=request.trace_id,
            checkpoint_ref="checkpoint://bi-lead/k2-e2e",
            artifact_ref="artifact:bi-lead-k2-e2e",
            handoff_status="completed",
            answer_summary="已生成渠道 GMV 汇总，线上渠道贡献最高。",
            row_count=12,
            column_count=4,
        )


def _assert_no_dataset_internals(response_text: str) -> None:
    for forbidden in FORBIDDEN_DATASET_INTERNALS:
        assert forbidden not in response_text


def _confirmation_payload(dataset_id: int) -> dict:
    return {
        "dataset_id": dataset_id,
        "confirmed_question": "统计 2026 年各渠道 GMV",
        "task_goal": "执行单数据集问数",
        "capability_snapshot": {
            "dataset_id": dataset_id,
            "name": "订单数据集",
            "domain": "销售",
            "supported_questions": ["渠道 GMV 趋势"],
            "key_metrics": ["GMV", "订单数"],
            "key_dimensions": ["渠道", "月份"],
            "freshness": "T+1",
            "availability": "ready",
        },
        "routing_rationale": "用户已确认订单数据集可回答渠道 GMV。",
        "risk_notice": "本次只执行只读查询。",
        "user_decision": "approved",
    }


def test_bi_lead_agent_k2_create_confirm_handoff_get_contract(
    client,
    db_session,
    sample_dataset,
    monkeypatch,
):
    fake_adapter = FakeDatasetHandoffAdapter()
    monkeypatch.setattr(
        "app.services.bi_lead_agent.handoff_service.DatalogueBIHandoffAdapter.from_db",
        lambda db: fake_adapter,
    )

    create_response = client.post(
        "/api/bi-lead-agent/runs",
        json={
            "question": "统计 2026 年各渠道 GMV",
            "trace_id": "trace-bi-k2-e2e",
            "task_id": "task-bi-k2-e2e",
        },
    )
    assert create_response.status_code == 200
    _assert_no_dataset_internals(create_response.text)
    created = create_response.json()
    assert created["status"] == "waiting_confirmation"
    assert created["phase"] == "confirm_run"

    confirm_response = client.post(
        f"/api/bi-lead-agent/runs/{created['run_id']}/confirm",
        json=_confirmation_payload(sample_dataset.id),
    )
    assert confirm_response.status_code == 200
    _assert_no_dataset_internals(confirm_response.text)
    confirmed = confirm_response.json()
    assert confirmed["status"] == "running"
    assert confirmed["phase"] == "confirm_run"

    handoff_response = client.post(f"/api/bi-lead-agent/runs/{created['run_id']}/handoff")
    assert handoff_response.status_code == 200
    _assert_no_dataset_internals(handoff_response.text)
    handed_off = handoff_response.json()
    assert handed_off["status"] == "completed"
    assert handed_off["phase"] == "summarize_run"
    assert handed_off["handoff"] == {
        "handoff_id": "handoff-k2-e2e",
        "parent_agent": "bi_lead_agent",
        "child_agent": "dataset_agent",
        "child_run_id": "dataset-run-k2-e2e",
        "dataset_id": sample_dataset.id,
        "task_id": "task-bi-k2-e2e",
        "trace_id": "trace-bi-k2-e2e",
        "checkpoint_ref": "checkpoint://bi-lead/k2-e2e",
        "artifact_ref": "artifact:bi-lead-k2-e2e",
        "handoff_status": "completed",
        "answer_summary": "已生成渠道 GMV 汇总，线上渠道贡献最高。",
        "row_count": 12,
        "column_count": 4,
        "status_reason": None,
        "error_code": None,
        "error_summary": None,
    }

    get_response = client.get(f"/api/bi-lead-agent/runs/{created['run_id']}")
    assert get_response.status_code == 200
    assert get_response.json() == handed_off

    assert len(fake_adapter.calls) == 1
    adapter_call = fake_adapter.calls[0]
    assert adapter_call["task_id"] == "task-bi-k2-e2e"
    assert adapter_call["request"].dataset_id == sample_dataset.id
    assert adapter_call["request"].confirmed_question == "统计 2026 年各渠道 GMV"
    assert adapter_call["request"].trace_id == "trace-bi-k2-e2e"
    assert adapter_call["request"].parent_run_id == str(created["run_id"])

    saved_handoff = db_session.query(BIAgentHandoff).filter_by(run_id=created["run_id"]).one()
    assert saved_handoff.handoff_id == "handoff-k2-e2e"
    assert saved_handoff.parent_agent == "bi_lead_agent"
    assert saved_handoff.child_agent == "dataset_agent"
    assert saved_handoff.child_run_id == "dataset-run-k2-e2e"
    assert saved_handoff.artifact_ref == "artifact:bi-lead-k2-e2e"
    assert saved_handoff.checkpoint_ref == "checkpoint://bi-lead/k2-e2e"
