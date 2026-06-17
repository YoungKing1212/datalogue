from datetime import datetime, timedelta, timezone

from app.services.multiturn.query_artifacts import (
    apply_local_result_filter,
    build_query_result_artifact,
    clear_query_artifact_cache,
    evaluate_query_artifact,
)
from app.services.multiturn.refinement_fast_path import plan_refinement_fast_path


def setup_function():
    clear_query_artifact_cache()


def test_query_artifact_keeps_metadata_outside_last_success_task_payload():
    artifact = build_query_result_artifact(
        question="查询日志",
        dataset_id=10,
        sql="SELECT name, amount FROM orders",
        sql_result={
            "columns": ["name", "amount"],
            "rows": [{"name": "汤杰", "amount": 20}],
            "row_count": 1,
        },
        answer="查询完成",
        schema_version="schema-v1",
        manifest_version="manifest-v1",
        ttl_seconds=1800,
    )

    assert artifact is not None
    assert artifact["result_ref"].startswith("result:")
    assert artifact["report_id"].startswith("report:")
    assert artifact["complete"] is True
    assert "rows" not in artifact
    assert artifact["display_summary"] == "完整结果，1 行，2 列"


def test_query_artifact_limit_sql_is_not_eligible_for_local_filter():
    artifact = build_query_result_artifact(
        question="查询10条日志",
        dataset_id=10,
        sql="SELECT name FROM orders LIMIT 10",
        sql_result={"columns": ["name"], "rows": [{"name": "汤杰"}], "row_count": 1},
    )

    _, status = evaluate_query_artifact(artifact)

    assert artifact["complete"] is False
    assert status["status"] == "not_eligible"
    assert status["reason"] == "sql_limit_makes_result_incomplete"


def test_query_artifact_ttl_expired_fails_closed():
    now = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
    artifact = build_query_result_artifact(
        question="查询日志",
        dataset_id=10,
        sql="SELECT name FROM orders",
        sql_result={"columns": ["name"], "rows": [{"name": "汤杰"}], "row_count": 1},
        ttl_seconds=60,
        now=now,
    )

    _, status = evaluate_query_artifact(artifact, now=now + timedelta(seconds=61))

    assert status["status"] == "expired"
    assert status["reason"] == "ttl_expired"


def test_local_result_filter_requires_complete_artifact():
    artifact = build_query_result_artifact(
        question="查询日志",
        dataset_id=10,
        sql="SELECT name, amount FROM orders",
        sql_result={
            "columns": ["name", "amount"],
            "rows": [{"name": "汤杰", "amount": 20}, {"name": "杨凯", "amount": 10}],
            "row_count": 2,
        },
    )
    hot_artifact, status = evaluate_query_artifact(artifact)

    filtered = apply_local_result_filter(hot_artifact, contains_text="汤杰", limit=5)

    assert status["status"] == "eligible"
    assert filtered["source"] == "local_result_filter"
    assert filtered["row_count"] == 1
    assert filtered["rows"][0]["name"] == "汤杰"


def test_fast_path_defaults_to_observe_only_when_feature_disabled():
    decision = plan_refinement_fast_path(
        question="只看汤杰",
        turn_event={"event_type": "followup_refine"},
        query_task_capsule={
            "base_task_ref": "last_success_task",
            "base_question": "查询日志",
            "base_main_table": "orders",
        },
        last_success_task_status={"status": "loaded"},
        artifact_status={"status": "eligible", "result_ref": "result:1", "complete": True},
        fast_path_enabled=False,
        local_filter_enabled=True,
        sql_ast_patch_enabled=False,
    )

    assert decision["status"] == "observe_only"
    assert decision["path"] == "dsl_refinement"
    assert decision["reason"] == "fast_path_feature_disabled"
    assert decision["ast_patch"]["status"] == "disabled"


def test_fast_path_selects_local_result_filter_only_when_enabled_and_complete():
    decision = plan_refinement_fast_path(
        question="只看汤杰",
        turn_event={"event_type": "followup_refine"},
        query_task_capsule={
            "base_task_ref": "last_success_task",
            "base_question": "查询日志",
            "base_main_table": "orders",
        },
        last_success_task_status={"status": "loaded"},
        artifact_status={"status": "eligible", "result_ref": "result:1", "complete": True},
        fast_path_enabled=True,
        local_filter_enabled=True,
        sql_ast_patch_enabled=False,
    )

    assert decision["path"] == "local_result_filter"
    assert decision["status"] == "eligible"
    assert decision["delta"]["contains_text"] == "汤杰"
