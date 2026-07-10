# ============================================================
# File Name   : annotation.py
# Description:
#   AI 辅助元数据标注服务。
#
# Responsibilities:
#   - 根据 Schema 上下文生成表和字段描述。
#   - 识别字段语义角色并生成审核建议。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""AI 字段标注服务 — 按需为 source_column 生成业务语义描述。

核心原则：
- 只在用户勾选表加入数据集时触发标注
- 数据库已有注释作为 AI 输入，AI 不覆盖、只增强
- 分层存储：db_comment / ai_description / user_description / effective_desc
- 标注缓存：同一张表被加入多个数据集时，跳过已标注字段
"""

import json
import re
import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple

from sqlalchemy.orm import Session

from app.core.models.dataset import SourceTable, SourceColumn
from app.core.llm import get_llm
from app.prompts import ANNOTATION_SYSTEM_PROMPT, TABLE_ANNOTATION_PROMPT
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


# ── 生效值解析 ──────────────────────────────────────

JUNK_COMMENTS = {"", "无", "字段", "列", "名称", "编号", "id", "date", "time", "name"}


def is_meaningful_comment(comment: str) -> bool:
    """判断数据库注释是否有实际业务含义（而非字段名重复或垃圾注释）。"""
    if not comment or len(comment.strip()) < 2:
        return False
    lowered = comment.strip().lower()
    if lowered in JUNK_COMMENTS:
        return False
    # 纯字段名重复（如 comment == "order_amount"）
    if re.match(r"^[a-z_][a-z0-9_]*$", lowered):
        return False
    # 形如 "字段1", "col_123", "field_xxx"
    if re.match(r"^(字段|列|col|field)[_\-\d]*$", comment.strip(), re.I):
        return False
    return True


def resolve_description(col: SourceColumn) -> Tuple[str, str]:
    """返回 (effective_desc, desc_source)。优先级从高到低：用户 > DB注释 > AI > 回退。"""
    # 1. 用户手动修改 → 永远用用户的
    if col.user_description and len(col.user_description.strip()) >= 2:
        return col.user_description.strip(), "user"

    # 2. 数据库注释有意义 → 用注释
    if col.column_comment and is_meaningful_comment(col.column_comment):
        return col.column_comment.strip(), "db_comment"

    # 3. AI 标注过 → 用 AI 的
    if col.ai_description and len(col.ai_description.strip()) >= 2:
        return col.ai_description.strip(), "ai"

    # 4. 什么都没有 → 退回字段名
    return col.column_name, "fallback"


def resolve_table_description(table: SourceTable) -> Tuple[str, str]:
    """返回 (effective_desc, desc_source)。优先级：用户 > DB注释 > AI > 回退。"""
    if table.user_description and len(table.user_description.strip()) >= 2:
        return table.user_description.strip(), "user"
    if table.table_comment and is_meaningful_comment(table.table_comment):
        return table.table_comment.strip(), "db_comment"
    if table.ai_description and len(table.ai_description.strip()) >= 2:
        return table.ai_description.strip(), "ai"
    return table.table_name, "fallback"


def refresh_effective_desc(col: SourceColumn) -> None:
    """重新计算并回写 effective_desc 和 desc_source。"""
    col.effective_desc, col.desc_source = resolve_description(col)


def refresh_table_effective_desc(table: SourceTable) -> None:
    """重新计算并回写表级 effective_desc 和 desc_source。"""
    table.effective_desc, table.desc_source = resolve_table_description(table)


# ── 批量标注一张表 ──────────────────────────────────


def _safe_json_parse(content: str) -> List[Dict[str, Any]]:
    """安全解析 LLM 返回的 JSON，支持 markdown code block 包裹。解析失败返回空列表。"""
    if not content or not content.strip():
        logger.warning("LLM 返回空内容")
        return []

    text = content.strip()

    # 去掉 <think> 标签
    if "<think>" in text:
        if "</think>" in text:
            text = text.split("</think>")[-1].strip()
        else:
            text = text.split("<think>")[0].strip()

    # 去掉可能的 markdown code block
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 尝试直接解析
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        return []
    except json.JSONDecodeError:
        pass

    # 尝试找第一个 [ 和最后一个 ]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            pass

    # 尝试找第一个 { 和最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return [parsed] if isinstance(parsed, dict) else []
        except json.JSONDecodeError:
            pass

    logger.warning(f"无法解析 LLM 返回为 JSON: {text[:200]}")
    return []


def _annotate_table_description(
    db: Session, table: SourceTable, columns: List[SourceColumn], force: bool = False
) -> bool:
    """为 SourceTable 生成 AI 业务描述。返回是否成功标注。"""
    # 判断是否需要标注
    needs_annotation = force or table.desc_source in ("unknown", "stale", "fallback")
    if not needs_annotation:
        return False

    lines = [f"表名: {table.table_name}", f"已有注释: {table.table_comment or '无'}"]
    # 取前 10 个字段作为上下文
    for c in columns[:10]:
        comment = c.column_comment or ""
        lines.append(f"字段: {c.column_name} | 类型: {c.data_type} | 注释: {comment}")

    try:
        llm = get_llm(temperature=0.2, role="annotation", db=db)
        response = llm.invoke(
            [
                SystemMessage(content=TABLE_ANNOTATION_PROMPT),
                HumanMessage(content="\n".join(lines)),
            ]
        )
        raw = str(response.content).strip()
        logger.info(f"[AI表级标注] table={table.table_name} raw_response={raw[:500]!r}")
        # 过滤 <think> 标签（支持未闭合的情况）
        if "<think>" in raw:
            if "</think>" in raw:
                raw = raw.split("</think>")[-1].strip()
            else:
                raw = raw.split("<think>")[0].strip()
        desc = raw.strip('"').strip("'")
        if desc and len(desc) >= 3 and desc != table.table_name:
            table.ai_description = desc
            table.annotated_at = datetime.utcnow()
            refresh_table_effective_desc(table)
            return True
    except Exception as e:
        logger.warning(f"表级标注失败 {table.table_name}: {e}")
    return False


def annotate_table_columns(
    db: Session, source_table_id: int, force: bool = False
) -> Dict[str, Any]:
    """为单张 source_table 生成表级描述 + 所有字段批量生成 AI 标注。

    Args:
        db: SQLAlchemy session
        source_table_id: SourceTable.id
        force: 是否强制重新标注（覆盖已有 AI 标注）

    Returns:
        {"annotated": int, "skipped": int, "table_annotated": bool, "failed": bool, "error": str|None}
    """
    table = db.get(SourceTable, source_table_id)
    if not table:
        return {
            "annotated": 0,
            "skipped": 0,
            "table_annotated": False,
            "failed": True,
            "error": "表不存在",
        }

    columns = db.query(SourceColumn).filter_by(table_id=source_table_id).all()
    if not columns:
        return {
            "annotated": 0,
            "skipped": 0,
            "table_annotated": False,
            "failed": False,
            "error": None,
        }

    # ── 表级标注 ──
    table_annotated = False
    if force or table.desc_source in ("unknown", "stale", "fallback"):
        table_annotated = _annotate_table_description(db, table, columns, force=force)
        if table_annotated:
            logger.info(f"表级标注完成: {table.table_name} -> {table.effective_desc}")

    # ── 字段级标注 ──
    if force:
        columns_to_annotate = columns
    else:
        columns_to_annotate = [
            c for c in columns if c.desc_source in ("unknown", "stale", "fallback")
        ]

    skipped = len(columns) - len(columns_to_annotate)

    if not columns_to_annotate:
        db.commit()
        logger.info(f"标注跳过: table={table.table_name}, 所有字段已标注")
        return {
            "annotated": 0,
            "skipped": skipped,
            "table_annotated": table_annotated,
            "failed": False,
            "error": None,
        }

    logger.info(
        f"开始字段标注: table={table.table_name}, fields={len(columns_to_annotate)}, skipped={skipped}"
    )

    # 构建 prompt
    lines = [
        f"表名: {table.table_name}",
        f"表描述: {table.effective_desc or table.table_comment or ''}",
        "",
    ]
    for c in columns_to_annotate:
        desc_hint = c.column_comment or ""
        sample = ", ".join(str(v) for v in (c.sample_values or [])[:3]) if c.sample_values else ""
        lines.append(
            f"字段: {c.column_name} | 类型: {c.data_type} | 注释: {desc_hint} | 样例值: {sample}"
        )

    try:
        llm = get_llm(temperature=0.2, role="annotation", db=db)
        response = llm.invoke(
            [
                SystemMessage(content=ANNOTATION_SYSTEM_PROMPT),
                HumanMessage(content="\n".join(lines)),
            ]
        )
        raw_content = str(response.content)
        logger.info(f"[AI字段标注] table={table.table_name} raw_response={raw_content[:2000]!r}")
        results = _safe_json_parse(raw_content)
    except Exception as e:
        logger.error(f"标注表 {table.table_name} LLM 调用失败: {e}")
        return {
            "annotated": 0,
            "skipped": skipped,
            "table_annotated": table_annotated,
            "failed": True,
            "error": str(e),
        }

    # 回写结果
    col_map = {c.column_name: c for c in columns_to_annotate}
    annotated_count = 0

    for r in results:
        col_name = r.get("column_name")
        col = col_map.get(col_name)
        if not col:
            continue

        desc = r.get("business_desc")
        if desc and len(desc.strip()) >= 2:
            col.ai_description = desc.strip()
        col.ai_semantic_role = r.get("semantic_role")
        col.ai_suggested_agg = r.get("default_agg")
        try:
            col.ai_confidence = (
                float(r.get("confidence")) if r.get("confidence") is not None else None
            )
        except (TypeError, ValueError):
            col.ai_confidence = None
        col.ai_reason = r.get("reason")
        synonyms = r.get("synonyms")
        enum_values = r.get("enum_values")
        col.suggested_synonyms = synonyms if isinstance(synonyms, list) else []
        col.suggested_enum_values = enum_values if isinstance(enum_values, list) else []
        col.review_status = "pending_review"
        col.annotated_at = datetime.utcnow()

        # 重新解析生效值
        refresh_effective_desc(col)
        annotated_count += 1

    db.commit()
    logger.info(
        f"标注完成: table={table.table_name}, annotated={annotated_count}, skipped={skipped}, table_annotated={table_annotated}"
    )
    return {
        "annotated": annotated_count,
        "skipped": skipped,
        "table_annotated": table_annotated,
        "failed": False,
        "error": None,
    }


def annotate_all_tables_for_datasource(db: Session, datasource_id: int) -> Dict[str, Any]:
    """管理员功能：为数据源下所有表批量标注（保留旧 API 行为，但使用新服务）。"""
    tables = db.query(SourceTable).filter_by(datasource_id=datasource_id).all()
    total_annotated = 0
    total_skipped = 0
    failed_tables = []

    for table in tables:
        result = annotate_table_columns(db, table.id)
        total_annotated += result["annotated"]
        total_skipped += result["skipped"]
        if result["failed"]:
            failed_tables.append({"table": table.table_name, "error": result.get("error")})

    return {
        "ok": True,
        "tables_processed": len(tables),
        "annotated": total_annotated,
        "skipped": total_skipped,
        "failed_tables": failed_tables,
    }
