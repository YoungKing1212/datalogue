# ============================================================
# File Name   : test_agentscope_direct_query_chain.py
# Description:
#   AgentScope 2.0 直连问数链路测试。
#
# Responsibilities:
#   - 验证 AgenticLeadAgent 与 BI Agent 都由 AgentScope Agent 创建。
#   - 验证最小直连链路不依赖 AgenticShellTask、Session/Message 和 Handoff。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import json
import inspect
from types import SimpleNamespace
from typing import Any

import pytest
from agentscope.agent import Agent
from agentscope.state import AgentState
from fastapi.testclient import TestClient

from app.agents.agentscope_model import build_agentscope_chat_model
from app.agents.agentic_lead_agent.direct_query_runner import AgenticDirectQueryRunner
from app.agents.agentic_lead_agent.react_factory import (
    AGENTIC_LEAD_AGENT_DIRECT_PROMPT,
    AgenticLeadAgentFactory,
)
from app.agents.bi_agent.react_factory import (
    BI_AGENT_DIRECT_QUERY_PROMPT,
    BIAgentFactory,
)
from app.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge
from app.bi.toolkit import build_bi_atomic_toolkit
from app.models.conversation import Conversation, ConversationState, Message
from app.services.subagent_planning import CandidateAsset, QueryPlan


async def _resolve_tool_schemas(toolkit: Any) -> list[dict[str, Any]]:
    schemas = toolkit.get_tool_schemas()
    if inspect.isawaitable(schemas):
        resolved = await schemas
    else:
        resolved = schemas
    return list(resolved)


def test_agentscope_model_factory_builds_streaming_model(db_session):
    model = build_agentscope_chat_model(db=db_session, role="lead_agent", stream=True)

    assert model is not None
    assert hasattr(model, "stream")
    assert model.stream is True


@pytest.mark.asyncio
async def test_agentic_lead_agent_factory_creates_agentscope_agent(db_session):
    agent = AgenticLeadAgentFactory(db=db_session).create()

    assert isinstance(agent, Agent)
    assert agent.name == "agentic_lead_agent"
    assert await agent._get_system_prompt() == AGENTIC_LEAD_AGENT_DIRECT_PROMPT
    assert agent.model.stream is False
    tool_schemas = await _resolve_tool_schemas(agent.toolkit)
    assert tool_schemas == []


@pytest.mark.asyncio
async def test_bi_agent_factory_creates_agentscope_agent_with_dataset_tools(db_session):
    toolkit = build_bi_atomic_toolkit(db_session, query_executor=lambda sql: [])
    bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
    session = bridge.start_session(dataset_id=12, question="统计合同总金额")

    agent = BIAgentFactory(db=db_session).create(session=session)

    assert isinstance(agent, Agent)
    assert agent.name == "bi_agent"
    assert await agent._get_system_prompt() == BI_AGENT_DIRECT_QUERY_PROMPT
    assert agent.model.stream is True
    tool_schemas = await _resolve_tool_schemas(agent.toolkit)
    tool_names = [schema["function"]["name"] for schema in tool_schemas]
    assert tool_names == [
        "get_dataset_status",
        "list_candidate_assets",
        "compile_dsl_to_sql",
        "execute_compiled_query",
        "repair_dsl",
        "create_query_artifact",
        "get_artifact_summary",
    ]


class FakeLeadAgent:
    name = "agentic_lead_agent"
    reply_payload: Any = {"selected_agent": "bi_agent", "task_type": "bi_query"}

    async def reply(self, msg):
        return self.reply_payload


class FakeBIAgent:
    name = "bi_agent"


class FakeLeadFactory:
    reply_payload: Any = {"selected_agent": "bi_agent", "task_type": "bi_query"}

    def __init__(self, *, db):
        self.db = db

    def create(self):
        agent = FakeLeadAgent()
        agent.reply_payload = self.reply_payload
        return agent


class FakeBIFactory:
    def __init__(self, *, db):
        self.db = db

    def create(self, *, session):
        return FakeBIAgent()


class FakeBridge:
    def __init__(self, *, last_error=None, expected_tool_name=None):
        self.last_error = last_error
        self.expected_tool_name = expected_tool_name
        self.start_session_called = False
        self.run_reply_stream_called = False
        self.start_session_kwargs = {}

    def start_session(self, **kwargs):
        self.start_session_called = True
        self.start_session_kwargs = kwargs
        return type(
            "FakeSession",
            (),
            {
                "artifact_ref": "artifact:direct",
                "checkpoint_ref": "checkpoint:direct",
                "last_error": self.last_error,
                "expected_tool_name": self.expected_tool_name,
                "tool_results": [],
                **kwargs,
            },
        )()

    async def run_reply_stream(self, agent, *, msg, session):
        self.run_reply_stream_called = True
        session.artifact_ref = "artifact:direct"
        session.checkpoint_ref = "checkpoint:direct"
        session.tool_results = [
            {"name": "execute_compiled_query", "row_count": 1, "column_count": 2},
            {"name": "get_artifact_summary", "summary": "合同总金额为 100 万元"},
        ]
        return []


