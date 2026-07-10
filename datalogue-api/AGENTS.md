# AGENTS.md

## 项目身份

- 当前项目：Datalogue / 数语后端 API（datalogue-api）
- 工作目录：`/Users/yangkai/code_place/study/python/Datalogue/datalogue-api`
- 用户：杨凯 / KenYang
- 默认回复语言：中文
- 本文件继承父级 `/Users/yangkai/code_place/study/python/Datalogue/AGENTS.md` 的项目规范；若本文件有更具体约束，以本文件为准。

## 技术架构

### 技术栈

- Python 3.11（`>=3.11,<3.14`）
- FastAPI 0.111 + uvicorn（ASGI 入口）
- SQLAlchemy 2.0 + Pydantic 2（ORM 与 Schema）
- AgentScope 2.0.3（主链，官方 Agent Team 架构）
- LangChain 0.2 + LangGraph 0.0.65（旧链残留，仅保留 LLM 调用辅助）
- 多数据源驱动：ClickHouse、BigQuery、MySQL、PostgreSQL

### 核心调用链（AS-R0）

```
用户 → POST /api/agent-team/tasks/stream（SSE）
  → app/api/agent_team.py → AgentTeamTaskRuntime（app/runtime/）
    → AgentScopeServiceTaskRunner（app/agentscope_service/runner.py，HTTP）
      → AgentScope Service 子应用（挂载于 /agentscope）
        → Agent Team：Leader + BI/Report/Python/Audit Worker（registry.py）
          → Datalogue BI 工具（tools.py：候选筛选 / 上下文准备 / schema 切片 / 执行捆绑 / 修复）
            → query_plan_compiler + dataset_query_executor（SQL 编译与执行）
```

主链已从 LangGraph 完全迁移到 AgentScope 官方 Agent Team；旧 LangGraph 代码已归档，仅 `app/graph/llm.py` 等保留 LLM 调用辅助。

### 目录结构

| 目录 | 职责 |
|------|------|
| `app/api/` | FastAPI 路由：`agent_team`（主链 SSE）、`dataset`、`datasource`、`conversation`、`llm`、`artifacts`、`messages`、`workbench`、`agentscope_control_plane` |
| `app/agentscope_service/` | AgentScope Service 子应用：worker 模板注册（`registry`）、运行时（`runner`/`bi_worker_runtime`/`bi_worker_validator`/`bi_worker_contracts`/`bi_worker_context`）、BI 工具（`tools`）、查询执行器（`dataset_query_executor`）、事件投影（`projection`/`progress_bridge`） |
| `app/agents/bi_agent/` | BI Agent handoff 层：`dataset_agent_factory`、`native_handoff`、`handoff_service`、`confirmation_service`、`runtime_context`、`run_service` |
| `app/bi/` | BI 技能层：`skill/dataset_query`、`skill/runtime_bridge`、`toolkit/atomic` |
| `app/runtime/` | 主链运行时：`agent_team_runtime`、`thread_resolver` |
| `app/services/` | 业务服务：标注（`annotation`）、蓝图分析（`blueprint_analyzer`）、Query Plan 编译（`query_plan_compiler`）、SQL 方言适配（`sql_dialect_adapter`）、artifact 存储 |
| `app/prompts/` | 统一 Prompt 管理：`annotation`/`blueprint_analyzer`/`dataset_agent`/`native_handoff`/`agent_team`，单一入口 `from app.prompts import XXX` |
| `app/models/` `app/schemas/` | SQLAlchemy 模型 / Pydantic Schema |
| `app/core/` | `config`、`database`、`security` |
| `app/safety/` | 安全投影（`payload_sanitizer`） |
| `app/contracts/` | 契约（`BI_SOUL`） |
| `app/events/` | 事件投影（`projection`） |
| `app/middlewares/` | 生命周期中间件（`lifecycle`） |
| `app/graph/` | LangGraph 旧链残留（LLM 调用） |
| `app/utils/` | 通用工具（SQL guard、方言、样例数据、列标签等） |

### 关键边界

- **BI Worker 安全边界**：BI Worker Agent/LLM 只能调用 Datalogue 暴露的安全查询工具，不得自行生成/执行 SQL、直接读取 raw rows，输出只含安全摘要、`artifact_ref`、`checkpoint_ref`、`row_count`、`column_count` 等。Datalogue runtime/tool 私有诊断层可以持有 SQL、schema、raw rows、原始数据库报错和 RepairPatch 主体，用于 Failure Classifier、Private Diagnosis、Repair Planner、Retry Executor 与本地 debug；这些私有细节不得进入 LLM prompt、用户可见 SSE、artifact 摘要、OpenViking 普通上下文或项目交接文档正文。
- **Prompt 统一管理**：所有 LLM prompt 常量集中在 `app/prompts/`，调用方统一 `from app.prompts import XXX`，不得在业务代码内散落 prompt 字符串。
- **官方团队工具**：`TeamCreate`/`AgentCreate`/`TeamSay`/`TeamDelete` 只用 AgentScope 官方内置工具，不自研替代、不自研 runner 绕过官方团队协作。

## 关键协作约束

- 修改代码前先读相关上下文，优先沿用现有项目结构和风格。
- 仓库如存在 `.codegraph/`，代码探索优先使用 CodeGraph，而不是 `grep` / `find` / 直接读文件。
- 不主动回滚用户或其他工具已有改动；脏工作区只处理当前任务相关文件。
- 新增 Python 文件必须按父级 `AGENTS.md` 的中文文件头模板写职责说明。
- 新增或修改关键后端逻辑时，必须在路由分支、方法调用、关键赋值、状态写入、fallback、异常降级、外部副作用和跨层契约处补充关键行级中文注释；优先写在对应调用或关键操作同一行的行尾，解释业务意图和边界，不机械复述代码。
- 完成功能后需要更新 `../.codex/project-memory.md`，按 `YYYY-MM-DD HH:mm` 记录完成时间、功能、涉及文件、关键改动、验证方式、残留风险。
- `../.codex/project-memory.md` 的最新详细记录超过 10 条时，先压缩较早详细记录；历史压缩条目超过 10 条时，继续深度压缩为主题摘要。
- 若实现前临时写 `TODO`，完成后必须清理对应 `TODO`。
- Datalogue 任务默认不只给方案，应直接实现、补验证，必要时做真实链路检查。
- 前端改动完成后优先 `npm run lint` 和 `npm run build`；如需页面验收，再启动 dev server。
- Java 任务按需使用 `jdk8` / `jdk17` 切换。

## 执行偏好

- 复杂 Datalogue 问题优先真实链路取证：页面/前端回放、trace、后端日志、prompt/token、final payload、历史回放等交叉验证。
- 截图或临时验证产物放 `/private/tmp` 或系统临时目录，不写入仓库。
- 最终回复保持简洁，说明改了什么、验证了什么、还有什么风险。

## 参考文档

- 上下文入口：`../docs/上下文入口.md`
- 系统架构：`../docs/architecture/系统架构.md`
- 执行链路：`../docs/architecture/执行链路.md`
- AgentScope 集成：`../docs/architecture/AgentScope集成.md`
- 数据模型：`../docs/architecture/数据模型.md`
- 项目记忆：`../.codex/project-memory.md`（按关键词检索，禁止默认全文读取）
- AgentScope 官方文档：`~/code_place/study/agentscope-docs/`（新增 Agent/RAG/工具/工作流能力时必先查阅，优先用框架原生 API）
