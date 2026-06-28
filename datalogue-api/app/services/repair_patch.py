# ============================================================
# File Name   : repair_patch.py
# Description:
#   RepairPatch Engine PR1 离线内核。
#
# Responsibilities:
#   - 从当前数据集已治理语义资产和已选字段生成字段修复候选。
#   - 生成、校验并应用 query_graph / compiler binding 字段级 patch。
#   - 输出用户可见脱敏摘要和 trace-only 字段级详情。
#
# Author      : yangkai
# Created On  : 2026-06-28
# ============================================================

from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.models.dataset import (
    DatasetSourceTable,
    SemanticDimension,
    SourceColumn,
    SourceTable,
)
from app.schemas.repair_plan import RepairFailureClass


CoarseType = Literal[
    "text_like",
    "date_like",
    "number_like",
    "boolean_like",
    "enum_like",
    "unknown",
]
PatchType = Literal["query_graph_patch", "compiler_binding_patch"]
OperationType = Literal["replace_logical_field", "replace_binding_field"]
ConfidenceBand = Literal["high", "medium", "blocked"]

_SQL_TEXT_RE = re.compile(
    r"(?is)\b(select|insert|update|delete|drop|alter|create|with)\b"
    r".{0,200}\b(from|into|set|table|join|where|values)\b"
)
_FORBIDDEN_PATCH_KEYS = {
    "sql",
    "raw_sql",
    "direct_sql",
    "llm_sql",
    "query_sql",
    "raw_result",
    "schema",
    "schema_context",
    "schema_dump",
    "control_plane",
}
_SAFE_PLACEHOLDER = "当前数据集候选字段"


class RepairPatchValidationError(ValueError):
    """RepairPatch 未通过 Tool 校验或 apply 失败时 fail-closed。"""


class FieldCandidate(BaseModel):
    """字段修复候选；仅供 Tool/trace 使用，不进入用户可见 payload。"""

    model_config = ConfigDict(extra="forbid")

    dataset_id: int
    datasource_id: int
    table_name: str
    column_name: str
    business_name: str
    business_description: str | None = None
    coarse_type: CoarseType = "unknown"
    source: Literal["semantic_asset", "selected_column"]
    selected: bool = True
    governance_status: str | None = None
    semantic_role: str | None = None

    @property
    def field_ref(self) -> str:
        """内部 trace 用字段引用；用户摘要不返回该值。"""

        return f"{self.table_name}.{self.column_name}"


class RepairPatchOperation(BaseModel):
    """单条字段替换操作；字段级详情只允许进入 trace-only。"""

    model_config = ConfigDict(extra="forbid")

    operation_type: OperationType
    source_field_intent: str
    replacement_field_ref: str
    reason: str
    target_path: list[str | int] | None = None
    binding_key: str | None = None


class RepairPatchValidation(BaseModel):
    """Tool 校验摘要；用户侧只看 summary，不看字段主体。"""

    model_config = ConfigDict(extra="forbid")

    status: Literal["validated", "blocked"] = "validated"
    summary: str = "修复方案已通过工具校验。"
    risk_flags: list[str] = Field(default_factory=list)


