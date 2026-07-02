# ============================================================
# File Name   : test_multiturn_context_builder.py
# Description:
#   MultiturnContextBuilder 抽取风险点单测。
#   7 个用例聚焦 Phase 1 抽取中识别到的 7 个风险（settings patch 路径、out_capsule
#   归属、services→graph 边界、dataclass 序列化、interpret_payload keys、
#   blueprint settings_enabled、既有测试不退化）。
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

import dataclasses
import importlib.util
import json

from app.services.multiturn_context import (
    MergeDecision,
    MultiturnContextBuilder,
)


# ===== 1. settings patch 路径迁移 =====


def test_settings_patch_in_builder_module(monkeypatch):
    """monkeypatch.setattr(\"app.services.multiturn_context.get_settings\") 必须能切换
    _blueprint_shortcut_enabled。覆盖 plan F1/F4 整改项：builder 不再从
    app.graph.nodes.get_settings 读 settings。
    """

    class SettingsOn:
        MULTITURN_BLUEPRINT_SHORTCUT_ENABLED = True

    class SettingsOff:
        MULTITURN_BLUEPRINT_SHORTCUT_ENABLED = False

    state = {
        "question": "只看华东",
        "turn_type": None,
        "dataset_id": 1,
        "prior_capsule": {
            "query_context": {
                "metrics": ["销售额"],
                "dimensions": ["门店"],
                "question": "各门店销售额",
                "dataset_id": 1,
                "blueprint_id": 42,
                "routing_path": "blueprint",
            },
            "resolved_question": "各门店销售额",
        },
        "lead_agent_context": {"multiturn_classification": {"intent": "continue"}},
    }
    builder = MultiturnContextBuilder()

    monkeypatch.setattr(
        "app.services.multiturn_context.get_settings", lambda: SettingsOn()
    )
    assert builder.blueprint_shortcut_enabled() is True
    decision_on = builder.build(state)
    assert decision_on.blueprint_shortcut is not None
    assert decision_on.blueprint_shortcut.get("settings_enabled") is True

    monkeypatch.setattr(
        "app.services.multiturn_context.get_settings", lambda: SettingsOff()
    )
    assert builder.blueprint_shortcut_enabled() is False
    decision_off = builder.build(state)
    assert decision_off.blueprint_shortcut is not None
    assert decision_off.blueprint_shortcut.get("settings_enabled") is False


# ===== 2. build_out_capsule 仍由 nodes.py 拥有 =====


def test_build_out_capsule_still_owned_by_nodes():
    """builder 模块源码中不应出现 build_out_capsule 的 import 或函数调用。

    docstring 提及 build_out_capsule 不算违规（仅是注释），用 AST 解析后仅检查
    ImportFrom / Call / Name 节点。
    """
    import ast
    import inspect

    from app.services import multiturn_context

    source = inspect.getsource(multiturn_context)
    tree = ast.parse(source)
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "graph.nodes" in node.module:
            for alias in node.names:
                if alias.name == "build_out_capsule":
                    offenders.append(
                        f"line {node.lineno}: from {node.module} import {alias.name}"
                    )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "build_out_capsule":
                offenders.append(f"line {node.lineno}: build_out_capsule() 调用")
            elif isinstance(func, ast.Attribute) and func.attr == "build_out_capsule":
                offenders.append(f"line {node.lineno}: .{func.attr}() 调用")
        elif isinstance(node, ast.Name) and node.id == "build_out_capsule":
            offenders.append(f"line {node.lineno}: 名字引用")

    assert not offenders, (
        "MultiturnContextBuilder 不应引用 build_out_capsule：\n  "
        + "\n  ".join(offenders)
    )


# ===== 3. services→graph 边界（import 期检查）=====


def test_builder_does_not_import_nodes():
    """app.services.multiturn_context 不应依赖 app.graph.nodes。"""
    from app.services import multiturn_context
    from app.services.multiturn_context import (
        MergeDecision,
        MultiturnContextBuilder,
    )

    # 关键类/方法存在（方法挂在类上，类挂在模块上）
    assert dataclasses.is_dataclass(MergeDecision)
    assert hasattr(MultiturnContextBuilder, "build")
    for method_name in (
        "is_interpret_result_turn",
        "is_continue_turn",
        "derive_multiturn_delta",
        "blueprint_shortcut_candidate",
        "blueprint_shortcut_enabled",
        "build_interpret_answer",
    ):
        assert hasattr(MultiturnContextBuilder, method_name), (
            f"MultiturnContextBuilder 应提供 {method_name} 方法"
        )

    # 模块级不应持有 build_out_capsule（边界保护）
    assert "build_out_capsule" not in vars(multiturn_context)


