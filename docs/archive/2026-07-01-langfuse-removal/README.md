# 2026-07-01 Langfuse 下线归档

本目录保存 Langfuse 技术栈移除前的历史设计文档，仅用于追溯旧方案和历史决策。

当前运行时口径：

- Langfuse SDK、部署服务、Prompt Manager 远端同步、Trace 深链和 `/api/observability/*` 已下线。
- `DatalogueTracer` 仅保留 no-op 兼容壳，不再分配外部 `trace_id`、写远端 observation 或生成跳转链接。
- 新任务路由不要把本目录文档当作现行实现依据；需要确认当前状态时优先查看 `docs/上下文入口.md` 和 `.codex/project-memory.md` 中 2026-07-01 的移除记录。

归档文件：

- `Langfuse可观测能力需求设计文档.md`
- `Langfuse可观测能力开发文档.md`
- `Langfuse可观测能力需求与开发文档.docx`
- `langfuse-metadata-schema.md`
