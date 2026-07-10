# Phase B — 目录语义迁移计划

> 前提文档：`docs/architecture/目录治理与模块边界.md`（Phase A 治理协议）
> 状态：**待评审**，逐步按步骤执行，每步需用户确认后再动代码。
> 创建日期：2026-07-09

---

## 0. 设计决策（Phase B 命名约定）

经讨论确认的三条命名原则，贯穿所有步骤：

### 0.1 目录中不出现框架名

`agentscope_service/`、`agentscope_runtime/`、`agents/` 中的 "agentscope" 是实现细节，不是业务概念。Phase B 完成后这些前缀全部消失，代之以语义目录：

| 旧的框架导向命名 | 新的语义命名 | 含义 |
|---|---|---|
| `agentscope_runtime/` | `runtime/engine/` | 运行时基础设施（框架无关） |
| `agentscope_service/` | 解散，拆入 `runtime/engine/` + `domains/` | 各归各域 |
| `agents/bi_agent/` | `domains/bi/agent/` | BI Agent 是 BI 领域的子域 |
| `graph/` | 解散，`llm.py` 进 `core/` | 历史残片 |

### 0.2 文件里可以出现框架名

`from agentscope import ...`、`from agentscope.message import ...` 这类框架 import 不禁止。目录名干净，import 实话实说——框架换掉时 grep 框架名就能找到所有改点。

### 0.3 目录名已含领域语义时，文件名不冗余前缀

例如 `domains/bi/worker/` 下文件名不带 `bi_worker_` 前缀：

```
# 旧（冗余）
domains/bi/worker/bi_worker_context.py
domains/bi/worker/bi_worker_contracts.py

# 新（简洁）
domains/bi/worker/context.py
domains/bi/worker/contracts.py
```

---

## 1. 目标目录结构

Phase B 完成后 `app/` 下的目录为：

