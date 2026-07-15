# 测试报告历史说明

本目录保留阶段测试报告。报告用于说明当时提交、分支或功能点的验证结果，不表示当前主链仍保持同样入口和 runtime 边界。

阅读规则：

- 报告中的 `/api/chat/stream`、AgentScope mirror、legacy adapter、Langfuse 或 provider-neutral observability 描述，按报告时间理解。
- 当前回归验证应以 `POST /api/agent-team/tasks/stream`、AgentScope Agent Team 的 Leader / BI Worker 边界、Artifact refs、SSE 事件、数据库状态和后端日志为主。
- 不修改旧报告结论；如果当前架构下重新验证，新增报告并写明当前入口。
