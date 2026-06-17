# ============================================================
# File Name   : asset_detail.py
# Description:
#   SubAgent Planner 按需资产详情请求的合同与服务。
#
# Responsibilities:
#   - 校验 Planner 资产详情请求是否位于候选资产召回范围内。
#   - 为后续 SQL 生成规划循环提供表字段、指标、维度和蓝图详情。
#   - 对宽表字段详情做分级返回，避免一次性暴露过大的 schema payload。
#
# Author      : yangkai
# Created On  : 2026-06-18
# ============================================================

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


VALID_DETAIL_LEVELS = {
    "table": {"full_schema", "field_search"},
    "metric": {"detail"},
    "dimension": {"detail"},
    "blueprint": {"detail"},
}


@dataclass
class AssetDetailRequest:
    asset_type: str
    asset_id: str
    detail_level: str
    purpose: str
    reason: str | None = None
    query: str | None = None
    top_k: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssetDetailRequest":
        return cls(
            asset_type=str(data.get("asset_type") or ""),
            asset_id=str(data.get("asset_id") or ""),
            detail_level=str(data.get("detail_level") or ""),
            purpose=str(data.get("purpose") or ""),
            reason=_optional_str(data.get("reason")),
            query=_optional_str(data.get("query")),
            top_k=_optional_int(data.get("top_k")),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "asset_type": self.asset_type,
            "asset_id": self.asset_id,
            "detail_level": self.detail_level,
            "purpose": self.purpose,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.query is not None:
            payload["query"] = self.query
        if self.top_k is not None:
            payload["top_k"] = self.top_k
        return payload


@dataclass
class AssetDetailError:
    request: AssetDetailRequest
    error_code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "error_code": self.error_code,
            "message": self.message,
        }


@dataclass
class AssetDetailValidationResult:
    valid_requests: list[AssetDetailRequest] = field(default_factory=list)
    errors: list[AssetDetailError] = field(default_factory=list)


@dataclass
class AssetDetailResult:
    request: AssetDetailRequest
    coverage: str
    payload: dict[str, Any]
    risk_flags: list[str] = field(default_factory=list)
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "request": self.request.to_dict(),
            "coverage": self.coverage,
            "payload": self.payload,
            "risk_flags": list(self.risk_flags),
        }
        if self.error_code is not None:
            result["error_code"] = self.error_code
        return result


def validate_asset_detail_requests(
    requests: list[AssetDetailRequest | dict[str, Any]],
    *,
    allowed_scope: set[tuple[str, str]],
    max_requests: int,
) -> AssetDetailValidationResult:
    normalized_requests = [_normalize_request(request) for request in requests]
    if len(normalized_requests) > max_requests:
        return AssetDetailValidationResult(
            errors=[
                AssetDetailError(
                    request=request,
                    error_code="request_limit_exceeded",
                    message=f"资产详情请求数量超过上限 {max_requests}",
                )
                for request in normalized_requests
            ]
        )

    valid_requests: list[AssetDetailRequest] = []
    errors: list[AssetDetailError] = []
    normalized_scope = {(str(asset_type), str(asset_id)) for asset_type, asset_id in allowed_scope}

    for request in normalized_requests:
        if request.purpose != "sql_generation":
            errors.append(
                AssetDetailError(
                    request=request,
                    error_code="invalid_purpose",
                    message="资产详情当前仅允许用于 SQL 生成。",
                )
            )
            continue

        if (request.asset_type, request.asset_id) not in normalized_scope:
            errors.append(
                AssetDetailError(
                    request=request,
                    error_code="asset_not_in_recall_scope",
                    message="请求资产不在本轮候选资产召回范围内。",
                )
            )
            continue

        valid_levels = VALID_DETAIL_LEVELS.get(request.asset_type, set())
        if request.detail_level not in valid_levels:
            errors.append(
                AssetDetailError(
                    request=request,
                    error_code="invalid_detail_level",
                    message="请求的资产详情级别不支持。",
                )
            )
            continue

        valid_requests.append(request)

    return AssetDetailValidationResult(valid_requests=valid_requests, errors=errors)


