# ============================================================
# File Name   : worker_logging.py
# Description:
#   AgentScope BI worker 的前端进度中间件。
#
# Responsibilities:
#   - 通过 AgentScope extra_agent_middlewares 只为 Datalogue BI worker 挂载进度中间件。
#   - 发布 Workbench/Chat 可消费的安全进度事件。
#   - 模型调用与工具执行观测交给 AgentScope TracingMiddleware / OpenTelemetry。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from agentscope.app.storage import StorageBase
from agentscope.middleware import MiddlewareBase, TracingMiddleware

from app.agentscope_service.progress_bridge import publish_agent_progress
from app.agentscope_service.task_context import resolve_task_context

AgentMiddlewareFactory = Callable[[str | None, str | None, str | None], Awaitable[list[MiddlewareBase]]]
_BI_WORKER_MARKERS = ("Datalogue BI Worker", "Dataset Query", "datalogue_query_dataset")


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
        # BIWorkerProgressMiddleware 只发布用户可见进度事件，不再打印自定义执行日志。
        middlewares: list[MiddlewareBase] = [TracingMiddleware()]
        if worker_context is not None:
            middlewares.append(BIWorkerProgressMiddleware(worker_context=worker_context))
        return middlewares

    return _extra_agent_middlewares


class BIWorkerProgressMiddleware(MiddlewareBase):
    """AgentScope Middleware：只发布 BI worker 的安全进度事件。"""

    def __init__(self, *, worker_context: dict[str, str | None]) -> None:
        self.worker_context = worker_context

    async def on_reply(
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        """发布 worker 一次 reply 的开始、工具调用和结束进度。"""

        _publish_worker_progress(
            worker_context=self.worker_context,
            phase="reply",
            status="running",
            title="BI Worker 开始处理",
            summary="BI Worker 已开始处理任务。",
        )
        del agent
        try:
            async for event in next_handler(**input_kwargs):
                _publish_tool_progress(worker_context=self.worker_context, event=event)
                yield event
        except Exception:
            _publish_worker_progress(
                worker_context=self.worker_context,
                phase="reply",
                status="failed",
                title="BI Worker 处理失败",
                summary="BI Worker 处理过程中发生错误，内部细节已隐藏。",
            )
            raise
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
    raw_type = getattr(event, "type", None)
    event_type = str(raw_type or event.__class__.__name__)
    summary: dict[str, Any] = {
        "event_type": event_type,
        "reply_id": getattr(event, "reply_id", None),
        "tool_call_id": getattr(event, "tool_call_id", None),
        "tool_call_name": getattr(event, "tool_call_name", None),
        "is_last": getattr(event, "is_last", None),
    }
    content = getattr(event, "content", None)
    if content is not None:
        summary["content_type"] = type(content).__name__
        summary["content_length"] = len(str(content))
    pending_tool_calls = _pending_tool_calls(event)
    if pending_tool_calls:
        summary["pending_tool_calls"] = pending_tool_calls
        summary["pending_tool_names"] = [item["name"] for item in pending_tool_calls if item.get("name")]
    return {key: value for key, value in summary.items() if value is not None}


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
    return text[:160] if text else None


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
