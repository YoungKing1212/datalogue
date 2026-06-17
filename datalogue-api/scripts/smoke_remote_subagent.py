#!/usr/bin/env python3
# ============================================================
# File Name   : smoke_remote_subagent.py
# Description:
#   A2A Remote SubAgent 双服务 smoke 验证脚本。
#
# Responsibilities:
#   - 校验 SUBAGENT_REMOTE_BASE_URL 必须包含 /api 的配置约定。
#   - 对远端 /api/internal/subagent/run 发起 NDJSON 调用并打印事件摘要。
#   - 辅助验证内部 token、HTTP 500、timeout、流中断的安全错误映射。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DatasetSubAgentRequestPayload:
    question: str
    dataset_id: int
    manifest_version: str | None
    bound_schema_version: str | None
    thread_id: str
    time_context: dict[str, Any]
    thread_context: dict[str, Any]
    route_decision: dict[str, Any]
    schema_status: dict[str, Any]
    lead_agent_context: dict[str, Any]
    prior_capsule: dict[str, Any] | None = None
    prior_capsule_status: dict[str, Any] | None = None
    query_task_capsule: dict[str, Any] | None = None
    turn_event: dict[str, Any] | None = None
    trace_id: str | None = None
    parent_observation_id: str | None = None


def _health_url(api_base_url: str) -> str:
    if not api_base_url.rstrip("/").endswith("/api"):
        raise ValueError("remote base url must include /api, e.g. http://localhost:8001/api")
    return api_base_url.rstrip("/")[:-4] + "/health"


def _post_ndjson(url: str, payload: dict[str, Any], token: str | None, timeout: float):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/x-ndjson",
    }
    if token:
        headers["X-Datalogue-Internal-Token"] = token
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            yield json.loads(line)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke A2A remote SubAgent. Example: start main API on 8000, remote API on 8001, "
            "then run SUBAGENT_RUNNER_MODE=remote SUBAGENT_REMOTE_BASE_URL=http://localhost:8001/api "
            "on the main service and use this script against the remote service."
        )
    )
    parser.add_argument("--remote-api", default="http://localhost:8001/api")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--dataset-id", type=int, required=True)
    parser.add_argument("--question", default="查询 1 条数据")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--trace-id", default="smoke-trace")
    parser.add_argument("--parent-observation-id", default="smoke-parent")
    args = parser.parse_args()

    remote_api = args.remote_api.rstrip("/")
    try:
        health_url = _health_url(remote_api)
        with urllib.request.urlopen(health_url, timeout=args.timeout) as response:
            print(f"health {response.status}: {health_url}")
    except Exception as exc:  # noqa: BLE001
        print(f"health check failed: {exc}", file=sys.stderr)
        return 2

    request_payload = DatasetSubAgentRequestPayload(
        question=args.question,
        dataset_id=args.dataset_id,
        manifest_version=None,
        bound_schema_version=None,
        thread_id="smoke-thread",
        time_context={},
        thread_context={},
        route_decision={"decision": "selected", "dataset_id": args.dataset_id},
        schema_status={"status": "smoke"},
        lead_agent_context={"resolved_question": args.question},
        prior_capsule_status={"status": "none"},
        trace_id=args.trace_id,
        parent_observation_id=args.parent_observation_id,
    )
    payload = {
        "request": asdict(request_payload),
        "initial_state": {
            "question": args.question,
            "dataset_id": args.dataset_id,
            "conversation_id": None,
        },
        "graph_kwargs": {"version": "v2", "dataset_name": "smoke"},
        "trace_context": {
            "trace_id": args.trace_id,
            "parent_observation_id": args.parent_observation_id,
        },
    }

    try:
        event_count = 0
        for event in _post_ndjson(
            f"{remote_api}/internal/subagent/run",
            payload,
            args.api_key,
            args.timeout,
        ):
            event_count += 1
            print(json.dumps(event, ensure_ascii=False, default=str))
        print(f"events={event_count}")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"remote http error: {exc.code}", file=sys.stderr)
        return 3
    except TimeoutError:
        print("remote timeout", file=sys.stderr)
        return 4
    except Exception as exc:  # noqa: BLE001
        print(f"remote stream failed: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
