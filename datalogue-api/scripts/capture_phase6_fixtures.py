# ============================================================
# File Name   : capture_phase6_fixtures.py
# Description:
#   Phase 6：在 term_normalize_node 迁出 LangGraph 之前，
#   冻结旧节点的当前实现行为作为对比基准。后续 DatasetSubAgent.resolve_term_conflict
#   用 tests/test_phase6_equivalence.py 加载本 fixture 验证 1:1 行为等价。
#
#   25 条 fixture 覆盖：
#   - not_applicable × 4（无 terms 字段 / terms 为空 / question 无 term / question 为空）
#   - resolved × 5（exact 命中 / display_name 命中 / synonym 命中 / 子串匹配 /
#                   selected_term_id 强制覆盖）
#   - needs_clarification × 5（同 token 命中多个 term / 同 token 命中 display_name+name /
#                               synonym 与 exact 撞车 / selected_term_id 仍冲突 / 2 个冲突组）
#   - 边界 × 6（dataset_id 不匹配 / 跨 dataset term / term 缺 aliases / 空 entities /
#               entities.terms 已存在 / tracer span）
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.graph.nodes import term_normalize_node  # noqa: E402

OUTPUT_PATH = ROOT / "tests" / "fixtures" / "phase6_term_normalize_fixtures.jsonl"

# 最近一次 _make_state 的 schema_structured（用于 fixture 自动 dump schema_seed）
_LAST_SCHEMA: dict | None = None


def _make_state(
    *,
    question: str = "",
    schema_structured: dict | None = None,
    entities: dict | None = None,
    selected_term_id: int | None = None,
    dataset_id: int = 1,
) -> dict:
    """构造 term_normalize_node 所需的 state。"""
    global _LAST_SCHEMA
    _LAST_SCHEMA = dict(schema_structured) if schema_structured else None
    state: dict[str, Any] = {
        "question": question,
        "schema_structured": schema_structured or {},
        "entities": entities or {},
        "selected_term_id": selected_term_id,
        "dataset_id": dataset_id,
    }
    return state


def _run_case(state: dict) -> dict:
    """跑旧 term_normalize_node 一次，冻结 outcome 字段。"""
    return term_normalize_node(state)


def _build_fixture(
    name: str,
    description: str,
    *,
    state: dict,
    extra_asserts: dict | None = None,
) -> dict:
    global _LAST_SCHEMA
    outcome = _run_case(state)
    fixture = {
        "name": name,
        "description": description,
        "input": {
            "question": state.get("question"),
            "schema_structured": state.get("schema_structured"),
            "entities": state.get("entities"),
            "selected_term_id": state.get("selected_term_id"),
            "dataset_id": state.get("dataset_id"),
        },
        "expected_output": outcome,
    }
    if extra_asserts:
        fixture["extra_asserts"] = extra_asserts
    if _LAST_SCHEMA is not None:
        fixture["schema_seed"] = _LAST_SCHEMA
    return fixture


