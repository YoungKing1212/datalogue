# Datalogue E2E 链路测试方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans only if this plan is turned into automated test code. 当前文件是测试执行方案；直接执行时按清单逐项记录证据。

**目标：** 验证数语从浏览器聊天入口到 AgentScope Agent Team、BI Worker、artifact 持久化、Workbench 展示、会话恢复的完整 E2E 链路。

**架构：** 前端 `datalogue-web` 通过 Vite 代理调用后端 `/api/agent-team/tasks/stream` SSE 主入口。后端 `AgentTeamTaskRuntime` 创建 AgentScope mirror session/message/task，调用 AgentScope Service runner，最终把安全摘要、artifact ref、checkpoint ref 投影给 Chat UI 和 Workbench。

**技术栈：** React + assistant-ui + Vite，FastAPI + SSE，AgentScope 2.0.3，PostgreSQL + Redis，Vitest，pytest，Claude 浏览器自动化或临时 Playwright。

## 全局约束

- 默认只测桌面视口，建议 `1440x960`；除非用户明确要求，不额外测 mobile。
- 不执行破坏性清库；如必须清历史数据，先备份并取得用户确认。
- 截图、HAR、临时 Playwright 脚本放到 `/tmp/datalogue-e2e-<timestamp>/`，不要提交进仓库。
- 聊天消息区不得暴露 `sql`、`schema`、`raw`、`hidden`、`secret`、`query_plan`、`patch`、`control`、`dsl` 等内部执行态。
- 真实 E2E 必须同时给出页面、Network、后端日志、数据库、artifact API 五类证据；只跑单元测试不算通过。

---

## 直接给 Claude 的执行提示词

把下面整段交给 Claude：

```text
你在 /Users/yangkai/code_place/study/python/Datalogue 执行 Datalogue 完整 E2E 链路验收。

要求：
1. 全程中文汇报。
2. 不要清库、不要重置 git、不要提交代码。
3. 若仓库有 .codegraph/，先用 CodeGraph 查入口；配置文件不在索引时再直接读取。
4. 默认只测桌面视口 1440x960。
5. 临时截图、HAR、脚本全部放 /tmp/datalogue-e2e-$(date +%Y%m%d-%H%M%S)/，最后汇总路径。
6. 必须验证五类证据：页面表现、Network/SSE、后端日志、数据库记录、artifact/workbench API。
7. 最终输出必须包含：通过项、失败项、阻塞项、证据路径、关键日志片段、建议修复优先级。

主链验收范围：
- 前端 /chat 入口能发起问数。
- POST /api/agent-team/tasks/stream 返回 SSE。
- SSE 至少出现 task.started、agent.selected、message.completed、task.completed；失败时必须解释 task.failed 原因。
- Chat 最终回答只展示业务摘要和 artifact，不展示 SQL/schema/raw/query_plan 等内部字段。
- Workbench 展示执行时间线或结果详情。
- artifact card 的“查看详情”可通过 /api/artifacts/{ref} 或 /api/workbench/artifact/{ref} 拉到受控 rows/columns。
- 数据库里 agentic_shell_task、conversation/message 或 query_artifact 至少有一组可关联记录。

请按 docs/superpowers/plans/2026-07-07-datalogue-e2e-chain-test-plan.md 执行，并把实际命令输出、截图和结论汇总给我。
```

## 阶段 1：静态与契约基线

### 1.1 后端契约测试

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
source .venv/bin/activate
pytest tests/test_agent_team_task_runtime.py tests/test_agent_team_task_contracts.py -q
```

通过标准：
- `test_agent_team_task_runtime_adds_reasoning_summary_for_final_artifact` 通过。
- `test_agent_team_task_runtime_sanitizes_internal_planning_final_answer` 通过。
- `test_agent_team_task_runtime_fails_closed` 通过。

失败处理：
- 如果失败信息含 `selects`、`operator`、`JoinRequirement`、`extra_forbidden`、`literal_error`，优先按 QueryPlan 契约问题归类，不要先归因 SQL 慢。

### 1.2 前端契约测试

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-web
npm test -- src/assistant/agent-team-task-api.test.js src/assistant/agent-team-event-adapter.test.js src/assistant/chat-adapter.test.js src/assistant/workbench-api.test.js src/assistant/MyMessage.test.jsx src/components/artifact-card.test.jsx
npm run lint
npm run build
```

通过标准：
- `agent-team-task-api` 能解析 SSE `data:` JSON。
- `chat-adapter` 能把 Agent Team envelope 转为 assistant-ui 消息。
- artifact 展示测试不把 raw rows 直接塞进聊天消息。
- lint/build 无错误。

## 阶段 2：本地服务启动

### 2.1 启动基础设施

