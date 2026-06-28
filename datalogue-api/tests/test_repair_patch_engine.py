# ============================================================
# File Name   : test_repair_patch_engine.py
# Description:
#   RepairPatch Engine PR1 离线内核测试。
#
# Responsibilities:
#   - 验证字段候选、置信度、Tool 校验和 patch apply 的核心契约。
#   - 确认 PR1 不生成 SQL、不接主链，用户摘要不泄露字段/schema/SQL。
#
# Author      : yangkai
# Created On  : 2026-06-28
# ============================================================

from __future__ import annotations

import copy
import json

import pytest

from app.models.dataset import (
    DatasetSourceTable,
    SemanticDataset,
    SemanticDimension,
    SourceColumn,
    SourceTable,
)
from app.services.repair_patch import (
    MockSemanticJudge,
    RepairPatch,
    RepairPatchValidation,
    RepairPatchValidationError,
    apply_repair_patch,
    build_repair_patch,
    build_semantic_judge_prompt_input,
    collect_field_candidates,
    merge_confidence,
    normalize_coarse_type,
    sanitize_repair_patch_summary,
    validate_repair_patch,
)


def _selected_table(db_session, dataset, *, table_name="work_log"):
    table = SourceTable(
        datasource_id=dataset.datasource_id,
        schema_name="public",
        table_name=table_name,
        table_comment="工作日志明细",
    )
    db_session.add(table)
    db_session.flush()
    columns = [
        SourceColumn(
            table_id=table.id,
            column_name="work_date",
            data_type="date",
            column_comment="工作日期",
            effective_desc="员工工作日志日期",
            user_semantic_role="time",
            review_status="published",
        ),
        SourceColumn(
            table_id=table.id,
            column_name="person_name",
            data_type="varchar",
            column_comment="人员姓名",
            effective_desc="员工姓名",
            user_semantic_role="person",
            review_status="published",
        ),
    ]
    db_session.add_all(columns)
    db_session.add(DatasetSourceTable(dataset_id=dataset.id, source_table_id=table.id))
    db_session.commit()
    return table


def test_collect_field_candidates_prefers_semantic_assets_then_selected_columns(db_session, sample_dataset):
    _selected_table(db_session, sample_dataset)
    db_session.add(
        SemanticDimension(
            dataset_id=sample_dataset.id,
            name="work_date",
            display_name="工作日期",
            column_name="work_log.work_date",
            table_name="work_log",
            synonyms=["日志日期"],
        )
    )
    db_session.commit()

    candidates = collect_field_candidates(
        db_session,
        dataset_id=sample_dataset.id,
        failed_field_intent_summary="工作日志日期",
    )

    assert candidates[0].source == "semantic_asset"
    assert candidates[0].business_name == "工作日期"
    assert candidates[0].column_name == "work_date"
    assert {item.column_name for item in candidates} == {"work_date", "person_name"}
    assert all(item.dataset_id == sample_dataset.id for item in candidates)


def test_collect_field_candidates_uses_only_selected_columns(db_session, sample_dataset, sample_datasource):
    _selected_table(db_session, sample_dataset, table_name="selected_table")
    unselected = SourceTable(
        datasource_id=sample_datasource.id,
        schema_name="public",
        table_name="hidden_table",
    )
    db_session.add(unselected)
    db_session.flush()
    db_session.add(
        SourceColumn(
            table_id=unselected.id,
            column_name="secret_col",
            data_type="varchar",
            column_comment="不应被读取的字段",
        )
    )
    db_session.commit()

    candidates = collect_field_candidates(
        db_session,
        dataset_id=sample_dataset.id,
        failed_field_intent_summary="人员姓名",
    )

    assert {item.table_name for item in candidates} == {"selected_table"}
    assert "secret_col" not in {item.column_name for item in candidates}


def test_prompt_input_and_summary_hide_physical_fields_schema_and_sql(db_session, sample_dataset):
    _selected_table(db_session, sample_dataset)
    candidate = collect_field_candidates(
        db_session,
        dataset_id=sample_dataset.id,
        failed_field_intent_summary="工作日期",
    )[0]

    prompt_input = build_semantic_judge_prompt_input(
        question_intent_summary="查询某员工 2024 年工作日志",
        failed_field_intent_summary="工作日期",
        candidate=candidate,
    )
    rendered_prompt = json.dumps(prompt_input, ensure_ascii=False).lower()
    assert "work_date" not in rendered_prompt
    assert "work_log" not in rendered_prompt
    assert "select" not in rendered_prompt
    assert prompt_input["candidate_business_name"] == candidate.business_name

    patch = build_repair_patch(
        patch_type="compiler_binding_patch",
        dataset_id=sample_dataset.id,
        failure_class="FIELD_NOT_FOUND",
        target={"binding_key": "date_field", "field_intent": "工作日期"},
        replacement=candidate,
        rule_score=0.9,
        semantic_judgement={"semantic_equivalent": True, "semantic_score": 0.92},
    )
    summary = sanitize_repair_patch_summary(patch)
    rendered_summary = json.dumps(summary, ensure_ascii=False).lower()
    assert summary["confidence_band"] == "high"
    assert summary["requires_user_confirmation"] is False
    assert "work_date" not in rendered_summary
    assert "work_log" not in rendered_summary
    assert "operations" not in rendered_summary


