# Datalogue API — 数语 AI 原生智能问数平台

**Datalogue**（数语）是一个基于 AgentScope Agent Team 架构的 AI 原生智能问数平台，支持自然语言查询、多数据源接入、语义数据集治理，以及可审计的自动查询执行链路。

## 架构概览

```
用户 / 前端 (SSE)
       │
       ▼
┌─────────────────────────────┐
│       FastAPI (端口 8000)     │
│  ┌───────────────────────┐  │
│  │  /api/* 业务路由        │  │
│  │  数据源 / 数据集 / 对话   │  │
│  │  LLM 配置 / 工作台       │  │
│  └──────────┬────────────┘  │
│             │               │
│  ┌──────────▼────────────┐  │
│  │  AgentScope Service   │  │
│  │  (/agentscope/*)       │  │
│  │                        │  │
│  │  ┌──── Agent Team ──┐ │  │
│  │  │   LeadAgent       │ │  │
│  │  │   ├ BI Worker     │ │  │
│  │  │   ├ Report Worker │ │  │
│  │  │   ├ Python Worker │ │  │
│  │  │   └ Audit Worker  │ │  │
│  │  └──────────────────┘ │  │
│  └────────────────────────┘  │
└─────────────────────────────┘
               │
     ┌─────────┼─────────┐
     ▼         ▼         ▼
  PostgreSQL   Redis   数据源(MySQL/
  (+pgvector)           Oracle/…)
```

## 核心技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| **Web 框架** | FastAPI 0.111 + Uvicorn | ASGI 服务，SSE 流式响应 |
| **ORM** | SQLAlchemy 2.0 + Alembic | 数据库迁移与操作 |
| **数据库** | PostgreSQL 16 + pgvector | 主存储 + 向量搜索 |
| **缓存/消息** | Redis 7 | AgentScope Storage & MessageBus |
| **AI Agent 框架** | AgentScope 2.0.3 (Service) | Agent Team 编排引擎 |
| **LLM 接入** | OpenAI-compatible / LiteLLM Proxy | 多模型、多供应商 |
| **数据源驱动** | MySQL / PostgreSQL / Oracle / Hive / SQL Server / Trino / ClickHouse / BigQuery | 企业级多源接入 |
| **安全** | SQL Guard / Payload Sanitizer / RBAC 工具白名单 | 防泄露、防注入 |
| **测试** | pytest + pytest-asyncio | 异步测试支持 |
| **代码质量** | Black + Ruff + MyPy | 格式、lint、类型检查 |

## 快速开始

### 前置条件

- Python 3.11+
- PostgreSQL 16+（含 pgvector 扩展）
- Redis 7+

### 1. 克隆并配置

```bash
git clone <repo-url> datalogue-api
cd datalogue-api

# 复制环境变量模板
cp .env.example .env

# 编辑 .env — 至少修改 DATABASE_URL 和 OPENAI_API_KEY
```

### 2. 安装依赖

```bash
# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate

# 安装核心依赖
pip install -r requirements.txt

# 企业数据源驱动（可选）
pip install -r requirements-enterprise.txt
```

### 3. 初始化数据库

```bash
# 创建数据库
createdb datalogue

# 运行迁移
alembic upgrade head
```

### 4. 启动服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 [http://localhost:8000/docs](http://localhost:8000/docs) 查看 Swagger API 文档。

## 目录结构

