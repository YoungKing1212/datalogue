# 数语（Datalogue）项目文档

> 版本：v2026.07 | 维护人：杨凯

## 📋 文档索引

### 入口与当前上下文
- [Onboarding 快速指南](Onboarding快速指南.md) — 新开发者 15 分钟上手：环境搭建、架构速览、开发规范、任务速查
- [AI Agent 上下文入口](上下文入口.md) — 当前主链、常用命令、文档导航和上下文边界
- [目录治理与模块边界](architecture/目录治理与模块边界.md) — 后端、前端、文档、运行产物的渐进迁移边界

### 架构设计
- [系统架构](architecture/系统架构.md) — 整体架构、分层、组件
- [执行链路](architecture/执行链路.md) — Agent Team 端到端执行流程
- [Leader 统一收口与 ECharts 可视化](architecture/Leader统一收口与ECharts可视化设计.md) — 取消强制 Report Worker、结构化回答收口与受限图表协议
- [登录认证设计](architecture/登录认证设计方案.md) — JWT、Refresh Token、路由守卫和用户归属设计
- [数据模型](architecture/数据模型.md) — 核心数据库模型
- [AgentScope 集成](architecture/AgentScope集成.md) — AgentScope Service 子应用挂载
- [OpenViking Service 交接记忆](architecture/OpenViking-Service交接记忆.md) — 面向 OpenViking Service 的当前项目记忆、接入边界和验证入口

### API 参考
- [API 概览](api/API概览.md) — 所有 API 端点一览

### 运维与验证
- [Docker 部署指南](../datalogue-api/docs/docker-deployment.md) — 根 Compose、一次性迁移、Nginx 单入口与 Phoenix 独立部署
- [Phoenix 开发观测部署与验收](operations/Phoenix开发观测部署与验收.md) — OTEL Trace 后台部署、权限和验收清单
- [运行时健康检查](operations/运行时健康检查.md) — AgentScope、Redis、Credential、Leader、Session stream、BI Tool、Artifact API、Frontend version 检查清单

### 计划与研究
- [计划目录](plans/README.md) — 当前路线图、专项实施方案和待办入口
- [研究目录](research/README.md) — 竞品、框架和提示词研究材料；研究结论不直接等同于当前架构

### 资产与交付物
- [E2E 截图资产清单](assets/screenshots/e2e/README.md) — 需要长期保留的真实页面和端到端验证截图
- `assets/screenshots/user-manual/` — 用户手册截图资产
- `assets/diagrams/` — 当前文档引用的架构图和链路图
- `deliverables/` — 对外交付文档
- `test-reports/` — 历史测试报告和验收记录

### 历史归档
> `archive/` 是只读历史归档区，不作为 Codex / Claude 的常规上下文入口；只有追溯旧 LangGraph、Langfuse 下线或历史交付背景时才按需读取。

- `archive/old-architecture/` — 旧版 LangGraph 架构材料
- `archive/2026-07-01-langfuse-removal/` — Langfuse 下线相关历史材料
- `archive/2026-07-03-legacy-assets/` — 原顶层 `assets/` 中的旧截图、原型和设计源文件
- `archive/2026-07-03-legacy-design-plans/` — 早期设计开发方案和 Word 版本
- `archive/2026-07-13-roadmap-drafts/` — 已被后续版本替代的下半年计划草稿
- `archive/2026-06-legacy-docx/` — 早期 docx 交付源文件
