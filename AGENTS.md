# AGENTS.md

## 项目沟通

- 用户名：yangkai，英文名：KenYang。
- 默认使用中文回复。
- 当前项目：数语（智能问数）。
- 本机有 JDK 8 和 JDK 17，需要切换 Java 版本时使用 `jdk8` 或 `jdk17`。

## 开发标准

- 新增代码文件时，必须写清楚文件用途或关键职责的注释；注释尽量使用中文。
- 注释应服务于理解业务意图、边界条件和复杂流程，避免机械解释每一行代码。
- 新增或修改关键业务代码时，必须在重要分支、边界条件、方法调用、关键赋值、跨层状态写入/回放、外部副作用、降级/fallback 和异常处理处补充中文关键注释；优先写在对应调用或关键操作同一行的行尾，不要求逐行注释，但要解释“为什么”和业务边界。
- 实现新功能前，先在相关任务记录或实现位置标记 `TODO`，写明待完成事项。
- 功能完成后，必须删除对应的临时 `TODO`，避免把已完成事项长期留在代码或文档中。
- 每完成一个功能，都要写文档记录，记录内容放入当前项目记忆：[.codex/project-memory.md](.codex/project-memory.md)。
- 功能记录文件名尽量使用中文；工具约定文件（例如 `AGENTS.md`）按约定保留英文文件名。
- 功能记录按时间顺序排列，使用 `YYYY-MM-DD HH:mm` 格式；较早记录在前，较晚记录在后。
- 功能记录至少包含：完成时间、功能名称、涉及文件、关键改动、验证方式、残留风险或后续事项。
- [.codex/project-memory.md](.codex/project-memory.md) 的“最新详细记录”超过 10 条时，必须把较早详细记录压缩进“历史压缩记录”；“历史压缩记录”中的压缩条目超过 10 条时，继续做深度压缩，合并为更高层主题摘要。
- 若功能尚未完成，可以在项目记忆中保留 `TODO`；一旦完成，更新为完成记录并删除该 `TODO`。

## Python 文件注释模板

新增 Python 文件时，文件头必须使用以下模板。`${NAME}` 为不含扩展名的文件名，`${USER}` 为作者名，`${DATE}` 为创建日期。

```python
# ============================================================
# File Name   : ${NAME}.py
# Description:
#   TODO: Brief description of this file.
#
# Responsibilities:
#   - TODO: 
#
# Author      : ${USER}
# Created On  : ${DATE}
# ============================================================
```

创建文件时先保留模板中的 `TODO`，完成对应文件职责说明后，应把 `TODO` 替换为实际中文描述。

## 当前协作约定

- 修改代码前先读相关上下文，尽量沿用现有项目结构和样式。
- 保持改动范围聚焦，不主动回滚用户或其他工具已有改动。
- 前端改动完成后优先执行 `npm run lint` 和 `npm run build` 验证；如需要实际页面验收，再启动本地 dev server。

## 上下文预算

- Agent 启动时先读本文件；需要项目任务路由时再读 [docs/上下文入口.md](docs/上下文入口.md)。
- [.codex/project-memory.md](.codex/project-memory.md) 是完成记录，不是启动上下文；只按关键词检索相关段落，禁止默认全文读取。
- `docs/superpowers/` 下的长计划和规格文档只在对应任务继续实施时读取，不作为默认上下文。

## AgentScope 2.0.3 官方文档参考

本项目部分功能基于 AgentScope 框架开发。在新增 Agent/RAG/工具/工作流等能力时，**必须优先查阅官方文档**，确认框架已有原生支持，避免重复造轮子。

📚 文档路径：`~/code_place/study/agentscope-docs/`

| 模块 | 文档文件 |
|------|----------|
| AgentScope 概述 | `pages/index.md` |
| 快速开始 | `pages/quickstart.md` |
| 消息与事件 | `pages/message-and-event.md` |
| 智能体 | `pages/agent.md` |
| 模型配置 | `pages/model.md` |
| 上下文管理 | `pages/context.md` |
| 工具 | `pages/tool.md` |
| 计划模式 | `pages/plan.md` |
| 权限系统 | `pages/permission-system.md` |
| 中间件 | `pages/middleware.md` |
| RAG | `pages/rag.md` |
| 长期记忆 | `pages/long-term-memory.md` |
| 工作区 | `pages/workspace.md` |
| 架构-智能体即服务 | `pages/agent-service.md` |
| 智能体团队 | `pages/agent-team.md` |
| RAG 服务 | `pages/rag-deploy.md` |

**开发原则**：遇到 Agent/RAG/工具/工作流等需求时，优先查阅上述文档对应章节，使用 `agentscope` 框架的原生 API，而非自行实现。
