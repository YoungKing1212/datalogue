# ============================================================
# File Name   : test_dataset_subagent.py
# Description:
#   Phase 5/6/7: DatasetSubAgent 单元测试。
#
#   Phase 5: resolve_analysis_blueprint — 6 状态分支 + 13 字段 + tracer。
#   Phase 6: resolve_term_conflict — 5 状态分支 + 字段结构 + tracer + 边界。
#   Phase 7: resolve_metric — 5 状态分支 + 字段结构 + tracer + 边界。
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.security import encrypt_password
from app.models.dataset import AnalysisBlueprint, SemanticDataset
from app.models.datasource import Datasource
from app.services.dataset_subagent import DatasetSubAgent


# ============================================================
# 测试基础设施
# ============================================================


def _setup_session(dataset_id: int = 1):
    """构造 in-memory SQLite + 临时文件数据源（让 executed 路线能跑 SQL）。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()

    ds = Datasource(
        id=1,
        name="bp-test-ds",
        db_type="sqlite",
        host="",
        port=0,
        database_name=tmp_db.name,
        username="",
        password_enc=encrypt_password("test"),
    )
    session.add(ds)
    session.commit()
    session.refresh(ds)

    dataset = SemanticDataset(
        id=dataset_id,
        name="bp-test-dataset",
        datasource_id=ds.id,
        status="active",
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)

    return engine, session, dataset, Path(tmp_db.name)


def _make_blueprint(session, dataset_id, **kwargs) -> AnalysisBlueprint:
    bp = AnalysisBlueprint(dataset_id=dataset_id, **kwargs)
    session.add(bp)
    session.commit()
    session.refresh(bp)
    return bp


def _make_sub_agent(session, dataset_id, tracer=None, trace_context=None):
    return DatasetSubAgent(db=session, dataset_id=dataset_id), tracer, trace_context


@pytest.fixture
def bp_env():
    """准备带数据源 + dataset 的 in-memory 测试环境。"""
    engine, session, dataset, tmp_path = _setup_session(dataset_id=1)
    yield engine, session, dataset, tmp_path
    session.close()
    engine.dispose()
    tmp_path.unlink(missing_ok=True)


# ============================================================
# 6 状态分支测试
# ============================================================


def test_not_applicable_no_blueprint_id(bp_env):
    """分支 1a：无 blueprint_id → not_applicable。"""
    _, session, dataset, _ = bp_env
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    result = sub.resolve_analysis_blueprint(
        blueprint_id=None,
        question="为什么毛利下降",
        entry_route="analysis_blueprint",
    )
    assert result["status"] == "not_applicable"
    assert result["blueprint_id"] is None
    assert result["blueprint_name"] is None
    assert result["sql_result"] is None
    assert result["sql"] is None
    assert result["sql_list"] == []
    assert result["generation_mode"] is None
    assert result["blueprint_context"] is None
    assert result["answer"] is None
    assert result["error"] == "未命中分析蓝图，无法执行"
    assert result["should_retry"] is False
    assert result["route_payload"] == {"kind": "not_applicable"}


def test_not_applicable_entry_route_mismatch(bp_env):
    """分支 1b：entry_route != analysis_blueprint → not_applicable。"""
    _, session, dataset, _ = bp_env
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    result = sub.resolve_analysis_blueprint(
        blueprint_id=999,
        question="为什么毛利下降",
        entry_route="query_graph",
    )
    assert result["status"] == "not_applicable"
    assert result["error"] == "分析蓝图不存在或不属于当前数据集"
    assert result["route_payload"] == {"kind": "not_applicable"}


def test_not_found_blueprint_id_not_exist(bp_env):
    """分支 2a：blueprint_id 在 db 中查无 → not_found。"""
    _, session, dataset, _ = bp_env
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    result = sub.resolve_analysis_blueprint(
        blueprint_id=99999,
        question="为什么毛利下降",
        entry_route="analysis_blueprint",
    )
    assert result["status"] == "not_found"
    assert result["blueprint_id"] == 99999
    assert result["blueprint_name"] is None
    assert result["sql_result"] is None
    assert result["sql"] is None
    assert result["sql_list"] == []
    assert result["generation_mode"] is None
    assert result["blueprint_context"] is None
    assert result["answer"] is None
    assert "不存在" in result["error"]
    assert result["should_retry"] is False
    assert result["route_payload"] == {"kind": "not_found", "blueprint_id": 99999}


def test_not_found_blueprint_dataset_mismatch(bp_env):
    """分支 2b：blueprint 属于别的 dataset → not_found。"""
    _, session, dataset, _ = bp_env
    # 第二个 dataset + 蓝图
    ds_other = SemanticDataset(
        id=999, name="other", datasource_id=dataset.datasource_id, status="active"
    )
    session.add(ds_other)
    session.commit()
    bp = AnalysisBlueprint(
        dataset_id=ds_other.id, name="跨 dataset 蓝图",
        call_template="SELECT 1", status="active",
    )
    session.add(bp)
    session.commit()
    session.refresh(bp)

    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    result = sub.resolve_analysis_blueprint(
        blueprint_id=bp.id, question="x", entry_route="analysis_blueprint"
    )
    assert result["status"] == "not_found"
    assert result["blueprint_id"] == bp.id


def test_semantic_plan_basic(bp_env):
    """分支 3：semantic_plan 蓝图 → 注入 QueryGraph 业务上下文。"""
    _, session, dataset, _ = bp_env
    bp = _make_blueprint(
        session, dataset.id,
        name="个人计划任务日报查询",
        description="按人员姓名和时间范围查询个人计划任务日报明细。",
        parameters=[
            {"name": "person_name", "type": "string", "required": True, "semantic": "人员姓名"},
        ],
        output_schema=[{"column": "report_date", "semantic": "日报日期", "role": "dimension"}],
        steps=[{"name": "过滤人员", "purpose": "按姓名过滤", "key_rules": ["排除作废"]}],
        implementation_type="semantic_plan",
        status="active",
    )

    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    result = sub.resolve_analysis_blueprint(
        blueprint_id=bp.id,
        question="查询 2024 年杨凯的日报",
        entry_route="analysis_blueprint",
        original_question="查 2024 年杨凯的日报",
        resolved_question="查询 2024 年杨凯的日报",
    )
    assert result["status"] == "semantic_plan"
    assert result["blueprint_id"] == bp.id
    assert result["blueprint_name"] == "个人计划任务日报查询"
    assert result["sql_result"] is None
    assert result["sql"] is None
    assert result["sql_list"] == []
    assert result["generation_mode"] == "analysis_blueprint_semantic"
    assert result["blueprint_context"] is not None
    assert "个人计划任务日报查询" in result["blueprint_context"]
    assert "不能要求用户提供 SQL" in result["blueprint_context"]
    assert result["answer"] is None
    assert result["error"] is None
    assert result["should_retry"] is False
    assert result["route_payload"]["kind"] == "analysis_blueprint_semantic"
    assert result["route_payload"]["blueprint_id"] == bp.id
    assert result["route_payload"]["name"] == "个人计划任务日报查询"
    assert result["route_payload"]["implementation_type"] == "semantic_plan"


def test_executed_sql_template_success(bp_env):
    """分支 4：SQL 模板执行成功 → executed。"""
    _, session, dataset, _ = bp_env
    bp = _make_blueprint(
        session, dataset.id,
        name="毛利归因",
        parameters=[
            {"name": "start_date", "type": "date", "required": True, "default_expr": "MONTH_START"},
            {"name": "end_date", "type": "date", "required": True, "default_expr": "TODAY"},
        ],
        call_template=(
            "SELECT :start_date AS start_date, :end_date AS end_date, "
            "'电子' AS category, 0.31 AS margin_rate"
        ),
        status="active",
    )

    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    result = sub.resolve_analysis_blueprint(
        blueprint_id=bp.id,
        question="为什么毛利下降",
        entry_route="analysis_blueprint",
        original_question="为什么去年毛利下降",
        resolved_question="为什么 2025 年毛利下降",
        time_context={
            "detected_time_range": {
                "label": "去年", "start_date": "2025-01-01", "end_date": "2025-12-31",
                "granularity": "year", "source": "relative_last_year",
            }
        },
    )
    assert result["status"] == "executed"
    assert result["blueprint_id"] == bp.id
    assert result["blueprint_name"] == "毛利归因"
    assert result["sql_result"]["row_count"] == 1
    assert result["sql_result"]["rows"][0]["category"] == "电子"
    assert result["sql"] is not None
    assert ":start_date" not in result["sql"]
    assert "'" in result["sql"]
    assert result["sql_list"] == [result["sql"]]
    assert result["generation_mode"] == "analysis_blueprint"
    assert result["blueprint_context"] is None
    assert result["answer"] is None
    assert result["error"] is None
    assert result["should_retry"] is False
    rp = result["route_payload"]
    assert rp["kind"] == "analysis_blueprint"
    assert rp["blueprint_id"] == bp.id
    assert rp["name"] == "毛利归因"
    assert rp["params"]["start_date"] == "2025-01-01"
    assert rp["params"]["end_date"] == "2025-12-31"
    assert rp["original_question"] == "为什么去年毛利下降"
    assert rp["resolved_question"] == "为什么 2025 年毛利下降"
    assert isinstance(rp["execution_time_ms"], int)
    assert result["execution_time_ms"] == rp["execution_time_ms"]


def test_clarification_missing_required_param(bp_env):
    """分支 5：缺必填参数 → clarification。"""
    _, session, dataset, _ = bp_env
    bp = _make_blueprint(
        session, dataset.id,
        name="毛利归因",
        parameters=[{"name": "start_date", "type": "date", "required": True}],
        call_template="SELECT :start_date AS start_date",
        status="active",
    )

    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    result = sub.resolve_analysis_blueprint(
        blueprint_id=bp.id,
        question="跑毛利分析",
        entry_route="analysis_blueprint",
        original_question="跑毛利分析",
        resolved_question="跑毛利分析",
    )
    assert result["status"] == "clarification"
    assert result["blueprint_id"] == bp.id
    assert result["blueprint_name"] == "毛利归因"
    assert result["sql_result"] is None
    # clarification 路径 sql 已被 sql_preview 替换为 NULL，但 route_payload.sql_template 保留模板
    assert result["sql"] is not None
    assert result["sql_list"] == [result["sql"]]
    assert result["generation_mode"] is None
    assert result["blueprint_context"] is None
    assert result["answer"] is not None
    assert result["error"] is not None
    assert result["should_retry"] is False
    rp = result["route_payload"]
    assert rp["kind"] == "clarification"
    assert rp["blueprint_id"] == bp.id
    assert rp["missing"] == ["start_date"]
    assert rp["original_question"] == "跑毛利分析"
    assert rp["resolved_question"] == "跑毛利分析"


def test_error_not_active_blueprint(bp_env):
    """分支 6a：蓝图未发布（status != active）→ error。"""
    _, session, dataset, _ = bp_env
    bp = _make_blueprint(
        session, dataset.id,
        name="草稿蓝图",
        call_template="SELECT 1",
        status="draft",
    )
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    result = sub.resolve_analysis_blueprint(
        blueprint_id=bp.id, question="x", entry_route="analysis_blueprint"
    )
    assert result["status"] == "error"
    assert result["blueprint_id"] == bp.id
    assert result["blueprint_name"] == "草稿蓝图"
    assert result["sql_result"] is None
    assert result["answer"] is not None
    assert result["error"] is not None
    assert "尚未发布" in result["error"] or "draft" in result["error"].lower()
    assert result["should_retry"] is False
    assert result["route_payload"]["kind"] == "analysis_blueprint_error"


def test_error_sql_execution_failed(bp_env):
    """分支 6b：SQL 执行失败（非缺参）→ error。"""
    _, session, dataset, _ = bp_env
    bp = _make_blueprint(
        session, dataset.id,
        name="危险蓝图",
        call_template="DROP TABLE orders",
        status="active",
    )
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    result = sub.resolve_analysis_blueprint(
        blueprint_id=bp.id, question="x", entry_route="analysis_blueprint"
    )
    assert result["status"] == "error"
    assert "drop" in (result.get("error") or "").lower()
    assert result["route_payload"]["kind"] == "analysis_blueprint_error"


# ============================================================
# 13 字段存在性 + tracer span + 边界测试
# ============================================================


def test_status_field_present(bp_env):
    """所有分支都返回 status 字段。"""
    _, session, dataset, _ = bp_env
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out = sub.resolve_analysis_blueprint(blueprint_id=None, question="x")
    assert "status" in out
    assert out["status"] in (
        "not_applicable", "not_found", "semantic_plan",
        "executed", "clarification", "error",
    )


def test_blueprint_id_field_present(bp_env):
    """所有分支都返回 blueprint_id 字段（None 或 int）。"""
    _, session, dataset, _ = bp_env
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out = sub.resolve_analysis_blueprint(blueprint_id=None, question="x")
    assert "blueprint_id" in out
    assert out["blueprint_id"] is None


def test_blueprint_name_field_present(bp_env):
    """所有分支都返回 blueprint_name 字段。"""
    _, session, dataset, _ = bp_env
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out = sub.resolve_analysis_blueprint(blueprint_id=None, question="x")
    assert "blueprint_name" in out
    assert out["blueprint_name"] is None


def test_execution_time_ms_field_present(bp_env):
    """executed 分支返回 execution_time_ms 字段。"""
    _, session, dataset, _ = bp_env
    bp = _make_blueprint(
        session, dataset.id,
        name="测试", call_template="SELECT 1", status="active",
    )
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out = sub.resolve_analysis_blueprint(
        blueprint_id=bp.id, question="x", entry_route="analysis_blueprint"
    )
    assert out["status"] == "executed"
    assert "execution_time_ms" in out
    assert isinstance(out["execution_time_ms"], int)
    assert out["execution_time_ms"] >= 0


def test_error_legacy_compat(bp_env):
    """旧节点字段保留：sql / sql_list / should_retry / route_payload。"""
    _, session, dataset, _ = bp_env
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out = sub.resolve_analysis_blueprint(blueprint_id=None, question="x")
    for key in ("sql", "sql_list", "should_retry", "route_payload", "sql_result", "answer", "error"):
        assert key in out, f"缺少兼容字段 {key}"


def test_jsonable_encoder_used(bp_env):
    """返回 dict 必须可被 jsonable_encoder 二次编码（Pydantic 友好）。"""
    from fastapi.encoders import jsonable_encoder
    _, session, dataset, _ = bp_env
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out = sub.resolve_analysis_blueprint(blueprint_id=None, question="x")
    encoded = jsonable_encoder(out)
    assert isinstance(encoded, dict)
    assert encoded["status"] == "not_applicable"


def test_tracer_span_emitted(bp_env):
    """tracer.start_span + end_span 被调用。"""
    _, session, dataset, _ = bp_env
    tracer = MagicMock()
    trace_context = MagicMock()
    span = MagicMock()
    tracer.start_span.return_value = span

    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out = sub.resolve_analysis_blueprint(
        blueprint_id=None, question="x",
        tracer=tracer, trace_context=trace_context,
    )
    tracer.start_span.assert_called_once()
    span.end_span.assert_called_once()
    # end_span 的 output_payload 含 status
    call_kwargs = span.end_span.call_args.kwargs
    assert "output_payload" in call_kwargs
    assert call_kwargs["output_payload"]["status"] == "not_applicable"


def test_tracer_span_emitted_executed(bp_env):
    """tracer 在 executed 路径也正常 emit。"""
    _, session, dataset, _ = bp_env
    bp = _make_blueprint(
        session, dataset.id,
        name="测试", call_template="SELECT 1", status="active",
    )
    tracer = MagicMock()
    trace_context = MagicMock()
    span = MagicMock()
    tracer.start_span.return_value = span

    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out = sub.resolve_analysis_blueprint(
        blueprint_id=bp.id, question="x", entry_route="analysis_blueprint",
        tracer=tracer, trace_context=trace_context,
    )
    assert out["status"] == "executed"
    span.end_span.assert_called_once()
    assert span.end_span.call_args.kwargs["output_payload"]["status"] == "executed"
    assert span.end_span.call_args.kwargs["output_payload"]["blueprint_id"] == bp.id


def test_no_tracer_no_crash(bp_env):
    """tracer=None / trace_context=None 时不崩。"""
    _, session, dataset, _ = bp_env
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out = sub.resolve_analysis_blueprint(
        blueprint_id=None, question="x",
        tracer=None, trace_context=None,
    )
    assert out["status"] == "not_applicable"


def test_tracer_crash_does_not_break_main_flow(bp_env):
    """tracer.start_span 抛异常时主流程仍返回 outcome。"""
    _, session, dataset, _ = bp_env
    tracer = MagicMock()
    trace_context = MagicMock()
    tracer.start_span.side_effect = RuntimeError("tracer down")

    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out = sub.resolve_analysis_blueprint(
        blueprint_id=None, question="x",
        tracer=tracer, trace_context=trace_context,
    )
    assert out["status"] == "not_applicable"


def test_resolve_analysis_blueprint_idempotent(bp_env):
    """连续调用两次返回相同 outcome 形状。"""
    _, session, dataset, _ = bp_env
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out1 = sub.resolve_analysis_blueprint(blueprint_id=None, question="x")
    out2 = sub.resolve_analysis_blueprint(blueprint_id=None, question="x")
    assert out1["status"] == out2["status"]
    assert out1["error"] == out2["error"]
    assert out1["route_payload"] == out2["route_payload"]


def test_question_optional(bp_env):
    """question 缺省 / 空字符串都不崩。"""
    _, session, dataset, _ = bp_env
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out_empty = sub.resolve_analysis_blueprint(blueprint_id=None, question="")
    assert out_empty["status"] == "not_applicable"


def test_time_context_passed_through(bp_env):
    """time_context 透传到 executed 路径的 params 解析。"""
    _, session, dataset, _ = bp_env
    bp = _make_blueprint(
        session, dataset.id,
        name="时间敏感",
        parameters=[
            {"name": "start_date", "type": "date", "required": True, "default_expr": "MONTH_START"},
            {"name": "end_date", "type": "date", "required": True, "default_expr": "TODAY"},
        ],
        call_template="SELECT :start_date AS s, :end_date AS e",
        status="active",
    )
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out = sub.resolve_analysis_blueprint(
        blueprint_id=bp.id, question="x", entry_route="analysis_blueprint",
        time_context={
            "detected_time_range": {
                "start_date": "2024-06-01", "end_date": "2024-06-30",
                "granularity": "month", "source": "explicit",
            }
        },
    )
    assert out["status"] == "executed"
    assert out["route_payload"]["params"]["start_date"] == "2024-06-01"
    assert out["route_payload"]["params"]["end_date"] == "2024-06-30"


def test_dataset_id_mismatch_blocked(bp_env):
    """dataset_id 校验：跨 dataset 蓝图被拦截为 not_found。"""
    _, session, dataset, _ = bp_env
    # 构造另一个 dataset 的蓝图
    other = SemanticDataset(
        id=42, name="other", datasource_id=dataset.datasource_id, status="active"
    )
    session.add(other)
    session.commit()
    bp = _make_blueprint(
        session, other.id,
        name="他数据集", call_template="SELECT 1", status="active",
    )
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)  # 当前 dataset_id=1
    out = sub.resolve_analysis_blueprint(
        blueprint_id=bp.id, question="x", entry_route="analysis_blueprint"
    )
    assert out["status"] == "not_found"


def test_dataset_id_zero_skips_mismatch_check(bp_env):
    """dataset_id=0 时跳过跨 dataset 校验（向后兼容）。"""
    _, session, dataset, _ = bp_env
    bp = _make_blueprint(
        session, dataset.id,
        name="本数据集", call_template="SELECT 1", status="active",
    )
    sub = DatasetSubAgent(db=session, dataset_id=0)  # 0 视为未约束
    out = sub.resolve_analysis_blueprint(
        blueprint_id=bp.id, question="x", entry_route="analysis_blueprint"
    )
    assert out["status"] == "executed"
    assert out["blueprint_id"] == bp.id


def test_original_question_fallback(bp_env):
    """executed 路径：original_question=None 时回退到 question。"""
    _, session, dataset, _ = bp_env
    bp = _make_blueprint(
        session, dataset.id,
        name="测试", call_template="SELECT 1", status="active",
    )
    sub = DatasetSubAgent(db=session, dataset_id=dataset.id)
    out = sub.resolve_analysis_blueprint(
        blueprint_id=bp.id, question="q", entry_route="analysis_blueprint",
        original_question=None, resolved_question=None,
    )
    assert out["status"] == "executed"
    assert out["route_payload"]["original_question"] == "q"
    assert out["route_payload"]["resolved_question"] == "q"


# ============================================================
# Phase 6: resolve_term_conflict 单元测试
# ============================================================


def _sub_agent_no_db(dataset_id: int = 1) -> DatasetSubAgent:
    """构造一个不带真实 DB 的 DatasetSubAgent（resolve_term_conflict 只读入参，不查 DB）。"""
    return DatasetSubAgent(db=None, dataset_id=dataset_id)  # type: ignore[arg-type]


class TestResolveTermConflict:
    """DatasetSubAgent.resolve_term_conflict 5 分支 + 边界覆盖。"""

    def test_status_not_applicable_when_no_terms(self):
        """无 term 候选 → not_applicable 透明通过。"""
        out = _sub_agent_no_db().resolve_term_conflict(question="GMV", terms=[])
        assert out["status"] == "not_applicable"
        assert out["route_payload"]["kind"] == "not_applicable"
        assert out["term_normalization"]["has_conflict"] is False
        assert out["term_normalization"]["matched_terms"] == []
        # not_applicable 分支不返回 entities 字段（透明通过语义）

    def test_status_not_applicable_terms_none(self):
        """terms=None（默认）→ not_applicable。"""
        out = _sub_agent_no_db().resolve_term_conflict(question="GMV")
        assert out["status"] == "not_applicable"
        assert out["route_payload"]["kind"] == "not_applicable"

    def test_status_resolved_single_term_exact_name(self):
        """单 term name 精确命中 → resolved，entities.terms 注入原文。"""
        out = _sub_agent_no_db().resolve_term_conflict(
            question="GMV",
            terms=[{"id": 1, "name": "GMV"}],
            entities={"metrics": [], "dimensions": []},
        )
        assert out["status"] == "resolved"
        assert out["route_payload"]["kind"] == "term_conflict_resolved"
        assert out["term_normalization"]["matched_terms"][0]["term_id"] == 1
        assert out["term_normalization"]["matched_terms"][0]["name"] == "GMV"
        assert out["term_normalization"]["has_conflict"] is False
        assert out["entities"]["terms"] == ["GMV"]
        # 注：直接命中（未走澄清）时 selected_term_id=None；
        # 只有 selected_term_id 注入路径（澄清后）才会设此字段
        assert out["selected_term_id"] is None
        assert out["resolved_question"] == "GMV"

    def test_status_resolved_alias_match_injects_text(self):
        """alias 命中 → entities.terms 注入 matched_text（chat 层负责 merge）。"""
        out = _sub_agent_no_db().resolve_term_conflict(
            question="销售额趋势",
            terms=[{"id": 7, "name": "gmv", "aliases": ["销售额"]}],
            entities={"metrics": [], "dimensions": []},
        )
        assert out["status"] == "resolved"
        assert out["term_normalization"]["matched_terms"][0]["match_type"] == "synonym"
        assert out["entities"]["terms"] == ["销售额"]
        # 入参 entities 不被原地修改（保持纯函数语义）
        assert "terms" not in {"metrics": [], "dimensions": []}

    def test_status_needs_clarification_two_close_aliases(self):
        """同一 alias 命中两个 term → needs_clarification 早退。"""
        out = _sub_agent_no_db().resolve_term_conflict(
            question="销售额是多少",
            terms=[
                {"id": 1, "name": "gmv", "aliases": ["销售额"]},
                {"id": 2, "name": "paid_amount", "aliases": ["销售额"]},
            ],
        )
        assert out["status"] == "needs_clarification"
        assert out["route_payload"]["kind"] == "term_conflict_clarification"
        cands = out["route_payload"]["candidates"]
        assert {c["term_id"] for c in cands} == {1, 2}
        assert out["term_normalization"]["has_conflict"] is True
        assert out["selected_term_id"] is None

    def test_status_resolved_selected_term_id_overrides_conflict(self):
        """selected_term_id 注入后 → 冲突被压成 resolved。"""
        out = _sub_agent_no_db().resolve_term_conflict(
            question="销售额是多少",
            terms=[
                {"id": 1, "name": "gmv", "aliases": ["销售额"]},
                {"id": 2, "name": "paid_amount", "aliases": ["销售额"]},
            ],
            selected_term_id=2,
        )
        assert out["status"] == "resolved"
        assert out["term_normalization"]["has_conflict"] is False
        assert out["term_normalization"]["selected_term_id"] == 2
        assert [m["term_id"] for m in out["term_normalization"]["matched_terms"]] == [2]

    def test_status_missing_term_missing_id(self):
        """term 缺 id → missing_term 错误早退。"""
        out = _sub_agent_no_db().resolve_term_conflict(
            question="GMV",
            terms=[{"name": "GMV"}],
        )
        assert out["status"] == "missing_term"
        assert out["route_payload"]["kind"] == "term_conflict_missing"
        assert out["route_payload"]["invalid_count"] == 1
        assert "error" in out and "id 或 name" in out["error"]

    def test_status_missing_term_missing_name(self):
        """term 缺 name → missing_term。"""
        out = _sub_agent_no_db().resolve_term_conflict(
            question="GMV",
            terms=[{"id": 1}],
        )
        assert out["status"] == "missing_term"

    def test_should_retry_false_on_missing(self):
        """missing_term → should_retry=False（错误早退）。"""
        out = _sub_agent_no_db().resolve_term_conflict(
            question="x",
            terms=[{"name": "x"}],
        )
        assert out["should_retry"] is False

    def test_route_payload_kind_consistency_with_status(self):
        """route_payload.kind 与 status 严格一致（4 状态机分支）。"""
        # not_applicable
        out = _sub_agent_no_db().resolve_term_conflict(question="x", terms=[])
        assert out["route_payload"]["kind"] == "not_applicable"
        # resolved
        out = _sub_agent_no_db().resolve_term_conflict(
            question="GMV", terms=[{"id": 1, "name": "GMV"}]
        )
        assert out["route_payload"]["kind"] == "term_conflict_resolved"
        # needs_clarification
        out = _sub_agent_no_db().resolve_term_conflict(
            question="g",
            terms=[
                {"id": 1, "name": "a", "aliases": ["g"]},
                {"id": 2, "name": "b", "aliases": ["g"]},
            ],
        )
        assert out["route_payload"]["kind"] == "term_conflict_clarification"
        # missing_term
        out = _sub_agent_no_db().resolve_term_conflict(
            question="x", terms=[{"name": "x"}]
        )
        assert out["route_payload"]["kind"] == "term_conflict_missing"

    def test_8_field_contract_resolved(self):
        """resolved 分支：返回 dict 必须含 8 字段。"""
        out = _sub_agent_no_db().resolve_term_conflict(
            question="GMV", terms=[{"id": 1, "name": "GMV"}]
        )
        for key in (
            "status", "term_normalization", "selected_term_id",
            "resolved_question", "answer", "error", "should_retry",
            "route_payload",
        ):
            assert key in out, f"missing key: {key}"

    def test_tracer_span_emitted_resolved(self):
        """tracer 传入时 emit span，end_span 输出 status。"""
        tracer = MagicMock()
        span_cm = MagicMock()
        span_cm.__enter__ = MagicMock(return_value=MagicMock())
        span_cm.__exit__ = MagicMock(return_value=False)
        tracer.start_span = MagicMock(return_value=span_cm)

        _sub_agent_no_db().resolve_term_conflict(
            question="GMV",
            terms=[{"id": 1, "name": "GMV"}],
            tracer=tracer,
            trace_context=MagicMock(),
        )
        tracer.start_span.assert_called_once()
        kwargs = tracer.start_span.call_args.kwargs
        assert kwargs["node"] == "term_conflict_resolve"
        assert kwargs["display_name"] == "term_conflict_resolve"

    def test_no_tracer_no_crash(self):
        """tracer=None 时不崩溃，返回结果不变。"""
        out = _sub_agent_no_db().resolve_term_conflict(
            question="GMV",
            terms=[{"id": 1, "name": "GMV"}],
        )
        assert out["status"] == "resolved"


# ============================================================
# Phase 7: resolve_metric 单元测试
# ============================================================


class TestResolveMetric:
    """DatasetSubAgent.resolve_metric 5 分支 + 边界覆盖。"""

    def test_status_not_applicable_when_no_schema(self):
        """无 schema → not_applicable。"""
        out = _sub_agent_no_db().resolve_metric(question="GMV", schema_structured=None)
        assert out["status"] == "not_applicable"
        assert out["route_payload"]["kind"] == "not_applicable"
        assert out["semantic_asset_resolution"]["assets"] == []
        assert out["metric_resolution"]["all_matched"] is True

    def test_status_not_applicable_empty_schema(self):
        """空 schema（无任何资产）→ not_applicable。"""
        out = _sub_agent_no_db().resolve_metric(
            question="GMV",
            schema_structured={
                "metrics": [], "dimensions": [], "terms": [],
                "fields": [], "blueprints": [],
            },
        )
        assert out["status"] == "not_applicable"

    def test_status_resolved_metric_exact(self):
        """metric name 精确命中 → resolved。"""
        out = _sub_agent_no_db().resolve_metric(
            question="GMV",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [], "terms": [], "fields": [], "blueprints": [],
            },
        )
        assert out["status"] == "resolved"
        assert out["route_payload"]["kind"] == "metric_resolve_resolved"
        assert out["selected_metric_id"] == 1
        assert out["resolved_question"] == "GMV"
        assert out["metric_resolution"]["all_matched"] is True
        assert len(out["semantic_asset_resolution"]["metrics"]) == 1

    def test_status_resolved_metric_synonym(self):
        """metric synonym 命中 → resolved, match_type=synonym。"""
        out = _sub_agent_no_db().resolve_metric(
            question="销售额",
            entities={"metrics": ["销售额"]},
            schema_structured={
                "metrics": [
                    {"id": 1, "name": "gmv", "synonyms": ["销售额"]}
                ],
                "dimensions": [], "terms": [], "fields": [], "blueprints": [],
            },
        )
        assert out["status"] == "resolved"
        assert out["semantic_asset_resolution"]["metrics"][0]["match_type"] == "synonym"

    def test_status_needs_clarification_two_close_metrics(self):
        """2 个 metric 置信度接近 → needs_clarification。"""
        out = _sub_agent_no_db().resolve_metric(
            question="GMV",
            schema_structured={
                "metrics": [
                    {"id": 1, "name": "GMV", "synonyms": ["GMV 总额"]},
                    {"id": 2, "name": "GMV 总额", "synonyms": ["GMV"]},
                ],
                "dimensions": [], "terms": [], "fields": [], "blueprints": [],
            },
        )
        assert out["status"] == "needs_clarification"
        assert out["route_payload"]["kind"] == "metric_resolve_clarification"
        assert len(out["semantic_asset_resolution"]["ambiguities"]) >= 1
        assert out["selected_metric_id"] is None

    def test_status_missing_metric_missing_id(self):
        """metric 缺 id → missing_metric 错误早退。"""
        out = _sub_agent_no_db().resolve_metric(
            question="GMV",
            schema_structured={
                "metrics": [{"name": "GMV"}],
                "dimensions": [], "terms": [], "fields": [], "blueprints": [],
            },
        )
        assert out["status"] == "missing_metric"
        assert out["route_payload"]["kind"] == "metric_resolve_missing"
        assert out["route_payload"]["invalid_count"] == 1

    def test_status_missing_metric_missing_name(self):
        """metric 缺 name → missing_metric。"""
        out = _sub_agent_no_db().resolve_metric(
            question="x",
            schema_structured={
                "metrics": [{"id": 1}],
                "dimensions": [], "terms": [], "fields": [], "blueprints": [],
            },
        )
        assert out["status"] == "missing_metric"

    def test_should_retry_false_on_missing(self):
        """missing_metric → should_retry=False（错误早退）。"""
        out = _sub_agent_no_db().resolve_metric(
            question="x",
            schema_structured={
                "metrics": [{"name": "x"}],
                "dimensions": [], "terms": [], "fields": [], "blueprints": [],
            },
        )
        assert out["should_retry"] is False

    def test_term_linked_metric_via_asset_links(self):
        """term 命中后通过 asset_links 扩展到 metric。"""
        out = _sub_agent_no_db().resolve_metric(
            question="成交总额",
            schema_structured={
                "metrics": [{"id": 10, "name": "GMV", "synonyms": ["总成交额"]}],
                "dimensions": [{"id": 20, "name": "订单日期"}],
                "terms": [
                    {
                        "id": 100,
                        "name": "成交总额",
                        "synonyms": ["GMV"],
                        "asset_links": [
                            {"asset_type": "metric", "asset_id": 10},
                            {"asset_type": "dimension", "asset_id": 20},
                        ],
                    }
                ],
                "fields": [],
                "blueprints": [],
            },
        )
        assert out["status"] == "resolved"
        assert len(out["semantic_asset_resolution"]["assets"]) >= 2
        asset_types = {a["asset_type"] for a in out["semantic_asset_resolution"]["assets"]}
        assert {"term", "metric", "dimension"} <= asset_types

    def test_field_label_resolution(self):
        """field 中文标注命中 → assets 含 field。"""
        out = _sub_agent_no_db().resolve_metric(
            question="查询人员姓名明细",
            schema_structured={
                "metrics": [], "dimensions": [], "terms": [],
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

    def test_dimension_ambiguity(self):
        """2 个 dimension 名称接近 → ambiguities。"""
        out = _sub_agent_no_db().resolve_metric(
            question="查询地区",
            entities={"dimensions": ["地区"]},
            schema_structured={
                "metrics": [],
                "dimensions": [
                    {"id": 1, "name": "region", "display_name": "地区"},
                    {"id": 2, "name": "area", "display_name": "地区"},
                ],
                "terms": [], "fields": [], "blueprints": [],
            },
        )
        assert out["status"] == "needs_clarification"
        assert {c["asset_id"] for c in out["semantic_asset_resolution"]["ambiguities"][0]["candidates"]} == {1, 2}

    def test_route_payload_kind_consistency(self):
        """route_payload.kind 与 status 严格一致。"""
        # not_applicable
        out = _sub_agent_no_db().resolve_metric(question="x", schema_structured=None)
        assert out["route_payload"]["kind"] == "not_applicable"
        # resolved
        out = _sub_agent_no_db().resolve_metric(
            question="GMV",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [], "terms": [], "fields": [], "blueprints": [],
            },
        )
        assert out["route_payload"]["kind"] == "metric_resolve_resolved"
        # needs_clarification
        out = _sub_agent_no_db().resolve_metric(
            question="GMV",
            schema_structured={
                "metrics": [
                    {"id": 1, "name": "GMV", "synonyms": ["GMV 总额"]},
                    {"id": 2, "name": "GMV 总额", "synonyms": ["GMV"]},
                ],
                "dimensions": [], "terms": [], "fields": [], "blueprints": [],
            },
        )
        assert out["route_payload"]["kind"] == "metric_resolve_clarification"
        # missing_metric
        out = _sub_agent_no_db().resolve_metric(
            question="x",
            schema_structured={
                "metrics": [{"name": "x"}],
                "dimensions": [], "terms": [], "fields": [], "blueprints": [],
            },
        )
        assert out["route_payload"]["kind"] == "metric_resolve_missing"

    def test_9_field_contract_resolved(self):
        """resolved 分支：返回 dict 必须含 9 字段。"""
        out = _sub_agent_no_db().resolve_metric(
            question="GMV",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [], "terms": [], "fields": [], "blueprints": [],
            },
        )
        for key in (
            "status", "semantic_asset_resolution", "metric_resolution",
            "selected_metric_id", "resolved_question", "answer",
            "error", "should_retry", "route_payload",
        ):
            assert key in out, f"missing key: {key}"

    def test_tracer_span_emitted_resolved(self):
        """tracer 传入时 emit span。"""
        tracer = MagicMock()
        span_cm = MagicMock()
        span_cm.__enter__ = MagicMock(return_value=MagicMock())
        span_cm.__exit__ = MagicMock(return_value=False)
        tracer.start_span = MagicMock(return_value=span_cm)

        _sub_agent_no_db().resolve_metric(
            question="GMV",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [], "terms": [], "fields": [], "blueprints": [],
            },
            tracer=tracer,
            trace_context=MagicMock(),
        )
        tracer.start_span.assert_called_once()
        kwargs = tracer.start_span.call_args.kwargs
        assert kwargs["node"] == "metric_resolve"
        assert kwargs["display_name"] == "metric_resolve"

    def test_no_tracer_no_crash(self):
        """tracer=None 时不崩溃。"""
        out = _sub_agent_no_db().resolve_metric(
            question="GMV",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [], "terms": [], "fields": [], "blueprints": [],
            },
        )
        assert out["status"] == "resolved"
