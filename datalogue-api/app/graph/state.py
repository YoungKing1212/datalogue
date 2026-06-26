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
    question: str  # 当前工作问题；LeadAgent 解析后优先使用 resolved_question
    original_question: Optional[str]  # 用户原始问题
    resolved_question: Optional[str]  # LeadAgent 控制面解析后的问题文本
    dataset_id: Optional[int]  # 指定数据集（可选）
    manifest_version: Optional[str]  # 本轮绑定的 SubAgent Manifest 版本
    bound_schema_version: Optional[str]  # 本轮 Manifest 绑定的数据集 schema hash
    time_context: Optional[dict[str, Any]]  # LeadAgent TimeTool 解析出的时间上下文
    thread_context: Optional[dict[str, Any]]  # LeadAgent ThreadContextTool 会话锁定快照
    route_decision: Optional[dict[str, Any]]  # LeadAgent/Manifest 路由决策快照
    schema_status: Optional[dict[str, Any]]  # LeadAgent SchemaStatusTool schema stale 检查结果
    lead_agent_context: Optional[dict[str, Any]]  # LeadAgent 控制面工具完整上下文
    skip_subagent_report: bool  # 是否跳过 SubAgent 报告生成，由 LeadAgent 接管最终报告
    report_owner: str  # subagent | lead_agent
    subagent_report_skipped: bool  # 本轮是否实际跳过了 SubAgent 报告节点
    lead_agent_report: Optional[dict[str, Any]]  # LeadAgent 报告生成结果摘要
    conversation_id: Optional[int]  # 当前会话 ID，用于诊断日志关联
    history: Optional[List[dict]]  # 历史对话消息（最近 N 轮）
    clarification_response: Optional[dict]  # 用户对上一轮澄清的结构化回复
    clarification_resolution_result: Optional[dict]  # 澄清解析结果和 pending 状态（节点名 clarification_resolution 与此字段不同名，符合 LangGraph 要求）
    prior_capsule: Optional[dict[str, Any]]  # 上一轮 SubAgent 输出胶囊，用于数据面多轮上下文合并
    prior_capsule_status: Optional[dict[str, Any]]  # 上一轮胶囊加载/作废状态，供审计和观测使用
    out_capsule: Optional[dict[str, Any]]  # 本轮 SubAgent 输出胶囊，供下一轮继续追问
    multiturn_context: Optional[dict[str, Any]]  # 多轮合并后的查询上下文和本轮 delta 摘要
    turn_type: Optional[str]  # new | continue，本轮是否承接上一轮查询
    merge_debug: Optional[dict[str, Any]]  # 多轮上下文合并调试信息

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
    selected_term_id: Optional[int]  # 澄清后确认使用的业务术语 ID
    # 非 QueryGraph 路由需要返回给前端的结构化数据
    route_payload: Optional[dict[str, Any]]

    # Schema 召回层
    schema_context: Optional[str]  # 召回的语义层描述文本
    schema_structured: Optional[dict]  # 结构化语义层配置（供编译器使用）
    ddl_context: Optional[str]  # 当前数据集所选表的真实 DDL
    query_constraints: Optional[dict]  # SQL 生成默认时间范围和默认 LIMIT 等结构化约束
    dataset_context_debug: Optional[dict]  # 数据集问数上下文组装调试摘要
    datasource_context: Optional[dict]  # 规范化数据源上下文，包含 db_type/dialect/授权表/超时
    generation_mode: Optional[str]  # "semantic" | "inferred" — 供前端显示徽标
    term_normalization: Optional[dict]  # 业务术语归一化结果，含命中同义词和冲突澄清
    semantic_asset_resolution: Optional[dict]  # 术语/指标/维度/字段/蓝图统一资产解析结果
    metric_resolution: Optional[dict]  # 指标/维度解析结果，供意图卡和审计
    candidate_assets: Optional[dict]  # SubAgent 统一候选资产召回结果，含 blueprint/metric/dimension/term/field/table
    query_plan: Optional[dict]  # SubAgent 查询规划结果，决定 blueprint_execute/query_graph/clarify 等执行策略
    query_plan_debug: Optional[dict]  # 查询规划调试信息，供 trace 和审计页使用
    query_plan_compilation: Optional[dict]  # 工具编译器产物，SQL 只允许作为执行/trace/artifact 元数据流转
    control_plane: Optional[dict]  # 控制面执行元数据，不进入 LLM prompt
    query_artifact: Optional[dict]  # 查询产物元数据，供多轮和审计引用
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
    execution_source: Optional[str]  # SQL 来源，例如 tool_compiler

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
    schema_tokens: Optional[int]  # schema_context 部分的估算 token 数，用于 prompt 压缩监控
