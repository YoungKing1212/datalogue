from app.services.message_gateway import classify_turn_event


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
