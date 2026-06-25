# 项目记忆

本文件是 Datalogue 项目的压缩版完成记录。文件名使用英文，内容继续使用中文，便于新 Codex 线程检索，同时避免旧版长文件拖慢启动上下文。

## 使用规则

- 新完成的功能继续按时间顺序追加，时间格式为 `YYYY-MM-DD HH:mm`。
- 每条新增记录至少包含：完成时间、功能名称、涉及文件、关键改动、验证方式、残留风险或后续事项。
- 本文件不是启动上下文；需要历史背景时，按关键词、模块名、文件名或任务名检索。
- 任务路由优先读取 `docs/上下文入口.md`，再按需检索本文件。
- 旧文件 `.codex/项目记忆.md` 已在 2026-06-20 压缩迁移到本文件。
- 新增或修改关键代码时，必须在重要分支、边界条件、方法调用、关键赋值、跨层状态写入/回放、外部副作用、降级/fallback 和异常处理处补充中文关键行级注释；优先写在对应调用或关键操作同一行的行尾，不逐行机械注释。
- “最新详细记录”超过 10 条时，必须把较早详细记录压缩进“历史压缩记录”；“历史压缩记录”中的压缩条目超过 10 条时，继续深度压缩为更高层主题摘要。

## 当前协作默认值

- 默认使用中文协作。
- 当前项目是 Datalogue / 数语，核心方向是 AI 原生智能问数。
- 仓库存在 `.codegraph/` 时，代码探索优先用 CodeGraph。
- 不主动回滚用户或其他工具已有改动；脏工作区只处理当前任务相关文件。
- Datalogue 复杂问题优先做真实链路验证：页面/前端回放、Langfuse trace、后端日志、prompt/token、final payload、历史回放交叉取证。
- Playwright、浏览器或 E2E 截图放 `/private/tmp` 或系统临时目录，不写入仓库。
- 新增数据库表时，Alembic 迁移必须同步添加中文表注释，并为表内每个字段添加中文字段注释；后续新增字段也必须添加中文字段注释；状态、类型、角色等字典字段要写清 `字典：code=中文含义`。

## 历史压缩记录

### 2026-06-05 至 2026-06-14

- 建立早期工程规范、项目记忆、Python 文件头模板和基础前端工作台体验。
- 打通问数入口、蓝图分析、NL2DSL/语义资产、术语归一化、数据集上下文、SQL 安全校验与自动修复、回答解释和低置信确认等问数基础链路。
- 接入 LiteLLM 配置化、Langfuse 本地观测、Trace 深链、查询审计、历史 Trace 可见性、Think 模式关闭和相关设计/开发文档。
- 建立 Dataset SubAgent Manifest、LeadAgent 控制面工具/Planner、渐进式披露、多轮 ConversationStore/capsule/澄清恢复、ChatBI 思考过程和 Prompt 批量创建基础。
- 持续修复入口分类、SSE 序列化、历史会话数据集绑定、术语澄清早退、LangGraph noop、工作日志页面链路、Manifest 展示和 assistant-ui 会话映射等早期问题。

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
- 将旧版中文项目记忆压缩迁移为英文文件名 `.codex/project-memory.md`，同步更新 Agent/Claude/上下文入口引用，保留中文正文和任务级检索线索。

### 2026-06-22

- 补齐数据库字典字段、后续新增表和 LangGraph checkpoint 相关表/字段中文注释迁移，真实 PostgreSQL 抽查确认表注释和字段注释缺失数为 0。
- 替换前端侧栏品牌 Logo 与浏览器 favicon，完成桌面和移动视口可见性检查。
- 修正数据集页面顶部“数据表”能力卡计数为当前数据集已选表数量，并补组件回归测试、lint 和 build 验证。
- 去重 LeadAgent 两阶段 Planner Prompt，并同步 Langfuse Prompt Management 的 production v4，回读确认远端与本地一致。
- 修复新建对话排序与本地草稿体验：新对话优先显示在最近对话顶部，未发送时不落库，发送首条消息时再创建后端会话。