def test_prompt_input_masks_physical_fallback_when_business_metadata_missing(db_session, sample_dataset):
    _selected_table(db_session, sample_dataset)
    candidate = collect_field_candidates(
        db_session,
        dataset_id=sample_dataset.id,
        failed_field_intent_summary="人员姓名",
    )[1].model_copy(
        update={
            "business_name": "person_name",
            "business_description": "use work_log.person_name",
        }
    )

    prompt_input = build_semantic_judge_prompt_input(
        question_intent_summary="查询某员工 2024 年工作日志",
        failed_field_intent_summary="人员姓名",
        candidate=candidate,
    )
    rendered_prompt = json.dumps(prompt_input, ensure_ascii=False).lower()

    assert "person_name" not in rendered_prompt
    assert "work_log" not in rendered_prompt
    assert prompt_input["candidate_business_name"] == "当前数据集候选字段"
    assert prompt_input["candidate_business_description"] == "当前数据集候选字段"


def test_sanitize_repair_patch_summary_masks_validation_leaks(db_session, sample_dataset):
    _selected_table(db_session, sample_dataset)
    candidate = collect_field_candidates(
        db_session,
        dataset_id=sample_dataset.id,
        failed_field_intent_summary="工作日期",
    )[0]
    patch = build_repair_patch(
        patch_type="compiler_binding_patch",
        dataset_id=sample_dataset.id,
        failure_class="FIELD_NOT_FOUND",
        target={"binding_key": "date_field", "field_intent": "工作日期"},
        replacement=candidate,
        rule_score=0.9,
        semantic_judgement={"semantic_equivalent": True, "semantic_score": 0.92},
    ).model_copy(
        update={
            "validation": RepairPatchValidation(
                summary="SELECT * FROM work_log，schema=public",
                risk_flags=["needs_confirmation", "schema", "RAW SQL detail"],
            )
        }
    )

    summary = sanitize_repair_patch_summary(patch)
    rendered_summary = json.dumps(summary, ensure_ascii=False).lower()

    assert summary["validation_summary"] == "修复方案已通过工具校验。"
    assert summary["risk_flags"] == ["needs_confirmation"]
    assert "select" not in rendered_summary
    assert "schema=public" not in rendered_summary
    assert "work_log" not in rendered_summary


def test_repair_patch_semantic_judge_prompt_template_declares_public_boundary():
    from app.prompts.repair_patch import REPAIR_PLAN_FIELD_SEMANTIC_JUDGE_PROMPT_NAME, REPAIR_PLAN_FIELD_SEMANTIC_JUDGE_SYSTEM

    assert REPAIR_PLAN_FIELD_SEMANTIC_JUDGE_PROMPT_NAME == "repair_plan_field_semantic_judge"
    prompt = REPAIR_PLAN_FIELD_SEMANTIC_JUDGE_SYSTEM
    assert "只输出 JSON" in prompt
    assert "不要输出 SQL" in prompt
    assert "物理字段名" in prompt
    assert "schema" in prompt.lower()


def test_merge_confidence_bands_and_mock_judge():
    high = merge_confidence(
        rule_score=0.92,
        semantic_judgement={"semantic_equivalent": True, "semantic_score": 0.94},
        hard_constraints_ok=True,
        type_compatible=True,
    )
    medium = merge_confidence(
        rule_score=0.55,
        semantic_judgement={"semantic_equivalent": True, "semantic_score": 0.95},
        hard_constraints_ok=True,
        type_compatible=True,
    )
    blocked = merge_confidence(
        rule_score=0.99,
        semantic_judgement={"semantic_equivalent": True, "semantic_score": 0.99},
        hard_constraints_ok=False,
        type_compatible=True,
    )

    assert high == {"confidence": 0.93, "confidence_band": "high", "requires_user_confirmation": False}
    assert medium["confidence_band"] == "medium"
    assert medium["requires_user_confirmation"] is True
    assert blocked == {"confidence": 0.0, "confidence_band": "blocked", "requires_user_confirmation": False}
    assert merge_confidence(
        rule_score=1.5,
        semantic_judgement={"semantic_equivalent": True, "semantic_score": 2},
        hard_constraints_ok=True,
        type_compatible=True,
    ) == {"confidence": 1.0, "confidence_band": "high", "requires_user_confirmation": False}
    assert MockSemanticJudge(score=0.77).judge({})["semantic_score"] == 0.77


