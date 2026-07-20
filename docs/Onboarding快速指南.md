# 数语（Datalogue）项目 Onboarding 快速指南

> 版本：v2026.07 | 目标读者：新加入的开发者
> 阅读时长：约 15 分钟读完，30 分钟完成环境搭建

---

## 一、项目定位（一句话理解）

**数语（Datalogue）** 是一个面向企业数据的 **AI 原生智能问数平台**。

业务人员用自然语言提问（如"上个月销售额是多少？"），系统通过 AI Agent 编排自动完成数据查询、分析和报告生成，全程可追溯、可审计。

### 核心产品形态

| 功能 | 路径 | 说明 |
|------|------|------|
| **问数对话** | `/chat` | 自然语言提问 → AI 自动查询 → 流式回答 |
| **语义治理** | `/datasets` | 数据集、指标、维度、术语、蓝图的配置与管理 |
| **数据源管理** | `/datasources` | 多数据源接入（MySQL / Oracle / Hive / Trino 等） |
| **工作台** | `/workbench/:threadId` | 查询产物、任务时间线、重试控制 |
| **系统设置** | `/settings` | LLM 模型配置、用户权限 |

---

## 二、技术栈速览（30 秒看懂）

### 后端（`datalogue-api/`）

| 层级 | 技术 | 说明 |
|------|------|------|
| Web 框架 | FastAPI 0.111 + Uvicorn | ASGI 服务，SSE 流式响应 |
| ORM | SQLAlchemy 2.0 + Alembic | 数据库迁移与操作 |
| 数据库 | PostgreSQL 16 + pgvector | 主存储 + 向量搜索 |
| 缓存/消息 | Redis 7 | AgentScope Storage & MessageBus |
| AI Agent 框架 | AgentScope 2.0.3 | Agent Team 编排引擎（核心） |
| LLM 接入 | OpenAI-compatible / LiteLLM Proxy | 多模型、多供应商 |
| 安全 | SQL Guard + Payload Sanitizer | 防注入、防泄露 |
| 测试 | pytest + pytest-asyncio | 60+ 测试文件 |
| 代码质量 | Black + Ruff + MyPy | 格式、lint、类型检查 |

### 前端（`datalogue-web/`）

| 技术 | 说明 |
|------|------|
| React 19 + Vite + TypeScript | 现代前端栈 |
| assistant-ui | 聊天 UI 组件库 |
| ECharts | 数据可视化图表 |
| Ant Design | UI 组件库 |
| react-router-dom v7 | 路由管理 |

---

## 三、环境搭建（5 分钟上手）

### 前置条件

- Python 3.11+
- PostgreSQL 16+（含 pgvector 扩展）
- Redis 7+
- Node.js 20+（前端开发）
- LLM API Key（MiniMax / DeepSeek / OpenAI 等）

### 方式一：Docker 一键启动（推荐首次）

```bash
# 1. 在仓库根目录启动唯一一套 PostgreSQL + Redis
docker compose up -d db redis

# 2. 进入后端目录并复制环境变量模板
cd datalogue-api
cp .env.example .env
# 编辑 .env，至少修改 OPENAI_API_KEY

# 3. 安装 Python 依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. 初始化数据库
alembic upgrade head

# 5. 启动后端服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端启动后访问：http://localhost:8000/docs（Swagger API 文档）

```bash
# 6. 启动前端（另开终端）
cd datalogue-web
npm install  # 或 pnpm install
npm run dev
```

前端启动后访问：http://localhost:5173

### 方式二：Docker Compose 完整部署

```bash
cp .env.example .env
# 编辑根目录 .env 后启动；migration 会先执行 Alembic
docker compose up -d --build
```

详见 [Docker 部署方案](../datalogue-api/docs/docker-deployment.md)。

### 验证环境

```bash
# 后端健康检查
curl http://localhost:8000/health
# 预期：{"status":"ok"}

# 数据库连接
docker compose exec db pg_isready -U datalogue

# 前端构建测试
cd datalogue-web && npm run build
```

---

## 四、核心架构速览（5 分钟理解）

### 4.1 系统分层

```
用户 / 前端 (React + SSE)
       │
       ▼
