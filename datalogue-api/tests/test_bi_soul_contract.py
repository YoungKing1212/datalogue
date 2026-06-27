# ============================================================
# File Name   : test_bi_soul_contract.py
# Description:
#   BI_SOUL 内部契约与外部入口同步校验测试。
#
# Responsibilities:
#   - 验证内部 BI_SOUL 是不可越界协议 source of truth。
#   - 验证 Hermes Skill SOUL 与内部契约同步。
#   - 验证 AgentScope Shell policy 只暴露 ask_bi 外层入口。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

from app.services.soul_contract_sync import (
    assert_hermes_soul_synced,
    load_hermes_skill_soul,
    load_internal_bi_soul,
    normalize_contract,
    render_agentscope_shell_policy,
)


def test_internal_bi_soul_is_source_of_truth_for_external_entries():
    internal = load_internal_bi_soul()

    assert "LeadAgent 不看字段级 schema 明细" in internal
    assert "外层 Agent 只能调用 `ask_bi`" in internal
    assert "LLM 不直接生成可执行 SQL" in internal
    assert "raw SQL / raw result / capsule / trace 主体属于 `control_plane`" in internal


def test_hermes_skill_soul_syncs_internal_bi_soul_contract():
    internal = load_internal_bi_soul()
    hermes = load_hermes_skill_soul()

    assert normalize_contract(internal) == normalize_contract(hermes)
    assert_hermes_soul_synced()


def test_agentscope_shell_policy_allows_only_ask_bi_and_hides_control_plane():
    policy = render_agentscope_shell_policy()

    assert "allowed_tools: ask_bi" in policy
    assert "AgentScopeShellAdapter 不替代 Datalogue 真相源" in policy
    assert "不得注册 schema、SQL、preview、database、artifact body 或 control_plane 工具" in policy
    assert "raw SQL / raw result / capsule / trace 主体属于 `control_plane`" in policy
