# ============================================================
# File Name   : column_labels.py
# Description:
#   结果列展示名映射工具。
#
# Responsibilities:
#   - 根据语义元数据构建可读列名。
#   - 将 SQL 结果列映射为前端展示名称。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# SQL 结果列名 → 中文展示名映射工具

from typing import Dict

from sqlalchemy.orm import Session

from app.core.models import SemanticDataset, DatasetSourceTable


def build_column_labels(db: Session, dataset_id: int | None) -> Dict[str, str]:
    """根据数据集语义层 + 字段标注构建 {列名 → 中文展示名} 映射。

    优先级（后者覆盖前者）：
    1. SourceColumn `column_name` → `effective_desc`（AI / 用户标注的字段中文）
    2. 维度 `column_name` → `display_name`（如 person_name → 姓名）
    3. 指标 `name` → `display_name`（如 refund_amt → 退款金额）
       （指标的 name 是语义层别名，LLM 在 SELECT 中作为 AS 别名使用）

    推断路径下 LLM 直接选 DDL 列，所以必须把 source_column 标注也算进来，
    否则 `SELECT person_name FROM ...` 这类直查永远显示英文。
    """
    labels: Dict[str, str] = {}
    if not dataset_id:
        return labels
    dataset = db.get(SemanticDataset, dataset_id)
    if not dataset:
        return labels

    # 1) 字段标注（兜底最广，覆盖所有 DDL 列）
    source_table_ids = [
        link.source_table_id
        for link in db.query(DatasetSourceTable).filter_by(dataset_id=dataset_id).all()
    ]
    if source_table_ids:
        from app.core.models import SourceColumn
        cols = (
            db.query(SourceColumn)
            .filter(SourceColumn.table_id.in_(source_table_ids))
            .all()
        )
        for col in cols:
            if col.column_name and col.effective_desc and col.desc_source not in (
                "unknown",
                "stale",
                "fallback",
            ):
                # 已确认有意义的标注（用户、AI、DB 注释），才用作展示名
                labels[col.column_name] = col.effective_desc

    # 2) 维度 column_name → display_name
    for dim in dataset.dimensions or []:
        if dim.column_name and dim.display_name:
            labels[dim.column_name] = dim.display_name

    # 3) 指标 name → display_name（最高优先，LLM 生成的 AS 别名要走这个）
    for metric in dataset.metrics or []:
        if metric.name and metric.display_name:
            labels[metric.name] = metric.display_name

    return labels
