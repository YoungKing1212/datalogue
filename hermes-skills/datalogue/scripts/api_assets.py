#!/usr/bin/env python3
# ============================================================
# File Name   : api_assets.py
# Description:
#   通过 Datalogue 常驻 API 实时查询 Hermes Skill 所需语义资产。
#
# Responsibilities:
#   - 调用已有只读 API 获取数据集、指标、维度、蓝图、Schema、术语和 Manifest。
#   - 提供自然语言轻量检索和 SQL 生成上下文，供 Hermes Agent 判断可用资产。
#   - 仅通过 Datalogue 只读 SQL preview API 执行查询，不修改任何业务数据。
#
# Author      : yangkai
# Created On  : 2026-06-23
# ============================================================

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = os.getenv("DATALOGUE_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("DATALOGUE_API_TIMEOUT_SECONDS", "20"))


class DatalogueApiError(RuntimeError):
    """Datalogue API 调用失败。"""


def _json_default(value: Any) -> str:
    return str(value)


def _api_get(base_url: str, path: str, timeout: float) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DatalogueApiError(f"GET {path} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise DatalogueApiError(f"GET {path} failed: {exc.reason}") from exc
    if not raw:
        return None
    return json.loads(raw)


def _api_get_optional(base_url: str, path: str, timeout: float) -> Any:
    try:
        return _api_get(base_url, path, timeout)
    except DatalogueApiError as exc:
        return {"error": str(exc)}


def _api_post(base_url: str, path: str, payload: dict[str, Any], timeout: float) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    raw = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=raw,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DatalogueApiError(f"POST {path} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise DatalogueApiError(f"POST {path} failed: {exc.reason}") from exc
    if not body:
        return None
    return json.loads(body)


def health(base_url: str, timeout: float) -> dict[str, Any]:
    return {
        "base_url": base_url.rstrip("/"),
        "health": _api_get(base_url, "/health", timeout),
    }


def list_datasets(base_url: str, timeout: float) -> dict[str, Any]:
    datasets = _api_get(base_url, "/api/dataset", timeout)
    return {
        "base_url": base_url.rstrip("/"),
        "items": datasets or [],
    }


def describe_dataset(base_url: str, timeout: float, dataset_id: int) -> dict[str, Any]:
    prefix = f"/api/dataset/{dataset_id}"
    return {
        "base_url": base_url.rstrip("/"),
        "dataset_id": dataset_id,
        "dataset": _api_get(base_url, prefix, timeout),
        "metrics": _api_get_optional(base_url, f"{prefix}/metrics", timeout),
        "dimensions": _api_get_optional(base_url, f"{prefix}/dimensions", timeout),
        "terms": _api_get_optional(base_url, f"{prefix}/terms", timeout),
        "blueprints": _api_get_optional(base_url, f"{prefix}/blueprints", timeout),
        "selected_tables": _api_get_optional(base_url, f"{prefix}/selected-tables", timeout),
        "selected_columns": _api_get_optional(base_url, f"{prefix}/selected-columns", timeout),
        "manifest": _api_get_optional(base_url, f"{prefix}/subagent-manifest", timeout),
    }


def capabilities(base_url: str, timeout: float) -> dict[str, Any]:
    return {
        "base_url": base_url.rstrip("/"),
        "mode": "live_api",
        "health_path": "/health",
        "capabilities": [
            {
                "name": "dataset_lookup",
                "path": "GET /api/dataset",
                "description": "列出可用数据集。",
            },
            {
                "name": "metric_lookup",
                "path": "GET /api/dataset/{dataset_id}/metrics",
                "description": "查询数据集已有指标。",
            },
            {
                "name": "dimension_lookup",
                "path": "GET /api/dataset/{dataset_id}/dimensions",
                "description": "查询数据集已有维度。",
            },
            {
                "name": "blueprint_lookup",
                "path": "GET /api/dataset/{dataset_id}/blueprints",
                "description": "查询数据集已有分析蓝图。",
            },
            {
                "name": "schema_lookup",
                "path": "GET /api/dataset/{dataset_id}/selected-columns",
                "description": "查询数据集已选 schema 字段。",
            },
            {
                "name": "term_lookup",
                "path": "GET /api/dataset/{dataset_id}/terms",
                "description": "查询数据集业务术语。",
            },
            {
                "name": "manifest_lookup",
                "path": "GET /api/dataset/{dataset_id}/subagent-manifest",
                "description": "查询当前 Manifest 治理状态。",
            },
            {
                "name": "query_plan_context",
                "path": "scripts/api_assets.py plan-query",
                "description": "为 Hermes 生成 SQL 前组装数据集候选、匹配资产和已选 schema 上下文。",
            },
            {
                "name": "readonly_sql_preview",
                "path": "POST /api/dataset/{dataset_id}/sql/preview",
                "description": "仅通过数语后端 Guard 后的只读 SQL preview 接口执行 SELECT/WITH 查询。",
            },
        ],
    }


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _terms(question: str) -> list[str]:
    lowered = question.lower()
    words = re.findall(r"[a-zA-Z0-9_]+", lowered)
    cjk = re.findall(r"[\u4e00-\u9fff]+", question)
    chunks: list[str] = []
    for block in cjk:
        chunks.extend(block[i : i + 2] for i in range(max(len(block) - 1, 0)))
        chunks.extend(block[i : i + 3] for i in range(max(len(block) - 2, 0)))
    seen: set[str] = set()
    result: list[str] = []
    for item in [lowered, *words, *chunks]:
        item = item.strip()
        if len(item) < 2 or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _score(question: str, item: dict[str, Any], fields: list[str]) -> tuple[int, list[str]]:
    blob = " ".join(_text(item.get(field)) for field in fields).lower()
    score = 0
    signals: list[str] = []
    for term in _terms(question):
        if term.lower() in blob:
            signals.append(term)
            score += 3 if len(term) >= 3 else 1
    if question.lower() in blob:
        score += 10
    return score, signals[:12]


def _rank(
    *,
    question: str,
    items: list[dict[str, Any]],
    fields: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in items:
        score, signals = _score(question, item, fields)
        if score <= 0:
            continue
        compact = dict(item)
        compact["_match_score"] = score
        compact["_match_signals"] = signals
        matches.append(compact)
    matches.sort(key=lambda item: (item["_match_score"], item.get("id") or 0), reverse=True)
    return matches[:limit]


def _schema_columns(description: dict[str, Any]) -> list[dict[str, Any]]:
    dataset = description.get("dataset") or {}
    dataset_id = dataset.get("id") or description.get("dataset_id")
    dataset_name = dataset.get("name")
    tables_by_name = {
        item.get("table_name"): item
        for item in (description.get("selected_tables") or [])
        if isinstance(item, dict)
    }
    columns: list[dict[str, Any]] = []
    for column in description.get("selected_columns") or []:
        if not isinstance(column, dict):
            continue
        table = tables_by_name.get(column.get("table_name")) or {}
        merged = dict(column)
        merged["dataset_id"] = dataset_id
        merged["dataset_name"] = dataset_name
        merged["table_comment"] = table.get("table_comment")
        merged["table_effective_desc"] = table.get("effective_desc")
        columns.append(merged)
    return columns


def _descriptions_for_search(
    base_url: str,
    timeout: float,
    dataset_id: int | None,
) -> list[dict[str, Any]]:
    if dataset_id is not None:
        return [describe_dataset(base_url, timeout, dataset_id)]
    dataset_payload = list_datasets(base_url, timeout)
    descriptions: list[dict[str, Any]] = []
    for dataset in dataset_payload.get("items") or []:
        if not isinstance(dataset, dict) or dataset.get("id") is None:
            continue
        descriptions.append(describe_dataset(base_url, timeout, int(dataset["id"])))
    return descriptions


def search_assets(
    base_url: str,
    timeout: float,
    question: str,
    dataset_id: int | None,
    limit: int,
) -> dict[str, Any]:
    descriptions = _descriptions_for_search(base_url, timeout, dataset_id)
    datasets: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    terms: list[dict[str, Any]] = []
    blueprints: list[dict[str, Any]] = []
    schema_columns: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []

    for description in descriptions:
        dataset = description.get("dataset")
        if isinstance(dataset, dict):
            datasets.append(dataset)
        for key, target in [
            ("metrics", metrics),
            ("dimensions", dimensions),
            ("terms", terms),
            ("blueprints", blueprints),
        ]:
            values = description.get(key)
            if isinstance(values, list):
                target.extend(item for item in values if isinstance(item, dict))
        schema_columns.extend(_schema_columns(description))
        manifest = description.get("manifest")
        if isinstance(manifest, dict) and "error" not in manifest:
            manifests.append(manifest)

    return {
        "base_url": base_url.rstrip("/"),
        "question": question,
        "dataset_id": dataset_id,
        "limit": limit,
        "matches": {
            "datasets": _rank(
                question=question,
                items=datasets,
                fields=["name", "description", "status", "query_constraints", "tables_json"],
                limit=limit,
            ),
            "metrics": _rank(
                question=question,
                items=metrics,
                fields=["name", "display_name", "description", "expr", "table_name", "time_field", "synonyms"],
                limit=limit,
            ),
            "dimensions": _rank(
                question=question,
                items=dimensions,
                fields=["name", "display_name", "column_name", "table_name", "enum_values", "synonyms", "hierarchy"],
                limit=limit,
            ),
            "blueprints": _rank(
                question=question,
                items=blueprints,
                fields=["name", "description", "trigger_keywords", "trigger_examples", "when_to_use", "parameters", "steps"],
                limit=limit,
            ),
            "schema_columns": _rank(
                question=question,
                items=schema_columns,
                fields=[
                    "dataset_name",
                    "table_name",
                    "table_comment",
                    "table_effective_desc",
                    "column_name",
                    "data_type",
                    "column_comment",
                    "effective_desc",
                    "semantic_role",
                    "sample_values",
                    "synonyms",
                ],
                limit=limit,
            ),
            "terms": _rank(
                question=question,
                items=terms,
                fields=["name", "display_name", "term_type", "definition", "aliases", "examples", "asset_links"],
                limit=limit,
            ),
            "manifests": _rank(
                question=question,
                items=manifests,
                fields=["manifest_version", "bound_schema_version", "review_status", "schema_hash", "quality_status", "permission_scope"],
                limit=limit,
            ),
        },
    }


def _compact_schema_columns(columns: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for column in columns[:limit]:
        compact.append(
            {
                "table_name": column.get("table_name"),
                "column_name": column.get("column_name"),
                "data_type": column.get("data_type"),
                "column_comment": column.get("column_comment"),
                "effective_desc": column.get("effective_desc"),
                "semantic_role": column.get("semantic_role")
                or column.get("ai_semantic_role")
                or column.get("user_semantic_role"),
                "sample_values": column.get("sample_values"),
            }
        )
    return compact


def plan_query(
    base_url: str,
    timeout: float,
    question: str,
    dataset_id: int | None,
    limit: int,
    schema_limit: int,
) -> dict[str, Any]:
    """为 Hermes 生成 SQL 前准备最小语义上下文，不替模型生成 SQL。"""

    routing_matches = search_assets(base_url, timeout, question, dataset_id, limit)
    dataset_candidates = routing_matches.get("matches", {}).get("datasets") or []
    selected_dataset_id = dataset_id
    if selected_dataset_id is None and dataset_candidates:
        selected_dataset_id = int(dataset_candidates[0]["id"])

    # 先全局找候选数据集，再把 SQL 生成资产收窄到选中数据集，避免跨数据集字段误入 SQL。
    asset_matches = (
        search_assets(base_url, timeout, question, selected_dataset_id, limit)
        if selected_dataset_id is not None
        else routing_matches
    )
    selected_context: dict[str, Any] | None = None
    if selected_dataset_id is not None:
        selected_context = describe_dataset(base_url, timeout, selected_dataset_id)

    schema_columns = _schema_columns(selected_context or {}) if selected_context else []
    return {
        "base_url": base_url.rstrip("/"),
        "question": question,
        "selected_dataset_id": selected_dataset_id,
        "dataset_candidates": dataset_candidates,
        "matched_assets": asset_matches.get("matches", {}),
        "selected_context": {
            "dataset": (selected_context or {}).get("dataset"),
            "metrics": (selected_context or {}).get("metrics") or [],
            "dimensions": (selected_context or {}).get("dimensions") or [],
            "terms": (selected_context or {}).get("terms") or [],
            "blueprints": (selected_context or {}).get("blueprints") or [],
            "selected_tables": (selected_context or {}).get("selected_tables") or [],
            "selected_columns": _compact_schema_columns(schema_columns, max(schema_limit, 1)),
            "manifest": (selected_context or {}).get("manifest"),
        },
        "sql_generation_rules": [
            "只能基于 selected_tables/selected_columns 中存在的表和字段生成 SQL。",
            "优先使用 matched_assets 中命中的已有蓝图、指标、维度和业务术语，不猜不存在的口径。",
            "只生成 SELECT 或 WITH 查询，不生成 INSERT/UPDATE/DELETE/DROP/DDL。",
            "若问题没有明确返回条数，应保留或补充合理 LIMIT；后端还会按数据集 query_constraints 裁剪。",
            "生成 SQL 后必须调用 execute-sql，不要直连数据库，也不要调用 /api/chat/stream。",
        ],
        "next_step": (
            f"生成 SQL 后运行: scripts/api_assets.py execute-sql {selected_dataset_id} --sql '<SQL>'"
            if selected_dataset_id is not None
            else "先根据 dataset_candidates 选择 dataset_id，再生成 SQL。"
        ),
    }


def execute_sql(
    base_url: str,
    timeout: float,
    dataset_id: int,
    sql: str,
    question: str | None,
    limit: int | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"sql": sql}
    if question:
        payload["question"] = question
    if limit is not None:
        payload["limit"] = limit
    return _api_post(base_url, f"/api/dataset/{dataset_id}/sql/preview", payload, timeout)


def _print(payload: Any) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Call live Datalogue semantic asset APIs for Hermes.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Datalogue API base URL.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout seconds.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health", help="Check Datalogue API health.")
    subparsers.add_parser("capabilities", help="Show supported live API capabilities.")
    subparsers.add_parser("list-datasets", help="List Datalogue datasets.")

    describe_parser = subparsers.add_parser("describe-dataset", help="Describe one dataset and its assets.")
    describe_parser.add_argument("dataset_id", type=int)

    search_parser = subparsers.add_parser("search-assets", help="Search live semantic assets.")
    search_parser.add_argument("question")
    search_parser.add_argument("--dataset-id", type=int, default=None)
    search_parser.add_argument("--limit", type=int, default=8)

    plan_parser = subparsers.add_parser("plan-query", help="Prepare SQL-generation context for a question.")
    plan_parser.add_argument("question")
    plan_parser.add_argument("--dataset-id", type=int, default=None)
    plan_parser.add_argument("--limit", type=int, default=8)
    plan_parser.add_argument("--schema-limit", type=int, default=120)

    execute_parser = subparsers.add_parser("execute-sql", help="Execute readonly SQL through Datalogue preview API.")
    execute_parser.add_argument("dataset_id", type=int)
    execute_parser.add_argument("--sql", required=True)
    execute_parser.add_argument("--question", default=None)
    execute_parser.add_argument("--limit", type=int, default=None)

    args = parser.parse_args(argv)
    try:
        if args.command == "health":
            return _print(health(args.base_url, args.timeout))
        if args.command == "capabilities":
            return _print(capabilities(args.base_url, args.timeout))
        if args.command == "list-datasets":
            return _print(list_datasets(args.base_url, args.timeout))
        if args.command == "describe-dataset":
            return _print(describe_dataset(args.base_url, args.timeout, args.dataset_id))
        if args.command == "search-assets":
            return _print(
                search_assets(
                    args.base_url,
                    args.timeout,
                    args.question,
                    args.dataset_id,
                    max(args.limit, 1),
                )
            )
        if args.command == "plan-query":
            return _print(
                plan_query(
                    args.base_url,
                    args.timeout,
                    args.question,
                    args.dataset_id,
                    max(args.limit, 1),
                    max(args.schema_limit, 1),
                )
            )
        if args.command == "execute-sql":
            return _print(
                execute_sql(
                    args.base_url,
                    args.timeout,
                    args.dataset_id,
                    args.sql,
                    args.question,
                    args.limit,
                )
            )
    except DatalogueApiError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
