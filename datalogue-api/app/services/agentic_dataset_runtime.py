# ============================================================
# File Name   : agentic_dataset_runtime.py
# Description:
#   AS-R0 DatasetAgent tool-call runtime 最小编排层。
#
# Responsibilities:
#   - 串联 BI atomic tools 完成 DatasetAgent 查询链路。
#   - 保证 DSL、SQL、schema、raw rows 只在受控工具和 artifact 内部流转。
#   - 为后续 AgentScope runner 接入提供可测试的 runtime contract。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.agentic_bi_tools import BIAtomicToolProvider
from app.services.agentic_shell import DatalogueAgenticShell
from app.services.subagent_planning.contracts import QueryPlan


DatasetDslGenerator = Callable[..., QueryPlan | dict[str, Any]]


class DatasetAgentToolCallRuntime:
    """DatasetAgent 的受控 tool-call 编排；不提供大而全 plan_bi_query 黑盒。"""

    def __init__(
        self,
        *,
        provider: BIAtomicToolProvider,
        dsl_generator: DatasetDslGenerator,
    ) -> None:
        self.provider = provider
        self.dsl_generator = dsl_generator
        self._sanitizer = DatalogueAgenticShell()

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
        """按 PR1.3 固定顺序串联 atomic tools，返回 Agent 可见的安全摘要。"""

        tool_calls: list[dict[str, Any]] = []

        dataset_status = self.provider.get_dataset_status(dataset_id)
        self._append_tool_call(tool_calls, "get_dataset_status", dataset_status.get("status") or "ready")
        if dataset_status.get("status") in {"not_found", "disabled", "inactive"}:
            return self._final_result(
                status="blocked",
                tool_calls=tool_calls,
                code="DATASET_NOT_AVAILABLE",
            )

        candidate_assets = self.provider.list_candidate_assets(dataset_id, question=question)
        self._append_tool_call(tool_calls, "list_candidate_assets", candidate_assets.get("status") or "ready")

        try:
            dsl = self.dsl_generator(
                question=question,
                dataset_status=dataset_status,
                candidate_assets=candidate_assets,
            )
        except Exception as exc:  # pragma: no cover - 具体异常类型由后续 DSL generator 决定。
            self._append_tool_call(tool_calls, "generate_dsl", "blocked", {"code": "DSL_GENERATION_FAILED"})
            return self._final_result(
                status="blocked",
                tool_calls=tool_calls,
                code="DSL_GENERATION_FAILED",
                error_summary=str(exc),
            )

        self._append_tool_call(tool_calls, "generate_dsl", "generated", self._safe_dsl_summary(dsl))

        compiled = self.provider.compile_dsl_to_sql(
            dataset_id=dataset_id,
            dsl=dsl,
            sql_generation_context=sql_generation_context,
            dialect=dialect,
            current_datasource_dialect=current_datasource_dialect,
            query_constraints=query_constraints,
            allowed_tables=allowed_tables,
        )
        self._append_tool_call(tool_calls, "compile_dsl_to_sql", compiled.get("status") or "blocked", compiled)
        if compiled.get("status") != "compiled":
            return self._final_result(
                status="blocked",
                tool_calls=tool_calls,
                code=str(compiled.get("code") or "COMPILE_BLOCKED"),
                error_summary=compiled.get("error_summary"),
            )

        executed = self.provider.execute_compiled_query(
            compiled_query_ref=str(compiled["compiled_query_ref"]),
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )
        self._append_tool_call(tool_calls, "execute_compiled_query", executed.get("status") or "blocked", executed)
        if executed.get("status") != "completed":
            return self._final_result(
                status="blocked",
                tool_calls=tool_calls,
                code=str(executed.get("code") or executed.get("status") or "EXECUTE_BLOCKED"),
            )

        artifact_ref = str(executed["artifact_ref"])
        artifact_summary = self.provider.get_artifact_summary(artifact_ref)
        self._append_tool_call(tool_calls, "get_artifact_summary", artifact_summary.get("status") or "ready")

        return self._final_result(
            status="completed",
            tool_calls=tool_calls,
            artifact_ref=artifact_ref,
            artifact_summary=artifact_summary,
            row_count=executed.get("row_count"),
            column_count=executed.get("column_count"),
        )

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

    def _final_result(self, **payload: Any) -> dict[str, Any]:
        safe_payload = self._sanitizer.sanitize_output(payload)
        return safe_payload if isinstance(safe_payload, dict) else {"status": "blocked"}
