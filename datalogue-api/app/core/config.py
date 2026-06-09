# ============================================================
# File Name   : config.py
# Description:
#   应用配置定义。
#
# Responsibilities:
#   - 从环境变量读取服务配置。
#   - 为 API 和图工作流模块提供缓存后的配置对象。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://datalogue:datalogue@localhost:5432/datalogue"

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = "https://api.minimaxi.com/v1"
    OPENAI_PROXY_URL: Optional[str] = None
    LLM_MODEL: str = "MiniMax-M2.7"
    LLM_TIMEOUT_SECONDS: float = 60.0

    SECRET_KEY: str = "change-me"
    AES_KEY: str = "your-32-byte-aes-key-here!!"

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
