# C2 RepairPatch 字段漂移自动修复设计

## 1. 阶段目标

C2 的目标是把 C1 的 RepairPlan 从“协议与自动化 fixture”推进到真实可执行的字段级 Patch Engine。

C2 P0 聚焦一类失败：字段不存在 / 字段漂移。系统在首次执行失败后，自动生成字段级 RepairPatch，由 Tool 校验、应用到 QueryGraph 或 compiler binding，重新编译 SQL 并重跑，最终完成真实查数。

本阶段不接 AgentScope runner，不做独立 BI 工作台，不做管理员 RepairPlan 详情 UI，不允许 LLM 生成可执行 SQL。

## 2. 核心原则

- RepairPatch 不是 SQL patch。所有最终 SQL 必须由 Tool 编译和方言适配产生。
- 高置信字段修复自动执行，中置信只保留确认协议和占位 UI，低置信阻断。
- LLM 只做业务语义裁判，不做最终执行裁判；最终 confidence 由 Tool merge/clamp。
- 用户可见层只展示业务级修复摘要，不展示字段名、表名、schema、SQL、patch operations 或 raw result。
- 字段级详情只进入 trace-only metadata、Langfuse observation 和后端日志。

## 3. C2 P0 范围

### 3.1 实现范围

- 新增统一 `RepairPatch` envelope。
- 支持 `query_graph_patch` 和 `compiler_binding_patch` 两种 patch type。
- 字段候选来源采用语义资产优先，不足时 fallback 到当前 dataset 的 selected columns。
- 类型兼容采用粗粒度类型组。
- Patch apply 使用纯函数，输入原对象，返回 patched copy、脱敏 diff summary 和 trace-only details。
- RepairPlan artifact 保存内部 patch 结构；Artifact API 只返回脱敏摘要。
- 新增 patch 阶段事件，支撑页面 timeline 和五件套验收。

### 3.2 不做范围

- 不读取未选中的 datasource columns。
- 不跨 dataset 或 datasource 选字段。
- 不新增 `repair_patch` 表。
- 不把中置信确认点击后的继续执行放入 P0。
- 不做 AgentScope runtime 接管。
- 不开放字段 patch 详情给普通用户。

## 4. RepairPatch IR

`RepairPatch` 是 C2 的统一 patch envelope。

```text
RepairPatch
  - patch_id
  - patch_type
  - dataset_id
  - failure_class
  - confidence
  - confidence_band
  - requires_user_confirmation
  - operations
  - validation
  - trace_only_metadata
```

`patch_type` 第一阶段只允许：

- `query_graph_patch`
- `compiler_binding_patch`

### 4.1 QueryGraphPatch

用于修 QueryGraph 中的逻辑字段引用。

```text
operation_type = replace_logical_field
target_path
source_field_intent
replacement_field_ref
reason
```

### 4.2 CompilerBindingPatch

用于修 template、blueprint 或 compiler binding 中的字段绑定。

```text
operation_type = replace_binding_field
binding_key
source_field_intent
replacement_field_ref
reason
```

## 5. 字段候选来源

候选字段只来自当前 confirmed dataset。

读取顺序：

1. 语义资产：指标、维度、字段业务名、字段注释、manifest 摘要、已治理资产。
2. selected columns fallback：当前 dataset 已选字段元数据。

禁止：

- 读取未选字段。
- 跨 dataset。
- 跨 datasource。
- 扩大权限范围。
- 把候选字段列表进入用户可见 payload。

## 6. Confidence 计算

### 6.1 规则基础分

规则基础分考虑：

- 字段业务名相似度。
- 字段注释相似度。
- 语义资产是否命中。
- 字段类型组是否兼容。
- 是否同 dataset。
- 是否在 selected columns 范围内。
- 是否权限范围不扩大。
- 语义类别是否一致，例如人员、时间、金额、组织、状态。

### 6.2 LLM 业务语义裁判

LLM 只看中文业务名 / 注释和粗粒度类型，不看物理字段名、表名、SQL、schema 或 raw result。

输入只允许：

- question_intent_summary
- failed_field_intent_summary
- candidate_business_name
- candidate_business_description
- candidate_coarse_type
- candidate_source
- candidate_governance_status

输出：

- semantic_equivalent
- semantic_score
- business_reason
- risk_flags

### 6.3 Tool merge/clamp

Tool 是最终裁判。