class RepairPatch(BaseModel):
    """RepairPatch v1 envelope；PR1 仅离线使用，不接主链。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "repair_patch.v1"
    patch_id: str = Field(default_factory=lambda: f"repair-patch-{uuid.uuid4().hex}")
    patch_type: PatchType
    dataset_id: int
    failure_class: RepairFailureClass
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_band: ConfidenceBand
    requires_user_confirmation: bool
    operations: list[RepairPatchOperation] = Field(default_factory=list)
    validation: RepairPatchValidation = Field(default_factory=RepairPatchValidation)
    trace_only_metadata: dict[str, Any] = Field(default_factory=dict)


class RepairPatchApplyResult(BaseModel):
    """Patch apply 的纯函数结果。"""

    model_config = ConfigDict(extra="forbid")

    patched_copy: dict[str, Any]
    diff_summary: dict[str, Any]
    trace_only_details: dict[str, Any]


class MockSemanticJudge:
    """离线测试用语义裁判；真实 LLM 裁判在后续 PR 接入。"""

    def __init__(self, *, equivalent: bool = True, score: float = 0.9, reason: str = "业务含义一致"):
        self.equivalent = equivalent
        self.score = score
        self.reason = reason

    def judge(self, prompt_input: dict[str, Any]) -> dict[str, Any]:
        """返回稳定裁判结构；prompt_input 已由 sanitizer 去除物理字段。"""

        return {
            "semantic_equivalent": self.equivalent,
            "semantic_score": round(float(self.score), 4),
            "business_reason": self.reason,
            "risk_flags": [],
        }


def normalize_coarse_type(data_type: str | None) -> CoarseType:
    """把数据源类型归一到 C2 粗粒度类型组。"""

    value = str(data_type or "").lower()
    if any(token in value for token in ("char", "text", "string", "uuid")):
        return "text_like"
    if any(token in value for token in ("date", "time", "timestamp")):
        return "date_like"
    if any(token in value for token in ("int", "decimal", "numeric", "number", "float", "double", "real")):
        return "number_like"
    if any(token in value for token in ("bool", "bit")):
        return "boolean_like"
    if "enum" in value:
        return "enum_like"
    return "unknown"


def _split_column_ref(column_name: str | None, fallback_table: str | None = None) -> tuple[str, str]:
    raw = str(column_name or "").strip()
    if "." in raw:
        table_name, col = raw.rsplit(".", 1)
        return table_name.strip(), col.strip()
    return str(fallback_table or "").strip(), raw


def _selected_source_columns(db: Session, *, dataset_id: int) -> list[tuple[SourceTable, SourceColumn]]:
    rows = (
        db.query(SourceTable, SourceColumn)
        .join(DatasetSourceTable, DatasetSourceTable.source_table_id == SourceTable.id)
        .join(SourceColumn, SourceColumn.table_id == SourceTable.id)
        .filter(DatasetSourceTable.dataset_id == dataset_id)
        .order_by(SourceTable.table_name.asc(), SourceColumn.ordinal_position.asc().nullslast(), SourceColumn.id.asc())
        .all()
    )
    return [(table, column) for table, column in rows]


def _column_lookup(db: Session, *, dataset_id: int) -> dict[tuple[str, str], SourceColumn]:
    lookup: dict[tuple[str, str], SourceColumn] = {}
    for table, column in _selected_source_columns(db, dataset_id=dataset_id):
        lookup[(table.table_name, column.column_name)] = column
    return lookup


def _candidate_from_source_column(
    *,
    dataset_id: int,
    table: SourceTable,
    column: SourceColumn,
    source: Literal["semantic_asset", "selected_column"],
    business_name: str | None = None,
    business_description: str | None = None,
    semantic_role: str | None = None,
) -> FieldCandidate:
    return FieldCandidate(
        dataset_id=dataset_id,
        datasource_id=int(table.datasource_id),
        table_name=str(table.table_name),
        column_name=str(column.column_name),
        business_name=business_name or column.column_comment or column.effective_desc or column.column_name,
        business_description=(
            business_description
            or column.effective_desc
            or column.user_description
            or column.ai_description
            or column.column_comment
        ),
        coarse_type=normalize_coarse_type(column.data_type),
        source=source,
        selected=True,
        governance_status=column.review_status,
        semantic_role=semantic_role or column.user_semantic_role or column.ai_semantic_role or column.semantic_role,
    )


def collect_field_candidates(
    db: Session,
    *,
    dataset_id: int,
    failed_field_intent_summary: str,
) -> list[FieldCandidate]:
    """从当前数据集生成字段候选；语义资产优先，fallback 到 selected columns。"""

    del failed_field_intent_summary  # PR1 先返回安全候选集，排序和分数由后续 scorer 处理。
    selected_pairs = _selected_source_columns(db, dataset_id=dataset_id)
    selected_tables = {table.table_name: table for table, _ in selected_pairs}
    selected_columns = _column_lookup(db, dataset_id=dataset_id)
    candidates: list[FieldCandidate] = []
    seen: set[tuple[str, str]] = set()

    dimensions = (
        db.query(SemanticDimension)
        .filter(SemanticDimension.dataset_id == dataset_id)
        .order_by(SemanticDimension.id.asc())
        .all()
    )
    for dimension in dimensions:
        table_name, column_name = _split_column_ref(dimension.column_name, dimension.table_name)
        column = selected_columns.get((table_name, column_name))
        table = selected_tables.get(table_name)
        if not table or not column:
            continue  # 语义资产如果指向未选字段，也不能成为候选。
        key = (table_name, column_name)
        candidates.append(
            _candidate_from_source_column(
                dataset_id=dataset_id,
                table=table,
                column=column,
                source="semantic_asset",
                business_name=dimension.display_name or dimension.name,
                business_description="/".join(dimension.synonyms or []) or dimension.display_name,
                semantic_role="enum" if dimension.enum_values else None,
            )
        )
        seen.add(key)

    for table, column in selected_pairs:
        key = (table.table_name, column.column_name)
        if key in seen:
            continue
        candidates.append(
            _candidate_from_source_column(
                dataset_id=dataset_id,
                table=table,
                column=column,
                source="selected_column",
            )
        )
    return candidates


def build_semantic_judge_prompt_input(
    *,
    question_intent_summary: str,
    failed_field_intent_summary: str,
    candidate: FieldCandidate,
) -> dict[str, Any]:
    """构造 LLM 语义裁判输入；不包含物理字段名、表名、SQL 或 schema。"""

    source_label = "governed_asset" if candidate.source == "semantic_asset" else "current_dataset"
    # 语义裁判只看业务词；当字段缺少治理描述时，不能把物理列名 fallback 给 LLM。
    business_name = _safe_business_text(candidate.business_name, candidate=candidate, max_len=120)
    business_description = _safe_business_text(candidate.business_description, candidate=candidate, max_len=300)
    return {
        "question_intent_summary": str(question_intent_summary or "")[:300],
        "failed_field_intent_summary": str(failed_field_intent_summary or "")[:160],
        "candidate_business_name": business_name,
        "candidate_business_description": business_description,
        "candidate_coarse_type": candidate.coarse_type,
        "candidate_source": source_label,
        "candidate_governance_status": candidate.governance_status or "unknown",
    }


def merge_confidence(
    *,
    rule_score: float,
    semantic_judgement: dict[str, Any],
    hard_constraints_ok: bool,
    type_compatible: bool,
) -> dict[str, Any]:
    """合并规则分和语义裁判分；Tool 是最终裁判并负责 clamp。"""

    clamped_rule_score = min(max(float(rule_score), 0.0), 1.0)
    if not hard_constraints_ok or not type_compatible:
        return {"confidence": 0.0, "confidence_band": "blocked", "requires_user_confirmation": False}
    semantic_score = min(max(float(semantic_judgement.get("semantic_score") or 0.0), 0.0), 1.0)
    equivalent = bool(semantic_judgement.get("semantic_equivalent"))
    if not equivalent:
        return {"confidence": min(round(clamped_rule_score, 2), 0.59), "confidence_band": "blocked", "requires_user_confirmation": False}
    if clamped_rule_score >= 0.85 and semantic_score >= 0.85:
        confidence = round((clamped_rule_score + semantic_score) / 2, 2)
    else:
        confidence = min(round(max(clamped_rule_score, semantic_score), 2), 0.84)
    if confidence >= 0.85:
        return {"confidence": confidence, "confidence_band": "high", "requires_user_confirmation": False}
    if confidence >= 0.60:
        return {"confidence": confidence, "confidence_band": "medium", "requires_user_confirmation": True}
    return {"confidence": confidence, "confidence_band": "blocked", "requires_user_confirmation": False}


def _field_ref(candidate: FieldCandidate) -> str:
    return candidate.field_ref


def _safe_business_text(value: str | None, *, candidate: FieldCandidate, max_len: int) -> str:
    """清理进入 LLM/用户摘要的业务文本，避免物理字段、表名或 SQL 混入。"""

    text = str(value or "").strip()
    lowered = text.lower()
    blocked_fragments = {
        candidate.table_name.lower(),
        candidate.column_name.lower(),
        candidate.field_ref.lower(),
    }
    if not text:
        return _SAFE_PLACEHOLDER
    # 这里不尝试“部分脱敏”，因为字段名常常是完整语义载体；命中后直接换成业务占位更稳。
    if _SQL_TEXT_RE.search(text) or any(fragment and fragment in lowered for fragment in blocked_fragments):
        return _SAFE_PLACEHOLDER
    return text[:max_len]


def _safe_summary_text(value: str | None, *, fallback: str) -> str:
    """用户可见摘要只允许业务级短句；命中执行细节时退回固定文案。"""

    text = str(value or "").strip()
    if not text:
        return fallback
    lowered = text.lower()
    if _SQL_TEXT_RE.search(text) or any(token in lowered for token in ("schema", "raw_sql", "query_plan", "raw_result")):
        return fallback
    return text[:160]


def build_repair_patch(
    *,
    patch_type: PatchType,
    dataset_id: int,
    failure_class: RepairFailureClass,
    target: dict[str, Any],
    replacement: FieldCandidate,
    rule_score: float,
    semantic_judgement: dict[str, Any],
) -> RepairPatch:
    """生成最小 RepairPatch envelope；最终可执行性仍由 validate/apply 决定。"""

    confidence = merge_confidence(
        rule_score=rule_score,
        semantic_judgement=semantic_judgement,
        hard_constraints_ok=True,
        type_compatible=True,
    )
    if patch_type == "query_graph_patch":
        operation = RepairPatchOperation(
            operation_type="replace_logical_field",
            source_field_intent=str(target.get("field_intent") or ""),
            replacement_field_ref=_field_ref(replacement),
            reason="按业务口径替换 QueryGraph 字段引用。",
            target_path=list(target.get("target_path") or []),
        )
    else:
        operation = RepairPatchOperation(
            operation_type="replace_binding_field",
            source_field_intent=str(target.get("field_intent") or ""),
            replacement_field_ref=_field_ref(replacement),
            reason="按业务口径替换编译绑定字段。",
            binding_key=str(target.get("binding_key") or ""),
        )
    return RepairPatch(
        patch_type=patch_type,
        dataset_id=dataset_id,
        failure_class=failure_class,
        confidence=confidence["confidence"],
        confidence_band=confidence["confidence_band"],
        requires_user_confirmation=confidence["requires_user_confirmation"],
        operations=[operation],
        trace_only_metadata={
            "replacement_field_ref": _field_ref(replacement),
            "candidate_source": replacement.source,
            "candidate_coarse_type": replacement.coarse_type,
            "semantic_judgement": semantic_judgement,
        },
    )


def _contains_forbidden_patch_payload(value: Any, *, key_name: str = "") -> bool:
    key = key_name.lower()
    if key in _FORBIDDEN_PATCH_KEYS or key.endswith("_sql"):
        return True
    if isinstance(value, dict):
        return any(
            _contains_forbidden_patch_payload(item, key_name=str(item_key))
            for item_key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_patch_payload(item, key_name=key_name) for item in value)
    if isinstance(value, str):
        return _SQL_TEXT_RE.search(value) is not None
    return False


def _candidate_key(candidate: FieldCandidate) -> tuple[int, str, str]:
    return (int(candidate.dataset_id), candidate.table_name, candidate.column_name)


def _type_compatible(actual: CoarseType, expected: CoarseType | None) -> bool:
    if expected is None:
        return True
    if actual == expected:
        return True
    return {actual, expected} == {"enum_like", "text_like"}


def validate_repair_patch(
    patch: RepairPatch,
    *,
    candidates: list[FieldCandidate],
    dataset_id: int,
    expected_type_group: CoarseType | None = None,
) -> RepairPatch:
    """Tool 层校验 patch；跨数据集、未选字段、SQL 注入、类型冲突直接拒绝。"""

    if int(patch.dataset_id) != int(dataset_id):
        raise RepairPatchValidationError("repair patch dataset mismatch")
    if not patch.operations:
        raise RepairPatchValidationError("repair patch has no operations")
    if _contains_forbidden_patch_payload(patch.model_dump(mode="json")):
        raise RepairPatchValidationError("repair patch contains forbidden executable detail")
    candidate_index = {_candidate_key(candidate): candidate for candidate in candidates if candidate.selected}
    for operation in patch.operations:
        replacement = operation.replacement_field_ref
        if "." not in replacement:
            raise RepairPatchValidationError("repair patch replacement is not a field ref")
        table_name, column_name = replacement.rsplit(".", 1)
        candidate = candidate_index.get((int(dataset_id), table_name, column_name))
        if not candidate:
            raise RepairPatchValidationError("replacement field is not selected in current dataset")
        if not _type_compatible(candidate.coarse_type, expected_type_group):
            raise RepairPatchValidationError("replacement field type is incompatible")
        if patch.patch_type == "query_graph_patch" and operation.operation_type != "replace_logical_field":
            raise RepairPatchValidationError("invalid query graph operation")
        if patch.patch_type == "compiler_binding_patch" and operation.operation_type != "replace_binding_field":
            raise RepairPatchValidationError("invalid compiler binding operation")
    return patch


def _set_path(target: dict[str, Any], path: list[str | int], value: Any) -> None:
    if not path:
        raise RepairPatchValidationError("query graph target path is empty")
    node: Any = target
    for part in path[:-1]:
        if isinstance(part, int):
            if not isinstance(node, list) or part >= len(node):
                raise RepairPatchValidationError("query graph target path does not exist")
            node = node[part]
        else:
            if not isinstance(node, dict) or part not in node:
                raise RepairPatchValidationError("query graph target path does not exist")
            node = node[part]
    last = path[-1]
    if isinstance(last, int):
        if not isinstance(node, list) or last >= len(node):
            raise RepairPatchValidationError("query graph target path does not exist")
        node[last] = value
    else:
        if not isinstance(node, dict) or last not in node:
            raise RepairPatchValidationError("query graph target path does not exist")
        node[last] = value


def apply_repair_patch(original: dict[str, Any], patch: RepairPatch) -> RepairPatchApplyResult:
    """纯函数 apply；失败不会修改原对象。"""

    patched = copy.deepcopy(original)
    trace_operations: list[dict[str, Any]] = []
    for operation in patch.operations:
        if patch.patch_type == "query_graph_patch":
            _set_path(patched, operation.target_path or [], operation.replacement_field_ref)
        elif patch.patch_type == "compiler_binding_patch":
            bindings = patched.get("bindings")
            if not isinstance(bindings, dict) or operation.binding_key not in bindings:
                raise RepairPatchValidationError("compiler binding target does not exist")
            bindings[operation.binding_key] = operation.replacement_field_ref
        else:
            raise RepairPatchValidationError("unsupported patch type")
        trace_operations.append(operation.model_dump(mode="json"))
    return RepairPatchApplyResult(
        patched_copy=patched,
        diff_summary={
            "summary": f"已按业务口径替换 {len(trace_operations)} 处字段引用。",
            "operation_count": len(trace_operations),
        },
        trace_only_details={
            "patch_id": patch.patch_id,
            "patch_type": patch.patch_type,
            "operations": trace_operations,
        },
    )


def sanitize_repair_patch_summary(patch: RepairPatch) -> dict[str, Any]:
    """生成用户可见 RepairPatch 摘要，不包含字段名、表名、schema、SQL 或 operations。"""

    validation_summary = _safe_summary_text(
        patch.validation.summary,
        fallback="修复方案已通过工具校验。",
    )
    # risk_flags 只保留稳定机器枚举，避免把外部返回的解释性文本带到用户面。
    risk_flags = [
        item
        for item in patch.validation.risk_flags
        if re.fullmatch(r"[a-z0-9_]{1,64}", str(item or ""))
        and item not in {"schema", "raw_sql", "query_plan", "raw_result"}
    ]
    return {
        "schema_version": patch.schema_version,
        "patch_id": patch.patch_id,
        "repair_strategy": "按业务口径自动修复字段引用。",
        "failure_class": patch.failure_class,
        "confidence": patch.confidence,
        "confidence_band": patch.confidence_band,
        "requires_user_confirmation": patch.requires_user_confirmation,
        "validation_summary": validation_summary,
        "risk_flags": risk_flags,
    }
