# ============================================================
# File Name   : mvp.py
# Description:
#   AgentScope 2.0 Hermes-style DatasetAgent MVP 的真实服务调用实现。
#
# Responsibilities:
#   - 加载 Hermes SOUL/SKILL/capability 文档，生成受控 DatasetAgent system prompt。
#   - 使用 capability_manifest 决定 AgentScope Toolkit 暴露哪些工具。
#   - 通过 Datalogue Tool Adapter 调用真实语义资产 API 和只读 SQL preview。
#   - 返回 result_ref、artifact、tool_trace 和 preview_result，便于验证业务真相源边界。
#
# Author      : yangkai
# Created On  : 2026-06-25
# ============================================================

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from agentscope.agent import Agent
from agentscope.agent._config import ModelConfig
from agentscope.credential import OpenAICredential
from agentscope.message import Msg, TextBlock, ToolCallBlock, UserMsg
from agentscope.model import ChatResponse, OpenAIChatModel
from agentscope.permission import PermissionBehavior, PermissionContext, PermissionDecision
from agentscope.tool import ToolBase, ToolChunk, Toolkit

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.llm_config import resolve_llm_config


logger = logging.getLogger(__name__)

DEFAULT_DATASET_AGENT_TOOLS = (
    "recall_assets",
    "plan_query",
    "guard_sql",
    "preview_sql",
    "execute_query",
    "persist_artifact",
    "summarize_result",
)

LEAD_AGENT_ALLOWED_TOOL_SURFACE = (
    "list_datasets",
    "describe_dataset_capability",
    "query_dataset",
    "query_multiple_datasets",
)

SQL_GENERATION_RULES = [
    "只能基于 selected_tables / selected_columns 中出现的表和字段生成 SQL。",
    "只允许 SELECT 或 WITH 查询，不允许 INSERT / UPDATE / DELETE / DROP / DDL。",
    "生成 SQL 后必须调用 preview_sql 或 execute_query；两者都只能进入 Datalogue SQL preview。",
    "不要调用 /api/chat/stream，也不要调用 /api/conversation。",
    "不要直连数据库，不要把 AgentScope memory 当作 conversation_state 或 query_artifact 真相源。",
]


@dataclass(frozen=True)
class CapabilityManifest:
    """控制 DatasetAgent 可见工具面的最小 manifest。"""

    agent_name: str = "DatalogueDatasetAgentMVP"
    agent_role: str = "dataset_agent"
    allowed_tools: tuple[str, ...] = DEFAULT_DATASET_AGENT_TOOLS
    lead_agent_surface: tuple[str, ...] = LEAD_AGENT_ALLOWED_TOOL_SURFACE
    raw_sql_visible_to_lead_agent: bool = False
    state_truth_sources: tuple[str, ...] = (
        "conversation_state",
        "query_artifact",
        "manifest",
        "sql_audit",
        "langfuse_trace",
    )


@dataclass
class HermesSkillPrompt:
    """从 Hermes skill 文件加载后的 prompt 素材。"""

    soul: str
    skill: str
    capabilities: str
    source_paths: dict[str, str]


@dataclass
class DatalogueToolTrace:
    """记录 AgentScope DatasetAgent 实际调用过哪些数语能力。"""

    tool_names: list[str] = field(default_factory=list)
    called_paths: list[str] = field(default_factory=list)
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    react_events: list[dict[str, Any]] = field(default_factory=list)
    preview_result: dict[str, Any] | None = None
    artifact: dict[str, Any] | None = None
    result_ref: str | None = None


@dataclass
class DatalogueReactMvpResult:
    """真实 Hermes-style DatasetAgent MVP 的测试可断言结果。"""

    final_text: str
    tool_names: list[str]
    called_paths: list[str]
    preview_result: dict[str, Any] | None
    result_ref: str | None
    artifact: dict[str, Any] | None
    tool_trace: list[dict[str, Any]]
    react_trace: list[dict[str, Any]]
    registered_tools: list[str]
    capability_manifest: dict[str, Any]
    system_prompt: str
    prompt_sources: dict[str, str]


