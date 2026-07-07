# 017 · refs 拆分为 primary_ref 与 related_refs 并预留 role

## 状态

- 状态：已敲定
- 时间：2026-06-26 12:33
- 触发：用户确认采用 `primary_ref + related_refs`，并预留 `role` 字段

## 决策

`ArtifactCard` 引用拆分为 `primary_ref` 与 `related_refs`。`primary_ref` 表示当前卡片的主产物，`actions` 默认绑定 `primary_ref`；`related_refs` 表示来源结果、审计证据、图表依赖、分析依赖等辅助引用。引用结构预留 `role` 字段，但第一阶段不强依赖完整 `ref_roles` 体系。

## 背景

前面已经确定 `ArtifactCard` 使用统一壳、半强 `preview_payload` 和受控 `actions`。接下来需要决定引用字段是继续用单一 `refs` 数组，还是拆分主引用与相关引用。

如果只有 `refs` 数组，前端和 Agent 很难判断打开详情、继续分析、导出等动作应该绑定哪个引用；如果一开始设计完整 `ref_roles` 体系，又会增加第一阶段复杂度。

## 选择理由

- `primary_ref` 能明确当前卡片的主产物，方便动作默认绑定，减少前端猜测。
- `related_refs` 能保留来源结果、审计证据、图表依赖等辅助上下文，支撑后续详情面板、审计解释和工作台联动。
- 预留 `role` 字段能为未来工作台和多产物编排留口子，但第一阶段不强依赖，避免过早设计完整角色体系。
- 该策略能让 `actions`、详情面板、导出、继续编辑、继续分析等能力都有清晰引用边界。

## 被排除方案

- 只保留 `refs` 数组：实现简单，但主引用不明确，后续动作绑定和详情跳转容易歧义。
- 第一阶段直接采用完整 `ref_roles` 体系：表达力最强，但角色枚举、兼容策略和前端渲染成本偏高。

## 对架构的影响

- `ArtifactCard` 外层引用字段从通用 `refs` 调整为：
  - `primary_ref`
  - `related_refs`
- `primary_ref` 至少包含：`ref_type`、`ref_id`、`label`。
- `related_refs` 每项至少包含：`ref_type`、`ref_id`、`label`。
- `role` 字段作为预留字段，可用于表达 `main_artifact`、`source_result`、`audit_evidence`、`chart_dependency`、`analysis_dependency` 等语义，但第一阶段不要求完整枚举闭环。
- `actions` 默认绑定 `primary_ref`；如果动作需要使用 `related_refs`，必须在白名单 payload 中显式声明引用用途。

## 对开发计划的影响

- P5 需要更新 `ArtifactCard` schema，将 `refs` 拆为 `primary_ref` 与 `related_refs`。
- 轻量产物卡、详情面板、动作 payload、事件 payload 都需要明确主引用和辅助引用。
- 后续独立 BI 工作台可以基于 `primary_ref` 打开主产物，并基于 `related_refs` 展示来源、证据和依赖。
- 后续如果需要完整 `ref_roles`，可以在现有 `role` 预留字段上收紧枚举和校验。

## 后续问题

- `export` 第一阶段是否进入可用动作，还是只做预留禁用态。
- `continue_edit` 第一阶段由 ReportAgent 承接，还是先作为详情面板动作预留。
- `retry` 是重试整个任务，还是重试最近失败的子任务。
- `role` 何时从预留字段升级为强枚举。
