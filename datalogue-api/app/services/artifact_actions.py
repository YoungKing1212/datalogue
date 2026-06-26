# ============================================================
# File Name   : artifact_actions.py
# Description:
#   ArtifactCard 第一阶段动作协议生成器。
#
# Responsibilities:
#   - 将 export / continue_edit 固化为禁用态或受控入口。
#   - 忽略未知动作，避免前端或外层 Agent 触发未登记能力。
#   - 保证用户可见动作 payload 不携带 SQL、schema、capsule、trace body 或 control_plane。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

from typing import Any


RESERVED_ACTIONS = {
    "export": {
        "label": "导出",
        "disabled_reason": "导出能力将在后续版本开放",
    },
    "continue_edit": {
        "label": "继续编辑",
        "disabled_reason": "继续编辑能力将在后续版本开放",
    },
}


def resolve_artifact_action(action: dict[str, Any] | None) -> dict[str, Any] | None:
    """解析单个 ArtifactCard 动作；未知动作 fail-closed，保留动作强制禁用。"""

    if not isinstance(action, dict):
        return None
    action_type = str(action.get("action_type") or "").strip()
    config = RESERVED_ACTIONS.get(action_type)
    if config is None:
        return None

    # 第一阶段只允许向用户暴露禁用态元数据，不透传调用方 payload，避免外层能力误读内部状态。
    return {
        "action_type": action_type,
        "label": str(action.get("label") or config["label"]),
        "enabled": False,
        "disabled_reason": config["disabled_reason"],
        "launches_enhanced_chain": False,
        "payload": {
            "status": "disabled",
            "message": config["disabled_reason"],
        },
    }


def build_artifact_actions(actions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """构造用户可见动作列表，保持输入顺序并跳过未知 action。"""

    visible_actions: list[dict[str, Any]] = []
    for action in actions or []:
        resolved = resolve_artifact_action(action)
        if resolved is not None:
            visible_actions.append(resolved)
    return visible_actions
