# 项目记忆

本文件是 Datalogue 项目的压缩版完成记录。文件名使用英文，内容继续使用中文，便于新 Codex 线程检索，同时避免旧版长文件拖慢启动上下文。

## 使用规则

- 新完成的功能继续按时间顺序追加，时间格式为 `YYYY-MM-DD HH:mm`。
- 每条新增记录至少包含：完成时间、功能名称、涉及文件、关键改动、验证方式、残留风险或后续事项。
- 本文件不是启动上下文；需要历史背景时，按关键词、模块名、文件名或任务名检索。
- 任务路由优先读取 `docs/上下文入口.md`，再按需检索本文件。
- 旧文件 `.codex/项目记忆.md` 已在 2026-06-20 压缩迁移到本文件。

## 当前协作默认值

- 默认使用中文协作。
- 当前项目是 Datalogue / 数语，核心方向是 AI 原生智能问数。
- 仓库存在 `.codegraph/` 时，代码探索优先用 CodeGraph。
- 不主动回滚用户或其他工具已有改动；脏工作区只处理当前任务相关文件。
- Datalogue 复杂问题优先做真实链路验证：页面/前端回放、Langfuse trace、后端日志、prompt/token、final payload、历史回放交叉取证。
- Playwright、浏览器或 E2E 截图放 `/private/tmp` 或系统临时目录，不写入仓库。
- 新增数据库表时，Alembic 迁移必须同步添加中文表注释，并为表内每个字段添加中文字段注释；后续新增字段也必须添加中文字段注释；状态、类型、角色等字典字段要写清 `字典：code=中文含义`。

## 历史压缩记录

### 2026-06-05

- 建立项目开发标准、项目记忆规则和 Python 文件头注释模板。
- 前端侧隐藏语义治理助手入口，优化数据集数据预览组件。

### 2026-06-08

- 建立问数入口意图分类与路由策略。
- 分析蓝图从 mock SQL 分析逐步接入真实 AI/语义执行链路，补充 SQL 参数保护、耗时日志、同步请求、手动草稿、创建向导 UI、发布流程简化和详情节点修复。
- 修复入口分类、蓝图执行和 SSE 序列化问题。
- 增加数据集级 SQL 查询约束配置。

### 2026-06-09

- 升级 NL2DSL 资产引用 Schema，使用语义资产解析替换指标解析节点。
- 接入业务术语运行时归一化和数据集问数上下文组装服务。
- 建立 SQL 静态安全校验、SQLGlot AST 解析、方言规范化、失败诊断、自动修复与重试闭环。
- 增加回答解释、低置信确认、SQL 结果折叠、SQL 复制、风险提示逐行展示等前端体验。
- 修复历史会话数据集绑定丢失。
- 增强术语和蓝图语义验证。

### 2026-06-10

- 完成术语冲突澄清回复闭环。
- 增强多数据源能力和企业驱动离线交付方案。
- 接入 LiteLLM 前端配置化、模型配置表单、自动填充和测试连接能力。
- 产出 Langfuse 可观测能力需求与开发文档，并支持导出 Word。

### 2026-06-11

- 接入 Langfuse 本地部署、SDK 运行环境修复、Trace 深链、查询审计、内嵌 Trace 渲染和历史消息 Trace 可见性。
- 将术语功能降级为语义词典。
- 固定数据集能力 Tab 像素布局，做响应式与可访问性收尾。
- 补齐 Langfuse 耗时、Token、性能指标和中文/原始节点名口径。
- 支持 LLM Think 模式配置化关闭。
- 试验 shadcn/ui 迁移，后因视觉和回归问题回滚。

### 2026-06-12

- 建立 Dataset SubAgent Manifest 治理契约和 LeadAgent Manifest 自动路由。
- 接入 LeadAgent 控制面 Tools、ToolPolicy、Skills 自主决策、Planner Langfuse 监测、渐进式披露和自动路由报告生成。
- 区分 Lead/Sub Trace 层级，修复 Manifest 候选展示名。
- 建立多轮能力基础：SubAgent 数据面 merge/digest、LeadAgent 控制面记忆、ConversationStore、胶囊管道、澄清跨轮恢复、消息压缩、Langfuse 多轮观测、回归与灰度。
- 修复 assistant 聊天链路稳定 session 与后端会话 ID 映射。
- 生成用户手册、操作手册和真实页面截图版文档。
- 完成 ChatBI 思考过程三层展示和 Langfuse Prompt 批量创建脚本。

### 2026-06-13 至 2026-06-14

- 增强 LeadAgent LLM 交互日志，修复意图识别澄清回复。
- 产出数语系统设计方案文档。
- 修复术语澄清早退顺序、LangGraph noop、工作日志问题页面链路等问题。

### 2026-06-15