@pytest.mark.asyncio
async def test_direct_query_runner_links_lead_agent_to_bi_agent_without_task_or_handoff(db_session):
    conversation = Conversation(title="direct query test", dataset_id=12)
    db_session.add(conversation)
    db_session.flush()
    bridge = FakeBridge()
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=FakeLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: bridge,
    )

    result = await runner.run(
        question="统计合同总金额",
        dataset_id=12,
        conversation_id=conversation.id,
        trace_id="trace-direct-001",
    )

    assert result["status"] == "completed"
    assert result["selected_agent"] == "bi_agent"
    assert result["artifact_ref"] == "artifact:direct"
    assert result["checkpoint_ref"] == "checkpoint:direct"
    assert result["row_count"] == 1
    assert result["column_count"] == 2
    assert "handoff_id" not in result
    assert "task_id" not in result
    assert "message_id" not in result
    assert bridge.start_session_kwargs["conversation_id"] == conversation.id
    assert bridge.start_session_kwargs["trace_id"] == "trace-direct-001"


@pytest.mark.asyncio
async def test_direct_query_runner_streams_agentscope_messages_and_final_result(db_session):
    bridge = FakeBridge()
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=FakeLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: bridge,
    )

    events = [
        event
        async for event in runner.stream(
            question="统计合同总金额",
            dataset_id=12,
            conversation_id=None,
            trace_id="trace-direct-stream-001",
        )
    ]

    assert [event["type"] for event in events] == [
        "agent_message",
        "agent_message",
        "agent_event",
        "agent_message",
        "agent_message",
        "agent_event",
        "agent_message",
        "agent_message",
        "final",
    ]
    assert events[0]["agent"] == "agentic_lead_agent"
    assert events[0]["role"] == "user"
    assert events[1]["role"] == "assistant"
    assert events[2]["agent"] == "bi_agent"
    assert events[3]["role"] == "user"
    assert events[4]["role"] == "assistant"
    assert events[6]["agent"] == "agentic_lead_agent"
    assert events[6]["phase"] == "final_prompt"
    assert events[7]["agent"] == "agentic_lead_agent"
    assert events[7]["phase"] == "final_response"
    assert events[-1]["agent"] == "agentic_lead_agent"
    assert events[-1]["result"]["status"] == "completed"
    assert events[-1]["result"]["summary"].startswith("## 查询结果")
    assert "- **结论**：合同总金额为 100 万元" in events[-1]["result"]["summary"]
    serialized = json.dumps(events, ensure_ascii=False)
    assert "handoff_id" not in serialized
    assert "task_id" not in serialized
    assert "message_id" not in serialized


@pytest.mark.asyncio
async def test_direct_query_runner_returns_bi_result_to_lead_agent_for_final_answer(db_session):
    class SynthesizingLeadAgent:
        name = "agentic_lead_agent"

        def __init__(self):
            self.messages: list[str] = []

        async def reply(self, msg):
            content = str(getattr(msg, "content", msg))
            self.messages.append(content)
            if "query_result" in content:
                assert "artifact:direct" in content
                assert "row_count: 1" in content
                assert "column_count: 2" in content
                return {"summary": "合同总金额为 100 万元，查询结果已生成。"}
            return {"selected_agent": "bi_agent", "task_type": "bi_query"}

    class SynthesizingLeadFactory:
        agent = SynthesizingLeadAgent()

        def __init__(self, *, db):
            self.db = db

        def create(self):
            return self.agent

    bridge = FakeBridge()
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=SynthesizingLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: bridge,
    )

    result = await runner.run(question="统计合同总金额", dataset_id=12)

    assert result["status"] == "completed"
    assert result["summary"] == "合同总金额为 100 万元，查询结果已生成。"
    assert len(SynthesizingLeadFactory.agent.messages) == 2
    assert "只能基于 BI Agent 返回的安全结果回答" in SynthesizingLeadFactory.agent.messages[1]


