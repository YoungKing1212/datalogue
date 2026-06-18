import json

from app.services.subagent_planning.asset_detail import AssetDetailRequest, AssetDetailResult
from app.services.subagent_planning.contracts import CandidateAsset, QueryPlan
from app.services.subagent_planning.detail_loop import PlannerDetailLoop, PlannerLoopResult
from app.services.subagent_planning.sql_context import build_sql_generation_context


class ScriptedPlanner:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.outputs.pop(0)


def _candidate_assets(field_count=4):
    fields = [
        {
            "table_name": "plan_task_daily_record",
            "column_name": f"field_{index}",
            "column_comment": f"字段 {index}",
            "data_type": "varchar",
        }
        for index in range(field_count)
    ]
    return {
        "dataset_id": 10,
        "question": "查询用户任务日志",
        "assets": [
            {
                "asset_type": "table",
                "asset_id": "plan_task_daily_record",
                "name": "plan_task_daily_record",
                "display_name": "任务日报",
                "confidence": 0.9,
                "metadata": {"table_name": "plan_task_daily_record", "comment": "任务日报"},
            }
        ],
        "context": {"schema_structured": {"fields": fields}},
    }


def test_detail_loop_hydrates_requested_asset_then_returns_final_plan():
    planner = ScriptedPlanner(
        [
            {
                "asset_detail_requests": [
                    {
                        "asset_type": "table",
                        "asset_id": "plan_task_daily_record",
                        "detail_level": "full_schema",
                        "purpose": "sql_generation",
                        "reason": "需要字段",
                    }
                ]
            },
            QueryPlan(
                query_type="detail_query",
                execution_strategy="query_graph",
                confidence=0.8,
                planner_source="llm",
            ),
        ]
    )
    loop = PlannerDetailLoop(max_rounds=3, max_requests_per_round=5, planner_call=planner)
    result = loop.run(
        db=None,
        question="查询用户任务日志",
        routing={"dataset_id": 10},
        candidate_assets=_candidate_assets(),
    )
    assert isinstance(result, PlannerLoopResult)
    assert result.query_plan.execution_strategy == "query_graph"
    assert result.detail_rounds == 1
    assert result.asset_details[0].coverage == "full"
    assert len(planner.calls) == 2


def test_detail_loop_returns_sql_generation_context_without_embedding_details_in_query_plan():
    planner = ScriptedPlanner(
        [
            {
                "asset_detail_requests": [
                    {
                        "asset_type": "table",
                        "asset_id": "plan_task_daily_record",
                        "detail_level": "full_schema",
                        "purpose": "sql_generation",
                        "reason": "需要字段生成 SQL",
                    }
                ]
            },
            QueryPlan(
                query_type="detail_query",
                execution_strategy="query_graph",
                confidence=0.8,
                selected_assets=[
                    CandidateAsset(
                        asset_type="table",
                        asset_id="plan_task_daily_record",
                        name="plan_task_daily_record",
                        display_name="任务日报",
                        source="recall",
                        confidence=0.9,
                        usage="selected",
                    )
                ],
                planner_source="llm",
            ),
        ]
    )
    loop = PlannerDetailLoop(max_rounds=3, max_requests_per_round=5, planner_call=planner)

    result = loop.run(
        db=None,
        question="查询用户任务日志",
        routing={"dataset_id": 10},
        candidate_assets=_candidate_assets(),
    )

    sql_context = result.sql_generation_context
    assert sql_context["table_schemas"][0]["asset_id"] == "plan_task_daily_record"
    assert sql_context["table_schemas"][0]["fields"][0]["name"] == "field_0"
    assert sql_context["coverage"] == {"plan_task_daily_record": "full"}
    assert sql_context["selected_assets"][0]["asset_id"] == "plan_task_daily_record"
    assert "table_schemas" not in result.query_plan.to_dict()


