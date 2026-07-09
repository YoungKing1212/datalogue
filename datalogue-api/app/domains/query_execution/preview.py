# ============================================================
# File Name   : preview.py
# Description:
#   查询执行领域的数据集级只读 SQL 预览执行服务。
#
# Responsibilities:
#   - 复用 SQL Guard 校验 Hermes 生成的只读 SQL。
#   - 限制 SQL 只能访问当前数据集已选择的 source tables。
#   - 通过数据集绑定数据源执行预览查询，不进入 LeadAgent/LangGraph 链路。
#
# Author      : yangkai
# Created On  : 2026-06-23
# ============================================================

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
import logging
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import models
from app.domains.data_source.service import create_engine_for_datasource, normalize_db_type
from app.domains.query_execution.query_constraints import normalize_query_constraints
from app.domains.query_execution.guard import guard_readonly_sql

logger = logging.getLogger(__name__)


def _empty_response(
    *,
    dataset_id: int,
    sql: str,
    error: str,
    sql_guard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成结构化失败响应，保持 Hermes 侧错误解析稳定。"""

    return {
        "dataset_id": dataset_id,
        "sql": sql,
        "columns": [],
        "rows": [],
        "row_count": 0,
        "sql_guard": sql_guard
        or {
            "ok": False,
            "normalized_sql": None,
            "code": None,
            "error": error,
            "keyword": None,
            "warnings": [],
        },
        "error": error,
    }


def _selected_table_names(db: Session, dataset_id: int) -> list[str]:
    """读取当前数据集显式选择的物理表名，供 SQL Guard 做授权边界。"""

    rows = (
        db.query(models.SourceTable)
        .join(
            models.DatasetSourceTable,
            models.DatasetSourceTable.source_table_id == models.SourceTable.id,
        )
        .filter(models.DatasetSourceTable.dataset_id == dataset_id)
        .all()
    )
    names: list[str] = []
    for table in rows:
        table_name = getattr(table, "table_name", None)
        schema_name = getattr(table, "schema_name", None)
        if table_name:
            names.append(str(table_name))
        if schema_name and table_name:
            names.append(f"{schema_name}.{table_name}")
    return names


def _preview_constraints(dataset: models.SemanticDataset, limit: int | None) -> dict[str, Any]:
    """合并数据集查询约束和本次预览 limit，不能绕过 max_limit。"""

    constraints = normalize_query_constraints(getattr(dataset, "query_constraints", None))
    if limit is not None:
        # preview 的 limit 只作为本次默认行数；最终仍由 normalize/guard 按 max_limit 裁剪。
        constraints["default_limit"] = max(1, int(limit))
    return normalize_query_constraints(constraints)


def _jsonable_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def preview_dataset_sql(
    db: Session,
    *,
    dataset: models.SemanticDataset,
    sql: str,
    question: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """执行数据集范围内的只读 SQL 预览，不写 conversation/message/trace。"""

    dataset_id = int(dataset.id)
    raw_sql = (sql or "").strip()
    datasource = db.get(models.Datasource, dataset.datasource_id)
    if not datasource:
        logger.warning("SQL preview 数据源缺失: dataset_id=%s", dataset_id)
        return _empty_response(
            dataset_id=dataset_id,
            sql=raw_sql,
            error="当前数据集绑定的数据源不存在，无法执行 SQL 预览",
        )

    allowed_tables = _selected_table_names(db, dataset_id)
    if not allowed_tables:
        logger.warning("SQL preview 未配置已选表: dataset_id=%s", dataset_id)
        return _empty_response(
            dataset_id=dataset_id,
            sql=raw_sql,
            error="当前数据集未选择可查询的数据表，无法执行 SQL 预览",
        )

    dialect = (
        getattr(datasource, "dialect", None)
        or normalize_db_type(getattr(datasource, "db_type", None))
        or "postgres"
    )
    constraints = _preview_constraints(dataset, limit)
    # 这里是 Hermes 直连问数的核心边界：先静态校验只读、单语句、授权表和 LIMIT，再连接数据源。
    guard_result = guard_readonly_sql(
        raw_sql,
        dialect=dialect,
        query_constraints=constraints,
        allowed_tables=allowed_tables,
    )
    guard_payload = asdict(guard_result)
    if not guard_result.ok:
        logger.warning(
            "SQL preview 被 Guard 拦截: dataset_id=%s code=%s error=%s",
            dataset_id,
            guard_result.code,
            guard_result.error,
        )
        return _empty_response(
            dataset_id=dataset_id,
            sql=raw_sql,
            error=guard_result.error or "SQL Guard 拦截",
            sql_guard=guard_payload,
        )

    normalized_sql = guard_result.normalized_sql or raw_sql
    engine = create_engine_for_datasource(datasource)
    try:
        with engine.connect() as conn:
            result_proxy = conn.execute(text(normalized_sql))
            columns = list(result_proxy.keys())
            rows: list[dict[str, Any]] = []
            for row in result_proxy:
                mapping = row._mapping
                rows.append({column: _jsonable_value(mapping[column]) for column in columns})

        logger.info(
            "SQL preview 执行成功: dataset_id=%s question=%s row_count=%s",
            dataset_id,
            question,
            len(rows),
        )
        return jsonable_encoder(
            {
                "dataset_id": dataset_id,
                "sql": normalized_sql,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "sql_guard": guard_payload,
                "error": None,
            }
        )
    except Exception as exc:
        logger.warning("SQL preview 执行失败: dataset_id=%s error=%s", dataset_id, exc)
        return _empty_response(
            dataset_id=dataset_id,
            sql=normalized_sql,
            error=f"SQL 执行失败: {exc}",
            sql_guard=guard_payload,
        )
    finally:
        engine.dispose()
