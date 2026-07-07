# AgentScope Service 模型配置接管计划

> **当前决策:** 保留 Datalogue 现有“LLM 模型配置”产品功能，但持久化、密钥、模型发现、运行时选择和 Agent Team session 配置全部由 AgentScope Service 的 credential/model 资源接管。Datalogue 不再保留本地模型配置表、角色绑定表或旧模型配置 API。

## 目标

- 设置页继续提供模型配置列表、创建、编辑、删除、发现模型和聊天选择体验。
- AgentScope Service `/credential` 是 credential 的唯一真相源。
- AgentScope Service `/model?provider=...` 是模型发现的唯一真相源。
- Agent Team 创建 session 时只接受 `model_credential_id`、`model_name` 和 `model_parameters`，不再接收历史本地配置 ID。
- Datalogue 仍保留 artifact、checkpoint、Workbench、Agent Team task 和事件投影真相源。

## 阶段 1：AgentScope 控制面代理

**状态：已完成。**

- [x] 后端代理 `/api/agentscope-control/credential/schemas`、`/credentials`、`/model`。
- [x] 代理响应统一脱敏，前端只看到 `api_key_set`。
- [x] `AgentScopeServiceClient.list_models()` 兼容 Service `/model/` 路径。

**验证：**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_service_client.py tests/test_agentscope_control_plane_api.py -q
```

## 阶段 2：前端设置页迁移

**状态：已完成。**

- [x] 设置页模型配置入口保留，但 CRUD 改为 AgentScope credential CRUD。
- [x] “测试连接”改为“发现模型”，直接读取 AgentScope ModelCard。
- [x] 删除设置页对旧模型 API 和角色绑定 API 的调用。
- [x] 真实页面 smoke：`/settings -> LLM 模型` 可见 AgentScope credential，发现模型返回可用 ModelCard。

**验证：**

```bash
cd datalogue-web && npm run lint
cd datalogue-web && npm run build
```

## 阶段 3：聊天模型选择与运行时接管

**状态：已完成。**

- [x] 聊天页模型选择器从 AgentScope credential + ModelCard 组合可选项。
- [x] 前端只发送 `model_credential_id`、`model_name`、`model_parameters`。
- [x] 后端 runner 用这些字段生成 AgentScope session `chat_model_config`。
- [x] 未显式选择模型时，runner 直接引用 AgentScope 默认 credential。

**验证：**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_agent_team_task_runner.py tests/test_agent_team_task_contracts.py -q
cd datalogue-web && npm test -- src/assistant/chat-adapter.test.js --run
```

## 阶段 4：删除本地模型配置层

**状态：本轮实施。**

- [x] 删除 `/api/llm` 旧路由入口。
- [x] 删除旧 ORM、Schema 和本地模型配置测试。
- [x] 新增迁移删除本地模型配置表。
- [x] 兼容型 `resolve_llm_config()` 改为只从 AgentScope 默认 credential 解析，数据库参数仅为旧调用签名兼容。
- [x] 前端删除旧模型列表 API helper。
- [x] 静态扫描约束 app、tests、web 不再引用旧模型表、旧模型 API、旧请求字段或旧执行依赖。

**验证：**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_llm_resource_boundary.py tests/test_agentscope_agent_team_task_runner.py tests/test_workbench_retry_actions.py -q
cd datalogue-api && .venv/bin/python -m compileall app alembic/versions/x4y5z6a7b8c9_drop_llm_model_config.py -q
rg -n "旧模型表/旧模型字段扫描表达式" datalogue-api/app datalogue-api/tests datalogue-web/src
```

## 阶段 5：真实页面 smoke

**状态：待本轮最终验证。**

- [ ] 设置页模型配置功能可用，发现模型成功。
- [ ] 聊天页选择 AgentScope 模型后发问。
- [ ] 候选数据集卡出现。
- [ ] 点击候选数据集后 BI Worker 查询执行。
- [ ] 结果卡出现。
- [ ] 点击 artifact 详情后表格加载。
- [ ] 后端日志中的 task/artifact/ref 与数据库 artifact 记录、页面结果卡一致。

**验证命令和页面操作：**

```bash
cd datalogue-api && .venv/bin/alembic upgrade head
cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_llm_resource_boundary.py tests/test_agentscope_control_plane_api.py tests/test_agentscope_agent_team_task_runner.py tests/test_agent_team_task_contracts.py tests/test_workbench_retry_actions.py -q
cd datalogue-web && npm test -- src/assistant/chat-adapter.test.js src/assistant/MyMessage.test.jsx src/assistant/agent-team-event-adapter.test.js --run
cd datalogue-web && npm run lint && npm run build
```

## 最终验收清单

- [ ] 旧模型配置 API 不存在。
- [ ] 旧模型配置表已通过迁移删除。
- [ ] 旧角色绑定 API 和表不存在。
- [ ] 设置页模型配置功能仍可用，但背后只操作 AgentScope credential/model。
- [ ] 聊天模型选择只发送 AgentScope credential/model 资源。
- [ ] Agent Team session 创建只携带 AgentScope `chat_model_config`。
- [ ] 真实页面 smoke 完成并写入 `.codex/project-memory.md`。
