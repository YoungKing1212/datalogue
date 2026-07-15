# B-first / C-ready 决策历史说明

本目录保留 B-first / C-ready 阶段的决策沉淀。它解释了旧阶段为什么采用 `BIWorkbenchTool`、`ask_bi`、`AgentScopeShellAdapter`、Chat 承载和分层验收。

这些决策已被当前 AgentScope Agent Team 主链取代：外部请求通过 `/api/agent-team/tasks/stream` 进入 `AgentTeamTaskRuntime`，再由 `AgentScopeServiceTaskRunner` 调用 AgentScope Service，由 Leader Agent 与 BI Worker 协作执行。

阅读规则：

- `decisions/` 下文档保留历史决策，不代表当前仍采用旧 adapter 或 `ask_bi` 作为新主链入口。
- 如果历史决策与当前架构冲突，以 `docs/上下文入口.md`、`docs/architecture/系统架构.md`、`docs/architecture/执行链路.md` 和 `docs/README.md` 为准。
- 后续若需要重启某条历史路线，必须新建当前决策记录，而不是直接复用旧结论。
