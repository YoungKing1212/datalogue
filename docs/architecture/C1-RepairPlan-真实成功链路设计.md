# C1 RepairPlan 真实成功链路设计

本文档是 C1 的架构沉淀版。执行规格以 `docs/superpowers/specs/2026-06-28-c1-repair-plan-real-acceptance-design.md` 为准。

## 定位

C1 的目标是补齐 B-first C-ready 阶段留下的真实链路缺口：让真实问题 `查询杨凯 2024 年工作日志` 在现有 Chat Shell 中成功查出业务结果，并完成页面、SSE / event envelope、后端日志、Langfuse observation、`query_artifact` 和 `conversation_state` 的五件套一致性验收。

C1 不是完整 C 产品形态，不启动独立 BI 工作台，不接管 AgentScope runtime，不打开 ReportAgent / PythonAgent / AuditAgent。

## 核心设计

C1 引入 `RepairPlan v1`，用于承接 SQL 执行失败后的受控自动修复。LLM 只提出修复意图，Tool 负责校验、应用到 QueryGraph 或执行策略、重新编译 SQL、走方言适配并执行。

RepairPlan 不是可执行 SQL。普通用户也不会看到字段、表、schema、SQL 或 raw result。

## 失败分层

所有 SQL 执行失败都会进入 repair evaluation，但按三层处理：

- 可自动修复并可重跑：字段不存在、表不存在、函数 / 方言不兼容、类型转换错误。
- 只诊断不重跑：权限不足、数据源不可达、超时、结果过大。
- fail closed：疑似越权、raw SQL 注入、跨数据集访问、schema 泄露风险。

重跑次数按失败类型动态控制，字段 / 表错误最多 1 次，函数 / 方言错误最多 2 次，类型错误最多 1 次。权限、连接、超时、安全风险不自动重跑。

## 用户确认

高置信单点修复可自动重跑。低置信、多候选、多 action、涉及口径变化或新增表时，返回修复确认卡。

确认卡采用双层展示：

- 普通用户只看到业务级解释。
- 开发 / 管理员详情可查看 failure class、RepairPlan、字段级 patch、trace/ref 和 Tool 校验结果。

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
- `repair_plan_ref` 读取必须 fail closed，不能返回 raw SQL、raw result 或完整 schema。

## Langfuse 验收

C1 必须修复本地后端 `langfuse` SDK / observation：

- 后端能导入并初始化 `langfuse` SDK。
- 真实请求能写入 Langfuse trace / observation。
- Langfuse UI 能用同一 `trace_id` 找到 RepairPlan 相关链路。

如果 Langfuse observation 不通，C1 不能标为完成。

## 验收

C1 必须通过两个问题：

- 真实业务问题：`查询杨凯 2024 年工作日志`。
- 自动化 fixture：构造字段错误或函数 / 方言错误，首次失败后生成 RepairPlan，Tool 校验通过，自动重跑成功。

真实业务验收必须核对同一个 `task_id / trace_id / artifact_ref / repair_plan_ref` 在页面、SSE / event envelope、后端日志、Langfuse、`query_artifact / conversation_state` 中一致。

## 后续阶段

C2 可以进入 Artifact 详情面板、低置信修复确认卡完整交互、更多失败类型修复策略。

C3 可以进入独立 BI 工作台、AgentScope runner adapter、ReportAgent / PythonAgent / AuditAgent，以及 RepairPlan 独立表和审计查询。
