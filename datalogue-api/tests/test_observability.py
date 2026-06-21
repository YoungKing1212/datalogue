# ============================================================
# File Name   : test_observability.py
# Description:
#   Langfuse 可观测封装和反馈接口测试。
#
# Responsibilities:
#   - 验证 no-op/异常降级、脱敏和本地报表聚合。
#   - 覆盖消息反馈写本地 metadata 的闭环。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

import asyncio
import contextvars

from app import models
from app.core.config import Settings
from app.services.observability.context import (
    ObservabilityRequestContext,
    current_observability_context,
    set_observability_context,
)
from app.services.observability.masking import sanitize_payload, sanitize_sql, sanitize_text
from app.services.observability.prompt_registry import (
    RegisteredPrompt,
    get_registered_prompts,
    sync_registered_prompts,
)
from app.services.observability.tracer import (
    DatalogueTracer,
    ObservabilityTraceContext,
    build_langfuse_trace_url,
)
from app.services.runner import DatasetSubAgentRequest, InProcessDatasetSubAgentRunner
from app.utils.token import extract_token_usage


def test_masking_hides_sensitive_values():
    assert "<phone>" in sanitize_text("联系人 13812345678")
    assert "password=<masked>" in sanitize_text("password=abc123")
    assert "华东" not in sanitize_sql("select * from t where region = '华东'")
    payload = sanitize_payload({"api_key": "sk-xxx", "rows": [{"name": "张三"}]})
    assert payload["api_key"] == "<masked>"
    assert payload["rows"]["row_count"] == 1


def test_tracer_disabled_returns_noop_context():
    tracer = DatalogueTracer(
        Settings(
            LANGFUSE_ENABLED=False,
            LANGFUSE_BASE_URL="http://localhost:3000",
            LANGFUSE_PROJECT_ID="project-1",
        )
    )
    ctx = tracer.create_trace_context(
        conversation_id=1,
        dataset_id=2,
        user_id="1",
        tenant_id="default",
        question="最近30天GMV是多少",
    )
    assert ctx.enabled is False
    assert ctx.active is False
    assert ctx.trace_id
    assert ctx.trace_url == f"http://localhost:3000/project/project-1/traces/{ctx.trace_id}"


def test_trace_context_accepts_business_session_id():
    """Langfuse session_id 应可使用业务 session_id，而不是只能用 conversation_id。"""

    tracer = DatalogueTracer(Settings(LANGFUSE_ENABLED=False))
    ctx = tracer.create_trace_context(
        conversation_id=1,
        dataset_id=2,
        user_id="1",
        tenant_id="default",
        question="最近30天GMV是多少",
        session_id="business-session-1",
    )

    assert ctx.session_id == "business-session-1"


def test_langfuse_trace_url_builder():
    assert (
        build_langfuse_trace_url(
            base_url="http://localhost:3000/",
            project_id="project 1",
            trace_id="trace/1",
        )
        == "http://localhost:3000/project/project%201/traces/trace%2F1"
    )
    assert build_langfuse_trace_url(base_url="http://localhost:3000", project_id=None, trace_id="t") is None


def test_set_observability_context_tolerates_cross_context_reset():
    """SSE 流式响应在客户端断连时会在另一个 asyncio Context 中触发 cleanup，
    `ContextVar.reset(token)` 必须降级处理，避免污染日志或中断关闭流程。"""

    request_context = ObservabilityRequestContext(
        trace_id="trace-cross-context",
        session_id="session-cross-context",
        conversation_id=1,
        dataset_id=2,
        user_id="1",
        tenant_id="default",
    )

    cm = set_observability_context(request_context)
    cm.__enter__()
    assert current_observability_context.get() is request_context

    # 在另一个 Context 副本里关闭 contextmanager，模拟 aclose 落在 cleanup task 的场景
    isolated_context = contextvars.copy_context()
    isolated_context.run(cm.__exit__, None, None, None)


def test_token_usage_estimates_when_provider_usage_missing():
    """模型未返回 usage_metadata 时，本地估算 usage，避免观测里全是 0。"""

    response = type("LLMResponse", (), {"content": "综合评分较高。", "usage_metadata": None})()
    message = type("Message", (), {"type": "human", "content": "供应商综合评估与分级排名"})()

    usage = extract_token_usage(response, [message])

    assert usage["prompt_tokens"] > 0
    assert usage["completion_tokens"] > 0
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    assert usage["usage_source"] == "estimated"


