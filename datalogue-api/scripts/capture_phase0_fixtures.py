# ============================================================
# File Name   : capture_phase0_fixtures.py
# Description:
#   在 MultiturnContextBuilder 抽取（Phase 1）前冻结 merge_prior_context_node
#   的当前输出，作为后续等价性测试的基线。每条 fixture 形如：
#       {"name": ..., "input_state": {...}, "expected_output": {...}}
#   本脚本只跑一次；之后用 tests/test_multiturn_context_builder.py 加载
#   fixtures 比对 builder.build(state) 与 expected_output 的等价性。
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.graph.nodes import merge_prior_context_node  # noqa: E402

OUTPUT_PATH = ROOT / "tests" / "fixtures" / "multiturn_phase0_outputs.jsonl"

# 输出里需要剔除的动态时间字段，避免每次跑 created_at 不一致导致 fixture 失效。
DYNAMIC_KEYS = {"created_at", "last_updated_at", "updated_at"}


def strip_dynamic(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_dynamic(item)
            for key, item in value.items()
            if key not in DYNAMIC_KEYS
        }
    if isinstance(value, list):
        return [strip_dynamic(item) for item in value]
    return value


def prior_capsule_base(
    *,
    dataset_id: int = 1,
    metrics=None,
    dimensions=None,
    question: str = "各省销售额",
    blueprint_id=None,
    routing_path: str = "free_query",
    resolved_question=None,
    result_digest=None,
) -> dict:
    """构造与 SubAgent build_out_capsule 兼容的最小 prior_capsule。"""
    capsule = {
        "capsule_version": "subagent.v1",
        "dataset_id": dataset_id,
        "manifest_version": "m.v1",
        "bound_schema_version": "s.v1",
        "query_context": {
            "metrics": metrics or [],
            "dimensions": dimensions or [],
            "question": question,
            "dataset_id": dataset_id,
            "blueprint_id": blueprint_id,
            "routing_path": routing_path,
        },
        "resolved_question": resolved_question or question,
        "result_digest": result_digest or {},
        "last_result_digest": result_digest or {},
    }
    return capsule


def lead_continue_intent() -> dict:
    return {"multiturn_classification": {"intent": "continue"}}


def lead_interpret_dispatch() -> dict:
    return {
        "dispatch": {
            "capsule": {"execution_mode": "interpret_result"},
        },
    }


