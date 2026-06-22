本指南将带领你从零开始搭建 Datalogue API（数语 AI 原生智能问数平台）的本地开发环境，完成首次启动，并验证服务是否正常运行。适用于首次接触该项目的开发者，预计耗时 15–20 分钟。完成本指南后，建议继续阅读 [核心概念：数据集、指标、维度与语义层治理](3-he-xin-gai-nian-shu-ju-ji-zhi-biao-wei-du-yu-yu-yi-ceng-zhi-li) 以理解平台的语义层抽象模型。

## 一、技术栈与环境要求

Datalogue API 基于 **Python 3.11** 构建，核心依赖包括 FastAPI（Web 框架）、SQLAlchemy 2.0（ORM）、LangGraph（Agent 工作流编排）和 PostgreSQL + pgvector（向量化存储）。下表汇总了开发环境的核心组件及其用途：

| 组件 | 版本要求 | 用途 |
| --- | --- | --- |
| Python | ≥ 3.11 | 运行语言 |
| PostgreSQL | 16（含 pgvector 扩展） | 主数据库 + 向量检索 |
| Docker Compose | ≥ 2.0 | 一键启动 PostgreSQL 与 Langfuse 全家桶 |
| pip / uv | 最新稳定版 | Python 包管理 |

项目使用 `pyproject.toml` 管理依赖元数据，同时维护 `requirements.txt` 供传统 pip 安装。推荐使用 `uv` 以加速依赖解析，但标准 pip 同样可用。

