# Doris / Oracle 数据源问数链路集成验证记录

日期：2026-07-09 17:30  
执行者：OMX team `leader-worktree-doris-8419a349` / `worker-4`  
状态：**集成基线已验证；目标实现未全部落地，Doris/Oracle 完整问数链路仍需上游实现后复验。**

## 1. 范围与依据

只读规划证据：

- `/Users/yangkai/code_place/study/python/Datalogue/.omx/state/ralplan-doris-oracle-datasource-handoff.json`
- `/Users/yangkai/code_place/study/python/Datalogue/.omx/tmp/ralplan-doris-oracle-datasource-draft.md`

规划目标要求：

1. Doris 在产品/API 层独立暴露为 `db_type=doris`，服务端第一阶段统一归一到 `dialect=mysql` 执行。
2. Oracle 补齐 capability、adapter、URL、compiler、preview、BI runtime 与分页语法链路。
3. 最终 answer 与 Workbench artifact 均能看到安全结果引用、行列数和预览。
4. 不搭建真实 Doris/Oracle 数据库；真实环境验收仅连接用户已有环境并沉淀手册/脚本证据。

## 2. 当前集成闸门结论

| 闸门 | 当前证据 | 结论 |
|---|---|---|
| Doris 产品/API 独立类型 | `rg -n "doris" datalogue-api datalogue-web docs .codex/project-memory.md` 命中数为 `0` | **未落地** |
| Doris 执行方言归一化 | 当前无 `normalize_execution_dialect(db_type=doris)` 或 Doris capability 可验证 | **未落地** |
| Oracle capability | `datalogue-api/app/domains/data_source/adapters/registry.py` 已有 `oracle` capability，默认端口 `1521`、驱动 `oracledb`、`test_sql=SELECT 1 FROM DUAL` | 已有基础能力 |
| Oracle SQL Guard 分页 | `tests/test_sql_guard.py::test_guard_oracle_uses_fetch_first` 通过，输出 `FETCH FIRST 20 ROWS ONLY` | 已覆盖 guard 层 |
| Oracle QueryPlan compiler / adapter | 当前 `datalogue-api/app/domains/query_execution/dialect/adapter.py` 的 `_SUPPORTED_DIALECTS = {"mysql", "sqlite"}`，`tests/test_query_plan_compiler.py::test_fails_closed_for_unknown_dialect` 仍断言 `dialect="oracle"` 被 fail-closed | **未落地完整执行链路** |
| Preview / analysis blueprint 基线 | 数据集 SQL preview、analysis blueprint 安全测试通过 | 基线通过 |
| BI Worker 安全 payload | BI Worker runtime targeted tests 通过，artifact card 安全 payload 仍可用 | 基线通过 |
| Workbench / artifact 可见性 | `artifact-card`、`workbench-panel`、`workbench-route` 前端测试通过，`npm run build` 通过 | 基线通过 |

## 3. 已执行验证

### 后端：数据源、query execution、preview、analysis blueprint

```bash
cd datalogue-api && python3 -m pytest \
  tests/test_datasource.py::TestDatasourceAPI::test_list_datasource_capabilities \
  tests/test_datasource.py::TestDatasourceAPI::test_test_connection_returns_driver_missing_diagnostic \
  tests/test_dataset.py::TestDatasetAPI::test_sql_preview_select_returns_rows \
  tests/test_dataset.py::TestDatasetAPI::test_sql_preview_blocks_dml \
  tests/test_dataset.py::TestDatasetAPI::test_sql_preview_missing_datasource_returns_structured_error \
  tests/test_directory_facades.py::test_query_execution_preview_is_direct_domain_access \
  tests/test_sql_guard.py::test_guard_oracle_uses_fetch_first \
  tests/test_sql_dialect_adapter.py \
  tests/test_query_plan_compiler.py::test_fails_closed_for_unknown_dialect \
  tests/test_query_plan_compiler.py::test_rejects_dialect_mismatch_with_current_datasource \
  tests/test_analysis_blueprint.py::test_render_blueprint_sql_preview_replaces_bound_params \
  tests/test_analysis_blueprint.py::test_analyze_sql_returns_task_result \
  tests/test_analysis_blueprint.py::test_blueprint_test_remains_optional_validation \
  tests/test_analysis_blueprint.py::test_blueprint_test_blocks_unsafe_sql \
  -q
```

结果：`17 passed, 10 warnings in 0.37s`。  
说明：这是当前基线验证；其中 `test_fails_closed_for_unknown_dialect` 仍证明 Oracle 尚未进入 QueryPlan compiler 可执行白名单。

