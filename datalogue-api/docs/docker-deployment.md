# Datalogue Docker 部署指南

本文以仓库根目录 `docker-compose.yml` 为业务部署入口。PostgreSQL 只在根 Compose 定义；根 Compose 通过 `include` 聚合 `datalogue-api/docker-compose.yml` 中与后端版本强绑定的数据库迁移服务。Redis、API、Web 和 Nginx 仍由根 Compose 编排；Phoenix 使用独立的 `docker-compose.phoenix.yml`，不会影响业务栈启动。

## 部署结构

```text
浏览器
  │ HTTPS ${WEB_PORT:-3000}
  ▼
Nginx
  ├── /        → Web:3000
  ├── /api/*   → API:8000
  └── /agentscope/* → 404（AgentScope 原始服务仅供容器内调用）

PostgreSQL healthy
  ▼
Migration: alembic upgrade head
  ▼
API healthy → Web → Nginx
```

API 的 8000 端口不发布到宿主机，只允许 Nginx 和 Docker 内网服务访问。数据库迁移是 API 的启动闸门：迁移失败时 API、Web、Nginx 不会继续启动。

## 前置条件

- Docker Engine 24+
- Docker Compose v2.20+，需支持 `include` 与 `service_completed_successfully`
- 建议至少 4 核 CPU、8 GB 内存和 50 GB 可用磁盘

## 首次部署

在仓库根目录执行：

```bash
cp .env.example .env
```

编辑 `.env`，至少替换以下值：

```dotenv
DB_PASSWORD=<数据库强密码>
SECRET_KEY=<随机 JWT 密钥>
AES_KEY=<32 字节 AES 密钥>
APP_ENV=production
WEB_PORT=3000
NGINX_TLS_HOSTS=localhost,127.0.0.1,<部署机 IP 或域名>
```

构建并启动业务栈：

```bash
docker compose up -d --build
```

启动顺序由 Compose 自动控制：

1. PostgreSQL、Redis 通过健康检查。
2. `migration` 执行 `alembic upgrade head` 并正常退出。
3. API 启动并通过健康检查。
4. Web 和 Nginx 启动。

## 验证部署

```bash
# 查看所有服务及一次性迁移容器
docker compose ps -a

# migration 预期为 Exited (0)
docker compose logs migration

# API 仅在容器内验证，不从宿主机暴露 8000
docker compose exec api python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"

# Nginx HTTPS 入口
curl -k https://localhost:${WEB_PORT:-3000}/healthz
```

浏览器访问：

```text
https://<部署机地址>:${WEB_PORT:-3000}
```

首次使用自签证书时，浏览器会提示证书不受信任。正式生产环境应挂载受信任 CA 签发的证书。

## 单独运行迁移

部署流程会自动执行迁移。如需手动补跑：

```bash
docker compose run --rm migration
```

查看当前迁移版本：

```bash
docker compose run --rm migration alembic current
```

迁移会修改数据库结构，生产执行前必须完成 PostgreSQL 备份。

## 本地开发基础设施

PostgreSQL 只在根 Compose 定义。即使开发后端位于 `datalogue-api/`，也应从仓库根目录启动基础设施：

```bash
docker compose up -d db redis
```

也可以在 `datalogue-api/` 目录执行：

```bash
make docker-up-infra
```

该 Makefile 命令同样调用根 Compose，不会创建第二套数据卷。

## Phoenix 独立部署

Phoenix 不属于业务栈。先确保根 Compose 已创建 PostgreSQL 和共享网络：

```bash
docker compose up -d db
docker compose -f docker-compose.phoenix.yml up -d
```

Phoenix 默认仅绑定宿主机回环地址：

- UI：`127.0.0.1:${PHOENIX_PORT:-8065}`
- OTLP gRPC：`127.0.0.1:${PHOENIX_OTLP_PORT:-4317}`

远程访问 UI 时使用 SSH 隧道：

```bash
ssh -N -L 8065:127.0.0.1:8065 <部署用户>@<部署机地址>
```

停止 Phoenix 不会停止业务栈：

```bash
docker compose -f docker-compose.phoenix.yml down
```

详细初始化与验收步骤见根目录 `docs/Phoenix开发观测部署与验收.md`。

## 日常运维

```bash
# 查看状态
docker compose ps -a

# 查看业务日志
docker compose logs -f api nginx

# 重建并升级
docker compose up -d --build

# 停止业务容器，保留数据卷
docker compose down
```

### PostgreSQL 备份

```bash
docker compose exec -T db pg_dump -U datalogue -Fc datalogue > datalogue.dump
```

恢复前先停止 API，并在独立环境验证备份文件可恢复。

## 故障排查

### API 未启动

先检查迁移：

```bash
docker compose ps -a migration
docker compose logs migration
```

如果迁移退出码不是 0，修复迁移或数据库连接问题后重新执行：

```bash
docker compose run --rm migration
docker compose up -d api web nginx
```

### Phoenix 提示网络不存在

独立 Phoenix Compose 依赖根业务栈创建的共享网络。先执行：

```bash
docker compose up -d db
docker compose -f docker-compose.phoenix.yml up -d
```

### 无法从宿主机访问 8000

这是预期安全边界。API 不再发布宿主机端口，业务访问统一经过 Nginx 的 HTTPS 入口；本地调试后端时应直接运行 Uvicorn，而不是修改生产 Compose。

## 数据卷

| 数据卷 | 用途 | 是否必须备份 |
| --- | --- | --- |
| `datalogue_pgdata` | 业务数据库及 Phoenix Schema | 必须 |
| `datalogue_redisdata` | Redis AOF | 按恢复目标决定 |
| `datalogue_workspaces` | AgentScope 临时工作区 | 按业务要求决定 |
| `datalogue_api_logs` | API 文件日志 | 建议按审计要求保留 |
| `datalogue_nginx_certs` | Nginx TLS 证书 | 使用自有证书时必须 |

禁止在未备份的情况下执行 `docker compose down -v`。