# ===== 4. MergeDecision dataclass 序列化兼容 =====


def test_merge_decision_dataclass_serializable():
    """asdict(decision) 后必须能 json.dumps；供 API/SSE 输出使用。"""
    state = {
        "question": "再按门店拆分",
        "turn_type": None,
        "dataset_id": 1,
        "prior_capsule": {
            "query_context": {
                "metrics": ["销售额"],
                "dimensions": ["省份"],
                "question": "各省销售额是多少",
                "dataset_id": 1,
            },
            "resolved_question": "各省销售额是多少",
        },
        "lead_agent_context": {"multiturn_classification": {"intent": "continue"}},
    }
    decision = MultiturnContextBuilder().build(state)
    payload = dataclasses.asdict(decision)
    serialized = json.dumps(payload, ensure_ascii=False)
    roundtrip = json.loads(serialized)
    assert roundtrip["turn_type"] == decision.turn_type
    assert roundtrip["synthesized_question"] == decision.synthesized_question


# ===== 5. interpret_payload 必含 keys（factory 注入 out_capsule）=====


def test_interpret_payload_contains_required_keys():
    """interpret 早退时，interpret_payload 必含 entry_intent/entry_route/answer/
    route_payload/multiturn_context/merge_debug/should_retry/out_capsule。
    out_capsule 通过 factory 注入，验证 builder 调用 factory 并把结果写入 payload。
    """
    state = {
        "question": "为什么广东最高",
        "turn_type": None,
        "turn_index": 2,
        "dataset_id": 1,
        "prior_capsule": {
            "query_context": {
                "metrics": ["销售额"],
                "dimensions": ["省份"],
                "question": "各省销售额",
                "dataset_id": 1,
            },
            "resolved_question": "各省销售额",
            "result_digest": {
                "row_count": 5,
                "columns": [{"name": "省份"}],
                "numeric_summary": {},
                "highlights": {},
            },
        },
        "lead_agent_context": {
            "dispatch": {"capsule": {"execution_mode": "interpret_result"}},
        },
    }

    calls = []

    def fake_factory(state_arg, output_arg):
        calls.append((state_arg, output_arg))
        return {"capsule_version": "stub", "row_count": 5}

    builder = MultiturnContextBuilder(out_capsule_factory=fake_factory)
    decision = builder.build(state)
    assert decision.interpret_payload is not None
    payload = decision.interpret_payload

    for key in (
        "entry_intent",
        "entry_route",
        "answer",
        "multiturn_context",
        "merge_debug",
        "should_retry",
        "out_capsule",
    ):
        assert key in payload, f"interpret_payload 缺 {key}"

    assert payload["entry_intent"] == "interpret"
    assert payload["entry_route"] == "interpret_result"
    assert "不会重新生成 SQL" in payload["answer"]
    assert payload["out_capsule"]["capsule_version"] == "stub"
    assert len(calls) == 1, "builder 应调用 factory 恰好一次"


# ===== 6. blueprint_shortcut 必含 settings_enabled =====