def default_capability_manifest(
    *,
    allowed_tools: tuple[str, ...] = DEFAULT_DATASET_AGENT_TOOLS,
) -> CapabilityManifest:
    return CapabilityManifest(allowed_tools=allowed_tools)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_hermes_skill_prompt(repo_root: Path | None = None) -> HermesSkillPrompt:
    root = repo_root or _repo_root()
    skill_root = root / "hermes-skills" / "datalogue"
    source_paths = {
        "SOUL.md": str(skill_root / "SOUL.md"),
        "SKILL.md": str(skill_root / "SKILL.md"),
        "capabilities.md": str(skill_root / "references" / "capabilities.md"),
    }
    return HermesSkillPrompt(
        soul=Path(source_paths["SOUL.md"]).read_text(encoding="utf-8"),
        skill=Path(source_paths["SKILL.md"]).read_text(encoding="utf-8"),
        capabilities=Path(source_paths["capabilities.md"]).read_text(encoding="utf-8"),
        source_paths=source_paths,
    )


def build_dataset_agent_system_prompt(
    *,
    hermes_prompt: HermesSkillPrompt,
    manifest: CapabilityManifest,
) -> str:
    manifest_json = json.dumps(asdict(manifest), ensure_ascii=False, indent=2)
    return (
        "你是 AgentScope 2.0 中的 Datalogue Hermes-style DatasetAgent MVP。\n"
        "你的职责是验证 AgentScope 能否像 Hermes ReActAgent 一样，在受控工具面内自主决策。\n\n"
        "【角色边界】\n"
        "- 你是 DatasetAgent，不是 LeadAgent。\n"
        "- LeadAgent 只能看到 list_datasets / describe_dataset_capability / query_dataset / query_multiple_datasets。\n"
        "- 你内部可以使用 capability_manifest 允许的 DatasetAgent 工具，但不能调用未注册工具。\n"
        "- SQL、schema 细节和完整 rows 只能停留在 DatasetAgent / artifact 边界内。\n"
        "- conversation_state、query_artifact、Manifest、SQL audit、Langfuse trace 仍是 Datalogue 业务真相源。\n\n"
        "【capability_manifest】\n"
        f"{manifest_json}\n\n"
        "【必须遵守的 SQL 规则】\n"
        f"{json.dumps(SQL_GENERATION_RULES, ensure_ascii=False, indent=2)}\n\n"
        "【推荐 ReAct 流程】\n"
        "1. 调用 recall_assets 获取真实数据集、语义资产、已选表和已选字段。\n"
        "2. 调用 plan_query 形成数据集内部查询计划和 SQL 生成边界。\n"
        "3. 生成只读 SELECT/WITH SQL。\n"
        "4. 调用 preview_sql 或 execute_query；两者都必须走 Datalogue SQL preview，不允许直连数据库。\n"
        "5. 使用 result_ref / artifact / sql_guard / rows 摘要回答，不要调用 /api/chat/stream 或 /api/conversation。\n\n"
        "【Hermes SOUL.md】\n"
        f"{hermes_prompt.soul}\n\n"
        "【Hermes SKILL.md】\n"
        f"{hermes_prompt.skill}\n\n"
        "【Hermes capabilities.md】\n"
        f"{hermes_prompt.capabilities}\n"
    )


def _json_chunk(payload: dict[str, Any]) -> ToolChunk:
    return ToolChunk(content=[TextBlock(text=json.dumps(payload, ensure_ascii=False, default=str))])


def _json_preview(payload: Any, *, limit: int = 1200) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<truncated {len(text) - limit} chars>"


def _text_preview(text: str | None, *, limit: int = 1200) -> str:
    value = text or ""
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...<truncated {len(value) - limit} chars>"


def _trace_content_blocks(content: list[Any]) -> list[dict[str, Any]]:
    traced: list[dict[str, Any]] = []
    for block in content:
        if isinstance(block, TextBlock):
            traced.append(
                {
                    "type": "assistant_visible_text",
                    "text": _text_preview(block.text),
                }
            )
            continue
        if isinstance(block, ToolCallBlock):
            traced.append(
                {
                    "type": "tool_call",
                    "name": block.name,
                    "input": block.input,
                    "id": block.id,
                }
            )
            continue
        traced.append({"type": type(block).__name__, "value": str(block)})
    return traced


def _trace_messages(messages: list[dict[str, Any]], *, limit: int = 4) -> list[dict[str, Any]]:
    traced: list[dict[str, Any]] = []
    for message in messages[-max(limit, 1) :]:
        copied = dict(message)
        if isinstance(copied.get("content"), str):
            copied["content"] = _text_preview(copied["content"], limit=1800)
        traced.append(copied)
    return traced