def test_prompt_registry_contains_runtime_prompt_names():
    """脚本应覆盖运行期已在 Langfuse 拉取的 prompt 名称。"""

    names = {item.name for item in get_registered_prompts()}

    assert "report_generate" in names
    assert "sql_audit" in names
    assert "lead_agent_skill_selector" in names
    assert "lead_agent_tool_planner" in names
    assert "datalogue-compaction" in names
    assert "dsl_generate_real_schema" in names


def test_sync_registered_prompts_skips_unchanged_and_creates_changed():
    """同步脚本应避免未变化 prompt 反复创建版本，除非显式 force。"""

    created = []

    class RemotePrompt:
        def __init__(self, prompt, config=None):
            self.prompt = prompt
            self.version = 7
            self.config = config or {}

    class FakeClient:
        def get_prompt(self, name, **_kwargs):
            if name == "same_prompt":
                return RemotePrompt(
                    "same",
                    {
                        "display_name": "相同 Prompt",
                        "chinese_name": "相同 Prompt",
                        "chinese_description": "相同",
                        "description": "相同",
                        "variables": [],
                        "prompt_pack_version": "2026-06-12-current",
                    },
                )
            return RemotePrompt("old")

        def create_prompt(self, **kwargs):
            created.append(kwargs)
            return type("CreatedPrompt", (), {"version": 8})()

    prompts = [
        RegisteredPrompt(
            name="same_prompt",
            display_name="相同 Prompt",
            prompt="same",
            description="相同",
        ),
        RegisteredPrompt(
            name="changed_prompt",
            display_name="变化 Prompt",
            prompt="changed",
            description="变化",
        ),
    ]

    results = sync_registered_prompts(
        FakeClient(),
        prompts=prompts,
        label="production",
        apply=True,
    )

    assert results[0]["action"] == "skipped"
    assert results[0]["version"] == 7
    assert results[1]["action"] == "created"
    assert results[1]["display_name"] == "变化 Prompt"
    assert results[1]["description"] == "变化"
    assert created[0]["name"] == "changed_prompt"
    assert created[0]["labels"] == ["production"]
    assert created[0]["config"]["chinese_name"] == "变化 Prompt"
    assert created[0]["config"]["chinese_description"] == "变化"


