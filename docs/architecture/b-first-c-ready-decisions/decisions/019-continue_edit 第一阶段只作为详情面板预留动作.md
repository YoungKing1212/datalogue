# 019 · continue_edit 第一阶段只作为详情面板预留动作

## 状态

- 状态：已敲定
- 时间：2026-06-26 12:45
- 触发：用户确认采用方案 2，并明确现阶段所有 ReportAgent 相关链路都先不实现

## 决策

`continue_edit` 第一阶段进入固定 Action Registry，但只作为详情面板或未来工作台的预留动作。它可以禁用，也可以只打开 `detail_view_ref` / `artifact_panel_ref` 指向的详情面板；第一阶段不直接启动 ReportAgent，不实现报告继续编辑、版本管理、保存、回滚或编辑审计链路。

## 背景

前面已经确定产物详情采用 Chat 轻量卡并预留详情面板，`actions` 使用固定注册表，`export` 第一阶段也只作为禁用态保留。接下来需要决定报告草稿或分析产物上的 `continue_edit` 是否要进入第一阶段。

当前阶段的核心目标不是完整 Agentic Shell，而是先把智能问数主链路跑通：用户提问、能力路由、候选数据集确认、受控查询执行、结果产物、轻量卡展示、引用和事件协议。ReportAgent 属于增强能力，过早接入会把编辑状态、产物版本、保存和审计复杂度带入第一阶段。

## 选择理由

- 符合“先实现智能问数核心链路”的阶段目标，避免 ReportAgent 抢占主链路建设。
- `continue_edit` 保留在 Action Registry，可以提前固定产品入口和协议位置。
- 禁用或只打开详情面板，能让用户理解该产物未来可继续加工，但不会承诺当前已具备 ReportAgent 编辑能力。
- 后续接入 ReportAgent 时，可以复用同一 action 类型和详情面板入口，逐步扩展为真实编辑链路。

## 被排除方案

- 第一阶段完全不出现 `continue_edit`：实现最简单，但产物卡缺少后续加工入口，C 产品形态表达偏弱。
- 第一阶段直接由 ReportAgent 承接：产品体验最完整，但会提前引入报告编辑状态、版本管理、产物保存、回滚和审计链路，明显拖慢核心问数主链路。

## 对架构的影响

- Action Registry 第一阶段保留 `continue_edit`。
- `continue_edit` action 实例默认结构为：

```text
action_type: continue_edit
enabled: false
disabled_reason: 编辑能力将在后续版本开放
payload:
  primary_ref
  detail_view_ref
  artifact_panel_ref
```

- 如果第一阶段需要给用户查看详情，可以将动作语义降级为打开详情面板，而不是启动 ReportAgent。
- 后端不得在第一阶段返回启动 ReportAgent 所需的执行 payload。
- 前端不得因为看到 `continue_edit` 就自行创建 ReportAgent 任务、编辑会话或产物版本。

## 对开发计划的影响

- P5 需要在 `ArtifactCard` 动作区支持 `continue_edit` 禁用态或详情面板跳转。
- P5 不实现 ReportAgent 调用、报告编辑状态、版本保存、回滚和编辑审计。
- P5 的验收口径聚焦智能问数主链路：路由、确认、执行、结果、产物卡、引用、动作禁用态和事件 envelope。
- P6 或后续 C-ready 阶段再补 ReportAgent 的真实编辑链路和产物生命周期。

## 后续问题

- `retry` 是重试整个任务，还是重试最近失败的子任务。
- 主链路最小闭环是否还需要单独定义 `ask_bi` 入参/出参契约。
- 主链路验收时是否要求真实页面、SSE event、后端日志、Langfuse trace 和 query_artifact 全部一致。
