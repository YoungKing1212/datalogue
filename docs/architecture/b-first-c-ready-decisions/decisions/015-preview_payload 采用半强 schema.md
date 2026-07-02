# 015 · preview_payload 采用半强 schema

## 状态

- 状态：已敲定
- 时间：2026-06-26 12:24
- 触发：用户确认采用半强 schema 方案

## 决策

`ArtifactCard` 外层采用强 schema；`preview_payload` 采用半强 schema：按 `artifact_type` 定义最小必填字段，同时保留 `optional_details` 扩展位。所有 `preview_payload` 必须携带 `schema_version`，并受 size guard、敏感字段扫描和 `visibility` 约束。

## 背景

前面已经确定轻量产物卡采用统一 `ArtifactCard` 壳和类型化 `preview_payload`。接下来需要决定 `preview_payload` 的约束方式：完全强 schema、宽松 JSON 加版本号，还是半强 schema。

第一阶段 ReportAgent、PythonAgent、AuditAgent 的产物形态仍会继续演进。如果 schema 过早锁死，后续改动成本会偏高；如果完全宽松，又会让前端渲染、测试、审计和泄露扫描失控。

## 选择理由

- 外层 `ArtifactCard` 强 schema 能保证 Chat 内卡片渲染、引用、动作和状态稳定。
- `preview_payload` 半强 schema 能保证每类产物至少有可渲染、可测试的核心字段。
- `optional_details` 允许后续扩展报告章节、图表预览、审计证据、分析方法等轻量信息，不需要频繁改外层协议。
- `schema_version`、size guard、敏感字段扫描和 `visibility` 可以避免半强 schema 退化成任意 JSON 容器。

## 被排除方案

- 完全强 schema：契约最清晰，但第一阶段容易过早绑定 report/chart/audit/analysis 的字段形态。
- 宽松 JSON 加版本号：演进最快，但前端、测试和审计约束弱，长期容易成为新的上下文泄露入口。

## 对架构的影响

- `ArtifactCard` 外层字段必须稳定，包括 `artifact_type`、`schema_version`、`title`、`status`、`summary_for_chat`、`refs`、`actions`、`preview_payload`、`detail_view_ref`、`artifact_panel_ref`。
- `preview_payload.kind` 必须与 `artifact_type` 对齐。
- 每类 `preview_payload` 都必须定义最小必填字段：
  - `report`：`outline`、`key_points`。
  - `chart`：`chart_type`、`metrics`、`dimensions`。
  - `audit`：`explanation_level`、`policy_summary`。
  - `analysis`：`method_summary`、`key_findings`。
- `optional_details` 只能承载轻量、脱敏、用户可见的扩展摘要。
- `preview_payload` 不得承载完整报告正文、完整图表数据、raw SQL、raw result、schema、capsule、trace 主体或 `control_plane` 主体。

## 对开发计划的影响

- P5 需要新增 `ArtifactCard` 外层强 schema 与 `preview_payload` 半强 schema 定义。
- 前端第一阶段可以按最小必填字段稳定渲染，遇到 `optional_details` 时只做受控兜底展示。
- ReportAgent、PythonAgent、AuditAgent 输出轻量卡片时必须满足最小字段和版本约束。
- 后续详情面板可以继续使用 `schema_version` 做兼容和迁移。

## 后续问题

- `actions` 第一阶段是固定枚举，还是允许后端下发受控动作列表。
- `refs` 是否需要拆成 `primary_ref` 与 `related_refs`。
- `optional_details` 是否需要按用户、管理员、开发者分 visibility。
- `schema_version` 的兼容策略是只支持当前版本，还是支持多版本渲染。
