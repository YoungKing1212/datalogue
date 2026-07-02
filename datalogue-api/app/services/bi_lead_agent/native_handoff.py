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
            payload = self._fail_closed_without_terminal_evidence(payload)
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

    @staticmethod
    def _collect_payload(*, events: list[Any], session: Any, child_run_id: str) -> dict[str, Any]:
        return collect_native_handoff_payload(
            AgentScopeNativeBIHandoff._wrap_native_events(events, child_run_id=child_run_id),
            fallback_artifact_ref=getattr(session, "artifact_ref", None),
            fallback_error=getattr(session, "last_error", None),
        )

    @staticmethod
    def _fail_closed_without_terminal_evidence(payload: dict[str, Any]) -> dict[str, Any]:
        status = str(payload.get("handoff_status") or "").strip().lower()
        if status in {"completed", "blocked", "failed", "cancelled"}:
            return payload
        if payload.get("artifact_ref") or payload.get("error_code") or payload.get("error_summary"):
            return payload
        blocked = dict(payload)
        blocked["handoff_status"] = "blocked"
        blocked["status_reason"] = "native_handoff_missing_terminal_event"
        blocked["error_code"] = "NATIVE_HANDOFF_MISSING_ARTIFACT"
        blocked["error_summary"] = "DatasetAgent native handoff 未生成安全结果引用，已停止补执行。"
        return blocked

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
