# ============================================================
# File Name   : agentscope_event_adapter.py
# Description:
#   AgentScope 事件验证适配器。
#
# Responsibilities:
#   - 将 DatalogueEventEnvelope 映射为 AgentScope Shell 第一阶段可验证事件。
#   - 保证 control_plane 事件不进入 AgentScope 可见事件流。
#   - 保留 trace_only 到 trace 事件的只读映射，供 Agentic Shell task stream 使用。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.bi_workbench import (
    DatalogueEventEnvelope,
    sanitize_event_payload,
)


class AgentScopeShellEvent(BaseModel):
    """AgentScope Shell 可消费的事件视图，不包含 Datalogue 控制面。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    event_type: str
    channel: str
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None


class AgentScopeEventAdapterResult(BaseModel):
    """事件映射结果；内部丢弃计数仅供测试和内部观测。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    visible_events: list[AgentScopeShellEvent] = Field(default_factory=list)
    trace_events: list[AgentScopeShellEvent] = Field(default_factory=list)
    dropped_internal_count: int = 0


class AgentScopeEventAdapter:
    """只读映射 Datalogue 事件，不承担事件生成或 SSE 输出职责。"""

    def map_events(
        self,
        envelopes: list[DatalogueEventEnvelope | dict[str, Any]],
    ) -> AgentScopeEventAdapterResult:
        visible_events: list[AgentScopeShellEvent] = []
        trace_events: list[AgentScopeShellEvent] = []
        dropped_internal_count = 0

        for item in envelopes:
            envelope = item if isinstance(item, DatalogueEventEnvelope) else DatalogueEventEnvelope(**item)
            if envelope.visibility == "control_plane":
                dropped_internal_count += 1  # control_plane 是 Datalogue 内部状态，不能交给 Shell。
                continue
            shell_event = AgentScopeShellEvent(
                event_id=envelope.event_id,
                event_type=envelope.event_type,
                channel=(
                    "shell_visible"
                    if envelope.visibility == "user_visible"
                    else "trace"
                ),
                payload=sanitize_event_payload(envelope.payload) or {},  # trace 也只暴露验证摘要，避免旧 payload 夹带敏感键。
                trace_id=envelope.trace_id,
            )
            if envelope.visibility == "user_visible":
                visible_events.append(shell_event)
            else:
                trace_events.append(shell_event)

        return AgentScopeEventAdapterResult(
            visible_events=visible_events,
            trace_events=trace_events,
            dropped_internal_count=dropped_internal_count,
        )
