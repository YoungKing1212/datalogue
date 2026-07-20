# ============================================================
# File Name   : sample_data.py
# Description:
#   样例数据格式化工具。
#
# Responsibilities:
#   - 为提示词和审核上下文格式化表样例数据。
#   - 规范化样例行以便安全展示。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# 样例数据查询工具 — 给 SQL 审计 Agent 提供 1-2 行真实表数据作为 LLM 上下文
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import models


def fetch_sample_rows(
    db: Session,
    table_names: Iterable[str],
    per_table: int = 2,
    datasource=None,
) -> str:
    """为每个相关表取 `per_table` 行真实样例，拼成 prompt 片段。

    优先从传入的 `datasource` 取样例；没有 datasource 时回退到 `dataset_id` 解析。
    直接用 SQLAlchemy `text()` 执行 `SELECT * FROM "table" LIMIT N`。

    Args:
        db: SQLAlchemy Session（用于解析 dataset 关联的 datasource）
        table_names: 需要取样例的表名列表（来自 DSL metrics 引用的 table_name）
        per_table: 每个表取几行，默认 2
        datasource: 可选，已知 Datasource 时直接传入避免再次查 db

    Returns:
        多行字符串，例：
        ```
        【样例数据】
        表 t_order:
          - id=1, order_no='SO20250101001', order_amt=299.00, status=1
          - id=2, order_no='SO20250101002', order_amt=1599.00, status=4
        ```
        表名取不到样例时只输出表名占位，便于 LLM 知道该表存在但样本缺失。
    """
    lines = ["【样例数据】"]
    if not table_names:
        lines.append("（无关联表，无需样例）")
        return "\n".join(lines)

    if datasource is None:
        lines.append("（未绑定数据源，跳过样例查询）")
        return "\n".join(lines)

    from app.domains.data_source.service import create_engine_for_datasource, normalize_db_type
    from app.domains.data_source.helpers import _table_ref

    engine = create_engine_for_datasource(datasource)
    db_type = normalize_db_type(getattr(datasource, "db_type", None))
    try:
        with engine.connect() as conn:
            safe_per_table = max(1, min(int(per_table or 2), 10))
            for requested_name in table_names:
                if not requested_name:
                    continue
                try:
                    raw_name = str(requested_name).strip()
                    schema_name, _, table_name = raw_name.rpartition(".")
                    if not table_name:
                        table_name, schema_name = schema_name, ""
                    source_query = db.query(models.SourceTable).filter(
                        models.SourceTable.datasource_id == datasource.id,
                        models.SourceTable.table_name == table_name,
                    )
                    if schema_name:
                        source_query = source_query.filter(
                            models.SourceTable.schema_name == schema_name
                        )
                    matches = source_query.limit(2).all()
                    if len(matches) != 1:
                        # 样例表引用来自模型/DSL，必须回到已同步元数据解析，不能信任调用方口头承诺。
                        lines.append(f"表 {raw_name}:（未同步或 schema 不明确，跳过样例）")
                        continue
                    source_table = matches[0]
                    table_ref = _table_ref(
                        source_table.schema_name, source_table.table_name, db_type
                    )
                    limit_clause = (
                        "FETCH FIRST :limit ROWS ONLY" if db_type == "oracle" else "LIMIT :limit"
                    )
                    rows = conn.execute(
                        text(f"SELECT * FROM {table_ref} {limit_clause}"),
                        {"limit": safe_per_table},
                    )
                    columns = list(rows.keys())
                    fetched: list[dict] = []
                    for r in rows:
                        row_dict = {}
                        for col in columns:
                            val = r[col]
                            if hasattr(val, "isoformat"):
                                val = val.isoformat()
                            row_dict[col] = val
                        fetched.append(row_dict)
                    lines.append(f"表 {source_table.table_name}:")
                    if not fetched:
                        lines.append("  （表存在但无数据）")
                    for row in fetched:
                        parts = [f"{k}={v!r}" for k, v in row.items()]
                        lines.append("  - " + ", ".join(parts))
                except Exception as e:
                    # 单表查询失败不影响整体：打 WARN 让日志可观测
                    import logging

                    logging.getLogger(__name__).warning(f"样例查询失败 table={table_name}: {e}")
                    # Prompt 只能知道样例不可用，驱动异常、内网地址和连接信息仅保留在服务日志。
                    lines.append(f"表 {table_name}:（样例查询失败，已跳过）")
    finally:
        engine.dispose()

    if len(lines) == 1:
        lines.append("（无可用表）")
    return "\n".join(lines)


__all__ = ["fetch_sample_rows"]
