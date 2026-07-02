# AgentScope 架构瘦身设计规格

## 1. 背景

当前 Datalogue 的 AgentScope 迁移经历了多个阶段：旧 `/chat/stream` 主链、Agentic Shell、BI LeadAgent K1/K2/K3、AgentScope native handoff、DatasetAgent Runtime、受控蓝图 fallback、Workbench refs、日志和脱敏安全矩阵陆续叠加。为了先跑通链路，很多能力临时堆在 `app/services/` 下。

现在新的目标已经收敛：

```text
AgenticLeadAgent
  -> BI Agent
      -> Dataset Skill / SOUL
      -> BI Toolkit
      -> Dataset Toolchain
      -> SQL Control Plane
      -> Artifact / Trace / Checkpoint
```

因此下一步不应继续在 `services/` 下堆功能，而要先重建目录边界，再迁移能力，最后删除旧壳。

## 2. 用户已确认的架构决策

### 2.1 命名

正式命名采用：

```text
AgenticLeadAgent   顶层任务主控 Agent
BI Agent           问数专业 ReAct Agent
Dataset Skill      BI Agent 的查数说明书
BI Toolkit         BI Agent 可调用工具集合
Dataset Toolchain  确定性执行链
SQL Control Plane  BI Agent 持有的 SQL 控制面
```

旧命名处理：

- `BI LeadAgent` 作为历史名称退役。
- `DatasetAgentRuntime` 不再作为目标架构中的独立 Agent/Runtime 盒子。
- 现有旧模块可保留迁移期 adapter，但不能继续作为新代码扩展入口。

### 2.2 Runtime 目录命名

目录使用 `app/runtime/`，不再使用 `agent_runtime/agentscope/` 这类双层命名。AgentScope 2.0 是目标 runtime 底座，不作为边角适配器隐藏在目录名里。

### 2.3 Middleware 归属

所有 AgentScope middleware 单独归入：

```text
app/middlewares/
```

Middleware 是横切层，不属于某个 Agent 私有目录。`AgenticLeadAgent`、`BI Agent` 和后续 `ReportAgent/PythonAgent/AuditAgent` 都应复用同一套 middleware。

### 2.4 SQL 可见边界

SQL 可以上移到 `BI Agent`，但必须以 control plane 对象流转：

```text
BI Agent 可以持有 raw SQL / SQL AST / compiled_query_ref / guard_result。
AgenticLeadAgent 默认只接收 sql_ref / sql_summary / guard_status。
用户可见 SSE / API / 日志 / final answer 永不展示 raw SQL。
```

不能只依赖 prompt 约束“不要暴露 SQL”。必须由 middleware、DTO sanitizer、event projection 和测试共同保证。

## 3. 目标目录结构

目标结构：

```text
datalogue-api/app/
  agents/
    agentic_lead_agent/
      factory.py
      prompt.py
      runner.py
      tools.py

    bi_agent/
      factory.py
      prompt.py
      runner.py

  runtime/
    event_stream.py
    permissions.py
    session.py
    skill_registry.py
    state.py
    tool_registry.py

  middlewares/
    lifecycle.py
    output_projection.py
    permission_guard.py
    sanitizer.py
    sql_control_plane.py
    tracing.py

  bi/
    skill/
      SKILL.md
      SOUL.md

    toolkit/
      factory.py
      tools.py

    toolchain/
      asset_catalog.py
      artifact_writer.py
      compiler.py
      executor.py
      query_planner.py
      repair.py
      sql_guard.py

    sql_control/
      models.py
      sanitizer.py
      store.py

  events/
    envelope.py
    projection.py
    sse.py

  persistence/
    agent_state_store.py
    artifact_store.py
    audit_store.py
    checkpoint_store.py
    task_store.py
```

`app/services/` 只允许保留迁移期薄 adapter。完成后，核心 Agent、runtime、BI、events、persistence 能力不应继续从 `services/` 暴露新入口。

## 4. 目录职责

### 4.1 `agents/`

只放具体 Agent 的组装和运行入口。

`agents/agentic_lead_agent/`：

- 创建 AgentScope `Agent(name="agentic_lead_agent")`。
- 注册调用专业 Agent 的 tools。
- 消费 AgentScope `reply_stream()`。
- 将事件交给 `events/projection.py`。
- 不直接注册 Dataset 原子工具。
- 默认不持有 raw SQL。

`agents/bi_agent/`：

- 创建 AgentScope `Agent(name="bi_agent")`。
- 注册 Dataset Skill 和 BI Toolkit。
- 负责问数 ReAct loop。
- 持有 SQL control plane。
- 产出 answer summary、artifact refs、checkpoint refs、sql refs。

