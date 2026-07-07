# C1 RepairPlan 真实成功链路加固设计

## 1. 背景

B-first C-ready 阶段已经把主链协议、`capability_manifest`、`ask_bi`、`DatalogueEventEnvelope`、Artifact refs、候选数据集确认、retry checkpoint、AgentScope Shell Adapter 和现有 Chat Shell 承接合入 `b-first-c`。

DAT-18 的验收记录显示，当前链路已经能完成页面回放、SSE / event envelope、Artifact API、`query_artifact`、`conversation_state` 和本地 trace index 的一致性核对。但真实问题 `查询杨凯 2024 年工作日志` 仍未达到完整成功验收：后端环境缺少 `langfuse` SDK，真实 Langfuse observation 未写入；真实业务 SQL 因语义层引用不存在字段 `eas_personofile.create_time` 受控失败。

C1 的目标是补齐这个真实成功链路缺口，而不是直接进入完整 C 产品形态。本文继续使用“真实成功链路”表述时，含义限定为：C1 协议链路、`repair.*` 事件、Artifact refs、失败分类、受控 retry / fixture 验证，以及现有可信 template 路径下的真实业务成功验收；它不是 `FIELD_NOT_FOUND` / `FIELD_MAPPING_DRIFT` 字段漂移自动修复闭环。

## 2. 目标

C1 必须让真实问题 `查询杨凯 2024 年工作日志` 在现有 Chat Shell 中通过可信 template 路径成功返回业务结果，并且同一个 `task_id`、`trace_id`、`artifact_ref` 能在页面、SSE / event envelope、后端日志、Langfuse observation、`query_artifact` 和 `conversation_state` 中互相核对。只有实际触发 RepairPlan 的 fixture 或失败分支才要求核对 `repair_plan_ref`。

C1 同时必须提供稳定自动化 fixture：构造一次可控 SQL 失败，触发 RepairPlan，完成协议校验、事件、Artifact refs、checkpoint 和受控重跑成功断言，防止后续回归。该 fixture 验证 C1 协议链路，不等同于真实字段漂移自动修复引擎。

完成标准：

- 真实业务问题成功查出业务结果。
- 页面展示业务结果、ArtifactCard 和业务级修复摘要。
- fixture 或触发修复的分支中，SSE / event envelope 记录完整 `repair.*` 生命周期。
- 后端日志记录 failure classification、RepairPlan 协议校验和受控 rerun result。
- Langfuse UI 能用同一 `trace_id` 查到 observation。
- `query_artifact` 能用 `artifact_ref` 找到产物。
- fixture 或触发修复的分支中，`conversation_state` 能查到 `repair_plan_ref` 和 `checkpoint_ref`。
- 自动化 fixture 覆盖失败、修复、重跑、产物、trace 和状态持久化。

## 3. 非目标

C1 不做以下事项：

- 不做独立 BI 工作台。
- 不做完整 Artifact 详情面板。
- 不启动 AgentScope runner。
- 不替换 `/chat/stream`。
- 不开放新的公开 AgentScope API。
- 不启动 ReportAgent、PythonAgent 或 AuditAgent。
- 不让 LLM 直接生成可执行 SQL。
- 不把 raw SQL、raw result、完整 schema 或完整 RepairPlan patch 主体暴露给普通用户或用户可见 SSE。
- 不实现真实字段级 patch / apply / recompile 引擎。
- 不把 `FIELD_NOT_FOUND` / `FIELD_MAPPING_DRIFT` 字段漂移标记为已具备自动修复闭环。

这些能力作为 C2 / C3 的后续口子保留。

## 4. RepairPlan v1 协议

C1 引入 `RepairPlan v1`，它不是 SQL，也不是直接 QueryGraph patch，而是受限的修复意图协议。LLM 只能提出 RepairPlan；C1 负责协议校验、失败分类、脱敏摘要、事件、Artifact refs、checkpoint、受控重跑上限和 fixture 验证。

真实字段级 patch / apply / recompile 不属于 C1。`FIELD_NOT_FOUND`、`FIELD_MAPPING_DRIFT` 的字段候选、`RepairPatch` IR、Tool 校验、应用到 QueryGraph 或 compiler binding、重新编译和真实漂移验收由 C2 的 `RepairPatch Engine` 承接。

