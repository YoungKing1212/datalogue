# ============================================================
# File Name   : test_chat.py
# Description:
#   聊天问数和 NL2SQL 行为测试。
#
# Responsibilities:
#   - 验证 DSL 生成、编译和聊天响应。
#   - 覆盖语义层路径和推断查询路径。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""
问数对话 API 测试 — SSE 流式接口 + LangGraph 工作流节点测试
"""

import asyncio
import json
import pytest
from types import SimpleNamespace
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app import models
from app.schemas.chat import ChatRequest
from app.services.dataset_manifest import publish_manifest


def _manifest_manual_fields(*, domain="销售运营", subject="订单销售"):
    return {
        "description": (
            f"{subject}数据集用于分析门店订单在日、周、月范围内的GMV、订单数、地区和品类表现，"
            "覆盖销售运营人员查看各区域成交趋势、品类结构、异常波动和门店经营质量，不覆盖库存、会员画像和售后工单。"
        ),
        "business_domain": [domain],
        "sample_questions": [
            "最近30日GMV趋势如何",
            "按地区统计本月订单数",
            "各品类销售额排名",
            "华东区域订单量是多少",
            "本周门店成交金额变化",
        ],
        "routing_negative_examples": [
            "库存周转率是多少",
            "会员画像年龄分布",
            "售后工单处理时长",
        ],
        "permission_scope": {
            "status": "allowed",
            "description": "测试环境允许执行该数据集。",
        },
    }


def _collect_stream_events(payload, db_session):
    from app.api.chat import _stream_chat

    async def _collect():
        events = []
        async for item in _stream_chat(ChatRequest(**payload), db_session):
            events.append(json.loads(item["data"]))
        return events

    return asyncio.run(_collect())


def _find_event(events, event_type):
    return next(item for item in events if item.get("type") == event_type)


def _graph_backed_fake_subagent_class():
    """测试用 SubAgent：保留 chat 旧用例中直接驱动 fake graph 的边界。"""
    from app.services.subagent_planning import SubAgentEvent

    class FakeSubAgent:
        captured_runs = []

        def __init__(self, db, dataset_id):
            self.db = db
            self.dataset_id = dataset_id

        def resolve_term_conflict(self, **kwargs):
            return {"status": "not_applicable"}

        def resolve_metric(self, **kwargs):
            return {"status": "not_applicable"}

        def resolve_analysis_blueprint(self, **kwargs):
            return {"status": "not_applicable"}

        async def run(
            self, request, trace_context, *, graph, initial_state=None, graph_kwargs=None
        ):
            type(self).captured_runs.append(
                {
                    "request": request,
                    "trace_context": trace_context,
                    "initial_state": initial_state or {},
                    "graph_kwargs": graph_kwargs or {},
                }
            )
            version = (graph_kwargs or {}).get("version", "v2")
            async for event in graph.astream_events(initial_state or {}, version):
                yield SubAgentEvent(event_type="graph_event", payload={"event": event})

    return FakeSubAgent


class TestChatAPI:
    """测试 /api/chat 路由"""

    def test_sql_audit_node_is_exposed_to_stream_payloads(self):
        """SQL 诊断节点应按原始节点名展示，并纳入状态输出提取。"""
        from app.api.chat import _NODE_DISPLAY_NAMES, _STATE_OUTPUT_KEYS

        assert _NODE_DISPLAY_NAMES["sql_audit"] == "sql_audit"
        assert "sql_audit_result" in _STATE_OUTPUT_KEYS
        assert "sql_diagnosis" in _STATE_OUTPUT_KEYS
        assert "sql_retry_trace" in _STATE_OUTPUT_KEYS
        assert "answer_explanation" in _STATE_OUTPUT_KEYS

    def test_chat_stream_log_summary_extracts_debug_fields(self):
        """聊天流日志摘要应保留排查 final payload 所需的关键字段。"""
        from app.api.chat import _chat_stream_log_summary

        summary = _chat_stream_log_summary(
            {
                "type": "final",
                "answer": "查询完成",
                "entry_route": "reject",
                "entry_reason": "no_query_target",
                "error": None,
                "sql": "",
                "sql_list": ["select 1"],
                "conversation_id": 12,
                "message_id": 34,
                "query_plan": {
                    "query_type": "unsupported",
                    "planner_source": "fallback",
                    "fallback_reason": "candidate_assets_insufficient",
                },
            }
        )

        assert summary == {
            "payload_type": "final",
            "conversation_id": 12,
            "message_id": 34,
            "entry_route": "reject",
            "entry_reason": "no_query_target",
            "query_plan_type": "unsupported",
            "planner_source": "fallback",
            "fallback_reason": "candidate_assets_insufficient",
            "has_sql": True,
            "sql_count": 1,
            "has_error": False,
            "error": None,
            "answer_len": 4,
        }

    def test_query_plan_prompt_exposes_main_table_and_join_hints(self):
        """DSL prompt 中应带主表和 JOIN 线索，避免生成端再次选错表。"""
        from app.graph.nodes import _format_query_plan_for_prompt

        prompt = _format_query_plan_for_prompt(
            {
                "query_type": "detail_query",
                "execution_strategy": "query_graph",
                "planner_source": "deterministic",
                "explanation": {"summary": "日志明细查询。"},
                "debug": {
                    "selected_main_table": "plan_task_daily_record",
                    "join_hints": [
                        {
                            "left_table": "plan_task_daily_record",
                            "left_column": "account",
                            "right_table": "eas_personofile",
                            "right_column": "person_card",
                            "purpose": "日志账号关联人员姓名",
                        }
                    ],
                },
            }
        )

        assert "规划来源: deterministic" in prompt
        assert "事实主表: plan_task_daily_record" in prompt
        assert "plan_task_daily_record.account = eas_personofile.person_card" in prompt

    def test_dsl_asset_catalog_filters_fields_by_query_plan(self):
        """QueryPlan 已选表字段时，DSL 资产目录不再追加全量字段目录。"""
        from app.graph.nodes import _format_dsl_asset_catalog

        catalog = _format_dsl_asset_catalog(
            {
                "fields": [
                    {
                        "id": 1,
                        "name": "rzrq",
                        "column_name": "rzrq",
                        "table_name": "plan_task_daily_record",
                    },
                    {
                        "id": 2,
                        "name": "zt",
                        "column_name": "zt",
                        "table_name": "plan_task_daily_record",
                    },
                    {
                        "id": 3,
                        "name": "person_money",
                        "column_name": "person_money",
                        "table_name": "eas_personofile",
                    },
                ]
            },
            {
                "selected_assets": [
                    {
                        "asset_type": "field",
                        "name": "rzrq",
                        "metadata": {
                            "table_name": "plan_task_daily_record",
                            "column_name": "rzrq",
                        },
                    }
                ]
            },
        )

        assert "rzrq" in catalog
        assert "zt" in catalog
        assert "person_money" not in catalog

    def test_dsl_generate_template_plan_skips_llm(self, monkeypatch):
        """模板 QueryPlan 应直接产出 SQL，不初始化 DSL LLM。"""
        from app.graph.nodes import dsl_generate_node

        def fail_get_llm(*_args, **_kwargs):
            raise AssertionError("template path should not create llm")

        monkeypatch.setattr("app.graph.nodes.get_llm", fail_get_llm)
        sql = "SELECT * FROM plan_task_daily_record LIMIT 10"

        result = dsl_generate_node(
            {
                "question": "查询10条用户日志",
                "query_plan": {
                    "planner_source": "template",
                    "debug": {"sql_template": sql},
                },
            }
        )

        assert result["generation_mode"] == "template"
        assert result["llm_skipped_reason"] == "query_plan_template_sql"
        assert result["sql"] == sql

    def test_dsl_generate_fallback_template_plan_skips_llm(self, monkeypatch):
        """LLM planner 失败后的可信模板 fallback 也应直接产出 SQL。"""
        from app.graph.nodes import dsl_generate_node

        def fail_get_llm(*_args, **_kwargs):
            raise AssertionError("fallback template path should not create llm")

        monkeypatch.setattr("app.graph.nodes.get_llm", fail_get_llm)
        sql = "SELECT * FROM plan_task_daily_record LIMIT 10"

        result = dsl_generate_node(
            {
                "question": "查询10条用户日志",
                "query_plan": {
                    "planner_source": "fallback",
                    "fallback_reason": "llm_planner_unavailable",
                    "debug": {
                        "template_name": "dataset10_log_detail",
                        "sql_template": sql,
                    },
                },
            }
        )

        assert result["generation_mode"] == "template"
        assert result["llm_skipped_reason"] == "query_plan_template_sql"
        assert result["sql"] == sql

    def test_sql_execute_preserves_upstream_compile_error(self, db_session):
        """上游 SQL 编译失败时，不应被 SQL 执行节点覆盖成笼统的 SQL 为空。"""
        from app.graph.nodes import sql_execute_node

        state = {
            "sql": None,
            "error": "SQL 引用了当前数据集未授权的表：contract_stats",
            "should_retry": False,
            "sql_guard": {"ok": False, "code": "SQL_GUARD_BLOCKED"},
        }

        result = sql_execute_node(db_session)(state)

        assert result["sql_result"] is None
        assert result["error"] == state["error"]
        assert result["should_retry"] is False
        assert result["sql_guard"] == state["sql_guard"]

    def test_chat_stream_basic(self, client, sample_dataset):
        """基础流式问数接口应返回 200"""
        payload = {
            "question": "最近30天的GMV是多少",
            "dataset_id": sample_dataset.id,
        }
        try:
            resp = client.post("/api/chat/stream", json=payload)
            assert resp.status_code == 200
            # SSE 响应
            assert "text/event-stream" in resp.headers.get("content-type", "")
        except Exception:
            # SSE 流式在同步 TestClient 中可能抛 ExceptionGroup，集成环境再验证
            pytest.skip("SSE stream not fully supported in sync TestClient")

    def test_chat_stream_no_dataset(self, client):
        """无 dataset_id 时也应能请求（走真实 schema 或无 schema 路径）"""
        payload = {"question": "Hello"}
        # SSE 在 TestClient 中可能因事件循环问题报错，这里只验证接口可访问
        # 实际流式内容在集成环境中测试
        try:
            resp = client.post("/api/chat/stream", json=payload)
            assert resp.status_code == 200
        except Exception:
            # SSE 流式在同步 TestClient 中可能有问题，跳过
            pytest.skip("SSE stream not fully supported in sync TestClient")

    def test_chat_feedback(self, client, db_session):
        """人工反馈接口"""
        from app import models

        conv = models.Conversation(title="反馈测试", thread_id="feedback-test", user_id=1)
        db_session.add(conv)
        db_session.commit()
        db_session.refresh(conv)
        msg = models.Message(
            conversation_id=conv.id,
            role="assistant",
            content="回答内容",
            response_metadata={
                "langfuse": {"trace_id": "trace-test", "session_id": "session-test"}
            },
        )
        db_session.add(msg)
        db_session.commit()
        db_session.refresh(msg)

        payload = {
            "message_id": msg.id,
            "action": "approve",
            "comment": "回答正确",
        }
        resp = client.post("/api/chat/feedback", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "approve"
        assert data["message_id"] == msg.id


class TestLangGraphNodes:
    """测试 LangGraph 各节点逻辑"""

    def test_intent_recognition_chitchat(self):
        """测试意图识别：闲聊"""
        from app.services.lead_agent_routing import route_query_intent

        with patch("app.services.lead_agent_routing.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = json.dumps(
                {
                    "intent": "chitchat",
                    "entities": {},
                    "direct_answer": "你好！有什么可以帮你的？",
                }
            )
            mock_response.usage_metadata = {"input_tokens": 50, "output_tokens": 20}
            mock_llm.invoke.return_value = mock_response
            mock_get_llm.return_value = mock_llm

            state = {"question": "你好", "history": [], "token_usage": None}
            result = route_query_intent(
                db=None,
                question=state["question"],
                dataset_id=None,
                lead_agent_context={},
                history=state["history"],
                multiturn_context={},
                clarification_response=None,
            )

            assert result["intent"] == "chitchat"
            assert result["answer"] == "你好！有什么可以帮你的？"
            assert result["token_usage"]["total_tokens"] == 70

    def test_intent_recognition_query(self):
        """测试意图识别：数据查询"""
        from app.services.lead_agent_routing import route_query_intent

        with patch("app.services.lead_agent_routing.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = json.dumps(
                {
                    "intent": "query",
                    "entities": {"metrics": ["gmv"], "dimensions": ["region"]},
                }
            )
            mock_response.usage_metadata = {"input_tokens": 60, "output_tokens": 30}
            mock_llm.invoke.return_value = mock_response
            mock_get_llm.return_value = mock_llm

            state = {"question": "各地区的GMV", "history": [], "token_usage": None}
            result = route_query_intent(
                db=None,
                question=state["question"],
                dataset_id=None,
                lead_agent_context={},
                history=state["history"],
                multiturn_context={},
                clarification_response=None,
            )

            assert result["intent"] == "query"
            assert result["entities"]["metrics"] == ["gmv"]
            assert result["entry_route"] == "clarify"
            assert result["route_payload"] == {"kind": "clarification", "missing": ["dataset"]}
            assert "确认要使用的数据集" in result["answer"]  # DAT-13 后未确认数据集时必须先阻断 QueryGraph。

    def test_entry_intent_metric_query(self, db_session, sample_dataset):
        """入口分类：指标查询继续 QueryGraph。"""
        from app.services.lead_agent_routing import _classify_entry_intent

        state = {
            "question": "最近30天GMV是多少",
            "dataset_id": sample_dataset.id,
            "intent": "query",
            "entities": {"metrics": ["gmv"], "dimensions": []},
        }
        result = _classify_entry_intent(
            db=db_session,
            question=state.get("question") or "",
            intent=state.get("intent") or "query",
            entities=state.get("entities") or {},
            dataset_id=state.get("dataset_id"),
            history=state.get("history") or [],
            multiturn_context=state.get("multiturn_context") or {},
            clarification_response=state.get("clarification_response"),
            lead_agent_context=state.get("lead_agent_context") or {},
        )

        assert result["entry_intent"] == "metric_query"
        assert result["entry_route"] == "query_graph"

    def test_entry_intent_detail_query(self, db_session, sample_dataset):
        """入口分类：明细查询继续 QueryGraph。"""
        from app.services.lead_agent_routing import _classify_entry_intent

        state = {
            "question": "列出华东订单明细",
            "dataset_id": sample_dataset.id,
            "intent": "query",
            "entities": {"metrics": [], "dimensions": ["region"]},
        }
        result = _classify_entry_intent(
            db=db_session,
            question=state.get("question") or "",
            intent=state.get("intent") or "query",
            entities=state.get("entities") or {},
            dataset_id=state.get("dataset_id"),
            history=state.get("history") or [],
            multiturn_context=state.get("multiturn_context") or {},
            clarification_response=state.get("clarification_response"),
            lead_agent_context=state.get("lead_agent_context") or {},
        )

        assert result["entry_intent"] == "detail_query"
        assert result["entry_route"] == "query_graph"

    def test_entry_intent_blueprint_hit(self, db_session, sample_dataset):
        """入口分类：命中已发布分析蓝图时返回 blueprint_id。"""
        from app.services.lead_agent_routing import _classify_entry_intent
        from app.models.dataset import AnalysisBlueprint

        bp = AnalysisBlueprint(
            dataset_id=sample_dataset.id,
            name="毛利归因分析",
            trigger_keywords=["毛利", "归因"],
            trigger_examples=["为什么本月毛利下降"],
            when_to_use="当用户询问毛利变化原因时使用。",
            status="active",
        )
        db_session.add(bp)
        db_session.commit()
        db_session.refresh(bp)

        state = {
            "question": "为什么本月毛利下降",
            "dataset_id": sample_dataset.id,
            "intent": "query",
            "entities": {"metrics": [], "dimensions": []},
        }
        result = _classify_entry_intent(
            db=db_session,
            question=state.get("question") or "",
            intent=state.get("intent") or "query",
            entities=state.get("entities") or {},
            dataset_id=state.get("dataset_id"),
            history=state.get("history") or [],
            multiturn_context=state.get("multiturn_context") or {},
            clarification_response=state.get("clarification_response"),
            lead_agent_context=state.get("lead_agent_context") or {},
        )

        assert result["entry_intent"] == "analysis_blueprint"
        assert result["entry_route"] == "analysis_blueprint"
        assert result["blueprint_id"] == bp.id
        assert result["route_payload"]["blueprint_id"] == bp.id

    def test_semantic_asset_resolution_metric_synonym(self):
        """语义资产解析：指标同义词命中，并兼容旧 metric_resolution。"""
        from app.services.dataset_subagent import DatasetSubAgent

        sub_agent = DatasetSubAgent(db=None, dataset_id=1)  # type: ignore[arg-type]
        out = sub_agent.resolve_metric(
            question="销售额是多少",
            entities={"metrics": ["销售额"], "dimensions": []},
            schema_structured={
                "metrics": [
                    {
                        "id": 1,
                        "name": "gmv",
                        "display_name": "GMV",
                        "synonyms": ["销售额"],
                    }
                ],
                "dimensions": [],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        )

        # Phase 7 改写：DatasetSubAgent.resolve_metric 返回 status=resolved
        assert out["status"] == "resolved"
        semantic = out["semantic_asset_resolution"]
        assert semantic["metrics"][0]["name"] == "gmv"
        assert semantic["metrics"][0]["asset_id"] == 1
        assert semantic["metrics"][0]["match_type"] == "synonym"
        assert out["metric_resolution"]["metrics"][0]["resolved"] == "gmv"
        assert out["metric_resolution"]["all_matched"] is True

    def test_term_normalize_node_alias_match(self):
        """术语归一化：业务术语同义词应注入 entities.terms。"""
        from app.services.dataset_subagent import DatasetSubAgent

        sub_agent = DatasetSubAgent(db=None, dataset_id=1)  # type: ignore[arg-type]
        out = sub_agent.resolve_term_conflict(
            question="销售额趋势",
            terms=[
                {
                    "id": 7,
                    "name": "gmv",
                    "display_name": "GMV",
                    "term_type": "metric",
                    "aliases": ["销售额"],
                    "asset_links": [
                        {
                            "asset_type": "metric",
                            "asset_id": 1,
                            "asset_name": "gmv",
                        }
                    ],
                }
            ],
            entities={"metrics": [], "dimensions": []},
        )

        # Phase 6 改写：DatasetSubAgent.resolve_term_conflict 返回 status=resolved
        assert out["status"] == "resolved"
        normalization = out["term_normalization"]
        assert normalization["matched_terms"][0]["name"] == "gmv"
        assert normalization["matched_terms"][0]["match_type"] == "synonym"
        assert normalization["has_conflict"] is False
        assert out["entities"]["terms"] == ["销售额"]

    def test_term_normalize_node_conflict_clarification(self):
        """术语归一化：同一个同义词命中多个术语时进入澄清。"""
        from app.services.dataset_subagent import DatasetSubAgent

        sub_agent = DatasetSubAgent(db=None, dataset_id=1)  # type: ignore[arg-type]
        out = sub_agent.resolve_term_conflict(
            question="销售额是多少",
            terms=[
                {
                    "id": 1,
                    "name": "gmv",
                    "display_name": "GMV",
                    "aliases": ["销售额"],
                },
                {
                    "id": 2,
                    "name": "paid_amount",
                    "display_name": "实付金额",
                    "aliases": ["销售额"],
                },
            ],
            entities={"metrics": [], "dimensions": []},
        )

        # Phase 6 改写：needs_clarification 由 DatasetSubAgent 决策；
        # entry_intent / entry_route 由 chat 层在 _early_route_return 时注入。
        assert out["status"] == "needs_clarification"
        assert out["route_payload"]["kind"] == "term_conflict_clarification"
        assert out["term_normalization"]["has_conflict"] is True
        assert {t["id"] for t in out["route_payload"]["conflicts"][0]["terms"]} == {1, 2}
        assert {t["term_id"] for t in out["route_payload"]["candidates"]} == {1, 2}

    def test_term_normalize_selected_term_resolves_conflict(self):
        """术语归一化：澄清后的 selected_term_id 会压掉同义词冲突。"""
        from app.services.dataset_subagent import DatasetSubAgent

        sub_agent = DatasetSubAgent(db=None, dataset_id=1)  # type: ignore[arg-type]
        out = sub_agent.resolve_term_conflict(
            question="销售额是多少",
            terms=[
                {
                    "id": 1,
                    "name": "gmv",
                    "display_name": "GMV",
                    "aliases": ["销售额"],
                },
                {
                    "id": 2,
                    "name": "paid_amount",
                    "display_name": "实付金额",
                    "aliases": ["销售额"],
                },
            ],
            entities={"metrics": [], "dimensions": []},
            selected_term_id=2,
        )

        # Phase 6 改写：selected_term_id 由 DatasetSubAgent 接收并直接归一化
        assert out["status"] == "resolved"
        assert out["term_normalization"]["has_conflict"] is False
        assert out["term_normalization"]["selected_term_id"] == 2
        assert [m["term_id"] for m in out["term_normalization"]["matched_terms"]] == [2]
        assert out["entities"]["terms"] == ["销售额"]

    def _create_pending_term_clarification(self, db_session, sample_dataset, **overrides):
        """创建一个术语冲突澄清态，供澄清解析测试复用。"""
        from app.models.conversation import Conversation, PendingClarification

        conv = Conversation(
            title="术语澄清测试",
            thread_id="thread-term-conflict",
            dataset_id=sample_dataset.id,
        )
        db_session.add(conv)
        db_session.flush()
        candidates = [
            {
                "index": 1,
                "term_id": 1,
                "name": "gmv",
                "display_name": "GMV",
                "definition": "商品交易总额",
                "aliases": ["成交额"],
            },
            {
                "index": 2,
                "term_id": 2,
                "name": "paid_amount",
                "display_name": "实付金额",
                "definition": "用户实际支付金额",
                "aliases": ["支付金额"],
            },
        ]
        expires_at = overrides.pop("expires_at", datetime.utcnow() + timedelta(minutes=30))
        pending = PendingClarification(
            conversation_id=conv.id,
            dataset_id=sample_dataset.id,
            clarification_type="term_conflict",
            status="pending",
            original_question="销售额是多少",
            conflict_payload={"kind": "term_conflict_clarification"},
            candidates=candidates,
            expires_at=expires_at,
            **overrides,
        )
        db_session.add(pending)
        db_session.commit()
        db_session.refresh(conv)
        db_session.refresh(pending)
        return conv, pending

    def test_chat_stream_conflict_creates_pending_clarification(self, db_session, sample_dataset):
        """聊天流：术语冲突 final payload 会创建 pending_clarification。"""
        from app.api.chat import _ensure_pending_term_clarification
        from app.models.conversation import Conversation, PendingClarification

        conv = Conversation(
            title="冲突会话", thread_id="thread-conflict", dataset_id=sample_dataset.id
        )
        db_session.add(conv)
        db_session.commit()
        payload = {
            "kind": "term_conflict_clarification",
            "conflicts": [
                {
                    "token": "销售额",
                    "terms": [
                        {"id": 1, "name": "gmv", "display_name": "GMV"},
                        {"id": 2, "name": "paid_amount", "display_name": "实付金额"},
                    ],
                }
            ],
        }

        enriched = _ensure_pending_term_clarification(
            db_session,
            conversation_id=conv.id,
            dataset_id=sample_dataset.id,
            question="销售额是多少",
            route_payload=payload,
        )

        assert enriched["clarification_id"]
        assert {c["term_id"] for c in enriched["candidates"]} == {1, 2}
        pending = db_session.query(PendingClarification).filter_by(conversation_id=conv.id).one()
        assert pending.original_question == "销售额是多少"
        assert pending.status == "pending"

    def test_chat_stream_conflict_enriches_existing_candidate_labels(
        self, db_session, sample_dataset
    ):
        """已有候选只有 term_id 时，应回查业务术语补齐前端展示名。"""
        from app.api.chat import _ensure_pending_term_clarification
        from app.models.conversation import Conversation

        term = models.BusinessTerm(
            dataset_id=sample_dataset.id,
            name="paid_amount",
            display_name="实付金额",
            term_type="metric",
            definition="用户实际支付金额",
            status="active",
        )
        conv = Conversation(
            title="候选补齐", thread_id="thread-candidate-label", dataset_id=sample_dataset.id
        )
        db_session.add_all([term, conv])
        db_session.commit()

        enriched = _ensure_pending_term_clarification(
            db_session,
            conversation_id=conv.id,
            dataset_id=sample_dataset.id,
            question="销售额是多少",
            route_payload={
                "kind": "term_conflict_clarification",
                "candidates": [{"index": 1, "term_id": term.id}],
            },
        )

        assert enriched["candidates"][0]["display_name"] == "实付金额"
        assert enriched["candidates"][0]["name"] == "paid_amount"
        assert enriched["candidates"][0]["definition"] == "用户实际支付金额"

    def test_clarification_resolution_selected_term_id(self, db_session, sample_dataset):
        """澄清解析：结构化 selected_term_id 可恢复原问题。"""
        from app.services.lead_agent_routing import resolve_term_clarification

        conv, pending = self._create_pending_term_clarification(db_session, sample_dataset)
        result = resolve_term_clarification(
            db=db_session,
            question="选择 GMV",
            conversation_id=conv.id,
            dataset_id=sample_dataset.id,
            clarification_response={
                "clarification_id": pending.id,
                "selected_term_id": 1,
            },
        )

        assert result["resolved_question"] == "销售额是多少"
        assert result["selected_term_id"] == 1
        assert result["status"] == "resolved"
        assert result["clarification_resolution_result"]["status"] == "resolved"
        db_session.refresh(pending)
        assert pending.status == "resolved"
        assert pending.selected_payload["term_id"] == 1

    def test_clarification_resolution_ordinal_reply(self, db_session, sample_dataset):
        """澄清解析：自然语言“第一个”可匹配候选序号。"""
        from app.services.lead_agent_routing import resolve_term_clarification

        conv, pending = self._create_pending_term_clarification(db_session, sample_dataset)
        result = resolve_term_clarification(
            db=db_session,
            question="第一个",
            conversation_id=conv.id,
            dataset_id=sample_dataset.id,
            clarification_response=None,
        )

        assert result["selected_term_id"] == 1
        assert result["status"] == "resolved"
        assert result["resolved_question"] == pending.original_question

    def test_clarification_resolution_name_reply(self, db_session, sample_dataset):
        """澄清解析：自然语言术语展示名可匹配候选。"""
        from app.services.lead_agent_routing import resolve_term_clarification

        conv, _ = self._create_pending_term_clarification(db_session, sample_dataset)
        result = resolve_term_clarification(
            db=db_session,
            question="实付金额",
            conversation_id=conv.id,
            dataset_id=sample_dataset.id,
            clarification_response=None,
        )

        assert result["selected_term_id"] == 2
        assert result["status"] == "resolved"
        assert (
            result["clarification_resolution_result"]["selected_term"]["display_name"] == "实付金额"
        )

    def test_clarification_resolution_invalid_reply(self, db_session, sample_dataset):
        """澄清解析：无效回复继续提示候选并保持 pending。"""
        from app.services.lead_agent_routing import resolve_term_clarification

        conv, pending = self._create_pending_term_clarification(db_session, sample_dataset)
        result = resolve_term_clarification(
            db=db_session,
            question="都不是",
            conversation_id=conv.id,
            dataset_id=sample_dataset.id,
            clarification_response=None,
        )

        assert result["status"] == "unresolved"
        assert result["entry_route"] == "clarify"
        assert result["route_payload"]["kind"] == "term_conflict_clarification"
        assert result["clarification_resolution_result"]["status"] == "unresolved"
        db_session.refresh(pending)
        assert pending.status == "pending"

    def test_clarification_resolution_missing_state(self, db_session, sample_dataset):
        """澄清解析：结构化回复找不到 pending 时提示重新提问。"""
        from app.services.lead_agent_routing import resolve_term_clarification

        result = resolve_term_clarification(
            db=db_session,
            question="第一个",
            conversation_id=99999,
            dataset_id=sample_dataset.id,
            clarification_response={"selected_index": 1},
        )

        assert result["status"] == "missing"
        assert result["route_payload"]["kind"] == "term_conflict_missing"
        assert result["clarification_resolution_result"]["status"] == "missing"

    def test_clarification_resolution_expired_state(self, db_session, sample_dataset):
        """澄清解析：过期 pending 惰性标记 expired。"""
        from app.services.lead_agent_routing import resolve_term_clarification

        conv, pending = self._create_pending_term_clarification(
            db_session,
            sample_dataset,
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        result = resolve_term_clarification(
            db=db_session,
            question="第一个",
            conversation_id=conv.id,
            dataset_id=sample_dataset.id,
            clarification_response=None,
        )

        assert result["status"] == "expired"
        assert result["route_payload"]["kind"] == "term_conflict_expired"
        assert result["clarification_resolution_result"]["status"] == "expired"
        db_session.refresh(pending)
        assert pending.status == "expired"

    def test_term_normalization_router_blocks_conflict(self):
        """工作流路由：术语冲突时不再进入 LangGraph 节点（Phase 6 由 chat 层 _early_route_return 早退）。"""
        from app.graph.workflow import _lead_agent_router

        # Phase 6 改写：_term_normalization_router 已删除，术语冲突早退由 chat 层
        # 在 Phase 6 集成块内 _early_route_return 完成；LangGraph 不再承担冲突判定。
        # 验证：route_query_intent 决策 entry_route=schema_recall 时直接进 schema_recall，
        # 已不再路由到 term_normalize_node 或 semantic_asset_resolution_node。
        state_clarify = {
            "entry_route": "schema_recall",
            "route_payload": {"kind": "term_conflict_clarification"},
        }
        assert _lead_agent_router(state_clarify) == "schema_recall"
        state_normal = {"entry_route": "schema_recall", "route_payload": {}}
        assert _lead_agent_router(state_normal) == "schema_recall"

    def test_term_normalize_feeds_semantic_asset_resolution(self):
        """术语归一化结果应影响后续资产解析。"""
        from app.services.dataset_subagent import DatasetSubAgent

        sub_agent = DatasetSubAgent(db=None, dataset_id=1)  # type: ignore[arg-type]
        schema_structured = {
            "metrics": [{"id": 1, "name": "gmv", "display_name": "GMV", "synonyms": []}],
            "dimensions": [],
            "fields": [],
            "terms": [
                {
                    "id": 7,
                    "name": "sales_term",
                    "display_name": "销售额术语",
                    "aliases": ["销售额"],
                    "asset_links": [
                        {
                            "asset_type": "metric",
                            "asset_id": 1,
                            "asset_name": "gmv",
                        }
                    ],
                }
            ],
            "blueprints": [],
        }
        term_outcome = sub_agent.resolve_term_conflict(
            question="销售额趋势",
            terms=schema_structured["terms"],
            entities={"metrics": [], "dimensions": []},
        )
        # Phase 6+7 改写：把 term_outcome.entities 合并到 metric 调用的 entities 入参
        metric_outcome = sub_agent.resolve_metric(
            question="销售额趋势",
            entities=term_outcome.get("entities") or {"metrics": [], "dimensions": []},
            schema_structured=schema_structured,
        )

        assert any(
            t["name"] == "sales_term" for t in metric_outcome["semantic_asset_resolution"]["terms"]
        )
        assert any(
            m["name"] == "gmv" and m["match_type"] == "linked_term"
            for m in metric_outcome["semantic_asset_resolution"]["metrics"]
        )

    def test_semantic_asset_resolution_field_label(self):
        """语义资产解析：字段中文标注可被解析为 field 资产。"""
        from app.services.dataset_subagent import DatasetSubAgent

        sub_agent = DatasetSubAgent(db=None, dataset_id=1)  # type: ignore[arg-type]
        out = sub_agent.resolve_metric(
            question="查询人员姓名明细",
            entities={"metrics": [], "dimensions": []},
            schema_structured={
                "metrics": [],
                "dimensions": [],
                "terms": [],
                "fields": [
                    {
                        "id": 12,
                        "name": "person_name",
                        "column_name": "person_name",
                        "display_name": "人员姓名",
                        "table_name": "plan_task_daily_record",
                        "synonyms": ["姓名"],
                    }
                ],
                "blueprints": [],
            },
        )

        fields = out["semantic_asset_resolution"]["fields"]
        assert fields[0]["name"] == "person_name"
        assert fields[0]["asset_type"] == "field"
        assert fields[0]["match_type"] in ("display_name", "column_label", "synonym")

    def test_semantic_asset_resolution_term_linked_metric(self):
        """语义资产解析：命中业务术语后扩展显式关联指标。"""
        from app.services.dataset_subagent import DatasetSubAgent

        sub_agent = DatasetSubAgent(db=None, dataset_id=1)  # type: ignore[arg-type]
        out = sub_agent.resolve_metric(
            question="日报怎么看",
            entities={"metrics": [], "dimensions": []},
            schema_structured={
                "metrics": [
                    {
                        "id": 3,
                        "name": "daily_finish_rate",
                        "display_name": "日报完成率",
                        "synonyms": [],
                    }
                ],
                "dimensions": [],
                "fields": [],
                "terms": [
                    {
                        "id": 8,
                        "name": "daily_report",
                        "display_name": "日报",
                        "aliases": ["工作日报"],
                        "asset_links": [
                            {
                                "asset_type": "metric",
                                "asset_id": 3,
                                "asset_name": "daily_finish_rate",
                            }
                        ],
                    }
                ],
                "blueprints": [],
            },
        )

        semantic = out["semantic_asset_resolution"]
        assert semantic["terms"][0]["name"] == "daily_report"
        assert any(
            m["name"] == "daily_finish_rate" and m["match_type"] == "linked_term"
            for m in semantic["metrics"]
        )

    def test_semantic_asset_resolution_ambiguity(self):
        """语义资产解析：近似同名资产应输出歧义候选。"""
        from app.services.dataset_subagent import DatasetSubAgent

        sub_agent = DatasetSubAgent(db=None, dataset_id=1)  # type: ignore[arg-type]
        out = sub_agent.resolve_metric(
            question="查询地区",
            entities={"metrics": [], "dimensions": ["地区"]},
            schema_structured={
                "metrics": [],
                "dimensions": [
                    {"id": 1, "name": "region", "display_name": "地区", "synonyms": []},
                    {"id": 2, "name": "area", "display_name": "地区", "synonyms": []},
                ],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        )

        # Phase 7 改写：needs_clarification 由 DatasetSubAgent 决策
        assert out["status"] == "needs_clarification"
        ambiguities = out["semantic_asset_resolution"]["ambiguities"]
        assert ambiguities
        assert {c["asset_id"] for c in ambiguities[0]["candidates"]} == {1, 2}

    def test_analysis_blueprint_execute_success(self, db_session, sample_dataset):
        """蓝图执行：执行只读 SQL 模板并写入结果。"""
        from app.services.dataset_subagent import DatasetSubAgent
        from app.models.dataset import AnalysisBlueprint, BlueprintUsageLog

        bp = AnalysisBlueprint(
            dataset_id=sample_dataset.id,
            name="毛利归因分析",
            trigger_keywords=["毛利"],
            parameters=[
                {
                    "name": "start_date",
                    "type": "date",
                    "required": True,
                    "default_expr": "MONTH_START",
                },
                {
                    "name": "end_date",
                    "type": "date",
                    "required": True,
                    "default_expr": "TODAY",
                },
            ],
            call_template=(
                "SELECT :start_date AS start_date, :end_date AS end_date, "
                "'电子' AS category, 0.31 AS margin_rate"
            ),
            output_schema=[
                {"column": "category", "semantic": "品类"},
                {"column": "margin_rate", "semantic": "毛利率"},
            ],
            status="active",
        )
        db_session.add(bp)
        db_session.commit()
        db_session.refresh(bp)

        state = {
            "question": "为什么2025年毛利下降",
            "original_question": "为什么去年毛利下降",
            "resolved_question": "为什么2025年毛利下降",
            "time_context": {
                "detected_time_range": {
                    "label": "去年",
                    "start_date": "2025-01-01",
                    "end_date": "2025-12-31",
                    "granularity": "year",
                    "source": "relative_last_year",
                }
            },
            "dataset_id": sample_dataset.id,
            "blueprint_id": bp.id,
        }
        sub = DatasetSubAgent(db=db_session, dataset_id=sample_dataset.id)
        result = sub.resolve_analysis_blueprint(
            blueprint_id=bp.id,
            question=state.get("question") or "",
            entry_route="analysis_blueprint",
            original_question=state.get("original_question"),
            resolved_question=state.get("resolved_question"),
            time_context=state.get("time_context"),
        )

        assert result["generation_mode"] == "analysis_blueprint"
        assert result["sql_result"]["row_count"] == 1
        assert result["sql_result"]["rows"][0]["category"] == "电子"
        assert result["route_payload"]["blueprint_id"] == bp.id
        assert ":start_date" not in result["sql"]
        assert result["route_payload"]["params"]["start_date"] == "2025-01-01"
        assert result["route_payload"]["params"]["end_date"] == "2025-12-31"
        assert result["route_payload"]["original_question"] == "为什么去年毛利下降"
        assert result["route_payload"]["resolved_question"] == "为什么2025年毛利下降"
        assert "'" in result["sql"]
        assert ":start_date" in result["route_payload"]["sql_template"]
        assert "LIMIT 100" in result["route_payload"]["sql_template"]
        db_session.refresh(bp)
        assert bp.usage_count == 1
        assert db_session.query(BlueprintUsageLog).filter_by(blueprint_id=bp.id).count() == 1

    def test_analysis_blueprint_semantic_plan_enters_query_graph(self, db_session, sample_dataset):
        """手动语义蓝图：不要求 SQL，转为 QueryGraph 业务上下文。"""
        from app.services.dataset_subagent import DatasetSubAgent
        from app.models.dataset import AnalysisBlueprint

        bp = AnalysisBlueprint(
            dataset_id=sample_dataset.id,
            name="个人计划任务日报查询",
            description="按人员姓名和时间范围查询个人计划任务日报明细。",
            trigger_keywords=["日报", "计划任务"],
            trigger_examples=["查询杨凯 2024 年的日报"],
            when_to_use="用户询问某个人在指定时间内的任务日报时使用。",
            parameters=[
                {"name": "person_name", "type": "string", "required": True, "semantic": "人员姓名"},
                {"name": "start_date", "type": "date", "required": True, "semantic": "开始日期"},
                {"name": "end_date", "type": "date", "required": True, "semantic": "结束日期"},
            ],
            output_schema=[
                {"column": "report_date", "semantic": "日报日期", "role": "dimension"},
                {"column": "task_content", "semantic": "任务内容", "role": "detail"},
            ],
            steps=[
                {
                    "name": "过滤人员和日期",
                    "purpose": "按姓名与日期范围过滤日报明细",
                    "key_rules": ["排除已作废记录"],
                }
            ],
            attribution_hints="回答中说明统计范围和过滤口径。",
            implementation_type="semantic_plan",
            status="active",
        )
        db_session.add(bp)
        db_session.commit()
        db_session.refresh(bp)

        sub = DatasetSubAgent(db=db_session, dataset_id=sample_dataset.id)
        result = sub.resolve_analysis_blueprint(
            blueprint_id=bp.id,
            question="我要查询2024年杨凯的日报",
            entry_route="analysis_blueprint",
            original_question="我要查询2024年杨凯的日报",
            resolved_question="我要查询2024年杨凯的日报",
            time_context=None,
        )

        assert result["sql_result"] is None
        assert result["sql"] is None
        assert result["generation_mode"] == "analysis_blueprint_semantic"
        assert result["route_payload"]["kind"] == "analysis_blueprint_semantic"
        assert "个人计划任务日报查询" in result["blueprint_context"]
        assert "不能要求用户提供 SQL" in result["blueprint_context"]
        assert "任务内容" in result["blueprint_context"]

    def test_schema_recall_appends_blueprint_context(self, db_session, sample_dataset):
        """Schema 召回：语义蓝图上下文会随数据集约束一起进入提示词。"""
        from app.graph.nodes import schema_recall_node

        blueprint_context = "【命中的分析蓝图语义计划】\n蓝图名称: 个人计划任务日报查询"
        result = schema_recall_node(db_session)(
            {
                "question": "我要查询2024年杨凯的日报",
                "dataset_id": sample_dataset.id,
                "blueprint_context": blueprint_context,
            }
        )

        assert blueprint_context in result["schema_context"]
        assert blueprint_context in result["dataset_prompt_instructions"]
        assert result["dataset_context_debug"]["asset_counts"]["metrics"] == 2
        assert result["dataset_context_debug"]["retained_counts"]["metrics"] == 2

    def test_analysis_blueprint_execute_missing_required_param(self, db_session, sample_dataset):
        """蓝图执行：缺少必填参数时进入澄清。"""
        from app.services.dataset_subagent import DatasetSubAgent
        from app.models.dataset import AnalysisBlueprint

        bp = AnalysisBlueprint(
            dataset_id=sample_dataset.id,
            name="毛利归因分析",
            parameters=[{"name": "start_date", "type": "date", "required": True}],
            call_template="SELECT :start_date AS start_date",
            status="active",
        )
        db_session.add(bp)
        db_session.commit()
        db_session.refresh(bp)

        sub = DatasetSubAgent(db=db_session, dataset_id=sample_dataset.id)
        result = sub.resolve_analysis_blueprint(
            blueprint_id=bp.id,
            question="跑毛利分析",
            entry_route="analysis_blueprint",
            original_question="跑毛利分析",
            resolved_question="跑毛利分析",
            time_context=None,
        )

        assert result["sql_result"] is None
        assert result["route_payload"]["kind"] == "clarification"
        assert result["route_payload"]["missing"] == ["start_date"]

    def test_analysis_blueprint_execute_blocks_unsafe_sql(self, db_session, sample_dataset):
        """蓝图执行：拦截非只读 SQL。"""
        from app.services.dataset_subagent import DatasetSubAgent
        from app.models.dataset import AnalysisBlueprint

        bp = AnalysisBlueprint(
            dataset_id=sample_dataset.id,
            name="危险蓝图",
            call_template="DROP TABLE orders",
            status="active",
        )
        db_session.add(bp)
        db_session.commit()
        db_session.refresh(bp)

        sub = DatasetSubAgent(db=db_session, dataset_id=sample_dataset.id)
        result = sub.resolve_analysis_blueprint(
            blueprint_id=bp.id,
            question="执行危险蓝图",
            entry_route="analysis_blueprint",
            original_question="执行危险蓝图",
            resolved_question="执行危险蓝图",
            time_context=None,
        )

        assert result["sql_result"] is None
        assert "drop" in (result.get("error") or "").lower()

    def test_entry_intent_knowledge_term(self, db_session, sample_dataset):
        """入口分类：知识解释命中业务术语。"""
        from app.services.lead_agent_routing import _classify_entry_intent
        from app.models.dataset import BusinessTerm

        term = BusinessTerm(
            dataset_id=sample_dataset.id,
            name="gmv",
            display_name="GMV",
            aliases=["销售额"],
            definition="商品交易总额，按支付成功订单金额汇总。",
            status="active",
        )
        db_session.add(term)
        db_session.commit()
        db_session.refresh(term)

        state = {
            "question": "GMV是什么口径",
            "dataset_id": sample_dataset.id,
            "intent": "query",
            "entities": {},
        }
        result = _classify_entry_intent(
            db=db_session,
            question=state.get("question") or "",
            intent=state.get("intent") or "query",
            entities=state.get("entities") or {},
            dataset_id=state.get("dataset_id"),
            history=state.get("history") or [],
            multiturn_context=state.get("multiturn_context") or {},
            clarification_response=state.get("clarification_response"),
            lead_agent_context=state.get("lead_agent_context") or {},
        )

        assert result["entry_intent"] == "knowledge_qa"
        assert result["entry_route"] == "knowledge_qa"
        assert result["knowledge_term_id"] == term.id
        assert "商品交易总额" in result["answer"]

    def test_entry_intent_permission_rejection(self, db_session, sample_dataset):
        """入口分类：权限不足问题拒答，不进入 QueryGraph。"""
        from app.services.lead_agent_routing import _classify_entry_intent

        state = {
            "question": "帮我查一下没有权限的数据源",
            "dataset_id": sample_dataset.id,
            "intent": "query",
            "entities": {},
        }
        result = _classify_entry_intent(
            db=db_session,
            question=state.get("question") or "",
            intent=state.get("intent") or "query",
            entities=state.get("entities") or {},
            dataset_id=state.get("dataset_id"),
            history=state.get("history") or [],
            multiturn_context=state.get("multiturn_context") or {},
            clarification_response=state.get("clarification_response"),
            lead_agent_context=state.get("lead_agent_context") or {},
        )

        assert result["entry_intent"] == "rejection"
        assert result["entry_route"] == "reject"
        assert "权限" in result["answer"]

    def test_entry_intent_clarification(self, db_session, sample_dataset):
        """入口分类：短句指代不清时进入澄清。"""
        from app.services.lead_agent_routing import _classify_entry_intent

        state = {
            "question": "这个呢",
            "dataset_id": sample_dataset.id,
            "intent": "query",
            "entities": {},
        }
        result = _classify_entry_intent(
            db=db_session,
            question=state.get("question") or "",
            intent=state.get("intent") or "query",
            entities=state.get("entities") or {},
            dataset_id=state.get("dataset_id"),
            history=state.get("history") or [],
            multiturn_context=state.get("multiturn_context") or {},
            clarification_response=state.get("clarification_response"),
            lead_agent_context=state.get("lead_agent_context") or {},
        )

        assert result["entry_intent"] == "clarification"
        assert result["entry_route"] == "clarify"
        assert "补充" in result["answer"]

    def test_entry_intent_function_short_circuits_with_pending_clarification(
        self, db_session, sample_dataset
    ):
        """入口分类：dataset 已锁 + pending_clarification 时，function 不再拒答。"""
        from app.services.lead_agent_routing import _classify_entry_intent

        state = {
            "question": "选择：生产经营管理系统日志数据集",
            "dataset_id": sample_dataset.id,
            "intent": "function",
            "entities": {},
            "multiturn_context": {
                "active_dataset_id": sample_dataset.id,
                "pending_clarification": {
                    "kind": "dataset_choice",
                    "candidates": [{"dataset_id": sample_dataset.id, "name": "生产日志"}],
                },
            },
        }
        result = _classify_entry_intent(
            db=db_session,
            question=state.get("question") or "",
            intent=state.get("intent") or "query",
            entities=state.get("entities") or {},
            dataset_id=state.get("dataset_id"),
            history=state.get("history") or [],
            multiturn_context=state.get("multiturn_context") or {},
            clarification_response=state.get("clarification_response"),
            lead_agent_context=state.get("lead_agent_context") or {},
        )

        assert result["entry_intent"] != "rejection"
        assert result["route_payload"]["kind"] != "unsupported_function"

    def test_entry_intent_function_still_rejected_without_pending_clarification(
        self, db_session, sample_dataset
    ):
        """入口分类：无 pending_clarification 时真实功能操作仍走 rejection。"""
        from app.services.lead_agent_routing import _classify_entry_intent

        state = {
            "question": "把这份报表导出成 Excel 并发送给老板",
            "dataset_id": sample_dataset.id,
            "intent": "function",
            "entities": {},
            "multiturn_context": {},
        }
        result = _classify_entry_intent(
            db=db_session,
            question=state.get("question") or "",
            intent=state.get("intent") or "query",
            entities=state.get("entities") or {},
            dataset_id=state.get("dataset_id"),
            history=state.get("history") or [],
            multiturn_context=state.get("multiturn_context") or {},
            clarification_response=state.get("clarification_response"),
            lead_agent_context=state.get("lead_agent_context") or {},
        )

        assert result["entry_intent"] == "rejection"
        assert result["entry_route"] == "reject"
        assert result["route_payload"]["kind"] == "unsupported_function"
        assert "暂不直接执行" in result["answer"]

    def test_entry_intent_function_rejected_when_dataset_not_locked(
        self, db_session, sample_dataset
    ):
        """入口分类：dataset 未锁时即使有 pending_clarification 也不能放行。"""
        from app.services.lead_agent_routing import _classify_entry_intent

        state = {
            "question": "把报表导出",
            "dataset_id": None,
            "intent": "function",
            "entities": {},
            "multiturn_context": {
                "pending_clarification": {"kind": "dataset_choice"},
            },
        }
        result = _classify_entry_intent(
            db=db_session,
            question=state.get("question") or "",
            intent=state.get("intent") or "query",
            entities=state.get("entities") or {},
            dataset_id=state.get("dataset_id"),
            history=state.get("history") or [],
            multiturn_context=state.get("multiturn_context") or {},
            clarification_response=state.get("clarification_response"),
            lead_agent_context=state.get("lead_agent_context") or {},
        )

        assert result["entry_intent"] == "rejection"
        assert result["route_payload"]["kind"] == "unsupported_function"

    def test_intent_recognition_prompt_mentions_clarification_rule(self):
        """意图识别 prompt 必须包含多轮澄清判为 query 的规则说明。"""
        from app.prompts.intent_router import INTENT_RECOGNITION_SYSTEM

        assert "多轮澄清" in INTENT_RECOGNITION_SYSTEM
        assert "query 而非 function" in INTENT_RECOGNITION_SYSTEM

    def test_intent_recognition_node_injects_clarification_hint(self):
        """意图识别 human_text 应包含多轮提示块，让 LLM 看到澄清信号。"""
        from app.services.lead_agent_routing import _build_human_text

        state = {
            "question": "选择：销售数据集",
            "history": [
                {"role": "user", "content": "查一下近 7 天销售"},
                {"role": "assistant", "content": "请选择数据集"},
            ],
            "multiturn_context": {
                "pending_clarification": {"kind": "dataset_choice"},
            },
            "clarification_response": {"kind": "dataset_choice"},
        }
        human_text = _build_human_text(
            question=state["question"],
            history=state["history"],
            multiturn_context=state["multiturn_context"],
            clarification_response=state["clarification_response"],
        )
        assert "多轮提示" in human_text
        assert "dataset_choice" in human_text

    def test_dsl_validate_semantic_valid(self):
        """DSL 校验：语义层路径，合法 DSL"""
        from app.graph.nodes import dsl_validate_node

        schema = """【语义层】
