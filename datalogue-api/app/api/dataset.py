# ============================================================
# File Name   : dataset.py
# Description:
#   语义数据集治理 API 端点。
#
# Responsibilities:
#   - 管理数据集、指标、维度、业务术语和分析蓝图。
#   - 处理选表、字段审核、语义验证和 YAML 导入导出。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from datetime import datetime
from typing import Any, List
import json
import logging
import re
import time
import uuid

import yaml
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app import schemas, models
from app.graph.llm import get_llm

router = APIRouter()
logger = logging.getLogger(__name__)

BLUEPRINT_ANALYZE_TASKS: dict[str, dict[str, Any]] = {}
BLUEPRINT_STATUSES = {"draft", "reviewing", "active", "deprecated"}
COLUMN_REVIEW_STATUSES = {
    "pending_review",
    "confirmed",
    "ignored",
    "converted_to_metric",
    "converted_to_dimension",
}
TERM_STATUSES = {"draft", "active", "deprecated"}
TERM_TYPES = {
    "metric_concept",
    "dimension_enum",
    "business_object",
    "business_process",
    "status_enum",
    "org_scope",
}
TERM_ASSET_TYPES = {"metric", "dimension", "column", "blueprint"}


@router.get("", response_model=List[schemas.DatasetOut])
def list_datasets(datasource_id: int | None = None, db: Session = Depends(get_db)):
    logger.info(f"获取数据集列表: datasource_id={datasource_id}")
    q = db.query(models.SemanticDataset)
    if datasource_id:
        q = q.filter(models.SemanticDataset.datasource_id == datasource_id)
    result = q.order_by(models.SemanticDataset.id.desc()).all()
    logger.info(f"返回 {len(result)} 个数据集")
    return result


@router.post("", response_model=schemas.DatasetOut)
def create_dataset(payload: schemas.DatasetCreate, db: Session = Depends(get_db)):
    logger.info(f"创建数据集: name={payload.name}")
    ds = models.SemanticDataset(**payload.model_dump())
    db.add(ds)
    db.commit()
    db.refresh(ds)
    logger.info(f"数据集创建成功: id={ds.id}")
    return ds


@router.get("/{ds_id}", response_model=schemas.DatasetOut)
def get_dataset(ds_id: int, db: Session = Depends(get_db)):
    """获取单个数据集详情。"""
    logger.info(f"获取数据集详情: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")
    return ds


