# Datalogue Docker 部署方案

## 架构

```
                 ┌──────────────┐
                 │    Nginx     │  ← 可选反向代理（HTTPS 终止）
                 │  (443/80)    │
                 └──────┬───────┘
                        │
                 ┌──────▼───────┐
                 │  datalogue-  │
                 │  api:8000    │  ← FastAPI + AgentScope Service
                 │              │
                 │  /api/*      │  ← 业务 API
                 │  /agentscope/*│ ← Agent 编排
                 └──────┬───────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
  ┌────────────┐ ┌────────────┐ ┌────────────┐
  │ datalogue- │ │ datalogue- │ │  外部数据源 │
  │ db:5432    │ │ redis:6379 │ │ (MySQL/…)  │
  │ PostgreSQL │ │            │ │            │
  │ +pgvector  │ │ MessageBus │ │            │
  └────────────┘ └────────────┘ └────────────┘
```

## 快速部署

### 前置条件

- Docker Engine 24+ 及 Docker Compose v2
- 可用的 LLM API Key（MiniMax / DeepSeek / OpenAI 等）

### 1. 一键启动

```bash
# 设置 LLM API Key（必填）
export OPENAI_API_KEY=your-api-key-here

# 设置数据库密码（可选，默认 datalogue）
export DB_PASSWORD=your-strong-password

# 使用 Makefile 一键构建并启动
make docker-build
make docker-up

# ── 或手动执行 ──
# 构建镜像（多阶段，仅运行时层）
./scripts/docker-build.sh

# 启动完整部署
docker compose --profile all up -d

# 查看启动日志
docker compose logs -f
```

### 2. 验证部署

```bash
# 健康检查
curl http://localhost:8000/health
# 预期: {"status":"ok"}

# 查看运行容器
docker compose ps

# 确认数据库就绪
docker compose exec db pg_isready -U datalogue
```

### 3. 初始化数据库

```bash
# 自动建表（容器启动时自动执行 metadata.create_all）
# 如需手动运行迁移：
docker compose exec api alembic upgrade head
```

### 4. 访问

| 服务 | 地址 |
|------|------|
| API Swagger 文档 | http://localhost:8000/docs |
| API ReDoc 文档 | http://localhost:8000/redoc |
| 健康检查 | http://localhost:8000/health |

---

## 自定义配置

### 环境变量文件

推荐使用 `.env` 文件管理配置：

```bash
cp .env.example .env
# 编辑 .env
```

关键变量示例（`.env`）：

```env
# ── 数据库 ──
DB_PASSWORD=datalogue@2024
API_PORT=8000

# ── LLM ──
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://api.minimaxi.com/v1
LLM_MODEL=MiniMax-M2.7

# ── 安全（生产环境务必修改）──
SECRET_KEY=generate-a-random-secret-here
AES_KEY=your-32-byte-aes-key-here

# ── 运行模式 ──
APP_ENV=production
LOG_LEVEL=INFO
```

然后启动：

```bash
docker compose --profile all --env-file .env up -d
```

---

## 生产环境部署

### 1. 反向代理 + HTTPS

推荐用 Nginx 做 TLS 终止：

```nginx
# /etc/nginx/sites-available/datalogue
server {
    listen 443 ssl http2;
    server_name datalogue.your-company.com;

    ssl_certificate /etc/ssl/certs/datalogue.crt;
    ssl_certificate_key /etc/ssl/private/datalogue.key;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 流式响应需要关闭缓冲
        proxy_buffering off;
        proxy_cache off;
    }
}
```

### 2. 资源建议

| 服务 | CPU | 内存 | 存储 |
|------|-----|------|------|
| API (datalogue-api) | 2 核 | 4 GB | — |
| PostgreSQL | 2 核 | 4 GB | 50 GB+ (数据增长) |
| Redis | 1 核 | 1 GB | 10 GB (AOF 持久化) |
| **合计** | **5 核** | **9 GB** | **60 GB+** |

> 实际需求取决于并发量、数据集规模和查询频率。上述为中等负载参考。

### 3. 安全加固

| 措施 | 说明 |
|------|------|
| 修改默认密码 | 设置 `DB_PASSWORD`、`SECRET_KEY`、`AES_KEY` |
| 数据库端口隔离 | 生产环境移除 `db:5432` 的 `ports` 暴露，仅内部网络访问 |
| 网络隔离 | 使用 Docker 自定义网络，只暴露 `api:8000` |
| 数据卷备份 | 定期备份 `datalogue_pgdata` 和 `datalogue_redisdata` |
| 日志轮转 | Docker 默认 json-file 日志驱动，配置 max-size/max-file |

```yaml
# docker-compose.override.yml 追加
services:
  api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
  db:
    ports: []  # 不暴露数据库端口到宿主机
  redis:
    ports: []
```

### 4. 多环境配置

```bash
# 开发环境
docker compose --profile all -f docker-compose.yml -f docker-compose.override.yml up -d

# 生产环境（覆盖配置）
docker compose --profile all -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 运维操作

### 查看日志

```bash
# 所有服务
docker compose logs -f

# 仅 API
docker compose logs -f api

