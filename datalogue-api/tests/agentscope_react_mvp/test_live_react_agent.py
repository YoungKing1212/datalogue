# ============================================================
# File Name   : test_live_react_agent.py
# Description:
#   用真实 Datalogue 服务验证 AgentScope 2.0 Agent 能自主调用平台能力。
#
# Responsibilities:
#   - 启动 AgentScope Agent，而不是手动顺序调用工具。
#   - 使用真实 HTTP 请求访问当前部署的 Datalogue API。
#   - 断言 Agent 自主完成 plan-query 与 readonly SQL preview 两类能力调用。
#
# Author      : yangkai
# Created On  : 2026-06-25
# ============================================================

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any


import pytest


logger = logging.getLogger(__name__)


def _configure_console_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
        force=True,
    )


def _first_positive_number(rows: list[dict[str, Any]]) -> int | float | None:
    """从 SQL preview 的首行结果中提取正数，避免把测试绑定到模型生成的列别名。"""

    if not rows:
        return None
    for value in rows[0].values():
        if isinstance(value, (int, float)) and value > 0:
            return value
    return None


def _preview_result_for_log(preview_result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not preview_result or os.getenv("AGENTSCOPE_MVP_LOG_FULL_RESULT") == "1":
        return preview_result
    return {
        "dataset_id": preview_result.get("dataset_id"),
        "sql": preview_result.get("sql"),
        "columns": preview_result.get("columns"),
        "row_count": preview_result.get("row_count"),
        "sql_guard": preview_result.get("sql_guard"),
        "error": preview_result.get("error"),
        "rows_first_5": (preview_result.get("rows") or [])[:5],
    }


def _react_trace_for_log(react_trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if os.getenv("AGENTSCOPE_MVP_LOG_FULL_REACT_TRACE") == "1":
        return react_trace
    return react_trace[-12:]


def _import_mvp_module():
    try:
        from agentscope_react_mvp import mvp
    except ImportError as exc:
        pytest.skip(f"运行 AgentScope MVP 测试前需要安装 agentscope 2.0：{exc}")
    return mvp


def test_capability_manifest_filters_dataset_agent_tools() -> None:
    mvp = _import_mvp_module()
    trace = mvp.DatalogueToolTrace()
    manifest = mvp.default_capability_manifest(allowed_tools=("recall_assets", "preview_sql"))

    tools = mvp.build_dataset_agent_tools(
        base_url="http://127.0.0.1:8000",
        trace=trace,
        manifest=manifest,
    )

    assert [tool.name for tool in tools] == ["recall_assets", "preview_sql"]
    assert "guard_sql" not in [tool.name for tool in tools]
    assert "execute_query" not in [tool.name for tool in tools]
    assert "persist_artifact" not in [tool.name for tool in tools]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agentscope_agent_autonomously_calls_live_datalogue_tools() -> None:
    if os.getenv("RUN_AGENTSCOPE_REACT_MVP") != "1":
        pytest.skip("设置 RUN_AGENTSCOPE_REACT_MVP=1 后才请求真实服务和真实 LLM")

    _configure_console_logging()
    base_url = os.getenv("DATALOGUE_BASE_URL", "http://127.0.0.1:8000")
    question = "我想查询杨凯2024年的工作日志。"
    dataset_id = None
    logger.info(
        "[AgentScope MVP][Test start] base_url=%s dataset_id=%s question=%s",
        base_url,
        dataset_id,
        question,
    )

    mvp = _import_mvp_module()

    result = await mvp.run_datalogue_react_mvp(
        question=question,
        dataset_id=dataset_id,
        base_url=base_url,
    )

    logger.info("[AgentScope MVP][Test final_text]\n%s", result.final_text)
    logger.info(
        "[AgentScope MVP][Test preview_result]\n%s",
        json.dumps(
            _preview_result_for_log(result.preview_result),
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
    )
    logger.info("[AgentScope MVP][Test tool_names] %s", result.tool_names)
    logger.info("[AgentScope MVP][Test called_paths] %s", result.called_paths)
    logger.info("[AgentScope MVP][Test result_ref] %s", result.result_ref)
    logger.info(
        "[AgentScope MVP][Test artifact]\n%s",
        json.dumps(result.artifact, ensure_ascii=False, indent=2, default=str),
    )
    logger.info(
        "[AgentScope MVP][Test react_trace]\n%s",
        json.dumps(
            _react_trace_for_log(result.react_trace),
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
    )
    logger.info("[AgentScope MVP][Test registered_tools] %s", result.registered_tools)

    assert "recall_assets" in result.registered_tools
    assert "plan_query" in result.registered_tools
    assert "preview_sql" in result.registered_tools
    assert "summarize_result" in result.registered_tools
    assert any(tool_name in result.tool_names for tool_name in ("recall_assets", "plan_query"))
    assert any(tool_name in result.tool_names for tool_name in ("preview_sql", "execute_query"))
    assert "/api/dataset" in result.called_paths
    assert any(path.endswith("/selected-tables") for path in result.called_paths)
    assert any(path.endswith("/selected-columns") for path in result.called_paths)
    assert any(path.endswith("/sql/preview") for path in result.called_paths)
    assert "/api/chat/stream" not in result.called_paths
    assert "/api/conversation" not in result.called_paths
    assert result.preview_result is not None
    assert result.preview_result["sql_guard"]["ok"] is True
    assert _first_positive_number(result.preview_result["rows"]) is not None
    assert result.result_ref is not None
    assert result.result_ref.startswith("mvp://query_artifact/")
    assert result.artifact is not None
    assert result.artifact["result_ref"] == result.result_ref
    assert result.artifact["truth_source"] == "datalogue_sql_preview"
    assert result.artifact["persisted"] is False
    assert result.tool_trace
    assert result.react_trace
    assert any(event["event"] == "llm_request" for event in result.react_trace)
    assert any(event["event"] == "llm_response" for event in result.react_trace)
    assert any(event["event"] == "tool_observation" for event in result.react_trace)
    assert result.capability_manifest["agent_role"] == "dataset_agent"
    assert result.capability_manifest["raw_sql_visible_to_lead_agent"] is False
    assert "SOUL.md" in result.prompt_sources
    assert "SKILL.md" in result.prompt_sources
    assert "Hermes SOUL.md" in result.system_prompt
    assert "capability_manifest" in result.system_prompt
    assert "DatasetAgent" in result.system_prompt
    assert result.final_text.strip()
