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

from app.core.models.dataset import AnalysisBlueprint, BlueprintUsageLog, SemanticDataset
from app.core.models.datasource import Datasource
from app.domains.data_source.service import build_datasource_context, create_engine_for_datasource
from app.domains.query_execution.guard import guard_readonly_sql
from app.domains.query_execution.dialect.adapter import normalize_execution_dialect

logger = logging.getLogger(__name__)


class BlueprintExecutionTimeout(Exception):
    """蓝图执行超时的内部异常标记。"""


DIAGNOSIS_TITLES = {
    "NOT_ACTIVE": "蓝图尚未发布",
    "DATASOURCE_MISSING": "数据源不可用",
    "MISSING_PARAMS": "缺少运行参数",
    "UNSAFE_SQL": "SQL 安全校验未通过",
    "TIMEOUT": "蓝图执行超时",
    "EXECUTION_ERROR": "SQL 执行失败",
}

DIAGNOSIS_ACTIONS = {
    "NOT_ACTIVE": "先发布蓝图，或在测试入口中执行校验。",
    "DATASOURCE_MISSING": "检查数据集是否绑定了可用数据源。",
    "MISSING_PARAMS": "补充缺失参数后重新测试。",
    "UNSAFE_SQL": "仅允许 SELECT/WITH 只读查询，移除写操作或 DDL 语句。",
    "TIMEOUT": "缩小查询范围、增加过滤条件或适当调大超时时间。",
    "EXECUTION_ERROR": "检查 SQL 模板、参数名、表字段和数据源连接状态。",
}

SENSITIVE_COLUMN_PATTERN = re.compile(
    r"(phone|mobile|tel|email|mail|id_card|identity|idcard|token|secret|password|passwd|pwd|key|api_key|access_key|credential)",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-]{1,3})[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
MOBILE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
ID_CARD_PATTERN = re.compile(r"(?<!\d)(\d{6})\d{8}([\dXx]{4})(?!\d)")
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_\-.=]{24,}$")


def _build_diagnosis(code: str, detail: str = "") -> dict[str, str]:
    """构造蓝图执行失败的结构化诊断。"""
    return {
        "code": code,
        "title": DIAGNOSIS_TITLES.get(code, "蓝图执行失败"),
        "detail": detail,
        "suggested_action": DIAGNOSIS_ACTIONS.get(code, "根据错误信息调整配置后重试。"),
    }


