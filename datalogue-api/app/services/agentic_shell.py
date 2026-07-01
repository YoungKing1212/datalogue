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

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


AgentStatus = Literal["enabled", "disabled"]
AgenticShellStatus = Literal["ready", "disabled"]
TaskType = Literal["bi_query", "report", "python_analysis", "audit", "unsupported"]
AgenticShellWriteKind = Literal["event", "action", "checkpoint"]


AS_R0_ALLOWED_BI_TOOLS = [
    "get_dataset_status",
    "list_candidate_assets",
    "get_artifact_summary",
]

AS_R0_BI_CAPABILITIES = [
    "query_dataset",
    "query_multiple_datasets",
]

AS_R0_RESERVED_DATASET_TOOLS = [
    "compile_dsl_to_sql",
    "execute_compiled_query",
    "create_query_artifact",
]

AS_R0_DISABLED_FUTURE_TOOLS = [
    "repair_dsl",
    "classify_query_failure",
    "create_report_from_artifact",
    "run_sandboxed_analysis_on_artifact",
]

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
    policy_version: str = "as-r0"


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
    """AS-R0 Agentic Shell 统一入口；当前只生成契约，不替换 /chat/stream。"""

    def __init__(
        self,
        *,
        registry: list[AgentRegistryEntry] | None = None,
        writer: AgenticShellWriter | None = None,
    ) -> None:
        self.registry = registry or self._default_registry()
        self.writer = writer or NoopAgenticShellWriter()

    def prepare_turn(
        self,
        *,
        question: str,
        context: dict[str, Any] | None = None,
    ) -> AgenticShellTurnContract:
        task_type = self.classify_task(question)
        selected_agent = self._select_agent(task_type)
        status: AgenticShellStatus = "ready" if selected_agent == "bi_lead_agent" else "disabled"
        # AS-R0 fail-closed：只有 BI 主链能拿到工具；placeholder Agent 必须没有工具白名单。
        tool_policy = (
            AgenticToolPolicy(
                allowed_tools=list(AS_R0_ALLOWED_BI_TOOLS),
                business_capabilities=list(AS_R0_BI_CAPABILITIES),
                disabled_tools=list(AS_R0_RESERVED_DATASET_TOOLS + AS_R0_DISABLED_FUTURE_TOOLS),
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
    def _default_registry() -> list[AgentRegistryEntry]:
        return [
            AgentRegistryEntry(
                name="bi_lead_agent",
                role="BI 主链能力路由与 DatasetAgent Runtime 调度",
                status="enabled",
            ),
            AgentRegistryEntry(
                name="report_agent",
                role="从查询 artifact 生成报告",
                status="disabled",
                reason="AS-R0 只启用 BI 主链，报告生成留到后续阶段",
            ),
            AgentRegistryEntry(
                name="python_agent",
                role="在沙箱中基于 artifact 做二次分析",
                status="disabled",
                reason="沙箱分析工具尚未进入 AS-R0 白名单",
            ),
            AgentRegistryEntry(
                name="audit_agent",
                role="审计查询、策略与工具调用",
                status="disabled",
                reason="审计链路先作为 registry 占位",
            ),
        ]

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