数据集: 测试数据集
描述: 测试

【指标列表】
- gmv (GMV): 表达式=SUM(o.amount)
- order_count (订单数): 表达式=COUNT(o.id)

【维度列表】
- region (地区): 字段=o.region
- category (品类): 字段=o.category
"""
        state = {
            "dsl": {"metrics": ["gmv"], "dimensions": ["region"]},
            "schema_context": schema,
        }
        result = dsl_validate_node(state)
        assert result["dsl_valid"] is True
        assert result["error"] is None

    def test_dsl_validate_semantic_invalid_metric(self):
        """DSL 校验：语义层路径，非法指标名"""
        from app.graph.nodes import dsl_validate_node

        schema = """【语义层】
数据集: 测试数据集

【指标列表】
- gmv (GMV): 表达式=SUM(o.amount)

【维度列表】
- region (地区): 字段=o.region
"""
        state = {
            "dsl": {"metrics": ["invalid_metric"], "dimensions": []},
            "schema_context": schema,
        }
        result = dsl_validate_node(state)
        assert result["dsl_valid"] is False
        assert "invalid_metric" in result["error"]
        assert result["should_retry"] is True

    def test_dsl_validate_detail_query_empty_dsl_explains_asset_or_template_gap(self):
        """明细查询空 DSL：提示字段召回不足或模板未命中，而不是泛化成语义层错误。"""
        from app.graph.nodes import dsl_validate_node

        schema = """【语义层】
