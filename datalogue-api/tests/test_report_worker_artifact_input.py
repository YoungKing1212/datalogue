# ============================================================
# File Name   : test_report_worker_artifact_input.py
# Description:
#   Report Worker artifact 输入投影测试。
#
# Responsibilities:
#   - 验证 sql_result report_input_meta 的裁剪和安全字段白名单。
#   - 验证 artifact_ref 读取工具对缺 meta、行列不一致等异常 fail-closed。
#   - 确认 Report Worker 读取明细行时不接触 SQL/schema/raw rows 等内部执行态。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


def test_build_sql_result_report_payload_clips_rows_cells_and_drops_internal_fields():
    from app.domains.query_execution.report_input import (
        REPORT_INPUT_META_KEY,
        build_sql_result_report_payload,
    )

    payload = build_sql_result_report_payload(
        {
            "columns": ["name", "note", "raw_payload", "query_plan_dump", "schema_notes"],
            "rows": [
                {
                    "name": "杨凯",
                    "note": "x" * 20,
                    "raw_score": 9,
                    "query_plan_dump": {"secret": True},
                    "raw_payload": {"secret": True},
                    "schema_notes": "private schema",
                    "raw_rows": [{"secret": "hidden"}],
                    "nested": {
                        "schema": "private",
                        "query_plan_detail": "hidden",
                        "raw_payload": {"secret": True},
                        "display": "safe",
                    },
                    "children": [
                        {"display": "safe child", "schema_notes": "private child"},
                        {"raw_payload": "hidden"},
                    ],
                },
                {"name": "张三", "note": "ok"},
            ],
            "row_count": 2,
            "total_row_count": 5,
            "sql": "SELECT * FROM hidden",
            "schema": {"tables": ["hidden"]},
            "query_plan": {"secret": True},
            "metadata": {"sql": "SELECT secret FROM hidden"},
            "summary": "查询成功",
        },
        settings=SimpleNamespace(REPORT_RESULT_MAX_ROWS=1, REPORT_CELL_MAX_CHARS=8),
    )

    assert payload["columns"] == ["name", "note"]
    assert payload["rows"] == [
        {
            "name": "杨凯",
            "note": "xxxxxxxx...",
            "nested": {"display": "safe"},
            "children": [{"display": "safe chi..."}, {}],
        }
    ]
    assert payload["row_count"] == 2
    assert payload["total_row_count"] == 5
    assert payload["summary"] == "查询成功"
    assert "sql" not in payload
    assert "schema" not in payload
    assert "query_plan" not in payload
    assert "metadata" not in payload
    assert "raw_rows" not in json.dumps(payload, ensure_ascii=False)
    assert "raw_score" not in json.dumps(payload, ensure_ascii=False)
    assert "query_plan_dump" not in json.dumps(payload, ensure_ascii=False)
    assert "raw_payload" not in json.dumps(payload, ensure_ascii=False)
    assert "schema_notes" not in json.dumps(payload, ensure_ascii=False)
    assert payload[REPORT_INPUT_META_KEY] == {
        "visible_row_limit": 1,
        "visible_cell_max_chars": 8,
        "visible_row_count": 1,
        "total_row_count": 5,
        "visible_column_count": 2,
        "total_column_count": 5,
        "truncated": True,
    }


def test_build_sql_result_report_payload_handles_empty_result():
    from app.domains.query_execution.report_input import (
        REPORT_INPUT_META_KEY,
        build_sql_result_report_payload,
    )

    payload = build_sql_result_report_payload(
        {"columns": [], "rows": [], "row_count": 0},
        settings=SimpleNamespace(REPORT_RESULT_MAX_ROWS=10, REPORT_CELL_MAX_CHARS=20),
    )

    assert payload["columns"] == []
    assert payload["rows"] == []
    assert payload[REPORT_INPUT_META_KEY]["visible_row_count"] == 0
    assert payload[REPORT_INPUT_META_KEY]["truncated"] is False


def test_create_query_artifact_tool_preserves_visible_rows_and_drops_internals(db_session):
    from app.domains.bi.toolkit.atomic import build_bi_atomic_toolkit
    from app.domains.query_execution.artifact_store import ArtifactStore
    from app.domains.query_execution.report_input import build_artifact_report_input

    toolkit = build_bi_atomic_toolkit(db_session)
    create_tool = toolkit.get_tool("create_query_artifact")

    result = create_tool.execute_external(
        payload={
            "columns": ["name", "amount"],
            "rows": [{"name": "杨凯", "amount": 100, "raw_rows": ["hidden"]}],
            "row_count": 1,
            "summary": "查询成功",
            "schema": {"secret": True},
            "query_plan": {"secret": True},
        }
    )
    artifact = ArtifactStore(db_session).get(result["artifact_ref"])
    report_input = build_artifact_report_input(artifact)

    assert report_input["status"] == "completed"
    assert report_input["rows"] == [{"name": "杨凯", "amount": 100}]
    assert report_input["safe_summary"] == "查询成功"
    assert "schema" not in json.dumps(artifact.content_json, ensure_ascii=False)
    assert "query_plan" not in json.dumps(artifact.content_json, ensure_ascii=False)


