# ============================================================
# File Name   : dataset.py
# Description:
#   语义数据集治理持久化模型。
#
# Responsibilities:
#   - 存储数据集、指标、维度、源元数据、术语和蓝图。
#   - 定义语义资产和审核工作流之间的关系。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class SemanticDataset(Base, TimestampMixin):
    __tablename__ = "semantic_dataset"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    datasource_id = Column(Integer, ForeignKey("datasource.id"), nullable=False)
    tables_json = Column(JSON, default=dict)
    description = Column(Text)
    # 数据集级 LLM 约束（硬性要求）。由用户在前端编辑，问数时由
    # build_schema_prompt / report_generator 注入到 prompt。
    prompt_instructions = Column(Text, nullable=True)
    # 数据集级 SQL 生成约束。默认启用：无时间范围时查近 30 天，无条数时 LIMIT 100。
    query_constraints = Column(JSON, default=dict)
    status = Column(String(20), default="draft")

    datasource = relationship("Datasource", backref="datasets")
    metrics = relationship("SemanticMetric", backref="dataset", cascade="all, delete-orphan")
    dimensions = relationship("SemanticDimension", backref="dataset", cascade="all, delete-orphan")
    terms = relationship("BusinessTerm", back_populates="dataset", cascade="all, delete-orphan")
    blueprints = relationship(
        "AnalysisBlueprint", back_populates="dataset", cascade="all, delete-orphan"
    )
    validation_cases = relationship(
        "SemanticValidationCase", back_populates="dataset", cascade="all, delete-orphan"
    )
    # 显式覆盖 DatasetSourceTable.dataset 的 backref，启用 ORM 级联删除，
    # 否则 SQLAlchemy 默认 SET NULL，会与 NOT NULL 约束冲突。
    selected_tables = relationship(
        "DatasetSourceTable", back_populates="dataset", cascade="all, delete-orphan"
    )


class SemanticMetric(Base):
    __tablename__ = "semantic_metric"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("semantic_dataset.id"), nullable=False)
    name = Column(String(100), nullable=False)
    display_name = Column(String(100), nullable=False)
    expr = Column(Text, nullable=False)
    table_name = Column(String(100))
    time_field = Column(String(100))
    granularity = Column(String(20))
    format_str = Column(String(50))
    filter_sql = Column(Text)
    synonyms = Column(JSON)
    description = Column(Text)


class SemanticDimension(Base):
    __tablename__ = "semantic_dimension"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("semantic_dataset.id"), nullable=False)
    name = Column(String(100), nullable=False)
    display_name = Column(String(100), nullable=False)
    column_name = Column(String(100), nullable=False)
    table_name = Column(String(100))
    join_to = Column(String(100))
    join_key = Column(String(100))
    hierarchy = Column(JSON)
    enum_values = Column(JSON)
    synonyms = Column(JSON)


class SourceTable(Base, TimestampMixin):
    __tablename__ = "source_table"
    __table_args__ = (
        UniqueConstraint("datasource_id", "schema_name", "table_name", name="uix_source_table"),
    )

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, ForeignKey("datasource.id"), nullable=False)
    schema_name = Column(String(100), nullable=False, default="public")
    table_name = Column(String(100), nullable=False)
    table_comment = Column(Text)
    business_desc = Column(Text)  # 旧字段，保留兼容
    ai_description = Column(Text)
    user_description = Column(Text)
    effective_desc = Column(Text)
    desc_source = Column(String(20), default="unknown")
    annotated_at = Column(DateTime)
    row_count_approx = Column(Integer)
    status = Column(String(20), default="active")
    synced_at = Column(DateTime, default=datetime.utcnow)

    datasource = relationship("Datasource", backref="source_tables")
    columns = relationship(
        "SourceColumn",
        backref="table",
        cascade="all, delete-orphan",
        order_by="SourceColumn.ordinal_position",
    )


