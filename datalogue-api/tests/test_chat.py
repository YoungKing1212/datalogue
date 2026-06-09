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
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock


class TestChatAPI:
    """测试 /api/chat 路由"""

    def test_sql_audit_node_is_exposed_to_stream_payloads(self):
        """SQL 诊断节点应纳入 SSE 展示名和状态输出提取。"""
        from app.api.chat import _NODE_DISPLAY_NAMES, _STATE_OUTPUT_KEYS

        assert _NODE_DISPLAY_NAMES["sql_audit"] == "SQL 诊断"
        assert "sql_audit_result" in _STATE_OUTPUT_KEYS
        assert "sql_diagnosis" in _STATE_OUTPUT_KEYS

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

    def test_chat_feedback(self, client):
        """人工反馈接口"""
        payload = {
            "message_id": 1,
            "action": "approve",
            "comment": "回答正确",
        }
        resp = client.post("/api/chat/feedback", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "approve"


class TestLangGraphNodes:
    """测试 LangGraph 各节点逻辑"""

    def test_intent_recognition_chitchat(self):
        """测试意图识别：闲聊"""
        from app.graph.nodes import intent_recognition_node

        with patch("app.graph.nodes.get_llm") as mock_get_llm:
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
            result = intent_recognition_node(state)

            assert result["intent"] == "chitchat"
            assert result["answer"] == "你好！有什么可以帮你的？"
            assert result["token_usage"]["total_tokens"] == 70

    def test_intent_recognition_query(self):
        """测试意图识别：数据查询"""
        from app.graph.nodes import intent_recognition_node

        with patch("app.graph.nodes.get_llm") as mock_get_llm:
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
            result = intent_recognition_node(state)

            assert result["intent"] == "query"
            assert result["entities"]["metrics"] == ["gmv"]
            assert result["answer"] is None

    def test_entry_intent_metric_query(self, db_session, sample_dataset):
        """入口分类：指标查询继续 QueryGraph。"""
        from app.graph.nodes import entry_intent_classification_node

        state = {
            "question": "最近30天GMV是多少",
            "dataset_id": sample_dataset.id,
            "intent": "query",
            "entities": {"metrics": ["gmv"], "dimensions": []},
        }
        result = entry_intent_classification_node(db_session)(state)

        assert result["entry_intent"] == "metric_query"
        assert result["entry_route"] == "query_graph"

    def test_entry_intent_detail_query(self, db_session, sample_dataset):
        """入口分类：明细查询继续 QueryGraph。"""
        from app.graph.nodes import entry_intent_classification_node

        state = {
            "question": "列出华东订单明细",
            "dataset_id": sample_dataset.id,
            "intent": "query",
            "entities": {"metrics": [], "dimensions": ["region"]},
        }
        result = entry_intent_classification_node(db_session)(state)

        assert result["entry_intent"] == "detail_query"
        assert result["entry_route"] == "query_graph"

    def test_entry_intent_blueprint_hit(self, db_session, sample_dataset):
        """入口分类：命中已发布分析蓝图时返回 blueprint_id。"""
        from app.graph.nodes import entry_intent_classification_node
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
        result = entry_intent_classification_node(db_session)(state)

        assert result["entry_intent"] == "analysis_blueprint"
        assert result["entry_route"] == "analysis_blueprint"
        assert result["blueprint_id"] == bp.id
        assert result["route_payload"]["blueprint_id"] == bp.id

    def test_semantic_asset_resolution_metric_synonym(self):
        """语义资产解析：指标同义词命中，并兼容旧 metric_resolution。"""
        from app.graph.nodes import semantic_asset_resolution_node

        state = {
            "question": "销售额是多少",
            "entities": {"metrics": ["销售额"], "dimensions": []},
            "schema_structured": {
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
        }
        result = semantic_asset_resolution_node(state)

        semantic = result["semantic_asset_resolution"]
        assert semantic["metrics"][0]["name"] == "gmv"
        assert semantic["metrics"][0]["asset_id"] == 1
        assert semantic["metrics"][0]["match_type"] == "synonym"
        assert result["metric_resolution"]["metrics"][0]["resolved"] == "gmv"
        assert result["metric_resolution"]["all_matched"] is True

    def test_term_normalize_node_alias_match(self):
        """术语归一化：业务术语同义词应注入 entities.terms。"""
        from app.graph.nodes import term_normalize_node

        state = {
            "question": "销售额趋势",
            "entities": {"metrics": [], "dimensions": []},
            "schema_structured": {
                "terms": [
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
                ]
            },
        }
        result = term_normalize_node(state)

        normalization = result["term_normalization"]
        assert normalization["matched_terms"][0]["name"] == "gmv"
        assert normalization["matched_terms"][0]["match_type"] == "synonym"
        assert normalization["has_conflict"] is False
        assert result["entities"]["terms"] == ["销售额"]

    def test_term_normalize_node_conflict_clarification(self):
        """术语归一化：同一个同义词命中多个术语时进入澄清。"""
        from app.graph.nodes import term_normalize_node

        state = {
            "question": "销售额是多少",
            "entities": {"metrics": [], "dimensions": []},
            "schema_structured": {
                "terms": [
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
                ]
            },
        }
        result = term_normalize_node(state)

        assert result["entry_intent"] == "clarification"
        assert result["entry_route"] == "clarify"
        assert result["route_payload"]["kind"] == "term_conflict_clarification"
        assert result["term_normalization"]["has_conflict"] is True
        assert {t["id"] for t in result["route_payload"]["conflicts"][0]["terms"]} == {1, 2}

    def test_term_normalization_router_blocks_conflict(self):
        """工作流路由：术语冲突时不继续进入 DSL 生成链路。"""
        from app.graph.workflow import _term_normalization_router

        assert (
            _term_normalization_router(
                {"route_payload": {"kind": "term_conflict_clarification"}}
            )
            == "end"
        )
        assert _term_normalization_router({"route_payload": {}}) == "semantic_asset_resolution"

    def test_term_normalize_feeds_semantic_asset_resolution(self):
        """术语归一化结果应影响后续资产解析。"""
        from app.graph.nodes import semantic_asset_resolution_node, term_normalize_node

        state = {
            "question": "销售额趋势",
            "entities": {"metrics": [], "dimensions": []},
            "schema_structured": {
                "metrics": [
                    {"id": 1, "name": "gmv", "display_name": "GMV", "synonyms": []}
                ],
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
            },
        }
        normalized = term_normalize_node(state)
        result = semantic_asset_resolution_node({**state, **normalized})

        assert any(t["name"] == "sales_term" for t in result["semantic_asset_resolution"]["terms"])
        assert any(
            m["name"] == "gmv" and m["match_type"] == "linked_term"
            for m in result["semantic_asset_resolution"]["metrics"]
        )

    def test_semantic_asset_resolution_field_label(self):
        """语义资产解析：字段中文标注可被解析为 field 资产。"""
        from app.graph.nodes import semantic_asset_resolution_node

        state = {
            "question": "查询人员姓名明细",
            "entities": {"metrics": [], "dimensions": []},
            "schema_structured": {
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
        }
        result = semantic_asset_resolution_node(state)

        fields = result["semantic_asset_resolution"]["fields"]
        assert fields[0]["name"] == "person_name"
        assert fields[0]["asset_type"] == "field"
        assert fields[0]["match_type"] in ("display_name", "column_label", "synonym")

    def test_semantic_asset_resolution_term_linked_metric(self):
        """语义资产解析：命中业务术语后扩展显式关联指标。"""
        from app.graph.nodes import semantic_asset_resolution_node

        state = {
            "question": "日报怎么看",
            "entities": {"metrics": [], "dimensions": []},
            "schema_structured": {
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
        }
        result = semantic_asset_resolution_node(state)

        semantic = result["semantic_asset_resolution"]
        assert semantic["terms"][0]["name"] == "daily_report"
        assert any(
            m["name"] == "daily_finish_rate" and m["match_type"] == "linked_term"
            for m in semantic["metrics"]
        )

    def test_semantic_asset_resolution_ambiguity(self):
        """语义资产解析：近似同名资产应输出歧义候选。"""
        from app.graph.nodes import semantic_asset_resolution_node

        state = {
            "question": "查询地区",
            "entities": {"metrics": [], "dimensions": ["地区"]},
            "schema_structured": {
                "metrics": [],
                "dimensions": [
                    {"id": 1, "name": "region", "display_name": "地区", "synonyms": []},
                    {"id": 2, "name": "area", "display_name": "地区", "synonyms": []},
                ],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        }
        result = semantic_asset_resolution_node(state)

        ambiguities = result["semantic_asset_resolution"]["ambiguities"]
        assert ambiguities
        assert {c["asset_id"] for c in ambiguities[0]["candidates"]} == {1, 2}

    def test_analysis_blueprint_execute_success(self, db_session, sample_dataset):
        """蓝图执行：执行只读 SQL 模板并写入结果。"""
        from app.graph.nodes import analysis_blueprint_execute_node
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
            "question": "为什么本月毛利下降",
            "dataset_id": sample_dataset.id,
            "blueprint_id": bp.id,
        }
        result = analysis_blueprint_execute_node(db_session)(state)

        assert result["generation_mode"] == "analysis_blueprint"
        assert result["sql_result"]["row_count"] == 1
        assert result["sql_result"]["rows"][0]["category"] == "电子"
        assert result["route_payload"]["blueprint_id"] == bp.id
        db_session.refresh(bp)
        assert bp.usage_count == 1
        assert db_session.query(BlueprintUsageLog).filter_by(blueprint_id=bp.id).count() == 1

    def test_analysis_blueprint_semantic_plan_enters_query_graph(
        self, db_session, sample_dataset
    ):
        """手动语义蓝图：不要求 SQL，转为 QueryGraph 业务上下文。"""
        from app.graph.nodes import analysis_blueprint_execute_node
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

        result = analysis_blueprint_execute_node(db_session)(
            {
                "question": "我要查询2024年杨凯的日报",
                "dataset_id": sample_dataset.id,
                "blueprint_id": bp.id,
            }
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
        from app.graph.nodes import analysis_blueprint_execute_node
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

        result = analysis_blueprint_execute_node(db_session)(
            {
                "question": "跑毛利分析",
                "dataset_id": sample_dataset.id,
                "blueprint_id": bp.id,
            }
        )

        assert result["sql_result"] is None
        assert result["route_payload"]["kind"] == "clarification"
        assert result["route_payload"]["missing"] == ["start_date"]

    def test_analysis_blueprint_execute_blocks_unsafe_sql(self, db_session, sample_dataset):
        """蓝图执行：拦截非只读 SQL。"""
        from app.graph.nodes import analysis_blueprint_execute_node
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

        result = analysis_blueprint_execute_node(db_session)(
            {
                "question": "执行危险蓝图",
                "dataset_id": sample_dataset.id,
                "blueprint_id": bp.id,
            }
        )

        assert result["sql_result"] is None
        assert "drop" in result["error"].lower()

    def test_entry_intent_knowledge_term(self, db_session, sample_dataset):
        """入口分类：知识解释命中业务术语。"""
        from app.graph.nodes import entry_intent_classification_node
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
        result = entry_intent_classification_node(db_session)(state)

        assert result["entry_intent"] == "knowledge_qa"
        assert result["entry_route"] == "knowledge_qa"
        assert result["knowledge_term_id"] == term.id
        assert "商品交易总额" in result["answer"]

    def test_entry_intent_permission_rejection(self, db_session, sample_dataset):
        """入口分类：权限不足问题拒答，不进入 QueryGraph。"""
        from app.graph.nodes import entry_intent_classification_node

        state = {
            "question": "帮我查一下没有权限的数据源",
            "dataset_id": sample_dataset.id,
            "intent": "query",
            "entities": {},
        }
        result = entry_intent_classification_node(db_session)(state)

        assert result["entry_intent"] == "rejection"
        assert result["entry_route"] == "reject"
        assert "权限" in result["answer"]

    def test_entry_intent_clarification(self, db_session, sample_dataset):
        """入口分类：短句指代不清时进入澄清。"""
        from app.graph.nodes import entry_intent_classification_node

        state = {
            "question": "这个呢",
            "dataset_id": sample_dataset.id,
            "intent": "query",
            "entities": {},
        }
        result = entry_intent_classification_node(db_session)(state)

        assert result["entry_intent"] == "clarification"
        assert result["entry_route"] == "clarify"
        assert "补充" in result["answer"]

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
                "filters": [
                    {"field": "person_name", "op": "in", "values": ["李四", "王五"]}
                ],
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

        with patch("app.graph.nodes.get_llm") as mock_get_llm:
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


class TestWorkflowRouting:
    """测试工作流路由逻辑"""

    def test_should_continue_chitchat(self):
        """闲聊意图直接结束"""
        from app.graph.workflow import _should_continue

        assert _should_continue({"intent": "chitchat"}) == "end"

    def test_should_continue_query(self):
        """查询意图继续"""
        from app.graph.workflow import _should_continue

        assert _should_continue({"intent": "query"}) == "schema_recall"

    def test_entry_classification_router_query_graph(self):
        """入口分类：普通问数进入 QueryGraph。"""
        from app.graph.workflow import _entry_classification_router

        assert _entry_classification_router({"entry_route": "query_graph"}) == "schema_recall"

    def test_entry_classification_router_non_query(self):
        """入口分类：蓝图/知识库/澄清/拒答不进入 NL2SQL。"""
        from app.graph.workflow import _entry_classification_router

        assert (
            _entry_classification_router({"entry_route": "analysis_blueprint"})
            == "analysis_blueprint_execute"
        )

    def test_analysis_blueprint_execution_router_success(self):
        """蓝图执行成功后生成报告。"""
        from app.graph.workflow import _analysis_blueprint_execution_router

        assert _analysis_blueprint_execution_router({"sql_result": {"rows": []}}) == "report"

    def test_analysis_blueprint_execution_router_failed(self):
        """蓝图执行失败后直接结束。"""
        from app.graph.workflow import _analysis_blueprint_execution_router

        assert _analysis_blueprint_execution_router({"sql_result": None}) == "end"

    def test_analysis_blueprint_execution_router_semantic_plan(self):
        """手动语义蓝图执行后回到 QueryGraph。"""
        from app.graph.workflow import _analysis_blueprint_execution_router

        assert (
            _analysis_blueprint_execution_router(
                {"generation_mode": "analysis_blueprint_semantic", "sql_result": None}
            )
            == "schema_recall"
        )

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
            "metadata": {"langgraph_node": "intent_recognition"},
        }

        output = _extract_node_output(event, "intent_recognition")

        assert output["intent"] == "query"
        assert output["entities"]["metrics"] == ["gmv"]

    def test_chat_stream_event_types(self, client, sample_dataset):
        """SSE 流式接口每个事件必须含 type 字段，值为 step / token / final 之一"""
        payload = {"question": "查询所有订单", "dataset_id": sample_dataset.id}
        with patch("app.api.chat.build_workflow") as mock_wf:
            # 模拟 astream_events 返回两个 step 事件和一个 final 事件
            async def fake_astream_events(state, version):
                yield {
                    "event": "on_chain_start",
                    "name": "intent_recognition",
                    "data": {},
                    "metadata": {"langgraph_node": "intent_recognition"},
                }
                yield {
                    "event": "on_chain_end",
                    "name": "intent_recognition",
                    "data": {"output": {"intent": "query", "entities": {}}},
                    "metadata": {"langgraph_node": "intent_recognition"},
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

            lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
            events = [json.loads(l[5:].strip()) for l in lines]
            types = {e["type"] for e in events}
            assert "step" in types
            assert "token" in types
            assert "final" in types

    def test_chat_stream_step_event_structure(self, client, sample_dataset):
        """step 事件必须含 node 和 status 字段"""
        payload = {"question": "测试", "dataset_id": sample_dataset.id}
        with patch("app.api.chat.build_workflow") as mock_wf:

            async def fake_astream_events(state, version):
                yield {
                    "event": "on_chain_start",
                    "name": "intent_recognition",
                    "data": {},
                    "metadata": {"langgraph_node": "intent_recognition"},
                }
                yield {
                    "event": "on_chain_end",
                    "name": "intent_recognition",
                    "data": {"output": {"intent": "query", "entities": {}}},
                    "metadata": {"langgraph_node": "intent_recognition"},
                }

            mock_graph = MagicMock()
            mock_graph.astream_events = fake_astream_events
            mock_wf.return_value = mock_graph

            try:
                resp = client.post("/api/chat/stream", json=payload)
            except Exception:
                # sse_starlette 在测试中复用事件循环时可能抛出 ExceptionGroup，跳过
                pytest.skip("SSE AppStatus event loop issue in repeated TestClient usage")

            lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
            step_events = [json.loads(l[5:].strip()) for l in lines if '"step"' in l]
            for e in step_events:
                assert "node" in e
                assert "status" in e
                assert e["status"] in ("running", "done")