示例结构仅说明 RepairPlan 协议形状，不代表 C1 已实现字段漂移自动修复引擎：

```json
{
  "schema_version": "repair_plan.v1",
  "failure_class": "FIELD_NOT_FOUND",
  "repair_actions": [
    {
      "action": "replace_field",
      "target": "eas_personofile.create_time",
      "candidate": "eas_personofile.biz_date",
      "reason": "候选字段更符合工作日志时间过滤"
    }
  ],
  "confidence": 0.82,
  "requires_user_confirmation": false,
  "rerun_policy": {
    "max_attempts": 1
  }
}
```

初始 action 作为协议枚举保留：

- `replace_field`：字段不存在或字段绑定失效时的修复意图；C1 只保留协议、分类和受控 fixture 验证，真实字段替换引擎归 C2。
- `replace_table`：表不存在或表绑定失效时的修复意图；真实表绑定修复引擎归 C2。
- `replace_dialect_function`：函数或方言不兼容时替换函数表达方式。
- `cast_type`：类型转换错误时增加受控类型转换。
- `diagnose_only`：不可自动修复的问题只输出诊断。
- `block_repair`：触发安全风险时 fail closed。

Tool 校验职责在 C1 只覆盖协议和安全边界，字段候选计算和 patch 应用留到 C2：

- 校验 `schema_version` 和 `failure_class` 是否受支持。
- 校验 candidate 存在于当前数据源真实 schema 或当前 QueryGraph 资产上下文。
- 校验 RepairPlan 不跨 dataset。
- 校验不新增不可见 schema、raw SQL 或 raw result。
- 校验不会扩大查询范围，例如扩大时间范围或绕过权限。
- 校验不会绕过 QueryGraph compiler 和方言适配。
- 校验失败时进入 `repair.blocked`，不重跑。

## 5. 失败分层与重跑策略

所有 SQL 执行失败都进入 repair evaluation，但不是所有失败都允许自动重跑。C1 的重跑只覆盖现有受控路径和自动化 fixture；真实字段漂移修复不在 C1 完成标准内。

失败分三层：

| 层级 | failure_class | 行为 |
| --- | --- | --- |
| 可进入受控修复协议并按策略重跑 | `FIELD_NOT_FOUND`、`TABLE_NOT_FOUND`、`DIALECT_FUNCTION_UNSUPPORTED`、`TYPE_CAST_ERROR` | 生成 RepairPlan，完成协议校验；字段 / 表漂移真实 patch 到 C2，C1 只验证 fixture 或现有受控路径 |
| 只诊断不重跑 | `PERMISSION_DENIED`、`DATASOURCE_UNREACHABLE`、`QUERY_TIMEOUT`、`RESULT_TOO_LARGE` | 输出业务级诊断和 ArtifactCard，不自动重跑 |
| fail closed | 疑似越权、raw SQL 注入、跨数据集访问、schema 泄露风险 | 输出安全阻断，不生成可执行修复 |

动态重跑次数：

- 字段不存在 / 表不存在：最多 1 次。
- 函数 / 方言不兼容：最多 2 次。
- 类型转换错误：最多 1 次。
- 权限不足、数据源不可达、超时、结果过大：0 次。
- 越权、注入、跨数据集、泄露风险：0 次并 fail closed。

重跑次数必须写入 trace 和 `conversation_state`，避免无限循环。

## 6. 用户确认规则

高置信 RepairPlan 可以进入受控重跑。判定条件：

- `confidence >= 0.8`。
- 只包含一个低风险 action，例如 `replace_field`、`cast_type` 或 `replace_dialect_function`。
- candidate 来自当前数据源真实 schema 或当前 QueryGraph 资产上下文。
- 不跨数据集。
- 不新增表，除非表替换已经由 Tool 证明是同一业务资产的绑定修复。
- 不扩大时间范围。
- 不引入 raw SQL。
- Tool 校验通过。

低置信、多候选、多 action、涉及口径变化或新增表时，必须返回修复确认卡。

