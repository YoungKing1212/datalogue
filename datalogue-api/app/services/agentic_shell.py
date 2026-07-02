# ============================================================
# File Name   : agentic_shell.py
# Description:
#   Datalogue Agentic Shell-first AS-R0 契约层。
#
# Responsibilities:
#   - 定义 Agentic Shell 统一受控运行环境的 Agent Registry、工具白名单和回合契约。
#   - 在进入 AgentScope Runtime 前执行任务分类、上下文投影和输出清洗。
#   - 固定 AS-R0 只启用 BI 主链，其他业务 Agent 以 disabled placeholder 形式占位。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


AgentStatus = Literal["enabled", "disabled"]
AgenticShellStatus = Literal["ready", "disabled"]
AgenticShellActionStatus = Literal["ready", "disabled"]
AgenticFutureToolStatus = Literal["disabled", "admin_gated"]
TaskType = Literal["bi_query", "report", "python_analysis", "audit", "unsupported"]
AgenticShellWriteKind = Literal["event", "action", "checkpoint"]
AgenticStreamDelegate = Callable[[], AsyncIterator[dict[str, Any]]]


AS_R0_ALLOWED_BI_TOOLS = [
    "get_dataset_status",
    "list_candidate_assets",
    "compile_dsl_to_sql",
    "execute_compiled_query",
    "repair_dsl",
    "create_query_artifact",
    "get_artifact_summary",
]

AS_R0_BI_CAPABILITIES = [
    "query_dataset",
    "query_multiple_datasets",
]

AS_R0_RESERVED_DATASET_TOOLS: list[str] = []

AS_R0_DISABLED_FUTURE_TOOLS = [
    "classify_query_failure",
    "create_report_from_artifact",
    "run_sandboxed_analysis_on_artifact",
]

AS_R0_OPTIONAL_AGENT_TOOL_WHITELISTS = {
    "report_agent": ["create_report_from_artifact"],
    "python_agent": ["run_sandboxed_analysis_on_artifact"],
    "audit_agent": ["classify_query_failure"],
}

# 这些字段只能在 compile/execute/tool 内部流转，不能进入 Agent 上下文或用户可见输出。
FORBIDDEN_AGENT_CONTEXT_KEYS = {
    "sql",
    "raw_sql",
    "direct_sql",
    "llm_sql",
    "schema",
    "schema_context",
    "schema_structured",
    "ddl_context",
    "raw_rows",
    "raw_result",
    "query_plan",
    "repair_patch",
    "patch_body",
    "blueprint",
    "blueprint_context",
}

FORBIDDEN_KEY_FRAGMENTS = {
    "ddl",
    "directsql",
    "field",
    "fields",
    "llmsql",
    "patchbody",
    "queryplan",
    "raw",
    "rawresult",
    "rawrows",
    "repairpatch",
    "rows",
    "schema",
    "sql",
}

SAFE_SCHEMA_SUMMARY_KEYS = {
    "metadata_schema_summary",
    "selected_table_count",
}

SAFE_CONTEXT_KEYS = {
    "artifact_ref",
    "checkpoint_ref",
    "conversation_id",
    "dataset_id",
    "question",
    "session_id",
    "thread_id",
    "time_context",
}


class AgentRegistryEntry(BaseModel):
    """Agentic Shell Registry 中的单个 Agent 定义。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    role: str
    status: AgentStatus
    reason: str | None = None


class AgenticToolPolicy(BaseModel):
    """单次 Shell 回合可见的工具策略。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_tools: list[str] = Field(default_factory=list)
    business_capabilities: list[str] = Field(default_factory=list)
    disabled_tools: list[str] = Field(default_factory=list)
    disabled_tool_specs: list["AgenticDisabledToolSpec"] = Field(default_factory=list)
    policy_version: str = "as-r0"


