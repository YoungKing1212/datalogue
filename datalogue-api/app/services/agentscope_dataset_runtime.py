# ============================================================
# File Name   : agentscope_dataset_runtime.py
# Description:
#   DatasetAgent Runtime 的 AgentScope 2.0 SDK 适配层。
#
# Responsibilities:
#   - 将 BI 原子工具注册为 AgentScope ToolBase external tool。
#   - 用 PermissionDecision 在 AgentScope 工具调用前执行 Datalogue 安全门禁。
#   - 监听 RequireExternalExecutionEvent，并用 ToolResultBlock 回填安全结果。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from agentscope.event import ExternalExecutionResultEvent, RequireExternalExecutionEvent
from agentscope.message import TextBlock, ToolCallBlock, ToolResultBlock, ToolResultState
from agentscope.permission import PermissionBehavior, PermissionContext, PermissionDecision
from agentscope.tool import ToolBase

from app.services.agentic_dataset_runtime import DatasetAgentToolCallRuntime
from app.services.agentic_shell import DatalogueAgenticShell
from app.services.agentscope_middlewares import DatasetRuntimeToolLoggingMiddleware
from app.services.bi_tools import DatalogueBIAtomicToolkit


logger = logging.getLogger(__name__)

AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE = (
    "get_dataset_status",
    "list_candidate_assets",
    "compile_dsl_to_sql",
    "execute_compiled_query",
    "repair_dsl",
    "create_query_artifact",
    "get_artifact_summary",
)
_REPAIR_TOOL_INDEX = AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE.index("repair_dsl")
_EXECUTE_TOOL_INDEX = AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE.index("execute_compiled_query")
_CREATE_ARTIFACT_TOOL_INDEX = AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE.index("create_query_artifact")

_READ_ONLY_TOOLS = {
    "get_dataset_status",
    "list_candidate_assets",
    "get_artifact_summary",
}


@dataclass
class AgentScopeDatasetRuntimeSession:
    """AgentScope DatasetAgent 单轮外部工具执行会话；敏感状态只保存在 Datalogue 侧。"""

    dataset_id: int
    question: str
    agent_name: str = "bi_lead_agent"
    sql_generation_context: dict[str, Any] | None = None
    dialect: str | None = "sqlite"
    current_datasource_dialect: str | None = None
    query_constraints: dict[str, Any] | None = None
    allowed_tables: list[str] | None = None
    conversation_id: int | None = None
    trace_id: str | None = None
    expected_tool_index: int = 0
    compiled_query_ref: str | None = None
    artifact_ref: str | None = None
    last_error: dict[str, Any] | None = None
    repair_pending: bool = False
    repair_attempted: bool = False
    tool_results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def expected_tool_name(self) -> str | None:
        if self.expected_tool_index >= len(AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE):
            return None
        return AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE[self.expected_tool_index]