### 4.2 `runtime/`

只放 AgentScope runtime 公共能力：

- AgentState 加载和保存。
- session/run 生命周期。
- permission context 和 rule 装配。
- tool registry 和 skill registry。
- AgentScope event stream 基础封装。

`runtime/` 不放 BI 业务规则，不放 SQL 编译执行，不放 artifact 业务写入。

### 4.3 `middlewares/`

统一管理所有 AgentScope middleware：

- `lifecycle.py`：记录 Agent/run/tool 生命周期。
- `tracing.py`：接 OpenTelemetry 或内部 trace span。
- `sanitizer.py`：清洗 SQL、schema、raw rows、query_plan、repair patch。
- `permission_guard.py`：工具权限和 fail-closed。
- `sql_control_plane.py`：识别、隔离和投影 SQL control plane 对象。
- `output_projection.py`：阻止 control plane 进入用户可见事件。

Middleware 不直接执行业务查询。它只能观察、拦截、改写或投影。

### 4.4 `bi/`

放问数领域能力。

`bi/skill/`：

- `SKILL.md`：BI Agent 如何使用数据集查询能力。
- `SOUL.md`：问数边界、口径、安全红线和输出规范。

`bi/toolkit/`：

- 组装 AgentScope `Toolkit`。
- 注册 BI Agent 可见的工具 schema。
- 将工具调用转入 `bi/toolchain/`。

`bi/toolchain/`：

- 确定性执行链。
- 包括资产目录、QueryGraph/DSL 规划、SQL 编译、SQL Guard、执行、修复、artifact 写入。
- 这里可以处理 raw SQL、schema context、raw rows，但不能直接对用户输出。

`bi/sql_control/`：

- 定义 SQL control plane 对象。
- 保存 `compiled_query_ref`、raw SQL、guard result、执行状态。
- 提供 sanitizer 和只读摘要投影。

### 4.5 `events/`

放 Datalogue 对外事件协议：

- Datalogue Event Envelope。
- AgentScope event 到 Datalogue event 的投影。
- SSE 输出封装。

前端和 Workbench 只依赖 `events/` 的稳定 envelope，不依赖 AgentScope Python SDK 内部对象。

### 4.6 `persistence/`

放 Datalogue 真相源写入：

- AgentState store。
- task/run store。
- artifact store。
- audit store。
- checkpoint store。

这些模块负责“系统最终承认什么”，不能被 Agent 文本输出替代。

## 5. 文件迁移地图

### 5.1 Agentic Shell / 顶层 Agent

| 当前文件 | 目标位置 | 阶段 | 处理 |
| --- | --- | --- | --- |
| `app/services/agentic_shell.py` | `app/agents/agentic_lead_agent/` + `app/runtime/` | P1 | 拆出 AgenticLeadAgent factory、runner 和 registry |
| `app/services/agentic_shell_task_runtime.py` | `app/agents/agentic_lead_agent/runner.py` + `app/persistence/task_store.py` | P1 | 任务运行和落库拆分 |
| `app/services/agentic_shell_event_projection.py` | `app/events/projection.py` | P1 | 改为统一 event projection |
| `app/services/agentic_shell_writers.py` | `app/persistence/task_store.py` / `checkpoint_store.py` | P1 | 写回逻辑迁出 services |
| `app/api/agentic_shell.py` | 保留 | P1 | API 只调用新 runner，不承载业务执行 |

### 5.2 BI Agent

| 当前文件 | 目标位置 | 阶段 | 处理 |
| --- | --- | --- | --- |
| `app/services/bi_lead_agent/*` | `app/agents/bi_agent/` + `app/bi/` + `app/persistence/` | P2 | 按职责拆分，旧包保留 adapter |
| `app/services/bi_lead_agent/native_handoff.py` | `app/agents/bi_agent/runner.py` | P2 | handoff 语义收敛为 BI Agent 内部 run |
| `app/services/bi_lead_agent/dataset_agent_factory.py` | `app/agents/bi_agent/factory.py` | P2 | 不再创建独立 DatasetAgentRuntime |
| `app/services/bi_lead_agent/capabilities.py` | `app/bi/toolkit/factory.py` | P2 | 能力面归入 BI Toolkit |
| `app/services/bi_lead_agent/handoff_service.py` | `app/persistence/task_store.py` + `app/agents/bi_agent/runner.py` | P2 | 状态写入和 Agent 运行分离 |

### 5.3 Dataset 执行链

