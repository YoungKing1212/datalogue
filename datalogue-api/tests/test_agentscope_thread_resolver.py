# ============================================================
# File Name   : test_agentscope_thread_resolver.py
# Description:
#   C3 AgentScope Workbench 线程标识解析测试。
#
# Responsibilities:
#   - 验证 as_* 新会话和 conv_* 历史会话的线程 ID 规范化规则。
#   - 验证非法线程 ID fail closed，避免前端路由污染后端状态。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

import pytest

from app.schemas.agentscope_workbench import AgentScopeThreadKind
from app.services.agentscope_thread_resolver import normalize_thread_id, resolve_thread_ref


def test_normalize_thread_id_keeps_none_for_new_session():
    assert normalize_thread_id(None) is None


def test_normalize_thread_id_converts_numeric_route_to_legacy_thread():
    assert normalize_thread_id("25") == "conv_25"


def test_normalize_thread_id_accepts_prefixed_legacy_thread():
    assert normalize_thread_id("conv_25") == "conv_25"


def test_normalize_thread_id_accepts_agentscope_uuid_thread():
    value = normalize_thread_id("as_01234567-89ab-cdef-0123-456789abcdef")

    assert value.startswith("as_")


def test_normalize_thread_id_rejects_unknown_values():
    with pytest.raises(ValueError, match="INVALID_THREAD_ID"):
        normalize_thread_id("chat-25")


def test_resolve_thread_ref_marks_agentscope_and_legacy_boundaries():
    agentscope = resolve_thread_ref("as_01234567-89ab-cdef-0123-456789abcdef")
    legacy = resolve_thread_ref("25")

    assert agentscope.thread_id == "as_01234567-89ab-cdef-0123-456789abcdef"
    assert agentscope.kind == AgentScopeThreadKind.AGENTSCOPE
    assert agentscope.read_only is False
    assert legacy.thread_id == "conv_25"
    assert legacy.kind == AgentScopeThreadKind.LEGACY_CONVERSATION
    assert legacy.legacy_conversation_id == 25
    assert legacy.read_only is True
