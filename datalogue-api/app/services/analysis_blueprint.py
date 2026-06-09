# ============================================================
# File Name   : analysis_blueprint.py
# Description:
#   分析蓝图真实执行服务。
#
# Responsibilities:
#   - 校验并执行已发布分析蓝图的只读 SQL 模板。
#   - 提取默认参数、写入执行日志并返回结构化结果。
#
# Author      : yangkai
# Created On  : 2026-06-08
# ============================================================

import logging
import re
import time
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.dataset import AnalysisBlueprint, BlueprintUsageLog, SemanticDataset
from app.models.datasource import Datasource
from app.services.datasource import create_engine_for_datasource

logger = logging.getLogger(__name__)


def _default_blueprint_param(default_expr: str | None) -> Any:
    """解析蓝图参数的内置默认表达式。"""
    if not default_expr:
        return None
    expr = default_expr.strip().upper()
    today = date.today()
    if expr == "TODAY":
        return today.isoformat()
    if expr == "MONTH_START":
        return today.replace(day=1).isoformat()
    if expr == "NULL":
        return None
    return default_expr


def _extract_date_range(question: str) -> tuple[str | None, str | None]:
    """从中文问题中提取常见年份/月度日期范围。"""
    text = question or ""
    month_match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", text)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        if 1 <= month <= 12:
            last_day = monthrange(year, month)[1]
            return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"

    year_match = re.search(r"(\d{4})\s*年", text)
    if year_match:
        year = int(year_match.group(1))
        return f"{year:04d}-01-01", f"{year:04d}-12-31"

    return None, None


