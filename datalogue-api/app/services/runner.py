# ============================================================
# File Name   : runner.py
# Description:
#   SubAgent 运行器抽象。
#
# Responsibilities:
#   - 定义 LeadAgent 调用数据集 SubAgent 的进程内协议。
#   - 为后续拆分独立 SubAgent 服务预留 trace 和 parent observation 字段。
#   - 在当前进程内执行 LangGraph，并包裹 SubAgent 级可观测 span。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import asdict, dataclass
import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.observability.tracer import ObservabilityTraceContext, get_observability_tracer


@dataclass
class DatasetSubAgentRequest:
    """SubAgent 调用协议。trace 字段为将来跨进程部署预留，进程内可不填。"""

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


class InProcessDatasetSubAgentRunner:
    """在当前进程内执行 SubAgent 图，同时包裹 subagent.{dataset_id} span。"""

    def __init__(self, graph: Any, db: Session):
        self.graph = graph
        self.db = db

    async def run(
        self,
        request: DatasetSubAgentRequest,
        trace_context: ObservabilityTraceContext | None,
        initial_state: dict[str, Any],
        dataset_name: str = "",
        **graph_kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        tracer = get_observability_tracer()
        span_key = f"subagent.{request.dataset_id}"
        tracer.start_span(
            trace_context,
            node=span_key,
            display_name=span_key,
            input_payload={
                "question": request.question,
                "dataset_id": request.dataset_id,
                "manifest_version": request.manifest_version,
                "bound_schema_version": request.bound_schema_version,
                "prior_capsule_status": request.prior_capsule_status,
                "prior_capsule_loaded": request.prior_capsule is not None,
                "trace_id": request.trace_id,
                "parent_observation_id": request.parent_observation_id,
            },
            trace_tags=["sub", f"dataset:{request.dataset_id}"],
        )
        error: str | None = None
        state = dict(initial_state)
        if request.prior_capsule is not None and state.get("prior_capsule") is None:
            state["prior_capsule"] = request.prior_capsule
        if request.prior_capsule_status is not None:
            state["prior_capsule_status"] = request.prior_capsule_status
        delta_merge_recorded = False
        try:
            async for event in self.graph.astream_events(state, **graph_kwargs):
                if not delta_merge_recorded and _is_merge_prior_context_end_event(event):
                    delta_merge_recorded = True
                    _record_delta_merge_span(
                        tracer,
                        trace_context,
                        state,
                        event,
                    )
                yield event
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            tracer.end_span(
                trace_context,
                node=span_key,
                output_payload={
                    "dataset_id": request.dataset_id,
                    "manifest_version": request.manifest_version,
                    "bound_schema_version": request.bound_schema_version,
                    "status": "error" if error else "success",
                },
                error=error,
            )


class RemoteDatasetSubAgentRunner:
    """通过内部 A2A HTTP 流式协议调用远端 DatasetSubAgent 服务。"""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        retries: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        resolved_base_url = base_url or settings.SUBAGENT_REMOTE_BASE_URL
        if not resolved_base_url:
            raise ValueError("SUBAGENT_REMOTE_BASE_URL is required for remote subagent runner")
        self.base_url = resolved_base_url.rstrip("/")
        self.api_key = api_key if api_key is not None else settings.SUBAGENT_REMOTE_API_KEY
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else settings.SUBAGENT_REMOTE_TIMEOUT_SECONDS
        )
        self.retries = int(
            retries
            if retries is not None
            else settings.SUBAGENT_REMOTE_RETRIES
        )
        self.client = client or httpx.AsyncClient(timeout=self.timeout_seconds)

    async def run(
        self,
        request: DatasetSubAgentRequest,
        trace_context: ObservabilityTraceContext | None,
        initial_state: dict[str, Any],
        dataset_name: str = "",
        **graph_kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        payload = {
            "request": asdict(request),
            "initial_state": initial_state,
            "dataset_name": dataset_name,
            "graph_kwargs": graph_kwargs,
            "trace_context": {
                "trace_id": getattr(trace_context, "trace_id", None) or request.trace_id,
                "parent_observation_id": request.parent_observation_id
                or getattr(trace_context, "root_observation_id", None),
            },
        }
        headers = {"Accept": "application/x-ndjson"}
        if self.api_key:
            headers["X-Datalogue-Internal-Token"] = self.api_key

        try:
            response = await self._post_with_retries(payload, headers)
            if response.status_code >= 400:
                yield self._safe_error_event(
                    f"remote subagent request failed with status {response.status_code}"
                )
                return
            async for event in self._iter_events(response):
                yield event
        except TimeoutError as exc:
            yield self._safe_error_event(f"remote subagent timeout: {exc}")
        except httpx.TimeoutException as exc:
            yield self._safe_error_event(f"remote subagent timeout: {exc}")
        except Exception as exc:
            yield self._safe_error_event(f"remote subagent error: {exc}")

    async def _post_with_retries(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(max(0, self.retries) + 1):
            try:
                return await self.client.post(
                    f"{self.base_url}/internal/subagent/run",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            except httpx.TimeoutException:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt >= self.retries:
                    raise
        raise last_exc or RuntimeError("remote subagent request failed")

    async def _iter_events(
        self,
        response: httpx.Response,
    ) -> AsyncGenerator[dict[str, Any], None]:
        async for line in response.aiter_lines():
            text = line.strip()
            if not text:
                continue
            if text.startswith("data:"):
                text = text[5:].strip()
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload

    @staticmethod
    def _safe_error_event(raw_error: str) -> dict[str, Any]:
        return {
            "event_type": "result",
            "payload": {
                "final_state": {
                    "error": "remote_subagent_error",
                    "raw_error": raw_error,
                }
            },
        }


def _is_merge_prior_context_end_event(event: dict[str, Any]) -> bool:
    return (
        event.get("event") == "on_chain_end"
        and (event.get("metadata") or {}).get("langgraph_node") == "merge_prior_context"
    )


def _record_delta_merge_span(
    tracer: Any,
    trace_context: ObservabilityTraceContext | None,
    initial_state: dict[str, Any],
    event: dict[str, Any],
) -> None:
    output = ((event.get("data") or {}).get("output") or {})
    prior_capsule = initial_state.get("prior_capsule") if isinstance(initial_state, dict) else None
    prior_query_context = (prior_capsule or {}).get("query_context") if isinstance(prior_capsule, dict) else None
    tracer.start_span(
        trace_context,
        node="delta-merge",
        display_name="delta-merge",
        input_payload={
            "question": initial_state.get("question"),
            "prior_capsule_status": initial_state.get("prior_capsule_status"),
            "prior_query_context": prior_query_context,
        },
    )
    tracer.end_span(
        trace_context,
        node="delta-merge",
        output_payload={
            "turn_type": output.get("turn_type"),
            "multiturn_context": output.get("multiturn_context"),
            "merge_debug": output.get("merge_debug"),
            "entry_route": output.get("entry_route"),
        },
    )
