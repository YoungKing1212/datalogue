# 014 · 轻量产物卡采用统一壳加类型化 preview_payload

## 状态

- 状态：已敲定
- 时间：2026-06-26 12:16
- 触发：用户确认建议采用方案 3

## 决策

第一阶段轻量产物卡采用“统一 `ArtifactCard` 壳 + 类型化 `preview_payload`”模式。所有产物共享 `artifact_type`、`title`、`status`、`summary_for_chat`、`refs`、`actions` 等通用字段；报告、图表、审计解释、分析结果等差异化轻量预览放入 `preview_payload`，由 `artifact_type` 决定解释方式。

## 背景

前面已经确认产物详情第一阶段采用 Chat 轻量产物卡，并预留详情面板或独立 BI 工作台承载完整产物。接下来需要决定轻量产物卡本身是完全统一组件、完全分类型组件，还是统一壳加类型化内容区。

完全统一组件协议简单但产品表达过平；完全分类型组件体验更好但第一阶段成本偏高。因此采用折中模式。

## 选择理由

- 统一 `ArtifactCard` 壳可以保持前端组件和后端协议稳定，避免第一阶段为 report/chart/audit/analysis 各做一套独立卡片协议。
- 类型化 `preview_payload` 能保留产物差异，让报告有章节感、图表有指标维度感、审计解释有证据摘要感。
- 后续右侧详情面板或独立 BI 工作台可以复用 `artifact_type + preview_payload + refs`，不用重建产物索引协议。
- 该方案符合第一阶段目标：快速打通 Chat 内产物引用和动作链路，同时为 C 形态体验留足演进空间。

## 被排除方案

- 完全统一组件：实现最快，但 report/chart/audit/analysis 的体验差异过弱，不利于用户理解产物类型。
- 完全分类型组件：产品表达最强，但会增加第一阶段字段设计、前端组件、测试和维护成本。

## 对架构的影响

- `ArtifactCard` 成为 Chat 内轻量产物卡的统一外壳。
- 通用字段包括：`artifact_type`、`title`、`status`、`summary_for_chat`、`refs`、`actions`、`detail_view_ref`、`artifact_panel_ref`。
- `preview_payload` 按 `artifact_type` 类型解释：
  - `report`：`outline`、`key_points`、`source_refs`。
  - `chart`：`chart_type`、`metrics`、`dimensions`、`preview_spec_ref`。
  - `audit`：`explanation_level`、`policy_summary`、`evidence_refs`。
  - `analysis`：`method_summary`、`key_findings`、`analysis_ref`。
- `preview_payload` 只能承载轻量、脱敏、用户可见摘要，不承载完整报告正文、完整图表数据、raw result、raw SQL、schema、capsule 或 `control_plane` 主体。

## 对开发计划的影响

- P5 需要补充 `ArtifactCard` 协议和 `preview_payload` 类型分支。
- ReportAgent、PythonAgent、AuditAgent 的输出需要同时产出通用 `ArtifactCard` 字段和各自 `preview_payload`。
- 前端第一阶段可以实现一个 `ArtifactCard` 组件，再按 `artifact_type` 渲染轻量内容区。
- 后续详情面板可以直接根据 `refs` 和 `artifact_type` 加载完整产物，不依赖 Chat message body。

## 后续问题

- 第一阶段 `preview_payload` 每类字段是否需要强 schema，还是先采用宽松 JSON。
- `actions` 是否统一为固定枚举，例如 `open_detail`、`continue_edit`、`analyze_more`、`export`。
- 图表第一阶段是否需要 `preview_spec_ref`，还是只展示图表建议和指标维度。
- `ArtifactCard` 的错误态、阻断态、生成中状态是否与普通任务卡共用状态模型。