确认卡双层展示：

- 普通用户只看到业务级解释，例如“系统发现时间条件引用的数据口径不可用，建议改用工作日志日期口径继续查询”。
- C1 不做开发 / 管理员详情 UI；RepairPlan 协议校验结果、内部定位和后续 C2 RepairPatch 详情只允许进入 Langfuse observation、后端日志和 trace-only metadata。

用户确认时只提交：

- `repair_plan_ref`
- `checkpoint_ref`
- `selected_action`

用户确认时不得提交字段、schema、SQL 或 raw result。

## 7. 执行链路

C1 主链仍走现有 `/chat/stream`。

链路顺序：

1. DatasetAgent / QueryGraph 正常生成并执行 SQL。
2. SQL 执行失败后，执行层分类失败原因。
3. 所有 SQL 失败进入 repair evaluation。
4. fail closed 问题输出 `repair.blocked`。
5. 只诊断问题输出业务级诊断和 ArtifactCard。
6. 可进入修复协议的问题生成 RepairPlan。
7. C1 校验 RepairPlan 协议、安全边界和 retry policy。
8. 高置信通过后进入现有受控重跑路径或 fixture 路径；低置信返回确认卡。
9. 重跑成功后 final payload 带上业务结果、ArtifactCard 和 repair refs。
10. 重跑失败后停止，输出诊断，不无限循环。

关键边界：

- LLM 不直接生成可执行 SQL。
- C1 负责 RepairPlan 协议校验、事件、refs、checkpoint 和受控重跑边界；QueryGraph / compiler binding 的字段级 patch、apply 和重新编译归 C2。
- raw SQL / raw result 只允许留在 control plane、artifact store 或 trace 受控区域。
- 普通用户可见面只看到业务级修复摘要。

## 8. Event Envelope

C1 复用现有 `DatalogueEventEnvelope`，只新增 `repair.*` event type。

新增事件：

- `repair.evaluated`
- `repair.plan_created`
- `repair.confirmation_required`
- `repair.rerun_started`
- `repair.rerun_completed`
- `repair.failed`
- `repair.blocked`

用户可见 payload 只允许包含：

- 业务级修复摘要。
- 修复状态。
- 是否需要确认。
- `repair_plan_ref`。
- `checkpoint_ref`。

trace / control payload 可包含：

- `failure_class`。
- attempt index。
- Tool validation result。
- blocked reason。
- trace/ref。

禁止进入用户可见面：

- raw SQL。
- raw result。
- 完整 schema。
- 完整 RepairPlan / RepairPatch 主体。
- control_plane 主体。

AgentScope C1 范围：

- `AgentScopeEventAdapter` 识别并映射 `repair.*` envelope。
- 不启动 AgentScope runner。
- 不替换 `/chat/stream`。
- `AgentScopeShellAdapter` 继续只允许 `ask_bi`。
- AgentScope event adapter 只消费 envelope，不读取 control_plane 主体。

## 9. 前端 Chat Shell

C1 只使用现有 Chat Shell。

普通用户看到：

- 查询结果。
- ArtifactCard。
- 业务级修复摘要。
- 低置信时的修复确认卡。

普通用户不看到：

- 字段名。
- 表名。
- schema。
- SQL。
- raw result。
- RepairPlan / RepairPatch 详情。

开发 / 管理员详情能力 C1 不实现独立面板，只预留 trace-only / Langfuse / 后端日志数据：

- `failure_class`。
- `repair_plan_ref`。
- Tool 校验结果。
- trace/ref。
- attempt history。

历史回放：

- 有真实 RepairPlan metadata 时展示业务级摘要。
- 没有 RepairPlan 的旧会话不伪造修复卡。
- `repair_plan_ref` 读取必须 fail closed。

## 10. 持久化与引用

C1 不新建 repair_plan 表，先复用 `conversation_state`、`query_artifact` 和 ArtifactCard refs。

`conversation_state.facts` 写入：

```json
{
  "kind": "repair_plan",
  "repair_plan_ref": "artifact:<uuid>",
  "failure_class": "FIELD_NOT_FOUND",
  "repair_status": "rerun_completed",
  "attempts": 1,
  "requires_user_confirmation": false,
  "checkpoint_ref": "checkpoint:<uuid>"
}
```

