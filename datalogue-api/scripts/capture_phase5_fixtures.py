# ============================================================
# File Name   : capture_phase5_fixtures.py
# Description:
#   Phase 5：在 analysis_blueprint_execute_node 迁出 LangGraph 之前，
#   冻结旧节点的当前实现行为作为对比基准。后续 DatasetSubAgent.resolve_analysis_blueprint
#   用 tests/test_phase5_equivalence.py 加载本 fixture 验证 1:1 行为等价。
#
#   25 条 fixture 覆盖：
#   - not_applicable × 2（无 blueprint_id / entry_route 错）
#   - not_found × 2（blueprint 不存在 / 跨 dataset）
#   - semantic_plan × 2（基础 / 带 question）
#   - executed × 5（成功 / time_context / route_payload / execution_time / sql_list 格式）
#   - clarification × 3（缺参 / original_question / missing 字段）
#   - error × 4（SQL 失败 / 不 active / 跨 dataset / route_payload kind）
#   - 边界 × 5（无 time_context / semantic_plan 无 sql / count_usage / not_found 早退 / safe_sql 验证）
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.database import Base  # noqa: E402
from app.core.security import encrypt_password  # noqa: E402
from app.graph.nodes import analysis_blueprint_execute_node  # noqa: E402
from app.models.datasource import Datasource  # noqa: E402
from app.models.dataset import AnalysisBlueprint, SemanticDataset  # noqa: E402

OUTPUT_PATH = ROOT / "tests" / "fixtures" / "phase5_analysis_blueprint_fixtures.jsonl"

# 最近一次 _make_blueprint 的种子字段（用于 _build_fixture 自动 dump 到 blueprint_seed）
_LAST_BLUEPRINT_SEED: dict | None = None


def _make_db_and_dataset(dataset_id: int = 1, ds_db_path: str | None = None):
    """构造 in-memory ORM session + 临时文件 SQLite 数据源。"""
    global _LAST_BLUEPRINT_SEED
    _LAST_BLUEPRINT_SEED = None  # 新 session 时清空
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    ds_db_path = ds_db_path or ":memory:"
    datasource = Datasource(
        id=1,
        name="bp-test-ds",
        db_type="sqlite",
        host="",
        port=0,
        database_name=ds_db_path,
        username="",
        password_enc=encrypt_password("test"),
    )
    session.add(datasource)
    session.commit()
    session.refresh(datasource)

    dataset = SemanticDataset(
        id=dataset_id,
        name="bp-test-dataset",
        datasource_id=datasource.id,
        status="active",
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)

    return engine, session, dataset


def _make_blueprint(
    session,
    dataset_id: int,
    *,
    bp_id: int,
    name: str,
    status: str = "active",
    implementation_type: str = "stored_procedure",
    call_template: str | None = None,
    raw_sql: str | None = None,
    parameters: list | None = None,
    output_schema: list | None = None,
    steps: list | None = None,
    description: str | None = None,
    when_to_use: str | None = None,
) -> AnalysisBlueprint:
    global _LAST_BLUEPRINT_SEED
    _LAST_BLUEPRINT_SEED = {
        "id": bp_id,
        "dataset_id": dataset_id,
        "name": name,
        "status": status,
        "implementation_type": implementation_type,
        "call_template": call_template,
        "raw_sql": raw_sql,
        "parameters": parameters or [],
        "output_schema": output_schema or [],
        "steps": steps or [],
        "description": description,
        "when_to_use": when_to_use,
    }
    bp = AnalysisBlueprint(
        id=bp_id,
        dataset_id=dataset_id,
        name=name,
        status=status,
        implementation_type=implementation_type,
        call_template=call_template,
        raw_sql=raw_sql,
        parameters=parameters or [],
        output_schema=output_schema or [],
        steps=steps or [],
        description=description,
        when_to_use=when_to_use,
    )
    session.add(bp)
    session.commit()
    session.refresh(bp)
    return bp


def _run_case(session, state: dict) -> dict:
    """跑旧 analysis_blueprint_execute_node 一次，冻结 outcome 字段。"""
    node = analysis_blueprint_execute_node(session)
    return node(state)


