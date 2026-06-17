from app.services.message_gateway import classify_turn_event
from app.api.chat import _has_last_success_task
from app.services.multiturn.last_success_task import evaluate_last_success_task
from app.services.task_capsule import build_success_task_state


def test_dataset_select_event_is_not_query():
    event = classify_turn_event(
        "选择：生产经营管理系统日志数据集",
        active_dataset_id=None,
        has_pending_clarification=False,
        has_last_success_task=False,
    )

    assert event["event_type"] == "dataset_select"
    assert event["should_enter_graph"] is False
    assert event["dataset_name"] == "生产经营管理系统日志数据集"


def test_followup_refine_requires_last_success_task():
    event = classify_turn_event(
        "只看汤杰",
        active_dataset_id=10,
        has_pending_clarification=False,
        has_last_success_task=True,
    )

    assert event["event_type"] == "followup_refine"
    assert event["should_enter_graph"] is True
    assert event["delta_intent"] == "add_filter"


def test_schema_stale_last_success_task_does_not_enable_followup_refine():
    task = build_success_task_state(
        question="查询10条用户日志",
        dataset_id=10,
        query_plan={
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "debug": {"selected_main_table": "plan_task_daily_record"},
        },
        dsl={"fields": [{"name": "rzrq"}]},
        sql="SELECT rzrq FROM plan_task_daily_record LIMIT 10",
        sql_result={"columns": ["rzrq"], "rows": []},
        schema_version="schema-v1",
        manifest_version="manifest-v1",
    )
    _, status = evaluate_last_success_task(
        task,
        active_dataset_id=10,
        current_schema_version="schema-v2",
        current_manifest_version="manifest-v1",
    )

    assert _has_last_success_task({"last_success_task": task}, status) is False
    event = classify_turn_event(
        "只看汤杰",
        active_dataset_id=10,
        has_pending_clarification=False,
        has_last_success_task=_has_last_success_task({"last_success_task": task}, status),
    )

    assert event["event_type"] == "clarify"
    assert "上一轮" in event["answer"]


def test_followup_without_prior_downgrades_to_clarify():
    event = classify_turn_event(
        "只看汤杰",
        active_dataset_id=10,
        has_pending_clarification=False,
        has_last_success_task=False,
    )

    assert event["event_type"] == "clarify"
    assert event["should_enter_graph"] is False
    assert "上一轮" in event["answer"]


def test_interpret_result_event_skips_query_graph():
    event = classify_turn_event(
        "这个结果说明什么",
        active_dataset_id=10,
        has_pending_clarification=False,
        has_last_success_task=True,
    )

    assert event["event_type"] == "interpret_result"
    assert event["should_enter_graph"] is False