Sources: [pyproject.toml](pyproject.toml#L1-L41)

## 二、项目结构速览

在开始之前，先了解项目的顶层目录布局，这有助于定位关键文件：

```
datalogue-api/
├── app/
│   ├── main.py              # FastAPI 应用入口
│   ├── core/                # 配置（config.py）、数据库（database.py）、安全（security.py）、日志（logging.py）
│   ├── models/               # SQLAlchemy ORM 模型
│   ├── schemas/              # Pydantic 请求/响应校验
│   ├── api/                  # REST API 路由（数据集、数据源、对话、聊天等）
│   ├── services/             # 核心业务逻辑（LLM 配置、SubAgent、报告生成等）
│   ├── graph/                # LangGraph Agent 工作流定义
│   ├── prompts/              # 各节点的提示词模板
│   └── utils/                # 工具函数（SQL 方言、安全守卫、JSON 处理等）
├── alembic/                  # 数据库迁移脚本（含 versions/ 迁移链）
├── tests/                    # pytest 测试套件（含 fixtures/ 测试数据）
├── scripts/                  # 种子数据、离线部署等运维脚本
├── docker/                   # Docker 初始化脚本（PostgreSQL 多库初始化）
├── docs/                     # 技术说明文档
├── docker-compose.yml        # 本地开发基础设施编排
├── pyproject.toml            # 项目元数据与工具配置
├── requirements.txt          # 基础依赖清单
└── requirements-enterprise.txt # 企业数据源驱动依赖
```

Sources: [README.md](README.md#L58-L83), [app/main.py](app/main.py#L1-L61), [app/api/__init__.py](app/api/__init__.py#L1-L29)

## 三、第一步：启动 PostgreSQL 基础设施

Datalogue API 依赖 PostgreSQL 16（含 pgvector 扩展）作为主存储。项目提供 `docker-compose.yml`，一键启动数据库及可选的 Langfuse 可观测性全家桶（ClickHouse、Redis、MinIO、Langfuse Web/Worker）。

```bash
# 在项目根目录执行
docker compose up -d db
```

仅启动 `db` 服务即可满足最小开发需求。该服务默认创建了 `datalogue` 数据库，用户名和密码均为 `datalogue`，监听宿主机 `5432` 端口。如果同时需要 Langfuse 链路追踪，执行 `docker compose up -d` 启动全部服务，但首次启动会拉取多个镜像，建议在网络良好的环境下进行。

关键的默认连接信息：

| 参数 | 值 |
| --- | --- |
| 主机 | `localhost` |
| 端口 | `5432` |
| 用户 | `datalogue` |
| 密码 | `datalogue` |
| 数据库 | `datalogue` |

Sources: [docker-compose.yml](docker-compose.yml#L1-L28), [docker/postgres/init-langfuse-db.sh](docker/postgres/init-langfuse-db.sh#L1-L34)

## 四、第二步：环境变量配置

在项目根目录创建 `.env` 文件。系统通过 `pydantic-settings` 自动加载该文件，所有配置项均有合理的默认值，最小配置只需填写 LLM API Key：

```bash
# .env — 最小配置示例
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=https://api.minimaxi.com/v1
LLM_MODEL=MiniMax-M2.7
LLM_TIMEOUT_SECONDS=60
```

核心环境变量一览：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://datalogue:datalogue@localhost:5432/datalogue` | 数据库连接串 |
| `OPENAI_API_KEY` | — | LLM API Key（必填） |
| `OPENAI_BASE_URL` | `https://api.minimaxi.com/v1` | OpenAI-compatible API 端点 |
| `LLM_MODEL` | `MiniMax-M2.7` | 默认模型名 |
| `LLM_TIMEOUT_SECONDS` | `60` | LLM 调用超时（秒） |
| `SECRET_KEY` | `change-me` | JWT 签名密钥（生产环境必须更换） |
| `AES_KEY` | `your-32-byte-aes-key-here!!` | API Key 存储加密密钥（生产环境必须更换） |
| `APP_ENV` | `development` | 运行环境（development / production） |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `LOG_DIR` | `logs` | 日志持久化目录（空字符串表示仅 stdout） |
| `LANGFUSE_ENABLED` | `false` | 是否启用 Langfuse 链路追踪 |
| `LANGFUSE_BASE_URL` | `http://localhost:3000` | Langfuse 服务地址 |

数据库配置优先于环境变量兜底的 LLM 配置机制详见 [LLM 多模型配置：角色绑定、LiteLLM 适配与降级策略](25-llm-duo-mo-xing-pei-zhi-jiao-se-bang-ding-litellm-gua-pei-yu-jiang-ji-ce-lue)。

Sources: [app/core/config.py](app/core/config.py#L23-L165), [docs/LiteLLM多模型接入说明.md](docs/LiteLLM多模型接入说明.md#L56-L69)

## 五、第三步：安装 Python 依赖

基础依赖覆盖 FastAPI、SQLAlchemy、LangGraph 等核心能力，以及 MySQL、PostgreSQL、SQLite 数据源驱动：

```bash
pip install -r requirements.txt
```

如果使用 `uv`（推荐，解析速度更快）：

```bash
uv pip install -r requirements.txt
```

**企业数据源驱动**（Oracle、Hive、SQL Server、Trino、Presto、ClickHouse、BigQuery）不包含在基础依赖中。纯内网部署前，需要在有网构建机预先下载离线 wheel 包：

```bash
scripts/download_enterprise_wheels.sh ./wheelhouse
```

内网环境安装：

```bash
pip install --no-index --find-links ./wheelhouse -r requirements-enterprise.txt
```

详细的离线部署流程参见 [多数据源连接引擎：方言适配、Schema 探查与能力注册](27-duo-shu-ju-yuan-lian-jie-yin-qing-fang-yan-gua-pei-schema-tan-cha-yu-neng-li-zhu-ce)。

Sources: [requirements.txt](requirements.txt#L1-L42), [requirements-enterprise.txt](requirements-enterprise.txt), [docs/企业数据源驱动离线部署.md](docs/企业数据源驱动离线部署.md#L1-L88)

## 六、第四步：数据库迁移

Alembic 负责管理所有数据库 schema 的版本化变更。迁移脚本位于 `alembic/versions/` 目录，`alembic/env.py` 会自动从 `Settings.DATABASE_URL` 读取目标数据库连接。

```bash
# 应用所有未执行的迁移到最新版本
alembic upgrade head
```

首次执行会创建 `conversations`、`datasets`、`datasources`、`llm_model_config` 等核心表，以及 pgvector 扩展。如果数据库不存在，需先手动创建：

```bash
# 如果尚未创建 datalogue 数据库
createdb datalogue
```

迁移链中包含 30+ 个版本文件（从 `20260528_0001_init_models.py` 到 `k6l7m8n9o0p1_add_query_artifact.py`），覆盖了从初始模型建表到查询产物（QueryArtifact）、对话状态（ConversationState）等所有增量变更。详细的迁移管理流程参见 [数据库迁移管理：Alembic 版本化与模型变更流程](28-shu-ju-ku-qian-yi-guan-li-alembic-ban-ben-hua-yu-mo-xing-bian-geng-liu-cheng)。

Sources: [alembic/env.py](alembic/env.py#L1-L65), [alembic.ini](alembic.ini#L1-L27)

## 七、第五步：填充演示种子数据

项目提供了 `scripts/seed_data.py`，可为本地开发环境快速填充电商主题的演示数据，包括示例数据源、语义数据集（订单主题）、指标（GMV、订单数、客单价等）、维度（地区、品类、时间等）和对话历史：

```bash
python scripts/seed_data.py
```

该脚本依赖已运行的 PostgreSQL 和已完成的 Alembic 迁移。种子数据是验证平台端到端链路的前置条件——创建数据集后，即可在 Swagger UI 或前端页面中测试 "本月各地区 GMV 是多少？" 等典型问数请求。

Sources: [scripts/seed_data.py](scripts/seed_data.py#L1-L30)

## 八、第六步：启动 API 服务

一切就绪后，使用 Uvicorn 启动 FastAPI 应用：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

参数说明：

| 参数 | 含义 |
| --- | --- |
| `app.main:app` | 指向 `app/main.py` 中的 `app` 实例 |
| `--reload` | 开发模式热重载（代码变更时自动重启） |
| `--host 0.0.0.0` | 监听所有网络接口 |
| `--port 8000` | HTTP 监听端口 |

启动后，FastAPI 的生命周期管理器（`lifespan`）会自动执行 `Base.metadata.create_all(bind=engine)`，确保缺失的表在启动时自动创建。同时系统会初始化彩色日志输出——绿色 INFO、黄色 WARNING、红色 ERROR，SQLAlchemy 引擎日志默认关闭（设置 `SQL_LOG_LEVEL=INFO` 可查看生成的 SQL）。

Sources: [app/main.py](app/main.py#L1-L61), [app/core/logging.py](app/core/logging.py#L1-L154)

## 九、验证服务运行

### 9.1 健康检查

```bash
curl http://localhost:8000/health
# 预期响应: {"status":"ok"}
```

### 9.2 Swagger API 文档

浏览器访问 **http://localhost:8000/docs** 即可查看自动生成的 OpenAPI 交互式文档。这里列出了所有注册的 API 路由分组：

| 路由前缀 | 标签 | 核心功能 |
| --- | --- | --- |
| `/api/datasource` | 数据源 | 数据源创建、列表、连接测试 |
| `/api/dataset` | 数据集 | 数据集创建、指标/维度管理 |
| `/api/conversation` | 对话 | 对话列表、详情、归档 |
| `/api/chat` | 问数 | 流式问数（SSE）、反馈提交 |
| `/api/llm` | LLM 配置 | 模型注册、角色绑定 |
| `/api/messages` | 消息反馈 | 消息评分与修正 |
| `/api/observability` | 可观测 | 链路追踪查询 |
| `/api/internal` | 内部 SubAgent | SubAgent 进程内调用 |
| `/api/artifacts` | 查询产物 | 跨轮查询状态查询 |

启动日志也会打印每个已注册路由的完整路径。API 路由的完整端到端说明参见 [API 路由总览：数据源、数据集、对话与问数端点](4-api-lu-you-zong-lan-shu-ju-yuan-shu-ju-ji-dui-hua-yu-wen-shu-duan-dian)。

### 9.3 首次 API 调用

用 curl 测试数据集列表接口（需要先执行 `seed_data.py`）：

```bash
curl http://localhost:8000/api/dataset
# 预期返回包含种子数据的 JSON 数组
```

### 9.4 首次流式问数

```bash
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "本月GMV是多少？", "conversation_id": null}'
```

该端点返回 SSE（Server-Sent Events）事件流，实时推送 LangGraph Agent 工作流各阶段的处理结果。问数管道的完整处理链路参见 [NL2DSL2SQL 处理管道：从自然语言到结构化查询的端到端链路](5-nl2dsl2sql-chu-li-guan-dao-cong-zi-ran-yu-yan-dao-jie-gou-hua-cha-xun-de-duan-dao-duan-lian-lu)。

Sources: [app/api/__init__.py](app/api/__init__.py#L18-L29), [README.md](README.md#L91-L108)

## 十、环境搭建流程图

以下 Mermaid 流程图直观展示了从零到首次成功运行 Datalogue API 的完整路径：

```mermaid
flowchart TD
    A["docker compose up -d db<br/>启动 PostgreSQL 16 + pgvector"] --> B["创建 .env 文件<br/>配置 LLM API Key"]
    B --> C["pip install -r requirements.txt<br/>安装 Python 基础依赖"]
    C --> D{"是否需要<br/>企业数据源驱动？"}
    D -- "是" --> D1["scripts/download_enterprise_wheels.sh<br/>下载离线 wheel 包"]
    D1 --> D2["pip install -r requirements-enterprise.txt<br/>安装企业驱动"]
    D -- "否" --> E["alembic upgrade head<br/>执行数据库迁移"]
    D2 --> E
    E --> F["python scripts/seed_data.py<br/>填充演示种子数据"]
    F --> G["uvicorn app.main:app --reload<br/>启动 FastAPI 服务"]
    G --> H["curl /health → {status: ok}<br/>验证服务运行"]
    H --> I["浏览器访问 /docs<br/>查看 Swagger API 文档"]
    I --> J["curl /api/chat/stream<br/>发送首次流式问数请求"]
```

## 十一、常见问题排查

| 现象 | 可能原因 | 解决方案 |
| --- | --- | --- |
| `docker compose up` 失败 | Docker 未启动或端口 5432 被占用 | 检查 `docker ps`；释放 5432 端口或修改 `docker-compose.yml` 端口映射 |
| `alembic upgrade head` 报连接拒绝 | PostgreSQL 未就绪 | 等待 `docker compose` 健康检查通过（`datalogue-db` 状态为 `healthy`） |
| `pip install` 报 `psycopg2-binary` 编译失败 | 缺少 PostgreSQL 开发头文件 | macOS: `brew install postgresql`；Ubuntu: `apt install libpq-dev` |
| 启动后 `/health` 无响应 | 端口未监听或防火墙阻拦 | 检查 `uvicorn` 输出是否显示 `Uvicorn running on http://0.0.0.0:8000` |
| 流式问数返回空或报错 | LLM API Key 未配置或模型不可达 | 检查 `.env` 中的 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 是否正确 |
| `seed_data.py` 执行报错 | 数据库迁移未执行或 DATABASE_URL 配置错误 | 确认 `alembic upgrade head` 已成功；检查 `.env` 中 `DATABASE_URL` |
| Langfuse 服务启动后页面 502 | ClickHouse 或 MinIO 尚未就绪 | 等待约 30 秒（首次启动需创建表），刷新页面 |

## 十二、下一步阅读指引

完成环境搭建后，建议按以下路径深入理解 Datalogue 平台：

1. **[核心概念：数据集、指标、维度与语义层治理](3-he-xin-gai-nian-shu-ju-ji-zhi-biao-wei-du-yu-yu-yi-ceng-zhi-li)** —— 理解平台的核心抽象模型，这是所有问数能力的语义基础。
2. **[API 路由总览：数据源、数据集、对话与问数端点](4-api-lu-you-zong-lan-shu-ju-yuan-shu-ju-ji-dui-hua-yu-wen-shu-duan-dian)** —— 掌握后端对外暴露的完整 REST 接口体系。
3. **[NL2DSL2SQL 处理管道：从自然语言到结构化查询的端到端链路](5-nl2dsl2sql-chu-li-guan-dao-cong-zi-ran-yu-yan-dao-jie-gou-hua-cha-xun-de-duan-dao-duan-lian-lu)** —— 深入理解"用户自然语言 → DSL → SQL → 结果"的核心处理管道。
4. **[LLM 多模型配置：角色绑定、LiteLLM 适配与降级策略](25-llm-duo-mo-xing-pei-zhi-jiao-se-bang-ding-litellm-gua-pei-yu-jiang-ji-ce-lue)** —— 了解如何为不同任务角色（意图、DSL、报告等）绑定差异化模型。
5. **[数据库迁移管理：Alembic 版本化与模型变更流程](28-shu-ju-ku-qian-yi-guan-li-alembic-ban-ben-hua-yu-mo-xing-bian-geng-liu-cheng)** —— 掌握项目模型变更的标准操作流程。