def _write_blueprint_usage_log(
    db: Session,
    bp: AnalysisBlueprint,
    question: str,
    params: dict[str, Any],
    success: bool,
    elapsed_ms: int | None = None,
    row_count: int = 0,
    diagnosis: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    """写入蓝图执行日志，测试执行也保留日志但不增加 usage_count。"""
    db.add(
        BlueprintUsageLog(
            blueprint_id=bp.id,
            question=question,
            extracted_params=params,
            execution_success=success,
            execution_time_ms=elapsed_ms,
            row_count=row_count,
            diagnosis=diagnosis,
            error_message=error_message,
        )
    )
    db.commit()


def _mask_sensitive_value(column: str, value: Any) -> tuple[Any, bool]:
    """根据字段名和值规则脱敏单个单元格。"""
    if value is None:
        return value, False
    text_value = str(value)
    is_sensitive_column = bool(SENSITIVE_COLUMN_PATTERN.search(column or ""))
    masked = text_value
    changed = False

    new_value = EMAIL_PATTERN.sub(r"\1***\2", masked)
    changed = changed or new_value != masked
    masked = new_value

    new_value = MOBILE_PATTERN.sub(r"\1****\2", masked)
    changed = changed or new_value != masked
    masked = new_value

    new_value = ID_CARD_PATTERN.sub(r"\1********\2", masked)
    changed = changed or new_value != masked
    masked = new_value

    if TOKEN_PATTERN.fullmatch(masked):
        masked = f"{masked[:4]}***{masked[-4:]}"
        changed = True

    if is_sensitive_column and not changed:
        if len(masked) <= 4:
            masked = "***"
        else:
            masked = f"***{masked[-4:]}"
        changed = True

    return masked if changed else value, changed


def _mask_blueprint_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """统一脱敏蓝图查询结果并返回脱敏摘要。"""
    masked_rows: list[dict[str, Any]] = []
    masked_columns: set[str] = set()
    masked_cells = 0

    for row in rows:
        masked_row: dict[str, Any] = {}
        for column, value in row.items():
            masked_value, changed = _mask_sensitive_value(column, value)
            masked_row[column] = masked_value
            if changed:
                masked_columns.add(column)
                masked_cells += 1
        masked_rows.append(masked_row)

    return masked_rows, {
        "masked_cells": masked_cells,
        "masked_columns": sorted(masked_columns),
    }


def _datasource_dialect(datasource: Datasource) -> str:
    """获取数据源方言标识。"""
    context = build_datasource_context(datasource)
    value = (context or {}).get("dialect") or getattr(datasource, "db_type", None) or ""
    return normalize_execution_dialect(value) or str(value).lower()


def _get_raw_connection(conn: Any) -> Any:
    """兼容 SQLAlchemy 1.x/2.x 获取底层 DBAPI 连接。"""
    connection = getattr(conn, "connection", None)
    if connection is None:
        return None
    return getattr(connection, "driver_connection", None) or getattr(connection, "connection", None)


def _apply_database_timeout(conn: Any, datasource: Datasource, timeout_seconds: int):
    """按方言 best-effort 设置数据库级超时，返回清理函数。"""
    timeout_ms = max(1, int(timeout_seconds)) * 1000
    dialect = _datasource_dialect(datasource)
    cleanup = None

    try:
        if dialect in {"postgres", "postgresql"}:
            conn.execute(text(f"SET statement_timeout = {timeout_ms}"))
        elif dialect in {"mysql", "mariadb"}:
            conn.execute(text(f"SET SESSION max_execution_time = {timeout_ms}"))
        elif dialect == "sqlite":
            raw_conn = _get_raw_connection(conn)
            if hasattr(raw_conn, "set_progress_handler"):
                started_at = time.monotonic()

                def _timeout_handler():
                    return 1 if time.monotonic() - started_at > timeout_seconds else 0

                raw_conn.set_progress_handler(_timeout_handler, 1000)

                def cleanup():
                    raw_conn.set_progress_handler(None, 0)

        else:
            raw_conn = _get_raw_connection(conn)
            if hasattr(raw_conn, "call_timeout"):
                raw_conn.call_timeout = timeout_ms
    except Exception as exc:
        logger.warning("数据库级超时设置失败，继续执行蓝图: dialect=%s error=%s", dialect, exc)
    return cleanup


def _is_timeout_exception(exc: Exception) -> bool:
    """识别常见方言超时异常。"""
    if isinstance(exc, BlueprintExecutionTimeout):
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "timeout",
            "timed out",
            "statement timeout",
            "max_execution_time",
            "query execution was interrupted",
            "interrupted",
            "canceling statement due to statement timeout",
        )
    )


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


def _sql_literal(value: Any) -> str:
    """把蓝图参数转成仅用于展示的 SQL 字面量。执行仍使用绑定参数。"""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, date):
        return f"'{value.isoformat()}'"
    text_value = str(value).replace("'", "''")
    return f"'{text_value}'"


def render_blueprint_sql_preview(sql: str, params: dict[str, Any]) -> str:
    """渲染带参数值的 SQL 预览，缺失参数保留 :name 占位符。"""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            return match.group(0)
        return _sql_literal(params[name])

    return re.sub(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)", replace, sql or "")


