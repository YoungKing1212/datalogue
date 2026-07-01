# AS-R0 Agentic Shell-first Formal PR Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以用户确认的正式 PR0 / PR1 / PR2 计划为唯一执行口径，推进 Agentic Shell-first AS-R0，避免把临时“小刀”或提前探索误当成正式 PR 阶段。

**Architecture:** AS-R0 的方向是 AgentScope 接管 Datalogue 主链 Runtime，但迁移必须按 strangler 方式推进。P0 只做 Shell Contract 与 Tool Boundary，不替换 `/chat/stream` 主链；P1 才让 AgentScope Runtime 驱动 BI 主链；P2 再收敛 legacy runtime 并扩展 Report/Python/Audit 等业务 Agent。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、pytest、AgentScope Runtime、Datalogue Agentic Shell、AgentScope Workbench mirror。

---

## 0. Plan Governance

本文件是 AS-R0 后续工作的正式计划口径。执行规则如下：

- 后续所有 AS-R0 工作必须先映射到本文的 PR0.1 - PR2.4。
- 不再使用“P0.1 / P0.2 / P0.3”这类临时说法描述正式 PR 进度。
- 如果需要新增 PR、移动 scope、提前实现后续阶段能力，必须先在本文 `6. Proposed Plan Changes` 中登记：
  - 新增或调整内容。
  - 为什么现有 PR 计划承载不了。
  - 影响哪些文件、测试和验收。
  - 风险和回滚方式。
  - 审核状态必须保持 `Pending User Review`，直到用户明确批准。
- 未经用户批准的新增计划不得实施；已提前做出的探索性提交只能标为 `P1-prep` 或 `out-of-plan prep`，不能计入正式 PR 完成。

## 1. Formal PR Plan

### P0: Shell Contract 与 Tool Boundary，不替换主链

#### PR0.1: AS-R0 架构文档与迁移闸门

**目标：** 更新 C3 文档口径，明确哪些是 foundation、哪些要被 Shell ownership 替换。

**验收：**

- C3 Workbench / mirror 被标注为 foundation，而不是 AgentScope Runtime ownership 完成态。
- AS-R0 Shell ownership、Tool Provider 边界、安全禁区和迁移闸门写清楚。
- 明确 P0 不替换 `/chat/stream`，P1 才开始 runtime ownership 迁移。

#### PR0.2: `DatalogueAgenticShell` 契约层

**目标：** 新增 task classification、agent registry、disabled placeholders、policy whitelist、context projection、output sanitizer、event/action/checkpoint writer 接口。

**验收：**

- registry 只启用 `bi_lead_agent`。
- `report_agent`、`python_agent`、`audit_agent` 和其他业务 Agent 是 disabled placeholder。
- policy whitelist fail-closed。
- context projection 和 output sanitizer 阻断 SQL/schema/物理字段/raw rows/query_plan/RepairPatch/blueprint body。
- event/action/checkpoint writer 先定义接口，不要求替换现有 Workbench/retry 写回。

#### PR0.3: BI atomic tool provider

**目标：** 新增 `get_dataset_status`、`list_candidate_assets`、`compile_dsl_to_sql`、`execute_compiled_query`、`create_query_artifact`、`get_artifact_summary`。

**验收：**

- `list_candidate_assets(question=...)` 保留 `question` 参数但不做语义召回。
- 第一阶段返回 full catalog summary，包含 blueprint、metric、dimension、metadata_schema_summary。
- SQL 只能在 compile/execute tool 内部流转。
- DatasetAgent 可以生成 DSL，但不能生成最终可执行 SQL。
- tool response 不暴露 SQL/schema/raw rows/query_plan/RepairPatch/blueprint body。

#### PR0.4: 安全测试矩阵

**目标：** 固化 SQL/schema/物理字段/raw rows/query_plan/RepairPatch/blueprint body 不进入 Agent context、SSE 用户可见层或 Workbench View Model。

**验收：**

- pytest 覆盖 registry disabled、whitelist fail-closed、tool response sanitization、catalog summary 形状。
- 增加 Agent context、SSE final payload、AgentScope mirror metadata/event、Workbench View Model 的禁用词和结构扫描。
- 现有 `/chat/stream` 行为不变。

### P1: AgentScope Runtime 驱动 BI 主链

#### PR1.1: Runtime adapter 接管入口

**目标：** 新增 AgentScope runtime adapter，`/chat/stream` 先作为 HTTP/SSE 兼容壳，内部委托 `DatalogueAgenticShell.run_turn()`。

