# ============================================================
# File Name   : dataset_manifest.py
# Description:
#   数据集 SubAgent Manifest 治理契约服务。
#
# Responsibilities:
#   - 派生 Manifest 自动字段和 schema 绑定版本。
#   - 管理 Manifest 草稿、发布、过期标记和路由自检。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app import models

DRAFT_VERSION = "draft"
MANUAL_FIELD_KEYS = (
    "description",
    "business_domain",
    "sample_questions",
    "routing_negative_examples",
)
LOW_INFORMATION_WORDS = ("等", "相关", "业务")
TIME_OR_SCOPE_TERMS = (
    "日",
    "周",
    "月",
    "年",
    "季度",
    "时间",
    "期间",
    "范围",
    "区域",
    "门店",
    "部门",
    "组织",
    "全国",
    "省",
    "市",
)


def normalize_manual_fields(value: dict[str, Any] | None) -> dict[str, Any]:
    """归一化人工维护字段，只保留 Manifest B 类允许写入的内容。"""

    raw = value or {}
    return {
        "description": str(raw.get("description") or "").strip(),
        "business_domain": _clean_text_list(raw.get("business_domain"), max_items=8),
        "sample_questions": _clean_text_list(raw.get("sample_questions"), max_items=10),
        "routing_negative_examples": _clean_text_list(
            raw.get("routing_negative_examples"), max_items=5
        ),
    }


