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

from app.core.config import get_settings
from app.graph.nodes import (
    lead_agent_node,
    schema_recall_node,
    dsl_generate_node,
    dsl_validate_node,
    dsl_compiler_node,
    sql_execute_node,
    sql_audit_node,
    repair_patch_node,
    report_generator_node,
)
from app.graph.state import AgentState

logger = logging.getLogger(__name__)

DEFAULT_MAX_SQL_RETRY_COUNT = 3
REPAIR_PATCH_FAILURE_CLASSES = {"FIELD_NOT_FOUND", "FIELD_MAPPING_DRIFT"}
REPAIR_PATCH_GRAPH_NODE = "repair_patch_step"


def _sql_max_retry_count() -> int:
    try:
        value = int(getattr(get_settings(), "SQL_MAX_RETRY_COUNT", DEFAULT_MAX_SQL_RETRY_COUNT))
    except (TypeError, ValueError):
        return DEFAULT_MAX_SQL_RETRY_COUNT
    return value if value > 0 else DEFAULT_MAX_SQL_RETRY_COUNT


def _lead_agent_router(state: AgentState) -> str:
    """LeadAgent 入口节点路由器：按 state["entry_route"] 路由后续分支。

    入口路由决策由 chat.py 通过 `route_query_intent` 一次性产出，写入 initial_state。
    Phase 4: term 澄清已在 chat 层 `resolve_term_clarification` 处理完。
    Phase 5: analysis_blueprint 已在 chat 层 `DatasetSubAgent.resolve_analysis_blueprint` 处理完。
    LangGraph `lead_agent` 节点本身是 noop，仅保留 SSE 事件可见性。
    """
    entry = state.get("entry_route")
    if entry in ("interpret_result", "analysis_blueprint"):
        return "end"
    if entry == "analysis_blueprint_execute":  # 兼容旧值（不应出现）
        return "end"
    if entry == "analysis_blueprint_semantic_execute":  # 兼容旧值
        return "schema_recall"
    return "schema_recall"


def _should_skip_subagent_report(state: AgentState) -> bool:
    """LeadAgent 自动路由场景由 LeadAgent 接管报告生成。"""

    explicit = state.get("skip_subagent_report")
    if explicit is not None:
        return bool(explicit)
    route_decision = state.get("route_decision") or (state.get("lead_agent_context") or {}).get("route_decision") or {}
    return route_decision.get("decision") == "selected"


def _dsl_validation_router(state: AgentState) -> str:
    """DSL 校验通过则编译，失败则重试或结束。
    若节点已标记 should_retry=False（不可恢复错误），直接结束。"""
    if state.get("dsl_valid"):
        return "compile"
    if state.get("should_retry") is False:
        return "end"
    retry = state.get("retry_count", 0)
    max_retry = state.get("max_retry_count", _sql_max_retry_count())
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
    - C2 可修复字段漂移 → RepairPatch → dsl_compiler → sql_execute
    - 其他 retryable=True → increment_retry → dsl_generate
    """
    audit = state.get("sql_audit_result") or {}
    if audit.get("retryable") is False or audit.get("severity") == "architectural":
        return "end"
    retry = state.get("retry_count", 0)
    max_retry = state.get("max_retry_count", _sql_max_retry_count())
    if retry >= max_retry:
        return "end"
    repair_plan = state.get("repair_plan") or {}
    failure_class = (
        repair_plan.get("failure_class")
        or state.get("repair_failure_class")
        or audit.get("code")
    )
    if (
        state.get("repair_status") == "plan_created"
        and failure_class in REPAIR_PATCH_FAILURE_CLASSES
        and isinstance(state.get("query_plan"), dict)
    ):
        return "repair_patch"
    return "retry"


def _repair_patch_router(state: AgentState) -> str:
    """RepairPatch 通过工具编译后继续执行；失败则终止，避免回退到模型 SQL。"""

    compilation = state.get("query_plan_compilation") or {}
    if state.get("repair_status") == "patch_applied" and compilation.get("ok"):
        return "compile"
    return "end"


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
    # 合并为 lead_agent 入口。Phase 4 改造：删 clarification_resolution，由 chat 层 `resolve_term_clarification` 接管。
    # Phase 5 改造：删 analysis_blueprint_execute，由 chat 层 `DatasetSubAgent.resolve_analysis_blueprint` 接管。
    # Phase 6 改造：删 term_normalize_node，由 chat 层 `DatasetSubAgent.resolve_term_conflict` 接管。
    # Phase 7 改造：删 semantic_asset_resolution_node，由 chat 层 `DatasetSubAgent.resolve_metric` 接管。
    # 当前 LangGraph 节点数：9：lead_agent / schema_recall / dsl_generate / dsl_validate / dsl_compiler /
    #   sql_execute / sql_audit / repair_patch_step / report_generator / increment_retry）
    workflow.add_node("lead_agent", lead_agent_node)
    workflow.add_node("schema_recall", schema_recall_node(db))
    workflow.add_node("dsl_generate", lambda state: dsl_generate_node(state, db=db))
    workflow.add_node("dsl_validate", dsl_validate_node)
    # dsl_compiler 现在是工厂函数（接 db 以查 Datasource.db_type 推断方言）
    workflow.add_node("dsl_compiler", dsl_compiler_node(db))
    workflow.add_node("sql_execute", sql_execute_node(db))
    workflow.add_node("sql_audit", sql_audit_node(db))
    # LangGraph 不允许节点名与 AgentState 字段同名；内部节点用 step 后缀，
    # 对外 SSE/Artifact 仍映射为业务节点 repair_patch，保持前端契约稳定。
    workflow.add_node(REPAIR_PATCH_GRAPH_NODE, repair_patch_node(db))
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
            "schema_recall": "schema_recall",
            "end": END,
        },
    )

    # Schema 召回 → DSL 生成
    workflow.add_edge("schema_recall", "dsl_generate")

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

    # SQL 审计分支：C2 字段漂移走 RepairPatch，其余 fixable 保留原 retry 链路。
    workflow.add_conditional_edges(
        "sql_audit",
        _sql_audit_router,
        {
            "repair_patch": REPAIR_PATCH_GRAPH_NODE,
            "retry": "increment_retry",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        REPAIR_PATCH_GRAPH_NODE,
        _repair_patch_router,
        {
            "compile": "dsl_compiler",
            "end": END,
        },
    )

    # 报告生成 → 结束
    workflow.add_edge("report_generator", END)

    logger.info("工作流编译完成")
    return workflow.compile()
