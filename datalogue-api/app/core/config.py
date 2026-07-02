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

from pydantic import field_validator
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

    MULTITURN_ENABLED: bool = False
    MULTITURN_LOCK_TTL_SECONDS: int = 300
    MULTITURN_COMPACTION_ENABLED: bool = False
    MULTITURN_COMPACTION_TOKEN_THRESHOLD: int = 8000
    MULTITURN_BLUEPRINT_SHORTCUT_ENABLED: bool = False
    MULTITURN_LAST_SUCCESS_TASK_MAX_TOKENS: int = 2000
    MULTITURN_ARTIFACT_CACHE_TTL_SECONDS: int = 1800
    MULTITURN_REFINEMENT_FAST_PATH_ENABLED: bool = False
    MULTITURN_RESULT_LOCAL_FILTER_ENABLED: bool = False
    MULTITURN_SQL_AST_PATCH_ENABLED: bool = False
    # LeadAgent Planner 输入投影灰度开关；默认关闭，生产按环境变量切流。
    LEAD_AGENT_PLANNER_USE_PROJECTION: bool = False
    LEAD_AGENT_ENABLE_DATASET_FANOUT: bool = False
    # BI LeadAgent DatasetAgent fallback 默认关闭；dev_only 只允许本地开发显式打开，避免生产绕过 AgentScope handoff。
    BI_LEAD_AGENT_DATASET_FALLBACK_MODE: str = "off"
    # BI LeadAgent handoff 实现模式；默认保留 K1/K2 Host Adapter，K3 可显式切到 AgentScope native handoff。
    BI_LEAD_AGENT_HANDOFF_MODE: str = "host_adapter"
    # AS-R0 影子路径开关：只生成 Agentic Shell -> Runtime driver 边界契约，不替换真实 /chat/stream 主链。
    AS_R0_AGENTIC_RUNTIME_SHADOW_ENABLED: bool = False

    QUERY_ARTIFACT_TTL_SECONDS: int = 7 * 24 * 60 * 60
    QUERY_ARTIFACT_MAX_BYTES: int = 2 * 1024 * 1024
    QUERY_ARTIFACT_CLEANUP_INTERVAL_SECONDS: int = 300
    QUERY_ARTIFACT_CLEANUP_BATCH_SIZE: int = 500

    SUBAGENT_FANOUT_MAX_PARALLEL: int = 3

    SUBAGENT_RUNNER_MODE: str = "in_process"
    SUBAGENT_REMOTE_BASE_URL: Optional[str] = None
    SUBAGENT_REMOTE_API_KEY: Optional[str] = None
    SUBAGENT_REMOTE_TIMEOUT_SECONDS: float = 60.0
    SUBAGENT_REMOTE_RETRIES: int = 0

    SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED: bool = False
    SUBAGENT_PLANNER_DETAIL_MAX_ROUNDS: int = 3
    SUBAGENT_PLANNER_DETAIL_MAX_REQUESTS_PER_ROUND: int = 5
    SUBAGENT_PLANNER_FIELD_SEARCH_DEFAULT_TOP_K: int = 30
    SUBAGENT_PLANNER_FIELD_SEARCH_MAX_TOP_K: int = 50
    SUBAGENT_PLANNER_TABLE_FULL_FIELD_LIMIT: int = 120
    SUBAGENT_PLANNER_TABLE_COMPACT_FIELD_LIMIT: int = 300

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

    # --- 数据集路由 ---
    DATASET_ROUTER_AUTO_SELECT_THRESHOLD: float = 0.65
    DATASET_ROUTER_AUTO_SELECT_MARGIN: float = 0.12
    DATASET_ROUTER_MAX_CANDIDATES: int = 3

    # --- 多轮、SubAgent 与数据集上下文预算 ---
    SUBAGENT_LLM_VISIBLE_TOKEN_BUDGET: int = 200
    DATASET_CONTEXT_TOKEN_BUDGET: int = 4000
    SUBAGENT_CANDIDATE_ASSET_CONTEXT_TOKEN_BUDGET: int = 2500

    # --- SubAgent Planner Prompt 与公开控制面裁剪 ---
    SUBAGENT_PLANNER_PROMPT_ASSET_LIMIT: int = 40
    SUBAGENT_PLANNER_PROMPT_TEXT_LIMIT: int = 120
    SUBAGENT_PLANNER_PROMPT_LIST_LIMIT: int = 20
    SUBAGENT_PLANNER_PUBLIC_TEXT_LIMIT: int = 240
    SUBAGENT_PLANNER_PUBLIC_LIST_LIMIT: int = 12

    # --- LeadAgent Planner 投影上下文 ---
    LEAD_AGENT_PLANNER_PROJECTION_MAX_PRIOR_TURNS: int = 3
    LEAD_AGENT_PLANNER_PROJECTION_MAX_TEXT_CHARS: int = 240
    LEAD_AGENT_PLANNER_PROJECTION_MAX_PRIOR_BRIEF_CHARS: int = 360

    # --- 报告、解释与 SQL 自动修复 ---
    ANSWER_EXPLANATION_LOW_CONFIDENCE_THRESHOLD: float = 0.75
    REPORT_RESULT_MAX_ROWS: int = 30
    REPORT_CELL_MAX_CHARS: int = 120
    SQL_MAX_RETRY_COUNT: int = 3
    DSL_FIELD_CATALOG_LIMIT: int = 20

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @field_validator("BI_LEAD_AGENT_DATASET_FALLBACK_MODE")
    @classmethod
    def _validate_bi_lead_agent_dataset_fallback_mode(cls, value: str) -> str:
        normalized = (value or "off").strip().lower()
        if normalized not in {"off", "dev_only"}:
            raise ValueError("BI_LEAD_AGENT_DATASET_FALLBACK_MODE must be 'off' or 'dev_only'")
        return normalized

    @field_validator("BI_LEAD_AGENT_HANDOFF_MODE")
    @classmethod
    def _validate_bi_lead_agent_handoff_mode(cls, value: str) -> str:
        normalized = (value or "host_adapter").strip().lower()
        if normalized not in {"host_adapter", "agentscope_native"}:
            raise ValueError("BI_LEAD_AGENT_HANDOFF_MODE must be 'host_adapter' or 'agentscope_native'")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
