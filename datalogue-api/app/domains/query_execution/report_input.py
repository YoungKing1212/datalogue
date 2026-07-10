# ============================================================
# File Name   : report_input.py
# Description:
#   Report Worker 可读取的查询结果输入投影。
#
# Responsibilities:
#   - 为 sql_result artifact 写入用户可见的 rows/columns 与 report_input_meta。
#   - 按报告预算裁剪明细行和长单元格，避免把大结果直接塞进模型上下文。
#   - 读取 artifact_ref 时执行 fail-closed 校验，阻断 SQL/schema/query_plan/raw rows 等内部态。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

REPORT_INPUT_META_KEY = "report_input_meta"
REPORT_INPUT_STATUS_COMPLETED = "completed"
REPORT_INPUT_STATUS_FAILED = "failed"

FORBIDDEN_REPORT_INPUT_KEYS = {
    "sql",
    "raw_sql",
    "sql_template",
    "sql_preview",
    "schema",
    "schema_context",
    "query_plan",
    "dsl",
    "raw_rows",
    "result_rows",
    "sample_rows",
    "debug",
    "internal_error",
    "repair_payload",
    "repair_patch",
    "blueprint_body",
}
_SAFE_ARTIFACT_CARD_KEYS = {
    "title",
    "subtitle",
    "summary",
    "artifact_ref",
    "row_count",
    "column_count",
}
_SAFE_AUXILIARY_KEYS = {
    "answer_summary",
    "artifact_card",
    "column_labels",
    "display_summary",
    "execution_time_ms",
    "masking_summary",
    "params",
    "safe_summary",
    "source",
    "summary",
}


@dataclass
class _ClipState:
    cell_clipped: bool = False


