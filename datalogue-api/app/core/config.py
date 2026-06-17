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
    MULTITURN_ARTIFACT_CACHE_TTL_SECONDS: int = 1800
    MULTITURN_REFINEMENT_FAST_PATH_ENABLED: bool = False
    MULTITURN_RESULT_LOCAL_FILTER_ENABLED: bool = False
    MULTITURN_SQL_AST_PATCH_ENABLED: bool = False
    # LeadAgent Planner 输入投影灰度开关；默认关闭，生产按环境变量切流。
    LEAD_AGENT_PLANNER_USE_PROJECTION: bool = False

    # ============================================================
    # LeadAgent 渐进式资产注入（Progressive Asset Integration）
    # ============================================================

    # 总开关：是否启用候选资产召回并注入 LeadAgent Planner
    LEAD_AGENT_USE_PROGRESSIVE_ASSETS: bool = False

    # --- 按资产类型的 Top-K 限制 ---
    LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_BLUEPRINT: int = 3
    LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_METRIC: int = 5
    LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_DIMENSION: int = 5
    LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_TERM: int = 5
    LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_FIELD: int = 10
    LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_TABLE: int = 8

    # --- 按资产类型的置信度阈值 ---
    LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_BLUEPRINT: float = 0.60
    LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_METRIC: float = 0.35
    LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_DIMENSION: float = 0.35
    LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_TERM: float = 0.30
    LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_FIELD: float = 0.25
    LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_TABLE: float = 0.25

    # --- 全局 Token 预算（按阶段） ---
    LEAD_AGENT_PROGRESSIVE_ASSET_TOKEN_BUDGET_SKILL_SELECTION: int = 600
    LEAD_AGENT_PROGRESSIVE_ASSET_TOKEN_BUDGET_TOOL_PLANNING: int = 800

    # --- 全局最小置信度（兜底，任何类型资产都必须超过此值） ---
    LEAD_AGENT_PROGRESSIVE_ASSET_GLOBAL_MIN_CONFIDENCE: float = 0.20

    # --- 元信息脱敏白名单（逗号分隔的字段名） ---
    # 空字符串表示全部脱敏（只保留 name/display_name）
    LEAD_AGENT_PROGRESSIVE_ASSET_METADATA_WHITELIST: str = "table_name,column_name,parameters,expr"

    # --- match_signals 保留数量 ---
    LEAD_AGENT_PROGRESSIVE_ASSET_MAX_SIGNALS_PER_ASSET: int = 3

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