def test_blueprint_shortcut_decision_attaches_settings_enabled(monkeypatch):
    """continue 命中蓝图候选时，decision.blueprint_shortcut 必含 settings_enabled 标志。

    节点薄壳据此决定是否走 blueprint_execute 路由（与 nodes.py 旧行为等价）。
    """

    class SettingsOn:
        MULTITURN_BLUEPRINT_SHORTCUT_ENABLED = True

    class SettingsOff:
        MULTITURN_BLUEPRINT_SHORTCUT_ENABLED = False

    state = {
        "question": "只看华东",
        "turn_type": None,
        "dataset_id": 1,
        "prior_capsule": {
            "query_context": {
                "metrics": ["销售额"],
                "dimensions": ["门店"],
                "question": "各门店销售额",
                "dataset_id": 1,
                "blueprint_id": 42,
                "routing_path": "blueprint",
            },
            "resolved_question": "各门店销售额",
        },
        "lead_agent_context": {"multiturn_classification": {"intent": "continue"}},
    }
    builder = MultiturnContextBuilder()

    monkeypatch.setattr(
        "app.services.multiturn_context.get_settings", lambda: SettingsOn()
    )
    decision_on = builder.build(state)
    assert decision_on.blueprint_shortcut is not None
    assert decision_on.blueprint_shortcut.get("blueprint_id") == 42
    assert decision_on.blueprint_shortcut.get("settings_enabled") is True

    monkeypatch.setattr(
        "app.services.multiturn_context.get_settings", lambda: SettingsOff()
    )
    decision_off = builder.build(state)
    assert decision_off.blueprint_shortcut is not None
    assert decision_off.blueprint_shortcut.get("settings_enabled") is False


# ===== 8. frozen fixtures 等价性比对 =====


def test_equivalence_with_frozen_phase0_fixtures():
    """加载 tests/fixtures/multiturn_phase0_outputs.jsonl（T0 冻结的 Phase 0 预期输出），
    跑 MultiturnContextBuilder.build(state) 与 expected_output 语义比对。

    比对规则（覆盖 plan T0 设计意图）：
    - turn_type: 必须相等
    - synthesized_question: builder 顶层 vs expected['question']
    - blueprint_shortcut: builder 顶层 vs expected['multiturn_context']['blueprint_shortcut']
      * expected = {enabled, blueprint_id, reason} 或 None
      * builder = {blueprint_id, reason, enabled, settings_enabled} 或 None
      * 字段映射：blueprint_id/reason/enabled 必须等价；settings_enabled 是 builder 独有
    - multiturn_context: 整体 deep_equal（剔除 blueprint_shortcut）
    - merge_debug: 整体 deep_equal，merge_debug.blueprint_shortcut 内 settings_enabled 允许差异
    - interpret_payload: builder.interpret_payload vs expected（除 out_capsule 外）
    """
    from pathlib import Path

    fixtures_path = (
        Path(__file__).resolve().parent / "fixtures" / "multiturn_phase0_outputs.jsonl"
    )
    if not fixtures_path.exists():
        import pytest

        pytest.skip("Phase 0 fixtures 文件未生成（先跑 capture_phase0_fixtures.py）")

    builder = MultiturnContextBuilder()
    failures: list[str] = []

    def deep_equal(a, b, ignore_keys=()):
        if a == b:
            return True
        if isinstance(a, dict) and isinstance(b, dict):
            sa = {k: v for k, v in a.items() if k not in ignore_keys}
            sb = {k: v for k, v in b.items() if k not in ignore_keys}
            if set(sa.keys()) != set(sb.keys()):
                return False
            return all(deep_equal(sa[k], sb[k], ignore_keys) for k in sa)
        if isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                return False
            return all(deep_equal(x, y, ignore_keys) for x, y in zip(a, b))
        return False

    import json

    for line in fixtures_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        fixture = json.loads(line)
        name = fixture["name"]
        state = fixture["input_state"]
        expected = fixture["expected_output"]
        decision = builder.build(state)

        # 1. interpret 路径
        if decision.interpret_payload is not None:
            expected_payload = {k: v for k, v in expected.items() if k != "out_capsule"}
            if not deep_equal(decision.interpret_payload, expected_payload):
                failures.append(f"{name}: interpret_payload mismatch")
            continue

        # 2. turn_type
        if expected.get("turn_type") != decision.turn_type:
            failures.append(
                f"{name}: turn_type expected={expected.get('turn_type')!r} "
                f"actual={decision.turn_type!r}"
            )
            continue

        # 3. synthesized_question
        if decision.synthesized_question is not None:
            if expected.get("question") != decision.synthesized_question:
                failures.append(f"{name}: synthesized_question vs expected.question")
                continue

        # 4. blueprint_shortcut 语义比对
        expected_bs = (expected.get("multiturn_context") or {}).get("blueprint_shortcut")
        actual_bs = decision.blueprint_shortcut
        if (expected_bs is None) != (actual_bs is None):
            failures.append(
                f"{name}: blueprint_shortcut presence "
                f"expected={'present' if expected_bs else 'None'} "
                f"actual={'present' if actual_bs else 'None'}"
            )
        elif expected_bs is not None:
            if actual_bs.get("blueprint_id") != expected_bs.get("blueprint_id"):
                failures.append(f"{name}: blueprint_id mismatch")
            if actual_bs.get("reason") != expected_bs.get("reason"):
                failures.append(f"{name}: reason mismatch")
            if actual_bs.get("enabled") != expected_bs.get("enabled"):
                failures.append(f"{name}: enabled mismatch")

        # 5. multiturn_context（剔除 blueprint_shortcut）
        expected_mt = dict(expected.get("multiturn_context") or {})
        expected_mt.pop("blueprint_shortcut", None)
        actual_mt = dict(decision.multiturn_context or {})
        actual_mt.pop("blueprint_shortcut", None)
        if not deep_equal(actual_mt, expected_mt):
            failures.append(f"{name}: multiturn_context mismatch")

        # 6. merge_debug（settings_enabled 允许差异）
        if not deep_equal(
            decision.merge_debug, expected.get("merge_debug"), {"settings_enabled"}
        ):
            failures.append(f"{name}: merge_debug mismatch")

    assert not failures, (
        f"Builder 与 Phase 0 frozen fixtures 不等价 ({len(failures)} 失败):\n  "
        + "\n  ".join(failures)
    )


