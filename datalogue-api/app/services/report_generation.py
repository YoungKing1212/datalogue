# ============================================================
# File Name   : report_generation.py
# Description:
#   问数结果报告生成共享服务。
#
# Responsibilities:
#   - 复用同一套报告 Prompt、结果压缩和 Token 统计逻辑。
#   - 支持 SubAgent 节点和 LeadAgent 控制面分别生成最终自然语言回答。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

from __future__ import annotations

import re
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.graph.llm import get_llm
from app.prompts.report_generate import build_report_system
from app.services.observability.prompts import get_prompt_manager
from app.services.observability.tracer import get_observability_tracer
from app.utils import extract_token_usage, merge_token_usage

REPORT_RESULT_MAX_ROWS = 30
REPORT_CELL_MAX_CHARS = 120


def _strip_think_blocks(text: str) -> str:
    """移除模型泄露的思考标签，避免最终回答污染用户可见内容。"""

    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text or "", flags=re.IGNORECASE)
    return cleaned.strip()


def _llm_thinking_enabled(llm) -> bool:
    """读取模型配置中的 Think 开关，未知客户端默认保留原始输出。"""

    return bool(getattr(llm, "datalogue_thinking_enabled", True))


def _clean_llm_content_if_needed(llm, content: Any) -> Any:
    """Think 关闭时清理模型泄露的思考标签。"""

    if _llm_thinking_enabled(llm) or not isinstance(content, str):
        return content
    return _strip_think_blocks(content)


def _compact_report_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """压缩报告生成输入，控制 LLM 上下文体量。"""

    compact_rows = []
    for row in rows[:REPORT_RESULT_MAX_ROWS]:
        compact_row: dict[str, Any] = {}
        for key, value in row.items():
            text = str(value)
            if len(text) > REPORT_CELL_MAX_CHARS:
                text = text[:REPORT_CELL_MAX_CHARS] + "..."
            compact_row[key] = text
        compact_rows.append(compact_row)
    return compact_rows, max(0, len(rows) - len(compact_rows))


def _llm_perf_metadata(
    *,
    started_at: float,
    ended_at: float,
    first_token_at: float | None = None,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成 LLM 性能观测指标，供 Langfuse metadata 展示。"""

    latency_ms = max(0, int((ended_at - started_at) * 1000))
    output_tokens = int((usage or {}).get("completion_tokens") or (usage or {}).get("output_tokens") or 0)
    metadata: dict[str, Any] = {"latency_ms": latency_ms}
    if first_token_at is not None:
        ttft_ms = max(0, int((first_token_at - started_at) * 1000))
        decode_seconds = max(ended_at - first_token_at, 0.001)
        metadata["ttft_ms"] = ttft_ms
        metadata["tps"] = round(output_tokens / decode_seconds, 2) if output_tokens else 0
    else:
        total_seconds = max(ended_at - started_at, 0.001)
        metadata["ttft_ms"] = None
        metadata["tps"] = round(output_tokens / total_seconds, 2) if output_tokens else 0
        metadata["ttft_source"] = "unavailable_non_streaming"
    return metadata


async def stream_sql_result_report(
    state: dict[str, Any],
    *,
    db: Session | None = None,
    observation_name: str = "llm.report_generator",
    report_owner: str = "subagent",
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """流式生成 SQL 结果报告。

    产出两类事件：
    - {"type": "token", "content": "..."}
    - {"type": "result", "answer": "...", "token_usage": {...}}
    """

    question = state.get("question") or ""
    sql_result = state.get("sql_result")
    if not sql_result:
        yield {
            "type": "result",
            "answer": "查询未返回结果，请检查语义层配置。",
            "token_usage": state.get("token_usage") or {},
        }
        return

    rows = sql_result.get("rows", [])
    report_rows, omitted_rows = _compact_report_rows(rows)
    summary_lines = [f"查询结果共 {len(rows)} 行，以下展开前 {len(report_rows)} 行："]
    for row in report_rows:
        parts = [f"{k}={v}" for k, v in row.items()]
        summary_lines.append("  " + ", ".join(parts))
    if omitted_rows:
        summary_lines.append(f"  （其余 {omitted_rows} 行未展开，请基于已展开样本和总行数总结趋势）")

    result_text = "\n".join(summary_lines)
    llm = get_llm(temperature=0.3, role="report", db=db)
    dataset_prompt = state.get("dataset_prompt_instructions") or ""
    report_prompt = get_prompt_manager().get_text_prompt(
        "report_generate",
        fallback=build_report_system(dataset_prompt),
    )
    system = SystemMessage(content=report_prompt.content)
    human = HumanMessage(content=f"用户问题: {question}\n\n查询结果:\n{result_text}")

    full_content = ""
    usage = None
    tracer = get_observability_tracer()
    generation = tracer.start_generation(
        name=observation_name,
        model=getattr(llm, "model_name", None) or getattr(llm, "model", None),
        messages=[system, human],
        metadata={
            "path": observation_name.removeprefix("llm."),
            "report_owner": report_owner,
            "thinking_enabled": _llm_thinking_enabled(llm),
            **(metadata or {}),
        },
    )
    started_at = time.perf_counter()
    first_token_at = None
    first_token_wall = None
    async for chunk in llm.astream([system, human]):
        content = chunk.content or ""
        if content and first_token_at is None:
            first_token_at = time.perf_counter()
            first_token_wall = datetime.now(timezone.utc)
        full_content += content
        if content:
            yield {"type": "token", "content": content}
        if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
            usage = chunk.usage_metadata

    ended_at = time.perf_counter()
    answer = _clean_llm_content_if_needed(llm, full_content)
    if usage:
        prompt = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
        completion = usage.get("output_tokens") or usage.get("completion_tokens", 0)
        total = usage.get("total_tokens", prompt + completion)
        token_usage = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }
    else:
        token_usage = extract_token_usage(
            type("LLMResponse", (), {"content": answer, "usage_metadata": None})(),
            [system, human],
        )

    merged = merge_token_usage(state.get("token_usage") or {}, token_usage or {})
    tracer.end_generation(
        generation,
        output=answer,
        usage=token_usage or {},
        completion_start_time=first_token_wall,
        metadata={
            "path": observation_name.removeprefix("llm."),
            "report_owner": report_owner,
            "thinking_enabled": _llm_thinking_enabled(llm),
            **(metadata or {}),
            **_llm_perf_metadata(
                started_at=started_at,
                ended_at=ended_at,
                first_token_at=first_token_at,
                usage=token_usage,
            ),
        },
    )
    yield {"type": "result", "answer": answer, "token_usage": merged}


async def generate_sql_result_report(
    state: dict[str, Any],
    *,
    db: Session | None = None,
    observation_name: str = "llm.report_generator",
    report_owner: str = "subagent",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """非流式收集报告生成结果，供 LangGraph 节点复用。"""

    result: dict[str, Any] | None = None
    async for event in stream_sql_result_report(
        state,
        db=db,
        observation_name=observation_name,
        report_owner=report_owner,
        metadata=metadata,
    ):
        if event.get("type") == "result":
            result = event
    return {
        "answer": (result or {}).get("answer") or "",
        "token_usage": (result or {}).get("token_usage") or state.get("token_usage"),
    }