```
app/
├── main.py                         # FastAPI 入口（不变）
├── api/                            # HTTP 路由（不变）
├── middlewares/                    # 中间件（不变）
├── core/                           # 基础设施（吸收 graph/llm.py）
│   ├── config.py
│   ├── database.py
│   ├── logging.py
│   ├── security.py
│   └── llm.py                      # ← 从 graph/llm.py 迁入
│
├── runtime/                        # 运行时基础设施（框架无关）
│   ├── agent_team_runtime.py       # Agent Team 任务运行时（保持）
│   ├── thread_resolver.py          # 线程 ID 解析（保持）
│   └── engine/                     # ← 吸收 agentscope_service/ 的框架桥接层
│       ├── app_factory.py          # 子应用挂载
│       ├── registry.py             # Agent/Team 注册
│       ├── runner.py               # 任务运行器
│       ├── projection.py           # 事件投影
│       ├── client.py               # 服务客户端
│       ├── credentials.py          # 凭证管理
│       └── otel_setup.py           # 追踪初始化
│
├── domains/
│   ├── agent_team/                 # 多智能体主链业务
│   │   ├── runner.py               # facade（→ runtime/engine/runner）
│   │   ├── projection.py           # facade（→ runtime/engine/projection）
│   │   ├── team_templates.py       # 团队模板（业务，从 agentscope_service 迁）
│   │   ├── task_context.py         # 任务上下文（业务）
│   │   ├── progress_bridge.py      # 前端进度投递
│   │   └── worker_logging.py       # 业务日志
│   │
│   ├── bi/                         # BI 领域（完整收拢）
│   │   ├── agent/                  # ← 从 agents/bi_agent/ 迁入
│   │   │   ├── capabilities.py
│   │   │   ├── confirmation_service.py
│   │   │   ├── dataset_agent_factory.py
│   │   │   ├── handoff_events.py
│   │   │   ├── handoff_port.py
│   │   │   ├── handoff_service.py
│   │   │   ├── native_handoff.py
│   │   │   ├── run_service.py
│   │   │   └── runtime_context.py
│   │   ├── worker/                 # ← 从 agentscope_service/bi_worker_* 迁入
│   │   │   ├── context.py          # bi_worker_context.py
│   │   │   ├── contracts.py        # bi_worker_contracts.py
│   │   │   ├── runtime.py          # bi_worker_runtime.py
│   │   │   ├── timeline_cache.py   # bi_worker_timeline_cache.py
│   │   │   ├── validator.py        # bi_worker_validator.py
│   │   │   └── dataset_query.py    # dataset_query_executor.py
│   │   ├── agent_services.py       # BI Agent 门面（保持）
│   │   ├── worker_query.py         # Worker 查询门面（保持）
│   │   ├── skill/                  # ← 从 app/bi/skill/ 迁入
│   │   │   ├── dataset_query.py
│   │   │   └── runtime_bridge.py
│   │   └── toolkit/                # ← 从 app/bi/toolkit/ 迁入
│   │       └── atomic.py
│   │
│   ├── data_source/                # 数据源领域（保持现状，实体已在）
│   └── query_execution/            # 查询执行领域（吸收 utils/ SQL 工具）
│       ├── compiler.py
│       ├── dialect/
│       ├── guard.py
│       ├── preview.py
│       ├── sql_diagnosis.py        # ← 从 utils/ 迁入
│       ├── sql_dialect.py          # ← 从 utils/ 迁入
│       ├── sql_guard.py            # ← 从 utils/ 迁入
│       ├── schema_formatter.py     # ← 从 utils/ 迁入
│       ├── query_constraints.py    # ← 从 utils/ 迁入
│       ├── sample_data.py          # ← 从 utils/ 迁入
│       ├── column_labels.py        # ← 从 utils/ 迁入
│       └── compiler_context.py     # ← 从 utils/ 迁入
│
├── models/                         # ORM 模型（不变）
├── schemas/                        # Pydantic 契约（不变）
├── prompts/                        # 集中 Prompt 常量（不变）
├── safety/                         # 输出安全（不变）
├── events/                         # 事件投影（不变）
├── services/                       # 应用服务——仅保留 facade 兼容层
├── utils/                          # 无归属工具（净身在 Step 6 后）
└── contracts/                      # 契约文档（不变）

删掉的目录：
✗ app/agentscope_service/           → 解散到 runtime/engine/ + domains/
✗ app/agentscope_runtime/           → 合并到 runtime/engine/
✗ app/agents/                       → bi_agent/ 进 domains/bi/agent/，agentscope_model.py 进 core/
✗ app/graph/                        → llm.py 进 core/
✗ app/bi/                           → skill/ + toolkit/ 进 domains/bi/
```

---

## 2. 迁移硬约束（每步强制执行）

1. **不改主链语义**：AgentScope / BI Worker / Agent Team 的对外协议、事件字段、消息格式不变。
2. **不改 API 路径和请求响应结构**。
3. **每步先建目标目录 + facade 转发，再逐文件搬实体，最后删旧文件**——保证每次 commit 都可回滚。
4. **每步完成后跑一次完整 pytest**，结果作为完工判据。
5. **每步单独一个 commit**，commit message 注明 `phase-b-step-N:` 前缀。

---

## 3. 迁移步骤

---

### Step 1：`graph/llm.py` 归位 + `agentscope_model.py` 归位

**优先级**：最高（无依赖、fan-in 极小、改动最安全）。

#### 1a: `graph/llm.py` → `core/llm.py`

当前 fan-in（3 个文件）：
```
app/api/llm.py
app/services/annotation.py
app/services/blueprint_analyzer.py
```

操作：
1. 创建 `app/core/llm.py`，把 `app/graph/llm.py` 内容原样搬过去。
2. 在 `app/graph/__init__.py` 加 facade 转发：

```python
# app/graph/__init__.py（兼容过渡）
from app.core.llm import get_llm, AgentScopeChatClient  # noqa: F401
__all__ = ["get_llm", "AgentScopeChatClient"]
```

