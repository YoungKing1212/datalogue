# AgentScope Service 模型配置保留与 Role Binding 移除计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Use checkboxes for progress tracking.

**Goal:** 保留 Datalogue 现有 LLM 模型配置功能和用户体验，删除 role binding，并让 AgentScope Service 接管 credential 注册、模型列表和 Agent Team session 的 `chat_model_config`。

**Architecture:** Datalogue 继续提供“模型配置”产品能力，用于展示、编辑、测试、选择和审计模型配置；运行时不再依赖角色绑定。保存模型配置时同步注册到 AgentScope Service credential，执行 Agent Team 时由 `model_config_id` 解析出 AgentScope `chat_model_config`，再交给 AgentScope Service 创建 session。Datalogue artifact、dataset、Workbench、Agent Team task 仍归 Datalogue 管。

**Tech Stack:** FastAPI、AgentScope 2.0.3 Agent Service、RedisStorage、React/Vite、SQLAlchemy/Alembic、pytest、Vitest。

---

## 不可协商决策

- 保留现有 LLM 模型配置功能：设置页、模型配置列表、创建、编辑、删除、连接测试、聊天模型选择和历史配置兼容都要保留。
- 不保留 Datalogue role binding：删除 `llm_role_binding` 表、API、Schema、服务逻辑和设置页角色绑定编辑器。
- `model_config_id` 保留为 Datalogue 内部和前端选择模型配置的稳定入口；它不是 AgentScope 的运行时模型配置。
- AgentScope Service `/credential`、`/credential/schemas`、`/model?provider=...`、`/sessions` 的 `chat_model_config` 是实际执行入口。
- 不允许继续用 LiteLLM 实现模型配置、连接测试或生产 LLM 调用；所有模型配置执行能力必须改由 AgentScope 实现。
- Datalogue 不再按角色自动选模型；没有显式模型时走默认模型配置或环境兜底，并在后续阶段切到 AgentScope 默认配置。

## 目标请求形态

前端和历史会话可以继续发送：

```json
{
  "model_config_id": 8
}
```

后端 AgentScope runner 必须在创建 session 前转换为：

```json
{
  "chat_model_config": {
    "type": "openai_credential",
    "credential_id": "datalogue-openai-compatible-model-8",
    "model": "MiniMax-M2.7",
    "parameters": {
      "thinking_enable": true
    }
  }
}
```

如果用户没有选择模型，运行时不能再查 role binding；改为使用默认启用模型配置或环境兜底，并同步到 AgentScope credential。

---

## Task 1: AgentScope 控制面 Client 与代理 API

**Status:** 实现和单测已完成，待按新目标提交。

**Files:**
- Modify: `datalogue-api/app/agentscope_service/client.py`
- Create: `datalogue-api/app/api/agentscope_control_plane.py`
- Modify: `datalogue-api/app/api/__init__.py`
- Test: `datalogue-api/tests/test_agentscope_service_client.py`
- Test: `datalogue-api/tests/test_agentscope_control_plane_api.py`

- [x] 增加 `list_credential_schemas`、credential CRUD、`list_models(provider)`。
- [x] 增加 `/api/agentscope-control/credential/schemas`、`/credentials`、`/model` 代理。
- [x] 覆盖 AgentScope 官方路径、payload 透传和代理错误处理。
- [ ] 提交本阶段。

**Verification:**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_service_client.py tests/test_agentscope_control_plane_api.py -q
cd datalogue-api && .venv/bin/ruff check app/agentscope_service/client.py app/api/agentscope_control_plane.py app/api/__init__.py tests/test_agentscope_service_client.py tests/test_agentscope_control_plane_api.py
cd datalogue-api && .venv/bin/python -m compileall app -q
git diff --check
```

---

## Task 2: 保留模型配置 API，删除 Role Binding API

**Files:**
- Modify: `datalogue-api/app/api/llm.py`
- Modify: `datalogue-api/app/schemas/llm.py`
- Modify: `datalogue-api/app/services/llm_config.py`
- Test: `datalogue-api/tests/test_llm_config.py`

- [ ] 后端测试改为：`/api/llm/models` CRUD 继续可用，`/api/llm/role-bindings` 返回 404 或完全不存在。
- [ ] 从 `LLM_ROLES`、`ensure_llm_role`、`_active_config_by_role`、`LLMRoleBindingOut`、`LLMRoleBindingsUpdate` 中移除角色绑定概念。
- [ ] `resolve_llm_config(settings, db, model_config_id=...)` 保留显式模型配置解析；无显式模型时只允许默认模型配置或环境兜底，不再按角色查询。
- [ ] `/api/llm/models` 保存配置后同步或预留同步 AgentScope credential 的服务调用点；失败要有明确错误边界，不能静默产生不可执行配置。
- [ ] 删除 `/api/llm/role-bindings` 的 GET/PUT 路由和测试。

**Verification:**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_llm_config.py -q
cd datalogue-api && .venv/bin/ruff check app/api/llm.py app/schemas/llm.py app/services/llm_config.py tests/test_llm_config.py
cd datalogue-api && .venv/bin/python -m compileall app -q
git diff --check
```