- 建立 SubAgent 查询规划层 v1/v2，增强规划质量和 Langfuse Trace。
- 修复模型 Think 标签关闭后的流式泄露。
- 前端与 Trace 节点名统一为原始节点名。
- LLM 调用统一到 LiteLLM SDK，优化慢节点和日志明细正确性。
- 收窄明细查询空 DSL 错误提示，加入 DSL 语义层提示词渐进式披露。
- 建立 Thread Memory 与 QueryTaskCapsule，并支持明细追问上下文承接与写回。

### 2026-06-16

- SubAgent 与 DSL 消费 QueryTaskCapsule。
- Message Gateway 与 QueryTaskCapsule SSE 可观测落地。
- 修复日志明细模板 fallback 和 LiteLLM 流式报告。
- 修复 assistant-ui 本地线程与后端会话 ID 映射。
- 数据集选择后可恢复上一轮原问题执行。
- LeadAgent Planner 输入投影 M1 灰度接入，并修复审查问题。

### 2026-06-17

- 建立 Agent 上下文轻量入口，清理启动上下文冗余。
- LeadAgent 渐进式语义资产注入 Phase 2/3 接入。
- 历史对话恢复 SQL 与执行结果展示。
- 蓝图步骤结构化视图 T1。
- `last_success_task` 最小承接快照与跨轮状态瘦身。
- SubAgent Tool Adapter 双层出参分离。
- 多轮结果 artifact、快速路径、ArtifactStore、fan-out、A2A Runner 基础落地。
- 修复 `query_artifact` Alembic 幂等升级和 SubAgent/A2A/Artifact 层 review 阻塞问题。

### 2026-06-18

- SubAgent Planner 资产详情受控循环。
- 修复 `last_success_task` 重复 `result_ref` 启动错误。
- 打通 `query_artifacts` 到 ArtifactStore 的 DB 兜底闭环。
- `last_success_task` token 预算配置化，并补充多轮配置示例。
- 将推荐配置项运行时接入 `Settings` 和调用点。
- 修复日志数据集姓名过滤追问、蓝图缺参抢占明细查询。
- 增加 ConversationState 多轮状态排查日志。
- LeadAgent 多轮追问抽象槽位修复，并同步本地 Prompt 到 Langfuse。
- 在 planner 截断或非法 JSON 时保留多轮追问槽位。
- 修复内联产物结果表格渲染。
- 撤销从当前自然语言硬猜人名的 fallback；姓名优先来自结构化槽位或上一轮已确认过滤，时间类低风险槽位可保守归一化。

### 2026-06-20

- 合并本地 Docker Compose 系统 PostgreSQL 与 Langfuse PostgreSQL：删除独立 `langfuse-postgres`，让 Langfuse 使用同一 PostgreSQL 实例中的独立 database；迁移后 Langfuse public 表数量 70，`curl -I http://localhost:3000` 返回 200。
- Manifest 治理与执行前 fail-closed 门禁：阻断 current Manifest 缺失、schema stale、review 非 current、权限未允许、quality failed 和低置信路由；新增 rollback API 和前端 Manifest 面板。验证包括 166 条后端测试、`py_compile`、前端 lint/build。
- 新增 `datalogue-api/AGENTS.md`，固化 API 子目录 Codex 交接规则。

## 高价值判断

- Datalogue 当前业务链路不依赖 Redis 保存多轮业务状态；`last_success_task`、`conversation_state.subagent_capsules` 和 query artifacts 的真相在数据库或应用 ArtifactStore 路径，Langfuse/BullMQ Redis key 不能当成业务状态依据。
- 多轮追问不要从当前自然语言残留硬猜 `person`；应依赖 LLM 结构化槽位、上一轮已确认过滤或澄清。
- 数据集上下文压缩优先采用“轻量候选资产目录 + 按需详情补合”，不要一开始把完整字段、SQL、样例行全部塞进 prompt。
- `.env.example` 中要区分“已被 Settings 读取并生效的配置”和“尚未接入的候选项”。
- `localhost:8080` 等地址返回应用层 `Unauthorized` 时，优先判断服务已启动，继续排查认证、代理或路由，不要直接判定服务未启动。

## 最新详细记录

### 2026-06-20 18:13 · 项目记忆英文文件名与中文压缩内容迁移

- 涉及文件：`datalogue-api/AGENTS.md`、`AGENTS.md`、`CLAUDE.md`、`docs/上下文入口.md`、`.codex/project-memory.md`、`.codex/项目记忆.md`
- 关键改动：将项目记忆文件名改为英文 `.codex/project-memory.md`，内容保持中文；把旧 `.codex/项目记忆.md` 的 1100 多行完成记录压缩为按日期和主题组织的可检索摘要；更新 Agent/Claude/上下文入口文档中的项目记忆路径；删除旧中文文件。
- 验证方式：使用 `rg` 检查旧文件名引用；读取新文件和入口文档；执行 `git diff --check`。
- 残留风险：压缩版保留任务级线索和关键判断，不再逐字保存所有历史记录；如需旧版精确措辞，需要从 Git 历史中恢复。

