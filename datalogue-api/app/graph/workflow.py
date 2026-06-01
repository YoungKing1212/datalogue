# LangGraph 工作流组装 — NL2DSL2SQL 状态图

from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, END
from typing import Any

from app.graph.state import AgentState
from app.graph.nodes import (
    intent_recognition_node,
    schema_recall_node,
    dsl_generate_node,
    dsl_validate_node,
    dsl_compiler_node,
    sql_execute_node,
    report_generator_node,
)


def _should_continue(state: AgentState) -> str:
    """判断意图识别后应该走向哪个分支。"""
    intent = state.get("intent")
    if intent == "chitchat":
        return "end"
    return "schema_recall"


def _dsl_validation_router(state: AgentState) -> str:
    """DSL 校验通过则编译，失败则重试或结束。"""
    if state.get("dsl_valid"):
        return "compile"
    retry = state.get("retry_count", 0)
    if retry < 3:
        return "retry"
    return "end"


def _sql_execution_router(state: AgentState) -> str:
    """SQL 执行成功则生成报告，失败则重试或结束。"""
    if not state.get("should_retry"):
        return "report"
    retry = state.get("retry_count", 0)
    if retry < 3:
        return "retry"
    return "end"


def _increment_retry(state: AgentState) -> dict:
    """重试计数器 +1。"""
    return {"retry_count": state.get("retry_count", 0) + 1}


def build_workflow(db: Session) -> Any:
    """构建并返回编译好的 NL2DSL2SQL StateGraph。

    调用方通过 db 参数传入 SQLAlchemy Session，用于 Schema 召回和 SQL 执行。
    """
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("intent_recognition", intent_recognition_node)
    workflow.add_node("schema_recall", schema_recall_node(db))
    workflow.add_node("dsl_generate", dsl_generate_node)
    workflow.add_node("dsl_validate", dsl_validate_node)
    workflow.add_node("dsl_compiler", dsl_compiler_node)
    workflow.add_node("sql_execute", sql_execute_node(db))
    workflow.add_node("report_generator", report_generator_node)
    workflow.add_node("increment_retry", _increment_retry)

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
            "retry": "increment_retry",
            "end": END,
        },
    )

    # 报告生成 → 结束
    workflow.add_edge("report_generator", END)

    return workflow.compile()
