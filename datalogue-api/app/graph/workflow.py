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
from app.graph.nodes import (
    intent_recognition_node,
    schema_recall_node,
    metric_resolution_node,
    dsl_generate_node,
    dsl_validate_node,
    dsl_compiler_node,
    sql_execute_node,
    sql_audit_node,
    report_generator_node,
)


def _should_continue(state: AgentState) -> str:
    """判断意图识别后应该走向哪个分支。"""
    intent = state.get("intent")
    if intent == "chitchat":
        return "end"
    return "schema_recall"


def _dsl_validation_router(state: AgentState) -> str:
    """DSL 校验通过则编译，失败则重试或结束。
    若节点已标记 should_retry=False（不可恢复错误），直接结束。"""
    if state.get("dsl_valid"):
        return "compile"
    if state.get("should_retry") is False:
        return "end"
    retry = state.get("retry_count", 0)
    if retry < 3:
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
        return "report"
    # SQL 失败 → 进 sql_audit（不再直接 increment_retry，让 audit 决定）
    return "audit"


def _sql_audit_router(state: AgentState) -> str:
    """SQL 审计后路由。
    - architectural：数据集配置错误，LLM 无法修复 → END
    - retry_count 已用尽（>= 3） → END
    - 其他（fixable） → increment_retry → dsl_generate
    """
    audit = state.get("sql_audit_result") or {}
    if audit.get("severity") == "architectural":
        return "end"
    retry = state.get("retry_count", 0)
    if retry >= 3:
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

    # 注册节点
    workflow.add_node("intent_recognition", intent_recognition_node)
    workflow.add_node("schema_recall", schema_recall_node(db))
    workflow.add_node("metric_resolution_node", metric_resolution_node)
    workflow.add_node("dsl_generate", dsl_generate_node)
    workflow.add_node("dsl_validate", dsl_validate_node)
    # dsl_compiler 现在是工厂函数（接 db 以查 Datasource.db_type 推断方言）
    workflow.add_node("dsl_compiler", dsl_compiler_node(db))
    workflow.add_node("sql_execute", sql_execute_node(db))
    workflow.add_node("sql_audit", sql_audit_node(db))
    workflow.add_node("report_generator", report_generator_node)
    workflow.add_node("increment_retry", _increment_retry)
    logger.info("工作流节点注册完成")

    # 设置入口
    workflow.set_entry_point("intent_recognition")

    # 意图识别分支：闲聊直接结束，查询继续
    workflow.add_conditional_edges(
        "intent_recognition",
        _should_continue,
        {
            "end": END,
            "schema_recall": "schema_recall",
        },
    )

    # Schema 召回 → 指标解析 → DSL 生成
    workflow.add_edge("schema_recall", "metric_resolution_node")
    workflow.add_edge("metric_resolution_node", "dsl_generate")

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
