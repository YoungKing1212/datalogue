# 2026-06-28 C1 RepairPlan 验收记录

用途：记录 C1 RepairPlan 真实成功链路加固分支的自动化证据和真实问题复验结果。本文档刻意区分“自动化可重复成功链路”和“真实业务成功链路”，避免把测试替身误记为生产可用。

## 基本信息

- 验收时间：2026-06-28 12:22-12:34
- 实现分支：`c1-repair-plan`
- 工作区：`.worktrees/c1-repair-plan`
- 目标真实问题：`查询杨凯 2024 年工作日志`
- RepairPlan ref 约定：统一使用 `artifact:<uuid>`，`ArtifactRef.ref_type="repair_plan"`，不引入 `repair_plan:<uuid>` 新前缀。
- UI 范围：C1 不做管理员详情 UI；字段级 patch / Tool 校验详情只进入后端日志、Langfuse observation 或 trace-only metadata，Artifact API 只返回脱敏摘要。

## 自动化验收结论

自动化 fixture 已覆盖 RepairPlan 成功链路：第一次 SQL 失败后生成 RepairPlan artifact，发出 repair event envelope，重跑成功，并在 final payload、trace index、`query_artifact` 和 `conversation_state.facts` 中写入同一组引用。

| 验收面 | 命令 | 结果 |
| --- | --- | --- |
| RepairPlan 契约 / event / Artifact / AgentScope / SQL audit / 主链 / Chat / Observability | `cd datalogue-api && python3 -m pytest tests/test_repair_plan_contract.py tests/test_event_envelope.py tests/test_artifact_card_contract.py tests/test_artifact_api.py tests/test_agentscope_event_adapter.py tests/test_sql_audit.py tests/test_bi_main_chain_acceptance.py tests/test_chat.py tests/test_observability.py -q` | 195 passed |
| RepairPlan 成功与 blocked 分支 | `cd datalogue-api && python3 -m pytest tests/test_bi_main_chain_acceptance.py::test_repair_plan_success_cross_checks_five_evidence_sets tests/test_bi_main_chain_acceptance.py::test_repair_plan_blocked_emits_repair_events_without_artifact_ref -q` | 2 passed |
| 前端 Chat Shell 承接 | `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js src/assistant/MyMessage.test.jsx src/components/artifact-card.test.jsx` | 3 个文件，32 passed |
| 前端质量门禁 | `cd datalogue-web && npm run lint`；`cd datalogue-web && npm run build` | 通过；保留既有 15 个 lint warning 和 Vite chunk warning |
| Python 编译 | `cd datalogue-api && python3 -m py_compile app/schemas/repair_plan.py app/services/repair_plan.py app/schemas/bi_workbench.py app/services/artifact_store.py app/api/artifacts.py app/api/chat.py app/graph/nodes.py app/schemas/__init__.py` | 通过 |

自动化成功链路关键断言：

| 验收项 | 当前证据 |
| --- | --- |
| SSE repair 事件 | `repair.evaluated -> repair.plan_created -> repair.rerun_started -> repair.rerun_completed -> answer.completed` |
| RepairPlan artifact | `kind="repair_plan"`，artifact id 使用 `artifact:<uuid>` |
| final payload | 包含 `repair_plan_ref`、`repair_status=rerun_completed`、`repair_failure_class=FIELD_NOT_FOUND`、`primary_ref`、`related_refs` |
| ArtifactCard refs | `related_refs` 包含 `ref_type="repair_plan"` |
| conversation_state | 写入 `kind=repair_plan` fact，包含 `repair_plan_ref`、`failure_class`、`repair_status`、`attempts`、`checkpoint_ref` |
| blocked 分支 | 发出 `repair.evaluated -> repair.blocked`，不伪造 `repair_plan_ref` 或 repair artifact |

## 真实链路复验

### 环境准备

- 后端使用 worktree 代码启动：`cd datalogue-api && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001`
- `.venv` 软链指向主工作区已安装依赖环境，`import langfuse` 返回 `4.7.1`。
- `.env` 软链指向主工作区后端环境文件。
- `GET http://127.0.0.1:8001/health` 返回 `{"status":"ok"}`。
- 启动日志未再出现 `No module named 'langfuse'`。