@pytest.mark.asyncio
async def test_direct_query_runner_passes_conversation_history_to_agentscope_lead_agent(db_session):
    """同一会话第二轮应通过 AgentScope 消息带入上一轮安全问答上下文。"""

    class HistoryAwareLeadAgent:
        name = "agentic_lead_agent"

        def __init__(self):
            self.messages: list[str] = []

        async def reply(self, msg):
            content = str(getattr(msg, "content", msg))
            self.messages.append(content)
            if len(self.messages) == 1:
                assert "历史对话摘要" in content
                assert "上一轮问题：统计合同总金额" in content
                assert "上一轮结论：合同总金额为 100 万元" in content
                assert "继续按供应商分组" in content
                assert "sum(amount)" not in content
                assert "raw_rows" not in content
                return {"selected_agent": "bi_agent", "task_type": "bi_query"}
            return {"summary": "已按上一轮合同总金额上下文继续分组。"}

    class HistoryAwareLeadFactory:
        agent = HistoryAwareLeadAgent()
        state: AgentState | None = None

        def __init__(self, *, db):
            self.db = db

        def create(self, *, state=None):
            self.__class__.state = state
            return self.agent

    conversation = Conversation(title="multi turn", dataset_id=12)
    db_session.add(conversation)
    db_session.flush()
    from app.models.conversation import Message

    db_session.add_all(
        [
            Message(
                conversation_id=conversation.id,
                role="user",
                content="统计合同总金额",
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="合同总金额为 100 万元",
                response_metadata={
                    "sql": "SELECT sum(amount) FROM contract",
                    "raw_rows": [{"amount": 1000000}],
                },
            ),
        ]
    )
    db_session.commit()

    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=HistoryAwareLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: FakeBridge(),
    )

    result = await runner.run(
        question="继续按供应商分组",
        dataset_id=12,
        conversation_id=conversation.id,
    )

    assert result["status"] == "completed"
    assert result["summary"] == "已按上一轮合同总金额上下文继续分组。"
    assert isinstance(HistoryAwareLeadFactory.state, AgentState)
    assert "上一轮问题：统计合同总金额" in HistoryAwareLeadFactory.state.summary


@pytest.mark.asyncio
async def test_direct_query_runner_serializes_full_agentscope_context_between_turns(db_session):
    """同一会话第二轮必须恢复 AgentScope context，而不是只靠 summary 文本续聊。"""

    class ContextSerializingLeadAgent:
        name = "agentic_lead_agent"

        def __init__(self, state: AgentState):
            self.state = state

        async def reply(self, msg):
            content = str(getattr(msg, "content", msg))
            self.state.context.append(msg)
            ContextSerializingLeadFactory.prompts.append(content)
            if "query_result" in content:
                summary = "合同总金额为 100 万元" if len(ContextSerializingLeadFactory.prompts) <= 2 else "已按供应商继续分组。"
                self.state.append_context(self.name, [{"type": "text", "text": json.dumps({"summary": summary}, ensure_ascii=False)}])
                return {"summary": summary}
            route_payload = {"selected_agent": "bi_agent", "task_type": "bi_query"}
            self.state.append_context(self.name, [{"type": "text", "text": json.dumps(route_payload, ensure_ascii=False)}])
            return route_payload

    class ContextSerializingLeadFactory:
        prompts: list[str] = []
        created_states: list[AgentState | None] = []

        def __init__(self, *, db):
            self.db = db

        def create(self, *, state=None):
            self.__class__.created_states.append(state)
            return ContextSerializingLeadAgent(state or AgentState())

    conversation = Conversation(title="agentscope context", dataset_id=12)
    db_session.add(conversation)
    db_session.flush()
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=ContextSerializingLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: FakeBridge(),
    )

    first_result = await runner.run(
        question="统计合同总金额",
        dataset_id=12,
        conversation_id=conversation.id,
    )
    db_session.expire_all()
    state_row = db_session.get(ConversationState, f"agentic_direct_query:{conversation.id}")
    first_capsule = state_row.subagent_capsules["agentic_direct_query"]
    first_state_payload = first_capsule["lead_agent_state"]

    assert first_result["status"] == "completed"
    assert first_capsule["version"] == 1
    assert first_capsule["agent"] == "agentic_lead_agent"
    assert len(first_state_payload["context"]) >= 4
    assert "统计合同总金额" in json.dumps(first_state_payload["context"], ensure_ascii=False)
    assert "合同总金额为 100 万元" in json.dumps(first_state_payload["context"], ensure_ascii=False)

    second_result = await runner.run(
        question="继续按供应商分组",
        dataset_id=12,
        conversation_id=conversation.id,
    )

    restored_state = ContextSerializingLeadFactory.created_states[1]
    restored_text = json.dumps(restored_state.model_dump(mode="json"), ensure_ascii=False)
    assert second_result["status"] == "completed"
    assert isinstance(restored_state, AgentState)
    assert len(restored_state.context) >= 4
    assert "统计合同总金额" in restored_text
    assert "合同总金额为 100 万元" in restored_text
    assert "历史对话摘要" not in ContextSerializingLeadFactory.prompts[2]
    db_session.expire_all()
    state_row = db_session.get(ConversationState, f"agentic_direct_query:{conversation.id}")
    assert state_row.turn_index == 2


@pytest.mark.asyncio
async def test_direct_query_runner_formats_generic_lead_final_answer_as_markdown(db_session):
    class GenericLeadAgent:
        name = "agentic_lead_agent"

        def __init__(self):
            self.messages: list[str] = []

        async def reply(self, msg):
            content = str(getattr(msg, "content", msg))
            self.messages.append(content)
            if "query_result" in content:
                assert "当前没有 ReportAgent" in content
                assert "Markdown" in content
                assert "artifact:direct" in content
                return {"summary": "查询已完成。"}
            return {"selected_agent": "bi_agent", "task_type": "bi_query"}

    class GenericLeadFactory:
        agent = GenericLeadAgent()

        def __init__(self, *, db):
            self.db = db

        def create(self):
            return self.agent

    bridge = FakeBridge()
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=GenericLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: bridge,
    )

    result = await runner.run(question="统计合同总金额", dataset_id=12)

    assert result["status"] == "completed"
    assert result["summary"].startswith("## 查询结果")
    assert "- **结论**：合同总金额为 100 万元" in result["summary"]
    assert "- **数据规模**：返回 1 行，2 列" in result["summary"]
    assert "- **结果入口**：`artifact:direct`" in result["summary"]
    assert "ReportAgent" not in result["summary"]


