# ============================================================
# File Name   : direct_query_runner.py
# Description:
#   AgentScope 直连问数 runner。
#
# Responsibilities:
#   - 顺序驱动 AgenticLeadAgent 与 BI Agent。
#   - 直接进入 Dataset 工具链，不创建 ShellTask、会话消息或 Handoff。
#   - 只返回 artifact/checkpoint 与行列数等安全业务结果。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import json
import re
import inspect
from collections.abc import AsyncIterator, Callable
from typing import Any

from agentscope.message import UserMsg
from agentscope.state import AgentState
from sqlalchemy.orm import Session

from app.agents.agentic_lead_agent.react_factory import (
    AGENTIC_LEAD_AGENT_DIRECT_PROMPT,
    AgenticLeadAgentFactory,
)
from app.agents.bi_agent.react_factory import BI_AGENT_DIRECT_QUERY_PROMPT, BIAgentFactory
from app.agents.bi_agent.runtime_context import build_bi_runtime_context
from app.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge
from app.bi.toolkit import build_bi_atomic_toolkit
from app.middlewares.lifecycle import log_agent_io, log_lifecycle
from app.models.conversation import Conversation, ConversationState, Message
from app.schemas.agentic_direct_query import sanitize_public_summary


BridgeFactory = Callable[[Session], AgentScopeDatasetRuntimeBridge]
AgentFactory = Callable[..., Any]
AGENTSCOPE_DIRECT_CONTEXT_KEY = "agentic_direct_query"
AGENTSCOPE_DIRECT_CONTEXT_VERSION = 1
MAX_BI_AGENT_TOOL_TURNS = 8
MAX_HISTORY_MESSAGES = 6
MAX_HISTORY_TEXT_CHARS = 240
CONTROLLED_DATASET_TAIL_TOOLS = {
    "compile_dsl_to_sql",
    "execute_compiled_query",
    "create_query_artifact",
    "get_artifact_summary",
}
GENERIC_FINAL_SUMMARIES = {
    "查询已完成",
    "查询已完成。",
    "已完成查询",
    "已完成查询。",
}


def _default_bridge_factory(db: Session) -> AgentScopeDatasetRuntimeBridge:
    return AgentScopeDatasetRuntimeBridge(toolkit=build_bi_atomic_toolkit(db))