def test_sql_generation_context_deep_copies_payload_and_merges_risk_flags():
    detail = AssetDetailResult(
        request=AssetDetailRequest(
            asset_type="table",
            asset_id="plan_task_daily_record",
            detail_level="full_schema",
            purpose="sql_generation",
        ),
        coverage="full",
        payload={
            "fields": [{"name": "field_0", "metadata": {"source": "schema"}}],
            "metadata": {"owner": "origin"},
        },
        risk_flags=["detail_risk", "shared_risk"],
    )
    query_plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.8,
        risk_flags=["plan_risk", "shared_risk"],
    )

    sql_context = build_sql_generation_context(
        query_plan=query_plan,
        asset_details=[detail],
        lightweight_catalog={"summary": {"schema_version": "v1", "manifest_version": "m1"}},
    )
    sql_context["table_schemas"][0]["fields"][0]["name"] = "mutated"
    sql_context["table_schemas"][0]["metadata"]["owner"] = "mutated"

    assert detail.payload["fields"][0]["name"] == "field_0"
    assert detail.payload["metadata"]["owner"] == "origin"
    assert sql_context["risk_flags"] == ["detail_risk", "plan_risk", "shared_risk"]


def test_detail_loop_rejects_out_of_scope_request_and_retries_planner():
    planner = ScriptedPlanner(
        [
            {
                "asset_detail_requests": [
                    {
                        "asset_type": "table",
                        "asset_id": "not_recalled",
                        "detail_level": "full_schema",
                        "purpose": "sql_generation",
                        "reason": "越界请求",
                    }
                ]
            },
            QueryPlan(
                query_type="unsupported",
                execution_strategy="reject",
                confidence=0.2,
                planner_source="fallback",
                missing_context=["资产不在召回范围"],
                why_not_generate_sql="资产详情请求越界。",
            ),
        ]
    )
    loop = PlannerDetailLoop(max_rounds=3, max_requests_per_round=5, planner_call=planner)
    result = loop.run(
        db=None,
        question="查询用户任务日志",
        routing={"dataset_id": 10},
        candidate_assets=_candidate_assets(),
    )
    assert result.query_plan.execution_strategy == "reject"
    assert result.warnings[0]["error_code"] == "asset_not_in_recall_scope"
    planner_warnings = result.query_plan.to_dict()["planner_warnings"]
    assert planner_warnings[0]["code"] == "asset_not_in_recall_scope"
    assert planner_warnings[0]["request"]["asset_id"] == "not_recalled"


def test_detail_loop_forces_reject_after_max_rounds_when_planner_keeps_requesting():
    planner = ScriptedPlanner(
        [
            {
                "asset_detail_requests": [
                    {
                        "asset_type": "table",
                        "asset_id": "plan_task_daily_record",
                        "detail_level": "full_schema",
                        "purpose": "sql_generation",
                        "reason": "第 1 轮",
                    }
                ]
            },
            {
                "asset_detail_requests": [
                    {
                        "asset_type": "table",
                        "asset_id": "plan_task_daily_record",
                        "detail_level": "full_schema",
                        "purpose": "sql_generation",
                        "reason": "第 2 轮",
                    }
                ]
            },
            {
                "asset_detail_requests": [
                    {
                        "asset_type": "table",
                        "asset_id": "plan_task_daily_record",
                        "detail_level": "full_schema",
                        "purpose": "sql_generation",
                        "reason": "第 3 轮",
                    }
                ]
            },
        ]
    )
    loop = PlannerDetailLoop(max_rounds=3, max_requests_per_round=5, planner_call=planner)
    result = loop.run(
        db=None,
        question="查询用户任务日志",
        routing={"dataset_id": 10},
        candidate_assets=_candidate_assets(),
    )
    assert result.query_plan.execution_strategy == "reject"
    assert result.query_plan.fallback_reason == "max_detail_rounds_exceeded"
    assert result.query_plan.why_not_generate_sql == "达到 3 轮资产详情请求后仍未形成可执行计划。"


