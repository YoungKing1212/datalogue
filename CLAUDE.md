# Claude Code 使用说明

通用规则以 `AGENTS.md` 为准。Claude Code 进入本项目时只需要：

1. 读取 `AGENTS.md`。
2. 按需读取 `docs/上下文入口.md`。
3. 代码探索优先使用 `.codegraph/`。

禁止默认全文读取：

- `.codex/project-memory.md`
- `docs/superpowers/` 下的长计划和规格文档
- 大型源码文件或大型测试文件

需要历史信息时，用关键词检索：

```bash
rg -n "关键词|文件名" .codex/project-memory.md
```

完成任务后仍需按 `AGENTS.md` 追加 `.codex/project-memory.md`。

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