def build_dataset_schema_version(db: Session, dataset_id: int) -> str:
    """基于语义资产和已选物理字段生成稳定 schema hash。"""

    dataset = db.get(models.SemanticDataset, dataset_id)
    if not dataset:
        return "missing"

    metrics = (
        db.query(models.SemanticMetric)
        .filter(models.SemanticMetric.dataset_id == dataset_id)
        .order_by(models.SemanticMetric.id)
        .all()
    )
    dimensions = (
        db.query(models.SemanticDimension)
        .filter(models.SemanticDimension.dataset_id == dataset_id)
        .order_by(models.SemanticDimension.id)
        .all()
    )
    links = (
        db.query(models.DatasetSourceTable)
        .filter(models.DatasetSourceTable.dataset_id == dataset_id)
        .order_by(models.DatasetSourceTable.id)
        .all()
    )
    selected_tables: list[dict[str, Any]] = []
    for link in links:
        table = link.source_table
        if not table:
            continue
        selected_tables.append(
            {
                "schema_name": table.schema_name,
                "table_name": table.table_name,
                "effective_desc": table.effective_desc,
                "synced_at": table.synced_at.isoformat() if table.synced_at else None,
                "columns": [
                    {
                        "column_name": col.column_name,
                        "data_type": col.data_type,
                        "effective_desc": col.effective_desc,
                        "semantic_role": col.user_semantic_role
                        or col.ai_semantic_role
                        or col.semantic_role,
                        "converted_metric_id": col.converted_metric_id,
                        "converted_dimension_id": col.converted_dimension_id,
                        "ordinal_position": col.ordinal_position,
                    }
                    for col in sorted(table.columns, key=lambda c: c.ordinal_position or 0)
                ],
            }
        )

    payload = {
        "dataset": {
            "id": dataset.id,
            "name": dataset.name,
            "tables_json": dataset.tables_json or {},
            "query_constraints": dataset.query_constraints or {},
        },
        "metrics": [
            {
                "name": item.name,
                "display_name": item.display_name,
                "expr": item.expr,
                "table_name": item.table_name,
                "time_field": item.time_field,
                "filter_sql": item.filter_sql,
                "synonyms": item.synonyms or [],
                "description": item.description,
            }
            for item in metrics
        ],
        "dimensions": [
            {
                "name": item.name,
                "display_name": item.display_name,
                "column_name": item.column_name,
                "table_name": item.table_name,
                "join_to": item.join_to,
                "join_key": item.join_key,
                "hierarchy": item.hierarchy or {},
                "enum_values": item.enum_values or [],
                "synonyms": item.synonyms or [],
            }
            for item in dimensions
        ],
        "selected_tables": selected_tables,
    }
    encoded = json.dumps(jsonable_encoder(payload), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def build_auto_fields(
    db: Session,
    dataset_id: int,
    *,
    manifest_version: str = DRAFT_VERSION,
    bound_schema_version: str | None = None,
) -> dict[str, Any]:
    """派生 Manifest A 类字段。"""

    dataset = db.get(models.SemanticDataset, dataset_id)
    if not dataset:
        raise ValueError("数据集不存在")
    schema_version = bound_schema_version or build_dataset_schema_version(db, dataset_id)
    metrics = (
        db.query(models.SemanticMetric)
        .filter(models.SemanticMetric.dataset_id == dataset_id)
        .order_by(models.SemanticMetric.id)
        .all()
    )
    dimensions = (
        db.query(models.SemanticDimension)
        .filter(models.SemanticDimension.dataset_id == dataset_id)
        .order_by(models.SemanticDimension.id)
        .all()
    )
    selected_links = (
        db.query(models.DatasetSourceTable)
        .filter(models.DatasetSourceTable.dataset_id == dataset_id)
        .order_by(models.DatasetSourceTable.id)
        .all()
    )
    selected_tables = [
        link.source_table.table_name
        for link in selected_links
        if link.source_table and link.source_table.table_name
    ]
    return {
        "dataset_id": dataset.id,
        "name": dataset.name,
        "version": manifest_version,
        "manifest_version": manifest_version,
        "bound_schema_version": schema_version,
        "key_metrics": [
            {
                "id": item.id,
                "name": item.name,
                "display_name": item.display_name,
                "description": item.description,
                "synonyms": item.synonyms or [],
            }
            for item in metrics[:20]
        ],
        "key_dimensions": [
            {
                "id": item.id,
                "name": item.name,
                "display_name": item.display_name,
                "column_name": item.column_name,
                "synonyms": item.synonyms or [],
            }
            for item in dimensions[:20]
        ],
        "permission_scope": {
            "status": "not_configured",
            "description": "当前未配置数据集级权限策略；按数据集绑定数据源和已选表范围执行。",
            "datasource_id": dataset.datasource_id,
            "selected_tables": selected_tables,
        },
    }


def lint_manifest(manual_fields: dict[str, Any], auto_fields: dict[str, Any]) -> list[dict[str, str]]:
    """校验人工字段质量，发布时 error 会阻断。"""

    manual = normalize_manual_fields(manual_fields)
    issues: list[dict[str, str]] = []
    description = manual["description"]
    if not description:
        issues.append(_issue("description_required", "error", "description 不能为空。"))
    elif len(description) < 80 or len(description) > 200:
        issues.append(_issue("description_length", "error", "description 建议保持 80-200 字。"))

    entity_terms = _entity_terms(auto_fields, manual)
    if description and not any(term and term in description for term in entity_terms):
        issues.append(
            _issue("description_entity", "error", "description 至少应包含一个业务实体、指标或维度。")
        )
    if description and not any(term in description for term in TIME_OR_SCOPE_TERMS):
        issues.append(_issue("description_scope", "error", "description 至少应包含时间或范围线索。"))
    vague_words = [word for word in LOW_INFORMATION_WORDS if word in description]
    if vague_words:
        issues.append(
            _issue(
                "description_vague",
                "error",
                f"description 包含低信息词：{', '.join(vague_words)}。",
            )
        )
    if not manual["business_domain"]:
        issues.append(_issue("business_domain_required", "error", "business_domain 至少选择一项。"))
    if len(manual["sample_questions"]) < 5 or len(manual["sample_questions"]) > 10:
        issues.append(_issue("sample_questions_count", "error", "sample_questions 需要维护 5-10 条。"))
    if (
        len(manual["routing_negative_examples"]) < 3
        or len(manual["routing_negative_examples"]) > 5
    ):
        issues.append(
            _issue(
                "routing_negative_examples_count",
                "error",
                "routing_negative_examples 需要维护 3-5 条。",
            )
        )
    return issues


def get_manifest_detail(db: Session, dataset_id: int) -> dict[str, Any]:
    """读取 manifest 治理详情，并在 current schema 过期时标记需复核。"""

    auto_preview = build_auto_fields(db, dataset_id, manifest_version=DRAFT_VERSION)
    current = _current_manifest(db, dataset_id)
    draft = _draft_manifest(db, dataset_id)
    stale = False
    if current and current.bound_schema_version != auto_preview["bound_schema_version"]:
        current.review_status = "needs_review"
        stale = True
        db.commit()
        db.refresh(current)
    manual_fields = _manifest_manual_fields(draft or current)
    lint = lint_manifest(manual_fields, auto_preview)
    return {
        "dataset_id": dataset_id,
        "current_manifest": current,
        "draft_manifest": draft,
        "auto_fields_preview": auto_preview,
        "manual_fields": manual_fields,
        "lint": lint,
        "stale": stale or bool(current and current.review_status == "needs_review"),
        "review_status": current.review_status if current else "missing",
    }


def save_manifest_draft(
    db: Session,
    dataset_id: int,
    manual_fields: dict[str, Any],
    *,
    created_by: str | None = None,
) -> models.DatasetSubAgentManifest:
    """保存 Manifest 人工字段草稿，不影响 current 版本。"""

    manual = normalize_manual_fields(manual_fields)
    auto_fields = build_auto_fields(db, dataset_id, manifest_version=DRAFT_VERSION)
    manifest = _draft_manifest(db, dataset_id)
    if not manifest:
        manifest = models.DatasetSubAgentManifest(
            dataset_id=dataset_id,
            manifest_version=DRAFT_VERSION,
            is_current=False,
            review_status="draft",
            created_by=created_by,
            bound_schema_version=auto_fields["bound_schema_version"],
            manifest_json={},
        )
        db.add(manifest)
    manifest.bound_schema_version = auto_fields["bound_schema_version"]
    manifest.review_status = "draft"
    manifest.created_by = created_by or manifest.created_by
    manifest.manifest_json = _manifest_payload(auto_fields, manual)
    db.commit()
    db.refresh(manifest)
    return manifest


def publish_manifest(
    db: Session,
    dataset_id: int,
    manual_fields: dict[str, Any] | None = None,
    *,
    created_by: str | None = None,
) -> models.DatasetSubAgentManifest:
    """发布 current Manifest，新版本与 schema hash 绑定。"""

    source_manual = normalize_manual_fields(manual_fields or _manifest_manual_fields(_draft_manifest(db, dataset_id)))
    version = _next_manifest_version(db, dataset_id)
    auto_fields = build_auto_fields(db, dataset_id, manifest_version=version)
    issues = lint_manifest(source_manual, auto_fields)
    errors = [issue for issue in issues if issue["severity"] == "error"]
    if errors:
        raise ManifestValidationError(errors)

    (
        db.query(models.DatasetSubAgentManifest)
        .filter(
            models.DatasetSubAgentManifest.dataset_id == dataset_id,
            models.DatasetSubAgentManifest.is_current.is_(True),
        )
        .update({"is_current": False, "review_status": "archived"}, synchronize_session=False)
    )
    manifest = models.DatasetSubAgentManifest(
        dataset_id=dataset_id,
        manifest_version=version,
        bound_schema_version=auto_fields["bound_schema_version"],
        manifest_json=_manifest_payload(auto_fields, source_manual, quality={"lint": issues}),
        is_current=True,
        review_status="current",
        created_by=created_by,
    )
    db.add(manifest)
    db.commit()
    db.refresh(manifest)
    return manifest


def mark_current_manifest_needs_review(db: Session, dataset_id: int) -> None:
    """当 schema 结构变化时，把 current Manifest 标记为需复核。"""

    current = _current_manifest(db, dataset_id)
    if not current:
        return
    latest_schema_version = build_dataset_schema_version(db, dataset_id)
    if current.bound_schema_version != latest_schema_version:
        current.review_status = "needs_review"
        db.commit()


def list_current_manifest_summaries(db: Session) -> list[dict[str, Any]]:
    """返回所有 current manifest 的轻量摘要，供后续 LeadAgent 构造路由上下文。"""

    manifests = (
        db.query(models.DatasetSubAgentManifest)
        .filter(models.DatasetSubAgentManifest.is_current.is_(True))
        .order_by(models.DatasetSubAgentManifest.dataset_id)
        .all()
    )
    return [_manifest_summary(item) for item in manifests]


def route_check_manifest(
    db: Session,
    dataset_id: int,
    questions: list[str],
    *,
    expected: str | None = None,
) -> list[dict[str, Any]]:
    """使用 manifest scorer 做路由自检。"""

    manifest = _current_manifest(db, dataset_id) or _draft_manifest(db, dataset_id)
    if not manifest:
        raise ValueError("请先保存或发布 Manifest")
    results = []
    for question in questions[:20]:
        score, reasons, negative_hit = score_manifest_question(question, manifest)
        if negative_hit:
            decision = "miss"
            reasons.append("命中负例，应该避免路由到该数据集。")
        elif score >= 0.55:
            decision = "hit"
        elif score >= 0.28:
            decision = "ambiguous"
        else:
            decision = "miss"
        suggestions = []
        if expected == "positive" and decision != "hit":
            suggestions.append("正例未稳定命中，建议补充更具体的 sample_questions 或 description。")
        if expected == "negative" and decision == "hit":
            suggestions.append("负例仍被命中，建议加入 routing_negative_examples 或收窄 description。")
        if decision == "ambiguous":
            suggestions.append("命中证据不足，建议补充业务域、指标名或典型问法。")
        results.append(
            {
                "question": question,
                "top_dataset_id": dataset_id if decision != "miss" else None,
                "matched_manifest_version": manifest.manifest_version,
                "score": round(score, 2),
                "decision": decision,
                "reasons": reasons,
                "suggestions": suggestions,
            }
        )
    return results


def score_manifest_question(
    question: str,
    manifest: models.DatasetSubAgentManifest,
) -> tuple[float, list[str], bool]:
    """对单个问题和 Manifest 计算路由分，供自检和 LeadAgent 入口共用。"""

    score, reasons = _score_question(question, manifest)
    negative_hit = _matches_any(question, _manual_list(manifest, "routing_negative_examples"))
    if negative_hit:
        score = min(score, 0.24)
    return score, reasons, negative_hit


class ManifestValidationError(ValueError):
    """Manifest 发布校验失败。"""

    def __init__(self, issues: list[dict[str, str]]) -> None:
        super().__init__("Manifest 校验未通过")
        self.issues = issues


def _clean_text_list(value: Any, *, max_items: int) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[\n；;]+", value)
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip()
        key = _normalize_text(text)
        if not text or not key or key in seen:
            continue
        out.append(text)
        seen.add(key)
        if len(out) >= max_items:
            break
    return out


def _issue(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _entity_terms(auto_fields: dict[str, Any], manual_fields: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for key in ("key_metrics", "key_dimensions"):
        for item in auto_fields.get(key) or []:
            terms.extend([item.get("display_name"), item.get("name")])
    terms.extend(manual_fields.get("business_domain") or [])
    return [term for term in _clean_text_list(terms, max_items=80) if len(term) >= 2]


def _manifest_payload(
    auto_fields: dict[str, Any],
    manual_fields: dict[str, Any],
    *,
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "auto_fields": auto_fields,
        "manual_fields": normalize_manual_fields(manual_fields),
        "quality": quality or {"lint": lint_manifest(manual_fields, auto_fields)},
    }


def _current_manifest(db: Session, dataset_id: int) -> models.DatasetSubAgentManifest | None:
    return (
        db.query(models.DatasetSubAgentManifest)
        .filter(
            models.DatasetSubAgentManifest.dataset_id == dataset_id,
            models.DatasetSubAgentManifest.is_current.is_(True),
        )
        .order_by(models.DatasetSubAgentManifest.created_at.desc())
        .first()
    )


def _draft_manifest(db: Session, dataset_id: int) -> models.DatasetSubAgentManifest | None:
    return db.get(models.DatasetSubAgentManifest, (dataset_id, DRAFT_VERSION))


def _manifest_manual_fields(manifest: models.DatasetSubAgentManifest | None) -> dict[str, Any]:
    if not manifest:
        return normalize_manual_fields(None)
    return normalize_manual_fields((manifest.manifest_json or {}).get("manual_fields") or {})


def _manual_list(manifest: models.DatasetSubAgentManifest, key: str) -> list[str]:
    return _manifest_manual_fields(manifest).get(key) or []


def _next_manifest_version(db: Session, dataset_id: int) -> str:
    versions = [
        item.manifest_version
        for item in db.query(models.DatasetSubAgentManifest)
        .filter(models.DatasetSubAgentManifest.dataset_id == dataset_id)
        .all()
    ]
    max_num = 0
    for version in versions:
        match = re.fullmatch(r"v(\d+)", str(version or ""))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"v{max_num + 1}"


def _manifest_summary(manifest: models.DatasetSubAgentManifest) -> dict[str, Any]:
    payload = manifest.manifest_json or {}
    auto_fields = payload.get("auto_fields") or {}
    manual_fields = payload.get("manual_fields") or {}
    return {
        "dataset_id": manifest.dataset_id,
        "manifest_version": manifest.manifest_version,
        "bound_schema_version": manifest.bound_schema_version,
        "review_status": manifest.review_status,
        "name": auto_fields.get("name"),
        "description": manual_fields.get("description"),
        "business_domain": manual_fields.get("business_domain") or [],
        "sample_questions": manual_fields.get("sample_questions") or [],
        "routing_negative_examples": manual_fields.get("routing_negative_examples") or [],
        "key_metrics": auto_fields.get("key_metrics") or [],
        "key_dimensions": auto_fields.get("key_dimensions") or [],
        "permission_scope": auto_fields.get("permission_scope") or {},
    }


def _normalize_text(text: str) -> str:
    return re.sub(r"[\s_`'\".，,。；;：:、/\\-]+", "", str(text or "").lower())


def _score_question(
    question: str,
    manifest: models.DatasetSubAgentManifest,
) -> tuple[float, list[str]]:
    payload = manifest.manifest_json or {}
    auto_fields = payload.get("auto_fields") or {}
    manual_fields = normalize_manual_fields(payload.get("manual_fields") or {})
    q_norm = _normalize_text(question)
    score = 0.0
    reasons: list[str] = []
    if _matches_any(question, manual_fields["sample_questions"]):
        score += 0.65
        reasons.append("命中典型正例。")
    if _matches_any(question, manual_fields["business_domain"]):
        score += 0.2
        reasons.append("命中业务域。")
    if _matches_any(question, [manual_fields["description"]]):
        score += 0.15
        reasons.append("命中 description 关键文本。")
    metric_terms = [
        term
        for item in auto_fields.get("key_metrics") or []
        for term in (item.get("display_name"), item.get("name"), *(item.get("synonyms") or []))
    ]
    dimension_terms = [
        term
        for item in auto_fields.get("key_dimensions") or []
        for term in (item.get("display_name"), item.get("name"), *(item.get("synonyms") or []))
    ]
    metric_hits = [term for term in metric_terms if term and _normalize_text(term) in q_norm]
    dim_hits = [term for term in dimension_terms if term and _normalize_text(term) in q_norm]
    if metric_hits:
        score += min(0.25, 0.08 * len(metric_hits))
        reasons.append(f"命中指标：{', '.join(metric_hits[:3])}。")
    if dim_hits:
        score += min(0.18, 0.06 * len(dim_hits))
        reasons.append(f"命中维度：{', '.join(dim_hits[:3])}。")
    if not reasons:
        reasons.append("未命中 manifest 中的稳定路由证据。")
    return min(score, 0.99), reasons


def _matches_any(question: str, candidates: list[str]) -> bool:
    q_norm = _normalize_text(question)
    if not q_norm:
        return False
    for candidate in candidates or []:
        c_norm = _normalize_text(candidate)
        if not c_norm:
            continue
        if c_norm in q_norm or q_norm in c_norm:
            return True
        q_chars = set(q_norm)
        c_chars = set(c_norm)
        overlap = len(q_chars & c_chars) / max(len(c_chars), 1)
        if len(c_norm) >= 6 and overlap >= 0.65:
            return True
    return False
