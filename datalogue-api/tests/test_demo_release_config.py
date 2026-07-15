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

import json

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


@pytest.mark.asyncio
async def test_single_table_release_blocks_multi_table_plan_before_execution(
    monkeypatch: pytest.MonkeyPatch,
):
    from app.runtime.engine.tools import build_datalogue_progressive_bi_worker_tools

    monkeypatch.setenv("DATALOGUE_DEMO_CAPABILITY_LEVEL", "single_table")
    get_settings.cache_clear()
    tools = build_datalogue_progressive_bi_worker_tools(worker_context=None)
    execute_tool = next(
        tool for tool in tools if tool.name == "datalogue_execute_query_plan_bundle"
    )
    plan = {
        "intent": "detail_query",
        "question": "查询人员所属部门",
        "result_shape": {"type": "table", "grain": "人员"},
        "data_graph": {
            "primary_entity": {
                "asset_ref": "asset:demo.person",
                "alias": "p",
                "role": "fact",
            },
            "supporting_entities": [
                {
                    "asset_ref": "asset:demo.department",
                    "alias": "d",
                    "role": "dimension",
                }
            ],
        },
        "join_requirements": [
            {
                "left_alias": "p",
                "right_alias": "d",
                "relationship_ref": "relationship:demo.person_department",
                "join_keys": [{"left_field": "department_id", "right_field": "id"}],
            }
        ],
        "selects": [
            {
                "target": {
                    "asset_ref": "field:demo.person.name",
                    "alias": "p",
                    "field": "name",
                },
                "display_name": "人员",
            }
        ],
    }
    try:
        chunk = await execute_tool(
            dataset_id=1,
            confirmed_question=plan["question"],
            query_plan=plan,
            context_state={},
        )
        payload = json.loads(chunk.content[0].text)
        assert payload["code"] == "CAPABILITY_LEVEL_RESTRICTED"
        assert payload["capability_level"] == "single_table"
        assert "demo.person" not in json.dumps(payload, ensure_ascii=False)
    finally:
        get_settings.cache_clear()
