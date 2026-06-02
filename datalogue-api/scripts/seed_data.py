#!/usr/bin/env python3
"""
Datalogue MVP 测试数据初始化脚本

用法:
    cd datalogue-api
    python scripts/seed_data.py

功能:
    1. 创建演示数据源（SQLite 内存库，无需外部数据库）
    2. 创建语义数据集（电商订单主题）
    3. 创建常用指标（GMV、订单数、客单价等）
    4. 创建常用维度（地区、品类、时间等）
    5. 创建示例对话历史

环境要求: 后端服务已配置 DATABASE_URL 指向可写的 PostgreSQL
"""

import os
import sys
import random
import logging
from datetime import datetime, timedelta

# 将项目根目录加入路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import encrypt_password
from app import models

# ── 配置 ─────────────────────────────────────────────

DEMO_DB_PATH = os.path.join(PROJECT_ROOT, "scripts", "demo_ecommerce.db")

# ── 1. 创建演示 SQLite 数据源 ─────────────────────────


def create_demo_sqlite_db():
    """创建演示用的 SQLite 电商数据库，包含 orders 和 users 表。"""
    if os.path.exists(DEMO_DB_PATH):
        os.remove(DEMO_DB_PATH)

    engine = create_engine(f"sqlite:///{DEMO_DB_PATH}")
    with engine.connect() as conn:
        # 创建 orders 表
        conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                region TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """))
        # 创建 users 表
        conn.execute(text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                register_date TEXT NOT NULL,
                vip_level INTEGER DEFAULT 0
            )
        """))

        # 插入演示数据
        regions = ["华东", "华南", "华北", "西南", "西北"]
        categories = ["手机", "电脑", "家电", "服装", "食品"]
        statuses = ["已完成", "已发货", "待付款", "已取消"]

        base_date = datetime(2026, 4, 1)
        for i in range(1, 501):
            region = random.choice(regions)
            category = random.choice(categories)
            status = random.choice(statuses)
            amount = round(random.uniform(50, 5000), 2)
            day_offset = random.randint(0, 59)
            created_at = (base_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            conn.execute(
                text(
                    "INSERT INTO orders (id, user_id, amount, region, category, status, created_at) "
                    "VALUES (:id, :user_id, :amount, :region, :category, :status, :created_at)"
                ),
                {
                    "id": i,
                    "user_id": random.randint(1, 100),
                    "amount": amount,
                    "region": region,
                    "category": category,
                    "status": status,
                    "created_at": created_at,
                },
            )

        for i in range(1, 101):
            register_date = (base_date + timedelta(days=random.randint(0, 365))).strftime(
                "%Y-%m-%d"
            )
            conn.execute(
                text(
                    "INSERT INTO users (id, name, register_date, vip_level) VALUES (:id, :name, :register_date, :vip_level)"
                ),
                {
                    "id": i,
                    "name": f"用户_{i:03d}",
                    "register_date": register_date,
                    "vip_level": random.randint(0, 3),
                },
            )

        conn.commit()

    logger.info(f"演示 SQLite 数据库创建完成: {DEMO_DB_PATH}")
    logger.info("  - orders 表: 500 条记录")
    logger.info("  - users 表: 100 条记录")
    return DEMO_DB_PATH


# ── 2. 初始化元数据 ───────────────────────────────────


def seed_metadata(db: SessionLocal, demo_db_path: str):
    """在 PostgreSQL 元数据库中创建演示数据源、数据集、指标、维度。"""

    # 检查是否已有数据
    existing = db.query(models.Datasource).first()
    if existing:
        logger.warning("数据库中已存在数据源，跳过初始化。如需重新初始化，请先清空表。")
        return

    # ── 数据源 ──
    ds = models.Datasource(
        name="演示电商数据库",
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name=demo_db_path,
        username="",
        password_enc=encrypt_password(""),
        status="connected",
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    logger.info(f"数据源创建完成: id={ds.id}, name={ds.name}")

    # ── 数据集 ──
    dataset = models.SemanticDataset(
        name="电商订单分析",
        datasource_id=ds.id,
        tables_json={
            "tables": [
                {"name": "orders", "alias": "o", "description": "订单主表"},
                {"name": "users", "alias": "u", "description": "用户表"},
            ],
            "joins": [
                {
                    "from": "orders",
                    "from_column": "user_id",
                    "to": "users",
                    "to_column": "id",
                    "type": "LEFT JOIN",
                }
            ],
        },
        description="电商平台的订单数据，包含地区、品类、金额等维度，支持 GMV、订单数等核心指标分析",
        status="active",
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    logger.info(f"数据集创建完成: id={dataset.id}, name={dataset.name}")

    # ── 指标 ──
    metrics_data = [
        {
            "name": "gmv",
            "display_name": "GMV",
            "expr": "SUM(o.amount)",
            "filter_sql": "o.status != '已取消'",
            "synonyms": ["销售额", "成交金额", "交易总额", "营收"],
            "description": "商品交易总额，排除已取消订单",
        },
        {
            "name": "order_count",
            "display_name": "订单数",
            "expr": "COUNT(o.id)",
            "filter_sql": None,
            "synonyms": ["订单量", "下单数", "笔数"],
            "description": "订单总笔数",
        },
        {
            "name": "avg_order_value",
            "display_name": "客单价",
            "expr": "AVG(o.amount)",
            "filter_sql": "o.status != '已取消'",
            "synonyms": ["平均订单金额", "人均消费", "ARPU"],
            "description": "平均每笔订单金额",
        },
        {
            "name": "completed_order_count",
            "display_name": "已完成订单数",
            "expr": "COUNT(o.id)",
            "filter_sql": "o.status = '已完成'",
            "synonyms": ["成交订单", "完成单量"],
            "description": "状态为已完成的订单数量",
        },
        {
            "name": "cancel_rate",
            "display_name": "取消率",
            "expr": "COUNT(CASE WHEN o.status = '已取消' THEN 1 END) * 1.0 / COUNT(o.id)",
            "filter_sql": None,
            "synonyms": ["订单取消率", "流失率"],
            "description": "取消订单占总订单的比例",
        },
    ]

    for m in metrics_data:
        metric = models.SemanticMetric(dataset_id=dataset.id, **m)
        db.add(metric)
    db.commit()
    logger.info(f"指标创建完成: {len(metrics_data)} 个")

    # ── 维度 ──
    dimensions_data = [
        {
            "name": "region",
            "display_name": "地区",
            "column_name": "o.region",
            "enum_values": ["华东", "华南", "华北", "西南", "西北"],
            "synonyms": ["区域", "地域", "大区"],
        },
        {
            "name": "category",
            "display_name": "品类",
            "column_name": "o.category",
            "enum_values": ["手机", "电脑", "家电", "服装", "食品"],
            "synonyms": ["类目", "分类", "商品类别"],
        },
        {
            "name": "status",
            "display_name": "订单状态",
            "column_name": "o.status",
            "enum_values": ["已完成", "已发货", "待付款", "已取消"],
            "synonyms": ["状态", "订单进度"],
        },
        {
            "name": "created_at",
            "display_name": "下单日期",
            "column_name": "o.created_at",
            "enum_values": None,
            "synonyms": ["日期", "时间", "下单时间"],
        },
        {
            "name": "vip_level",
            "display_name": "会员等级",
            "column_name": "u.vip_level",
            "enum_values": ["0", "1", "2", "3"],
            "synonyms": ["VIP等级", "用户等级"],
        },
    ]

    for d in dimensions_data:
        dim = models.SemanticDimension(dataset_id=dataset.id, **d)
        db.add(dim)
    db.commit()
    logger.info(f"维度创建完成: {len(dimensions_data)} 个")

    # ── 示例对话 ──
    conv = models.Conversation(
        title="华东区 GMV 分析",
        thread_id="thread-demo-001",
        user_id=1,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)

    messages = [
        {"role": "user", "content": "最近30天华东区的 GMV 是多少？"},
        {
            "role": "assistant",
            "content": "最近30天华东区的 **GMV 为 523,480.50元**，在五大区域中排名第一，占总 GMV 的 **28.3%**。",
            "sql_list": [
                "SELECT SUM(amount) AS gmv FROM orders WHERE region = '华东' AND created_at >= '2026-04-01'"
            ],
        },
        {"role": "user", "content": "那华南区呢？"},
        {
            "role": "assistant",
            "content": "华南区最近30天的 **GMV 为 418,235.20元**，排名第二，与华东区相差约 **10.5万元**。",
            "sql_list": [
                "SELECT SUM(amount) AS gmv FROM orders WHERE region = '华南' AND created_at >= '2026-04-01'"
            ],
        },
    ]
    for m in messages:
        msg = models.Message(conversation_id=conv.id, **m)
        db.add(msg)
    db.commit()
    logger.info(f"示例对话创建完成: id={conv.id}, {len(messages)} 条消息")

    logger.info("所有测试数据初始化完成！")
    logger.info(f"  数据源 ID: {ds.id}")
    logger.info(f"  数据集 ID: {dataset.id}")
    logger.info("你可以通过以下 API 测试:")
    logger.info("  GET  /api/datasource")
    logger.info("  GET  /api/dataset")
    logger.info(
        f'  POST /api/chat/stream  {{"question": "最近30天各品类GMV", "dataset_id": {dataset.id}}}'
    )


# ── 主入口 ───────────────────────────────────────────


def main():
    logger.info("=" * 60)
    logger.info("Datalogue MVP 测试数据初始化")
    logger.info("=" * 60)

    settings = get_settings()
    logger.info(f"元数据库: {settings.DATABASE_URL}")

    # 创建演示 SQLite 数据库
    demo_db_path = create_demo_sqlite_db()

    # 初始化元数据
    db = SessionLocal()
    try:
        seed_metadata(db, demo_db_path)
    finally:
        db.close()


if __name__ == "__main__":
    main()