@router.put("/{ds_id}", response_model=schemas.DatasetOut)
def update_dataset(ds_id: int, payload: schemas.DatasetUpdate, db: Session = Depends(get_db)):
    """部分更新数据集信息（重命名、修改描述/状态等）。"""
    logger.info(f"更新数据集: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(ds, key, value)
    db.commit()
    db.refresh(ds)
    logger.info(f"数据集更新成功: ds_id={ds_id}")
    return ds


@router.delete("/{ds_id}")
def delete_dataset(ds_id: int, db: Session = Depends(get_db)):
    """删除数据集及其关联的指标、维度和已选源表关联。"""
    logger.info(f"删除数据集: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")
    # 显式级联删除关联记录，避免 ORM 默认 SET NULL 与 NOT NULL 冲突
    db.query(models.SemanticMetric).filter(models.SemanticMetric.dataset_id == ds_id).delete()
    db.query(models.SemanticDimension).filter(models.SemanticDimension.dataset_id == ds_id).delete()
    db.query(models.DatasetSourceTable).filter(
        models.DatasetSourceTable.dataset_id == ds_id
    ).delete()
    db.delete(ds)
    db.commit()
    logger.info(f"数据集删除成功: ds_id={ds_id}")
    return {"ok": True}


# ── Metrics ──────────────────────────────────────────


@router.post("/{ds_id}/metric", response_model=schemas.MetricOut)
def add_metric(ds_id: int, payload: schemas.MetricCreate, db: Session = Depends(get_db)):
    logger.info(f"添加指标: ds_id={ds_id}, name={payload.name}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")
    m = models.SemanticMetric(dataset_id=ds_id, **payload.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    logger.info(f"指标添加成功: id={m.id}")
    return m


@router.put("/{ds_id}/metric/{mid}", response_model=schemas.MetricOut)
def update_metric(
    ds_id: int, mid: int, payload: schemas.MetricCreate, db: Session = Depends(get_db)
):
    """更新指标。"""
    logger.info(f"更新指标: ds_id={ds_id}, mid={mid}")
    m = db.get(models.SemanticMetric, mid)
    if not m or m.dataset_id != ds_id:
        logger.warning(f"指标不存在: ds_id={ds_id}, mid={mid}")
        raise HTTPException(status_code=404, detail="指标不存在")
    for key, value in payload.model_dump().items():
        setattr(m, key, value)
    db.commit()
    db.refresh(m)
    logger.info(f"指标更新成功: mid={mid}")
    return m


@router.get("/{ds_id}/metrics", response_model=List[schemas.MetricOut])
def list_metrics(ds_id: int, db: Session = Depends(get_db)):
    """获取数据集下的所有指标。"""
    return db.query(models.SemanticMetric).filter(models.SemanticMetric.dataset_id == ds_id).all()


@router.delete("/{ds_id}/metric/{mid}")
def delete_metric(ds_id: int, mid: int, db: Session = Depends(get_db)):
    """删除指标。"""
    logger.info(f"删除指标: ds_id={ds_id}, mid={mid}")
    m = db.get(models.SemanticMetric, mid)
    if not m or m.dataset_id != ds_id:
        logger.warning(f"指标不存在: ds_id={ds_id}, mid={mid}")
        raise HTTPException(status_code=404, detail="指标不存在")
    db.delete(m)
    db.commit()
    logger.info(f"指标删除成功: mid={mid}")
    return {"ok": True}


# ── Dimensions ───────────────────────────────────────


@router.post("/{ds_id}/dimension", response_model=schemas.DimensionOut)
def add_dimension(ds_id: int, payload: schemas.DimensionCreate, db: Session = Depends(get_db)):
    logger.info(f"添加维度: ds_id={ds_id}, name={payload.name}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")
    d = models.SemanticDimension(dataset_id=ds_id, **payload.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    logger.info(f"维度添加成功: id={d.id}")
    return d


@router.put("/{ds_id}/dimension/{did}", response_model=schemas.DimensionOut)
def update_dimension(
    ds_id: int, did: int, payload: schemas.DimensionCreate, db: Session = Depends(get_db)
):
    """更新维度。"""
    logger.info(f"更新维度: ds_id={ds_id}, did={did}")
    d = db.get(models.SemanticDimension, did)
    if not d or d.dataset_id != ds_id:
        logger.warning(f"维度不存在: ds_id={ds_id}, did={did}")
        raise HTTPException(status_code=404, detail="维度不存在")
    for key, value in payload.model_dump().items():
        setattr(d, key, value)
    db.commit()
    db.refresh(d)
    logger.info(f"维度更新成功: did={did}")
    return d


@router.get("/{ds_id}/dimensions", response_model=List[schemas.DimensionOut])
def list_dimensions(ds_id: int, db: Session = Depends(get_db)):
    """获取数据集下的所有维度。"""
    return (
        db.query(models.SemanticDimension)
        .filter(models.SemanticDimension.dataset_id == ds_id)
        .all()
    )


@router.delete("/{ds_id}/dimension/{did}")
def delete_dimension(ds_id: int, did: int, db: Session = Depends(get_db)):
    """删除维度。"""
    logger.info(f"删除维度: ds_id={ds_id}, did={did}")
    d = db.get(models.SemanticDimension, did)
    if not d or d.dataset_id != ds_id:
        logger.warning(f"维度不存在: ds_id={ds_id}, did={did}")
        raise HTTPException(status_code=404, detail="维度不存在")
    db.delete(d)
    db.commit()
    logger.info(f"维度删除成功: did={did}")
    return {"ok": True}


# ── Source Column Review / Conversion ────────────────


def _coerce_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _short_text(value: str | None, max_len: int = 100) -> str:
    return (value or "").strip()[:max_len]


def _column_display_name(col: models.SourceColumn) -> str:
    return _short_text(
        col.user_description
        or col.ai_description
        or col.business_desc
        or col.effective_desc
        or col.column_comment
        or col.column_name
    )


def _asset_name(col: models.SourceColumn, display_name: str) -> str:
    candidate = re.sub(r"\W+", "_", (display_name or col.column_name or "").lower()).strip("_")
    if not candidate:
        candidate = re.sub(r"\W+", "_", (col.column_name or "").lower()).strip("_")
    return _short_text(candidate or f"field_{col.id}", 100)


def _effective_role(col: models.SourceColumn) -> str | None:
    return col.user_semantic_role or col.ai_semantic_role or col.semantic_role


def _source_column_payload(col: models.SourceColumn) -> dict[str, Any]:
    table = col.table
    return {
        "id": col.id,
        "table_id": col.table_id,
        "source_table_id": table.id if table else col.table_id,
        "table_name": table.table_name if table else None,
        "schema_name": table.schema_name if table else None,
        "column_name": col.column_name,
        "data_type": col.data_type,
        "column_comment": col.column_comment,
        "business_desc": col.business_desc,
        "ai_description": col.ai_description,
        "ai_semantic_role": col.ai_semantic_role,
        "ai_suggested_agg": col.ai_suggested_agg,
        "ai_confidence": col.ai_confidence,
        "ai_reason": col.ai_reason,
        "suggested_synonyms": col.suggested_synonyms,
        "suggested_enum_values": col.suggested_enum_values,
        "user_description": col.user_description,
        "user_semantic_role": col.user_semantic_role,
        "effective_desc": col.effective_desc,
        "desc_source": col.desc_source,
        "annotated_at": col.annotated_at,
        "review_status": col.review_status,
        "converted_metric_id": col.converted_metric_id,
        "converted_dimension_id": col.converted_dimension_id,
        "reviewed_at": col.reviewed_at,
        "is_nullable": col.is_nullable,
        "column_default": col.column_default,
        "ordinal_position": col.ordinal_position,
        "semantic_role": col.semantic_role,
        "default_agg": col.default_agg,
        "sample_values": col.sample_values,
    }


def _get_selected_column(ds_id: int, column_id: int, db: Session) -> models.SourceColumn:
    _ensure_dataset(ds_id, db)
    col = db.get(models.SourceColumn, column_id)
    if not col:
        raise HTTPException(status_code=404, detail="字段不存在")
    link = (
        db.query(models.DatasetSourceTable)
        .filter_by(dataset_id=ds_id, source_table_id=col.table_id)
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="字段不属于当前数据集已选表")
    return col


def _time_field_for_table(col: models.SourceColumn) -> str | None:
    if not col.table:
        return None
    for candidate in col.table.columns:
        if _effective_role(candidate) == "time_field":
            return candidate.column_name
    return None


@router.post("/{ds_id}/columns/{column_id}/convert-metric")
def convert_column_to_metric(
    ds_id: int,
    column_id: int,
    payload: schemas.ColumnMetricConvertPayload | None = Body(default=None),
    db: Session = Depends(get_db),
):
    col = _get_selected_column(ds_id, column_id, db)
    role = _effective_role(col)
    if role != "metric_candidate":
        raise HTTPException(status_code=400, detail="该字段不是度量候选，不能转换为指标")

    data = payload.model_dump(exclude_unset=True) if payload else {}
    display_name = _short_text(data.get("display_name") or _column_display_name(col))
    name = _short_text(data.get("name") or _asset_name(col, display_name))
    agg = (col.ai_suggested_agg or col.default_agg or "SUM").upper()
    if agg == "NONE":
        agg = "SUM"
    expr = data.get("expr") or f"{agg}({col.column_name})"
    table_name = data.get("table_name") or (col.table.table_name if col.table else None)

    existing = (
        db.query(models.SemanticMetric)
        .filter(models.SemanticMetric.dataset_id == ds_id)
        .filter(
            or_(
                models.SemanticMetric.name == name,
                (models.SemanticMetric.table_name == table_name)
                & (models.SemanticMetric.expr == expr),
            )
        )
        .first()
    )
    created = False
    metric = existing
    if not metric:
        metric = models.SemanticMetric(
            dataset_id=ds_id,
            name=name,
            display_name=display_name,
            expr=expr,
            table_name=table_name,
            time_field=data.get("time_field") or _time_field_for_table(col),
            granularity=data.get("granularity") or "daily",
            format_str=data.get("format_str"),
            filter_sql=data.get("filter_sql"),
            synonyms=_coerce_list(data.get("synonyms")) or _coerce_list(col.suggested_synonyms),
            description=data.get("description") or col.ai_reason or col.ai_description or col.effective_desc,
        )
        db.add(metric)
        db.flush()
        created = True

    col.converted_metric_id = metric.id
    col.review_status = "converted_to_metric"
    col.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(metric)
    db.refresh(col)
    return {
        "created": created,
        "existing": not created,
        "asset_type": "metric",
        "metric": schemas.MetricOut.model_validate(metric),
        "column": _source_column_payload(col),
    }


@router.post("/{ds_id}/columns/{column_id}/convert-dimension")
def convert_column_to_dimension(
    ds_id: int,
    column_id: int,
    payload: schemas.ColumnDimensionConvertPayload | None = Body(default=None),
    db: Session = Depends(get_db),
):
    col = _get_selected_column(ds_id, column_id, db)
    role = _effective_role(col)
    if role not in {"dimension_candidate", "time_field", "id_field"}:
        raise HTTPException(status_code=400, detail="该字段不是维度候选，不能转换为维度")

    data = payload.model_dump(exclude_unset=True) if payload else {}
    display_name = _short_text(data.get("display_name") or _column_display_name(col))
    name = _short_text(data.get("name") or _asset_name(col, display_name))
    table_name = data.get("table_name") or (col.table.table_name if col.table else None)
    column_name = data.get("column_name") or col.column_name

    existing = (
        db.query(models.SemanticDimension)
        .filter(models.SemanticDimension.dataset_id == ds_id)
        .filter(
            or_(
                models.SemanticDimension.name == name,
                (models.SemanticDimension.table_name == table_name)
                & (models.SemanticDimension.column_name == column_name),
            )
        )
        .first()
    )
    created = False
    dimension = existing
    if not dimension:
        enum_values = (
            _coerce_list(data.get("enum_values"))
            or _coerce_list(col.suggested_enum_values)
            or _coerce_list(col.sample_values)[:20]
        )
        dimension = models.SemanticDimension(
            dataset_id=ds_id,
            name=name,
            display_name=display_name,
            table_name=table_name,
            column_name=column_name,
            join_to=data.get("join_to"),
            join_key=data.get("join_key"),
            hierarchy=data.get("hierarchy"),
            enum_values=enum_values,
            synonyms=_coerce_list(data.get("synonyms")) or _coerce_list(col.suggested_synonyms),
        )
        db.add(dimension)
        db.flush()
        created = True

    col.converted_dimension_id = dimension.id
    col.review_status = "converted_to_dimension"
    col.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(dimension)
    db.refresh(col)
    return {
        "created": created,
        "existing": not created,
        "asset_type": "dimension",
        "dimension": schemas.DimensionOut.model_validate(dimension),
        "column": _source_column_payload(col),
    }


@router.patch("/{ds_id}/columns/{column_id}/review-status")
def update_column_review_status(
    ds_id: int,
    column_id: int,
    payload: schemas.SourceColumnReviewPayload,
    db: Session = Depends(get_db),
):
    if payload.review_status not in COLUMN_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail="不支持的字段审核状态")
    col = _get_selected_column(ds_id, column_id, db)
    col.review_status = payload.review_status
    col.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(col)
    return {"ok": True, "column": _source_column_payload(col)}


# ── Business Terms ───────────────────────────────────


def _term_snapshot(term: models.BusinessTerm | None) -> dict[str, Any] | None:
    if not term:
        return None
    return {
        "id": term.id,
        "dataset_id": term.dataset_id,
        "name": term.name,
        "display_name": term.display_name,
        "term_type": term.term_type,
        "definition": term.definition,
        "aliases": term.aliases or [],
        "forbidden_aliases": term.forbidden_aliases or [],
        "examples": term.examples or [],
        "owner": term.owner,
        "status": term.status,
        "source": term.source,
        "confidence": term.confidence,
        "extra_metadata": term.extra_metadata or {},
    }


def _record_term_change(
    db: Session,
    term: models.BusinessTerm,
    action: str,
    before: dict[str, Any] | None = None,
    actor: str | None = None,
) -> None:
    db.add(
        models.BusinessTermChangeLog(
            term_id=term.id,
            action=action,
            before_snapshot=before,
            after_snapshot=_term_snapshot(term),
            actor=actor,
        )
    )


def _get_term(ds_id: int, term_id: int, db: Session) -> models.BusinessTerm:
    term = db.get(models.BusinessTerm, term_id)
    if not term or term.dataset_id != ds_id:
        raise HTTPException(status_code=404, detail="业务术语不存在")
    return term


def _normalize_term_payload(data: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    normalized = dict(data)
    if not normalized.get("display_name") and normalized.get("name"):
        normalized["display_name"] = normalized["name"]
    for key in ["aliases", "forbidden_aliases", "examples"]:
        if key in normalized or not partial:
            normalized[key] = _coerce_list(normalized.get(key))
    if "extra_metadata" in normalized or not partial:
        normalized["extra_metadata"] = normalized.get("extra_metadata") or {}
    return normalized


def _validate_term_data(data: dict[str, Any]) -> None:
    if data.get("status") and data["status"] not in TERM_STATUSES:
        raise HTTPException(status_code=400, detail="术语状态不合法")
    if data.get("term_type") and data["term_type"] not in TERM_TYPES:
        raise HTTPException(status_code=400, detail="术语类型不合法")


def _resolve_asset_name(ds_id: int, link: dict[str, Any], db: Session) -> str | None:
    asset_type = link.get("asset_type")
    asset_id = link.get("asset_id")
    if asset_type not in TERM_ASSET_TYPES:
        raise HTTPException(status_code=400, detail="资产类型不合法")
    if not isinstance(asset_id, int):
        raise HTTPException(status_code=400, detail="asset_id 必须是整数")
    if asset_type == "metric":
        asset = db.get(models.SemanticMetric, asset_id)
        if not asset or asset.dataset_id != ds_id:
            raise HTTPException(status_code=404, detail="指标资产不存在")
        return asset.display_name or asset.name
    if asset_type == "dimension":
        asset = db.get(models.SemanticDimension, asset_id)
        if not asset or asset.dataset_id != ds_id:
            raise HTTPException(status_code=404, detail="维度资产不存在")
        return asset.display_name or asset.name
    if asset_type == "blueprint":
        asset = db.get(models.AnalysisBlueprint, asset_id)
        if not asset or asset.dataset_id != ds_id:
            raise HTTPException(status_code=404, detail="分析蓝图资产不存在")
        return asset.name
    col = _get_selected_column(ds_id, asset_id, db)
    return f"{col.table.table_name}.{col.column_name}" if col.table else col.column_name


def _term_conflicts(terms: list[models.BusinessTerm]) -> list[dict[str, Any]]:
    token_map: dict[str, list[models.BusinessTerm]] = {}
    for term in terms:
        tokens = {term.name, term.display_name, *(_coerce_list(term.aliases))}
        for token in {t.strip().lower() for t in tokens if t and t.strip()}:
            token_map.setdefault(token, []).append(term)
    conflicts = []
    for token, owners in token_map.items():
        unique_ids = {term.id for term in owners}
        if len(unique_ids) > 1:
            conflicts.append(
                {
                    "type": "alias_collision",
                    "token": token,
                    "term_ids": sorted(unique_ids),
                    "terms": [
                        {"id": term.id, "name": term.name, "display_name": term.display_name}
                        for term in owners
                    ],
                    "severity": "warning",
                    "message": "同一个名称或别名被多个术语使用",
                }
            )
    for term in terms:
        aliases = {a.strip().lower() for a in _coerce_list(term.aliases)}
        forbidden = {a.strip().lower() for a in _coerce_list(term.forbidden_aliases)}
        overlap = sorted(aliases & forbidden)
        if overlap:
            conflicts.append(
                {
                    "type": "forbidden_alias_overlap",
                    "token": overlap[0],
                    "term_ids": [term.id],
                    "terms": [
                        {"id": term.id, "name": term.name, "display_name": term.display_name}
                    ],
                    "severity": "error",
                    "message": "同一术语的同义词和禁用词存在重叠",
                }
            )
    return conflicts


@router.get("/{ds_id}/terms", response_model=List[schemas.BusinessTermOut])
def list_terms(
    ds_id: int,
    q: str | None = None,
    term_type: str | None = None,
    status: str | None = None,
    has_conflict: bool | None = None,
    db: Session = Depends(get_db),
):
    _ensure_dataset(ds_id, db)
    query = db.query(models.BusinessTerm).filter(models.BusinessTerm.dataset_id == ds_id)
    if term_type:
        query = query.filter(models.BusinessTerm.term_type == term_type)
    if status:
        query = query.filter(models.BusinessTerm.status == status)
    terms = query.order_by(models.BusinessTerm.updated_at.desc(), models.BusinessTerm.id.desc()).all()
    if q:
        needle = q.strip().lower()
        terms = [
            term
            for term in terms
            if needle in " ".join(
                [
                    term.name or "",
                    term.display_name or "",
                    term.definition or "",
                    " ".join(_coerce_list(term.aliases)),
                ]
            ).lower()
        ]
    if has_conflict is not None:
        conflicted_ids = {
            term_id
            for conflict in _term_conflicts(terms)
            for term_id in conflict.get("term_ids", [])
        }
        terms = [
            term
            for term in terms
            if (term.id in conflicted_ids) is has_conflict
        ]
    return terms


@router.post("/{ds_id}/terms", response_model=schemas.BusinessTermOut)
def create_term(
    ds_id: int, payload: schemas.BusinessTermCreate, db: Session = Depends(get_db)
):
    _ensure_dataset(ds_id, db)
    data = _normalize_term_payload(payload.model_dump())
    _validate_term_data(data)
    exists = (
        db.query(models.BusinessTerm)
        .filter_by(dataset_id=ds_id, name=data["name"])
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="同名业务术语已存在")
    term = models.BusinessTerm(dataset_id=ds_id, **data)
    db.add(term)
    db.flush()
    _record_term_change(db, term, "create")
    db.commit()
    db.refresh(term)
    return term


@router.get("/{ds_id}/terms/{term_id:int}", response_model=schemas.BusinessTermOut)
def get_term(ds_id: int, term_id: int, db: Session = Depends(get_db)):
    return _get_term(ds_id, term_id, db)


@router.put("/{ds_id}/terms/{term_id:int}", response_model=schemas.BusinessTermOut)
def update_term(
    ds_id: int,
    term_id: int,
    payload: schemas.BusinessTermUpdate,
    db: Session = Depends(get_db),
):
    term = _get_term(ds_id, term_id, db)
    before = _term_snapshot(term)
    data = _normalize_term_payload(payload.model_dump(exclude_unset=True), partial=True)
    _validate_term_data(data)
    if data.get("name") and data["name"] != term.name:
        exists = (
            db.query(models.BusinessTerm)
            .filter_by(dataset_id=ds_id, name=data["name"])
            .first()
        )
        if exists:
            raise HTTPException(status_code=409, detail="同名业务术语已存在")
    for key, value in data.items():
        setattr(term, key, value)
    _record_term_change(db, term, "update", before=before)
    db.commit()
    db.refresh(term)
    return term


@router.delete("/{ds_id}/terms/{term_id:int}")
def delete_term(ds_id: int, term_id: int, db: Session = Depends(get_db)):
    term = _get_term(ds_id, term_id, db)
    db.delete(term)
    db.commit()
    return {"ok": True}


@router.post("/{ds_id}/terms/{term_id:int}/link-assets", response_model=schemas.BusinessTermOut)
def link_term_assets(
    ds_id: int,
    term_id: int,
    payload: schemas.BusinessTermAssetLinkPayload,
    db: Session = Depends(get_db),
):
    term = _get_term(ds_id, term_id, db)
    before = _term_snapshot(term)
    db.query(models.BusinessTermAssetLink).filter_by(term_id=term.id).delete()
    for link in payload.links:
        asset_name = link.get("asset_name") or _resolve_asset_name(ds_id, link, db)
        db.add(
            models.BusinessTermAssetLink(
                term_id=term.id,
                asset_type=link["asset_type"],
                asset_id=link["asset_id"],
                asset_name=asset_name,
            )
        )
    _record_term_change(db, term, "link_assets", before=before)
    db.commit()
    db.refresh(term)
    return term


@router.get("/{ds_id}/terms/{term_id:int}/usage")
def get_term_usage(ds_id: int, term_id: int, db: Session = Depends(get_db)):
    term = _get_term(ds_id, term_id, db)
    return {
        "term_id": term.id,
        "usage_count": len(term.asset_links),
        "asset_links": [
            {
                "asset_type": link.asset_type,
                "asset_id": link.asset_id,
                "asset_name": link.asset_name,
            }
            for link in term.asset_links
        ],
        "examples": term.examples or [],
    }


@router.post("/{ds_id}/terms/discover", response_model=schemas.BusinessTermDiscoverOut)
def discover_terms(ds_id: int, db: Session = Depends(get_db)):
    _ensure_dataset(ds_id, db)
    candidates: list[dict[str, Any]] = []
    for metric in db.query(models.SemanticMetric).filter_by(dataset_id=ds_id).all():
        aliases = _coerce_list(metric.synonyms)
        candidates.append(
            {
                "name": metric.name,
                "display_name": metric.display_name,
                "term_type": "metric_concept",
                "definition": metric.description or metric.expr,
                "aliases": aliases,
                "source": "metric",
                "confidence": 0.86 if aliases else 0.72,
                "asset_links": [
                    {
                        "asset_type": "metric",
                        "asset_id": metric.id,
                        "asset_name": metric.display_name or metric.name,
                    }
                ],
            }
        )
    for dimension in db.query(models.SemanticDimension).filter_by(dataset_id=ds_id).all():
        candidates.append(
            {
                "name": dimension.name,
                "display_name": dimension.display_name,
                "term_type": "dimension_enum" if dimension.enum_values else "business_object",
                "definition": f"{dimension.table_name or ''}.{dimension.column_name}".strip("."),
                "aliases": _coerce_list(dimension.synonyms),
                "examples": _coerce_list(dimension.enum_values)[:5],
                "source": "dimension",
                "confidence": 0.78,
                "asset_links": [
                    {
                        "asset_type": "dimension",
                        "asset_id": dimension.id,
                        "asset_name": dimension.display_name or dimension.name,
                    }
                ],
            }
        )
    selected_links = db.query(models.DatasetSourceTable).filter_by(dataset_id=ds_id).all()
    selected_table_ids = [link.source_table_id for link in selected_links]
    if selected_table_ids:
        columns = (
            db.query(models.SourceColumn)
            .filter(models.SourceColumn.table_id.in_(selected_table_ids))
            .all()
        )
        for col in columns:
            role = _effective_role(col)
            if role not in {"metric_candidate", "dimension_candidate", "time_field"}:
                continue
            display_name = _column_display_name(col)
            candidates.append(
                {
                    "name": col.column_name,
                    "display_name": display_name,
                    "term_type": "metric_concept" if role == "metric_candidate" else "business_object",
                    "definition": col.effective_desc or col.ai_description or col.column_comment,
                    "aliases": _coerce_list(col.suggested_synonyms),
                    "examples": _coerce_list(col.suggested_enum_values)[:5]
                    or _coerce_list(col.sample_values)[:5],
                    "source": "column",
                    "confidence": col.ai_confidence or 0.64,
                    "asset_links": [
                        {
                            "asset_type": "column",
                            "asset_id": col.id,
                            "asset_name": f"{col.table.table_name}.{col.column_name}"
                            if col.table
                            else col.column_name,
                        }
                    ],
                }
            )
    existing_names = {
        term.name.lower()
        for term in db.query(models.BusinessTerm).filter_by(dataset_id=ds_id).all()
    }
    deduped = []
    seen = set()
    for candidate in candidates:
        key = candidate["name"].lower()
        if key in seen or key in existing_names:
            continue
        seen.add(key)
        deduped.append(candidate)
    return {"candidates": deduped[:30]}


@router.post("/{ds_id}/terms/conflicts/check", response_model=schemas.BusinessTermConflictOut)
def check_term_conflicts(ds_id: int, db: Session = Depends(get_db)):
    _ensure_dataset(ds_id, db)
    terms = db.query(models.BusinessTerm).filter_by(dataset_id=ds_id).all()
    return {"conflicts": _term_conflicts(terms)}


# ── Analysis Blueprints ──────────────────────────────


def _ensure_dataset(ds_id: int, db: Session):
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")
    return ds


def _get_blueprint(ds_id: int, bid: int, db: Session):
    bp = db.get(models.AnalysisBlueprint, bid)
    if not bp or bp.dataset_id != ds_id:
        logger.warning(f"蓝图不存在: ds_id={ds_id}, bid={bid}")
        raise HTTPException(status_code=404, detail="蓝图不存在")
    return bp


def _blueprint_snapshot(bp: models.AnalysisBlueprint) -> dict[str, Any]:
    return {
        "id": bp.id,
        "dataset_id": bp.dataset_id,
        "name": bp.name,
        "description": bp.description,
        "trigger_keywords": bp.trigger_keywords or [],
        "trigger_examples": bp.trigger_examples or [],
        "when_to_use": bp.when_to_use,
        "parameters": bp.parameters or [],
        "implementation_type": bp.implementation_type,
        "call_template": bp.call_template,
        "output_schema": bp.output_schema or [],
        "timeout_seconds": bp.timeout_seconds,
        "steps": bp.steps or [],
        "attribution_hints": bp.attribution_hints,
        "raw_sql": bp.raw_sql,
        "status": bp.status,
        "version": bp.version,
        "ai_confidence": bp.ai_confidence,
        "owner": bp.owner,
        "last_validated_at": bp.last_validated_at.isoformat()
        if bp.last_validated_at
        else None,
        "usage_count": bp.usage_count,
        "last_test_result": bp.last_test_result,
    }


def _apply_blueprint_snapshot(bp: models.AnalysisBlueprint, snapshot: dict[str, Any]) -> None:
    for key in [
        "name",
        "description",
        "trigger_keywords",
        "trigger_examples",
        "when_to_use",
        "parameters",
        "implementation_type",
        "call_template",
        "output_schema",
        "timeout_seconds",
        "steps",
        "attribution_hints",
        "raw_sql",
        "ai_confidence",
        "owner",
        "last_test_result",
    ]:
        if key in snapshot:
            setattr(bp, key, snapshot[key])


def _mock_analyze_sql(sql: str) -> dict[str, Any]:
    sql_lower = sql.lower()
    params = []
    if "start" in sql_lower or "p_start" in sql_lower:
        params.append(
            {
                "name": "start_date",
                "type": "date",
                "extract_hint": "时间起点，默认本月1号",
                "default_expr": "MONTH_START",
                "required": True,
                "confidence": 0.86,
            }
        )
    if "end" in sql_lower or "p_end" in sql_lower:
        params.append(
            {
                "name": "end_date",
                "type": "date",
                "extract_hint": "时间终点，默认今天",
                "default_expr": "TODAY",
                "required": True,
                "confidence": 0.84,
            }
        )
    if "region" in sql_lower:
        params.append(
            {
                "name": "region",
                "type": "string",
                "extract_hint": "区域名称，未提及传 NULL",
                "default_expr": "NULL",
                "required": False,
                "confidence": 0.68,
            }
        )
    if not params:
        params.append(
            {
                "name": "report_date",
                "type": "date",
                "extract_hint": "报表日期，默认今天",
                "default_expr": "TODAY",
                "required": True,
                "confidence": 0.72,
            }
        )

    name = "月度毛利归因报表" if "margin" in sql_lower or "毛利" in sql else "SQL 分析蓝图"
    output_schema = [
        {"column": "category", "semantic": "业务分类", "unit": "-", "role": "dimension", "confidence": 0.78},
        {"column": "revenue", "semantic": "营收金额", "unit": "元", "role": "metric", "confidence": 0.74},
        {"column": "gross_margin", "semantic": "毛利额", "unit": "元", "role": "metric", "confidence": 0.7},
        {"column": "margin_rate", "semantic": "毛利率", "unit": "%", "role": "metric", "confidence": 0.68},
    ]
    steps = [
        {
            "step": 1,
            "name": "基础数据筛选",
            "purpose": "按用户输入参数限定业务数据范围",
            "key_rules": ["过滤无效或取消状态记录", "按时间和区域参数裁剪数据"],
            "output_columns": [],
            "confidence": 0.8,
        },
        {
            "step": 2,
            "name": "业务指标聚合",
            "purpose": "汇总核心收入、成本和变化指标",
            "key_rules": ["按业务分类聚合", "保留最终 SELECT 输出列"],
            "output_columns": [c["column"] for c in output_schema],
            "confidence": 0.76,
        },
    ]
    return {
        "name": name,
        "description": "AI 根据 SQL 草稿提取的分析蓝图，请数据团队审核业务含义和低置信字段。",
        "trigger_keywords": ["毛利", "毛利率", "利润结构"] if "margin" in sql_lower else ["日报", "分析"],
        "trigger_examples": ["为什么本月毛利下降", "各品类毛利情况"]
        if "margin" in sql_lower
        else ["查看今天的分析报表", "本周业务日报"],
        "when_to_use": "当用户询问固定报表、归因分析或需要按参数运行既定 SQL 逻辑时使用。",
        "parameters": params,
        "implementation_type": "stored_procedure" if "procedure" in sql_lower else "sql_template",
        "call_template": "SELECT * FROM analyzed_blueprint(:params)",
        "output_schema": output_schema,
        "steps": steps,
        "attribution_hints": "优先关注核心度量的环比变化、排名变化和低于预期的分类。",
        "raw_sql": sql,
        "ai_confidence": 0.82,
        "low_confidence_fields": [
            {"path": "parameters.region", "confidence": 0.68, "reason": "区域参数语义需人工确认"},
            {"path": "output_schema.margin_rate", "confidence": 0.68, "reason": "输出列单位需确认"},
        ],
    }


@router.get("/{ds_id}/blueprints", response_model=List[schemas.BlueprintOut])
def list_blueprints(ds_id: int, status: str | None = None, db: Session = Depends(get_db)):
    _ensure_dataset(ds_id, db)
    q = db.query(models.AnalysisBlueprint).filter(models.AnalysisBlueprint.dataset_id == ds_id)
    if status:
        q = q.filter(models.AnalysisBlueprint.status == status)
    return q.order_by(models.AnalysisBlueprint.updated_at.desc(), models.AnalysisBlueprint.id.desc()).all()


@router.post("/{ds_id}/blueprints", response_model=schemas.BlueprintOut)
def create_blueprint(
    ds_id: int, payload: schemas.BlueprintCreate, db: Session = Depends(get_db)
):
    _ensure_dataset(ds_id, db)
    if payload.status not in BLUEPRINT_STATUSES:
        raise HTTPException(status_code=400, detail="蓝图状态不合法")
    bp = models.AnalysisBlueprint(dataset_id=ds_id, **payload.model_dump())
    db.add(bp)
    db.commit()
    db.refresh(bp)
    return bp


@router.post(
    "/{ds_id}/blueprints/analyze-sql", response_model=schemas.BlueprintAnalyzeTaskOut
)
def analyze_blueprint_sql(
    ds_id: int, payload: schemas.BlueprintAnalyzeSqlPayload, db: Session = Depends(get_db)
):
    _ensure_dataset(ds_id, db)
    if not payload.sql.strip():
        raise HTTPException(status_code=400, detail="sql 不能为空")
    task_id = str(uuid.uuid4())
    started_at = time.time()
    try:
        result = _mock_analyze_sql(payload.sql)
        BLUEPRINT_ANALYZE_TASKS[task_id] = {
            "task_id": task_id,
            "status": "done",
            "result": result,
            "error": None,
            "created_at": started_at,
        }
    except Exception as exc:
        BLUEPRINT_ANALYZE_TASKS[task_id] = {
            "task_id": task_id,
            "status": "failed",
            "result": None,
            "error": str(exc),
            "created_at": started_at,
        }
    return BLUEPRINT_ANALYZE_TASKS[task_id]


@router.get(
    "/{ds_id}/blueprints/analyze-sql/{task_id}",
    response_model=schemas.BlueprintAnalyzeTaskOut,
)
def get_blueprint_analyze_task(ds_id: int, task_id: str, db: Session = Depends(get_db)):
    _ensure_dataset(ds_id, db)
    task = BLUEPRINT_ANALYZE_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    return task


@router.get("/{ds_id}/blueprints/{bid}", response_model=schemas.BlueprintOut)
def get_blueprint(ds_id: int, bid: int, db: Session = Depends(get_db)):
    return _get_blueprint(ds_id, bid, db)


@router.put("/{ds_id}/blueprints/{bid}", response_model=schemas.BlueprintOut)
def update_blueprint(
    ds_id: int, bid: int, payload: schemas.BlueprintUpdate, db: Session = Depends(get_db)
):
    bp = _get_blueprint(ds_id, bid, db)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(bp, key, value)
    db.commit()
    db.refresh(bp)
    return bp


@router.patch("/{ds_id}/blueprints/{bid}/status", response_model=schemas.BlueprintOut)
def update_blueprint_status(
    ds_id: int, bid: int, payload: schemas.BlueprintStatusPayload, db: Session = Depends(get_db)
):
    bp = _get_blueprint(ds_id, bid, db)
    action = payload.action
    if action == "publish":
        if not (bp.last_test_result or {}).get("ok"):
            raise HTTPException(status_code=400, detail="发布前必须先完成一次测试")
        bp.status = "active"
        bp.version = (bp.version or 0) + 1
        snapshot = _blueprint_snapshot(bp)
        db.add(
            models.BlueprintVersion(
                blueprint_id=bp.id,
                version=bp.version,
                snapshot=snapshot,
                change_summary=payload.change_summary or f"发布 v{bp.version}",
                published_by=payload.published_by,
            )
        )
    elif action == "deprecate":
        bp.status = "deprecated"
    elif action == "reactivate":
        bp.status = "active"
    elif action in BLUEPRINT_STATUSES:
        bp.status = action
    else:
        raise HTTPException(status_code=400, detail="状态动作不合法")
    db.commit()
    db.refresh(bp)
    return bp


@router.post("/{ds_id}/blueprints/{bid}/test", response_model=schemas.BlueprintTestOut)
def test_blueprint(
    ds_id: int, bid: int, payload: schemas.BlueprintTestPayload, db: Session = Depends(get_db)
):
    bp = _get_blueprint(ds_id, bid, db)
    output_schema = bp.output_schema or []
    columns = [c.get("column") for c in output_schema if c.get("column")]
    if not columns:
        columns = ["category", "revenue", "gross_margin", "margin_rate"]
    sample_rows = [
        {columns[0]: "电子" if columns else "样例", **{c: i for i, c in enumerate(columns[1:], start=1)}},
        {columns[0]: "服饰" if columns else "样例", **{c: i * 2 for i, c in enumerate(columns[1:], start=1)}},
    ]
    result = {
        "ok": True,
        "execution_success": True,
        "execution_time_ms": 820,
        "columns": columns,
        "rows": sample_rows,
        "sql_preview": bp.call_template or "SELECT * FROM blueprint_result(:params)",
        "interpretation_preview": f"{bp.name} 测试成功，返回 {len(sample_rows)} 行 {len(columns)} 列。请确认样例结果和业务解读是否符合预期。",
        "error_message": None,
    }
    bp.last_validated_at = datetime.utcnow()
    bp.last_test_result = result
    db.add(
        models.BlueprintUsageLog(
            blueprint_id=bp.id,
            question=payload.question or "蓝图测试运行",
            extracted_params=payload.params,
            execution_success=True,
            execution_time_ms=result["execution_time_ms"],
        )
    )
    db.commit()
    return result


@router.get("/{ds_id}/blueprints/{bid}/versions", response_model=List[schemas.BlueprintVersionOut])
def list_blueprint_versions(ds_id: int, bid: int, db: Session = Depends(get_db)):
    _get_blueprint(ds_id, bid, db)
    return (
        db.query(models.BlueprintVersion)
        .filter(models.BlueprintVersion.blueprint_id == bid)
        .order_by(models.BlueprintVersion.version.desc())
        .all()
    )


@router.post("/{ds_id}/blueprints/{bid}/rollback", response_model=schemas.BlueprintOut)
def rollback_blueprint(
    ds_id: int, bid: int, payload: schemas.BlueprintRollbackPayload, db: Session = Depends(get_db)
):
    bp = _get_blueprint(ds_id, bid, db)
    version = (
        db.query(models.BlueprintVersion)
        .filter_by(blueprint_id=bid, version=payload.version)
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    _apply_blueprint_snapshot(bp, version.snapshot or {})
    bp.version = (bp.version or 0) + 1
    db.add(
        models.BlueprintVersion(
            blueprint_id=bp.id,
            version=bp.version,
            snapshot=_blueprint_snapshot(bp),
            change_summary=payload.change_summary or f"回滚到 v{payload.version}",
        )
    )
    db.commit()
    db.refresh(bp)
    return bp


@router.get("/{ds_id}/blueprints/{bid}/usage-stats")
def get_blueprint_usage_stats(ds_id: int, bid: int, db: Session = Depends(get_db)):
    bp = _get_blueprint(ds_id, bid, db)
    logs = db.query(models.BlueprintUsageLog).filter_by(blueprint_id=bid).all()
    total = len(logs)
    success = sum(1 for log in logs if log.execution_success)
    execution_times = [log.execution_time_ms for log in logs if log.execution_time_ms is not None]
    feedback_logs = [log for log in logs if log.user_feedback]
    thumbs_up = sum(1 for log in feedback_logs if log.user_feedback == "thumbs_up")
    return {
        "blueprint_id": bp.id,
        "usage_count": bp.usage_count or total,
        "total_logs": total,
        "execution_success_rate": round(success / total, 4) if total else 0,
        "avg_execution_time_ms": round(sum(execution_times) / len(execution_times))
        if execution_times
        else 0,
        "user_satisfaction_rate": round(thumbs_up / len(feedback_logs), 4)
        if feedback_logs
        else 0,
        "common_questions": [
            {"question": log.question, "count": 1}
            for log in logs[:5]
            if log.question
        ],
        "recent_failures": [
            {
                "question": log.question,
                "error_message": log.error_message,
                "created_at": log.created_at,
            }
            for log in logs
            if not log.execution_success
        ][:5],
    }


@router.get("/{ds_id}/blueprints/{bid}/usage-logs", response_model=List[schemas.BlueprintUsageLogOut])
def list_blueprint_usage_logs(ds_id: int, bid: int, db: Session = Depends(get_db)):
    _get_blueprint(ds_id, bid, db)
    return (
        db.query(models.BlueprintUsageLog)
        .filter_by(blueprint_id=bid)
        .order_by(models.BlueprintUsageLog.created_at.desc())
        .limit(100)
        .all()
    )


@router.post(
    "/{ds_id}/blueprints/{bid}/re-analyze",
    response_model=schemas.BlueprintAnalyzeTaskOut,
)
def re_analyze_blueprint_sql(
    ds_id: int,
    bid: int,
    payload: schemas.BlueprintAnalyzeSqlPayload,
    db: Session = Depends(get_db),
):
    bp = _get_blueprint(ds_id, bid, db)
    result = _mock_analyze_sql(payload.sql)
    result["diff_summary"] = {
        "name_changed": bp.name != result.get("name"),
        "parameter_count_before": len(bp.parameters or []),
        "parameter_count_after": len(result.get("parameters") or []),
        "step_count_before": len(bp.steps or []),
        "step_count_after": len(result.get("steps") or []),
    }
    task_id = str(uuid.uuid4())
    BLUEPRINT_ANALYZE_TASKS[task_id] = {
        "task_id": task_id,
        "status": "done",
        "result": result,
        "error": None,
        "created_at": time.time(),
    }
    return BLUEPRINT_ANALYZE_TASKS[task_id]


# ── LLM Auto Annotation ──────────────────────────────


@router.post("/{ds_id}/annotate-columns")
def annotate_dataset_columns(ds_id: int, db: Session = Depends(get_db)):
    """调用 LLM 自动标注 **当前数据集已选中的表**（非数据源下全量表）。

    委托给 app.services.annotation.annotate_table_columns（统一服务），
    同时标注 **表级**（ai_description / table_comment 增强）和 **列级**
    （ai_description / ai_semantic_role / ai_suggested_agg），并刷新 effective_desc。
    """
    logger.info(f"自动标注字段: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    # 只标注「当前数据集已选中的表」：避免对数据源下未选中的表烧 token
    selected_links = (
        db.query(models.DatasetSourceTable).filter_by(dataset_id=ds_id).all()
    )
    selected_table_ids = [link.source_table_id for link in selected_links]
    if not selected_table_ids:
        raise HTTPException(status_code=400, detail="该数据集尚未选择任何表，请先在「数据源表」中勾选要纳入数据集的表")

    tables = (
        db.query(models.SourceTable)
        .filter(models.SourceTable.id.in_(selected_table_ids))
        .all()
    )

    # 委托给统一标注服务（同时跑表级 + 列级，写 ai_description / effective_desc）
    from app.services.annotation import annotate_table_columns as svc_annotate

    total_annotated = 0
    total_skipped = 0
    total_table_annotated = 0
    failed_tables: list[dict] = []
    total_metrics = 0
    total_dims = 0
    total_times = 0

    for table in tables:
        try:
            result = svc_annotate(db, table.id, force=False)
        except Exception as e:
            logger.error(f"标注表 {table.table_name} 失败: {e}")
            failed_tables.append({"table": table.table_name, "error": str(e)})
            continue
        total_annotated += result.get("annotated", 0)
        total_skipped += result.get("skipped", 0)
        if result.get("table_annotated"):
            total_table_annotated += 1
        # 统计角色分布（基于本张表的最新结果）
        for c in table.columns:
            role = c.ai_semantic_role
            if role == "metric_candidate":
                total_metrics += 1
            elif role == "dimension_candidate":
                total_dims += 1
            elif role == "time_field":
                total_times += 1

    logger.info(
        f"自动标注完成: ds_id={ds_id}, tables={len(tables)} (已选), "
        f"annotated={total_annotated}, skipped={total_skipped}, "
        f"table_annotated={total_table_annotated}, "
        f"metrics={total_metrics}, dims={total_dims}, times={total_times}, "
        f"failed={len(failed_tables)}"
    )
    return {
        "ok": True,
        "metric_candidates": total_metrics,
        "dimension_candidates": total_dims,
        "time_fields": total_times,
        "tables_processed": len(tables),
        "table_annotated": total_table_annotated,
        "annotated": total_annotated,
        "skipped": total_skipped,
        "failed_tables": failed_tables,
    }


# ── YAML Import / Export ─────────────────────────────


@router.post("/{ds_id}/import-yaml")
def import_dataset_yaml(ds_id: int, payload: dict, db: Session = Depends(get_db)):
    """从 YAML 导入语义层配置（指标、维度、JOIN 关系）。"""
    logger.info(f"导入YAML: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    yaml_text = payload.get("yaml", "")
    if not yaml_text:
        raise HTTPException(status_code=400, detail="yaml 字段不能为空")

    try:
        data = yaml.safe_load(yaml_text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"YAML 解析失败: {e}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="YAML 根节点必须是对象")

    # 更新 tables_json
    tables_json = {"tables": [], "joins": []}
    if "tables" in data:
        tables_json["tables"] = data["tables"]
    if "joins" in data:
        tables_json["joins"] = data["joins"]
    ds.tables_json = tables_json

    # 导入指标
    imported_metrics = 0
    if "metrics" in data:
        for mdata in data["metrics"]:
            name = mdata.get("name")
            existing = (
                db.query(models.SemanticMetric).filter_by(dataset_id=ds_id, name=name).first()
            )
            metric_payload = {
                "name": name,
                "display_name": mdata.get("display_name", name),
                "expr": mdata.get("expression") or mdata.get("expr", ""),
                "table_name": mdata.get("table") or mdata.get("table_name"),
                "time_field": mdata.get("time_field"),
                "granularity": mdata.get("granularity"),
                "format_str": mdata.get("format") or mdata.get("format_str"),
                "filter_sql": mdata.get("filter_sql")
                or (mdata.get("filters", [""])[0] if mdata.get("filters") else None),
                "synonyms": mdata.get("synonyms", []),
                "description": mdata.get("description"),
            }
            if existing:
                for key, value in metric_payload.items():
                    setattr(existing, key, value)
            else:
                db.add(models.SemanticMetric(dataset_id=ds_id, **metric_payload))
                imported_metrics += 1

    # 导入维度
    imported_dims = 0
    if "dimensions" in data:
        for ddata in data["dimensions"]:
            name = ddata.get("name")
            existing = (
                db.query(models.SemanticDimension).filter_by(dataset_id=ds_id, name=name).first()
            )
            dim_payload = {
                "name": name,
                "display_name": ddata.get("display_name", name),
                "column_name": ddata.get("column") or ddata.get("column_name", ""),
                "table_name": ddata.get("table") or ddata.get("table_name"),
                "join_to": ddata.get("join_to"),
                "join_key": ddata.get("join_key"),
                "hierarchy": ddata.get("hierarchy"),
                "enum_values": ddata.get("enum_values", []),
                "synonyms": ddata.get("synonyms", []),
            }
            if existing:
                for key, value in dim_payload.items():
                    setattr(existing, key, value)
            else:
                db.add(models.SemanticDimension(dataset_id=ds_id, **dim_payload))
                imported_dims += 1

    db.commit()
    logger.info(f"YAML导入成功: metrics={imported_metrics}, dims={imported_dims}")
    return {
        "ok": True,
        "metrics_imported": imported_metrics,
        "dimensions_imported": imported_dims,
        "tables_json_updated": bool(tables_json["tables"] or tables_json["joins"]),
    }


@router.get("/{ds_id}/export-yaml")
def export_dataset_yaml(ds_id: int, db: Session = Depends(get_db)):
    """将当前数据集的语义层配置导出为 YAML。"""
    logger.info(f"导出YAML: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    metrics = db.query(models.SemanticMetric).filter_by(dataset_id=ds_id).all()
    dimensions = db.query(models.SemanticDimension).filter_by(dataset_id=ds_id).all()

    tables_json = ds.tables_json or {}

    data = {
        "dataset": {
            "name": ds.name,
            "description": ds.description,
            "datasource_id": ds.datasource_id,
        },
        "tables": tables_json.get("tables", []),
        "joins": tables_json.get("joins", []),
        "metrics": [],
        "dimensions": [],
    }

    for m in metrics:
        data["metrics"].append(
            {
                "name": m.name,
                "display_name": m.display_name,
                "expression": m.expr,
                "table_name": m.table_name,
                "time_field": m.time_field,
                "filter_sql": m.filter_sql,
                "granularity": m.granularity,
                "format_str": m.format_str,
                "synonyms": m.synonyms or [],
                "description": m.description,
            }
        )

    for d in dimensions:
        data["dimensions"].append(
            {
                "name": d.name,
                "display_name": d.display_name,
                "column_name": d.column_name,
                "table_name": d.table_name,
                "join_to": d.join_to,
                "join_key": d.join_key,
                "hierarchy": d.hierarchy,
                "enum_values": d.enum_values or [],
                "synonyms": d.synonyms or [],
            }
        )

    yaml_text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    logger.info(f"YAML导出成功: ds_id={ds_id}")
    return {"yaml": yaml_text}


# ── Dataset Source Table Selection ───────────────────


@router.post("/{ds_id}/select-tables")
def select_tables_for_dataset(
    ds_id: int,
    payload: schemas.SelectTablesPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """批量选择 source_table 加入当前数据集，并异步触发 AI 标注。"""
    logger.info(f"选择表: ds_id={ds_id}, table_ids={payload.source_table_ids}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    added = 0
    added_table_ids = []
    for st_id in payload.source_table_ids:
        st = db.get(models.SourceTable, st_id)
        if not st:
            continue
        # 检查是否已存在
        existing = (
            db.query(models.DatasetSourceTable)
            .filter_by(dataset_id=ds_id, source_table_id=st_id)
            .first()
        )
        if not existing:
            db.add(models.DatasetSourceTable(dataset_id=ds_id, source_table_id=st_id))
            added += 1
            added_table_ids.append(st_id)

    db.commit()

    # 异步触发 AI 标注（只对新加入的表）
    if added_table_ids:
        from app.services.annotation import annotate_table_columns

        for st_id in added_table_ids:
            background_tasks.add_task(annotate_table_columns, db, st_id)
        logger.info(f"异步触发标注: tables={len(added_table_ids)}")

    logger.info(f"选择表完成: added={added}")
    return {"ok": True, "added": added}


@router.delete("/{ds_id}/select-tables/{source_table_id}")
def deselect_table_from_dataset(ds_id: int, source_table_id: int, db: Session = Depends(get_db)):
    """从数据集中移除某张 source_table。"""
    logger.info(f"移除表: ds_id={ds_id}, source_table_id={source_table_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    link = (
        db.query(models.DatasetSourceTable)
        .filter_by(dataset_id=ds_id, source_table_id=source_table_id)
        .first()
    )
    if link:
        db.delete(link)
        db.commit()
        logger.info(f"表移除成功: source_table_id={source_table_id}")
    return {"ok": True}


@router.get("/{ds_id}/selected-tables")
def list_selected_tables(ds_id: int, db: Session = Depends(get_db)):
    """获取数据集已选中的 source_table 列表。"""
    logger.info(f"获取已选表: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    links = db.query(models.DatasetSourceTable).filter_by(dataset_id=ds_id).all()
    result = []
    for link in links:
        st = link.source_table
        result.append(
            {
                "id": st.id,
                "dataset_link_id": link.id,
                "schema_name": st.schema_name,
                "table_name": st.table_name,
                "table_comment": st.table_comment,
                "ai_description": st.ai_description,
                "user_description": st.user_description,
                "effective_desc": st.effective_desc,
                "desc_source": st.desc_source,
                "annotated_at": st.annotated_at,
                "row_count_approx": st.row_count_approx,
                "column_count": len(st.columns),
            }
        )
    logger.info(f"返回 {len(result)} 个已选表")
    return result


@router.get("/{ds_id}/selected-columns")
def list_selected_columns(ds_id: int, db: Session = Depends(get_db)):
    """获取数据集所有已选表的字段（合并返回，含 table_name）。"""
    logger.info(f"获取已选字段: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    links = db.query(models.DatasetSourceTable).filter_by(dataset_id=ds_id).all()
    result = []
    for link in links:
        st = link.source_table
        for col in st.columns:
            result.append(_source_column_payload(col))
    # 按表名、字段位置排序
    result.sort(key=lambda c: (c["table_name"], c["ordinal_position"] or 0))
    logger.info(f"返回 {len(result)} 个字段")
    return result
