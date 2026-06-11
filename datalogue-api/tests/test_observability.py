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

from app import models
from app.core.config import Settings
from app.services.observability.masking import sanitize_payload, sanitize_sql, sanitize_text
from app.services.observability.tracer import DatalogueTracer, build_langfuse_trace_url


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
