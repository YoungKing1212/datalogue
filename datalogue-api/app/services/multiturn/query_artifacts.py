# ============================================================
# File Name   : query_artifacts.py
# Description:
#   多轮问数结果产物与热缓存边界。
#
# Responsibilities:
#   - 为上一轮 SQL 结果和报告生成可跨轮引用的轻量 artifact 元数据。
#   - 提供 Redis 兼容的短 TTL 热缓存接口，当前用进程内实现承接测试与本地开发。
#   - 用严格完整性判定保护“基于上一轮结果集本地过滤”的快速路径。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder

DEFAULT_ARTIFACT_TTL_SECONDS = 30 * 60
ARTIFACT_VERSION = "query_result_artifact.v1"
_LIMIT_RE = re.compile(r"(?is)\blimit\s+\d+\b")


_HOT_CACHE: dict[str, dict[str, Any]] = {}


def build_query_result_artifact(
    *,
    question: str,
    dataset_id: int | None,
    sql: str | None,
    sql_result: dict[str, Any] | None,
    answer: str | None = None,
    schema_version: str | None = None,
    manifest_version: str | None = None,
    ttl_seconds: int = DEFAULT_ARTIFACT_TTL_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """生成上一轮结果 artifact，并写入短 TTL 热缓存。"""

    if not isinstance(sql_result, dict) or not sql_result:
        return None
    rows = sql_result.get("rows")
    if not isinstance(rows, list):
        return None

    now_utc = _utc(now)
    ttl = max(int(ttl_seconds or DEFAULT_ARTIFACT_TTL_SECONDS), 1)
    expires_at = now_utc + timedelta(seconds=ttl)
    complete, completeness_reason = _result_complete(sql=sql, sql_result=sql_result)
    payload = {
        "version": ARTIFACT_VERSION,
        "question": question,
        "dataset_id": dataset_id,
        "schema_version": schema_version or "",
        "manifest_version": manifest_version or "",
        "sql_hash": _hash_text(sql),
        "columns": jsonable_encoder(sql_result.get("columns") or []),
        "row_count": int(sql_result.get("row_count") or len(rows)),
        "rows": jsonable_encoder(rows),
        "complete": complete,
        "completeness_reason": completeness_reason,
        "created_at": now_utc.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ttl_seconds": ttl,
    }
    result_ref = _artifact_ref(payload)
    report_id = _report_id(answer)
    payload["result_ref"] = result_ref
    payload["report_id"] = report_id
    _HOT_CACHE[result_ref] = payload
    return {
        "version": ARTIFACT_VERSION,
        "result_ref": result_ref,
        "report_id": report_id,
        "cache_backend": "memory_redis_compatible",
        "ttl_seconds": ttl,
        "expires_at": payload["expires_at"],
        "complete": complete,
        "completeness_reason": completeness_reason,
        "display_summary": _display_summary(payload),
        "row_count": payload["row_count"],
        "columns": payload["columns"],
    }


def evaluate_query_artifact(
    metadata: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """校验 result_ref 是否仍可用于多轮快速路径。"""

    if not isinstance(metadata, dict) or not metadata.get("result_ref"):
        return None, {"status": "missing", "reason": "no_result_ref"}
    result_ref = str(metadata["result_ref"])
    artifact = _HOT_CACHE.get(result_ref)
    if not artifact:
        return None, {
            "status": "miss",
            "reason": "cache_miss",
            "result_ref": result_ref,
            "cache_backend": metadata.get("cache_backend") or "memory_redis_compatible",
        }
    expires_at = _parse_dt(artifact.get("expires_at"))
    now_utc = _utc(now)
    if expires_at and expires_at <= now_utc:
        _HOT_CACHE.pop(result_ref, None)
        return None, {
            "status": "expired",
            "reason": "ttl_expired",
            "result_ref": result_ref,
            "expired_at": expires_at.isoformat(),
        }
    if not artifact.get("complete"):
        return artifact, {
            "status": "not_eligible",
            "reason": artifact.get("completeness_reason") or "result_not_complete",
            "result_ref": result_ref,
            "complete": False,
        }
    return artifact, {
        "status": "eligible",
        "reason": "artifact_complete_and_hot",
        "result_ref": result_ref,
        "complete": True,
        "expires_at": artifact.get("expires_at"),
        "row_count": artifact.get("row_count"),
        "columns": artifact.get("columns") or [],
    }


def apply_local_result_filter(
    artifact: dict[str, Any],
    *,
    contains_text: str | None = None,
    limit: int | None = None,
) -> dict[str, Any] | None:
    """对完整 artifact 做最保守的本地结果过滤。"""

    if not artifact.get("complete"):
        return None
    rows = artifact.get("rows")
    if not isinstance(rows, list):
        return None
    filtered = list(rows)
    if contains_text:
        needle = str(contains_text).strip()
        if needle:
            filtered = [
                row
                for row in filtered
                if isinstance(row, dict) and any(needle in str(value) for value in row.values())
            ]
    if limit is not None and limit >= 0:
        filtered = filtered[:limit]
    return {
        "columns": artifact.get("columns") or [],
        "rows": filtered,
        "row_count": len(filtered),
        "source": "local_result_filter",
        "result_ref": artifact.get("result_ref"),
    }


def clear_query_artifact_cache() -> None:
    """清理测试和本地开发中的进程内热缓存。"""

    _HOT_CACHE.clear()


def _result_complete(*, sql: str | None, sql_result: dict[str, Any]) -> tuple[bool, str]:
    rows = sql_result.get("rows")
    row_count = int(sql_result.get("row_count") or len(rows or []))
    if sql_result.get("truncated") or sql_result.get("sampled") or sql_result.get("partial"):
        return False, "result_marked_partial"
    if isinstance(rows, list) and row_count != len(rows):
        return False, "row_count_exceeds_cached_rows"
    if sql and _LIMIT_RE.search(sql):
        return False, "sql_limit_makes_result_incomplete"
    return True, "complete_result"


def _artifact_ref(payload: dict[str, Any]) -> str:
    stable = json.dumps(
        {
            "dataset_id": payload.get("dataset_id"),
            "schema_version": payload.get("schema_version"),
            "manifest_version": payload.get("manifest_version"),
            "sql_hash": payload.get("sql_hash"),
            "row_count": payload.get("row_count"),
            "columns": payload.get("columns"),
            "rows": payload.get("rows"),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return f"result:{hashlib.sha256(stable.encode('utf-8')).hexdigest()[:24]}"


def _report_id(answer: str | None) -> str | None:
    if not answer:
        return None
    return f"report:{hashlib.sha256(answer.encode('utf-8')).hexdigest()[:24]}"


def _hash_text(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _display_summary(payload: dict[str, Any]) -> str:
    completeness = "完整结果" if payload.get("complete") else "非完整结果"
    columns = payload.get("columns") or []
    return f"{completeness}，{payload.get('row_count') or 0} 行，{len(columns)} 列"


def _utc(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return _utc(datetime.fromisoformat(str(value)))
    except ValueError:
        return None