def _log_react_event(trace: DatalogueToolTrace | None, event: dict[str, Any]) -> None:
    if trace is not None:
        trace.react_events.append(event)
    logger.info("[AgentScope Hermes MVP][ReAct trace] %s", _json_preview(event, limit=2400))


def _compact_columns(columns: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for column in columns[: max(limit, 1)]:
        compact.append(
            {
                "table_name": column.get("table_name"),
                "column_name": column.get("column_name"),
                "data_type": column.get("data_type"),
                "column_comment": column.get("column_comment"),
                "effective_desc": column.get("effective_desc"),
                "semantic_role": column.get("semantic_role")
                or column.get("ai_semantic_role")
                or column.get("user_semantic_role"),
            }
        )
    return compact


def _text_from_reply(reply: Any) -> str:
    content = getattr(reply, "content", reply)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            text = getattr(block, "text", None)
            if text:
                parts.append(str(text))
        return "\n".join(parts)
    return str(content or "")


def _first_rows(rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    return rows[: max(limit, 0)]


def _make_result_ref(preview_result: dict[str, Any]) -> str:
    payload = json.dumps(preview_result, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"mvp://query_artifact/{preview_result.get('dataset_id', 'unknown')}/{digest}"


def _artifact_from_preview(
    *,
    question: str | None,
    preview_result: dict[str, Any],
    result_ref: str,
) -> dict[str, Any]:
    rows = preview_result.get("rows") or []
    return {
        "result_ref": result_ref,
        "persisted": False,
        "truth_source": "datalogue_sql_preview",
        "question": question,
        "dataset_id": preview_result.get("dataset_id"),
        "summary": {
            "row_count": preview_result.get("row_count"),
            "columns": preview_result.get("columns") or [],
            "guard_ok": (preview_result.get("sql_guard") or {}).get("ok"),
            "error": preview_result.get("error"),
        },
        "preview": {
            "sql": preview_result.get("sql"),
            "rows_first_5": _first_rows(rows),
        },
    }


class DatalogueToolAdapter(ToolBase):
    """Datalogue 受控工具适配器基类。"""

    is_concurrency_safe = False
    is_read_only = True

    def __init__(
        self,
        *,
        base_url: str,
        trace: DatalogueToolTrace,
        manifest: CapabilityManifest,
        timeout_seconds: float = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.trace = trace
        self.manifest = manifest
        self.timeout_seconds = timeout_seconds

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        if self.name not in self.manifest.allowed_tools:
            return PermissionDecision(
                behavior=PermissionBehavior.DENY,
                message=f"{self.name} is not allowed by capability_manifest.",
            )
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Allowed by DatasetAgent capability_manifest.",
        )

    def _record_event(self, phase: str, payload: dict[str, Any]) -> None:
        event = {
            "tool": self.name,
            "phase": phase,
            "payload": payload,
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        self.trace.tool_events.append(event)
        _log_react_event(
            self.trace,
            {
                "event": "tool_observation",
                "tool": self.name,
                "phase": phase,
                "payload": payload,
            },
        )

    async def _get_json(self, client: httpx.AsyncClient, path: str) -> Any:
        self.trace.called_paths.append(path)  # 真实请求路径用于证明没有进入 chat/conversation 主链路。
        logger.info("[AgentScope Hermes MVP][HTTP GET] %s", path)
        response = await client.get(path)
        response.raise_for_status()
        logger.info("[AgentScope Hermes MVP][HTTP GET OK] %s status=%s", path, response.status_code)
        return response.json()

    async def _get_optional_json(self, client: httpx.AsyncClient, path: str) -> Any:
        self.trace.called_paths.append(path)  # 可选语义资产失败时结构化返回，由 Agent 自主决定是否继续。
        logger.info("[AgentScope Hermes MVP][HTTP GET optional] %s", path)
        response = await client.get(path)
        if response.status_code >= 400:
            logger.warning(
                "[AgentScope Hermes MVP][HTTP GET optional failed] %s status=%s body=%s",
                path,
                response.status_code,
                response.text,
            )
            return {"error": response.text}
        logger.info(
            "[AgentScope Hermes MVP][HTTP GET optional OK] %s status=%s",
            path,
            response.status_code,
        )
        return response.json()

    async def _post_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        payload: dict[str, Any],
    ) -> Any:
        self.trace.called_paths.append(path)  # SQL 执行只能通过 Datalogue preview API 进入后端 Guard。
        logger.info("[AgentScope Hermes MVP][HTTP POST] %s payload=%s", path, _json_preview(payload))
        response = await client.post(path, json=payload)
        response.raise_for_status()
        logger.info("[AgentScope Hermes MVP][HTTP POST OK] %s status=%s", path, response.status_code)
        return response.json()


class RecallAssetsTool(DatalogueToolAdapter):
    """获取数据集内部真实语义资产。"""

    name = "recall_assets"
    description = "Recall live Datalogue dataset assets, selected schema, semantic assets, and Manifest summary."
    input_schema = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "用户业务问题。"},
            "dataset_id": {"type": "integer", "description": "可选数据集 ID。"},
            "schema_limit": {"type": "integer", "description": "返回字段数量上限。"},
        },
        "required": ["question"],
    }

    async def __call__(
        self,
        question: str,
        dataset_id: int | None = None,
        schema_limit: int = 80,
    ) -> ToolChunk:
        self.trace.tool_names.append(self.name)
        self._record_event(
            "start",
            {"question": question, "dataset_id": dataset_id, "schema_limit": schema_limit},
        )
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            datasets = await self._get_json(client, "/api/dataset")
            selected_dataset_id = dataset_id or int((datasets or [])[0]["id"])
            prefix = f"/api/dataset/{selected_dataset_id}"
            dataset = await self._get_json(client, prefix)
            selected_tables = await self._get_json(client, f"{prefix}/selected-tables")
            selected_columns = await self._get_json(client, f"{prefix}/selected-columns")
            metrics = await self._get_optional_json(client, f"{prefix}/metrics")
            dimensions = await self._get_optional_json(client, f"{prefix}/dimensions")
            terms = await self._get_optional_json(client, f"{prefix}/terms")
            blueprints = await self._get_optional_json(client, f"{prefix}/blueprints")
            manifest = await self._get_optional_json(client, f"{prefix}/subagent-manifest")

        payload = {
            "question": question,
            "selected_dataset_id": selected_dataset_id,
            "dataset_candidates": datasets,
            "selected_context": {
                "dataset": dataset,
                "selected_tables": selected_tables,
                "selected_columns": _compact_columns(selected_columns, schema_limit),
                "metrics": metrics,
                "dimensions": dimensions,
                "terms": terms,
                "blueprints": blueprints,
                "manifest": manifest,
            },
            "sql_generation_rules": SQL_GENERATION_RULES,
            "next_step": "Call plan_query, then generate readonly SQL and call preview_sql.",
        }
        self._record_event(
            "result",
            {
                "selected_dataset_id": selected_dataset_id,
                "dataset_count": len(datasets or []),
                "table_count": len(selected_tables or []),
                "column_count": len(selected_columns or []),
            },
        )
        logger.info(
            "[AgentScope Hermes MVP][Tool result] recall_assets selected_dataset_id=%s dataset_count=%s table_count=%s column_count=%s",
            selected_dataset_id,
            len(datasets or []),
            len(selected_tables or []),
            len(selected_columns or []),
        )
        return _json_chunk(payload)


