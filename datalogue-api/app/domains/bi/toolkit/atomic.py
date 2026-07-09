# ============================================================
# File Name   : atomic.py
# Description:
#   AgentScope 2.0 形态的 BI Toolkit 原子工具实现。
#
# Responsibilities:
#   - 用 ToolBase 子类表达 Datalogue 的最小 BI 原子工具。
#   - 用 Toolkit 作为 Dataset Query Skill 可见的工具容器。
#   - 把 SQL、query_plan 主体、raw rows 和物理字段细节隔离在受控工具上下文内。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import copy
import json
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from agentscope.permission import PermissionBehavior, PermissionContext, PermissionDecision
from agentscope.tool import ToolBase, Toolkit
from sqlalchemy.orm import Session

from app.models.dataset import AnalysisBlueprint, SemanticDataset
from app.safety import DataloguePayloadSanitizer
from app.domains.query_execution.artifact_store import ArtifactStore
from app.domains.query_execution.compiler import compile_query_plan_to_sql


logger = logging.getLogger(__name__)


BI_ATOMIC_TOOL_SEQUENCE = (
    "get_dataset_status",
    "list_candidate_assets",
    "compile_dsl_to_sql",
    "execute_compiled_query",
    "repair_dsl",
    "create_query_artifact",
    "get_artifact_summary",
)

_READ_ONLY_TOOLS = {
    "get_dataset_status",
    "list_candidate_assets",
    "get_artifact_summary",
}


@dataclass
class BIAtomicToolContext:
    """BI 原子工具共享的受控执行上下文；敏感状态只保存在 Datalogue 侧。"""

    db: Session
    query_executor: Callable[[str], Any] | None = None
    sanitizer: DataloguePayloadSanitizer = field(default_factory=DataloguePayloadSanitizer)
    compiled_queries: dict[str, dict[str, Any]] = field(default_factory=dict)
    toolkit: Any | None = None


class DatalogueBIAtomicTool(ToolBase):
    """所有 BI 原子工具的 AgentScope ToolBase 基类。"""

    is_external_tool = True
    is_concurrency_safe = False
    is_mcp = False
    is_read_only = False

    def __init__(
        self,
        *,
        context: BIAtomicToolContext,
        name: str,
        description: str,
        input_schema: dict[str, Any] | None = None,
        is_read_only: bool = False,
    ) -> None:
        super().__init__()
        self.context = context
        self.name = name
        self.description = description
        self.input_schema = input_schema or _tool_input_schema(name)
        self.is_read_only = is_read_only

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        del context
        if self.name not in BI_ATOMIC_TOOL_SEQUENCE:
            return self._deny("TOOL_NOT_WHITELISTED", "工具不在 BI 原子工具白名单中。")
        if self._contains_forbidden_tool_input(tool_input):
            return self._deny("SENSITIVE_TOOL_ARGUMENT", "工具入参包含 SQL/schema/raw rows 等禁区内容。")
        if self.name == "compile_dsl_to_sql" and not isinstance(tool_input.get("dsl"), dict):
            return self._deny("DSL_REQUIRED", "compile_dsl_to_sql 必须接收结构化 DSL。")
        if self.name in {"execute_compiled_query", "repair_dsl"} and not tool_input.get("compiled_query_ref"):
            return self._deny("COMPILED_QUERY_REF_REQUIRED", "工具必须使用 compile/repair 返回的私有句柄。")
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Datalogue BI atomic tool call allowed.",
            decision_reason="ALLOWED",
        )

    def execute_external(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(f"{self.__class__.__name__} must implement execute_external")

    @staticmethod
    def _deny(code: str, message: str) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.DENY,
            message=message,
            decision_reason=code,
        )

    @classmethod
    def _contains_forbidden_tool_input(cls, value: Any) -> bool:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_text = str(key).lower()
                if key_text in {"schema", "schema_context", "raw_rows", "query_plan", "repair_patch", "blueprint_body"}:
                    return True
                if "sql" in key_text and nested not in (None, "", [], {}):
                    return True
                if cls._contains_forbidden_tool_input(nested):
                    return True
        elif isinstance(value, list):
            return any(cls._contains_forbidden_tool_input(item) for item in value)
        elif isinstance(value, str):
            lowered = value.lower()
            return "select " in lowered or " from " in lowered or "drop table" in lowered
        return False


