# ============================================================
# File Name   : test_bi_soul_contract.py
# Description:
#   BI_SOUL 内部契约与外部入口同步校验测试。
#
# Responsibilities:
#   - 验证内部 BI_SOUL 是不可越界协议 source of truth。
#   - 验证 Hermes Skill SOUL 与内部契约同步。
#   - 验证 Agentic Shell policy 明确删除旧兼容入口。
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

    assert "BI Agent 不看字段级 schema 明细" in internal
    assert "legacy `ask_bi` 和旧 Chat stream 已删除" in internal
    assert "主 Runtime ownership 属于 Datalogue Agentic Shell" in internal
    assert "LLM 不直接生成可执行 SQL" in internal
    assert "raw SQL / raw result / capsule / trace 主体属于 `control_plane`" in internal


def test_hermes_skill_soul_syncs_internal_bi_soul_contract():
    internal = load_internal_bi_soul()
    hermes = load_hermes_skill_soul()

    assert normalize_contract(internal) == normalize_contract(hermes)
    assert_hermes_soul_synced()


def test_agentscope_shell_policy_marks_legacy_removed_and_hides_control_plane():
    policy = render_agentscope_shell_policy()

    assert "compatibility_mode: removed_legacy_shell_adapter" in policy
    assert "runtime_owner: datalogue_agentic_shell" in policy
    assert "owns_business_runtime: true" in policy
    assert "不得注册 schema、SQL、preview、database、artifact body 或 control_plane 工具" in policy
    assert "raw SQL / raw result / capsule / trace 主体属于 `control_plane`" in policy