class AssetDetailService:
    def __init__(
        self,
        candidate_assets: Any,
        full_field_limit: int = 120,
        compact_field_limit: int = 300,
        field_search_default_top_k: int = 30,
        field_search_max_top_k: int = 50,
    ) -> None:
        self.candidate_assets = candidate_assets
        self.full_field_limit = full_field_limit
        self.compact_field_limit = compact_field_limit
        self.field_search_default_top_k = field_search_default_top_k
        self.field_search_max_top_k = field_search_max_top_k
        self.assets = _as_list(_get_value(candidate_assets, "assets"))
        context = _get_value(candidate_assets, "context")
        schema_structured = _get_value(context, "schema_structured") if context is not None else None
        self.fields = _as_list(_get_value(schema_structured, "fields"))

    def get_detail(self, request: AssetDetailRequest | dict[str, Any]) -> AssetDetailResult:
        normalized_request = _normalize_request(request)
        if normalized_request.asset_type == "table":
            if normalized_request.detail_level == "full_schema":
                return self._get_table_full_schema(normalized_request)
            if normalized_request.detail_level == "field_search":
                return self._get_table_field_search(normalized_request)
        if normalized_request.asset_type in {"metric", "dimension", "blueprint"}:
            return self._get_metadata_detail(normalized_request)
        return AssetDetailResult(
            request=normalized_request,
            coverage="empty",
            payload={},
            error_code="invalid_detail_level",
        )

    def _get_table_full_schema(self, request: AssetDetailRequest) -> AssetDetailResult:
        asset = self._find_asset(request.asset_type, request.asset_id)
        if asset is None:
            return self._asset_missing_result(request)

        table_name = self._table_name(asset, request)
        fields = self._table_fields(table_name)
        field_count = len(fields)

        payload = self._base_table_payload(request, asset, table_name, field_count)
        if field_count > self.compact_field_limit:
            payload.update(
                {
                    "returned_field_count": 0,
                    "fields": [],
                    "available_detail_requests": ["field_search"],
                    "suggested_next_requests": [
                        AssetDetailRequest(
                            asset_type=request.asset_type,
                            asset_id=request.asset_id,
                            detail_level="field_search",
                            purpose=request.purpose,
                            reason="宽表字段过多，建议按问题搜索字段。",
                            query=request.query,
                            top_k=self.field_search_default_top_k,
                        ).to_dict()
                    ],
                }
            )
            return AssetDetailResult(
                request=request,
                coverage="too_large",
                payload=payload,
                risk_flags=["wide_table"],
            )

        compact = self.full_field_limit < field_count <= self.compact_field_limit
        payload.update(
            {
                "returned_field_count": field_count,
                "fields": [self._render_field(field, include_business_desc=not compact) for field in fields],
            }
        )
        return AssetDetailResult(
            request=request,
            coverage="full_compacted" if compact else "full",
            payload=payload,
        )

    def _get_table_field_search(self, request: AssetDetailRequest) -> AssetDetailResult:
        asset = self._find_asset(request.asset_type, request.asset_id)
        if asset is None:
            return self._asset_missing_result(request)

        table_name = self._table_name(asset, request)
        fields = self._table_fields(table_name)
        requested_top_k = request.top_k or self.field_search_default_top_k
        capped_top_k = min(max(1, requested_top_k), self.field_search_max_top_k)
        scored_fields = [self._score_field(field, request.query) for field in fields]
        matched_fields = [field for field in scored_fields if field["text_score"] > 0]
        matched_fields.sort(
            key=lambda item: (
                item["final_score"],
                item["text_score"],
                item["name"] or "",
            ),
            reverse=True,
        )
        returned_fields = matched_fields[:capped_top_k]
        payload = {
            "asset_type": request.asset_type,
            "asset_id": request.asset_id,
            "table_name": table_name,
            "query": request.query,
            "requested_top_k": requested_top_k,
            "capped_top_k": capped_top_k,
            "returned_count": len(returned_fields),
            "total_matched_estimate": len(matched_fields),
            "fields": returned_fields,
            "suggested_next_queries": self._suggest_next_queries(request.query, returned_fields),
        }
        return AssetDetailResult(
            request=request,
            coverage="partial" if returned_fields else "empty",
            payload=payload,
        )

    def _get_metadata_detail(self, request: AssetDetailRequest) -> AssetDetailResult:
        asset = self._find_asset(request.asset_type, request.asset_id)
        if not asset:
            return AssetDetailResult(
                request=request,
                coverage="empty",
                payload={},
                error_code="asset_not_found",
            )
        payload: dict[str, Any] = {
            "asset_type": asset.get("asset_type"),
            "asset_id": asset.get("asset_id"),
            "name": asset.get("name"),
            "display_name": asset.get("display_name"),
            "description": asset.get("description"),
            "confidence": asset.get("confidence"),
            "metadata": asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {},
            "match_signals": asset.get("match_signals") if isinstance(asset.get("match_signals"), list) else [],
        }
        return AssetDetailResult(request=request, coverage="full", payload=payload)

    def _asset_missing_result(self, request: AssetDetailRequest) -> AssetDetailResult:
        return AssetDetailResult(
            request=request,
            coverage="empty",
            payload={
                "asset_type": request.asset_type,
                "asset_id": request.asset_id,
            },
            risk_flags=["asset_missing"],
            error_code="asset_not_found",
        )

    def _find_asset(self, asset_type: str, asset_id: str) -> dict[str, Any] | None:
        for raw_asset in self.assets:
            asset = raw_asset if isinstance(raw_asset, dict) else {}
            if str(asset.get("asset_type")) == asset_type and str(asset.get("asset_id")) == asset_id:
                return asset
        return None

    def _table_name(self, asset: dict[str, Any] | None, request: AssetDetailRequest) -> str:
        metadata = asset.get("metadata") if isinstance(asset, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        return str(metadata.get("table_name") or (asset or {}).get("name") or request.asset_id)

    def _table_fields(self, table_name: str) -> list[dict[str, Any]]:
        table_fields = []
        for raw_field in self.fields:
            field = raw_field if isinstance(raw_field, dict) else {}
            field_table = field.get("table_name") or field.get("table")
            if str(field_table or "") == table_name:
                table_fields.append(field)
        return table_fields

    def _base_table_payload(
        self,
        request: AssetDetailRequest,
        asset: dict[str, Any] | None,
        table_name: str,
        field_count: int,
    ) -> dict[str, Any]:
        metadata = asset.get("metadata") if isinstance(asset, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        return {
            "asset_type": request.asset_type,
            "asset_id": request.asset_id,
            "table_name": table_name,
            "comment": metadata.get("comment") or metadata.get("description"),
            "field_count": field_count,
        }

    def _render_field(self, field: dict[str, Any], *, include_business_desc: bool) -> dict[str, Any]:
        rendered = {
            "name": _field_name(field),
            "data_type": _optional_str(field.get("data_type") or field.get("type")),
            "comment": _field_comment(field),
            "is_time_candidate": _is_time_field(field),
            "is_filter_candidate": _is_filter_field(field),
            "is_join_candidate": _is_join_field(field),
        }
        if include_business_desc:
            rendered["business_desc"] = _field_business_desc(field)
        return rendered

    def _score_field(self, field: dict[str, Any], query: str | None) -> dict[str, Any]:
        rendered = self._render_field(field, include_business_desc=True)
        text_score, match, fragments = _field_text_score(field, query)
        boost_reason = _field_boost_reason(field)
        boost = 1.5 if boost_reason else 0.0
        final_score = round(text_score + boost, 4)
        return {
            **rendered,
            "text_score": round(text_score, 4),
            "final_score": final_score,
            "boosted": boost_reason is not None,
            "boost_reason": boost_reason,
            "match": match,
            "fragments": fragments,
        }

    def _suggest_next_queries(self, query: str | None, returned_fields: list[dict[str, Any]]) -> list[str]:
        suggestions = []
        if query:
            suggestions.append(str(query))
        for field in returned_fields[:3]:
            name = field.get("name")
            if name:
                suggestions.append(str(name))
        deduplicated = []
        for suggestion in suggestions:
            if suggestion not in deduplicated:
                deduplicated.append(suggestion)
        return deduplicated


def _normalize_request(request: AssetDetailRequest | dict[str, Any]) -> AssetDetailRequest:
    if isinstance(request, AssetDetailRequest):
        return request
    return AssetDetailRequest.from_dict(request if isinstance(request, dict) else {})


def _get_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _field_name(field: dict[str, Any]) -> str | None:
    return _optional_str(field.get("column_name") or field.get("name") or field.get("column"))


def _field_comment(field: dict[str, Any]) -> str | None:
    return _optional_str(field.get("column_comment") or field.get("comment") or field.get("description"))


def _field_business_desc(field: dict[str, Any]) -> str | None:
    return _optional_str(field.get("business_desc") or field.get("effective_desc") or field.get("semantic"))


def _field_text_score(field: dict[str, Any], query: str | None) -> tuple[float, bool, list[str]]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0, False, []

    searchable_parts = [
        _field_name(field),
        _field_comment(field),
        _field_business_desc(field),
        field.get("display_name"),
    ]
    searchable_text = " ".join(str(part) for part in searchable_parts if part).lower()
    text_score = 0.0
    fragments = []
    for token in query_tokens:
        if token and token in searchable_text:
            text_score += 1.0
            fragments.append(token)
    return text_score, bool(fragments), fragments


def _tokens(text: str | None) -> list[str]:
    if not text:
        return []
    tokens = [token.lower() for token in re.split(r"[\s,，。;；、]+", str(text)) if token.strip()]
    return tokens


def _field_boost_reason(field: dict[str, Any]) -> str | None:
    if _is_time_field(field):
        return "time_field_candidate"
    if _is_join_field(field):
        return "join_field_candidate"
    if _is_filter_field(field):
        return "filter_field_candidate"
    return None


def _is_time_field(field: dict[str, Any]) -> bool:
    name = str(_field_name(field) or "").lower()
    data_type = str(field.get("data_type") or field.get("type") or "").lower()
    comment = str(_field_comment(field) or "")
    explicit = field.get("is_time_candidate")
    if isinstance(explicit, bool):
        return explicit
    return (
        name in {"created_at", "updated_at", "create_time", "update_time", "dt", "date"}
        or "time" in name
        or "date" in name
        or "datetime" in data_type
        or "timestamp" in data_type
        or "时间" in comment
        or "日期" in comment
    )


def _is_join_field(field: dict[str, Any]) -> bool:
    explicit = field.get("is_join_candidate")
    if isinstance(explicit, bool):
        return explicit
    name = str(_field_name(field) or "").lower()
    return name == "id" or name.endswith("_id") or name.endswith("id")


def _is_filter_field(field: dict[str, Any]) -> bool:
    explicit = field.get("is_filter_candidate")
    if isinstance(explicit, bool):
        return explicit
    name = str(_field_name(field) or "").lower()
    comment = str(_field_comment(field) or "")
    return any(
        signal in name or signal in comment
        for signal in (
            "status",
            "state",
            "type",
            "category",
            "tenant",
            "region",
            "状态",
            "类型",
            "分类",
        )
    )