```bash
cd /Users/yangkai/code_place/study/python/Datalogue
docker compose up -d db redis
docker compose ps
```

通过标准：
- `datalogue-db` 与 `datalogue-redis` 为 healthy 或 running。

### 2.2 准备后端环境

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
test -f .env || cp .env.example .env
source .venv/bin/activate
alembic upgrade head
python scripts/seed_data.py
```

说明：
- `seed_data.py` 只在数据库没有数据源时初始化演示电商数据；如果已有数据源，它会跳过。
- 如果 `.env` 没有可用模型密钥，真实 AgentScope E2E 会阻塞在模型配置。阻塞时记录具体错误，例如 `AGENTSCOPE_DEFAULT_CREDENTIAL_NOT_CONFIGURED`。

启动 API：

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

健康检查：

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/dataset | python -m json.tool | head -80
```

通过标准：
- `/health` 返回 `{"status":"ok"}`。
- `/api/dataset` 至少有一个 active 数据集；演示环境通常有“电商订单分析”。

### 2.3 启动前端

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-web
npm install
VITE_API_PROXY_TARGET=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1 --port 5173
```

通过标准：
- 浏览器访问 `http://127.0.0.1:5173/chat` 成功。
- DevTools Network 中 `/api/*` 请求被代理到后端，无 CORS 错误。

## 阶段 3：API 级 E2E

先用 API 直接打 SSE，排除浏览器 UI 干扰。

```bash
curl -N -s \
  -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8000/api/agent-team/tasks/stream \
  -d '{
    "task_source": "chat",
    "task_type": "bi_query",
    "question": "统计 2026年4月到5月各地区 GMV，并按 GMV 从高到低排序",
    "dataset_id": 1,
    "session_id": "manual-e2e-api-001",
    "thread_id": "as_manual_e2e_api_001",
    "client_context": {"source": "manual-e2e"}
  }' | tee /tmp/datalogue-e2e-api-stream.log
```

如果本地数据集 id 不是 `1`，先从 `/api/dataset` 取“电商订单分析”的真实 id 后替换。

通过标准：
- SSE data JSON 中出现 `event_envelope.event_type`：
  - `task.started`
  - `agent.selected`
  - `message.completed`
  - `task.completed`
- `message.completed.payload.summary` 是中文业务摘要。
- 如果产生 artifact，payload 或 reasoning summary 中能看到 `artifact:` ref、行数或列数摘要。

失败分类：
- `422`：payload schema 不匹配，先核对 `AgentTeamTaskRequest` 字段。
- `500` 且日志含 credential：模型凭证未配置，归类为环境阻塞。
- `task.failed`：继续看后端日志和 `agentic_shell_task.error_payload_json`。
- 长时间无 final：优先查 QueryPlan 契约反复修复、AgentScope 迭代上限、旧 session/prompt 缓存。

## 阶段 4：浏览器真实 E2E

### 4.1 主查询链路

步骤：
1. 打开 `http://127.0.0.1:5173/chat`。
2. 新建对话。
3. 如页面有数据集选择，选择 active 数据集；演示数据优先选择“电商订单分析”。
4. 输入：

```text
统计 2026年4月到5月各地区 GMV，并按 GMV 从高到低排序
```

5. 等待最终回答完成。
6. 保存整页截图和 Network HAR。

页面通过标准：
- 用户消息出现在聊天区。
- assistant 最终回答出现中文业务摘要。
- 出现结果 artifact card 或可查看结果的入口。
- Workbench 有任务时间线、结果详情或 artifact 面板。
- 聊天区不出现原始 SQL、schema、raw rows、query_plan、DSL、内部 patch。

Network 通过标准：
- `POST /api/agent-team/tasks/stream` 状态为 `200`。
- SSE 按阶段返回，最终有 `message.completed` 和 `task.completed`。
- 如点击结果详情，出现 `GET /api/artifacts/<artifactRef>` 或 `GET /api/workbench/artifact/<artifactRef>`。

### 4.2 artifact 详情链路

步骤：
1. 点击结果卡片的“查看详情”或等价操作。
2. 记录触发的 API。
3. 截图保存详情面板。

通过标准：
- 详情面板展示表格列名和若干行数据。
- API 返回内容来自受控 `content_json.rows` / `content_json.columns` 或 Workbench view model。
- 前端没有把内部 SQL/schema/raw/query_plan 原样展示给普通聊天区。

### 4.3 多轮追问链路

在同一对话继续输入：

```text
继续按品类拆分，并只保留前 10 条
```

通过标准：
- 新请求沿用当前 thread/session，不新开无关对话。
- 回答能继承上一轮数据集或上下文。
- 若上下文不足，系统应给出澄清或安全失败，不编造结果。
- 数据库 `conversation_state` 或 message/task payload 可看到同一线程的连续记录。