### 2026-06-23

- SubAgent Planner 金额/合计类聚合兜底增强：当 LLM 空响应或非法 JSON 且候选资产已有字段/表时，不再误判 `unsupported/reject`，而是生成 `metric_query + query_graph` 计划交给 QueryGraph 继续执行；补充 planner 和 subagent run 回归测试。
- `/chat/stream` 主链路 checkpoint 日志增强：统一记录 request、trace、gateway、LeadAgent 路由、SubAgent 候选资产/query plan/result、Graph 完成、落库和 final payload 等关键节点，并补充关键链路行级注释，便于页面、SSE、后端日志和 Langfuse trace 交叉取证。
- SubAgent 规则规划器命名澄清：将 `build_fallback_query_plan` 更名为 `build_rule_based_query_plan`，同步公共导出、测试和规划文档，明确 LLM 前确定性预判与 LLM 失败后规则兜底的边界。
- 固化关键代码中文行级注释规范与项目记忆压缩规则：更新 AGENTS、上下文入口和核心问数链路注释，要求新增或修改关键业务代码时在重要分支、跨层状态、fallback、外部副作用等位置补充解释业务边界的中文注释。
- 关键注释进一步调整为调用行/操作行行尾注释：覆盖 chat stream checkpoint、trace context、artifact、conversation store、planner、thread list 等关键调用点，并通过 py_compile、ruff、前端 lint 和 diff check 验证。
- SubAgent Planner LLM 原始响应诊断：新增 `_planner_response_debug()`，在普通规划和 detail loop 的 LLM 返回后记录截断后的响应类型、content 类型、metadata、usage 和 additional kwargs，便于排查空响应、非法 JSON 与服务端 token/finish reason 的真实关系；通过 planner targeted tests 和 py_compile 验证。

## 高价值判断

- Datalogue 当前业务链路不依赖 Redis 保存多轮业务状态；`last_success_task`、`conversation_state.subagent_capsules` 和 query artifacts 的真相在数据库或应用 ArtifactStore 路径，Langfuse/BullMQ Redis key 不能当成业务状态依据。
- 多轮追问不要从当前自然语言残留硬猜 `person`；应依赖 LLM 结构化槽位、上一轮已确认过滤或澄清。
- 数据集上下文压缩优先采用“轻量候选资产目录 + 按需详情补合”，不要一开始把完整字段、SQL、样例行全部塞进 prompt。
- `.env.example` 中要区分“已被 Settings 读取并生效的配置”和“尚未接入的候选项”。
- `localhost:8080` 等地址返回应用层 `Unauthorized` 时，优先判断服务已启动，继续排查认证、代理或路由，不要直接判定服务未启动。

## 最新详细记录

### 2026-06-23 12:41 · 新对话本地草稿可见且未发送不持久化

- 涉及文件：`datalogue-web/src/assistant/ThreadList.jsx`、`datalogue-web/tests/unit/assistant/thread-list-new-conversation.test.jsx`、`.codex/project-memory.md`
- 关键改动：新对话按钮不再调用 `createConversation`，改为只执行 `aui.threads().switchToNewThread()` 并导航回 `/chat`；新增 `DraftThreadListItem`，当 assistant-ui 存在 `newThreadId` 时在“最近对话”顶部显示本地“新对话”草稿并按 `mainThreadId` 高亮；首条消息发送时仍由 `thread-list-adapter.initialize()` 创建后端 conversation；按钮保留创建中禁用保护，避免连续点击造成 runtime 状态抖动。
- 验证方式：先执行 `cd datalogue-web && npm test -- tests/unit/assistant/thread-list-new-conversation.test.jsx` 确认组件层用例红灯，失败表现为找不到 `thread-list-draft-item`；实现后再次执行该命令，4 条用例通过；执行 `cd datalogue-web && npm run lint`，0 error、15 个既有 warning；执行 `cd datalogue-web && npm run build` 通过；调用 `GET /api/conversation?archived=false` 记录点击前数量为 4，使用 in-app Browser 打开 `http://localhost:5173/chat/4` 后点击 `.thread-list-new` 且不发送消息，URL 回到 `/chat`，左栏第 0 项为 active draft“新对话”，再次请求后端列表数量仍为 4。
- 残留风险：本次只验证“未发送不新增数据库会话”和本地草稿可见；未实际发送一条新消息走 LLM 全链路验证创建后的标题刷新和列表排序。