```
datalogue-api/
├── app/                          # 应用主代码
│   ├── main.py                   # FastAPI 入口 + 生命周期
│   ├── __init__.py
│   │
│   ├── core/                     # 基础设施层
│   │   ├── config.py             # 环境变量配置（Pydantic Settings）
│   │   ├── database.py           # SQLAlchemy engine & session
│   │   ├── logging.py            # 日志配置（彩色输出 + 文件轮转）
│   │   └── security.py           # JWT / AES 加密
│   │
│   ├── models/                   # SQLAlchemy ORM 模型
│   │   ├── dataset.py            # 语义数据集、指标、维度、蓝图、Manifest
│   │   ├── datasource.py         # 数据源配置
│   │   ├── conversation.py       # 对话历史
│   │   ├── llm.py                # LLM 模型配置
│   │   ├── agent_team_task.py    # Agent Team 任务记录
│   │   ├── bi_agent.py           # BI Agent 模型
│   │   ├── agentscope_workbench.py # AgentScope 工作台
│   │   └── base.py               # 基类（时间戳混入）
│   │
│   ├── schemas/                  # Pydantic 校验 & 序列化
│   │   ├── dataset.py
│   │   ├── datasource.py
│   │   ├── conversation.py
│   │   ├── chat.py
│   │   ├── llm.py
│   │   ├── bi_agent.py
│   │   ├── bi_workbench.py
│   │   ├── capability_manifest.py
│   │   └── repair_plan.py
│   │
│   ├── api/                      # API 路由
│   │   ├── datasource.py         # 数据源 CRUD
│   │   ├── dataset.py            # 数据集治理
│   │   ├── conversation.py       # 对话历史
│   │   ├── messages.py           # 消息接口
│   │   ├── chat.py               # 流式问数 (SSE)
│   │   ├── llm.py                # LLM 模型配置
│   │   ├── workbench.py          # 治理工作台
│   │   ├── artifacts.py          # 查询产物
│   │   ├── agent_team.py         # Agent Team 任务
│   │   └── agentscope_control_plane.py  # AgentScope 控制面
│   │
│   ├── services/                 # 业务逻辑层
│   │   ├── datasource.py         # 数据源连接与同步
│   │   ├── dataset_manifest.py   # Manifest 治理 & 权限
│   │   ├── capability_manifest.py # 能力清单（LeadAgent 路由）
│   │   ├── sql_preview.py        # SQL 预览
│   │   ├── sql_dialect_adapter.py # 方言适配
│   │   └── repair_plan.py        # 修复计划
│   │
│   ├── agentscope_service/       # AgentScope 子应用集成
│   │   ├── __init__.py           # factory 入口
│   │   ├── app_factory.py        # 创建嵌入的 AgentScope 子应用
│   │   ├── registry.py           # Worker 模板注册表 & 权限配置
│   │   ├── tools.py              # Datalogue Dataset 工具（7 个）
│   │   ├── bi_worker_runtime.py  # BI Worker 查询运行时
│   │   ├── bi_worker_contracts.py # 查询计划契约模型
│   │   ├── bi_worker_context.py  # BI Worker 上下文提供者
│   │   ├── bi_worker_validator.py # 渐进式上下文校验
│   │   ├── bi_worker_timeline_cache.py # 时间线缓存
│   │   ├── task_context.py       # 任务上下文
│   │   ├── progress_bridge.py    # SSE 事件发布
│   │   ├── projection.py         # 输入投影
│   │   ├── runner.py             # 任务运行器
│   │   ├── dataset_query_executor.py # 数据集查询执行器
│   │   ├── client.py             # AgentScope Service 客户端
│   │   ├── credentials.py        # 凭证管理
│   │   ├── worker_logging.py     # Worker 日志
│   │   ├── otel_setup.py         # OpenTelemetry 追踪
│   │   └── team_templates.py     # Worker 模板聚合导出
│   │
│   ├── agents/                   # 业务 Agent 实现
│   │   ├── bi_agent/             # BI Agent（本地 handoff）
│   │   │   ├── capabilities.py
│   │   │   ├── dataset_agent_factory.py
│   │   │   ├── handoff_service.py
│   │   │   ├── handoff_port.py
│   │   │   ├── native_handoff.py
│   │   │   ├── run_service.py
│   │   │   ├── runtime_context.py
│   │   │   ├── confirmation_service.py
│   │   │   └── handoff_events.py
│   │   └── agentscope_model.py
│   │
│   ├── bi/                       # BI 引擎
│   │   ├── skill/
│   │   │   └── runtime_bridge.py # 蓝图运行时桥接
│   │   ├── toolchain/            # 查询工具链
│   │   └── toolkit/
│   │       └── atomic.py         # 原子查询工具
│   │
│   ├── prompts/                  # Agent 提示词模板
│   │   └── agent_team.py         # LeadAgent & Worker Prompts
│   │
│   ├── graph/                    # 遗留 LangGraph 模块
│   │   └── llm.py                # LLM 工具函数
│   │
│   ├── safety/                   # 安全
│   │   └── payload_sanitizer.py  # 输出脱敏
│   │
│   ├── middlewares/              # FastAPI 中间件
│   │   ├── lifecycle.py          # 生命周期管理
│   │   ├── dataset_tool_logging.py
│   │   └── safe_log_summary.py
│   │
│   ├── contracts/                # 契约定义
│   ├── events/                   # 事件定义
│   ├── runtime/                  # 运行时
│   │   ├── agent_team_runtime.py
│   │   └── thread_resolver.py
│   │
│   └── utils/                    # 工具函数
│       ├── sql_guard.py          # SQL 安全防护
│       ├── sql_diagnosis.py      # SQL 错误诊断
│       ├── sql_dialect.py        # 方言处理
│       ├── json_utils.py
│       ├── column_labels.py
│       ├── schema_formatter.py
│       ├── think.py
│       ├── token.py
│       ├── sample_data.py
│       ├── query_constraints.py
│       └── compiler_context.py
│
├── conf/                         # 外部 JSON 配置文件
│   └── bi_worker_permissions.json # BI Worker 工具权限白名单
│
├── alembic/                      # 数据库迁移
│   ├── env.py
│   └── versions/                 # 迁移版本文件
│
├── tests/                        # 测试（pytest）
│   ├── conftest.py
│   ├── test_dataset.py
│   ├── test_datasource.py
│   ├── test_security.py
│   ├── test_agentscope_service_tools.py
│   ├── test_agentscope_static_agent_registry.py
│   ├── test_bi_worker_progressive_context_*.py
│   └── ... (60+ 测试文件)
│
├── scripts/                      # 运维脚本
│   ├── seed_data.py              # 初始数据种子
│   └── capture_phase3_fixtures.py
│
├── docs/                         # 设计文档
├── docker-compose.yml            # Docker 编排（Postgres + Redis）
├── Dockerfile                    # API 容器镜像
├── .env.example                  # 环境变量模板
├── pyproject.toml                # 项目元数据 & 工具配置
└── requirements.txt              # Python 依赖锁定
```