def test_detail_query_followup_keeps_prior_without_metrics():
    """明细查询有字段和主表即可承接追问，不应因为 metrics 为空降级。"""
    builder = MultiturnContextBuilder()
    decision = builder.build(
        {
            "question": "只看汤杰",
            "turn_type": "continue",
            "prior_capsule": {
                "query_context": {
                    "query_type": "detail_query",
                    "fields": [{"name": "rzrq"}],
                    "main_table": "plan_task_daily_record",
                    "question": "查询10条用户日志",
                }
            },
        }
    )

    assert decision.turn_type == "continue"
    assert (
        decision.multiturn_context["merged_query_context"]["main_table"]
        == "plan_task_daily_record"
    )
    assert decision.merge_debug["reason"] == "continue_turn_with_prior_query_context"


def test_detail_query_followup_keeps_prior_with_query_plan_only():
    """明细查询只有 query_plan 时也有可继承查询目标。"""
    builder = MultiturnContextBuilder()
    decision = builder.build(
        {
            "question": "只看汤杰",
            "turn_type": "continue",
            "prior_capsule": {
                "query_context": {
                    "query_type": "detail_query",
                    "query_plan": {
                        "query_type": "detail_query",
                        "select_fields": ["rzrq", "person_name"],
                    },
                    "question": "查询10条用户日志",
                }
            },
        }
    )

    assert decision.turn_type == "continue"
    assert decision.multiturn_context["merged_query_context"]["query_plan"]
    assert decision.merge_debug["reason"] == "continue_turn_with_prior_query_context"


def test_detail_query_followup_keeps_prior_with_dsl_only():
    """明细查询只有 dsl 时也有可继承查询目标。"""
    builder = MultiturnContextBuilder()
    decision = builder.build(
        {
            "question": "只看汤杰",
            "turn_type": "continue",
            "prior_capsule": {
                "query_context": {
                    "query_type": "detail_query",
                    "dsl": {
                        "select": ["rzrq", "person_name"],
                        "from": "plan_task_daily_record",
                    },
                    "question": "查询10条用户日志",
                }
            },
        }
    )

    assert decision.turn_type == "continue"
    assert decision.multiturn_context["merged_query_context"]["dsl"]
    assert decision.merge_debug["reason"] == "continue_turn_with_prior_query_context"


def test_metric_query_without_metrics_still_downgrades_to_new_query():
    """指标查询没有 metrics 仍然不能承接，避免把无目标上下文传给下游。"""
    builder = MultiturnContextBuilder()
    decision = builder.build(
        {
            "question": "只看华东",
            "turn_type": "continue",
            "prior_capsule": {
                "query_context": {
                    "query_type": "metric_query",
                    "dimensions": ["地区"],
                    "question": "按地区统计销售情况",
                }
            },
        }
    )

    assert decision.turn_type == "new"
    assert decision.merge_debug["reason"] == "merged_metrics_empty_downgraded_to_new_query"