def test_detail_loop_clamps_max_rounds_to_three_when_configured_higher():
    request = {
        "asset_type": "table",
        "asset_id": "plan_task_daily_record",
        "detail_level": "full_schema",
        "purpose": "sql_generation",
        "reason": "持续请求",
    }
    planner = ScriptedPlanner([{"asset_detail_requests": [request]} for _ in range(5)])
    loop = PlannerDetailLoop(max_rounds=5, max_requests_per_round=5, planner_call=planner)

    result = loop.run(
        db=None,
        question="查询用户任务日志",
        routing={"dataset_id": 10},
        candidate_assets=_candidate_assets(),
    )

    assert len(planner.calls) == 3
    assert result.detail_rounds == 3
    assert result.query_plan.fallback_reason == "max_detail_rounds_exceeded"


def test_detail_loop_truncates_oversized_request_batch_before_audit_and_hydration():
    requests = [
        {
            "asset_type": "table",
            "asset_id": "plan_task_daily_record",
            "detail_level": "full_schema",
            "purpose": "sql_generation",
            "reason": f"第 {index} 个请求",
        }
        for index in range(4)
    ]
    planner = ScriptedPlanner(
        [
            {"asset_detail_requests": requests},
            QueryPlan(
                query_type="detail_query",
                execution_strategy="query_graph",
                confidence=0.8,
                planner_source="llm",
            ),
        ]
    )
    loop = PlannerDetailLoop(max_rounds=3, max_requests_per_round=2, planner_call=planner)

    result = loop.run(
        db=None,
        question="查询用户任务日志",
        routing={"dataset_id": 10},
        candidate_assets=_candidate_assets(),
    )

    assert len(result.attempted_detail_requests) == 2
    assert len(planner.calls[1]["previous_detail_requests"]) == 2
    assert len(result.asset_details) == 2
    summary_warning = result.warnings[0]
    assert summary_warning["code"] == "asset_detail_request_limit_exceeded"
    assert summary_warning["requested_count"] == 4
    assert summary_warning["max_requests"] == 2
    assert len(summary_warning["request"]["sampled_requests"]) == 2
    assert len(result.query_plan.to_dict()["attempted_detail_requests"]) == 2


def test_detail_loop_sanitizes_oversized_request_audit_without_mutating_detail_request():
    long_reason = "需要定位字段" + "长" * 500
    long_query = "SELECT * FROM private_schema.secret_table WHERE expr = 'raw_payload'" + "x" * 500
    requests = [
        {
            "asset_type": "table",
            "asset_id": "plan_task_daily_record",
            "detail_level": "field_search",
            "purpose": "sql_generation",
            "reason": long_reason,
            "query": long_query,
            "top_k": 5,
        },
        {
            "asset_type": "table",
            "asset_id": "not_recalled",
            "detail_level": "full_schema",
            "purpose": "sql_generation",
            "reason": long_reason,
            "query": long_query,
        },
    ]
    planner = ScriptedPlanner(
        [
            {"asset_detail_requests": requests},
            QueryPlan(
                query_type="detail_query",
                execution_strategy="query_graph",
                confidence=0.8,
                planner_source="llm",
            ),
        ]
    )

    class CapturingDetailService:
        def __init__(self):
            self.requests = []

        def get_detail(self, request):
            self.requests.append(request)
            return AssetDetailResult(
                request=request,
                coverage="partial",
                payload={"fields": [{"name": "field_0"}]},
            )

    detail_service = CapturingDetailService()
    loop = PlannerDetailLoop(
        max_rounds=3,
        max_requests_per_round=5,
        planner_call=planner,
        detail_service=detail_service,
    )

    result = loop.run(
        db=None,
        question="查询用户任务日志",
        routing={"dataset_id": 10},
        candidate_assets=_candidate_assets(),
    )

    assert detail_service.requests[0].query == long_query
    assert len(result.attempted_detail_requests[0]["reason"]) <= 180
    assert result.attempted_detail_requests[0]["query"] == "[removed_detail_context]"
    audit_text = json.dumps(
        {
            "attempted": result.attempted_detail_requests,
            "warnings": result.warnings,
            "planner_warnings": result.query_plan.to_dict()["planner_warnings"],
        },
        ensure_ascii=False,
    )
    assert "private_schema.secret_table" not in audit_text
    assert "SELECT * FROM" not in audit_text
    assert "raw_payload" not in audit_text
