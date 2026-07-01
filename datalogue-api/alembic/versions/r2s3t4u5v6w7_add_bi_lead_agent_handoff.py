# ============================================================
# File Name   : r2s3t4u5v6w7_add_bi_lead_agent_handoff.py
# Description:
#   新增 BI LeadAgent K1 状态和移交表。
#
# Responsibilities:
#   - 创建 LeadAgent run、用户确认和 DatasetAgent handoff 三张状态表。
#   - 为确认回放、子 Agent 移交追踪和失败诊断建立必要索引与唯一约束。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

"""add_bi_lead_agent_handoff

Revision ID: r2s3t4u5v6w7
Revises: p1q2r3s4t5u6
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "r2s3t4u5v6w7"
down_revision: Union[str, None] = "p1q2r3s4t5u6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _json_default() -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text("'{}'::jsonb")
    return sa.text("'{}'")


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def _existing_index_names(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    bind = op.get_bind()
    return {
        index_name
        for item in sa.inspect(bind).get_indexes(table_name)
        if (index_name := item.get("name")) is not None
    }


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    if index_name in _existing_index_names(table_name):
        return
    op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    if index_name not in _existing_index_names(table_name):
        return
    op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _has_table("bi_lead_agent_run"):
        op.create_table(
            "bi_lead_agent_run",
            sa.Column("id", sa.Integer(), nullable=False, comment="主键。"),
            sa.Column(
                "status",
                sa.String(length=40),
                server_default="created",
                nullable=False,
                comment="LeadAgent 总状态，只记录路由/确认/移交阶段。",
            ),
            sa.Column("phase", sa.String(length=60), server_default="route_run", nullable=False, comment="当前编排阶段。"),
            sa.Column("question", sa.Text(), nullable=False, comment="用户原始问数问题。"),
            sa.Column("task_id", sa.String(length=120), nullable=True, comment="业务任务 ID。"),
            sa.Column("trace_id", sa.String(length=120), nullable=False, comment="观测 trace ID。"),
            sa.Column("status_reason", sa.Text(), nullable=True, comment="状态原因，面向前端展示和回放诊断。"),
            sa.Column("error_code", sa.String(length=80), nullable=True, comment="失败错误码。"),
            sa.Column("error_summary", sa.Text(), nullable=True, comment="失败摘要。"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="创建时间。"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="更新时间。"),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True, comment="完成、失败或终止时间。"),
            sa.PrimaryKeyConstraint("id"),
            comment="BI LeadAgent run 状态表，记录 K1 编排主状态。",
        )

    if not _has_table("bi_lead_agent_confirmation"):
        op.create_table(
            "bi_lead_agent_confirmation",
            sa.Column("id", sa.Integer(), nullable=False, comment="主键。"),
            sa.Column("run_id", sa.Integer(), nullable=False, comment="所属 LeadAgent run。"),
            sa.Column("dataset_id", sa.Integer(), nullable=False, comment="确认后选择的数据集 ID。"),
            sa.Column("confirmed_question", sa.Text(), nullable=False, comment="用户确认后的问题文本。"),
            sa.Column("task_goal", sa.Text(), nullable=False, comment="交给 DatasetAgent 的任务目标。"),
            sa.Column(
                "capability_snapshot_json",
                _json_type(),
                server_default=_json_default(),
                nullable=False,
                comment="路由级能力摘要；禁止保存 schema、raw rows 和完整内部提示。",
            ),
            sa.Column("routing_rationale", sa.Text(), nullable=False, comment="LeadAgent 路由理由。"),
            sa.Column("risk_notice", sa.Text(), nullable=True, comment="展示给用户的风险提示。"),
            sa.Column(
                "user_decision",
                sa.String(length=40),
                server_default="pending",
                nullable=False,
                comment="用户确认决策：pending、approved、rejected、expired。",
            ),
            sa.Column("trace_id", sa.String(length=120), nullable=False, comment="观测 trace ID。"),
            sa.Column("parent_run_id", sa.String(length=120), nullable=False, comment="上游 run 标识，用于跨层回放。"),
            sa.Column("status_reason", sa.Text(), nullable=True, comment="确认阶段状态原因。"),
            sa.Column("error_code", sa.String(length=80), nullable=True, comment="确认阶段失败错误码。"),
            sa.Column("error_summary", sa.Text(), nullable=True, comment="确认阶段失败摘要。"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="创建时间。"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="更新时间。"),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True, comment="用户完成决策时间。"),
            sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"]),
            sa.ForeignKeyConstraint(["run_id"], ["bi_lead_agent_run.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", name="uq_bi_lead_agent_confirmation_run_id"),
            comment="BI LeadAgent 用户确认表，保存确认结果和路由级能力快照。",
        )

    if not _has_table("bi_agent_handoff"):
        op.create_table(
            "bi_agent_handoff",
            sa.Column("id", sa.Integer(), nullable=False, comment="主键。"),
            sa.Column("run_id", sa.Integer(), nullable=False, comment="所属 LeadAgent run。"),
            sa.Column("handoff_id", sa.String(length=120), nullable=False, comment="LeadAgent 到子 Agent 的稳定移交 ID。"),
            sa.Column(
                "parent_agent",
                sa.String(length=80),
                server_default="bi_lead_agent",
                nullable=False,
                comment="父 Agent 名称。",
            ),
            sa.Column(
                "child_agent",
                sa.String(length=80),
                server_default="dataset_agent",
                nullable=False,
                comment="子 Agent 名称，K1 默认移交 DatasetAgent。",
            ),
            sa.Column("child_run_id", sa.String(length=120), nullable=True, comment="子 Agent run ID。"),
            sa.Column("dataset_id", sa.Integer(), nullable=False, comment="移交目标数据集 ID。"),
            sa.Column("task_id", sa.String(length=120), nullable=True, comment="业务任务 ID。"),
            sa.Column("trace_id", sa.String(length=120), nullable=False, comment="观测 trace ID。"),
            sa.Column("checkpoint_ref", sa.String(length=200), nullable=True, comment="checkpoint 业务引用。"),
            sa.Column("artifact_ref", sa.String(length=200), nullable=True, comment="artifact 业务引用。"),
            sa.Column(
                "handoff_status",
                sa.String(length=40),
                server_default="created",
                nullable=False,
                comment="子 Agent 移交状态：created、running、completed、failed。",
            ),
            sa.Column("answer_summary", sa.Text(), nullable=True, comment="子 Agent 回答摘要。"),
            sa.Column("row_count", sa.Integer(), nullable=True, comment="结果行数摘要。"),
            sa.Column("column_count", sa.Integer(), nullable=True, comment="结果列数摘要。"),
            sa.Column("status_reason", sa.Text(), nullable=True, comment="移交阶段状态原因。"),
            sa.Column("error_code", sa.String(length=80), nullable=True, comment="移交阶段失败错误码。"),
            sa.Column("error_summary", sa.Text(), nullable=True, comment="移交阶段失败摘要。"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="创建时间。"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="更新时间。"),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True, comment="完成、失败或终止时间。"),
            sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"]),
            sa.ForeignKeyConstraint(["run_id"], ["bi_lead_agent_run.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", name="uq_bi_agent_handoff_run_id"),
            sa.UniqueConstraint("handoff_id", name="uq_bi_agent_handoff_handoff_id"),
            comment="BI Agent handoff 表，保存 LeadAgent 到 DatasetAgent 的轻量移交状态。",
        )

    for table_name, index_name, columns, unique in [
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_status"), ["status"], False),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_phase"), ["phase"], False),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_task_id"), ["task_id"], False),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_trace_id"), ["trace_id"], False),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_error_code"), ["error_code"], False),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_created_at"), ["created_at"], False),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_updated_at"), ["updated_at"], False),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_completed_at"), ["completed_at"], False),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_dataset_id"), ["dataset_id"], False),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_user_decision"), ["user_decision"], False),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_trace_id"), ["trace_id"], False),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_parent_run_id"), ["parent_run_id"], False),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_error_code"), ["error_code"], False),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_created_at"), ["created_at"], False),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_updated_at"), ["updated_at"], False),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_decided_at"), ["decided_at"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_parent_agent"), ["parent_agent"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_child_agent"), ["child_agent"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_child_run_id"), ["child_run_id"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_dataset_id"), ["dataset_id"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_task_id"), ["task_id"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_trace_id"), ["trace_id"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_checkpoint_ref"), ["checkpoint_ref"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_artifact_ref"), ["artifact_ref"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_handoff_status"), ["handoff_status"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_error_code"), ["error_code"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_created_at"), ["created_at"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_updated_at"), ["updated_at"], False),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_completed_at"), ["completed_at"], False),
    ]:
        _create_index_if_missing(table_name, index_name, columns, unique=unique)


def downgrade() -> None:
    for table_name, index_name in [
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_completed_at")),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_updated_at")),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_created_at")),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_error_code")),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_handoff_status")),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_artifact_ref")),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_checkpoint_ref")),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_trace_id")),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_task_id")),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_dataset_id")),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_child_run_id")),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_child_agent")),
        ("bi_agent_handoff", op.f("ix_bi_agent_handoff_parent_agent")),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_decided_at")),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_updated_at")),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_created_at")),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_error_code")),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_parent_run_id")),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_trace_id")),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_user_decision")),
        ("bi_lead_agent_confirmation", op.f("ix_bi_lead_agent_confirmation_dataset_id")),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_completed_at")),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_updated_at")),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_created_at")),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_error_code")),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_trace_id")),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_task_id")),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_phase")),
        ("bi_lead_agent_run", op.f("ix_bi_lead_agent_run_status")),
    ]:
        _drop_index_if_exists(table_name, index_name)

    for table_name in ["bi_agent_handoff", "bi_lead_agent_confirmation", "bi_lead_agent_run"]:
        if _has_table(table_name):
            op.drop_table(table_name)
