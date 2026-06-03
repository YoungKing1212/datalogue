from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey, DateTime, UniqueConstraint
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
    status = Column(String(20), default="draft")

    datasource = relationship("Datasource", backref="datasets")
    metrics = relationship("SemanticMetric", backref="dataset", cascade="all, delete-orphan")
    dimensions = relationship("SemanticDimension", backref="dataset", cascade="all, delete-orphan")
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
    user_description = Column(Text)
    user_semantic_role = Column(String(30))
    effective_desc = Column(Text)
    desc_source = Column(String(20), default="unknown")
    annotated_at = Column(DateTime)
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