class PlanQueryTool(RecallAssetsTool):
    """形成 DatasetAgent 内部查询计划上下文。"""

    name = "plan_query"
    description = "Prepare a dataset-scoped query plan context and SQL-generation boundary."

    async def __call__(
        self,
        question: str,
        dataset_id: int | None = None,
        schema_limit: int = 80,
    ) -> ToolChunk:
        chunk = await super().__call__(
            question=question,
            dataset_id=dataset_id,
            schema_limit=schema_limit,
        )
        self.trace.tool_events[-1]["payload"]["plan_kind"] = "dataset_agent_sql_preview_plan"
        return chunk


class GuardSqlTool(DatalogueToolAdapter):
    """只做轻量预检；最终 SQL Guard 仍以后端 preview 返回为准。"""

    name = "guard_sql"
    description = "Lightweight local SQL precheck. Backend SQL preview guard remains the source of truth."
    input_schema = {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "待预检 SQL。"},
        },
        "required": ["sql"],
    }

    async def __call__(self, sql: str) -> ToolChunk:
        self.trace.tool_names.append(self.name)
        normalized = (sql or "").strip().lower()
        blocked_keywords = ["insert", "update", "delete", "drop", "alter", "truncate", ";"]
        blocked = [keyword for keyword in blocked_keywords if keyword in normalized]
        payload = {
            "ok": normalized.startswith(("select", "with")) and not blocked,
            "blocked_keywords": blocked,
            "backend_guard_is_final": True,
            "next_step": "Call preview_sql or execute_query so Datalogue backend guard validates dataset scope.",
        }
        self._record_event("result", payload)
        logger.info("[AgentScope Hermes MVP][Tool result] guard_sql %s", payload)
        return _json_chunk(payload)


