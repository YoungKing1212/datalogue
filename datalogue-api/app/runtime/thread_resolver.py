# ============================================================
# File Name   : thread_resolver.py
# Description:
#   AgentScope runtime 线程 ID 解析边界。
#
# Responsibilities:
#   - 统一 as_* 新会话和 conv_* 历史会话的线程命名。
#   - 为 Chat、Workbench 和 retry 层提供 fail-closed 的线程边界判断。
#   - 明确区分可写 AgentScope 线程与只读历史会话。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

import re
import uuid

from app.schemas.agentscope_workbench import AgentScopeThreadKind, ThreadRef

_LEGACY_NUMERIC_RE = re.compile(r"^\d+$")
_LEGACY_THREAD_RE = re.compile(r"^conv_(\d+)$")
_AGENTSCOPE_THREAD_RE = re.compile(
    r"^as_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def normalize_thread_id(raw_thread_id: str | int | None) -> str | None:
    if raw_thread_id is None:
        return None  # None 表示创建 C3 新会话，调用方会生成 as_* 真相源线程。

    value = str(raw_thread_id).strip()
    if not value:
        raise ValueError("INVALID_THREAD_ID")
    if _LEGACY_NUMERIC_RE.match(value):
        return f"conv_{value}"  # 兼容旧 `/chat/:number` 路由，统一投影为只读历史线程。
    if _LEGACY_THREAD_RE.match(value):
        return value
    if _AGENTSCOPE_THREAD_RE.match(value):
        return value
    raise ValueError("INVALID_THREAD_ID")


def resolve_thread_ref(raw_thread_id: str | int | None) -> ThreadRef | None:
    thread_id = normalize_thread_id(raw_thread_id)
    if thread_id is None:
        return None

    legacy_match = _LEGACY_THREAD_RE.match(thread_id)
    if legacy_match:
        return ThreadRef(
            thread_id=thread_id,
            kind=AgentScopeThreadKind.LEGACY_CONVERSATION,
            legacy_conversation_id=int(legacy_match.group(1)),
            read_only=True,
        )
    return ThreadRef(
        thread_id=thread_id,
        kind=AgentScopeThreadKind.AGENTSCOPE,
        read_only=False,
    )


def new_runtime_thread_id() -> str:
    return f"as_{uuid.uuid4()}"
