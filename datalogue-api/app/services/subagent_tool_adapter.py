# ============================================================
# File Name   : subagent_tool_adapter.py
# Description:
#   SubAgent 结果双层出参适配器。
#
# Responsibilities:
#   - 将 SubAgent final_state 拆分为 LLM 可见摘要和 LeadAgent 控制面状态。
#   - 约束进入 LLM / 前端可见面的字段白名单，避免 capsule、SQL 结果和异常泄漏。
#   - 为多轮状态持久化提供只在后端内存流转的 control plane payload。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field

from app.services.task_capsule import build_success_task_state, has_query_target
from app.utils.token import estimate_text_tokens


class LLMVisibleBudgetExceededError(ValueError):
    """LLM 可见摘要超过 adapter 预算，属于内部装配错误。"""

    def __init__(self, estimated_tokens: int, max_tokens: int) -> None:
        super().__init__(
            f"subagent llm visible token budget exceeded: {estimated_tokens}>{max_tokens}"
        )
        self.estimated_tokens = estimated_tokens
        self.max_tokens = max_tokens


class LLMVisibleStatus(str, Enum):
    OK = "ok"
    CLARIFICATION_NEEDED = "clarification_needed"
    ERROR = "error"
    EMPTY = "empty"
    TIMEOUT = "timeout"