### 真实请求 1

请求：

```bash
curl -sS -N --max-time 180 \
  -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8001/api/chat/stream \
  -d '{"question":"查询杨凯 2024 年工作日志","dataset_id":10,"session_id":"c1-repair-live-20260628"}'
```

结果：

| 字段 | 值 |
| --- | --- |
| `conversation_id` | `19` |
| `message_id` | `44` |
| `trace_id` | `e59af4ac091d86038ef93ec25f03a94f` |
| `task_id` | `conv-19-msg-44` |
| `report_ref` | `artifact:2678bf5266934ee1924565af913bb55e` |
| `repair_status` | `blocked` |
| `repair_failure_class` | `FIELD_NOT_FOUND` |
| `repair_plan_ref` | `None` |

最终回答为失败诊断：SQL 引用了 `eas_personofile.create_time` / `eas_personofile.update_time` 等不存在字段。SQL audit 将其归为 `FIELD_NOT_FOUND` 且 `severity=architectural`，建议修正语义层字段映射，因此没有生成 RepairPlan artifact，也没有重跑成功。

### 真实请求 2

重启后端并复验最新代码后，使用新 session：

```bash
curl -sS -N --max-time 180 \
  -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8001/api/chat/stream \
  -d '{"question":"查询杨凯 2024 年工作日志","dataset_id":10,"session_id":"c1-repair-live-20260628-v2"}'
```

结果：

| 字段 | 值 |
| --- | --- |
| `conversation_id` | `20` |
| `message_id` | `46` |
| `trace_id` | `8334a4eb9224b33b5c2a729c210d9ece` |
| `task_id` | `conv-20-msg-46` |
| `report_ref` | `artifact:7a7922c5c2f24e1a85d69fb75ea73940` |
| `repair_plan_ref` | `None` |
| 最终回答 | `运行分析蓝图前还需要补充参数：person_name` |

该轮没有进入 SQL repair，因为规划路径提前停在蓝图参数缺失。它说明真实问题链路仍不稳定，受当前蓝图参数抽取和 planner 输出校验影响。

## Langfuse 验收

- SDK 依赖层：通过主工作区 `.venv` 验证 `langfuse_import=ok 4.7.1`，后端启动不再因缺少 SDK 降级。
- 自动化层：当前测试覆盖本地 trace index / mocked 或 no-op observation，不依赖外部 Langfuse UI。
- 真实 UI 层：本轮没有完成 Langfuse UI 手工核对，因此不能把 C1 标为“真实 Langfuse observation 完整通过”。

## 当前结论

- C1 工程契约：通过。
- RepairPlan 自动化成功链路：通过。
- 普通用户脱敏边界：通过。
- AgentScope adapter 边界：通过，仅映射 `repair.*` event，不启动 runner。
- 真实业务问题 `查询杨凯 2024 年工作日志`：未通过成功查数。
- 真实 Langfuse UI 五件套：未完成。

## 残留问题

1. 真实问题仍被语义资产挡住：当前 SQL 会引用 `eas_personofile.create_time` / `update_time` 这类不存在字段，需要修正 dataset 10 的字段资产或蓝图映射。
2. SubAgent planner 曾输出 `reference_assets.usage="template_reference"`，但契约只允许 `candidate/reference/rejected/selected`，导致 fallback 到 QueryGraph。
3. 第二次真实请求提前要求 `person_name` 参数，说明蓝图参数抽取没有稳定识别“杨凯”。
4. 当前 RepairPlan 仍复用 `sql_audit -> increment_retry -> dsl_generate` 的重试链；尚未实现字段级 QueryGraph patch Tool 引擎。
5. 真实失败回答仍可能被写入 `last_success_task`，需要单独收口“失败查询不得写 last_success_task”。
6. Langfuse UI 需要在真实成功查询后按同一 `trace_id` 手工或 Playwright 辅助核对 observation。
