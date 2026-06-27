# DAT-7 轻量协议验收与全量回归计划

## 要求摘要

- 基线分支：`origin/b-first-c`，当前工作分支为平台创建的 `agent/datalogue/349839da`。
- 后端新增 `datalogue-api/tests/test_reserved_actions_contract.py`，覆盖 `export` / `continue_edit` 第一阶段禁用态、未知 action 安全忽略、final payload 防泄露。
- 前端新增/修改 `datalogue-web/src/components/artifact-card.test.jsx`，覆盖产物卡片只通过受控入口读取 artifact，不直接暴露敏感 payload。
- 完成后端核心回归、后端默认回归、前端 lint/test/build 和必要真实链路抽检；若服务不可用，明确 blocker。

## 命令矩阵

### 后端

- 核心契约：`cd datalogue-api && pytest -q tests/test_reserved_actions_contract.py`
- 相关回归：`cd datalogue-api && pytest -q tests/test_multiturn.py tests/test_multiturn_regression.py tests/test_multiturn_context_builder.py tests/test_subagent_tool_adapter.py tests/test_artifact_api.py`
- 默认回归：`cd datalogue-api && pytest -q`

### 前端

- 组件测试：`cd datalogue-web && npm test -- artifact-card.test.jsx --runInBand`
- lint：`cd datalogue-web && npm run lint`
- build：`cd datalogue-web && npm run build`

### 观测 / 真实链路

- 轻量 API 可用性：`cd hermes-skills/datalogue && python3 scripts/api_assets.py health`
- 若可用，SQL preview 只走只读入口：`python3 scripts/api_assets.py list-datasets`、`plan-query`、`execute-sql`。
- 不调用 `/api/chat/stream`、不发布 Manifest、不写外部数据源。

## 失败分流规则

- 契约测试失败：先定位最小失败断言，区分 action 协议缺口、防泄露缺口、测试夹具不匹配。
- 后端全量失败：若核心契约通过但全量失败，按首个失败模块归类为既有回归或本次改动影响；只修本 issue 范围内问题。
- 前端失败：先运行指定组件测试，再根据 lint/build 输出判断是测试环境缺依赖、导出不可测还是真实 UI 逻辑缺口。
- 真实链路失败：若 Datalogue API 不可达，记录为环境 blocker；若 SQL guard 拒绝写 SQL，视为预期保护；若只读 SELECT 失败，记录 dataset/schema 上下文。

## 验收标准

- 新增后端测试能证明：保留 action 不启动增强链路、未知 action 不进入 final payload、敏感 key 不泄露。
- 前端测试能证明：artifact 卡片按按钮触发 `getArtifact`，展示安全摘要/表格，不渲染 raw SQL/control plane 等敏感字段。
- 最终评论列出每条实际运行命令、通过/失败证据、风险和建议修复入口。