3. 改 3 个调用点的 import：
   - `app/api/llm.py`：`from app.graph.llm import ...` → `from app.core.llm import ...`
   - `app/services/annotation.py`：同上
   - `app/services/blueprint_analyzer.py`：同上

4. 验证：`pytest tests/` 全绿 → 删除 `app/graph/` 目录 → 再次跑测试。
5. Step 1a 完成。`app/graph/` 目录消失。

#### 1b: `agents/agentscope_model.py` → `core/agentscope_model.py`

当前 fan-in：**0**（没有任何外部模块 import 它）。操作：

1. 把 `app/agents/agentscope_model.py` 移到 `app/core/agentscope_model.py`。
2. 在 `app/agents/__init__.py` 中加 facade。
3. 验证测试全绿。

> **决策点**：这个文件当前 fan-in = 0，是否真的要保留？如果你觉得可以删除，Step 1b 可改为"确认无人使用后删除"。

---

### Step 2：`agents/` → `domains/bi/agent/`

**优先级**：高（收拢 BI Agent 到 BI 领域下）。

#### 迁移映射

| 旧路径 | 新路径 |
|---|---|
| `app/agents/bi_agent/*.py` | `app/domains/bi/agent/*.py` |
| `app/agents/__init__.py` | 变为 facade |

#### 外部 fan-in（需改 import 的文件）

```
app/agentscope_service/bi_worker_runtime.py    → from app.domains.bi.agent import ...
app/domains/bi/agent_services.py               → 同域内，改 import
tests/test_bi_lead_agent_capabilities.py
tests/test_bi_lead_agent_dataset_agent_factory.py
tests/test_bi_lead_agent_handoff_port.py
tests/test_bi_lead_agent_native_handoff.py
tests/test_bi_lead_agent_services.py
```

操作：

1. 创建 `app/domains/bi/agent/` 目录。
2. 复制 `app/agents/bi_agent/` 下所有 `.py` 到 `app/domains/bi/agent/`，内部相对 import 同步改。
3. 在 `app/agents/__init__.py` 加 facade 转发，保持 `from app.agents.bi_agent import ...` 仍然可用。
4. 逐个改 7 个外部调用点。
5. 验证所有测试 → 删除 `app/agents/` 目录。
6. `app/agents/` 目录消失。

---

### Step 3：`agentscope_service/bi_worker_*` + `dataset_query_executor` → `domains/bi/worker/`

**优先级**：高（BI Worker 五件套归属错误最明显）。

#### 迁移映射

| 旧路径 | 新路径 |
|---|---|
| `app/agentscope_service/bi_worker_context.py` | `app/domains/bi/worker/context.py` |
| `app/agentscope_service/bi_worker_contracts.py` | `app/domains/bi/worker/contracts.py` |
| `app/agentscope_service/bi_worker_runtime.py` | `app/domains/bi/worker/runtime.py` |
| `app/agentscope_service/bi_worker_timeline_cache.py` | `app/domains/bi/worker/timeline_cache.py` |
| `app/agentscope_service/bi_worker_validator.py` | `app/domains/bi/worker/validator.py` |
| `app/agentscope_service/dataset_query_executor.py` | `app/domains/bi/worker/dataset_query.py` |

#### 外部 fan-in（在 agentscope_service 内 + 测试）

```
# agentscope_service 内部互引用（同包内，改名同时改）
app/agentscope_service/bi_worker_context.py      → app/agentscope_service/bi_worker_runtime.py
app/agentscope_service/bi_worker_runtime.py      → app/agentscope_service/tools.py, worker_logging.py
app/agentscope_service/bi_worker_validator.py    → app/agentscope_service/dataset_query_executor.py

# 外部模块
app/domains/bi/worker_query.py   → 改 import

# 测试
tests/test_agentscope_service_tools.py
tests/test_bi_worker_progressive_context_*.py
tests/test_bi_worker_query_runtime.py
tests/test_bi_worker_query_validator.py
tests/test_bi_worker_timeline_cache.py
```

