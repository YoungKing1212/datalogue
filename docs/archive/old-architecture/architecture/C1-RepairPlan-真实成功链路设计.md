# C1 RepairPlan 真实成功链路设计

本文档是 C1 的架构沉淀版。执行规格以 `docs/superpowers/specs/2026-06-28-c1-repair-plan-real-acceptance-design.md` 为准。

## 定位

C1 的目标是补齐 B-first C-ready 阶段留下的真实链路缺口：让真实问题 `查询杨凯 2024 年工作日志` 在现有 Chat Shell 中通过现有可信 template 路径成功查出业务结果，并完成页面、SSE / event envelope、后端日志、Langfuse observation、`query_artifact` 和 `conversation_state` 的五件套一致性验收。

本文继续使用“真实成功链路”表述时，只表示 C1 协议链路、事件、Artifact refs、受控 retry / fixture 和现有真实业务 template 路径已完成验收；它不表示字段漂移已经具备自动修复闭环。

C1 不是完整 C 产品形态，不启动独立 BI 工作台，不接管 AgentScope runtime，不打开 ReportAgent / PythonAgent / AuditAgent。

## 核心设计

C1 引入 `RepairPlan v1`，用于承接 SQL 执行失败后的修复意图、失败分类、事件和引用协议。LLM 只提出修复意图，C1 负责协议校验、脱敏摘要、`repair.*` event、Artifact refs、retry checkpoint、受控重试上限和自动化 fixture 验证。

C1 不实现真实字段级 patch / apply / recompile 引擎。`FIELD_NOT_FOUND`、`FIELD_MAPPING_DRIFT` 这类字段漂移自动修复的 `RepairPatch Engine` 归 C2 交付。

RepairPlan 不是可执行 SQL。普通用户也不会看到字段、表、schema、SQL 或 raw result。

## 失败分层

所有 SQL 执行失败都会进入 repair evaluation，但按三层处理。C1 只保证分类、事件、引用和受控重试策略可验证；真实字段漂移的自动 patch 不在 C1 范围内。

- 可进入受控修复协议并按策略重跑：字段不存在、表不存在、函数 / 方言不兼容、类型转换错误。C1 对字段 / 表类问题只做分类、阻断或 fixture 级验证；真实字段映射修复归 C2。
- 只诊断不重跑：权限不足、数据源不可达、超时、结果过大。
- fail closed：疑似越权、raw SQL 注入、跨数据集访问、schema 泄露风险。

重跑次数按失败类型动态控制，字段 / 表错误最多 1 次，函数 / 方言错误最多 2 次，类型错误最多 1 次。权限、连接、超时、安全风险不自动重跑。

## 用户确认

高置信单点修复可自动重跑。低置信、多候选、多 action、涉及口径变化或新增表时，返回修复确认卡。

确认卡采用双层展示：

- 普通用户只看到业务级解释。
- C1 不做开发 / 管理员详情 UI；failure class、RepairPlan 内部校验结果和后续 C2 RepairPatch 详情只允许进入 Langfuse observation、后端日志和 trace-only metadata。

用户确认时只提交 `repair_plan_ref / checkpoint_ref / selected_action`，不提交字段、schema、SQL。

## 事件与 AgentScope 口子

C1 复用 `DatalogueEventEnvelope`，新增 `repair.*` event type：

- `repair.evaluated`
- `repair.plan_created`
- `repair.confirmation_required`
- `repair.rerun_started`
- `repair.rerun_completed`
- `repair.failed`
- `repair.blocked`

AgentScope 在 C1 只补 event adapter 映射，不启动 runner，不替换 `/chat/stream`。`AgentScopeShellAdapter` 仍只允许 `ask_bi`。

## 持久化

C1 不新增 repair_plan 表，先复用现有状态和引用体系：

- `conversation_state.facts` 写入 `kind=repair_plan`、`repair_plan_ref`、`failure_class`、`repair_status`、`attempts`、`requires_user_confirmation`、`checkpoint_ref`。
- ArtifactCard `related_refs` 增加 `repair_plan_ref`、`retry_checkpoint_ref`、`trace_ref`。
- 历史回放只展示业务级 repair summary。
- `repair_plan_ref` 使用现有 `artifact:<uuid>` 句柄，`ArtifactRef.ref_type="repair_plan"`，不引入 `repair_plan:<uuid>` 新前缀。
- Artifact API 对 `kind="repair_plan"` 只返回脱敏 RepairPlan 摘要，不能返回 raw SQL、raw result、完整 schema 或 RepairPatch / 字段映射主体。

## Langfuse 验收

C1 必须修复本地后端 `langfuse` SDK / observation，并区分自动化和真实验收：

- 自动化测试覆盖 SDK 初始化或 mocked / no-op observation 写入路径。
- 真实请求能写入 Langfuse trace / observation。
- Langfuse UI 能用同一 `trace_id` 找到 RepairPlan 相关链路。
- 真实验收必须手工或 Playwright 辅助核对 Langfuse UI，并写入验收记录。

如果 Langfuse observation 不通，C1 不能标为完成。

## 验收

C1 必须通过两个问题：

- 真实业务问题：`查询杨凯 2024 年工作日志`，通过现有可信 template 路径成功查出业务结果。
- 自动化 fixture：构造可控字段错误或函数 / 方言错误，首次失败后生成 RepairPlan，完成协议校验、事件、Artifact refs、checkpoint 和受控重跑成功断言。

真实业务验收必须核对同一个 `task_id / trace_id / artifact_ref` 在页面、SSE / event envelope、后端日志、Langfuse、`query_artifact / conversation_state` 中一致；只有实际触发 RepairPlan 的 fixture 或失败分支才要求核对 `repair_plan_ref`。

## 后续阶段

C2 进入 `RepairPatch Engine`：实现 `FIELD_NOT_FOUND` / `FIELD_MAPPING_DRIFT` 的字段候选、Patch IR、Tool 校验、apply、重新编译、方言适配和真实漂移验收，并可继续推进 Artifact 详情面板、低置信修复确认卡完整交互和更多失败类型修复策略。

C3 可以进入独立 BI 工作台、AgentScope runner adapter、ReportAgent / PythonAgent / AuditAgent，以及 RepairPlan 独立表和审计查询。
