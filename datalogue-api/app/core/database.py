# ============================================================
# File Name   : database.py
# Description:
#   数据库引擎和会话管理。
#
# Responsibilities:
#   - 创建 SQLAlchemy engine、session factory 和声明式基类。
#   - 提供请求级数据库会话依赖。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import get_settings
import os

settings = get_settings()

# echo=True 会绕过 logging 直接把 SQL print 到 stdout，必须显式关闭；
# 需要看 SQL 时设环境变量 SQL_ECHO=true
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=os.getenv("SQL_ECHO", "false").lower() in ("true", "1", "yes"),
    # 默认 ensure_ascii=True 会把中文序列化为 \uXXXX 存入 JSON 列，
    # 设为 False 直接存 UTF-8 明文，DB 工具中可读性更好。
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