操作：

1. 创建 `app/domains/bi/worker/` 目录。
2. 搬 6 个文件过去，去掉 `bi_worker_` 前缀，内部 import 同步改。
3. 在 `app/agentscope_service/__init__.py` 加 facade。
4. 改 2 个外部调用点 + 5-6 个测试文件。
5. 验证测试 → `app/agentscope_service/` 删掉这 6 个文件。

---

### Step 4：`agentscope_service/` 剩余文件解散 —— 引擎归 `runtime/engine/`，业务归 `domains/agent_team/`

**优先级**：中（改动面积最大，但收益最高——"目录体现职责"的最终一步）。

#### 迁移映射

| 旧路径 | 新路径 | 归属理由 |
|---|---|---|
| `agentscope_service/app_factory.py` | `runtime/engine/app_factory.py` | 框架桥接 |
| `agentscope_service/registry.py` | `runtime/engine/registry.py` | 框架桥接 |
| `agentscope_service/runner.py` | `runtime/engine/runner.py` | 框架桥接 |
| `agentscope_service/projection.py` | `runtime/engine/projection.py` | 框架桥接 |
| `agentscope_service/client.py` | `runtime/engine/client.py` | 框架附件 |
| `agentscope_service/credentials.py` | `runtime/engine/credentials.py` | 框架附件 |
| `agentscope_service/otel_setup.py` | `runtime/engine/otel_setup.py` | 框架附件 |
| `agentscope_service/tools.py` | `runtime/engine/tools.py` | 框架工具集 |
| `agentscope_service/team_templates.py` | `domains/agent_team/team_templates.py` | 团队编排是业务 |
| `agentscope_service/task_context.py` | `domains/agent_team/task_context.py` | 任务上下文是业务 |
| `agentscope_service/progress_bridge.py` | `domains/agent_team/progress_bridge.py` | 前端进度是业务 |
| `agentscope_service/worker_logging.py` | `domains/agent_team/worker_logging.py` | 业务日志 |

#### 前置条件

- Step 2、Step 3 已完成（`bi_agent/` 和 `bi_worker_*` 已搬离）。
- `domains/bi/` 下的 `agent_services.py`、`worker_query.py` 已改为指向新路径。

#### 外部 fan-in 矩阵（需改 import 的调用方）

**runtime/engine/ 的外部调用方：**
```
app/main.py                                    → create_embedded_agentscope_app
app/api/agent_team.py                          → runner, registry
app/api/agentscope_control_plane.py            → runner, registry, projection
app/api/llm.py                                 → client (tools 间接)
app/domains/agent_team/runner.py               → facade, 改指向 runtime/engine/
app/domains/agent_team/registry.py             → facade, 改指向 runtime/engine/
app/domains/bi/agent_services.py               → registry (subagent templates)
app/domains/bi/worker_query.py                 → dataset_query_executor (已在 Step 3 搬)
app/services/llm_config.py                     → tools
```

**domains/agent_team/ 的外部调用方：**
```
app/api/agent_team.py                          → task_context, team_templates
app/api/agentscope_control_plane.py            → progress_bridge
```

操作（分 4a 和 4b 两个子步骤，各跑一次测试）：

**Step 4a**：引擎层（`runtime/engine/`）先建、先切：
1. 创建 `app/runtime/engine/` 目录。
2. 搬 8 个框架文件（app_factory / registry / runner / projection / client / credentials / otel_setup / tools）到 `runtime/engine/`。
3. 在 `agentscope_service/__init__.py` 加 facade 转发全部公开导出。
4. 改所有外部调用点（`main.py`, `api/agent_team.py`, `api/agentscope_control_plane.py`, `api/llm.py`, `services/llm_config.py`, 以及 `domains/agent_team/runner.py`, `domains/agent_team/registry.py`, `domains/bi/agent_services.py`）。
5. 运行测试 → 全绿 → `agentscope_service/` 删除这 8 个文件。

