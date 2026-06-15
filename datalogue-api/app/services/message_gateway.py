# ============================================================
# File Name   : message_gateway.py
# Description:
#   多轮问数入口消息网关，先把用户输入归类为结构化事件。
#
# Responsibilities:
#   - 拦截数据集选择、结果解释、澄清回复等非查询事件。
#   - 为 LeadAgent / SubAgent 提供稳定的 turn event。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

import re
from typing import Any


_DATASET_SELECT_RE = re.compile(r"^\s*(?:选择|切换到|使用)[：:\s]*(?P<name>.+?数据集)\s*$")
_INTERPRET_PATTERNS = ("说明什么", "怎么看", "解释", "分析一下这个结果", "这个结果")
_FOLLOWUP_FILTER_PATTERNS = ("只看", "仅看", "筛选", "限定", "换成", "改成", "改为")
_QUERY_PATTERNS = ("查", "查询", "统计", "多少", "明细", "日志", "列表", "排名", "汇总")


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def classify_turn_event(
    question: str,
    *,
    active_dataset_id: int | None,
    has_pending_clarification: bool,
    has_last_success_task: bool,
) -> dict[str, Any]:
    """把一轮用户输入分类为网关事件，决定是否继续进入查询图。"""

    text = (question or "").strip()
    dataset_match = _DATASET_SELECT_RE.match(text)
    if dataset_match:
        dataset_name = dataset_match.group("name").strip()
        return {
            "event_type": "dataset_select",
            "should_enter_graph": False,
            "dataset_name": dataset_name,
            "answer": f"已选择数据集「{dataset_name}」，你可以开始提问。",
        }

    if has_pending_clarification:
        return {
            "event_type": "clarification_answer",
            "should_enter_graph": False,
            "answer": None,
        }

    if has_last_success_task and _contains_any(text, _INTERPRET_PATTERNS):
        return {
            "event_type": "interpret_result",
            "should_enter_graph": False,
            "answer": None,
        }

    if _contains_any(text, _FOLLOWUP_FILTER_PATTERNS):
        if has_last_success_task:
            return {
                "event_type": "followup_refine",
                "delta_intent": "add_filter",
                "should_enter_graph": True,
            }
        return {
            "event_type": "clarify",
            "should_enter_graph": False,
            "answer": "我没有可承接的上一轮查询结果。请先发起一个完整查询，再继续筛选。",
        }

    if active_dataset_id is None and not text:
        return {
            "event_type": "clarify",
            "should_enter_graph": False,
            "answer": "请先选择数据集，再告诉我要查询的数据、筛选条件或分析目标。",
        }

    return {
        "event_type": "new_query",
        "should_enter_graph": True,
        "query_hint_matched": _contains_any(text, _QUERY_PATTERNS),
    }