## API 路由概览

### 数据治理（/api/*）

| 方法 | 路径 | 功能 |
|------|------|------|
| GET/POST | `/api/datasource` | 数据源列表 / 创建 |
| GET/PUT/DELETE | `/api/datasource/{id}` | 数据源详情 / 更新 / 删除 |
| GET | `/api/datasource/{id}/tables` | 拉取数据源表结构 |
| POST | `/api/dataset` | 创建语义数据集 |
| GET | `/api/dataset` | 数据集列表 |
| GET/PUT/DELETE | `/api/dataset/{id}` | 数据集详情 / 更新 / 删除 |
| POST | `/api/dataset/{id}/metric` | 添加指标 |
| POST | `/api/dataset/{id}/dimension` | 添加维度 |
| POST | `/api/dataset/{id}/blueprint` | 添加分析蓝图 |
| GET | `/api/dataset/{id}/manifest` | 查看 Manifest |
| POST | `/api/dataset/{id}/manifest/draft` | 保存 Manifest 草稿 |
| POST | `/api/dataset/{id}/manifest/publish` | 发布 Manifest |

### 对话与问数（/api/*）

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/conversation` | 对话列表 |
| GET | `/api/conversation/{id}` | 对话详情（含消息） |
| POST | `/api/chat/stream` | 流式问数 (SSE / Server-Sent Events) |
| POST | `/api/chat/feedback` | 用户反馈 |

### AgentScope 控制面（/api/*）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/agent-team/task` | 提交 Agent Team 任务 |
| GET | `/api/agent-team/task/{id}` | 查询任务状态 |
| POST | `/api/agent-team/task/{id}/retry` | 重试失败任务 |