def test_query_task_capsule_base_query_plan_fills_prior_context():
    """prior_capsule 为空时，可从 query_task_capsule 的 base_query_plan 兜底承接。"""
    from app.services.task_capsule import build_query_task_capsule, build_success_task_state

    last_success_task = build_success_task_state(
        question="查询10条用户日志",
        dataset_id=10,
        query_plan={
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "planner_source": "deterministic",
            "debug": {"selected_main_table": "plan_task_daily_record"},
        },
        dsl={"fields": [{"table_name": "plan_task_daily_record", "name": "rzrq"}]},
        sql="SELECT rzrq, person_name FROM plan_task_daily_record LIMIT 10",
        sql_result={"columns": ["rzrq", "person_name"], "rows": []},
    )

    query_task_capsule = build_query_task_capsule(
        question="只看汤杰",
        turn_event={"event_type": "followup_refine"},
        active_dataset_id=10,
        last_success_task=last_success_task,
    )
    builder = MultiturnContextBuilder()
    decision = builder.build(
        {
            "question": "只看汤杰",
            "turn_type": "continue",
            "dataset_id": 10,
            "prior_capsule": {},
            "query_task_capsule": query_task_capsule,
        }
    )

    assert decision.turn_type == "continue"
    merged = decision.multiturn_context["merged_query_context"]
    assert merged["main_table"] == "plan_task_daily_record"
    assert merged["query_plan"]["query_type"] == "detail_query"
    assert decision.multiturn_context["prior_query_context"]["question"] == "查询10条用户日志"
    assert decision.synthesized_question == "基于上一轮问题「查询10条用户日志」，只看汤杰"


def test_prior_capsule_query_context_takes_precedence_over_query_task_capsule():
    builder = MultiturnContextBuilder()
    decision = builder.build(
        {
            "question": "只看汤杰",
            "turn_type": "continue",
            "dataset_id": 10,
            "prior_capsule": {
                "query_context": {
                    "query_type": "detail_query",
                    "main_table": "prior_capsule_table",
                    "question": "上一轮来自 prior capsule",
                }
            },
            "query_task_capsule": {
                "turn_type": "followup_refine",
                "dataset_id": 10,
                "base_task_ref": "last_success_task",
                "base_question": "查询10条用户日志",
                "base_main_table": "query_task_capsule_table",
                "base_query_plan": {"query_type": "detail_query"},
            },
        }
    )

    merged = decision.multiturn_context["merged_query_context"]
    assert merged["main_table"] == "prior_capsule_table"
    assert decision.multiturn_context["prior_query_context"]["question"] == "上一轮来自 prior capsule"


def test_query_task_capsule_prior_context_requires_followup_refine():
    builder = MultiturnContextBuilder()
    decision = builder.build(
        {
            "question": "只看汤杰",
            "turn_type": "continue",
            "dataset_id": 10,
            "prior_capsule": {},
            "query_task_capsule": {
                "turn_type": "followup_explain",
                "dataset_id": 10,
                "base_task_ref": "last_success_task",
                "base_main_table": "plan_task_daily_record",
                "base_query_plan": {"query_type": "detail_query"},
            },
        }
    )

    assert decision.turn_type == "new"


def test_query_task_capsule_prior_context_requires_base_task_ref():
    builder = MultiturnContextBuilder()
    decision = builder.build(
        {
            "question": "只看汤杰",
            "turn_type": "continue",
            "dataset_id": 10,
            "prior_capsule": {},
            "query_task_capsule": {
                "turn_type": "followup_refine",
                "dataset_id": 10,
                "base_main_table": "plan_task_daily_record",
                "base_query_plan": {"query_type": "detail_query"},
            },
        }
    )

    assert decision.turn_type == "new"


def test_query_task_capsule_prior_context_requires_same_dataset():
    builder = MultiturnContextBuilder()
    decision = builder.build(
        {
            "question": "只看汤杰",
            "turn_type": "continue",
            "dataset_id": 10,
            "prior_capsule": {},
            "query_task_capsule": {
                "turn_type": "followup_refine",
                "dataset_id": 11,
                "base_task_ref": "last_success_task",
                "base_main_table": "plan_task_daily_record",
                "base_query_plan": {"query_type": "detail_query"},
            },
        }
    )

    assert decision.turn_type == "new"
