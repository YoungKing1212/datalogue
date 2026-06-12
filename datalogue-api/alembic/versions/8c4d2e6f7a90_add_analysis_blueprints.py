# ============================================================
# File Name   : 8c4d2e6f7a90_add_analysis_blueprints.py
# Description:
#   增加分析蓝图相关持久化表。
#
# Responsibilities:
#   - 创建蓝图、版本和执行日志表。
#   - 支持分析蓝图治理表结构回滚。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""add_analysis_blueprints

Revision ID: 8c4d2e6f7a90
Revises: 7f1a2b3c4d5e
Create Date: 2026-06-05 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c4d2e6f7a90"
down_revision: Union[str, None] = "7f1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_blueprint",
        sa.Column("id", sa.Integer(), nullable=False, comment='主键'),
        sa.Column("dataset_id", sa.Integer(), nullable=False, comment='所属数据集 ID'),
        sa.Column("name", sa.String(length=100), nullable=False, comment='蓝图名称'),
        sa.Column("description", sa.Text(), nullable=True, comment='蓝图描述'),
        sa.Column("trigger_keywords", sa.JSON(), nullable=True, comment='触发关键词列表'),
        sa.Column("trigger_examples", sa.JSON(), nullable=True, comment='触发示例问题列表'),
        sa.Column("when_to_use", sa.Text(), nullable=True, comment='适用场景说明'),
        sa.Column("parameters", sa.JSON(), nullable=True, comment='参数定义'),
        sa.Column("implementation_type", sa.String(length=30), nullable=True, comment='实现类型（sql/api等）'),
        sa.Column("call_template", sa.Text(), nullable=True, comment='调用模板'),
        sa.Column("output_schema", sa.JSON(), nullable=True, comment='输出结构定义'),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True, comment='执行超时秒数'),
        sa.Column("steps", sa.JSON(), nullable=True, comment='执行步骤定义'),
        sa.Column("attribution_hints", sa.Text(), nullable=True, comment='归因提示文本'),
        sa.Column("raw_sql", sa.Text(), nullable=True, comment='原始 SQL 模板'),
        sa.Column("status", sa.String(length=20), nullable=False, comment='蓝图状态（active/draft/deprecated）'),
        sa.Column("version", sa.Integer(), nullable=False, comment='版本号'),
        sa.Column("ai_confidence", sa.Float(), nullable=True, comment='AI 生成置信度'),
        sa.Column("owner", sa.String(length=50), nullable=True, comment='负责人'),
        sa.Column("last_validated_at", sa.DateTime(), nullable=True, comment='最近验证时间'),
        sa.Column("usage_count", sa.Integer(), nullable=False, comment='累计使用次数'),
        sa.Column("last_test_result", sa.JSON(), nullable=True, comment='最近测试结果'),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment='创建时间'),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment='更新时间'),
        sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment='分析蓝图表',
    )
    op.create_index(op.f("ix_analysis_blueprint_id"), "analysis_blueprint", ["id"], unique=False)
    op.create_index(
        "ix_analysis_blueprint_dataset_status",
        "analysis_blueprint",
        ["dataset_id", "status"],
        unique=False,
    )

    op.create_table(
        "blueprint_version",
        sa.Column("id", sa.Integer(), nullable=False, comment='主键'),
        sa.Column("blueprint_id", sa.Integer(), nullable=False, comment='所属蓝图 ID'),
        sa.Column("version", sa.Integer(), nullable=False, comment='版本号'),
        sa.Column("snapshot", sa.JSON(), nullable=False, comment='蓝图完整快照'),
        sa.Column("change_summary", sa.Text(), nullable=True, comment='变更摘要'),
        sa.Column("published_by", sa.String(length=50), nullable=True, comment='发布人'),
        sa.Column("published_at", sa.DateTime(), nullable=True, comment='发布时间'),
        sa.ForeignKeyConstraint(["blueprint_id"], ["analysis_blueprint.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment='分析蓝图版本快照表',
    )
    op.create_index(op.f("ix_blueprint_version_id"), "blueprint_version", ["id"], unique=False)
    op.create_index(
        "ix_blueprint_version_blueprint_version",
        "blueprint_version",
        ["blueprint_id", "version"],
        unique=False,
    )

    op.create_table(
        "blueprint_usage_log",
        sa.Column("id", sa.Integer(), nullable=False, comment='主键'),
        sa.Column("blueprint_id", sa.Integer(), nullable=False, comment='关联蓝图 ID'),
        sa.Column("question", sa.Text(), nullable=True, comment='触发蓝图的用户问题'),
        sa.Column("extracted_params", sa.JSON(), nullable=True, comment='从问题中提取的参数'),
        sa.Column("execution_success", sa.Boolean(), nullable=True, comment='是否执行成功'),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True, comment='执行耗时（毫秒）'),
        sa.Column("user_feedback", sa.String(length=10), nullable=True, comment='用户反馈（like/dislike）'),
        sa.Column("error_message", sa.Text(), nullable=True, comment='执行失败的错误信息'),
        sa.Column("created_at", sa.DateTime(), nullable=True, comment='创建时间'),
        sa.ForeignKeyConstraint(["blueprint_id"], ["analysis_blueprint.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment='分析蓝图执行日志表',
    )
    op.create_index(op.f("ix_blueprint_usage_log_id"), "blueprint_usage_log", ["id"], unique=False)
    op.create_index(
        "ix_blueprint_usage_log_blueprint_created",
        "blueprint_usage_log",
        ["blueprint_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_blueprint_usage_log_blueprint_created", table_name="blueprint_usage_log")
    op.drop_index(op.f("ix_blueprint_usage_log_id"), table_name="blueprint_usage_log")
    op.drop_table("blueprint_usage_log")
    op.drop_index("ix_blueprint_version_blueprint_version", table_name="blueprint_version")
    op.drop_index(op.f("ix_blueprint_version_id"), table_name="blueprint_version")
    op.drop_table("blueprint_version")
    op.drop_index("ix_analysis_blueprint_dataset_status", table_name="analysis_blueprint")
    op.drop_index(op.f("ix_analysis_blueprint_id"), table_name="analysis_blueprint")
    op.drop_table("analysis_blueprint")
