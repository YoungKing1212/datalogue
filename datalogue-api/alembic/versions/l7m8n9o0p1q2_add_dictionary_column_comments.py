# ============================================================
# File Name   : l7m8n9o0p1q2_add_dictionary_column_comments.py
# Description:
#   更新数据库字典字段注释。
#
# Responsibilities:
#   - 为状态、类型、角色等字典字段补充 code 与中文含义。
#   - 兼容已有库中表或字段不存在的情况，迁移时跳过缺失项。
#
# Author      : yangkai
# Created On  : 2026-06-22
# ============================================================

"""add_dictionary_column_comments

Revision ID: l7m8n9o0p1q2
Revises: k6l7m8n9o0p1
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "l7m8n9o0p1q2"
down_revision: Union[str, None] = "k6l7m8n9o0p1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DICT_COLUMN_COMMENTS: list[tuple[str, str, str]] = [
    ("conversation", "archived", "是否已归档。字典：true=已归档；false=未归档"),
    ("datasource", "db_type", "数据库类型。字典：postgres=PostgreSQL；mysql=MySQL；sqlite=SQLite；sqlserver=SQL Server；oracle=Oracle；clickhouse=ClickHouse；hive=Hive；trino=Trino；bigquery=BigQuery"),
    ("datasource", "status", "连接状态。字典：connected=已连接；disconnected=未连接；syncing=同步中；error=连接异常"),
    ("datasource", "dialect", "SQL 方言。字典：postgresql=PostgreSQL 方言；mysql=MySQL 方言；sqlite=SQLite 方言；tsql=SQL Server T-SQL 方言；oracle=Oracle 方言；clickhouse=ClickHouse 方言；hive=Hive 方言；trino=Trino 方言；bigquery=BigQuery 方言"),
    ("semantic_dataset", "status", "数据集状态。字典：draft=草稿；active=已启用；deprecated=已废弃"),
    ("message", "role", "消息角色。字典：user=用户消息；assistant=助手消息；system=系统消息；tool=工具消息"),
    ("semantic_metric", "granularity", "时间粒度。字典：day=日；week=周；month=月；quarter=季度；year=年"),
    ("source_table", "desc_source", "描述来源。字典：ai=AI 生成；user=人工维护；unknown=未知"),
    ("source_table", "status", "源表状态。字典：active=可用；inactive=停用；deleted=已删除"),
    ("source_column", "ai_semantic_role", "AI 建议的语义角色。字典：metric_candidate=指标候选；dimension_candidate=维度候选；time_field=时间字段；identifier=标识字段；attribute=属性字段；ignore=忽略字段"),
    ("source_column", "ai_suggested_agg", "AI 建议的聚合方式。字典：SUM=求和；COUNT=计数；AVG=平均值；MAX=最大值；MIN=最小值；COUNT_DISTINCT=去重计数；NONE=不聚合"),
    ("source_column", "user_semantic_role", "人工指定的语义角色。字典：metric_candidate=指标候选；dimension_candidate=维度候选；time_field=时间字段；identifier=标识字段；attribute=属性字段；ignore=忽略字段"),
    ("source_column", "desc_source", "字段描述来源。字典：ai=AI 生成；user=人工维护；unknown=未知"),
    ("source_column", "review_status", "审核状态。字典：pending_review=待审核；approved=已通过；rejected=已拒绝；converted=已转化"),
    ("source_column", "is_nullable", "是否允许为空。字典：YES=允许为空；NO=不允许为空"),
    ("source_column", "semantic_role", "旧版语义角色。字典：metric_candidate=指标候选；dimension_candidate=维度候选；time_field=时间字段；identifier=标识字段；attribute=属性字段；ignore=忽略字段"),
    ("source_column", "default_agg", "旧版默认聚合方式。字典：SUM=求和；COUNT=计数；AVG=平均值；MAX=最大值；MIN=最小值；COUNT_DISTINCT=去重计数；NONE=不聚合"),
    ("business_term", "term_type", "术语类型。字典：business_object=业务对象；metric=指标；dimension=维度；entity=实体；process=业务过程；rule=业务规则"),
    ("business_term", "status", "术语状态。字典：draft=草稿；active=已启用；deprecated=已废弃"),
    ("business_term", "source", "术语来源。字典：manual=人工维护；ai=AI 生成；import=导入"),
    ("business_term_asset_link", "asset_type", "资产类型。字典：metric=指标；dimension=维度；term=术语；blueprint=分析蓝图；field=物理字段；table=物理表"),
    ("business_term_relation", "relation_type", "术语关系类型。字典：synonym=同义；broader=上位；narrower=下位；related=相关"),
    ("business_term_change_log", "action", "操作类型。字典：create=创建；update=更新；delete=删除；publish=发布；archive=归档"),
    ("semantic_validation_case", "status", "验证状态。字典：pass=通过；fail=失败；unknown=未知"),
    ("semantic_validation_case", "route_type", "问数路由类型。字典：metric_query=指标查询；detail_query=明细查询；analysis_blueprint=分析蓝图；knowledge_qa=知识问答；clarification=澄清；rejection=拒答"),
    ("semantic_validation_case", "entry_intent", "入口意图。字典：chitchat=闲聊；rejection=拒答；analysis_blueprint=分析蓝图；knowledge_qa=知识问答；detail_query=明细查询；metric_query=指标查询；clarification=澄清"),
    ("semantic_validation_case", "entry_route", "入口路由。字典：direct_answer=直接回答；reject=拒答；analysis_blueprint=分析蓝图；knowledge_qa=知识问答；query_graph=问数查询链路；clarify=澄清"),
    ("pending_clarification", "clarification_type", "澄清类型。字典：term_conflict=术语冲突；dataset=数据集选择；generic=通用澄清"),
    ("pending_clarification", "status", "处理状态。字典：pending=待处理；resolved=已解决；expired=已过期"),
    ("analysis_blueprint", "implementation_type", "实现类型。字典：sql_template=SQL 模板；stored_procedure=存储过程；semantic_plan=语义计划"),
    ("analysis_blueprint", "status", "蓝图状态。字典：draft=草稿；active=已启用；deprecated=已废弃"),
    ("analysis_blueprint", "creation_source", "创建来源。字典：manual=人工创建；ai_extract=AI 提取；ai_generate=AI 生成；manual_ai_draft=人工触发的 AI 草稿"),
    ("analysis_blueprint", "ai_generated", "是否由 AI 生成。字典：true=AI 生成；false=人工维护"),
    ("analysis_blueprint", "ai_generation_type", "AI 生成类型。字典：extract=从 SQL 或材料提取；generate=按需求生成；optimize=优化既有蓝图"),
    ("blueprint_usage_log", "execution_success", "是否执行成功。字典：true=执行成功；false=执行失败"),
    ("blueprint_usage_log", "user_feedback", "用户反馈。字典：like=点赞；dislike=点踩"),
    ("llm_model_config", "provider", "模型供应商。字典：litellm=LiteLLM 代理；openai=OpenAI；openai-compatible=OpenAI 兼容接口；litellm_sdk=LiteLLM SDK；anthropic=Anthropic；qwen=通义千问；dashscope=DashScope；aliyun=阿里云"),
    ("llm_model_config", "status", "模型配置状态。字典：active=启用；inactive=停用"),
    ("llm_model_config", "thinking_enabled", "是否开启 Think 模式。字典：true=开启推理过程输出；false=关闭推理过程输出"),
    ("llm_role_binding", "role", "任务角色名。字典：sql_generator=SQL 生成；report_generator=报告生成；intent_router=意图路由；blueprint_analyzer=蓝图分析；annotation=字段标注；lead_agent=LeadAgent 规划"),
    ("observability_trace_index", "entry_route", "问数入口路由类型。字典：direct_answer=直接回答；reject=拒答；analysis_blueprint=分析蓝图；knowledge_qa=知识问答；query_graph=问数查询链路；clarify=澄清；turn_pending=轮次处理中"),
    ("observability_trace_index", "status", "执行状态。字典：success=成功；failed=失败；error=错误；fallback=降级"),
    ("trace_annotation_candidate", "reason", "进入候选池的原因。字典：thumbs_down=用户点踩；error=执行错误；low_quality=低质量；sql_failure=SQL 失败；sql_retry=SQL 重试"),
    ("trace_annotation_candidate", "status", "处理状态。字典：pending=待处理；annotated=已标注；dismissed=已忽略"),
    ("conversation_state", "status", "多轮会话状态。字典：idle=空闲；turn_pending=轮次处理中"),
    ("dataset_subagent_manifest", "is_current", "是否当前生效版本。字典：true=当前版本；false=历史版本"),
    ("dataset_subagent_manifest", "review_status", "Manifest 审核状态。字典：draft=草稿；current=当前生效；needs_review=待复核；archived=已归档"),
    ("query_artifact", "kind", "产物类型。字典：sql_result=SQL 执行结果；report=报告内容；subagent_result=SubAgent 结果；debug=调试信息"),
]


_ROLLBACK_COLUMN_COMMENTS: dict[tuple[str, str], str] = {
    (table, column): comment.split("。字典：", 1)[0]
    for table, column, comment in _DICT_COLUMN_COMMENTS
}


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _apply_column_comments(comments: list[tuple[str, str, str]]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table, column, comment in comments:
        if table not in existing_tables:
            continue
        existing_columns = {item["name"] for item in inspector.get_columns(table)}
        if column not in existing_columns:
            continue
        escaped_comment = comment.replace("'", "''")
        bind.execute(
            sa.text(
                f"COMMENT ON COLUMN {_quote_ident(table)}.{_quote_ident(column)} "
                f"IS '{escaped_comment}'"
            )
        )


def upgrade() -> None:
    _apply_column_comments(_DICT_COLUMN_COMMENTS)


def downgrade() -> None:
    _apply_column_comments(
        [
            (table, column, comment)
            for (table, column), comment in _ROLLBACK_COLUMN_COMMENTS.items()
        ]
    )
