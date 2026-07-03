# 2026-07-02 AgentScope 架构瘦身 P3：旧兼容壳删除与 legacy 边界收口计划

## Scope

P3 在 P1/P2 新目录已经承接运行主链后，删除纯 re-export 兼容壳，并把仍需保留的历史实现明确标记为 legacy implementation。目标不是一次性改数据库表名，而是先让活跃代码不再依赖 `app/services/` 中的 Agent/runtime/middleware/toolchain 入口。

保留边界：

- `app/services/bi_lead_agent/*` 暂时保留为历史 run/confirmation/handoff 实现层，因为 API、DTO、DB model 和迁移仍依赖这些名字。
- `app/services/subagent_*`、planner、artifact、schema、audit 等非本次 AgentScope 瘦身范围的 service 暂不处理。
- 用户可见层继续禁止 SQL、schema、raw rows、query_plan、repair patch。

## Task 1: Move AgentScope Dataset bridge out of `services/`

Files:

- Create: `datalogue-api/app/bi/skill/runtime_bridge.py`
- Modify: `datalogue-api/app/bi/skill/__init__.py`
- Modify: `datalogue-api/app/bi/skill/dataset_query.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p2_bi_boundaries.py`
- Modify: `datalogue-api/tests/test_agentscope_dataset_runtime_bridge.py`
- Add: `datalogue-api/tests/test_agentic_architecture_p3_cleanup.py`
- Delete: `datalogue-api/app/services/agentscope_dataset_runtime.py`

- [x] **Step 1: Write failing bridge ownership test**

Assert `AgentScopeDatasetRuntimeBridge` and `build_dataset_agentscope_tools()` are owned by `app.bi.skill.runtime_bridge`.

- [x] **Step 2: Move bridge implementation**

Move the full AgentScope Dataset external execution bridge to `app/bi/skill/runtime_bridge.py`; update `DatasetQuerySkill`, handoff tests and bridge tests to import the new path.

- [x] **Step 3: Delete old bridge module**

Delete `app/services/agentscope_dataset_runtime.py` and assert importing it fails.

## Task 2: Delete pure re-export compatibility shells

Files:

- Delete: `datalogue-api/app/services/agentic_shell.py`
- Delete: `datalogue-api/app/services/agentic_shell_task_runtime.py`
- Delete: `datalogue-api/app/services/agentic_shell_writers.py`
- Delete: `datalogue-api/app/services/agentscope_thread_resolver.py`
- Delete: `datalogue-api/app/services/agentscope_runtime_driver.py`
- Delete: `datalogue-api/app/services/agentic_dataset_runtime.py`
- Delete: `datalogue-api/app/services/bi_tools/__init__.py`
- Delete: `datalogue-api/app/services/bi_tools/atomic.py`
- Delete: `datalogue-api/app/services/agentscope_middlewares/__init__.py`
- Delete: `datalogue-api/app/services/agentscope_middlewares/dataset_tool_logging.py`
- Delete: `datalogue-api/app/services/agentscope_middlewares/safe_log_summary.py`
- Delete: `datalogue-api/app/services/agentic_shell_event_projection.py`
- Delete: `datalogue-api/app/services/agentscope_event_projection.py`
- Delete: `datalogue-api/app/services/agentic_shell_logging.py`
- Delete: `datalogue-api/app/services/observability/agentscope_otel.py`
- Modify: P1/P2 architecture boundary tests to assert new ownership instead of old compatibility aliases.

- [x] **Step 1: Add old-module deletion regression test**

Assert pure compatibility modules fail import with `ModuleNotFoundError`.

- [x] **Step 2: Update remaining tests to new paths**

Tests should import from `app.middlewares`, `app.events`, `app.runtime`, `app.persistence`, `app.agents.agentic_lead_agent`, `app.bi.toolkit`, `app.bi.toolchain`, and `app.bi.skill`.

- [x] **Step 3: Delete shell files**

Remove only modules that are known pure re-export or migrated bridge files. Do not delete `app/services/bi_lead_agent/*` in this step.

## Task 3: Verification

- [x] Run P1/P2/P3 boundary tests.
- [x] Run Agentic Shell task API/runtime tests.
- [x] Run Dataset bridge, BI handoff and BI service tests.
- [x] Run `python3 -m compileall datalogue-api/app -q`.
- [x] Run `git diff --check`.
- [x] Run structure scans for old deleted modules.