#### PR1.2: BI LeadAgent 接入 Shell

**目标：** BI LeadAgent 只开放 `query_dataset` / `query_multiple_datasets` 能力路由；Report/Python/Audit 返回 disabled action。

#### PR1.3: DatasetAgent tool-call runtime

**目标：** 用原子 tools 串起 `get_dataset_status -> list_candidate_assets -> DSL -> compile -> execute -> artifact summary`，替代当前 `DatasetSubAgent.run()` 直接暴露 graph event/final_state 的方式。

#### PR1.4: checkpoint/retry 迁移

**目标：** Workbench retry 调 Shell action，Shell 写 `retry.started/checkpoint_restored/dataset.query.completed/answer.completed`，并继续满足 provider-neutral observability contract。

#### PR1.5: 双路径灰度

**目标：** feature flag 下新 Shell runtime 与 legacy `_stream_chat_singleturn` 对齐同一 final payload、artifact refs、trace contract。

**P1 验收：**

- 同一 BI 问题在新 runtime 下完成。
- Workbench Panel completed。
- `/api/observability/traces/{trace_id}` contract passed。
- DOM/API 扫描不命中禁用词。

### P2: 收敛 legacy runtime 与扩展业务 Agent

#### PR2.1: `_stream_chat` 收缩为 transport adapter

**目标：** 业务 turn lifecycle 从 `chat.py` 迁走。

#### PR2.2: legacy compatibility 收口

**目标：** 把 `AgentScopeShellAdapter + BIWorkbenchTool(ask_bi)` 标记为 legacy compatibility，或改造成调用 Agentic Shell 的薄 wrapper。

#### PR2.3: 后续 tools 接入

**目标：** 接入 `repair_dsl`、`classify_query_failure`、`create_report_from_artifact`、`run_sandboxed_analysis_on_artifact`，默认 disabled 或 admin-gated。

#### PR2.4: 业务 Agent 受控启用

**目标：** ReportAgent / PythonAgent / AuditAgent 从 placeholder 到受控启用，每个 Agent 单独 PR、单独白名单、单独验收。

**P2 验收：**

- 旧 `/chat`、`/workbench`、retry harness、真实浏览器、trace contract 全通过。
- legacy direct `/chat/stream` driver 不再拥有业务 runtime。

## 2. Dependency Baseline

- 原计划依赖：`b-first-c@4e4654c8`，执行前先处理本地未提交 C3-P2 脏改。
- 当前实际基线：C3-P2 已提交并 push 到 `origin/b-first-c`：
  - `14992dd5 feat: harden c3 p2 workbench observability`
- AS-R0 worktree：
  - Path: `/Users/yangkai/code_place/study/python/Datalogue/.worktrees/codex-as-r0-agentic-shell-p0`
  - Branch: `codex/as-r0-agentic-shell-p0`

## 3. Today's Work Mapped To Formal Plan

### 3.1 C3-P2 收口

**Commit:** `14992dd5 feat: harden c3 p2 workbench observability`

**正式计划归属：** P0 dependency cleanup。

**说明：** 这是进入 AS-R0 前必须先处理的 C3-P2 脏改，不属于 AS-R0 PR0.x 本体。

### 3.2 `04e01c84 feat: add as-r0 agentic shell contract`

**正式计划归属：**

- PR0.2: partial complete。
- PR0.3: partial complete。
- PR0.4: partial complete。

**已覆盖：**

- `DatalogueAgenticShell`。
- task classification。
- agent registry。
- disabled placeholders。
- policy whitelist / business capabilities / reserved disabled tools。
- context projection。
- output sanitizer。
- `BIAtomicToolProvider` skeleton。
- `get_dataset_status`。
- `list_candidate_assets` full catalog summary。
- `get_artifact_summary`。
- 部分 sanitizer / registry / catalog shape pytest。

**该早期提交当时未覆盖，后续正式 PR 已补齐或待补齐：**

- PR0.2 的 event/action/checkpoint writer 接口已在 PR0.2 完成。
- PR0.3 的 `compile_dsl_to_sql`、`execute_compiled_query`、`create_query_artifact` 真实受控工具实现已在 PR0.3 完成。
- PR0.4 的 SSE 用户可见层和 Workbench View Model 完整安全矩阵。

### 3.3 `abcc0618 feat: add as-r0 agentscope runtime boundary`

**正式计划归属：** P1-prep，不计入 PR0 完成。

