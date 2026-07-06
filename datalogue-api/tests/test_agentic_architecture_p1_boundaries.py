# ============================================================
# File Name   : test_agentic_architecture_p1_boundaries.py
# Description:
#   AgentScope 架构瘦身 P1 目录边界测试。
#
# Responsibilities:
#   - 验证 middleware 与 event projection 已由新目录持有。
#   - 验证 P3 后旧 services 兼容壳已移除，活跃入口只从新目录导入。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import logging

import pytest


def test_p1_middlewares_new_paths_own_runtime_logging():
    from app.middlewares import DatasetRuntimeToolLoggingMiddleware
    from app.middlewares.dataset_tool_logging import DatasetRuntimeToolLoggingMiddleware as DirectMiddleware

    assert DatasetRuntimeToolLoggingMiddleware is DirectMiddleware
    assert DirectMiddleware.__module__ == "app.middlewares.dataset_tool_logging"


def test_p1_lifecycle_logging_new_path_is_silent_after_agent_debug_log_cutover(caplog):
    from app.middlewares.lifecycle import log_lifecycle, log_output

    with caplog.at_level(logging.INFO, logger="app.middlewares.lifecycle"):
        log_lifecycle(
            "dataset.query.completed",
            trace_id="trace-1",
            sql="SELECT * FROM secret_table",
            schema_context="secret schema",
            artifact_ref="artifact:1",
        )
        log_output(
            event_type="message.completed",
            trace_id="trace-1",
            summary="查询已完成",
            artifact_ref="artifact:1",
        )

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "SELECT" not in logs
    assert "secret schema" not in logs
    assert "[datalogue.lifecycle]" not in logs
    assert "[datalogue.output]" not in logs
    assert logs == ""


def test_p1_agent_debug_raw_logs_can_be_enabled_from_env_file(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.middlewares.lifecycle import raw_agent_logs_enabled

    monkeypatch.delenv("AGENT_DEBUG_RAW_LOGS", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("AGENT_DEBUG_RAW_LOGS=true\n", encoding="utf-8")
    get_settings.cache_clear()

    try:
        assert raw_agent_logs_enabled() is True
    finally:
        get_settings.cache_clear()


def test_p1_events_projection_new_path_preserves_legacy_task_projection():
    from app.events.projection import project_agentscope_event

    envelope = project_agentscope_event(
        {"data": '{"type":"token","content":"hello"}'},
        task_id="task-1",
        trace_id="trace-1",
        thread_id="thread-1",
        message_id="message-1",
        selected_agent="bi_agent",
    )

    assert envelope.event_type == "message.delta"
    assert envelope.payload == {"content": "hello"}
    assert envelope.task_id == "task-1"
    assert envelope.trace_id == "trace-1"


def test_p1_workbench_projection_new_path_preserves_legacy_sanitizer():
    from app.events.projection import sanitize_event_payload_for_workbench

    with pytest.raises(ValueError, match="AGENTSCOPE_MIRROR_PAYLOAD_LEAK_DETECTED"):
        sanitize_event_payload_for_workbench(
            "answer.completed",
            {
                "summary": "完成",
                "artifact_ref": "artifact:1",
                "sql": "SELECT * FROM secret_table",
            },
        )

    safe_payload = sanitize_event_payload_for_workbench(
        "answer.completed",
        {"summary": "完成", "artifact_ref": "artifact:1"},
    )
    assert safe_payload == {"summary": "完成", "artifact_ref": "artifact:1"}


def test_p1_runtime_new_path_owns_thread_resolver():
    from app.runtime import new_agentscope_thread_id, normalize_thread_id, resolve_thread_ref
    from app.runtime.thread_resolver import normalize_thread_id as direct_normalize_thread_id

    assert normalize_thread_id is direct_normalize_thread_id
    assert direct_normalize_thread_id.__module__ == "app.runtime.thread_resolver"
    assert normalize_thread_id(123) == "conv_123"
    assert resolve_thread_ref("conv_123").read_only is True
    assert new_agentscope_thread_id().startswith("as_")