class PreviewSqlTool(DatalogueToolAdapter):
    """通过 Datalogue readonly SQL preview 执行查询并生成 MVP artifact。"""

    name = "preview_sql"
    description = "Run readonly SQL through Datalogue SQL preview and create result_ref/artifact."
    input_schema = {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "integer", "description": "数据集 ID。"},
            "sql": {"type": "string", "description": "只读 SELECT/WITH SQL。"},
            "question": {"type": "string", "description": "原始业务问题。"},
            "limit": {"type": "integer", "description": "可选预览行数。"},
        },
        "required": ["dataset_id", "sql"],
    }

    async def __call__(
        self,
        dataset_id: int,
        sql: str,
        question: str | None = None,
        limit: int | None = None,
    ) -> ToolChunk:
        self.trace.tool_names.append(self.name)
        payload: dict[str, Any] = {"sql": sql}
        if question:
            payload["question"] = question
        if limit is not None:
            payload["limit"] = limit

        self._record_event("start", {"dataset_id": dataset_id, "sql": sql, "question": question})
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            preview_result = await self._post_json(
                client,
                f"/api/dataset/{dataset_id}/sql/preview",
                payload,
            )

        result_ref = _make_result_ref(preview_result)
        artifact = _artifact_from_preview(
            question=question,
            preview_result=preview_result,
            result_ref=result_ref,
        )
        self.trace.preview_result = preview_result  # 测试只信后端 preview 结构化结果，不从模型文本里猜数字。
        self.trace.result_ref = result_ref
        self.trace.artifact = artifact
        result_payload = {
            "result_ref": result_ref,
            "summary": artifact["summary"],
            "sql_guard": preview_result.get("sql_guard"),
            "artifact": artifact,
            "tool_trace": self.trace.tool_events,
            "next_step": "Use summarize_result or final answer to explain the preview result.",
        }
        self._record_event(
            "result",
            {
                "result_ref": result_ref,
                "guard_ok": (preview_result.get("sql_guard") or {}).get("ok"),
                "columns": preview_result.get("columns") or [],
                "row_count": preview_result.get("row_count"),
            },
        )
        logger.info(
            "[AgentScope Hermes MVP][Tool result] preview_sql result_ref=%s guard_ok=%s columns=%s row_count=%s rows=%s",
            result_ref,
            (preview_result.get("sql_guard") or {}).get("ok"),
            preview_result.get("columns"),
            preview_result.get("row_count"),
            _json_preview(_first_rows(preview_result.get("rows") or [])),
        )
        return _json_chunk(result_payload)


class ExecuteQueryTool(PreviewSqlTool):
    """兼容 DatasetAgent 内部 execute_query 语义，实际仍走 preview_sql。"""

    name = "execute_query"
    description = "Execute a dataset query through the same guarded readonly SQL preview path."


class PersistArtifactTool(DatalogueToolAdapter):
    """MVP 中只生成内存 artifact，生产化时再落 query_artifact。"""

    name = "persist_artifact"
    description = "Return the latest MVP artifact. This test does not write query_artifact DB rows."
    input_schema = {
        "type": "object",
        "properties": {
            "result_ref": {"type": "string", "description": "preview_sql 返回的 result_ref。"},
        },
    }

    async def __call__(self, result_ref: str | None = None) -> ToolChunk:
        self.trace.tool_names.append(self.name)
        if not self.trace.artifact:
            payload = {"error": "No artifact exists. Call preview_sql first."}
        else:
            payload = {
                "result_ref": result_ref or self.trace.result_ref,
                "artifact": self.trace.artifact,
                "persisted": False,
                "production_truth_source": "query_artifact",
            }
        self._record_event("result", payload)
        logger.info("[AgentScope Hermes MVP][Tool result] persist_artifact %s", _json_preview(payload))
        return _json_chunk(payload)