### 后端：BI Worker runtime / artifact card 安全 payload

```bash
cd datalogue-api && python3 -m pytest \
  tests/test_bi_worker_progressive_context_contracts.py::test_safe_result_payload_contains_artifact_card_only \
  tests/test_bi_worker_query_validator.py::test_known_fields_and_relationships_are_supported \
  tests/test_bi_worker_query_validator.py::test_unknown_asset_and_field_are_reported_as_safe_missing_context \
  tests/test_bi_worker_query_runtime.py::test_validation_needs_more_context_returns_l4_and_does_not_execute \
  tests/test_bi_worker_query_runtime.py::test_supported_plan_returns_dataset_query_result_without_private_details \
  tests/test_bi_worker_query_runtime.py::test_execute_query_plan_derives_field_refs_from_dataset \
  tests/test_bi_worker_progressive_context_e2e.py::test_execute_query_plan_returns_l4_validation_when_plan_uses_undisclosed_context \
  -q
```

结果：`7 passed, 2 warnings in 0.21s`。

### 前端：artifact / Workbench 可见性基线

首次执行：

```bash
cd datalogue-web && npm test -- src/components/artifact-card.test.jsx src/components/workbench-panel.test.jsx src/components/workbench-route.test.jsx -q
```

结果：`FAIL`，原因为本 worktree 前端依赖未安装，`sh: vitest: command not found`。  
处理：执行 `cd datalogue-web && npm install`，安装本地依赖。

复验：

```bash
cd datalogue-web && npm test -- src/components/artifact-card.test.jsx src/components/workbench-panel.test.jsx src/components/workbench-route.test.jsx
```

结果：`3 passed (3), 31 passed (31)`。

```bash
cd datalogue-web && npm run lint
```

结果：`0 errors, 13 warnings`，均为既有 unused / hooks warnings。

```bash
cd datalogue-web && npm run build
```

结果：构建成功；保留 Vite 大 chunk warning。

## 4. 上游实现完成后必须复验的最小清单

后续 worker 或集成 owner 完成 Doris/Oracle 实现后，至少补跑并确认以下新增/更新测试：

1. `tests/test_datasource.py`：Doris capability、默认端口 `9030`、`dialect=mysql`、update partial stale dialect。
2. `tests/test_datasource.py` 或 service 级测试：`build_datasource_context(db_type=doris,dialect=doris)` 输出 `dialect=mysql`。
3. `tests/test_bi_worker_query_runtime.py` 或 runtime context 专项：`build_bi_runtime_context()` 兜住 Doris stale dialect，Oracle 保持 `oracle`。
4. `tests/test_analysis_blueprint.py`：Doris stale dialect 进入 MySQL timeout 分支，Oracle 走 Oracle 分支。
5. `tests/test_dataset.py` / query execution preview 专项：`preview_dataset_sql()` guard 前 Doris 已归一到 `mysql`，Oracle 不被 fail-closed。
6. `tests/test_datasource.py` / preview_table 专项：Doris 使用反引号与 `LIMIT :limit`，Oracle 使用 `FETCH FIRST`。
7. `tests/test_query_plan_compiler.py` / `tests/test_sql_dialect_adapter.py`：Oracle `FETCH FIRST` 编译执行链路通过，不再把 `oracle` 断言为 unsupported。
8. 前端数据源页测试：Doris 能显示为独立数据源类型，Oracle service_name/SID 表单保持可见。
9. Artifact / Workbench 回归：安全 payload 中 `artifact_ref/result_ref/artifact_card/row_count/column_count` 仍能投影到最终 answer 与 Workbench。

## 5. 真实环境验收保留位

本任务不搭建真实 Doris/Oracle。连接用户已有环境时，每个数据库至少记录：

- 数据源类型、datasource id、dataset id、conversation/thread id。
- 三类问题：明细查询、聚合指标查询、时间/条件过滤查询。
- 后端日志里的 `datalogue_execute_query_plan_bundle` 请求/响应摘要。
- 最终 answer 截图或 payload。
- Workbench artifact 截图或 payload。

## 6. 协调风险

- 当前 worktree 尚不能声明 Doris/Oracle 完整问数链路完成；Doris 无代码命中，Oracle compiler/adapter 仍 fail-closed。
- worker-4 的本轮产物是集成闸门与基线证据，后续需要 worker1/worker2/worker3 或 leader 集成实现后再把本报告更新为通过记录。
- 真实数据库验收仍依赖用户已有环境；本报告不把 mock/单元测试写成真实 Doris/Oracle 连通性证据。
