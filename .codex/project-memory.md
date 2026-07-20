# 项目记忆

本文件是 Datalogue 项目的压缩版完成记录。文件名使用英文，内容继续使用中文，便于新 Codex 线程检索，同时避免旧版长文件拖慢启动上下文。

## 使用规则

- 本文件只记录实际影响 Datalogue 项目的需求变更、代码/测试/运行配置/项目文档改动、缺陷修复和关键技术决策。
- 普通对话、知识问答、临时分析、状态确认、纯代码阅读/审查及项目无关事项不得写入；未产生实际项目变更时默认不更新本文件。
- 新完成的项目变更按时间顺序追加，时间格式为 `YYYY-MM-DD HH:mm`。
- 每条新增记录至少包含：完成时间、功能名称、涉及文件、关键改动、验证方式、残留风险或后续事项。
- 本文件不是启动上下文；需要历史背景时，按关键词、模块名、文件名或任务名检索。
- 任务路由优先读取 `docs/上下文入口.md`，再按需检索本文件。
- 旧文件 `.codex/项目记忆.md` 已在 2026-06-20 压缩迁移到本文件。
- 新增或修改关键代码时，必须在重要分支、边界条件、方法调用、关键赋值、跨层状态写入/回放、外部副作用、降级/fallback 和异常处理处补充中文关键行级注释；优先写在对应调用或关键操作同一行的行尾，不逐行机械注释。
- "最新详细记录"超过 10 条时，必须把较早详细记录压缩进"历史压缩记录"；"历史压缩记录"中的压缩条目超过 10 条时，继续深度压缩为更高层主题摘要。

## 当前协作默认值

- 默认使用中文协作。
- 当前项目是 Datalogue / 数语，核心方向是 AI 原生智能问数。
- 仓库存在 `.codegraph/` 时，代码探索优先用 CodeGraph。
- 不主动回滚用户或其他工具已有改动；脏工作区只处理当前任务相关文件。
- Datalogue 复杂问题优先做真实链路验证：页面/前端回放、Langfuse trace、后端日志、prompt/token、final payload、历史回放交叉取证。
- Datalogue 架构头脑风暴若存在多个候选方案，先列出各方案的大体概括，再给出 Codex 的建议和理由，最后让用户选择或确认。
- Playwright、浏览器或 E2E 截图放 `/private/tmp` 或系统临时目录，不写入仓库。
- 新增数据库表时，Alembic 迁移必须同步添加中文表注释，并为表内每个字段添加中文字段注释；后续新增字段也必须添加中文字段注释；状态、类型、角色等字典字段要写清 `字典：code=中文含义`。

## 历史压缩记录

### 问数引擎核心链路（2026-06-05 至 2026-07-08）

- **问数基础链路**：建立 NL2DSL/SQL 安全校验、语义资产、术语归一化、数据集上下文、回答解释和低置信确认等问数核心流程；接入 LiteLLM/Langfuse 本地观测与 Trace 深链。
- **SubAgent/多轮/DSL**：建立 SubAgent 查询规划层 v1/v2、Thread Memory、QueryTaskCapsule、多轮槽位承接；打通 SubAgent/DSL 消费链路，建立 ArtifactStore/query_artifacts DB 兜底。
- **BI Worker 渐进式上下文与修复闭环**：实现 BI Worker 渐进式上下文执行、QueryPlan 编译/重试止损、repair 状态机（FIELD_NOT_FOUND 死循环四层修复）、Schema Slice 三段式（tables → describe → preview）；工具统一绕过 AgentScope 权限引擎误拦截。
- **基础体验与治理**：收口新对话草稿、最近对话排序、SubAgent 规则金额聚合 fallback、LLM 原始响应诊断、日志脱敏、关键代码中文注释规范；Manifest 治理与执行前 fail-closed 门禁。

### AgentScope R0 主链迁移与 Workbench 收口（2026-06-28 至 2026-07-09）

- **AgentScope R0 接入**：完成 AS-R0 P0/P1 初始接入、AgentScope Service 主链打通、BI Worker 上下文契约、Leader 控制面工具/Planner 迁移。
- **RepairPlan → RepairPatch 闭环**：C1 RepairPlan 与页面主链收口、C2 RepairPatch 主链收口（bridge status/code + 空结果映射 + join_keys 契约）。
- **Workbench 产品化**：Workbench retry/action/view 状态模型、P0/P1/P2 产品化；去常驻化（Chat retry 承接 + 退役闸门）。
- **BI Worker 工具链完善**：execute_query_plan_bundle 完整链路与工具族文档、L2 Schema Slice 表列表/详情解耦、字段别名与 schema-qualified 引用、raw thinking 流式摘要与 debug 通道。
- **数据源集成**：Doris/Oracle 问数链路基线验证与集成复核。