- 字段不存在、跨 dataset、权限扩大或类型组冲突时直接 fail closed。
- LLM 高分但硬约束不通过时，最终分数归零。
- 规则低分但 LLM 高分时，最多提升到中置信。
- 高置信必须同时满足规则强命中和 LLM 业务等价判断。

阈值：

- `confidence >= 0.85`：自动修复。
- `0.60 <= confidence < 0.85`：发出确认协议，P0 不继续执行。
- `confidence < 0.60`：阻断。

## 7. 类型兼容

字段类型归一到粗粒度类型组：

- `text_like`
- `date_like`
- `number_like`
- `boolean_like`
- `enum_like`
- `unknown`

规则：

- 同组允许替换。
- `enum_like` 可视作受限 `text_like`，最多中置信。
- `unknown` 不能自动高置信。
- 类型组冲突直接 fail closed。
- 明显语义类别冲突直接 fail closed。

## 8. Patch Apply

Patch apply 必须是纯函数。

```text
apply_repair_patch(original, patch)
  -> patched_copy
  -> diff_summary
  -> trace_only_details
```

要求：

- 原 QueryGraph / compiler binding 不变。
- apply 失败时不产生部分修改。
- `diff_summary` 是脱敏业务摘要。
- `trace_only_details` 保存字段级详情。
- retry/checkpoint 恢复使用 patched copy，不污染原上下文。

## 9. RepairPlan Artifact

C2 P0 不新增 `repair_patch` 表。

保存方式：

- RepairPatch 作为 RepairPlan artifact 的内部结构保存。
- trace-only metadata / Langfuse / 后端日志保存完整字段级 patch 详情。
- Artifact API 对 `kind="repair_plan"` 只返回脱敏摘要。

Artifact API 可返回：

- kind
- failure_class
- status
- attempts
- business_summary
- repair_strategy
- confidence_band
- requires_user_confirmation
- validation_summary
- risk_flags
- trace_ref
- checkpoint_ref
- created_at

Artifact API 禁止返回：

- operations
- replacement_field_ref
- source_field_ref
- 字段业务名
- 字段注释
- 表名
- schema
- SQL
- raw result

## 10. 事件流

C2 在现有 `repair.*` 基础上新增：

- `repair.patch_validated`
- `repair.patch_applied`
- `repair.recompile_started`
- `repair.recompile_completed`

高置信自动修复事件顺序：

```text
repair.evaluated
repair.plan_created
repair.patch_validated
repair.patch_applied
repair.recompile_started
repair.recompile_completed
repair.rerun_started
repair.rerun_completed
answer.completed
```

中置信占位事件：

```text
repair.evaluated
repair.plan_created
repair.confirmation_required
```

低置信 / 不可修事件：

```text
repair.evaluated
repair.blocked
```

用户可见 event payload 只允许业务级摘要、状态、confidence_band、attempts、refs、task_id 和 trace_id。

## 11. 前端承接

Chat timeline 展示业务级自动修复节点：

- 检测到查询口径异常。
- 生成修复方案。
- 校验修复方案。
- 应用修复并重试。
- 查询完成。

中置信占位展示“需要确认后继续”，按钮可以禁用或提示后续开放。

ArtifactCard 的 `related_refs` 展示 repair_plan ref、trace ref、checkpoint ref，但不展示字段 patch 详情。

## 12. 真实验收策略

真实验收问题继续使用：

```text
查询杨凯 2024 年工作日志
```

字段漂移注入点：

- 真实验收主路径使用 compiler binding 阶段注入错误字段绑定。
- QueryGraphPatch 通过单元 / 集成测试补覆盖。

完成标准：

- 自动化测试通过。
- 页面 E2E 通过。
- 真实问题首次失败，RepairPlan 自动生成并应用 compiler_binding_patch 后重跑成功。
- 页面、SSE/event envelope、后端日志、Langfuse/mock observation、query_artifact、conversation_state 五件套一致。
- 用户可见层不泄露字段、表、schema、SQL、patch operations。

## 13. 分支与 PR 策略

C2 等 C1 合并到 `b-first-c` 后再开始。

开发拆成 3 个 stacked PR：

- PR1：离线 Patch Engine 内核。
- PR2：RepairPlan 协议与真实链路。
- PR3：前端承接与页面 E2E。

PR1 不接 `/chat` 主链；PR2 接主链和五件套；PR3 接前端 timeline / ArtifactCard / E2E。
