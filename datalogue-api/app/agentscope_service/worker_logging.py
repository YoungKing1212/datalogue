# ============================================================
# File Name   : worker_logging.py
# Description:
#   AgentScope BI worker 的前端进度中间件。
#
# Responsibilities:
#   - 通过 AgentScope extra_agent_middlewares 只为 Datalogue BI worker 挂载进度中间件。
#   - 发布 Workbench/Chat 可消费的安全进度事件。
#   - 记录 BI Worker 的 AgentScope 事件链路摘要，辅助排查 thinking/tool/model 事件顺序。
#   - 模型调用完整观测交给 AgentScope TracingMiddleware / OpenTelemetry。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
import json
import logging
import re
from typing import Any

from agentscope.app.storage import StorageBase
from agentscope.message import AssistantMsg
from agentscope.middleware import MiddlewareBase, TracingMiddleware

from app.agentscope_service.progress_bridge import publish_agent_progress
from app.agentscope_service.task_context import resolve_task_context
from app.middlewares.lifecycle import raw_agent_logs_enabled

AgentMiddlewareFactory = Callable[[str | None, str | None, str | None], Awaitable[list[MiddlewareBase]]]
_BI_WORKER_MARKERS = ("Datalogue BI Worker", "Dataset Query", "datalogue_query_dataset")
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


def build_datalogue_extra_agent_middlewares(*, storage: StorageBase | None = None) -> AgentMiddlewareFactory:
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
        # TracingMiddleware 全局挂载（所有 agent），未配置 TracerProvider 时零开销短路。
        # BIWorkerProgressMiddleware 只记录 thinking 路径摘要、工具结果摘要与用户可见进度，不接管原始模型 I/O 日志。
        middlewares: list[MiddlewareBase] = [TracingMiddleware()]
        if worker_context is not None:
            middlewares.append(BIWorkerProgressMiddleware(worker_context=worker_context))
        return middlewares

    return _extra_agent_middlewares


class BIWorkerProgressMiddleware(MiddlewareBase):
    """AgentScope Middleware：发布 BI worker 安全进度，并提取受控的 reply 结果日志。"""

    def __init__(self, *, worker_context: dict[str, str | None]) -> None:
        self.worker_context = worker_context

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
        try:
            async for event in next_handler(**input_kwargs):
                reply_msg = _append_event_to_reply_msg(reply_msg, event, agent_name=agent_name)
                if _should_log_worker_event(event):
                    _log_worker_event(worker_context=self.worker_context, event=event)
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
        _log_raw_debug_blocks_if_enabled(msg=reply_msg)
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
    agent_record = await storage.get_agent(user_id, agent_id)
    if not agent_record or agent_record.source != "team":
        return None
    agent_data = getattr(agent_record, "data", None)
    system_prompt = str(getattr(agent_data, "system_prompt", "") or "")
    if not any(marker in system_prompt for marker in _BI_WORKER_MARKERS):
        return None
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
        summary["pending_tool_names"] = [item["name"] for item in pending_tool_calls if item.get("name")]
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


def _log_worker_event(*, worker_context: dict[str, str | None], event: Any) -> None:
    """记录 AgentScope 原生 thinking 事件摘要；不写原始思维文本。"""

    payload = {
        "agent_role": "worker",
        **_worker_context_log_fields(worker_context),
        "event": _event_summary(event),
    }
    logger.info("[agentscope.bi_worker.event] %s", _json_log(payload))


def _log_raw_debug_blocks_if_enabled(*, msg: Any) -> None:
    """显式开启 raw debug 时，在 reply 拼接完成后用 DEBUG 打印原始调试内容。"""

    if msg is None or not raw_agent_logs_enabled():
        return
    payload = _raw_debug_blocks_from_msg(msg)
    if not payload:
        return
    logger.debug("[agentscope.bi_worker.raw_debug] %s", _json_raw_log(payload))


