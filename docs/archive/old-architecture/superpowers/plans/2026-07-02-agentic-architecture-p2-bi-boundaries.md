# 2026-07-02 AgentScope 架构瘦身 P2：BI Agent / BI Toolkit / Dataset Skill 边界迁移计划

## Scope

P2 在 P1 的 `agents/`、`runtime/`、`middlewares/`、`events/`、`persistence/` 边界基础上，继续把 BI 查询能力从 `app/services/` 中拆出，目标目录为：

- `app/agents/bi_agent/`：BI Agent 的 AgentScope ReAct Agent 入口和业务 prompt/策略。
- `app/bi/toolkit/`：BI Agent 可注册的 AgentScope ToolBase / Toolkit。
- `app/bi/toolchain/`：确定性的 Dataset 查询状态机、DSL 编译、执行、repair 和 artifact 生成链路。
- `app/bi/skill/`：面向 BI Agent 注册的 Skill 包装层，只暴露受控能力。

本阶段继续保留旧 `app.services.*` 兼容壳，P3 再统一删除。

## Task 1: Move BI atomic toolkit to `app/bi/toolkit/`

Move `DatalogueBIAtomicToolkit` and atomic AgentScope ToolBase implementations out of `app/services/bi_tools/`. This is the foundation for registering Dataset query skills/tools directly into BI Agent.

Files:

- Create: `datalogue-api/app/bi/__init__.py`
- Create: `datalogue-api/app/bi/toolkit/__init__.py`
- Create: `datalogue-api/app/bi/toolkit/atomic.py`
- Modify: `datalogue-api/app/services/bi_tools/__init__.py`
- Modify: `datalogue-api/app/services/bi_tools/atomic.py`
- Modify: `datalogue-api/app/runtime/boundary.py`
- Modify: `datalogue-api/app/services/agentic_dataset_runtime.py`
- Modify: `datalogue-api/app/services/agentscope_dataset_runtime.py`
- Modify: `datalogue-api/app/services/bi_lead_agent/handoff_adapter.py`
- Modify: `datalogue-api/app/services/bi_lead_agent/native_handoff.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p2_bi_boundaries.py`

- [x] **Step 1: Write failing BI toolkit boundary test**

Add `datalogue-api/tests/test_agentic_architecture_p2_bi_boundaries.py`:

```python
def test_p2_bi_toolkit_new_path_owns_atomic_toolkit():
    from app.bi.toolkit import DatalogueBIAtomicToolkit, build_bi_atomic_toolkit
    from app.bi.toolkit.atomic import DatalogueBIAtomicToolkit as DirectToolkit
    from app.services.bi_tools import DatalogueBIAtomicToolkit as LegacyToolkit

    assert DatalogueBIAtomicToolkit is DirectToolkit
    assert LegacyToolkit is DirectToolkit
    assert build_bi_atomic_toolkit.__module__ == "app.bi.toolkit.atomic"
    assert DirectToolkit.__module__ == "app.bi.toolkit.atomic"
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p2_bi_boundaries.py::test_p2_bi_toolkit_new_path_owns_atomic_toolkit -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.bi'`.

- [x] **Step 3: Move atomic toolkit implementation**

Move `datalogue-api/app/services/bi_tools/atomic.py` into `datalogue-api/app/bi/toolkit/atomic.py`. Export all public names from `app/bi/toolkit/__init__.py` and keep `app/bi/__init__.py` as the BI domain package marker.

- [x] **Step 4: Keep legacy `services.bi_tools` as adapter**

Replace `datalogue-api/app/services/bi_tools/atomic.py` and `datalogue-api/app/services/bi_tools/__init__.py` with re-export imports from `app.bi.toolkit.atomic`.

- [x] **Step 5: Update active imports to new BI toolkit path**

Use `app.bi.toolkit` for active runtime/toolchain callers. Keep legacy imports only in compatibility tests.

