# ============================================================
# File Name   : report.py
# Description:
#   本地观测索引报表聚合服务。
#
# Responsibilities:
#   - 基于 observability_trace_index 生成成本、质量和失败摘要。
#   - 为管理端和客户报表提供轻量 API 数据。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models


def build_observability_summary(db: Session, *, dataset_id: int | None = None) -> dict:
    query = db.query(models.ObservabilityTraceIndex)
    if dataset_id is not None:
        query = query.filter(models.ObservabilityTraceIndex.dataset_id == dataset_id)
    total = query.count()
    failed = query.filter(models.ObservabilityTraceIndex.status == "failed").count()
    tokens = query.with_entities(func.coalesce(func.sum(models.ObservabilityTraceIndex.total_tokens), 0)).scalar()
    return {
        "total_traces": total,
        "failed_traces": failed,
        "success_rate": round((total - failed) / total, 4) if total else None,
        "total_tokens": int(tokens or 0),
    }


def build_cost_report(db: Session, *, dataset_id: int | None = None) -> dict:
    query = db.query(models.ObservabilityTraceIndex)
    if dataset_id is not None:
        query = query.filter(models.ObservabilityTraceIndex.dataset_id == dataset_id)
    cost = query.with_entities(func.coalesce(func.sum(models.ObservabilityTraceIndex.total_cost), 0)).scalar()
    tokens = query.with_entities(func.coalesce(func.sum(models.ObservabilityTraceIndex.total_tokens), 0)).scalar()
    return {
        "total_cost": float(cost or 0),
        "total_tokens": int(tokens or 0),
        "currency": "USD",
    }


def build_quality_report(db: Session, *, dataset_id: int | None = None) -> dict:
    query = db.query(models.ObservabilityTraceIndex)
    if dataset_id is not None:
        query = query.filter(models.ObservabilityTraceIndex.dataset_id == dataset_id)
    total = query.count()
    failed = query.filter(models.ObservabilityTraceIndex.status == "failed").count()
    return {
        "total_traces": total,
        "failed_traces": failed,
        "failure_rate": round(failed / total, 4) if total else None,
    }


def build_failure_report(db: Session, *, dataset_id: int | None = None) -> dict:
    query = db.query(models.ObservabilityTraceIndex.status, func.count(models.ObservabilityTraceIndex.id))
    if dataset_id is not None:
        query = query.filter(models.ObservabilityTraceIndex.dataset_id == dataset_id)
    rows = query.group_by(models.ObservabilityTraceIndex.status).all()
    return {
        "by_status": [{"status": status or "unknown", "count": count} for status, count in rows],
    }
