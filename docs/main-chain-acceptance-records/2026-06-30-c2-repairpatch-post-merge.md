# 2026-06-30 C2 RepairPatch 合并后验收记录

用途：记录 C2 RepairPatch 在合并到 `b-first-c` 后的可重复验收结果。本文档只记录本次实际核对过的证据；未重跑的浏览器页面和 Langfuse UI 不伪造成通过项。

## 基本信息

- 验收时间：2026-06-30 09:45
- 验收分支：`b-first-c`
- 验收 commit：`3ad8bb2c`
- C2 合并记录：
  - `3ad8bb2c`：Merge pull request #19 from `c2-repair-patch-stream-pr2`
  - `e6b33714`：Merge pull request #20 from `c2-repair-patch-frontend-pr3`
  - `5d62e2e7`：`test: cover RepairPatch field drift workflow e2e`
  - `1f7307db`：`feat: surface RepairPatch timeline in chat`
  - `c156df6f`：`feat: wire RepairPatch into chat retry stream`
- 验收场景：注入字段映射漂移，触发 `FIELD_MAPPING_DRIFT -> RepairPatch -> QueryGraph patch -> 重新编译 SQL -> 二次真实执行成功`
- 代表问题：`查询杨凯 2024 年工作日志`
- 代表坏字段：`old_work_date_for_c2_e2e`
- 修复后字段：`work_date`
- 执行方式：内部-only workflow E2E pytest，使用临时 SQLite 数据源保留真实 SQL 执行，不启动公开 `/chat/stream` HTTP 服务。

## 验收结论

| 验收面 | 结论 |
| --- | --- |
| RepairPatch 主路径 | 通过。内部 E2E 覆盖首次坏 SQL 失败、SQL 诊断归类、RepairPatch 生成、Tool 校验、QueryGraph patch、重新编译、二次 SQL 成功。 |
| 用户可见脱敏 | 通过。RepairPatch 用户可见摘要不包含表名、字段名、SQL、`query_plan`、`trace_only_metadata` 或 raw result。 |
| SSE / event envelope 协议 | 通过自动化。`repair.patch_applied` 事件类型存在，公开 payload 只保留 `repair_plan_ref` 与 `repair_patch_summary`，内部 patch body 被移除。 |
| 前端 Chat Shell 承接 | 通过自动化。前端 adapter 能把 `repair.patch_applied` 和 `repair_patch` graph step 映射为单个业务级 `repair_patch/自动修复` timeline 节点。 |
| Artifact / conversation_state 五件套 | C2 本次未新增真实页面会话记录；Artifact refs 与旧会话安全边界仍由 B/C1/DAT-17 自动化和历史页面验收覆盖。 |
| Langfuse UI | 本次未重跑真实 UI observation；不标为通过。后续若要做发布级验收，应启动真实 API/前端并用同一 trace id 核对 Langfuse 页面。 |

## RepairPatch 内部 E2E 证据

测试用例：`tests/test_repair_patch_stream.py::test_workflow_e2e_repairs_injected_field_mapping_drift`

该用例构造临时 SQLite 表：

- `work_log.work_date`
- `work_log.person_name`

首轮注入坏 SQL：

```sql
SELECT "work_log"."old_work_date_for_c2_e2e" AS "工作日期" FROM "work_log"
```

测试断言的事件顺序：

| 顺序 | 节点 | 说明 |
| --- | --- | --- |
| 1 | `lead_agent` | 主链进入工作流 |
| 2 | `schema_recall` | 注入带旧字段的语义上下文 |
| 3 | `dsl_generate` | 产出首轮坏 SQL |
| 4 | `dsl_validate` | DSL 校验通过，进入编译/执行 |
| 5 | `dsl_compiler` | 首轮编译阶段 |
| 6 | `sql_execute` | 首轮执行失败，真实 SQLite 报字段不存在 |
| 7 | `sql_audit` | 诊断归类为 `FIELD_MAPPING_DRIFT` |
| 8 | `repair_patch` | 生成并应用字段映射 RepairPatch |
| 9 | `dsl_compiler` | 基于 patch 后 QueryGraph 重新编译 |
| 10 | `sql_execute` | 二次执行成功 |
| 11 | `report_generator` | 进入回答生成阶段 |

关键断言：

- `audit_code == "FIELD_MAPPING_DRIFT"`
- `repair_status == "patch_applied"`
- patched SQL 为：

```sql
SELECT "work_log"."work_date" AS "工作日期" FROM "work_log"
```

