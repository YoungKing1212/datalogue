# 2026-07-06 BI Worker 渐进式上下文验收记录

## 验收范围

- Agentic Lead + BI Worker 架构保持不变：LeadAgent 负责任务编排、候选确认和安全结果承接，BI Worker 负责具体问数执行。
- BI Worker 工具继续通过 AgentScope SDK `FunctionTool` 暴露，不绕开 AgentScope 工具注册与调用边界。
- 渐进式上下文固定骨架为 L0 / L1 / L5，确保任务入口、资产目录和输出安全契约稳定存在。
- L2 / L3 按需加载，避免默认把字段详情和值域画像塞进 Worker 上下文。
- L4 强制加载，用于支撑关系路径和 join 相关判断。
- Query Plan v1 必须携带 `relationship_ref`，让关系路径通过引用流转，而不是把完整 schema 或 join 细节暴露给用户可见层。
- 用户可见输出禁止出现 SQL、raw rows、schema、query plan；这些内容只能在受控工具、运行时内部或 artifact 存储层流转。

## 自动化验证命令

### 后端回归

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_bi_worker_progressive_context_contracts.py tests/test_bi_worker_progressive_context_tools.py tests/test_bi_worker_query_validator.py tests/test_bi_worker_query_runtime.py tests/test_bi_worker_progressive_context_e2e.py tests/test_agentscope_service_tools.py tests/test_agentscope_static_agent_registry.py tests/test_agentscope_agent_team_task_runner.py tests/test_agentscope_service_worker_logging.py -q
```

结果：`69 passed, 29 warnings`；warnings 为 pytest-asyncio fixture loop scope、Starlette/Pydantic/SQLAlchemy deprecation，以及既有 fake client stream close runtime warning。

### 前端回归

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-web
npm test -- agent-team-event-adapter.test.js chat-adapter.test.js --run
npm run lint
npm run build
```

结果：`npm test` 通过，`2 passed (2)`、`37 passed (37)`；`npm run lint` 通过，`0 errors, 13 warnings`；`npm run build` 通过，保留既有 Vite chunk size warning。

## 手工 Smoke 步骤

1. 启动后端、前端和 AgentScope Service，打开 `http://localhost:5173/chat`。
2. 输入一个需要候选数据集的问数问题，例如“查询杨凯2025年工作日志”。
3. 确认页面先展示候选数据集卡，且聊天区不出现 SQL、schema、raw rows 或 query plan。
4. 选择目标数据集后等待 BI Worker 执行，确认结果卡只展示业务摘要、行列规模和 artifact 引用。
5. 打开 Workbench artifact 详情，确认详情入口可用，聊天区仍不展示 SQL、schema、raw rows 或 query plan。
6. 检查后端日志或测试输出，确认 Query Plan v1 使用 `relationship_ref` 表达关系路径。

## 残留风险

- L3 真实值域画像仍需继续收敛，避免值域信息过少影响解释，或过多挤占 Worker 上下文预算。
- 复杂多跳 join 仍需继续收敛，尤其是多关系路径竞争、弱关系命中和跨主题资产组合场景。
