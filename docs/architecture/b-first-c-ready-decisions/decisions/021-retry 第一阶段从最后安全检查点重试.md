# 021 · retry 第一阶段从最后安全检查点重试

## 状态

- 状态：已敲定
- 时间：2026-06-26 12:52
- 触发：用户确认采用方案 3

## 决策

`retry` 第一阶段进入固定 Action Registry，但默认只支持从最后安全检查点重试。后端通过 `checkpoint_ref` 决定恢复点；如果没有可用安全检查点，降级为整任务重试。第一阶段不实现完整任务 DAG、任意子任务重试或不受控内部状态重放。

## 背景

前面已经确定第一阶段聚焦智能问数核心链路，并把 `export`、`continue_edit`、ReportAgent 等增强能力降级为禁用态或详情入口。`retry` 不同于增强能力，它直接影响主链路失败后的用户体验，因此需要在第一阶段保留，但必须控制实现复杂度。

如果每次都重试整个任务，状态边界最简单，但用户已确认数据集或已完成路由时会重复走很多步骤；如果只重试最近失败子任务，又需要完整 DAG、子任务输入快照和幂等控制，第一阶段成本偏高。

## 选择理由

- 从最后安全检查点重试能减少重复步骤，同时不要求第一阶段建设完整任务 DAG。
- `checkpoint_ref` 让后端掌握恢复点，前端不需要理解内部任务结构。
- 安全检查点只保存可重放的业务级状态，例如已确认数据集、受控 query context、当前问题和必要引用，不保存 raw SQL、schema 主体、`control_plane` 主体或不可审计内部状态。
- 如果检查点不可用或过期，降级整任务重试，保证行为可解释。

## 被排除方案

- 始终重试整个任务：实现简单，但会重复已完成的数据集确认、路由和上下文准备，体验偏重。
- 只重试最近失败子任务：体验更细，但需要完整任务 DAG、子任务状态、输入快照、幂等和部分回放策略，不适合第一阶段。

## 对架构的影响

- Action Registry 第一阶段保留 `retry`。
- `retry` action 实例默认结构为：

```text
action_type: retry
enabled: true
disabled_reason: null
payload:
  primary_ref
  checkpoint_ref
  retry_scope: last_safe_checkpoint
  fallback_scope: whole_task
```

- 第一阶段允许的安全检查点包括：
  - `dataset_confirmed`：用户已确认候选数据集后。
  - `query_context_ready`：受控查询上下文已准备完成后。
  - `artifact_generation_failed`：结果已存在但轻量产物卡生成失败后。
- 后端必须验证 `checkpoint_ref` 是否属于当前会话、当前用户、当前任务和当前权限范围。
- 检查点过期、缺失或校验失败时，`retry` 降级为整任务重试，并通过 event envelope 告知恢复策略。
- 第一阶段不得通过 `retry` 重放 raw SQL、raw result、schema 主体、capsule 主体、trace 主体或 `control_plane` 主体。

## 对开发计划的影响

- P3 需要在 `ArtifactCard` 动作区支持 `retry`，并携带受控 `checkpoint_ref`。
- P3 需要在 event envelope 中增加 `retry.started`、`retry.checkpoint_restored`、`retry.fallback_to_whole_task`、`retry.completed`、`retry.failed` 等业务级事件。
- P3 需要定义最小安全检查点结构，并接入现有 conversation_state / query_artifact / artifact ref。
- 第一阶段不实现完整 DAG 级子任务重试；后续 C-ready 阶段再评估细粒度子任务 retry、幂等执行和可视化任务恢复。

## 后续问题

- 主链路验收时是否要求真实页面、SSE event、后端日志、Langfuse trace 和 query_artifact 全部一致。