### 2026-06-23 17:08 · 生成用户版项目整体介绍手册

- 涉及文件：`docs/数语项目整体介绍手册.docx`、`.codex/project-memory.md`
- 关键改动：生成面向业务用户、项目负责人和使用方的 Word 版介绍手册；按用户反馈弱化技术实现和内部代码名称，重点说明数语已经具备的功能、每项能力大致如何实现、能解决的业务问题、典型场景、使用流程、与普通报表/简单聊天机器人的区别、当前边界和可交付内容。
- 验证方式：使用文档构建脚本生成 DOCX；通过 bundled LibreOffice 渲染为 6 页 PNG/PDF；抽查首页、功能表格页、使用流程页、对比页和边界页，确认无文字裁剪、表格跨页断裂、编号延续或提示框拆分问题。
- 残留风险：本文是用户版整体介绍，不替代销售材料、正式产品白皮书或逐页截图版操作手册；若用于外部客户交付，后续可补品牌视觉、真实页面截图和客户场景案例。

### 2026-06-23 17:35 · Hermes Skill 直连数语只读问数预览

- 涉及文件：`datalogue-api/app/api/dataset.py`、`datalogue-api/app/services/sql_preview.py`、`datalogue-api/app/schemas/dataset.py`、`datalogue-api/app/schemas/__init__.py`、`datalogue-api/tests/test_dataset.py`、`hermes-skills/datalogue/scripts/api_assets.py`、`hermes-skills/datalogue/SKILL.md`、`hermes-skills/datalogue/SOUL.md`、`hermes-skills/datalogue/references/capabilities.md`、`.codex/project-memory.md`
- 关键改动：新增 `POST /api/dataset/{ds_id}/sql/preview`，按 dataset 绑定 datasource、已选 source tables、`guard_readonly_sql` 和 `query_constraints` 执行只读 SQL 预览，不写 conversation/message/trace，也不进入 LeadAgent/LangGraph；Hermes Skill 新增 `plan-query` 和 `execute-sql`，前者组装数据集候选、选中数据集资产和 schema，后者只调用后端 preview 接口；同步更新 Skill/SOUL/capabilities 的轻量问数流程和 SQL 生成边界。
- 验证方式：先执行 `pytest datalogue-api/tests/test_dataset.py -k "sql_preview"` 确认新增用例红灯，失败表现为 `app.services.sql_preview` 不存在和路由 404；实现后该组 5 条用例通过；执行 `pytest datalogue-api/tests/test_dataset.py`，32 条通过；执行 `python3 -m py_compile hermes-skills/datalogue/scripts/api_assets.py datalogue-api/app/services/sql_preview.py`；执行 `python3 hermes-skills/datalogue/scripts/api_assets.py capabilities`；执行 live `health`、`list-datasets`、`plan-query "双周会议部门项目进展" --limit 3 --schema-limit 10`；执行 live `execute-sql 12 --sql "SELECT deptcode, COUNT(*) AS cnt FROM xm_zbjgbp GROUP BY deptcode LIMIT 5"` 返回 3 行；执行 live `execute-sql 12 --sql "DELETE FROM xm_zbjgbp WHERE 1 = 0"` 被 Guard 以 `FORBIDDEN_KEYWORD` 拦截。
- 残留风险：第一版 SQL 由 Hermes 模型生成，后端只做安全校验和执行，不做 SQL 自动修复；`plan-query` 默认返回选中数据集的部分 schema，复杂问题可能需要 Hermes 继续调用 `describe-dataset` 获取更完整字段上下文。

