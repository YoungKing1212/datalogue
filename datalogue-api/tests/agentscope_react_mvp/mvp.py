# ============================================================
# File Name   : mvp.py
# Description:
#   AgentScope 2.0 ReAct MVP 的真实服务调用实现。
#
# Responsibilities:
#   - 构建 AgentScope Agent，并挂载 Datalogue 只读工具集。
#   - 从 Datalogue 现有 LLM 配置解析模型连接，避免重复维护一套密钥。
#   - 记录工具调用路径和 SQL preview 结果，供真实集成测试验证自主调用行为。
#
# Author      : yangkai
# Created On  : 2026-06-25
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import Any, Type

import httpx
import litellm

from agentscope.agent import Agent
from agentscope.credential import OpenAICredential
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg, TextBlock, ToolCallBlock, UserMsg
from agentscope.model import ChatResponse, OpenAIChatModel
from agentscope.model._base import ChatModelBase
from agentscope.model._model_usage import ChatUsage
from agentscope.permission import PermissionBehavior, PermissionContext, PermissionDecision
from agentscope.tool import ToolBase, ToolChunk, Toolkit

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.llm_config import resolve_llm_config
from app.graph.llm import _litellm_model_name


SQL_GENERATION_RULES = [
    "只能基于 selected_tables / selected_columns 中出现的表和字段生成 SQL。",
    "只允许 SELECT 或 WITH 查询，不允许 INSERT / UPDATE / DELETE / DROP / DDL。",
    "生成 SQL 后必须调用 DatalogueExecuteSqlTool，不要直连数据库。",
    "不要调用 /api/chat/stream，也不要调用 /api/conversation。",
]


@dataclass
class DatalogueToolTrace:
    """记录 AgentScope Agent 实际调用过哪些数语能力。"""

    tool_names: list[str] = field(default_factory=list)
    called_paths: list[str] = field(default_factory=list)
    preview_result: dict[str, Any] | None = None


@dataclass
class DatalogueReactMvpResult:
    """真实 ReAct MVP 的测试可断言结果。"""

    final_text: str
    tool_names: list[str]
    called_paths: list[str]
    preview_result: dict[str, Any] | None


def _json_chunk(payload: dict[str, Any]) -> ToolChunk:
    return ToolChunk(content=[TextBlock(text=json.dumps(payload, ensure_ascii=False))])


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


class _DatalogueToolBase(ToolBase):
    """Datalogue 只读工具公共基类。"""

    is_concurrency_safe = True
    is_read_only = True

    def __init__(
        self,
        *,
        base_url: str,
        trace: DatalogueToolTrace,
        timeout_seconds: float = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.trace = trace
        self.timeout_seconds = timeout_seconds

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Datalogue MVP tools only call readonly semantic APIs and SQL preview.",
        )

    async def _get_json(self, client: httpx.AsyncClient, path: str) -> Any:
        self.trace.called_paths.append(path)  # 真实请求路径用于证明没有进入完整 chat/conversation 链路。
        response = await client.get(path)
        response.raise_for_status()
        return response.json()

    async def _get_optional_json(self, client: httpx.AsyncClient, path: str) -> Any:
        self.trace.called_paths.append(path)  # 可选语义资产失败时返回结构化错误，不中断 Agent 自主决策。
        response = await client.get(path)
        if response.status_code >= 400:
            return {"error": response.text}
        return response.json()

    async def _post_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        payload: dict[str, Any],
    ) -> Any:
        self.trace.called_paths.append(path)  # SQL 只能通过 preview API 进入后端 Guard。
        response = await client.post(path, json=payload)
        response.raise_for_status()
        return response.json()


class DataloguePlanQueryTool(_DatalogueToolBase):
    """准备 Hermes plan-query 等价的最小语义上下文。"""

    name = "DataloguePlanQueryTool"
    description = (
        "Prepare dataset-scoped Datalogue semantic context before generating readonly SQL. "
        "Call this before DatalogueExecuteSqlTool."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "用户业务问题。"},
            "dataset_id": {"type": "integer", "description": "已知数据集 ID。"},
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
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            datasets = await self._get_json(client, "/api/dataset")
            selected_dataset_id = dataset_id
            if selected_dataset_id is None:
                selected_dataset_id = int((datasets or [])[0]["id"])

            prefix = f"/api/dataset/{selected_dataset_id}"
            dataset = await self._get_json(client, prefix)
            selected_tables = await self._get_json(client, f"{prefix}/selected-tables")
            selected_columns = await self._get_json(client, f"{prefix}/selected-columns")
            metrics = await self._get_optional_json(client, f"{prefix}/metrics")
            dimensions = await self._get_optional_json(client, f"{prefix}/dimensions")
            terms = await self._get_optional_json(client, f"{prefix}/terms")
            blueprints = await self._get_optional_json(client, f"{prefix}/blueprints")
            manifest = await self._get_optional_json(client, f"{prefix}/subagent-manifest")

        # 返回足够小的上下文，避免 ReAct Agent 被 100+ 字段淹没；业务边界仍来自真实 API。
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
            "next_step": "Generate SELECT/WITH SQL from selected_context, then call DatalogueExecuteSqlTool.",
        }
        return _json_chunk(payload)


