# ============================================================
# File Name   : dataset_runtime.py
# Description:
#   BI Dataset 查询确定性工具链。
#
# Responsibilities:
#   - 串联 BI atomic tools 完成 DatasetAgent 查询链路。
#   - 保证 DSL、SQL、schema、raw rows 只在受控工具和 artifact 内部流转。
#   - 为 BI Agent Skill / AgentScope runner 接入提供可测试的 toolchain contract。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents.agentic_lead_agent import AgenticLeadAgent
from app.bi.toolkit import DatalogueBIAtomicToolkit
from app.services.subagent_planning.contracts import QueryPlan


DatasetDslGenerator = Callable[..., QueryPlan | dict[str, Any]]

@dataclass(frozen=True)
class DatasetAgentNextToolCall:
    """AgentScope external tool event 投影；Agent 只能提出下一步工具名和受限参数。"""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class DatasetAgentToolCallSession:
    """DatasetAgent 单次查询的受控状态机上下文；内部状态不直接暴露给 Agent。"""

    dataset_id: int
    question: str
    sql_generation_context: dict[str, Any] | None = None
    dialect: str | None = "sqlite"
    current_datasource_dialect: str | None = None
    query_constraints: dict[str, Any] | None = None
    allowed_tables: list[str] | None = None
    conversation_id: int | None = None
    trace_id: str | None = None
    expected_tool_index: int = 0
    status: str = "running"
    dataset_status: dict[str, Any] | None = None
    candidate_assets: dict[str, Any] | None = None
    dsl: QueryPlan | dict[str, Any] | None = None
    compiled_query_ref: str | None = None
    artifact_ref: str | None = None
    last_error: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class DatasetAgentToolCallRuntime:
    """DatasetAgent 的受控 tool-call 编排；不提供大而全 plan_bi_query 黑盒。"""

    TOOL_SEQUENCE = (
        "get_dataset_status",
        "list_candidate_assets",
        "generate_dsl",
        "compile_dsl_to_sql",
        "execute_compiled_query",
        "get_artifact_summary",
    )
    ALLOWED_TOOLS = set(TOOL_SEQUENCE)
    FORBIDDEN_AGENT_ARGUMENT_KEYS = {
        "sql",
        "raw_sql",
        "llm_sql",
        "direct_sql",
        "schema",
        "schema_context",
        "raw_rows",
        "query_plan",
        "repair_patch",
        "blueprint_body",
    }

    def __init__(
        self,
        *,
        dsl_generator: DatasetDslGenerator,
        toolkit: DatalogueBIAtomicToolkit,
    ) -> None:
        if toolkit is None:
            raise ValueError("DatasetAgentToolCallRuntime requires a DatalogueBIAtomicToolkit")
        self.toolkit = toolkit
        self.dsl_generator = dsl_generator
        self._sanitizer = AgenticLeadAgent()

    def run_query(
        self,
        *,
        dataset_id: int,
        question: str,
        sql_generation_context: dict[str, Any] | None = None,
        dialect: str | None = "sqlite",
        current_datasource_dialect: str | None = None,
        query_constraints: dict[str, Any] | None = None,
        allowed_tables: list[str] | None = None,
        conversation_id: int | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """兼容入口：按 Runtime 状态机自动提交下一步 tool call。"""

        session = self.start_tool_call_session(
            dataset_id=dataset_id,
            question=question,
            sql_generation_context=sql_generation_context,
            dialect=dialect,
            current_datasource_dialect=current_datasource_dialect,
            query_constraints=query_constraints,
            allowed_tables=allowed_tables,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )
        executed: dict[str, Any] | None = None
        artifact_summary: dict[str, Any] | None = None
        for tool_name in self.TOOL_SEQUENCE:
            arguments: dict[str, Any] = {}
            if tool_name == "execute_compiled_query":
                arguments["compiled_query_ref"] = str(session.compiled_query_ref or "")
            output = self.handle_agent_tool_call(
                session,
                DatasetAgentNextToolCall(name=tool_name, arguments=arguments),
            )
            if output.get("status") == "blocked":
                return self._final_result(
                    status="blocked",
                    tool_calls=session.tool_calls,
                    code=str(output.get("code") or "RUNTIME_BLOCKED"),
                    error_summary=output.get("error_summary"),
                )
            if tool_name == "execute_compiled_query":
                executed = output
            elif tool_name == "get_artifact_summary":
                artifact_summary = output

        executed = executed or {}
        artifact_summary = artifact_summary or {}
        return self._final_result(
            status="completed",
            tool_calls=session.tool_calls,
            artifact_ref=session.artifact_ref,
            artifact_summary=artifact_summary,
            row_count=executed.get("row_count"),
            column_count=executed.get("column_count"),
        )

    def start_tool_call_session(
        self,
        *,
        dataset_id: int,
        question: str,
        sql_generation_context: dict[str, Any] | None = None,
        dialect: str | None = "sqlite",
        current_datasource_dialect: str | None = None,
        query_constraints: dict[str, Any] | None = None,
        allowed_tables: list[str] | None = None,
        conversation_id: int | None = None,
        trace_id: str | None = None,
    ) -> DatasetAgentToolCallSession:
        """创建单次 Runtime 会话；后续每一步由 Agent 提议、Runtime 校验并执行。"""

        return DatasetAgentToolCallSession(
            dataset_id=dataset_id,
            question=question,
            sql_generation_context=sql_generation_context,
            dialect=dialect,
            current_datasource_dialect=current_datasource_dialect,
            query_constraints=query_constraints,
            allowed_tables=allowed_tables,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )

    def handle_agent_tool_call(
        self,
        session: DatasetAgentToolCallSession,
        tool_call: DatasetAgentNextToolCall,
    ) -> dict[str, Any]:
        """执行 Agent 提议的下一步工具调用；安全顺序和敏感入参由 Runtime 强制校验。"""

        if tool_call.name not in self.ALLOWED_TOOLS:
            output = self._blocked_tool_call(session, tool_call.name, "TOOL_NOT_WHITELISTED")
            return output
        if self._contains_forbidden_agent_argument(tool_call.arguments):
            output = self._blocked_tool_call(session, tool_call.name, "SENSITIVE_TOOL_ARGUMENT")
            return output
        expected = self.TOOL_SEQUENCE[session.expected_tool_index] if session.expected_tool_index < len(self.TOOL_SEQUENCE) else None
        if tool_call.name != expected:
            output = self._blocked_tool_call(session, tool_call.name, "TOOL_ORDER_VIOLATION")
            return output

        handler = {
            "get_dataset_status": self._run_get_dataset_status,
            "list_candidate_assets": self._run_list_candidate_assets,
            "generate_dsl": self._run_generate_dsl,
            "compile_dsl_to_sql": self._run_compile_dsl_to_sql,
            "execute_compiled_query": self._run_execute_compiled_query,
            "get_artifact_summary": self._run_get_artifact_summary,
        }[tool_call.name]
        output = handler(session, tool_call.arguments)
        if output.get("status") == "blocked":
            session.status = "blocked"
            session.last_error = output
            return output
        session.expected_tool_index += 1
        if session.expected_tool_index >= len(self.TOOL_SEQUENCE):
            session.status = "completed"
        return output

    def _run_get_dataset_status(
        self,
        session: DatasetAgentToolCallSession,
        _arguments: dict[str, Any],
    ) -> dict[str, Any]:
        dataset_status = self.toolkit.execute_tool("get_dataset_status", dataset_id=session.dataset_id)
        session.dataset_status = dataset_status
        self._append_tool_call(
            session.tool_calls,
            "get_dataset_status",
            dataset_status.get("status") or "ready",
        )
        if dataset_status.get("status") in {"not_found", "disabled", "inactive"}:
            return self._blocked_tool_call(session, "get_dataset_status", "DATASET_NOT_AVAILABLE")
        return self._safe_agent_tool_output(
            {
                "status": dataset_status.get("status") or "ready",
                "dataset_id": session.dataset_id,
            }
        )

    def _run_list_candidate_assets(
        self,
        session: DatasetAgentToolCallSession,
        _arguments: dict[str, Any],
    ) -> dict[str, Any]:
        candidate_assets = self.toolkit.execute_tool(
            "list_candidate_assets",
            dataset_id=session.dataset_id,
            question=session.question,
        )
        session.candidate_assets = candidate_assets
        self._append_tool_call(
            session.tool_calls,
            "list_candidate_assets",
            candidate_assets.get("status") or "ready",
        )
        return self._safe_agent_tool_output(
            {
                "status": candidate_assets.get("status") or "ready",
                "question_used": candidate_assets.get("question_used") is True,
                "asset_group_count": len(
                    [
                        key
                        for key in ("blueprint", "metric", "dimension")
                        if candidate_assets.get(key)
                    ]
                ),
            }
        )

    def _run_generate_dsl(
        self,
        session: DatasetAgentToolCallSession,
        _arguments: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            dsl = self.dsl_generator(
                question=session.question,
                dataset_status=session.dataset_status or {},
                candidate_assets=session.candidate_assets or {},
            )
        except Exception as exc:  # pragma: no cover - 具体异常类型由后续 DSL generator 决定。
            return self._blocked_tool_call(
                session,
                "generate_dsl",
                "DSL_GENERATION_FAILED",
                error_summary=str(exc),
            )
        session.dsl = dsl
        safe_summary = self._safe_dsl_summary(dsl)
        self._append_tool_call(session.tool_calls, "generate_dsl", "generated", safe_summary)
        return self._safe_agent_tool_output({"status": "generated", **safe_summary})

    def _run_compile_dsl_to_sql(
        self,
        session: DatasetAgentToolCallSession,
        _arguments: dict[str, Any],
    ) -> dict[str, Any]:
        compiled = self.toolkit.execute_tool(
            "compile_dsl_to_sql",
            dataset_id=session.dataset_id,
            dsl=session.dsl or {},
            sql_generation_context=session.sql_generation_context,
            dialect=session.dialect,
            current_datasource_dialect=session.current_datasource_dialect,
            query_constraints=session.query_constraints,
            allowed_tables=session.allowed_tables,
        )
        self._append_tool_call(
            session.tool_calls,
            "compile_dsl_to_sql",
            compiled.get("status") or "blocked",
            compiled,
        )
        if compiled.get("status") != "compiled":
            return self._blocked_tool_call(
                session,
                "compile_dsl_to_sql",
                str(compiled.get("code") or "COMPILE_BLOCKED"),
                error_summary=compiled.get("error_summary"),
                append=False,
            )
        session.compiled_query_ref = str(compiled["compiled_query_ref"])
        return self._safe_agent_tool_output(
            {
                "status": "compiled",
                "compiled_query_ref": session.compiled_query_ref,
                "agent_context": {"compiled_query_ref": session.compiled_query_ref},
            }
        )

    def _run_execute_compiled_query(
        self,
        session: DatasetAgentToolCallSession,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        compiled_query_ref = str(arguments.get("compiled_query_ref") or "")
        if not session.compiled_query_ref or compiled_query_ref != session.compiled_query_ref:
            return self._blocked_tool_call(
                session,
                "execute_compiled_query",
                "COMPILED_QUERY_REF_MISMATCH",
            )
        executed = self.toolkit.execute_tool(
            "execute_compiled_query",
            compiled_query_ref=session.compiled_query_ref,
            dataset_id=session.dataset_id,
            conversation_id=session.conversation_id,
            trace_id=session.trace_id,
        )
        self._append_tool_call(
            session.tool_calls,
            "execute_compiled_query",
            executed.get("status") or "blocked",
            executed,
        )
        if executed.get("status") != "completed":
            return self._blocked_tool_call(
                session,
                "execute_compiled_query",
                str(executed.get("code") or executed.get("status") or "EXECUTE_BLOCKED"),
                append=False,
            )
        session.artifact_ref = str(executed["artifact_ref"])
        return self._safe_agent_tool_output(
            {
                "status": "completed",
                "artifact_ref": session.artifact_ref,
                "row_count": executed.get("row_count"),
                "column_count": executed.get("column_count"),
            }
        )

    def _run_get_artifact_summary(
        self,
        session: DatasetAgentToolCallSession,
        _arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if not session.artifact_ref:
            return self._blocked_tool_call(
                session,
                "get_artifact_summary",
                "ARTIFACT_REF_MISSING",
            )
        artifact_summary = self.toolkit.execute_tool("get_artifact_summary", artifact_ref=session.artifact_ref)
        self._append_tool_call(
            session.tool_calls,
            "get_artifact_summary",
            artifact_summary.get("status") or "ready",
        )
        return self._safe_agent_tool_output({"status": artifact_summary.get("status") or "ready", **artifact_summary})

    def _append_tool_call(
        self,
        tool_calls: list[dict[str, Any]],
        name: str,
        status: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        record: dict[str, Any] = {"name": name, "status": status}
        if payload:
            # Agent 可见 tool call 只保留清洗后的状态摘要；不返回 schema、SQL、字段明细或 raw rows。
            safe_payload = self._sanitizer.sanitize_output(payload)
            if isinstance(safe_payload, dict):
                record["payload"] = safe_payload
        tool_calls.append(record)

    def _blocked_tool_call(
        self,
        session: DatasetAgentToolCallSession,
        name: str,
        code: str,
        *,
        error_summary: str | None = None,
        append: bool = True,
    ) -> dict[str, Any]:
        session.status = "blocked"
        payload = {"status": "blocked", "code": code}
        if error_summary:
            payload["error_summary"] = error_summary
        if append:
            self._append_tool_call(session.tool_calls, name, "blocked", payload)
        safe_payload = self._safe_agent_tool_output(payload)
        session.last_error = safe_payload
        return safe_payload

    @staticmethod
    def _safe_dsl_summary(dsl: QueryPlan | dict[str, Any]) -> dict[str, Any]:
        if isinstance(dsl, QueryPlan):
            return {
                "query_type": dsl.query_type,
                "execution_strategy": dsl.execution_strategy,
                "confidence": round(float(dsl.confidence), 4),
            }
        if isinstance(dsl, dict):
            return {
                key: dsl.get(key)
                for key in ("query_type", "execution_strategy", "confidence")
                if key in dsl
            }
        return {}

    def _safe_agent_tool_output(self, payload: dict[str, Any]) -> dict[str, Any]:
        safe_payload = self._sanitizer.sanitize_output(payload)
        return safe_payload if isinstance(safe_payload, dict) else {"status": "blocked"}

    @classmethod
    def _contains_forbidden_agent_argument(cls, value: Any) -> bool:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_text = str(key).lower()
                if key_text in cls.FORBIDDEN_AGENT_ARGUMENT_KEYS or "sql" in key_text:
                    return True
                if cls._contains_forbidden_agent_argument(nested):
                    return True
        elif isinstance(value, list):
            return any(cls._contains_forbidden_agent_argument(item) for item in value)
        elif isinstance(value, str):
            lowered = value.lower()
            return "select " in lowered or " from " in lowered or "drop table" in lowered
        return False

    def _final_result(self, **payload: Any) -> dict[str, Any]:
        safe_payload = self._sanitizer.sanitize_output(payload)
        return safe_payload if isinstance(safe_payload, dict) else {"status": "blocked"}