class AgenticDisabledToolSpec(BaseModel):
    """P2.3 future tool 契约；默认不可执行，必要时只允许 admin gate。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: AgenticFutureToolStatus
    gate: Literal["not_enabled", "admin_only"]
    reason: str


class ProjectedContext(BaseModel):
    """投影后的 Agent 上下文；只保留安全业务字段和 safe_* 扩展字段。"""

    model_config = ConfigDict(extra="allow", frozen=True)

    question: str
    conversation_id: int | None = None
    dataset_id: int | None = None
    thread_id: str | None = None
    session_id: str | None = None
    artifact_ref: str | None = None
    checkpoint_ref: str | None = None
    time_context: dict[str, Any] | None = None

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(*args, **kwargs)


class AgenticShellTurnContract(BaseModel):
    """Agentic Shell 在调用主链 Runtime 前生成的受控回合契约。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: AgenticShellStatus
    task_type: TaskType
    selected_agent: str
    agent_registry: list[AgentRegistryEntry]
    tool_policy: AgenticToolPolicy
    projected_context: ProjectedContext

    @property
    def enabled_agents(self) -> list[str]:
        return [agent.name for agent in self.agent_registry if agent.status == "enabled"]

    @property
    def disabled_agents(self) -> list[str]:
        return [agent.name for agent in self.agent_registry if agent.status == "disabled"]


class AgenticShellAction(BaseModel):
    """Shell 输出给 Runtime 的受控 action；PR1.2 只描述能力路由，不执行工具。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_type: str
    status: AgenticShellActionStatus
    selected_agent: str
    task_type: TaskType
    capability: str | None = None
    allowed_capabilities: list[str] = Field(default_factory=list)
    disabled_reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgenticShellWriteRecord(BaseModel):
    """Shell 写回接口的安全记录；P0 只定义契约，不替换现有持久化主链。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    write_kind: AgenticShellWriteKind
    writer_name: str
    persisted: bool = False
    thread_id: str
    message_id: str | None = None
    event_type: str | None = None
    action_id: str | None = None
    checkpoint_ref: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgenticShellWriter(Protocol):
    """event/action/checkpoint 写回接口；后续 P1 再接真实 Workbench/mirror 写入。"""

    writer_name: str

    def write(self, record: AgenticShellWriteRecord) -> AgenticShellWriteRecord:
        ...


class NoopAgenticShellWriter:
    """默认 writer 只返回安全记录，不产生外部副作用。"""

    writer_name = "noop"

    def write(self, record: AgenticShellWriteRecord) -> AgenticShellWriteRecord:
        return record.model_copy(update={"writer_name": self.writer_name, "persisted": False})


class InMemoryAgenticShellWriter:
    """测试用 writer：记录 Shell 产出的安全写入契约，不连接数据库或 Workbench。"""

    writer_name = "memory"

    def __init__(self) -> None:
        self.records: list[AgenticShellWriteRecord] = []

    def write(self, record: AgenticShellWriteRecord) -> AgenticShellWriteRecord:
        stored = record.model_copy(update={"writer_name": self.writer_name, "persisted": False})
        self.records.append(stored)
        return stored