def test_build_artifact_report_input_validates_meta_and_returns_visible_rows(db_session):
    from app.domains.query_execution.artifact_store import ArtifactStore
    from app.domains.query_execution.report_input import (
        REPORT_INPUT_META_KEY,
        build_artifact_report_input,
        build_sql_result_report_payload,
    )

    artifact_ref = ArtifactStore(db_session).put_json(
        kind="sql_result",
        payload=build_sql_result_report_payload(
            {
                "columns": ["name", "amount"],
                "rows": [{"name": "杨凯", "amount": 100}],
                "row_count": 1,
                "summary": "共 1 条记录。",
            }
        ),
    )
    artifact = ArtifactStore(db_session).get(artifact_ref)

    payload = build_artifact_report_input(artifact)

    assert payload["status"] == "completed"
    assert payload["artifact_ref"] == artifact_ref
    assert payload["columns"] == ["name", "amount"]
    assert payload["rows"] == [{"name": "杨凯", "amount": 100}]
    assert payload[REPORT_INPUT_META_KEY]["visible_row_count"] == 1
    assert payload["safe_summary"] == "共 1 条记录。"


def test_build_artifact_report_input_fail_closed_when_meta_missing_or_mismatch(db_session):
    from app.domains.query_execution.artifact_store import ArtifactStore
    from app.domains.query_execution.report_input import build_artifact_report_input

    store = ArtifactStore(db_session)
    missing_meta_ref = store.put_json(
        kind="sql_result",
        payload={"columns": ["id"], "rows": [{"id": 1}]},
    )
    missing_meta_payload = build_artifact_report_input(store.get(missing_meta_ref))

    mismatch_ref = store.put_json(
        kind="sql_result",
        payload={
            "columns": ["id"],
            "rows": [{"id": 1}, {"id": 2}],
            "report_input_meta": {
                "visible_row_limit": 10,
                "visible_cell_max_chars": 120,
                "visible_row_count": 1,
                "total_row_count": 2,
                "visible_column_count": 1,
                "total_column_count": 1,
                "truncated": False,
            },
        },
    )
    mismatch_payload = build_artifact_report_input(store.get(mismatch_ref))

    assert missing_meta_payload["status"] == "failed"
    assert missing_meta_payload["code"] == "REPORT_INPUT_META_MISSING"
    assert mismatch_payload["status"] == "failed"
    assert mismatch_payload["code"] == "REPORT_INPUT_ROW_MISMATCH"


@pytest.mark.asyncio
async def test_report_worker_tool_reads_artifact_report_input(monkeypatch, db_session):
    from app.domains.query_execution.artifact_store import ArtifactStore
    from app.domains.query_execution.report_input import build_sql_result_report_payload
    from app.runtime.engine import tools as tools_module
    from app.runtime.engine.tools import build_datalogue_report_worker_tools

    class FakeSessionLocal:
        def __enter__(self):
            return db_session

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(tools_module, "SessionLocal", FakeSessionLocal)
    artifact_ref = ArtifactStore(db_session).put_json(
        kind="sql_result",
        payload=build_sql_result_report_payload(
            {"columns": ["city"], "rows": [{"city": "上海"}], "row_count": 1}
        ),
    )
    tool = build_datalogue_report_worker_tools(worker_context={"worker_type": "report"})[0]

    chunk = await tool(artifact_ref=artifact_ref)
    payload = json.loads(chunk.content[0].text)

    assert payload["status"] == "completed"
    assert payload["artifact_ref"] == artifact_ref
    assert payload["rows"] == [{"city": "上海"}]
    assert "SELECT" not in chunk.content[0].text
    assert "schema" not in chunk.content[0].text.lower()
    assert "raw_rows" not in chunk.content[0].text.lower()


@pytest.mark.asyncio
async def test_report_worker_tool_fail_closed_for_missing_artifact(monkeypatch, db_session):
    from app.runtime.engine import tools as tools_module
    from app.runtime.engine.tools import build_datalogue_report_worker_tools

    class FakeSessionLocal:
        def __enter__(self):
            return db_session

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(tools_module, "SessionLocal", FakeSessionLocal)
    tool = build_datalogue_report_worker_tools(worker_context={"worker_type": "report"})[0]

    chunk = await tool(artifact_ref="artifact:not-found")
    payload = json.loads(chunk.content[0].text)

    assert payload["status"] == "failed"
    assert payload["code"] == "ARTIFACT_NOT_FOUND"