### 2026-06-22 11:35 · 数据库字典字段注释更新

- 涉及文件：`datalogue-api/alembic/versions/l7m8n9o0p1q2_add_dictionary_column_comments.py`、`datalogue-api/alembic/versions/m8n9o0p1q2r3_add_late_table_comments.py`、`datalogue-api/alembic/versions/n9o0p1q2r3s4_complete_existing_comments.py`、`datalogue-api/tests/test_dictionary_column_comments.py`、`.codex/project-memory.md`
- 关键改动：新增 Alembic 迁移，为数据源状态、消息角色、字段语义角色、审核状态、术语类型、蓝图实现类型、入口路由、Manifest 审核状态等字典字段追加统一的 `字典：code=中文含义` 注释；补充 `conversation_state`、`dataset_subagent_manifest`、`query_artifact` 三个后续新增表的表级中文注释；检查当前 PostgreSQL `public` schema 后，继续补齐 `alembic_version`、LangGraph checkpoint 表、`conversation_state`、`dataset_subagent_manifest`、`query_artifact`、`source_table`、`source_column` 的缺失表/字段注释；迁移会检查表和字段存在性，兼容本地库结构差异。
- 验证方式：执行 `python3 -m py_compile`；执行 `cd datalogue-api && pytest tests/test_dictionary_column_comments.py -q`；执行 `cd datalogue-api && alembic upgrade head`；通过 PostgreSQL `col_description` 抽查字典字段注释已写入真实数据库；通过 `obj_description` 抽查表注释已写入真实数据库；最后用缺失统计 SQL 确认 `public` schema 表注释缺失数为 0、字段注释缺失数为 0，当前 Alembic 版本为 `n9o0p1q2r3s4 (head)`。
- 残留风险：字典值来自当前代码、前端选项和既有注释中的稳定取值；未来新增状态码、新表或新增字段时必须同步维护中文注释迁移。

### 2026-06-22 11:45 · 前端品牌 Logo 与浏览器标题图标替换

- 涉及文件：`datalogue-web/public/datalogue-logo.png`、`datalogue-web/public/datalogue-favicon.png`、`datalogue-web/src/components/sidebar.jsx`、`datalogue-web/src/styles.css`、`datalogue-web/index.html`、`.codex/project-memory.md`
- 关键改动：基于新品牌图裁剪生成完整页面 logo 和方形 D 标识 favicon；侧边栏品牌区从 CSS 绘制标识改为图片资产；浏览器标题图标从旧 `favicon.svg` 切换为新的 PNG favicon；将侧栏 logo 显示宽度从 152px 逐步收敛到 112px，并减少品牌区底部留白。
- 验证方式：执行 `cd datalogue-web && npm run lint`；执行 `cd datalogue-web && npm run build`；启动 `npm run dev -- --host 127.0.0.1` 后用 in-app Browser 检查 `/` 桌面视口和 `390x844` 移动视口，确认侧栏 logo 加载完成、favicon href 指向 `/datalogue-favicon.png`、侧栏导航到 `/chat` 后 logo 仍可见且控制台无 warn/error；优化后复查桌面视口，logo 实际渲染为 112x49，品牌区高度约 63px。
- 残留风险：窄视口仍沿用现有固定侧栏布局，本次只验证 logo 不丢失、不溢出；未调整整体移动端布局。

### 2026-06-22 12:06 · 数据集页面数据表计数显示已选表

- 涉及文件：`datalogue-web/src/components/datasets.jsx`、`datalogue-web/tests/unit/components/datasets-selected-table-count.test.jsx`、`.codex/project-memory.md`
- 关键改动：将数据集语义能力工作区顶部“数据表”能力卡计数从 `allSourceTables.length` 改为 `selectedTableIds.size`，避免显示当前连接 schema 的全量表数量；新增组件回归测试，模拟 schema 3 张表但数据集只选 1 张表，固定顶部能力卡显示 1。
- 验证方式：先执行 `cd datalogue-web && npm test -- tests/unit/components/datasets-selected-table-count.test.jsx` 确认测试红灯，失败输出显示“数据表”按钮 count 为 3；修复后再次执行该命令通过；执行 `cd datalogue-web && npm test`，3 个测试文件 14 条用例通过；执行 `cd datalogue-web && npm run lint`，0 error、15 个既有 warning；执行 `cd datalogue-web && npm run build` 通过。
- 残留风险：本次只修正顶部能力卡计数；左侧“已选择/未选择”分组仍按当前搜索过滤结果计数，保持原有交互语义。
