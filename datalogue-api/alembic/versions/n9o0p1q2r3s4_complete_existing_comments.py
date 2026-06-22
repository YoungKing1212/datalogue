# ============================================================
# File Name   : n9o0p1q2r3s4_complete_existing_comments.py
# Description:
#   补齐当前数据库中缺失的表和字段中文注释。
#
# Responsibilities:
#   - 为 Alembic、LangGraph checkpoint、源表目录、多轮状态和查询产物表补齐注释。
#   - 迁移前检查表和字段是否存在，兼容不同环境的历史结构差异。
#
# Author      : yangkai
# Created On  : 2026-06-22
# ============================================================

"""complete_existing_comments

Revision ID: n9o0p1q2r3s4
Revises: m8n9o0p1q2r3
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "n9o0p1q2r3s4"
down_revision: Union[str, None] = "m8n9o0p1q2r3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_COMMENTS: list[tuple[str, str]] = [
    ("alembic_version", "Alembic 数据库迁移版本表"),
    ("checkpoint_blobs", "LangGraph checkpoint 二进制大字段存储表"),
    ("checkpoint_migrations", "LangGraph checkpoint 迁移版本表"),
    ("checkpoint_writes", "LangGraph checkpoint 写入记录表"),
    ("checkpoints", "LangGraph checkpoint 状态快照表"),
]


_COLUMN_COMMENTS: list[tuple[str, str, str]] = [
    ("alembic_version", "version_num", "当前已应用的 Alembic 迁移版本号"),
    ("checkpoint_blobs", "thread_id", "LangGraph 线程 ID"),
    ("checkpoint_blobs", "checkpoint_ns", "checkpoint 命名空间"),
    ("checkpoint_blobs", "channel", "checkpoint 通道名"),
    ("checkpoint_blobs", "version", "checkpoint 通道版本"),
    ("checkpoint_blobs", "type", "blob 数据类型"),
    ("checkpoint_blobs", "blob", "序列化后的二进制数据"),
    ("checkpoint_migrations", "v", "LangGraph checkpoint 迁移版本号"),
    ("checkpoint_writes", "thread_id", "LangGraph 线程 ID"),
    ("checkpoint_writes", "checkpoint_ns", "checkpoint 命名空间"),
    ("checkpoint_writes", "checkpoint_id", "checkpoint 快照 ID"),
    ("checkpoint_writes", "task_id", "写入任务 ID"),
    ("checkpoint_writes", "idx", "同一任务内写入序号"),
    ("checkpoint_writes", "channel", "写入通道名"),
    ("checkpoint_writes", "type", "写入载体类型"),
    ("checkpoint_writes", "blob", "写入内容的二进制数据"),
    ("checkpoint_writes", "task_path", "LangGraph 任务路径"),
    ("checkpoints", "thread_id", "LangGraph 线程 ID"),
    ("checkpoints", "checkpoint_ns", "checkpoint 命名空间"),
    ("checkpoints", "checkpoint_id", "checkpoint 快照 ID"),
    ("checkpoints", "parent_checkpoint_id", "父 checkpoint 快照 ID"),
    ("checkpoints", "type", "checkpoint 序列化类型"),
    ("checkpoints", "checkpoint", "checkpoint 状态快照 JSON"),
    ("checkpoints", "metadata", "checkpoint 元数据 JSON"),
    ("conversation_state", "session_id", "业务多轮会话 ID"),
    ("conversation_state", "user_id", "用户 ID"),
    ("conversation_state", "messages", "压缩前后的消息索引"),
    ("conversation_state", "compacted_summary", "长会话压缩摘要"),
    ("conversation_state", "facts", "会话内稳定事实"),
    ("conversation_state", "resolved_time_context", "LeadAgent 最近解析的时间上下文"),
    ("conversation_state", "active_dataset_id", "当前活跃数据集 ID"),
    ("conversation_state", "pending_clarification", "跨轮挂起澄清状态"),
    ("conversation_state", "subagent_capsules", "按数据集分桶的 SubAgent 状态胶囊"),
    ("conversation_state", "turn_index", "已完成轮次"),
    ("conversation_state", "lock_owner", "当前轮锁持有者"),
    ("conversation_state", "locked_until", "轮次锁过期时间"),
    ("conversation_state", "created_at", "创建时间"),
    ("conversation_state", "updated_at", "更新时间"),
    ("dataset_subagent_manifest", "dataset_id", "所属数据集 ID"),
    ("dataset_subagent_manifest", "manifest_version", "Manifest 版本号"),
    ("dataset_subagent_manifest", "bound_schema_version", "绑定的数据集 schema 版本"),
    ("dataset_subagent_manifest", "manifest_json", "Manifest 完整 JSON 定义"),
    ("dataset_subagent_manifest", "created_by", "创建人"),
    ("dataset_subagent_manifest", "created_at", "创建时间"),
    ("dataset_subagent_manifest", "updated_at", "更新时间"),
    ("query_artifact", "id", "主键"),
    ("query_artifact", "artifact_id", "产物唯一标识"),
    ("query_artifact", "dataset_id", "关联的数据集 ID"),
    ("query_artifact", "conversation_id", "关联的会话 ID"),
    ("query_artifact", "message_id", "关联的消息 ID"),
    ("query_artifact", "trace_id", "关联的 Trace ID"),
    ("query_artifact", "content_json", "JSON 格式产物内容"),
    ("query_artifact", "content_text", "文本格式产物内容"),
    ("query_artifact", "content_mime", "产物内容 MIME 类型"),
    ("query_artifact", "size_bytes", "产物大小字节数"),
    ("query_artifact", "expires_at", "产物过期时间"),
    ("query_artifact", "created_at", "创建时间"),
    ("source_column", "id", "主键"),
    ("source_column", "table_id", "所属物理源表 ID"),
    ("source_column", "column_name", "物理字段名"),
    ("source_column", "data_type", "物理字段数据类型"),
    ("source_column", "column_comment", "数据库原始字段注释"),
    ("source_column", "business_desc", "旧版业务字段描述"),
    ("source_column", "column_default", "数据库字段默认值"),
    ("source_column", "ordinal_position", "字段在表内的顺序位置"),
    ("source_column", "sample_values", "字段样例值"),
    ("source_table", "id", "主键"),
    ("source_table", "datasource_id", "所属数据源 ID"),
    ("source_table", "schema_name", "物理 Schema 名称"),
    ("source_table", "table_name", "物理表名"),
    ("source_table", "table_comment", "数据库原始表注释"),
    ("source_table", "business_desc", "旧版业务表描述"),
    ("source_table", "row_count_approx", "近似行数"),
    ("source_table", "synced_at", "最近同步时间"),
    ("source_table", "created_at", "创建时间"),
    ("source_table", "updated_at", "更新时间"),
]


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _apply_table_comments(comments: list[tuple[str, str | None]]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table, comment in comments:
        if table not in existing_tables:
            continue
        if comment is None:
            bind.execute(sa.text(f"COMMENT ON TABLE {_quote_ident(table)} IS NULL"))
            continue
        escaped_comment = comment.replace("'", "''")
        bind.execute(
            sa.text(f"COMMENT ON TABLE {_quote_ident(table)} IS '{escaped_comment}'")
        )


def _apply_column_comments(comments: list[tuple[str, str, str | None]]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table, column, comment in comments:
        if table not in existing_tables:
            continue
        existing_columns = {item["name"] for item in inspector.get_columns(table)}
        if column not in existing_columns:
            continue
        if comment is None:
            bind.execute(
                sa.text(f"COMMENT ON COLUMN {_quote_ident(table)}.{_quote_ident(column)} IS NULL")
            )
            continue
        escaped_comment = comment.replace("'", "''")
        bind.execute(
            sa.text(
                f"COMMENT ON COLUMN {_quote_ident(table)}.{_quote_ident(column)} "
                f"IS '{escaped_comment}'"
            )
        )


def upgrade() -> None:
    _apply_table_comments(_TABLE_COMMENTS)
    _apply_column_comments(_COLUMN_COMMENTS)


def downgrade() -> None:
    _apply_column_comments(
        [(table, column, None) for table, column, _ in _COLUMN_COMMENTS]
    )
    _apply_table_comments([(table, None) for table, _ in _TABLE_COMMENTS])
