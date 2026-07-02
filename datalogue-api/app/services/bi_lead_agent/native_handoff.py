# ============================================================
# File Name   : native_handoff.py
# Description:
#   BI LeadAgent AgentScope native handoff 实现。
#
# Responsibilities:
#   - 以 AgentScope 2.0 DatasetAgent 子运行为内部 handoff 实现。
#   - 将 native child-run 事件投影成 Datalogue BILeadAgentHandoffResult 安全契约。
#   - 保持 Datalogue DB 为 run/confirmation/handoff 的业务状态真相源。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from agentscope.message import UserMsg
from sqlalchemy.orm import Session

from app.models.dataset import SemanticDataset
from app.models.datasource import Datasource
from app.schemas.bi_lead_agent import BILeadAgentHandoffRequest, BILeadAgentHandoffResult
from app.services.agentscope_dataset_runtime import AgentScopeDatasetRuntimeBridge
from app.services.bi_lead_agent.dataset_agent_factory import AgentScopeDatasetAgentFactory
from app.services.bi_lead_agent.handoff_events import (
    collect_native_handoff_payload,
    native_status_or_default,
    safe_native_failure_result_payload,
)
from app.services.bi_tools import build_bi_atomic_toolkit
from app.services.sql_preview import preview_dataset_sql
from app.services.subagent_planning import (
    build_query_plan_compiler_context,
    plan_query,
    recall_candidate_assets,
)


logger = logging.getLogger(__name__)