**Step 4b**：业务层（`domains/agent_team/`）再接盘：
1. 搬剩余 4 个业务文件（team_templates / task_context / progress_bridge / worker_logging）到 `domains/agent_team/`。
2. 改外部调用点（`api/agent_team.py`, `api/agentscope_control_plane.py`）。
3. 运行测试 → 全绿 → `agentscope_service/` 目录完全为空 → 删除。

**Step 4c**：删除 `agentscope_runtime/`（4 个 facade 文件）：
- 此时所有外部模块已指向 `runtime/engine/` 或 `domains/agent_team/`。
- 确认无任何 import 引用 → 删除 `app/agentscope_runtime/`。

Step 4 完成后，`app/agentscope_service/` 和 `app/agentscope_runtime/` 目录全部消失。

---

### Step 5：`services/` 残余清理 —— facade 对接 + 目标落地

**优先级**：中（services 里 domain 和 service 已有重叠，需要收尾）。

当前状况：
- `services/datasource.py` 实体已迁 `domains/data_source/service.py`，services 版是 facade。
- `services/query_plan_compiler.py` 实体已迁 `domains/query_execution/compiler.py`。
- 但大部分 services 文件还在用旧的 `from app.agentscope_service import ...` 路径。

这一步不搬实体（实体大部分已在 Step 1-4 搬完），而是：

**5a**：确认 services 文件中所有 import 改为新路径（`runtime/engine/`、`domains/`）。

**5b**：对以下"纯 facade"文件（实体已在 domains），加 `DeprecationWarning` 注释，标记将在 Phase C 删除：

```python
# services/datasource.py           → 实体在 domains/data_source/service.py
# services/query_plan_compiler.py  → 实体在 domains/query_execution/compiler.py
# services/repair_plan.py          → 实体在 domains/query_execution/repair_plan.py
# services/sql_dialect_adapter.py  → 实体在 domains/query_execution/dialect/adapter.py
# services/sql_preview.py          → 实体在 domains/query_execution/preview.py
# services/analysis_blueprint.py   → 实体在 services/analysis_blueprint.py（暂不动）
# services/artifact_store.py       → 实体在 domains/query_execution/artifact_store.py
```

**5c**：不动的 services 文件（纯业务服务，无领域副本）：
```
services/agentscope_chat_bridge.py  → 保留（Bridge 层，不是领域实体）
services/agentscope_mirror.py       → 保留（镜像同步是服务，不是领域）
services/annotation.py              → 保留
services/blueprint_analyzer.py      → 保留
services/capability_manifest.py     → 保留
services/dataset_manifest.py        → 保留（数据集清单是服务）
services/dataset_router.py          → 保留
services/llm_config.py              → 保留（全局 LLM 配置入口）
services/message_feedback.py        → 保留
services/title_generator.py         → 保留
services/workbench_actions.py       → 保留
services/workbench_view_model.py    → 保留
```

验证：所有测试全绿。

---

### Step 6：`utils/` 中 SQL / 查询工具 → `domains/query_execution/`

**优先级**：中（一次性迁 8 个文件，全部只服务查询领域）。

#### 迁移映射

| 旧路径 | 新路径 |
|---|---|
| `app/utils/sql_diagnosis.py` | `app/domains/query_execution/sql_diagnosis.py` |
| `app/utils/sql_dialect.py` | `app/domains/query_execution/sql_dialect.py` |
| `app/utils/sql_guard.py` | `app/domains/query_execution/sql_guard.py` |
| `app/utils/schema_formatter.py` | `app/domains/query_execution/schema_formatter.py` |
| `app/utils/query_constraints.py` | `app/domains/query_execution/query_constraints.py` |
| `app/utils/sample_data.py` | `app/domains/query_execution/sample_data.py` |
| `app/utils/column_labels.py` | `app/domains/query_execution/column_labels.py` |
| `app/utils/compiler_context.py` | `app/domains/query_execution/compiler_context.py` |