### 4.4 候选数据集/澄清链路

仅当本地存在“生产经营管理系统日志数据集”或其他日志数据集时执行：

```text
查询杨凯2025年日志
```

通过标准：
- 如果数据集唯一命中，应进入查询并生成最终回答或 artifact。
- 如果候选不唯一，应显示候选数据集确认文案，而不是暴露英文内部规划文本。
- 如沿用历史验收数据，成功结果可接受“100 行、48 列”这类摘要。

若本地没有日志数据集：
- 记录为“数据前置条件缺失”，不要判定功能失败。

### 4.5 会话恢复链路

步骤：
1. 复制当前 URL。
2. 刷新页面。
3. 从左侧线程列表切换到刚才的对话。
4. 再次打开 artifact 详情。

通过标准：
- 历史用户消息、assistant 最终回答可恢复。
- artifact card 或 Workbench 详情仍能按 ref 拉取。
- 未发送内容的新草稿不应被持久化成数据库会话。

## 阶段 5：日志与数据库取证

### 5.1 后端日志

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
tail -n 300 logs/*.log | rg "agent_team|datalogue_describe_dataset_capability|datalogue_recall_query_assets|datalogue_execute_query_plan|bi_worker|QueryPlan|task.failed|AGENTSCOPE"
```

通过标准：
- 能看到 `agent_team.api.stream.accepted`。
- 能看到 `agent_team.api.stream.event` 和具体 event_type。
- 能看到 `agent_team.task.completed`。
- 如果走 BI Worker progressive path，优先确认工具顺序接近：
  - `datalogue_describe_dataset_capability`
  - `datalogue_recall_query_assets`
  - `datalogue_execute_query_plan`

### 5.2 数据库记录

```bash
docker exec -i datalogue-db psql -U datalogue -d datalogue <<'SQL'
\dt
select task_id, status, selected_agent, thread_id, message_id, artifact_refs_json, checkpoint_refs_json, created_at
from agentic_shell_task
order by id desc
limit 5;

select id, title, thread_id, dataset_id, archived, created_at, updated_at
from conversation
order by id desc
limit 5;

select id, conversation_id, role, left(content, 120) as content_preview, response_metadata, created_at
from message
order by id desc
limit 10;

select artifact_id, kind, dataset_id, conversation_id, message_id, trace_id, size_bytes, created_at
from query_artifact
order by id desc
limit 5;

select session_id, active_dataset_id, turn_index, status, updated_at
from conversation_state
order by updated_at desc
limit 5;
SQL
```

通过标准：
- `agentic_shell_task.status = completed`。
- `agentic_shell_task.thread_id/message_id` 能和前端当前会话关联。
- 有 artifact 时，`artifact_refs_json` 或 `query_artifact.artifact_id` 能和页面 ref 对上。
- `message` 中有 user 与 assistant 记录。

## 阶段 6：最终判定矩阵

| 检查项 | 通过标准 | 失败时优先看 |
|---|---|---|
| 服务健康 | `/health` ok，前端可访问 | 端口占用、uvicorn 旧进程、Vite proxy |
| SSE 主入口 | `/api/agent-team/tasks/stream` 200 且完整事件 | `agent_team.py`、Network payload、schema 422 |
| Agent Team runtime | task completed，DB 有记录 | `agent_team_runtime.py`、runner credential、AgentScope session |
| BI Worker 查询 | 有业务摘要或 artifact | QueryPlan 契约、工具顺序、模型输出 |
| Chat 展示 | 只有业务摘要和受控结果 | `chat-adapter.js`、`MyMessage.jsx`、安全过滤 |
| Workbench | 能展示 timeline/artifact | `/api/workbench/thread`、`/api/workbench/artifact` |
| artifact 详情 | rows/columns 可查看 | artifact ref、`query_artifact`、API 404 |
| 多轮追问 | 沿用线程和上下文 | `conversation_state`、thread_id/session_id |
| 会话恢复 | 刷新后历史可见 | `/api/conversation`、thread-list adapter |
| 安全边界 | 不泄露 SQL/schema/raw/query_plan | final payload、message metadata、artifact card |

## Claude 最终汇报格式

```markdown
## E2E 结论
- 总体结论：通过 / 部分通过 / 阻塞 / 失败
- 测试时间：
- 后端端口：
- 前端端口：
- 数据集：
- 线程/会话 ID：
- task_id：
- artifact_ref：

## 证据
- 页面截图：
- HAR 或 Network 截图：
- SSE 原始日志：
- 后端日志片段：
- 数据库查询输出：
- artifact API 输出摘要：

## 通过项
- ...

## 失败或阻塞项
- [P0/P1/P2] 现象：
  证据：
  初步根因：
  建议下一步：

## 风险
- ...
```