@pytest.mark.asyncio
async def test_direct_query_runner_logs_agent_prompts_and_outputs_without_lifecycle(
    db_session,
    monkeypatch,
    caplog,
):
    monkeypatch.setenv("AGENT_DEBUG_RAW_LOGS", "true")
    bridge = FakeBridge()
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=FakeLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: bridge,
    )

    await runner.run(
        question="统计合同总金额",
        dataset_id=12,
        conversation_id=None,
        trace_id="trace-agent-log-001",
    )

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "[datalogue.lifecycle]" not in log_text
    assert "[datalogue.agent]" in log_text
    assert '"agent": "agentic_lead_agent"' in log_text
    assert '"agent": "bi_agent"' in log_text
    assert "Datalogue AgenticLeadAgent" in log_text
    assert "Datalogue BI Agent" in log_text
    assert "统计合同总金额" in log_text
    assert '"selected_agent": "bi_agent"' in log_text
    assert '"artifact_ref": "artifact:direct"' in log_text


@pytest.mark.asyncio
async def test_direct_query_runner_drops_missing_conversation_id_before_artifact_write(db_session):
    bridge = FakeBridge()
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=FakeLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: bridge,
    )

    result = await runner.run(
        question="统计合同总金额",
        dataset_id=12,
        conversation_id=2026070201,
        trace_id="trace-direct-missing-conversation",
    )

    assert result["status"] == "completed"
    assert bridge.start_session_kwargs["conversation_id"] is None


@pytest.mark.asyncio
async def test_direct_query_runner_continues_bi_agent_when_real_model_stops_after_one_tool(
    db_session,
):
    class ContinuingBridge:
        def __init__(self):
            self.run_count = 0
            self.messages: list[str] = []

        def start_session(self, **kwargs):
            return SimpleNamespace(
                artifact_ref=None,
                checkpoint_ref=None,
                last_error=None,
                expected_tool_name="get_dataset_status",
                tool_results=[],
                **kwargs,
            )

        async def run_reply_stream(self, agent, *, msg, session):
            self.run_count += 1
            self.messages.append(str(getattr(msg, "content", msg)))
            if self.run_count == 1:
                session.tool_results.append({"name": "get_dataset_status", "status": "draft"})
                session.expected_tool_name = "list_candidate_assets"
                return []
            session.tool_results.extend(
                [
                    {"name": "execute_compiled_query", "row_count": 1, "column_count": 2},
                    {"name": "get_artifact_summary", "summary": "双周会议共有 1 条记录"},
                ]
            )
            session.artifact_ref = "artifact:continued"
            session.checkpoint_ref = "checkpoint:continued"
            session.expected_tool_name = None
            return []

    bridge = ContinuingBridge()
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=FakeLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: bridge,
    )

    result = await runner.run(question="统计双周会议数据记录数量", dataset_id=12)

    assert result["status"] == "completed"
    assert result["artifact_ref"] == "artifact:continued"
    assert result["summary"].startswith("## 查询结果")
    assert "- **结论**：双周会议共有 1 条记录" in result["summary"]
    assert bridge.run_count == 2
    assert "当前必须调用的下一个工具: list_candidate_assets" in bridge.messages[1]