class LLMVisiblePart(BaseModel):
    """允许进入 LLM / 前端可见 metadata 的 SubAgent 结果摘要。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: LLMVisibleStatus
    dataset_id: int
    display_summary: str = ""
    clarification_question: str | None = None
    error_summary: str | None = None
    report_ref: str | None = None


class ControlPlanePart(BaseModel):
    """只在后端代码层流转的控制面结果，禁止进入 SSE final 或 LLM context。"""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    capsule: dict[str, Any] | None = None
    last_success_task: dict[str, Any] | None = None
    result_ref: str | None = None
    report_ref: str | None = None
    prior_capsule_status: dict[str, Any] = Field(default_factory=dict)
    raw_error: Any | None = None


class SubAgentToolResult(BaseModel):
    """SubAgent 工具调用结果，强制拆分可见面和控制面。"""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    llm_visible: LLMVisiblePart
    control_plane: ControlPlanePart
    trace_metadata: dict[str, Any] = Field(default_factory=dict)


class SubAgentInvocation(BaseModel):
    """SubAgent 单次调用的 adapter 装配上下文。"""

    model_config = ConfigDict(extra="forbid")

    dataset_id: int
    question: str
    resolved_question: str | None = None
    turn_index: int | None = None
    prior_capsule_status: dict[str, Any] = Field(default_factory=dict)


class SubAgentToolAdapter:
    """把现有流式 SubAgent 完成态拆成 LLM 可见层和控制面层。"""

    LLM_VISIBLE_TOKEN_BUDGET = 200

    def __init__(self, artifact_store: Any | None = None) -> None:
        self.artifact_store = artifact_store

    def assemble_from_final_state(
        self,
        invocation: SubAgentInvocation,
        final_state: dict[str, Any],
        *,
        conversation_id: int | None = None,
        trace_id: str | None = None,
    ) -> SubAgentToolResult:
        """从现有 final_state 组装双层结果，不改变 SubAgent 流式执行模型。"""

        state = final_state if isinstance(final_state, dict) else {}
        state = self._with_artifact_refs(
            invocation,
            state,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )
        llm_visible = self._build_llm_visible(invocation, state)
        self._enforce_llm_visible_budget(llm_visible)
        control_plane = self._build_control_plane(invocation, state)
        return SubAgentToolResult(
            llm_visible=llm_visible,
            control_plane=control_plane,
            trace_metadata={
                "status": llm_visible.status.value,
                "dataset_id": invocation.dataset_id,
                "prior_capsule_status": invocation.prior_capsule_status,
            },
        )

    def render_for_llm(self, result: SubAgentToolResult) -> str:
        """渲染 tool_result 文本；只能读取 llm_visible 字段。"""

        part = result.llm_visible
        if part.status == LLMVisibleStatus.OK:
            tail = f" [report:{part.report_ref}]" if part.report_ref else ""
            return f"[dataset={part.dataset_id} ok] {part.display_summary}{tail}"
        if part.status == LLMVisibleStatus.EMPTY:
            return f"[dataset={part.dataset_id} empty] {part.display_summary}"
        if part.status == LLMVisibleStatus.CLARIFICATION_NEEDED:
            return f"[dataset={part.dataset_id} clarification] {part.clarification_question or ''}"
        return f"[dataset={part.dataset_id} {part.status.value}] {part.error_summary or ''}"

    def _build_llm_visible(
        self,
        invocation: SubAgentInvocation,
        final_state: dict[str, Any],
    ) -> LLMVisiblePart:
        error = final_state.get("error")
        if error:
            return LLMVisiblePart(
                status=LLMVisibleStatus.ERROR,
                dataset_id=invocation.dataset_id,
                error_summary=self._sanitize_error(error),
            )

        query_plan = final_state.get("query_plan") if isinstance(final_state.get("query_plan"), dict) else {}
        route_payload = (
            final_state.get("route_payload")
            if isinstance(final_state.get("route_payload"), dict)
            else {}
        )
        if query_plan.get("execution_strategy") == "clarify" or route_payload.get("kind") == "query_plan_clarification":
            question = (
                route_payload.get("message")
                or final_state.get("answer")
                or "请补充必要信息后再继续查询。"
            )
            return LLMVisiblePart(
                status=LLMVisibleStatus.CLARIFICATION_NEEDED,
                dataset_id=invocation.dataset_id,
                clarification_question=str(question),
            )

        sql_result = final_state.get("sql_result") if isinstance(final_state.get("sql_result"), dict) else None
        if sql_result is not None and int(sql_result.get("row_count") or 0) == 0:
            return LLMVisiblePart(
                status=LLMVisibleStatus.EMPTY,
                dataset_id=invocation.dataset_id,
                display_summary=self._display_summary(final_state, default="查询无匹配结果"),
            )

        return LLMVisiblePart(
            status=LLMVisibleStatus.OK,
            dataset_id=invocation.dataset_id,
            display_summary=self._display_summary(final_state, default="查询完成"),
            report_ref=self._optional_str(final_state.get("report_ref")),
        )

    def _build_control_plane(
        self,
        invocation: SubAgentInvocation,
        final_state: dict[str, Any],
    ) -> ControlPlanePart:
        error = final_state.get("error")
        capsule = final_state.get("out_capsule") if isinstance(final_state.get("out_capsule"), dict) else None
        last_success_task = None
        if not error:
            try:
                candidate_task = build_success_task_state(
                    question=final_state.get("original_question")
                    or invocation.resolved_question
                    or invocation.question,
                    dataset_id=invocation.dataset_id,
                    query_plan=final_state.get("query_plan"),
                    dsl=final_state.get("dsl"),
                    sql=final_state.get("sql"),
                    sql_result=final_state.get("sql_result"),
                    schema_version=final_state.get("bound_schema_version")
                    or final_state.get("schema_version"),
                    manifest_version=final_state.get("manifest_version"),
                    turn_index=invocation.turn_index,
                    result_ref=self._optional_str(final_state.get("result_ref")),
                )
                if has_query_target(candidate_task):
                    last_success_task = candidate_task
            except Exception:
                last_success_task = None

        return ControlPlanePart(
            capsule=jsonable_encoder(capsule) if capsule else None,
            last_success_task=jsonable_encoder(last_success_task) if last_success_task else None,
            result_ref=self._optional_str(final_state.get("result_ref")),
            report_ref=self._optional_str(final_state.get("report_ref")),
            prior_capsule_status=dict(invocation.prior_capsule_status or {}),
            raw_error=error,
        )

    def _with_artifact_refs(
        self,
        invocation: SubAgentInvocation,
        final_state: dict[str, Any],
        *,
        conversation_id: int | None,
        trace_id: str | None,
    ) -> dict[str, Any]:
        if self.artifact_store is None:
            return final_state
        state = dict(final_state)
        dataset_id = invocation.dataset_id
        if not state.get("result_ref") and isinstance(state.get("sql_result"), dict):
            try:
                state["result_ref"] = self.artifact_store.put_json(
                    kind="sql_result",
                    payload=state["sql_result"],
                    dataset_id=dataset_id,
                    conversation_id=conversation_id,
                    trace_id=trace_id,
                )
            except Exception:
                state.pop("result_ref", None)
        if not state.get("report_ref") and state.get("answer"):
            try:
                state["report_ref"] = self.artifact_store.put_text(
                    kind="report",
                    text=str(state["answer"]),
                    dataset_id=dataset_id,
                    conversation_id=conversation_id,
                    trace_id=trace_id,
                )
            except Exception:
                state.pop("report_ref", None)
        return state

    def _display_summary(self, final_state: dict[str, Any], *, default: str) -> str:
        explicit_summary = final_state.get("display_summary")
        if explicit_summary:
            return str(explicit_summary)
        value = final_state.get("answer_preview") or final_state.get("answer") or default
        text = str(value)
        return text if len(text) <= 240 else f"{text[:240]}..."

    def _sanitize_error(self, error: Any) -> str:
        text = str(error or "")
        lowered = text.lower()
        if "timeout" in lowered or "timed out" in lowered:
            return "查询超时，可以尝试缩小时间范围或筛选条件。"
        if "sql" in lowered:
            return "数据查询执行失败，已记录，可以稍后重试。"
        return "查询过程出错，已记录。"

    def _enforce_llm_visible_budget(self, part: LLMVisiblePart) -> None:
        estimated = estimate_text_tokens(
            " ".join(
                item
                for item in (
                    part.display_summary,
                    part.clarification_question or "",
                    part.error_summary or "",
                )
                if item
            )
        )
        if estimated > self.LLM_VISIBLE_TOKEN_BUDGET:
            raise LLMVisibleBudgetExceededError(
                estimated,
                self.LLM_VISIBLE_TOKEN_BUDGET,
            )

    def _optional_str(self, value: Any) -> str | None:
        if value is None or value == "":
            return None
        return str(value)