┌─────────────────────────────────────┐
│  FastAPI (端口 8000)                  │
│  ├── /api/*  业务路由（数据集/对话）   │
│  └── /agentscope/* AgentScope Service │
│         │                            │
│         ▼                            │
│  ┌──────────────────────────────┐    │
│  │ Agent Team (官方架构)         │    │
│  │  Leader Agent → 理解/规划/路由 │    │
│  │  BI Worker Agent → 受控查询执行 │    │
│  └──────────────────────────────┘    │
└─────────────────────────────────────┘
       │
┌──────┼──────┐
▼      ▼      ▼
PostgreSQL  Redis  企业数据源
(+pgvector)        MySQL/Oracle/Hive...
```

### 4.2 问数流程（端到端）

```
用户提问: "上个月销售额是多少？"
    │
    ▼
POST /api/agent-team/tasks/stream (SSE 流式)
    │
    ├─▶ AgentTeamTaskRuntime（创建任务、Mirror 会话）
    │
    ├─▶ AgentScope Service（Agent Team 编排）
    │   ├─ Leader Agent：理解问题 → 路由数据集 → 创建 BI Worker
    │   └─ BI Worker：通过 Tools 调用查询工具链
    │
    ├─▶ 事件投影（AgentScope 事件 → Datalogue 事件）
    │   task.started → agent.selected → message.delta → artifact.created → message.completed
    │
    └─▶ 前端消费 SSE，渲染对话 UI
```

### 4.3 核心设计原则（必须记住）

| 原则 | 说明 | 为什么重要 |
|------|------|-----------|
| **控制面/数据面分离** | Leader Agent 只做编排，不直接生产 SQL | 防止 LLM 直接生成危险 SQL |
| **DSL 先行** | 工具层先生成结构化查询描述（DSL）→ 再编译为 SQL | 增加可控性，减少注入风险 |
| **Repair 一等链路** | 失败不是错误提示，而是闭环修复流程 | 保证问数可信 |
| **安全分层** | L4 校验 → L5 执行，SQL/原始数据不进入用户可见层 | 企业级安全合规 |

---

## 五、关键文件速查（按任务定位）

### 5.1 后端核心文件

| 想做什么 | 先看哪个文件 | 说明 |
|----------|-------------|------|
| **理解主入口** | `datalogue-api/app/main.py` | FastAPI 应用、生命周期、AgentScope 子应用挂载 |
| **新增 API 端点** | `datalogue-api/app/api/` 目录 | 已有 datasource.py / dataset.py / chat.py 等 |
| **新增数据模型** | `datalogue-api/app/models/` 目录 | SQLAlchemy ORM 模型 |
| **新增 Pydantic Schema** | `datalogue-api/app/schemas/` 目录 | 请求/响应校验模型 |
| **理解 Agent Team 主链** | `datalogue-api/app/runtime/engine/runner.py` | 646 行，HTTP 调用 AgentScope Service |
| **理解事件投影** | `datalogue-api/app/runtime/engine/projection.py` | 179 行，AgentScope → Datalogue 事件清洗 |
| **理解 BI Worker 工具** | `datalogue-api/app/domains/bi/` 目录 | 查询执行、DSL 编译、SQL 安全 |
| **新增数据库迁移** | `datalogue-api/alembic/versions/` | `alembic revision --autogenerate -m "描述"` |

### 5.2 前端核心文件

| 想做什么 | 先看哪个文件 | 说明 |
|----------|-------------|------|
| **理解路由和布局** | `datalogue-web/src/App.jsx` | 主路由、主题、布局 |
| **新增页面** | `datalogue-web/src/components/` 或 `src/features/` | 按功能域组织 |
| **理解 Chat 问数页面** | `datalogue-web/src/features/chat/chat-page.jsx` | SSE 消费、Workbench Panel |
| **新增 API 调用** | `datalogue-web/src/api/client.js` | HTTP/SSE 封装 |
| **理解事件适配** | `datalogue-web/src/assistant/` 目录 | Agent Team 事件投影适配 |

### 5.3 配置与文档

| 文件 | 说明 |
|------|------|
| `.env.example` | 环境变量模板（必填：OPENAI_API_KEY） |
| `docs/上下文入口.md` | 当前架构入口、文档导航 |
| `docs/architecture/系统架构.md` | 详细架构设计 |
| `docs/architecture/执行链路.md` | 端到端执行流程 |
| `docs/architecture/数据模型.md` | 核心数据库模型 |
| `docs/architecture/目录治理与模块边界.md` | 目录职责与迁移规则 |
| `.codex/project-memory.md` | 实际项目变更完成记录（按时间线） |
| `AGENTS.md` | AI Agent 协作约定（开发标准） |

---

## 六、开发规范（5 分钟掌握）

### 6.1 代码质量门禁（提交前必须执行）

```bash
cd datalogue-api

# 1. 格式化
black app/ tests/ scripts/

# 2. Lint 检查
ruff check . --fix

# 3. 类型检查
mypy app/

# 4. 运行测试
pytest tests/ -q
```

前端：
```bash
cd datalogue-web
npm run lint
npm run build
npm run test
```

### 6.2 Python 文件头模板（新增文件必填）

```python
# ============================================================
# File Name   : your_file.py
# Description:
#   简要说明本文件用途。
#
# Responsibilities:
#   - 职责1：...
#   - 职责2：...
#
# Author      : yangkai
# Created On  : 2026-07-10
# ============================================================
```

### 6.3 注释规范

- **中文注释**：所有注释使用中文，解释"为什么"而非"是什么"
- **关键位置**：重要分支、边界条件、跨层状态写入、外部副作用、降级/fallback、异常处理处必须注释
- **TODO 管理**：实现前标记 TODO，完成后删除

### 6.4 项目变更完成记录

仅当实际完成需求变更、代码/测试/运行配置/项目文档改动、缺陷修复或关键技术决策时，才在 `.codex/project-memory.md` 追加记录。普通对话、问答、临时分析、状态确认、纯阅读/审查和项目无关事项不记录。

记录内容包含：
- 完成时间（`YYYY-MM-DD HH:mm`）
- 功能名称
- 涉及文件
- 关键改动
- 验证方式
- 残留风险或后续事项

---

## 七、常见开发任务速查

### 7.1 新增一个 API 端点

1. 在 `app/schemas/` 定义 Pydantic 请求/响应模型
2. 在 `app/api/` 新增路由函数，使用 `APIRouter`
3. 在 `app/services/` 实现业务逻辑（如需要）
4. 在 `app/main.py` 或对应 router 注册新路由
5. 运行 `pytest` 确保测试通过

### 7.2 新增一个数据库表

1. 在 `app/models/` 定义 SQLAlchemy 模型（继承 `Base` + `TimestampMixin`）
2. 运行 `alembic revision --autogenerate -m "描述"` 生成迁移
3. 检查生成的迁移文件，确认无误后运行 `alembic upgrade head`
4. 在 `app/schemas/` 定义对应的 Pydantic Schema
5. 为新表和字段添加**中文注释**（字典字段写清 `code=中文含义`）

### 7.3 修改 BI Worker 查询逻辑

1. 修改 `app/domains/bi/` 下的相关文件（skill / toolkit / worker）
2. 注意 **SQL、schema、原始数据不得进入用户可见层**
3. 如果新增工具，需在 `conf/bi_worker_permissions.json` 注册白名单
4. 运行相关 BI Worker 测试确保通过

### 7.4 修改前端 Chat 页面

1. 修改 `src/features/chat/` 下的文件
2. 注意 SSE 事件消费和 Agent Team 事件适配
3. 运行 `npm run lint && npm run build && npm run test`
4. 如需实际页面验证，启动本地 dev server 查看

### 7.5 新增 AgentScope 工具

1. 在 `app/agentscope_runtime/tools.py` 或 `app/domains/bi/skill/` 注册工具
2. 在 `conf/bi_worker_permissions.json` 的 `allow_rules` 添加权限条目
3. 更新 AgentScope registry 配置
4. 测试工具调用链路

---

## 八、测试与验证

### 8.1 后端测试

```bash
cd datalogue-api

# 全部测试
pytest tests/ -q

# 特定模块（推荐）
pytest tests/test_dataset.py -v
pytest tests/test_chat.py -v
pytest tests/test_agentscope_service_tools.py -v

# 带覆盖率
pytest --cov=app tests/ -q
```

### 8.2 前端测试

```bash
cd datalogue-web
npm run test        # vitest
npm run lint        # eslint
npm run build       # 生产构建验证
```

### 8.3 本地端到端验证

1. 启动后端：`uvicorn app.main:app --reload`
2. 启动前端：`npm run dev`
3. 访问 http://localhost:5173，登录后进入 `/chat`
4. 输入一个测试问题，观察 SSE 流式响应
5. 检查后端日志确认 Agent Team 执行链路正常

---

## 九、遇到问题怎么办

### 9.1 常见启动问题

| 问题 | 排查方向 |
|------|----------|
| `psycopg2.OperationalError` | 检查 PostgreSQL 是否启动、数据库密码是否匹配 `.env` |
| `OPENAI_API_KEY required` | 确认 `.env` 中已设置有效的 API Key |
| 前端无法连接后端 | 检查 CORS 配置、`VITE_API_BASE_URL` 是否正确 |
| AgentScope 子应用未启动 | 确认 `AGENTSCOPE_SERVICE_ENABLED=true` |

### 9.2 调试工具

```bash
# 查看后端日志
cd datalogue-api && tail -f logs/app.log

# 查看 AgentScope 运行时日志
# 日志中搜索关键词：agent_team、bi_worker、query_plan、repair

# 查看数据库
psql -U datalogue -d datalogue -c "\dt"  # 列出所有表

# 查看 Redis
redis-cli -n 0 keys "*agentscope*"  # 查看 AgentScope 相关 key
```

### 9.3 求助路径

1. **先查文档**：`docs/` 目录下的架构文档和 API 参考
2. **再查项目记忆**：`.codex/project-memory.md` 搜索关键词
3. **查看测试**：`tests/` 目录找相关测试用例理解预期行为
4. **最后求助**：带上完整的错误日志、复现步骤、已尝试的方案

---

## 十、关键术语速查表

| 术语 | 含义 |
|------|------|
| **Agent Team** | AgentScope 官方多智能体协作架构（Leader + Workers） |
| **LeadAgent** | 控制面 Agent，负责理解、规划、路由、协调 |
| **BI Worker** | 执行面 Agent，负责受控查询执行 |
| **Manifest** | 数据集路由契约，描述该数据集能回答什么问题 |
| **QueryPlan** | 查询计划（结构化查询描述，非直接 SQL） |
| **DSL** | 领域特定语言，结构化查询描述，先 DSL 再编译 SQL |
| **Repair** | 问数失败时的修复闭环（Failure → Diagnosis → Repair → Retry） |
| **SSE** | Server-Sent Events，后端向前端推送流式事件 |
| **Artifact** | 查询产物（结果摘要、图表、报表等），带 ref 可审计 |
| **Workbench** | 工作台，查看任务时间线、产物、重试控制 |
| **Facade** | 门面模式，渐进迁移时的新入口层 |
| **DONT_ASK** | AgentScope 工具权限模式，白名单外工具静默拒绝 |

---

## 附录：推荐阅读顺序

### 入职第 1 天（熟悉环境）
1. 本文（Onboarding 快速指南）← 你正在读
2. `docs/上下文入口.md` — 了解当前架构主链
3. `AGENTS.md` — 了解开发协作约定

### 入职第 2-3 天（深入架构）
4. `docs/architecture/系统架构.md` — 整体架构
5. `docs/architecture/执行链路.md` — 端到端执行流程
6. `docs/architecture/数据模型.md` — 核心数据库模型

### 入职第 4-5 天（准备开发）
7. `docs/architecture/目录治理与模块边界.md` — 目录职责与迁移规则
8. `docs/architecture/AgentScope集成.md` — AgentScope 子应用细节
9. 跑通本地环境，完成一次端到端问数测试

### 持续参考
- `docs/api/API概览.md` — 新增 API 时查阅
- `.codex/project-memory.md` — 实际项目变更历史记录
- `datalogue-api/docs/CODE_STYLE.md` — 编码规范细节
- `datalogue-api/docs/CHECKLIST.md` — 提交前自检清单

---

> 如有疑问或发现本文过时，请联系当前维护人（杨凯）并直接修正文档；形成实际项目变更后，再按上述规则更新 `.codex/project-memory.md`。