class DatalogueExecuteSqlTool(_DatalogueToolBase):
    """通过 Datalogue readonly SQL preview 执行查询。"""

    name = "DatalogueExecuteSqlTool"
    description = "Execute readonly SELECT/WITH SQL through Datalogue dataset SQL preview API."
    input_schema = {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "integer", "description": "数据集 ID。"},
            "sql": {"type": "string", "description": "只读 SQL。"},
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

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            result = await self._post_json(client, f"/api/dataset/{dataset_id}/sql/preview", payload)

        self.trace.preview_result = result  # 测试只信后端 preview 结构化结果，不从模型文本里猜数字。
        return _json_chunk(result)


class LiteLLMAgentScopeChatModel(ChatModelBase):
    """AgentScope ChatModel 适配器：ReAct 仍由 AgentScope 驱动，底层复用数语 LiteLLM。"""

    def __init__(
        self,
        *,
        resolved_config: Any,
        context_size: int = 32768,
    ) -> None:
        self.resolved_config = resolved_config
        self.formatter = OpenAIChatFormatter()
        super().__init__(
            credential=OpenAICredential(
                api_key=resolved_config.api_key,
                base_url=resolved_config.base_url,
            ),
            model=_litellm_model_name(resolved_config),
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
    def _get_retryable_exceptions(cls) -> tuple[Type[Exception], ...]:
        return (
            TimeoutError,
            httpx.TimeoutException,
            httpx.TransportError,
            litellm.exceptions.APIConnectionError,
            litellm.exceptions.Timeout,
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
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": formatted_messages,
            "temperature": 0,
            "stream": False,
            "timeout": self.resolved_config.request_timeout_seconds,
            "api_key": self.resolved_config.api_key,
            "api_base": self.resolved_config.base_url,
        }
        if fmt_tools:
            kwargs["tools"] = fmt_tools
            kwargs["parallel_tool_calls"] = False
        if fmt_tool_choice is not None:
            kwargs["tool_choice"] = fmt_tool_choice
        kwargs.update(generate_kwargs)

        start = datetime.now()
        response = await litellm.acompletion(**kwargs)
        return self._parse_litellm_response(start, response)

    def _parse_litellm_response(self, start: datetime, response: Any) -> ChatResponse:
        content_blocks: list[Any] = []
        choices = getattr(response, "choices", None) or []
        if choices:
            message = choices[0].message
            text = getattr(message, "content", None)
            if text:
                content_blocks.append(TextBlock(text=text))
            for tool_call in getattr(message, "tool_calls", None) or []:
                content_blocks.append(
                    ToolCallBlock(
                        id=tool_call.id,
                        name=tool_call.function.name,
                        input=tool_call.function.arguments,
                    )
                )

        usage = None
        raw_usage = getattr(response, "usage", None)
        if raw_usage:
            usage = ChatUsage(
                input_tokens=getattr(raw_usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(raw_usage, "completion_tokens", 0) or 0,
                time=(datetime.now() - start).total_seconds(),
            )
        return ChatResponse(
            content=content_blocks,
            is_last=True,
            usage=usage,
            id=getattr(response, "id", None) or "litellm-agentscope-response",
        )


def _build_agentscope_model() -> LiteLLMAgentScopeChatModel:
    settings = get_settings()
    with SessionLocal() as db:
        resolved = resolve_llm_config(settings, role="lead_agent", db=db)
    if not resolved.api_key:
        raise RuntimeError("当前 Datalogue LLM 配置没有可用 API key，无法运行 AgentScope ReAct MVP")
    return LiteLLMAgentScopeChatModel(resolved_config=resolved)


async def run_datalogue_react_mvp(
    *,
    question: str,
    dataset_id: int,
    base_url: str,
) -> DatalogueReactMvpResult:
    trace = DatalogueToolTrace()
    toolkit = Toolkit(
        tools=[
            DataloguePlanQueryTool(base_url=base_url, trace=trace),
            DatalogueExecuteSqlTool(base_url=base_url, trace=trace),
        ]
    )
    agent = Agent(
        name="DatalogueReActMVP",
        system_prompt=(
            "你是数语 Datalogue 的轻量问数 Agent。你必须像 Hermes skill 一样自主选择工具："
            "先调用 DataloguePlanQueryTool 获取真实语义资产和 schema，再基于返回内容生成 SQL，"
            "然后调用 DatalogueExecuteSqlTool 执行。禁止调用 /api/chat/stream，禁止直连数据库，"
            "禁止编造未出现在 selected_context 中的表或字段。最终用中文总结 preview 返回的结果。"
        ),
        model=_build_agentscope_model(),
        toolkit=toolkit,
    )
    user_msg = UserMsg(
        name="user",
        content=(
            f"{question}\n"
            f"已知 dataset_id={dataset_id}。请不要直接回答，必须先调用规划工具，再调用 SQL preview 工具。"
        ),
    )
    try:
        reply = await agent.reply(user_msg)  # 由 AgentScope 自主 ReAct 决策工具调用顺序，而不是测试手动编排。
        return DatalogueReactMvpResult(
            final_text=_text_from_reply(reply),
            tool_names=trace.tool_names,
            called_paths=trace.called_paths,
            preview_result=trace.preview_result,
        )
    finally:
        await litellm.close_litellm_async_clients()  # 真实 LLM 请求结束后关闭异步连接，避免 pytest teardown 留 pending task。
