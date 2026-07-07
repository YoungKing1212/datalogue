# C2 RepairPatch Engine 开发计划

## Summary

C2 目标是补齐 RepairPlan 的真实字段级 Patch Engine：当字段不存在 / 字段漂移导致第一次执行失败时，系统自动生成 RepairPatch，经 Tool 校验、应用、重新编译 SQL 并重跑成功。

C2 等 C1 合并到 `b-first-c` 后再开始开发，不直接叠在未合并的 C1 分支上。

开发拆成 3 个 stacked PR。

## PR1：Patch Engine 内核

### 目标

离线实现字段级 RepairPatch Engine，不接 `/chat` 主链。

### 任务

- 新增 `datalogue-api/app/services/repair_patch.py`。
- 定义 `RepairPatch` envelope 辅助结构。
- 支持 `query_graph_patch` 和 `compiler_binding_patch`。
- 实现 field candidate collector：
  - 语义资产优先。
  - fallback 到当前 dataset selected columns。
  - 禁止读取未选字段。
  - 禁止跨 dataset / datasource。
- 实现粗粒度类型归一：
  - `text_like`
  - `date_like`
  - `number_like`
  - `boolean_like`
  - `enum_like`
  - `unknown`
- 实现规则基础评分。
- 定义 `FieldSemanticJudge` 接口。
- 实现 `MockSemanticJudge`。
- 新增本地 prompt 模板 `repair_plan_field_semantic_judge`。
- 实现 prompt input sanitizer。
- 实现 judge output schema。
- 实现 confidence merge/clamp。
- 实现 Tool validator：
  - patch_type 白名单。
  - operation_type 白名单。
  - dataset 一致。
  - replacement field 存在。
  - replacement field 属于 selected columns。
  - 类型组兼容。
  - 权限范围不扩大。
  - patch 不包含 SQL / raw result / schema dump。
- 实现 pure apply：
  - QueryGraphPatch apply。
  - CompilerBindingPatch apply。
  - 返回 patched copy、diff summary、trace-only details。
- 实现 sanitized summary builder。

### 测试

新增 `datalogue-api/tests/test_repair_patch_engine.py`。

覆盖：

- RepairPatch schema / operation 校验。
- candidate collector 语义资产优先。
- selected columns fallback。
- 未选字段不进入候选。
- 跨 dataset 拒绝。
- 类型组兼容。
- 类型组冲突 fail closed。
- mock semantic judge。
- prompt input 不含物理字段名、表名、SQL、schema。
- merge/clamp 阈值：
  - 高置信自动修。
  - 中置信 requires_user_confirmation。
  - 低置信 blocked。
- validator 拒绝 raw SQL 注入。
- QueryGraphPatch apply 成功。
- CompilerBindingPatch apply 成功。
- target path 不存在 fail closed。
- apply 失败后原对象不变。
- diff summary 不含字段/schema/SQL。
- trace-only details 含完整 patch 信息。

### 验收命令

```bash
cd datalogue-api
python3 -m pytest tests/test_repair_patch_engine.py tests/test_repair_plan_contract.py -q
python3 -m py_compile app/services/repair_patch.py app/services/repair_plan.py
```

## PR2：RepairPlan 协议与真实链路

### 目标

把 PR1 的 Patch Engine 接入 C1 RepairPlan 生命周期和 `/chat/stream` 主链。

### 任务

- 扩展 repair event type：
  - `repair.patch_validated`
  - `repair.patch_applied`
  - `repair.recompile_started`
  - `repair.recompile_completed`
- 在字段失败分类后调用 RepairPatch Engine。
- 高置信自动 patch、重新编译、sql audit、重跑。
- 中置信发 `repair.confirmation_required`，P0 不继续执行。
- 低置信发 `repair.blocked`。
- RepairPlan artifact 内部保存 RepairPatch。
- Artifact API 只返回脱敏摘要。
- final payload 带：
  - result artifact
  - report artifact
  - repair_plan artifact
  - trace id
  - checkpoint ref
- conversation_state 写入 repair_plan fact，不写字段 patch 主体。
- query_artifact refs 串起 result/report/repair_plan。
- Langfuse/mock observation 记录 trace-only 字段 patch 详情。
- 真实验收 fixture 在 compiler binding 阶段注入字段漂移。
- QueryGraphPatch 通过单元 / 集成测试补覆盖。

### 测试

覆盖：

- `repair.patch_validated` user-visible payload 不含字段/schema/SQL。
- `repair.patch_applied` user-visible payload 不含 patch operations。
- RepairPlan Artifact API 不返回字段 ref。
- final answer 不包含字段替换详情。
- Langfuse/mock observation 可以看到字段级详情。
- 真实问题 + compiler binding 字段漂移自动重跑成功。
- 中置信只发 confirmation_required，不继续执行。
- 低置信 blocked。
- query_artifact / conversation_state refs 一致。

### 验收命令

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_repair_patch_engine.py \
  tests/test_repair_plan_contract.py \
  tests/test_event_envelope.py \
  tests/test_artifact_card_contract.py \
  tests/test_artifact_api.py \
  tests/test_bi_main_chain_acceptance.py \
  tests/test_chat.py \
  tests/test_observability.py -q
```

## PR3：前端承接与页面 E2E

### 目标

让用户在 Chat timeline 中看到业务级自动修复过程，并确保会话切换不串台。

### 任务

- chat-adapter 解析新增 repair patch events。
- timeline 映射：
  - 检测到查询口径异常。
  - 生成修复方案。
  - 校验修复方案。
  - 应用修复并重试。
  - 查询完成。
- 中置信 confirmation card 占位：
  - 显示“需要确认后继续”。
  - 按钮禁用或提示后续开放。
- ArtifactCard 展示 repair_plan related ref。
- 前端 sanitize：
  - 不展示字段名。
  - 不展示字段候选。
  - 不展示表名、schema、SQL、patch operations。
- 历史回放不伪造 RepairPlan。
- 页面 E2E 验证切换会话后 repair timeline / ArtifactCard 不串台。

### 测试

覆盖：

- chat-adapter repair patch event mapping。
- timeline 自动修复节点。
- confirmation card 占位。
- ArtifactCard repair_plan ref。
- 用户可见 payload 泄露扫描。
- 旧会话不伪造 RepairPlan。

### 验收命令

```bash
cd datalogue-web
npm run test -- \
  src/assistant/chat-adapter.test.js \
  src/assistant/MyMessage.test.jsx \
  src/components/artifact-card.test.jsx \
  src/components/chat-page.test.jsx \
  tests/unit/assistant/thread-list-new-conversation.test.jsx
npm run lint
npm run build
```

## 页面与五件套验收

启动本地服务：

```bash
cd datalogue-api
uvicorn app.main:app --reload --port 8000
```

```bash
cd datalogue-web
npm run dev
```

真实问题：

```text
查询杨凯 2024 年工作日志
```

验收必须记录：

- 页面 Chat timeline。
- ArtifactCard related_refs。
- SSE/event envelope。
- 后端日志。
- Langfuse/mock observation。
- query_artifact。
- conversation_state。

同一组标识必须一致：

- task_id
- trace_id
- repair_plan_ref
- result artifact_ref
- checkpoint_ref

## 发布前闸门

- C1 已合并到 `b-first-c`。
- C2 PR1/PR2/PR3 依次 rebase。
- 用户可见层无字段、表、schema、SQL、patch operations 泄露。
- LLM 不输出可执行 SQL。
- Patch apply 不原地修改对象。
- 自动化 + 页面 E2E + 五件套记录都通过。
