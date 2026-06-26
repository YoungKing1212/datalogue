# ============================================================
# File Name   : capability_manifest.py
# Description:
#   数据集能力清单对外可见契约。
#
# Responsibilities:
#   - 定义 LeadAgent 路由只能消费的业务摘要字段。
#   - 禁止字段、表、SQL、blueprint 主体和完整语义资产详情进入可见面。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from typing import Literal

from pydantic import BaseModel, ConfigDict


class CapabilityManifest(BaseModel):
    """数据集能力清单完整可见面，只包含业务摘要层信息。"""

    dataset_id: int
    business_name: str
    can_answer: list[str] = []
    cannot_answer: list[str] = []
    metrics: list[str] = []
    dimensions: list[str] = []
    typical_questions: list[str] = []
    route_hints: list[str] = []
    permission_scope: str = "dataset"
    quality_status: Literal["draft", "reviewed", "published"] = "draft"
    schema_version: str = "capability_manifest.v1"

    model_config = ConfigDict(extra="forbid")


class CapabilityManifestSummary(BaseModel):
    """给 LeadAgent 路由使用的最小摘要，不包含任何内部执行资产。"""

    dataset_id: int
    business_name: str
    can_answer: list[str] = []
    cannot_answer: list[str] = []
    metrics: list[str] = []
    dimensions: list[str] = []
    typical_questions: list[str] = []
    route_hints: list[str] = []
    permission_scope: str = "dataset"
    quality_status: Literal["draft", "reviewed", "published"] = "draft"
    schema_version: str = "capability_manifest.v1"

    model_config = ConfigDict(extra="forbid")