- `final_row_count == 2`
- `final_error is None`
- `retry_trace[-1].status == "success"`
- `repair_patch_summary.failure_class == "FIELD_MAPPING_DRIFT"`
- `public_summary_forbidden_hits == []`

## 自动化验收命令

| 验收项 | 命令 | 结果 |
| --- | --- | --- |
| C2 字段漂移内部 E2E 单例 | `cd datalogue-api && .venv/bin/python -m pytest tests/test_repair_patch_stream.py::test_workflow_e2e_repairs_injected_field_mapping_drift -q` | `1 passed` |
| C2 后端回归 | `cd datalogue-api && .venv/bin/python -m pytest tests/test_repair_patch_stream.py tests/test_repair_patch_engine.py tests/test_repair_plan_contract.py tests/test_event_envelope.py tests/test_sql_audit.py tests/test_query_plan_compiler.py tests/test_chat.py -q` | `192 passed, 3 skipped` |
| C2 前端承接回归 | `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js src/components/task-timeline.test.jsx src/components/artifact-card.test.jsx src/assistant/MyMessage.test.jsx` | `4 files passed, 48 passed` |
| 前端 lint | `cd datalogue-web && npm run lint` | 通过，保留既有 `15 warnings` |
| 前端 build | `cd datalogue-web && npm run build` | 通过，保留既有 Vite chunk size warning |
| 空白检查 | `git diff --check` | 通过 |

## 公开层安全边界

本次合并后验收重点确认 C2 没有把字段级 patch 细节泄漏到普通用户可见面：

- `tests/test_event_envelope.py::test_chat_sse_public_payload_keeps_repair_patch_summary_but_removes_internal_body`
  - 公开 SSE payload 保留 `repair_patch_summary`
  - 移除内部 `repair_patch`
  - 移除内部 `repair_patch_apply`
  - 移除 `trace_only_metadata.replacement_field_ref`
- `tests/test_repair_patch_stream.py::test_repair_patch_node_applies_query_plan_patch_and_recompiles`
  - 内部 trace-only metadata 可保存字段 ref
  - 用户可见 summary 不包含 `work_log`
  - 用户可见 summary 不包含 `sql`
- `datalogue-web/src/assistant/chat-adapter.test.js`
  - `repair.patch_applied` 和 final payload 中的 `repair_patch.trace_only_metadata` 不进入普通用户 timeline
  - repair timeline 被收敛为单个业务节点，避免多条 repair event 造成重复 running 状态

## 五件套分层说明

C2 的新增能力是 RepairPatch 自动修复，不是重新实现完整 Chat 五件套。合并后验收按以下分层理解：

| 五件套位置 | 本次 C2 证据 | 状态 |
| --- | --- | --- |
| 页面 Chat 结果和 ArtifactCard | 前端 adapter / timeline / message / ArtifactCard 自动化通过；未启动浏览器页面重跑真实会话 | 部分通过，需发布前手工补证 |
| SSE / event envelope | `repair.patch_applied` 事件和公开 payload 脱敏测试通过 | 通过 |
| 后端日志 / checkpoint | 内部 E2E 的 `retry_trace[-1].status == "success"`；工作流事件顺序包含 repair patch 重跑 | 通过 |
| Langfuse trace / observation | 本次未启动真实 Langfuse UI 核对 | 未完成 |
| `query_artifact` / `conversation_state` | C2 内部 E2E 不落真实 conversation；B/C1/DAT-17 已覆盖 artifact refs 和旧会话边界 | C2 本次不新增证据 |

## 验收判断

C2 RepairPatch 合并后核心链路验收通过：

- 已证明 `FIELD_MAPPING_DRIFT` 可以触发 RepairPatch。
- 已证明 RepairPatch 不直接 patch raw SQL，而是生成 QueryGraph patch 后重新编译。
- 已证明 Tool 校验后可以把旧字段映射到当前数据集中可用字段。
- 已证明二次 SQL 在真实 SQLite 数据源上执行成功。
- 已证明用户可见 payload 不暴露表、字段、SQL、raw result 或 trace-only patch 主体。

尚未完成的发布级补证：

- 启动本地 API 和前端，跑一次带真实 `conversation_id / task_id / trace_id / artifact_ref / repair_plan_ref` 的浏览器链路。
- 在 Langfuse UI 中用同一 `trace_id` 核对 RepairPatch 生命周期 observation。
- 将真实页面补证追加到本文档，或新增 `C2 RepairPatch live five-piece` 记录。