@pytest.mark.asyncio
async def test_direct_query_runner_completes_dataset_tail_without_waiting_for_model(db_session):
    class TailBridge:
        def __init__(self):
            self.reply_stream_count = 0
            self.direct_query_called = False

        def start_session(self, **kwargs):
            return SimpleNamespace(
                artifact_ref=None,
                checkpoint_ref=None,
                last_error=None,
                expected_tool_name="get_dataset_status",
                tool_results=[],
                **kwargs,
            )

        async def run_reply_stream(self, agent, *, msg, session):
            self.reply_stream_count += 1
            if self.reply_stream_count == 1:
                session.tool_results.append({"name": "get_dataset_status", "status": "draft"})
                session.expected_tool_name = "list_candidate_assets"
                return []
            session.tool_results.append({"name": "list_candidate_assets", "status": "ready"})
            session.expected_tool_name = "compile_dsl_to_sql"
            return []

        async def run_direct_query(self, *, session, dsl):
            self.direct_query_called = True
            assert dsl == {}
            session.tool_results.extend(
                [
                    {"name": "compile_dsl_to_sql", "status": "compiled"},
                    {"name": "execute_compiled_query", "row_count": 3, "column_count": 2},
                    {"name": "get_artifact_summary", "summary": "双周会议共有 3 条记录"},
                ]
            )
            session.artifact_ref = "artifact:tail"
            session.checkpoint_ref = "checkpoint:tail"
            session.expected_tool_name = None
            return {"status": "completed"}

    bridge = TailBridge()
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=FakeLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: bridge,
    )

    result = await runner.run(question="统计双周会议数据记录数量", dataset_id=12)

    assert result["status"] == "completed"
    assert result["artifact_ref"] == "artifact:tail"
    assert result["row_count"] == 3
    assert result["summary"].startswith("## 查询结果")
    assert "- **结论**：双周会议共有 3 条记录" in result["summary"]
    assert bridge.reply_stream_count == 2
    assert bridge.direct_query_called is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply_payload",
    [
        {"selected_agent": "report_agent", "task_type": "report"},
        "无法判断，请转人工。",
        {"selected_agent": "bi_agent"},
        {"selected_agent": "bi_agent", "task_type": "report"},
    ],
)
async def test_direct_query_runner_blocks_non_bi_or_invalid_lead_route_without_bridge(
    db_session,
    reply_payload,
):
    class BlockingLeadFactory(FakeLeadFactory):
        pass

    BlockingLeadFactory.reply_payload = reply_payload
    bridge = FakeBridge()
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=BlockingLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: bridge,
    )

    result = await runner.run(question="统计合同总金额", dataset_id=12)

    assert result["status"] == "blocked"
    assert result["code"] == "LEAD_AGENT_ROUTE_BLOCKED"
    assert bridge.start_session_called is False
    assert bridge.run_reply_stream_called is False
    assert "handoff_id" not in result
    assert "task_id" not in result
    assert "message_id" not in result


@pytest.mark.asyncio
async def test_direct_query_runner_blocks_markdown_wrapped_lead_json_without_task_type(db_session):
    class MarkdownLeadFactory(FakeLeadFactory):
        reply_payload = SimpleNamespace(
            content='路由结果如下：\n```json\n{"selected_agent": "bi_agent"}\n```'
        )

    bridge = FakeBridge()
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=MarkdownLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: bridge,
    )

    result = await runner.run(question="统计合同总金额", dataset_id=12)

    assert result["status"] == "blocked"
    assert result["selected_agent"] == "bi_agent"
    assert result["code"] == "LEAD_AGENT_ROUTE_BLOCKED"
    assert bridge.start_session_called is False
    assert bridge.run_reply_stream_called is False


@pytest.mark.asyncio
async def test_direct_query_runner_blocks_session_with_last_error_even_with_artifact(db_session):
    bridge = FakeBridge(last_error={"code": "FIELD_NOT_FOUND"})
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=FakeLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: bridge,
    )

    result = await runner.run(question="统计合同总金额", dataset_id=12)

    assert result["status"] == "blocked"
    assert result["code"] == "FIELD_NOT_FOUND"
    assert result["artifact_ref"] == "artifact:direct"


@pytest.mark.asyncio
async def test_direct_query_runner_blocks_incomplete_dataset_toolchain(db_session):
    bridge = FakeBridge(expected_tool_name="get_artifact_summary")
    runner = AgenticDirectQueryRunner(
        db=db_session,
        lead_agent_factory=FakeLeadFactory,
        bi_agent_factory=FakeBIFactory,
        bridge_factory=lambda db: bridge,
    )

    result = await runner.run(question="统计合同总金额", dataset_id=12)

    assert result["status"] == "blocked"
    assert result["code"] == "DATASET_TOOLCHAIN_INCOMPLETE"
    assert result["expected_tool"] == "get_artifact_summary"


def _assert_no_internal_response_keys(payload):
    serialized = str(payload).lower()
    for token in (
        "sql",
        "schema",
        "raw rows",
        "raw_rows",
        "compiled_query_ref",
        "query plan",
        "query_plan",
        "physical plan",
        "physical_plan",
        "expected_tool",
        "task_id",
        "handoff_id",
        "message_id",
        "session_id",
    ):
        assert token not in serialized


def test_agentic_lead_agent_direct_query_api_returns_safe_result(monkeypatch):
    captured_kwargs = {}

    class FakeRunner:
        def __init__(self, *, db):
            self.db = db

        async def run(self, **kwargs):
            captured_kwargs.update(kwargs)
            return {
                "status": "completed",
                "selected_agent": "bi_agent",
                "summary": "合同总金额为 100 万元",
                "artifact_ref": "artifact:direct",
                "checkpoint_ref": "checkpoint:direct",
                "row_count": 1,
                "column_count": 2,
            }

    from app.main import app

    monkeypatch.setattr(
        "app.api.agentic_lead_agent.AgenticDirectQueryRunner",
        FakeRunner,
    )
    client = TestClient(app)

    response = client.post(
        "/api/agentic-lead-agent/direct-query",
        json={
            "question": "统计合同总金额",
            "dataset_id": 12,
            "conversation_id": 34,
            "trace_id": "trace-direct-001",
        },
    )

    assert response.status_code == 200
    assert captured_kwargs == {
        "question": "统计合同总金额",
        "dataset_id": 12,
        "conversation_id": 34,
        "trace_id": "trace-direct-001",
    }
    assert response.json() == {
        "status": "completed",
        "selected_agent": "bi_agent",
        "summary": "合同总金额为 100 万元",
        "artifact_ref": "artifact:direct",
        "checkpoint_ref": "checkpoint:direct",
        "row_count": 1,
        "column_count": 2,
    }


