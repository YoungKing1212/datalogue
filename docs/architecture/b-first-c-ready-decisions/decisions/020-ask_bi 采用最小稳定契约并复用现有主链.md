# 020 · ask_bi 采用最小稳定契约并复用现有主链

## 状态

- 状态：已敲定
- 时间：2026-06-26 12:49
- 触发：用户确认采用方案 2，并要求记录后续改造方案

## 决策

第一阶段定义最小 `ask_bi` / `BIWorkbenchTool` 契约，作为 Agentic Shell、未来 BI 工作台和外部 Agent 调用智能问数能力的稳定外壳；内部暂时复用现有 Chat、LeadAgent、DatasetAgent 和 `/chat/stream` 主链，不第一阶段重写完整 BI 工作台运行时。

## 背景

前面已经确定第一阶段复用现有 Chat 入口，但按未来工作台协议设计任务模型、事件流、产物卡、引用和动作。现在需要把“智能问数主链路”对外收敛成一个稳定能力入口，否则后续 Agentic Shell、独立 BI 工作台、外部 Agent 或 AgentScope adapter 都会继续直接依赖 Chat 形态。

如果直接复用现有 Chat 请求结构，第一阶段改动最小，但调用边界会继续模糊；如果直接定义完整 BI 工作台契约，又会提前引入任务编排、多产物状态、详情面板和权限视图复杂度。

## 选择理由

- 最小 `ask_bi` 契约能把智能问数主链路变成稳定工具能力，符合 Hermes-style “最小能力暴露”的方向。
- 内部复用现有主链，可以优先验证核心链路，不被完整工作台重构拖慢。
- 入参和出参先控制在业务级、引用级和事件级，不暴露 schema、字段、SQL、blueprint 主体和完整语义资产详情。
- 后续完整 BI 工作台可以在同一契约上扩展任务编排、详情面板、多产物状态和权限视图，不需要推翻第一阶段入口。

## 被排除方案

- 直接复用现有 Chat 请求结构：短期最省事，但不利于后续 Agentic Shell、独立 BI 工作台和外部 Agent 复用。
- 一次性定义完整 BI 工作台契约：最 C-ready，但第一阶段会引入过多工作台复杂度，偏离先跑通智能问数主链路的目标。

## 对架构的影响

第一阶段 `ask_bi` 最小入参只包含：

```text
question
conversation_id
caller
confirmed_dataset_id
context_refs
request_options
```

第一阶段 `ask_bi` 最小出参只包含：

```text
task_id
event_envelope
candidate_datasets
answer
artifact_card
primary_ref
related_refs
status
error
```

边界约束：

- `question` 是用户原始问题。
- `conversation_id` 用于复用现有多轮状态。
- `caller` 表示调用来源，例如 `chat`、`agentic_shell`、`workbench_preview`。
- `confirmed_dataset_id` 仅在用户已确认候选数据集后传入。
- `context_refs` 只传引用句柄，不传 raw result、schema、SQL 或 `control_plane` 主体。
- `event_envelope` 对齐已确定的统一 SSE envelope。
- `artifact_card` 对齐 `ArtifactCard`、`preview_payload`、`primary_ref`、`related_refs` 和受控 `actions`。

## 对开发计划的影响

- P0/P1 需要固化 `ask_bi` 最小契约文档和类型定义。
- P3 需要实现 `BIWorkbenchTool` 外部入口，但内部先转接现有 Chat / LeadAgent / DatasetAgent 主链。
- P3 需要把现有 SSE 输出映射成 `event_envelope`，并把最终 answer、候选数据集、产物卡和引用句柄整理成 `ask_bi` 出参。
- 第一阶段不实现完整工作台任务编排、多产物编辑状态、完整详情面板状态机和跨 Agent 协作 runtime。
- 后续 C-ready 改造需要把 `ask_bi` 从“Chat 主链适配壳”升级为“BI 工作台原生能力入口”，补齐任务生命周期、权限视图、详情面板恢复、多产物状态和 AgentScope adapter。

## 后续问题

- `retry` 是重试整个任务，还是重试最近失败的子任务。
- 主链路验收时是否要求真实页面、SSE event、后端日志、Langfuse trace 和 query_artifact 全部一致。
