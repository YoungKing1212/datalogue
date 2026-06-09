# ============================================================
# File Name   : state.py
# Description:
#   图工作流执行状态类型定义。
#
# Responsibilities:
#   - 定义节点之间传递的共享状态字段。
#   - 说明 NL2SQL 处理链路携带的数据。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# AgentState — LangGraph 工作流全局状态定义

from typing import Any, TypedDict, Optional, List


class AgentState(TypedDict):
    """NL2DSL2SQL 工作流状态，贯穿 IntentRecognition → ReportGenerator 全链路。"""

    # 输入层
    question: str  # 用户原始问题
    dataset_id: Optional[int]  # 指定数据集（可选）
    conversation_id: Optional[int]  # 当前会话 ID，用于诊断日志关联
    history: Optional[List[dict]]  # 历史对话消息（最近 N 轮）

    # 意图识别层
    intent: Optional[str]  # query | chitchat | function
    entities: Optional[dict]  # {"metrics": [], "dimensions": [], "time_range": {}}
    entry_intent: Optional[
        str
    ]  # metric_query | detail_query | analysis_blueprint | knowledge_qa | clarification | rejection
    entry_route: Optional[
        str
    ]  # query_graph | analysis_blueprint | knowledge_qa | clarify | reject | direct_answer
    entry_reason: Optional[str]  # 入口分类理由，供审计和前端展示
    blueprint_id: Optional[int]  # 命中的分析蓝图 ID
    blueprint_match: Optional[dict]  # 蓝图匹配详情 {"name": str, "score": int, ...}
    blueprint_context: Optional[str]  # 手动语义蓝图注入 QueryGraph 的业务计划上下文
    knowledge_term_id: Optional[int]  # 命中的知识库业务术语 ID
    # 非 QueryGraph 路由需要返回给前端的结构化数据
    route_payload: Optional[dict[str, Any]]

    # Schema 召回层
    schema_context: Optional[str]  # 召回的语义层描述文本
    schema_structured: Optional[dict]  # 结构化语义层配置（供编译器使用）
    ddl_context: Optional[str]  # 当前数据集所选表的真实 DDL
    query_constraints: Optional[dict]  # SQL 生成默认时间范围和默认 LIMIT 等结构化约束
    dataset_context_debug: Optional[dict]  # 数据集问数上下文组装调试摘要
    generation_mode: Optional[str]  # "semantic" | "inferred" — 供前端显示徽标
    term_normalization: Optional[dict]  # 业务术语归一化结果，含命中同义词和冲突澄清
    semantic_asset_resolution: Optional[dict]  # 术语/指标/维度/字段/蓝图统一资产解析结果
    metric_resolution: Optional[dict]  # 指标/维度解析结果，供意图卡和审计
    # 数据集级 LLM 约束（硬性要求）— schema_recall_node 写入，report_generator 等
    # 不读 schema_context 的节点直接从这里取
    dataset_prompt_instructions: Optional[str]

    # DSL 层
    dsl: Optional[dict]  # 结构化 DSL JSON
    dsl_valid: bool  # DSL 校验是否通过

    # SQL 层
    sql: Optional[str]  # 编译后的 SQL
    sql_result: Optional[dict]  # 查询结果 {"columns": [], "rows": []}
    datasource_dialect: Optional[str]  # 实际执行 SQL 的数据源方言

    # 输出层
    answer: Optional[str]  # 最终自然语言回答
    answer_explanation: Optional[dict]  # 回答口径、来源、SQL 摘要、置信度和风险解释包
    sql_list: List[str]  # 本轮执行的所有 SQL

    # 控制层
    error: Optional[str]  # 错误信息（用于重试）
    retry_count: int  # 当前重试次数
    max_retry_count: int  # 本轮 SQL 自动修复最多重试次数
    should_retry: bool  # 是否触发重试
    sql_retry_trace: Optional[List[dict]]  # SQL 自动修复重试记录，含原 SQL、修复原因和结果

    # SQL 审计（sql_audit_node 写入）：区分 fixable（可重试） / architectural（需用户改数据集）
    # 注意：节点名是 "sql_audit"，state 字段必须用不同名（LangGraph 禁止同名）
    sql_audit_result: Optional[
        dict
    ]  # {"root_cause": str, "wrong_field": str, "suggested_fix": str, "severity": "fixable"|"architectural"}
    sql_diagnosis: Optional[dict]  # SQL 执行失败的结构化诊断，供前端和日志使用

    # 可观测性
    token_usage: Optional[
        dict
    ]  # 累积 Token 用量 {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