def _extract_date_range(question: str) -> tuple[str | None, str | None]:
    """从中文问题中提取常见年份/月度日期范围。"""
    text = question or ""
    today = date.today()
    relative_years = {
        "今年": today.year,
        "本年": today.year,
        "去年": today.year - 1,
        "上年": today.year - 1,
        "前年": today.year - 2,
    }
    for marker, year in relative_years.items():
        if marker in text:
            return f"{year:04d}-01-01", f"{year:04d}-12-31"

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
    # 相对时间词不属于姓名；先移除后再按“某人的日志/任务”模式提取。
    text = re.sub(r"(?:今年|本年|去年|上年|前年)", "", text)
    text = re.sub(r"^(?:我要|我想|帮我)?(?:查询|查看|查一下|查)", "", text)
    patterns = (
        # "XXX的[工作]日报" — 允许"的"和关键词之間有 0-2 个修饰字（工作、每日等）
        r"([\u4e00-\u9fa5]{2,4})的[\u4e00-\u9fa5]{0,2}(?:日报|周报|月报|日志|任务|记录|明细)",
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


def blueprint_params_from_time_context(
    bp: AnalysisBlueprint,
    time_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """把 LeadAgent TimeTool 的结构化时间范围转换为蓝图显式参数。"""

    detected = (time_context or {}).get("detected_time_range") or {}
    start_date = detected.get("start_date")
    end_date = detected.get("end_date")
    if not start_date or not end_date:
        return {}

    params: dict[str, Any] = {}
    for spec in bp.parameters or []:
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        if not name or str(spec.get("type") or "").lower() != "date":
            continue
        if _is_start_date_param(name):
            params[name] = start_date
        elif _is_end_date_param(name):
            params[name] = end_date
    return params


def validate_blueprint_sql(sql: str) -> str | None:
    """校验蓝图执行 SQL，只允许只读查询。"""
    guard_result = guard_readonly_sql(sql, query_constraints={"enabled": False})
    if guard_result.ok:
        return None
    if guard_result.code == "EMPTY_SQL":
        return "分析蓝图未配置可执行 SQL"
    return guard_result.error


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
        diagnosis = _build_diagnosis("NOT_ACTIVE", "分析蓝图尚未发布，不能执行")
        _write_blueprint_usage_log(
            db,
            bp,
            question,
            {},
            success=False,
            elapsed_ms=0,
            row_count=0,
            diagnosis=diagnosis,
            error_message=diagnosis["detail"],
        )
        return {
            "ok": False,
            "error": diagnosis["detail"],
            "params": {},
            "row_count": 0,
            "diagnosis": diagnosis,
        }

    dataset = db.get(SemanticDataset, bp.dataset_id)
    datasource = db.get(Datasource, dataset.datasource_id) if dataset else None
    if not datasource:
        diagnosis = _build_diagnosis("DATASOURCE_MISSING", "分析蓝图所属数据集没有可用数据源")
        _write_blueprint_usage_log(
            db,
            bp,
            question,
            {},
            success=False,
            elapsed_ms=0,
            row_count=0,
            diagnosis=diagnosis,
            error_message=diagnosis["detail"],
        )
        return {
            "ok": False,
            "error": diagnosis["detail"],
            "params": {},
            "row_count": 0,
            "diagnosis": diagnosis,
        }

    sql = (bp.call_template or bp.raw_sql or "").strip()
    params, missing = extract_blueprint_params(bp, question, input_params)
    sql_preview = render_blueprint_sql_preview(sql, params)
    if missing:
        detail = "运行分析蓝图前还需要补充参数：" + "、".join(missing)
        diagnosis = _build_diagnosis("MISSING_PARAMS", detail)
        _write_blueprint_usage_log(
            db,
            bp,
            question,
            params,
            success=False,
            elapsed_ms=0,
            row_count=0,
            diagnosis=diagnosis,
            error_message=detail,
        )
        return {
            "ok": False,
            "error": detail,
            "params": params,
            "missing": missing,
            "sql": sql,
            "sql_preview": sql_preview,
            "row_count": 0,
            "diagnosis": diagnosis,
        }

    guard_result = guard_readonly_sql(
        sql,
        dialect=_datasource_dialect(datasource),
        query_constraints=getattr(dataset, "query_constraints", None),
        allowed_tables=[
            link.source_table.table_name
            for link in (getattr(dataset, "selected_tables", None) or [])
            if link.source_table and link.source_table.table_name
        ],
    )
    if not guard_result.ok:
        validation_error = guard_result.error or "SQL 安全校验未通过"
        diagnosis = _build_diagnosis("UNSAFE_SQL", validation_error)
        _write_blueprint_usage_log(
            db,
            bp,
            question,
            params,
            success=False,
            elapsed_ms=0,
            row_count=0,
            diagnosis=diagnosis,
            error_message=validation_error,
        )
        return {
            "ok": False,
            "error": validation_error,
            "params": params,
            "sql": sql,
            "sql_preview": sql_preview,
            "row_count": 0,
            "diagnosis": diagnosis,
        }
    sql = guard_result.normalized_sql or sql
    sql_preview = render_blueprint_sql_preview(sql, params)

    engine = create_engine_for_datasource(datasource)
    started_at = time.monotonic()
    timeout_seconds = max(1, int(bp.timeout_seconds or 30))
    try:
        with engine.connect() as conn:
            cleanup_timeout = _apply_database_timeout(conn, datasource, timeout_seconds)
            try:
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
            finally:
                if cleanup_timeout:
                    cleanup_timeout()

        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        masked_rows, masking_summary = _mask_blueprint_rows(rows)
        column_labels = {
            c.get("column"): c.get("semantic")
            for c in (bp.output_schema or [])
            if c.get("column") and c.get("semantic")
        }
        sql_result = {
            "columns": columns,
            "rows": masked_rows,
            "row_count": len(masked_rows),
            "column_labels": column_labels,
            "blueprint_id": bp.id,
            "blueprint_name": bp.name,
            "execution_time_ms": elapsed_ms,
            "params": params,
            "sql_template": sql,
            "sql_preview": sql_preview,
            "masking_summary": masking_summary,
        }
        if count_usage:
            bp.usage_count = (bp.usage_count or 0) + 1
        _write_blueprint_usage_log(
            db,
            bp,
            question,
            params,
            success=True,
            elapsed_ms=elapsed_ms,
            row_count=len(masked_rows),
        )
        logger.info(
            "分析蓝图执行成功: blueprint_id=%s row_count=%s elapsed_ms=%s params=%s",
            bp.id,
            len(masked_rows),
            elapsed_ms,
            params,
        )
        return {
            "ok": True,
            "sql": sql,
            "sql_preview": sql_preview,
            "sql_result": sql_result,
            "params": params,
            "execution_time_ms": elapsed_ms,
            "row_count": len(masked_rows),
            "masking_summary": masking_summary,
            "diagnosis": None,
        }
    except Exception as e:
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        code = "TIMEOUT" if _is_timeout_exception(e) else "EXECUTION_ERROR"
        diagnosis = _build_diagnosis(code, str(e))
        logger.exception(
            "分析蓝图执行失败: blueprint_id=%s code=%s elapsed_ms=%s params=%s error=%s",
            bp.id,
            code,
            elapsed_ms,
            params,
            e,
        )
        _write_blueprint_usage_log(
            db,
            bp,
            question,
            params,
            success=False,
            elapsed_ms=elapsed_ms,
            row_count=0,
            diagnosis=diagnosis,
            error_message=str(e),
        )
        return {
            "ok": False,
            "error": f"分析蓝图执行失败: {e}",
            "sql": sql,
            "sql_preview": sql_preview,
            "params": params,
            "execution_time_ms": elapsed_ms,
            "row_count": 0,
            "diagnosis": diagnosis,
            "masking_summary": {"masked_cells": 0, "masked_columns": []},
        }
    finally:
        engine.dispose()
