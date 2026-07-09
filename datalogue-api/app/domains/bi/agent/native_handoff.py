# ============================================================
# File Name   : native_handoff.py
# Description:
#   BI Agent AgentScope native handoff 实现。
#
# Responsibilities:
#   - 以 AgentScope 2.0 DatasetAgent 子运行为内部 handoff 实现。
#   - 将 native child-run 事件投影成 Datalogue BIAgentHandoffResult 安全契约。
#   - 保持 Datalogue DB 为 run/confirmation/handoff 的业务状态真相源。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from agentscope.message import UserMsg
from sqlalchemy.orm import Session

from app.core.models.dataset import AnalysisBlueprint, SemanticDataset
from app.core.schemas.bi_agent import BIAgentHandoffRequest, BIAgentHandoffResult
from app.domains.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge
from app.core.middlewares.lifecycle import log_lifecycle
from app.prompts import NATIVE_HANDOFF_CHILD_MESSAGE_TEMPLATE
from app.services.analysis_blueprint import execute_analysis_blueprint
from app.domains.query_execution.artifact_store import ArtifactStore
from app.domains.bi.agent.dataset_agent_factory import AgentScopeDatasetAgentFactory
from app.domains.bi.agent.handoff_events import (
    collect_native_handoff_payload,
    native_status_or_default,
    safe_native_failure_result_payload,
)
from app.domains.bi.skill import DatasetQuerySkill
from app.domains.bi.agent.runtime_context import (
    allowed_tables_and_sql_context,
    build_bi_runtime_context,
)


logger = logging.getLogger(__name__)