| 当前文件 | 目标位置 | 阶段 | 处理 |
| --- | --- | --- | --- |
| `app/services/agentscope_dataset_runtime.py` | `app/bi/toolchain/` + `app/agents/bi_agent/runner.py` | P2 | 去掉独立 runtime 概念，保留状态机能力 |
| `app/services/agentic_dataset_runtime.py` | `app/bi/toolchain/` | P2 | 如仍有活引用，按功能迁移；否则删除 |
| `app/services/bi_tools/atomic.py` | `app/bi/toolkit/tools.py` + `app/bi/toolchain/*` | P2 | ToolBase wrapper 与确定性执行拆分 |
| `app/services/subagent_planning/*` | `app/bi/toolchain/asset_catalog.py` / `query_planner.py` | P2 | 规划和资产召回归入 BI toolchain |
| `app/services/query_plan_compiler.py` | `app/bi/toolchain/compiler.py` | P2 | SQL 编译归入 toolchain |
| `app/services/sql_dialect_adapter.py` | `app/bi/toolchain/compiler.py` 或 `sql_guard.py` | P2 | 方言适配归入 toolchain |
| `app/services/sql_preview.py` | `app/bi/toolchain/executor.py` | P2 | 执行预览归入 executor |
| `app/services/repair_patch.py` | `app/bi/toolchain/repair.py` | P2 | 修复链归入 repair |
| `app/services/analysis_blueprint.py` | `app/bi/toolchain/query_planner.py` 或独立 `blueprint.py` | P2 | 蓝图执行作为 toolchain 能力 |

### 5.4 Middleware / Runtime

| 当前文件 | 目标位置 | 阶段 | 处理 |
| --- | --- | --- | --- |
| `app/services/agentscope_middlewares/*` | `app/middlewares/` | P1 | 统一 middleware 目录 |
| `app/services/agentic_shell_logging.py` | `app/middlewares/lifecycle.py` | P1 | 生命周期日志归入 middleware |
| `app/services/observability/agentscope_otel.py` | `app/middlewares/tracing.py` | P1 | OTel 接入归入 tracing middleware |
| `app/services/agentscope_runtime_driver.py` | `app/runtime/event_stream.py` / `session.py` | P1 | Runtime driver 改为公共 runtime |
| `app/services/agentscope_chat_bridge.py` | `app/runtime/session.py` 或删除 | P3 | 若只服务旧 chat bridge，迁移后删除 |

### 5.5 Events / Persistence

| 当前文件 | 目标位置 | 阶段 | 处理 |
| --- | --- | --- | --- |
| `app/services/agentscope_event_adapter.py` | `app/events/projection.py` | P1 | 事件投影统一 |
| `app/services/agentscope_event_projection.py` | `app/events/projection.py` | P1 | 与 event adapter 合并 |
| `app/services/agentscope_mirror.py` | `app/persistence/agent_state_store.py` 或 `task_store.py` | P2 | mirror 语义按真相源重新命名 |
| `app/services/agentscope_thread_resolver.py` | `app/persistence/task_store.py` | P2 | thread/task 解析归入 persistence |
| `app/services/artifact_store.py` | `app/persistence/artifact_store.py` | P2 | artifact store 从 services 迁出 |
| `app/services/workbench_actions.py` | `app/persistence/checkpoint_store.py` + API action layer | P3 | Workbench action 与 checkpoint 写入分离 |
| `app/services/workbench_view_model.py` | `app/events/projection.py` 或 API view model | P3 | 保持用户可见投影，不混入 runtime |

## 6. 三阶段执行计划

### P1：目录边界重建和 adapter 骨架

目标：让新目录存在，并让新代码只能往新目录写。

交付：

- 新增 `agents/`、`runtime/`、`middlewares/`、`bi/`、`events/`、`persistence/` 包。
- 迁移 middleware 和 event projection 这类低风险横切逻辑。
- 新增 adapter，让旧入口调用新目录，但不改变用户可见行为。
- 补 import 兼容测试，确保旧路径暂时仍能运行。

验收：

```text
python3 -m compileall datalogue-api/app -q
pytest tests/test_agentic_shell_task_runtime.py tests/test_bi_lead_agent_native_handoff.py -q
pytest tests/test_agentscope_dataset_runtime_bridge.py -q
```

### P2：BI Agent 和 Dataset Toolchain 迁移

目标：让 `BI Agent` 成为问数主 Agent，Dataset 执行链注册进 BI Agent 的 Skill / Toolkit。

交付：

