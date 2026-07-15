# ============================================================
# File Name   : capability_policy.py
# Description:
#   BI 查询能力分级策略与安全校验。
#
# Responsibilities:
#   - 定义单表、多表、指标语义和多智能体四级查询能力。
#   - 在执行前校验 QueryPlan 是否超出当前能力边界。
#   - 返回不包含表、字段、关系和查询内容的结构化安全违规。
#
# Author      : yangkai
# Created On  : 2026-07-15
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domains.bi.worker.contracts import BIWorkerQueryPlan


class BICapabilityLevel(StrEnum):
    """演示版本逐级开放的 BI 查询能力。"""

    SINGLE_TABLE = "single_table"
    MULTI_TABLE = "multi_table"
    SEMANTIC_METRICS = "semantic_metrics"
    AGENT_TEAM = "agent_team"


class BICapabilityViolationCode(StrEnum):
    """稳定的能力违规码，供运行时和前端按类型处理。"""

    SUPPORTING_ENTITY_NOT_ALLOWED = "supporting_entity_not_allowed"
    JOIN_NOT_ALLOWED = "join_not_allowed"
    METRIC_NOT_ALLOWED = "metric_not_allowed"
    GROUP_BY_NOT_ALLOWED = "group_by_not_allowed"
    ENTITY_LIMIT_EXCEEDED = "entity_limit_exceeded"


@dataclass(frozen=True, slots=True)
class BICapabilityPolicy:
    """单个能力等级对应的后端强制边界。"""

    level: BICapabilityLevel
    max_entities: int | None
    allow_supporting_entities: bool
    allow_joins: bool
    allow_metrics: bool
    allow_group_by: bool


@dataclass(frozen=True, slots=True)
class BICapabilityViolation:
    """面向安全响应的违规项，不携带 QueryPlan 内部引用。"""

    code: BICapabilityViolationCode
    safe_reason: str


@dataclass(frozen=True, slots=True)
class BICapabilityValidationResult:
    """能力校验结果；调用方可据此 fail closed。"""

    allowed: bool
    level: BICapabilityLevel
    violations: tuple[BICapabilityViolation, ...] = ()


BI_CAPABILITY_POLICIES: dict[BICapabilityLevel, BICapabilityPolicy] = {
    BICapabilityLevel.SINGLE_TABLE: BICapabilityPolicy(
        level=BICapabilityLevel.SINGLE_TABLE,
        max_entities=1,
        allow_supporting_entities=False,
        allow_joins=False,
        allow_metrics=False,
        allow_group_by=False,
    ),
    BICapabilityLevel.MULTI_TABLE: BICapabilityPolicy(
        level=BICapabilityLevel.MULTI_TABLE,
        max_entities=3,
        allow_supporting_entities=True,
        allow_joins=True,
        allow_metrics=False,
        allow_group_by=False,
    ),
    BICapabilityLevel.SEMANTIC_METRICS: BICapabilityPolicy(
        level=BICapabilityLevel.SEMANTIC_METRICS,
        max_entities=None,
        allow_supporting_entities=True,
        allow_joins=True,
        allow_metrics=True,
        allow_group_by=True,
    ),
    BICapabilityLevel.AGENT_TEAM: BICapabilityPolicy(
        level=BICapabilityLevel.AGENT_TEAM,
        max_entities=None,
        allow_supporting_entities=True,
        allow_joins=True,
        allow_metrics=True,
        allow_group_by=True,
    ),
}


def get_bi_capability_policy(level: BICapabilityLevel | str) -> BICapabilityPolicy:
    """把配置值解析为确定的能力策略，无效配置直接抛错避免静默放权。"""

    parsed_level = BICapabilityLevel(level)
    return BI_CAPABILITY_POLICIES[parsed_level]


def validate_bi_query_plan_capability(
    plan: BIWorkerQueryPlan,
    policy: BICapabilityPolicy,
) -> BICapabilityValidationResult:
    """校验查询计划是否处于能力边界内，并返回去内部细节的违规列表。"""

    violations: list[BICapabilityViolation] = []

    # 支持实体与关联分别校验，调用方可以准确区分超范围原因。
    if plan.data_graph.supporting_entities and not policy.allow_supporting_entities:
        violations.append(
            BICapabilityViolation(
                code=BICapabilityViolationCode.SUPPORTING_ENTITY_NOT_ALLOWED,
                safe_reason="当前能力等级仅支持单表查询。",
            )
        )
    if plan.join_requirements and not policy.allow_joins:
        violations.append(
            BICapabilityViolation(
                code=BICapabilityViolationCode.JOIN_NOT_ALLOWED,
                safe_reason="当前能力等级暂不支持关联查询。",
            )
        )
    if plan.metrics and not policy.allow_metrics:
        violations.append(
            BICapabilityViolation(
                code=BICapabilityViolationCode.METRIC_NOT_ALLOWED,
                safe_reason="当前能力等级暂不支持指标查询。",
            )
        )
    if plan.group_by and not policy.allow_group_by:
        violations.append(
            BICapabilityViolation(
                code=BICapabilityViolationCode.GROUP_BY_NOT_ALLOWED,
                safe_reason="当前能力等级暂不支持维度分组。",
            )
        )

    entity_count = 1 + len(plan.data_graph.supporting_entities)
    if policy.max_entities is not None and entity_count > policy.max_entities:
        violations.append(
            BICapabilityViolation(
                code=BICapabilityViolationCode.ENTITY_LIMIT_EXCEEDED,
                safe_reason="查询涉及的实体数量超出当前能力等级限制。",
            )
        )

    return BICapabilityValidationResult(
        allowed=not violations,
        level=policy.level,
        violations=tuple(violations),
    )
