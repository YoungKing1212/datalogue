# ============================================================
# File Name   : workflow.py
# Description:
#   NL2SQL 图工作流装配模块。
#
# Responsibilities:
#   - 连接图节点和条件跳转。
#   - 暴露编译后的工作流执行入口。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# LangGraph 工作流组装 — NL2DSL2SQL 状态图

from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, END
from typing import Any

import logging

from app.graph.state import AgentState

logger = logging.getLogger(__name__)

DEFAULT_MAX_SQL_RETRY_COUNT = 3
from app.graph.nodes import (
    clarification_resolution_node,
    lead_agent_node,
    analysis_blueprint_execute_node,
    schema_recall_node,
    term_normalize_node,
    semantic_asset_resolution_node,
    dsl_generate_node,
    dsl_validate_node,
    dsl_compiler_node,
    sql_execute_node,
    sql_audit_node,
    report_generator_node,
)


def _clarification_resolution_router(state: AgentState) -> str:
    """澄清回复解析后决定恢复查询或直接结束。

    Phase 3 简化：意图识别已由 LeadAgent `route_query_intent` 在 chat.py 完成，
    本节点不再回退到 `intent_recognition` 节点（已删除）。
    """
    status = (state.get("clarification_resolution_result") or {}).get("status")
    if status == "resolved":
        return "schema_recall"
    if status in {"missing", "expired", "unresolved"}:
        return "end"
    return "schema_recall"


def _lead_agent_router(state: AgentState) -> str:
    """LeadAgent 入口节点路由器（Phase 3）：按 state["entry_route"] 路由后续分支。

    入口路由决策由 chat.py 通过 `route_query_intent` 一次性产出，写入 initial_state。
    LangGraph `lead_agent` 节点本身是 noop，仅保留 SSE 事件可见性。
    """
    if state.get("entry_route") == "interpret_result":
        return "end"
    if state.get("entry_route") == "analysis_blueprint":
        return "analysis_blueprint_execute"
    return "clarification_resolution"


def _should_skip_subagent_report(state: AgentState) -> bool:
    """LeadAgent 自动路由场景由 LeadAgent 接管报告生成。"""

    explicit = state.get("skip_subagent_report")
    if explicit is not None:
        return bool(explicit)
    route_decision = state.get("route_decision") or (state.get("lead_agent_context") or {}).get("route_decision") or {}
    return route_decision.get("decision") == "selected"


def _analysis_blueprint_execution_router(state: AgentState) -> str:
    """分析蓝图执行后分流。

    SQL 模板蓝图执行成功后生成报告；手动语义计划蓝图不要求可执行 SQL，
    而是带着蓝图上下文回到 QueryGraph 继续做 Schema 召回和 NL2SQL。
    """
    if state.get("generation_mode") == "analysis_blueprint_semantic":
        return "schema_recall"
    if state.get("sql_result") is not None:
        if _should_skip_subagent_report(state):
            return "end"
        return "report"
    return "end"


def _term_normalization_router(state: AgentState) -> str:
    """业务术语归一化后路由；冲突术语必须先澄清。"""
    route_payload = state.get("route_payload") or {}
    if route_payload.get("kind") == "term_conflict_clarification":
        return "end"
    return "semantic_asset_resolution"


def _dsl_validation_router(state: AgentState) -> str:
    """DSL 校验通过则编译，失败则重试或结束。
    若节点已标记 should_retry=False（不可恢复错误），直接结束。"""
    if state.get("dsl_valid"):
        return "compile"
    if state.get("should_retry") is False:
        return "end"
    retry = state.get("retry_count", 0)
    max_retry = state.get("max_retry_count", DEFAULT_MAX_SQL_RETRY_COUNT)
    if retry < max_retry:
        return "retry"
    return "end"


def _sql_execution_router(state: AgentState) -> str:
    """SQL 执行成功则生成报告；失败时路由到 sql_audit（Agent 智能审计）。
    审计后再决定是重试还是直接结束。

    - 无 sql_result 且 should_retry=False → END（避免 report 收到空结果）
    - 有 sql_result → report
    - 失败（should_retry=True）→ audit
    """
    if not state.get("should_retry"):
        if state.get("sql_result") is None:
            return "end"
        if _should_skip_subagent_report(state):
            return "end"
        return "report"
    # SQL 失败 → 进 sql_audit（不再直接 increment_retry，让 audit 决定）
    return "audit"