class GetDatasetStatusTool(DatalogueBIAtomicTool):
    def __init__(self, context: BIAtomicToolContext) -> None:
        super().__init__(
            context=context,
            name="get_dataset_status",
            description="读取数据集可用状态和计数级 metadata 摘要。",
            is_read_only=True,
        )

    def execute_external(self, *, dataset_id: int) -> dict[str, Any]:
        dataset = _get_dataset(self.context.db, dataset_id)
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
            "metadata_schema_summary": _metadata_schema_summary(dataset),
        }


class ListCandidateAssetsTool(DatalogueBIAtomicTool):
    def __init__(self, context: BIAtomicToolContext) -> None:
        super().__init__(
            context=context,
            name="list_candidate_assets",
            description="返回 full catalog 级候选资产摘要；AS-R0 不做问题语义召回。",
            is_read_only=True,
        )

    def execute_external(self, *, dataset_id: int, question: str | None = None) -> dict[str, Any]:
        del question  # AS-R0 第一阶段没有向量库；参数保留但不参与召回或排序。
        dataset = _get_dataset(self.context.db, dataset_id)
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
        catalog = {
            "dataset_id": dataset.id,
            "question_used": False,
            "blueprint": [_blueprint_summary(item) for item in _sorted_blueprints(dataset)],
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
            "metadata_schema_summary": _metadata_schema_summary(dataset),
        }
        return _safe_dict(self.context.sanitizer.sanitize_output(catalog))


