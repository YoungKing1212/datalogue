# ============================================================
# File Name   : test_repair_patch_stream.py
# Description:
#   C2 PR2 RepairPatch 接入 SQL 失败重跑链路测试。
#
# Responsibilities:
#   - 验证 sql_audit 后进入 RepairPatch 节点，而不是让 LLM 重新生成 SQL。
#   - 验证 RepairPatch 只修补 QueryPlan / compiler binding，并重新走工具编译。
#
# Author      : yangkai
# Created On  : 2026-06-28
# ============================================================

from __future__ import annotations

import json

import pytest

from app.services.subagent_planning import CandidateAsset, QueryPlan


def _field_asset(name: str, table_name: str, column_name: str) -> CandidateAsset:
    return CandidateAsset(
        asset_type="field",
        asset_id=f"{table_name}.{column_name}",
        name=name,
        display_name=name,
        source="schema",
        confidence=0.9,
        metadata={"table_name": table_name, "column_name": column_name},
        usage="selected",
    )


def test_sql_audit_router_sends_field_failures_to_repair_patch_node():
    from app.graph.workflow import _sql_audit_router

    state = {
        "sql_audit_result": {
            "retryable": True,
            "severity": "fixable",
            "code": "FIELD_NOT_FOUND",
        },
        "repair_plan": {"failure_class": "FIELD_NOT_FOUND"},
        "repair_status": "plan_created",
        "query_plan": {"selected_assets": []},
        "retry_count": 0,
        "max_retry_count": 1,
    }

    assert _sql_audit_router(state) == "repair_patch"


def test_sql_audit_router_sends_field_mapping_drift_to_repair_patch_node():
    from app.graph.workflow import _sql_audit_router

    state = {
        "sql_audit_result": {
            "retryable": True,
            "severity": "fixable",
            "code": "FIELD_MAPPING_DRIFT",
        },
        "repair_plan": {"failure_class": "FIELD_MAPPING_DRIFT"},
        "repair_status": "plan_created",
        "query_plan": {"selected_assets": []},
        "retry_count": 0,
        "max_retry_count": 1,
    }

    assert _sql_audit_router(state) == "repair_patch"


def test_build_workflow_registers_repair_patch_without_state_key_collision(db_session):
    from app.graph.workflow import build_workflow

    workflow = build_workflow(db_session)

    assert workflow is not None


def test_repair_patch_node_applies_query_plan_patch_and_recompiles(db_session, sample_dataset):
    from app.graph.nodes import repair_patch_node

    failed_plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.88,
        selected_assets=[_field_asset("工作日期", "work_log", "missing_date")],
        debug={"selected_main_table": "work_log"},
    )
    state = {
        "question": "查询某员工 2024 年工作日志",
        "dataset_id": sample_dataset.id,
        "query_plan": failed_plan.to_dict(),
        "sql_generation_context": {
            "table_schemas": [
                {
                    "table_name": "work_log",
                    "fields": [
                        {"column_name": "work_date", "display_name": "工作日期"},
                        {"column_name": "person_name", "display_name": "人员姓名"},
                    ],
                }
            ]
        },
        "datasource_context": {
            "dialect": "sqlite",
            "allowed_tables": ["work_log"],
        },
        "query_constraints": {"enabled": False},
        "sql_audit_result": {"code": "FIELD_NOT_FOUND", "retryable": True},
        "sql_diagnosis": {"wrong_field": "missing_date", "suggested_fix": "改用工作日期字段"},
        "repair_plan": {
            "schema_version": "repair_plan.v1",
            "failure_class": "FIELD_NOT_FOUND",
            "status": "plan_created",
            "attempts": 1,
        },
        "repair_status": "plan_created",
        "retry_count": 0,
        "sql_retry_trace": [{"attempt": 1, "status": "pending"}],
    }

    result = repair_patch_node(db_session)(state)

    assert result["repair_status"] == "patch_applied"
    assert result["should_retry"] is False
    assert result["dsl"] == {"compiled_query_plan": True}
    assert result["query_plan_compilation"]["ok"] is True
    assert '"work_log"."work_date"' in result["query_plan_compilation"]["sql"]
    assert "missing_date" not in result["query_plan_compilation"]["sql"]
    assert result["repair_patch_summary"]["confidence_band"] in {"high", "medium"}
    assert result["repair_patch"]["trace_only_metadata"]["replacement_field_ref"] == "work_log.work_date"
    assert result["sql_retry_trace"][0]["status"] == "patch_applied"
    assert "work_log" not in json.dumps(result["repair_patch_summary"], ensure_ascii=False)
    assert "sql" not in json.dumps(result["repair_patch_summary"], ensure_ascii=False).lower()


