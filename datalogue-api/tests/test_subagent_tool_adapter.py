# ============================================================
# File Name   : test_subagent_tool_adapter.py
# Description:
#   SubAgentToolAdapter 双层出参分离测试。
#
# Responsibilities:
#   - 验证 LLM 可见层只包含安全摘要。
#   - 验证控制面 capsule 和 last_success_task 只通过独立对象流转。
#   - 验证 adapter 的状态判断、错误脱敏和 token 预算护栏。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

from app.services.subagent_tool_adapter import (
    LLMVisibleStatus,
    SubAgentInvocation,
    SubAgentToolAdapter,
    SubAgentToolResult,
)


def _invocation() -> SubAgentInvocation:
    return SubAgentInvocation(
        dataset_id=10,
        question="查询用户日志",
        resolved_question="查询用户日志",
        turn_index=3,
        prior_capsule_status={"status": "loaded", "reason": "capsule_matched"},
    )


def _ok_final_state() -> dict:
    return {
        "answer": "查询完成，共 2 条记录。",
        "display_summary": "共 2 条记录。",
        "out_capsule": {
            "capsule_version": "subagent.v1",
            "dataset_id": 10,
            "query_context": {"main_table": "plan_task_daily_record"},
        },
        "query_plan": {
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "planner_source": "deterministic",
            "main_table": "plan_task_daily_record",
        },
        "dsl": {
            "query_type": "detail_query",
            "select": [{"table": "plan_task_daily_record", "column": "rzrq"}],
        },
        "sql": "SELECT rzrq FROM plan_task_daily_record LIMIT 2",
        "sql_result": {
            "columns": ["rzrq"],
            "rows": [{"rzrq": "2026-06-17"}, {"rzrq": "2026-06-18"}],
            "row_count": 2,
        },
        "result_artifact": {
            "version": "query_result_artifact.v1",
            "result_ref": "result:hot-cache",
            "artifact_ref": "artifact:sql_result:json",
            "report_id": "report:answer",
            "cache_backend": "memory_redis_compatible",
            "ttl_seconds": 1800,
            "expires_at": "2026-06-18T12:00:00+00:00",
            "complete": True,
            "completeness_reason": "complete_result",
            "display_summary": "完整结果，2 行，1 列",
            "row_count": 2,
            "columns": ["rzrq"],
        },
        "bound_schema_version": "schema-v1",
        "manifest_version": "manifest-v1",
    }


def test_assemble_ok_builds_llm_visible_and_control_plane():
    result = SubAgentToolAdapter().assemble_from_final_state(
        _invocation(),
        _ok_final_state(),
    )

    assert result.llm_visible.status == LLMVisibleStatus.OK
    assert result.llm_visible.dataset_id == 10
    assert result.llm_visible.display_summary == "共 2 条记录。"
    assert result.control_plane.capsule["query_context"]["main_table"] == "plan_task_daily_record"
    assert result.control_plane.prior_capsule_status["status"] == "loaded"
    assert result.control_plane.last_success_task["dataset_id"] == 10
    assert result.control_plane.last_success_task["query_type"] == "detail_query"
    assert result.control_plane.last_success_task["result_digest"]["row_count"] == 2
    assert result.control_plane.last_success_task["result_ref"] == "result:hot-cache"
    assert (
        result.control_plane.last_success_task["result_artifact"]["artifact_ref"]
        == "artifact:sql_result:json"
    )
    assert "rows" not in result.control_plane.last_success_task["result_artifact"]


def test_subagent_tool_result_keeps_raw_payload_only_in_control_plane():
    result = SubAgentToolResult(
        llm_visible={
            "status": "ok",
            "dataset_id": 10,
            "display_summary": "查询完成",
            "result_ref": "result://1",
        },
        control_plane={
            "raw_sql": "select * from plan_task_daily_record",
            "raw_result": [{"name": "FORBIDDEN_RAW_RESULT"}],
        },
        trace_metadata={"schema_version": "subagent_tool_result.v1"},
    )

    visible_payload = result.llm_visible.model_dump(mode="json")
    assert "raw_sql" not in str(visible_payload)
    assert "FORBIDDEN_RAW_RESULT" not in str(visible_payload)
    assert result.control_plane.raw_sql.startswith("select")
    assert result.control_plane.raw_result[0]["name"] == "FORBIDDEN_RAW_RESULT"


def test_assemble_result_emits_stable_trace_metadata():
    final_state = _ok_final_state()
    final_state["guard_status"] = "passed"
    final_state["result_ref"] = "artifact:sql_result:json"

    result = SubAgentToolAdapter().assemble_from_final_state(
        _invocation(),
        final_state,
    )

    assert result.trace_metadata["schema_version"] == "subagent_tool_result.v1"
    assert result.trace_metadata["tool_name"] == "dataset_subagent"
    assert result.trace_metadata["dataset_id"] == 10
    assert result.trace_metadata["status"] == "ok"
    assert result.trace_metadata["guard_status"] == "passed"
    assert result.trace_metadata["artifact_id"] == "artifact:sql_result:json"


