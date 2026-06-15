# ============================================================
# File Name   : capture_phase7_fixtures.py
# Description:
#   Phase 7：在 semantic_asset_resolution_node 迁出 LangGraph 之前，
#   冻结旧节点的当前实现行为作为对比基准。后续 DatasetSubAgent.resolve_metric
#   用 tests/test_phase7_equivalence.py 加载本 fixture 验证 1:1 行为等价。
#
#   25 条 fixture 覆盖：
#   - not_applicable × 4（无 schema / empty schema / no query terms / entities 为空）
#   - resolved × 7（命中 metric / dimension / field / term / blueprint /
#                   metric+dimension / term link 扩展）
#   - ambiguity × 4（多个 metric 置信度接近 / 多个 dimension / 多个 term /
#                    metric 撞 blueprint）
#   - unresolved × 3（entities.metric 不在 schema / entities.dimension 不在 schema /
#                    未指定 preferred_type）
#   - 边界 × 7（context bias 触发 / preferred_type 加分 / empty entities /
#               trigger_keyword 命中 / trigger_example 命中 / synonym 命中 /
#               metric_resolution 兼容字段）
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

from app.graph.nodes import semantic_asset_resolution_node  # noqa: E402

OUTPUT_PATH = ROOT / "tests" / "fixtures" / "phase7_semantic_asset_fixtures.jsonl"

# 最近一次 _make_state 的 schema_structured（用于 fixture 自动 dump schema_seed）
_LAST_SCHEMA: dict | None = None


def _make_state(
    *,
    question: str = "",
    schema_structured: dict | None = None,
    entities: dict | None = None,
    dataset_id: int = 1,
) -> dict:
    """构造 semantic_asset_resolution_node 所需的 state。"""
    global _LAST_SCHEMA
    _LAST_SCHEMA = dict(schema_structured) if schema_structured else None
    return {
        "question": question,
        "schema_structured": schema_structured,
        "entities": entities or {},
        "dataset_id": dataset_id,
    }