@pytest.mark.parametrize(
    ("data_type", "expected"),
    [
        ("varchar", "text_like"),
        ("timestamp", "date_like"),
        ("decimal", "number_like"),
        ("bool", "boolean_like"),
        ("enum", "enum_like"),
        ("jsonb", "unknown"),
    ],
)
def test_normalize_coarse_type(data_type, expected):
    assert normalize_coarse_type(data_type) == expected


def test_validate_repair_patch_rejects_sql_cross_dataset_and_type_conflict(db_session, sample_dataset, sample_datasource):
    _selected_table(db_session, sample_dataset)
    candidate = collect_field_candidates(
        db_session,
        dataset_id=sample_dataset.id,
        failed_field_intent_summary="工作日期",
    )[0]
    patch = build_repair_patch(
        patch_type="query_graph_patch",
        dataset_id=sample_dataset.id,
        failure_class="FIELD_NOT_FOUND",
        target={"target_path": ["filters", 0, "field"], "field_intent": "工作日期"},
        replacement=candidate,
        rule_score=0.9,
        semantic_judgement={"semantic_equivalent": True, "semantic_score": 0.9},
    )

    assert validate_repair_patch(patch, candidates=[candidate], dataset_id=sample_dataset.id) is patch

    with pytest.raises(RepairPatchValidationError):
        validate_repair_patch(
            patch.model_copy(update={"dataset_id": sample_dataset.id + 999}),
            candidates=[candidate],
            dataset_id=sample_dataset.id,
        )

    with pytest.raises(RepairPatchValidationError):
        validate_repair_patch(
            patch.model_copy(update={"trace_only_metadata": {"raw_sql": "SELECT * FROM work_log"}}),
            candidates=[candidate],
            dataset_id=sample_dataset.id,
        )

    other_dataset = SemanticDataset(
        name="其他数据集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": []},
        status="active",
    )
    db_session.add(other_dataset)
    db_session.commit()
    cross = candidate.model_copy(update={"dataset_id": other_dataset.id})
    with pytest.raises(RepairPatchValidationError):
        validate_repair_patch(
            patch.model_copy(update={"dataset_id": other_dataset.id}),
            candidates=[cross],
            dataset_id=sample_dataset.id,
        )

    incompatible = candidate.model_copy(update={"coarse_type": "number_like"})
    with pytest.raises(RepairPatchValidationError):
        validate_repair_patch(
            patch,
            candidates=[incompatible],
            dataset_id=sample_dataset.id,
            expected_type_group="text_like",
        )


def test_apply_query_graph_patch_is_pure_and_returns_safe_diff(db_session, sample_dataset):
    _selected_table(db_session, sample_dataset)
    candidate = collect_field_candidates(
        db_session,
        dataset_id=sample_dataset.id,
        failed_field_intent_summary="工作日期",
    )[0]
    patch = build_repair_patch(
        patch_type="query_graph_patch",
        dataset_id=sample_dataset.id,
        failure_class="FIELD_NOT_FOUND",
        target={"target_path": ["filters", 0, "field"], "field_intent": "工作日期"},
        replacement=candidate,
        rule_score=0.9,
        semantic_judgement={"semantic_equivalent": True, "semantic_score": 0.9},
    )
    original = {"filters": [{"field": "missing_date"}], "select": ["person_name"]}
    before = copy.deepcopy(original)

    result = apply_repair_patch(original, patch)

    assert original == before
    assert result.patched_copy["filters"][0]["field"] == "work_log.work_date"
    assert result.diff_summary == {"summary": "已按业务口径替换 1 处字段引用。", "operation_count": 1}
    assert result.trace_only_details["operations"][0]["replacement_field_ref"] == "work_log.work_date"
    assert "work_log" not in json.dumps(result.diff_summary, ensure_ascii=False)


def test_apply_compiler_binding_patch_and_missing_target_fail_closed(db_session, sample_dataset):
    _selected_table(db_session, sample_dataset)
    candidate = collect_field_candidates(
        db_session,
        dataset_id=sample_dataset.id,
        failed_field_intent_summary="工作日期",
    )[0]
    patch = build_repair_patch(
        patch_type="compiler_binding_patch",
        dataset_id=sample_dataset.id,
        failure_class="FIELD_NOT_FOUND",
        target={"binding_key": "date_field", "field_intent": "工作日期"},
        replacement=candidate,
        rule_score=0.9,
        semantic_judgement={"semantic_equivalent": True, "semantic_score": 0.9},
    )
    binding = {"bindings": {"date_field": "missing_date", "person_field": "person_name"}}

    result = apply_repair_patch(binding, patch)

    assert binding["bindings"]["date_field"] == "missing_date"
    assert result.patched_copy["bindings"]["date_field"] == "work_log.work_date"

    missing = patch.model_copy(
        update={
            "operations": [
                patch.operations[0].model_copy(update={"binding_key": "not_exists"})
            ]
        }
    )
    with pytest.raises(RepairPatchValidationError):
        apply_repair_patch(binding, missing)