def build_sql_result_report_payload(
    execution_result: Any,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """构造可落库的 sql_result payload，给 Report Worker 留出受控读取面。"""

    source = execution_result if isinstance(execution_result, dict) else {}
    resolved_settings = settings or get_settings()
    row_limit = max(0, int(getattr(resolved_settings, "REPORT_RESULT_MAX_ROWS", 30) or 30))
    cell_max_chars = max(0, int(getattr(resolved_settings, "REPORT_CELL_MAX_CHARS", 120) or 120))

    source_columns = source.get("columns")
    columns = _safe_columns(source_columns)
    source_rows = _safe_rows(source.get("rows"))
    total_row_count = _safe_int(source.get("row_count"), fallback=len(source_rows))
    visible_rows = source_rows[:row_limit]
    clip_state = _ClipState()
    clipped_rows = [_clip_cell_value(row, max_chars=cell_max_chars, state=clip_state) for row in visible_rows]

    # 落库 payload 只允许用户可见结果字段；执行态、修复态、schema 和 SQL 统一剔除。
    payload = {
        key: _sanitize_auxiliary_value(value, max_chars=cell_max_chars)
        for key, value in source.items()
        if str(key) in _SAFE_AUXILIARY_KEYS and _is_safe_source_key(key)
    }
    payload["columns"] = columns
    payload["rows"] = clipped_rows
    payload["row_count"] = total_row_count
    payload[REPORT_INPUT_META_KEY] = {
        "visible_row_limit": row_limit,
        "visible_cell_max_chars": cell_max_chars,
        "visible_row_count": len(clipped_rows),
        "total_row_count": total_row_count,
        "visible_column_count": len(columns),
        "total_column_count": _safe_int(
            source.get("column_count"),
            fallback=len(source_columns) if isinstance(source_columns, list) else len(columns),
        ),
        "truncated": bool(
            total_row_count > len(clipped_rows)
            or len(source_rows) > len(clipped_rows)
            or clip_state.cell_clipped
            or source.get("truncated") is True
        ),
    }
    return payload


def build_artifact_report_input(artifact: Any, *, artifact_ref: str | None = None) -> dict[str, Any]:
    """把 QueryArtifact 转成 Report Worker 工具返回值；任何不一致都 fail-closed。"""

    resolved_ref = artifact_ref or str(getattr(artifact, "artifact_id", "") or "")
    if artifact is None:
        return _report_input_failure(resolved_ref, "ARTIFACT_NOT_FOUND", "未找到可读取的查询产物。")
    if getattr(artifact, "kind", None) != "sql_result":
        return _report_input_failure(resolved_ref, "ARTIFACT_KIND_UNSUPPORTED", "只允许读取 sql_result 查询产物。")

    content_json = getattr(artifact, "content_json", None)
    if not isinstance(content_json, dict):
        return _report_input_failure(resolved_ref, "ARTIFACT_CONTENT_INVALID", "查询产物内容不是结构化 JSON。")

    meta = content_json.get(REPORT_INPUT_META_KEY)
    if not isinstance(meta, dict):
        return _report_input_failure(resolved_ref, "REPORT_INPUT_META_MISSING", "查询产物缺少报告输入元信息。")
    columns = _safe_columns(content_json.get("columns"))
    rows = _safe_rows(content_json.get("rows"))
    validation_error = _validate_report_input_meta(meta=meta, columns=columns, rows=rows)
    if validation_error:
        return _report_input_failure(resolved_ref, validation_error, "查询产物报告输入元信息不一致，已拒绝读取。")

    return {
        "status": REPORT_INPUT_STATUS_COMPLETED,
        "artifact_ref": resolved_ref,
        "kind": "sql_result",
        "columns": columns,
        "rows": rows,
        REPORT_INPUT_META_KEY: {
            "visible_row_limit": int(meta["visible_row_limit"]),
            "visible_cell_max_chars": int(meta["visible_cell_max_chars"]),
            "visible_row_count": int(meta["visible_row_count"]),
            "total_row_count": int(meta["total_row_count"]),
            "visible_column_count": int(meta["visible_column_count"]),
            "total_column_count": int(meta["total_column_count"]),
            "truncated": bool(meta["truncated"]),
        },
        "safe_summary": _safe_text(
            content_json.get("safe_summary")
            or content_json.get("summary")
            or content_json.get("answer_summary")
            or content_json.get("display_summary")
        ),
        "artifact_card": _safe_artifact_card(content_json.get("artifact_card")),
    }


def _validate_report_input_meta(
    *,
    meta: dict[str, Any],
    columns: list[Any],
    rows: list[Any],
) -> str | None:
    required_keys = {
        "visible_row_limit",
        "visible_cell_max_chars",
        "visible_row_count",
        "total_row_count",
        "visible_column_count",
        "total_column_count",
        "truncated",
    }
    if set(meta) != required_keys:
        return "REPORT_INPUT_META_INVALID"
    try:
        visible_row_limit = int(meta["visible_row_limit"])
        visible_row_count = int(meta["visible_row_count"])
        visible_column_count = int(meta["visible_column_count"])
        total_row_count = int(meta["total_row_count"])
        total_column_count = int(meta["total_column_count"])
    except (TypeError, ValueError):
        return "REPORT_INPUT_META_INVALID"
    if visible_row_limit < 0 or visible_row_count < 0 or visible_column_count < 0:
        return "REPORT_INPUT_META_INVALID"
    if len(rows) != visible_row_count or visible_row_count > visible_row_limit:
        return "REPORT_INPUT_ROW_MISMATCH"
    if len(columns) != visible_column_count:
        return "REPORT_INPUT_COLUMN_MISMATCH"
    if total_row_count < visible_row_count or total_column_count < visible_column_count:
        return "REPORT_INPUT_TOTAL_MISMATCH"
    if not isinstance(meta.get("truncated"), bool):
        return "REPORT_INPUT_META_INVALID"
    return None


def _report_input_failure(artifact_ref: str, code: str, message: str) -> dict[str, Any]:
    return {
        "status": REPORT_INPUT_STATUS_FAILED,
        "artifact_ref": artifact_ref or None,
        "code": code,
        "message": message,
    }


def _is_safe_source_key(key: Any) -> bool:
    key_text = str(key or "").strip()
    if not key_text:
        logger.debug("Skipping empty source key in sql_result report payload.")
        return False
    lowered = key_text.lower()
    if lowered in FORBIDDEN_REPORT_INPUT_KEYS:
        return False
    if _contains_forbidden_report_token(lowered):
        return False
    return key_text not in {"columns", "rows", REPORT_INPUT_META_KEY}


def _safe_columns(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    columns: list[Any] = []
    for item in value:
        if isinstance(item, str) and not _is_safe_row_key(item):
            continue
        columns.append(_clip_cell_value(item, max_chars=120, state=_ClipState()))
    return columns


def _safe_rows(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _clip_cell_value(value: Any, *, max_chars: int, state: _ClipState) -> Any:
    if isinstance(value, str):
        if max_chars >= 0 and len(value) > max_chars:
            state.cell_clipped = True
            return value[:max_chars] + "..."
        return value
    if isinstance(value, dict):
        return {
            str(key): _clip_cell_value(nested, max_chars=max_chars, state=state)
            for key, nested in value.items()
            if _is_safe_row_key(key)
        }
    if isinstance(value, list):
        return [_clip_cell_value(item, max_chars=max_chars, state=state) for item in value]
    return value


def _sanitize_auxiliary_value(value: Any, *, max_chars: int) -> Any:
    state = _ClipState()
    if isinstance(value, dict):
        return {
            str(key): _sanitize_auxiliary_value(nested, max_chars=max_chars)
            for key, nested in value.items()
            if _is_safe_source_key(key)
        }
    if isinstance(value, list):
        return [_sanitize_auxiliary_value(item, max_chars=max_chars) for item in value]
    return _clip_cell_value(value, max_chars=max_chars, state=state)


def _is_safe_row_key(key: Any) -> bool:
    key_text = str(key or "").strip()
    if not key_text:
        return False
    lowered = key_text.lower()
    # rows 是 Report Worker 真实可见的数据面，字段名必须使用与 source/meta 一致的 denylist。
    return lowered not in FORBIDDEN_REPORT_INPUT_KEYS and not _contains_forbidden_report_token(lowered)


def _contains_forbidden_report_token(lowered_key: str) -> bool:
    """拦截内部执行态字段名变体，避免 query_plan_dump/raw_payload 等绕过精确 denylist。"""

    return any(
        token in lowered_key
        for token in ("sql", "schema", "query_plan", "raw", "repair", "dsl", "debug", "internal")
    )


def _safe_int(value: Any, *, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_text(value: Any, *, max_chars: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_chars]


def _safe_artifact_card(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {key: value[key] for key in _SAFE_ARTIFACT_CARD_KEYS if key in value}


__all__ = [
    "FORBIDDEN_REPORT_INPUT_KEYS",
    "REPORT_INPUT_META_KEY",
    "build_artifact_report_input",
    "build_sql_result_report_payload",
]
