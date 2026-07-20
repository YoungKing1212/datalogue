# ============================================================
# File Name   : worker_logging.py
# Description:
#   AgentScope BI worker 的前端进度中间件。
#
# Responsibilities:
#   - 通过 AgentScope extra_agent_middlewares 只为 Datalogue BI worker 挂载进度中间件。
#   - 发布 Workbench/Chat 可消费的安全进度事件。
#   - 在 DEBUG raw 开关开启时，基于完整 Msg 打印 Leader/BI worker 的 thinking/text 与工具入出参。
#   - 模型调用完整观测交给 AgentScope TracingMiddleware / OpenTelemetry。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
import json
import logging
import os
import re
from typing import Any

from agentscope.app.storage import StorageBase
from agentscope.message import AssistantMsg, Msg
from agentscope.middleware import MiddlewareBase, TracingMiddleware
from opentelemetry import trace as otel_trace

from app.domains.bi.worker.timeline_cache import store_bi_worker_timeline
from app.domains.agent_team.progress_bridge import publish_agent_progress
from app.domains.agent_team.task_context import resolve_task_context
from app.domains.agent_team.worker_identity import resolve_team_worker_type
from app.core.middlewares.lifecycle import raw_agent_logs_enabled

AgentMiddlewareFactory = Callable[
    [str | None, str | None, str | None], Awaitable[list[MiddlewareBase]]
]
_LEADER_MARKERS = ("Datalogue Agent Team Leader", "Agent Team Leader", "智能问数主链")
logger = logging.getLogger(__name__)
_SENSITIVE_TEXT_PATTERN = re.compile(
    r"\b(select|insert|update|delete|from|join|where|group\s+by|order\s+by|having|union|with)\b"
    r"|[`;]|raw_rows?|schema|query_plan|hidden|secret|password|credential|api_key|dsl",
    re.IGNORECASE,
)
_SAFE_TOOL_RESULT_KEYS = {
    "status",
    "dataset_id",
    "display_summary",
    "error_summary",
    "summary",
    "message",
    "result_ref",
    "report_ref",
    "artifact_ref",
    "row_count",
    "column_count",
}
_PROGRESSIVE_TOOL_SUMMARIES = {
    "datalogue_prepare_query_context": "BI Worker 正在准备查询上下文。",
    "datalogue_request_schema_slice": "BI Worker 正在申请相关数据结构切片。",
    "datalogue_execute_query_plan_bundle": "BI Worker 正在校验并执行受控查询计划。",
    "datalogue_repair_query_plan": "BI Worker 正在生成查询修复建议。",
}
_RAW_THINKING_TRUE_VALUES = {"1", "true", "yes", "on", "debug"}
_PHOENIX_SESSION_IO_TEXT_LIMIT = 1000


def build_datalogue_extra_agent_middlewares(
    *, storage: StorageBase | None = None
) -> AgentMiddlewareFactory:
    """构建 AgentScope create_app(extra_agent_middlewares=...) 使用的中间件工厂。"""

    async def _extra_agent_middlewares(
        user_id: str | None,
        agent_id: str | None,
        session_id: str | None,
    ) -> list[MiddlewareBase]:
        worker_context = await _bi_worker_context(
            storage=storage,
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
        )
        leader_context = None
        if worker_context is None:
            leader_context = await _leader_context(
                storage=storage,
                user_id=user_id,
                agent_id=agent_id,
                session_id=session_id,
            )
        # TracingMiddleware 必须位于最外层，Phoenix 兼容层才能把标准 I/O 属性写入根 Agent Span。
        # BIWorkerProgressMiddleware 只记录 thinking 路径摘要、工具结果摘要与用户可见进度，不接管原始模型 I/O 日志。
        agent_role = (
            "bi_worker" if worker_context is not None else "leader" if leader_context else "agent"
        )
        middlewares: list[MiddlewareBase] = [
            TracingMiddleware(),
            PhoenixSessionIOMiddleware(agent_role=agent_role),
        ]
        if worker_context is not None:
            middlewares.append(
                BIWorkerProgressMiddleware(worker_context=worker_context, storage=storage)
            )
        elif leader_context is not None:
            middlewares.append(LeaderRawDebugMiddleware())
        return middlewares

    return _extra_agent_middlewares


