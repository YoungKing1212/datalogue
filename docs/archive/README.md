# 历史归档说明

`docs/archive/` 只保存历史背景和已下线方案，不作为 Codex / Claude 的常规上下文入口。

- 需要追溯旧 LangGraph 架构、Langfuse 下线背景或早期交付物时，才按任务范围读取对应子目录。
- 日常开发、目录治理、AgentScope 主链、API 和前端上下文应优先读取 `docs/上下文入口.md`、`docs/README.md` 和 `docs/architecture/` 下的当前文档。
- 归档子目录默认只读；除非任务明确要求修正归档索引或补充归档说明，不应改写历史正文。
- `old-architecture/assets` 是指向当前 `docs/assets` 的兼容链接，仅用于修复旧归档文档中的历史相对图片引用。
