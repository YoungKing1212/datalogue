# Datalogue 文档总览

本文档用于人工阅读和维护 `docs/` 目录。Agent 任务路由仍优先读取 `docs/上下文入口.md`。

## 目录结构

| 目录 | 用途 | 维护建议 |
| --- | --- | --- |
| `product/` | 项目介绍、阶段总结、面向业务和管理视角的说明材料 | 内容要能脱离代码背景阅读，截图或结论变化时同步更新 |
| `architecture/` | 系统设计、执行链路、核心模块职责和架构边界 | 架构改动、Agent/QueryGraph/Manifest 边界变化时更新 |
| `observability/` | Langfuse、Trace、本地观测、generation metadata 等可观测材料 | 观测字段、Trace 结构、Langfuse Prompt/metadata 变化时更新 |
| `agent-planning/` | LeadAgent、SubAgent、语义资产注入、评估基线和测试计划 | 方案落地后保留设计依据，过时草案移动到 `archive/` |
| `superpowers/` | 历史实施计划和设计规格 | 只在继续对应任务时读取，避免默认塞入上下文 |
| `deliverables/` | 可直接交付或阅读的 DOCX 成品 | 新版本文档放这里，旧版本移动到 `archive/` |
| `assets/` | 文档图片、链路图、产品截图 | 图片文件按 `diagrams/`、`screenshots/` 分类 |
| `archive/` | 已被拆分、重复、旧版或仅供追溯的材料 | 默认不删除，避免丢失历史依据 |

## 当前入口

- Agent 上下文入口：`docs/上下文入口.md`
- 项目阶段总结：`docs/product/当前项目工作总结与下步计划.md`
- 项目介绍手册：`docs/product/数语项目介绍手册.md`
- 系统设计方案：`docs/architecture/数语系统设计方案.md`
- Langfuse 需求与开发：`docs/observability/Langfuse可观测能力需求设计文档.md`、`docs/observability/Langfuse可观测能力开发文档.md`

## 已归档内容

- `docs/archive/2026-06-legacy-docx/Langfuse可观测能力需求与开发文档.docx`：旧版合并 DOCX，内容已由 `observability/` 下的 Markdown 源文档承接，保留用于追溯。

## 整理规则

- 根目录只保留总览和 Agent 固定入口，业务文档不要继续堆在 `docs/` 根目录。
- 新增文档先判断读者和用途，再放入对应目录；不确定时优先补到 `docs/README.md` 的目录说明。
- 过期文档优先移动到 `archive/`，不要直接删除。
- 移动 Markdown 或图片后，必须同步更新引用路径，并用链接检查确认没有断链。
