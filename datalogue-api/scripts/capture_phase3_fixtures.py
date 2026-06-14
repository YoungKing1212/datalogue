# ============================================================
# File Name   : capture_phase3_fixtures.py
# Description:
#   在 LeadAgent 总入口化（Phase 3）前冻结 `route_query_intent` 入口路由的当前输出，
#   作为后续等价性测试的基线。每条 fixture 形如：
#       {"name": ..., "input_state": {...}, "llm_response": {...}, "expected_output": {...}}
#   本脚本只跑一次；之后用 tests/test_phase3_equivalence.py 加载 fixtures
#   比对 route_query_intent 与 expected_output 的等价性。
#
#   25 条 fixture 覆盖：
#   - chitchat × 3（基础/历史/澄清态）
#   - query × 7（metric / dimension / time / filter / 高召回 / 长问题 / 短关键词）
#   - function × 4（有 pending 降级 / 无 pending 拒答 / pending 缺 kind / 业务术语澄清）
#   - permission × 2（中文 / 英文）
#   - knowledge × 2（无术语 / 有术语但 dataset 为空）
#   - detail × 1
#   - blueprint_like × 2（未命中 / 命中 metric）
#   - short_ambiguous × 1
#   - default_clarification × 2（长问题 / 模糊短问）
#   - 边界 × 1（chitchat + dataset_id）
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

from app.services.lead_agent_routing import _classify_entry_intent  # noqa: E402

OUTPUT_PATH = ROOT / "tests" / "fixtures" / "phase3_routing_fixtures.jsonl"


def make_fixture(
    name: str,
    description: str,
    *,
    question: str,
    intent: str,
    entities: dict | None = None,
    dataset_id: int | None = 1,
    history: list | None = None,
    multiturn_context: dict | None = None,
    clarification_response: dict | None = None,
    lead_agent_context: dict | None = None,
) -> dict:
    """构造一条 fixture，跑 _classify_entry_intent 冻结输出。"""
    input_state = {
        "question": question,
        "intent": intent,
        "entities": entities or {},
        "dataset_id": dataset_id,
        "history": history or [],
        "multiturn_context": multiturn_context or {},
        "clarification_response": clarification_response,
        "lead_agent_context": lead_agent_context or {},
    }

    output = _classify_entry_intent(
        db=None,  # 蓝图像 mock 失败；fixture 不触发蓝图/术语匹配
        question=question,
        intent=intent,
        entities=entities or {},
        dataset_id=dataset_id,
        history=history or [],
        multiturn_context=multiturn_context or {},
        clarification_response=clarification_response,
        lead_agent_context=lead_agent_context or {},
    )
    return {
        "name": name,
        "description": description,
        "input_state": input_state,
        "expected_output": output,
    }