def _raw_debug_blocks_from_msg(msg: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    thinking = _raw_thinking_from_msg(msg)
    text = _raw_text_from_msg(msg)
    tools = _raw_tool_io_from_msg(msg)
    if thinking:
        payload["thinking"] = thinking
    if text:
        payload["text"] = text
    if tools:
        payload["tools"] = tools
    return payload


def _raw_thinking_from_msg(msg: Any) -> list[str]:
    return [
        str(_safe_getattr(block, "thinking") or "")
        for block in _safe_content_blocks(msg, "thinking")[:20]
        if str(_safe_getattr(block, "thinking") or "")
    ]


def _raw_text_from_msg(msg: Any) -> list[str]:
    return [
        str(_safe_getattr(block, "text") or "")
        for block in _safe_content_blocks(msg, "text")[:20]
        if str(_safe_getattr(block, "text") or "")
    ]


def _raw_tool_io_from_msg(msg: Any) -> list[dict[str, Any]]:
    results_by_id = {
        str(_safe_getattr(block, "id") or ""): block
        for block in _safe_content_blocks(msg, "tool_result")[:20]
    }
    tools: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for block in _safe_content_blocks(msg, "tool_call")[:20]:
        call_id = str(_safe_getattr(block, "id") or "")
        seen_ids.add(call_id)
        result_block = results_by_id.get(call_id)
        tools.append(
            _raw_tool_io_item(
                name=_safe_getattr(block, "name") or _safe_getattr(result_block, "name"),
                input_text=str(_safe_getattr(block, "input") or ""),
                output_text=_tool_result_output_text(_safe_getattr(result_block, "output")) if result_block else "",
            )
        )
    for call_id, result_block in results_by_id.items():
        if call_id in seen_ids:
            continue
        tools.append(
            _raw_tool_io_item(
                name=_safe_getattr(result_block, "name"),
                input_text="",
                output_text=_tool_result_output_text(_safe_getattr(result_block, "output")),
            )
        )
    return tools


def _raw_tool_io_item(*, name: Any, input_text: str, output_text: str) -> dict[str, Any]:
    item = {
        "tool_name": str(name) if name else None,
        "input": input_text,
        "output": output_text,
    }
    return {key: value for key, value in item.items() if value not in (None, "")}


def _should_log_worker_event(event: Any) -> bool:
    """普通事件日志只保留思考路径摘要；工具结果在 reply 结束后从 Msg 块统一提取。"""

    event_type = str(_safe_getattr(event, "type") or event.__class__.__name__)
    return _event_category(event_type) == "thinking"


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
        results.append({key: value for key, value in result.items() if value not in (None, "", [], {})})
    return results


def _safe_content_blocks(msg: Any, block_type: str) -> list[Any]:
    get_blocks = getattr(msg, "get_content_blocks", None)
    if not callable(get_blocks):
        return []
    try:
        blocks = get_blocks(block_type)
    except Exception:
        return []
    return blocks if isinstance(blocks, list) else []


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
    return {"content_type": type(parsed).__name__, "item_count": len(parsed) if isinstance(parsed, list) else None}


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
        safe_action = {key: value for key, value in safe_action.items() if value not in (None, "", [], {})}
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
    return json.dumps(_to_json_safe(payload, raw=False), ensure_ascii=False, sort_keys=True, default=str)


def _json_raw_log(payload: dict[str, Any]) -> str:
    return json.dumps(_to_json_safe(payload, raw=True), ensure_ascii=False, sort_keys=True, default=str)


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
    _publish_worker_progress(
        worker_context=worker_context,
        phase="tool",
        status="running",
        title="工具调用",
        summary=f"BI Worker 正在调用 {tool_name}。",
        tool_name=str(tool_name),
        tool_call_id=_safe_context_text(summary.get("tool_call_id")),
    )


def _publish_worker_progress(
    *,
    worker_context: dict[str, str | None],
    phase: str,
    status: str,
    title: str,
    summary: str,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
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
        "worker_agent_id": _safe_context_text(worker_context.get("agent_id")),
        "worker_session_id": _safe_context_text(worker_context.get("session_id")),
        "task_id": _safe_context_text(worker_context.get("task_id")),
        "thread_id": _safe_context_text(worker_context.get("thread_id")),
        "message_id": _safe_context_text(worker_context.get("message_id")),
    }
    publish_agent_progress(
        user_id=worker_context.get("user_id"),
        payload={key: value for key, value in payload.items() if value},
    )


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
        {key: value for key, value in item.items() if value is not None}
        for item in pending
        if item
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
    finish_reason = _safe_getattr(response, "finish_reason") or _safe_getattr(response, "stop_reason")
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