def test_llm_visible_summary_with_internal_payload_is_sanitized():
    final_state = _ok_final_state()
    final_state["display_summary"] = (
        "raw_sql: SELECT * FROM forbidden_table; raw_result: FORBIDDEN_RAW_RESULT"
    )

    result = SubAgentToolAdapter().assemble_from_final_state(
        _invocation(),
        final_state,
    )

    visible_payload = result.llm_visible.model_dump(mode="json")
    assert result.llm_visible.display_summary == "查询完成，结果已生成引用。"
    assert "raw_sql" not in str(visible_payload)
    assert "FORBIDDEN_RAW_RESULT" not in str(visible_payload)
    assert result.control_plane.raw_sql.startswith("SELECT rzrq")


def test_control_plane_last_success_task_uses_configured_budget(monkeypatch):
    class LowBudgetSettings:
        MULTITURN_LAST_SUCCESS_TASK_MAX_TOKENS = 1

    monkeypatch.setattr(
        "app.services.subagent_tool_adapter.get_settings",
        lambda: LowBudgetSettings(),
    )

    result = SubAgentToolAdapter().assemble_from_final_state(
        _invocation(),
        _ok_final_state(),
    )

    assert result.control_plane.last_success_task is None


def test_assemble_empty_result_is_not_error():
    final_state = _ok_final_state()
    final_state["display_summary"] = "查询无匹配结果"
    final_state["sql_result"] = {"columns": ["rzrq"], "rows": [], "row_count": 0}

    result = SubAgentToolAdapter().assemble_from_final_state(_invocation(), final_state)

    assert result.llm_visible.status == LLMVisibleStatus.EMPTY
    assert result.llm_visible.display_summary == "查询无匹配结果"
    assert result.llm_visible.error_summary is None


def test_assemble_error_sanitizes_llm_visible_message():
    final_state = _ok_final_state()
    final_state["error"] = "SQL syntax failed near forbidden_internal_table"

    result = SubAgentToolAdapter().assemble_from_final_state(_invocation(), final_state)

    assert result.llm_visible.status == LLMVisibleStatus.ERROR
    assert result.llm_visible.error_summary == "数据查询执行失败，已记录，可以稍后重试。"
    assert "forbidden_internal_table" not in result.llm_visible.error_summary
    assert result.control_plane.raw_error == "SQL syntax failed near forbidden_internal_table"
    assert result.control_plane.last_success_task is None


def test_render_for_llm_does_not_leak_control_plane():
    final_state = _ok_final_state()
    final_state["out_capsule"]["query_context"]["secret"] = "FORBIDDEN_TOKEN"
    final_state["sql_result"]["rows"] = [{"rzrq": "FORBIDDEN_TOKEN"}]
    result = SubAgentToolAdapter().assemble_from_final_state(_invocation(), final_state)

    rendered = SubAgentToolAdapter().render_for_llm(result)

    assert "FORBIDDEN_TOKEN" not in rendered
    assert "SELECT rzrq" not in rendered
    assert rendered == "[dataset=10 ok] 共 2 条记录。"


def test_llm_visible_budget_exceeded_truncates_display_summary():
    final_state = _ok_final_state()
    final_state["display_summary"] = "超长摘要" * 400

    result = SubAgentToolAdapter().assemble_from_final_state(_invocation(), final_state)

    assert result.llm_visible.status == LLMVisibleStatus.OK
    assert len(result.llm_visible.display_summary) < len("超长摘要" * 400)
    assert result.llm_visible.display_summary.endswith("...")


class FakeArtifactStore:
    def __init__(self):
        self.calls = []

    def put_json(self, *, kind, payload, dataset_id=None, conversation_id=None, trace_id=None):
        self.calls.append(
            {
                "method": "put_json",
                "kind": kind,
                "payload": payload,
                "dataset_id": dataset_id,
                "conversation_id": conversation_id,
                "trace_id": trace_id,
            }
        )
        return f"artifact:{kind}:json"

    def put_text(self, *, kind, text, dataset_id=None, conversation_id=None, trace_id=None):
        self.calls.append(
            {
                "method": "put_text",
                "kind": kind,
                "text": text,
                "dataset_id": dataset_id,
                "conversation_id": conversation_id,
                "trace_id": trace_id,
            }
        )
        return f"artifact:{kind}:text"


def test_assemble_writes_large_outputs_to_artifact_refs():
    final_state = _ok_final_state()
    final_state["answer"] = "完整报告正文"
    store = FakeArtifactStore()

    result = SubAgentToolAdapter(artifact_store=store).assemble_from_final_state(
        _invocation(),
        final_state,
        conversation_id=20,
        trace_id="trace-1",
    )

    assert result.llm_visible.report_ref == "artifact:report:text"
    assert result.control_plane.result_ref == "artifact:sql_result:json"
    assert result.control_plane.report_ref == "artifact:report:text"
    assert result.control_plane.last_success_task["result_ref"] == "result:hot-cache"
    assert (
        result.control_plane.last_success_task["result_artifact"]["artifact_ref"]
        == "artifact:sql_result:json"
    )
    assert "rows" not in result.control_plane.last_success_task["result_digest"]
    assert "rows" not in result.control_plane.last_success_task["result_artifact"]
    assert store.calls[0]["kind"] == "sql_result"
    assert store.calls[0]["dataset_id"] == 10
    assert store.calls[0]["conversation_id"] == 20
    assert store.calls[0]["trace_id"] == "trace-1"