**原因：** 该提交新增 `DatalogueAgentScopeRuntimeDriver`，属于 AgentScope Runtime 接入前边界适配。它对 P1 有帮助，但不是 PR0.1 - PR0.4 的必需项。

**风险控制：**

- 不替换 `/chat/stream`。
- 不启动真实 AgentScope runner。
- 不调用旧 `ask_bi`。
- 只输出安全 boundary contract。

### 3.4 `39fbae95 feat: add as-r0 runtime shadow path`

**正式计划归属：** P1-prep，不计入 PR0 完成。

**原因：** 该提交在 feature flag 下把 runtime boundary 写入 AgentScope mirror metadata，属于 P1 双路径灰度的前置影子路径。它提前完成了观测准备，但不是 PR0 的正式验收项。

**风险控制：**

- `AS_R0_AGENTIC_RUNTIME_SHADOW_ENABLED` 默认关闭。
- SSE 输出和真实执行仍走原 Datalogue 主链。
- shadow boundary 生成失败不影响 `/chat/stream`。

## 4. Current Formal Status

| Plan Item | Status | Evidence | Remaining Work |
| --- | --- | --- | --- |
| PR0.1 | Complete | C3 架构文档、C3 spec、C3 implementation plan、C3-P2 plan 和 C3 验收记录已标注 foundation / runtime ownership 边界 | 后续如发现旧口径，按本文 Plan Governance 补文档 |
| PR0.2 | Complete | `04e01c84` + writer interface commit | 后续 P1 再把 writer interface 接到真实 Workbench/mirror 写回 |
| PR0.3 | Complete | `04e01c84` + PR0.3 atomic provider commit + review fix commit | 后续 PR0.4 继续扩大安全矩阵到 SSE 和 Workbench View Model |
| PR0.4 | Complete | AS-R0 security matrix commit | PR0 已完成；后续在 P1 新 runtime 下继续沿用矩阵 |
| PR1.1 | Complete | Runtime adapter 接管入口提交 + `docs/test-reports/2026-07-01-as-r0-pr1-1.md` | 后续 PR1.2 接入 BI LeadAgent Shell 能力路由 |
| PR1.2 - PR1.5 | Not started | `abcc0618`, `39fbae95` only as P1-prep | 下一步进入 PR1.2 BI LeadAgent 接入 Shell |
| PR2.1 - PR2.4 | Not started | None | 等 P1 验收后再进入 |

## 5. Next Allowed Work Without Plan Change

以下工作可继续执行，因为它们直接属于现有正式计划：

1. PR1.2：BI LeadAgent 接入 Shell，只开放 `query_dataset` / `query_multiple_datasets` 能力路由；Report/Python/Audit 返回 disabled action。

优先级建议：

1. 先补 Shell 侧 BI LeadAgent capability routing contract 测试，确保默认只开放 BI 查询能力。
2. 再把 Report/Python/Audit 的任务路由落到 disabled action，不提前启用业务 Agent。

## 5.1 Completed Task Reports

### PR0.1: AS-R0 架构文档与迁移闸门

**Status:** Complete

**Artifacts:**

- `docs/architecture/C3-AgentScope-Workbench-产品化设计.md`
- `docs/superpowers/specs/2026-06-30-c3-agentscope-workbench-design.md`
- `docs/superpowers/plans/2026-06-30-c3-agentscope-workbench-p0.md`
- `docs/superpowers/plans/2026-06-30-c3-p2-workbench-productization.md`
- `docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md`
- `docs/test-reports/2026-07-01-as-r0-pr0-1.md`

**Result:** C3 Workbench / mirror 已明确标注为 AS-R0 foundation，而不是 AgentScope Runtime ownership 完成态；迁移闸门明确 P0 不替换 `/chat/stream`，P1 才开始 runtime ownership 迁移，P2 才收敛 legacy runtime 和扩展业务 Agent。

### PR0.2: `DatalogueAgenticShell` writer interface

**Status:** Complete

**Artifacts:**

- `datalogue-api/app/services/agentic_shell.py`
- `datalogue-api/tests/test_agentic_shell_contract.py`
- `docs/test-reports/2026-07-01-as-r0-pr0-2.md`

**Result:** `DatalogueAgenticShell` 已新增 event/action/checkpoint writer interface、Noop writer 和测试用 memory writer。P0 阶段只产出并清洗安全写入记录，不替换现有 Workbench/retry 写回，不产生数据库或外部副作用。

### PR0.3: BI atomic tool provider

