# Claude Code 使用说明

通用规则以 `AGENTS.md` 为准。Claude Code 进入本项目时只需要：

1. 读取 `AGENTS.md`。
2. 按需读取 `docs/上下文入口.md`。
3. 代码探索优先使用 `.codegraph/`。

禁止默认全文读取：

- `.codex/项目记忆.md`
- `docs/superpowers/` 下的长计划和规格文档
- 大型源码文件或大型测试文件

需要历史信息时，用关键词检索：

```bash
rg -n "关键词|文件名" .codex/项目记忆.md
```

完成任务后仍需按 `AGENTS.md` 追加 `.codex/项目记忆.md`。
