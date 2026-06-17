# ============================================================
# File Name   : refinement_fast_path.py
# Description:
#   多轮追问的快速路径判定器。
#
# Responsibilities:
#   - 将“只看/仅看/前 N 条”等追问解析为最小 refinement delta。
#   - 根据 last_success_task、artifact 状态和 feature flags 选择安全执行路径。
#   - 对 SQL AST Patch 保持默认关闭和 fail-closed 策略。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

import re
from typing import Any

_CONTAINS_RE = re.compile(r"(?:只看|仅看|筛选|限定|换成|改成|改为)[：:\s]*(?P<value>.+)$")
_LIMIT_RE = re.compile(r"(?:前|只要|保留)?\s*(?P<limit>\d+)\s*(?:条|行|个)")


def build_refinement_delta(question: str) -> dict[str, Any]:
    """把追问文本解析成保守 delta，供快速路径和 trace 共用。"""

    text = (question or "").strip()
    operations: list[str] = []
    delta: dict[str, Any] = {
        "version": "refinement_delta.v1",
        "raw_text": text,
        "operations": operations,
    }
    contains_match = _CONTAINS_RE.search(text)
    if contains_match:
        value = contains_match.group("value").strip()
        if value:
            operations.append("contains_filter")
            delta["contains_text"] = value
    limit_match = _LIMIT_RE.search(text)
    if limit_match:
        operations.append("limit")
        delta["limit"] = int(limit_match.group("limit"))
    return delta


def plan_refinement_fast_path(
    *,
    question: str,
    turn_event: dict[str, Any] | None,
    query_task_capsule: dict[str, Any] | None,
    last_success_task_status: dict[str, Any] | None,
    artifact_status: dict[str, Any] | None,
    fast_path_enabled: bool,
    local_filter_enabled: bool,
    sql_ast_patch_enabled: bool,
) -> dict[str, Any]:
    """选择多轮追问的最快安全路径；不确定时只返回降级原因。"""

    event = turn_event or {}
    capsule = query_task_capsule or {}
    inheritance_status = last_success_task_status or capsule.get("inheritance_status") or {}
    artifact = artifact_status or {"status": "missing", "reason": "no_result_ref"}
    delta = build_refinement_delta(question)
    base = {
        "version": "multiturn_refinement_fast_path.v1",
        "enabled": bool(fast_path_enabled),
        "local_filter_enabled": bool(local_filter_enabled),
        "sql_ast_patch_enabled": bool(sql_ast_patch_enabled),
        "event_type": event.get("event_type"),
        "base_task_ref": capsule.get("base_task_ref"),
        "base_question": capsule.get("base_question"),
        "base_main_table": capsule.get("base_main_table"),
        "delta": delta,
        "artifact_status": artifact,
        "ast_patch": {
            "enabled": bool(sql_ast_patch_enabled),
            "status": "disabled" if not sql_ast_patch_enabled else "candidate",
        },
    }
    if event.get("event_type") != "followup_refine":
        return {
            **base,
            "attempted": False,
            "path": "full_langgraph",
            "status": "not_applicable",
            "reason": "not_followup_refine",
        }
    if (
        inheritance_status.get("status") != "loaded"
        or capsule.get("base_task_ref") != "last_success_task"
    ):
        return {
            **base,
            "attempted": False,
            "path": "full_langgraph",
            "status": "fallback",
            "reason": inheritance_status.get("reason") or "last_success_task_not_loaded",
        }
    if not fast_path_enabled:
        return {
            **base,
            "attempted": False,
            "path": "dsl_refinement",
            "status": "observe_only",
            "reason": "fast_path_feature_disabled",
        }
    if (
        local_filter_enabled
        and artifact.get("status") == "eligible"
        and _has_local_filter_delta(delta)
    ):
        return {
            **base,
            "attempted": True,
            "path": "local_result_filter",
            "status": "eligible",
            "reason": "artifact_complete_and_delta_supported",
        }
    if artifact.get("status") in {"expired", "miss", "not_eligible"}:
        return {
            **base,
            "attempted": True,
            "path": "dsl_refinement",
            "status": "fallback",
            "reason": artifact.get("reason") or "artifact_not_eligible",
        }
    return {
        **base,
        "attempted": True,
        "path": "dsl_refinement",
        "status": "fallback",
        "reason": "delta_requires_query_regeneration",
    }


def _has_local_filter_delta(delta: dict[str, Any]) -> bool:
    operations = set(delta.get("operations") or [])
    return bool(operations & {"contains_filter", "limit"})
