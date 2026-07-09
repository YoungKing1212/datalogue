# ============================================================
# File Name   : runtime_context.py
# Description:
#   BI Agent 直连 Dataset 工具链的运行时上下文组装。
#
# Responsibilities:
#   - 从数据集选表生成工具编译器允许读取的表字段上下文。
#   - 绑定 execute_compiled_query 唯一可用的受控 SQL 执行器。
#   - 复用同一套上下文给 native handoff 与直连问数入口。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domains.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge
from app.core.models.dataset import SemanticDataset
from app.core.models.datasource import Datasource
from app.domains.query_execution.preview import preview_dataset_sql
from app.domains.query_execution.compiler_context import build_query_plan_compiler_context


def build_bi_runtime_context(
    db: Session,
    *,
    dataset_id: int,
    question: str,
    bridge: AgentScopeDatasetRuntimeBridge,
) -> dict[str, Any]:
    """构造 BI Agent 执行 Dataset 工具链必须具备的运行时上下文。"""

    dataset = db.get(SemanticDataset, dataset_id)
    if dataset is None:
        return {"dataset": None, "session_kwargs": {}}

    _bind_query_executor(db=db, bridge=bridge, dataset=dataset, question=question)
    allowed_tables, sql_generation_context = allowed_tables_and_sql_context(dataset)
    datasource = db.get(Datasource, dataset.datasource_id)
    datasource_dialect = (
        getattr(datasource, "dialect", None)
        or getattr(datasource, "db_type", None)
        or "sqlite"
    )
    return {
        "dataset": dataset,
        "session_kwargs": {
            "sql_generation_context": sql_generation_context,
            "dialect": datasource_dialect,
            "current_datasource_dialect": datasource_dialect,
            "query_constraints": getattr(dataset, "query_constraints", None) or {},
            "allowed_tables": allowed_tables,
        },
    }


def allowed_tables_and_sql_context(dataset: SemanticDataset) -> tuple[list[str], dict[str, Any]]:
    """把数据集选表投影成 SQL 编译器可读的安全 schema 摘要。"""

    allowed_tables: list[str] = []
    table_schemas: list[dict[str, Any]] = []
    for link in dataset.selected_tables or []:
        source_table = getattr(link, "source_table", None)
        if source_table is None:
            continue
        schema_name = str(getattr(source_table, "schema_name", "") or "").strip()
        table_name = str(getattr(source_table, "table_name", "") or "").strip()
        if not table_name:
            continue
        allowed_tables.append(table_name)
        if schema_name:
            allowed_tables.append(f"{schema_name}.{table_name}")
        fields = []
        for column in source_table.columns or []:
            column_name = str(getattr(column, "column_name", "") or "").strip()
            if not column_name:
                continue
            fields.append(
                {
                    "name": column_name,
                    "column_name": column_name,
                    "display_name": getattr(column, "effective_desc", None)
                    or getattr(column, "user_description", None)
                    or getattr(column, "ai_description", None)
                    or getattr(column, "column_comment", None)
                    or column_name,
                }
            )
        table_schemas.append({"name": table_name, "table_name": table_name, "fields": fields})
    return sorted(set(allowed_tables)), build_query_plan_compiler_context({"table_schemas": table_schemas})


def _bind_query_executor(
    *,
    db: Session,
    bridge: AgentScopeDatasetRuntimeBridge,
    dataset: SemanticDataset,
    question: str,
) -> None:
    toolkit = getattr(bridge, "toolkit", None)
    context = getattr(toolkit, "context", None)
    if context is None:
        return

    def _execute(sql: str) -> dict[str, Any]:
        # execute_compiled_query 是唯一能读取私有 SQL 的位置；上层 Agent 只拿 artifact 引用。
        result = preview_dataset_sql(db, dataset=dataset, sql=sql, question=question)
        return result if isinstance(result, dict) else {"rows": []}

    context.query_executor = _execute