---

## Task 3: 设置页保留“模型配置”，移除角色绑定 UI

**Files:**
- Modify: `datalogue-web/src/api/client.js`
- Modify: `datalogue-web/src/components/settings.jsx`
- Test: `datalogue-web/src/components/settings.test.jsx`

- [ ] 设置页继续展示“LLM 模型配置”或等价入口，不改成只管理裸 credential。
- [ ] 保留模型配置创建、编辑、删除、连接测试、启用/停用、思考模式字段。
- [ ] 移除 role binding 区块和 `/api/llm/role-bindings` 调用。
- [ ] 增加 AgentScope credential schema/model card 辅助能力：用于 provider/model 候选和保存前校验，但不替代模型配置功能入口。
- [ ] 前端测试断言 `/api/llm/models` 仍被调用，`/api/llm/role-bindings` 不再被调用。

**Verification:**

```bash
cd datalogue-web && npm test -- src/components/settings.test.jsx --run
cd datalogue-web && npm run lint
cd datalogue-web && npm run build
git diff --check
```

---

## Task 4: Agent Team 运行时从模型配置生成 AgentScope chat_model_config

**Files:**
- Modify: `datalogue-api/app/agentscope_service/runner.py`
- Modify: `datalogue-api/app/runtime/agent_team_runtime.py`
- Modify: `datalogue-api/app/schemas/agent_team_task.py`
- Modify: `datalogue-web/src/assistant/chat-adapter.js`
- Modify: `datalogue-web/src/assistant/MyComposer.jsx`
- Test: `datalogue-api/tests/test_agentscope_agent_team_task_runner.py`
- Test: `datalogue-api/tests/test_agent_team_task_runtime.py`
- Test: `datalogue-web/src/assistant/chat-adapter.test.js`

- [ ] 保留 `model_config_id` 请求字段，作为用户选择模型配置的引用。
- [ ] runner 明确断言不再通过 role binding 解析 `lead_agent`。
- [ ] runner 使用 `model_config_id` 或默认模型配置生成 AgentScope `chat_model_config`。
- [ ] `create_session(..., chat_model_config=...)` 的 credential_id 与旧配置 id 稳定映射。
- [ ] 聊天模型选择器继续展示模型配置列表，不展示角色绑定。

**Verification:**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_agent_team_task_runtime.py tests/test_agentscope_agent_team_task_runner.py -q
cd datalogue-web && npm test -- src/assistant/chat-adapter.test.js --run
cd datalogue-api && .venv/bin/ruff check app/runtime/agent_team_runtime.py app/agentscope_service/runner.py app/schemas/agent_team_task.py tests/test_agent_team_task_runtime.py tests/test_agentscope_agent_team_task_runner.py
cd datalogue-web && npm run lint
git diff --check
```

---

## Task 5: 数据库迁移，只删除 Role Binding

**Files:**
- Modify: `datalogue-api/app/models/llm.py`
- Modify: `datalogue-api/app/models/__init__.py`
- Create: `datalogue-api/alembic/versions/<rev>_drop_llm_role_binding.py`
- Test: `datalogue-api/tests/test_llm_config.py`

- [ ] 保留 `llm_model_config` 表和 `LLMModelConfig` ORM。
- [ ] 删除 `llm_role_binding` 表和 `LLMRoleBinding` ORM。
- [ ] Alembic upgrade 只 drop `llm_role_binding`，downgrade 按项目约定恢复该表。
- [ ] 所有生产代码不再引用 `LLMRoleBinding`、`llm_role_binding`、`role-bindings`。

**Verification:**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_llm_config.py -q
cd datalogue-api && .venv/bin/ruff check app/models/llm.py app/models/__init__.py alembic/versions tests/test_llm_config.py
git diff --check
```

---

## Task 6: 删除 LiteLLM，模型配置执行改用 AgentScope