class SummarizeResultTool(DatalogueToolAdapter):
    """给 Agent 返回可总结的 artifact 摘要。"""

    name = "summarize_result"
    description = "Summarize latest SQL preview artifact without exposing new platform capabilities."
    input_schema = {
        "type": "object",
        "properties": {
            "result_ref": {"type": "string", "description": "preview_sql 返回的 result_ref。"},
        },
    }

    async def __call__(self, result_ref: str | None = None) -> ToolChunk:
        self.trace.tool_names.append(self.name)
        if not self.trace.artifact:
            payload = {"error": "No result to summarize. Call preview_sql first."}
        else:
            payload = {
                "result_ref": result_ref or self.trace.result_ref,
                "summary": self.trace.artifact["summary"],
                "rows_first_5": self.trace.artifact["preview"]["rows_first_5"],
            }
        self._record_event("result", payload)
        logger.info("[AgentScope Hermes MVP][Tool result] summarize_result %s", _json_preview(payload))
        return _json_chunk(payload)


TOOL_REGISTRY: dict[str, type[DatalogueToolAdapter]] = {
    "recall_assets": RecallAssetsTool,
    "plan_query": PlanQueryTool,
    "guard_sql": GuardSqlTool,
    "preview_sql": PreviewSqlTool,
    "execute_query": ExecuteQueryTool,
    "persist_artifact": PersistArtifactTool,
    "summarize_result": SummarizeResultTool,
}


def build_dataset_agent_tools(
    *,
    base_url: str,
    trace: DatalogueToolTrace,
    manifest: CapabilityManifest,
) -> list[DatalogueToolAdapter]:
    tools: list[DatalogueToolAdapter] = []
    for tool_name in manifest.allowed_tools:
        tool_cls = TOOL_REGISTRY.get(tool_name)
        if not tool_cls:
            raise ValueError(f"Unknown DatasetAgent tool in capability_manifest: {tool_name}")
        tools.append(tool_cls(base_url=base_url, trace=trace, manifest=manifest))
    return tools


class TracedAgentScopeOpenAIChatModel(OpenAIChatModel):
    """AgentScope 原生 OpenAI-compatible ChatModel，额外记录 MVP ReAct 调用轨迹。"""

    def __init__(
        self,
        *,
        resolved_config: Any,
        trace: DatalogueToolTrace | None = None,
        context_size: int = 32768,
    ) -> None:
        self.resolved_config = resolved_config
        self.trace = trace
        self.react_turn = 0
        super().__init__(
            credential=OpenAICredential(
                api_key=resolved_config.api_key,
                base_url=resolved_config.base_url,
            ),
            model=resolved_config.model,
            parameters=OpenAIChatModel.Parameters(
                temperature=0,
                parallel_tool_calls=False,
            ),
            stream=False,
            max_retries=2,
            retry_delay=2,
            context_size=context_size,
        )

    @classmethod
    def _get_retryable_exceptions(cls) -> tuple[type[Exception], ...]:
        return (
            TimeoutError,
            httpx.TimeoutException,
            httpx.TransportError,
        )

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict] | None = None,
        tool_choice: Any | None = None,
        **generate_kwargs: Any,
    ) -> ChatResponse:
        formatted_messages = await self.formatter.format(messages)
        fmt_tools, fmt_tool_choice = OpenAIChatModel._format_tools(self, tools, tool_choice)
        self.react_turn += 1
        turn = self.react_turn
        request_event: dict[str, Any] = {
            "event": "llm_request",
            "turn": turn,
            "model": model_name,
            "message_count": len(formatted_messages),
            "tools": [tool.get("function", {}).get("name") for tool in fmt_tools or []],
            "tool_choice": fmt_tool_choice,
        }
        if self.trace is not None and self.trace.react_events:
            request_event["previous_event_count"] = len(self.trace.react_events)
        if os.getenv("AGENTSCOPE_MVP_LOG_REACT_MESSAGES") == "1":
            request_event["message_tail"] = _trace_messages(formatted_messages)
        _log_react_event(self.trace, request_event)
        logger.info(
            "[AgentScope Hermes MVP][LLM request] model=%s message_count=%s tools=%s tool_choice=%s",
            model_name,
            len(formatted_messages),
            [tool.get("function", {}).get("name") for tool in fmt_tools or []],
            fmt_tool_choice,
        )
        start = datetime.now()
        response = await super()._call_api(
            model_name,
            messages,
            tools=tools,
            tool_choice=tool_choice,
            **generate_kwargs,
        )
        response_blocks = _trace_content_blocks(response.content)
        _log_react_event(
            self.trace,
            {
                "event": "llm_response",
                "turn": turn,
                "response_id": response.id,
                "blocks": response_blocks,
                "usage": response.usage,
                "latency_seconds": (datetime.now() - start).total_seconds(),
            },
        )
        for block in response_blocks:
            if block["type"] == "assistant_visible_text":
                logger.info(
                    "[AgentScope Hermes MVP][ReAct assistant text][turn=%s]\n%s",
                    turn,
                    block["text"],
                )
            if block["type"] == "tool_call":
                logger.info(
                    "[AgentScope Hermes MVP][ReAct action][turn=%s] tool=%s input=%s",
                    turn,
                    block["name"],
                    _json_preview(block["input"], limit=2000),
                )
        logger.info(
            "[AgentScope Hermes MVP][LLM response] id=%s block_types=%s usage=%s",
            response.id,
            [type(block).__name__ for block in response.content],
            response.usage,
        )
        return response