class DatasetAgentScopeExternalTool(ToolBase):
    """AgentScope external tool 声明；真实执行由 Datalogue bridge 接管。"""

    is_external_tool = True
    is_concurrency_safe = False
    is_mcp = False

    def __init__(
        self,
        *,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        session: AgentScopeDatasetRuntimeSession,
        agent_name: str,
    ) -> None:
        super().__init__(
            middlewares=[
                DatasetRuntimeToolLoggingMiddleware(
                    dataset_id=session.dataset_id,
                    conversation_id=session.conversation_id,
                    trace_id=session.trace_id,
                )
            ]
        )
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.session = session
        self.agent_name = agent_name
        self.is_read_only = name in _READ_ONLY_TOOLS

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        """把 AgentScope permission hook 映射到 Datalogue fail-closed 策略。"""

        del context  # 当前门禁由 Datalogue 会话状态决定，不信任 Agent 可写上下文。
        if self.agent_name != "bi_lead_agent" or self.session.agent_name != "bi_lead_agent":
            return self._deny("AGENT_NOT_ALLOWED", "只有 BI LeadAgent 可以调用 BI 原子工具。")
        if self.name not in AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE:
            return self._deny("TOOL_NOT_WHITELISTED", "工具不在 DatasetAgent 白名单中。")
        if self._contains_forbidden_tool_input(tool_input):
            return self._deny("SENSITIVE_TOOL_ARGUMENT", "工具入参包含 SQL/schema/raw rows 等禁区内容。")
        if self.name == "compile_dsl_to_sql" and not isinstance(tool_input.get("dsl"), dict):
            return self._deny("DSL_REQUIRED", "compile_dsl_to_sql 必须接收结构化 DSL。")
        if self.name == "execute_compiled_query":
            compiled_query_ref = str(tool_input.get("compiled_query_ref") or "")
            if not self.session.compiled_query_ref:
                return self._deny("COMPILE_REQUIRED", "execute 必须在 compile 成功后调用。")
            if compiled_query_ref != self.session.compiled_query_ref:
                return self._deny("COMPILED_QUERY_REF_MISMATCH", "execute 只能使用当前会话 compile 产生的句柄。")
        if self.name == "repair_dsl":
            compiled_query_ref = str(tool_input.get("compiled_query_ref") or "")
            if not self.session.compiled_query_ref:
                return self._deny("COMPILE_REQUIRED", "repair 必须在 compile 成功后调用。")
            if compiled_query_ref != self.session.compiled_query_ref:
                return self._deny("COMPILED_QUERY_REF_MISMATCH", "repair 只能使用当前会话 compile 产生的句柄。")
            if not self.session.repair_pending or self.session.repair_attempted:
                return self._deny("REPAIR_NOT_ALLOWED", "repair_dsl 只允许在字段缺失失败后调用一次。")
        if self.session.expected_tool_name != self.name:
            return self._deny("TOOL_ORDER_VIOLATION", "工具调用顺序不符合 DatasetAgent Runtime 状态机。")
        if self.name in {"create_query_artifact", "get_artifact_summary"} and not self.session.artifact_ref:
            return self._deny("ARTIFACT_REF_MISSING", "artifact 工具必须在 execute 成功后调用。")
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="DatasetAgent tool call allowed.",
            decision_reason="ALLOWED",
        )

    @staticmethod
    def _deny(code: str, message: str) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.DENY,
            message=message,
            decision_reason=code,
        )

    @classmethod
    def _contains_forbidden_tool_input(cls, value: Any) -> bool:
        """检查 Agent 工具入参；允许 DSL 中空的 sql_template 占位，但禁止真实 SQL 内容。"""

        if isinstance(value, dict):
            for key, nested in value.items():
                key_text = str(key).lower()
                if key_text in {"schema", "schema_context", "raw_rows", "query_plan", "repair_patch", "blueprint_body"}:
                    return True
                if "sql" in key_text and nested not in (None, "", [], {}):
                    return True
                if cls._contains_forbidden_tool_input(nested):
                    return True
        elif isinstance(value, list):
            return any(cls._contains_forbidden_tool_input(item) for item in value)
        elif isinstance(value, str):
            return DatasetAgentToolCallRuntime._contains_forbidden_agent_argument(value)
        return False