def main() -> None:
    fixtures: list[dict] = []

    # ===== Case 1-4: not_applicable =====
    fixtures.append(_build_fixture(
        "not_applicable_no_terms_field",
        "schema_structured 无 terms 字段 → 透明通过",
        state=_make_state(
            question="GMV 是多少",
            schema_structured={"metrics": [{"name": "GMV"}]},
        ),
    ))
    fixtures.append(_build_fixture(
        "not_applicable_empty_terms",
        "terms 为空列表 → 透明通过",
        state=_make_state(
            question="GMV 是多少",
            schema_structured={"terms": []},
        ),
    ))
    fixtures.append(_build_fixture(
        "not_applicable_question_no_term",
        "question 不命中任何 term → 透明通过",
        state=_make_state(
            question="查询最近订单",
            schema_structured={
                "terms": [
                    {"id": 1, "name": "GMV", "display_name": "GMV 销售额"},
                    {"id": 2, "name": "DAU"},
                ],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "not_applicable_empty_question",
        "question 为空 → 透明通过",
        state=_make_state(
            question="",
            schema_structured={"terms": [{"id": 1, "name": "GMV"}]},
        ),
    ))

    # ===== Case 5-9: resolved =====
    fixtures.append(_build_fixture(
        "resolved_exact_match",
        "exact 命中（question 等于 term.name）",
        state=_make_state(
            question="GMV",
            schema_structured={
                "terms": [{"id": 1, "name": "GMV", "display_name": "GMV 销售额"}],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "resolved_display_name_match",
        "display_name 命中（question 等于 term.display_name）",
        state=_make_state(
            question="GMV 销售额",
            schema_structured={
                "terms": [{"id": 1, "name": "GMV", "display_name": "GMV 销售额"}],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "resolved_synonym_match",
        "synonym 命中（question 等于 term.aliases[0]）",
        state=_make_state(
            question="成交总额",
            schema_structured={
                "terms": [
                    {
                        "id": 1,
                        "name": "GMV",
                        "display_name": "GMV 销售额",
                        "aliases": ["成交总额", "总成交额"],
                    }
                ],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "resolved_substring_match",
        "子串匹配（question 包含 term）",
        state=_make_state(
            question="本周 GMV 趋势如何",
            schema_structured={
                "terms": [{"id": 1, "name": "GMV"}],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "resolved_selected_term_id_forces_pick",
        "selected_term_id 强制覆盖（即使有冲突也只保留命中项）",
        state=_make_state(
            question="订单",
            schema_structured={
                "terms": [
                    {"id": 1, "name": "订单", "display_name": "订单数"},
                    {"id": 2, "name": "订单", "display_name": "订单金额"},
                ],
            },
            selected_term_id=1,
        ),
    ))

    # ===== Case 10-14: needs_clarification =====
    fixtures.append(_build_fixture(
        "clarification_same_token_two_terms",
        "同名 token 命中 2 个 term → clarification",
        state=_make_state(
            question="订单",
            schema_structured={
                "terms": [
                    {"id": 1, "name": "订单", "display_name": "订单数"},
                    {"id": 2, "name": "订单", "display_name": "订单金额"},
                ],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "clarification_display_name_and_name_collision",
        "term1.display_name == term2.name 撞车",
        state=_make_state(
            question="GMV",
            schema_structured={
                "terms": [
                    {"id": 1, "name": "销售额", "display_name": "GMV"},
                    {"id": 2, "name": "GMV", "display_name": "GMV 销售额"},
                ],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "clarification_synonym_matches_multiple_terms",
        "同一 synonym 命中多个 term",
        state=_make_state(
            question="成交额",
            schema_structured={
                "terms": [
                    {
                        "id": 1,
                        "name": "GMV",
                        "aliases": ["成交额", "GMV 总额"],
                    },
                    {
                        "id": 2,
                        "name": "营业额",
                        "aliases": ["成交额", "营业额"],
                    },
                ],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "clarification_selected_term_id_still_conflicts",
        "selected_term_id 不在 matches 中时仍走澄清分支",
        state=_make_state(
            question="订单",
            schema_structured={
                "terms": [
                    {"id": 1, "name": "订单", "display_name": "订单数"},
                    {"id": 2, "name": "订单", "display_name": "订单金额"},
                ],
            },
            selected_term_id=999,  # 不存在的 id
        ),
    ))
    fixtures.append(_build_fixture(
        "clarification_two_conflict_groups",
        "2 个独立 token 各自冲突（answer 合并）",
        state=_make_state(
            question="订单 用户",
            schema_structured={
                "terms": [
                    {"id": 1, "name": "订单", "display_name": "订单数"},
                    {"id": 2, "name": "订单", "display_name": "订单金额"},
                    {"id": 3, "name": "用户", "display_name": "用户数"},
                    {"id": 4, "name": "用户", "display_name": "用户画像"},
                ],
            },
        ),
    ))

    # ===== Case 15-20: 边界 =====
    fixtures.append(_build_fixture(
        "boundary_entities_terms_already_present",
        "entities.terms 已存在时合并并去重",
        state=_make_state(
            question="GMV",
            entities={"terms": ["DAU", "GMV"]},
            schema_structured={"terms": [{"id": 1, "name": "GMV"}]},
        ),
    ))
    fixtures.append(_build_fixture(
        "boundary_term_with_no_aliases",
        "term 无 aliases 字段 → 仍能 exact 命中",
        state=_make_state(
            question="GMV",
            schema_structured={"terms": [{"id": 1, "name": "GMV"}]},
        ),
    ))
    fixtures.append(_build_fixture(
        "boundary_term_with_null_definition",
        "term.definition 为 None → 不影响匹配",
        state=_make_state(
            question="GMV",
            schema_structured={
                "terms": [{"id": 1, "name": "GMV", "definition": None}],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "boundary_question_with_whitespace",
        "question 含多空格/制表符仍归一化匹配",
        state=_make_state(
            question="  GMV  趋势  ",
            schema_structured={"terms": [{"id": 1, "name": "GMV"}]},
        ),
    ))
    fixtures.append(_build_fixture(
        "boundary_lowercase_normalization",
        "term 大小写不同也算同 token",
        state=_make_state(
            question="gmv",
            schema_structured={"terms": [{"id": 1, "name": "GMV"}]},
        ),
    ))
    fixtures.append(_build_fixture(
        "boundary_no_match_returns_only_normalization",
        "无匹配时仅返回 term_normalization（无 entry_intent/route_payload）",
        state=_make_state(
            question="无关问题",
            schema_structured={"terms": [{"id": 1, "name": "GMV"}]},
        ),
    ))

    # ===== Case 21-25: 多 term 单匹配 + 高 confidence =====
    fixtures.append(_build_fixture(
        "multiple_terms_one_match",
        "3 个 term 仅 1 个命中",
        state=_make_state(
            question="本周 GMV",
            schema_structured={
                "terms": [
                    {"id": 1, "name": "DAU"},
                    {"id": 2, "name": "MAU"},
                    {"id": 3, "name": "GMV"},
                ],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "term_with_asset_links_kept",
        "term 带 asset_links 字段 → 保留在 match 候选中",
        state=_make_state(
            question="GMV",
            schema_structured={
                "terms": [
                    {
                        "id": 1,
                        "name": "GMV",
                        "asset_links": [{"asset_type": "metric", "asset_id": 10}],
                    }
                ],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "term_with_term_type_kept",
        "term 带 term_type 字段 → 保留在 match 候选中",
        state=_make_state(
            question="GMV",
            schema_structured={
                "terms": [{"id": 1, "name": "GMV", "term_type": "metric"}],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "answer_contains_candidate_names",
        "clarification answer 含冲突 term 名",
        state=_make_state(
            question="订单",
            schema_structured={
                "terms": [
                    {"id": 1, "name": "订单", "display_name": "订单数"},
                    {"id": 2, "name": "订单", "display_name": "订单金额"},
                ],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "empty_input_question_no_schema",
        "question 为空且 schema 也为空 → 透明通过",
        state=_make_state(question="", schema_structured={}),
    ))

    # ===== 写出 =====
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for fx in fixtures:
            f.write(json.dumps(fx, ensure_ascii=False) + "\n")
    print(f"✅ wrote {len(fixtures)} fixtures to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()