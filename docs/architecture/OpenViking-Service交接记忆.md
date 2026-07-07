# OpenViking Service 交接记忆

> 整理时间：2026-07-07 15:02  
> 适用对象：OpenViking Service 接入、接手或复用数语 Datalogue 当前 AgentScope 主链时的上下文摘要。  
> 当前版本口径：AS-R0，AgentScope Agent Team 主链。

## 一页摘要

数语是面向企业数据的 AI 原生智能问数平台。当前主链已经从旧 LangGraph / SubAgent 路线迁到 AgentScope Service + Agent Team：前端通过 assistant-ui 消费 SSE，后端 FastAPI 创建 Datalogue task 和 AgentScope mirror session，再由 AgentScope Service 驱动 Leader Agent 与 BI Worker Agent 协作完成问数。

OpenViking Service 如果作为外部服务接入，建议把 Datalogue 当成受控问数能力提供方：只调用主问数 API、Workbench / artifact 查询 API 和必要的控制面 API，不直接绕过 Datalogue 读取业务库、拼 SQL、读取 raw rows 或把 schema / query plan 注入对话上下文。

## 当前主链

```text
用户 / OpenViking Service
  -> POST /api/agent-team/tasks/stream
  -> AgentTeamTaskRuntime
  -> AgentScopeServiceTaskRunner
  -> AgentScope Service 子应用 (/agentscope)
  -> Agent Team
     -> Leader Agent
     -> BI Worker Agent
  -> Datalogue BI Worker Runtime
     -> L4 校验
     -> L5 受控执行
     -> DSL -> SQL 编译 -> 查询执行 -> artifact
  -> DatalogueEventEnvelope SSE
  -> assistant-ui / OpenViking 消费端
```

核心结论：

- 主入口是 `POST /api/agent-team/tasks/stream`。
- AgentScope Service 作为 FastAPI 子应用挂载在 `/agentscope`。
- Leader Agent 负责规划、候选确认和 Worker 协调，不直接产出 SQL。
- BI Worker Agent 通过 Datalogue tools 执行受控问数。
- Datalogue 仍持有业务真相源：任务、会话投影、artifact、checkpoint、权限与审计边界。

## OpenViking 接入边界

建议接入方式：

- 用主问数 SSE API 发起任务，消费 `DatalogueEventEnvelope`。
- 用 `artifact_ref` / `thread_id` / `trace_id` / `checkpoint_ref` 串联结果、工作台和重试链路。
- 对用户展示只使用 `summary`、`reasoning_summary`、业务级 timeline、结果卡和 artifact 摘要。
- 需要详情时调用 artifact / workbench API，而不是要求 Agent 在自然语言里输出原始数据。

禁止或不建议：

- 不把 SQL、schema、raw rows、query plan、RepairPatch 主体暴露给 OpenViking 的普通对话上下文。
- 不让 OpenViking 直接生成可执行 SQL 后绕过 Datalogue 审计执行。
- 不依赖旧 LangGraph / Langfuse 文档作为现行主链依据；这些内容已归档或降级为历史事实。
- 不复用旧 `datalogue_query_dataset` 心智模型判断当前链路，当前 BI Worker 渐进式工具路径已经收口到 capability / assets / query plan。

## 关键 API

以当前 OpenAPI 和源码路由为准，以下是 OpenViking 最小接入所需的稳定入口。

| 类别 | 方法与路径 | 用途 |
|------|------------|------|
| 主问数 | `POST /api/agent-team/tasks/stream` | 发起 Agent Team SSE 任务 |
| AgentScope 状态 | `GET /api/agentscope-control/status` | 检查 AgentScope Service 健康状态 |
| 会话 | `GET /api/conversation` / `GET /api/conversation/{id}` | 读取会话列表和历史消息 |
| Workbench | `GET /api/workbench/thread/{thread_id}` | 读取线程工作台视图 |
| Workbench | `POST /api/workbench/actions/retry` | 受控重试，必须走白名单 payload |
| Artifact | `GET /api/artifacts/{ref}` | 读取查询产物详情或摘要 |
| 数据集 | `GET /api/dataset` / `GET /api/dataset/{id}` | 读取数据集治理信息 |

主问数请求最小形态：

```json
{
  "question": "查询杨凯2025年工作日志",
  "task_type": "bi_query",
  "dataset_id": 10,
  "conversation_id": null,
  "thread_id": null
}
```

SSE 事件中需要重点消费：

| 事件 | 用途 |
|------|------|
| `task.started` | 任务创建成功 |
| `agent.selected` | 当前执行 Agent 确认 |
| `reasoning.delta` | 安全推理摘要进度 |
| `message.delta` | 用户可见回答增量 |
| `tool_call.completed` | 工具调用完成 |
| `clarification.required` | 需要用户确认数据集或补充信息 |
| `artifact.created` | 产物生成，可读取 `artifact_ref` |
| `message.completed` | 最终回答 |
| `task.completed` | 任务完成 |
| `task.failed` | 任务失败，内部细节已隐藏 |

## 关键文件入口

