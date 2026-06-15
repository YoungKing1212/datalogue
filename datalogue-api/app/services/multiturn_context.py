"""
MultiturnContextBuilder — 把 SubAgent 多轮合并核心抽到 services 层。

设计原则（Phase 1 范围）：
- Builder 只返回纯合并决策 MergeDecision（dataclass），不触碰 LangGraph 路由字段、
  `out_capsule` 或最终 output dict 的组装。
- 节点 `merge_prior_context_node` 仍是薄壳：调 builder 后用 decision 字段组装 LangGraph
  output dict。
- `build_out_capsule` 仍由 nodes.py 拥有，builder 不直接 import；通过 `out_capsule_factory`
  依赖注入让 builder 在 interpret 早退 payload 中携带 out_capsule。
- helper 函数（_as_dict / _as_list / _normalized_text / _contains_any / _dedupe_* /
  _coerce_int_or_original）从 nodes.py 复制过来，避免 services→graph 反向依赖；
  Phase 2 整改时会抽到 `app/utils/dict_helpers.py`。
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from fastapi.encoders import jsonable_encoder

from app.core.config import get_settings


# 入口分类与时间 delta 关键词（与 nodes.py 同步）
_CONTINUE_PATTERNS: tuple[str, ...] = (
    "继续",
    "再",
    "也",
    "换成",
    "改成",
    "改为",
    "只看",
    "仅看",
    "筛选",
    "按",
    "拆分",
    "分组",
    "排名",
    "上面",
    "刚才",
    "这个",
    "那个",
    "同比",
    "环比",
)

_TIME_DELTA_PATTERNS: tuple[str, ...] = (
    "今天",
    "昨天",
    "本周",
    "上周",
    "本月",
    "上月",
    "上个月",
    "今年",
    "去年",
    "最近",
    "近",
)


# ============================================================
# Helper（与 nodes.py 同步；DRY 违反 Phase 2 整改）
# ============================================================


def _as_dict(value: Any) -> dict:
    """把未知状态片段安全收敛为 dict，避免多轮胶囊污染主状态。"""
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    """把未知状态片段安全收敛为 list。"""
    return value if isinstance(value, list) else []


def _normalized_text(text: str) -> str:
    """归一化问题文本，便于做确定性入口路由匹配。"""
    return re.sub(r"\s+", "", (text or "").lower())


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    """判断文本是否包含任意入口分类关键词。"""
    return any(pattern in text for pattern in patterns)


def _dedupe_jsonable(items: list) -> list:
    """对 JSON 友好对象做稳定去重，保留首次出现顺序。"""
    output: list = []
    seen: set = set()
    for item in items:
        key = json.dumps(
            jsonable_encoder(item), ensure_ascii=False, sort_keys=True, default=str
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _semantic_match_text(text: Any) -> str:
    """统一语义资产匹配用文本，忽略大小写、空白、下划线和常见引用符。"""
    if text is None:
        return ""
    return re.sub(r"[\s_`'\".]+", "", str(text).strip().lower())


def _dedupe_texts(values: list) -> list:
    """按语义匹配规则去重，保留原始展示文本。"""
    out: list = []
    seen: set = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        norm = _semantic_match_text(text)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(text)
    return out


def _coerce_int_or_original(value: Any) -> Any:
    """把字符串数字转 int；其他原值返回。"""
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


# ============================================================
# MergeDecision
# ============================================================


@dataclass
class MergeDecision:
    """Builder 输出的纯合并决策；节点薄壳据此组装 LangGraph output dict。

    字段：
    - turn_type: "interpret" | "new" | "new_query" | "continue"
    - multiturn_context: dict | None（DSL 生成 prompt 注入用）
    - synthesized_question: str | None（continue 时填"基于上一轮问题『…』，…"补全文本）
    - blueprint_shortcut: dict | None（候选 + enabled 标志；节点据此决定是否走 blueprint_execute）
    - interpret_payload: dict | None（仅 interpret 早退时填，含
      answer/entry_intent/entry_route/multiturn_context/merge_debug/should_retry；如 builder
      注入了 out_capsule_factory 则额外含 out_capsule）
    - merge_debug: dict（观测 trace 用）
    """

    turn_type: str
    multiturn_context: dict | None = None
    synthesized_question: str | None = None
    blueprint_shortcut: dict | None = None
    interpret_payload: dict | None = None
    merge_debug: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# MultiturnContextBuilder
# ============================================================


class MultiturnContextBuilder:
    """把 `merge_prior_context_node` 内的 11 个私有函数抽到 services 层。

    Builder 不导入 `app.graph.nodes`（保护 services→graph 边界）。
    节点薄壳负责：
    1. `builder = MultiturnContextBuilder(out_capsule_factory=build_out_capsule)`
    2. `decision = builder.build(state)`
    3. 把 decision 字段映射到 LangGraph output dict（4 个分支各保留 ~10 行模板）。
    """

    def __init__(self, out_capsule_factory: Callable | None = None) -> None:
        """out_capsule_factory: interpret 早退时用来组装 out_capsule 的可调用对象。
        默认 None 时 interpret_payload 不含 out_capsule（builder 不假设下游 schema）。
        """
        self._out_capsule_factory = out_capsule_factory

    # ----- 内部辅助（业务） -----

    def _lead_multiturn_intent(self, state: dict) -> str | None:
        lead_agent_context = _as_dict(state.get("lead_agent_context"))
        classification = _as_dict(lead_agent_context.get("multiturn_classification"))
        intent = str(classification.get("intent") or "").strip().lower()
        return intent or None

    def _dispatch_capsule(self, state: dict) -> dict:
        lead_agent_context = _as_dict(state.get("lead_agent_context"))
        dispatch = _as_dict(lead_agent_context.get("dispatch"))
        return _as_dict(dispatch.get("capsule") or dispatch.get("subagent_capsule"))

    # ----- 12 个迁自 nodes.py 的方法（去下划线前缀） -----

    def is_interpret_result_turn(self, state: dict) -> bool:
        """判 interpret_result 早退：dispatch.execution_mode / should_generate_query / lead intent。"""
        capsule = self._dispatch_capsule(state)
        return (
            capsule.get("execution_mode") == "interpret_result"
            or capsule.get("should_generate_query") is False
            or self._lead_multiturn_intent(state) == "interpret"
        )

    def is_continue_turn(self, state: dict, prior_query_context: dict) -> bool:
        """判断本轮是否应按承接上一轮处理；显式 turn_type 优先。"""
        explicit = str(state.get("turn_type") or "").strip().lower()
        if explicit in {"continue", "follow_up", "followup", "interpret"}:
            return True
        if explicit == "new":
            return False
        if self._lead_multiturn_intent(state) in {"continue", "interpret"}:
            return bool(prior_query_context)
        if not prior_query_context:
            return False
        q_norm = _normalized_text(state.get("question") or "")
        return _contains_any(q_norm, _CONTINUE_PATTERNS)

    def extract_dimension_delta(self, question: str) -> list:
        """从追问短句里提取"按 X 拆分/分组/统计"的原始维度短语。"""
        dimensions: list = []
        patterns = (
            r"按(.+?)(?:拆分|分组|统计|汇总|看|排名)",
            r"(?:拆分|分组)到(.+)",
            r"(?:按|从)(.+?)(?:维度|口径)",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, question):
                raw = re.split(r"[，,。；;、\s]", match.group(1).strip())[0]
                if raw:
                    dimensions.append(raw)
        return _dedupe_texts(dimensions)

    def extract_filter_delta(self, question: str) -> list:
        """提取"只看/仅看/筛选"类原始过滤条件，后续由 DSL LLM 映射到语义资产。"""
        filters: list = []
        for pattern in (r"(?:只看|仅看|筛选|限定)(.+)", r"(?:换成|改成|改为)(.+)"):
            match = re.search(pattern, question)
            if not match:
                continue
            text = match.group(1).strip(" ，,。；;")
            if text:
                filters.append({"raw": text, "source": "question_delta"})
        return filters

    def extract_time_delta(self, question: str) -> dict | None:
        """提取本轮追问中的时间表达；不做日期推理，只保留确定性原文。"""
        q_norm = _normalized_text(question)
        if not _contains_any(q_norm, _TIME_DELTA_PATTERNS):
            return None
        recent_match = re.search(r"(最近|近)(\d+)(天|日|周|月|年)", question)
        if recent_match:
            return {
                "raw": recent_match.group(0),
                "kind": "relative_recent",
                "amount": int(recent_match.group(2)),
                "unit": recent_match.group(3),
            }
        for token in _TIME_DELTA_PATTERNS:
            if token in q_norm:
                return {"raw": token, "kind": "relative_named"}
        return None

    def extract_limit_delta(self, question: str) -> int | None:
        """提取 TopN/前 N 这类返回条数限制。"""
        match = re.search(r"(?:top|前)\s*(\d+)", question, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            return max(1, int(match.group(1)))
        except ValueError:
            return None

    def derive_multiturn_delta(self, question: str) -> dict:
        """基于当前追问生成确定性 delta，不做 schema 绑定。"""
        delta: dict = {
            "question": question,
            "dimensions": self.extract_dimension_delta(question),
            "filters": self.extract_filter_delta(question),
        }
        time_delta = self.extract_time_delta(question)
        if time_delta:
            delta["time_range"] = time_delta
        limit = self.extract_limit_delta(question)
        if limit is not None:
            delta["limit"] = limit
        operations: list = []
        q_norm = _normalized_text(question)
        if delta["dimensions"]:
            operations.append("add_dimension")
        if delta["filters"]:
            operations.append("add_filter")
        if time_delta:
            operations.append("change_time_range")
        if limit is not None or "排名" in q_norm:
            operations.append("rank_or_limit")
        if "同比" in q_norm or "环比" in q_norm:
            operations.append("compare")
        if "同比" in q_norm or "环比" in q_norm:
            delta["comparison"] = "同比" if "同比" in q_norm else "环比"
        delta_type = (
            "compare"
            if "compare" in operations
            else "drill"
            if delta["dimensions"]
            else "refine"
            if operations
            else "refine"
        )
        delta["operations"] = operations or ["follow_up"]
        delta["delta_type"] = delta_type
        return delta

    def merge_query_context(
        self,
        prior_query_context: dict,
        delta: dict,
        *,
        question: str,
    ) -> dict:
        """确定性合并上一轮 query_context 和本轮 delta。"""
        merged = copy.deepcopy(prior_query_context)
        merged["question"] = question
        merged["source"] = "multiturn_merge"

        if delta.get("dimensions"):
            merged["dimensions"] = _dedupe_jsonable(
                _as_list(merged.get("dimensions")) + _as_list(delta.get("dimensions"))
            )
        if delta.get("filters"):
            merged["filters"] = _dedupe_jsonable(
                _as_list(merged.get("filters")) + _as_list(delta.get("filters"))
            )
        if delta.get("time_range"):
            merged["time_range"] = delta["time_range"]
        if delta.get("limit") is not None:
            merged["limit"] = delta["limit"]
        return merged

    def has_query_target(self, query_context: dict) -> bool:
        """判断上一轮上下文是否有可承接的查询目标。"""
        query_type = query_context.get("query_type")
        if query_type == "detail_query":
            return bool(
                query_context.get("fields")
                or query_context.get("main_table")
                or query_context.get("query_plan")
                or query_context.get("dsl")
            )
        metrics = query_context.get("metrics")
        if isinstance(metrics, list):
            return bool(metrics)
        return bool(metrics)

    def has_query_metrics(self, query_context: dict) -> bool:
        """兼容旧调用名；新语义由 has_query_target 统一承载。"""
        return self.has_query_target(query_context)

    def blueprint_shortcut_candidate(
        self,
        prior_query_context: dict,
        delta: dict,
    ) -> dict | None:
        """识别仍落在上一轮蓝图参数空间内的追问，仅返回候选字典本身。

        `settings_enabled` 由 builder 在外层叠加（合并 settings 开关判断），节点据此决定
        是否走 blueprint_execute 路由。返回 dict 不带 enabled 字段以避免和 settings 标志
        混淆。
        """
        blueprint_id = prior_query_context.get("blueprint_id")
        routing_path = prior_query_context.get("routing_path")
        if not blueprint_id and routing_path != "blueprint":
            return None
        unsupported = {"add_dimension", "compare"}
        operations = set(delta.get("operations") or [])
        if operations & unsupported:
            return None
        return {
            "blueprint_id": _coerce_int_or_original(blueprint_id),
            "reason": "delta 仅调整过滤、时间或返回条数，仍可复用上一轮蓝图参数空间。",
        }

    def blueprint_shortcut_enabled(self) -> bool:
        """从 app.core.config 读 settings（不再依赖 app.graph.nodes.get_settings）。"""
        return bool(getattr(get_settings(), "MULTITURN_BLUEPRINT_SHORTCUT_ENABLED", False))

    def prior_query_context(self, prior_capsule: dict) -> dict:
        """从上一轮 SubAgent capsule 中提取可继续追问的查询上下文。"""
        for key in ("query_context", "merged_query_context", "dsl"):
            value = prior_capsule.get(key)
            if isinstance(value, dict):
                return copy.deepcopy(value)
        multiturn = _as_dict(prior_capsule.get("multiturn_context"))
        value = multiturn.get("merged_query_context")
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def task_capsule_prior_query_context(self, state: dict) -> dict:
        """从 Task Capsule 的上一轮基础查询计划构造最小 prior 上下文。"""
        capsule = _as_dict(state.get("query_task_capsule"))
        if capsule.get("turn_type") != "followup_refine":
            return {}
        if capsule.get("base_task_ref") != "last_success_task":
            return {}
        capsule_dataset_id = capsule.get("dataset_id")
        state_dataset_id = state.get("dataset_id")
        if (
            capsule_dataset_id is not None
            and state_dataset_id is not None
            and str(capsule_dataset_id) != str(state_dataset_id)
        ):
            return {}
        base_query_plan = _as_dict(capsule.get("base_query_plan"))
        base_main_table = capsule.get("base_main_table")
        if not base_query_plan and not base_main_table:
            return {}
        prior_context: dict = {}
        query_type = base_query_plan.get("query_type") or capsule.get("query_type")
        if query_type:
            prior_context["query_type"] = query_type
        if base_query_plan:
            prior_context["query_plan"] = copy.deepcopy(base_query_plan)
        if base_main_table:
            prior_context["main_table"] = base_main_table
        question = capsule.get("base_question")
        if question:
            prior_context["question"] = question
        return prior_context

    def prior_question(self, prior_capsule: dict, query_context: dict) -> str:
        """读取上一轮问题文本，作为继续追问时的问题补全来源。"""
        return str(
            prior_capsule.get("resolved_question")
            or prior_capsule.get("question")
            or query_context.get("question")
            or ""
        ).strip()

    def build_interpret_answer(self, question: str, prior_capsule: dict) -> str:
        """基于上一轮 ResultDigest 生成轻量解释，避免 interpret 轮次重新查询。"""
        digest = _as_dict(
            prior_capsule.get("result_digest") or prior_capsule.get("last_result_digest")
        )
        if not digest:
            return "上一轮结果摘要已经失效或不存在，无法直接解释。你可以重新发起查询。"
        columns = digest.get("columns") or []
        column_names = [
            str(item.get("name") or item.get("column") or item)
            for item in columns
            if isinstance(item, (dict, str))
        ]
        numeric = _as_dict(digest.get("numeric_summary"))
        highlights = _as_dict(digest.get("highlights"))
        lines = ["这轮是对上一轮结果的解释，不会重新生成 SQL。"]
        lines.append(
            f"上一轮返回 {digest.get('row_count', 0)} 行，"
            f"字段包括：{', '.join(column_names) or '无字段摘要'}。"
        )
        if numeric:
            metric_bits = []
            for name, stats in numeric.items():
                if not isinstance(stats, dict):
                    continue
                metric_bits.append(
                    f"{name}: min={stats.get('min')}, max={stats.get('max')}, sum={stats.get('sum')}"
                )
            if metric_bits:
                lines.append("数值摘要：" + "；".join(metric_bits[:5]) + "。")
        if highlights:
            lines.append("摘要要点：" + json.dumps(highlights, ensure_ascii=False)[:500])
        audit_id = digest.get("sql_audit_id")
        if audit_id:
            lines.append(f"可通过 SQL 审计记录 {audit_id} 回看原查询。")
        return "\n".join(lines)

    # ----- 主入口 -----

    def build(self, state: dict) -> MergeDecision:
        """组装 MergeDecision；节点薄壳据此拼 LangGraph output dict。"""
        prior_capsule = _as_dict(state.get("prior_capsule"))
        prior_query_context = self.prior_query_context(prior_capsule)
        if not prior_query_context:
            prior_query_context = self.task_capsule_prior_query_context(state)
        current_question = state.get("question") or ""

        if self.is_interpret_result_turn(state):
            answer = self.build_interpret_answer(current_question, prior_capsule)
            multiturn_context = {
                "turn_type": "interpret",
                "prior_available": bool(prior_query_context),
                "prior_query_context": prior_query_context or None,
                "delta": {"delta_type": "interpret", "operations": ["interpret_result"]},
                "merged_query_context": prior_query_context or None,
                "result_digest_available": bool(
                    prior_capsule.get("result_digest") or prior_capsule.get("last_result_digest")
                ),
            }
            merge_debug = {
                "used_prior": bool(prior_query_context),
                "reason": "interpret_result_from_prior_digest",
                "prior_keys": sorted(prior_capsule.keys()),
                "generated_query": False,
            }
            interpret_payload: dict = {
                "turn_type": "interpret",
                "entry_intent": "interpret",
                "entry_route": "interpret_result",
                "answer": answer,
                "multiturn_context": multiturn_context,
                "merge_debug": merge_debug,
                "should_retry": False,
                "error": None,
            }
            if self._out_capsule_factory is not None:
                interpret_payload["out_capsule"] = self._out_capsule_factory(
                    state, interpret_payload
                )
            return MergeDecision(
                turn_type="interpret",
                multiturn_context=multiturn_context,
                synthesized_question=None,
                blueprint_shortcut=None,
                interpret_payload=interpret_payload,
                merge_debug=merge_debug,
            )

        if not self.is_continue_turn(state, prior_query_context):
            turn_type = "new"
            multiturn_context = {
                "turn_type": turn_type,
                "prior_available": bool(prior_query_context),
                "prior_query_context": prior_query_context or None,
                "delta": None,
                "merged_query_context": None,
            }
            return MergeDecision(
                turn_type=turn_type,
                multiturn_context=multiturn_context,
                synthesized_question=None,
                blueprint_shortcut=None,
                interpret_payload=None,
                merge_debug={
                    "used_prior": False,
                    "reason": "no_prior_or_not_continue",
                    "prior_keys": sorted(prior_capsule.keys()),
                },
            )

        delta = self.derive_multiturn_delta(current_question)
        merged_query_context = self.merge_query_context(
            prior_query_context, delta, question=current_question
        )
        if not self.has_query_target(merged_query_context):
            multiturn_context = {
                "turn_type": "new_query",
                "prior_available": True,
                "prior_query_context": prior_query_context,
                "delta": delta,
                "merged_query_context": None,
            }
            return MergeDecision(
                turn_type="new",
                multiturn_context=multiturn_context,
                synthesized_question=None,
                blueprint_shortcut=None,
                interpret_payload=None,
                merge_debug={
                    "used_prior": False,
                    "reason": "merged_metrics_empty_downgraded_to_new_query",
                    "delta_operations": delta.get("operations") or [],
                    "prior_keys": sorted(prior_capsule.keys()),
                },
            )

        previous_question = self.prior_question(prior_capsule, prior_query_context)
        synthesized_question = current_question
        if previous_question and previous_question not in current_question:
            synthesized_question = (
                f"基于上一轮问题「{previous_question}」，{current_question}"
            )

        blueprint_shortcut = self.blueprint_shortcut_candidate(prior_query_context, delta)
        if blueprint_shortcut is not None:
            blueprint_shortcut = dict(blueprint_shortcut)
            # enabled=True 表示 candidate 合法（与 nodes.py 兼容）；settings_enabled
            # 区分 settings 开关，节点据此决定是否走 blueprint_execute 路由。
            blueprint_shortcut["enabled"] = True
            blueprint_shortcut["settings_enabled"] = self.blueprint_shortcut_enabled()
        multiturn_context = {
            "turn_type": "continue",
            "delta_type": delta.get("delta_type"),
            "prior_available": True,
            "prior_query_context": prior_query_context,
            "delta": delta,
            "merged_query_context": merged_query_context,
            "synthesized_question": synthesized_question,
            "blueprint_shortcut": blueprint_shortcut,
        }
        return MergeDecision(
            turn_type="continue",
            multiturn_context=multiturn_context,
            synthesized_question=synthesized_question,
            blueprint_shortcut=blueprint_shortcut,
            interpret_payload=None,
            merge_debug={
                "used_prior": True,
                "reason": "continue_turn_with_prior_query_context",
                "delta_type": delta.get("delta_type"),
                "delta_operations": delta.get("operations") or [],
                "rewrote_question": synthesized_question != current_question,
                "prior_keys": sorted(prior_capsule.keys()),
                "blueprint_shortcut": blueprint_shortcut,
            },
        )
