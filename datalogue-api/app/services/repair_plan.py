# ============================================================
# File Name   : repair_plan.py
# Description:
#   RepairPlan 编排与安全校验旧路径兼容门面。
#
# Responsibilities:
#   - re-export 查询执行领域中的 RepairPlan 校验与脱敏能力，保持旧调用方导入不变。
#   - 兼容迁移中，不承载新业务逻辑。
#
# Author      : yangkai
# Created On  : 2026-06-28
# ============================================================

"""RepairPlan 旧路径兼容层。

真实实现已下沉到 `app.domains.query_execution.repair_plan`；旧路径只保留
re-export，避免目录治理过程中一次性改动 Artifact API、Workbench 和测试调用方。
"""

from app.domains.query_execution.repair_plan import (  # noqa: F401  兼容旧调用方导入
    RepairPlanValidationError,
    build_repair_plan_from_diagnosis,
    classify_sql_failure,
    repair_attempt_limit,
    sanitize_repair_plan_artifact_payload,
    sanitize_repair_plan_for_artifact,
    validate_repair_plan,
)

__all__ = [
    "RepairPlanValidationError",
    "build_repair_plan_from_diagnosis",
    "classify_sql_failure",
    "repair_attempt_limit",
    "sanitize_repair_plan_artifact_payload",
    "sanitize_repair_plan_for_artifact",
    "validate_repair_plan",
]