def _extract_person_name(question: str) -> str | None:
    """从“某人的日报/任务/记录”等问法中提取人员姓名。"""
    text = re.sub(r"\d{4}\s*年\s*(?:\d{1,2}\s*月)?", "", question or "")
    text = re.sub(r"^(?:我要|我想|帮我)?(?:查询|查看|查一下|查)", "", text)
    patterns = (
        r"([\u4e00-\u9fa5]{2,4})的(?:日报|周报|月报|任务|记录|明细)",
        r"(?:查询|查看|查一下|查|我要查询)([\u4e00-\u9fa5]{2,4})(?:在|的|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1)
            if name not in {"我要", "查询", "查看", "日报", "任务", "记录"}:
                return name
    return None


def _is_start_date_param(name: str) -> bool:
    """判断参数是否表达开始日期。"""
    normalized = name.lower()
    return normalized in {"start_date", "start", "begin_date", "from_date"} or "开始" in name


def _is_end_date_param(name: str) -> bool:
    """判断参数是否表达结束日期。"""
    normalized = name.lower()
    return normalized in {"end_date", "end", "to_date", "finish_date"} or "结束" in name


def _is_person_param(name: str) -> bool:
    """判断参数是否表达人员姓名。"""
    normalized = name.lower()
    return any(key in normalized for key in ("person", "user", "employee", "name")) or any(
        key in name for key in ("人员", "姓名", "员工")
    )


def extract_blueprint_params(
    bp: AnalysisBlueprint,
    question: str,
    input_params: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """从问题、默认值和显式输入中提取执行参数。"""
    params: dict[str, Any] = {}
    missing: list[str] = []
    explicit_params = input_params or {}
    date_values = re.findall(r"\d{4}-\d{2}-\d{2}", question or "")
    range_start, range_end = _extract_date_range(question or "")
    person_name = _extract_person_name(question or "")
    date_index = 0

    for spec in bp.parameters or []:
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        if not name:
            continue

        value = explicit_params.get(name)
        param_type = str(spec.get("type") or "").lower()
        if value is None and param_type == "date" and range_start and _is_start_date_param(name):
            value = range_start
        if value is None and param_type == "date" and range_end and _is_end_date_param(name):
            value = range_end
        if value is None and param_type == "date" and date_index < len(date_values):
            value = date_values[date_index]
            date_index += 1
        if value is None and person_name and _is_person_param(name):
            value = person_name
        if value is None:
            value = _default_blueprint_param(spec.get("default_expr"))
        if value is None and spec.get("required"):
            missing.append(name)
        params[name] = value

    for key, value in explicit_params.items():
        if key not in params:
            params[key] = value

    return params, missing


def validate_blueprint_sql(sql: str) -> str | None:
    """校验蓝图执行 SQL，只允许只读查询。"""
    sql_clean = (sql or "").strip()
    if not sql_clean:
        return "分析蓝图未配置可执行 SQL"
    if not re.match(r"^(select|with)\b", sql_clean, flags=re.IGNORECASE):
        return "分析蓝图执行器只允许 SELECT/WITH 只读查询"

    forbidden = [
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "create",
        "grant",
        "truncate",
        "merge",
        "replace",
    ]
    sql_lower = sql_clean.lower()
    for kw in forbidden:
        if re.search(rf"\b{kw}\b", sql_lower):
            return f"分析蓝图 SQL 包含危险关键字 '{kw}'，已拦截"
    return None


def execute_analysis_blueprint(
    db: Session,
    bp: AnalysisBlueprint,
    question: str = "",
    input_params: dict[str, Any] | None = None,
    require_active: bool = True,
    count_usage: bool = True,
    limit: int = 500,
) -> dict[str, Any]:
    """执行分析蓝图并返回结构化执行结果。"""
    if require_active and bp.status != "active":
        return {"ok": False, "error": "分析蓝图尚未发布，不能执行", "params": {}}

    dataset = db.get(SemanticDataset, bp.dataset_id)
    datasource = db.get(Datasource, dataset.datasource_id) if dataset else None
    if not datasource:
        return {"ok": False, "error": "分析蓝图所属数据集没有可用数据源", "params": {}}

    sql = (bp.call_template or bp.raw_sql or "").strip()
    params, missing = extract_blueprint_params(bp, question, input_params)
    if missing:
        return {
            "ok": False,
            "error": "运行分析蓝图前还需要补充参数：" + "、".join(missing),
            "params": params,
            "missing": missing,
            "sql": sql,
        }

    validation_error = validate_blueprint_sql(sql)
    if validation_error:
        db.add(
            BlueprintUsageLog(
                blueprint_id=bp.id,
                question=question,
                extracted_params=params,
                execution_success=False,
                error_message=validation_error,
            )
        )
        db.commit()
        return {"ok": False, "error": validation_error, "params": params, "sql": sql}

    engine = create_engine_for_datasource(datasource)
    started_at = time.monotonic()
    try:
        with engine.connect() as conn:
            result_proxy = conn.execute(text(sql), params)
            columns = list(result_proxy.keys())
            rows = []
            for row in result_proxy:
                row_dict = {}
                for col, val in zip(columns, row):
                    if isinstance(val, Decimal):
                        val = float(val)
                    row_dict[col] = val
                rows.append(row_dict)
                if len(rows) >= limit:
                    break

        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        column_labels = {
            c.get("column"): c.get("semantic")
            for c in (bp.output_schema or [])
            if c.get("column") and c.get("semantic")
        }
        sql_result = {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "column_labels": column_labels,
            "blueprint_id": bp.id,
            "blueprint_name": bp.name,
            "execution_time_ms": elapsed_ms,
            "params": params,
        }
        if count_usage:
            bp.usage_count = (bp.usage_count or 0) + 1
        db.add(
            BlueprintUsageLog(
                blueprint_id=bp.id,
                question=question,
                extracted_params=params,
                execution_success=True,
                execution_time_ms=elapsed_ms,
            )
        )
        db.commit()
        return {
            "ok": True,
            "sql": sql,
            "sql_result": sql_result,
            "params": params,
            "execution_time_ms": elapsed_ms,
        }
    except Exception as e:
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        logger.exception("分析蓝图执行失败: %s", e)
        db.add(
            BlueprintUsageLog(
                blueprint_id=bp.id,
                question=question,
                extracted_params=params,
                execution_success=False,
                execution_time_ms=elapsed_ms,
                error_message=str(e),
            )
        )
        db.commit()
        return {
            "ok": False,
            "error": f"分析蓝图执行失败: {e}",
            "sql": sql,
            "params": params,
            "execution_time_ms": elapsed_ms,
        }
    finally:
        engine.dispose()
