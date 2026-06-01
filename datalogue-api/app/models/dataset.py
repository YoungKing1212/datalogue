from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey
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
    status = Column(String(20), default="draft")

    datasource = relationship("Datasource", backref="datasets")
    metrics = relationship("SemanticMetric", backref="dataset", cascade="all, delete-orphan")
    dimensions = relationship("SemanticDimension", backref="dataset", cascade="all, delete-orphan")


class SemanticMetric(Base):
    __tablename__ = "semantic_metric"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("semantic_dataset.id"), nullable=False)
    name = Column(String(100), nullable=False)
    display_name = Column(String(100), nullable=False)
    expr = Column(Text, nullable=False)
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
    enum_values = Column(JSON)
    synonyms = Column(JSON)