- 新增 `agents/bi_agent/`。
- 新增 `bi/skill/SKILL.md` 和 `bi/skill/SOUL.md`。
- 将 `bi_tools/atomic.py` 拆成 ToolBase wrapper 与 `bi/toolchain/*`。
- 将 `agentscope_dataset_runtime.py` 的有效状态机能力迁入 BI Agent runner 和 toolchain。
- 建立 `bi/sql_control/`，让 SQL control plane 成为显式对象。
- 旧 `bi_lead_agent` 包只保留 adapter，不再扩展新能力。

验收：

```text
pytest tests/test_bi_lead_agent_native_handoff.py tests/test_bi_lead_agent_dataset_agent_factory.py -q
pytest tests/test_agentscope_dataset_runtime_bridge.py tests/test_agentic_shell_task_runtime.py -q
python3 -m compileall datalogue-api/app -q
```

需要新增或迁移测试：

- `tests/test_bi_agent_runtime.py`
- `tests/test_bi_agent_sql_control.py`
- `tests/test_bi_toolchain_security.py`

### P3：删除旧壳和服务目录瘦身

目标：删除旧 `BILeadAgent`、`DatasetAgentRuntime`、旧 handoff/fallback/adapter 壳，`services/` 不再作为核心代码堆积区。

交付：

- 删除或降级旧命名模块。
- 删除旧 handoff / fallback 代码路径。
- 清理测试文件旧命名。
- 更新文档入口和架构图。
- `services/` 只保留仍有明确必要的兼容层，或继续分批清空。

验收：

```text
rg "BILeadAgent|BI LeadAgent|DatasetAgentRuntime|DatasetAgent Runtime" datalogue-api/app docs -g '!docs/archive/**'
rg "agentscope_dataset_runtime|bi_lead_agent" datalogue-api/app
pytest -q
cd datalogue-web && npm test -- src/assistant/chat-adapter.test.js src/assistant/MyMessage.test.jsx
cd datalogue-web && npm run lint && npm run build
git diff --check
```

P3 的 `rg` 不是要求历史归档为 0，而是要求当前入口、当前文档和运行时代码不再使用旧概念作为目标架构。

## 7. 安全和行为不变量

改造过程中以下行为不能退化：

- 用户可见层不展示 raw SQL、schema、raw rows、query_plan、repair patch。
- `BI Agent` 可持有 SQL control plane，但必须有 `may_display_to_user=false` 等硬标签。
- `AgenticLeadAgent` 默认只收到 `sql_ref/sql_summary/guard_status/artifact_ref`。
- Artifact、checkpoint、trace、task 状态仍落到 Datalogue 可控真相源。
- 旧页面回放、Workbench refs、artifact 自动展示不能因为目录迁移中断。
- 出错时继续 fail-closed，不能为了兼容恢复泛化 direct SQL fallback。

## 8. 测试策略

每个阶段至少包含三类测试：

1. **结构测试**：旧入口能导入，新目录能导入，关键 adapter 指向新实现。
2. **安全测试**：SQL/schema/raw rows/control plane 不进入用户可见 envelope、API response、日志摘要。
3. **行为测试**：Agentic Shell task stream、BI Agent 查询、artifact refs、checkpoint refs、Workbench 展示仍闭环。

真实链路验收在 P2/P3 做：

```text
本地启动后端和前端
使用 dataset_id=10 或 dataset_id=12 跑一次真实问数
确认页面答案、artifact、DB refs、日志和 trace_id 对齐
扫描用户可见 payload 未泄露 SQL/schema/raw rows
```

## 9. 提交和迁移规则

- 每个阶段单独提交，不把 P1/P2/P3 混在一个提交里。
- 每个阶段只做目录边界相关迁移，不顺手重写业务逻辑。
- 如果发现某个旧文件仍有真实运行价值，先迁移到目标目录，再删除旧壳。
- 如果某个文件只是历史证据，移动到 archive 或保留在历史文档中，不改写历史验收事实。
- 新增 Python 文件必须按项目模板写文件头，职责说明用中文补完整。

## 10. 第一阶段最小实施入口

P1 可以从以下文件开始，因为风险低、边界清晰：

```text
app/services/agentscope_middlewares/*
  -> app/middlewares/*

app/services/agentic_shell_event_projection.py
app/services/agentscope_event_adapter.py
app/services/agentscope_event_projection.py
  -> app/events/projection.py

app/services/agentic_shell_logging.py
app/services/observability/agentscope_otel.py
  -> app/middlewares/lifecycle.py / tracing.py
```

P1 不迁移 SQL 编译、执行和 repair 主链。那些属于 P2，必须等 middleware/event/runtime 边界稳定后再动。