def test_repair_patch_node_blocks_raw_sql_patch_payload(db_session, sample_dataset):
    from app.graph.nodes import repair_patch_node

    state = {
        "question": "查询某员工 2024 年工作日志",
        "dataset_id": sample_dataset.id,
        "query_plan": {
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "confidence": 0.88,
            "selected_assets": [],
            "debug": {},
            "raw_sql": "SELECT * FROM work_log",
        },
        "sql_generation_context": {},
        "datasource_context": {"dialect": "sqlite", "allowed_tables": ["work_log"]},
        "sql_audit_result": {"code": "FIELD_NOT_FOUND", "retryable": True},
        "sql_diagnosis": {"wrong_field": "missing_date"},
        "repair_plan": {"failure_class": "FIELD_NOT_FOUND", "attempts": 1},
        "repair_status": "plan_created",
        "sql_retry_trace": [],
    }

    result = repair_patch_node(db_session)(state)

    assert result["repair_status"] == "blocked"
    assert result["should_retry"] is False
    assert result["query_plan_compilation"]["ok"] is False
    assert result["query_plan_compilation"]["code"] == "REPAIR_PATCH_BLOCKED"
    assert "raw_sql" not in json.dumps(result["repair_patch_summary"], ensure_ascii=False).lower()


@pytest.mark.asyncio
async def test_workflow_e2e_repairs_injected_field_mapping_drift(
    db_session,
    sample_dataset,
    monkeypatch,
    tmp_path,
):
    result = await _run_field_mapping_drift_workflow_e2e(
        db_session=db_session,
        dataset=sample_dataset,
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
    )

    assert result["event_nodes"] == [
        "schema_recall",
        "dsl_generate",
        "dsl_validate",
        "dsl_compiler",
        "sql_execute",
        "sql_audit",
        "repair_patch",
        "dsl_compiler",
        "sql_execute",
        "report_generator",
    ]
    assert result["audit_code"] == "FIELD_MAPPING_DRIFT"
    assert result["repair_status"] == "patch_applied"
    assert result["patched_sql"] == 'SELECT "work_log"."work_date" AS "工作日期" FROM "work_log"'
    assert result["final_row_count"] == 2
    assert result["final_error"] is None
    assert result["retry_trace"][-1]["status"] == "success"
    assert result["repair_patch_summary"]["failure_class"] == "FIELD_MAPPING_DRIFT"
    assert result["public_summary_forbidden_hits"] == []