class AgenticDirectQueryRunner:
    """AgentScope 直连问数入口；绕过旧 ShellTask/Message/Handoff 持久化链路。"""

    def __init__(
        self,
        *,
        db: Session,
        lead_agent_factory: AgentFactory = AgenticLeadAgentFactory,
        bi_agent_factory: AgentFactory = BIAgentFactory,
        bridge_factory: BridgeFactory = _default_bridge_factory,
    ) -> None:
        self.db = db
        self.lead_agent_factory = lead_agent_factory
        self.bi_agent_factory = bi_agent_factory
        self.bridge_factory = bridge_factory

    async def run(
        self,
        *,
        question: str,
        dataset_id: int,
        conversation_id: int | None = None,
        trace_id: str | None = None,
        model_config_id: int | None = None,
    ) -> dict[str, Any]:
        final_result: dict[str, Any] | None = None
        async for event in self.stream(
            question=question,
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
            model_config_id=model_config_id,
        ):
            if event.get("type") == "final" and isinstance(event.get("result"), dict):
                final_result = event["result"]
        return final_result or {
            "status": "blocked",
            "selected_agent": "",
            "code": "DIRECT_QUERY_STREAM_EMPTY",
        }

    async def stream(
        self,
        *,
        question: str,
        dataset_id: int,
        conversation_id: int | None = None,
        trace_id: str | None = None,
        model_config_id: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """按 AgentScope 消息/事件粒度输出直连问数过程，供前端流式展示。"""

        log_lifecycle(
            "agentic_direct_query.started",
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
            question_length=len(question or ""),
            model_config_id=model_config_id,
        )
        lead_state = self._load_lead_agent_state(
            conversation_id=conversation_id,
            dataset_id=dataset_id,
            trace_id=trace_id,
        )
        history_summary = None if self._has_agentscope_context(lead_state) else self._conversation_history_summary(
            conversation_id=conversation_id,
            current_question=question,
        )
        if lead_state is None and history_summary:
            # 旧会话没有 AgentScope 快照时，先用安全摘要启动 SDK State；本轮结束后会升级为完整 context 快照。
            lead_state = AgentState(summary=history_summary)
        lead_agent = self._create_lead_agent(state=lead_state, model_config_id=model_config_id)
        lead_msg = self._build_lead_message(
            question=question,
            dataset_id=dataset_id,
            history_summary=history_summary,
        )
        yield self._agent_message_event(
            agent="agentic_lead_agent",
            role="user",
            phase="prompt",
            title="AgenticLeadAgent 输入",
            content=self._message_content(lead_msg),
            trace_id=trace_id,
        )
        log_agent_io(
            "agentic_lead_agent",
            "prompt",
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
            system_prompt=AGENTIC_LEAD_AGENT_DIRECT_PROMPT,
            user_prompt=self._message_content(lead_msg),
        )
        lead_reply = await lead_agent.reply(lead_msg)
        lead_decision = self._parse_lead_route(lead_reply)
        selected_agent = str(lead_decision.get("selected_agent") or "")
        task_type = lead_decision.get("task_type")
        yield self._agent_message_event(
            agent="agentic_lead_agent",
            role="assistant",
            phase="response",
            title="AgenticLeadAgent 路由结果",
            content=self._lead_decision_summary(lead_decision),
            trace_id=trace_id,
            payload={
                "selected_agent": selected_agent,
                "task_type": task_type,
                "reason": lead_decision.get("reason"),
            },
        )
        log_lifecycle(
            "agentic_direct_query.lead.completed",
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
            selected_agent=selected_agent,
            task_type=task_type,
        )
        log_agent_io(
            "agentic_lead_agent",
            "response",
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
            output=self._message_content(lead_reply),
            parsed_decision=lead_decision,
        )

        if selected_agent != "bi_agent" or task_type != "bi_query":
            # 直连 runner 当前只开放 BI Agent，其他路由结果 fail-closed，不落库、不 handoff。
            log_lifecycle(
                "agentic_direct_query.blocked",
                dataset_id=dataset_id,
                conversation_id=conversation_id,
                trace_id=trace_id,
                selected_agent=selected_agent,
                error_code="LEAD_AGENT_ROUTE_BLOCKED",
            )
            result = {
                "status": "blocked",
                "selected_agent": selected_agent,
                "code": "LEAD_AGENT_ROUTE_BLOCKED",
            }
            self._save_lead_agent_state(
                conversation_id=conversation_id,
                dataset_id=dataset_id,
                trace_id=trace_id,
                lead_agent=lead_agent,
                result_status="blocked",
            )
            yield self._final_event(result, trace_id=trace_id)
            return

        bridge = self.bridge_factory(self.db)
        runtime_context = build_bi_runtime_context(
            self.db,
            dataset_id=dataset_id,
            question=question,
            bridge=bridge,
        )
        session_kwargs = runtime_context.get("session_kwargs") or {}
        session = bridge.start_session(
            dataset_id=dataset_id,
            question=question,
            agent_name="bi_agent",
            conversation_id=self._existing_conversation_id(
                conversation_id=conversation_id,
                dataset_id=dataset_id,
                trace_id=trace_id,
            ),
            trace_id=trace_id,
            **session_kwargs,
        )
        yield self._agent_event(
            agent="bi_agent",
            phase="session_started",
            title="BI Agent 接管",
            content="AgenticLeadAgent 已选择 BI Agent，正在进入 Dataset 工具链。",
            trace_id=trace_id,
            payload={
                "dataset_id": dataset_id,
                "conversation_id": getattr(session, "conversation_id", None),
            },
        )
        bi_agent_factory = self.bi_agent_factory(db=self.db)
        bi_msg = self._build_bi_message(question=question, dataset_id=dataset_id)
        log_lifecycle(
            "agentic_direct_query.bi.started",
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
            selected_agent=selected_agent,
        )
        async for event in self._run_bi_agent_tool_loop(
            bridge=bridge,
            create_bi_agent=lambda: self._create_bi_agent(
                bi_agent_factory,
                session=session,
                model_config_id=model_config_id,
            ),
            initial_msg=bi_msg,
            session=session,
        ):
            yield event
        result = self._result_from_session(session=session, selected_agent=selected_agent)
        if result.get("status") == "completed":
            lead_final_msg = self._build_lead_final_message(
                question=question,
                dataset_id=dataset_id,
                result=result,
            )
            yield self._agent_message_event(
                agent="agentic_lead_agent",
                role="user",
                phase="final_prompt",
                title="AgenticLeadAgent 接收 BI 查询结果",
                content=self._message_content(lead_final_msg),
                trace_id=trace_id,
                payload={
                    "artifact_ref": result.get("artifact_ref"),
                    "row_count": result.get("row_count"),
                    "column_count": result.get("column_count"),
                },
            )
            log_agent_io(
                "agentic_lead_agent",
                "final_prompt",
                dataset_id=dataset_id,
                conversation_id=conversation_id,
                trace_id=trace_id,
                user_prompt=self._message_content(lead_final_msg),
            )
            lead_final_reply = await lead_agent.reply(lead_final_msg)
            lead_summary = self._parse_lead_final_summary(lead_final_reply)
            # 调试阶段模型可能仍返回“查询已完成”这类泛化话术；此时用 BI Agent 安全结果生成稳定 Markdown。
            final_summary = self._lead_markdown_summary_or_fallback(
                question=question,
                result=result,
                lead_summary=lead_summary,
            )
            if final_summary:
                result["summary"] = final_summary
            yield self._agent_message_event(
                agent="agentic_lead_agent",
                role="assistant",
                phase="final_response",
                title="AgenticLeadAgent 最终回复",
                content=final_summary or result.get("summary") or "查询已完成。",
                trace_id=trace_id,
                payload={
                    "artifact_ref": result.get("artifact_ref"),
                    "row_count": result.get("row_count"),
                    "column_count": result.get("column_count"),
                },
            )
            log_agent_io(
                "agentic_lead_agent",
                "final_response",
                dataset_id=dataset_id,
                conversation_id=conversation_id,
                trace_id=trace_id,
                output=self._message_content(lead_final_reply),
                final_summary=result.get("summary"),
            )
        log_lifecycle(
            "agentic_direct_query.completed",
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
            selected_agent=selected_agent,
            status=result["status"],
            has_artifact=bool(result.get("artifact_ref")),
            row_count=result.get("row_count"),
            column_count=result.get("column_count"),
        )
        self._save_lead_agent_state(
            conversation_id=conversation_id,
            dataset_id=dataset_id,
            trace_id=trace_id,
            lead_agent=lead_agent,
            result_status=str(result.get("status") or "completed"),
        )
        yield self._final_event(result, trace_id=trace_id, agent="agentic_lead_agent")

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _existing_conversation_id(
        self,
        *,
        conversation_id: int | None,
        dataset_id: int,
        trace_id: str | None,
    ) -> int | None:
        safe_conversation_id = self._safe_int(conversation_id)
        if safe_conversation_id is None:
            return None
        if self.db.get(Conversation, safe_conversation_id) is not None:
            return safe_conversation_id
        # 直连测试或外部调用可能传入不存在的会话；artifact 外键必须 fail-safe 置空。
        log_lifecycle(
            "agentic_direct_query.conversation_id.dropped",
            dataset_id=dataset_id,
            trace_id=trace_id,
            conversation_id=safe_conversation_id,
            reason="conversation_not_found",
        )
        return None

    def _create_lead_agent(
        self,
        *,
        state: AgentState | None,
        model_config_id: int | None = None,
    ) -> Any:
        factory = self.lead_agent_factory(db=self.db)
        create = factory.create
        params = inspect.signature(create).parameters
        kwargs: dict[str, Any] = {}
        if "state" in params:
            kwargs["state"] = state
        if "model_config_id" in params:
            # 测试替身或旧工厂未声明该参数时保持兼容；真实工厂用它覆盖本轮模型。
            kwargs["model_config_id"] = model_config_id
        return create(**kwargs)

    @staticmethod
    def _create_bi_agent(
        factory: Any,
        *,
        session: Any,
        model_config_id: int | None = None,
    ) -> Any:
        create = factory.create
        params = inspect.signature(create).parameters
        kwargs: dict[str, Any] = {"session": session}
        if "model_config_id" in params:
            kwargs["model_config_id"] = model_config_id
        return create(**kwargs)

    def _load_lead_agent_state(
        self,
        *,
        conversation_id: int | None,
        dataset_id: int,
        trace_id: str | None,
    ) -> AgentState | None:
        safe_conversation_id = self._safe_int(conversation_id)
        if safe_conversation_id is None:
            return None
        if self.db.get(Conversation, safe_conversation_id) is None:
            return None
        state_row = self.db.get(ConversationState, self._agentscope_state_session_id(safe_conversation_id))
        capsule = (getattr(state_row, "subagent_capsules", None) or {}).get(AGENTSCOPE_DIRECT_CONTEXT_KEY) if state_row else None
        state_payload = capsule.get("lead_agent_state") if isinstance(capsule, dict) else None
        if not isinstance(state_payload, dict):
            return None
        try:
            state = AgentState.model_validate(state_payload)
        except Exception as exc:
            # 历史快照格式异常时不阻断问数，降级到安全摘要；同时记录 trace 便于定位坏数据。
            log_lifecycle(
                "agentic_direct_query.agentscope_state.restore_failed",
                dataset_id=dataset_id,
                conversation_id=safe_conversation_id,
                trace_id=trace_id,
                error=str(exc),
            )
            return None
        log_lifecycle(
            "agentic_direct_query.agentscope_state.restored",
            dataset_id=dataset_id,
            conversation_id=safe_conversation_id,
            trace_id=trace_id,
            context_count=len(getattr(state, "context", []) or []),
            has_summary=bool(getattr(state, "summary", None)),
        )
        return state

    def _save_lead_agent_state(
        self,
        *,
        conversation_id: int | None,
        dataset_id: int,
        trace_id: str | None,
        lead_agent: Any,
        result_status: str,
    ) -> None:
        safe_conversation_id = self._safe_int(conversation_id)
        if safe_conversation_id is None:
            return
        if self.db.get(Conversation, safe_conversation_id) is None:
            return
        state_payload = self._serialize_agentscope_state(getattr(lead_agent, "state", None))
        if state_payload is None:
            return
        session_id = self._agentscope_state_session_id(safe_conversation_id)
        state_row = self.db.get(ConversationState, session_id)
        if state_row is None:
            state_row = ConversationState(
                session_id=session_id,
                user_id=f"conversation:{safe_conversation_id}",
                messages=[],
                facts=[],
                subagent_capsules={},
            )
            self.db.add(state_row)
        capsules = dict(state_row.subagent_capsules or {})
        capsules[AGENTSCOPE_DIRECT_CONTEXT_KEY] = {
            "version": AGENTSCOPE_DIRECT_CONTEXT_VERSION,
            "agent": "agentic_lead_agent",
            "lead_agent_state": state_payload,
            "dataset_id": dataset_id,
            "trace_id": trace_id,
            "result_status": result_status,
        }
        state_row.subagent_capsules = capsules
        state_row.active_dataset_id = str(dataset_id)
        state_row.status = "idle"
        state_row.turn_index = int(state_row.turn_index or 0) + 1
        self.db.flush()
        log_lifecycle(
            "agentic_direct_query.agentscope_state.saved",
            dataset_id=dataset_id,
            conversation_id=safe_conversation_id,
            trace_id=trace_id,
            context_count=len(state_payload.get("context") or []),
            result_status=result_status,
        )

    @staticmethod
    def _serialize_agentscope_state(state: Any) -> dict[str, Any] | None:
        if state is None or not hasattr(state, "model_dump"):
            return None
        try:
            payload = state.model_dump(mode="json")
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    @staticmethod
    def _has_agentscope_context(state: AgentState | None) -> bool:
        return bool(getattr(state, "context", None))

    @staticmethod
    def _agentscope_state_session_id(conversation_id: int) -> str:
        return f"agentic_direct_query:{conversation_id}"

    @staticmethod
    def _build_lead_message(
        *,
        question: str,
        dataset_id: int,
        history_summary: str | None = None,
    ) -> Any:
        history_block = (
            "历史对话摘要（同一 conversation 的安全业务上下文，供多轮追问使用）：\n"
            f"{history_summary}\n"
            if history_summary
            else ""
        )
        content = (
            "请为 Datalogue 直连问数链路选择业务 Agent。\n"
            f"dataset_id: {dataset_id}\n"
            f"{history_block}"
            f"question: {question}\n"
            "只能返回 JSON：selected_agent、task_type、reason。"
        )
        return UserMsg(name="user", content=content)

    def _conversation_history_summary(
        self,
        *,
        conversation_id: int | None,
        current_question: str,
    ) -> str | None:
        safe_conversation_id = self._safe_int(conversation_id)
        if safe_conversation_id is None:
            return None
        conversation = self.db.get(Conversation, safe_conversation_id)
        if conversation is None:
            return None
        messages = (
            self.db.query(Message)
            .filter(Message.conversation_id == safe_conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .all()
        )
        lines: list[str] = []
        current_question_text = str(current_question or "").strip()
        for message in messages[-MAX_HISTORY_MESSAGES:]:
            text = self._safe_history_text(getattr(message, "content", None))
            if not text:
                continue
            role = str(getattr(message, "role", "") or "").lower()
            if role == "user":
                if text == current_question_text:
                    continue  # 当前轮问题如果已由前端预写入 message 表，不能重复当作历史。
                lines.append(f"上一轮问题：{text}")
            elif role == "assistant":
                lines.append(f"上一轮结论：{text}")  # 只取用户可见摘要，不读取 response_metadata/sql_list。
        return "\n".join(lines[-MAX_HISTORY_MESSAGES:]) or None

    @staticmethod
    def _safe_history_text(value: Any) -> str | None:
        text = sanitize_public_summary(value)
        if not text:
            return None
        return text[:MAX_HISTORY_TEXT_CHARS]

    @staticmethod
    def _build_bi_message(*, question: str, dataset_id: int) -> Any:
        content = (
            "请作为 BI Agent 执行 Dataset 工具链直连查询。\n"
            f"dataset_id: {dataset_id}\n"
            f"question: {question}\n"
            "最终只返回安全业务摘要、artifact_ref、checkpoint_ref、row_count、column_count。"
        )
        return UserMsg(name="user", content=content)

    @staticmethod
    def _build_lead_final_message(
        *,
        question: str,
        dataset_id: int,
        result: dict[str, Any],
    ) -> Any:
        # 这里只把 BI Agent 的安全查询结果回交给 LeadAgent；SQL/schema/raw rows 仍留在工具层。
        content = (
            "BI Agent 已完成数据查询，请作为 AgenticLeadAgent 生成最终用户回复。\n"
            "当前没有 ReportAgent；不要转交、不要声称由 ReportAgent 生成报告，你就是最终回答生成者。\n"
            "请直接用 Markdown 展示 BI Agent 返回的安全查询结果，至少包含：查询结果、数据规模、结果入口、可继续追问。\n"
            "只能基于 BI Agent 返回的安全结果回答；不要输出 SQL、schema、raw rows、query_plan 或内部执行细节。\n"
            f"question: {question}\n"
            f"dataset_id: {dataset_id}\n"
            "query_result:\n"
            f"  status: {result.get('status')}\n"
            f"  summary: {result.get('summary') or ''}\n"
            f"  artifact_ref: {result.get('artifact_ref') or ''}\n"
            f"  checkpoint_ref: {result.get('checkpoint_ref') or ''}\n"
            f"  row_count: {result.get('row_count') if result.get('row_count') is not None else ''}\n"
            f"  column_count: {result.get('column_count') if result.get('column_count') is not None else ''}\n"
            "请返回 JSON：{\"summary\":\"Markdown 字符串\"}。"
        )
        return UserMsg(name="user", content=content)

    @staticmethod
    def _message_content(message: Any) -> Any:
        return getattr(message, "content", message)

    async def _run_bi_agent_tool_loop(
        self,
        *,
        bridge: AgentScopeDatasetRuntimeBridge,
        create_bi_agent: Callable[[], Any],
        initial_msg: Any,
        session: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        msg = initial_msg
        for turn_index in range(MAX_BI_AGENT_TOOL_TURNS):
            if self._should_complete_dataset_tail(session=session, bridge=bridge):
                yield self._agent_event(
                    agent="bi_agent",
                    phase="controlled_tail_started",
                    title="Dataset 工具链尾段",
                    content="BI Agent 已完成前置判断，正在由受控 Dataset 工具链完成编译、执行和产物生成。",
                    trace_id=getattr(session, "trace_id", None),
                    payload={
                        "turn_index": turn_index,
                        "expected_tool": getattr(session, "expected_tool_name", None),
                    },
                )
                await self._complete_dataset_tail(bridge=bridge, session=session, turn_index=turn_index)
                yield self._agent_event(
                    agent="bi_agent",
                    phase="controlled_tail_completed",
                    title="Dataset 工具链完成",
                    content=self._tool_progress_summary(session=session),
                    trace_id=getattr(session, "trace_id", None),
                    payload={
                        "turn_index": turn_index,
                        "artifact_ref": getattr(session, "artifact_ref", None),
                    },
                )
                return
            previous_tool_count = len(getattr(session, "tool_results", []) or [])
            bi_agent = create_bi_agent()
            yield self._agent_message_event(
                agent="bi_agent",
                role="user",
                phase="prompt",
                title=f"BI Agent 输入（第 {turn_index + 1} 轮）",
                content=self._message_content(msg),
                trace_id=getattr(session, "trace_id", None),
                payload={
                    "turn_index": turn_index,
                    "expected_tool": getattr(session, "expected_tool_name", None),
                },
            )
            log_agent_io(
                "bi_agent",
                "prompt",
                dataset_id=getattr(session, "dataset_id", None),
                conversation_id=getattr(session, "conversation_id", None),
                trace_id=getattr(session, "trace_id", None),
                turn_index=turn_index,
                expected_tool=getattr(session, "expected_tool_name", None),
                system_prompt=BI_AGENT_DIRECT_QUERY_PROMPT,
                user_prompt=self._message_content(msg),
            )
            reply_stream_result = await bridge.run_reply_stream(bi_agent, msg=msg, session=session)
            yield self._agent_message_event(
                agent="bi_agent",
                role="assistant",
                phase="response",
                title=f"BI Agent 返回（第 {turn_index + 1} 轮）",
                content=self._tool_progress_summary(session=session),
                trace_id=getattr(session, "trace_id", None),
                payload={
                    "turn_index": turn_index,
                    "expected_tool": getattr(session, "expected_tool_name", None),
                    "tool_count": len(getattr(session, "tool_results", []) or []),
                    "artifact_ref": getattr(session, "artifact_ref", None),
                },
            )
            log_agent_io(
                "bi_agent",
                "response",
                dataset_id=getattr(session, "dataset_id", None),
                conversation_id=getattr(session, "conversation_id", None),
                trace_id=getattr(session, "trace_id", None),
                turn_index=turn_index,
                output=reply_stream_result,
                expected_tool=getattr(session, "expected_tool_name", None),
                tool_count=len(getattr(session, "tool_results", []) or []),
                artifact_ref=getattr(session, "artifact_ref", None),
                checkpoint_ref=getattr(session, "checkpoint_ref", None),
                last_error=getattr(session, "last_error", None),
            )
            yield self._agent_event(
                agent="bi_agent",
                phase="tool_progress",
                title="Dataset 工具调用进度",
                content=self._tool_progress_summary(session=session),
                trace_id=getattr(session, "trace_id", None),
                payload={
                    "turn_index": turn_index,
                    "tool_count": len(getattr(session, "tool_results", []) or []),
                    "expected_tool": getattr(session, "expected_tool_name", None),
                    "artifact_ref": getattr(session, "artifact_ref", None),
                },
            )
            if self._bi_tool_loop_completed(session=session):
                return
            current_expected_tool = getattr(session, "expected_tool_name", None)
            current_tool_count = len(getattr(session, "tool_results", []) or [])
            if current_tool_count <= previous_tool_count:
                log_lifecycle(
                    "agentic_direct_query.bi.stalled",
                    dataset_id=getattr(session, "dataset_id", None),
                    trace_id=getattr(session, "trace_id", None),
                    expected_tool=current_expected_tool,
                    tool_count=current_tool_count,
                    turn_index=turn_index,
                )
                return
            # 真实模型可能在收到工具结果后停止输出；这里用受控追问驱动它继续调用当前期望工具。
            msg = self._build_bi_continue_message(
                question=getattr(session, "question", ""),
                dataset_id=getattr(session, "dataset_id", None),
                expected_tool=current_expected_tool,
            )
        log_lifecycle(
            "agentic_direct_query.bi.max_turns_reached",
            dataset_id=getattr(session, "dataset_id", None),
            trace_id=getattr(session, "trace_id", None),
            expected_tool=getattr(session, "expected_tool_name", None),
            tool_count=len(getattr(session, "tool_results", []) or []),
            max_turns=MAX_BI_AGENT_TOOL_TURNS,
        )

    @staticmethod
    def _agent_message_event(
        *,
        agent: str,
        role: str,
        phase: str,
        title: str,
        content: Any,
        trace_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # 前端流只展示业务可理解的 AgentScope 消息视图；SQL/schema/raw rows 不在这里生成。
        return {
            "type": "agent_message",
            "event_type": "agent.message",
            "agent": agent,
            "role": role,
            "phase": phase,
            "title": title,
            "content": str(content or ""),
            "trace_id": trace_id,
            "payload": payload or {},
        }

    @staticmethod
    def _agent_event(
        *,
        agent: str,
        phase: str,
        title: str,
        content: str,
        trace_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # 事件 payload 仅放状态、引用和计数，避免把执行态数据塞进用户可见流。
        return {
            "type": "agent_event",
            "event_type": "agent.event",
            "agent": agent,
            "phase": phase,
            "title": title,
            "content": content,
            "trace_id": trace_id,
            "payload": payload or {},
        }

    @staticmethod
    def _final_event(result: dict[str, Any], *, trace_id: str | None, agent: str = "bi_agent") -> dict[str, Any]:
        return {
            "type": "final",
            "event_type": "message.completed",
            "agent": agent,
            "trace_id": trace_id,
            "result": result,
        }

    @staticmethod
    def _lead_decision_summary(lead_decision: dict[str, Any]) -> str:
        selected_agent = lead_decision.get("selected_agent") or "未选择"
        task_type = lead_decision.get("task_type") or "未知任务"
        reason = lead_decision.get("reason")
        suffix = f"；原因：{reason}" if reason else ""
        return f"已识别为 {task_type}，选择 {selected_agent}{suffix}。"

    @staticmethod
    def _tool_progress_summary(*, session: Any) -> str:
        tool_results = getattr(session, "tool_results", []) or []
        tool_names = [str(item.get("name")) for item in tool_results if isinstance(item, dict) and item.get("name")]
        expected_tool = getattr(session, "expected_tool_name", None)
        artifact_ref = getattr(session, "artifact_ref", None)
        last_error = getattr(session, "last_error", None)
        parts = []
        if tool_names:
            parts.append(f"已完成工具：{' / '.join(tool_names[-4:])}")
        else:
            parts.append("正在等待 Dataset 工具返回")
        if expected_tool:
            parts.append(f"下一步：{expected_tool}")
        if artifact_ref:
            parts.append("查询产物已生成")
        if last_error:
            parts.append("查询被安全拦截或执行失败")
        return "；".join(parts) + "。"

    @staticmethod
    def _should_complete_dataset_tail(
        *,
        session: Any,
        bridge: AgentScopeDatasetRuntimeBridge,
    ) -> bool:
        expected_tool = getattr(session, "expected_tool_name", None)
        tool_count = len(getattr(session, "tool_results", []) or [])
        return bool(
            expected_tool in CONTROLLED_DATASET_TAIL_TOOLS
            and tool_count >= 2
            and hasattr(bridge, "run_direct_query")
        )

    @staticmethod
    async def _complete_dataset_tail(
        *,
        bridge: AgentScopeDatasetRuntimeBridge,
        session: Any,
        turn_index: int,
    ) -> None:
        # 进入 compile 之后的尾段只依赖受控 Dataset 工具状态机；继续等待模型发同样工具会放大超时风险。
        log_lifecycle(
            "agentic_direct_query.bi.controlled_tail.started",
            dataset_id=getattr(session, "dataset_id", None),
            trace_id=getattr(session, "trace_id", None),
            expected_tool=getattr(session, "expected_tool_name", None),
            tool_count=len(getattr(session, "tool_results", []) or []),
            turn_index=turn_index,
        )
        await bridge.run_direct_query(session=session, dsl={})
        log_lifecycle(
            "agentic_direct_query.bi.controlled_tail.completed",
            dataset_id=getattr(session, "dataset_id", None),
            trace_id=getattr(session, "trace_id", None),
            expected_tool=getattr(session, "expected_tool_name", None),
            has_artifact=bool(getattr(session, "artifact_ref", None)),
            has_error=bool(getattr(session, "last_error", None)),
        )

    @staticmethod
    def _bi_tool_loop_completed(*, session: Any) -> bool:
        return bool(
            getattr(session, "artifact_ref", None)
            or getattr(session, "last_error", None)
            or not getattr(session, "expected_tool_name", None)
        )

    @staticmethod
    def _build_bi_continue_message(
        *,
        question: str,
        dataset_id: Any,
        expected_tool: Any,
    ) -> Any:
        content = (
            "继续执行 Dataset 工具链，不要给最终回答。请根据上一轮工具结果继续调用下一个工具。\\n"
            f"dataset_id: {dataset_id}\\n"
            f"question: {question}\\n"
            f"当前必须调用的下一个工具: {expected_tool}\\n"
            "只能调用这个工具；不要输出 SQL、schema、raw rows 或 compiled_query_ref。"
        )
        return UserMsg(name="user", content=content)

    @classmethod
    def _parse_lead_route(cls, reply: Any) -> dict[str, Any]:
        if isinstance(reply, dict):
            return reply
        content = getattr(reply, "content", reply)
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            for item in content:
                item_text = getattr(item, "text", None)
                if item_text:
                    return cls._json_payload_from_text(item_text)
        return cls._json_payload_from_text(str(content or ""))

    @classmethod
    def _json_payload_from_text(cls, text: str) -> dict[str, Any]:
        json_text = cls._extract_json_object(text)
        if not json_text:
            return {}
        try:
            payload = json.loads(json_text)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _extract_json_object(text: str) -> str | None:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            return fenced.group(1)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return text[start : end + 1]

    @classmethod
    def _parse_lead_final_summary(cls, reply: Any) -> str | None:
        if isinstance(reply, dict):
            return sanitize_public_summary(
                reply.get("summary") or reply.get("answer") or reply.get("final_answer")
            )
        content = getattr(reply, "content", reply)
        if isinstance(content, dict):
            return sanitize_public_summary(
                content.get("summary") or content.get("answer") or content.get("final_answer")
            )
        if isinstance(content, list):
            text_parts = [
                str(getattr(item, "text"))
                for item in content
                if getattr(item, "text", None)
            ]
            if text_parts:
                text = "\n".join(text_parts)
                parsed = cls._json_payload_from_text(text)
                return sanitize_public_summary(
                    parsed.get("summary") or parsed.get("answer") or parsed.get("final_answer") or text
                )
        text = str(content or "").strip()
        if not text:
            return None
        parsed = cls._json_payload_from_text(text)
        return sanitize_public_summary(
            parsed.get("summary") or parsed.get("answer") or parsed.get("final_answer") or text
        )

    @classmethod
    def _lead_markdown_summary_or_fallback(
        cls,
        *,
        question: str,
        result: dict[str, Any],
        lead_summary: str | None,
    ) -> str | None:
        if lead_summary and lead_summary.strip() not in GENERIC_FINAL_SUMMARIES:
            return lead_summary
        return cls._build_markdown_final_summary(question=question, result=result)

    @staticmethod
    def _build_markdown_final_summary(*, question: str, result: dict[str, Any]) -> str | None:
        summary = sanitize_public_summary(result.get("summary")) or "查询已完成，结果已生成。"
        row_count = result.get("row_count")
        column_count = result.get("column_count")
        artifact_ref = result.get("artifact_ref")
        lines = [
            "## 查询结果",
            "",
            f"- **问题**：{question}",
            f"- **结论**：{summary}",
        ]
        if row_count is not None or column_count is not None:
            row_text = f"{row_count} 行" if row_count is not None else "行数未返回"
            column_text = f"{column_count} 列" if column_count is not None else "列数未返回"
            lines.append(f"- **数据规模**：返回 {row_text}，{column_text}")  # 只展示数量，不展示 raw rows。
        if artifact_ref:
            lines.append(f"- **结果入口**：`{artifact_ref}`")
        lines.extend(
            [
                "",
                "## 可继续追问",
                "",
                "- 可以继续追问明细、筛选条件、分组对比或导出结果。",
            ]
        )
        return "\n".join(lines)

    @classmethod
    def _result_from_session(cls, *, session: Any, selected_agent: str) -> dict[str, Any]:
        tool_summary = cls._tool_result_summary(getattr(session, "tool_results", []))
        artifact_ref = getattr(session, "artifact_ref", None)
        checkpoint_ref = getattr(session, "checkpoint_ref", None)
        last_error = getattr(session, "last_error", None)
        expected_tool = getattr(session, "expected_tool_name", None)
        result: dict[str, Any] = {
            "status": "completed" if artifact_ref and not last_error and not expected_tool else "blocked",
            "selected_agent": selected_agent,
            "artifact_ref": artifact_ref,
            "checkpoint_ref": checkpoint_ref,
            "row_count": tool_summary.get("row_count"),
            "column_count": tool_summary.get("column_count"),
        }
        if last_error:
            result["code"] = cls._last_error_code(last_error)
        elif expected_tool:
            result["code"] = "DATASET_TOOLCHAIN_INCOMPLETE"
            result["expected_tool"] = expected_tool
        elif not artifact_ref:
            result["code"] = "DATASET_QUERY_BLOCKED"
        safe_summary = sanitize_public_summary(tool_summary.get("summary"))
        if safe_summary:
            result["summary"] = safe_summary
        return result

    @staticmethod
    def _last_error_code(last_error: Any) -> str:
        if isinstance(last_error, dict) and last_error.get("code"):
            return str(last_error["code"])
        return "DATASET_QUERY_BLOCKED"

    @staticmethod
    def _tool_result_summary(tool_results: Any) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        if not isinstance(tool_results, list):
            return summary
        for tool_result in tool_results:
            if not isinstance(tool_result, dict):
                continue
            # execute 结果是行列数的唯一可信来源；artifact summary 只作为安全业务摘要回传。
            if tool_result.get("name") == "execute_compiled_query":
                summary["row_count"] = tool_result.get("row_count")
                summary["column_count"] = tool_result.get("column_count")
            if tool_result.get("name") == "get_artifact_summary" and tool_result.get("summary"):
                summary["summary"] = tool_result.get("summary")
        return summary