def test_agentic_lead_agent_direct_query_api_passes_model_config_id(monkeypatch):
    captured_kwargs = {}

    class FakeRunner:
        def __init__(self, *, db):
            self.db = db

        async def run(self, **kwargs):
            captured_kwargs.update(kwargs)
            return {
                "status": "completed",
                "selected_agent": "bi_agent",
                "summary": "指定模型查询完成",
            }

    from app.main import app

    monkeypatch.setattr(
        "app.api.agentic_lead_agent.AgenticDirectQueryRunner",
        FakeRunner,
    )
    client = TestClient(app)

    response = client.post(
        "/api/agentic-lead-agent/direct-query",
        json={
            "question": "统计合同总金额",
            "dataset_id": 12,
            "model_config_id": 8,
        },
    )

    assert response.status_code == 200
    assert captured_kwargs["question"] == "统计合同总金额"
    assert captured_kwargs["model_config_id"] == 8


def test_agentic_lead_agent_direct_query_stream_api_returns_sse_events(monkeypatch):
    captured_kwargs = {}

    class FakeRunner:
        def __init__(self, *, db):
            self.db = db

        async def stream(self, **kwargs):
            captured_kwargs.update(kwargs)
            yield {
                "type": "agent_message",
                "event_type": "agent.message",
                "agent": "agentic_lead_agent",
                "role": "user",
                "phase": "prompt",
                "title": "AgenticLeadAgent 输入",
                "content": "正在判断任务类型并选择业务 Agent。",
            }
            yield {
                "type": "agent_message",
                "event_type": "agent.message",
                "agent": "bi_agent",
                "role": "assistant",
                "phase": "response",
                "title": "BI Agent 返回",
                "content": "已完成 Dataset 工具链查询。",
            }
            yield {
                "type": "final",
                "event_type": "message.completed",
                "result": {
                    "status": "completed",
                    "selected_agent": "bi_agent",
                    "summary": "## 查询结果\n\n- **结论**：合同总金额为 100 万元",
                    "artifact_ref": "artifact:direct",
                    "checkpoint_ref": "checkpoint:direct",
                    "row_count": 1,
                    "column_count": 2,
                    "expected_tool": "get_artifact_summary",
                },
            }

    from app.main import app

    monkeypatch.setattr(
        "app.api.agentic_lead_agent.AgenticDirectQueryRunner",
        FakeRunner,
    )
    client = TestClient(app, raise_server_exceptions=False)

    with client.stream(
        "POST",
        "/api/agentic-lead-agent/direct-query/stream",
        json={
            "question": "统计合同总金额",
            "dataset_id": 12,
            "conversation_id": 34,
            "trace_id": "trace-direct-stream-api",
        },
    ) as response:
        lines = [line for line in response.iter_lines() if line.startswith("data:")]

    assert captured_kwargs == {
        "question": "统计合同总金额",
        "dataset_id": 12,
        "conversation_id": 34,
        "trace_id": "trace-direct-stream-api",
    }
    payloads = [json.loads(line.removeprefix("data:").strip()) for line in lines]
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert [payload["type"] for payload in payloads] == ["agent_message", "agent_message", "final"]
    assert payloads[-1]["answer"].startswith("## 查询结果")
    assert "- **结论**：合同总金额为 100 万元" in payloads[-1]["answer"]
    assert payloads[-1]["result_ref"] == "artifact:direct"
    assert "expected_tool" not in json.dumps(payloads[-1], ensure_ascii=False)


def test_agentic_lead_agent_direct_query_stream_api_never_returns_generic_completed_answer(monkeypatch):
    class FakeRunner:
        def __init__(self, *, db):
            self.db = db

        async def stream(self, **kwargs):
            yield {
                "type": "final",
                "event_type": "message.completed",
                "result": {
                    "status": "completed",
                    "selected_agent": "bi_agent",
                    "summary": None,
                    "artifact_ref": "artifact:direct",
                    "checkpoint_ref": "checkpoint:direct",
                    "row_count": 1,
                    "column_count": 2,
                },
            }

    from app.main import app

    monkeypatch.setattr(
        "app.api.agentic_lead_agent.AgenticDirectQueryRunner",
        FakeRunner,
    )
    client = TestClient(app, raise_server_exceptions=False)

    with client.stream(
        "POST",
        "/api/agentic-lead-agent/direct-query/stream",
        json={"question": "统计合同总金额", "dataset_id": 12},
    ) as response:
        lines = [line for line in response.iter_lines() if line.startswith("data:")]

    payload = json.loads(lines[-1].removeprefix("data:").strip())
    assert response.status_code == 200
    assert payload["answer"].startswith("## 查询结果")
    assert "查询已完成。" not in payload["answer"]
    assert "- **数据规模**：返回 1 行，2 列" in payload["answer"]
    assert "- **结果入口**：`artifact:direct`" in payload["answer"]