async def _run_field_mapping_drift_workflow_e2e(*, db_session, dataset, monkeypatch, tmp_path):
    """运行内部-only RepairPatch E2E：注入旧字段漂移，保留真实 SQL 执行和 RepairPatch 重跑。"""

    from sqlalchemy import create_engine, text

    from app.graph import workflow as workflow_module
    from app.models.dataset import DatasetSourceTable, SemanticDimension, SourceColumn, SourceTable

    bad_field = "old_work_date_for_c2_e2e"
    bad_sql = f'SELECT "work_log"."{bad_field}" AS "工作日期" FROM "work_log"'
    sqlite_path = tmp_path / "repair_patch_e2e.sqlite"
    data_engine = create_engine(f"sqlite:///{sqlite_path}")
    with data_engine.begin() as conn:
        conn.execute(text('CREATE TABLE work_log (work_date TEXT NOT NULL, person_name TEXT NOT NULL)'))
        conn.execute(
            text("INSERT INTO work_log (work_date, person_name) VALUES (:work_date, :person_name)"),
            [
                {"work_date": "2024-12-30", "person_name": "杨凯"},
                {"work_date": "2024-12-31", "person_name": "杨凯"},
            ],
        )

    table = SourceTable(
        datasource_id=dataset.datasource_id,
        schema_name="main",
        table_name="work_log",
        table_comment="工作日志",
        status="active",
    )
    db_session.add(table)
    db_session.flush()
    for idx, (column_name, column_comment) in enumerate(
        [("work_date", "工作日期"), ("person_name", "人员姓名")],
        start=1,
    ):
        db_session.add(
            SourceColumn(
                table_id=table.id,
                column_name=column_name,
                data_type="text",
                column_comment=column_comment,
                effective_desc=column_comment,
                review_status="approved",
                ordinal_position=idx,
            )
        )
    db_session.add(DatasetSourceTable(dataset_id=dataset.id, source_table_id=table.id))
    db_session.add(
        SemanticDimension(
            dataset_id=dataset.id,
            name="work_date",
            display_name="工作日期",
            table_name="work_log",
            column_name="work_date",
            synonyms=["日志日期"],
        )
    )
    db_session.commit()

    failed_plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.88,
        selected_assets=[_field_asset("工作日期", "work_log", bad_field)],
        debug={"selected_main_table": "work_log"},
    ).to_dict()

    injected_state = {
        "query_plan": failed_plan,
        "dsl": {"direct_sql": bad_sql},
        "schema_structured": {
            # 顶层 dimensions 模拟语义资产仍指向旧字段；诊断器据此归类 FIELD_MAPPING_DRIFT。
            "dimensions": [
                {
                    "name": "work_date",
                    "display_name": "工作日期",
                    "column_name": bad_field,
                    "table_name": "work_log",
                }
            ],
            "fields": [],
            "metrics": [],
            "tables": [
                {
                    "table_name": "work_log",
                    "fields": [{"column_name": "work_date"}, {"column_name": "person_name"}],
                }
            ],
        },
        "sql_generation_context": {
            "table_schemas": [
                {
                    "table_name": "work_log",
                    "fields": [
                        {
                            "column_name": "work_date",
                            "display_name": "工作日期",
                            "data_type": "text",
                        }
                    ],
                }
            ]
        },
        "datasource_context": {"dialect": "sqlite", "allowed_tables": ["work_log"]},
        "query_constraints": {"enabled": False},
    }

    monkeypatch.setattr("app.graph.nodes.create_engine_for_datasource", lambda _datasource: data_engine)
    monkeypatch.setattr("app.services.datasource.create_engine_for_datasource", lambda _datasource: data_engine)

    class _FakeAuditResponse:
        content = "{}"
        usage_metadata = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    class _FakeAuditLLM:
        def invoke(self, _messages):
            return _FakeAuditResponse()

    monkeypatch.setattr("app.graph.nodes.get_llm", lambda *args, **kwargs: _FakeAuditLLM())
    monkeypatch.setattr(
        workflow_module,
        "schema_recall_node",
        lambda _db: lambda _state: dict(injected_state),
    )
    monkeypatch.setattr(
        workflow_module,
        "dsl_generate_node",
        lambda state, db=None: {"dsl": state.get("dsl") or {"direct_sql": bad_sql}},
    )
    monkeypatch.setattr(
        workflow_module,
        "dsl_validate_node",
        lambda _state: {"dsl_valid": True, "validation_errors": []},
    )

    async def _report_generator(state, db=None):
        result = state.get("sql_result") or {}
        return {"answer": f"RepairPatch E2E 完成，返回 {result.get('row_count')} 行。"}

    monkeypatch.setattr(workflow_module, "report_generator_node", _report_generator)

    graph = workflow_module.build_workflow(db_session)
    events: list[dict[str, object]] = []
    async for chunk in graph.astream(
        {
            "question": "查询杨凯 2024 年工作日志",
            "dataset_id": dataset.id,
            "entry_route": "query_graph",
            "retry_count": 0,
            "max_retry_count": 2,
        }
    ):
        for node_name, output in chunk.items():
            if node_name == "__end__":
                continue
            payload = output if isinstance(output, dict) else {}
            public_node = "repair_patch" if node_name == workflow_module.REPAIR_PATCH_GRAPH_NODE else node_name
            events.append({"node": public_node, "payload": payload})

    audit_payload = _payload_for(events, "sql_audit")
    repair_payload = _payload_for(events, "repair_patch")
    final_sql_execute = [event["payload"] for event in events if event["node"] == "sql_execute"][-1]
    summary = repair_payload.get("repair_patch_summary") or {}
    summary_text = json.dumps(summary, ensure_ascii=False).lower()

    return {
        "event_nodes": [event["node"] for event in events],
        "audit_code": (audit_payload.get("sql_audit_result") or {}).get("code"),
        "repair_status": repair_payload.get("repair_status"),
        "repair_patch_summary": summary,
        "patched_sql": (repair_payload.get("query_plan_compilation") or {}).get("sql"),
        "final_row_count": (final_sql_execute.get("sql_result") or {}).get("row_count"),
        "final_error": final_sql_execute.get("error"),
        "retry_trace": final_sql_execute.get("sql_retry_trace") or [],
        "public_summary_forbidden_hits": [
            term
            for term in [
                "raw_result",
                "work_log",
                bad_field,
                "work_date",
                "select ",
                " from ",
                "query_plan",
                "trace_only_metadata",
            ]
            if term in summary_text
        ],
    }


def _payload_for(events: list[dict[str, object]], node_name: str) -> dict:
    for event in events:
        if event["node"] == node_name:
            payload = event.get("payload")
            return payload if isinstance(payload, dict) else {}
    return {}
