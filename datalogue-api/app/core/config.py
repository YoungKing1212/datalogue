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
    AUTH_TRANSPORT_KEY: str = "datalogue-auth-transport-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUTH_COOKIE_NAME: str = "refresh_token"
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: str = "lax"
    AUTH_COOKIE_PATH: str = "/api/auth"
    BOOTSTRAP_ADMIN_USERNAME: str = "admin"
    BOOTSTRAP_ADMIN_PASSWORD: str = "admin"
    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    # 日志文件目录；空字符串表示不写文件（仅 stdout）
    LOG_DIR: str = "logs"
    # 单个日志文件最大字节数（默认 10MB）
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    # 保留的轮转文件份数
    LOG_BACKUP_COUNT: int = 7
    # 本地调试开关：打开后打印 Agent 原始 prompt 和返回值。
    AGENT_DEBUG_RAW_LOGS: bool = False
    # 本地调试开关：打开后允许 BI Worker thinking delta 原文进入前端推理摘要；仅限短时排障。
    DATALOGUE_DEBUG_STREAM_RAW_THINKING: bool = False
    # 自动标题后台线程开关；测试或批处理场景可关闭，避免异步 DB 副作用干扰主链验证。
    DATALOGUE_AUTO_TITLE_ENABLED: bool = True

    # ---- AgentScope OpenTelemetry 配置 ----
    # WARNING: TracingMiddleware 会将模型请求/响应内容（messages、tools schema、
    # 模型输出）写入 span 属性。开启 exporter 后这些内容会外发到 collector。
    # 默认全部关闭；排障时按短时间窗口打开。
    AGENTSCOPE_OTEL_TRACING_ENABLED: bool = False       # 启用 tracing（创建 span）
    AGENTSCOPE_OTEL_LOGGING_ENABLED: bool = False       # tracing 开启时，把 span 打到后端日志（DEBUG 级别）
    AGENTSCOPE_OTEL_EXPORTER_ENABLED: bool = False      # 启用 exporter（外发 span）
    AGENTSCOPE_OTEL_EXPORTER_ENDPOINT: str | None = None
    AGENTSCOPE_OTEL_SERVICE_NAME: str = "datalogue-api"

    # AgentScope 官方 Agent Service 子应用挂载配置；默认开启，让主链从 /api 旁路进入官方 service。
    AGENTSCOPE_SERVICE_ENABLED: bool = True
    AGENTSCOPE_MOUNT_PATH: str = "/agentscope"
    AGENTSCOPE_SERVICE_BASE_URL: Optional[str] = "http://127.0.0.1:8000/agentscope"
    # AgentScope Service 的 Redis/Workspace 参数只在子应用启动生命周期中真正连接外部资源。
    AGENTSCOPE_REDIS_HOST: str = "localhost"
    AGENTSCOPE_REDIS_PORT: int = 6379
    AGENTSCOPE_REDIS_DB: int = 0
    AGENTSCOPE_REDIS_PASSWORD: Optional[str] = None
    AGENTSCOPE_REDIS_URL: Optional[str] = "redis://localhost:6379/0"
    AGENTSCOPE_WORKSPACE_BASEDIR: str = "data/agentscope/workspaces"
    AGENTSCOPE_WORKSPACE_TTL_SECONDS: float = 3600.0

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
    # BI Agent DatasetAgent fallback 默认关闭；dev_only 只允许本地开发显式打开，避免生产绕过 AgentScope handoff。
    BI_LEAD_AGENT_DATASET_FALLBACK_MODE: str = "off"  # 兼容旧环境变量名；内部语义已迁为 BI Agent。
    # AS-R0 历史影子开关：保留配置读取兼容，当前真实入口已切到 AgentScope Agent Team。
    AS_R0_AGENTIC_RUNTIME_SHADOW_ENABLED: bool = False

    QUERY_ARTIFACT_TTL_SECONDS: int = 7 * 24 * 60 * 60
    QUERY_ARTIFACT_MAX_BYTES: int = 2 * 1024 * 1024
    QUERY_ARTIFACT_CLEANUP_INTERVAL_SECONDS: int = 300
    QUERY_ARTIFACT_CLEANUP_BATCH_SIZE: int = 500

    SUBAGENT_FANOUT_MAX_PARALLEL: int = 3

    QUERY_ARTIFACT_MAINTENANCE_API_KEY: Optional[str] = None

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
    def _validate_bi_agent_dataset_fallback_mode(cls, value: str) -> str:
        normalized = (value or "off").strip().lower()
        if normalized not in {"off", "dev_only"}:
            raise ValueError("BI_LEAD_AGENT_DATASET_FALLBACK_MODE must be 'off' or 'dev_only'")
        return normalized

    @field_validator("AUTH_COOKIE_SAMESITE")
    @classmethod
    def _validate_auth_cookie_samesite(cls, value: str) -> str:
        normalized = (value or "lax").strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("AUTH_COOKIE_SAMESITE must be 'lax', 'strict' or 'none'")
        return normalized

@lru_cache
def get_settings() -> Settings:
    return Settings()