def test_agentic_lead_agent_direct_query_stream_api_persists_visible_messages(
    monkeypatch,
    client,
    db_session,
):
    conversation = Conversation(title="direct stream history", dataset_id=12)
    db_session.add(conversation)
    db_session.flush()

    class FakeRunner:
        def __init__(self, *, db):
            self.db = db

        async def stream(self, **kwargs):
            yield {
                "type": "final",
                "event_type": "message.completed",
                "trace_id": kwargs.get("trace_id"),
                "result": {
                    "status": "completed",
                    "selected_agent": "bi_agent",
                    "summary": "## 查询结果\n\n- **结论**：合同总金额为 100 万元",
                    "artifact_ref": "artifact:direct",
                    "checkpoint_ref": "checkpoint:direct",
                    "row_count": 1,
                    "column_count": 2,
                    "raw_rows": [{"amount": 100}],
                },
            }

    monkeypatch.setattr(
        "app.api.agentic_lead_agent.AgenticDirectQueryRunner",
        FakeRunner,
    )

    with client.stream(
        "POST",
        "/api/agentic-lead-agent/direct-query/stream",
        json={
            "question": "统计合同总金额",
            "dataset_id": 12,
            "conversation_id": conversation.id,
            "trace_id": "trace-direct-stream-history",
        },
    ) as response:
        lines = [line for line in response.iter_lines() if line.startswith("data:")]

    assert response.status_code == 200
    assert json.loads(lines[-1].removeprefix("data:").strip())["answer"].startswith("## 查询结果")

    messages = (
        db_session.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.id.asc())
        .all()
    )
    assert [(message.role, message.content) for message in messages] == [
        ("user", "统计合同总金额"),
        ("assistant", "## 查询结果\n\n- **结论**：合同总金额为 100 万元"),
    ]
    assert messages[-1].response_metadata == {
        "type": "agentic_direct_query",
        "trace_id": "trace-direct-stream-history",
        "status": "completed",
        "selected_agent": "bi_agent",
        "artifact_ref": "artifact:direct",
        "checkpoint_ref": "checkpoint:direct",
        "row_count": 1,
        "column_count": 2,
    }