def _new_prefixed_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class AgentScopeNativeBIHandoff:
    """AgentScope native handoff port；内部使用子 DatasetAgent run，外部只返回 D2 安全结果。"""

    def __init__(
        self,
        *,
        bridge: AgentScopeDatasetRuntimeBridge,
        dataset_agent_factory: AgentScopeDatasetAgentFactory,
        db: Session | None = None,
    ) -> None:
        self.bridge = bridge
        self.dataset_agent_factory = dataset_agent_factory
        self.db = db

    @classmethod
    def from_db(cls, db: Session) -> "AgentScopeNativeBIHandoff":
        toolkit = build_bi_atomic_toolkit(db)
        return cls(
            bridge=AgentScopeDatasetRuntimeBridge(toolkit=toolkit),
            dataset_agent_factory=AgentScopeDatasetAgentFactory(db),
            db=db,
        )

    async def query_dataset(
        self,
        request: BILeadAgentHandoffRequest,
        *,
        task_id: str | None,
    ) -> BILeadAgentHandoffResult:
        handoff_id = _new_prefixed_id("native-handoff")
        child_run_id = _new_prefixed_id("dataset-native-run")
        runtime_context = self._build_runtime_context(request)
        self._bind_query_executor(request=request, dataset=runtime_context.get("dataset"))
        session = self.bridge.start_session(
            dataset_id=request.dataset_id,
            question=request.confirmed_question,
            agent_name="bi_lead_agent",
            trace_id=request.trace_id,
            **runtime_context.get("session_kwargs", {}),
        )  # AgentScope session 是执行态；Datalogue handoff 表仍是业务审计真相源。

        try:
            agent = self.dataset_agent_factory.create(session)
            events = await self.bridge.run_reply_stream(
                agent,
                msg=self._build_native_child_message(
                    request=request,
                    handoff_id=handoff_id,
                    child_run_id=child_run_id,
                ),
                session=session,
            )
            payload = self._collect_payload(events=events, session=session, child_run_id=child_run_id)
            if self._needs_direct_runtime_fallback(payload=payload, session=session):
                direct_payload = await self._run_direct_runtime_fallback(request=request, session=session)
                if direct_payload:
                    events.append(self._event_from_direct_payload(direct_payload, child_run_id=child_run_id))
                    payload = self._collect_payload(events=events, session=session, child_run_id=child_run_id)
            return self._result_from_payload(
                request=request,
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                payload=payload,
            )
        except Exception:
            logger.exception("BI LeadAgent native handoff failed while running AgentScope DatasetAgent.")
            return self._result_from_payload(
                request=request,
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                payload=safe_native_failure_result_payload(),
            )

    @staticmethod
    def _build_native_child_message(
        *,
        request: BILeadAgentHandoffRequest,
        handoff_id: str,
        child_run_id: str,
    ) -> Any:
        content = (
            "AgentScope native handoff: 请作为 DatasetAgent 子运行执行已确认任务。\n"
            f"handoff_id: {handoff_id}\n"
            f"parent_agent: bi_lead_agent\n"
            f"child_agent: dataset_agent\n"
            f"child_run_id: {child_run_id}\n"
            f"dataset_id: {request.dataset_id}\n"
            f"task_goal: {request.task_goal}\n"
            f"confirmed_question: {request.confirmed_question}\n"
            f"routing_rationale: {request.routing_rationale}\n"
            "只能返回安全 JSON：event_type、child_run_id、artifact_ref、checkpoint_ref、answer_summary、row_count、column_count。"
        )
        return UserMsg(name="user", content=content)

    def _build_runtime_context(self, request: BILeadAgentHandoffRequest) -> dict[str, Any]:
        if self.db is None:
            return {}
        dataset = self.db.get(SemanticDataset, request.dataset_id)
        if dataset is None:
            return {}
        allowed_tables, sql_generation_context = _native_allowed_tables_and_sql_context(dataset)
        datasource = self.db.get(Datasource, dataset.datasource_id)
        datasource_dialect = (
            getattr(datasource, "dialect", None)
            or getattr(datasource, "db_type", None)
            or "sqlite"
        )
        return {
            "dataset": dataset,
            "session_kwargs": {
                "sql_generation_context": sql_generation_context,
                "dialect": datasource_dialect,
                "current_datasource_dialect": datasource_dialect,
                "query_constraints": getattr(dataset, "query_constraints", None) or {},
                "allowed_tables": allowed_tables,
            },
        }

    def _bind_query_executor(
        self,
        *,
        request: BILeadAgentHandoffRequest,
        dataset: SemanticDataset | None,
    ) -> None:
        toolkit = getattr(self.bridge, "toolkit", None)
        context = getattr(toolkit, "context", None)
        if self.db is None or dataset is None or context is None:
            return

        def _execute(sql: str) -> dict[str, Any]:
            # execute_compiled_query 是唯一能读取私有 SQL 的位置；native handoff 只绑定执行器，不读取 SQL。
            return preview_dataset_sql(self.db, dataset=dataset, sql=sql, question=request.confirmed_question)

        context.query_executor = _execute

    async def _run_direct_runtime_fallback(
        self,
        *,
        request: BILeadAgentHandoffRequest,
        session: Any,
    ) -> dict[str, Any] | None:
        if self.db is None:
            return None
        dataset = self.db.get(SemanticDataset, request.dataset_id)
        if dataset is None:
            return None
        route_decision = {
            "decision": "selected",
            "dataset_id": request.dataset_id,
            "dataset_name": getattr(dataset, "name", None),
            "reason": "bi_lead_agent_native_handoff",
        }
        routing = {
            "entry_intent": "metric_query",
            "entry_route": "query_graph",
            "entry_reason": "bi_lead_agent_native_handoff",
            "route_payload": {},
        }
        lead_agent_context = {
            "selected_skills": [],
            "planned_tool_calls": [],
            "executed_tool_calls": [],
            "policy_violations": [],
            "time_context": {},
            "thread_context": {},
            "route_decision": route_decision,
            "schema_status": {"status": "confirmed_by_bi_lead_agent"},
        }
        candidate_assets = recall_candidate_assets(
            self.db,
            dataset_id=request.dataset_id,
            question=request.confirmed_question,
            manifest_version=route_decision.get("manifest_version"),
            bound_schema_version=route_decision.get("bound_schema_version"),
        )
        dsl = plan_query(
            db=self.db,
            question=request.confirmed_question,
            routing=routing,
            candidate_assets=candidate_assets,
            multiturn_context=None,
            lead_agent_context=lead_agent_context,
        )
        # AgentScope 模型可能在外部工具确认后停止继续调用；这里仍由 DatasetAgent Runtime 状态机驱动原子工具收口。
        return await self.bridge.run_direct_query(session=session, dsl=dsl)

    @staticmethod
    def _collect_payload(*, events: list[Any], session: Any, child_run_id: str) -> dict[str, Any]:
        return collect_native_handoff_payload(
            AgentScopeNativeBIHandoff._wrap_native_events(events, child_run_id=child_run_id),
            fallback_artifact_ref=getattr(session, "artifact_ref", None),
            fallback_error=getattr(session, "last_error", None),
        )

    @staticmethod
    def _needs_direct_runtime_fallback(*, payload: dict[str, Any], session: Any) -> bool:
        status = str(payload.get("handoff_status") or "").strip().lower()
        if getattr(session, "artifact_ref", None) or getattr(session, "last_error", None):
            return False
        return status in {"", "accepted", "running", "waiting_child"}

    @staticmethod
    def _event_from_direct_payload(payload: dict[str, Any], *, child_run_id: str) -> dict[str, Any]:
        status = str(payload.get("status") or "").strip().lower()
        if status == "completed" and payload.get("artifact_ref"):
            return {
                "event_type": "agent.child.completed",
                "child_run_id": child_run_id,
                "artifact_ref": payload.get("artifact_ref"),
                "answer_summary": "DatasetAgent 查询完成，已生成安全结果引用。",
                "row_count": payload.get("row_count"),
                "column_count": payload.get("column_count"),
            }
        return {
            "event_type": "agent.child.blocked",
            "child_run_id": child_run_id,
            "error_code": payload.get("code") or "DATASET_RUNTIME_FALLBACK_BLOCKED",
            "error_summary": payload.get("error_summary") or "DatasetAgent Runtime 未能生成安全结果引用。",
        }

    @staticmethod
    def _wrap_native_events(events: list[Any], *, child_run_id: str) -> list[Any]:
        wrapped: list[Any] = [
            {"event_type": "agent.child.accepted", "child_run_id": child_run_id},
            {"event_type": "agent.child.running", "child_run_id": child_run_id},
        ]
        wrapped.extend(events)
        return wrapped

    @staticmethod
    def _result_from_payload(
        *,
        request: BILeadAgentHandoffRequest,
        handoff_id: str,
        child_run_id: str,
        task_id: str | None,
        payload: dict[str, Any],
    ) -> BILeadAgentHandoffResult:
        return BILeadAgentHandoffResult(
            handoff_id=handoff_id,
            child_run_id=_safe_str(payload.get("child_run_id")) or child_run_id,
            dataset_id=request.dataset_id,
            task_id=task_id,
            trace_id=request.trace_id,
            handoff_status=native_status_or_default(payload),
            answer_summary=_safe_str(payload.get("answer_summary")),
            artifact_ref=_safe_str(payload.get("artifact_ref")),
            checkpoint_ref=_safe_str(payload.get("checkpoint_ref")),
            row_count=_safe_int(payload.get("row_count")),
            column_count=_safe_int(payload.get("column_count")),
            status_reason=_safe_str(payload.get("status_reason")),
            error_code=_safe_str(payload.get("error_code")),
            error_summary=_safe_str(payload.get("error_summary")),
        )


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _native_allowed_tables_and_sql_context(dataset: SemanticDataset) -> tuple[list[str], dict[str, Any]]:
    allowed_tables: list[str] = []
    table_schemas: list[dict[str, Any]] = []
    for link in dataset.selected_tables or []:
        source_table = getattr(link, "source_table", None)
        if source_table is None:
            continue
        schema_name = str(getattr(source_table, "schema_name", "") or "").strip()
        table_name = str(getattr(source_table, "table_name", "") or "").strip()
        if not table_name:
            continue
        allowed_tables.append(table_name)
        if schema_name:
            allowed_tables.append(f"{schema_name}.{table_name}")
        fields = []
        for column in source_table.columns or []:
            column_name = str(getattr(column, "column_name", "") or "").strip()
            if not column_name:
                continue
            fields.append(
                {
                    "name": column_name,
                    "column_name": column_name,
                    "display_name": getattr(column, "effective_desc", None)
                    or getattr(column, "user_description", None)
                    or getattr(column, "ai_description", None)
                    or getattr(column, "column_comment", None)
                    or column_name,
                }
            )
        table_schemas.append({"name": table_name, "table_name": table_name, "fields": fields})
    return sorted(set(allowed_tables)), build_query_plan_compiler_context({"table_schemas": table_schemas})
