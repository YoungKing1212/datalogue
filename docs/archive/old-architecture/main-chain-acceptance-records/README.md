# 主链验收记录历史说明

本目录保留历史主链验收记录。记录中的入口、trace、artifact、conversation_state 和页面证据均按当时系统状态书写，不随当前架构规划改写。

当前验收口径已经调整为：

- 主入口：`POST /api/agent-team/tasks/stream`。
- 主链边界：`AgentTeamTaskRuntime -> AgentScopeServiceTaskRunner -> AgentScope Service -> Agent Team (Leader + BI Worker)`。
- 可观测：优先核对 SSE 事件、AgentScope Session、消息 metadata、Artifact refs、Workbench refs、数据库状态和后端日志。

阅读规则：

- 历史记录中的 `/api/chat/stream`、`/chat/stream`、Langfuse、旧 Workbench mirror 和五件套表述，只代表当时验收事实。
- 新增验收记录必须使用当前入口和当前 Agent 边界。
- 不为了迎合新规划改写旧验收结论；需要复验时新建记录。
