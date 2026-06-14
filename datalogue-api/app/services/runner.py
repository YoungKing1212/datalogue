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
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

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
            display_name=f"SubAgent · {dataset_name or request.dataset_id}",
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
        display_name="多轮 · Delta 合并",
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