### 认证安全、系统管理与 UX 升级（2026-07-07 至 2026-07-15）

- **登录认证体系**：PBKDF2-SHA256 后端加解密、传输层 AES-GCM、登录/注册/刷新/退出全流程、首次登录强制改密、默认超级管理员初始化与校准、生产管理员密码同步。
- **用户管理与角色权限**：用户管理列表/新建/编辑页面、角色权限控制、管理员不可调整角色、重置密码规则。
- **前端视觉升级**：石墨天青全局配色方案落地、登录页现代双栏、独立管理页内边距收紧、系统管理子页面配色统一与表格图标操作按钮、登录/网关错误提示可读性、左侧功能栏与导航对齐。
- **LLM 模型控制面**：模型目录、database truth-source 与 AgentScope credential 关联、credential PATCH partial-update、LLM 加密密钥真相源与自动恢复、模型配置页面设计契约与独立页面迁移。
- **Report Worker**：智能报告闭环，BI 查询成功后自动生成报告。

### 目录治理、部署基础与 Phoenix 观测（2026-07-08 至 2026-07-16）

- **Domain 下沉与 Facade 收口**：SQL Guard/方言、查询编译、SQL Preview、ArtifactStore/RepairPlan 从 API 层下沉到 domain 层；AgentScope runtime facade 新目录建立、BI/Agent Team 业务域边界收口、G052-G093 阶段性测试闸门与文档入口治理。
- **前端代码组织**：src/app 应用壳规划、Chat 功能域搬迁、Assistant/assistant-ui 前端边界、Chat 页面与 shared 通用图标迁移、G064-G066 测试稳定化与桌面路由 smoke。
- **Phoenix 部署与观测**：Phoenix 接入业务 PostgreSQL 共享 Schema、宿主机直启 API 上报 Phoenix、OTLP 端口/认证/TLS 修复、Colima 劫持修复、Session 输入输出兼容中间件。
- **Docker 部署**：部署新版 docker-compose 到生产、Docker 部署边界与 Alembic 迁移闸门收口、生产基础设施备份/重建与离线部署验收。
- **LLM 配置页重构与 DS 链路**：LLM 模型配置视觉重构、按设计契约优化、左侧导航对齐工作台设计、数据集 Schema 选择与 Doris 跨库隔离链路。

### 安全、并发、质量债与协议收口（2026-07-17）

- **高危安全修复**：数据源预览注入、SQL Guard 语义绕过（SELECT INTO 拦截）、NL2SQL 值拼接改为 SQLAlchemy 命名参数；生产环境默认密钥拒启、前端传输加密移除、远端登录强制 HTTPS；会话/工作台/反馈/任务入口统一校验属主、删除会话同步清理 AgentScope 主存储、Worker 事件按 leader_session_id 隔离。
- **中危质量修复**：自由文本误脱敏、异步阻塞与资源生命周期、前端错误死链、数据竞态、内部异常泄露、蓝图分析任务持久化、Worker 跨进程进度桥。
- **低危质量债收敛**：聊天双轨实现合并、重复安全工具统一、`datetime.utcnow()` 替换、调试/原型入口净化、会话与消息历史有界分页、Lazy facade 循环依赖解除、`agentscope_runtime` 过渡包删除。
- **协议收口**：Report Worker 从强制执行改为 Leader 统一 `datalogue_finalize_answer` 收口、ECharts 可视化 `visualization_spec` v1 决策、`conf/demo/` 误导性配置目录删除。
- **项目规范**：Codex Stop Hook 从 Kimi 切换为 Claude Code 审查、项目记忆写入边界收紧。

## 最新详细记录

### 2026-07-17 18:45 · Leader 统一回答收口与 ECharts 可视化决策

- 事项：取消 Report Worker 强制必经阶段，BI Worker 只负责受控查询；Leader 通过 `datalogue_finalize_answer` 结构化收口，Runner/Runtime 只认可 `answer_finalized` 凭证。可视化由 Leader 生成受限 `visualization_spec` v1，前端本地 builder 构造 ECharts option。
- 设计文档：`docs/architecture/Leader统一收口与ECharts可视化设计.md`
- 残留风险：实施时需解决持久化 Leader 按名称复用导致的 Prompt 漂移，引入 spec version/prompt hash。

### 2026-07-17 18:20 · 删除 conf/demo 配置目录

- 事项：删除根目录 `conf/demo/`，避免误导配置来源；后端继续从容器环境变量及 `.env` 读取配置。
- 验证：删除依赖 `current.env` 的测试后，Worker 注册测试 `7 passed`。

### 2026-07-17 17:15 · 删除 agentscope_runtime 过渡 facade