# 12 条 fixture 场景定义。每条用单引号 description 避免与 dict 字符串冲突。
FIXTURES = [
    {
        "name": "continue_with_prior_question",
        "description": (
            "LeadAgent 分类为 continue, prior_query_context 存在且有 resolved_question, "
            "question 命中 dimensions 提取模式; 期望 output.synthesized_question 包含"
            " '基于上一轮问题' 补全前缀."
        ),
        "input_state": {
            "question": "再按门店拆分",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["省份"],
                question="各省销售额是多少",
                resolved_question="各省销售额是多少",
            ),
            "lead_agent_context": lead_continue_intent(),
        },
    },
    {
        "name": "continue_metrics_empty_downgrades",
        "description": (
            "LeadAgent 分类为 continue, prior_query_context.metrics 是空列表, "
            "delta 不引入 metrics; _has_query_metrics 返回 False, "
            "期望 turn_type=new, reason=merged_metrics_empty_downgraded_to_new_query."
        ),
        "input_state": {
            "question": "再按门店拆分",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=[],
                dimensions=["省份"],
                question="各省销售额是多少",
                resolved_question="各省销售额是多少",
            ),
            "lead_agent_context": lead_continue_intent(),
        },
    },
    {
        "name": "continue_with_blueprint_enabled",
        "description": (
            "prior_query_context.blueprint_id 非空 + routing_path=blueprint, "
            "delta 仅调整 filter, blueprint_shortcut 候选合法; "
            "monkeypatch settings.MULTITURN_BLUEPRINT_SHORTCUT_ENABLED=True, "
            "期望 output 含 entry_intent=analysis_blueprint / entry_route / blueprint_id / route_payload."
        ),
        "input_state": {
            "question": "只看华东",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["门店"],
                question="各门店销售额",
                blueprint_id=42,
                routing_path="blueprint",
            ),
            "lead_agent_context": lead_continue_intent(),
        },
        "patch_settings": {"MULTITURN_BLUEPRINT_SHORTCUT_ENABLED": True},
    },
    {
        "name": "continue_with_blueprint_disabled",
        "description": (
            "同上 fixture 3, 但 settings.MULTITURN_BLUEPRINT_SHORTCUT_ENABLED=False; "
            "期望 output 不含 entry_intent/blueprint_id/route_payload, "
            "multiturn_context.blueprint_shortcut 仍保留候选."
        ),
        "input_state": {
            "question": "只看华东",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["门店"],
                question="各门店销售额",
                blueprint_id=42,
                routing_path="blueprint",
            ),
            "lead_agent_context": lead_continue_intent(),
        },
        "patch_settings": {"MULTITURN_BLUEPRINT_SHORTCUT_ENABLED": False},
    },
    {
        "name": "interpret_result_turn",
        "description": (
            "LeadAgent dispatch.capsule.execution_mode=interpret_result, "
            "prior_capsule 含 result_digest; 期望 turn_type=interpret, "
            "entry_intent=interpret, entry_route=interpret_result, "
            "answer 包含 '这轮是对上一轮结果的解释', out_capsule 存在."
        ),
        "input_state": {
            "question": "为什么广东最高",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["省份"],
                question="各省销售额",
                resolved_question="各省销售额",
                result_digest={
                    "row_count": 5,
                    "columns": [{"name": "省份"}, {"name": "销售额"}],
                    "numeric_summary": {"销售额": {"min": 100, "max": 9000, "sum": 50000}},
                    "highlights": {"top": "广东"},
                    "sql_audit_id": "audit-001",
                },
            ),
            "lead_agent_context": lead_interpret_dispatch(),
        },
    },
    {
        "name": "new_turn_no_prior",
        "description": (
            "显式 turn_type=new 且无 prior_capsule, "
            "期望 turn_type=new, reason=no_prior_or_not_continue."
        ),
        "input_state": {
            "question": "本月订单总数",
            "turn_type": "new",
            "turn_index": 1,
            "dataset_id": 1,
            "prior_capsule": None,
            "lead_agent_context": {},
        },
    },
    {
        "name": "new_query_downgrade",
        "description": (
            "无 LeadAgent 显式分类, question 命中 continue 词 '再/排名'; "
            "prior_query_context.metrics 空, _has_query_metrics 返回 False, "
            "降级为 new_query, reason=merged_metrics_empty_downgraded_to_new_query."
        ),
        "input_state": {
            "question": "再加个排名",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=[],
                dimensions=["省份"],
                question="各省销售额",
            ),
            "lead_agent_context": {},
        },
    },
    {
        "name": "prior_capsule_corrupted",
        "description": (
            "prior_capsule 是字符串; _as_dict 收敛为 {}, "
            "期望 turn_type=new, reason=no_prior_or_not_continue."
        ),
        "input_state": {
            "question": "本月订单总数",
            "turn_type": None,
            "turn_index": 1,
            "dataset_id": 1,
            "prior_capsule": "garbage-not-a-dict",
            "lead_agent_context": {},
        },
    },
    {
        "name": "prior_capsule_none",
        "description": (
            "prior_capsule=None, _as_dict 收敛为 {}, 期望 turn_type=new."
        ),
        "input_state": {
            "question": "本月订单总数",
            "turn_type": None,
            "turn_index": 1,
            "dataset_id": 1,
            "lead_agent_context": {},
        },
    },
    {
        "name": "empty_history_non_continue",
        "description": (
            "prior_capsule.query_context 存在 metrics, "
            "question '本月订单总数' 不含 continue 词; "
            "_is_continue_turn 返回 False, 期望 turn_type=new."
        ),
        "input_state": {
            "question": "本月订单总数",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["省份"],
            ),
            "lead_agent_context": {},
        },
    },
    {
        "name": "short_history_non_continue",
        "description": (
            "question 短且无 continue 词, 期望 turn_type=new."
        ),
        "input_state": {
            "question": "总数",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["省份"],
            ),
            "lead_agent_context": {},
        },
    },
    {
        "name": "dataset_switch_explicit",
        "description": (
            "显式 turn_type=new, 即使 prior_capsule 有 query_context 也走 new 路径; "
            "期望 turn_type=new, reason=no_prior_or_not_continue."
        ),
        "input_state": {
            "question": "切到数据集 2 查订单",
            "turn_type": "new",
            "turn_index": 3,
            "dataset_id": 2,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["省份"],
                dataset_id=1,
            ),
            "lead_agent_context": {},
        },
    },
    # === Phase 2 扩展: 4 条 interpret 早退 case（覆盖三种触发条件 + 极简 result_digest）===
    {
        "name": "interpret_via_should_generate_query_false",
        "description": (
            "dispatch.capsule.should_generate_query=False 触发 interpret 早退；"
            "prior_capsule 含最小 result_digest；期望 turn_type=interpret, entry_route=interpret_result."
        ),
        "input_state": {
            "question": "为什么广东最高",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["省份"],
                question="各省销售额",
                resolved_question="各省销售额",
                result_digest={
                    "row_count": 5,
                    "columns": [{"name": "省份"}, {"name": "销售额"}],
                    "numeric_summary": {},
                    "highlights": {},
                },
            ),
            "lead_agent_context": {
                "dispatch": {"capsule": {"should_generate_query": False}},
            },
        },
    },
    {
        "name": "interpret_via_lead_intent_only",
        "description": (
            "lead_agent_context.multiturn_classification.intent=interpret 触发；"
            "无 dispatch 字段；期望 turn_type=interpret."
        ),
        "input_state": {
            "question": "为什么广东最高",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["省份"],
                result_digest={
                    "row_count": 5,
                    "columns": [{"name": "省份"}, {"name": "销售额"}],
                    "numeric_summary": {"销售额": {"min": 100, "max": 9000}},
                    "highlights": {"top": "广东"},
                },
            ),
            "lead_agent_context": {
                "multiturn_classification": {"intent": "interpret"},
            },
        },
    },
    {
        "name": "interpret_with_minimal_result_digest",
        "description": (
            "interpret 触发条件=execution_mode, result_digest 极简（无 numeric_summary/highlights）；"
            "验证 builder 仍能输出 answer 和 out_capsule，不依赖完整字段."
        ),
        "input_state": {
            "question": "这个数据怎么解读",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["省份"],
                result_digest={
                    "row_count": 3,
                    "columns": [{"name": "省份"}],
                },
            ),
            "lead_agent_context": lead_interpret_dispatch(),
        },
    },
    {
        "name": "interpret_with_dense_result_digest",
        "description": (
            "interpret 触发条件=execution_mode, result_digest 含完整 numeric_summary/highlights/sql_audit_id；"
            "验证 builder 把 sql_audit_id 透传到 out_capsule."
        ),
        "input_state": {
            "question": "为什么广东最高",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["省份", "门店"],
                result_digest={
                    "row_count": 5,
                    "columns": [
                        {"name": "省份"},
                        {"name": "门店"},
                        {"name": "销售额"},
                    ],
                    "numeric_summary": {
                        "销售额": {"min": 100, "max": 9000, "sum": 50000, "avg": 10000}
                    },
                    "highlights": {"top": "广东", "bottom": "西藏"},
                    "sql_audit_id": "audit-phase2-dense",
                },
            ),
            "lead_agent_context": lead_interpret_dispatch(),
        },
    },
    # === Phase 2 扩展: 4 条 blueprint_shortcut case（覆盖 delta 多样性）===
    {
        "name": "blueprint_shortcut_with_time_delta",
        "description": (
            "prior_query_context 含 blueprint_id + routing_path=blueprint；"
            "delta 含 time_range（最近 30 天）；settings enabled；"
            "期望 output 含 entry_intent=analysis_blueprint 且 multiturn_context.delta.time_range 存在."
        ),
        "input_state": {
            "question": "最近 30 天",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["门店"],
                question="各门店销售额",
                blueprint_id=99,
                routing_path="blueprint",
            ),
            "lead_agent_context": lead_continue_intent(),
        },
        "patch_settings": {"MULTITURN_BLUEPRINT_SHORTCUT_ENABLED": True},
    },
    {
        "name": "blueprint_shortcut_with_filter_delta_disabled",
        "description": (
            "prior_query_context 含 blueprint_id；delta 加 filter（'只看华东'）；"
            "settings disabled；期望 output 不含 entry_intent，但 blueprint_shortcut 候选保留."
        ),
        "input_state": {
            "question": "只看华东",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["门店"],
                question="各门店销售额",
                blueprint_id=99,
                routing_path="blueprint",
            ),
            "lead_agent_context": lead_continue_intent(),
        },
        "patch_settings": {"MULTITURN_BLUEPRINT_SHORTCUT_ENABLED": False},
    },
    {
        "name": "blueprint_shortcut_no_blueprint_id",
        "description": (
            "prior_query_context.blueprint_id=None；"
            "期望 output 不含 blueprint_shortcut 候选，entry_intent 不写."
        ),
        "input_state": {
            "question": "只看华东",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["门店"],
                question="各门店销售额",
                blueprint_id=None,
                routing_path="blueprint",
            ),
            "lead_agent_context": lead_continue_intent(),
        },
        "patch_settings": {"MULTITURN_BLUEPRINT_SHORTCUT_ENABLED": True},
    },
    {
        "name": "blueprint_shortcut_routing_path_free",
        "description": (
            "routing_path=free_query（不是 blueprint）即使 blueprint_id 存在也不算候选；"
            "期望 output 不含 blueprint_shortcut 候选."
        ),
        "input_state": {
            "question": "只看华东",
            "turn_type": None,
            "turn_index": 2,
            "dataset_id": 1,
            "prior_capsule": prior_capsule_base(
                metrics=["销售额"],
                dimensions=["门店"],
                question="各门店销售额",
                blueprint_id=99,
                routing_path="free_query",
            ),
            "lead_agent_context": lead_continue_intent(),
        },
        "patch_settings": {"MULTITURN_BLUEPRINT_SHORTCUT_ENABLED": True},
    },
]


def capture_one(spec: dict) -> dict:
    state = spec["input_state"]
    patches = spec.get("patch_settings") or {}
    settings = get_settings()
    saved = {}
    for key, value in patches.items():
        saved[key] = getattr(settings, key, None)
        setattr(settings, key, value)
    try:
        output = merge_prior_context_node(state)
    finally:
        for key, original in saved.items():
            setattr(settings, key, original)
    return {
        "name": spec["name"],
        "description": spec["description"],
        "input_state": strip_dynamic(state),
        "expected_output": strip_dynamic(output),
    }


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fixtures = []
    for spec in FIXTURES:
        captured = capture_one(spec)
        fixtures.append(captured)
        debug = captured["expected_output"].get("merge_debug", {}) or {}
        print(
            f"captured {captured['name']}: "
            f"turn_type={captured['expected_output'].get('turn_type')!r}, "
            f"reason={debug.get('reason')!r}"
        )

    with OUTPUT_PATH.open("w", encoding="utf-8") as fp:
        for item in fixtures:
            fp.write(json.dumps(item, ensure_ascii=False, sort_keys=False))
            fp.write("\n")
    print(f"wrote {len(fixtures)} fixtures to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