- [x] **Step 6: Run BI toolkit verification**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p2_bi_boundaries.py tests/test_agentic_dataset_runtime.py tests/test_agentscope_dataset_runtime_bridge.py tests/test_bi_lead_agent_native_handoff.py tests/test_agentic_shell_contract.py -q
```

Expected: PASS.

## Task 4: Add BI Agent package boundary under `app/agents/bi_agent/`

Create the BI Agent package as the new business-agent entrance. At this step the old `app.services.bi_lead_agent.*` implementation stays as the compatibility-backed service layer, but active runtime code should import BI Agent services through `app.agents.bi_agent`.

Files:

- Create: `datalogue-api/app/agents/bi_agent/__init__.py`
- Create: `datalogue-api/app/agents/bi_agent/agent.py`
- Create: `datalogue-api/app/agents/bi_agent/services.py`
- Modify: `datalogue-api/app/api/agentic_shell.py`
- Modify: `datalogue-api/app/runtime/__init__.py`
- Modify: `datalogue-api/app/runtime/task_runtime.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p2_bi_boundaries.py`
- Modify: `datalogue-api/tests/test_agentic_shell_task_api.py`
- Modify: `datalogue-api/tests/test_agentic_shell_task_runtime.py`

- [x] **Step 1: Write failing BI Agent boundary test**

Add tests that assert:

- `BIAgent` is owned by `app.agents.bi_agent.agent`.
- `BIAgent.capability_manifest()` exposes `agent_name=bi_agent` and includes `DatasetQuerySkill`.
- Runtime task runner default service factories import through `app.agents.bi_agent`.

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p2_bi_boundaries.py::test_p2_bi_agent_new_path_owns_business_agent_facade tests/test_agentic_architecture_p2_bi_boundaries.py::test_p2_task_runner_defaults_use_bi_agent_services -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.bi_agent'`.

- [x] **Step 3: Implement BI Agent façade**

Create `BIAgent` with a safe `capability_manifest()` that references `DatasetQuerySkill` and does not expose SQL/schema/raw rows/query plan.

- [x] **Step 4: Add BI Agent service exports**

Export `BIAgentRunService`, `BIAgentConfirmationService` and `BIAgentHandoffService` from `app.agents.bi_agent.services`, initially backed by the existing services.

- [x] **Step 5: Update active runtime imports**

Change `app/runtime/task_runtime.py` to import default BI service factories from `app.agents.bi_agent`, expose `BIAgentTaskRunner` as the active runner, and keep `BILeadAgentTaskRunner` only as a migration alias.

- [x] **Step 6: Run BI Agent boundary verification**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p2_bi_boundaries.py tests/test_agentic_shell_task_runtime.py tests/test_agentic_shell_task_api.py -q
```

Expected: PASS.

## Task 3: Add Dataset query Skill boundary under `app/bi/skill/`

Create a Dataset query Skill wrapper that owns BI Toolkit / Dataset Toolchain / AgentScope Dataset bridge construction. This is the first active step toward BI Agent registering Dataset query ability as a Skill instead of hand-assembling toolkit/runtime objects in service code.

Files:

- Create: `datalogue-api/app/bi/skill/__init__.py`
- Create: `datalogue-api/app/bi/skill/dataset_query.py`
- Modify: `datalogue-api/app/services/bi_lead_agent/handoff_adapter.py`
- Modify: `datalogue-api/app/services/bi_lead_agent/native_handoff.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p2_bi_boundaries.py`

- [x] **Step 1: Write failing Dataset Skill tests**

Add tests that assert:

- `DatasetQuerySkill` is owned by `app.bi.skill.dataset_query`.
- It builds `DatalogueBIAtomicToolkit`, `DatasetAgentToolCallRuntime`, and `AgentScopeDatasetRuntimeBridge`.
- Its public manifest exposes only tool names and safety flags, not SQL/schema/raw rows/query plan.
- Handoff factories call `DatasetQuerySkill.build_runtime_bridge()` instead of assembling the bridge directly.

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p2_bi_boundaries.py::test_p2_bi_skill_new_path_owns_dataset_query_skill tests/test_agentic_architecture_p2_bi_boundaries.py::test_p2_handoff_factories_build_dataset_bridge_through_skill -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.bi.skill'` or missing factory wiring.

