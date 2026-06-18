# ============================================================
# File Name   : test_subagent_fanout.py
# Description:
#   多数据集 SubAgent fan-out 编排测试。
#
# Responsibilities:
#   - 验证多个数据集调用会被并发编排并拆分双层出参。
#   - 验证单数据集失败不会污染成功数据集的控制面状态。
#   - 验证 LLM 渲染只使用安全摘要。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

import asyncio
from typing import Any

from app.services.subagent_fanout import (
    SubAgentFanOutAnswerSynthesizer,
    SubAgentFanOutInvocation,
    SubAgentFanOutOrchestrator,
    parse_dataset_fanout_invocations,
)
from app.services.subagent_tool_adapter import LLMVisibleStatus


def _ok_state(dataset_id: int) -> dict[str, Any]:
    return {
        "display_summary": f"数据集 {dataset_id} 查询完成",
        "answer": "完整报告不应直接进 LLM",
        "out_capsule": {"dataset_id": dataset_id, "query_context": {"table": "orders"}},
        "query_plan": {
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "main_table": "orders",
        },
        "dsl": {"fields": [{"name": "amount"}]},
        "sql": "SELECT amount FROM orders",
        "sql_result": {"columns": ["amount"], "rows": [{"amount": 1}], "row_count": 1},
    }


def test_fanout_collects_safe_results_and_control_plane():
    async def invoke(invocation: SubAgentFanOutInvocation) -> dict[str, Any]:
        if invocation.dataset_id == 2:
            return {"error": "SQL failed near internal_table"}
        return _ok_state(invocation.dataset_id)

    orchestrator = SubAgentFanOutOrchestrator(invoke_final_state=invoke, max_parallel=2)
    result = asyncio.run(
        orchestrator.run(
            [
                SubAgentFanOutInvocation(dataset_id=1, question="查销售"),
                SubAgentFanOutInvocation(dataset_id=2, question="查库存"),
            ]
        )
    )

    assert [item.llm_visible.dataset_id for item in result.results] == [1, 2]
    assert result.results[0].llm_visible.status == LLMVisibleStatus.OK
    assert result.results[1].llm_visible.status == LLMVisibleStatus.ERROR
    assert result.results[0].control_plane.capsule["dataset_id"] == 1
    assert result.results[1].control_plane.capsule is None
    assert result.control_planes[0]["capsule"]["dataset_id"] == 1
    assert result.control_planes[1]["last_success_task"] is None

    rendered = orchestrator.render_for_llm(result)

    assert "数据集 1 查询完成" in rendered
    assert "internal_table" not in rendered
    assert "SELECT amount" not in rendered


def test_fanout_respects_max_parallel():
    active = 0
    max_seen = 0

    async def invoke(invocation: SubAgentFanOutInvocation) -> dict[str, Any]:
        nonlocal active, max_seen
        active += 1
        max_seen = max(max_seen, active)
        await asyncio.sleep(0.01)
        active -= 1
        return _ok_state(invocation.dataset_id)

    orchestrator = SubAgentFanOutOrchestrator(invoke_final_state=invoke, max_parallel=2)
    asyncio.run(
        orchestrator.run(
            [
                SubAgentFanOutInvocation(dataset_id=1, question="q1"),
                SubAgentFanOutInvocation(dataset_id=2, question="q2"),
                SubAgentFanOutInvocation(dataset_id=3, question="q3"),
            ]
        )
    )

    assert max_seen == 2


def test_parse_dataset_fanout_invocations_requires_explicit_dataset_ids():
    calls = [
        {"tool": "subagent_dispatch", "arguments": {"dataset_id": 11, "question": "查销售"}},
        {"name": "dataset_query", "input": {"dataset_id": "12", "question": "查库存"}},
        {"tool": "subagent_dispatch", "arguments": {"question": "没有 dataset"}},
        {"tool": "time", "arguments": {"dataset_id": 13, "question": "不应解析"}},
    ]

    invocations = parse_dataset_fanout_invocations(
        calls,
        fallback_question="汇总销售和库存",
        turn_index=4,
        prior_capsule_status={"status": "loaded"},
    )

    assert [item.dataset_id for item in invocations] == [11, 12]
    assert [item.question for item in invocations] == ["查销售", "查库存"]
    assert all(item.turn_index == 4 for item in invocations)
    assert all(item.prior_capsule_status == {"status": "loaded"} for item in invocations)


def test_parse_dataset_fanout_invocations_returns_empty_for_single_dataset():
    invocations = parse_dataset_fanout_invocations(
        [{"tool": "subagent_dispatch", "arguments": {"dataset_id": 11, "question": "查销售"}}],
        fallback_question="查销售",
    )

    assert invocations == []


def test_answer_synthesizer_uses_only_llm_visible_and_refs():
    async def invoke(invocation: SubAgentFanOutInvocation) -> dict[str, Any]:
        return {
            "display_summary": f"数据集 {invocation.dataset_id} 安全摘要",
            "answer": "完整报告包含 raw_report_secret",
            "out_capsule": {"raw_capsule_marker": "should_not_leak"},
            "query_plan": {"query_type": "detail_query", "execution_strategy": "query_graph"},
            "dsl": {"fields": []},
            "sql": "SELECT raw_secret FROM internal_table",
            "sql_result": {"rows": [{"raw_secret": "should_not_leak"}]},
            "result_ref": f"artifact:result-{invocation.dataset_id}",
            "report_ref": f"artifact:report-{invocation.dataset_id}",
        }

    result = asyncio.run(
        SubAgentFanOutOrchestrator(invoke_final_state=invoke, max_parallel=2).run(
            [
                SubAgentFanOutInvocation(dataset_id=1, question="q1"),
                SubAgentFanOutInvocation(dataset_id=2, question="q2"),
            ]
        )
    )

    answer = SubAgentFanOutAnswerSynthesizer().synthesize(result)

    assert "数据集 1 安全摘要" in answer
    assert "artifact:result-1" in answer
    assert "artifact:report-2" in answer
    assert "SELECT raw_secret" not in answer
    assert "raw_capsule_marker" not in answer
    assert "raw_report_secret" not in answer
