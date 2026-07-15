# Superpowers 历史计划说明

本目录保留阶段实施计划和设计规格，主要用于追溯当时任务如何拆分、验证和落地。

这些文档不是当前默认上下文。当前主链已经收口为 AgentScope Agent Team，并以 `POST /api/agent-team/tasks/stream` 作为统一任务入口。

阅读规则：

- `plans/` 和 `specs/` 中的 `/api/chat/stream`、`/chat/stream`、`ask_bi`、`AgentScopeShellAdapter`、Langfuse 和五件套验收描述，保留为历史事实。
- 继续对应任务时可以参考实现拆分，但必须先按当前架构重新校准入口、Agent 边界、SQL control plane 和用户可见输出。
- 不要把历史计划中的“第一阶段”或“下一步”直接复制为当前计划。
