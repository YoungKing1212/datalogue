本文档详解 Datalogue 本地开发环境中 Docker Compose 编排的完整服务栈：从共享 PostgreSQL 实例的双库初始化策略，到 Langfuse 全家桶（Worker + Web + ClickHouse + MinIO + Redis）的拓扑关系，再到应用层如何通过配置和可观测性 SDK 接入这套基础设施。阅读本文前，建议先了解 [核心概念](3-he-xin-gai-nian-shu-ju-ji-zhi-biao-wei-du-yu-yu-yi-ceng-zhi-li) 和 [快速开始](2-kuai-su-kai-shi-huan-jing-da-jian-yu-shou-ci-yun-xing) 中对数据库角色的基本认知。

Sources: [docker-compose.yml](docker-compose.yml#L1-L154)

## 服务拓扑总览

`docker-compose.yml` 共编排 6 个容器化服务，以一张共享 PostgreSQL 实例为圆心，向外辐射到 Langfuse 的完整可观测性链路。这种"一库双库"设计（单个 PostgreSQL 容器承载 `datalogue` 和 `langfuse` 两个逻辑数据库）旨在降低本地开发的资源占用与启动复杂度，同时保持业务数据与观测数据在物理层面的隔离。

```mermaid
graph TB
    subgraph "Docker Compose 服务栈"
        DB[("PostgreSQL + pgvector<br/>容器: datalogue-db<br/>端口: 5432<br/>库: datalogue + langfuse")]
        CH[("ClickHouse<br/>容器: datalogue-langfuse-clickhouse<br/>端口: 8123 / 9000")]
        REDIS[("Redis 7<br/>容器: datalogue-langfuse-redis<br/>端口: 6380→6379")]
        MINIO[("MinIO<br/>容器: datalogue-langfuse-minio<br/>端口: 9090 / 9091")]
        WORKER["Langfuse Worker<br/>容器: datalogue-langfuse-worker"]
        WEB["Langfuse Web<br/>容器: datalogue-langfuse-web<br/>端口: 3000"]
    end

    subgraph "应用层"
        API["Datalogue FastAPI<br/>uvicorn :8000"]
        SEED["seed_langfuse_prompts.py"]
    end

    DB -->|读写 datalogue 库| API
    WEB -->|postgresql://langfuse@db/langfuse| DB
    WEB -->|事件/媒体存储| MINIO
    WEB -->|缓存/队列| REDIS
    WEB -->|分析数据| CH
    WORKER -->|同 WEB 配置| DB
    WORKER -->|同 WEB 配置| CH
    WORKER -->|同 WEB 配置| REDIS
    WORKER -->|同 WEB 配置| MINIO
    API -->|LANGFUSE_BASE_URL :3000| WEB
    SEED -->|Langfuse SDK 写入 Prompt| WEB
```

Sources: [docker-compose.yml](docker-compose.yml#L1-L154)

每个服务的启动依赖关系通过 `depends_on` + `condition: service_healthy` 构成严格的启动链：PostgreSQL → (ClickHouse, Redis, MinIO) → (Worker, Web)。这意味着直到 PostgreSQL 的 `pg_isready` 通过、ClickHouse 的 `/ping` 端点响应、Redis 的 `PING` 返回 `PONG`、MinIO 的 `mc ready` 就绪后，Langfuse 的核心服务才会启动。这套健康检查链保证了首次 `docker compose up` 时不会出现"数据库未就绪导致应用启动失败"的竞态问题。

Sources: [docker-compose.yml](docker-compose.yml#L12-L17) [docker-compose.yml](docker-compose.yml#L90-L97) [docker-compose.yml](docker-compose.yml#L140-L145)

## PostgreSQL：共享实例与双库策略

本地开发中，Datalogue 应用自身和 Langfuse 共享同一个 PostgreSQL 容器（`pgvector/pgvector:pg16`），但通过 init 脚本在逻辑层隔离为两个独立数据库。选择 `pgvector` 镜像而非标准 `postgres` 是因为 Datalogue 需要向量检索能力支撑语义资产召回，这在 [候选资产召回](16-hou-xuan-zi-chan-zhao-hui-duo-lei-xing-yu-yi-zi-chan-de-tong-jian-suo-yu-zhi-xin-du-pai-xu) 中有详细说明。

| 配置项 | 值 | 说明 |
|---|---|---|
| 镜像 | `pgvector/pgvector:pg16` | PostgreSQL 16 + pgvector 扩展 |
| 主用户 | `datalogue` / `datalogue` | Datalogue 应用数据库的所有者 |
| 主数据库 | `datalogue` | 存储业务模型、会话、数据集等 |
| Langfuse 用户 | `langfuse` / `langfuse`（可通过环境变量覆盖） | Langfuse 独立角色，权限隔离 |
| Langfuse 数据库 | `langfuse`（可通过环境变量覆盖） | Langfuse 元数据（用户、项目、Prompt 等） |
| 端口映射 | `5432:5432` | 宿主机可直接 psql 连接 |
| 数据卷 | `datalogue_pgdata` | 持久化数据，重建容器不丢失 |

Sources: [docker-compose.yml](docker-compose.yml#L3-L18)

### 初始化脚本：init-langfuse-db.sh

该脚本位于 `docker/postgres/init-langfuse-db.sh`，挂载到容器的 `/docker-entrypoint-initdb.d/20-init-langfuse-db.sh`。PostgreSQL 官方镜像的 entrypoint 会在首次初始化数据目录时，按字母序执行该目录下的 `.sh` 和 `.sql` 文件。脚本执行以下逻辑：

1. **检查角色是否存在**：查询 `pg_roles` 中是否已有 `langfuse` 角色。若不存在则 `CREATE ROLE ... LOGIN PASSWORD`；若已存在则 `ALTER ROLE` 更新密码。这保证了重复 `docker compose down -v && docker compose up` 时脚本依然幂等。
2. **检查数据库是否存在**：查询 `pg_database` 中是否已有 `langfuse` 库。若不存在则 `CREATE DATABASE ... OWNER langfuse`。

脚本中的用户名、密码、数据库名均通过环境变量注入，默认值在 `docker-compose.yml` 中以 `${LANGFUSE_POSTGRES_USER:-langfuse}` 语法定义。这意味着运维人员可以通过 `.env` 文件覆盖这些值，无需修改 Compose 文件或脚本本身。

Sources: [docker/postgres/init-langfuse-db.sh](docker/postgres/init-langfuse-db.sh#L1-L34)

关键实现细节：脚本通过 `psql` 的 `-v` 参数将 shell 变量传递给 SQL，并使用 `:'varname'` 语法在 SQL 中安全引用——这比字符串拼接更安全，避免了 SQL 注入风险。

Sources: [docker/postgres/init-langfuse-db.sh](docker/postgres/init-langfuse-db.sh#L18-L33)

## Langfuse 全家桶：五服务协同

Langfuse v3 的本地部署依赖五个服务协同工作，Datalogue 的 Compose 文件完整覆盖了全部组件：

### Langfuse Web（`datalogue-langfuse-web`）

面向用户的 Langfuse 管理界面，映射宿主机端口 `3000`。启动后可通过 `http://localhost:3000` 访问，首次登录需注册管理员账号。Web 服务依赖 `db`、`langfuse-clickhouse`、`langfuse-redis`、`langfuse-minio` 的健康检查全部通过后才启动。

Sources: [docker-compose.yml](docker-compose.yml#L70-L80)

### Langfuse Worker（`datalogue-langfuse-worker`）

后台异步任务处理器，负责将 trace 事件从队列中消费并持久化到 ClickHouse。与 Web 共享完全相同的 `&langfuse-env` 环境变量集合（通过 YAML anchor 复用），但不暴露任何端口。

Sources: [docker-compose.yml](docker-compose.yml#L22-L68)

### ClickHouse（`datalogue-langfuse-clickhouse`）

Langfuse 的 OLAP 分析引擎，存储 trace、span、generation 和 score 等观测数据。端口映射 `8123`（HTTP）和 `9000`（Native Protocol）均绑定 `127.0.0.1`，仅允许本机访问，防止开发环境中 ClickHouse 被外部误连。

Sources: [docker-compose.yml](docker-compose.yml#L82-L98)

### MinIO（`datalogue-langfuse-minio`）

S3 兼容对象存储，Langfuse 用其存储 trace 事件文件（`events/` 前缀）、媒体附件（`media/` 前缀）和批量导出文件（`exports/` 前缀）。宿主机映射 `9090:9000`（S3 API）和 `9091:9001`（Web Console，仅绑定 `127.0.0.1`）。

Sources: [docker-compose.yml](docker-compose.yml#L100-L120)

### Redis（`datalogue-langfuse-redis`）

Langfuse 的缓存和队列中间件，映射宿主机端口 `6380`（避免与本地 Redis 默认端口 6379 冲突），同样仅绑定 `127.0.0.1`。启动时通过命令行注入密码认证。

Sources: [docker-compose.yml](docker-compose.yml#L122-L145)

### 环境变量复用机制

Langfuse Worker 和 Web 共享一套环境变量，Compose 文件中通过 YAML anchor（`&langfuse-env`）定义一次、两处引用（`<<: *langfuse-env`），DRY 原则下避免了配置漂移。核心变量如下：

| 环境变量 | 默认值 | 作用 |
|---|---|---|
| `NEXTAUTH_URL` | `http://localhost:3000` | Langfuse Web 自身地址 |
| `DATABASE_URL` | `postgresql://langfuse:langfuse@db:5432/langfuse` | 元数据库连接 |
| `SALT` / `ENCRYPTION_KEY` | 开发固定值 | 会话加密，生产环境必须更换 |
| `CLICKHOUSE_URL` | `http://langfuse-clickhouse:8123` | ClickHouse HTTP 接口 |
| `REDIS_HOST` / `REDIS_PORT` | `langfuse-redis:6379` | Redis 队列连接 |
| `LANGFUSE_S3_*` | 指向 `langfuse-minio:9000` | 事件和媒体的 S3 兼容存储 |

Sources: [docker-compose.yml](docker-compose.yml#L28-L68)

## 应用层接入：从配置到追踪

Datalogue 应用通过 `app/core/config.py` 中的 `Settings` 类统一管理所有环境变量，并在 `app/core/database.py` 中建立 SQLAlchemy 引擎。默认连接串 `postgresql://datalogue:datalogue@localhost:5432/datalogue` 直接指向 Compose 暴露的 PostgreSQL 端口。

### Langfuse 可观测性配置

应用层通过以下环境变量控制 Langfuse 集成行为：

| 配置字段 | 默认值 | 说明 |
|---|---|---|
| `LANGFUSE_ENABLED` | `False` | 总开关，关闭时所有观测调用降级为 no-op |
| `LANGFUSE_BASE_URL` | `http://localhost:3000` | 指向 Langfuse Web 容器 |
| `LANGFUSE_PROJECT_ID` | `None` | 需在 Langfuse Web 中创建项目后填入 |
| `LANGFUSE_PUBLIC_KEY` | `None` | Langfuse 项目 API Key（公钥） |
| `LANGFUSE_SECRET_KEY` | `None` | Langfuse 项目 API Key（私钥） |
| `LANGFUSE_ENVIRONMENT` | `dev` | 环境标签，区分 dev/staging/prod |
| `LANGFUSE_PROMPT_LABEL` | `production` | Prompt 拉取标签 |
| `LANGFUSE_SAMPLE_RATE` | `1.0` | 采样率，1.0 = 全量上报 |

Sources: [app/core/config.py](app/core/config.py#L44-L56)

### 追踪链路与降级机制

`DatalogueTracer`（位于 `app/services/observability/tracer.py`）是 Langfuse SDK v4 的统一封装层，对外暴露 `create_trace_context`、`start_span`、`end_span`、`record_generation` 等接口。当 `LANGFUSE_ENABLED=False` 或 Langfuse 服务不可达时，所有调用自动降级为 no-op——`create_trace_context` 返回一个 `active=False` 的上下文对象，后续 span 和 generation 记录全部跳过，不会抛出异常。

降级层还包含一个轻量熔断器 `LangfuseHealthCheck`（位于 `app/services/observability/fallback.py`），阈值设为连续 10 次失败后进入 300 秒冷却期。在此期间所有观测请求被直接短路，避免持续重试耗尽连接池资源。这种"可观测性不影响主链路"的设计原则贯彻始终——即使整个 Langfuse 栈宕机，Datalogue 的问数功能依然正常工作。

Sources: [app/services/observability/tracer.py](app/services/observability/tracer.py#L109-L129) [app/services/observability/fallback.py](app/services/observability/fallback.py#L36-L61)

### Prompt 管理：Langfuse 与本地兜底

Datalogue 支持从 Langfuse Prompt Manager 拉取运行时 Prompt 模板，这是通过 `PromptManager`（位于 `app/services/observability/prompts.py`）实现的。其核心策略是：优先从 Langfuse 远程拉取指定 `label` 的 Prompt 版本，失败时自动回退到本地硬编码的 `fallback` 模板，并对两种来源都记录版本信息到观测上下文中。

本地 Prompt 模板注册在 `app/services/observability/prompt_registry.py` 的 `get_registered_prompts()` 函数中，当前共注册 13 条 Prompt，覆盖意图识别、DSL 生成、报告生成、SQL 审计、LeadAgent 规划和字段标注等全部工作流节点。

`scripts/seed_langfuse_prompts.py` 是 Prompt 种子脚本，将 `get_registered_prompts()` 的完整清单批量写入 Langfuse Prompt Manager。支持 `--apply` 实际写入和 dry-run 预览两种模式，并可通过 `--label` 指定目标标签（默认读取 `LANGFUSE_PROMPT_LABEL`）。

Sources: [app/services/observability/prompts.py](app/services/observability/prompts.py#L52-L88) [app/services/observability/prompt_registry.py](app/services/observability/prompt_registry.py#L92-L200) [scripts/seed_langfuse_prompts.py](scripts/seed_langfuse_prompts.py#L1-L127)

### 本地观测索引表

Datalogue 在业务数据库中维护了 `observability_trace_index` 和 `trace_annotation_candidate` 两张本地表（由 Alembic 迁移 `f1a2b3c4d5e6_add_observability_tables.py` 创建），作为 Langfuse 远端数据的本地索引和标注候选池。前者将 Langfuse trace ID 与本地 conversation、message、dataset 关联，后者收集用户点踩、执行失败和低质量 trace 待人工审核。

通过 `/api/observability/summary`、`/api/observability/costs`、`/api/observability/traces/{trace_id}` 等端点，可以无需直接访问 Langfuse Web 界面即可查看 trace 摘要、token 成本和执行状态。

Sources: [alembic/versions/f1a2b3c4d5e6_add_observability_tables.py](alembic/versions/f1a2b3c4d5e6_add_observability_tables.py#L1-L120) [app/api/observability.py](app/api/observability.py#L1-L97)

## 启动与验证流程

### 首次启动

```bash
# 1. 启动全部服务（首次执行会拉取镜像，约需 2-5 分钟）
docker compose up -d

# 2. 等待所有健康检查通过
docker compose ps
# 预期：全部 STATUS 为 "healthy" 或 "running"

# 3. 运行数据库迁移（在 Python 虚拟环境中）
alembic upgrade head

# 4. 初始化 Langfuse Prompt（需先在 http://localhost:3000 创建项目并获取 API Key）
python scripts/seed_langfuse_prompts.py --apply

# 5. 启动 Datalogue API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Sources: [README.md](README.md#L20-L56) [docker-compose.yml](docker-compose.yml#L1-L154)

### 关键验证检查

| 验证项 | 命令/地址 | 预期结果 |
|---|---|---|
| PostgreSQL 连通性 | `psql -h localhost -U datalogue -d datalogue` | 成功进入 psql |
| Langfuse 数据库存在 | `psql -h localhost -U datalogue -d datalogue -c "\l"` | 列表中含 `langfuse` |
| Langfuse Web 可访问 | `http://localhost:3000` | 显示注册/登录页面 |
| MinIO Console | `http://localhost:9091` | 显示 MinIO 管理界面 |
| ClickHouse 健康 | `curl http://localhost:8123/ping` | 返回 `Ok.` |
| Redis 连通 | `redis-cli -h 127.0.0.1 -p 6380 -a myredissecret PING` | 返回 `PONG` |

### 故障排查

| 症状 | 可能原因 | 解决方式 |
|---|---|---|
| `langfuse-web` 反复重启 | Langfuse 数据库不存在 | 检查 init 脚本是否正确执行：`docker compose logs db \| grep init` |
| ClickHouse 启动失败 | 宿主机 ClickHouse 端口冲突 | ClickHouse 仅绑定 `127.0.0.1`，检查本地是否运行了其他 ClickHouse |
| Langfuse 连接 PostgreSQL 失败 | `langfuse` 角色密码不匹配 | `docker compose down -v && docker compose up -d` 重建卷和数据库 |
| Alembic 迁移报连接错误 | PostgreSQL 未就绪或 DATABASE_URL 未配置 | 确认 `docker compose ps db` 状态为 healthy，检查 `.env` 中的 `DATABASE_URL` |

## 技术栈版本与依赖

Datalogue 应用层通过 `pyproject.toml` 声明了以下与 Docker Compose 栈直接相关的依赖：

| 依赖 | 版本 | 用途 |
|---|---|---|
| `sqlalchemy` | 2.0.30 | ORM，连接 PostgreSQL |
| `alembic` | 1.13.1 | 数据库迁移管理 |
| `psycopg2-binary` | 2.9.9 | PostgreSQL 驱动 |
| `pgvector` | 0.2.5 | 向量检索（需 pgvector 扩展） |
| `langfuse` | >=4,<5 | Langfuse Python SDK v4 |
| `langgraph` | 0.0.65 | Agent 工作流引擎 |

Sources: [pyproject.toml](pyproject.toml#L1-L30)

数据持久化方面，Compose 文件定义了四个命名卷——`datalogue_pgdata`（PostgreSQL 数据）、`langfuse_clickhouse_data`、`langfuse_clickhouse_logs`、`langfuse_minio_data`——确保 `docker compose down` 不会丢失数据。执行 `docker compose down -v` 才会彻底清理所有持久化数据，适合需要从头重建的调试场景。

Sources: [docker-compose.yml](docker-compose.yml#L147-L154)

## 阅读指引

本文档位于"数据源与部署运维"章节，建立了开发环境基础设施的全貌。接下来建议按以下路径深入：

- **[数据库迁移管理](28-shu-ju-ku-qian-yi-guan-li-alembic-ban-ben-hua-yu-mo-xing-bian-geng-liu-cheng)** — 了解 Alembic 版本化迁移的完整流程和模型变更规范
- **[Langfuse 追踪集成](24-langfuse-zhui-zong-ji-cheng-trace-span-generation-yu-prompt-guan-li)** — 深入 Trace、Span、Generation 的上报机制与 Scoring 反馈闭环
- **[Prompt 系统](26-prompt-xi-tong-ge-jie-dian-de-ti-shi-ci-mo-ban-yu-langfuse-prompt-guan-li)** — 各节点的 Prompt 模板设计与 Langfuse Prompt Manager 的运维实践
- **[LLM 多模型配置](25-llm-duo-mo-xing-pei-zhi-jiao-se-bang-ding-litellm-gua-pei-yu-jiang-ji-ce-lue)** — 角色绑定、LiteLLM 适配与 Provider 降级策略