### AgentScope Service（/agentscope/*）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/agentscope/agent` | 创建 Agent 实例 |
| POST | `/agentscope/session` | 创建会话 |
| POST | `/agentscope/session/{id}/message` | 发送消息 |
| GET | `/agentscope/session/{id}/stream` | 流式响应 (SSE) |

## Agent Team 体系

Datalogue 使用 AgentScope Agent Team 架构编排智能问数流程：

```
                    ┌─────────────────┐
                    │   LeadAgent      │ ← 路由、规划、协调
                    │  (Datalogue      │
                    │   Agent Team     │
                    │   Leader)        │
                    └────────┬────────┘
                             │
             ┌───────────────┼───────────────┐
             ▼               ▼               ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │ BI Worker   │  │Report Worker│  │Python Worker│
     │             │  │            │  │            │
     │ 查询执行    │  │ 报告生成   │  │ 受控分析   │
     │ 工具调用    │  │ 安全摘要   │  │ 沙箱执行   │
     └────────────┘  └────────────┘  └────────────┘
                             │
                     ┌───────┘
                     ▼
             ┌────────────┐
             │Audit Worker │ ← 审计每个工具调用
             │(可选)       │
             └────────────┘
```

### BI Worker 工具链

BI Worker 注册了 7 个白名单工具（权限见 `conf/bi_worker_permissions.json`）：

| 工具 | 用途 |
|------|------|
| `datalogue_prepare_query_context` | 查询上下文准备（L0+L1 合并） |
| `datalogue_search_assets` | 列出数据集候选蓝图/指标/维度 |
| `datalogue_request_schema_slice` | 请求表结构与跨表关系 |
| `datalogue_describe_tables` | 按表名返回字段细节 |
| `datalogue_execute_query_plan_bundle` | 校验并执行查询计划 |
| `datalogue_repair_query_plan` | 故障类型驱动的查询计划修复 |
| `datalogue_select_candidate_datasets` | 候选数据集筛选 |

## LLM 模型配置

系统支持两种层级配置（数据库配置优先）：

1. **数据库配置** — 在治理前端"系统设置 / LLM 模型"中配置，支持：
   - 多个 OpenAI-compatible 端点
   - LiteLLM Proxy 代理接入
   - 按任务角色绑定不同模型
2. **环境变量回退** — 数据库未配置时回退 `.env`：
   ```env
   OPENAI_API_KEY=your-api-key
   OPENAI_BASE_URL=https://api.minimaxi.com/v1
   LLM_MODEL=MiniMax-M2.7
   ```

详见 [LiteLLM 多模型接入说明](docs/LiteLLM多模型接入说明.md)。

## 数据源驱动

Datalogue 支持多种企业级数据源：

| 数据源 | 依赖 | 备注 |
|--------|------|------|
| **PostgreSQL** 16+ | psycopg2-binary | 核心依赖，强制安装 |
| **MySQL** 8+ | pymysql | 核心依赖，强制安装 |
| **Oracle** 19c+ | oracledb | [企业版] 需额外安装 |
| **SQL Server** 2019+ | pyodbc | [企业版] 需额外安装 |
| **Hive** / **Presto** | PyHive | [企业版] 需额外安装 |
| **Trino** | trino | [企业版] 需额外安装 |
| **ClickHouse** | clickhouse-driver | [企业版] 需额外安装 |
| **BigQuery** | sqlalchemy-bigquery | [企业版] 需额外安装 |