class CompileDslToSqlTool(DatalogueBIAtomicTool):
    def __init__(self, context: BIAtomicToolContext) -> None:
        super().__init__(
            context=context,
            name="compile_dsl_to_sql",
            description="把 DatasetAgent 结构化 DSL 编译为私有 compiled_query_ref。",
        )

    def execute_external(
        self,
        *,
        dataset_id: int,
        dsl: dict[str, Any],
        question: str | None = None,
        sql_generation_context: dict[str, Any] | None = None,
        dialect: str | None = "sqlite",
        current_datasource_dialect: str | None = None,
        query_constraints: dict[str, Any] | None = None,
        allowed_tables: list[str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(dsl, dict):
            return {
                "status": "blocked",
                "code": "DSL_INVALID",
                "error_summary": "dsl must be a dict",
                "compiled_query_ref": None,
            }

        compiled = compile_query_plan_to_sql(
            query_plan=dsl,
            sql_generation_context=sql_generation_context or {},
            dialect=dialect,
            current_datasource_dialect=current_datasource_dialect,
            query_constraints=query_constraints,
            allowed_tables=allowed_tables,
        )
        if not compiled.get("ok"):
            return _safe_compile_failure(compiled)

        compiled_query_ref = f"compiled_query:{uuid4().hex}"
        # SQL 和 query_plan 主体只进入 Datalogue 私有句柄，永不回填给 Agent/Workbench。
        logger.debug("compile sql: %s", compiled.get("sql"))
        self.context.compiled_queries[compiled_query_ref] = {
            "dataset_id": dataset_id,
            "dialect": compiled.get("dialect"),
            "execution_source": compiled.get("execution_source"),
            "sql": compiled.get("sql"),
            "sql_list": compiled.get("sql_list") or [],
            "query_plan": dsl,
            "sql_generation_context": copy.deepcopy(sql_generation_context or {}),
            "current_datasource_dialect": current_datasource_dialect,
            "query_constraints": copy.deepcopy(query_constraints or {}),
            "allowed_tables": list(allowed_tables or []),
        }
        return {
            "status": "compiled",
            "compiled_query_ref": compiled_query_ref,
            "dataset_id": dataset_id,
            "dialect": compiled.get("dialect"),
            "execution_source": compiled.get("execution_source"),
            "execution_guard": _safe_execution_guard(compiled),
            "warning_count": len(compiled.get("warnings") or []),
        }


class ExecuteCompiledQueryTool(DatalogueBIAtomicTool):
    def __init__(self, context: BIAtomicToolContext) -> None:
        super().__init__(
            context=context,
            name="execute_compiled_query",
            description="执行 compiled_query_ref 指向的私有 SQL，并写入 query artifact。",
        )

    def execute_external(
        self,
        *,
        compiled_query_ref: str,
        dataset_id: int | None = None,
        conversation_id: int | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        compiled = self.context.compiled_queries.get(compiled_query_ref)
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
        if self.context.query_executor is None:
            return {
                "status": "blocked",
                "code": "EXECUTOR_NOT_CONFIGURED",
                "compiled_query_ref": compiled_query_ref,
                "artifact_ref": None,
            }

        try:
            # 只有 execute 工具能读取私有 SQL；执行结果马上落 artifact，Agent 只拿安全摘要。
            raw_execution_result = self.context.query_executor(str(compiled["sql"]))
            if isinstance(raw_execution_result, dict) and raw_execution_result.get("error"):
                # sql_preview 会把数据库异常包装成结构化 error 返回；这里必须把它重新归类为 Runtime 状态。
                failure = _safe_execution_failure_from_text(compiled_query_ref, str(raw_execution_result.get("error") or ""))
                _record_field_not_found_failure(compiled, failure, raw_execution_result.get("error"))
                return failure
            execution_result = _normalize_execution_result(raw_execution_result)
        except Exception as exc:  # noqa: BLE001
            failure = _safe_execution_failure(compiled_query_ref, exc)
            _record_field_not_found_failure(compiled, failure, exc)
            return failure
        artifact_ref = ArtifactStore(self.context.db).put_json(
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


class RepairDslTool(DatalogueBIAtomicTool):
    def __init__(self, context: BIAtomicToolContext) -> None:
        super().__init__(
            context=context,
            name="repair_dsl",
            description="在 FIELD_NOT_FOUND 后修复 DSL 并返回新的 compiled_query_ref。",
        )

    def execute_external(
        self,
        *,
        compiled_query_ref: str,
        dataset_id: int | None = None,
    ) -> dict[str, Any]:
        compiled = self.context.compiled_queries.get(compiled_query_ref)
        if compiled is None:
            return {"status": "blocked", "code": "COMPILED_QUERY_NOT_FOUND", "compiled_query_ref": None}
        if dataset_id is not None and dataset_id != compiled.get("dataset_id"):
            return {"status": "blocked", "code": "DATASET_MISMATCH", "compiled_query_ref": None}
        failure = compiled.get("last_execution_failure") if isinstance(compiled.get("last_execution_failure"), dict) else {}
        if failure.get("code") != "FIELD_NOT_FOUND":
            return {"status": "blocked", "code": "REPAIR_CONTEXT_MISSING", "compiled_query_ref": None}

        patched_dsl = _repair_query_plan_payload(
            query_plan=compiled.get("query_plan"),
            sql_generation_context=compiled.get("sql_generation_context"),
            missing_column_ref=failure.get("missing_column_ref"),
        )
        if patched_dsl is None:
            return {"status": "blocked", "code": "REPAIR_CANDIDATE_NOT_FOUND", "compiled_query_ref": None}

        repaired = self.context.toolkit.execute_tool(
            "compile_dsl_to_sql",
            dataset_id=int(compiled["dataset_id"]),
            dsl=patched_dsl,
            sql_generation_context=compiled.get("sql_generation_context") or {},
            dialect=compiled.get("dialect"),
            current_datasource_dialect=compiled.get("current_datasource_dialect"),
            query_constraints=compiled.get("query_constraints") or {},
            allowed_tables=compiled.get("allowed_tables") or [],
        )
        if repaired.get("status") != "compiled":
            return {
                "status": "blocked",
                "code": str(repaired.get("code") or "REPAIR_COMPILE_BLOCKED"),
                "compiled_query_ref": None,
            }
        return {
            "status": "repaired",
            "compiled_query_ref": repaired["compiled_query_ref"],
            "dataset_id": compiled.get("dataset_id"),
            "repair_count": 1,
        }


class CreateQueryArtifactTool(DatalogueBIAtomicTool):
    def __init__(self, context: BIAtomicToolContext) -> None:
        super().__init__(
            context=context,
            name="create_query_artifact",
            description="写入清洗后的查询 artifact。",
        )

    def execute_external(
        self,
        *,
        payload: Any,
        dataset_id: int | None = None,
        conversation_id: int | None = None,
        trace_id: str | None = None,
    ) -> dict[str, str]:
        # 写入前复用 Shell 输出清洗，避免 Agent 旁路塞入内部执行载荷。
        sanitized_payload = self.context.sanitizer.sanitize_output(payload)
        artifact_ref = ArtifactStore(self.context.db).put_json(
            kind="sql_result",
            payload=sanitized_payload,
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )
        return {"artifact_ref": artifact_ref}


class GetArtifactSummaryTool(DatalogueBIAtomicTool):
    def __init__(self, context: BIAtomicToolContext) -> None:
        super().__init__(
            context=context,
            name="get_artifact_summary",
            description="读取 artifact 的安全摘要，不返回 artifact 主体或 raw rows。",
            is_read_only=True,
        )

    def execute_external(self, *, artifact_ref: str) -> dict[str, Any]:
        artifact = ArtifactStore(self.context.db).get(artifact_ref)
        if artifact is None:
            return {"artifact_ref": artifact_ref, "status": "not_found"}
        summary = {
            "artifact_ref": artifact.artifact_id,
            "kind": artifact.kind,
            "content_mime": artifact.content_mime,
            "size_bytes": artifact.size_bytes,
            "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        }
        return _safe_dict(self.context.sanitizer.sanitize_output(summary))


class DatalogueBIAtomicToolkit:
    """Dataset Query Skill 使用的 BI 工具容器。"""

    def __init__(self, *, context: BIAtomicToolContext, tools: list[DatalogueBIAtomicTool]) -> None:
        self.context = context
        self.tools = tools
        self._tool_by_name = {tool.name: tool for tool in tools}
        self.agentscope_toolkit = Toolkit(tools=tools)
        # repair_dsl 需要复用同一套 compile 工具和私有 compiled handle 状态。
        self.context.toolkit = self

    def get_tool(self, name: str) -> DatalogueBIAtomicTool:
        return self._tool_by_name[name]

    def execute_tool(self, name: str, **kwargs: Any) -> dict[str, Any]:
        tool = self.get_tool(name)
        logger.debug(
            "[datalogue.bi_atomic_tool.input] %s",
            _json_log_payload({"tool_name": name, "input": kwargs}),
        )
        result = tool.execute_external(**kwargs)
        logger.debug(
            "[datalogue.bi_atomic_tool.output] %s",
            _json_log_payload({"tool_name": name, "output": result}),
        )
        return result

    @property
    def tool_names(self) -> list[str]:
        return [tool.name for tool in self.tools]


def build_bi_atomic_toolkit(
    db: Session,
    *,
    query_executor: Callable[[str], Any] | None = None,
) -> DatalogueBIAtomicToolkit:
    """构建 AS-R0 Dataset Query Skill 可见的 AgentScope Toolkit。"""

    context = BIAtomicToolContext(db=db, query_executor=query_executor)
    tools: list[DatalogueBIAtomicTool] = [
        GetDatasetStatusTool(context),
        ListCandidateAssetsTool(context),
        CompileDslToSqlTool(context),
        ExecuteCompiledQueryTool(context),
        RepairDslTool(context),
        CreateQueryArtifactTool(context),
        GetArtifactSummaryTool(context),
    ]
    return DatalogueBIAtomicToolkit(context=context, tools=tools)


def _json_log_payload(payload: dict[str, Any]) -> str:
    """把工具入参/出参转成可 grep 的 JSON 日志；无法序列化时降级为 repr。"""

    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return json.dumps({"repr": repr(payload)}, ensure_ascii=False)


def _get_dataset(db: Session, dataset_id: int) -> SemanticDataset | None:
    return db.query(SemanticDataset).filter(SemanticDataset.id == dataset_id).one_or_none()


def _metadata_schema_summary(dataset: SemanticDataset) -> dict[str, int]:
    # 只返回计数级 metadata summary，不返回表名、字段名、DDL 或 schema 主体。
    return {"selected_table_count": len(dataset.selected_tables or [])}


def _sorted_blueprints(dataset: SemanticDataset) -> list[AnalysisBlueprint]:
    return sorted(dataset.blueprints or [], key=lambda item: item.id or 0)


def _blueprint_summary(blueprint: AnalysisBlueprint) -> dict[str, Any]:
    return {
        "id": blueprint.id,
        "name": blueprint.name,
        "description": blueprint.description,
        "trigger_keywords": blueprint.trigger_keywords or [],
        "when_to_use": blueprint.when_to_use,
    }


def _safe_execution_guard(compiled: dict[str, Any]) -> dict[str, Any]:
    guard = compiled.get("sql_guard") if isinstance(compiled.get("sql_guard"), dict) else {}
    return {
        "ok": bool(guard.get("ok")),
        "warning_count": len(compiled.get("warnings") or []),
    }


def _safe_compile_failure(compiled: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "blocked",
        "code": compiled.get("code") or "COMPILE_BLOCKED",
        "error_summary": compiled.get("error") or "DSL 无法编译为受控查询",
        "compiled_query_ref": None,
        "execution_source": compiled.get("execution_source"),
        "execution_guard": _safe_execution_guard(compiled),
    }


def _safe_execution_failure(compiled_query_ref: str, exc: Exception) -> dict[str, Any]:
    return _safe_execution_failure_from_text(compiled_query_ref, str(exc))


def _safe_execution_failure_from_text(compiled_query_ref: str, error: str) -> dict[str, Any]:
    error_text = str(error or "").lower()
    if "unknown column" in error_text or "no such column" in error_text or "undefined column" in error_text:
        return {
            "status": "blocked",
            "code": "FIELD_NOT_FOUND",
            "repair_required": True,
            "error_summary": "执行查询时发现字段不存在，已阻断本次执行并等待修复节点处理。",
            "compiled_query_ref": compiled_query_ref,
            "artifact_ref": None,
        }
    return {
        "status": "blocked",
        "code": "EXECUTE_FAILED",
        "error_summary": "查询执行失败，已阻断本次执行。",
        "compiled_query_ref": compiled_query_ref,
        "artifact_ref": None,
    }


def _extract_missing_column_ref(exc: Exception) -> str | None:
    return _extract_missing_column_ref_from_text(str(exc))


def _extract_missing_column_ref_from_text(error: Any) -> str | None:
    text = str(error or "")
    patterns = (
        r"Unknown column ['\"]([^'\"]+)['\"]",
        r"no such column: ['\"]?([^'\"\)\]]+)",
        r"column ['\"]([^'\"]+)['\"] does not exist",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" `")
    return None


def _record_field_not_found_failure(compiled: dict[str, Any], failure: dict[str, Any], error: Any) -> None:
    if failure.get("code") != "FIELD_NOT_FOUND":
        return
    compiled["last_execution_failure"] = {
        "code": "FIELD_NOT_FOUND",
        "missing_column_ref": _extract_missing_column_ref_from_text(error),
    }


def _repair_query_plan_payload(
    *,
    query_plan: Any,
    sql_generation_context: Any,
    missing_column_ref: Any,
) -> dict[str, Any] | None:
    if not isinstance(query_plan, dict) or not isinstance(sql_generation_context, dict):
        return None
    missing_table, missing_column = _split_field_ref(str(missing_column_ref or ""))
    if not missing_column:
        return None

    patched = copy.deepcopy(query_plan)
    selected_assets = patched.get("selected_assets")
    if not isinstance(selected_assets, list):
        return None
    for asset in selected_assets:
        if not isinstance(asset, dict):
            continue
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        table_name = str(metadata.get("table_name") or "").strip()
        column_name = str(metadata.get("column_name") or "").strip()
        if not _field_matches_missing(
            table_name=table_name,
            column_name=column_name,
            missing_table=missing_table,
            missing_column=missing_column,
        ):
            continue
        replacement = _find_replacement_field(
            sql_generation_context=sql_generation_context,
            table_name=table_name or missing_table,
            business_label=str(asset.get("display_name") or asset.get("name") or ""),
            old_column=column_name or missing_column,
        )
        if replacement is None:
            return None
        replacement_table, replacement_column = replacement
        repaired_metadata = dict(metadata)
        repaired_metadata["table_name"] = replacement_table
        repaired_metadata["column_name"] = replacement_column
        asset["metadata"] = repaired_metadata
        asset["asset_id"] = f"{replacement_table}.{replacement_column}"
        return patched
    return None


def _split_field_ref(value: str) -> tuple[str, str]:
    raw = str(value or "").strip(" `")
    if "." in raw:
        table_name, column_name = raw.rsplit(".", 1)
        return table_name.strip(" `"), column_name.strip(" `")
    return "", raw.strip(" `")


def _field_matches_missing(
    *,
    table_name: str,
    column_name: str,
    missing_table: str,
    missing_column: str,
) -> bool:
    if column_name != missing_column:
        return False
    return not missing_table or table_name == missing_table


def _find_replacement_field(
    *,
    sql_generation_context: dict[str, Any],
    table_name: str,
    business_label: str,
    old_column: str,
) -> tuple[str, str] | None:
    normalized_label = _normalize_business_label(business_label)
    for table_schema in sql_generation_context.get("table_schemas") or []:
        if not isinstance(table_schema, dict):
            continue
        candidate_table = str(table_schema.get("table_name") or table_schema.get("name") or "").strip()
        if table_name and candidate_table != table_name:
            continue
        for field_info in table_schema.get("fields") or []:
            if not isinstance(field_info, dict):
                continue
            column_name = str(field_info.get("column_name") or field_info.get("name") or "").strip()
            if not column_name or column_name == old_column:
                continue
            field_label = _normalize_business_label(str(field_info.get("display_name") or field_info.get("name") or ""))
            if normalized_label and field_label == normalized_label:
                return candidate_table, column_name
    return None


def _normalize_business_label(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


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


def _tool_input_schema(name: str) -> dict[str, Any]:
    base_schema: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}
    if name == "compile_dsl_to_sql":
        return {
            "type": "object",
            "properties": {
                "dsl": {
                    "type": "object",
                    "description": "DatasetAgent 生成的结构化 DSL；不能包含 SQL。",
                },
            },
            "required": ["dsl"],
            "additionalProperties": False,
        }
    if name in {"execute_compiled_query", "repair_dsl"}:
        return {
            "type": "object",
            "properties": {
                "compiled_query_ref": {
                    "type": "string",
                    "description": "compile_dsl_to_sql 或 repair_dsl 返回的私有执行句柄。",
                },
            },
            "required": ["compiled_query_ref"],
            "additionalProperties": False,
        }
    return base_schema


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {"status": "blocked"}
