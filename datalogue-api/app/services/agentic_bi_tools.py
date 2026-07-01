# ============================================================
# File Name   : agentic_bi_tools.py
# Description:
#   Agentic Shell-first AS-R0 的 BI 原子工具提供器。
#
# Responsibilities:
#   - 提供 Agentic Shell 可白名单化的最小 BI 原子工具骨架。
#   - 暴露数据集状态、候选资产目录和 artifact 摘要等安全结构。
#   - 保证 SQL、schema 全量、物理字段明细和 raw rows 不进入 Agent 上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.dataset import AnalysisBlueprint, SemanticDataset
from app.services.agentic_shell import DatalogueAgenticShell
from app.services.artifact_store import ArtifactStore
from app.services.query_plan_compiler import compile_query_plan_to_sql
from app.services.subagent_planning.contracts import QueryPlan, QueryPlanValidationError, normalize_query_plan


class BIAtomicToolProvider:
    """BI 主链原子工具集合；AS-R0 先提供安全契约和只读目录摘要。"""

    def __init__(
        self,
        db: Session,
        *,
        query_executor: Callable[[str], Any] | None = None,
    ) -> None:
        self.db = db
        self._sanitizer = DatalogueAgenticShell()
        self._query_executor = query_executor
        self._compiled_queries: dict[str, dict[str, Any]] = {}

    def get_dataset_status(self, dataset_id: int) -> dict[str, Any]:
        dataset = self._get_dataset(dataset_id)
        if dataset is None:
            return {
                "dataset_id": dataset_id,
                "status": "not_found",
                "metadata_schema_summary": {"selected_table_count": 0},
            }
        return {
            "dataset_id": dataset.id,
            "name": dataset.name,
            "status": dataset.status,
            "metric_count": len(dataset.metrics or []),
            "dimension_count": len(dataset.dimensions or []),
            "blueprint_count": len(dataset.blueprints or []),
            "metadata_schema_summary": self._metadata_schema_summary(dataset),
        }

    def list_candidate_assets(
        self,
        dataset_id: int,
        *,
        question: str | None = None,
    ) -> dict[str, Any]:
        dataset = self._get_dataset(dataset_id)
        if dataset is None:
            return {
                "dataset_id": dataset_id,
                "question_used": False,
                "status": "not_found",
                "blueprint": [],
                "metric": [],
                "dimension": [],
                "metadata_schema_summary": {"selected_table_count": 0},
            }
        # AS-R0 第一阶段没有向量库；question 参数只保留接口兼容，不参与召回或排序。
        catalog = {
            "dataset_id": dataset.id,
            "question_used": False,
            "blueprint": [self._blueprint_summary(item) for item in self._sorted_blueprints(dataset)],
            "metric": [
                {
                    "id": metric.id,
                    "name": metric.display_name or metric.name,
                    "description": metric.description,
                    "synonyms": metric.synonyms or [],
                }
                for metric in sorted(dataset.metrics or [], key=lambda item: item.id or 0)
            ],
            "dimension": [
                {
                    "id": dimension.id,
                    "name": dimension.display_name or dimension.name,
                    "synonyms": dimension.synonyms or [],
                    "enum_values": dimension.enum_values or [],
                }
                for dimension in sorted(dataset.dimensions or [], key=lambda item: item.id or 0)
            ],
            "metadata_schema_summary": self._metadata_schema_summary(dataset),
        }
        return self._sanitizer.sanitize_output(catalog)

    def compile_dsl_to_sql(
        self,
        *,
        dataset_id: int,
        dsl: QueryPlan | dict[str, Any],
        sql_generation_context: dict[str, Any] | None = None,
        dialect: str | None = "sqlite",
        current_datasource_dialect: str | None = None,
        query_constraints: dict[str, Any] | None = None,
        allowed_tables: list[str] | None = None,
    ) -> dict[str, Any]:
        """把 DatasetAgent DSL 编译为私有执行句柄；SQL 不进入返回值或 Agent 上下文。"""

        try:
            query_plan = self._coerce_query_plan(dsl)
        except QueryPlanValidationError as exc:
            return {
                "status": "blocked",
                "code": "DSL_INVALID",
                "error_summary": str(exc),
                "compiled_query_ref": None,
            }

        compiled = compile_query_plan_to_sql(
            query_plan=query_plan,
            sql_generation_context=sql_generation_context or {},
            dialect=dialect,
            current_datasource_dialect=current_datasource_dialect,
            query_constraints=query_constraints,
            allowed_tables=allowed_tables,
        )
        if not compiled.get("ok"):
            return self._safe_compile_failure(compiled)

        compiled_query_ref = f"compiled_query:{uuid4().hex}"
        # SQL 只保存在 provider 私有内存句柄中，供 execute_compiled_query 取用；不能返回给 Agent。
        self._compiled_queries[compiled_query_ref] = {
            "dataset_id": dataset_id,
            "dialect": compiled.get("dialect"),
            "execution_source": compiled.get("execution_source"),
            "sql": compiled.get("sql"),
            "sql_list": compiled.get("sql_list") or [],
        }
        return {
            "status": "compiled",
            "compiled_query_ref": compiled_query_ref,
            "dataset_id": dataset_id,
            "dialect": compiled.get("dialect"),
            "execution_source": compiled.get("execution_source"),
            "execution_guard": self._safe_execution_guard(compiled),
            "warning_count": len(compiled.get("warnings") or []),
        }

    def execute_compiled_query(
        self,
        *,
        compiled_query_ref: str,
        dataset_id: int | None = None,
        conversation_id: int | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """执行私有编译句柄并写入 artifact；返回值只暴露安全摘要和 artifact_ref。"""

        compiled = self._compiled_queries.get(compiled_query_ref)
        if compiled is None:
            return {
                "status": "not_found",
                "compiled_query_ref": compiled_query_ref,
                "artifact_ref": None,
            }
        if dataset_id is not None and dataset_id != compiled.get("dataset_id"):
            return {
                "status": "blocked",
                "code": "DATASET_MISMATCH",
                "compiled_query_ref": compiled_query_ref,
                "artifact_ref": None,
            }
        if self._query_executor is None:
            return {
                "status": "blocked",
                "code": "EXECUTOR_NOT_CONFIGURED",
                "compiled_query_ref": compiled_query_ref,
                "artifact_ref": None,
            }

        # 只有 execute 工具内部能读取 SQL；之后立即转成 artifact，不把 SQL 拼进任何可见响应。
        execution_result = self._normalize_execution_result(self._query_executor(str(compiled["sql"])))
        artifact_ref = ArtifactStore(self.db).put_json(
            kind="sql_result",
            payload=execution_result,
            dataset_id=dataset_id if dataset_id is not None else compiled.get("dataset_id"),
            conversation_id=conversation_id,
            trace_id=trace_id,
        )
        return {
            "status": "completed",
            "artifact_ref": artifact_ref,
            "row_count": execution_result["row_count"],
            "column_count": len(execution_result["columns"]),
        }

    def create_query_artifact(
        self,
        *,
        payload: Any,
        dataset_id: int | None = None,
        conversation_id: int | None = None,
        trace_id: str | None = None,
    ) -> dict[str, str]:
        # 写入前复用 Shell 输出清洗，确保 artifact 入口不会被 Agent 旁路塞入内部执行载荷。
        sanitized_payload = self._sanitizer.sanitize_output(payload)
        artifact_ref = ArtifactStore(self.db).put_json(
            kind="sql_result",
            payload=sanitized_payload,
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )
        return {"artifact_ref": artifact_ref}

    def get_artifact_summary(self, artifact_ref: str) -> dict[str, Any]:
        artifact = ArtifactStore(self.db).get(artifact_ref)
        if artifact is None:
            return {"artifact_ref": artifact_ref, "status": "not_found"}
        summary = {
            "artifact_ref": artifact.artifact_id,
            "kind": artifact.kind,
            "content_mime": artifact.content_mime,
            "size_bytes": artifact.size_bytes,
            "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        }
        return self._sanitizer.sanitize_output(summary)

    def _get_dataset(self, dataset_id: int) -> SemanticDataset | None:
        return (
            self.db.query(SemanticDataset)
            .filter(SemanticDataset.id == dataset_id)
            .one_or_none()
        )

    @staticmethod
    def _metadata_schema_summary(dataset: SemanticDataset) -> dict[str, int]:
        # 只返回计数级 metadata summary，不返回表名、字段名、DDL 或 schema 主体。
        return {"selected_table_count": len(dataset.selected_tables or [])}

    @staticmethod
    def _sorted_blueprints(dataset: SemanticDataset) -> list[AnalysisBlueprint]:
        return sorted(dataset.blueprints or [], key=lambda item: item.id or 0)

    @staticmethod
    def _blueprint_summary(blueprint: AnalysisBlueprint) -> dict[str, Any]:
        return {
            "id": blueprint.id,
            "name": blueprint.name,
            "description": blueprint.description,
            "trigger_keywords": blueprint.trigger_keywords or [],
            "when_to_use": blueprint.when_to_use,
        }

    @staticmethod
    def _coerce_query_plan(dsl: QueryPlan | dict[str, Any]) -> QueryPlan:
        if isinstance(dsl, QueryPlan):
            return dsl
        if isinstance(dsl, dict):
            # DatasetAgent 只提交结构化 DSL；任何不合法枚举/资产形状必须 fail closed。
            return normalize_query_plan(dsl)
        raise QueryPlanValidationError("dsl must be QueryPlan or object")

    @staticmethod
    def _safe_execution_guard(compiled: dict[str, Any]) -> dict[str, Any]:
        guard = compiled.get("sql_guard") if isinstance(compiled.get("sql_guard"), dict) else {}
        return {
            "ok": bool(guard.get("ok")),
            "warning_count": len(compiled.get("warnings") or []),
        }

    @staticmethod
    def _safe_compile_failure(compiled: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "blocked",
            "code": compiled.get("code") or "COMPILE_BLOCKED",
            "error_summary": compiled.get("error") or "DSL 无法编译为受控查询",
            "compiled_query_ref": None,
            "execution_source": compiled.get("execution_source"),
            "execution_guard": BIAtomicToolProvider._safe_execution_guard(compiled),
        }

    @staticmethod
    def _normalize_execution_result(result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            rows = result.get("rows")
            normalized_rows = list(rows) if isinstance(rows, list) else []
            columns = result.get("columns")
            normalized_columns = list(columns) if isinstance(columns, list) else []
            if not normalized_columns and normalized_rows and isinstance(normalized_rows[0], dict):
                normalized_columns = list(normalized_rows[0].keys())
            raw_count = result.get("row_count")
            row_count = raw_count if isinstance(raw_count, int) else len(normalized_rows)
            return {
                "columns": normalized_columns,
                "rows": normalized_rows,
                "row_count": row_count,
            }
        if isinstance(result, list):
            columns = list(result[0].keys()) if result and isinstance(result[0], dict) else []
            return {
                "columns": columns,
                "rows": result,
                "row_count": len(result),
            }
        return {"columns": [], "rows": [], "row_count": 0}
