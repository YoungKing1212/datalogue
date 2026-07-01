# ============================================================
# File Name   : observability.py
# Description:
#   Observability 可观测报表 API。
#
# Responsibilities:
#   - 暴露 trace、成本、质量和失败统计。
#   - 为后续管理端和客户报表提供统一数据入口。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.observability.report import (
    build_cost_report,
    build_failure_report,
    build_observability_summary,
    build_quality_report,
)
from app.services.observability.traces import (
    get_query_audit_trace,
    list_query_audit_traces,
)

router = APIRouter()


@router.get("/summary")
def observability_summary(
    dataset_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """获取本地 trace 索引摘要。"""

    return build_observability_summary(db, dataset_id=dataset_id)


@router.get("/costs")
def observability_costs(
    dataset_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """获取成本和 token 聚合。"""

    return build_cost_report(db, dataset_id=dataset_id)


@router.get("/quality")
def observability_quality(
    dataset_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """获取问数质量摘要。"""

    return build_quality_report(db, dataset_id=dataset_id)


@router.get("/failures")
def observability_failures(
    dataset_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """获取失败类型摘要。"""

    return build_failure_report(db, dataset_id=dataset_id)


@router.get("/traces")
def observability_traces(
    dataset_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """获取 Datalogue 查询审计 trace 列表。"""

    return list_query_audit_traces(
        db,
        dataset_id=dataset_id,
        status=status,
        limit=limit,
    )


@router.get("/traces/{trace_id}")
def observability_trace_detail(
    trace_id: str,
    db: Session = Depends(get_db),
):
    """获取单条 trace 详情，包含 Observability 数据和本地 fallback。"""

    return get_query_audit_trace(db, trace_id=trace_id)
