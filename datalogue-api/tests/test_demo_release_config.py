# ============================================================
# File Name   : test_demo_release_config.py
# Description:
#   分阶段演示版本配置与 Worker 注册边界测试。
#
# Responsibilities:
#   - 验证四级能力配置拒绝未知值。
#   - 验证演示关闭智能报告后只注册 BI Worker。
#
# Author      : yangkai
# Created On  : 2026-07-15
# ============================================================

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


@pytest.mark.parametrize(
    "level",
    ["single_table", "multi_table", "semantic_metrics", "agent_team"],
)
def test_settings_accepts_demo_capability_levels(level: str):
    settings = Settings(DATALOGUE_DEMO_CAPABILITY_LEVEL=level)
    assert settings.DATALOGUE_DEMO_CAPABILITY_LEVEL == level


def test_settings_rejects_unknown_demo_capability_level():
    with pytest.raises(ValidationError):
        Settings(DATALOGUE_DEMO_CAPABILITY_LEVEL="full_access")


def test_report_worker_can_be_removed_from_demo_registry(monkeypatch: pytest.MonkeyPatch):
    from app.runtime.engine.registry import (
        available_datalogue_worker_types,
        build_datalogue_leader_agent_spec,
    )

    monkeypatch.setenv("DATALOGUE_REPORT_WORKER_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert available_datalogue_worker_types() == ["bi"]
        assert "严禁创建 report worker" in build_datalogue_leader_agent_spec().system_prompt
    finally:
        # 缓存不能把本测试的演示配置带到其他注册表测试。
        get_settings.cache_clear()