def test_langfuse_observation_names_are_chinese():
    """Langfuse 展示名用中文，内部技术名保留在 metadata。"""

    calls = []
    updates = []

    class DummyObservation:
        def update(self, **kwargs):
            updates.append(kwargs)

    class DummyManager:
        def __init__(self, kwargs):
            self.kwargs = kwargs
            self.observation = DummyObservation()

        def __enter__(self):
            calls.append(self.kwargs)
            return self.observation

        def __exit__(self, *_args):
            return None

    class DummyClient:
        def start_as_current_observation(self, **kwargs):
            return DummyManager(kwargs)

    tracer = DatalogueTracer(
        Settings(LANGFUSE_ENABLED=True),
        client=DummyClient(),
    )
    ctx = ObservabilityTraceContext(
        trace_id="trace-1",
        session_id="session-1",
        conversation_id=1,
        dataset_id=2,
        user_id="1",
        tenant_id="default",
        question="供应商综合评估",
        active=True,
        enabled=True,
    )

    tracer.start_span(ctx, node="dsl_generate", display_name="DSL 生成")
    tracer.record_generation(
        name="llm.sql_audit",
        model="MiniMax-M3",
        messages=[],
        output="{}",
        usage={"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        metadata={"path": "sql_audit", "latency_ms": 1200, "ttft_ms": 300, "tps": 12.5},
    )

    assert calls[0]["name"] == "DSL 生成"
    assert calls[0]["metadata"]["technical_name"] == "node.dsl_generate"
    assert calls[1]["name"] == "llm.sql_audit"
    assert calls[1]["metadata"]["technical_name"] == "llm.sql_audit"
    assert updates[0]["usage_details"] == {"input": 11, "output": 7, "total": 18}
    assert updates[0]["metadata"]["usage_source"] == "provider"
    assert updates[0]["metadata"]["ttft_ms"] == 300
    assert updates[0]["metadata"]["tps"] == 12.5


def test_trace_tags_mark_lead_and_subagent():
    """根 Trace 标记 lead，SubAgent span 可追加 sub/dataset 标签。"""

    observations = []
    trace_updates = []

    class DummyObservation:
        def update(self, **_kwargs):
            return None

        def update_trace(self, **kwargs):
            trace_updates.append(kwargs)

    class DummyManager:
        def __init__(self, kwargs):
            self.kwargs = kwargs
            self.observation = DummyObservation()

        def __enter__(self):
            observations.append(self.kwargs)
            return self.observation

        def __exit__(self, *_args):
            return None

    class DummyClient:
        def start_as_current_observation(self, **kwargs):
            return DummyManager(kwargs)

    tracer = DatalogueTracer(
        Settings(
            LANGFUSE_ENABLED=True,
            LANGFUSE_ENVIRONMENT="test",
            LANGFUSE_RELEASE="r1",
        ),
        client=DummyClient(),
    )

    ctx = tracer.create_trace_context(
        conversation_id=1,
        dataset_id=7,
        user_id="1",
        tenant_id="default",
        question="GMV是多少",
    )
    tracer.start_span(
        ctx,
        node="subagent.7",
        display_name="SubAgent · 7",
        trace_tags=["sub", "dataset:7"],
    )

    assert trace_updates[0]["tags"] == ["tenant:default", "env:test", "release:r1", "lead"]
    assert trace_updates[1]["tags"] == [
        "tenant:default",
        "env:test",
        "release:r1",
        "lead",
        "sub",
        "dataset:7",
    ]
    assert observations[1]["metadata"]["technical_name"] == "node.subagent.7"


def test_in_process_subagent_runner_wraps_graph_span(monkeypatch):
    """Runner 应包裹 subagent.{dataset_id} span，并透传 LangGraph 事件。"""

    calls = []

    class DummyTracer:
        def start_span(self, trace_context, **kwargs):
            calls.append(("start", trace_context, kwargs))

        def end_span(self, trace_context, **kwargs):
            calls.append(("end", trace_context, kwargs))

    class DummyGraph:
        async def astream_events(self, initial_state, **kwargs):
            yield {"event": "on_chain_end", "data": {"output": initial_state}, "kwargs": kwargs}

    monkeypatch.setattr(
        "app.services.runner.get_observability_tracer",
        lambda: DummyTracer(),
    )
    runner = InProcessDatasetSubAgentRunner(DummyGraph(), db=None)
    request = DatasetSubAgentRequest(
        question="GMV是多少",
        dataset_id=7,
        manifest_version="v1",
        bound_schema_version="schema-1",
        thread_id="thread-1",
        time_context={},
        thread_context={},
        route_decision={},
        schema_status={},
        lead_agent_context={},
        trace_id="trace-1",
    )

    async def collect_events():
        return [
            event
            async for event in runner.run(
                request,
                trace_context=object(),
                initial_state={"question": "GMV是多少"},
                dataset_name="销售数据集",
                version="v2",
            )
        ]

    events = asyncio.run(collect_events())

    assert events[0]["kwargs"]["version"] == "v2"
    assert calls[0][2]["node"] == "subagent.7"
    assert calls[0][2]["display_name"] == "subagent.7"
    assert calls[0][2]["trace_tags"] == ["sub", "dataset:7"]
    assert calls[1][2]["node"] == "subagent.7"


def test_in_process_subagent_runner_records_delta_merge_span(monkeypatch):
    """Runner 监听 merge_prior_context 结束事件，记录 delta-merge span。"""

    calls = []

    class DummyTracer:
        def start_span(self, trace_context, **kwargs):
            calls.append(("start", kwargs))

        def end_span(self, trace_context, **kwargs):
            calls.append(("end", kwargs))

    class DummyGraph:
        async def astream_events(self, initial_state, **kwargs):
            yield {
                "event": "on_chain_end",
                "metadata": {"langgraph_node": "merge_prior_context"},
                "data": {
                    "output": {
                        "turn_type": "continue",
                        "multiturn_context": {"delta_type": "drill"},
                        "merge_debug": {"used_prior": True},
                    }
                },
            }

    monkeypatch.setattr(
        "app.services.runner.get_observability_tracer",
        lambda: DummyTracer(),
    )
    runner = InProcessDatasetSubAgentRunner(DummyGraph(), db=None)
    request = DatasetSubAgentRequest(
        question="按地区拆分",
        dataset_id=7,
        manifest_version="v1",
        bound_schema_version="schema-1",
        thread_id="thread-1",
        time_context={},
        thread_context={},
        route_decision={},
        schema_status={},
        lead_agent_context={},
        prior_capsule={"query_context": {"metrics": ["gmv"]}},
        prior_capsule_status={"status": "loaded"},
        trace_id="trace-1",
    )

    async def collect_events():
        return [
            event
            async for event in runner.run(
                request,
                trace_context=object(),
                initial_state={
                    "question": "按地区拆分",
                    "prior_capsule": {"query_context": {"metrics": ["gmv"]}},
                },
            )
        ]

    asyncio.run(collect_events())

    delta_start = [item for item in calls if item[1].get("node") == "delta-merge" and item[0] == "start"]
    delta_end = [item for item in calls if item[1].get("node") == "delta-merge" and item[0] == "end"]
    assert delta_start
    assert delta_start[0][1]["input_payload"]["prior_query_context"] == {"metrics": ["gmv"]}
    assert delta_end[0][1]["output_payload"]["multiturn_context"]["delta_type"] == "drill"


def test_message_feedback_updates_metadata(client, db_session, monkeypatch):
    class DummyTracer:
        def score_trace(self, **_kwargs):
            return False

    monkeypatch.setattr(
        "app.services.observability.feedback.get_observability_tracer",
        lambda: DummyTracer(),
    )

    conv = models.Conversation(title="反馈测试", thread_id="feedback-test", user_id=1)
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    msg = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content="回答内容",
        response_metadata={"langfuse": {"trace_id": "trace-test", "session_id": "session-test"}},
    )
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(msg)

    resp = client.post(
        f"/api/messages/{msg.id}/feedback",
        json={"message_id": msg.id, "action": "reject", "comment": "口径不对"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["partial_success"] is True
    db_session.refresh(msg)
    assert msg.response_metadata["feedback"]["action"] == "reject"


def test_observability_report_api(client, db_session, sample_dataset):
    conv = models.Conversation(title="观测测试", thread_id="obs-test", user_id=1)
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    msg = models.Message(conversation_id=conv.id, role="assistant", content="回答内容")
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(msg)
    db_session.add(
        models.ObservabilityTraceIndex(
            langfuse_trace_id="trace-1",
            langfuse_session_id="session-1",
            conversation_id=conv.id,
            message_id=msg.id,
            dataset_id=sample_dataset.id,
            entry_route="query_graph",
            status="success",
            total_tokens=42,
            total_cost=0.01,
        )
    )
    db_session.commit()

    summary = client.get(f"/api/observability/summary?dataset_id={sample_dataset.id}").json()
    costs = client.get(f"/api/observability/costs?dataset_id={sample_dataset.id}").json()

    assert summary["total_traces"] == 1
    assert summary["success_rate"] == 1
    assert costs["total_tokens"] == 42


def test_query_audit_trace_list_and_detail(client, db_session, sample_dataset, monkeypatch):
    class DummyTrace:
        def model_dump(self):
            return {
                "id": "trace-audit",
                "name": "user_query",
                "input": "GMV是多少",
                "output": "GMV 为 100",
                "observations": [
                    {
                        "id": "obs-1",
                        "name": "node.sql_execute",
                        "type": "SPAN",
                        "startTime": "2026-06-11T12:00:00Z",
                        "endTime": "2026-06-11T12:00:01Z",
                        "metadata": {"node": "sql_execute"},
                    }
                ],
                "scores": [
                    {"id": "score-1", "name": "user_feedback", "value": 1, "dataType": "NUMERIC"}
                ],
                "metrics": {"latency": 1},
            }

    monkeypatch.setattr(
        "app.services.observability.traces._fetch_langfuse_trace",
        lambda trace_id: (DummyTrace(), None),
    )

    conv = models.Conversation(title="审计测试", thread_id="audit-test", user_id=1)
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    user_msg = models.Message(conversation_id=conv.id, role="user", content="GMV是多少")
    assistant_msg = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content="GMV 为 100",
        sql_list=["select sum(amount) from orders"],
        step_trace=[
            {
                "type": "step",
                "node": "sql_execute",
                "display_name": "SQL 执行",
                "status": "done",
                "elapsed_ms": 42,
            }
        ],
        response_metadata={
            "observability": {
                "trace_url": "http://localhost:3000/project/p/traces/trace-audit",
                "environment": "dev",
            }
        },
    )
    db_session.add_all([user_msg, assistant_msg])
    db_session.commit()
    db_session.refresh(assistant_msg)
    db_session.add(
        models.ObservabilityTraceIndex(
            langfuse_trace_id="trace-audit",
            langfuse_session_id="session-audit",
            conversation_id=conv.id,
            message_id=assistant_msg.id,
            dataset_id=sample_dataset.id,
            entry_route="query_graph",
            status="success",
            total_tokens=12,
            total_cost=0,
        )
    )
    db_session.commit()

    listing = client.get("/api/observability/traces?limit=10").json()
    assert listing["summary"]["total_traces"] >= 1
    assert any(item["trace_id"] == "trace-audit" for item in listing["items"])

    detail = client.get("/api/observability/traces/trace-audit").json()
    assert detail["found"] is True
    assert detail["source"] == "langfuse"
    assert detail["trace"]["id"] == "trace-audit"
    assert detail["observations"][0]["name"] == "node.sql_execute"
    assert detail["scores"][0]["name"] == "user_feedback"
    assert detail["fallback_steps"][0]["name"] == "SQL 执行"