### 2026-06-24 00:08 · 生成当前项目工作总结与下步计划文档

- 涉及文件：`docs/当前项目工作总结与下步计划.md`、`.codex/project-memory.md`
- 关键改动：新增面向项目负责人、业务使用方和产品/研发协作人员的阶段总结文档，说明整体建设思路、已完成任务、成果截图、当前成熟度判断、P0/P1/P2 下步计划和真实链路验收口径；复用 `docs/user-manual-screenshots/` 和 `docs/datalogue_full_execution_flow.png` 的现有成果截图。
- 验证方式：确认文档引用的 7 张图片均存在；执行 `git diff --check -- docs/当前项目工作总结与下步计划.md` 通过；按项目记忆规则将最早一条最新详细记录压缩进历史区，保持最新详细记录不超过 10 条。
- 残留风险：本文使用现有截图和当前代码/记忆/文档梳理生成，未重新启动本地页面截取最新运行态截图；若用于正式外部汇报，可继续导出为 PPT/Word 并补充客户场景案例。

### 2026-06-24 00:17 · 工作总结文档改为功能点逐项展开

- 涉及文件：`docs/当前项目工作总结与下步计划.md`、`.codex/project-memory.md`
- 关键改动：按用户反馈移除“已完成工作任务”和“下步工作计划”里的功能点表格，改为一个功能点一个功能点展开说明；每个已落地功能补充“解决的问题、设计思路、当前效果”，下步计划补充任务目标、推进逻辑和验收关注点，让非研发读者能理解为什么要这么做。
- 验证方式：执行 `rg -n "\\| 模块|\\| 任务|建议任务|已完成内容：" docs/当前项目工作总结与下步计划.md` 未发现旧表格标记；执行 `git diff --check -- docs/当前项目工作总结与下步计划.md` 通过；按项目记忆规则将当前最早一条详细记录压缩进历史区，保持最新详细记录不超过 10 条。
- 残留风险：本次仍基于现有截图和文字材料改写，未重新导出 Word/PPT 版；若用于汇报，可继续做版式化交付。

### 2026-06-24 00:25 · 工作总结文档补齐功能点对应截图

- 涉及文件：`docs/当前项目工作总结与下步计划.md`、`.codex/project-memory.md`
- 关键改动：按用户反馈把截图从集中展示改为跟随具体功能点展示；27 个已完成功能点均补充对应截图说明和图片引用，前端/治理功能使用页面截图，后端链路/工程治理能力使用完整执行链路图、查询审计页或 Schema 页面承接。
- 验证方式：脚本检查“已完成工作任务”区 27 个功能点全部包含图片引用；脚本检查全篇 37 个图片引用文件均存在；执行 `git diff --check -- docs/当前项目工作总结与下步计划.md` 通过；按项目记忆规则将当前最早一条详细记录压缩进历史区，保持最新详细记录不超过 10 条。
- 残留风险：后端链路类功能没有独立产品页，当前用链路图/审计页对应其可见承接面；若后续要做正式汇报，可再补真实 Langfuse 页面或日志截图。

### 2026-06-24 00:47 · 工作总结 Word 增强版补齐截图与执行链路图

