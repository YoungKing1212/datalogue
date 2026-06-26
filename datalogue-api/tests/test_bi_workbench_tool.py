# ============================================================
# File Name   : test_bi_workbench_tool.py
# Description:
#   BIWorkbenchTool / ask_bi 外层稳定契约测试。
#
# Responsibilities:
#   - 验证 ask_bi 入参、出参和 Chat 主链转接边界。
#   - 覆盖用户可见响应不泄露 SQL、schema、capsule 或 control_plane。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

import json

import pytest

from app.schemas.bi_workbench import AskBIRequest
from app.services.bi_workbench_tool import ask_bi


def _sse(payload: dict):
    return {"data": json.dumps(payload, ensure_ascii=False)}


@pytest.mark.asyncio
async def test_ask_bi_returns_stable_outer_contract_without_internal_leaks():
    captured = {}

    async def fake_stream_chat(payload, db):
        captured["payload"] = payload
        captured["db"] = db
        yield _sse(
            {
                "type": "candidate_datasets",
                "candidate_datasets": [{"dataset_id": 12, "name": "工作日志"}],
                "raw_sql": "select * from internal_table",
            }
        )
        yield _sse(
            {
                "type": "final",
                "conversation_id": 1,
                "answer": "杨凯 2024 年工作日志共 10 条。",
                "result_ref": "artifact:sql_result:1",
                "report_ref": "artifact:report:1",
                "sql": "select * from internal_table",
                "sql_result": {"rows": [{"n": 10}]},
                "schema_context": {"tables": ["internal_table"]},
                "out_capsule": {"query_context": {"main_table": "internal_table"}},
                "subagent_control_plane": {"raw_error": None},
            }
        )

    response = await ask_bi(
        AskBIRequest(
            question="查询杨凯 2024 年工作日志",
            conversation_id=1,
            caller="chat",
            confirmed_dataset_id=12,
            context_refs=[],
            request_options={"session_id": "session-1"},
        ),
        db="db-session",
        stream_chat=fake_stream_chat,
    )

    assert captured["db"] == "db-session"
    assert captured["payload"].question == "查询杨凯 2024 年工作日志"
    assert captured["payload"].conversation_id == 1
    assert captured["payload"].dataset_id == 12
    assert captured["payload"].session_id == "session-1"
    assert response.task_id
    assert response.status == "completed"
    assert response.event_envelope.event_type == "answer.completed"
    assert response.event_envelope.visibility == "user_visible"
    assert response.candidate_datasets == [{"dataset_id": 12, "name": "工作日志"}]
    assert response.answer == "杨凯 2024 年工作日志共 10 条。"
    assert response.primary_ref.ref_id == "artifact:result:1"
    assert response.related_refs[0].ref_id == "artifact:report:1"

    visible_json = response.model_dump_json()
    for forbidden in (
        "raw_sql",
        "sql_result",
        "schema_context",
        "out_capsule",
        "subagent_control_plane",
        "internal_table",
    ):
        assert forbidden not in visible_json


@pytest.mark.asyncio
async def test_ask_bi_maps_clarification_to_waiting_user_status():
    async def fake_stream_chat(_payload, _db):
        yield _sse(
            {
                "type": "final",
                "answer": "请先选择一个数据集。",
                "entry_route": "dataset_select",
                "candidate_datasets": [{"dataset_id": 7, "name": "销售"}],
            }
        )

    response = await ask_bi(
        AskBIRequest(question="查 GMV", caller="report_agent"),
        stream_chat=fake_stream_chat,
    )

    assert response.status == "waiting_user"
    assert response.error is None
    assert response.event_envelope.event_type == "clarification.required"
    assert response.candidate_datasets == [{"dataset_id": 7, "name": "销售"}]
