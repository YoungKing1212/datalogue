# ============================================================
# File Name   : Dockerfile
# Description:
#   Datalogue API 容器镜像，承载 FastAPI 与内嵌 AgentScope Service。
#
# Responsibilities:
#   - 安装后端 Python 依赖。
#   - 暴露 uvicorn API 服务入口。
#   - 运行时通过 docker-compose 注入 Postgres、Redis 与 Workspace 配置。
# ============================================================

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