- 事项：完成 Phase B Step 4c，5 个调用点改为直连 `app.runtime.engine`，旧目录及 `__pycache__` 完全删除。
- 验证：后端全量 `611 passed`，目录边界测试断言旧包不可导入。

### 2026-07-17 16:45 · Report Worker 强制报告闭环（已废弃，被 Leader 收口替代）

- 状态：**已废弃** — 后续改为 Leader 统一收口，不再强制 BI 后经过 Report Worker。
- 原始内容：BI 成功只发 `artifact.created`，Report Worker 必须调用 `datalogue_submit_report`，Runner/Runtime 双完成闸门校验。
- 后端全量 `609 passed`。

### 2026-07-17 15:50 · 低危质量债与历史分页收敛

- 关键改动：聊天双轨实现合并、SQL 标识符/错误模式去重、`datetime.utcnow()` 替换、调试面板仅开发环境懒加载、会话历史有界分页（默认最近 200 条 + before_message_id 游标）、Lazy facade 循环依赖解除。
- 验证：后端 `572 passed`，前端 `22 files / 204 passed`，生产 build 不含调试协议。

### 2026-07-17 15:24 · 中危安全、并发、状态与前端正确性修复

- 关键改动：脱敏边界改为敏感字段优先，ORM/SQL 移到工作线程 + Session 不跨线程、SSE 建流前释放鉴权 Session、任务绝对超时、蓝图分析任务持久化、Worker 进度 Redis pub/sub 跨进程桥、前端数据竞态与死链修复。
- 验证：后端 `569 passed`，前端 `24 files / 210 passed`，Alembic head `g4b5c6d7e8f9`。

### 2026-07-17 15:06 · 代码审查后端从 Kimi 切换为 Claude Code

- 事项：`.codex/hooks/claude_code_review.py` 替换 Kimi，CLI 使用 `--print --permission-mode plan --safe-mode` 并禁止继承 Kimi 路由。
- 残留风险：需 `claude auth login` 完成 Anthropic 登录使审卫生效。

### 2026-07-17 14:53 · 高危安全问题系统性修复

- 关键改动：预览注入防御、SQL Guard `SELECT INTO` 拦截、NL2SQL 改为 SQLAlchemy 命名参数、生产环境默认密钥拒启、前端传输加密移除、首次改密强制、会话/工作台/任务入口属主校验、AgentScope 孤儿清理、Worker SSE 按 leader_session_id 隔离。
- 验证：后端 `565 passed`，Alembic head `f3a4b5c6d7e8`。部署前必须设置生产非默认密钥。
- 残留风险：尚未在真实异构数据源上重放攻击载荷。

### 2026-07-17 13:48 · Codex Stop Hook：Claude Code 自动审查

- 事项：`.codex/hooks/claude_code_review.py` — 隐藏标记触发 Stop Hook，汇总会话变更、macOS sandbox-exec 隔离副本、指纹去重、PASS/FAIL 回送。
- 残留风险：Anthropic OAuth 登录需用户自行完成。

### 2026-07-17 13:23 · 收紧项目记忆写入边界

- 事项：只记录实际项目变更（需求/代码/配置/文档/缺陷/技术决策），普通对话、问答、分析、状态确认不写入。
- 涉及文件：`AGENTS.md`、`datalogue-api/AGENTS.md`、`CLAUDE.md`。

### 2026-07-17 10:44 · 问数流协议、全量绿灯与小屏体验

- 关键改动：问数 SSE 使用 `agent_team` 事件能力等级、AgentScope SSE 取消读取超时、全局壳层 900px 抽屉 + 390px 输入区、移动端适配、全局搜索/快捷新建/404/图标标签补齐。
- 验证：后端 `552 passed`，前端 `24 files / 209 passed`，真实浏览器桌面+移动端走查通过。

### 2026-07-17 09:30 · 同步生产管理员密码

- 事项：SSH 定位生产 admin，PBKDF2-SHA256 更新哈希，生产 `.env` 注入 `BOOTSTRAP_ADMIN_PASSWORD`，保留修改前备份。
- 残留风险：后续应加首次登录强制改密机制。

### 2026-07-16 17:51 · 全局 API 鉴权与模型目录审查修复

- 关键改动：认证接口拆为公开路由，其余 `/api` 统一登录保护、LLM/credential 要求管理员权限、Nginx 禁止公网 `/agentscope/`、模型目录竞态修复、SSE 复用 Bearer Token。
- 验证：后端 `542 passed, 10 failed`（均为既有失败），前端 `16 passed`。

### 2026-07-16 17:40 · 修复模型切换缺少 API Key

- 关键改动：credential PATCH 时从 `api_key_enc` 解密补齐请求，`api_key_set` 以本地密文为准。
- 验证：回归 `13 passed`。
- 残留风险：切换供应商类型时仍需显式填写新密钥。