def _build_agentscope_model(trace: DatalogueToolTrace | None = None) -> TracedAgentScopeOpenAIChatModel:
    settings = get_settings()
    with SessionLocal() as db:
        resolved = resolve_llm_config(settings, role="lead_agent", db=db)
    if not resolved.api_key:
        raise RuntimeError("当前 Datalogue LLM 配置没有可用 API key，无法运行 AgentScope ReAct MVP")
    logger.info(
        "[AgentScope Hermes MVP][LLM config] source=%s provider=%s model=%s base_url=%s timeout=%s",
        getattr(resolved, "source", None),
        getattr(resolved, "provider", None),
        getattr(resolved, "model", None),
        getattr(resolved, "base_url", None),
        getattr(resolved, "request_timeout_seconds", None),
    )
    return TracedAgentScopeOpenAIChatModel(resolved_config=resolved, trace=trace)


async def run_datalogue_react_mvp(
    *,
    question: str,
    dataset_id: int | None,
    base_url: str,
    capability_manifest: CapabilityManifest | None = None,
) -> DatalogueReactMvpResult:
    manifest = capability_manifest or default_capability_manifest()
    trace = DatalogueToolTrace()
    hermes_prompt = load_hermes_skill_prompt()
    system_prompt = build_dataset_agent_system_prompt(
        hermes_prompt=hermes_prompt,
        manifest=manifest,
    )
    tools = build_dataset_agent_tools(base_url=base_url, trace=trace, manifest=manifest)
    registered_tools = [tool.name for tool in tools]
    logger.info(
        "[AgentScope Hermes MVP][Run start] base_url=%s dataset_id=%s question=%s registered_tools=%s",
        base_url,
        dataset_id,
        question,
        registered_tools,
    )
    agent = Agent(
        name=manifest.agent_name,
        system_prompt=system_prompt,
        model=_build_agentscope_model(trace),
        toolkit=Toolkit(tools=tools),
        model_config=ModelConfig(max_retries=2),
    )
    dataset_hint = f"已知 dataset_id={dataset_id}。" if dataset_id is not None else "dataset_id 未指定，请自主选择合适数据集。"
    user_msg = UserMsg(
        name="user",
        content=(
            f"{question}\n"
            f"{dataset_hint}\n"
            "请按 Hermes-style DatasetAgent 流程自主调用工具：先获取/规划资产，再通过 preview_sql 或 execute_query 返回 result_ref 和最终回答。"
        ),
    )
    reply = await agent.reply(user_msg)  # 由 AgentScope ReAct 循环自主选择受控工具。
    result = DatalogueReactMvpResult(
        final_text=_text_from_reply(reply),
        tool_names=trace.tool_names,
        called_paths=trace.called_paths,
        preview_result=trace.preview_result,
        result_ref=trace.result_ref,
        artifact=trace.artifact,
        tool_trace=trace.tool_events,
        react_trace=trace.react_events,
        registered_tools=registered_tools,
        capability_manifest=asdict(manifest),
        system_prompt=system_prompt,
        prompt_sources=hermes_prompt.source_paths,
    )
    logger.info(
        "[AgentScope Hermes MVP][Run result] tools=%s called_paths=%s result_ref=%s artifact=%s final_text=%s",
        result.tool_names,
        result.called_paths,
        result.result_ref,
        _json_preview(result.artifact),
        result.final_text,
    )
    return result