| 文件 | 职责 |
|------|------|
| `docs/上下文入口.md` | 项目最新上下文入口 |
| `docs/architecture/系统架构.md` | 当前 AS-R0 总体架构 |
| `docs/architecture/执行链路.md` | 端到端问数链路 |
| `docs/architecture/AgentScope集成.md` | AgentScope Service 子应用与配置 |
| `docs/api/API概览.md` | API 粗索引，细节以 OpenAPI / 源码为准 |
| `.codex/project-memory.md` | 项目完成记录，按关键词检索 |
| `datalogue-api/app/api/agent_team.py` | 主问数 SSE API |
| `datalogue-api/app/runtime/agent_team_runtime.py` | Datalogue task、mirror session、SSE 投影主运行时 |
| `datalogue-api/app/agentscope_service/runner.py` | Datalogue 到 AgentScope Service 的 runner |
| `datalogue-api/app/agentscope_service/client.py` | AgentScope Service HTTP/SSE client |
| `datalogue-api/app/agentscope_service/registry.py` | Leader / Worker prompt 与 Agent 规格 |
| `datalogue-api/app/agentscope_service/tools.py` | Datalogue 暴露给 AgentScope 的工具 |
| `datalogue-api/app/agentscope_service/bi_worker_contracts.py` | `BIWorkerQueryPlan` 等严格契约 |
| `datalogue-api/app/agentscope_service/bi_worker_context.py` | 渐进式上下文 L0-L4 构建 |
| `datalogue-api/app/agentscope_service/bi_worker_validator.py` | L4 查询支持校验 |
| `datalogue-api/app/agentscope_service/bi_worker_runtime.py` | L5 受控执行 |
| `datalogue-web/src/assistant/agent-team-event-adapter.js` | 前端 SSE 事件适配 |
| `datalogue-web/src/assistant/chat-adapter.js` | assistant-ui 消息适配 |

## BI Worker 记忆

当前 BI Worker 采用渐进式上下文：

- L0：数据集能力摘要。
- L1：候选资产目录。
- L2：schema slice，按需加载，并由后端生成 `context_state_patch`。
- L3：值域画像，仍在继续收敛。
- L4：查询支持校验，强制用于 join / relationship 判断。
- L5：受控执行，失败返回安全 repair payload。

`BIWorkerQueryPlan` 关键契约：

- 明细查询使用 `selects`，不是 `select` / `columns` / `fields` / `dimensions`。
- 指标查询使用 `metrics`，支持 `sum` / `count` / `avg` / `min` / `max` / `count_distinct`。
- filter operator 只接受 `=`、`!=`、`>`、`>=`、`<`、`<=`、`between`、`in`、`contains`。
- join requirement 使用 `left_alias`、`right_alias`、`relationship_ref`、`join_type`、`required`、`reason`。
- 契约失败会返回 `bi_worker_repair_request` 和重试策略；同类或累计错误达到预算后要求停止猜测并汇报澄清或失败摘要。

排障时如果看到执行时间很长，先排查 QueryPlan 契约反复校验失败，而不是先猜 SQL 慢。

## 安全输出边界

用户可见层和 OpenViking 普通上下文只能出现：

- 业务问题摘要。
- 业务级推理进度。
- 候选数据集卡片。
- 查询结果摘要。
- 行列规模。
- `artifact_ref` / `thread_id` / `trace_id` / `checkpoint_ref`。
- 可受控打开的 artifact 详情。

内部受控层才允许流转：

- SQL。
- schema。
- raw rows。
- query plan。
- RepairPatch 主体。
- 字段级映射细节。

## 本地启动和验证

首次或干净环境启动建议：

```bash
docker compose up -d db redis

cd datalogue-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp -n .env.example .env
alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

cd ../datalogue-web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

常用验证：

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_agentscope_agent_team_task_runner.py tests/test_agentscope_service_tools.py tests/test_bi_worker_query_runtime.py -q

cd ../datalogue-web
npm test -- agent-team-event-adapter.test.js chat-adapter.test.js --run
npm run lint
npm run build
```

真实页面 smoke：

1. 打开 `http://127.0.0.1:5173/chat`。
2. 输入“查询杨凯2025年工作日志”或指定数据集问题。
3. 如出现候选数据集卡，选择目标数据集。
4. 等待结果卡和 artifact 详情入口出现。
5. 检查聊天区不出现 SQL、schema、raw rows、query plan。
6. 后端日志核对 `/api/agent-team/tasks/stream`、`/agentscope/chat/` 和 BI Worker 工具路径。

## 当前风险和后续项

- 复杂多跳 join 仍依赖 `relationship_ref` 到真实 join key 的进一步解析收口。
- L3 值域画像还需要平衡上下文预算和业务解释质量。
- 跨进程 AgentScope Service 场景下，当前进程内 progress bridge / worker 事件桥需要迁到 Redis 或 message bus，并加强 task / session correlation。
- 如果页面 timeline 像旧路径，优先检查旧 AgentScope session、旧 prompt 或旧 worker 工具列表缓存。
- `AGENT_DEBUG_RAW_LOGS=true` 只建议本地短时排障，Leader / BI Worker raw debug 不进入 SSE、前端或 artifact。

## 给 OpenViking 的建议落点

OpenViking Service 第一阶段只需要实现三件事：

1. 作为 Datalogue 主问数 API 的调用方，稳定消费 SSE，并把 `thread_id`、`trace_id`、`artifact_ref` 保存为外部任务 refs。
2. 用 Workbench / artifact API 做结果详情、重试和历史回放，不要求 Agent 把原始数据直接写进回答。
3. 把安全边界写进 OpenViking 的 prompt / tool contract：OpenViking 只拿业务摘要和 refs，不拿 SQL、schema、raw rows、query plan。