class DatalogueAgenticShell:
    """Agentic Shell 统一入口；负责生成受控回合契约并选择业务 Agent。"""

    def __init__(
        self,
        *,
        registry: list[AgentRegistryEntry] | None = None,
        writer: AgenticShellWriter | None = None,
        enabled_optional_agents: list[str] | None = None,
    ) -> None:
        self.enabled_optional_agents = set(enabled_optional_agents or [])
        # P2.4 受控启用：未知 Agent 直接拒绝，避免拼写错误或越权配置绕过 registry gate。
        invalid_optional_agents = sorted(
            self.enabled_optional_agents - set(AS_R0_OPTIONAL_AGENT_TOOL_WHITELISTS)
        )
        if invalid_optional_agents:
            raise ValueError(f"Unknown optional agents: {invalid_optional_agents}")
        self.registry = registry or self._default_registry(self.enabled_optional_agents)
        self.writer = writer or NoopAgenticShellWriter()

    def prepare_turn(
        self,
        *,
        question: str,
        context: dict[str, Any] | None = None,
    ) -> AgenticShellTurnContract:
        task_type = self.classify_task(question)
        selected_agent = self._select_agent(task_type)
        # P2.4 默认仍 fail-closed；只有显式启用的业务 Agent 才能从 placeholder 变成 ready。
        status: AgenticShellStatus = (
            "ready"
            if selected_agent == "bi_lead_agent" or selected_agent in self.enabled_optional_agents
            else "disabled"
        )
        allowed_tools = self._allowed_tools_for_agent(selected_agent) if status == "ready" else []
        business_capabilities = (
            self._business_capabilities_for_agent(selected_agent) if status == "ready" else []
        )
        disabled_future_tools = [
            tool for tool in AS_R0_DISABLED_FUTURE_TOOLS if tool not in set(allowed_tools)
        ]
        # AS-R0 fail-closed：只有显式启用的 Agent 能拿到自己的单独工具白名单。
        tool_policy = (
            AgenticToolPolicy(
                allowed_tools=allowed_tools,
                business_capabilities=business_capabilities,
                disabled_tools=list(AS_R0_RESERVED_DATASET_TOOLS + disabled_future_tools),
                disabled_tool_specs=self._future_tool_specs(exclude_tools=allowed_tools),
            )
            if status == "ready"
            else AgenticToolPolicy(
                allowed_tools=[],
                business_capabilities=[],
                disabled_tools=list(
                    AS_R0_ALLOWED_BI_TOOLS
                    + AS_R0_BI_CAPABILITIES
                    + AS_R0_RESERVED_DATASET_TOOLS
                    + AS_R0_DISABLED_FUTURE_TOOLS
                ),
                disabled_tool_specs=self._future_tool_specs(),
            )
        )
        projected_context = self.project_context(question=question, context=context or {})
        return AgenticShellTurnContract(
            status=status,
            task_type=task_type,
            selected_agent=selected_agent,
            agent_registry=self.registry,
            tool_policy=tool_policy,
            projected_context=projected_context,
        )

    def route_agent_action(
        self,
        *,
        question: str,
        context: dict[str, Any] | None = None,
        capability: str | None = None,
    ) -> AgenticShellAction:
        """PR1.2 LeadAgent 能力路由；BI 只开放查询能力，其他 Agent 返回 disabled action。"""

        contract = self.prepare_turn(question=question, context=context or {})
        return self.route_action_from_contract(contract, capability=capability)

    @staticmethod
    def route_action_from_contract(
        contract: AgenticShellTurnContract,
        *,
        capability: str | None = None,
    ) -> AgenticShellAction:
        """从已生成的 turn contract 派生 action，供 Runtime driver 复用同一白名单判断。"""

        if contract.status != "ready":
            # AS-R0 先把非 BI Agent 显式收束为 disabled action，避免 placeholder 被 Runtime 误执行。
            return AgenticShellAction(
                action_type=f"{contract.selected_agent}.disabled",
                status="disabled",
                selected_agent=contract.selected_agent,
                task_type=contract.task_type,
                disabled_reason="agent_disabled_placeholder",
            )

        requested_capability = capability or "query_dataset"
        allowed_capabilities = list(contract.tool_policy.business_capabilities)
        if requested_capability not in allowed_capabilities:
            # 即使选中 BI LeadAgent，也只能路由 query_dataset/query_multiple_datasets 两个业务能力。
            return AgenticShellAction(
                action_type=f"{contract.selected_agent}.disabled",
                status="disabled",
                selected_agent=contract.selected_agent,
                task_type=contract.task_type,
                capability=requested_capability,
                allowed_capabilities=allowed_capabilities,
                disabled_reason="capability_not_whitelisted",
            )

        return AgenticShellAction(
            action_type=f"{contract.selected_agent}.capability_route",
            status="ready",
            selected_agent=contract.selected_agent,
            task_type=contract.task_type,
            capability=requested_capability,
            allowed_capabilities=allowed_capabilities,
            payload=contract.projected_context.model_dump(),
        )

    async def run_turn(
        self,
        *,
        question: str,
        context: dict[str, Any] | None = None,
        stream_delegate: AgenticStreamDelegate,
    ) -> AsyncIterator[dict[str, Any]]:
        """PR1.1 Runtime 入口；先生成 Shell 契约，再委托兼容流执行器保持 SSE 行为不变。"""

        self.prepare_turn(question=question, context=context or {})
        async for event in stream_delegate():
            # PR1.1 只接管入口生命周期；事件清洗仍由既有 SSE/envelope/mirror 层执行，避免改变 payload 兼容性。
            yield event

    def classify_task(self, question: str) -> TaskType:
        normalized = (question or "").strip().lower()
        # 第一阶段只做粗分类，避免 AS-R0 误把报告/分析/audit 类任务接入未启用主链。
        if any(keyword in normalized for keyword in ("报告", "周报", "日报", "report")):
            return "report"
        if any(keyword in normalized for keyword in ("python", "脚本", "sandbox")):
            return "python_analysis"
        if any(keyword in normalized for keyword in ("审计", "audit")):
            return "audit"
        return "bi_query" if normalized else "unsupported"

    def project_context(self, *, question: str, context: dict[str, Any]) -> ProjectedContext:
        projected: dict[str, Any] = {"question": question}
        for key, value in (context or {}).items():
            # SQL/schema/raw rows 等执行态载荷永远不能投影给 Agent。
            if self._is_forbidden_context_key(key):
                continue
            if key in SAFE_CONTEXT_KEYS or key.startswith("safe_"):
                projected[key] = self.sanitize_output(value)
        return ProjectedContext(**projected)

    def sanitize_output(self, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                # 输出清洗与上下文投影共享禁用键，避免 checkpoint/event/final answer 旁路泄露。
                if self._is_forbidden_output_key(key):
                    continue
                sanitized[key] = self.sanitize_output(item)
            return sanitized
        if isinstance(value, list):
            sanitized_items = [self.sanitize_output(item) for item in value]
            return [item for item in sanitized_items if item is not None]
        if isinstance(value, str):
            return None if self._looks_like_execution_payload(value) else value
        return value

    def record_event(
        self,
        *,
        event_type: str,
        thread_id: str,
        message_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AgenticShellWriteRecord:
        record = self._build_write_record(
            write_kind="event",
            thread_id=thread_id,
            message_id=message_id,
            event_type=event_type,
            payload=payload,
        )
        return self.writer.write(record)

    def record_action(
        self,
        *,
        action_id: str,
        thread_id: str,
        message_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AgenticShellWriteRecord:
        record = self._build_write_record(
            write_kind="action",
            thread_id=thread_id,
            message_id=message_id,
            action_id=action_id,
            payload=payload,
        )
        return self.writer.write(record)

    def record_checkpoint(
        self,
        *,
        checkpoint_ref: str,
        thread_id: str,
        message_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AgenticShellWriteRecord:
        record = self._build_write_record(
            write_kind="checkpoint",
            thread_id=thread_id,
            message_id=message_id,
            checkpoint_ref=checkpoint_ref,
            payload=payload,
        )
        return self.writer.write(record)

    def _build_write_record(
        self,
        *,
        write_kind: AgenticShellWriteKind,
        thread_id: str,
        message_id: str | None = None,
        event_type: str | None = None,
        action_id: str | None = None,
        checkpoint_ref: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AgenticShellWriteRecord:
        # Writer 接口只能接收 Shell 清洗后的业务级 payload，真实持久化留到 P1 适配层。
        safe_payload = self.sanitize_output(payload or {})
        return AgenticShellWriteRecord(
            write_kind=write_kind,
            writer_name=getattr(self.writer, "writer_name", "unknown"),
            persisted=False,
            thread_id=thread_id,
            message_id=message_id,
            event_type=event_type,
            action_id=action_id,
            checkpoint_ref=checkpoint_ref,
            payload=safe_payload if isinstance(safe_payload, dict) else {},
        )

    @staticmethod
    @staticmethod
    def _allowed_tools_for_agent(selected_agent: str) -> list[str]:
        if selected_agent == "bi_lead_agent":
            return list(AS_R0_ALLOWED_BI_TOOLS)
        return list(AS_R0_OPTIONAL_AGENT_TOOL_WHITELISTS.get(selected_agent, []))

    @staticmethod
    def _business_capabilities_for_agent(selected_agent: str) -> list[str]:
        if selected_agent == "bi_lead_agent":
            return list(AS_R0_BI_CAPABILITIES)
        return list(AS_R0_OPTIONAL_AGENT_TOOL_WHITELISTS.get(selected_agent, []))

    @staticmethod
    def _default_registry(enabled_optional_agents: set[str] | None = None) -> list[AgentRegistryEntry]:
        enabled_optional_agents = enabled_optional_agents or set()
        return [
            AgentRegistryEntry(
                name="bi_lead_agent",
                role="BI 主链能力路由与 DatasetAgent Runtime 调度",
                status="enabled",
            ),
            AgentRegistryEntry(
                name="report_agent",
                role="从查询 artifact 生成报告",
                status="enabled" if "report_agent" in enabled_optional_agents else "disabled",
                reason=None
                if "report_agent" in enabled_optional_agents
                else "AS-R0 只启用 BI 主链，报告生成留到后续阶段",
            ),
            AgentRegistryEntry(
                name="python_agent",
                role="在沙箱中基于 artifact 做二次分析",
                status="enabled" if "python_agent" in enabled_optional_agents else "disabled",
                reason=None
                if "python_agent" in enabled_optional_agents
                else "沙箱分析工具尚未进入 AS-R0 白名单",
            ),
            AgentRegistryEntry(
                name="audit_agent",
                role="审计查询、策略与工具调用",
                status="enabled" if "audit_agent" in enabled_optional_agents else "disabled",
                reason=None
                if "audit_agent" in enabled_optional_agents
                else "审计链路先作为 registry 占位",
            ),
        ]

    @staticmethod
    def _future_tool_specs(*, exclude_tools: list[str] | None = None) -> list[AgenticDisabledToolSpec]:
        """P2.3：future tools 只能以 disabled/admin-gated 契约出现，不能进入 allowed_tools。"""

        excluded = set(exclude_tools or [])
        specs = [
            AgenticDisabledToolSpec(
                name="repair_dsl",
                status="admin_gated",
                gate="admin_only",
                reason="requires_admin_repair_policy",
            ),
            AgenticDisabledToolSpec(
                name="classify_query_failure",
                status="disabled",
                gate="not_enabled",
                reason="failure_classifier_not_enabled",
            ),
            AgenticDisabledToolSpec(
                name="create_report_from_artifact",
                status="admin_gated",
                gate="admin_only",
                reason="report_agent_placeholder_disabled",
            ),
            AgenticDisabledToolSpec(
                name="run_sandboxed_analysis_on_artifact",
                status="admin_gated",
                gate="admin_only",
                reason="python_agent_placeholder_disabled",
            ),
        ]
        return [spec for spec in specs if spec.name not in excluded]

    @staticmethod
    def _select_agent(task_type: TaskType) -> str:
        mapping = {
            "bi_query": "bi_lead_agent",
            "report": "report_agent",
            "python_analysis": "python_agent",
            "audit": "audit_agent",
            "unsupported": "unsupported",
        }
        return mapping[task_type]

    @staticmethod
    def _is_forbidden_context_key(key: str) -> bool:
        return DatalogueAgenticShell._is_forbidden_key(key, allow_schema_summary=False)

    @staticmethod
    def _is_forbidden_output_key(key: str) -> bool:
        return DatalogueAgenticShell._is_forbidden_key(key, allow_schema_summary=True)

    @staticmethod
    def _is_forbidden_key(key: str, *, allow_schema_summary: bool) -> bool:
        normalized = DatalogueAgenticShell._normalize_key(key)
        if allow_schema_summary and str(key) in SAFE_SCHEMA_SUMMARY_KEYS:
            return False
        # 输出里允许出现 blueprint 目录摘要键；真正禁止的是 SQL/schema/patch/body 等内部载荷。
        exact_forbidden = {DatalogueAgenticShell._normalize_key(item) for item in FORBIDDEN_AGENT_CONTEXT_KEYS}
        if normalized in exact_forbidden:
            return not (allow_schema_summary and normalized == "blueprint")
        return any(fragment in normalized for fragment in FORBIDDEN_KEY_FRAGMENTS)

    @staticmethod
    def _normalize_key(key: str) -> str:
        return "".join(char for char in str(key).lower() if char.isalnum())

    @staticmethod
    def _looks_like_execution_payload(value: str) -> bool:
        lowered = value.lower()
        sql_markers = (
            "select ",
            " from ",
            " join ",
            " where ",
            "insert ",
            "update ",
            "delete ",
        )
        if any(marker in lowered for marker in sql_markers):
            return True
        # 物理字段明细常以 table.column 形式出现，Agent 可见层只保留业务名。
        return "." in value and any(char.isalpha() for char in value)