ArtifactCard `related_refs` 增加：

- `repair_plan_ref`
- `retry_checkpoint_ref`
- `trace_ref`

读取边界：

- 普通用户只读取业务级 repair summary。
- `repair_plan_ref` 使用现有 `artifact:<uuid>` 句柄，`ArtifactRef.ref_type="repair_plan"`，不引入 `repair_plan:<uuid>` 新前缀。
- Artifact API 对 `kind="repair_plan"` 只返回脱敏 RepairPlan 摘要；RepairPatch、字段映射主体和 Tool 内部详情只保存在 Langfuse observation、后端日志和 trace-only metadata。
- `repair_plan_ref` 读取必须 fail closed。
- 不返回 raw SQL、raw result 或完整 schema。

## 11. Langfuse 要求

C1 必须同步修复本地后端 `langfuse` SDK / observation，并区分自动化和真实验收层级。

完成标准：

- 自动化测试覆盖 SDK 初始化或 mocked / no-op observation 写入路径。
- 本地服务真实请求能写入 Langfuse trace / observation。
- Langfuse UI 可通过同一 `trace_id` 查到链路。
- RepairPlan 关键阶段作为 observation 或 metadata 可见。
- 真实验收必须由手工或 Playwright 辅助核对 Langfuse UI，并写入验收记录。
- 如果 SDK 不通或 UI 查不到 observation，C1 不算完成。

## 12. 验收问题

C1 必须通过两个问题。

### 12.1 真实业务验收问题

```text
查询杨凯 2024 年工作日志
```

必须验证：

- 页面 Chat 返回真实业务结果。
- ArtifactCard 可见。
- 真实业务成功路径至少有同一 `task_id / trace_id / artifact_ref` 的页面、SSE、后端日志、Langfuse、`query_artifact`、`conversation_state` 一致性。
- 如果该路径没有触发 RepairPlan，不要求出现 `repair_plan_ref`，也不能把它解读成字段漂移自动修复成功。
- fixture 或真实触发修复的分支有完整 `repair.*` 生命周期。
- 后端日志有 failure classification、RepairPlan 协议校验和受控 rerun result。
- Langfuse UI 能用同一 `trace_id` 找到 observation。
- `query_artifact` 能用 `artifact_ref` 找到产物。
- fixture 或触发修复的分支中，`conversation_state` 能查到 `repair_plan_ref / checkpoint_ref`。
- fixture 或触发修复的分支中，同一 `task_id / trace_id / artifact_ref / repair_plan_ref` 全链一致。

### 12.2 稳定自动化 fixture

构造一次字段错误或函数 / 方言错误：

- 第一次执行失败。
- RepairPlan 生成。
- Tool 校验通过。
- 自动重跑成功。
- 测试断言 event envelope、Artifact refs、`conversation_state`、`query_artifact`、Langfuse trace index 一致。

## 13. 后续口子

C2：

- `RepairPatch Engine`：实现 `FIELD_NOT_FOUND` / `FIELD_MAPPING_DRIFT` 字段候选、Patch IR、Tool 校验、apply、重新编译和真实漂移验收。
- Artifact 详情面板。
- RepairPlan、trace、attempt history 的开发 / 管理员可视化。
- 低置信修复确认卡的完整交互。
- 更多失败类型修复策略。

C3：

- 独立 BI 工作台。
- AgentScope runner adapter 试运行。
- ReportAgent、PythonAgent、AuditAgent 逐步打开。
- RepairPlan 独立表和审计查询。

## 14. 风险与约束

- RepairPlan 自动修复可能改变业务口径，因此低置信、多候选、多 action 必须确认。
- 所有自动修复必须保留 trace、attempt 和 blocked reason，避免不可解释重跑。
- C1 不能为了提高成功率绕过 QueryGraph compiler、方言适配或权限边界。
- C1 不能用 fixture 成功替代真实问题成功。
- C1 不能用 template 路径真实成功替代 C2 字段漂移自动修复验收。
- Langfuse observation 是 C1 硬验收项，不是可选项。