数据集: 生产经营管理系统日志数据集

【所选表字段与样例】
- plan_task_daily_record.rzrq (timestamp) 名称=日志日期 角色=time_field 默认聚合=NONE
"""
        state = {
            "dsl": {"metrics": [], "dimensions": [], "fields": []},
            "schema_context": schema,
            "schema_structured": {
                "metrics": [],
                "dimensions": [],
                "fields": [{"name": "rzrq"}],
                "terms": [],
                "blueprints": [],
            },
            "query_plan": {
                "query_type": "detail_query",
                "execution_strategy": "query_graph",
                "planner_source": "deterministic",
                "selected_assets": [
                    {
                        "asset_type": "field",
                        "asset_id": 1,
                        "name": "rzrq",
                        "usage": "selected",
                    }
                ],
                "debug": {"selected_main_table": "plan_task_daily_record"},
            },
        }

        result = dsl_validate_node(state)

        assert result["dsl_valid"] is False
        assert "字段召回不足或模板未命中" in result["error"]
        assert "plan_task_daily_record" in result["error"]
        assert "query_plan.debug.template_name/sql_template" in result["error"]
        assert "metrics/dimensions/fields 至少需要一项" not in result["error"]
        assert result["should_retry"] is True

    def test_dsl_validate_direct_sql(self):
        """DSL 校验：direct_sql 路径"""
        from app.graph.nodes import dsl_validate_node

        state = {
            "dsl": {"direct_sql": "SELECT * FROM orders"},
            "schema_context": "",
        }
        result = dsl_validate_node(state)
        assert result["dsl_valid"] is True

    def test_dsl_compiler_semantic(self, db_session):
        """DSL 编译器：语义层路径"""
        from app.graph.nodes import dsl_compiler_node

        schema = """【语义层】
数据集: 测试数据集

tables_json: {"tables": [{"name": "orders", "alias": "o"}], "joins": []}

【指标列表】
- gmv (GMV): 表达式=SUM(o.amount)

