# ============================================================
# File Name   : bi_workbench.py
# Description:
#   Datalogue 问数工作台事件 envelope Schema。
#
# Responsibilities:
#   - 定义可被 SSE 与未来 AgentScope event stream 复用的业务事件协议。
#   - 统一处理用户可见事件的敏感字段脱敏边界。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


DatalogueEventType = Literal[
    "route.started",
    "dataset.selected",
    "clarification.required",
    "dataset.query.started",
    "dataset.query.completed",
    "artifact.created",
    "answer.completed",
    "error.blocked",
]

DatalogueEventVisibility = Literal["user_visible", "trace_only", "control_plane"]

_USER_VISIBLE_BLOCKED_KEYS = {
    "capsule",
    "control_plane",
    "data",
    "direct_sql",
    "dsl",
    "query_task_capsule",
    "raw",
    "raw_sql",
    "records",
    "result",
    "result_rows",
    "rows",
    "sample_rows",
    "schema",
    "schema_context",
    "sql",
    "sql_list",
    "sql_result",
}
_SQL_TEXT_RE = re.compile(
    r"(?is)\b(select|insert|update|delete|drop|alter|create|with)\b"
    r".{0,200}\b(from|into|set|table|join|where|values)\b"
)


class DatalogueEventEnvelope(BaseModel):
    """跨 SSE 与 AgentScope 的统一业务事件外壳。"""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: DatalogueEventType
    visibility: DatalogueEventVisibility
    created_at: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _is_blocked_user_visible_key(key: str) -> bool:
    key_lower = key.lower()
    return key_lower in _USER_VISIBLE_BLOCKED_KEYS or "sql" in key_lower


def sanitize_event_payload(value: Any, *, key_name: str = "") -> Any:
    """递归清理 user_visible 事件，避免把执行明细和控制面主体下发给前端。"""

    if _is_blocked_user_visible_key(key_name):
        return None
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or _is_blocked_user_visible_key(key):
                continue
            safe_item = sanitize_event_payload(item, key_name=key)
            if safe_item in (None, "", [], {}):
                continue
            sanitized[key] = safe_item
        return sanitized
    if isinstance(value, list):
        # user_visible 只保留小型摘要列表，完整结果集必须通过 artifact/ref 访问。
        return [
            item
            for item in (sanitize_event_payload(item, key_name=key_name) for item in value[:8])
            if item not in (None, "", [], {})
        ]
    if isinstance(value, str):
        text = value.strip()
        if _SQL_TEXT_RE.search(text):
            return None
        return text[:1000]
    return value


def build_datalogue_event_envelope(
    *,
    event_type: DatalogueEventType,
    visibility: DatalogueEventVisibility,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> DatalogueEventEnvelope:
    """构造统一事件 envelope；用户可见事件在这里集中执行脱敏。"""

    raw_payload = payload or {}
    raw_metadata = metadata or {}
    if visibility == "user_visible":
        safe_payload = sanitize_event_payload(raw_payload)
        safe_metadata = sanitize_event_payload(raw_metadata)
    else:
        safe_payload = raw_payload
        safe_metadata = raw_metadata
    return DatalogueEventEnvelope(
        event_type=event_type,
        visibility=visibility,
        payload=safe_payload if isinstance(safe_payload, dict) else {},
        metadata=safe_metadata if isinstance(safe_metadata, dict) else {},
    )
