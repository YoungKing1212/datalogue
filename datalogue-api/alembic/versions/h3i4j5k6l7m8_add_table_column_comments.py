# ============================================================
# File Name   : h3i4j5k6l7m8_add_table_column_comments.py
# Description:
#   为所有已存在的数据表和字段追加中文注释。
#
# Responsibilities:
#   - 通过 COMMENT ON TABLE/COLUMN 为存量表补充中文描述。
#   - 不涉及表结构变更，降级时清空注释。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

"""add_table_column_comments

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-06-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "h3i4j5k6l7m8"
down_revision: Union[str, None] = "g2h3i4j5k6l7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_COMMENTS: list[tuple[str, str]] = [
    ("conversation",                  "用户会话表"),
    ("datasource",                    "数据源连接配置表"),
    ("semantic_dataset",              "语义数据集表"),
    ("message",                       "会话消息表"),
    ("semantic_dimension",            "语义维度表"),
    ("semantic_metric",               "语义指标表"),
    ("source_table",                  "物理源表元数据目录"),
    ("source_column",                 "物理源字段元数据目录"),
    ("dataset_source_table",          "数据集与物理源表关联表"),
    ("business_term",                 "业务术语表"),
    ("business_term_asset_link",      "业务术语与语义资产关联表"),
    ("business_term_relation",        "业务术语关系表"),
    ("business_term_change_log",      "业务术语变更日志表"),
    ("analysis_blueprint",            "分析蓝图表"),
    ("blueprint_version",             "分析蓝图版本快照表"),
    ("blueprint_usage_log",           "分析蓝图执行日志表"),
    ("semantic_validation_case",      "语义验证用例表"),
    ("pending_clarification",         "待处理术语澄清表"),
    ("llm_model_config",              "LLM 模型配置表"),
    ("llm_role_binding",              "LLM 角色绑定表"),
    ("sql_diagnosis_log",             "SQL 执行失败诊断日志表"),
    ("observability_trace_index",     "可观测性 Trace 本地索引表"),
    ("trace_annotation_candidate",    "Trace 人工标注候选池表"),
]

_COLUMN_COMMENTS: list[tuple[str, str, str]] = [
    # conversation
    ("conversation", "id",         "主键"),
    ("conversation", "agent_id",   "代理 ID"),
    ("conversation", "title",      "会话标题"),
    ("conversation", "thread_id",  "LangGraph 线程 ID"),
    ("conversation", "user_id",    "用户 ID"),
    ("conversation", "dataset_id", "会话绑定的语义数据集 ID"),
    ("conversation", "archived",   "是否已归档"),
    ("conversation", "created_at", "创建时间"),
    ("conversation", "updated_at", "更新时间"),

    # datasource
    ("datasource", "id",                      "主键"),
    ("datasource", "name",                    "数据源名称"),
    ("datasource", "db_type",                 "数据库类型（mysql/postgres等）"),
    ("datasource", "host",                    "主机地址"),
    ("datasource", "port",                    "端口号"),
    ("datasource", "database_name",           "数据库名"),
    ("datasource", "username",                "连接用户名"),
    ("datasource", "password_enc",            "加密存储的连接密码"),
    ("datasource", "status",                  "连接状态（connected/disconnected）"),
    ("datasource", "dialect",                 "SQL 方言（mysql/postgres/tsql等）"),
    ("datasource", "driver",                  "数据库驱动名（pymysql/psycopg2等）"),
    ("datasource", "default_schema",          "默认 Schema 名称"),
    ("datasource", "connection_options",      "扩展连接选项"),
    ("datasource", "connect_timeout_seconds", "连接超时秒数"),
    ("datasource", "query_timeout_seconds",   "查询超时秒数"),
    ("datasource", "last_test_result",        "最近连通性测试结果"),
    ("datasource", "last_error_code",         "最近错误码"),
    ("datasource", "last_error_message",      "最近错误信息"),
    ("datasource", "created_at",              "创建时间"),
    ("datasource", "updated_at",              "更新时间"),

    # semantic_dataset
    ("semantic_dataset", "id",                   "主键"),
    ("semantic_dataset", "name",                 "数据集名称"),
    ("semantic_dataset", "datasource_id",        "所属数据源 ID"),
    ("semantic_dataset", "tables_json",          "关联物理表信息 JSON"),
    ("semantic_dataset", "description",          "数据集描述"),
    ("semantic_dataset", "status",               "数据集状态"),
    ("semantic_dataset", "prompt_instructions",  "数据集级 LLM 约束指令，问数时拼入 schema_context"),
    ("semantic_dataset", "query_constraints",    "SQL 生成查询约束（默认时间范围、LIMIT 等）"),
    ("semantic_dataset", "created_at",           "创建时间"),
    ("semantic_dataset", "updated_at",           "更新时间"),

    # message
    ("message", "id",                "主键"),
    ("message", "conversation_id",   "所属会话 ID"),
    ("message", "role",              "消息角色（user/assistant）"),
    ("message", "content",           "消息文本内容"),
    ("message", "sql_list",          "生成的 SQL 列表"),
    ("message", "report_html",       "报告 HTML 内容"),
    ("message", "token_usage",       "token 用量统计"),
    ("message", "step_trace",        "LangGraph 工作流执行步骤轨迹"),
    ("message", "response_metadata", "回答元数据（解释包、可视化提示等）"),
    ("message", "created_at",        "创建时间"),

    # semantic_dimension
    ("semantic_dimension", "id",           "主键"),
    ("semantic_dimension", "dataset_id",   "所属数据集 ID"),
    ("semantic_dimension", "name",         "维度英文名"),
    ("semantic_dimension", "display_name", "维度显示名称"),
    ("semantic_dimension", "column_name",  "对应物理列名"),
    ("semantic_dimension", "enum_values",  "枚举值列表"),
    ("semantic_dimension", "synonyms",     "同义词列表"),
    ("semantic_dimension", "table_name",   "维度所属物理表名"),
    ("semantic_dimension", "join_to",      "关联目标表名"),
    ("semantic_dimension", "join_key",     "关联键列名"),
    ("semantic_dimension", "hierarchy",    "层级结构定义"),

    # semantic_metric
    ("semantic_metric", "id",           "主键"),
    ("semantic_metric", "dataset_id",   "所属数据集 ID"),
    ("semantic_metric", "name",         "指标英文名"),
    ("semantic_metric", "display_name", "指标显示名称"),
    ("semantic_metric", "expr",         "聚合计算表达式"),
    ("semantic_metric", "filter_sql",   "过滤条件 SQL"),
    ("semantic_metric", "synonyms",     "同义词列表"),
    ("semantic_metric", "description",  "指标描述"),
    ("semantic_metric", "table_name",   "指标所属物理表名"),
    ("semantic_metric", "time_field",   "时间字段列名"),
    ("semantic_metric", "granularity",  "时间粒度（day/week/month等）"),
    ("semantic_metric", "format_str",   "数值格式化模板"),

    # source_table
    ("source_table", "ai_description",  "AI 生成的表描述"),
    ("source_table", "user_description","人工填写的表描述"),
    ("source_table", "effective_desc",  "最终生效的表描述（人工优先）"),
    ("source_table", "desc_source",     "描述来源（ai/user/unknown）"),
    ("source_table", "annotated_at",    "最近标注时间"),

    # source_column
    ("source_column", "ai_description",         "AI 生成的字段描述"),
    ("source_column", "ai_semantic_role",        "AI 建议的语义角色（metric/dimension/time等）"),
    ("source_column", "ai_suggested_agg",        "AI 建议的聚合方式（sum/count/avg等）"),
    ("source_column", "user_description",        "人工填写的字段描述"),
    ("source_column", "user_semantic_role",      "人工指定的语义角色"),
    ("source_column", "effective_desc",          "最终生效的字段描述（人工优先）"),
    ("source_column", "desc_source",             "描述来源（ai/user/unknown）"),
    ("source_column", "annotated_at",            "最近标注时间"),
    ("source_column", "ai_confidence",           "AI 分析置信度"),
    ("source_column", "ai_reason",               "AI 分析理由"),
    ("source_column", "suggested_synonyms",      "AI 建议的同义词列表"),
    ("source_column", "suggested_enum_values",   "AI 建议的枚举值列表"),
    ("source_column", "review_status",           "审核状态（pending_review/approved/rejected等）"),
    ("source_column", "converted_metric_id",     "已转化的语义指标 ID"),
    ("source_column", "converted_dimension_id",  "已转化的语义维度 ID"),
    ("source_column", "reviewed_at",             "审核完成时间"),

    # dataset_source_table
    ("dataset_source_table", "id",              "主键"),
    ("dataset_source_table", "dataset_id",      "语义数据集 ID"),
    ("dataset_source_table", "source_table_id", "物理源表 ID"),
    ("dataset_source_table", "created_at",      "创建时间"),

    # business_term
    ("business_term", "id",             "主键"),
    ("business_term", "dataset_id",     "所属数据集 ID"),
    ("business_term", "name",           "术语英文名"),
    ("business_term", "display_name",   "术语显示名称"),
    ("business_term", "term_type",      "术语类型（metric/dimension/entity等）"),
    ("business_term", "definition",     "术语定义说明"),
    ("business_term", "aliases",        "同义词/别名列表"),
    ("business_term", "forbidden_aliases", "禁用别名列表"),
    ("business_term", "examples",       "使用示例列表"),
    ("business_term", "owner",          "术语负责人"),
    ("business_term", "status",         "状态（active/deprecated等）"),
    ("business_term", "source",         "来源（manual/ai）"),
    ("business_term", "confidence",     "AI 生成置信度"),
    ("business_term", "extra_metadata", "扩展元数据"),
    ("business_term", "created_at",     "创建时间"),
    ("business_term", "updated_at",     "更新时间"),

    # business_term_asset_link
    ("business_term_asset_link", "id",         "主键"),
    ("business_term_asset_link", "term_id",    "关联的业务术语 ID"),
    ("business_term_asset_link", "asset_type", "资产类型（metric/dimension）"),
    ("business_term_asset_link", "asset_id",   "资产主键 ID"),
    ("business_term_asset_link", "asset_name", "资产名称快照"),
    ("business_term_asset_link", "created_at", "创建时间"),

    # business_term_relation
    ("business_term_relation", "id",             "主键"),
    ("business_term_relation", "dataset_id",     "所属数据集 ID"),
    ("business_term_relation", "source_term_id", "源术语 ID"),
    ("business_term_relation", "target_term_id", "目标术语 ID"),
    ("business_term_relation", "relation_type",  "关系类型（synonym/broader/narrower等）"),
    ("business_term_relation", "note",           "关系说明备注"),
    ("business_term_relation", "created_at",     "创建时间"),

    # business_term_change_log
    ("business_term_change_log", "id",              "主键"),
    ("business_term_change_log", "term_id",         "关联的业务术语 ID"),
    ("business_term_change_log", "action",          "操作类型（create/update/delete等）"),
    ("business_term_change_log", "before_snapshot", "变更前术语快照"),
    ("business_term_change_log", "after_snapshot",  "变更后术语快照"),
    ("business_term_change_log", "actor",           "操作人"),
    ("business_term_change_log", "created_at",      "创建时间"),

    # analysis_blueprint
    ("analysis_blueprint", "id",                 "主键"),
    ("analysis_blueprint", "dataset_id",         "所属数据集 ID"),
    ("analysis_blueprint", "name",               "蓝图名称"),
    ("analysis_blueprint", "description",        "蓝图描述"),
    ("analysis_blueprint", "trigger_keywords",   "触发关键词列表"),
    ("analysis_blueprint", "trigger_examples",   "触发示例问题列表"),
    ("analysis_blueprint", "when_to_use",        "适用场景说明"),
    ("analysis_blueprint", "parameters",         "参数定义"),
    ("analysis_blueprint", "implementation_type","实现类型（sql/api等）"),
    ("analysis_blueprint", "call_template",      "调用模板"),
    ("analysis_blueprint", "output_schema",      "输出结构定义"),
    ("analysis_blueprint", "timeout_seconds",    "执行超时秒数"),
    ("analysis_blueprint", "steps",              "执行步骤定义"),
    ("analysis_blueprint", "attribution_hints",  "归因提示文本"),
    ("analysis_blueprint", "raw_sql",            "原始 SQL 模板"),
    ("analysis_blueprint", "status",             "蓝图状态（active/draft/deprecated）"),
    ("analysis_blueprint", "version",            "版本号"),
    ("analysis_blueprint", "ai_confidence",      "AI 生成置信度"),
    ("analysis_blueprint", "owner",              "负责人"),
    ("analysis_blueprint", "last_validated_at",  "最近验证时间"),
    ("analysis_blueprint", "usage_count",        "累计使用次数"),
    ("analysis_blueprint", "last_test_result",   "最近测试结果"),
    ("analysis_blueprint", "creation_source",    "创建来源（manual/ai_extract/ai_generate等）"),
    ("analysis_blueprint", "ai_generated",       "是否由 AI 生成"),
    ("analysis_blueprint", "ai_generation_type", "AI 生成类型（extract/generate等）"),
    ("analysis_blueprint", "created_at",         "创建时间"),
    ("analysis_blueprint", "updated_at",         "更新时间"),

    # blueprint_version
    ("blueprint_version", "id",             "主键"),
    ("blueprint_version", "blueprint_id",   "所属蓝图 ID"),
    ("blueprint_version", "version",        "版本号"),
    ("blueprint_version", "snapshot",       "蓝图完整快照"),
    ("blueprint_version", "change_summary", "变更摘要"),
    ("blueprint_version", "published_by",   "发布人"),
    ("blueprint_version", "published_at",   "发布时间"),

    # blueprint_usage_log
    ("blueprint_usage_log", "id",                "主键"),
    ("blueprint_usage_log", "blueprint_id",      "关联蓝图 ID"),
    ("blueprint_usage_log", "question",          "触发蓝图的用户问题"),
    ("blueprint_usage_log", "extracted_params",  "从问题中提取的参数"),
    ("blueprint_usage_log", "execution_success", "是否执行成功"),
    ("blueprint_usage_log", "execution_time_ms", "执行耗时（毫秒）"),
    ("blueprint_usage_log", "user_feedback",     "用户反馈（like/dislike）"),
    ("blueprint_usage_log", "error_message",     "执行失败的错误信息"),
    ("blueprint_usage_log", "row_count",         "本次执行返回的数据行数"),
    ("blueprint_usage_log", "diagnosis",         "结构化失败诊断信息"),
    ("blueprint_usage_log", "created_at",        "创建时间"),

    # semantic_validation_case
    ("semantic_validation_case", "id",            "主键"),
    ("semantic_validation_case", "dataset_id",    "所属数据集 ID"),
    ("semantic_validation_case", "question",      "测试问题文本"),
    ("semantic_validation_case", "status",        "验证状态（pass/fail/unknown）"),
    ("semantic_validation_case", "route_type",    "问数路由类型"),
    ("semantic_validation_case", "entry_intent",  "识别出的入口意图"),
    ("semantic_validation_case", "entry_route",   "识别出的入口路由"),
    ("semantic_validation_case", "blueprint_id",  "关联的分析蓝图 ID"),
    ("semantic_validation_case", "sql",           "生成的 SQL"),
    ("semantic_validation_case", "answer",        "回答内容"),
    ("semantic_validation_case", "error",         "执行错误信息"),
    ("semantic_validation_case", "report",        "报告数据快照"),
    ("semantic_validation_case", "created_by",    "创建人"),
    ("semantic_validation_case", "created_at",    "创建时间"),
    ("semantic_validation_case", "updated_at",    "更新时间"),

    # pending_clarification
    ("pending_clarification", "id",                "主键"),
    ("pending_clarification", "conversation_id",   "所属会话 ID"),
    ("pending_clarification", "dataset_id",        "关联的数据集 ID"),
    ("pending_clarification", "clarification_type","澄清类型（term_conflict等）"),
    ("pending_clarification", "status",            "处理状态（pending/resolved/expired）"),
    ("pending_clarification", "original_question", "触发澄清的原始问题"),
    ("pending_clarification", "conflict_payload",  "冲突信息载体"),
    ("pending_clarification", "candidates",        "供用户选择的候选项列表"),
    ("pending_clarification", "expires_at",        "澄清过期时间"),
    ("pending_clarification", "resolved_at",       "澄清解决时间"),
    ("pending_clarification", "selected_payload",  "用户最终选择的载体"),
    ("pending_clarification", "created_at",        "创建时间"),

    # llm_model_config
    ("llm_model_config", "id",                       "主键"),
    ("llm_model_config", "name",                     "配置名称"),
    ("llm_model_config", "provider",                 "供应商（litellm/openai等）"),
    ("llm_model_config", "base_url",                 "API 基础地址"),
    ("llm_model_config", "model",                    "模型标识符"),
    ("llm_model_config", "api_key_enc",              "加密存储的 API 密钥"),
    ("llm_model_config", "status",                   "状态（active/inactive）"),
    ("llm_model_config", "description",              "配置描述"),
    ("llm_model_config", "request_timeout_seconds",  "请求超时秒数"),
    ("llm_model_config", "thinking_enabled",         "是否开启 Think 模式（输出推理过程）"),
    ("llm_model_config", "last_test_result",         "最近连通性测试结果"),
    ("llm_model_config", "last_error_message",       "最近错误信息"),
    ("llm_model_config", "created_at",               "创建时间"),
    ("llm_model_config", "updated_at",               "更新时间"),

    # llm_role_binding
    ("llm_role_binding", "id",              "主键"),
    ("llm_role_binding", "role",            "任务角色名（sql_generator/report_generator等）"),
    ("llm_role_binding", "model_config_id", "绑定的模型配置 ID"),
    ("llm_role_binding", "created_at",      "创建时间"),
    ("llm_role_binding", "updated_at",      "更新时间"),

    # sql_diagnosis_log
    ("sql_diagnosis_log", "id",              "主键"),
    ("sql_diagnosis_log", "conversation_id", "关联的会话 ID"),
    ("sql_diagnosis_log", "dataset_id",      "关联的数据集 ID"),
    ("sql_diagnosis_log", "question",        "触发 SQL 的用户问题"),
    ("sql_diagnosis_log", "sql",             "执行失败的 SQL"),
    ("sql_diagnosis_log", "error",           "数据库返回的错误信息"),
    ("sql_diagnosis_log", "diagnosis",       "结构化诊断结果"),
    ("sql_diagnosis_log", "retry_count",     "已重试次数"),
    ("sql_diagnosis_log", "created_at",      "创建时间"),

    # observability_trace_index
    ("observability_trace_index", "id",                  "主键"),
    ("observability_trace_index", "langfuse_trace_id",   "Langfuse Trace ID"),
    ("observability_trace_index", "langfuse_session_id", "Langfuse Session ID"),
    ("observability_trace_index", "conversation_id",     "关联的会话 ID"),
    ("observability_trace_index", "message_id",          "关联的消息 ID"),
    ("observability_trace_index", "dataset_id",          "关联的数据集 ID"),
    ("observability_trace_index", "entry_route",         "问数入口路由类型"),
    ("observability_trace_index", "status",              "执行状态（success/error等）"),
    ("observability_trace_index", "total_tokens",        "本次请求总 token 消耗"),
    ("observability_trace_index", "total_cost",          "本次请求总费用"),
    ("observability_trace_index", "metadata_json",       "扩展元数据"),
    ("observability_trace_index", "created_at",          "创建时间"),

    # trace_annotation_candidate
    ("trace_annotation_candidate", "id",                  "主键"),
    ("trace_annotation_candidate", "langfuse_trace_id",   "Langfuse Trace ID"),
    ("trace_annotation_candidate", "conversation_id",     "关联的会话 ID"),
    ("trace_annotation_candidate", "message_id",          "关联的消息 ID"),
    ("trace_annotation_candidate", "dataset_id",          "关联的数据集 ID"),
    ("trace_annotation_candidate", "reason",              "进入候选池的原因（thumbs_down/error/low_quality等）"),
    ("trace_annotation_candidate", "status",              "处理状态（pending/annotated/dismissed）"),
    ("trace_annotation_candidate", "payload",             "附加数据载体"),
    ("trace_annotation_candidate", "created_at",          "创建时间"),
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = __import__("sqlalchemy").inspect(conn)
    existing_tables = set(inspector.get_table_names())

    for table, comment in _TABLE_COMMENTS:
        if table not in existing_tables:
            continue
        escaped = comment.replace("'", "''")
        conn.execute(__import__("sqlalchemy").text(
            f"COMMENT ON TABLE {table} IS '{escaped}'"
        ))

    for table, column, comment in _COLUMN_COMMENTS:
        if table not in existing_tables:
            continue
        existing_cols = {col["name"] for col in inspector.get_columns(table)}
        if column not in existing_cols:
            continue
        escaped = comment.replace("'", "''")
        conn.execute(__import__("sqlalchemy").text(
            f"COMMENT ON COLUMN {table}.{column} IS '{escaped}'"
        ))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = __import__("sqlalchemy").inspect(conn)
    existing_tables = set(inspector.get_table_names())

    for table, _ in _TABLE_COMMENTS:
        if table not in existing_tables:
            continue
        conn.execute(__import__("sqlalchemy").text(
            f"COMMENT ON TABLE {table} IS NULL"
        ))

    for table, column, _ in _COLUMN_COMMENTS:
        if table not in existing_tables:
            continue
        existing_cols = {col["name"] for col in inspector.get_columns(table)}
        if column not in existing_cols:
            continue
        conn.execute(__import__("sqlalchemy").text(
            f"COMMENT ON COLUMN {table}.{column} IS NULL"
        ))