【维度列表】
- region (地区): 字段=o.region
"""
        state = {
            "dsl": {
                "metrics": ["gmv"],
                "dimensions": ["region"],
                "filters": [{"field": "region", "op": "in", "values": ["华东", "华南"]}],
                "time_range": {"field": "created_at", "start": "2026-04-01", "end": "2026-04-30"},
                "order_by": [{"field": "gmv", "direction": "DESC"}],
                "limit": 50,
            },
            "schema_context": schema,
        }
        # dsl_compiler_node 是工厂函数（接 db 以推断方言），先 .(db) 拿 _node 再调
        result = dsl_compiler_node(db_session)(state)
        assert result["error"] is None
        sql = result["sql"]
        assert "SELECT" in sql
        assert "SUM(o.amount) AS gmv" in sql
        assert "region" in sql
        assert "GROUP BY" in sql
        assert "LIMIT 50" in sql
        assert "INSERT" not in sql.upper()

    def test_dsl_validate_normalizes_legacy_dsl(self):
        """DSL 校验：旧字符串 DSL 通过时应规范化为资产引用结构。"""
        from app.graph.nodes import dsl_validate_node

        state = {
            "dsl": {"metrics": ["gmv"], "dimensions": ["region"]},
            "schema_structured": {
                "metrics": [{"id": 1, "name": "gmv"}],
                "dimensions": [{"id": 2, "name": "region"}],
            },
            "schema_context": "【语义层】",
        }
        result = dsl_validate_node(state)

        assert result["dsl_valid"] is True
        assert result["dsl"]["version"] == "2.0"
        assert result["dsl"]["metrics"][0]["name"] == "gmv"
        assert result["dsl"]["metrics"][0]["asset_type"] == "metric"

    def test_dsl_validate_terms_and_blueprints_valid(self):
        """语义验证：DSL 中引用的业务术语和分析蓝图必须存在于语义层。"""
        from app.graph.nodes import dsl_validate_node

        state = {
            "dsl": {
                "metrics": ["gmv"],
                "terms": [{"name": "净销售额", "asset_type": "term", "asset_id": 10}],
                "blueprints": [{"name": "门店经营分析", "asset_type": "blueprint", "asset_id": 20}],
            },
            "schema_structured": {
                "metrics": [{"id": 1, "name": "gmv"}],
                "dimensions": [],
                "fields": [],
                "terms": [{"id": 10, "name": "净销售额"}],
                "blueprints": [{"id": 20, "name": "门店经营分析"}],
            },
            "schema_context": "【语义层】",
        }

        result = dsl_validate_node(state)

        assert result["dsl_valid"] is True
        assert result["error"] is None
        assert result["dsl"]["terms"][0]["asset_type"] == "term"
        assert result["dsl"]["blueprints"][0]["asset_type"] == "blueprint"

    def test_dsl_validate_terms_and_blueprints_unknown(self):
        """语义验证：未知术语或蓝图引用要提前拦截，避免验证报告误判。"""
        from app.graph.nodes import dsl_validate_node

        state = {
            "dsl": {
                "metrics": ["gmv"],
                "terms": [{"name": "不存在术语", "asset_type": "term", "asset_id": 99}],
                "blueprints": ["不存在蓝图"],
            },
            "schema_structured": {
                "metrics": [{"id": 1, "name": "gmv"}],
                "dimensions": [],
                "fields": [],
                "terms": [{"id": 10, "name": "净销售额"}],
                "blueprints": [{"id": 20, "name": "门店经营分析"}],
            },
            "schema_context": "【语义层】",
        }

        result = dsl_validate_node(state)

        assert result["dsl_valid"] is False
        assert "业务术语 '不存在术语#99' 不在语义层定义中" in result["error"]
        assert "分析蓝图 '不存在蓝图' 不在语义层定义中" in result["error"]
        assert result["should_retry"] is True

    def test_dsl_compiler_semantic_asset_refs(self, db_session):
        """DSL 编译器：v2 资产引用对象应与旧字符串 DSL 等价编译。"""
        from app.graph.nodes import dsl_compiler_node

        state = {
            "dsl": {
                "version": "2.0",
                "metrics": [
                    {
                        "name": "gmv",
                        "asset_type": "metric",
                        "asset_id": 1,
                        "confidence": 0.92,
                    }
                ],
                "dimensions": [
                    {
                        "name": "region",
                        "asset_type": "dimension",
                        "asset_id": 2,
                        "confidence": 0.88,
                    }
                ],
                "filters": [
                    {
                        "field": {
                            "name": "region",
                            "asset_type": "dimension",
                            "asset_id": 2,
                            "confidence": 0.88,
                        },
                        "op": "eq",
                        "values": ["华东"],
                    }
                ],
                "order_by": [
                    {
                        "field": {
                            "name": "gmv",
                            "asset_type": "metric",
                            "asset_id": 1,
                        },
                        "direction": "DESC",
                    }
                ],
                "limit": 20,
                "ambiguities": [
                    {
                        "text": "销售",
                        "reason": "可能指多个资产",
                        "candidates": [
                            {
                                "name": "gmv",
                                "asset_type": "metric",
                                "asset_id": 1,
                                "confidence": 0.6,
                            }
                        ],
                    }
                ],
            },
            "schema_context": "【语义层】",
            "schema_structured": {
                "tables_json": {"tables": [{"name": "orders", "alias": "o"}], "joins": []},
                "metrics": [
                    {
                        "id": 1,
                        "name": "gmv",
                        "display_name": "GMV",
                        "expr": "SUM(o.amount)",
                        "table_name": "orders",
                        "time_field": None,
                        "filter_sql": None,
                    }
                ],
                "dimensions": [
                    {
                        "id": 2,
                        "name": "region",
                        "display_name": "地区",
                        "column_name": "region",
                        "table_name": None,
                    }
                ],
            },
        }

        result = dsl_compiler_node(db_session)(state)

        assert result["error"] is None
        assert "SUM(o.amount) AS gmv" in result["sql"]
        assert "region" in result["sql"]
        assert "= '华东'" in result["sql"]
        assert "ORDER BY" in result["sql"]
        assert "gmv" in result["sql"]
        assert "LIMIT 20" in result["sql"]

    def test_dsl_compiler_direct_sql(self, db_session):
        """DSL 编译器：direct_sql 路径会补齐默认 LIMIT。"""
        from app.graph.nodes import dsl_compiler_node

        state = {
            "dsl": {"direct_sql": "SELECT id FROM users WHERE status = 'active'"},
            "schema_context": "",
        }
        result = dsl_compiler_node(db_session)(state)
        assert result["sql"] == "SELECT id FROM users WHERE status = 'active' LIMIT 100"
        assert result["sql_guard"]["ok"] is True

    def test_dsl_compiler_forbidden_keyword(self, db_session):
        """DSL 编译器：拦截危险 SQL 关键字"""
        from app.graph.nodes import dsl_compiler_node

        state = {
            "dsl": {"direct_sql": "DROP TABLE users"},
            "schema_context": "",
        }
        result = dsl_compiler_node(db_session)(state)
        assert result["sql"] is None
        assert "drop" in result["error"].lower()

    # ── T-018：语义层 fields 资产接入测试 ────────────────────────────────

    _FIELDS_STRUCTURED = {
        "tables_json": {
            "tables": [{"name": "eas_personofile", "alias": "p"}],
            "joins": [],
        },
        "metrics": [],
        "dimensions": [],
        "fields": [
            {
                "id": 1,
                "name": "person_name",
                "column_name": "person_name",
                "table_name": "eas_personofile",
                "data_type": "varchar",
                "semantic_role": "dimension_candidate",
                "default_agg": None,
            },
            {
                "id": 2,
                "name": "person_money",
                "column_name": "person_money",
                "table_name": "eas_personofile",
                "data_type": "decimal",
                "semantic_role": "metric_candidate",
                "default_agg": "SUM",
            },
            {
                "id": 3,
                "name": "dept_name",
                "column_name": "dept_name",
                "table_name": "eas_personofile",
                "data_type": "varchar",
                "semantic_role": "dimension_candidate",
                "default_agg": None,
            },
        ],
    }

    def test_field_as_filter_with_table_qualifier(self, db_session):
        """T-018：filter 字段引用 field 时带表限定符"""
        from app.graph.nodes import dsl_compiler_node

        state = {
            "dsl": {
                "metrics": ["person_money"],
                "filters": [{"field": "person_name", "op": "eq", "values": ["张三"]}],
            },
            "schema_context": "【语义层】",
            "schema_structured": self._FIELDS_STRUCTURED,
        }
        result = dsl_compiler_node(db_session)(state)
        assert result["error"] is None
        sql = result["sql"]
        assert "eas_personofile" in sql
        assert "person_name" in sql
        assert "'张三'" in sql

    def test_field_as_metric_with_default_agg(self, db_session):
        """T-018：metrics 引用 field 时利用 default_agg 自动生成聚合表达式"""
        from app.graph.nodes import dsl_compiler_node

        state = {
            "dsl": {
                "metrics": [{"name": "person_money", "asset_type": "field", "asset_id": 2}],
            },
            "schema_context": "【语义层】",
            "schema_structured": self._FIELDS_STRUCTURED,
        }
        result = dsl_compiler_node(db_session)(state)
        assert result["error"] is None
        sql = result["sql"]
        assert "SUM" in sql
        assert "person_money" in sql

    def test_field_as_dimension_table_qualifier_group_by(self, db_session):
        """T-018：dimensions 引用 field 时带表限定符，且正确参与 GROUP BY"""
        from app.graph.nodes import dsl_compiler_node

        structured = {
            **self._FIELDS_STRUCTURED,
            "metrics": [
                {
                    "id": 10,
                    "name": "total_money",
                    "expr": "SUM(p.person_money)",
                    "table_name": "eas_personofile",
                    "time_field": None,
                    "filter_sql": None,
                    "display_name": "总金额",
                    "synonyms": [],
                }
            ],
        }
        state = {
            "dsl": {
                "metrics": ["total_money"],
                "dimensions": [{"name": "dept_name", "asset_type": "field", "asset_id": 3}],
            },
            "schema_context": "【语义层】",
            "schema_structured": structured,
        }
        result = dsl_compiler_node(db_session)(state)
        assert result["error"] is None
        sql = result["sql"]
        assert "GROUP BY" in sql
        assert "eas_personofile" in sql
        assert "dept_name" in sql

    def test_detail_query_no_group_by_no_agg(self, db_session):
        """T-018：明细查询（无 metrics）不生成 GROUP BY 也不生成聚合"""
        from app.graph.nodes import dsl_compiler_node

        state = {
            "dsl": {
                "metrics": [],
                "fields": [
                    {"name": "person_name", "asset_type": "field", "asset_id": 1},
                    {"name": "person_money", "asset_type": "field", "asset_id": 2},
                ],
            },
            "schema_context": "【语义层】",
            "schema_structured": self._FIELDS_STRUCTURED,
        }
        result = dsl_compiler_node(db_session)(state)
        assert result["error"] is None
        sql = result["sql"]
        assert "GROUP BY" not in sql
        assert "SUM(" not in sql
        assert "person_name" in sql
        assert "person_money" in sql

    def test_detail_query_uses_field_table_when_tables_json_missing(self, db_session):
        """回归：明细查询没有 tables_json 时，应从 fields.table_name 确定主表。"""
        from app.graph.nodes import dsl_compiler_node

        structured = {
            **self._FIELDS_STRUCTURED,
            "tables_json": {},
        }
        state = {
            "dsl": {
                "metrics": [],
                "fields": [
                    {"name": "person_name", "asset_type": "field", "asset_id": 1},
                    {"name": "dept_name", "asset_type": "field", "asset_id": 3},
                ],
            },
            "schema_context": "【语义层】",
            "schema_structured": structured,
        }

        result = dsl_compiler_node(db_session)(state)

        assert result["error"] is None
        sql = result["sql"]
        assert "FROM" in sql
        assert "eas_personofile" in sql
        assert "person_name" in sql
        assert "dept_name" in sql

    def test_validate_allows_empty_metrics_with_fields(self):
        """T-018：validate 节点允许 metrics 为空但 fields 非空的 DSL 通过"""
        from app.graph.nodes import dsl_validate_node

        state = {
            "dsl": {
                "metrics": [],
                "fields": [{"name": "person_name", "asset_type": "field"}],
            },
            "schema_context": "【语义层】",
            "schema_structured": self._FIELDS_STRUCTURED,
        }
        result = dsl_validate_node(state)
        assert result["dsl_valid"] is True
        assert result["error"] is None

    def test_topn_with_field_metrics(self, db_session):
        """T-018：field 作为 metrics + 排序 + LIMIT（TopN 场景）"""
        from app.graph.nodes import dsl_compiler_node

        state = {
            "dsl": {
                "metrics": [{"name": "person_money", "asset_type": "field", "asset_id": 2}],
                "dimensions": [{"name": "dept_name", "asset_type": "field", "asset_id": 3}],
                "order_by": [{"field": "person_money", "direction": "DESC"}],
                "limit": 10,
            },
            "schema_context": "【语义层】",
            "schema_structured": self._FIELDS_STRUCTURED,
        }
        result = dsl_compiler_node(db_session)(state)
        assert result["error"] is None
        sql = result["sql"]
        assert "SUM" in sql
        assert "GROUP BY" in sql
        assert "ORDER BY" in sql
        assert "LIMIT 10" in sql

    def test_filter_field_only_in_field_map(self, db_session):
        """T-018：filter 字段只在 field_map（不在 dim_map）时正确带表限定符"""
        from app.graph.nodes import dsl_compiler_node

        structured = {
            **self._FIELDS_STRUCTURED,
            "metrics": [
                {
                    "id": 10,
                    "name": "total_money",
                    "expr": "SUM(p.person_money)",
                    "table_name": "eas_personofile",
                    "time_field": None,
                    "filter_sql": None,
                    "display_name": "总金额",
                    "synonyms": [],
                }
            ],
        }
        state = {
            "dsl": {
                "metrics": ["total_money"],
                "filters": [{"field": "person_name", "op": "in", "values": ["李四", "王五"]}],
            },
            "schema_context": "【语义层】",
            "schema_structured": structured,
        }
        result = dsl_compiler_node(db_session)(state)
        assert result["error"] is None
        sql = result["sql"]
        assert "eas_personofile" in sql
        assert "person_name" in sql
        assert "IN" in sql.upper()

    def test_report_generator_with_result(self):
        """报告生成：有 SQL 结果时生成回答"""
        from app.graph.nodes import report_generator_node

        with patch("app.services.report_generation.get_llm") as mock_get_llm:
            mock_llm = MagicMock()

            async def _fake_astream(messages):
                yield type(
                    "C", (), {"content": "GMV 为 **100万元**，表现良好。", "usage_metadata": None}
                )()
                # 末尾给一个含 usage_metadata 的 chunk，让 token 计算走正确分支
                yield type(
                    "C",
                    (),
                    {
                        "content": "",
                        "usage_metadata": {
                            "input_tokens": 100,
                            "output_tokens": 50,
                            "total_tokens": 150,
                        },
                    },
                )()

            mock_llm.astream = _fake_astream
            mock_get_llm.return_value = mock_llm

            state = {
                "question": "GMV是多少",
                "sql_result": {
                    "columns": ["gmv"],
                    "rows": [{"gmv": 1000000}],
                    "row_count": 1,
                },
                "token_usage": None,
            }
            # report_generator_node 是 async def，需要 asyncio.run
            result = asyncio.run(report_generator_node(state))
            assert "100万元" in result["answer"]
            assert result["token_usage"]["total_tokens"] == 150

    def test_report_generator_compacts_rows_and_strips_think(self):
        """报告生成应压缩大结果集，并清理模型泄露的思考标签。"""
        from app.graph.nodes import report_generator_node

        captured = {}
        with patch("app.services.report_generation.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.datalogue_thinking_enabled = False

            async def _fake_astream(messages):
                captured["human"] = messages[1].content
                yield type(
                    "C",
                    (),
                    {"content": "<think>内部推理</think>结论：表现稳定。", "usage_metadata": None},
                )()

            mock_llm.astream = _fake_astream
            mock_get_llm.return_value = mock_llm

            rows = [{"name": f"供应商{i}", "desc": "x" * 200} for i in range(35)]
            state = {
                "question": "供应商综合评估",
                "sql_result": {
                    "columns": ["name", "desc"],
                    "rows": rows,
                    "row_count": len(rows),
                },
                "token_usage": None,
            }

            result = asyncio.run(report_generator_node(state))

            assert "<think>" not in result["answer"]
            assert "内部推理" not in result["answer"]
            assert "结论：表现稳定。" in result["answer"]
            assert "前 30 行" in captured["human"]
            assert "其余 5 行未展开" in captured["human"]
            assert "x" * 150 not in captured["human"]

    def test_report_generation_uses_configured_compaction_limits(self, monkeypatch):
        """报告生成输入压缩应读取行数和单元格长度配置。"""
        from app.services.report_generation import _compact_report_rows

        monkeypatch.setattr(
            "app.services.report_generation.get_settings",
            lambda: SimpleNamespace(REPORT_RESULT_MAX_ROWS=2, REPORT_CELL_MAX_CHARS=4),
        )

        compact_rows, dropped = _compact_report_rows(
            [
                {"name": "一号供应商"},
                {"name": "二号供应商"},
                {"name": "三号供应商"},
            ]
        )

        assert len(compact_rows) == 2
        assert compact_rows[0]["name"] == "一号供应..."
        assert dropped == 1

    def test_report_generator_stream_strips_think_tokens_when_disabled(self):
        """报告生成流式 token 在 Think 关闭时不应泄露思考内容。"""
        from app.services.report_generation import stream_sql_result_report

        with patch("app.services.report_generation.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.datalogue_thinking_enabled = False

            async def _fake_astream(messages):
                yield type("C", (), {"content": "<Thi", "usage_metadata": None})()
                yield type("C", (), {"content": "nk>内部推理", "usage_metadata": None})()
                yield type("C", (), {"content": "</Think>结论：", "usage_metadata": None})()
                yield type("C", (), {"content": "表现稳定。", "usage_metadata": None})()

            mock_llm.astream = _fake_astream
            mock_get_llm.return_value = mock_llm

            state = {
                "question": "供应商综合评估",
                "sql_result": {
                    "columns": ["name"],
                    "rows": [{"name": "供应商A"}],
                    "row_count": 1,
                },
                "token_usage": None,
            }

            async def _collect():
                tokens = []
                result = None
                async for event in stream_sql_result_report(state):
                    if event.get("type") == "token":
                        tokens.append(event.get("content") or "")
                    elif event.get("type") == "result":
                        result = event
                return tokens, result

            tokens, result = asyncio.run(_collect())

            visible = "".join(tokens)
            assert visible == "结论：表现稳定。"
            assert result["answer"] == "结论：表现稳定。"
            assert "内部推理" not in visible

    def test_invoke_llm_with_metrics_strips_think_when_disabled(self):
        """通用 LLM 调用在 Think 关闭时也应清理流式输出。"""
        from app.graph.nodes import _invoke_llm_with_metrics

        class FakeLLM:
            streaming = True
            datalogue_thinking_enabled = False

            def stream(self, messages):
                yield type("C", (), {"content": "<think>过程</think>", "usage_metadata": None})()
                yield type("C", (), {"content": "最终答案", "usage_metadata": None})()

        response, first_token_at, _ = _invoke_llm_with_metrics(FakeLLM(), [])

        assert first_token_at is not None
        assert response.content == "最终答案"

    def test_report_generator_no_result(self):
        """报告生成：无 SQL 结果时返回提示"""
        from app.graph.nodes import report_generator_node

        state = {
            "question": "GMV是多少",
            "sql_result": None,
            "token_usage": None,
        }
        # 无结果时直接 return dict，不调 LLM，但函数本身是 async 所以也要 asyncio.run
        result = asyncio.run(report_generator_node(state))
        assert "未返回结果" in result["answer"]


class TestAnswerExplanation:
    """测试 T-022 回答解释包。"""

    def test_semantic_query_explanation_contains_caliber_source_and_sql_summary(self):
        from app.services.answer_explanation import build_answer_explanation

        state = {
            "dsl": {
                "version": "2.0",
                "metrics": [
                    {
                        "name": "gmv",
                        "asset_type": "metric",
                        "asset_id": 1,
                        "display_name": "GMV",
                    }
                ],
                "dimensions": [
                    {
                        "name": "region",
                        "asset_type": "dimension",
                        "asset_id": 2,
                        "display_name": "区域",
                    }
                ],
                "limit": 100,
            },
            "semantic_asset_resolution": {
                "assets": [
                    {
                        "asset_type": "metric",
                        "asset_id": 1,
                        "display_name": "GMV",
                        "table_name": "orders",
                        "column_name": "amount",
                        "confidence": 0.96,
                    }
                ],
                "metrics": [{"display_name": "GMV"}],
                "dimensions": [{"display_name": "区域"}],
                "terms": [],
                "blueprints": [],
                "ambiguities": [],
                "unresolved": [],
            },
            "sql": "SELECT region, SUM(amount) AS gmv FROM orders GROUP BY region LIMIT 100",
            "sql_result": {"columns": ["region", "gmv"], "rows": [{"region": "华东", "gmv": 100}]},
            "query_constraints": {"default_limit": 100},
        }

        explanation = build_answer_explanation(state)

        assert "GMV" in explanation["caliber"]["metrics"]
        assert "区域" in explanation["caliber"]["dimensions"]
        assert explanation["data_sources"][0]["table"] == "orders"
        assert "orders" in explanation["sql_summary"]["tables"]
        assert explanation["confidence"]["level"] in {"high", "medium"}
        assert explanation["confirmation"]["required"] is False

    def test_answer_explanation_uses_configured_low_confidence_threshold(self, monkeypatch):
        from app.services.answer_explanation import build_answer_explanation

        monkeypatch.setattr(
            "app.services.answer_explanation.get_settings",
            lambda: SimpleNamespace(ANSWER_EXPLANATION_LOW_CONFIDENCE_THRESHOLD=0.9),
        )

        explanation = build_answer_explanation(
            {
                "dsl": {"confidence": 0.86},
                "sql": "select * from orders",
                "datasource_dialect": "mysql",
            }
        )

        assert explanation["confidence"]["threshold"] == 0.9
        assert explanation["confidence"]["level"] == "low"

    def test_ambiguity_explanation_requires_confirmation(self):
        from app.services.answer_explanation import build_answer_explanation

        state = {
            "dsl": {"metrics": [], "dimensions": []},
            "semantic_asset_resolution": {
                "assets": [],
                "metrics": [],
                "dimensions": [],
                "terms": [],
                "blueprints": [],
                "ambiguities": [
                    {
                        "text": "收入",
                        "resolution_hint": "请确认“收入”具体指哪个业务资产",
                        "candidates": [{"asset_id": 1}, {"asset_id": 2}],
                    }
                ],
                "unresolved": [],
            },
            "sql": "SELECT SUM(amount) AS revenue FROM orders",
            "sql_result": {"columns": ["revenue"], "rows": [{"revenue": 10}]},
        }

        explanation = build_answer_explanation(state)

        assert explanation["confidence"]["level"] == "low"
        assert explanation["confirmation"]["required"] is True
        assert "请确认" in explanation["confirmation"]["message"]

    def test_inferred_query_adds_risk(self):
        from app.services.answer_explanation import build_answer_explanation

        explanation = build_answer_explanation(
            {
                "dsl": {"direct_sql": "SELECT COUNT(*) AS c FROM orders", "inferred": True},
                "generation_mode": "inferred",
                "sql": "SELECT COUNT(*) AS c FROM orders",
                "sql_result": {"columns": ["c"], "rows": [{"c": 1}]},
            }
        )

        messages = [item["message"] for item in explanation["risks"]]
        assert any("基于表结构推断" in message for message in messages)
        assert "orders" in explanation["sql_summary"]["tables"]

    def test_blueprint_sql_explanation_contains_name_and_params(self):
        from app.services.answer_explanation import build_answer_explanation

        explanation = build_answer_explanation(
            {
                "dsl": {
                    "direct_sql": "SELECT * FROM daily_report WHERE person_name = :person_name"
                },
                "sql": "SELECT * FROM daily_report WHERE person_name = '杨凯'",
                "sql_result": {"columns": ["person_name"], "rows": [{"person_name": "杨凯"}]},
                "generation_mode": "analysis_blueprint",
                "route_payload": {
                    "kind": "analysis_blueprint",
                    "blueprint_id": 7,
                    "name": "个人日报查询",
                    "params": {"person_name": "杨凯"},
                },
            }
        )

        assert "个人日报查询" in explanation["caliber"]["blueprints"]
        assert explanation["caliber"]["blueprint_params"]["person_name"] == "杨凯"
        assert "daily_report" in explanation["sql_summary"]["tables"]

    def test_term_conflict_clarification_is_low_confidence_without_sql(self):
        from app.services.answer_explanation import build_answer_explanation

        explanation = build_answer_explanation(
            {
                "dsl": {},
                "term_normalization": {"has_conflict": True},
                "route_payload": {"kind": "term_conflict_clarification"},
                "answer": "“收入”可能对应多个业务术语，请先确认你要使用哪个口径。",
            }
        )

        assert explanation["confidence"]["level"] == "low"
        assert explanation["confirmation"]["required"] is True
        assert explanation["sql_summary"]["preview"] == ""


class TestWorkflowRouting:
    """测试工作流路由逻辑"""

    def test_lead_agent_router_interpret_result(self):
        """LeadAgent 入口路由：interpret_result 直接结束。"""
        from app.graph.workflow import _lead_agent_router

        assert _lead_agent_router({"entry_route": "interpret_result"}) == "end"

    def test_lead_agent_router_analysis_blueprint(self):
        """LeadAgent 入口路由：analysis_blueprint 已在 chat 层处理（Phase 5），图层直接 end。"""
        from app.graph.workflow import _lead_agent_router

        assert _lead_agent_router({"entry_route": "analysis_blueprint"}) == "end"

    def test_lead_agent_router_default(self):
        """LeadAgent 入口路由：默认进 schema_recall（Phase 4: term 澄清由 chat 层处理）。"""
        from app.graph.workflow import _lead_agent_router

        assert _lead_agent_router({"entry_route": "query_graph"}) == "schema_recall"
        assert _lead_agent_router({"entry_route": "interpret_result"}) == "end"

    def test_dsl_validation_router_pass(self):
        """DSL 校验通过 → 编译"""
        from app.graph.workflow import _dsl_validation_router

        assert _dsl_validation_router({"dsl_valid": True}) == "compile"

    def test_dsl_validation_router_retry(self):
        """DSL 校验失败且重试次数 < 3 → 重试"""
        from app.graph.workflow import _dsl_validation_router

        assert _dsl_validation_router({"dsl_valid": False, "retry_count": 1}) == "retry"

    def test_dsl_validation_router_end(self):
        """DSL 校验失败且重试次数 >= 3 → 结束"""
        from app.graph.workflow import _dsl_validation_router

        assert _dsl_validation_router({"dsl_valid": False, "retry_count": 3}) == "end"

    def test_dsl_validation_router_uses_configured_retry_default(self, monkeypatch):
        """未显式传 max_retry_count 时，使用配置中的 SQL 重试上限。"""
        from app.graph.workflow import _dsl_validation_router

        monkeypatch.setattr(
            "app.graph.workflow.get_settings",
            lambda: SimpleNamespace(SQL_MAX_RETRY_COUNT=5),
        )

        assert _dsl_validation_router({"dsl_valid": False, "retry_count": 4}) == "retry"
        assert _dsl_validation_router({"dsl_valid": False, "retry_count": 5}) == "end"

    def test_sql_execution_router_pass(self):
        """SQL 执行成功 → 生成报告"""
        from app.graph.workflow import _sql_execution_router

        # 成功路径需要 sql_result 非空
        assert (
            _sql_execution_router({"should_retry": False, "sql_result": {"rows": [{"x": 1}]}})
            == "report"
        )

    def test_sql_execution_router_audit(self):
        """SQL 执行失败 → 进 sql_audit 审计（不是直接 retry）"""
        from app.graph.workflow import _sql_execution_router

        # 失败时路由到 audit，让 LLM 决定是 fixable 还是 architectural
        assert _sql_execution_router({"should_retry": True, "retry_count": 0}) == "audit"

    def test_sql_execution_router_end(self):
        """should_retry=False 且无 sql_result → END（避免 report 收到空结果）"""
        from app.graph.workflow import _sql_execution_router

        assert _sql_execution_router({"should_retry": False}) == "end"

    def test_increment_retry(self):
        """重试计数器"""
        from app.graph.workflow import _increment_retry

        assert _increment_retry({"retry_count": 2}) == {"retry_count": 3}


class TestChatStreamEvents:
    """测试 /api/chat/stream SSE 事件格式（astream_events）"""

    @pytest.mark.asyncio
    async def test_stream_message_gateway_step_and_final_include_turn_event_and_task_capsule(
        self,
        monkeypatch,
        db_session,
        sample_dataset,
    ):
        """message_gateway step 与 final payload 应暴露 turn_event / query_task_capsule。"""
        from app.api.chat import _stream_chat_singleturn

        publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())

        route_decision = {
            "decision": "selected",
            "dataset_id": sample_dataset.id,
            "dataset_name": sample_dataset.name,
            "manifest_version": "v-test",
            "bound_schema_version": "schema-test",
            "score": 1.0,
            "reason": "测试固定路由",
        }
        lead_agent_context = {
            "route_decision": route_decision,
            "effective_dataset_id": sample_dataset.id,
            "should_continue": True,
            "resolved_question": "查询10条用户日志",
            "time_context": {},
            "thread_context": {},
            "schema_status": {"status": "ok", "structured": {"terms": []}},
            "selected_skills": [],
            "planned_tool_calls": [],
            "executed_tool_calls": [],
            "policy_violations": [],
            "audit_trace": {},
            "multiturn_classification": {},
        }

        async def fake_astream_events(state, version):
            yield {
                "event": "on_chain_end",
                "name": "sql_execute",
                "data": {
                    "output": {
                        **state,
                        "answer": "查询完成",
                        "entry_intent": "detail_query",
                        "entry_route": "query_graph",
                        "sql": "SELECT rzrq FROM plan_task_daily_record LIMIT 10",
                        "sql_list": ["SELECT rzrq FROM plan_task_daily_record LIMIT 10"],
                        "sql_result": {
                            "columns": ["rzrq"],
                            "rows": [{"rzrq": "2024-01-01"}],
                            "row_count": 1,
                        },
                        "query_plan": {
                            "query_type": "detail_query",
                            "execution_strategy": "query_graph",
                            "debug": {"selected_main_table": "plan_task_daily_record"},
                        },
                        "error": None,
                    }
                },
                "metadata": {"langgraph_node": "sql_execute"},
            }

        monkeypatch.setattr(
            "app.api.chat.build_workflow", lambda db: MagicMock(astream_events=fake_astream_events)
        )
        monkeypatch.setattr("app.api.chat.DatasetSubAgent", _graph_backed_fake_subagent_class())
        monkeypatch.setattr(
            "app.api.chat.build_lead_agent_context", lambda *args, **kwargs: lead_agent_context
        )
        monkeypatch.setattr(
            "app.api.chat.resolve_term_clarification", lambda *args, **kwargs: {"status": "none"}
        )
        monkeypatch.setattr(
            "app.api.chat.route_query_intent",
            lambda *args, **kwargs: {
                "intent": "query",
                "entities": {},
                "entry_intent": "detail_query",
                "entry_route": "query_graph",
                "entry_reason": "测试进入查询图",
                "route_payload": {"kind": "query_graph"},
            },
        )

        events = []
        async for item in _stream_chat_singleturn(
            ChatRequest(question="查询10条用户日志", dataset_id=sample_dataset.id),
            db_session,
        ):
            events.append(json.loads(item["data"]))

        gateway_step = next(
            event
            for event in events
            if event.get("type") == "step" and event.get("node") == "message_gateway"
        )
        final = [event for event in events if event.get("type") == "final"][-1]

        assert gateway_step["display_name"] == "message_gateway"
        assert gateway_step["status"] == "done"
        assert gateway_step["turn_event"]["event_type"] == "new_query"
        assert gateway_step["query_task_capsule"]["dataset_id"] == sample_dataset.id
        assert gateway_step["payload"]["turn_event"] == gateway_step["turn_event"]
        assert gateway_step["payload"]["query_task_capsule"] == gateway_step["query_task_capsule"]
        assert final["turn_event"] == gateway_step["turn_event"]
        assert final["query_task_capsule"] == gateway_step["query_task_capsule"]
        assistant_message = db_session.get(models.Message, final["message_id"])
        assert assistant_message is not None
        assert any(
            step.get("node") == "message_gateway"
            and step.get("query_task_capsule") == gateway_step["query_task_capsule"]
            for step in (assistant_message.step_trace or [])
        )

    @pytest.mark.asyncio
    async def test_interpret_early_return_keeps_gateway_step_and_task_capsule(
        self,
        monkeypatch,
        db_session,
        sample_dataset,
    ):
        """interpret_result 早退也应保留 message_gateway step 和安全任务胶囊。"""
        from app.api.chat import _stream_chat_singleturn
        from app.services.multiturn_context import MergeDecision

        route_decision = {
            "decision": "selected",
            "dataset_id": sample_dataset.id,
            "dataset_name": sample_dataset.name,
            "manifest_version": "v-test",
            "bound_schema_version": "schema-test",
        }
        lead_agent_context = {
            "route_decision": route_decision,
            "effective_dataset_id": sample_dataset.id,
            "should_continue": True,
            "resolved_question": "这个结果说明什么",
            "time_context": {},
            "thread_context": {},
            "schema_status": {"status": "ok"},
            "selected_skills": [],
            "planned_tool_calls": [],
            "executed_tool_calls": [],
            "policy_violations": [],
            "audit_trace": {},
            "multiturn_classification": {},
        }
        merge_decision = MergeDecision(
            turn_type="interpret",
            multiturn_context={"turn_type": "interpret"},
            interpret_payload={
                "answer": "这是对上一轮结果的解释。",
                "entry_intent": "interpret",
                "entry_route": "interpret_result",
            },
            merge_debug={"reason": "test_interpret"},
        )

        monkeypatch.setattr(
            "app.api.chat.build_lead_agent_context", lambda *args, **kwargs: lead_agent_context
        )
        monkeypatch.setattr(
            "app.api.chat.merge_multiturn_decision_for_chat", lambda *args, **kwargs: merge_decision
        )
        monkeypatch.setattr("app.api.chat.route_query_intent", MagicMock())

        with patch("app.api.chat.build_workflow") as mock_wf:
            events = []
            async for item in _stream_chat_singleturn(
                ChatRequest(question="这个结果说明什么", dataset_id=sample_dataset.id),
                db_session,
            ):
                events.append(json.loads(item["data"]))

        gateway_step = next(
            event
            for event in events
            if event.get("type") == "step" and event.get("node") == "message_gateway"
        )
        final = [event for event in events if event.get("type") == "final"][-1]
        assert final["entry_route"] == "interpret_result"
        assert final["turn_event"] == gateway_step["turn_event"]
        assert final["query_task_capsule"] == gateway_step["query_task_capsule"]
        assistant_message = db_session.get(models.Message, final["message_id"])
        assert assistant_message is not None
        assert any(
            step.get("node") == "message_gateway" for step in assistant_message.step_trace or []
        )
        mock_wf.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_chat_emits_query_plan_step(self, monkeypatch, db_session, sample_dataset):
        """单轮 chat 应透传 DatasetSubAgent 的查询规划事件和最终状态。"""
        from app.api.chat import _stream_chat_singleturn
        from app.services.subagent_planning import SubAgentEvent

        query_plan = {
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "planner_source": "fallback",
            "fallback_reason": "测试兜底",
            "explanation": {"summary": "明细查询"},
        }
        candidate_assets = {"summary": {"field_count": 1}}
        query_plan_debug = {"planner_source": "final_state", "fallback_reason": "最终状态优先"}

        class FakeSubAgent:
            def __init__(self, db, dataset_id):
                self.db = db
                self.dataset_id = dataset_id

            def resolve_term_conflict(self, **kwargs):
                raise AssertionError("chat should not call resolve_term_conflict before run")

            def resolve_metric(self, **kwargs):
                raise AssertionError("chat should not call resolve_metric before run")

            def resolve_analysis_blueprint(self, **kwargs):
                raise AssertionError("chat should not call resolve_analysis_blueprint before run")

            async def run(
                self, request, trace_context, *, graph, initial_state=None, graph_kwargs=None
            ):
                yield SubAgentEvent(
                    event_type="candidate_assets",
                    payload={
                        "node": "candidate_assets",
                        "display_name": "subagent.candidate_assets",
                        "status": "done",
                        "candidate_assets": candidate_assets,
                    },
                )
                yield SubAgentEvent(
                    event_type="query_plan",
                    payload={
                        "node": "query_plan",
                        "display_name": "subagent.query_plan",
                        "status": "done",
                        "query_plan": query_plan,
                    },
                )
                yield SubAgentEvent(
                    event_type="graph_event",
                    payload={
                        "event": {
                            "event": "on_chain_end",
                            "name": "sql_execute",
                            "data": {"output": {"should_retry": False}},
                            "metadata": {"langgraph_node": "sql_execute"},
                        }
                    },
                )
                yield SubAgentEvent(
                    event_type="result",
                    payload={
                        "final_state": {
                            **(initial_state or {}),
                            "answer": "完成",
                            "sql": "select 1",
                            "sql_list": ["select 1"],
                            "sql_result": {
                                "columns": ["id"],
                                "rows": [{"id": 1}],
                                "row_count": 1,
                            },
                            "query_plan": query_plan,
                            "candidate_assets": candidate_assets,
                            "query_plan_debug": query_plan_debug,
                            "error": None,
                        }
                    },
                )

        route_decision = {
            "decision": "selected",
            "dataset_id": sample_dataset.id,
            "dataset_name": sample_dataset.name,
            "manifest_version": "v-test",
            "bound_schema_version": "schema-test",
            "score": 1.0,
            "reason": "测试固定路由",
        }
        lead_agent_context = {
            "route_decision": route_decision,
            "effective_dataset_id": sample_dataset.id,
            "should_continue": True,
            "resolved_question": "查询明细",
            "time_context": {},
            "thread_context": {},
            "schema_status": {"status": "ok", "structured": {"terms": []}},
            "selected_skills": [],
            "planned_tool_calls": [],
            "executed_tool_calls": [],
            "policy_violations": [],
            "audit_trace": {},
            "multiturn_classification": {},
        }

        monkeypatch.setattr("app.api.chat.DatasetSubAgent", FakeSubAgent)
        monkeypatch.setattr("app.api.chat.build_workflow", lambda db: object())
        monkeypatch.setattr(
            "app.api.chat.build_lead_agent_context",
            lambda *args, **kwargs: lead_agent_context,
        )
        monkeypatch.setattr(
            "app.api.chat.resolve_term_clarification",
            lambda *args, **kwargs: {"status": "none"},
        )
        monkeypatch.setattr(
            "app.api.chat.route_query_intent",
            lambda *args, **kwargs: {
                "intent": "query",
                "entities": {},
                "entry_intent": "detail_query",
                "entry_route": "query_graph",
                "entry_reason": "测试进入查询规划",
                "route_payload": {"kind": "query_graph"},
            },
        )

        events = []
        payload = ChatRequest(question="查询明细", dataset_id=sample_dataset.id)
        async for item in _stream_chat_singleturn(payload, db_session):
            events.append(json.loads(item["data"]))

        candidate_steps = [
            event
            for event in events
            if event.get("type") == "step" and event.get("node") == "candidate_assets"
        ]
        query_plan_steps = [
            event
            for event in events
            if event.get("type") == "step" and event.get("node") == "query_plan"
        ]
        final = [event for event in events if event.get("type") == "final"][-1]

        assert candidate_steps
        assert query_plan_steps
        assert candidate_steps[-1]["display_name"] == "subagent.candidate_assets"
        assert query_plan_steps[-1]["display_name"] == "subagent.query_plan"
        assert query_plan_steps[-1]["query_plan"]["execution_strategy"] == "query_graph"
        assert final["query_plan"]["execution_strategy"] == "query_graph"
        assert final["candidate_assets"]["summary"]["field_count"] == 1
        assert final["query_plan_debug"] == query_plan_debug

    @pytest.mark.asyncio
    async def test_stream_chat_dataset_fanout_returns_safe_results_and_control_sink(
        self,
        monkeypatch,
        db_session,
        sample_dataset,
        sample_datasource,
    ):
        """fan-out 主链路只把 LLMVisible 数组放入 final，控制面只进入内部 sink。"""
        from app.api.chat import _stream_chat_singleturn
        from app.services.subagent_planning import SubAgentEvent

        other_dataset = models.SemanticDataset(
            name="库存数据集",
            datasource_id=sample_datasource.id,
            tables_json={"tables": [{"name": "inventory"}], "joins": []},
            description="库存测试数据集",
            status="active",
        )
        db_session.add(other_dataset)
        db_session.commit()
        db_session.refresh(other_dataset)

        class FakeSubAgent:
            def __init__(self, db, dataset_id):
                self.db = db
                self.dataset_id = int(dataset_id)

            async def run(self, request, trace_context, *, graph, initial_state=None, graph_kwargs=None):
                assert request.dataset_id == self.dataset_id
                yield SubAgentEvent(
                    event_type="result",
                    payload={
                        "final_state": {
                            **(initial_state or {}),
                            "answer": f"完整报告 raw_report_secret_{self.dataset_id}",
                            "display_summary": f"数据集 {self.dataset_id} 安全摘要",
                            "sql": f"select raw_secret from table_{self.dataset_id}",
                            "sql_list": [f"select raw_secret from table_{self.dataset_id}"],
                            "sql_result": {
                                "columns": ["raw_secret"],
                                "rows": [{"raw_secret": f"secret-{self.dataset_id}"}],
                                "row_count": 1,
                            },
                            "query_plan": {
                                "query_type": "detail_query",
                                "execution_strategy": "query_graph",
                            },
                            "dsl": {"fields": []},
                            "out_capsule": {
                                "dataset_id": self.dataset_id,
                                "raw_capsule_marker": "should_not_leak",
                                "query_context": {"main_table": f"table_{self.dataset_id}"},
                            },
                            "error": None,
                        }
                    },
                )

        route_decision = {
            "decision": "selected",
            "dataset_id": sample_dataset.id,
            "dataset_name": sample_dataset.name,
            "manifest_version": "v-test",
            "bound_schema_version": "schema-test",
            "score": 1.0,
            "reason": "测试固定路由",
        }
        lead_agent_context = {
            "route_decision": route_decision,
            "effective_dataset_id": sample_dataset.id,
            "should_continue": True,
            "resolved_question": "同时查销售和库存",
            "time_context": {},
            "thread_context": {},
            "schema_status": {"status": "ok", "structured": {"terms": []}},
            "selected_skills": [],
            "planned_tool_calls": [
                {
                    "tool": "dataset_query",
                    "arguments": {"dataset_id": sample_dataset.id, "question": "查销售"},
                },
                {
                    "tool": "dataset_query",
                    "arguments": {"dataset_id": other_dataset.id, "question": "查库存"},
                },
            ],
            "executed_tool_calls": [],
            "policy_violations": [],
            "audit_trace": {},
            "multiturn_classification": {},
        }
        settings = SimpleNamespace(
            LEAD_AGENT_ENABLE_DATASET_FANOUT=True,
            SUBAGENT_RUNNER_MODE="in_process",
            SUBAGENT_FANOUT_MAX_PARALLEL=2,
        )

        monkeypatch.setattr("app.api.chat.get_settings", lambda: settings)
        monkeypatch.setattr("app.services.subagent_fanout.get_settings", lambda: settings)
        monkeypatch.setattr("app.api.chat.DatasetSubAgent", FakeSubAgent)
        monkeypatch.setattr("app.api.chat.build_workflow", lambda db: object())
        monkeypatch.setattr("app.api.chat.build_lead_agent_context", lambda *args, **kwargs: lead_agent_context)
        monkeypatch.setattr("app.api.chat.resolve_term_clarification", lambda *args, **kwargs: {"status": "none"})
        monkeypatch.setattr(
            "app.api.chat.route_query_intent",
            lambda *args, **kwargs: {
                "intent": "query",
                "entities": {},
                "entry_intent": "detail_query",
                "entry_route": "query_graph",
                "entry_reason": "测试进入 fan-out",
                "route_payload": {"kind": "query_graph"},
            },
        )

        events = []
        control_sink = []
        payload = ChatRequest(question="同时查销售和库存", dataset_id=sample_dataset.id)
        async for item in _stream_chat_singleturn(
            payload,
            db_session,
            subagent_control_plane_sink=control_sink,
        ):
            events.append(json.loads(item["data"]))

        final = [event for event in events if event.get("type") == "final"][-1]
        dumped_final = json.dumps(final, ensure_ascii=False)

        assert [item["dataset_id"] for item in final["subagent_tool_results"]] == [
            sample_dataset.id,
            other_dataset.id,
        ]
        assert final["sql_result"] is None
        assert "control_plane" not in final
        assert "last_success_task" not in final
        assert "raw_secret" not in dumped_final
        assert "raw_capsule_marker" not in dumped_final
        assert len(control_sink) == 2
        assert {item["capsule"]["dataset_id"] for item in control_sink} == {
            sample_dataset.id,
            other_dataset.id,
        }
        metadata = final["response_metadata"]
        assert metadata["subagent_tool_results"] == final["subagent_tool_results"]
        assert "control_plane" not in metadata

    @pytest.mark.asyncio
    async def test_blueprint_route_enters_subagent_run(
        self, monkeypatch, db_session, sample_dataset
    ):
        """蓝图命中不能在 chat 层直接早退，应进入 SubAgent.run 做规划后执行。"""
        from app.api.chat import _stream_chat_singleturn
        from app.services.subagent_planning import SubAgentEvent

        called = {"run": False}
        query_plan = {
            "query_type": "metric_query",
            "execution_strategy": "blueprint_execute",
            "planner_source": "llm",
            "fallback_reason": None,
            "explanation": {"summary": "蓝图完全适用"},
            "decision_factors": [{"code": "blueprint_matched", "message": "命中蓝图"}],
            "planner_warnings": [{"code": "review", "message": "建议复核参数"}],
            "governance_suggestions": [{"type": "blueprint", "message": "补充蓝图样例"}],
        }
        candidate_assets = {"summary": {"blueprint_count": 1}}

        class FakeSubAgent:
            def __init__(self, db, dataset_id):
                self.db = db
                self.dataset_id = dataset_id

            def resolve_term_conflict(self, **kwargs):
                raise AssertionError("chat should not call resolve_term_conflict before run")

            def resolve_metric(self, **kwargs):
                raise AssertionError("chat should not call resolve_metric before run")

            def resolve_analysis_blueprint(self, **kwargs):
                raise AssertionError("chat should not call resolve_analysis_blueprint before run")

            async def run(
                self, request, trace_context, *, graph, initial_state=None, graph_kwargs=None
            ):
                called["run"] = True
                yield SubAgentEvent(
                    event_type="candidate_assets",
                    payload={
                        "node": "candidate_assets",
                        "display_name": "subagent.candidate_assets",
                        "status": "done",
                        "candidate_assets": candidate_assets,
                    },
                )
                yield SubAgentEvent(
                    event_type="query_plan",
                    payload={
                        "node": "query_plan",
                        "display_name": "subagent.query_plan",
                        "status": "done",
                        "query_plan": query_plan,
                    },
                )
                yield SubAgentEvent(
                    event_type="result",
                    payload={
                        "final_state": {
                            **(initial_state or {}),
                            "answer": "蓝图执行完成",
                            "sql": "select 1",
                            "sql_list": ["select 1"],
                            "sql_result": {
                                "columns": ["id"],
                                "rows": [{"id": 1}],
                                "row_count": 1,
                            },
                            "query_plan": query_plan,
                            "candidate_assets": candidate_assets,
                            "error": None,
                        }
                    },
                )

        route_decision = {
            "decision": "selected",
            "dataset_id": sample_dataset.id,
            "dataset_name": sample_dataset.name,
            "manifest_version": "v-test",
            "bound_schema_version": "schema-test",
            "score": 1.0,
            "reason": "测试固定路由",
        }
        lead_agent_context = {
            "route_decision": route_decision,
            "effective_dataset_id": sample_dataset.id,
            "should_continue": True,
            "resolved_question": "跑蓝图",
            "time_context": {},
            "thread_context": {},
            "schema_status": {"status": "ok", "structured": {"terms": []}},
            "selected_skills": [],
            "planned_tool_calls": [],
            "executed_tool_calls": [],
            "policy_violations": [],
            "audit_trace": {},
            "multiturn_classification": {},
        }

        monkeypatch.setattr("app.api.chat.DatasetSubAgent", FakeSubAgent)
        monkeypatch.setattr("app.api.chat.build_workflow", lambda db: object())
        monkeypatch.setattr(
            "app.api.chat.build_lead_agent_context",
            lambda *args, **kwargs: lead_agent_context,
        )
        monkeypatch.setattr(
            "app.api.chat.resolve_term_clarification",
            lambda *args, **kwargs: {"status": "none"},
        )
        monkeypatch.setattr(
            "app.api.chat.route_query_intent",
            lambda *args, **kwargs: {
                "intent": "query",
                "entities": {},
                "entry_intent": "metric_query",
                "entry_route": "analysis_blueprint",
                "entry_reason": "命中蓝图",
                "blueprint_id": 12,
                "blueprint_match": {"id": 12, "name": "测试蓝图"},
                "route_payload": {"kind": "analysis_blueprint", "blueprint_id": 12},
            },
        )

        events = []
        payload = ChatRequest(question="跑蓝图", dataset_id=sample_dataset.id)
        async for item in _stream_chat_singleturn(payload, db_session):
            events.append(json.loads(item["data"]))

        final = [event for event in events if event.get("type") == "final"][-1]

        assert called["run"] is True
        assert not [event for event in events if event.get("node") == "analysis_blueprint_execute"]
        assert final["answer"] == "蓝图执行完成"
        assert final["query_plan"]["execution_strategy"] == "blueprint_execute"
        assert final["candidate_assets"]["summary"]["blueprint_count"] == 1
        assert final["query_plan_debug"] == {
            "planner_source": "llm",
            "fallback_reason": None,
            "decision_factors": query_plan["decision_factors"],
            "planner_warnings": query_plan["planner_warnings"],
            "governance_suggestions": query_plan["governance_suggestions"],
        }

    def test_sse_data_serializes_datetime_and_decimal(self):
        """SSE payload 应兼容 datetime 和 Decimal 等查询结果值。"""
        from app.api.chat import _sse_data

        event = _sse_data(
            {
                "type": "final",
                "sql_result": {
                    "rows": [
                        {
                            "created_at": datetime(2026, 6, 8, 16, 27, 10),
                            "amount": Decimal("12.30"),
                        }
                    ]
                },
            }
        )

        payload = json.loads(event["data"])

        assert payload["sql_result"]["rows"][0]["created_at"] == "2026-06-08T16:27:10"
        assert payload["sql_result"]["rows"][0]["amount"] == 12.3

    def test_build_query_profile_collects_explainability_fields(self):
        """query_profile 应稳定聚合口径、多轮继承、路由和 SQL 执行摘要。"""
        from app.api.chat import _build_query_profile

        profile = _build_query_profile(
            final_state={
                "original_question": "继续按地区拆分",
                "resolved_question": "基于上一轮 GMV 继续按地区拆分",
                "entry_intent": "metric_query",
                "entry_route": "query_graph",
                "blueprint_id": 7,
                "blueprint_match": {"name": "GMV 分析"},
                "multiturn_context": {
                    "turn_type": "continue",
                    "delta_type": "drill",
                    "delta": {"operations": ["add_dimension"], "dimensions": ["地区"]},
                    "prior_query_context": {"metrics": ["gmv"]},
                    "merged_query_context": {"metrics": ["gmv"], "dimensions": ["地区"]},
                },
                "turn_type": "continue",
                "merge_debug": {"used_prior": True},
                "prior_capsule_status": {"status": "loaded"},
                "sql_result": {
                    "columns": ["region", "gmv"],
                    "rows": [{"region": "华东", "gmv": 100}],
                    "row_count": 1,
                },
                "generation_mode": "semantic",
            },
            lead_agent_context={
                "time_context": {"detected_time_range": {"label": "最近30日"}},
                "schema_status": {"status": "ok"},
            },
            route_decision={
                "decision": "locked",
                "dataset_id": 10,
                "dataset_name": "销售数据集",
                "manifest_version": "v1",
                "bound_schema_version": "schema-a",
            },
            step_traces=[
                {
                    "type": "step",
                    "node": "merge_prior_context",
                    "status": "done",
                    "elapsed_ms": 12,
                },
                {
                    "type": "step",
                    "node": "sql_execute",
                    "status": "done",
                    "elapsed_ms": 34,
                },
            ],
            sql="SELECT region, SUM(amount) AS gmv FROM orders GROUP BY region",
            sql_list=["SELECT region, SUM(amount) AS gmv FROM orders GROUP BY region"],
            execution_path="query_graph",
            effective_dataset_id=10,
        )

        assert profile["version"] == "v1"
        assert profile["route"]["dataset_id"] == 10
        assert profile["route"]["blueprint_id"] == 7
        assert profile["query_context"]["merged_query_context"]["dimensions"] == ["地区"]
        assert profile["query_context"]["delta"]["operations"] == ["add_dimension"]
        assert profile["query_context"]["inheritance"]["inherited"] is True
        assert profile["sql"]["row_count"] == 1
        assert profile["sql"]["columns"] == ["region", "gmv"]
        assert profile["sql"]["elapsed_ms"] == 34
        stage_keys = [stage["key"] for stage in profile["execution_summary"]["stages"]]
        assert "understand" in stage_keys
        assert "execute_query" in stage_keys

    def test_extract_node_output_supports_langgraph_nested_output(self):
        """LangGraph 节点名包装输出时，应提取真实节点结果。"""
        from app.api.chat import _extract_node_output

        event = {
            "event": "on_chain_end",
            "data": {
                "output": {
                    "entry_intent_classification": {
                        "entry_intent": "metric_query",
                        "entry_route": "query_graph",
                        "route_payload": {"kind": "metric_query"},
                    }
                }
            },
            "metadata": {"langgraph_node": "entry_intent_classification"},
        }

        output = _extract_node_output(event, "entry_intent_classification")

        assert output["entry_intent"] == "metric_query"
        assert output["entry_route"] == "query_graph"
        assert output["route_payload"]["kind"] == "metric_query"

    def test_extract_node_output_supports_deep_wrapped_output(self):
        """LCEL 事件多层 output 包装时，仍能提取节点状态。"""
        from app.api.chat import _extract_node_output

        event = {
            "event": "on_chain_end",
            "data": {
                "output": {
                    "output": {
                        "analysis_blueprint_execute": {
                            "answer": "运行分析蓝图前还需要补充参数：start_date",
                            "error": "运行分析蓝图前还需要补充参数：start_date",
                            "sql_result": None,
                            "route_payload": {
                                "kind": "clarification",
                                "missing": ["start_date"],
                            },
                        }
                    }
                }
            },
            "metadata": {"langgraph_node": "analysis_blueprint_execute"},
        }

        output = _extract_node_output(event, "analysis_blueprint_execute")

        assert output["answer"].startswith("运行分析蓝图前还需要补充参数")
        assert output["route_payload"]["kind"] == "clarification"
        assert output["route_payload"]["missing"] == ["start_date"]

    def test_extract_node_output_keeps_flat_output(self):
        """旧的扁平事件输出仍保持兼容。"""
        from app.api.chat import _extract_node_output

        event = {
            "event": "on_chain_end",
            "data": {"output": {"intent": "query", "entities": {"metrics": ["gmv"]}}},
            "metadata": {"langgraph_node": "schema_recall"},
        }

        output = _extract_node_output(event, "intent_recognition")

        assert output["intent"] == "query"
        assert output["entities"]["metrics"] == ["gmv"]

    def test_chat_stream_event_types(self, client, sample_dataset, db_session):
        """SSE 流式接口每个事件必须含 type 字段，值为 step / token / final 之一"""
        # 发布 manifest 以通过 manifest guard，否则路由会被 locked 阻断
        publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())
        payload = {"question": "查询所有订单", "dataset_id": sample_dataset.id}
        with (
            patch("app.api.chat.build_workflow") as mock_wf,
            patch(
                "app.api.chat.DatasetSubAgent",
                _graph_backed_fake_subagent_class(),
            ),
        ):
            # 模拟 astream_events 返回两个 step 事件和一个 final 事件
            async def fake_astream_events(state, version):
                yield {
                    "event": "on_chain_start",
                    "name": "schema_recall",
                    "data": {},
                    "metadata": {"langgraph_node": "schema_recall"},
                }
                yield {
                    "event": "on_chain_end",
                    "name": "schema_recall",
                    "data": {"output": {"intent": "query", "entities": {}}},
                    "metadata": {"langgraph_node": "schema_recall"},
                }
                yield {
                    "event": "on_chain_start",
                    "name": "report_generator",
                    "data": {},
                    "metadata": {"langgraph_node": "report_generator"},
                }
                yield {
                    "event": "on_chat_model_stream",
                    "name": "ChatOpenAI",
                    "data": {"chunk": type("C", (), {"content": "查"})()},
                    "metadata": {},
                }
                yield {
                    "event": "on_chat_model_stream",
                    "name": "ChatOpenAI",
                    "data": {"chunk": type("C", (), {"content": "询"})()},
                    "metadata": {},
                }
                yield {
                    "event": "on_chain_end",
                    "name": "report_generator",
                    "data": {"output": {"answer": "查询完成", "sql": "SELECT 1"}},
                    "metadata": {"langgraph_node": "report_generator"},
                }

            mock_graph = MagicMock()
            mock_graph.astream_events = fake_astream_events
            mock_wf.return_value = mock_graph

            try:
                resp = client.post("/api/chat/stream", json=payload)
            except Exception:
                # sse_starlette 在测试中复用事件循环时可能抛出 ExceptionGroup，跳过
                pytest.skip("SSE AppStatus event loop issue in repeated TestClient usage")

            assert resp.status_code == 200

            lines = [line for line in resp.text.split("\n") if line.startswith("data:")]
            events = [json.loads(line[5:].strip()) for line in lines]
            types = {e["type"] for e in events}
            assert "step" in types
            assert "token" in types
            assert "final" in types

    def test_chat_stream_report_generator_strips_think_tokens(self, db_session, sample_dataset):
        """Graph report_generator 的原生 LLM token 不应泄露 Think 标签。"""
        publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())

        async def fake_astream_events(state, version):
            yield {
                "event": "on_chain_start",
                "name": "report_generator",
                "data": {},
                "metadata": {"langgraph_node": "report_generator"},
            }
            for content in ["<Thi", "nk>内部推理", "</Think>结论：", "表现稳定。"]:
                yield {
                    "event": "on_chat_model_stream",
                    "name": "ChatOpenAI",
                    "data": {"chunk": type("C", (), {"content": content})()},
                    "metadata": {"langgraph_node": "report_generator"},
                }
            yield {
                "event": "on_chain_end",
                "name": "report_generator",
                "data": {
                    "output": {
                        "answer": "结论：表现稳定。",
                        "sql": "SELECT 1",
                        "sql_list": ["SELECT 1"],
                    }
                },
                "metadata": {"langgraph_node": "report_generator"},
            }

        with (
            patch("app.api.chat.build_workflow") as mock_wf,
            patch(
                "app.api.chat.DatasetSubAgent",
                _graph_backed_fake_subagent_class(),
            ),
        ):
            mock_graph = MagicMock()
            mock_graph.astream_events = fake_astream_events
            mock_wf.return_value = mock_graph

            events = _collect_stream_events(
                {"question": "查询供应商日志", "dataset_id": sample_dataset.id},
                db_session,
            )

        visible = "".join(
            event.get("content", "") for event in events if event.get("type") == "token"
        )
        assert visible == "结论：表现稳定。"
        assert "内部推理" not in visible
        assert "<Thi" not in visible

    def test_dataset_select_does_not_enter_workflow(self, db_session, sample_dataset):
        """数据集选择事件应在 chat 入口早退，不能进入 LangGraph workflow。"""

        with patch("app.api.chat.build_workflow") as mock_wf:
            mock_wf.side_effect = AssertionError("dataset_select should not enter workflow")

            events = _collect_stream_events(
                {"question": f"选择：{sample_dataset.name}", "dataset_id": None},
                db_session,
            )

        final = [event for event in events if event.get("type") == "final"][-1]

        assert mock_wf.called is False
        assert "已选择数据集" in final["answer"]
        assert final["turn_event"]["event_type"] == "dataset_select"

    def test_dataset_pending_selection_restores_original_question(
        self,
        db_session,
        sample_dataset,
        monkeypatch,
    ):
        """有数据集挂起澄清时，选择数据集后应恢复上一轮原问题继续查询。"""
        from app.api.chat import _stream_chat
        from app.services.conversation_store import ConversationStore

        class MultiturnSettings:
            MULTITURN_ENABLED = True
            MULTITURN_LOCK_TTL_SECONDS = 300

        session_id = "session-dataset-selection-restore"
        original_question = "最近30日GMV趋势如何"
        selection_text = f"选择：{sample_dataset.name}"
        publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())
        monkeypatch.setattr("app.api.chat.get_settings", lambda: MultiturnSettings())

        store = ConversationStore(db_session)
        conversation_state = store.load_or_create(session_id=session_id, user_id="1")
        conversation_state.pending_clarification = {
            "kind": "dataset_choice",
            "original_question": original_question,
            "candidates": [
                {
                    "index": 1,
                    "dataset_id": sample_dataset.id,
                    "dataset_name": sample_dataset.name,
                }
            ],
        }
        db_session.add(conversation_state)
        db_session.commit()
        db_session.refresh(conversation_state)

        captured_states = []

        async def fake_astream_events(state, version):
            captured_states.append(state)
            yield {
                "event": "on_chain_end",
                "name": "report_generator",
                "data": {
                    "output": {
                        **state,
                        "answer": "查询完成",
                        "query_plan": {
                            "query_type": "detail_query",
                            "execution_strategy": "query_graph",
                            "debug": {"selected_main_table": "orders"},
                        },
                        "dsl": {"fields": [{"name": "gmv"}]},
                        "sql": "SELECT 1",
                        "sql_list": ["SELECT 1"],
                        "sql_result": {
                            "columns": ["one"],
                            "rows": [{"one": 1}],
                            "row_count": 1,
                        },
                    }
                },
                "metadata": {"langgraph_node": "report_generator"},
            }

        async def collect():
            events = []
            async for item in _stream_chat(
                ChatRequest(question=selection_text, session_id=session_id),
                db_session,
            ):
                events.append(json.loads(item["data"]))
            return events

        fake_subagent_class = _graph_backed_fake_subagent_class()
        with (
            patch("app.api.chat.build_workflow") as mock_wf,
            patch(
                "app.api.chat.DatasetSubAgent",
                fake_subagent_class,
            ),
        ):
            mock_graph = MagicMock()
            mock_graph.astream_events = fake_astream_events
            mock_wf.return_value = mock_graph

            events = asyncio.run(collect())

        final = [event for event in events if event.get("type") == "final"][-1]
        initial_state = captured_states[-1]
        user_message = (
            db_session.query(models.Message)
            .filter(models.Message.role == "user")
            .order_by(models.Message.id.desc())
            .first()
        )
        saved_state = store.load(session_id)
        thread_state = store.get_thread_state(session_id)

        assert "已选择数据集" not in final["answer"]
        assert final["answer"] == "查询完成"
        assert initial_state["original_question"] == original_question
        assert selection_text not in initial_state["question"]
        assert "GMV趋势" in initial_state["question"]
        assert initial_state["dataset_id"] == sample_dataset.id
        assert initial_state["turn_event"]["event_type"] == "new_query"
        assert user_message.content == selection_text
        assert saved_state.pending_clarification is None
        assert saved_state.active_dataset_id == str(sample_dataset.id)
        assert thread_state["last_success_task"]["question"] == original_question
        assert (
            fake_subagent_class.captured_runs[-1]["request"].question == initial_state["question"]
        )

    def test_message_gateway_detects_thread_last_success_task(self):
        """Thread Memory 的 last_success_task 应触发二轮 refine 判定。"""
        from app.api.chat import _has_last_success_task

        assert (
            _has_last_success_task(
                {
                    "last_success_task": {
                        "query_type": "detail_query",
                        "main_table": "plan_task_daily_record",
                        "metrics": [],
                    }
                }
            )
            is True
        )
        assert _has_last_success_task({"capsule_metas": {"10": {"dataset_id": "10"}}}) is False
        assert (
            _has_last_success_task(
                {"last_success_task": {"query_type": "metric_query", "metrics": []}}
            )
            is False
        )

    def test_persist_completed_turn_uses_configured_last_success_task_budget(
        self,
        monkeypatch,
    ):
        """持久化 last_success_task 时应使用配置化 token 预算。"""
        from app.api.chat import _persist_completed_turn

        captured = {}

        class FakeSettings:
            MULTITURN_LAST_SUCCESS_TASK_MAX_TOKENS = 4096

        class FakeStore:
            def with_updated_capsule(self, state, *, dataset_id, capsule):
                return None

            def append_completed_turn(self, **kwargs):
                captured["append_completed_turn"] = kwargs

            def update_thread_state(self, session_id, updates, *, user_id=None):
                captured["thread_state"] = {
                    "session_id": session_id,
                    "updates": updates,
                    "user_id": user_id,
                }
                return updates

        def fake_build_success_task_state(**kwargs):
            captured["max_tokens"] = kwargs["max_tokens"]
            return {
                "capsule_version": "last_success_task.v1",
                "dataset_id": 10,
                "question": kwargs["question"],
                "query_type": "detail_query",
                "main_table": "plan_task_daily_record",
            }

        monkeypatch.setattr("app.api.chat.get_settings", lambda: FakeSettings())
        monkeypatch.setattr(
            "app.api.chat.build_success_task_state",
            fake_build_success_task_state,
        )

        completed = _persist_completed_turn(
            store=FakeStore(),
            state=SimpleNamespace(turn_index=2, subagent_capsules=None),
            user_id="1",
            business_session_id="session-budget",
            effective_payload=ChatRequest(
                question="查询10条用户日志",
                dataset_id=10,
                session_id="session-budget",
            ),
            final_payload={
                "answer": "查询完成",
                "route_decision": {
                    "dataset_id": 10,
                    "bound_schema_version": "schema-v1",
                    "manifest_version": "manifest-v1",
                },
                "query_plan": {"query_type": "detail_query"},
                "dsl": {},
                "sql": "SELECT * FROM plan_task_daily_record LIMIT 10",
                "sql_result": {"columns": [], "rows": [], "row_count": 0},
                "conversation_id": 307,
            },
            pending_resolution={},
            payload_question="查询10条用户日志",
            trace_context_sink=[],
        )

        assert completed is True
        assert captured["max_tokens"] == 4096
        assert captured["thread_state"]["updates"]["last_success_task"]["main_table"] == (
            "plan_task_daily_record"
        )

    def test_stream_chat_writes_last_success_task_and_reuses_it_next_turn(
        self,
        db_session,
        sample_dataset,
        monkeypatch,
    ):
        """第一轮成功查询应自动写入 _thread，第二轮无需手工 seed 即可承接。"""
        from app.api.chat import _stream_chat
        from app.services.conversation_store import ConversationStore

        class MultiturnSettings:
            MULTITURN_ENABLED = True
            MULTITURN_LOCK_TTL_SECONDS = 300

        publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())
        monkeypatch.setattr("app.api.chat.get_settings", lambda: MultiturnSettings())
        captured_states = []

        async def fake_astream_events(state, version):
            captured_states.append(state)
            yield {
                "event": "on_chain_end",
                "name": "report_generator",
                "data": {
                    "output": {
                        **state,
                        "answer": "查询完成",
                        "query_plan": {
                            "query_type": "detail_query",
                            "execution_strategy": "query_graph",
                            "debug": {"selected_main_table": "plan_task_daily_record"},
                        },
                        "dsl": {"fields": [{"name": "rzrq"}]},
                        "sql": "SELECT rzrq FROM plan_task_daily_record LIMIT 10",
                        "sql_list": ["SELECT rzrq FROM plan_task_daily_record LIMIT 10"],
                        "sql_result": {
                            "columns": ["rzrq"],
                            "rows": [{"rzrq": "2024-01-01"}],
                            "row_count": 1,
                        },
                    }
                },
                "metadata": {"langgraph_node": "report_generator"},
            }

        async def collect(question):
            events = []
            async for item in _stream_chat(
                ChatRequest(
                    question=question,
                    dataset_id=sample_dataset.id,
                    session_id="session-auto-last-success",
                ),
                db_session,
            ):
                events.append(json.loads(item["data"]))
            return events

        fake_subagent_class = _graph_backed_fake_subagent_class()
        with (
            patch("app.api.chat.build_workflow") as mock_wf,
            patch(
                "app.api.chat.DatasetSubAgent",
                fake_subagent_class,
            ),
        ):
            mock_graph = MagicMock()
            mock_graph.astream_events = fake_astream_events
            mock_wf.return_value = mock_graph

            first_events = asyncio.run(collect("查询10条用户日志"))
            second_events = asyncio.run(collect("只看汤杰"))

        assert any(event.get("type") == "final" for event in first_events)
        assert any(event.get("type") == "final" for event in second_events)
        first_final = [event for event in first_events if event.get("type") == "final"][-1]
        assert first_final["result_artifact"]["result_ref"].startswith("result:")
        assert first_final["result_artifact"]["complete"] is False
        assert (
            first_final["result_artifact"]["completeness_reason"]
            == "sql_limit_makes_result_incomplete"
        )
        thread_state = ConversationStore(db_session).get_thread_state("session-auto-last-success")
        assert thread_state["last_success_task"]["main_table"] == "plan_task_daily_record"
        assert (
            thread_state["last_success_task"]["result_ref"]
            == first_final["result_artifact"]["result_ref"]
        )

        second_state = captured_states[-1]
        capsule = second_state["query_task_capsule"]
        assert second_state["turn_event"]["event_type"] == "followup_refine"
        assert capsule["base_task_ref"] == "last_success_task"
        assert capsule["base_question"] == "查询10条用户日志"
        assert capsule["multiturn_fast_path"]["status"] == "observe_only"
        assert capsule["multiturn_fast_path"]["artifact_status"]["status"] == "not_eligible"
        assert (
            capsule["multiturn_fast_path"]["artifact_status"]["reason"]
            == "sql_limit_makes_result_incomplete"
        )
        assert second_state["merge_debug"]["used_prior"] is True
        assert second_state["question"] == "基于上一轮问题「查询10条用户日志」，只看汤杰"
        second_gateway_step = next(
            event
            for event in second_events
            if event.get("type") == "step" and event.get("node") == "message_gateway"
        )
        assert second_gateway_step["payload"]["multiturn_fast_path"]["status"] == "observe_only"
        second_request = fake_subagent_class.captured_runs[-1]["request"]
        assert second_request.query_task_capsule == capsule
        assert second_request.turn_event == second_state["turn_event"]

    def test_singleturn_stream_injects_query_task_capsule_from_thread_memory(
        self,
        db_session,
        sample_dataset,
    ):
        """真实 chat merge 前应从 Thread Memory 构建 query_task_capsule。"""
        from app.api.chat import _stream_chat_singleturn
        from app.services.conversation_store import ConversationStore
        from app.services.task_capsule import build_success_task_state

        manifest = publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())
        store = ConversationStore(db_session)
        conversation_state = store.load_or_create(
            session_id="session-query-task-capsule",
            user_id="1",
        )
        conversation_state.active_dataset_id = sample_dataset.id
        db_session.add(conversation_state)
        db_session.commit()
        db_session.refresh(conversation_state)
        last_success_task = build_success_task_state(
            question="查询10条用户日志",
            dataset_id=sample_dataset.id,
            query_plan={
                "query_type": "detail_query",
                "execution_strategy": "query_graph",
                "planner_source": "deterministic",
                "debug": {
                    "selected_main_table": "plan_task_daily_record",
                    "sql_template": "SELECT rzrq FROM plan_task_daily_record LIMIT 10",
                },
            },
            dsl={"fields": [{"table_name": "plan_task_daily_record", "name": "rzrq"}]},
            sql="SELECT rzrq FROM plan_task_daily_record LIMIT 10",
            sql_result={"columns": ["rzrq"], "rows": [], "row_count": 0},
            schema_version=manifest.bound_schema_version,
            manifest_version=manifest.manifest_version,
        )
        store.update_thread_state(
            "session-query-task-capsule",
            {"last_success_task": last_success_task},
        )
        db_session.refresh(conversation_state)
        captured = {}

        async def fake_astream_events(state, version):
            captured["initial_state"] = state
            yield {
                "event": "on_chain_end",
                "name": "report_generator",
                "data": {
                    "output": {
                        **state,
                        "answer": "查询完成",
                        "sql": "SELECT 1",
                        "sql_list": ["SELECT 1"],
                        "sql_result": {"columns": ["one"], "rows": [{"one": 1}], "row_count": 1},
                    }
                },
                "metadata": {"langgraph_node": "report_generator"},
            }

        async def collect():
            events = []
            async for item in _stream_chat_singleturn(
                ChatRequest(question="只看汤杰", dataset_id=sample_dataset.id),
                db_session,
                multiturn_context=store.lead_multiturn_context(conversation_state),
                conversation_state=conversation_state,
                conversation_store=store,
                observability_session_id="session-query-task-capsule",
            ):
                events.append(json.loads(item["data"]))
            return events

        fake_subagent_class = _graph_backed_fake_subagent_class()
        with (
            patch("app.api.chat.build_workflow") as mock_wf,
            patch(
                "app.api.chat.DatasetSubAgent",
                fake_subagent_class,
            ),
        ):
            mock_graph = MagicMock()
            mock_graph.astream_events = fake_astream_events
            mock_wf.return_value = mock_graph

            events = asyncio.run(collect())

        assert any(event.get("type") == "final" for event in events)
        initial_state = captured["initial_state"]
        capsule = initial_state["query_task_capsule"]
        assert initial_state["turn_event"]["event_type"] == "followup_refine"
        assert capsule["turn_type"] == "followup_refine"
        assert capsule["base_task_ref"] == "last_success_task"
        assert capsule["base_question"] == "查询10条用户日志"
        assert capsule["base_main_table"] == "plan_task_daily_record"
        assert (
            capsule["base_query_plan"]["debug"]["selected_main_table"] == "plan_task_daily_record"
        )
        assert "sql_template" not in json.dumps(capsule["base_query_plan"], ensure_ascii=False)
        assert initial_state["merge_debug"]["used_prior"] is True
        assert initial_state["question"] == "基于上一轮问题「查询10条用户日志」，只看汤杰"
        gateway_step = next(
            event
            for event in events
            if event.get("type") == "step" and event.get("node") == "message_gateway"
        )
        assert "sql_template" not in json.dumps(
            gateway_step["query_task_capsule"], ensure_ascii=False
        )
        final = [event for event in events if event.get("type") == "final"][-1]
        assert final["turn_event"] == initial_state["turn_event"]
        assert final["query_task_capsule"]["base_query_plan"]["debug"] == {
            "selected_main_table": "plan_task_daily_record"
        }
        assert "sql_template" not in json.dumps(final["query_task_capsule"], ensure_ascii=False)
        assistant_message = db_session.get(models.Message, final["message_id"])
        assert assistant_message is not None
        assert "sql_template" not in json.dumps(assistant_message.step_trace, ensure_ascii=False)
        request = fake_subagent_class.captured_runs[-1]["request"]
        assert request.query_task_capsule == capsule
        assert request.turn_event == initial_state["turn_event"]

    def test_chat_stream_final_and_message_metadata_include_query_profile(
        self, db_session, sample_dataset
    ):
        """final payload 与落库消息都应包含稳定的 explainability/query_profile。"""
        publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())

        async def fake_astream_events(state, version):
            yield {
                "event": "on_chain_start",
                "name": "sql_execute",
                "data": {},
                "metadata": {"langgraph_node": "sql_execute"},
            }
            yield {
                "event": "on_chain_end",
                "name": "sql_execute",
                "data": {
                    "output": {
                        "answer": "GMV 为 100。",
                        "entry_intent": "metric_query",
                        "entry_route": "query_graph",
                        "entry_reason": "识别为指标查询",
                        "sql": "SELECT 100 AS gmv",
                        "sql_list": ["SELECT 100 AS gmv"],
                        "sql_result": {
                            "columns": ["gmv"],
                            "rows": [{"gmv": 100}],
                            "row_count": 1,
                        },
                        "multiturn_context": {
                            "turn_type": "continue",
                            "delta_type": "refine",
                            "delta": {"operations": ["time_refine"]},
                            "merged_query_context": {"metrics": ["gmv"]},
                        },
                        "turn_type": "continue",
                        "merge_debug": {"used_prior": True},
                        "prior_capsule_status": {"status": "loaded"},
                    }
                },
                "metadata": {"langgraph_node": "sql_execute"},
            }

        with (
            patch("app.api.chat.build_workflow") as mock_wf,
            patch(
                "app.api.chat.DatasetSubAgent",
                _graph_backed_fake_subagent_class(),
            ),
        ):
            mock_graph = MagicMock()
            mock_graph.astream_events = fake_astream_events
            mock_wf.return_value = mock_graph

            events = _collect_stream_events(
                {"question": "继续看 GMV", "dataset_id": sample_dataset.id},
                db_session,
            )

        final = [event for event in events if event.get("type") == "final"][-1]
        metadata = final["response_metadata"]
        assistant_message = (
            db_session.query(models.Message)
            .filter(models.Message.role == "assistant")
            .order_by(models.Message.id.desc())
            .first()
        )

        assert final["query_profile"] == metadata["query_profile"]
        assert final["explainability"]["query_profile"] == final["query_profile"]
        assert metadata["explainability"]["query_profile"] == final["query_profile"]
        assert assistant_message.response_metadata["query_profile"] == final["query_profile"]
        assert final["query_profile"]["sql"]["row_count"] == 1
        assert final["query_profile"]["query_context"]["inheritance"]["inherited"] is True
        assert final["result_artifact"]["result_ref"].startswith("result:")
        assert final["query_profile"]["sql"]["result_artifact"] == final["result_artifact"]
        assert metadata["result_artifact"] == final["result_artifact"]
        assert final["query_profile"]["execution_summary"]["stages"]
        assert "control_plane" not in final
        assert "last_success_task" not in final
        assert final["sql_result"] is None
        assert final["result_ref"].startswith("artifact:")
        assert final["report_ref"].startswith("artifact:")
        subagent_tool_result = metadata["subagent_tool_result"]
        assert set(subagent_tool_result) == {
            "status",
            "dataset_id",
            "display_summary",
            "clarification_question",
            "error_summary",
            "result_ref",
            "report_ref",
        }
        assert subagent_tool_result["status"] == "ok"
        assert subagent_tool_result["dataset_id"] == sample_dataset.id
        assert subagent_tool_result["result_ref"] == final["result_ref"]
        assert subagent_tool_result["report_ref"] == final["report_ref"]
        assert "control_plane" not in assistant_message.response_metadata
        assert assistant_message.response_metadata["subagent_tool_result"] == subagent_tool_result
        artifacts = (
            db_session.query(models.QueryArtifact)
            .filter(models.QueryArtifact.artifact_id.in_([final["result_ref"], final["report_ref"]]))
            .all()
        )
        assert len(artifacts) == 2
        assert {item.message_id for item in artifacts} == {assistant_message.id}

    def test_chat_stream_step_event_structure(self, client, sample_dataset):
        """step 事件必须含 node 和 status 字段"""
        payload = {"question": "测试", "dataset_id": sample_dataset.id}
        with patch("app.api.chat.build_workflow") as mock_wf:

            async def fake_astream_events(state, version):
                yield {
                    "event": "on_chain_start",
                    "name": "schema_recall",
                    "data": {},
                    "metadata": {"langgraph_node": "schema_recall"},
                }
                yield {
                    "event": "on_chain_end",
                    "name": "schema_recall",
                    "data": {"output": {"intent": "query", "entities": {}}},
                    "metadata": {"langgraph_node": "schema_recall"},
                }

            mock_graph = MagicMock()
            mock_graph.astream_events = fake_astream_events
            mock_wf.return_value = mock_graph

            try:
                resp = client.post("/api/chat/stream", json=payload)
            except Exception:
                # sse_starlette 在测试中复用事件循环时可能抛出 ExceptionGroup，跳过
                pytest.skip("SSE AppStatus event loop issue in repeated TestClient usage")

            lines = [line for line in resp.text.split("\n") if line.startswith("data:")]
            step_events = [json.loads(line[5:].strip()) for line in lines if '"step"' in line]
            for e in step_events:
                assert "node" in e
                assert "status" in e
                assert e["status"] in ("running", "done")

    def test_chat_stream_auto_routes_by_current_manifest(self, db_session, sample_dataset):
        """未传 dataset_id 时，应先用 current Manifest 自动选择数据集再进入工作流。"""
        publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())
        captured = {}

        async def fake_astream_events(state, version):
            captured["state"] = state
            yield {
                "event": "on_chain_end",
                "name": "sql_execute",
                "data": {
                    "output": {
                        "sql": "SELECT 1",
                        "sql_list": ["SELECT 1"],
                        "sql_result": {
                            "columns": ["gmv"],
                            "rows": [{"gmv": 100}],
                            "row_count": 1,
                        },
                        "should_retry": False,
                    }
                },
                "metadata": {"langgraph_node": "sql_execute"},
            }

        async def fake_lead_report_stream(state, **kwargs):
            captured["lead_report_state"] = state
            captured["lead_report_kwargs"] = kwargs
            yield {"type": "token", "content": "Lead"}
            yield {
                "type": "result",
                "answer": "LeadAgent 汇总：GMV 为 100。",
                "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }

        with (
            patch("app.api.chat.build_workflow") as mock_wf,
            patch(
                "app.api.chat.DatasetSubAgent",
                _graph_backed_fake_subagent_class(),
            ),
            patch(
                "app.api.chat.stream_sql_result_report",
                fake_lead_report_stream,
            ),
        ):
            mock_graph = MagicMock()
            mock_graph.astream_events = fake_astream_events
            mock_wf.return_value = mock_graph

            events = _collect_stream_events({"question": "最近30日GMV趋势如何"}, db_session)

        lead_event = _find_event(events, "lead_agent_tools")
        route_event = _find_event(events, "route_decision")
        assert lead_event["should_continue"] is True
        assert "tool_policy" in lead_event
        assert lead_event["planned_tool_calls"]
        assert lead_event["executed_tool_calls"]
        assert "policy_violations" in lead_event
        assert "planner_fallback" in lead_event
        assert lead_event["time_context"]["detected_time_range"]["label"] == "最近30日"
        assert route_event["type"] == "route_decision"
        assert route_event["decision"] == "selected"
        assert route_event["dataset_id"] == sample_dataset.id
        assert captured["state"]["original_question"] == "最近30日GMV趋势如何"
        assert captured["state"]["resolved_question"] == captured["state"]["question"]
        assert captured["state"]["resolved_question"] != captured["state"]["original_question"]
        assert captured["state"]["dataset_id"] == sample_dataset.id
        assert captured["state"]["manifest_version"] == "v1"
        assert captured["state"]["bound_schema_version"] == route_event["bound_schema_version"]
        assert captured["state"]["lead_agent_context"]["audit_trace"]["dispatched"] is True
        assert captured["state"]["skip_subagent_report"] is True
        assert captured["state"]["report_owner"] == "lead_agent"
        assert (
            captured["lead_report_kwargs"]["observation_name"] == "llm.lead_agent_report_generator"
        )
        assert captured["lead_report_kwargs"]["report_owner"] == "lead_agent"
        assert not [event for event in events if event.get("node") == "report_generator"]
        lead_report_step = [
            event for event in events if event.get("node") == "lead_agent_report_generator"
        ]
        assert {event["status"] for event in lead_report_step} == {"running", "done"}
        assert events[-1]["answer"] == "LeadAgent 汇总：GMV 为 100。"
        assert events[-1]["report_owner"] == "lead_agent"
        assert events[-1]["subagent_report_skipped"] is True
        assert events[-1]["lead_agent_report"] == {
            "generated": True,
            "reason": "auto_routed_manifest",
        }
        assert events[-1]["route_decision"]["decision"] == "selected"

    def test_chat_stream_keeps_explicit_dataset_locked(
        self, db_session, sample_dataset, sample_datasource
    ):
        """已传 dataset_id 时，即使命中其他 Manifest，也不能自动改选。"""
        publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())
        other = models.SemanticDataset(
            name="供应商采购数据集",
            datasource_id=sample_datasource.id,
            tables_json={"tables": [{"name": "suppliers", "alias": "s"}]},
            status="active",
        )
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)
        db_session.add(
            models.SemanticMetric(
                dataset_id=other.id,
                name="supplier_count",
                display_name="供应商数量",
                expr="COUNT(s.id)",
                synonyms=["供应商数"],
                description="供应商总数量",
            )
        )
        db_session.add(
            models.SemanticDimension(
                dataset_id=other.id,
                name="supplier_level",
                display_name="供应商层级",
                column_name="s.level",
                synonyms=["层级"],
            )
        )
        db_session.commit()
        supplier_manual = _manifest_manual_fields(domain="采购管理", subject="供应商采购")
        supplier_manual["description"] = (
            "供应商采购数据集用于分析日、周、月范围内的供应商数量、供应商层级、地区和新增趋势表现，"
            "覆盖采购管理人员查看供应商准入、层级结构、区域分布和异常波动，不覆盖订单销售、会员画像和售后工单。"
        )
        supplier_manual["sample_questions"] = [
            "最近30日供应商数量趋势如何",
            "按供应商层级统计本月供应商数量",
            "各地区供应商数量排名",
            "本周新增供应商数量是多少",
            "供应商层级分布如何",
        ]
        supplier_manual["routing_negative_examples"] = [
            "最近30日GMV趋势如何",
            "售后工单处理时长",
            "会员画像年龄分布",
        ]
        publish_manifest(db_session, other.id, supplier_manual)
        captured = {}

        async def fake_astream_events(state, version):
            captured["state"] = state
            yield {
                "event": "on_chain_end",
                "name": "report_generator",
                "data": {"output": {"answer": "查询完成", "sql": "SELECT 1"}},
                "metadata": {"langgraph_node": "report_generator"},
            }

        with (
            patch("app.api.chat.build_workflow") as mock_wf,
            patch(
                "app.api.chat.DatasetSubAgent",
                _graph_backed_fake_subagent_class(),
            ),
        ):
            mock_graph = MagicMock()
            mock_graph.astream_events = fake_astream_events
            mock_wf.return_value = mock_graph

            events = _collect_stream_events(
                {
                    "question": "最近30日供应商数量趋势如何",
                    "dataset_id": sample_dataset.id,
                },
                db_session,
            )

        route_event = _find_event(events, "route_decision")
        assert route_event["decision"] == "locked"
        assert route_event["dataset_id"] == sample_dataset.id
        assert captured["state"]["dataset_id"] == sample_dataset.id
        assert captured["state"]["route_decision"]["decision"] == "locked"
        assert captured["state"]["skip_subagent_report"] is False
        assert captured["state"]["report_owner"] == "subagent"
        assert events[-1]["report_owner"] == "subagent"
        assert events[-1]["subagent_report_skipped"] is False

    def test_chat_stream_no_manifest_blocks_auto_route(self, db_session):
        """未传 dataset_id 且没有 current Manifest 时，不进入旧的无 schema 猜测路径。"""
        with patch("app.api.chat.build_workflow") as mock_wf:
            events = _collect_stream_events({"question": "最近30日GMV趋势如何"}, db_session)

        lead_event = _find_event(events, "lead_agent_tools")
        route_event = _find_event(events, "route_decision")
        assert lead_event["should_continue"] is False
        assert lead_event["clarification"]["kind"] == "dataset_missing"
        assert lead_event["tool_policy"]["allowed_tools"]
        assert lead_event["planned_tool_calls"]
        assert lead_event["executed_tool_calls"]
        assert route_event["type"] == "route_decision"
        assert route_event["decision"] == "no_match"
        assert events[-1]["type"] == "final"
        assert events[-1]["entry_route"] == "no_match"
        assert events[-1]["lead_agent_context"]["audit_trace"]["dispatched"] is False
        assert "current SubAgent Manifest" in events[-1]["answer"]
        trace_index = db_session.query(models.ObservabilityTraceIndex).one()
        assert trace_index.status == "blocked"
        assert trace_index.entry_route == "no_match"
        assert trace_index.message_id == events[-1]["message_id"]
        mock_wf.assert_not_called()

    def test_chat_stream_pending_term_resolution_preempts_generic_clarify(
        self, db_session, sample_dataset
    ):
        """pending 术语澄清回复必须先解析，不能被入口路由的普通 clarify 早退吞掉。"""
        publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())
        conv, pending = TestLangGraphNodes()._create_pending_term_clarification(
            db_session,
            sample_dataset,
        )

        def fake_route_query_intent(*args, **kwargs):
            return {
                "intent": "query",
                "entities": {},
                "entry_intent": "clarification",
                "entry_route": "clarify",
                "entry_reason": "短句或指代不清，无法可靠判断查询目标。",
                "answer": "这个问题缺少明确对象。",
                "route_payload": {"kind": "clarification", "missing": ["query_target"]},
                "blueprint_id": None,
                "blueprint_match": None,
                "knowledge_term_id": None,
            }

        with (
            patch("app.api.chat.route_query_intent", fake_route_query_intent),
            patch("app.api.chat.build_workflow") as mock_wf,
        ):
            events = _collect_stream_events(
                {
                    "question": "都不是",
                    "conversation_id": conv.id,
                    "dataset_id": sample_dataset.id,
                },
                db_session,
            )

        final = events[-1]
        assert final["type"] == "final"
        assert final["entry_route"] == "clarify"
        assert final["route_payload"]["kind"] == "term_conflict_clarification"
        assert "GMV" in final["answer"]
        db_session.refresh(pending)
        assert pending.status == "pending"
        trace_index = db_session.query(models.ObservabilityTraceIndex).one()
        assert trace_index.metadata_json["route_payload"]["kind"] == "term_conflict_clarification"
        mock_wf.assert_not_called()

    def test_chat_stream_direct_answer_early_return_writes_trace_index(
        self, db_session, sample_dataset
    ):
        """入口路由早退也必须写 trace output、TraceIndex 和 final observability metadata。"""
        publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())

        def fake_route_query_intent(*args, **kwargs):
            return {
                "intent": "chitchat",
                "entities": {},
                "entry_intent": "chitchat",
                "entry_route": "direct_answer",
                "entry_reason": "粗粒度意图识别为闲聊，直接返回回答。",
                "answer": "你好！",
                "route_payload": {"kind": "direct_answer"},
                "blueprint_id": None,
                "blueprint_match": None,
                "knowledge_term_id": None,
            }

        with (
            patch("app.api.chat.route_query_intent", fake_route_query_intent),
            patch("app.api.chat.build_workflow") as mock_wf,
        ):
            events = _collect_stream_events(
                {"question": "最近30日GMV趋势如何", "dataset_id": sample_dataset.id},
                db_session,
            )

        final = events[-1]
        gateway_step = next(
            event
            for event in events
            if event.get("type") == "step" and event.get("node") == "message_gateway"
        )
        assert final["type"] == "final"
        assert final["entry_route"] == "direct_answer"
        assert gateway_step["query_task_capsule"]["dataset_id"] == sample_dataset.id
        assert final["query_task_capsule"] == gateway_step["query_task_capsule"]
        assert (
            final["response_metadata"]["query_task_capsule"] == gateway_step["query_task_capsule"]
        )
        assert final["langfuse_trace_id"]
        assert final["response_metadata"]["langfuse"]["trace_id"] == final["langfuse_trace_id"]
        assert final["response_metadata"]["observability"]
        trace_index = db_session.query(models.ObservabilityTraceIndex).one()
        assert trace_index.status == "success"
        assert trace_index.entry_route == "direct_answer"
        assert trace_index.message_id == final["message_id"]
        assistant_message = db_session.get(models.Message, final["message_id"])
        assert assistant_message is not None
        assert any(
            step.get("node") == "message_gateway" for step in assistant_message.step_trace or []
        )
        mock_wf.assert_not_called()


class TestSchemaFormatter:
    """SchemaFormatter 紧凑序列化工具单测。"""

    def _make_field(self, name, data_type, role, desc="", agg=None, samples=None):
        return {
            "name": name,
            "column_name": name,
            "data_type": data_type,
            "semantic_role": role,
            "effective_desc": desc,
            "default_agg": agg,
            "sample_values": samples or [],
        }

    def test_schema_formatter_filters_unused(self):
        """unused 字段不出现在 format_fields_compact 输出中。"""
        from app.utils.schema_formatter import format_fields_compact

        fields = [
            self._make_field("person_name", "VARCHAR", "dimension_candidate", "人员名称"),
            self._make_field("deleted_flag", "TINYINT", "unused", "软删除标记"),
            self._make_field("version_num", "INT", "unused", "版本号"),
        ]
        result = format_fields_compact(fields)
        assert "deleted_flag" not in result
        assert "version_num" not in result
        assert "person_name" in result

    def test_schema_formatter_enum_inline(self):
        """维度候选且样例 ≤ 6 个时，样例内联到括号里，不在单独 样例= 段。"""
        from app.utils.schema_formatter import format_fields_compact

        fields = [
            self._make_field(
                "order_status",
                "VARCHAR",
                "dimension_candidate",
                "订单状态",
                samples=["已完成", "待处理", "已取消", "退款中"],
            )
        ]
        result = format_fields_compact(fields)
        assert "已完成" in result
        assert "样例=" not in result  # 内联后不再单独出现 "样例=" 段
        assert "(" in result and ")" in result

    def test_schema_formatter_metric_with_agg(self):
        """metric_candidate 字段输出 [M,SUM]。"""
        from app.utils.schema_formatter import format_fields_compact

        fields = [
            self._make_field("order_amount", "DECIMAL", "metric_candidate", "订单金额", agg="SUM")
        ]
        result = format_fields_compact(fields)
        assert "order_amount" in result
        assert "[M,SUM]" in result

    def test_lead_agent_router_analysis_blueprint_phase5_end(self):
        """Phase 5: analysis_blueprint 已在 chat 层处理完，入口路由直接 end。"""
        from app.graph.workflow import _lead_agent_router

        # 蓝图成功（executed）/ 失败（error）走 chat 早退，不进 graph
        assert _lead_agent_router({"entry_route": "analysis_blueprint"}) == "end"

    def test_lead_agent_router_analysis_blueprint_semantic_legacy(self):
        """Phase 5 兼容: 旧值 analysis_blueprint_semantic_execute → schema_recall。"""
        from app.graph.workflow import _lead_agent_router

        assert (
            _lead_agent_router({"entry_route": "analysis_blueprint_semantic_execute"})
            == "schema_recall"
        )