class AgentScopeDatasetRuntimeBridge:
    """AgentScope 2.0 external tool event 与 Datalogue BI 原子工具之间的桥接器。"""

    def __init__(self, *, toolkit: DatalogueBIAtomicToolkit) -> None:
        self.toolkit = toolkit
        self._sanitizer = DatalogueAgenticShell()

    def start_session(
        self,
        *,
        dataset_id: int,
        question: str,
        agent_name: str = "bi_lead_agent",
        sql_generation_context: dict[str, Any] | None = None,
        dialect: str | None = "sqlite",
        current_datasource_dialect: str | None = None,
        query_constraints: dict[str, Any] | None = None,
        allowed_tables: list[str] | None = None,
        conversation_id: int | None = None,
        trace_id: str | None = None,
    ) -> AgentScopeDatasetRuntimeSession:
        return AgentScopeDatasetRuntimeSession(
            dataset_id=dataset_id,
            question=question,
            agent_name=agent_name,
            sql_generation_context=sql_generation_context,
            dialect=dialect,
            current_datasource_dialect=current_datasource_dialect,
            query_constraints=query_constraints,
            allowed_tables=allowed_tables,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )

    async def handle_external_execution_event(
        self,
        session: AgentScopeDatasetRuntimeSession,
        event: RequireExternalExecutionEvent,
    ) -> ExternalExecutionResultEvent:
        """执行 AgentScope 外部工具事件，并生成可回填给 Agent 的安全结果块。"""

        execution_results: list[ToolResultBlock] = []
        for tool_call in event.tool_calls:
            tool_input = self._parse_tool_input(tool_call.input)
            tool = self._tool_for_call(session=session, name=tool_call.name)
            decision = await tool.check_permissions(tool_input, PermissionContext())
            if decision.behavior is not PermissionBehavior.ALLOW:
                payload = self._blocked_payload(str(decision.decision_reason or "PERMISSION_DENIED"))
                execution_results.append(
                    self._tool_result_block(
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.name,
                        payload=payload,
                        state=ToolResultState.DENIED,
                    )
                )
                session.last_error = payload
                session.tool_results.append({"name": tool_call.name, **payload})
                continue

            try:
                payload = self._execute_tool(session, tool_call.name, tool_input)
                state = ToolResultState.SUCCESS if payload.get("status") != "blocked" else ToolResultState.DENIED
            except Exception as exc:  # pragma: no cover - 防御外部 SDK/DB 异常，确保回填仍安全。
                logger.exception("AgentScope DatasetAgent external tool execution failed: %s", tool_call.name)
                payload = self._blocked_payload("EXTERNAL_TOOL_EXECUTION_FAILED", error_summary=str(exc))
                state = ToolResultState.ERROR

            self._advance_session_after_tool(
                session=session,
                tool_name=tool_call.name,
                payload=payload,
                state=state,
            )
            session.tool_results.append({"name": tool_call.name, **payload})
            execution_results.append(
                self._tool_result_block(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    payload=payload,
                    state=state,
                )
            )

        result_event = ExternalExecutionResultEvent(
            reply_id=event.reply_id,
            execution_results=execution_results,
        )
        return result_event

    async def run_reply_stream(
        self,
        agent: Any,
        *,
        msg: Any,
        session: AgentScopeDatasetRuntimeSession,
    ) -> list[Any]:
        """驱动 AgentScope agent.reply_stream，并在外部工具事件处暂停/执行/回填。"""

        results: list[Any] = []

        async def drive_event(event: Any) -> None:
            if isinstance(event, RequireExternalExecutionEvent):
                external_event = await self.handle_external_execution_event(session, event)
                results.append(external_event)
                reply_result = await agent.reply(external_event)
                await drive_reply_result(reply_result)
                return
            results.append(event)

        async def drive_reply_result(reply_result: Any) -> None:
            if hasattr(reply_result, "__aiter__"):
                async for item in reply_result:
                    # AgentScope 在收到 external result 后可能继续发起下一轮工具请求；
                    # 必须递归执行并回填，不能只把事件追加到结果列表里。
                    await drive_event(item)
                return
            await drive_event(reply_result)

        async for event in agent.reply_stream(msg):
            await drive_event(event)
        return results

    async def run_direct_query(
        self,
        *,
        session: AgentScopeDatasetRuntimeSession,
        dsl: Any,
    ) -> dict[str, Any]:
        """直通测试入口使用的确定性 tool-call 驱动；真实执行仍走 AgentScope external event。"""

        final_execute_payload: dict[str, Any] | None = None
        artifact_summary: dict[str, Any] | None = None
        for _ in range(len(AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE) + 2):
            tool_name = session.expected_tool_name
            if tool_name is None:
                break
            tool_input: dict[str, Any] = {}
            if tool_name == "compile_dsl_to_sql":
                # DSL 由 direct 入口外部生成，但 compile/execute/repair 均由 AgentScope 工具状态机管控。
                tool_input["dsl"] = dsl.to_dict() if hasattr(dsl, "to_dict") else dsl
            elif tool_name in {"execute_compiled_query", "repair_dsl"}:
                tool_input["compiled_query_ref"] = str(session.compiled_query_ref or "")

            result_event = await self.handle_external_execution_event(
                session,
                RequireExternalExecutionEvent(
                    reply_id=f"dataset-runtime-direct-{tool_name}",
                    tool_calls=[
                        ToolCallBlock(
                            id=f"dataset-runtime-direct-{tool_name}",
                            name=tool_name,
                            input=json.dumps(tool_input, ensure_ascii=False, default=str),
                        )
                    ],
                ),
            )
            block = result_event.execution_results[0]
            payload = self._payload_from_tool_result_block(block)
            if tool_name == "execute_compiled_query" and block.state == ToolResultState.SUCCESS:
                final_execute_payload = payload
            elif tool_name == "get_artifact_summary" and block.state == ToolResultState.SUCCESS:
                artifact_summary = payload
            if block.state != ToolResultState.SUCCESS:
                # FIELD_NOT_FOUND 是唯一允许继续的 blocked 状态；下一步必须切到 repair_dsl。
                if tool_name == "execute_compiled_query" and session.repair_pending:
                    continue
                return {
                    "status": "blocked",
                    "code": payload.get("code") or "RUNTIME_BLOCKED",
                    "error_summary": payload.get("error_summary"),
                    "tool_results": session.tool_results,
                }
        else:
            return {
                "status": "blocked",
                "code": "TOOL_SEQUENCE_EXHAUSTED",
                "tool_results": session.tool_results,
            }

        return {
            "status": "completed" if session.artifact_ref else "blocked",
            "artifact_ref": session.artifact_ref,
            "artifact_summary": artifact_summary or {},
            "row_count": (final_execute_payload or {}).get("row_count"),
            "column_count": (final_execute_payload or {}).get("column_count"),
            "tool_results": session.tool_results,
        }

    def _execute_tool(
        self,
        session: AgentScopeDatasetRuntimeSession,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name == "get_dataset_status":
            dataset_status = self.toolkit.execute_tool("get_dataset_status", dataset_id=session.dataset_id)
            if dataset_status.get("status") in {"not_found", "disabled", "inactive"}:
                return self._blocked_payload("DATASET_NOT_AVAILABLE")
            return self._safe_output(
                {
                    "status": dataset_status.get("status") or "ready",
                    "dataset_id": session.dataset_id,
                }
            )
        if tool_name == "list_candidate_assets":
            candidate_assets = self.toolkit.execute_tool(
                "list_candidate_assets",
                dataset_id=session.dataset_id,
                question=session.question,
            )
            return self._safe_output(
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
        if tool_name == "compile_dsl_to_sql":
            compiled = self.toolkit.execute_tool(
                "compile_dsl_to_sql",
                dataset_id=session.dataset_id,
                dsl=tool_input["dsl"],
                sql_generation_context=session.sql_generation_context,
                dialect=session.dialect,
                current_datasource_dialect=session.current_datasource_dialect,
                query_constraints=session.query_constraints,
                allowed_tables=session.allowed_tables,
            )
            if compiled.get("status") != "compiled":
                return self._blocked_payload(
                    str(compiled.get("code") or "COMPILE_BLOCKED"),
                    error_summary=compiled.get("error_summary"),
                )
            session.compiled_query_ref = str(compiled["compiled_query_ref"])
            return self._safe_output(
                {
                    "status": "compiled",
                    "compiled_query_ref": session.compiled_query_ref,
                    "agent_context": {"compiled_query_ref": session.compiled_query_ref},
                }
            )
        if tool_name == "execute_compiled_query":
            executed = self.toolkit.execute_tool(
                "execute_compiled_query",
                compiled_query_ref=session.compiled_query_ref or "",
                dataset_id=session.dataset_id,
                conversation_id=session.conversation_id,
                trace_id=session.trace_id,
            )
            if executed.get("status") != "completed":
                return self._blocked_payload(str(executed.get("code") or executed.get("status") or "EXECUTE_BLOCKED"))
            session.artifact_ref = str(executed["artifact_ref"])
            return self._safe_output(
                {
                    "status": "completed",
                    "artifact_ref": session.artifact_ref,
                    "row_count": executed.get("row_count"),
                    "column_count": executed.get("column_count"),
                }
            )
        if tool_name == "repair_dsl":
            repaired = self.toolkit.execute_tool(
                "repair_dsl",
                compiled_query_ref=session.compiled_query_ref or "",
                dataset_id=session.dataset_id,
            )
            if repaired.get("status") != "repaired":
                return self._blocked_payload(str(repaired.get("code") or "REPAIR_DSL_BLOCKED"))
            session.compiled_query_ref = str(repaired["compiled_query_ref"])
            return self._safe_output(
                {
                    "status": "repaired",
                    "compiled_query_ref": session.compiled_query_ref,
                    "agent_context": {"compiled_query_ref": session.compiled_query_ref},
                    "repair_count": repaired.get("repair_count"),
                }
            )
        if tool_name == "create_query_artifact":
            return self._safe_output({"status": "ready", "artifact_ref": session.artifact_ref})
        if tool_name == "get_artifact_summary":
            return self._safe_output(
                {
                    "status": "ready",
                    **self.toolkit.execute_tool("get_artifact_summary", artifact_ref=str(session.artifact_ref)),
                }
            )
        return self._blocked_payload("TOOL_NOT_WHITELISTED")

    @staticmethod
    def _advance_session_after_tool(
        *,
        session: AgentScopeDatasetRuntimeSession,
        tool_name: str,
        payload: dict[str, Any],
        state: ToolResultState,
    ) -> None:
        if state != ToolResultState.SUCCESS:
            session.last_error = payload
            if (
                tool_name == "execute_compiled_query"
                and payload.get("code") == "FIELD_NOT_FOUND"
                and not session.repair_attempted
            ):
                session.repair_pending = True
                session.expected_tool_index = _REPAIR_TOOL_INDEX
            return
        session.last_error = None
        if tool_name == "repair_dsl":
            session.repair_pending = False
            session.repair_attempted = True
            session.expected_tool_index = _EXECUTE_TOOL_INDEX
            return
        if tool_name == "execute_compiled_query":
            session.repair_pending = False
            session.expected_tool_index = _CREATE_ARTIFACT_TOOL_INDEX
            return
        session.expected_tool_index += 1

    def _tool_for_call(
        self,
        *,
        session: AgentScopeDatasetRuntimeSession,
        name: str,
    ) -> DatasetAgentScopeExternalTool:
        return DatasetAgentScopeExternalTool(
            name=name,
            description=f"Datalogue DatasetAgent external tool: {name}",
            input_schema=_tool_input_schema(name),
            session=session,
            agent_name=session.agent_name,
        )

    @staticmethod
    def _parse_tool_input(raw_input: Any) -> dict[str, Any]:
        if isinstance(raw_input, dict):
            return raw_input
        if isinstance(raw_input, str) and raw_input.strip():
            loaded = json.loads(raw_input)
            return loaded if isinstance(loaded, dict) else {}
        return {}

    @staticmethod
    def _payload_from_tool_result_block(block: ToolResultBlock) -> dict[str, Any]:
        if not block.output or not isinstance(block.output[0], TextBlock):
            return {}
        try:
            payload = json.loads(block.output[0].text)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _safe_output(self, payload: dict[str, Any]) -> dict[str, Any]:
        safe_payload = self._sanitizer.sanitize_output(payload)
        return safe_payload if isinstance(safe_payload, dict) else self._blocked_payload("OUTPUT_SANITIZED")

    def _blocked_payload(self, code: str, *, error_summary: Any | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": "blocked", "code": code}
        if error_summary:
            payload["error_summary"] = str(error_summary)
        return self._safe_output(payload)

    @staticmethod
    def _tool_result_block(
        *,
        tool_call_id: str,
        tool_name: str,
        payload: dict[str, Any],
        state: ToolResultState,
    ) -> ToolResultBlock:
        return ToolResultBlock(
            id=tool_call_id,
            name=tool_name,
            output=[TextBlock(text=json.dumps(payload, ensure_ascii=False, default=str))],
            state=state,
        )


def build_dataset_agentscope_tools(
    *,
    session: AgentScopeDatasetRuntimeSession,
    agent_name: str = "bi_lead_agent",
) -> list[DatasetAgentScopeExternalTool]:
    """构建 AgentScope 可注册的 DatasetAgent external tools。"""

    return [
        DatasetAgentScopeExternalTool(
            name=name,
            description=f"Datalogue DatasetAgent external tool: {name}",
            input_schema=_tool_input_schema(name),
            session=session,
            agent_name=agent_name,
        )
        for name in AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE
    ]


def _tool_input_schema(name: str) -> dict[str, Any]:
    base_schema: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}
    if name == "compile_dsl_to_sql":
        return {
            "type": "object",
            "properties": {
                "dsl": {
                    "type": "object",
                    "description": "DatasetAgent 生成的结构化 DSL；不能包含 SQL。",
                },
            },
            "required": ["dsl"],
            "additionalProperties": False,
        }
    if name in {"execute_compiled_query", "repair_dsl"}:
        return {
            "type": "object",
            "properties": {
                "compiled_query_ref": {
                    "type": "string",
                    "description": "compile_dsl_to_sql 或 repair_dsl 返回的私有执行句柄。",
                },
            },
            "required": ["compiled_query_ref"],
            "additionalProperties": False,
        }
    return base_schema
