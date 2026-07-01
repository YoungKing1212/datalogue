# ============================================================
# File Name   : test_observability.py
# Description:
#   Observability 可观测封装和反馈接口测试。
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
)
from app.services.observability.tracer import (
    DatalogueTracer,
    ObservabilityTraceContext,
    build_observability_trace_url,
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
    tracer = DatalogueTracer(Settings())
    ctx = tracer.create_trace_context(
        conversation_id=1,
        dataset_id=2,
        user_id="1",
        tenant_id="default",
        question="最近30天GMV是多少",
    )
    assert ctx.enabled is False
    assert ctx.active is False
    assert ctx.trace_id is None
    assert ctx.trace_url is None
    assert ctx.observability_payload()["enabled"] is False


def test_trace_context_accepts_business_session_id():
    """Observability session_id 应可使用业务 session_id，而不是只能用 conversation_id。"""

    tracer = DatalogueTracer(Settings())
    ctx = tracer.create_trace_context(
        conversation_id=1,
        dataset_id=2,
        user_id="1",
        tenant_id="default",
        question="最近30天GMV是多少",
        session_id="business-session-1",
    )

    assert ctx.session_id == "business-session-1"


def test_observability_trace_url_builder():
    assert build_observability_trace_url(
        base_url="http://localhost:3000/",
        project_id="project 1",
        trace_id="trace/1",
    ) is None
    assert build_observability_trace_url(base_url="http://localhost:3000", project_id=None, trace_id="t") is None


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
    """本地注册表应覆盖运行期 prompt 名称。"""

    names = {item.name for item in get_registered_prompts()}

    assert "report_generate" in names
    assert "sql_audit" in names
    assert "lead_agent_skill_selector" in names
    assert "lead_agent_tool_planner" in names
    assert "datalogue-compaction" in names
    assert "dsl_generate_real_schema" in names


def test_registered_prompt_config_is_stable_for_local_audit():
    """本地 Prompt 清单仍提供稳定配置，供离线审计和版本比对使用。"""

    prompt = RegisteredPrompt(
        name="local_prompt",
        display_name="本地 Prompt",
        prompt="content",
        description="本地说明",
        variables=("question",),
    )

    assert prompt.observability_config() == {
        "display_name": "本地 Prompt",
        "chinese_name": "本地 Prompt",
        "chinese_description": "本地说明",
        "description": "本地说明",
        "variables": ["question"],
        "prompt_pack_version": "2026-06-12-current",
    }


def test_tracer_methods_do_not_call_external_client():
    """暂不建设 Trace 时，tracer 方法不得调用外部 client。"""

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

    tracer = DatalogueTracer(Settings(), client=DummyClient())
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

    assert calls == []
    assert updates == []


def test_trace_tags_are_ignored_while_trace_is_disabled():
    """暂不建设 Trace 时，根标签和 span 标签都不写出。"""

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

    tracer = DatalogueTracer(Settings(), client=DummyClient())

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

    assert trace_updates == []
    assert observations == []


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


def test_message_feedback_updates_metadata(client, db_session):
    conv = models.Conversation(title="反馈测试", thread_id="feedback-test", user_id=1)
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    msg = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content="回答内容",
        response_metadata={"observability": {"trace_id": "trace-test", "session_id": "session-test"}},
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
    assert data["partial_success"] is False
    assert data["observability_synced"] is False
    db_session.refresh(msg)
    assert msg.response_metadata["feedback"]["action"] == "reject"


def test_observability_api_is_not_mounted(client):
    """暂不建设 Trace 时，查询审计 API 不再对外挂载。"""

    assert client.get("/api/observability/summary").status_code == 404
    assert client.get("/api/observability/traces").status_code == 404
