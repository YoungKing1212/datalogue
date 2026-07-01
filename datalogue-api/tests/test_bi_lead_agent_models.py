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

from sqlalchemy import inspect, select, text

from app.core.database import Base
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


def test_bi_lead_agent_confirmation_raw_insert_defaults_snapshot(db_session):
    db_session.execute(
        text(
            """
            INSERT INTO bi_lead_agent_run (status, question, trace_id, task_id)
            VALUES (:status, :question, :trace_id, :task_id)
            """
        ),
        {
            "status": "waiting_confirmation",
            "question": "统计 2026 年订单金额",
            "trace_id": "trace-bi-core-001",
            "task_id": "task-bi-core-001",
        },
    )
    run_id = db_session.execute(
        select(BILeadAgentRun.id).where(BILeadAgentRun.trace_id == "trace-bi-core-001")
    ).scalar_one()

    db_session.execute(
        text(
            """
            INSERT INTO bi_lead_agent_confirmation (
                run_id,
                dataset_id,
                confirmed_question,
                task_goal,
                routing_rationale,
                trace_id,
                parent_run_id
            )
            VALUES (
                :run_id,
                :dataset_id,
                :confirmed_question,
                :task_goal,
                :routing_rationale,
                :trace_id,
                :parent_run_id
            )
            """
        ),
        {
            "run_id": run_id,
            "dataset_id": 12,
            "confirmed_question": "统计 2026 年订单金额",
            "task_goal": "按确认的数据集执行单数据集问数",
            "routing_rationale": "订单金额问题应由订单数据集回答。",
            "trace_id": "trace-bi-core-001",
            "parent_run_id": str(run_id),
        },
    )
    db_session.commit()

    snapshot = db_session.execute(
        select(BILeadAgentConfirmation.capability_snapshot_json).where(
            BILeadAgentConfirmation.run_id == run_id
        )
    ).scalar_one()
    assert snapshot == {}


def test_bi_lead_agent_models_registered_through_app_main():
    import app.main  # noqa: F401  # 导入主应用后，三张 K1 表必须已进入共享 metadata，避免测试外运行漏注册。

    assert "bi_lead_agent_run" in Base.metadata.tables
    assert "bi_lead_agent_confirmation" in Base.metadata.tables
    assert "bi_agent_handoff" in Base.metadata.tables


def test_bi_lead_agent_create_all_avoids_duplicate_identity_indexes(db_session):
    inspector = inspect(db_session.get_bind())

    def index_names(table_name):
        return {index["name"] for index in inspector.get_indexes(table_name)}

    run_indexes = index_names("bi_lead_agent_run")
    confirmation_indexes = index_names("bi_lead_agent_confirmation")
    handoff_indexes = index_names("bi_agent_handoff")

    assert "ix_bi_lead_agent_run_id" not in run_indexes
    assert "ix_bi_lead_agent_confirmation_id" not in confirmation_indexes
    assert "ix_bi_lead_agent_confirmation_run_id" not in confirmation_indexes
    assert "ix_bi_agent_handoff_id" not in handoff_indexes
    assert "ix_bi_agent_handoff_run_id" not in handoff_indexes
    assert "ix_bi_agent_handoff_handoff_id" not in handoff_indexes

    assert {"ix_bi_lead_agent_run_status", "ix_bi_lead_agent_run_phase", "ix_bi_lead_agent_run_trace_id"} <= run_indexes
    assert {
        "ix_bi_lead_agent_confirmation_dataset_id",
        "ix_bi_lead_agent_confirmation_trace_id",
        "ix_bi_lead_agent_confirmation_error_code",
    } <= confirmation_indexes
    assert {
        "ix_bi_agent_handoff_dataset_id",
        "ix_bi_agent_handoff_child_run_id",
        "ix_bi_agent_handoff_artifact_ref",
        "ix_bi_agent_handoff_checkpoint_ref",
    } <= handoff_indexes
