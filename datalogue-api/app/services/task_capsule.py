# ============================================================
# File Name   : task_capsule.py
# Description:
#   多轮问数任务胶囊，把线程记忆转成 SubAgent 可消费的最小上下文。
#
# Responsibilities:
#   - 保存上一轮成功查询的结构化摘要。
#   - 生成第二轮追问的 standalone question 和基础查询约束。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder


def has_query_target(task: dict[str, Any] | None) -> bool:
    """判断任务是否已经具备可继续执行的查询目标。"""

    if not isinstance(task, dict):
        return False
    query_type = task.get("query_type")
    if query_type == "detail_query":
        return bool(
            task.get("fields")
            or task.get("main_table")
            or task.get("query_plan")
            or task.get("dsl")
        )
    return bool(task.get("metrics"))


def _result_digest(sql_result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(sql_result, dict):
        return {"row_count": 0, "columns": [], "sample_rows": []}
    rows = sql_result.get("rows") or []
    return {
        "row_count": int(sql_result.get("row_count") or len(rows)),
        "columns": list(sql_result.get("columns") or []),
        "sample_rows": jsonable_encoder(rows[:5]),
    }


def _selected_main_table(query_plan: dict[str, Any], dsl: dict[str, Any]) -> Any:
    debug = query_plan.get("debug") if isinstance(query_plan.get("debug"), dict) else {}
    return (
        debug.get("selected_main_table")
        or query_plan.get("main_table")
        or dsl.get("main_table")
    )


def build_success_task_state(
    *,
    question: str,
    dataset_id: int | None,
    query_plan: dict[str, Any] | None,
    dsl: dict[str, Any] | None,
    sql: str | None,
    sql_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """构造上一轮成功查询的可复用任务状态。"""

    plan = query_plan or {}
    dsl_payload = dsl or {}
    return {
        "question": question,
        "dataset_id": dataset_id,
        "query_type": plan.get("query_type"),
        "main_table": _selected_main_table(plan, dsl_payload),
        "query_plan": plan,
        "dsl": dsl_payload,
        "fields": dsl_payload.get("fields") or [],
        "metrics": dsl_payload.get("metrics") or [],
        "sql": sql,
        "result_digest": _result_digest(sql_result),
    }


def build_query_task_capsule(
    *,
    question: str,
    turn_event: dict[str, Any],
    active_dataset_id: int | None,
    last_success_task: dict[str, Any] | None,
) -> dict[str, Any]:
    """把当前轮事件和上一轮成功任务合成 SubAgent 可消费的查询胶囊。"""

    event = turn_event if isinstance(turn_event, dict) else {}
    event_type = event.get("event_type") or "new_query"
    capsule = {
        "task_type": "query",
        "turn_type": event_type,
        "dataset_id": active_dataset_id,
        "question": question,
        "standalone_question": question,
        "base_task_ref": None,
        "base_main_table": None,
        "base_query_plan": None,
    }
    can_inherit = (
        event_type == "followup_refine"
        and isinstance(last_success_task, dict)
        and active_dataset_id is not None
        and last_success_task.get("dataset_id") == active_dataset_id
        and has_query_target(last_success_task)
    )
    if can_inherit:
        prior_question = last_success_task.get("question") or ""
        capsule.update(
            {
                "standalone_question": f"基于上一轮问题「{prior_question}」，{question}",
                "base_task_ref": "last_success_task",
                "base_main_table": last_success_task.get("main_table"),
                "base_query_plan": last_success_task.get("query_plan"),
            }
        )
    return capsule
