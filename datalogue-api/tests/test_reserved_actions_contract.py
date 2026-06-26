# ============================================================
# File Name   : test_reserved_actions_contract.py
# Description:
#   ArtifactCard 第一阶段保留动作协议测试。
#
# Responsibilities:
#   - 验证 export / continue_edit 只输出禁用态，不触发增强链路。
#   - 验证未知 action 安全忽略。
#   - 验证禁用动作 payload 不泄露 SQL、schema、capsule、trace body 或 control_plane。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

import json

from app.services.artifact_actions import build_artifact_actions, resolve_artifact_action


FORBIDDEN_VISIBLE_KEYS = {
    "raw_sql",
    "raw_result",
    "schema",
    "capsule",
    "body",
    "control_plane",
}


def _assert_no_forbidden_payload_keys(value):
    """递归扫描用户可见动作 payload，防止第一阶段禁用动作带出内部面字段。"""

    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            assert lowered not in FORBIDDEN_VISIBLE_KEYS
            assert "trace" not in lowered or lowered in {"trace_id"}
            _assert_no_forbidden_payload_keys(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden_payload_keys(item)


def test_reserved_export_and_continue_edit_are_disabled():
    actions = build_artifact_actions(
        [
            {"action_type": "export", "label": "导出", "enabled": True},
            {"action_type": "continue_edit", "label": "继续编辑", "enabled": True},
        ]
    )

    assert [item["action_type"] for item in actions] == ["export", "continue_edit"]
    assert all(item["enabled"] is False for item in actions)
    assert all(item["launches_enhanced_chain"] is False for item in actions)
    assert actions[0]["disabled_reason"] == "导出能力将在后续版本开放"
    assert actions[1]["disabled_reason"] == "继续编辑能力将在后续版本开放"


def test_unknown_action_is_ignored():
    actions = build_artifact_actions(
        [
            {"action_type": "export"},
            {"action_type": "delete_everything", "label": "危险动作"},
            {"action_type": ""},
            {},
        ]
    )

    assert [item["action_type"] for item in actions] == ["export"]
    assert resolve_artifact_action({"action_type": "delete_everything"}) is None


def test_disabled_action_payload_does_not_expose_internal_fields():
    action = resolve_artifact_action(
        {
            "action_type": "export",
            "enabled": True,
            "payload": {
                "raw_sql": "select * from orders",
                "raw_result": [{"name": "secret"}],
                "schema": {"tables": ["orders"]},
                "capsule": {"dataset_id": 1},
                "trace": {"body": {"prompt": "internal"}},
                "control_plane": {"raw_sql": "select * from orders"},
            },
        }
    )

    assert action is not None
    _assert_no_forbidden_payload_keys(action)
    dumped = json.dumps(action, ensure_ascii=False).lower()
    assert "select * from orders" not in dumped
    assert "secret" not in dumped
    assert "control_plane" not in dumped