def _sql_audit_router(state: AgentState) -> str:
    """SQL 审计后路由。
    - retryable=False：权限、表未选、语义层缺字段等硬性问题 → END
    - retry_count 已用尽（>= max_retry_count） → END
    - retryable=True → increment_retry → dsl_generate
    """
    audit = state.get("sql_audit_result") or {}
    if audit.get("retryable") is False or audit.get("severity") == "architectural":
        return "end"
    retry = state.get("retry_count", 0)
    max_retry = state.get("max_retry_count", DEFAULT_MAX_SQL_RETRY_COUNT)
    if retry >= max_retry:
        return "end"
    return "retry"


def _increment_retry(state: AgentState) -> dict:
    """重试计数器 +1。"""
    return {"retry_count": state.get("retry_count", 0) + 1}


def build_workflow(db: Session) -> Any:
    """构建并返回编译好的 NL2DSL2SQL StateGraph。

    调用方通过 db 参数传入 SQLAlchemy Session，用于 Schema 召回和 SQL 执行。
    """
    workflow = StateGraph(AgentState)
    logger.info("开始构建LangGraph工作流")

    # 注册节点（Phase 3 改造：删 intent_recognition / entry_intent_classification / merge_prior_context，
    # 合并为 lead_agent 入口）
    workflow.add_node("lead_agent", lead_agent_node)
    workflow.add_node("clarification_resolution", clarification_resolution_node(db))
    workflow.add_node("analysis_blueprint_execute", analysis_blueprint_execute_node(db))
    workflow.add_node("schema_recall", schema_recall_node(db))
    workflow.add_node("term_normalize_node", term_normalize_node)
    workflow.add_node("semantic_asset_resolution_node", semantic_asset_resolution_node)
    workflow.add_node("dsl_generate", lambda state: dsl_generate_node(state, db=db))
    workflow.add_node("dsl_validate", dsl_validate_node)
    # dsl_compiler 现在是工厂函数（接 db 以查 Datasource.db_type 推断方言）
    workflow.add_node("dsl_compiler", dsl_compiler_node(db))
    workflow.add_node("sql_execute", sql_execute_node(db))
    workflow.add_node("sql_audit", sql_audit_node(db))
    async def _report_generator_with_db(state: AgentState) -> dict:
        return await report_generator_node(state, db=db)

    workflow.add_node("report_generator", _report_generator_with_db)
    workflow.add_node("increment_retry", _increment_retry)
    logger.info("工作流节点注册完成")

    # 设置入口（Phase 3：LeadAgent 总入口）
    workflow.set_entry_point("lead_agent")
    workflow.add_conditional_edges(
        "lead_agent",
        _lead_agent_router,
        {
            "clarification_resolution": "clarification_resolution",
            "analysis_blueprint_execute": "analysis_blueprint_execute",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "clarification_resolution",
        _clarification_resolution_router,
        {
            "schema_recall": "schema_recall",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "analysis_blueprint_execute",
        _analysis_blueprint_execution_router,
        {
            "schema_recall": "schema_recall",
            "report": "report_generator",
            "end": END,
        },
    )

    # Schema 召回 → 术语归一化 → 语义资产解析 → DSL 生成
    workflow.add_edge("schema_recall", "term_normalize_node")
    workflow.add_conditional_edges(
        "term_normalize_node",
        _term_normalization_router,
        {
            "semantic_asset_resolution": "semantic_asset_resolution_node",
            "end": END,
        },
    )
    workflow.add_edge("semantic_asset_resolution_node", "dsl_generate")

    # DSL 生成 → DSL 校验
    workflow.add_edge("dsl_generate", "dsl_validate")

    # DSL 校验分支
    workflow.add_conditional_edges(
        "dsl_validate",
        _dsl_validation_router,
        {
            "compile": "dsl_compiler",
            "retry": "increment_retry",
            "end": END,
        },
    )

    # 重试后回到 DSL 生成
    workflow.add_edge("increment_retry", "dsl_generate")

    # DSL 编译 → SQL 执行
    workflow.add_edge("dsl_compiler", "sql_execute")

    # SQL 执行分支
    workflow.add_conditional_edges(
        "sql_execute",
        _sql_execution_router,
        {
            "report": "report_generator",
            "audit": "sql_audit",
            "end": END,
        },
    )

    # SQL 审计分支：architectural 走 END，fixable 走 increment_retry
    workflow.add_conditional_edges(
        "sql_audit",
        _sql_audit_router,
        {
            "retry": "increment_retry",
            "end": END,
        },
    )

    # 报告生成 → 结束
    workflow.add_edge("report_generator", END)

    logger.info("工作流编译完成")
    return workflow.compile()
