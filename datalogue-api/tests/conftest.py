# ============================================================
# File Name   : conftest.py
# Description:
#   API 测试的共享 pytest fixture 配置。
#
# Responsibilities:
#   - 创建隔离的测试数据库会话和测试客户端。
#   - 准备通用数据源、数据集、指标和维度测试数据。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""
Pytest 全局配置与共享 fixtures
"""

import os
import sys
import pytest
from contextlib import asynccontextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# 确保项目根目录在路径中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app.core.database import Base, get_db
from app.main import app


@asynccontextmanager
async def _test_lifespan(_app):
    yield


app.router.lifespan_context = _test_lifespan

# ── 使用 SQLite 内存数据库作为测试数据库 ─────────────────
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """创建测试用数据库引擎（SQLite 内存）。"""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(engine):
    """每个测试函数独立的 DB Session。"""
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session):
    """返回配置好测试数据库的 FastAPI TestClient。"""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_datasource(db_session):
    """创建一个示例数据源。"""
    from app.core.models.datasource import Datasource
    from app.core.security import encrypt_password

    ds = Datasource(
        name="测试数据源",
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name=":memory:",
        username="test",
        password_enc=encrypt_password("testpass"),
        status="connected",
    )
    db_session.add(ds)
    db_session.commit()
    db_session.refresh(ds)
    return ds


@pytest.fixture
def sample_dataset(db_session, sample_datasource):
    """创建一个示例数据集（含指标和维度）。"""
    from app.core.models.dataset import SemanticDataset, SemanticMetric, SemanticDimension

    dataset = SemanticDataset(
        name="测试数据集",
        datasource_id=sample_datasource.id,
        tables_json={
            "tables": [{"name": "orders", "alias": "o"}],
            "joins": [],
        },
        description="测试用数据集",
        status="active",
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)

    # 指标
    metrics = [
        SemanticMetric(
            dataset_id=dataset.id,
            name="gmv",
            display_name="GMV",
            expr="SUM(o.amount)",
            filter_sql="o.status != '已取消'",
            synonyms=["销售额"],
            description="商品交易总额",
        ),
        SemanticMetric(
            dataset_id=dataset.id,
            name="order_count",
            display_name="订单数",
            expr="COUNT(o.id)",
            synonyms=["订单量"],
            description="订单总笔数",
        ),
    ]
    for m in metrics:
        db_session.add(m)

    # 维度
    dimensions = [
        SemanticDimension(
            dataset_id=dataset.id,
            name="region",
            display_name="地区",
            column_name="o.region",
            enum_values=["华东", "华南"],
            synonyms=["区域"],
        ),
        SemanticDimension(
            dataset_id=dataset.id,
            name="category",
            display_name="品类",
            column_name="o.category",
            enum_values=["手机", "电脑"],
            synonyms=["类目"],
        ),
    ]
    for d in dimensions:
        db_session.add(d)

    db_session.commit()
    db_session.refresh(dataset)
    return dataset