def _run_case(state: dict) -> dict:
    """跑旧 semantic_asset_resolution_node 一次，冻结 outcome 字段。"""
    return semantic_asset_resolution_node(state)


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
        "not_applicable_no_schema",
        "schema_structured 为 None → 不解析",
        state=_make_state(
            question="本周 GMV",
            schema_structured=None,
        ),
    ))
    fixtures.append(_build_fixture(
        "not_applicable_empty_schema",
        "schema_structured 为 {} → 不解析",
        state=_make_state(
            question="本周 GMV",
            schema_structured={},
        ),
    ))
    fixtures.append(_build_fixture(
        "not_applicable_empty_question_no_entities",
        "question 为空 + entities 为空 → 不解析",
        state=_make_state(
            question="",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "not_applicable_all_buckets_empty",
        "所有资产桶都为空 → 不解析",
        state=_make_state(
            question="本周 GMV",
            schema_structured={
                "metrics": [], "dimensions": [], "terms": [],
                "fields": [], "blueprints": [],
            },
        ),
    ))

    # ===== Case 5-11: resolved（命中单一资产类型） =====
    fixtures.append(_build_fixture(
        "resolved_metric_exact",
        "metric exact 命中（question 等于 metric.name）",
        state=_make_state(
            question="GMV",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV", "synonyms": ["总成交额"]}],
                "dimensions": [],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "resolved_dimension_exact",
        "dimension exact 命中",
        state=_make_state(
            question="订单状态",
            schema_structured={
                "metrics": [],
                "dimensions": [{"id": 1, "name": "订单状态", "synonyms": ["状态"]}],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "resolved_field_column_match",
        "field 通过 column_name 命中",
        state=_make_state(
            question="user_id",
            schema_structured={
                "metrics": [],
                "dimensions": [],
                "terms": [],
                "fields": [{
                    "id": 1, "name": "user_id", "column_name": "user_id",
                    "table_name": "orders",
                }],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "resolved_term_with_linked_asset",
        "term 命中并扩展 asset_links 中的 metric/dimension",
        state=_make_state(
            question="成交总额",
            schema_structured={
                "metrics": [{"id": 10, "name": "GMV", "synonyms": ["总成交额"]}],
                "dimensions": [{"id": 20, "name": "订单日期"}],
                "terms": [
                    {
                        "id": 100,
                        "name": "成交总额",
                        "display_name": "成交总额",
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
        ),
    ))
    fixtures.append(_build_fixture(
        "resolved_blueprint_trigger_keyword",
        "blueprint 通过 trigger_keywords 命中",
        state=_make_state(
            question="GMV 趋势归因分析",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [],
                "terms": [],
                "fields": [],
                "blueprints": [{
                    "id": 1,
                    "name": "GMV 归因",
                    "trigger_keywords": ["趋势归因分析", "GMV 归因"],
                    "trigger_examples": ["GMV 下降原因是什么"],
                }],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "resolved_metric_via_synonym",
        "metric 通过 synonym 命中（置信度 0.88）",
        state=_make_state(
            question="总成交额",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV", "synonyms": ["总成交额", "GMV 总额"]}],
                "dimensions": [],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "resolved_metric_via_entities",
        "entities.metrics 列表命中 metric",
        state=_make_state(
            question="最近一周汇总",
            entities={"metrics": ["GMV"], "dimensions": [], "terms": []},
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))

    # ===== Case 12-15: ambiguity =====
    fixtures.append(_build_fixture(
        "ambiguity_two_close_metrics",
        "两个 metric 置信度接近 → ambiguity",
        state=_make_state(
            question="GMV",
            schema_structured={
                "metrics": [
                    {"id": 1, "name": "GMV", "synonyms": ["GMV 总额"]},
                    {"id": 2, "name": "GMV 总额", "synonyms": ["GMV"]},
                ],
                "dimensions": [],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "ambiguity_two_close_dimensions",
        "两个 dimension 置信度接近 → ambiguity",
        state=_make_state(
            question="日期",
            schema_structured={
                "metrics": [],
                "dimensions": [
                    {"id": 1, "name": "日期", "synonyms": ["订单日期"]},
                    {"id": 2, "name": "订单日期", "synonyms": ["日期"]},
                ],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "ambiguity_metric_vs_blueprint",
        "metric 撞 blueprint（context bias 让 blueprint 偏置）",
        state=_make_state(
            question="GMV 归因分析",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [],
                "terms": [],
                "fields": [],
                "blueprints": [{
                    "id": 1,
                    "name": "GMV 归因",
                    "trigger_keywords": ["归因分析", "GMV 归因"],
                }],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "ambiguity_term_synonym_vs_metric",
        "term 同义词和 metric 撞名（term 通过 linked_term 扩展 metric）",
        state=_make_state(
            question="GMV",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [],
                "terms": [
                    {
                        "id": 100,
                        "name": "成交总额",
                        "synonyms": ["GMV"],
                        "asset_links": [{"asset_type": "metric", "asset_id": 1}],
                    }
                ],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))

    # ===== Case 16-18: unresolved =====
    fixtures.append(_build_fixture(
        "unresolved_entity_metric_not_in_schema",
        "entities.metric 不在 schema → unresolved",
        state=_make_state(
            question="最近一周",
            entities={"metrics": ["不存在的指标"], "dimensions": [], "terms": []},
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "unresolved_entity_dimension_not_in_schema",
        "entities.dimension 不在 schema → unresolved",
        state=_make_state(
            question="最近一周",
            entities={"metrics": [], "dimensions": ["不存在的维度"], "terms": []},
            schema_structured={
                "metrics": [],
                "dimensions": [{"id": 1, "name": "日期"}],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "unresolved_no_match_no_query",
        "question 无匹配 + entities 也无 → unresolved",
        state=_make_state(
            question="随便问",
            entities={"metrics": [], "dimensions": [], "terms": []},
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [{"id": 2, "name": "日期"}],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))

    # ===== Case 19-25: 边界 =====
    fixtures.append(_build_fixture(
        "boundary_metric_pattern_context_bias",
        "问题含「统计/汇总」触发 metric 偏置",
        state=_make_state(
            question="GMV 统计",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [{"id": 2, "name": "GMV 分组维度"}],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "boundary_dimension_pattern_context_bias",
        "问题含「明细/列表」触发 dimension 偏置",
        state=_make_state(
            question="订单明细列表",
            schema_structured={
                "metrics": [{"id": 1, "name": "订单明细数"}],
                "dimensions": [{"id": 2, "name": "订单明细"}],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "boundary_preferred_type_metric_priority",
        "entities 指定 preferred_type=metric，metric 优先级更高",
        state=_make_state(
            question="GMV",
            entities={"metrics": ["GMV"], "dimensions": [], "terms": []},
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [{"id": 2, "name": "GMV 分组"}],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "boundary_empty_entities",
        "entities 为空 dict → 只 question 单独走匹配",
        state=_make_state(
            question="GMV",
            entities={},
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "boundary_trigger_example_match",
        "blueprint 通过 trigger_example 命中（置信度 0.78）",
        state=_make_state(
            question="GMV 下降原因是什么",
            schema_structured={
                "metrics": [{"id": 1, "name": "GMV"}],
                "dimensions": [],
                "terms": [],
                "fields": [],
                "blueprints": [{
                    "id": 1,
                    "name": "GMV 归因",
                    "trigger_examples": ["GMV 下降原因是什么"],
                }],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "boundary_field_synonym_match",
        "field 通过 synonyms 命中",
        state=_make_state(
            question="客户编号",
            schema_structured={
                "metrics": [],
                "dimensions": [],
                "terms": [],
                "fields": [{
                    "id": 1, "name": "user_id", "column_name": "user_id",
                    "table_name": "users",
                    "synonyms": ["客户编号"],
                }],
                "blueprints": [],
            },
        ),
    ))
    fixtures.append(_build_fixture(
        "boundary_metric_resolution_compat_field",
        "metric_resolution 兼容字段（all_matched / unresolved）正确",
        state=_make_state(
            question="本周",
            entities={"metrics": ["GMV", "DAU"], "dimensions": [], "terms": []},
            schema_structured={
                "metrics": [
                    {"id": 1, "name": "GMV"},
                    {"id": 2, "name": "DAU"},
                ],
                "dimensions": [],
                "terms": [],
                "fields": [],
                "blueprints": [],
            },
        ),
    ))

    # ===== 写出 =====
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for fx in fixtures:
            f.write(json.dumps(fx, ensure_ascii=False) + "\n")
    print(f"✅ wrote {len(fixtures)} fixtures to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()