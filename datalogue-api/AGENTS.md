# AGENTS.md

## 项目身份

- 当前项目：Datalogue / 数语后端 API
- 工作目录：`/Users/yangkai/code_place/study/python/Datalogue/datalogue-api`
- 用户：杨凯 / Ken Yang
- 默认回复语言：中文
- 当前交接日期：2026-06-20，时区 Asia/Shanghai
- 本文件继承父级 `/Users/yangkai/code_place/study/python/Datalogue/AGENTS.md` 的项目规范；若本文件有更具体约束，以本文件为准。

## 关键协作约束

- 修改代码前先读相关上下文，优先沿用现有项目结构和风格。
- 仓库如存在 `.codegraph/`，代码探索优先使用 CodeGraph，而不是 `grep` / `find` / 直接读文件。
- 不主动回滚用户或其他工具已有改动；脏工作区只处理当前任务相关文件。
- 新增 Python 文件必须按父级 `AGENTS.md` 的中文文件头模板写职责说明。
- 完成功能后需要更新 `.codex/project-memory.md`，按 `YYYY-MM-DD HH:mm` 记录完成时间、功能、涉及文件、关键改动、验证方式、残留风险。
- 若实现前临时写 `TODO`，完成后必须清理对应 `TODO`。
- Datalogue 任务默认不只给方案，应直接实现、补验证，必要时做真实链路检查。
- 前端改动完成后优先 `npm run lint` 和 `npm run build`；如需页面验收，再启动 dev server。
- Java 任务按需使用 `jdk8` / `jdk17` 切换。

## 当前上下文状态

- 当前没有正在进行的代码改动任务。
- 用户刚要求整理上下文，并希望生成一份用于新 Codex 线程的精简交接摘要。
- 已确认应保留的核心上下文是：项目路径、中文回复、`AGENTS.md` 约束、CodeGraph 优先、Datalogue 验证偏好、不要覆盖用户改动、完成功能要写项目记忆。

## 可丢弃背景

- 飞书、PPT、WPS、Figma、iOS、Stripe、Supabase 等技能清单当前无关。
- WeKnora、Dify、RCenter 等旧项目记忆当前无关。
- 前端视觉设计细则仅在后续涉及 UI 时再启用。
- 已批准命令前缀列表通常只在提权或运行特定命令时再考虑。

## 执行偏好

- 复杂 Datalogue 问题优先真实链路取证：页面/前端回放、trace、后端日志、prompt/token、final payload、历史回放等交叉验证。
- 截图或临时验证产物放 `/private/tmp` 或系统临时目录，不写入仓库。
- 最终回复保持简洁，说明改了什么、验证了什么、还有什么风险。
