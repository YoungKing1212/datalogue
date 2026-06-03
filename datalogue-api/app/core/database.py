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
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