def _debug_native_handoff(stage: str, **fields: Any) -> None:
    payload = {"stage": stage, **fields}
    logger.debug(
        "[native_handoff.debug] %s",
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
    )


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
        dataset_query_skill = DatasetQuerySkill(db=db)
        return cls(
            bridge=dataset_query_skill.build_runtime_bridge(),
            dataset_agent_factory=AgentScopeDatasetAgentFactory(db),
            db=db,
        )

    async def query_dataset(
        self,
        request: BIAgentHandoffRequest,
        *,
        task_id: str | None,
    ) -> BIAgentHandoffResult:
        handoff_id = _new_prefixed_id("native-handoff")
        child_run_id = _new_prefixed_id("dataset-native-run")
        log_lifecycle(
            "bi_agent.native_handoff.started",
            handoff_id=handoff_id,
            child_run_id=child_run_id,
            task_id=task_id,
            trace_id=request.trace_id,
            dataset_id=request.dataset_id,
            parent_run_id=request.parent_run_id,
        )
        failure_stage = "initializing"
        try:
            failure_stage = "build_runtime_context"
            log_lifecycle(
                "bi_agent.native_handoff.init_stage.started",
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                trace_id=request.trace_id,
                dataset_id=request.dataset_id,
                init_stage=failure_stage,
            )
            runtime_context = self._build_runtime_context(request)
            session_kwargs = runtime_context.get("session_kwargs", {})
            log_lifecycle(
                "bi_agent.native_handoff.init_stage.completed",
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                trace_id=request.trace_id,
                dataset_id=request.dataset_id,
                init_stage=failure_stage,
                has_dataset=bool(runtime_context.get("dataset")),
                allowed_table_count=len(session_kwargs.get("allowed_tables") or []),
                has_compiler_context=bool(session_kwargs.get("sql_generation_context")),
                compiler_table_schema_count=len(
                    (session_kwargs.get("sql_generation_context") or {}).get("table_schemas") or []
                ),
            )

            failure_stage = "bind_query_executor"
            log_lifecycle(
                "bi_agent.native_handoff.init_stage.started",
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                trace_id=request.trace_id,
                dataset_id=request.dataset_id,
                init_stage=failure_stage,
            )
            self._bind_query_executor(request=request, dataset=runtime_context.get("dataset"))
            log_lifecycle(
                "bi_agent.native_handoff.init_stage.completed",
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                trace_id=request.trace_id,
                dataset_id=request.dataset_id,
                init_stage=failure_stage,
                has_dataset=bool(runtime_context.get("dataset")),
            )

            failure_stage = "start_session"
            log_lifecycle(
                "bi_agent.native_handoff.init_stage.started",
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                trace_id=request.trace_id,
                dataset_id=request.dataset_id,
                init_stage=failure_stage,
                allowed_table_count=len(session_kwargs.get("allowed_tables") or []),
            )
            session = self.bridge.start_session(
                dataset_id=request.dataset_id,
                question=request.confirmed_question,
                agent_name="bi_worker",
                trace_id=request.trace_id,
                **session_kwargs,
            )  # AgentScope session 是执行态；Datalogue handoff 表仍是业务审计真相源。
            log_lifecycle(
                "bi_agent.native_handoff.init_stage.completed",
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                trace_id=request.trace_id,
                dataset_id=request.dataset_id,
                init_stage=failure_stage,
                has_session=True,
                has_session_artifact=bool(getattr(session, "artifact_ref", None)),
            )

            failure_stage = "create_dataset_agent"
            log_lifecycle(
                "bi_agent.native_handoff.init_stage.started",
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                trace_id=request.trace_id,
                dataset_id=request.dataset_id,
                init_stage=failure_stage,
            )
            agent = self.dataset_agent_factory.create(session)
            log_lifecycle(
                "bi_agent.native_handoff.init_stage.completed",
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                trace_id=request.trace_id,
                dataset_id=request.dataset_id,
                init_stage=failure_stage,
                has_agent=True,
            )

            failure_stage = "reply_stream"
            events = await self.bridge.run_reply_stream(
                agent,
                msg=self._build_native_child_message(
                    request=request,
                    handoff_id=handoff_id,
                    child_run_id=child_run_id,
                ),
                session=session,
            )
            log_lifecycle(
                "bi_agent.native_handoff.agent_stream.completed",
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                trace_id=request.trace_id,
                dataset_id=request.dataset_id,
                event_count=len(events),
                has_session_artifact=bool(getattr(session, "artifact_ref", None)),
                has_session_error=bool(getattr(session, "last_error", None)),
            )
            payload = self._collect_payload(
                events=events, session=session, child_run_id=child_run_id
            )
            if self._missing_terminal_evidence(payload):
                self._log_missing_terminal_evidence_debug(
                    request=request,
                    session=session,
                    payload=payload,
                    handoff_id=handoff_id,
                    child_run_id=child_run_id,
                    task_id=task_id,
                    event_count=len(events),
                )
                log_lifecycle(
                    "bi_agent.native_handoff.terminal_evidence.missing",
                    handoff_id=handoff_id,
                    child_run_id=child_run_id,
                    task_id=task_id,
                    trace_id=request.trace_id,
                    dataset_id=request.dataset_id,
                    event_count=len(events),
                    expected_tool_at_stop=getattr(session, "expected_tool_name", None),
                    expected_tool_index=getattr(session, "expected_tool_index", None),
                    executed_tool_count=len(getattr(session, "tool_results", None) or []),
                    last_tool_name=self._last_tool_name(session),
                    terminal_diagnosis=self._terminal_diagnosis(session),
                )
                controlled_payload = self._try_controlled_blueprint_completion(
                    request=request,
                    session=session,
                    handoff_id=handoff_id,
                    child_run_id=child_run_id,
                    task_id=task_id,
                    event_count=len(events),
                )
                if controlled_payload is not None:
                    payload = controlled_payload
            payload = self._fail_closed_without_terminal_evidence(payload)
            result = self._result_from_payload(
                request=request,
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                payload=payload,
            )
            log_lifecycle(
                "bi_agent.native_handoff.completed",
                handoff_id=result.handoff_id,
                child_run_id=result.child_run_id,
                task_id=task_id,
                trace_id=result.trace_id,
                dataset_id=result.dataset_id,
                handoff_status=result.handoff_status,
                error_code=result.error_code,
                has_artifact=bool(result.artifact_ref),
                row_count=result.row_count,
                column_count=result.column_count,
            )
            return result
        except Exception:
            logger.error(
                "BI Agent native handoff failed at %s; internal details are hidden.", failure_stage
            )
            result = self._result_from_payload(
                request=request,
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                payload=safe_native_failure_result_payload(),
            )
            log_lifecycle(
                "bi_agent.native_handoff.failed",
                handoff_id=result.handoff_id,
                child_run_id=result.child_run_id,
                task_id=task_id,
                trace_id=result.trace_id,
                dataset_id=result.dataset_id,
                handoff_status=result.handoff_status,
                error_code=result.error_code,
                failure_stage=failure_stage,
            )
            return result

    @staticmethod
    def _build_native_child_message(
        *,
        request: BIAgentHandoffRequest,
        handoff_id: str,
        child_run_id: str,
    ) -> Any:
        content = NATIVE_HANDOFF_CHILD_MESSAGE_TEMPLATE.format(
            handoff_id=handoff_id,
            child_run_id=child_run_id,
            dataset_id=request.dataset_id,
            task_goal=request.task_goal,
            confirmed_question=request.confirmed_question,
            routing_rationale=request.routing_rationale,
        )
        return UserMsg(name="user", content=content)

    def _build_runtime_context(self, request: BIAgentHandoffRequest) -> dict[str, Any]:
        if self.db is None:
            return {}
        return build_bi_runtime_context(
            self.db,
            dataset_id=request.dataset_id,
            question=request.confirmed_question,
            bridge=self.bridge,
        )

    def _bind_query_executor(
        self,
        *,
        request: BIAgentHandoffRequest,
        dataset: SemanticDataset | None,
    ) -> None:
        # 兼容旧调用点：执行器已由 _build_runtime_context 统一绑定。
        del request, dataset
        return

    @staticmethod
    def _collect_payload(*, events: list[Any], session: Any, child_run_id: str) -> dict[str, Any]:
        return collect_native_handoff_payload(
            AgentScopeNativeBIHandoff._wrap_native_events(events, child_run_id=child_run_id),
            fallback_artifact_ref=getattr(session, "artifact_ref", None),
            fallback_error=getattr(session, "last_error", None),
        )

    @staticmethod
    def _fail_closed_without_terminal_evidence(payload: dict[str, Any]) -> dict[str, Any]:
        if not AgentScopeNativeBIHandoff._missing_terminal_evidence(payload):
            return payload
        blocked = dict(payload)
        blocked["handoff_status"] = "blocked"
        blocked["status_reason"] = "native_handoff_missing_terminal_event"
        blocked["error_code"] = "NATIVE_HANDOFF_MISSING_ARTIFACT"
        blocked["error_summary"] = "DatasetAgent native handoff 未生成安全结果引用，已停止补执行。"
        return blocked

    def _try_controlled_blueprint_completion(
        self,
        *,
        request: BIAgentHandoffRequest,
        session: Any,
        handoff_id: str,
        child_run_id: str,
        task_id: str | None,
        event_count: int,
    ) -> dict[str, Any] | None:
        """在 native agent 停在工具链中途时，只允许命中的受控分析蓝图生成终态 artifact。"""
        if self.db is None:
            self._log_controlled_blueprint_skipped(
                request=request,
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                event_count=event_count,
                reason="db_missing",
            )
            return None

        blueprint = self._select_controlled_blueprint(request)
        if blueprint is None:
            self._log_controlled_blueprint_skipped(
                request=request,
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                event_count=event_count,
                reason="blueprint_not_matched",
            )
            return None

        log_lifecycle(
            "bi_agent.native_handoff.controlled_blueprint.started",
            handoff_id=handoff_id,
            child_run_id=child_run_id,
            task_id=task_id,
            trace_id=request.trace_id,
            dataset_id=request.dataset_id,
            blueprint_id=blueprint.id,
            blueprint_name=blueprint.name,
        )
        result = execute_analysis_blueprint(
            self.db,
            blueprint,
            question=request.confirmed_question,
            require_active=True,
            count_usage=True,
        )
        if not result.get("ok") or not result.get("sql_result"):
            self._log_controlled_blueprint_skipped(
                request=request,
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                event_count=event_count,
                reason="blueprint_execution_not_ok",
                blueprint=blueprint,
                missing_param_count=len(result.get("missing") or []),
                diagnosis_code=(result.get("diagnosis") or {}).get("code"),
            )
            return None

        artifact_payload = self._safe_blueprint_artifact_payload(result)
        artifact_ref = ArtifactStore(self.db).put_json(
            kind="sql_result",
            payload=artifact_payload,
            dataset_id=request.dataset_id,
            trace_id=request.trace_id,
        )
        # session.artifact_ref 是 Dataset Query Skill 的终态证据，补齐后让后续日志和结果口径一致。
        try:
            session.artifact_ref = artifact_ref
        except Exception:
            logger.debug("native handoff session artifact_ref is not writable", exc_info=True)

        column_count = len(artifact_payload.get("columns") or [])
        row_count = _safe_int(artifact_payload.get("row_count"))
        log_lifecycle(
            "bi_agent.native_handoff.controlled_blueprint.completed",
            handoff_id=handoff_id,
            child_run_id=child_run_id,
            task_id=task_id,
            trace_id=request.trace_id,
            dataset_id=request.dataset_id,
            blueprint_id=blueprint.id,
            blueprint_name=blueprint.name,
            has_artifact=True,
            row_count=row_count,
            column_count=column_count,
        )
        return {
            "event_type": "agent.child.completed",
            "handoff_status": "completed",
            "child_run_id": child_run_id,
            "artifact_ref": artifact_ref,
            "answer_summary": "DatasetAgent 已通过受控分析蓝图完成查询，生成安全结果引用。",
            "row_count": row_count,
            "column_count": column_count,
            "status_reason": "controlled_blueprint_completion",
        }

    def _select_controlled_blueprint(
        self, request: BIAgentHandoffRequest
    ) -> AnalysisBlueprint | None:
        if self.db is None:
            return None
        blueprints = (
            self.db.query(AnalysisBlueprint)
            .filter(
                AnalysisBlueprint.dataset_id == request.dataset_id,
                AnalysisBlueprint.status == "active",
                AnalysisBlueprint.implementation_type == "sql_template",
            )
            .all()
        )
        scored: list[tuple[int, AnalysisBlueprint]] = []
        for blueprint in blueprints:
            if not ((blueprint.call_template or "").strip() or (blueprint.raw_sql or "").strip()):
                continue
            score = self._controlled_blueprint_match_score(blueprint, request.confirmed_question)
            if score > 0:
                scored.append((score, blueprint))
        if not scored:
            return None
        scored.sort(key=lambda item: (-item[0], item[1].id or 0))
        return scored[0][1]

    @staticmethod
    def _controlled_blueprint_match_score(blueprint: AnalysisBlueprint, question: str) -> int:
        question_text = str(question or "").strip()
        if not question_text:
            return 0

        score = 0
        for keyword in blueprint.trigger_keywords or []:
            keyword_text = str(keyword or "").strip()
            if keyword_text and keyword_text in question_text:
                score += 10

        blueprint_text = " ".join(AgentScopeNativeBIHandoff._blueprint_text_parts(blueprint))
        for token in ("工作日志", "日志", "日报", "计划任务", "任务记录", "明细"):
            if token in question_text and token in blueprint_text:
                score += 3
        return score

    @staticmethod
    def _blueprint_text_parts(blueprint: AnalysisBlueprint) -> list[str]:
        parts = [
            blueprint.name,
            blueprint.description,
            blueprint.when_to_use,
            blueprint.attribution_hints,
        ]
        parts.extend(blueprint.trigger_keywords or [])
        parts.extend(blueprint.trigger_examples or [])
        return [str(part) for part in parts if part]

    @staticmethod
    def _safe_blueprint_artifact_payload(result: dict[str, Any]) -> dict[str, Any]:
        sql_result = result.get("sql_result") or {}
        allowed_keys = {
            "columns",
            "rows",
            "row_count",
            "column_labels",
            "blueprint_id",
            "blueprint_name",
            "execution_time_ms",
            "params",
            "masking_summary",
        }
        # SQL 模板和预览只留在蓝图服务内部，handoff artifact 只暴露可展示的安全结果。
        payload = {key: value for key, value in sql_result.items() if key in allowed_keys}
        payload.setdefault("row_count", result.get("row_count"))
        payload.setdefault("execution_time_ms", result.get("execution_time_ms"))
        payload.setdefault("params", result.get("params") or {})
        payload.setdefault("masking_summary", result.get("masking_summary") or {})
        payload["source"] = "controlled_analysis_blueprint"
        return payload

    @staticmethod
    def _log_controlled_blueprint_skipped(
        *,
        request: BIAgentHandoffRequest,
        handoff_id: str,
        child_run_id: str,
        task_id: str | None,
        event_count: int,
        reason: str,
        blueprint: AnalysisBlueprint | None = None,
        missing_param_count: int | None = None,
        diagnosis_code: str | None = None,
    ) -> None:
        log_lifecycle(
            "bi_agent.native_handoff.controlled_blueprint.skipped",
            handoff_id=handoff_id,
            child_run_id=child_run_id,
            task_id=task_id,
            trace_id=request.trace_id,
            dataset_id=request.dataset_id,
            event_count=event_count,
            skip_reason=reason,
            blueprint_id=getattr(blueprint, "id", None),
            blueprint_name=getattr(blueprint, "name", None),
            missing_param_count=missing_param_count,
            diagnosis_code=diagnosis_code,
        )
        _debug_native_handoff(
            "bi_agent.native_handoff.controlled_blueprint.skipped",
            handoff_id=handoff_id,
            child_run_id=child_run_id,
            task_id=task_id,
            trace_id=request.trace_id,
            dataset_id=request.dataset_id,
            event_count=event_count,
            skip_reason=reason,
            blueprint_id=getattr(blueprint, "id", None),
            blueprint_name=getattr(blueprint, "name", None),
            missing_param_count=missing_param_count,
            diagnosis_code=diagnosis_code,
        )

    @staticmethod
    def _missing_terminal_evidence(payload: dict[str, Any]) -> bool:
        status = str(payload.get("handoff_status") or "").strip().lower()
        if status in {"completed", "blocked", "failed", "cancelled"}:
            return False
        return not (
            payload.get("artifact_ref") or payload.get("error_code") or payload.get("error_summary")
        )

    @staticmethod
    def _last_tool_name(session: Any) -> str | None:
        tool_results = getattr(session, "tool_results", None) or []
        if not tool_results:
            return None
        last = tool_results[-1]
        if not isinstance(last, dict):
            return None
        return str(last.get("name") or "") or None

    @staticmethod
    def _safe_tool_result_digest(session: Any) -> list[dict[str, Any]]:
        digest: list[dict[str, Any]] = []
        for item in (getattr(session, "tool_results", None) or [])[-5:]:
            if not isinstance(item, dict):
                continue
            # DEBUG 日志只说明工具链停在哪一步；SQL、schema、raw rows 等执行态不进入日志。
            digest.append(
                {
                    "name": item.get("name"),
                    "status": item.get("status"),
                    "error_code": item.get("error_code"),
                    "row_count": _safe_int(item.get("row_count")),
                    "column_count": _safe_int(item.get("column_count")),
                    "has_artifact_ref": bool(item.get("artifact_ref")),
                }
            )
        return digest

    def _log_missing_terminal_evidence_debug(
        self,
        *,
        request: BIAgentHandoffRequest,
        session: Any,
        payload: dict[str, Any],
        handoff_id: str,
        child_run_id: str,
        task_id: str | None,
        event_count: int,
    ) -> None:
        _debug_native_handoff(
            "bi_agent.native_handoff.terminal_evidence.missing",
            handoff_id=handoff_id,
            child_run_id=child_run_id,
            task_id=task_id,
            trace_id=request.trace_id,
            dataset_id=request.dataset_id,
            event_count=event_count,
            payload_status=payload.get("handoff_status"),
            payload_has_artifact=bool(payload.get("artifact_ref")),
            payload_error_code=payload.get("error_code"),
            payload_error_summary=payload.get("error_summary"),
            session_has_artifact=bool(getattr(session, "artifact_ref", None)),
            session_has_error=bool(getattr(session, "last_error", None)),
            expected_tool_at_stop=getattr(session, "expected_tool_name", None),
            expected_tool_index=getattr(session, "expected_tool_index", None),
            executed_tool_count=len(getattr(session, "tool_results", None) or []),
            last_tool_name=self._last_tool_name(session),
            terminal_diagnosis=self._terminal_diagnosis(session),
            tool_results_digest=self._safe_tool_result_digest(session),
        )

    @staticmethod
    def _terminal_diagnosis(session: Any) -> str:
        if getattr(session, "artifact_ref", None) or getattr(session, "last_error", None):
            return "terminal_evidence_present"
        if getattr(session, "expected_tool_name", None):
            return "agent_stopped_before_expected_tool"
        if getattr(session, "tool_results", None):
            return "tool_sequence_completed_without_artifact"
        return "agent_stopped_without_tool_call"

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
        request: BIAgentHandoffRequest,
        handoff_id: str,
        child_run_id: str,
        task_id: str | None,
        payload: dict[str, Any],
    ) -> BIAgentHandoffResult:
        return BIAgentHandoffResult(
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


def _native_allowed_tables_and_sql_context(
    dataset: SemanticDataset,
) -> tuple[list[str], dict[str, Any]]:
    return allowed_tables_and_sql_context(dataset)