**Status:** Complete

**Artifacts:**

- `datalogue-api/app/services/agentic_bi_tools.py`
- `datalogue-api/app/services/agentic_shell.py`
- `datalogue-api/app/services/agentscope_runtime_driver.py`
- `datalogue-api/tests/test_agentic_shell_contract.py`
- `datalogue-api/tests/test_agentscope_runtime_driver_contract.py`
- `docs/test-reports/2026-07-01-as-r0-pr0-3.md`

**Result:** `BIAtomicToolProvider` 已补齐 `compile_dsl_to_sql`、`execute_compiled_query` 和 `create_query_artifact` 的受控边界；Shell whitelist 与 Runtime tool registry 同步开放六个 BI 原子工具。SQL 只在 compile/execute 工具内部通过私有 `compiled_query_ref` 流转，Agent 可见响应只返回句柄、状态、计数和 artifact ref，不返回 SQL、schema、raw rows、query_plan、RepairPatch 或 blueprint body。Review fix 已补冷启动导入测试和 dataset mismatch fail-closed 校验。

### PR0.4: 安全测试矩阵

**Status:** Complete

**Artifacts:**

- `datalogue-api/tests/test_as_r0_security_matrix.py`
- `datalogue-api/app/api/chat.py`
- `datalogue-api/app/services/agentscope_mirror.py`
- `datalogue-api/app/services/workbench_view_model.py`
- `docs/test-reports/2026-07-01-as-r0-pr0-4.md`

**Result:** 已固化 Agent context、BI tool response、SSE payload、AgentScope mirror metadata/event 和 Workbench View Model 的统一安全矩阵。`raw_rows`、`repair_patch`、`patch_body`、`blueprint_body` 及其 camelCase / 归一形式不会进入 Agent 或用户可见层；trace_only SSE 随流 payload 也移除内部 `node/display_name`。

### PR1.1: Runtime adapter 接管入口

**Status:** Complete

**Artifacts:**

- `datalogue-api/app/api/chat.py`
- `datalogue-api/app/core/config.py`
- `datalogue-api/app/services/agentic_shell.py`
- `datalogue-api/tests/test_agentscope_chat_bridge.py`
- `docs/test-reports/2026-07-01-as-r0-pr1-1.md`

**Result:** 新增默认关闭的 `AS_R0_AGENTIC_RUNTIME_ENABLED` feature flag；开启后 `/chat/stream` 仍保持 HTTP/SSE 兼容壳，但单轮与多轮入口会先委托 `DatalogueAgenticShell.run_turn()`，Shell 只生成安全 turn contract 并包裹既有 `_stream_chat_singleturn` 流，不改变 final payload、mirror 写入和 legacy 回退路径。PR1.1 不提前实现 DatasetAgent tool-call runtime，后者仍归 PR1.3。

## 6. Proposed Plan Changes

当前没有已批准的新增计划。

### Pending User Review

暂无。

### Rejected / Superseded

- “P0.1 / P0.2 / P0.3 / P0.4”临时小刀命名废弃。原因：与正式 PR0.1 - PR0.4 冲突，容易误导进度判断。

## 7. Change Request Template

任何新增计划或 scope 移动必须按以下模板先写入本文，并等待用户审核：

```markdown
### CR-YYYY-MM-DD-N: [变更标题]

**Status:** Pending User Review

**Requested Change:** [新增或调整什么]

**Reason:** [为什么现有 PR 计划承载不了]

**Affected Plan Items:** [PR0.x / PR1.x / PR2.x]

**Files Likely Affected:** [文件列表]

**Acceptance Impact:** [新增或变化的验收]

**Risk:** [风险]

**Rollback:** [如何回退]
```

## 8. Verification Commands For Plan Alignment

每次执行 AS-R0 任务后，至少运行：

```bash
cd datalogue-api
python3 -m pytest tests/test_agentic_shell_contract.py tests/test_agentscope_runtime_driver_contract.py tests/test_agentscope_chat_bridge.py tests/test_agentscope_shell_adapter.py tests/test_bi_workbench_tool.py -q
python3 -m py_compile app/api/chat.py app/core/config.py app/services/agentic_shell.py app/services/agentic_bi_tools.py app/services/agentscope_runtime_driver.py app/services/agentscope_chat_bridge.py
cd ..
git diff --check
```

如果任务触及 Workbench View Model、SSE final payload 或前端 Workbench，需要额外运行对应 pytest / Vitest / lint / build。