- [x] **Step 3: Implement DatasetQuerySkill**

Create `DatasetQuerySkill` with:

- `skill_name = "dataset_query"`
- `build_toolkit()`
- `build_toolchain_runtime(dsl_generator, toolkit=None)`
- `build_runtime_bridge(toolkit=None)`
- `capability_manifest()`

- [x] **Step 4: Wire handoff factories through DatasetQuerySkill**

Update `DatalogueBIHandoffAdapter.from_db()` and `AgentScopeNativeBIHandoff.from_db()` to build their bridge through `DatasetQuerySkill`.

- [x] **Step 5: Run Skill verification**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p2_bi_boundaries.py tests/test_bi_lead_agent_native_handoff.py tests/test_agentscope_dataset_runtime_bridge.py -q
```

Expected: PASS.

## Task 2: Move deterministic Dataset toolchain to `app/bi/toolchain/`

Move `DatasetAgentToolCallRuntime` out of `app/services/agentic_dataset_runtime.py`. This class is the deterministic Dataset query toolchain used by BI Agent/Dataset Skill; it should live under the BI domain package rather than the generic services layer.

Files:

- Create: `datalogue-api/app/bi/toolchain/__init__.py`
- Create: `datalogue-api/app/bi/toolchain/dataset_runtime.py`
- Modify: `datalogue-api/app/services/agentic_dataset_runtime.py`
- Modify: `datalogue-api/app/services/agentscope_dataset_runtime.py`
- Modify: `datalogue-api/tests/test_agentic_architecture_p2_bi_boundaries.py`
- Modify: `datalogue-api/tests/test_agentic_dataset_runtime.py`

- [x] **Step 1: Write failing Dataset toolchain boundary test**

Add to `datalogue-api/tests/test_agentic_architecture_p2_bi_boundaries.py`:

```python
def test_p2_bi_toolchain_new_path_owns_dataset_tool_call_runtime():
    from app.bi.toolchain import DatasetAgentToolCallRuntime
    from app.bi.toolchain.dataset_runtime import DatasetAgentToolCallRuntime as DirectRuntime
    from app.services.agentic_dataset_runtime import DatasetAgentToolCallRuntime as LegacyRuntime

    assert DatasetAgentToolCallRuntime is DirectRuntime
    assert LegacyRuntime is DirectRuntime
    assert DirectRuntime.__module__ == "app.bi.toolchain.dataset_runtime"
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p2_bi_boundaries.py::test_p2_bi_toolchain_new_path_owns_dataset_tool_call_runtime -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.bi.toolchain'`.

- [x] **Step 3: Move Dataset toolchain implementation**

Move `DatasetAgentNextToolCall`, `DatasetAgentToolCallSession`, `DatasetAgentToolCallRuntime` and helper functions into `datalogue-api/app/bi/toolchain/dataset_runtime.py`, and export them from `app/bi/toolchain/__init__.py`.

- [x] **Step 4: Keep legacy service runtime as adapter**

Replace `datalogue-api/app/services/agentic_dataset_runtime.py` with a re-export import from `app.bi.toolchain.dataset_runtime`.

- [x] **Step 5: Update active imports**

Change `agentscope_dataset_runtime.py` and tests to import Dataset toolchain symbols from `app.bi.toolchain`.

- [x] **Step 6: Run Dataset toolchain verification**

Run:

```bash
cd datalogue-api && python3 -m pytest tests/test_agentic_architecture_p2_bi_boundaries.py tests/test_agentic_dataset_runtime.py tests/test_agentscope_dataset_runtime_bridge.py -q
```

Expected: PASS.