# 25 条 fixture
FIXTURES: list[dict] = [
    # === chitchat × 3 ===
    make_fixture(
        name="chitchat_basic",
        description="闲聊场景，intent=chitchat → direct_answer 早退",
        question="你好",
        intent="chitchat",
        entities={},
    ),
    make_fixture(
        name="chitchat_with_history",
        description="闲聊 + 6 轮历史，intent=chitchat → direct_answer",
        question="今天天气怎么样",
        intent="chitchat",
        entities={},
        history=[
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮你的？"},
            {"role": "user", "content": "在吗"},
            {"role": "assistant", "content": "在的"},
        ],
    ),
    make_fixture(
        name="chitchat_with_clarification_pending",
        description="闲聊 + 上轮 pending 澄清态，intent=chitchat → direct_answer 优先",
        question="随便聊聊",
        intent="chitchat",
        entities={},
        multiturn_context={
            "pending_clarification": {"kind": "dataset_choice"},
        },
    ),
    # === query × 7 ===
    make_fixture(
        name="query_metric",
        description="指标查询：entities 含 metrics → query_graph / metric_query",
        question="各省销售额",
        intent="query",
        entities={"metrics": ["销售额"], "dimensions": ["省份"]},
    ),
    make_fixture(
        name="query_dimension_only",
        description="维度查询：entities 仅含 dimensions → query_graph / metric_query",
        question="看各门店情况",
        intent="query",
        entities={"dimensions": ["门店"]},
    ),
    make_fixture(
        name="query_metric_and_dimension",
        description="指标 + 维度：双实体都存在 → query_graph / metric_query",
        question="各门店的 GMV 和订单数",
        intent="query",
        entities={"metrics": ["GMV", "订单数"], "dimensions": ["门店"]},
    ),
    make_fixture(
        name="query_time_range",
        description="时间范围查询：entities 含 time_range → query_graph",
        question="最近 30 天的销售额",
        intent="query",
        entities={"metrics": ["销售额"], "time_range": {"raw": "最近 30 天"}},
    ),
    make_fixture(
        name="query_with_history",
        description="普通查询 + 2 轮历史上下文",
        question="再按门店拆分",
        intent="query",
        entities={},
        history=[
            {"role": "user", "content": "各省销售额"},
            {"role": "assistant", "content": "已生成报告"},
        ],
    ),
    make_fixture(
        name="query_with_clarification_response",
        description="普通查询 + clarification_response（数据集选择回复）",
        question="销售数据集",
        intent="query",
        entities={},
        clarification_response={"selected_dataset_id": 1},
    ),
    make_fixture(
        name="query_with_filter",
        description="含 filter 实体：query_graph + 携带 filter",
        question="只看华东的销售额",
        intent="query",
        entities={"metrics": ["销售额"], "filters": [{"raw": "华东"}]},
    ),
    # === function × 4 ===
    make_fixture(
        name="function_with_pending_dataset",
        description="function + dataset_id 锁定 + pending 澄清态 → 降级为 query",
        question="选销售数据集",
        intent="function",
        entities={},
        dataset_id=1,
        multiturn_context={
            "pending_clarification": {"kind": "dataset_choice"},
        },
    ),
    make_fixture(
        name="function_without_pending",
        description="function + 无 dataset_id + 无 pending → reject 拒答",
        question="帮我导出报表",
        intent="function",
        entities={},
        dataset_id=None,
    ),
    make_fixture(
        name="function_with_pending_no_kind",
        description="function + dataset 锁定 + pending 缺 kind → reject（安全默认）",
        question="帮我重置",
        intent="function",
        entities={},
        dataset_id=1,
        multiturn_context={"pending_clarification": {}},
    ),
    make_fixture(
        name="function_with_term_clarification",
        description="function + dataset 锁定 + pending.kind=term_conflict_clarification → 降级 query",
        question="GMV",
        intent="function",
        entities={},
        dataset_id=1,
        multiturn_context={
            "pending_clarification": {
                "kind": "term_conflict_clarification",
            },
        },
    ),
    # === permission × 2 ===
    make_fixture(
        name="permission_denied_chinese",
        description="中文权限模式 '权限不足' → reject / permission_denied",
        question="查询受限数据，权限不足怎么办",
        intent="query",
        entities={},
    ),
    make_fixture(
        name="permission_denied_english",
        description="英文权限模式 'forbidden' → reject / permission_denied",
        question="this request is forbidden",
        intent="query",
        entities={},
    ),
    # === knowledge × 2 ===
    make_fixture(
        name="knowledge_no_term",
        description="知识问答 + 无业务术语匹配（dataset_id=None） → knowledge_qa + term_id=None",
        question="GMV 是什么意思",
        intent="query",
        entities={},
        dataset_id=None,
    ),
    make_fixture(
        name="knowledge_with_clarification_pending",
        description="知识问答 + 有 pending 澄清态（dataset_id=1 仍查不到术语）",
        question="毛利率口径",
        intent="query",
        entities={},
        dataset_id=1,
        multiturn_context={
            "pending_clarification": {"kind": "term_conflict_clarification"},
        },
    ),
    # === detail × 1 ===
    make_fixture(
        name="detail_query",
        description="明细查询模式 '明细' → query_graph / detail_query",
        question="查看本月订单明细",
        intent="query",
        entities={},
    ),
    # === blueprint_like × 2 ===
    make_fixture(
        name="blueprint_like_unmatched",
        description="含 '分析' 但无 metric/dimension 实体 → clarification",
        question="做下分析",
        intent="query",
        entities={},
    ),
    make_fixture(
        name="blueprint_like_with_metric",
        description="含 '分析' 且有 metric 实体 → query_graph / metric_query",
        question="销售归因分析",
        intent="query",
        entities={"metrics": ["销售额"]},
    ),
    # === short_ambiguous × 1 ===
    make_fixture(
        name="short_ambiguous_continue",
        description="短句 '继续' 含 '继续' 词 → clarification / missing=query_target",
        question="继续",
        intent="query",
        entities={},
    ),
    # === default_clarification × 2 ===
    make_fixture(
        name="default_clarification_long",
        description="长问题无任何模式 → clarification / missing=intent",
        question="我想了解一些关于数据方面的情况",
        intent="query",
        entities={},
    ),
    make_fixture(
        name="default_clarification_ambiguous_short",
        description="短问题无 'metrics' 模式 → default clarification",
        question="数据",
        intent="query",
        entities={},
    ),
    # === 边界 × 1 ===
    make_fixture(
        name="chitchat_with_dataset_locked",
        description="chitchat 路径 dataset_id 锁定（不影响 direct_answer 判定）",
        question="你好啊",
        intent="chitchat",
        entities={},
        dataset_id=1,
    ),
]


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as fp:
        for fixture in FIXTURES:
            fp.write(json.dumps(fixture, ensure_ascii=False, sort_keys=False))
            fp.write("\n")
            print(
                f"captured {fixture['name']}: "
                f"entry_intent={fixture['expected_output'].get('entry_intent')!r}, "
                f"entry_route={fixture['expected_output'].get('entry_route')!r}"
            )
    print(f"wrote {len(FIXTURES)} fixtures to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