@pytest.mark.parametrize(
    "runner_result",
    [
        {
            "status": "blocked",
            "selected_agent": "bi_agent",
            "code": "DATASET_TOOLCHAIN_INCOMPLETE",
            "expected_tool": "get_artifact_summary",
            "task_id": "task-agentic-1",
            "handoff_id": "handoff-1",
            "message_id": "message-1",
            "session_id": "session-1",
        },
        {
            "status": "blocked",
            "selected_agent": "",
            "code": "LEAD_AGENT_ROUTE_BLOCKED",
            "raw_rows": [{"amount": 100}],
            "schema": {"tables": ["contracts"]},
            "compiled_query_ref": "compiled_query:unsafe",
        },
    ],
)
def test_agentic_lead_agent_direct_query_api_projects_blocked_result_to_safe_fields(
    monkeypatch,
    runner_result,
):
    class FakeRunner:
        def __init__(self, *, db):
            self.db = db

        async def run(self, **kwargs):
            return runner_result

    from app.main import app

    monkeypatch.setattr(
        "app.api.agentic_lead_agent.AgenticDirectQueryRunner",
        FakeRunner,
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/agentic-lead-agent/direct-query",
        json={"question": "统计合同总金额", "dataset_id": 12},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert set(payload).issubset(
        {
            "status",
            "selected_agent",
            "summary",
            "artifact_ref",
            "checkpoint_ref",
            "row_count",
            "column_count",
        }
    )
    _assert_no_internal_response_keys(payload)


@pytest.mark.parametrize(
    "unsafe_summary",
    [
        "SQL: SELECT * FROM contracts; schema_context 含 raw rows 和 compiled_query_ref",
        "query_plan: {scan: contracts}",
        "physical_plan: scan contracts",
    ],
)
def test_agentic_lead_agent_direct_query_api_redacts_unsafe_summary(monkeypatch, unsafe_summary):
    class FakeRunner:
        def __init__(self, *, db):
            self.db = db

        async def run(self, **kwargs):
            return {
                "status": "completed",
                "selected_agent": "bi_agent",
                "summary": unsafe_summary,
                "artifact_ref": "artifact:direct",
                "checkpoint_ref": "checkpoint:direct",
                "row_count": 1,
                "column_count": 2,
                "expected_tool": "get_artifact_summary",
            }

    from app.main import app

    monkeypatch.setattr(
        "app.api.agentic_lead_agent.AgenticDirectQueryRunner",
        FakeRunner,
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/agentic-lead-agent/direct-query",
        json={"question": "统计合同总金额", "dataset_id": 12},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == "查询已完成，结果摘要因包含内部执行信息已被隐藏。"
    _assert_no_internal_response_keys(payload)


def test_agentic_lead_agent_direct_query_api_redacts_schema_context_summary(monkeypatch):
    class FakeRunner:
        def __init__(self, *, db):
            self.db = db

        async def run(self, **kwargs):
            return {
                "status": "completed",
                "selected_agent": "bi_agent",
                "summary": "schema_context: contracts table fields",
                "artifact_ref": "artifact:direct",
                "checkpoint_ref": "checkpoint:direct",
                "row_count": 1,
                "column_count": 2,
            }

    from app.main import app

    monkeypatch.setattr(
        "app.api.agentic_lead_agent.AgenticDirectQueryRunner",
        FakeRunner,
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/agentic-lead-agent/direct-query",
        json={"question": "统计合同总金额", "dataset_id": 12},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == "查询已完成，结果摘要因包含内部执行信息已被隐藏。"
    assert payload["summary"] != "schema_context: contracts table fields"
    _assert_no_internal_response_keys(payload)


def test_agentic_lead_agent_direct_query_api_commits_artifact_transaction(monkeypatch):
    class FakeDb:
        def __init__(self):
            self.commit_count = 0

        def commit(self):
            self.commit_count += 1

    class FakeRunner:
        def __init__(self, *, db):
            self.db = db

        async def run(self, **kwargs):
            return {
                "status": "completed",
                "selected_agent": "bi_agent",
                "summary": "查询已完成。",
                "artifact_ref": "artifact:direct",
                "row_count": 1,
                "column_count": 2,
            }

    from app.api.agentic_lead_agent import get_db as direct_query_get_db
    from app.main import app

    fake_db = FakeDb()

    def override_get_db():
        yield fake_db

    monkeypatch.setattr(
        "app.api.agentic_lead_agent.AgenticDirectQueryRunner",
        FakeRunner,
    )
    app.dependency_overrides[direct_query_get_db] = override_get_db
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/agentic-lead-agent/direct-query",
            json={"question": "统计合同总金额", "dataset_id": 12},
        )
    finally:
        app.dependency_overrides.pop(direct_query_get_db, None)

    assert response.status_code == 200
    assert response.json()["artifact_ref"] == "artifact:direct"
    assert fake_db.commit_count == 1


def test_compile_dsl_to_sql_falls_back_to_runtime_planner(monkeypatch, db_session):
    captured = {}

    def fake_plan_query(**kwargs):
        captured["planner_kwargs"] = kwargs
        return QueryPlan(
            query_type="metric_query",
            execution_strategy="query_graph",
            confidence=0.62,
            selected_assets=[
                CandidateAsset(
                    asset_type="field",
                    asset_id="meeting_records.id",
                    name="id",
                    display_name="记录ID",
                    source="schema",
                    confidence=0.68,
                    metadata={"table_name": "meeting_records", "column_name": "id"},
                    usage="selected",
                )
            ],
        )

    def fake_compile_query_plan_to_sql(**kwargs):
        captured["compiled_plan"] = kwargs["query_plan"]
        return {
            "ok": True,
            "dialect": "sqlite",
            "execution_source": "tool_compiler",
            "sql": "SELECT meeting_records.id AS id FROM meeting_records",
            "sql_list": ["SELECT meeting_records.id AS id FROM meeting_records"],
            "sql_guard": {"ok": True},
            "warnings": [],
        }

    monkeypatch.setattr("app.bi.toolkit.atomic.plan_query", fake_plan_query)
    monkeypatch.setattr("app.bi.toolkit.atomic.compile_query_plan_to_sql", fake_compile_query_plan_to_sql)
    toolkit = build_bi_atomic_toolkit(db_session, query_executor=lambda _sql: {"rows": []})

    result = toolkit.execute_tool(
        "compile_dsl_to_sql",
        dataset_id=12,
        question="统计双周会议数据记录数量",
        dsl={"bad": True},
        sql_generation_context={
            "table_schemas": [
                {
                    "table_name": "sys_dict_data",
                    "fields": [{"name": "dict_code", "column_name": "dict_code", "display_name": "字典编码"}],
                },
                {
                    "table_name": "meeting_records",
                    "fields": [{"name": "id", "column_name": "id", "display_name": "记录ID"}],
                }
            ]
        },
        dialect="sqlite",
        allowed_tables=["meeting_records"],
    )

    assert result["status"] == "compiled"
    assert result["compiled_query_ref"].startswith("compiled_query:")
    assert captured["planner_kwargs"]["routing"] == {"dataset_id": 12}
    assert captured["planner_kwargs"]["question"] == "统计双周会议数据记录数量"
    candidate_assets = captured["planner_kwargs"]["candidate_assets"]["assets"]
    assert candidate_assets[0]["asset_type"] == "table"
    assert {asset["metadata"]["table_name"] for asset in candidate_assets} == {"meeting_records"}
    assert captured["compiled_plan"].execution_strategy == "query_graph"
