# ============================================================
# File Name   : payload_sanitizer.py
# Description:
#   Datalogue 业务 payload 脱敏器。
#
# Responsibilities:
#   - 清理 SQL、schema、raw rows、query_plan、repair patch 等内部执行载荷。
#   - 为 AgentScope Agent Team worker 工具、BI 工具链和 Workbench 输出提供统一安全边界。
#   - 保持脱敏逻辑独立于运行时编排类命名。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import re
from typing import Any


FORBIDDEN_DATALOGUE_PAYLOAD_KEYS = {
    "sql",
    "raw_sql",
    "direct_sql",
    "llm_sql",
    "schema",
    "schema_context",
    "schema_structured",
    "ddl_context",
    "raw_rows",
    "raw_result",
    "query_plan",
    "repair_patch",
    "patch_body",
    "blueprint",
    "blueprint_context",
}

FORBIDDEN_DATALOGUE_KEY_FRAGMENTS = {
    "ddl",
    "directsql",
    "field",
    "fields",
    "llmsql",
    "patchbody",
    "queryplan",
    "raw",
    "rawresult",
    "rawrows",
    "repairpatch",
    "rows",
    "schema",
    "sql",
}

SAFE_SCHEMA_SUMMARY_KEYS = {
    "metadata_schema_summary",
    "selected_table_count",
}

FORBIDDEN_TASK_REQUEST_KEYS = {
    "capsule",
    "control_plane",
    "data",
    "direct_sql",
    "dsl",
    "patch",
    "patch_body",
    "query_plan",
    "raw",
    "raw_result",
    "records",
    "result_rows",
    "rows",
    "sample_rows",
    "schema",
    "schema_context",
    "sql",
    "sql_list",
    "sql_result",
    "subagent_control_plane",
}

FORBIDDEN_TASK_REQUEST_KEY_FRAGMENTS = (
    "sql",
    "schema",
    "raw",
    "rows",
    "record",
    "queryplan",
    "repairpatch",
    "patchbody",
    "blueprintbody",
)

SQL_TEXT_RE = re.compile(
    r"(?is)\b(select|insert|update|delete|drop|alter|create|with)\b"
    r".{0,200}\b(from|into|set|table|join|where|values)\b"
)


class DataloguePayloadSanitizer:
    """业务可见 payload 清洗器；只保留用户/Agent 可见的安全摘要。"""

    def sanitize_output(self, value: Any) -> Any:
        """递归清理内部执行态字段；返回可进入事件、工具输出和最终回答的值。"""

        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                # SQL/schema/raw rows/query_plan 等只允许留在 Datalogue 私有执行上下文。
                if self._is_forbidden_output_key(str(key)):
                    continue
                sanitized[key] = self.sanitize_output(item)
            return sanitized
        if isinstance(value, list):
            sanitized_items = [self.sanitize_output(item) for item in value]
            return [item for item in sanitized_items if item is not None]
        if isinstance(value, str):
            return None if self._looks_like_execution_payload(value) else value
        return value

    @classmethod
    def _is_forbidden_output_key(cls, key: str) -> bool:
        return cls._is_forbidden_key(key, allow_schema_summary=True)

    @classmethod
    def _is_forbidden_key(cls, key: str, *, allow_schema_summary: bool) -> bool:
        normalized = cls._normalize_key(key)
        if allow_schema_summary and key in SAFE_SCHEMA_SUMMARY_KEYS:
            return False
        exact_forbidden = {cls._normalize_key(item) for item in FORBIDDEN_DATALOGUE_PAYLOAD_KEYS}
        if normalized in exact_forbidden:
            return not (allow_schema_summary and normalized == "blueprint")
        return any(fragment in normalized for fragment in FORBIDDEN_DATALOGUE_KEY_FRAGMENTS)

    @staticmethod
    def _normalize_key(key: str) -> str:
        return "".join(char for char in str(key).lower() if char.isalnum())

    @staticmethod
    def _looks_like_execution_payload(value: str) -> bool:
        lowered = value.lower()
        sql_markers = (
            "select ",
            " from ",
            " join ",
            " where ",
            "insert ",
            "update ",
            "delete ",
        )
        if any(marker in lowered for marker in sql_markers):
            return True
        # table.column 形式通常是物理字段明细，用户可见层只保留业务摘要。
        return "." in value and any(char.isalpha() for char in value)


def sanitize_datalogue_payload(value: Any) -> Any:
    """函数式入口，便于无状态调用方直接清洗 payload。"""

    return DataloguePayloadSanitizer().sanitize_output(value)


def contains_internal_task_payload(value: Any) -> bool:
    """识别 task 请求中不允许由客户端提交的内部执行态字段。"""

    if isinstance(value, dict):
        for key, item in value.items():
            if _is_forbidden_task_request_key(str(key)):
                return True
            if contains_internal_task_payload(item):
                return True
        return False
    if isinstance(value, list):
        return any(contains_internal_task_payload(item) for item in value)
    if isinstance(value, str):
        return SQL_TEXT_RE.search(value) is not None
    return False


def _is_forbidden_task_request_key(key: str) -> bool:
    normalized = DataloguePayloadSanitizer._normalize_key(key)
    exact = {
        DataloguePayloadSanitizer._normalize_key(item)
        for item in FORBIDDEN_TASK_REQUEST_KEYS
    }
    return normalized in exact or any(
        fragment in normalized for fragment in FORBIDDEN_TASK_REQUEST_KEY_FRAGMENTS
    )