class PhoenixSessionIOMiddleware(MiddlewareBase):
    """为 Phoenix Session 根 Span 补充 OpenInference 标准输入输出属性。

    AgentScope 2.0.3 原生中间件记录 ``gen_ai.*.messages``，而 Phoenix Session
    摘要只读取根 Span 的 ``input.value`` / ``output.value``。本中间件位于原生
    TracingMiddleware 内层，只提取最终文本块并执行敏感内容过滤与长度限制。
    """

    def __init__(self, *, agent_role: str = "agent") -> None:
        self.agent_role = agent_role

    async def on_reply(
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        """在一次 reply 的根 Span 上写入 Phoenix 可识别的安全文本。"""

        input_text = _phoenix_message_text(input_kwargs.get("inputs"))
        _set_phoenix_session_io_attribute(
            name="input",
            value=input_text or _phoenix_fallback_text(self.agent_role, direction="input"),
        )

        last_msg: Msg | None = None
        try:
            async for event_or_msg in next_handler(**input_kwargs):
                if isinstance(event_or_msg, Msg):
                    last_msg = event_or_msg
                yield event_or_msg
        except BaseException:
            # 异常状态由外层 TracingMiddleware 记录；失败回复不能伪装成正常 output。
            raise
        else:
            output_text = _phoenix_message_text(last_msg)
            _set_phoenix_session_io_attribute(
                name="output",
                value=output_text or _phoenix_fallback_text(self.agent_role, direction="output"),
            )


class LeaderRawDebugMiddleware(MiddlewareBase):
    """AgentScope Middleware：仅在 raw debug 开启时记录 Leader 原始 reply timeline。"""

    async def on_reply(
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        """透传 Leader reply 事件，并在本地 DEBUG 开关开启时输出原始思考链。"""

        agent_name = (
            _safe_context_text(_safe_getattr(agent, "name")) or "Datalogue Agent Team Leader"
        )
        reply_msg = None
        async for event in next_handler(**input_kwargs):
            reply_msg = _append_event_to_reply_msg(reply_msg, event, agent_name=agent_name)
            yield event
        _log_raw_debug_blocks_if_enabled(msg=reply_msg, log_name="agentscope.leader.raw_debug")


class BIWorkerProgressMiddleware(MiddlewareBase):
    """AgentScope Middleware：发布 BI worker 安全进度，并提取受控的 reply 结果日志。"""

    def __init__(
        self,
        *,
        worker_context: dict[str, str | None],
        storage: StorageBase | None = None,
    ) -> None:
        self.worker_context = worker_context
        self.storage = storage

    async def on_reply(
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        """发布 worker 一次 reply 的开始、工具调用和结束进度。"""

        _log_worker_lifecycle(
            worker_context=self.worker_context,
            status="running",
            summary="BI Worker reply started",
        )
        _publish_worker_progress(
            worker_context=self.worker_context,
            phase="reply",
            status="running",
            title="BI Worker 开始处理",
            summary="BI Worker 已开始处理任务。",
        )
        agent_name = _safe_context_text(_safe_getattr(agent, "name")) or "BI Worker"
        reply_msg = None
        thinking_state: dict[str, Any] = {}
        try:
            async for event in next_handler(**input_kwargs):
                reply_msg = _append_event_to_reply_msg(reply_msg, event, agent_name=agent_name)
                _publish_thinking_progress(
                    worker_context=self.worker_context,
                    event=event,
                    state=thinking_state,
                )
                _publish_tool_progress(worker_context=self.worker_context, event=event)
                yield event
        except Exception:
            _log_worker_lifecycle(
                worker_context=self.worker_context,
                status="failed",
                summary="BI Worker reply failed",
            )
            _publish_worker_progress(
                worker_context=self.worker_context,
                phase="reply",
                status="failed",
                title="BI Worker 处理失败",
                summary="BI Worker 处理过程中发生错误，内部细节已隐藏。",
            )
            raise
        # 主循环走完时 flush 所有残留的 raw delta 缓冲，防止 ThinkingBlockEndEvent 缺失导致尾段被吞。
        _flush_all_thinking_raw_buffers(
            worker_context=self.worker_context,
            state=thinking_state,
        )
        _log_raw_debug_blocks_if_enabled(msg=reply_msg, log_name="agentscope.bi_worker.raw_debug")
        await _cache_bi_worker_timeline_if_enabled(
            storage=self.storage,
            worker_context=self.worker_context,
            msg=reply_msg,
        )
        _log_reply_content_blocks(worker_context=self.worker_context, msg=reply_msg)
        _log_worker_lifecycle(
            worker_context=self.worker_context,
            status="completed",
            summary="BI Worker reply completed",
        )
        _publish_worker_progress(
            worker_context=self.worker_context,
            phase="reply",
            status="completed",
            title="BI Worker 完成处理",
            summary="BI Worker 已完成本轮处理。",
        )


async def _bi_worker_context(
    *,
    storage: StorageBase | None,
    user_id: str | None,
    agent_id: str | None,
    session_id: str | None,
) -> dict[str, str | None] | None:
    """从 AgentScope storage 判断当前 agent 是否是 Datalogue BI worker。"""

    if storage is None or not user_id or not agent_id:
        return None
    worker_type = await resolve_team_worker_type(
        storage=storage, user_id=user_id, agent_id=agent_id
    )
    if worker_type != "bi":
        return None
    agent_record = await storage.get_agent(user_id, agent_id)
    if not agent_record or agent_record.source != "team":
        return None
    agent_data = getattr(agent_record, "data", None)
    agent_name = getattr(agent_data, "name", None)

    # 从 Redis 解析 task context（通过直接命中或 TeamRecord 反查 leader session）。
    task_ctx = await resolve_task_context(
        storage=storage,
        user_id=user_id,
        agent_id=agent_id,
        session_id=session_id,
    )

    return {
        "user_id": user_id,
        "agent_id": agent_id,
        "agent_name": str(agent_name) if agent_name else None,
        "session_id": session_id,
        "task_id": task_ctx.get("task_id"),
        "thread_id": task_ctx.get("thread_id"),
        "message_id": task_ctx.get("message_id"),
        "trace_id": task_ctx.get("trace_id"),
        "leader_session_id": task_ctx.get("leader_session_id"),
    }


async def _leader_context(
    *,
    storage: StorageBase | None,
    user_id: str | None,
    agent_id: str | None,
    session_id: str | None,
) -> dict[str, str | None] | None:
    """识别 Datalogue Agent Team Leader；只用于挂 raw debug 中间件。"""

    del session_id
    if storage is None or not user_id or not agent_id:
        return None
    agent_record = await storage.get_agent(user_id, agent_id)
    if not agent_record:
        return None
    agent_data = getattr(agent_record, "data", None)
    system_prompt = str(getattr(agent_data, "system_prompt", "") or "")
    agent_name = str(getattr(agent_data, "name", "") or "")
    marker_text = f"{agent_name}\n{system_prompt}"
    if not any(marker in marker_text for marker in _LEADER_MARKERS):
        return None
    return {
        "user_id": user_id,
        "agent_id": agent_id,
        "agent_name": agent_name or None,
    }


def _event_summary(event: Any) -> dict[str, Any]:
    raw_type = _safe_getattr(event, "type")
    event_type = str(raw_type or event.__class__.__name__)
    summary: dict[str, Any] = {
        "event_type": event_type,
        "category": _event_category(event_type),
        "phase": _event_phase(event_type),
        "reply_id": _safe_getattr(event, "reply_id"),
        "block_id": _safe_getattr(event, "block_id"),
        "tool_call_id": _safe_getattr(event, "tool_call_id"),
        "tool_call_name": _safe_getattr(event, "tool_call_name"),
        "model_name": _safe_getattr(event, "model_name"),
        "state": _safe_getattr(event, "state"),
        "is_last": _safe_getattr(event, "is_last"),
        "input_tokens": _safe_getattr(event, "input_tokens"),
        "output_tokens": _safe_getattr(event, "output_tokens"),
    }
    delta = _safe_getattr(event, "delta")
    if delta is not None:
        # ThinkingBlockDelta / ToolCallDelta 只记录长度和类型，不把原始思维链或工具参数打进日志。
        summary["delta_type"] = type(delta).__name__
        summary["delta_length"] = len(str(delta))
    content = _safe_getattr(event, "content")
    if content is not None:
        summary["content_type"] = type(content).__name__
        summary["content_length"] = len(str(content))
    pending_tool_calls = _pending_tool_calls(event)
    if pending_tool_calls:
        summary["pending_tool_calls"] = pending_tool_calls
        summary["pending_tool_names"] = [
            item["name"] for item in pending_tool_calls if item.get("name")
        ]
    return {key: value for key, value in summary.items() if value is not None}


def _log_worker_lifecycle(
    *,
    worker_context: dict[str, str | None],
    status: str,
    summary: str,
) -> None:
    """记录 reply 级生命周期；只包含关联 ID，不包含用户输入和模型原文。"""

    payload = {
        "agent_role": "worker",
        "status": status,
        "summary": summary,
        **_worker_context_log_fields(worker_context),
    }
    logger.info("[agentscope.bi_worker.event] %s", _json_log(payload))


def _log_raw_debug_blocks_if_enabled(*, msg: Any, log_name: str) -> None:
    """显式开启 raw debug 时，在 reply 拼接完成后用 DEBUG 打印原始调试内容。"""

    if msg is None or not raw_agent_logs_enabled():
        return
    timeline = _raw_debug_blocks_from_msg(msg)
    if not timeline:
        return
    logger.info("[%s] %s", log_name, _json_raw_log({"timeline": timeline}))


async def _cache_bi_worker_timeline_if_enabled(
    *,
    storage: StorageBase | None,
    worker_context: dict[str, str | None],
    msg: Any,
) -> None:
    """TODO(后期删除): raw debug 开启时把 BI worker reply 的原始 timeline 暂存 Redis，供跨进程调试排查。

    后期由 AgentScope TracingMiddleware / OpenTelemetry 统一观测取代，届时删除本函数与
    bi_worker_timeline_cache 模块。
    """
    if storage is None or msg is None or not raw_agent_logs_enabled():
        return
    timeline = _raw_debug_blocks_from_msg(msg)
    if not timeline:
        return
    worker_session_id = _safe_context_text(worker_context.get("session_id"))
    reply_id = _safe_context_text(_safe_getattr(msg, "id"))
    if not worker_session_id or not reply_id:
        return
    await store_bi_worker_timeline(
        storage,
        worker_session_id=worker_session_id,
        reply_id=reply_id,
        timeline=timeline,
    )


def _raw_debug_blocks_from_msg(msg: Any) -> list[dict[str, Any]]:
    """按 msg.content 原始顺序输出所有内容块，还原 ReAct 思考→调工具→结果的先后顺序。"""
    timeline: list[dict[str, Any]] = []
    content = _safe_getattr(msg, "content")
    if not isinstance(content, list):
        return timeline
    for idx, block in enumerate(content):
        block_type = str(_safe_getattr(block, "type") or "")
        entry: dict[str, Any] = {"step": idx + 1, "type": block_type}
        if block_type == "text":
            text = _raw_block_text(block, attrs=("text", "content"))
            if text:
                entry["text"] = text
        elif block_type == "thinking":
            thinking = _raw_block_text(block, attrs=("thinking", "text", "content"))
            if thinking:
                entry["thinking"] = thinking
        elif block_type == "tool_call":
            entry["tool_name"] = str(_safe_getattr(block, "name") or "")
            entry["input"] = str(_safe_getattr(block, "input") or "")
        elif block_type == "tool_result":
            entry["tool_name"] = str(_safe_getattr(block, "name") or "")
            entry["state"] = str(_safe_getattr(block, "state") or "")
            entry["output"] = _tool_result_output_text(_safe_getattr(block, "output"))
        else:
            continue
        timeline.append(entry)
    return timeline


def _append_event_to_reply_msg(msg: Any, event: Any, *, agent_name: str) -> Any:
    """使用 AgentScope Msg.append_event 重建 reply，便于后续通过 get_content_blocks 提取结果。"""

    reply_id = _safe_getattr(event, "reply_id")
    event_type = str(_safe_getattr(event, "type") or event.__class__.__name__).lower()
    if msg is None and reply_id:
        name = _safe_context_text(_safe_getattr(event, "name")) or agent_name
        msg = AssistantMsg(name=name, content=[], id=str(reply_id))
    if msg is None or "reply_start" in event_type:
        return msg
    try:
        msg.append_event(event)
    except Exception:
        # 部分测试替身或上游兼容事件不满足 AgentScope append_event 协议，不能影响主链流式输出。
        return msg
    return msg


def _log_reply_content_blocks(*, worker_context: dict[str, str | None], msg: Any) -> None:
    """从完整 Msg 中提取 thinking 路径和工具结果；只写安全摘要。"""

    if msg is None:
        return
    thinking_path = _thinking_path_from_msg(msg)
    tool_results = _tool_results_from_msg(msg)
    if not thinking_path and not tool_results:
        return
    payload = {
        "agent_role": "worker",
        **_worker_context_log_fields(worker_context),
        "reply_id": _safe_context_text(_safe_getattr(msg, "id")),
        "thinking_path": thinking_path,
        "tool_results": tool_results,
    }
    logger.info("[agentscope.bi_worker.reply_blocks] %s", _json_log(payload))


def _thinking_path_from_msg(msg: Any) -> list[dict[str, Any]]:
    """提取思考块路径摘要；不输出原始 thinking 内容，避免把隐藏推理链写入普通日志。"""

    blocks = _safe_content_blocks(msg, "thinking")
    path: list[dict[str, Any]] = []
    for index, block in enumerate(blocks[:20], start=1):
        thinking = _safe_getattr(block, "thinking", "") or ""
        path.append(
            {
                "index": index,
                "block_id": _safe_context_text(_safe_getattr(block, "id")),
                "content_length": len(str(thinking)),
            }
        )
    return path


def _tool_results_from_msg(msg: Any) -> list[dict[str, Any]]:
    """提取工具结果块，只保留 result_ref/artifact_card/行列数等安全业务结果。"""

    results: list[dict[str, Any]] = []
    for block in _safe_content_blocks(msg, "tool_result")[:20]:
        output_text = _tool_result_output_text(_safe_getattr(block, "output"))
        result = {
            "tool_call_id": _safe_context_text(_safe_getattr(block, "id")),
            "tool_name": _safe_context_text(_safe_getattr(block, "name")),
            "state": _safe_context_text(_safe_getattr(block, "state")),
            "output_length": len(output_text),
            "output": _safe_tool_result_output(output_text),
        }
        results.append(
            {key: value for key, value in result.items() if value not in (None, "", [], {})}
        )
    return results


def _safe_content_blocks(msg: Any, block_type: str) -> list[Any]:
    has_blocks = _safe_getattr(msg, "has_content_blocks")
    if callable(has_blocks):
        try:
            if not has_blocks(block_type):
                return []
        except Exception:
            pass
    get_blocks = _safe_getattr(msg, "get_content_blocks")
    if not callable(get_blocks):
        return []
    try:
        blocks = get_blocks(block_type)
    except Exception:
        return []
    return blocks if isinstance(blocks, list) else []


def _phoenix_message_text(value: Any) -> str | None:
    """从 AgentScope Msg 提取普通文本块，过滤工具、思维链和敏感内部材料。"""

    messages = value if isinstance(value, list) else [value]
    chunks: list[str] = []
    for msg in messages[:20]:
        if not isinstance(msg, Msg):
            continue
        for block in _safe_content_blocks(msg, "text")[:20]:
            text = _raw_block_text(block, attrs=("text", "content"))
            if text:
                chunks.append(text)
    return _phoenix_safe_trace_text("\n".join(chunks))


def _phoenix_safe_trace_text(value: Any) -> str | None:
    """生成可离开进程进入 Phoenix 的限长文本；命中内部敏感模式时整体丢弃。"""

    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text or _SENSITIVE_TEXT_PATTERN.search(text):
        return None
    return _clip(text, limit=_PHOENIX_SESSION_IO_TEXT_LIMIT)


def _phoenix_fallback_text(agent_role: str, *, direction: str) -> str:
    """当子智能体没有直接输入或安全文本被过滤时，写入不含业务原文的真实状态。"""

    labels = {
        "bi_worker": "BI Worker",
        "leader": "智能问数主智能体",
        "agent": "智能体",
    }
    label = labels.get(agent_role, labels["agent"])
    if direction == "input":
        return f"{label}继续处理当前任务"
    return f"{label}本轮处理已完成"


def _set_phoenix_session_io_attribute(*, name: str, value: str) -> None:
    """写入当前根 Span；观测兼容失败不得影响 Agent 主链。"""

    try:
        span = otel_trace.get_current_span()
        if not span.is_recording():
            return
        span.set_attribute(f"{name}.value", value)
        span.set_attribute(f"{name}.mime_type", "text/plain")
    except Exception:
        logger.debug("Failed to set Phoenix session %s attribute.", name, exc_info=True)


def _raw_block_text(block: Any, *, attrs: tuple[str, ...]) -> str:
    for attr in attrs:
        value = _safe_getattr(block, attr)
        if value not in (None, ""):
            return str(value)
    return ""


def _tool_result_output_text(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output[:50]:
            text = _safe_getattr(item, "text")
            if text is not None:
                chunks.append(str(text))
        return "".join(chunks)
    return str(output)


def _safe_tool_result_output(output_text: str) -> dict[str, Any]:
    if not output_text:
        return {}
    try:
        parsed = json.loads(output_text)
    except (TypeError, ValueError):
        safe_text = _safe_result_text(output_text)
        return {"text": safe_text} if safe_text else {"content_type": "text"}
    if isinstance(parsed, dict):
        return _safe_tool_result_dict(parsed)
    return {
        "content_type": type(parsed).__name__,
        "item_count": len(parsed) if isinstance(parsed, list) else None,
    }


def _safe_tool_result_dict(value: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in _SAFE_TOOL_RESULT_KEYS:
        item = value.get(key)
        if item in (None, "", [], {}):
            continue
        safe[key] = _safe_result_value(item)
    artifact_card = _safe_artifact_card_for_log(value.get("artifact_card"))
    if artifact_card:
        safe["artifact_card"] = artifact_card
    return {key: value for key, value in safe.items() if value not in (None, "", [], {})}


def _safe_artifact_card_for_log(card: Any) -> dict[str, Any] | None:
    if not isinstance(card, dict):
        return None
    safe: dict[str, Any] = {
        "title": _safe_result_text(card.get("title")) or "查询结果",
    }
    for key in ("status", "summary_for_chat"):
        value = _safe_result_text(card.get(key))
        if value:
            safe[key] = value
    primary_ref = _safe_ref_for_log(card.get("primary_ref"))
    if primary_ref:
        safe["primary_ref"] = primary_ref
    related_refs = [_safe_ref_for_log(item) for item in (card.get("related_refs") or [])[:8]]
    related_refs = [item for item in related_refs if item]
    if related_refs:
        safe["related_refs"] = related_refs
    actions: list[dict[str, Any]] = []
    for action in (card.get("actions") or [])[:8]:
        if not isinstance(action, dict):
            continue
        safe_action = {
            "action_type": _safe_result_text(action.get("action_type")),
            "label": _safe_result_text(action.get("label")),
            "ref": action.get("ref") if isinstance(action.get("ref"), str) else None,
            "disabled": bool(action.get("disabled")),
            "disabled_reason": _safe_result_text(action.get("disabled_reason")),
        }
        safe_action = {
            key: value for key, value in safe_action.items() if value not in (None, "", [], {})
        }
        if safe_action:
            actions.append(safe_action)
    if actions:
        safe["actions"] = actions
    return safe


def _safe_ref_for_log(value: Any) -> str | dict[str, Any] | None:
    if isinstance(value, str):
        return _safe_result_text(value)
    if not isinstance(value, dict):
        return None
    safe = {
        "ref": _safe_result_text(value.get("ref")),
        "ref_type": _safe_result_text(value.get("ref_type")),
        "label": _safe_result_text(value.get("label")),
    }
    return {key: item for key, item in safe.items() if item} or None


def _safe_result_value(value: Any) -> Any:
    if isinstance(value, str):
        return _safe_result_text(value)
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _safe_result_value(item)
            for key, item in value.items()
            if str(key) in _SAFE_TOOL_RESULT_KEYS and item not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_safe_result_value(item) for item in value[:20]]
    return None


def _safe_result_text(value: Any, *, limit: int = 300) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or _SENSITIVE_TEXT_PATTERN.search(text):
        return None
    return _clip(text, limit=limit)


def _worker_context_log_fields(worker_context: dict[str, str | None]) -> dict[str, str]:
    fields = {
        "agent_name": _safe_context_text(worker_context.get("agent_name")) or "BI Worker",
        "worker_agent_id": _safe_context_text(worker_context.get("agent_id")),
        "worker_session_id": _safe_context_text(worker_context.get("session_id")),
        "task_id": _safe_context_text(worker_context.get("task_id")),
        "thread_id": _safe_context_text(worker_context.get("thread_id")),
        "message_id": _safe_context_text(worker_context.get("message_id")),
        "trace_id": _safe_context_text(worker_context.get("trace_id")),
        "leader_session_id": _safe_context_text(worker_context.get("leader_session_id")),
    }
    return {key: value for key, value in fields.items() if value}


def _json_log(payload: dict[str, Any]) -> str:
    return json.dumps(
        _to_json_safe(payload, raw=False), ensure_ascii=False, sort_keys=True, default=str
    )


def _json_raw_log(payload: dict[str, Any]) -> str:
    return json.dumps(
        _to_json_safe(payload, raw=True), ensure_ascii=False, sort_keys=True, default=str
    )


def _event_category(event_type: str) -> str:
    lowered = event_type.lower()
    if "thinking" in lowered:
        return "thinking"
    if "tool_call" in lowered or "toolcall" in lowered:
        return "tool_call"
    if "tool_result" in lowered or "toolresult" in lowered:
        return "tool_result"
    if "model_call" in lowered or "modelcall" in lowered:
        return "model_call"
    if "reply" in lowered:
        return "reply"
    if "confirm" in lowered or "external_execution" in lowered:
        return "hitl"
    if "text" in lowered:
        return "text"
    return "other"


def _event_phase(event_type: str) -> str:
    lowered = event_type.lower()
    if "start" in lowered:
        return "start"
    if "delta" in lowered:
        return "delta"
    if "end" in lowered or "finish" in lowered:
        return "end"
    return "event"


def _publish_tool_progress(*, worker_context: dict[str, str | None], event: Any) -> None:
    summary = _event_summary(event)
    event_type = str(summary.get("event_type") or "").lower()
    tool_name = summary.get("tool_call_name")
    if event_type != "tool_call_start" or not tool_name:
        return
    progress = summarize_tool_progress(str(tool_name))
    _publish_worker_progress(
        worker_context=worker_context,
        phase="tool",
        status="running",
        title="工具调用",
        summary=progress["summary"],
        tool_name=_safe_context_text(tool_name),
        tool_call_id=_safe_context_text(summary.get("tool_call_id")),
    )


def _publish_thinking_progress(
    *,
    worker_context: dict[str, str | None],
    event: Any,
    state: dict[str, Any],
) -> None:
    """把 AgentScope thinking 事件投影为前端可消费的安全推理摘要进度。"""

    summary = _event_summary(event)
    if summary.get("category") != "thinking":
        return
    phase = str(summary.get("phase") or "")
    reply_id = _safe_context_text(summary.get("reply_id"))
    block_id = _safe_context_text(summary.get("block_id"))
    stream_group_id = _stream_group_id(reply_id=reply_id, block_id=block_id)
    if phase == "start":
        sequence = _next_thinking_sequence(state, stream_group_id)
        _publish_worker_progress(
            worker_context=worker_context,
            phase="thinking",
            status="running",
            title="BI Worker 思考中",
            summary="正在分析问题与可用数据证据。",
            reasoning_kind="bi_worker_thinking_summary",
            stream_group_id=stream_group_id,
            sequence=sequence,
            block_id=block_id,
        )
        return
    if phase == "end":
        # 结束时先把残留的 raw delta buffer 刷出去，避免尾段被吞。
        _flush_thinking_raw_buffer(
            worker_context=worker_context,
            state=state,
            stream_group_id=stream_group_id,
            block_id=block_id,
        )
        sequence = _next_thinking_sequence(state, stream_group_id)
        _publish_worker_progress(
            worker_context=worker_context,
            phase="thinking",
            status="completed",
            title="BI Worker 完成思考",
            summary="已完成一段安全推理摘要。",
            reasoning_kind="bi_worker_thinking_summary",
            stream_group_id=stream_group_id,
            sequence=sequence,
            block_id=block_id,
        )
        return
    if phase != "delta" or not _debug_stream_raw_thinking_enabled():
        return
    raw_delta = _safe_getattr(event, "delta")
    if raw_delta in (None, ""):
        return
    # LLM 供应商流式 chunk 常常按 tokenizer 边界切分并在词内插空格
    # (例如 `left_al` + ` ias`、`de` + `pt code`)。这里按 stream_group_id 累积
    # 到自然停顿(空白/标点/换行)或长度阈值再 emit，尽量让 UI 看到连贯的字段名。
    buffer_key = _thinking_raw_buffer_key(stream_group_id)
    buffered = str(state.get(buffer_key) or "") + str(raw_delta)
    if not _should_flush_thinking_raw_buffer(buffered):
        state[buffer_key] = buffered
        return
    state.pop(buffer_key, None)
    sequence = _next_thinking_sequence(state, stream_group_id)
    _publish_worker_progress(
        worker_context=worker_context,
        phase="thinking",
        status="running",
        title="BI Worker 调试原文",
        summary="调试原文流式更新。",
        reasoning_kind="bi_worker_raw_thinking_delta",
        stream_group_id=stream_group_id,
        sequence=sequence,
        block_id=block_id,
        debug_raw=True,
        raw_delta=buffered,
    )


def _thinking_raw_buffer_key(stream_group_id: str) -> str:
    """把 raw delta buffer 编码到同一份 state 字典中，避免和 sequence 计数冲突。"""

    return f"{stream_group_id}::raw_buffer"


_RAW_THINKING_FLUSH_TAIL_CHARS = frozenset(" \t\n\r　。！？；：，、!?;:,.）)]}】》」』")
_RAW_THINKING_FLUSH_LENGTH = 64


def _should_flush_thinking_raw_buffer(buffered: str) -> bool:
    """判定累积的 raw delta 是否已到自然停顿点或长度阈值。"""

    if not buffered:
        return False
    if len(buffered) >= _RAW_THINKING_FLUSH_LENGTH:
        return True
    return buffered[-1] in _RAW_THINKING_FLUSH_TAIL_CHARS


def _flush_thinking_raw_buffer(
    *,
    worker_context: dict[str, str | None],
    state: dict[str, Any],
    stream_group_id: str,
    block_id: str | None,
) -> None:
    """强制把 stream_group_id 对应的 raw delta 缓冲 emit 一次并清空。"""

    if not _debug_stream_raw_thinking_enabled():
        return
    buffer_key = _thinking_raw_buffer_key(stream_group_id)
    buffered = str(state.get(buffer_key) or "")
    if not buffered:
        return
    state.pop(buffer_key, None)
    sequence = _next_thinking_sequence(state, stream_group_id)
    _publish_worker_progress(
        worker_context=worker_context,
        phase="thinking",
        status="running",
        title="BI Worker 调试原文",
        summary="调试原文流式更新。",
        reasoning_kind="bi_worker_raw_thinking_delta",
        stream_group_id=stream_group_id,
        sequence=sequence,
        block_id=block_id,
        debug_raw=True,
        raw_delta=buffered,
    )


def _flush_all_thinking_raw_buffers(
    *,
    worker_context: dict[str, str | None],
    state: dict[str, Any],
) -> None:
    """兜底刷新所有 stream_group_id 的 raw delta 缓冲；用于 reply 完全结束时。"""

    pending_keys = [key for key in list(state.keys()) if key.endswith("::raw_buffer")]
    for key in pending_keys:
        stream_group_id = key[: -len("::raw_buffer")]
        # 兜底时 block_id 已不可考，从 stream_group_id 后缀解析（`agent-worker-thinking:reply:block`）。
        block_id_part = stream_group_id.rsplit(":", 1)[-1] or None
        _flush_thinking_raw_buffer(
            worker_context=worker_context,
            state=state,
            stream_group_id=stream_group_id,
            block_id=block_id_part,
        )


def _stream_group_id(*, reply_id: str | None, block_id: str | None) -> str:
    reply_part = reply_id or "reply"
    block_part = block_id or "thinking"
    return f"agent-worker-thinking:{reply_part}:{block_part}"


def _next_thinking_sequence(state: dict[str, int], stream_group_id: str) -> int:
    sequence = state.get(stream_group_id, 0) + 1
    state[stream_group_id] = sequence
    return sequence


def _debug_stream_raw_thinking_enabled() -> bool:
    raw_env = os.getenv("DATALOGUE_DEBUG_STREAM_RAW_THINKING")
    if raw_env is not None:
        return raw_env.strip().lower() in _RAW_THINKING_TRUE_VALUES
    try:
        from app.core.config import get_settings

        # 兼容写在 datalogue-api/.env 的配置：BaseSettings 会读取 env_file，
        # 但不会保证把值同步回 os.environ，所以这里必须走 Settings fallback。
        return bool(get_settings().DATALOGUE_DEBUG_STREAM_RAW_THINKING)
    except Exception:
        return False


def summarize_tool_progress(tool_name: str) -> dict[str, str]:
    """把 BI Worker 工具名投影为用户可见安全进度，避免展示 schema/query_plan/raw rows。"""

    if tool_name in _PROGRESSIVE_TOOL_SUMMARIES:
        return {"summary": _PROGRESSIVE_TOOL_SUMMARIES[tool_name]}
    safe_tool_name = _safe_context_text(tool_name) or "受控工具"
    return {"summary": f"BI Worker 正在调用 {safe_tool_name}。"}


def _publish_worker_progress(
    *,
    worker_context: dict[str, str | None],
    phase: str,
    status: str,
    title: str,
    summary: str,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
    reasoning_kind: str | None = None,
    stream_group_id: str | None = None,
    sequence: int | None = None,
    block_id: str | None = None,
    debug_raw: bool = False,
    raw_delta: str | None = None,
) -> None:
    """发布用户可见实时摘要；禁止把 inputs、tool input、raw LLM I/O 写入 payload。"""

    payload = {
        "agent_role": "worker",
        "agent_name": _safe_context_text(worker_context.get("agent_name")) or "BI Worker",
        "phase": phase,
        "status": status,
        "title": title,
        "summary": summary,
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "reasoning_kind": _safe_context_text(reasoning_kind),
        "stream_group_id": _safe_context_text(stream_group_id),
        "sequence": sequence if isinstance(sequence, int) and sequence > 0 else None,
        "block_id": _safe_context_text(block_id),
        "debug_raw": True if debug_raw else None,
        "raw_delta": str(raw_delta) if debug_raw and raw_delta is not None else None,
        "worker_agent_id": _safe_context_text(worker_context.get("agent_id")),
        "worker_session_id": _safe_context_text(worker_context.get("session_id")),
        "task_id": _safe_context_text(worker_context.get("task_id")),
        "thread_id": _safe_context_text(worker_context.get("thread_id")),
        "message_id": _safe_context_text(worker_context.get("message_id")),
    }
    payload = {key: value for key, value in payload.items() if value}
    try:
        _assert_worker_progress_safe(payload)
    except ValueError as exc:
        # 进度事件只是前端可视化增强；一旦命中泄露风险必须丢弃该 progress，
        # 但不能打断 AgentScope 主事件流，否则调试防线会反过来影响 BI Worker 执行。
        logger.warning(
            "[agentscope.bi_worker.progress_drop] unsafe progress payload dropped: %s",
            exc,
        )
        return
    publish_agent_progress(
        leader_session_id=worker_context.get("leader_session_id"),
        payload=payload,
    )


def _assert_worker_progress_safe(payload: dict[str, Any]) -> None:
    """防止默认进度误带 raw thinking / SQL / schema / QueryPlan 等内部细节。"""

    debug_raw = payload.get("debug_raw") is True
    raw_delta = payload.get("raw_delta")
    if raw_delta is not None and not debug_raw:
        raise ValueError("raw_delta requires debug_raw=true")
    if debug_raw and payload.get("reasoning_kind") != "bi_worker_raw_thinking_delta":
        raise ValueError("debug raw thinking progress requires raw reasoning kind")
    for key, value in payload.items():
        if key == "raw_delta" and debug_raw:
            continue
        if key in {"delta", "thinking"}:
            raise ValueError(f"unsafe worker progress key: {key}")
        if isinstance(value, str) and _SENSITIVE_TEXT_PATTERN.search(value):
            raise ValueError(f"unsafe worker progress value for {key}")


def _safe_context_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or _SENSITIVE_TEXT_PATTERN.search(text):
        return None
    return text[:160]


def _pending_tool_calls(event: Any) -> list[dict[str, Any]]:
    """提取等待确认/外部执行事件中的工具名；不记录完整 input，避免把查询问题或路径细节打进普通日志。"""

    tool_calls = getattr(event, "tool_calls", None)
    if not isinstance(tool_calls, list):
        return []
    pending: list[dict[str, Any]] = []
    for tool_call in tool_calls[:20]:
        name = getattr(tool_call, "name", None)
        tool_call_id = getattr(tool_call, "id", None)
        state = getattr(tool_call, "state", None)
        pending.append(
            {
                "id": str(tool_call_id) if tool_call_id else None,
                "name": str(name) if name else None,
                "state": str(state) if state else None,
            }
        )
    return [
        {key: value for key, value in item.items() if value is not None} for item in pending if item
    ]


def _model_input_summary(input_kwargs: dict[str, Any]) -> dict[str, Any]:
    messages = input_kwargs.get("messages") or []
    tools = input_kwargs.get("tools") or []
    # 估算输入字符数（前 50 条消息，避免超大上下文撑爆日志）。
    input_text = ""
    if isinstance(messages, list):
        input_text = "".join(str(getattr(m, "content", m)) for m in messages[:50])
    return {
        "message_count": len(messages) if hasattr(messages, "__len__") else None,
        "tool_count": len(tools) if hasattr(tools, "__len__") else None,
        "tool_names": _tool_names(tools),
        "tool_choice": str(input_kwargs.get("tool_choice") or ""),
        "input_chars": len(input_text),
    }


def _model_output_summary(
    response: Any,
    *,
    chunk_index: int | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    content = _safe_getattr(response, "content")
    finish_reason = _safe_getattr(response, "finish_reason") or _safe_getattr(
        response, "stop_reason"
    )
    return {
        "response_type": type(response).__name__,
        "is_last": _safe_getattr(response, "is_last"),
        "content_type": type(content).__name__ if content is not None else None,
        "content_length": len(str(content)) if content is not None else None,
        "chunk_index": chunk_index,
        "output_chars": len(str(content)) if content is not None else 0,
        "finish_reason": str(finish_reason) if finish_reason else None,
        "duration_ms": duration_ms,
        "usage": _to_json_safe(_safe_getattr(response, "usage"), raw=False),
    }


def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    """安全的 getattr — 兼容 __getattr__ 抛出 KeyError 的对象（如 AgentScope StreamingEvent）。"""
    try:
        return getattr(obj, name, default)
    except KeyError:
        return default


def _tool_names(tools: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(tools, list):
        return names
    for tool in tools[:20]:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if isinstance(function, dict) and function.get("name"):
            names.append(str(function["name"]))
    return names


def _to_json_safe(value: Any, *, raw: bool) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value if raw or not isinstance(value, str) else _clip(value)
    if isinstance(value, dict):
        return {str(key): _to_json_safe(nested, raw=raw) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(item, raw=raw) for item in value[:50]]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _to_json_safe(model_dump(mode="json"), raw=raw)
    as_dict = getattr(value, "to_dict", None)
    if callable(as_dict):
        return _to_json_safe(as_dict(), raw=raw)
    if hasattr(value, "__dict__"):
        return _to_json_safe(vars(value), raw=raw)
    return str(value) if raw else _clip(str(value))


def _clip(value: str, limit: int = 300) -> str:
    return value if len(value) <= limit else f"{value[:limit]}..."