- 涉及文件：`/Users/yangkai/Downloads/数语智能问数平台-项目介绍与工作总结-增强版.docx`、`/Users/yangkai/Downloads/datalogue_execution_chain_explained.png`、`.codex/project-memory.md`
- 关键改动：在用户提供的 Word 文档基础上生成增强版，保留原始文档不覆盖；为能力详解部分新增“数语智能问数执行链路说明图”，用图解释从用户提问、LeadAgent 编排、Manifest 门禁、Dataset SubAgent、QueryGraph、SQL 执行到答案解释的执行链路；为每个具体功能点插入对应截图或组合截图；在后续工作计划中新增 ECharts 报表生成、多租户能力和权限管理体系三项企业级治理计划。
- 验证方式：使用 bundled Python 检查增强版 DOCX 包含 28 个内嵌图片，且 `ECharts 报表生成`、`多租户能力`、`权限管理体系` 三个计划标题均存在；通过 bundled LibreOffice 将增强版 DOCX 渲染为 34 页 PNG/PDF；抽查执行链路图页、功能截图页、计划页和结论页，确认图片和文字无明显裁剪、重叠或断裂。
- 残留风险：截图复用当前项目已有用户手册截图和生成的链路说明图；后续若页面样式或功能命名调整，应重新截取最新运行态页面并同步替换文档图片。

### 2026-06-24 01:04 · 工作总结 Word 截图替换为当前运行态

- 涉及文件：`/Users/yangkai/Downloads/数语智能问数平台-项目介绍与工作总结-增强版-最新截图.docx`、`/Users/yangkai/Downloads/datalogue_latest_screenshots_20260624/`、`/Users/yangkai/Downloads/datalogue_docx_assets_latest/`、`.codex/project-memory.md`
- 关键改动：启动当前前端页面并复用本地后端健康服务，重新截取工作台、问数中心、查询审计、数据集治理各 Tab、数据源 Schema、API 管理、系统设置等当前运行态截图；按原 Word 图片位尺寸生成单图和组合图，替换增强版 DOCX 中除执行链路图外的所有页面截图，生成“最新截图”版本。
- 验证方式：使用 Chrome headless 批量截取 37 张当前页面截图并生成总览拼图；处理为 21 张 Word 图像资产后替换 DOCX 内嵌媒体；使用 bundled Python 检查最新截图版仍包含 28 个内嵌图片且 ECharts、多租户、权限管理三项计划标题保留；通过 bundled LibreOffice 渲染为 34 页 PNG/PDF；抽查工作台、数据集、执行链路、历史/审计、LLM、数据源/API 等关键页，确认无白屏、错误遮罩、明显裁剪或重叠。
- 残留风险：截图反映 2026-06-24 01:04 本地运行态；数据源 Schema 截图过程中前端控制台曾出现一次 Schema fetch warning，但最终截图页有可见 Schema/数据源状态，后续若后端数据或页面样式变化仍需重新截取。

### 2026-06-24 10:11 · 工作总结 Word 分拆执行链路图

- 涉及文件：`/Users/yangkai/Downloads/数语智能问数平台-项目介绍与工作总结-增强版-分链路图.docx`、`/Users/yangkai/Downloads/datalogue_chain_diagrams_split/`、`.codex/project-memory.md`
- 关键改动：基于用户已修改的“增强版-最新截图”Word 文档继续生成新版，不覆盖原文件；保留总体介绍处的总体链路图，并为 LeadAgent、Dataset SubAgent、QueryGraph/SubGraph、Trace 观测分别生成独立执行链路图，替换原先多个功能点复用同一张总体图的问题；同步更新功能点的“界面 / 链路承载”和图片说明文字，强调总体图与具体能力链路图的边界。
- 验证方式：使用 bundled Python 检查新版 DOCX 包含 29 个内嵌图片，且 `总体版`、`LeadAgent 控制链路图`、`Dataset SubAgent 执行链路图`、`QueryGraph / SubGraph 执行链路图`、`Trace 观测链路图` 等说明均存在；确认四个功能链路段落分别引用 4 个不同媒体文件；通过 bundled LibreOffice 渲染为 36 页 PNG/PDF，并抽查总体图、LeadAgent、Dataset SubAgent、QueryGraph/SubGraph、Trace 观测关键页无明显裁剪、重叠或错图。
- 残留风险：本次新增链路图是解释型架构图，不是实时页面截图；后续如果 Agent 职责、Trace 字段或 QueryGraph 节点命名调整，需要同步更新对应链路图与文档说明。