class SourceColumn(Base):
    __tablename__ = "source_column"
    __table_args__ = (UniqueConstraint("table_id", "column_name", name="uix_source_column"),)

    id = Column(Integer, primary_key=True, index=True)
    table_id = Column(Integer, ForeignKey("source_table.id"), nullable=False)
    column_name = Column(String(100), nullable=False)
    data_type = Column(String(100))
    column_comment = Column(Text)
    business_desc = Column(Text)  # 旧字段，保留兼容
    ai_description = Column(Text)
    ai_semantic_role = Column(String(30))
    ai_suggested_agg = Column(String(20))
    ai_confidence = Column(Float)
    ai_reason = Column(Text)
    suggested_synonyms = Column(JSON)
    suggested_enum_values = Column(JSON)
    user_description = Column(Text)
    user_semantic_role = Column(String(30))
    effective_desc = Column(Text)
    desc_source = Column(String(20), default="unknown")
    annotated_at = Column(DateTime)
    review_status = Column(String(30), default="pending_review")
    converted_metric_id = Column(
        Integer, ForeignKey("semantic_metric.id", ondelete="SET NULL"), nullable=True
    )
    converted_dimension_id = Column(
        Integer, ForeignKey("semantic_dimension.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at = Column(DateTime)
    is_nullable = Column(String(10))
    column_default = Column(Text)
    ordinal_position = Column(Integer)
    semantic_role = Column(String(30))  # 旧字段，保留兼容
    default_agg = Column(String(20))  # 旧字段，保留兼容
    sample_values = Column(JSON)


class DatasetSourceTable(Base):
    __tablename__ = "dataset_source_table"
    __table_args__ = (
        UniqueConstraint("dataset_id", "source_table_id", name="uix_dataset_source_table"),
    )

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer, ForeignKey("semantic_dataset.id", ondelete="CASCADE"), nullable=False
    )
    source_table_id = Column(
        Integer, ForeignKey("source_table.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("SemanticDataset", back_populates="selected_tables")
    source_table = relationship("SourceTable", backref="dataset_links")


class BusinessTerm(Base, TimestampMixin):
    __tablename__ = "business_term"
    __table_args__ = (
        UniqueConstraint("dataset_id", "name", name="uix_business_term_dataset_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer, ForeignKey("semantic_dataset.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(100), nullable=False)
    display_name = Column(String(100), nullable=False)
    term_type = Column(String(30), default="business_object", nullable=False)
    definition = Column(Text)
    aliases = Column(JSON, default=list)
    forbidden_aliases = Column(JSON, default=list)
    examples = Column(JSON, default=list)
    owner = Column(String(50))
    status = Column(String(20), default="draft", nullable=False)
    source = Column(String(20), default="manual", nullable=False)
    confidence = Column(Float)
    extra_metadata = Column(JSON, default=dict)

    dataset = relationship("SemanticDataset", back_populates="terms")
    asset_links = relationship(
        "BusinessTermAssetLink", back_populates="term", cascade="all, delete-orphan"
    )
    change_logs = relationship(
        "BusinessTermChangeLog", back_populates="term", cascade="all, delete-orphan"
    )


class BusinessTermAssetLink(Base):
    __tablename__ = "business_term_asset_link"
    __table_args__ = (
        UniqueConstraint(
            "term_id", "asset_type", "asset_id", name="uix_business_term_asset_link"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    term_id = Column(Integer, ForeignKey("business_term.id", ondelete="CASCADE"), nullable=False)
    asset_type = Column(String(30), nullable=False)
    asset_id = Column(Integer, nullable=False)
    asset_name = Column(String(150))
    created_at = Column(DateTime, default=datetime.utcnow)

    term = relationship("BusinessTerm", back_populates="asset_links")


class BusinessTermRelation(Base):
    __tablename__ = "business_term_relation"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer, ForeignKey("semantic_dataset.id", ondelete="CASCADE"), nullable=False
    )
    source_term_id = Column(
        Integer, ForeignKey("business_term.id", ondelete="CASCADE"), nullable=False
    )
    target_term_id = Column(
        Integer, ForeignKey("business_term.id", ondelete="CASCADE"), nullable=False
    )
    relation_type = Column(String(30), nullable=False)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class BusinessTermChangeLog(Base):
    __tablename__ = "business_term_change_log"

    id = Column(Integer, primary_key=True, index=True)
    term_id = Column(Integer, ForeignKey("business_term.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(30), nullable=False)
    before_snapshot = Column(JSON)
    after_snapshot = Column(JSON)
    actor = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

    term = relationship("BusinessTerm", back_populates="change_logs")


class SemanticValidationCase(Base, TimestampMixin):
    __tablename__ = "semantic_validation_case"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer, ForeignKey("semantic_dataset.id", ondelete="CASCADE"), nullable=False
    )
    question = Column(Text, nullable=False)
    status = Column(String(20), default="unknown", nullable=False)
    route_type = Column(String(50))
    entry_intent = Column(String(50))
    entry_route = Column(String(50))
    blueprint_id = Column(Integer, ForeignKey("analysis_blueprint.id", ondelete="SET NULL"))
    sql = Column(Text)
    answer = Column(Text)
    error = Column(Text)
    report = Column(JSON, default=dict)
    created_by = Column(String(50))

    dataset = relationship("SemanticDataset", back_populates="validation_cases")
    blueprint = relationship("AnalysisBlueprint")


class DatasetSubAgentManifest(Base, TimestampMixin):
    __tablename__ = "dataset_subagent_manifest"

    dataset_id = Column(
        Integer,
        ForeignKey("semantic_dataset.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    manifest_version = Column(String(40), primary_key=True, nullable=False)
    bound_schema_version = Column(String(64), nullable=False)
    manifest_json = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    is_current = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    review_status = Column(String(30), nullable=False, default="draft", server_default="draft")
    created_by = Column(String(50))

    dataset = relationship("SemanticDataset", backref="subagent_manifests")

    @property
    def schema_hash(self):
        payload = self.manifest_json or {}
        quality = payload.get("quality") or {}
        auto_fields = payload.get("auto_fields") or {}
        return quality.get("schema_hash") or auto_fields.get("bound_schema_version") or self.bound_schema_version

    @property
    def permission_scope(self):
        payload = self.manifest_json or {}
        auto_fields = payload.get("auto_fields") or {}
        return auto_fields.get("permission_scope") or {}

    @property
    def quality_status(self):
        payload = self.manifest_json or {}
        quality = dict(payload.get("quality") or {})
        lint = quality.get("lint") or []
        has_errors = any((item or {}).get("severity") == "error" for item in lint)
        if not quality.get("status"):
            quality["status"] = "failed" if has_errors else "passed"
        quality.setdefault("lint", lint)
        quality.setdefault("schema_hash", self.schema_hash)
        return quality


class AnalysisBlueprint(Base, TimestampMixin):
    __tablename__ = "analysis_blueprint"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(
        Integer, ForeignKey("semantic_dataset.id", ondelete="CASCADE"), nullable=False
    )

    # L0 路由层
    name = Column(String(100), nullable=False)
    description = Column(Text)
    trigger_keywords = Column(JSON, default=list)
    trigger_examples = Column(JSON, default=list)
    when_to_use = Column(Text)

    # L1 调用层
    parameters = Column(JSON, default=list)
    implementation_type = Column(String(30), default="stored_procedure")
    call_template = Column(Text)
    output_schema = Column(JSON, default=list)
    timeout_seconds = Column(Integer, default=30)

    # L2 业务逻辑层
    steps = Column(JSON, default=list)
    attribution_hints = Column(Text)

    # L3 原始代码
    raw_sql = Column(Text)

    status = Column(String(20), default="draft", nullable=False)
    version = Column(Integer, default=0, nullable=False)
    creation_source = Column(String(30), default="manual", nullable=False)
    ai_generated = Column(Boolean, default=False, nullable=False)
    ai_generation_type = Column(String(30))
    ai_confidence = Column(Float)
    owner = Column(String(50))
    last_validated_at = Column(DateTime)
    usage_count = Column(Integer, default=0, nullable=False)
    last_test_result = Column(JSON)

    dataset = relationship("SemanticDataset", back_populates="blueprints")
    versions = relationship(
        "BlueprintVersion", back_populates="blueprint", cascade="all, delete-orphan"
    )
    usage_logs = relationship(
        "BlueprintUsageLog", back_populates="blueprint", cascade="all, delete-orphan"
    )


class BlueprintVersion(Base):
    __tablename__ = "blueprint_version"

    id = Column(Integer, primary_key=True, index=True)
    blueprint_id = Column(
        Integer, ForeignKey("analysis_blueprint.id", ondelete="CASCADE"), nullable=False
    )
    version = Column(Integer, nullable=False)
    snapshot = Column(JSON, nullable=False)
    change_summary = Column(Text)
    published_by = Column(String(50))
    published_at = Column(DateTime, default=datetime.utcnow)

    blueprint = relationship("AnalysisBlueprint", back_populates="versions")


class BlueprintUsageLog(Base):
    __tablename__ = "blueprint_usage_log"

    id = Column(Integer, primary_key=True, index=True)
    blueprint_id = Column(
        Integer, ForeignKey("analysis_blueprint.id", ondelete="CASCADE"), nullable=False
    )
    question = Column(Text)
    extracted_params = Column(JSON, default=dict)
    execution_success = Column(Boolean)
    execution_time_ms = Column(Integer)
    row_count = Column(Integer)
    diagnosis = Column(JSON)
    user_feedback = Column(String(10))
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    blueprint = relationship("AnalysisBlueprint", back_populates="usage_logs")
