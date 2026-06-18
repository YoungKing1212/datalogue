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

from app.services.multiturn.last_success_task import (
    build_last_success_task,
    evaluate_last_success_task,
    task_has_query_target,
)


def has_query_target(task: dict[str, Any] | None) -> bool:
    """判断任务是否已经具备可继续执行的查询目标。"""

    return task_has_query_target(task)


def build_success_task_state(
    *,
    question: str,
    dataset_id: int | None,
    query_plan: dict[str, Any] | None,
    dsl: dict[str, Any] | None,
    sql: str | None,
    sql_result: dict[str, Any] | None,
    schema_version: str | None = None,
    manifest_version: str | None = None,
    turn_index: int | None = None,
    result_artifact: dict[str, Any] | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """构造上一轮成功查询的可复用任务状态。"""

    return build_last_success_task(
        question=question,
        dataset_id=dataset_id,
        query_plan=query_plan,
        dsl=dsl,
        sql=sql,
        sql_result=sql_result,
        schema_version=schema_version,
        manifest_version=manifest_version,
        turn_index=turn_index,
        result_artifact=result_artifact,
        **({"max_tokens": max_tokens} if max_tokens is not None else {}),
    )


def build_query_task_capsule(
    *,
    question: str,
    turn_event: dict[str, Any],
    active_dataset_id: int | None,
    last_success_task: dict[str, Any] | None,
    last_success_task_status: dict[str, Any] | None = None,
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
        "base_question": None,
        "base_main_table": None,
        "base_query_plan": None,
        "inheritance_status": last_success_task_status
        or {"status": "not_applicable", "reason": "not_evaluated"},
    }
    evaluated_task = None
    evaluated_status = last_success_task_status
    if evaluated_status is None:
        evaluated_task, evaluated_status = evaluate_last_success_task(
            last_success_task,
            active_dataset_id=active_dataset_id,
        )
        capsule["inheritance_status"] = evaluated_status
    can_inherit = (
        event_type == "followup_refine"
        and evaluated_status.get("status") == "loaded"
        and active_dataset_id is not None
    )
    if can_inherit:
        if evaluated_task is None:
            evaluated_task, evaluated_status = evaluate_last_success_task(
                last_success_task,
                active_dataset_id=active_dataset_id,
            )
            capsule["inheritance_status"] = evaluated_status
        if evaluated_task is None:
            return capsule
        prior_question = evaluated_task.question or ""
        capsule.update(
            {
                "standalone_question": f"基于上一轮问题「{prior_question}」，{question}",
                "base_task_ref": "last_success_task",
                "base_question": prior_question,
                "base_main_table": evaluated_task.main_table,
                "base_query_plan": evaluated_task.to_base_query_plan(),
            }
        )
    return capsule