# 最近 100 行
docker compose logs --tail=100 api
```

### 数据备份与恢复

```bash
# 备份 PostgreSQL
docker compose exec db pg_dump -U datalogue datalogue > datalogue_backup_$(date +%Y%m%d).sql

# 恢复
cat datalogue_backup.sql | docker compose exec -T db psql -U datalogue datalogue

# 备份 Redis RDB
docker compose cp redis:/data/appendonly.aof ./redis_backup.aof
```

### 升级

```bash
# 拉取最新代码
git pull

# 重新构建并滚动重启
docker compose --profile all build --no-cache api
docker compose --profile all up -d

# 运行数据库迁移（如有）
docker compose exec api alembic upgrade head
```

### 健康检查与监控

```yaml
# docker-compose.override.yml — 健康检查增强
services:
  api:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

```bash
# 查看容器健康状态
docker compose ps

# Prometheus 指标（如需）
# FastAPI 默认不暴露 metrics endpoint，可集成 prometheus-fastapi-instrumentator
```

---

## 常见问题

### Q: 启动后 API 无法连接数据库

确认 `db` 容器先于 `api` 就绪。健康检查会自动等待，但如果数据库密码不匹配会报错：

```
psycopg2.OperationalError: FATAL: password authentication failed for user "datalogue"
```

**解决**：检查 `.env` 中 `DB_PASSWORD` 与 docker-compose 中设置的密码一致。

### Q: API 提示 "OPENAI_API_KEY environment variable required"

`OPENAI_API_KEY` 是必填环境变量：

```bash
export OPENAI_API_KEY=sk-your-key
docker compose --profile all up -d
```

### Q: 想要只启动基础设施（本地开发）

```bash
docker compose up -d db redis
# 然后在 IDE/终端中用 .venv/bin/uvicorn 启动 API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Q: 如何添加数据源驱动（Oracle / Hive / SQL Server 等）

企业数据源驱动不包含在基础镜像中。有两种方式：

**方案 A：在 Dockerfile 中预装**

```dockerfile
RUN pip install oracledb PyHive[hive_pure_sasl,presto] trino pyodbc
```

**方案 B：挂载离线 wheel 包后运行时安装**

```yaml
services:
  api:
    volumes:
      - ./wheelhouse:/app/wheelhouse
    command: >
      sh -c "pip install --no-index --find-links /app/wheelhouse -r requirements-enterprise.txt 2>/dev/null
      && uvicorn app.main:app --host 0.0.0.0 --port 8000"
```

### Q: 数据库表没自动创建

容器的 `lifespan` 会自动执行 `Base.metadata.create_all`。如果未生效：

```bash
docker compose exec api alembic upgrade head
```

### Q: 如何扩缩容

```bash
# 启动多个 API 副本（前面需加负载均衡）
docker compose --profile all up -d --scale api=3
```

---

## 快速参考

| 场景 | 命令 |
|------|------|
| 开发环境启动 | `make docker-up-infra` (仅 db+redis) + `make dev` (API) |
| 完整部署启动 | `make docker-build && make docker-up` |
| 生产构建 | `./scripts/docker-build.sh --version --enterprise` |
| 构建+推送 | `./scripts/docker-build.sh --version --enterprise --push` |
| 查看日志 | `make docker-logs` |
| 运行迁移 | `make docker-migrate` |
| 连接数据库 | `make docker-psql` |
| 全部清理 | `make docker-clean` |

## 构建脚本

`scripts/docker-build.sh` 是生产级构建脚本，支持：

```bash
# 构建 latest 标签
./scripts/docker-build.sh

# 使用 git tag/SHA 作为版本号
./scripts/docker-build.sh --version

# 包含企业数据源驱动（Oracle / Hive / SQL Server 等）
./scripts/docker-build.sh --enterprise

# 构建开发镜像（热重载）
./scripts/docker-build.sh --dev

# 构建 + 推送到镜像仓库
export DOCKER_REGISTRY=registry.example.com
./scripts/docker-build.sh --version --push

# 构建时清理缓存
./scripts/docker-build.sh --clean

# 完整生产构建
./scripts/docker-build.sh --version --enterprise --clean
```

Dockerfile 使用多阶段构建：

| 阶段 | 目标 | 尺寸 | 用途 |
|------|------|------|------|
| `base` | python:3.12-slim + 编译工具 | ~1.2 GB | 中间层 |
| `dependencies` | base + pip install | ~1.5 GB | 依赖缓存层 |
| `production` | 仅运行时 + 应用代码 | ~500 MB | **生产部署** |
| `development` | dependencies + 源码 | ~1.6 GB | 本地调试 |

默认构建使用 `--target production`，镜像仅包含运行时依赖和应用代码，不保留 build-essential 等编译工具。

| 资源 | 位置 |
|------|------|
| Dockerfile | `./Dockerfile` |
| Docker Compose | `./docker-compose.yml` |
| 环境变量模板 | `.env.example` |
| 企业驱动离线安装 | `docs/企业数据源驱动离线部署.md` |
| LLM 多模型配置 | `docs/LiteLLM多模型接入说明.md` |