def _build_fixture(
    name: str,
    description: str,
    *,
    session,
    state: dict,
    extra_asserts: dict | None = None,
    blueprint_seed: dict | None = None,
) -> dict:
    global _LAST_BLUEPRINT_SEED
    outcome = _run_case(session, state)
    fixture = {
        "name": name,
        "description": description,
        "input": {
            "question": state.get("question"),
            "entry_route": state.get("entry_route"),
            "dataset_id": state.get("dataset_id"),
            "blueprint_id": state.get("blueprint_id"),
            "original_question": state.get("original_question"),
            "resolved_question": state.get("resolved_question"),
            "time_context": state.get("time_context"),
        },
        "expected_output": outcome,
    }
    if extra_asserts:
        fixture["extra_asserts"] = extra_asserts
    # 自动捕获最近一次 _make_blueprint 的种子（同 session 内粘性，新 session 由 _make_db_and_dataset 重置）
    if blueprint_seed is None and _LAST_BLUEPRINT_SEED is not None:
        fixture["blueprint_seed"] = dict(_LAST_BLUEPRINT_SEED)
    elif blueprint_seed is not None:
        fixture["blueprint_seed"] = blueprint_seed
    return fixture


def main() -> None:
    fixtures: list[dict] = []
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()

    try:
        # ===== Case 1-2: not_applicable =====
        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        fixtures.append(_build_fixture(
            "not_applicable_no_blueprint_id",
            "无 blueprint_id 时节点透明通过",
            session=session,
            state={
                "question": "随便问",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": None,
            },
        ))
        fixtures.append(_build_fixture(
            "not_applicable_entry_route_mismatch",
            "entry_route != analysis_blueprint 时节点不执行",
            session=session,
            state={
                "question": "销售额是多少",
                "entry_route": "query_graph",
                "dataset_id": dataset.id,
                "blueprint_id": 10,  # 蓝图存在但 entry_route 错
            },
        ))
        session.close()
        engine.dispose()

        # ===== Case 3-4: not_found =====
        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        fixtures.append(_build_fixture(
            "not_found_blueprint_id_not_exist",
            "blueprint_id 查无记录",
            session=session,
            state={
                "question": "查最近 GMV",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 999,
            },
        ))

        # 跨 dataset 的 blueprint（dataset_id=2，但当前 dataset_id=1）
        bp_cross = _make_blueprint(
            session, dataset_id=2,
            bp_id=40, name="跨 dataset 蓝图",
            call_template="SELECT 1 AS n",
        )
        fixtures.append(_build_fixture(
            "not_found_blueprint_dataset_mismatch",
            "蓝图存在但属于其他 dataset",
            session=session,
            state={
                "question": "查 GMV",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": bp_cross.id,
            },
        ))
        session.close()
        engine.dispose()

        # ===== Case 5-6: semantic_plan =====
        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        _make_blueprint(
            session, dataset_id=dataset.id,
            bp_id=20, name="GMV 趋势分析",
            implementation_type="semantic_plan",
            description="分析 GMV 趋势",
            when_to_use="用户问 GMV 走势时",
            parameters=[{"name": "time_range", "type": "date", "required": True}],
            output_schema=[{"column": "month", "semantic": "月份"}],
            steps=[{"name": "统计每月 GMV"}],
        )
        fixtures.append(_build_fixture(
            "semantic_plan_basic",
            "manual semantic_plan 蓝图转入 QueryGraph",
            session=session,
            state={
                "question": "GMV 趋势",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 20,
            },
        ))
        fixtures.append(_build_fixture(
            "semantic_plan_with_question",
            "semantic_plan 蓝图带 question + time_context",
            session=session,
            state={
                "question": "过去 30 天 GMV 走势",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 20,
                "original_question": "GMV 走势",
                "resolved_question": "过去 30 天 GMV 走势",
                "time_context": {"detected_time_range": {"start_date": "2026-05-01", "end_date": "2026-05-31"}},
            },
        ))
        session.close()
        engine.dispose()

        # ===== Case 7-11: executed（SQL 模板执行成功） =====
        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        _make_blueprint(
            session, dataset_id=dataset.id,
            bp_id=10, name="GMV 概览",
            call_template="SELECT 1 AS value, 'GMV' AS name",
            output_schema=[{"column": "value", "semantic": "数值"}],
        )
        fixtures.append(_build_fixture(
            "executed_sql_template_success",
            "SQL 模板蓝图执行成功（带 SELECT 1）",
            session=session,
            state={
                "question": "GMV 是多少",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 10,
            },
            extra_asserts={"status_shape_check": "executed_or_error"},
        ))
        bp_10 = session.get(AnalysisBlueprint, 10)
        bp_10.usage_count = 0
        session.commit()

        fixtures.append(_build_fixture(
            "executed_sql_template_with_time_context",
            "SQL 模板带 time_context（不影响 select 1）",
            session=session,
            state={
                "question": "GMV",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 10,
                "time_context": {"detected_time_range": {"start_date": "2026-05-01", "end_date": "2026-05-31"}},
            },
        ))
        fixtures.append(_build_fixture(
            "executed_route_payload_full",
            "验证 executed 路线 route_payload 完整字段",
            session=session,
            state={
                "question": "GMV",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 10,
            },
            extra_asserts={"required_route_payload_keys": ["kind", "blueprint_id", "name", "params", "sql_template", "original_question", "resolved_question", "execution_time_ms"]},
        ))
        fixtures.append(_build_fixture(
            "executed_execution_time_ms_present",
            "executed 路线带 execution_time_ms",
            session=session,
            state={
                "question": "GMV",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 10,
            },
        ))
        fixtures.append(_build_fixture(
            "executed_sql_list_format",
            "executed 路线 sql_list 是 list[str]",
            session=session,
            state={
                "question": "GMV",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 10,
            },
        ))
        session.close()
        engine.dispose()

        # ===== Case 12-14: clarification（缺参） =====
        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        _make_blueprint(
            session, dataset_id=dataset.id,
            bp_id=50, name="订单查询（缺参）",
            call_template="SELECT * FROM orders WHERE order_date BETWEEN :start_date AND :end_date",
            parameters=[
                {"name": "start_date", "type": "date", "required": True},
                {"name": "end_date", "type": "date", "required": True},
            ],
        )
        fixtures.append(_build_fixture(
            "clarification_missing_required_param",
            "缺 start_date / end_date → clarification",
            session=session,
            state={
                "question": "查订单",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 50,
            },
            extra_asserts={"required_route_payload_keys": ["kind", "blueprint_id", "missing", "params", "sql_template", "original_question", "resolved_question"]},
        ))
        fixtures.append(_build_fixture(
            "clarification_uses_original_question",
            "缺参时 route_payload 保留 original_question / resolved_question",
            session=session,
            state={
                "question": "最近一周 GMV",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 50,
                "original_question": "查订单",
                "resolved_question": "最近一周 GMV",
            },
        ))
        fixtures.append(_build_fixture(
            "clarification_missing_field_populated",
            "missing 字段是 list[str]",
            session=session,
            state={
                "question": "查",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 50,
            },
        ))
        session.close()
        engine.dispose()

        # ===== Case 15-18: error =====
        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        _make_blueprint(
            session, dataset_id=dataset.id,
            bp_id=30, name="非 active 蓝图",
            status="draft",
            call_template="SELECT 1",
        )
        fixtures.append(_build_fixture(
            "error_not_active_blueprint",
            "status=draft 时报 NOT_ACTIVE 错误",
            session=session,
            state={
                "question": "GMV",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 30,
            },
            extra_asserts={"required_route_payload_keys": ["kind", "blueprint_id", "params", "sql_template", "original_question", "resolved_question"]},
        ))
        session.close()
        engine.dispose()

        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        _make_blueprint(
            session, dataset_id=dataset.id,
            bp_id=60, name="SQL 语法错",
            call_template="SELECT FROM WHERE BROKEN",
        )
        fixtures.append(_build_fixture(
            "error_sql_execution_failed",
            "SQL 语法错执行失败",
            session=session,
            state={
                "question": "查",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 60,
            },
        ))
        fixtures.append(_build_fixture(
            "error_route_payload_kind",
            "执行失败时 route_payload.kind == analysis_blueprint_error",
            session=session,
            state={
                "question": "查",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 60,
            },
        ))
        fixtures.append(_build_fixture(
            "error_includes_sql_preview",
            "错误分支含 sql preview",
            session=session,
            state={
                "question": "查",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 60,
            },
        ))
        session.close()
        engine.dispose()

        # ===== Case 19-25: 边界 =====
        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        _make_blueprint(
            session, dataset_id=dataset.id,
            bp_id=10, name="GMV 概览",
            call_template="SELECT 1 AS value",
        )
        fixtures.append(_build_fixture(
            "executed_with_no_time_context",
            "executed 路线无 time_context",
            session=session,
            state={
                "question": "GMV",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 10,
            },
        ))
        session.close()
        engine.dispose()

        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        _make_blueprint(
            session, dataset_id=dataset.id,
            bp_id=20, name="语义计划",
            implementation_type="semantic_plan",
        )
        fixtures.append(_build_fixture(
            "semantic_plan_no_sql_executed",
            "semantic_plan 路线 sql_result=None 且 generation_mode=analysis_blueprint_semantic",
            session=session,
            state={
                "question": "查",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 20,
            },
        ))
        session.close()
        engine.dispose()

        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        _make_blueprint(
            session, dataset_id=dataset.id,
            bp_id=10, name="GMV",
            call_template="SELECT 1 AS value",
        )
        bp_before = session.get(AnalysisBlueprint, 10)
        usage_before = bp_before.usage_count
        _run_case(session, {
            "question": "GMV",
            "entry_route": "analysis_blueprint",
            "dataset_id": dataset.id,
            "blueprint_id": 10,
        })
        session.refresh(bp_before)
        fixtures.append(_build_fixture(
            "executed_count_usage_called",
            "executed 路线触发 usage_count 自增",
            session=session,
            state={
                "question": "GMV",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 10,
            },
            extra_asserts={"usage_count_after": bp_before.usage_count, "usage_count_before": usage_before},
        ))
        session.close()
        engine.dispose()

        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        fixtures.append(_build_fixture(
            "not_found_returns_early",
            "not_found 不调 execute_analysis_blueprint",
            session=session,
            state={
                "question": "查",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 888,
            },
        ))
        session.close()
        engine.dispose()

        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        _make_blueprint(
            session, dataset_id=dataset.id,
            bp_id=10, name="GMV 概览",
            call_template="SELECT 1 AS value",
        )
        fixtures.append(_build_fixture(
            "executed_count_usage_increments_by_one",
            "executed 后 usage_count 比执行前多 1",
            session=session,
            state={
                "question": "GMV",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 10,
            },
        ))
        session.close()
        engine.dispose()

        # ===== Case 26: safe_sql 危险语句被 guard 拦截 =====
        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        _make_blueprint(
            session, dataset_id=dataset.id,
            bp_id=70, name="DELETE 蓝图",
            call_template="DELETE FROM orders",
        )
        fixtures.append(_build_fixture(
            "error_sql_unsafe_blocked",
            "非只读 SQL 被 guard 拦截（UNSAFE_SQL）",
            session=session,
            state={
                "question": "删除订单",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 70,
            },
        ))
        session.close()
        engine.dispose()

        # ===== Case 27: semantic_plan blueprint_context 内容校验 =====
        engine, session, dataset = _make_db_and_dataset(dataset_id=1, ds_db_path=tmp_db.name)
        _make_blueprint(
            session, dataset_id=dataset.id,
            bp_id=20, name="GMV 趋势",
            implementation_type="semantic_plan",
            description="分析 GMV 趋势",
            when_to_use="用户问 GMV 时",
            parameters=[{"name": "time_range", "type": "date", "required": True, "default_expr": "last 30 days"}],
            output_schema=[{"column": "month", "semantic": "月份"}],
            steps=[{"name": "按月聚合"}],
        )
        fixtures.append(_build_fixture(
            "semantic_plan_blueprint_context_format",
            "验证 semantic_plan 蓝图 context 文本格式",
            session=session,
            state={
                "question": "GMV 趋势",
                "entry_route": "analysis_blueprint",
                "dataset_id": dataset.id,
                "blueprint_id": 20,
            },
        ))
        session.close()
        engine.dispose()

        # ===== 写出 =====
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_PATH.open("w", encoding="utf-8") as f:
            for fx in fixtures:
                f.write(json.dumps(fx, ensure_ascii=False) + "\n")
        print(f"✅ wrote {len(fixtures)} fixtures to {OUTPUT_PATH}")
    finally:
        Path(tmp_db.name).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