**Files:**
- Modify: `datalogue-api/app/graph/llm.py`
- Modify: `datalogue-api/app/api/llm.py`
- Modify: `datalogue-api/app/services/subagent_planning/planner.py`
- Modify: `datalogue-api/app/services/blueprint_analyzer.py`
- Modify: `datalogue-api/app/services/annotation.py`
- Modify: `datalogue-api/app/agents/bi_agent/dataset_agent_factory.py`
- Test: `datalogue-api/tests/test_subagent_query_planner.py`
- Test: `datalogue-api/tests/test_analysis_blueprint.py`
- Test: `datalogue-api/tests/test_bi_lead_agent_dataset_agent_factory.py`
- Test: `datalogue-api/tests/test_llm_config.py`

- [ ] 连接测试改为 AgentScope-backed test，不再直接调用 LiteLLM。
- [ ] 非 Agent Team 的 LLM 调用迁到 AgentScope ChatModel 或 AgentScope Service helper。
- [ ] 保留模型配置输入输出字段，但 provider 语义改为可映射到 AgentScope credential type。
- [ ] 生产代码和依赖中无 `litellm` / `LiteLLM`，并由测试强制约束。

**Verification:**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_query_planner.py tests/test_analysis_blueprint.py tests/test_bi_lead_agent_dataset_agent_factory.py tests/test_llm_config.py -q
cd datalogue-api && .venv/bin/ruff check app/graph/llm.py app/api/llm.py app/services/subagent_planning/planner.py app/services/blueprint_analyzer.py app/services/annotation.py app/agents/bi_agent/dataset_agent_factory.py
cd datalogue-api && .venv/bin/python -m compileall app -q
git diff --check
```

---

## Task 7: 真实页面 Smoke 与项目记忆

**Files:**
- Modify: `.codex/project-memory.md`

- [ ] 后端定向回归通过。
- [ ] 前端定向测试、lint、build 通过。
- [ ] 打开设置页，确认模型配置功能可见，role binding 不可见。
- [ ] 新建或选择模型配置，确认 AgentScope credential 同步成功。
- [ ] 打开聊天页，选择模型配置，询问 `查询杨凯2025年工作日志`。
- [ ] 确认候选数据集卡出现。
- [ ] 点击 `生产经营管理系统日志数据集`。
- [ ] 确认 BI Worker 查询执行。
- [ ] 确认结果卡出现。
- [ ] 点击 artifact 详情，确认详情表加载。
- [ ] 后端日志、数据库 artifact 记录、页面 artifact_ref 对齐。
- [ ] 写入 `.codex/project-memory.md`，记录变更、验证命令、真实 smoke 证据和残留风险。

**Verification:**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_service_client.py tests/test_agentscope_control_plane_api.py tests/test_agentscope_agent_team_task_runner.py tests/test_agent_team_task_runtime.py tests/test_llm_config.py tests/test_agentscope_service_projection.py tests/test_artifact_api.py -q
cd datalogue-web && npm test -- src/components/settings.test.jsx src/assistant/chat-adapter.test.js src/assistant/MyMessage.test.jsx src/assistant/agent-team-event-adapter.test.js --run
cd datalogue-api && .venv/bin/python -m compileall app -q
cd datalogue-web && npm run lint
cd datalogue-web && npm run build
git diff --check
```

---

## 最终验收清单

- [ ] `/api/llm/models` 保留并能管理模型配置。
- [ ] 设置页模型配置功能保留。
- [ ] 聊天模型选择仍基于模型配置列表。
- [ ] `/api/llm/role-bindings` 不存在。
- [ ] 前端无 role binding UI。
- [ ] 生产代码无 `LLMRoleBinding`、`llm_role_binding`、`role-bindings`。
- [ ] Agent Team session 创建时携带 AgentScope `chat_model_config`。
- [ ] AgentScope credential 与 Datalogue 模型配置建立稳定映射。
- [ ] 最终无生产 `litellm` 依赖。
- [ ] 真实页面 smoke 通过：候选数据集卡 -> BI Worker 查询 -> 结果卡 -> artifact 详情 -> 后端日志 -> 数据库 artifact。
- [ ] `.codex/project-memory.md` 记录完成情况。

## 自检

- Spec coverage: 保留模型配置功能、删除 role binding、AgentScope 接管执行时模型注册与 session 配置、真实页面 smoke 均有阶段任务。
- Boundary clarity: `model_config_id` 保留为 Datalogue 配置引用；`chat_model_config` 是 AgentScope 执行层 payload。
- Risk: LiteLLM 替换范围较大，必须在最终验收前完成；模型配置功能保留，但执行层只能落到 AgentScope。
