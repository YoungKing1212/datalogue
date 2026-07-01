# ============================================================
# File Name   : test_bi_lead_agent_models.py
# Description:
#   BI LeadAgent K1 数据模型测试。
#
# Responsibilities:
#   - 验证 run、confirmation、handoff 三张表可在 SQLite 测试库中写入和关联。
#   - 验证 JSON 快照字段只保存路由级摘要。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from app.models.bi_lead_agent import BIAgentHandoff, BILeadAgentConfirmation, BILeadAgentRun


def test_bi_lead_agent_models_persist_k1_contract(db_session):
    run = BILeadAgentRun(
        status="waiting_confirmation",
        phase="confirm_run",
        question="统计 2026 年订单金额",
        trace_id="trace-bi-001",
        task_id="task-bi-001",
    )
    db_session.add(run)
    db_session.flush()

    confirmation = BILeadAgentConfirmation(
        run_id=run.id,
        dataset_id=12,
        confirmed_question="统计 2026 年订单金额",
        task_goal="按确认的数据集执行单数据集问数",
        capability_snapshot_json={
            "dataset_id": 12,
            "name": "订单数据集",
            "domain": "销售",
            "key_metrics": ["订单金额"],
            "key_dimensions": ["月份"],
            "availability": "ready",
        },
        routing_rationale="订单金额问题应由订单数据集回答。",
        risk_notice="本次只执行只读聚合查询。",
        user_decision="approved",
        trace_id="trace-bi-001",
        parent_run_id=str(run.id),
    )
    db_session.add(confirmation)

    handoff = BIAgentHandoff(
        run_id=run.id,
        handoff_id="handoff-001",
        parent_agent="bi_lead_agent",
        child_run_id="dataset-run-001",
        dataset_id=12,
        task_id="task-bi-001",
        trace_id="trace-bi-001",
        handoff_status="completed",
        answer_summary="订单金额汇总完成。",
        artifact_ref="artifact-001",
        checkpoint_ref="checkpoint-001",
        row_count=10,
        column_count=3,
    )
    db_session.add(handoff)
    db_session.commit()

    saved = db_session.query(BILeadAgentRun).filter_by(trace_id="trace-bi-001").one()
    assert saved.status == "waiting_confirmation"
    assert saved.phase == "confirm_run"
    assert saved.confirmation.dataset_id == 12
    assert saved.handoff.child_agent == "dataset_agent"
    assert saved.handoff.handoff_status == "completed"
    assert "schema" not in saved.confirmation.capability_snapshot_json