```bash
# 离线安装企业驱动
bash scripts/download_enterprise_wheels.sh ./wheelhouse
pip install --no-index --find-links ./wheelhouse -r requirements-enterprise.txt
```

## Manifest 权限体系

Datalogue 的权限控制分三层：

| 层次 | 位置 | 控制内容 | 配置方式 |
|------|------|---------|----------|
| 运行时工具权限 | `conf/bi_worker_permissions.json` | BI Worker 可调用的工具白名单 | JSON 文件 |
| 数据集执行权限 | Manifest 编辑界面 | 数据集能否被发布/调度/执行 | 前端设置 `status: "allowed"` |
| 路由可见摘要 | `capability_manifest` | 对 LeadAgent 暴露的权限摘要 | 自动派生 |

### BI Worker 工具白名单（JSON 外部化配置）

工具权限从 `registry.py` 迁移到了外部 JSON 文件，修改时不需改代码：

```json
{
  "mode": "dont_ask",
  "allow_rules": {
    "datalogue_prepare_query_context": [
      { "tool_name": "...", "behavior": "allow", "source": "datalogue-bi-worker-template" }
    ]
  }
}
```

**⚠️ 新增 BI Worker 工具时**：在 `tools.py` 注册后，必须在 `conf/bi_worker_permissions.json` 的 `allow_rules` 中同步添加对应条目，否则 Worker 调用会被 DONT_ASK 静默拒绝。

## 开发

### 运行测试

```bash
# 全部测试
pytest tests/ -q

# 特定模块
pytest tests/test_dataset.py -v

# 带覆盖率
pytest --cov=app tests/ -q
```

### 代码质量

```bash
# 格式化
black app/ tests/

# Lint
ruff check app/ tests/

# 类型检查
mypy app/
```

### 数据库迁移

```bash
# 生成新迁移
alembic revision --autogenerate -m "描述改动的名称"

# 应用迁移
alembic upgrade head

# 回滚
alembic downgrade -1

# 查看状态
alembic current
```

## 环境变量参考

完整的环境变量列表见 [.env.example](.env.example)。关键变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql://...` | PostgreSQL 连接串 |
| `OPENAI_API_KEY` | — | LLM API Key |
| `OPENAI_BASE_URL` | `https://api.minimaxi.com/v1` | LLM 端点 |
| `LLM_MODEL` | `MiniMax-M2.7` | 默认模型 |
| `SECRET_KEY` | `change-me` | JWT 密钥 |
| `AGENTSCOPE_SERVICE_ENABLED` | `true` | 启用 AgentScope 子应用 |
| `AGENTSCOPE_REDIS_URL` | `redis://localhost:6379/0` | Redis 连接 |
| `APP_ENV` | `development` | 运行环境 |

## Docker 部署

```bash
# 完整部署（Postgres + Redis + API）
docker compose --profile api up -d

# 仅基础设施（方便本地开发后端）
docker compose up -d db redis
```

详见 [Docker 部署方案](docs/docker-deployment.md)。

## 文档索引

| 文档 | 内容 |
|------|------|
| [Docker 部署方案](docs/docker-deployment.md) | 生产级 Docker 部署 |
| [LiteLLM 多模型接入说明](docs/LiteLLM多模型接入说明.md) | 多模型管理与绑定 |
| [企业数据源驱动离线部署](docs/企业数据源驱动离线部署.md) | 内网离线安装企业驱动 |
| [NL2DSL 资产引用 Schema](docs/NL2DSL资产引用Schema.md) | 查询计划契约 |
| [DSL 校验节点改造方案](docs/DSL校验节点改造方案.md) | 校验架构设计 |
| [数据集字段显示规则设计方案](docs/数据集字段显示规则设计方案.md) | 字段显示与脱敏 |
| [CHECKLIST](docs/CHECKLIST.md) | 发布前检查清单 |
| [CODE_STYLE](docs/CODE_STYLE.md) | 编码规范 |

## 许可证

内部使用。
