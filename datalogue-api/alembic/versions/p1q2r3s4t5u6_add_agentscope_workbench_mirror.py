# ============================================================
# File Name   : p1q2r3s4t5u6_add_agentscope_workbench_mirror.py
# Description:
#   新增 C3 AgentScope 工作台本地镜像表。
#
# Responsibilities:
#   - 创建 session/message/event/ref 四张镜像表。
#   - 为 Workbench View Model 和受控 retry 提供可追溯状态索引。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

"""add_agentscope_workbench_mirror

Revision ID: p1q2r3s4t5u6
Revises: o0p1q2r3s4t5
Create Date: 2026-06-30 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p1q2r3s4t5u6"
down_revision: Union[str, None] = "o0p1q2r3s4t5"
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
    return {item["name"] for item in sa.inspect(bind).get_indexes(table_name)}


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    if index_name in _existing_index_names(table_name):
        return
    op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    if index_name not in _existing_index_names(table_name):
        return
    op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _has_table("agentscope_session"):
        op.create_table(
            "agentscope_session",
            sa.Column("id", sa.Integer(), nullable=False, comment="主键。"),
            sa.Column(
                "thread_id",
                sa.String(length=80),
                nullable=False,
                comment="C3 统一线程 ID；as_* 为新会话真相源，conv_* 只读历史线程不写入本表。",
            ),
            sa.Column(
                "source_type",
                sa.String(length=40),
                server_default="agentscope",
                nullable=False,
                comment="来源类型；P0 仅写 agentscope。",
            ),
            sa.Column(
                "legacy_conversation_id",
                sa.Integer(),
                nullable=True,
                comment="历史 conversation 只读映射 ID；P0 不迁移旧会话。",
            ),
            sa.Column("title", sa.String(length=200), nullable=True, comment="工作台线程标题。"),
            sa.Column(
                "status",
                sa.String(length=30),
                server_default="active",
                nullable=False,
                comment="线程状态：active、archived、read_only。",
            ),
            sa.Column(
                "metadata_json",
                _json_type(),
                server_default=_json_default(),
                nullable=False,
                comment="线程业务级扩展信息；禁止保存 SQL/schema/raw rows。",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="创建时间。"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="更新时间。"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("thread_id", name="uq_agentscope_session_thread_id"),
            comment="AgentScope 工作台 session 镜像表，新会话的会话真相源。",
        )
    if not _has_table("agentscope_message"):
        op.create_table(
            "agentscope_message",
            sa.Column("id", sa.Integer(), nullable=False, comment="主键。"),
            sa.Column("message_id", sa.String(length=80), nullable=False, comment="AgentScope-compatible 消息 ID。"),
            sa.Column("thread_id", sa.String(length=80), nullable=False, comment="所属 as_* 工作台线程。"),
            sa.Column("role", sa.String(length=20), nullable=False, comment="消息角色：user、assistant、tool、system。"),
            sa.Column(
                "status",
                sa.String(length=30),
                server_default="created",
                nullable=False,
                comment="消息状态：created、running、completed、failed、interrupted。",
            ),
            sa.Column("content_summary", sa.Text(), nullable=True, comment="用户可见业务摘要，不保存内部执行明细。"),
            sa.Column(
                "business_payload_json",
                _json_type(),
                server_default=_json_default(),
                nullable=False,
                comment="业务级消息载荷；禁止保存 raw SQL、schema、raw result。",
            ),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True, comment="assistant running lease 到期时间。"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="创建时间。"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="更新时间。"),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True, comment="完成、失败或中断时间。"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("message_id", name="uq_agentscope_message_message_id"),
            comment="AgentScope 工作台 message 镜像表，记录 Chat turn 的用户消息和 assistant 状态。",
        )
    if not _has_table("agentscope_event"):
        op.create_table(
            "agentscope_event",
            sa.Column("id", sa.Integer(), nullable=False, comment="主键。"),
            sa.Column("event_id", sa.String(length=80), nullable=False, comment="事件 ID。"),
            sa.Column("thread_id", sa.String(length=80), nullable=False, comment="所属 as_* 工作台线程。"),
            sa.Column("message_id", sa.String(length=80), nullable=True, comment="关联消息 ID。"),
            sa.Column("event_type", sa.String(length=80), nullable=False, comment="Datalogue event envelope 投影后的事件类型。"),
            sa.Column("task_id", sa.String(length=120), nullable=True, comment="业务任务 ID。"),
            sa.Column("trace_id", sa.String(length=120), nullable=True, comment="Langfuse / observability trace ID。"),
            sa.Column(
                "payload_json",
                _json_type(),
                server_default=_json_default(),
                nullable=False,
                comment="事件业务级 payload；user visibility 不允许写内部调试内容。",
            ),
            sa.Column(
                "visibility",
                sa.String(length=20),
                server_default="user",
                nullable=False,
                comment="可见性：user、admin、trace_only。",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="事件创建时间。"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("event_id", name="uq_agentscope_event_event_id"),
            comment="AgentScope 工作台 event 镜像表，承接 SSE/event envelope 的产品化时间线。",
        )
    if not _has_table("agentscope_ref"):
        op.create_table(
            "agentscope_ref",
            sa.Column("id", sa.Integer(), nullable=False, comment="主键。"),
            sa.Column("thread_id", sa.String(length=80), nullable=False, comment="所属 as_* 工作台线程。"),
            sa.Column("message_id", sa.String(length=80), nullable=True, comment="关联消息 ID。"),
            sa.Column("ref_type", sa.String(length=40), nullable=False, comment="引用类型：artifact、checkpoint、trace、repair_plan。"),
            sa.Column("ref_value", sa.String(length=200), nullable=False, comment="稳定 ref 句柄，如 artifact:<uuid>。"),
            sa.Column("relation", sa.String(length=40), nullable=False, comment="关系：primary、related、checkpoint、trace。"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="引用关系创建时间。"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "thread_id",
                "message_id",
                "ref_type",
                "ref_value",
                "relation",
                name="uq_agentscope_ref_thread_message_ref_relation",
            ),
            comment="AgentScope 工作台 ref 关系表，保存消息与 artifact/checkpoint/trace 的业务级引用。",
        )

    _create_index_if_missing("agentscope_session", op.f("ix_agentscope_session_id"), ["id"])
    _create_index_if_missing("agentscope_session", op.f("ix_agentscope_session_thread_id"), ["thread_id"], unique=True)
    _create_index_if_missing("agentscope_session", op.f("ix_agentscope_session_source_type"), ["source_type"])
    _create_index_if_missing("agentscope_session", op.f("ix_agentscope_session_legacy_conversation_id"), ["legacy_conversation_id"])
    _create_index_if_missing("agentscope_session", op.f("ix_agentscope_session_status"), ["status"])
    _create_index_if_missing("agentscope_session", op.f("ix_agentscope_session_created_at"), ["created_at"])
    _create_index_if_missing("agentscope_session", op.f("ix_agentscope_session_updated_at"), ["updated_at"])

    _create_index_if_missing("agentscope_message", op.f("ix_agentscope_message_id"), ["id"])
    _create_index_if_missing("agentscope_message", op.f("ix_agentscope_message_message_id"), ["message_id"], unique=True)
    _create_index_if_missing("agentscope_message", op.f("ix_agentscope_message_thread_id"), ["thread_id"])
    _create_index_if_missing("agentscope_message", op.f("ix_agentscope_message_role"), ["role"])
    _create_index_if_missing("agentscope_message", op.f("ix_agentscope_message_status"), ["status"])
    _create_index_if_missing("agentscope_message", op.f("ix_agentscope_message_lease_expires_at"), ["lease_expires_at"])
    _create_index_if_missing("agentscope_message", op.f("ix_agentscope_message_created_at"), ["created_at"])
    _create_index_if_missing("agentscope_message", op.f("ix_agentscope_message_updated_at"), ["updated_at"])
    _create_index_if_missing("agentscope_message", op.f("ix_agentscope_message_completed_at"), ["completed_at"])

    _create_index_if_missing("agentscope_event", op.f("ix_agentscope_event_id"), ["id"])
    _create_index_if_missing("agentscope_event", op.f("ix_agentscope_event_event_id"), ["event_id"], unique=True)
    _create_index_if_missing("agentscope_event", op.f("ix_agentscope_event_thread_id"), ["thread_id"])
    _create_index_if_missing("agentscope_event", op.f("ix_agentscope_event_message_id"), ["message_id"])
    _create_index_if_missing("agentscope_event", op.f("ix_agentscope_event_event_type"), ["event_type"])
    _create_index_if_missing("agentscope_event", op.f("ix_agentscope_event_task_id"), ["task_id"])
    _create_index_if_missing("agentscope_event", op.f("ix_agentscope_event_trace_id"), ["trace_id"])
    _create_index_if_missing("agentscope_event", op.f("ix_agentscope_event_visibility"), ["visibility"])
    _create_index_if_missing("agentscope_event", op.f("ix_agentscope_event_created_at"), ["created_at"])

    _create_index_if_missing("agentscope_ref", op.f("ix_agentscope_ref_id"), ["id"])
    _create_index_if_missing("agentscope_ref", op.f("ix_agentscope_ref_thread_id"), ["thread_id"])
    _create_index_if_missing("agentscope_ref", op.f("ix_agentscope_ref_message_id"), ["message_id"])
    _create_index_if_missing("agentscope_ref", op.f("ix_agentscope_ref_ref_type"), ["ref_type"])
    _create_index_if_missing("agentscope_ref", op.f("ix_agentscope_ref_ref_value"), ["ref_value"])
    _create_index_if_missing("agentscope_ref", op.f("ix_agentscope_ref_relation"), ["relation"])


def downgrade() -> None:
    for index_name, table_name in [
        (op.f("ix_agentscope_ref_relation"), "agentscope_ref"),
        (op.f("ix_agentscope_ref_ref_value"), "agentscope_ref"),
        (op.f("ix_agentscope_ref_ref_type"), "agentscope_ref"),
        (op.f("ix_agentscope_ref_message_id"), "agentscope_ref"),
        (op.f("ix_agentscope_ref_thread_id"), "agentscope_ref"),
        (op.f("ix_agentscope_ref_id"), "agentscope_ref"),
        (op.f("ix_agentscope_event_created_at"), "agentscope_event"),
        (op.f("ix_agentscope_event_visibility"), "agentscope_event"),
        (op.f("ix_agentscope_event_trace_id"), "agentscope_event"),
        (op.f("ix_agentscope_event_task_id"), "agentscope_event"),
        (op.f("ix_agentscope_event_event_type"), "agentscope_event"),
        (op.f("ix_agentscope_event_message_id"), "agentscope_event"),
        (op.f("ix_agentscope_event_thread_id"), "agentscope_event"),
        (op.f("ix_agentscope_event_event_id"), "agentscope_event"),
        (op.f("ix_agentscope_event_id"), "agentscope_event"),
        (op.f("ix_agentscope_message_completed_at"), "agentscope_message"),
        (op.f("ix_agentscope_message_updated_at"), "agentscope_message"),
        (op.f("ix_agentscope_message_created_at"), "agentscope_message"),
        (op.f("ix_agentscope_message_lease_expires_at"), "agentscope_message"),
        (op.f("ix_agentscope_message_status"), "agentscope_message"),
        (op.f("ix_agentscope_message_role"), "agentscope_message"),
        (op.f("ix_agentscope_message_thread_id"), "agentscope_message"),
        (op.f("ix_agentscope_message_message_id"), "agentscope_message"),
        (op.f("ix_agentscope_message_id"), "agentscope_message"),
        (op.f("ix_agentscope_session_updated_at"), "agentscope_session"),
        (op.f("ix_agentscope_session_created_at"), "agentscope_session"),
        (op.f("ix_agentscope_session_status"), "agentscope_session"),
        (op.f("ix_agentscope_session_legacy_conversation_id"), "agentscope_session"),
        (op.f("ix_agentscope_session_source_type"), "agentscope_session"),
        (op.f("ix_agentscope_session_thread_id"), "agentscope_session"),
        (op.f("ix_agentscope_session_id"), "agentscope_session"),
    ]:
        _drop_index_if_exists(table_name, index_name)
    for table_name in ["agentscope_ref", "agentscope_event", "agentscope_message", "agentscope_session"]:
        if _has_table(table_name):
            op.drop_table(table_name)
