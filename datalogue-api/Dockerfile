# ============================================================================
# Datalogue API — 多阶段 Docker 构建
# ============================================================================
# 使用方式：
#   docker build -t datalogue-api:latest -f Dockerfile .
#   docker build --target production -t datalogue-api:latest -f Dockerfile .
#
# 构建参数：
#   ENTERPRISE_DEPS=1  — 安装企业数据源驱动 (Oracle/Hive/SQL Server/...)
# ============================================================================

# ── Stage 1: 基础依赖层 ──────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 系统依赖 (build-essential 在编译后移除，最终镜像不保留)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Stage 2: 安装 Python 依赖 ─────────────────────────
FROM base AS dependencies

# 先复制依赖文件 → 利用 Docker 层缓存，不改依赖时不重装
COPY requirements.txt requirements-enterprise.txt ./

# 核心依赖
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# 企业数据源驱动 (由 --build-arg ENTERPRISE_DEPS=1 控制)
ARG ENTERPRISE_DEPS=0
RUN if [ "$ENTERPRISE_DEPS" = "1" ]; then \
        pip install -r requirements-enterprise.txt; \
    fi

# ── Stage 3: 运行时镜像 ──────────────────────────────
FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

WORKDIR /app

# 仅复制编译好的依赖，不保留 build-essential
COPY --from=dependencies /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# 复制应用代码 (config/ 含 bi_worker_permissions.json 等运行时配置)
COPY app/ ./app/
COPY conf/ ./conf/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# 创建工作区目录 (运行时挂载 volume 覆盖)
RUN mkdir -p /app/data/agentscope/workspaces

# 非 root 用户运行 (安全)
RUN groupadd -r datalogue && useradd -r -g datalogue -d /app -s /sbin/nologin datalogue \
    && chown -R datalogue:datalogue /app

# 健康检查（改用 python urllib，避免依赖 curl；production stage 未安装 curl）
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else sys.exit(1)"

EXPOSE 8000

USER datalogue

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── Stage 4: 开发镜像 (热重载) ──────────────────────
FROM dependencies AS development

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
