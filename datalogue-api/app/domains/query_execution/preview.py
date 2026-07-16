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
import sqlglot
from sqlglot import exp
from app.domains.query_execution.dialect.adapter import normalize_execution_dialect

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


_MAX_PREVIEW_ROWS = 10000


def _parse_sql(sql: str, dialect: str) -> exp.Expression | None:
    """按目标方言解析 SQL，解析失败返回 None。"""
    try:
        parsed = sqlglot.parse_one(sql, read=dialect)
        return parsed if isinstance(parsed, exp.Expression) else None
    except (sqlglot.errors.ParseError, sqlglot.errors.SqlglotError, ValueError):
        return None


def _sql_without_limit(expression: exp.Expression) -> exp.Expression:
    """返回去掉外层 LIMIT/FETCH 的 SQL 表达式副本。"""
    cloned = expression.copy()
    cloned.set("limit", None)
    cloned.set("fetch", None)
    return cloned


def _build_count_sql(expression: exp.Expression, dialect: str) -> str:
    """把查询包成 SELECT COUNT(*) FROM (... ) cnt，去掉内层 ORDER BY 避免部分数据库报错。"""
    inner = _sql_without_limit(expression)
    inner.set("order", None)
    # 内层可能是 Select/Union；sqlglot 的 subquery() 在 Query 子类上定义，运行时全部实现，
    # 类型上补一个断言避免 mypy 抱怨 Expression 基类没有该方法。
    subquery = inner.subquery("cnt")  # type: ignore[attr-defined]
    count_expr = exp.select(exp.Count(this=exp.Star())).from_(subquery)
    return count_expr.sql(dialect=dialect)


def _apply_max_row_limit(expression: exp.Expression, dialect: str, max_rows: int) -> str:
    """应用预览绝对上限；已有更小 LIMIT 时必须原样保留。"""
    current_limit = expression.args.get("limit")
    current_value = None
    if isinstance(current_limit, exp.Limit):
        value = current_limit.args.get("expression")
        if isinstance(value, exp.Literal) and not value.is_string:
            try:
                current_value = int(value.this)
            except (TypeError, ValueError):
                current_value = None
    target_limit = min(current_value, max_rows) if current_value is not None else max_rows
    expression.set("limit", exp.Limit(expression=exp.Literal.number(target_limit)))
    expression.set("fetch", None)
    return expression.sql(dialect=dialect)


def _execute_count(conn, count_sql: str) -> int | None:
    """执行 COUNT(*) SQL，失败返回 None。"""
    try:
        result_proxy = conn.execute(text(count_sql))
        row = result_proxy.fetchone()
        if row is None:
            return None
        value = row[0]
        return int(value) if value is not None else None
    except Exception:
        return None


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

    raw_dialect = (
        getattr(datasource, "dialect", None)
        or normalize_db_type(getattr(datasource, "db_type", None))
        or "postgres"
    )
    dialect = normalize_execution_dialect(raw_dialect) or str(raw_dialect).lower()
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
            # 先执行 COUNT(*) 获知真实总量；失败时降级为直接执行原 SQL。
            total_row_count: int | None = None
            parsed = _parse_sql(normalized_sql, dialect)
            if parsed is not None:
                count_sql = _build_count_sql(parsed, dialect)
                try:
                    total_row_count = _execute_count(conn, count_sql)
                except Exception as exc:
                    logger.warning(
                        "SQL preview COUNT 执行失败，降级为直接执行: dataset_id=%s error=%s",
                        dataset_id,
                        exc,
                    )
                if total_row_count is not None and total_row_count > _MAX_PREVIEW_ROWS:
                    normalized_sql = _apply_max_row_limit(parsed, dialect, _MAX_PREVIEW_ROWS)

            result_proxy = conn.execute(text(normalized_sql))
            columns = list(result_proxy.keys())
            rows: list[dict[str, Any]] = []
            for row in result_proxy:
                mapping = row._mapping
                rows.append({column: _jsonable_value(mapping[column]) for column in columns})

            effective_total_row_count = (
                total_row_count if total_row_count is not None else len(rows)
            )

        logger.info(
            "SQL preview 执行成功: dataset_id=%s question=%s row_count=%s total_row_count=%s",
            dataset_id,
            question,
            len(rows),
            effective_total_row_count,
        )
        return jsonable_encoder(
            {
                "dataset_id": dataset_id,
                "sql": normalized_sql,
                "columns": columns,
                "rows": rows,
                # row_count 表示本次 artifact 实际可见结果；全量候选规模单独放 total_row_count。
                "row_count": len(rows),
                "total_row_count": effective_total_row_count,
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
