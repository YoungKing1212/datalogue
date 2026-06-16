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
    # 日志文件目录；空字符串表示不写文件（仅 stdout）
    LOG_DIR: str = "logs"
    # 单个日志文件最大字节数（默认 10MB）
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    # 保留的轮转文件份数
    LOG_BACKUP_COUNT: int = 7

    LANGFUSE_ENABLED: bool = False
    # Langfuse Python SDK v4 使用 base_url；保留 HOST 兼容旧配置和文档。
    LANGFUSE_BASE_URL: Optional[str] = "http://localhost:3000"
    LANGFUSE_HOST: Optional[str] = None
    LANGFUSE_PROJECT_ID: Optional[str] = None
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_ENVIRONMENT: str = "dev"
    LANGFUSE_RELEASE: str = "local"
    LANGFUSE_PROMPT_LABEL: str = "production"
    LANGFUSE_SAMPLE_RATE: float = 1.0
    LANGFUSE_FLUSH_AT_END: bool = True
    LANGFUSE_MAX_TEXT_LENGTH: int = 4000

    MULTITURN_ENABLED: bool = False
    MULTITURN_LOCK_TTL_SECONDS: int = 300
    MULTITURN_COMPACTION_ENABLED: bool = False
    MULTITURN_COMPACTION_TOKEN_THRESHOLD: int = 8000
    MULTITURN_BLUEPRINT_SHORTCUT_ENABLED: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