#### 外部 fan-in（需改 import 的文件）

```
app/bi/toolkit/atomic.py
app/domains/query_execution/compiler.py
app/domains/query_execution/dialect/adapter.py
app/domains/query_execution/guard.py
app/services/analysis_blueprint.py
app/services/query_plan_compiler.py
app/services/sql_dialect_adapter.py
app/services/sql_preview.py
app/domains/data_source/... （数个）
```

操作：

1. 搬 8 个文件到 `domains/query_execution/`。
2. 在 `app/utils/__init__.py` 中加 facade 转发（`__getattr__` 懒加载）。
3. 改约 10+ 个调用点的 import。
4. 验证测试全绿 → `app/utils/` 中删除这 8 个文件。

Step 6 完成后，`app/utils/` 留下的全是真正无领域归属的通用工具（`think.py`、`token.py`、`json_utils.py`）。

---

### Step 7（可选收尾）：`app/bi/` 归入 `domains/bi/`

当前 `app/bi/` 下：

```
app/bi/toolkit/atomic.py
app/bi/skill/dataset_query.py
app/bi/skill/runtime_bridge.py
app/bi/toolchain/__init__.py   # 空
```

这些本身就是 BI 领域的工具链，搬进 `domains/bi/` 才完整：

```
app/domains/bi/toolkit/atomic.py
app/domains/bi/skill/dataset_query.py
app/domains/bi/skill/runtime_bridge.py
```

操作同 Step 2/3 模式（先建 facade，再切断），fan-in 极小。

---

## 4. 执行顺序总结

```
Step 1a: graph/llm.py → core/llm.py         [△ 极小风险, 3 个 import 点]
Step 1b: agentscope_model.py → core/         [△ 极小风险, fan-in=0]
Step 2:  agents/bi_agent/ → domains/bi/agent/ [△ 低风险, 7 个 import 点]
Step 3:  bi_worker_* → domains/bi/worker/    [△ 低风险, 2 外部 + 5 测试]
Step 4a: 框架桥接 → runtime/engine/          [▲ 中风险, 10+ import 点]
Step 4b: 业务层 → domains/agent_team/        [▲ 中风险, 4 个外部]
Step 4c: 删除 agentscope_runtime/            [△ 极低风险, fan-in=0]
Step 5:  services/ 残余清理                  [△ 低风险, 纯改 import]
Step 6:  utils/ SQL → domains/query_exec/    [▲ 中风险, 10+ import 点]
Step 7:  app/bi/ → domains/bi/               [△ 低风险, 可选]
```

每步独立可回滚。建议从 Step 1a 开始，积累信心后推进。

---

## 5. 每步的验收标准

| 检查项 | 标准 |
|---|---|
| 新旧 import 路径均可工作 | 通过 facade 转发 或 直接改 import |
| 完整 pytest | `python -m pytest tests/ -x -q` 全绿 |
| 无循环依赖 | import 阶段无异常 |
| commit message 规范 | `phase-b-step-N: <描述>` |
| 删除旧目录 | 确认 grep 全项目无残留 import |

---

## 6. Phase B 结束后仍保留但标记为"待清理"的目录

| 路径 | 状态 | Phase C 动作 |
|---|---|---|
| `app/services/` | 保留下约 14 个文件（纯业务服务），facade 加 DeprecationWarning | Phase C 按新领域理念重分组 |
| `app/runtime/agent_team_runtime.py` | 800+ 行，里面还有 `agentscope_` 方法命名 | Phase C 做内部命名整理 |
| `app/events/projection.py` | 独立存在 | 保持，功能单一 |

---

## 7. 下一步

**请你逐步骤确认**。可回复 "Step 1a 开始" 我就动代码，或 "Step 1-3 都确认" 我连续执行。

也可以对某一步提修改意见（比如 "Step 4 的 runner.py 不该进 engine，应该留在 agent_team"），我会调整后再动。
