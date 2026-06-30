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
- 修正数据集页面顶部“数据表”能力卡计数为当前数据集已选表数量，并补组件回归测试；压缩 LeadAgent 两阶段 Planner Prompt 重复说明，同步 Langfuse production v4，保持 JSON 输出契约不变。

### 2026-06-28 C1 RepairPlan 与页面主链收口

- 完成 C1 RepairPlan v1 契约、`repair.*` 事件、Artifact refs、脱敏 Artifact API、前端 Chat/ArtifactCard 承接和真实问题“查询杨凯 2024 年工作日志”可信模板成功链路；补齐字段失败诊断、旧会话回放、公共 SSE/history/API 脱敏和 `last_success_task` 成功门禁。
- 基于页面 E2E 修复普通 Chat 可见层 SQL 泄露、ArtifactCard 回放、会话切换 URL 同步、新对话草稿不回填旧会话等问题；验证包含后端 pytest、前端 test/lint/build、`git diff --check` 和本地 `/chat/25` 页面扫描。
- 保留边界：C1 不实现字段级 RepairPatch apply/recompile；真实字段漂移自动修复、RepairPatch IR、候选字段和真实重跑验收归 C2。


### 2026-06-26 B-first C-ready 核心链路集成

- 完成 BI_SOUL 内部契约同步、Capability Router 路由收窄、QueryGraph Compiler 与当前数据源方言门禁、SubAgent ToolAdapter 三层出参、统一 Event Envelope、ask_bi 最小契约、AgentScope Shell Adapter、ArtifactCard/TaskTimeline/CandidateDatasetCard 前端承接、Retry checkpoint、Artifact refs 持久化、旧会话兼容和 DAT-18 五件套验收记录。
- 核心边界：LeadAgent 只看业务能力摘要，外层 Agent 只能调用 `ask_bi`；LLM 不直接生成可执行 SQL；用户可见 SSE/前端/历史回放不暴露 raw SQL、raw result、schema、capsule、query_plan、完整字段/表资产详情；旧会话不迁移、不回填、不伪造 ArtifactCard。
- 验证覆盖：后端 capability/BI_SOUL/router/compiler/dialect/tool adapter/event envelope/ask_bi/AgentScope adapter/artifact/retry/legacy/chat/main-chain acceptance 系列 pytest，前端 chat-adapter、ArtifactCard、TaskTimeline、MyMessage、ChatPage、lint/build 和 `git diff --check`；真实页面仍按后续 DAT-18/C1/C2/C3 记录继续补证。
- 残留风险：2026-06-26 阶段仍处 B-first C-ready，AgentScope 未接管主 runtime；真实 Langfuse UI 和真实业务成功查询证据在后续 C1/C2/C3 记录中继续分层推进。


### 2026-06-28 至 2026-06-30 C2 RepairPatch 主链收口

- 完成 C2 RepairPatch 设计、离线 Patch Engine、字段候选与 Tool validation、字段漂移注入 fixture、RepairPatch 接入 `sql_audit -> repair_patch -> dsl_compiler -> sql_execute` 主链、前端 repair timeline / Artifact refs 承接、timeline 去重和合并后验收落档。
- 核心边界：LLM 只参与业务语义裁判，不产出可执行 SQL；Patch IR 只 patch QueryGraph/compiler binding，禁止 patch raw SQL；字段级 patch 主体只进入 trace-only/Langfuse/后端日志，用户可见层只显示业务级 repair summary、status 和 refs。
- 验证覆盖：`tests/test_repair_patch_engine.py`、`tests/test_repair_patch_stream.py`、`tests/test_repair_plan_contract.py`、`tests/test_event_envelope.py`、`tests/test_sql_audit.py`、`tests/test_query_plan_compiler.py`、`tests/test_chat.py`，前端 `chat-adapter`、`task-timeline`、`artifact-card`、`MyMessage` 测试，以及 lint/build、`git diff --check`；内部-only E2E 固化 `FIELD_MAPPING_DRIFT -> repair.patch_applied -> answer.completed`。
- 残留风险：C2 合并后已有内部 E2E 和自动化验收，发布级浏览器页面、Langfuse UI 和真实五件套证据在 C3 Workbench 阶段继续补。

## 高价值判断

- Datalogue 当前业务链路不依赖 Redis 保存多轮业务状态；`last_success_task`、`conversation_state.subagent_capsules` 和 query artifacts 的真相在数据库或应用 ArtifactStore 路径，Langfuse/BullMQ Redis key 不能当成业务状态依据。
- 多轮追问不要从当前自然语言残留硬猜 `person`；应依赖 LLM 结构化槽位、上一轮已确认过滤或澄清。
- 数据集上下文压缩优先采用“轻量候选资产目录 + 按需详情补合”，不要一开始把完整字段、SQL、样例行全部塞进 prompt。
- `.env.example` 中要区分“已被 Settings 读取并生效的配置”和“尚未接入的候选项”。
- `localhost:8080` 等地址返回应用层 `Unauthorized` 时，优先判断服务已启动，继续排查认证、代理或路由，不要直接判定服务未启动。

## 最新详细记录

### 2026-06-22 13:04 · 新建对话固定进入最近对话顶部

- 涉及文件：`datalogue-web/src/assistant/ThreadList.jsx`、`datalogue-web/tests/unit/assistant/thread-list-new-conversation.test.jsx`、`datalogue-api/app/api/conversation.py`、`datalogue-api/tests/test_conversation.py`、`.codex/project-memory.md`
- 关键改动：新建对话按钮创建后先刷新 assistant-ui thread list，再跳转到新会话，避免本地运行时把新 thread 追加到列表底部；后端 `/api/conversation` 列表排序增加 `updated_at desc nullslast`、`created_at desc nullslast`、`id desc` 稳定兜底。
- 验证方式：执行 `cd datalogue-web && npm test -- tests/unit/assistant/thread-list-new-conversation.test.jsx`；执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_conversation.py -q`；执行 `cd datalogue-web && npm run lint`、`npm run build`；使用 in-app Browser 打开 `http://localhost:5173/chat`，点击最近对话区域“新对话”，确认跳转 `/chat/4` 后最近对话第一项和 active 项均为“新对话”，控制台无 error/warn。
- 残留风险：本地验证会在开发库里额外创建空“新对话”测试记录；本次未清理用户现有对话数据。

### 2026-06-23 10:56 · SubAgent Planner 金额聚合兜底不再误拒

- 涉及文件：`datalogue-api/app/services/subagent_planning/planner.py`、`datalogue-api/tests/test_subagent_query_planner.py`、`.codex/project-memory.md`
- 关键改动：为规则规划器增加金额/合计类聚合问法识别，例如“总共”“多少钱”“万元”“省了”“节省”；当 LLM 返回空响应或非法 JSON，且候选资产中已有字段/表但没有指标/维度资产时，不再落入 `unsupported/reject`，而是生成 `metric_query + query_graph` 计划并把字段/表作为 selected assets 交给 QueryGraph 继续生成 SQL。
- 验证方式：先执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_query_planner.py::test_rule_based_aggregate_amount_query_uses_field_table_assets -q` 确认新增用例红灯，失败表现为 `unsupported`；修复后再次执行该用例通过；补充 `plan_query` 空 LLM 响应链路测试并通过；执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_query_planner.py -q`，33 条用例通过；执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_run.py -q`，14 条用例通过。
- 残留风险：本次修复聚焦 planner fallback，不直接解决 DeepSeek 空响应本身；如果真实 SQL 仍生成失败，需要继续按 QueryGraph 的最终 DSL/SQL、dataset 12 字段描述和 Langfuse trace 取证。

### 2026-06-23 11:07 · `/chat/stream` 主链路行级日志增强

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_chat.py`、`.codex/project-memory.md`
- 关键改动：新增 `_chat_stream_log_summary()` 和 `_log_chat_stream_checkpoint()`，统一 `/chat/stream` 关键节点日志格式；在请求入口、多轮包装、会话准备、trace context、gateway 分类、LeadAgent 路由、早退分支、SubAgent 候选资产/query plan/result、fanout、Graph 完成、助手消息落库和 final payload 输出前增加 `chat.stream.<checkpoint>` 行级日志，日志摘要包含 `entry_route`、`entry_reason`、`query_plan_type`、`planner_source`、`fallback_reason`、`has_sql`、`sql_count`、`has_error`、`answer_len` 等字段。
- 验证方式：先执行 `cd datalogue-api && python3 -m pytest tests/test_chat.py::TestChatAPI::test_chat_stream_log_summary_extracts_debug_fields -q` 确认新增 helper 测试红灯，失败原因为 `_chat_stream_log_summary` 不存在；实现后再次执行该用例通过；执行 `cd datalogue-api && python3 -m ruff check app/api/chat.py tests/test_chat.py` 通过。
- 残留风险：本次验证覆盖日志摘要 helper 和静态检查，未启动本地 `/chat` 页面做真实 SSE 日志回放；如果需要排查某个具体问题，仍应结合后端日志、DevTools Network final payload 和 Langfuse trace 三方对齐。

### 2026-06-23 11:07 · SubAgent 规则规划器中性命名与接口注释

- 涉及文件：`datalogue-api/app/services/subagent_planning/planner.py`、`datalogue-api/app/services/subagent_planning/__init__.py`、`datalogue-api/tests/test_subagent_query_planner.py`、`docs/上下文入口.md`、`docs/superpowers/plans/2026-06-15-subagent-query-planning.md`、`docs/superpowers/plans/2026-06-17-subagent-planner-asset-detail-loop.md`、`.codex/project-memory.md`
- 关键改动：将 `build_fallback_query_plan` 更名为 `build_rule_based_query_plan`，公共导出和测试引用同步更新；补全规则规划器、`plan_query()`、`plan_query_with_detail_context()` 的接口 docstring，明确 `fallback_reason is None` 是 LLM 前确定性预判，有值时才是 LLM 失败后的规则兜底。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_query_planner.py -q`；执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_run.py -q`；执行 `cd datalogue-api && .venv/bin/python -m py_compile app/services/subagent_planning/planner.py app/services/subagent_planning/__init__.py`；执行 `rg -n "build_fallback_query_plan" datalogue-api/app datalogue-api/tests docs` 确认代码与当前项目文档入口无旧接口名；执行 `git diff --check -- datalogue-api/app/services/subagent_planning/planner.py datalogue-api/app/services/subagent_planning/__init__.py datalogue-api/tests/test_subagent_query_planner.py docs/上下文入口.md docs/superpowers/plans/2026-06-15-subagent-query-planning.md docs/superpowers/plans/2026-06-17-subagent-planner-asset-detail-loop.md .codex/project-memory.md`。
- 残留风险：本次是命名和注释澄清，不改变 planner 的执行策略；如果仓库外部代码仍直接 import 旧函数名，需要同步迁移。

### 2026-06-23 11:17 · `/chat/stream` 日志链路代码注释增强

- 涉及文件：`datalogue-api/app/api/chat.py`、`.codex/project-memory.md`
- 关键改动：围绕 `_chat_stream_log_summary()`、`_log_chat_stream_checkpoint()` 和 `/chat/stream` 主链路 checkpoint 增加行级中文注释；注释解释各日志点对应的链路事实，例如请求入口、会话落库、trace 创建、gateway 分类、LeadAgent 路由、早退分支、SubAgent 候选资产/query plan/result、Graph 完成、answer 兜底、final payload 和多轮状态写回触发点。
- 验证方式：执行 `cd datalogue-api && python3 -m py_compile app/api/chat.py`；执行 `cd datalogue-api && python3 -m ruff check app/api/chat.py`。
- 残留风险：本次仅增强代码阅读注释，不改变运行逻辑；仍未启动本地 `/chat` 页面回放真实 SSE 日志。

### 2026-06-23 11:24 · 项目关键代码注释规范与记忆压缩规则固化

- 涉及文件：`AGENTS.md`、`datalogue-api/AGENTS.md`、`docs/上下文入口.md`、`.codex/project-memory.md`、`datalogue-api/app/services/lead_agent.py`、`datalogue-api/app/services/conversation_store.py`、`datalogue-api/app/services/subagent_planning/planner.py`、`datalogue-api/app/services/subagent_planning/contracts.py`、`datalogue-api/app/api/conversation.py`、`datalogue-web/src/assistant/ThreadList.jsx`
- 关键改动：固化“新增或修改关键代码时补充中文关键行级注释”的长期规则；固化项目记忆最新详细记录超过 10 条时压缩、历史压缩条目超过 10 条时深度压缩的规则；把较早 3 条详细记录压缩进历史区，并把 2026-06-05 至 2026-06-14 的历史压缩条目深度合并为主题摘要；在 LeadAgent ToolPolicy/快路径、多轮状态写入与澄清恢复、SubAgent 规则 planner、QueryPlan 契约校验、对话列表排序和新建会话刷新顺序处补充关键注释。
- 验证方式：执行 `cd datalogue-api && python3 -m py_compile app/services/lead_agent.py app/services/conversation_store.py app/services/subagent_planning/planner.py app/services/subagent_planning/contracts.py app/api/conversation.py`；执行 `cd datalogue-api && python3 -m ruff check app/services/lead_agent.py app/services/conversation_store.py app/services/subagent_planning/planner.py app/services/subagent_planning/contracts.py app/api/conversation.py`；执行 `cd datalogue-web && npm run lint`；执行 `git diff --check -- AGENTS.md datalogue-api/AGENTS.md docs/上下文入口.md .codex/project-memory.md datalogue-api/app/services/lead_agent.py datalogue-api/app/services/conversation_store.py datalogue-api/app/services/subagent_planning/planner.py datalogue-api/app/services/subagent_planning/contracts.py datalogue-api/app/api/conversation.py datalogue-web/src/assistant/ThreadList.jsx`。
- 残留风险：本次是注释和规则治理，不改变业务逻辑；“整个项目”按当前高风险核心链路补关键注释，未对所有历史文件做机械扫注释。

### 2026-06-23 11:36 · 关键注释调整为调用行/操作行行尾注释

- 涉及文件：`AGENTS.md`、`datalogue-api/AGENTS.md`、`docs/上下文入口.md`、`.codex/project-memory.md`、`datalogue-api/app/api/chat.py`、`datalogue-api/app/services/lead_agent.py`、`datalogue-api/app/services/conversation_store.py`、`datalogue-api/app/services/subagent_planning/planner.py`、`datalogue-api/app/services/subagent_planning/contracts.py`、`datalogue-api/app/api/conversation.py`、`datalogue-web/src/assistant/ThreadList.jsx`
- 关键改动：按“方法调用或关键操作所在行增加注释”的口径，调整前一轮偏前置的说明性注释；在 `_log_chat_stream_checkpoint()`、`tracer.create_trace_context()`、`build_query_result_artifact()`、`store.append_completed_turn()`、`_persist_completed_turn()`、`store.release_turn_lock()`、`QueryPlan(...)`、`thread_state.update()`、`reloadThreads()` 等关键调用或操作行增加短行尾注释；同步更新 AGENTS、上下文入口和项目记忆规则，明确以后优先使用调用行/操作行行尾注释。
- 验证方式：执行 `cd datalogue-api && python3 -m py_compile app/api/chat.py app/services/lead_agent.py app/services/conversation_store.py app/services/subagent_planning/planner.py app/services/subagent_planning/contracts.py app/api/conversation.py`；执行 `cd datalogue-api && python3 -m ruff check app/api/chat.py app/services/lead_agent.py app/services/conversation_store.py app/services/subagent_planning/planner.py app/services/subagent_planning/contracts.py app/api/conversation.py`；执行 `cd datalogue-web && npm run lint`，0 error、15 个既有 warning；执行 `git diff --check -- datalogue-api/app/api/chat.py datalogue-api/app/services/lead_agent.py datalogue-api/app/services/conversation_store.py datalogue-api/app/services/subagent_planning/planner.py datalogue-api/app/services/subagent_planning/contracts.py datalogue-api/app/api/conversation.py datalogue-web/src/assistant/ThreadList.jsx`。
- 残留风险：本次仍是阅读性注释和规则治理，不改变业务逻辑；未对项目所有历史文件逐一扫描，只覆盖当前最关键且近期已改动的问数主链路。

### 2026-06-23 11:48 · SubAgent Planner 打印 LLM 原始响应诊断

- 涉及文件：`datalogue-api/app/services/subagent_planning/planner.py`、`datalogue-api/tests/test_subagent_query_planner.py`、`.codex/project-memory.md`
- 关键改动：新增 `_planner_response_debug()`，在 `subagent_query_planner` 普通规划和 detail loop 的每次 LLM 成功返回后立即打印 DEBUG 级 `raw_response_debug`，并在响应校验失败 warning 中继续追加同一诊断字段；诊断内容包含 response 类型、content 类型、response `repr`、`response_metadata`、`usage_metadata` 和 `additional_kwargs`，用于排查 `content=""` 但服务端返回对象仍有 finish reason、request id 或 token usage 的场景。
- 验证方式：先执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_query_planner.py::test_plan_query_logs_raw_llm_response_when_validation_fails -q` 确认新增用例红灯，失败表现为日志缺少 `raw_response_debug=`；再执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_query_planner.py::test_plan_query_debug_logs_raw_llm_response_before_parsing -q` 确认 DEBUG 原始响应日志缺失；实现后两个用例通过；执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_query_planner.py -q`，35 条用例通过；执行 `cd datalogue-api && .venv/bin/python -m py_compile app/services/subagent_planning/planner.py`。
- 残留风险：日志只做截断后的诊断摘要，不会改变 LLM 返回内容或 fallback 行为；DEBUG 日志会增加本地排障输出量，问题定位完成后可降级为配置开关或移除。

### 2026-06-23 12:41 · 新对话本地草稿可见且未发送不持久化

- 涉及文件：`datalogue-web/src/assistant/ThreadList.jsx`、`datalogue-web/tests/unit/assistant/thread-list-new-conversation.test.jsx`、`.codex/project-memory.md`
- 关键改动：新对话按钮不再调用 `createConversation`，改为只执行 `aui.threads().switchToNewThread()` 并导航回 `/chat`；新增 `DraftThreadListItem`，当 assistant-ui 存在 `newThreadId` 时在“最近对话”顶部显示本地“新对话”草稿并按 `mainThreadId` 高亮；首条消息发送时仍由 `thread-list-adapter.initialize()` 创建后端 conversation；按钮保留创建中禁用保护，避免连续点击造成 runtime 状态抖动。
- 验证方式：先执行 `cd datalogue-web && npm test -- tests/unit/assistant/thread-list-new-conversation.test.jsx` 确认组件层用例红灯，失败表现为找不到 `thread-list-draft-item`；实现后再次执行该命令，4 条用例通过；执行 `cd datalogue-web && npm run lint`，0 error、15 个既有 warning；执行 `cd datalogue-web && npm run build` 通过；调用 `GET /api/conversation?archived=false` 记录点击前数量为 4，使用 in-app Browser 打开 `http://localhost:5173/chat/4` 后点击 `.thread-list-new` 且不发送消息，URL 回到 `/chat`，左栏第 0 项为 active draft“新对话”，再次请求后端列表数量仍为 4。
- 残留风险：本次只验证“未发送不新增数据库会话”和本地草稿可见；未实际发送一条新消息走 LLM 全链路验证创建后的标题刷新和列表排序。

### 2026-06-30 10:18 · C3 AgentScope Workbench 产品化设计落档

- 涉及文件：`docs/architecture/C3-AgentScope-Workbench-产品化设计.md`、`docs/superpowers/specs/2026-06-30-c3-agentscope-workbench-design.md`、`.codex/project-memory.md`
- 关键改动：将 C3 脑暴决策正式落为架构设计和 superpowers spec；C3 主线定为 BI 工作台产品化，入口采用 Chat 右侧 Workbench Panel + 隐藏 `/workbench/:threadId/:artifactRef?` 路由；新会话以 AgentScope-compatible `session/message/event/ref` mirror 为真相源，统一 thread id 为 `as_* / conv_*`；后端提供 Workbench View Model API，支持普通视图、管理员诊断抽屉、Lease / timeout、只读 action 和受控 retry；旧会话只做只读回放，转新会话时仅带业务级摘要和 refs。
- 验证方式：执行两份 C3 文档占位词扫描，无命中；执行关键决策扫描，确认 BI 工作台产品化、Session / Message Bridge、mirror 四表、统一 thread id、Lease、View Model、受控 retry、管理员诊断抽屉和旧会话策略均已写入两份文档；执行 `git diff --check` 通过。
- 残留风险：本次仅完成 C3 设计文档，不实现代码；下一步需要按设计生成开发计划，并把 P0 拆成数据库迁移、后端 API、前端 Panel、retry action 和验收用例等可执行 PR。

### 2026-06-30 11:08 · C3-P0 AgentScope Workbench 实施计划

- 涉及文件：`docs/superpowers/plans/2026-06-30-c3-agentscope-workbench-p0.md`、`.codex/project-memory.md`
- 关键改动：按 superpowers implementation plan 格式把 C3-P0 拆成 6 个可执行 PR：AgentScope mirror 四表和 thread resolver、Chat Session Bridge、Workbench View Model API、受控 retry 与 lease recovery、Chat 右侧 Workbench Panel、双主路径验收加固；计划明确 `as_* / conv_*` 线程规则、AgentScope 管会话消息而 Datalogue 主链管 BI 执行的边界、用户可见层禁止 SQL/schema/raw rows/query_plan/field_patch 的安全约束，以及每个 PR 的测试文件、验证命令、提交范围和 stop condition。
- 验证方式：执行 C3-P0 plan 空白项和简写扫描，无命中；检查计划包含 writing-plans 要求的 agentic worker 提示、Goal、Architecture、Tech Stack、checkbox 任务、PR stack、验证命令和 merge plan。
- 残留风险：本次只完成实施计划，不修改业务代码；下一步应从 PR1 `c3-p0-01-agentscope-mirror-storage` 开始按 TDD 实现数据库迁移、模型、schema、thread resolver 和 mirror service。

### 2026-06-30 11:49 · C3-P0 PR1 AgentScope Mirror Storage

- 涉及文件：`datalogue-api/alembic/versions/p1q2r3s4t5u6_add_agentscope_workbench_mirror.py`、`datalogue-api/app/models/agentscope_workbench.py`、`datalogue-api/app/models/__init__.py`、`datalogue-api/app/schemas/agentscope_workbench.py`、`datalogue-api/app/services/agentscope_thread_resolver.py`、`datalogue-api/app/services/agentscope_mirror.py`、`datalogue-api/tests/test_agentscope_mirror_models.py`、`datalogue-api/tests/test_agentscope_thread_resolver.py`、`.codex/project-memory.md`
- 关键改动：按 C3-P0 PR1 计划新增 AgentScope Workbench 本地 mirror 四表契约，包含 `agentscope_session/message/event/ref` Alembic 迁移、SQLAlchemy 模型导出、线程解析 schema/service 和 mirror 写入服务；`as_*` 作为新会话真相源，`conv_*` 作为历史只读线程引用，assistant running message 写入 lease，到期查询只返回仍处于 running 的消息；ref 关系表增加 `(thread_id, message_id, ref_type, ref_value, relation)` 唯一约束，避免同一消息重复挂载相同 artifact/checkpoint/trace ref。
- 验证方式：先执行 `cd datalogue-api && python3 -m pytest tests/test_agentscope_mirror_models.py tests/test_agentscope_thread_resolver.py -q` 确认 RED，失败为 `app.models.agentscope_workbench` 和 `app.schemas.agentscope_workbench` 缺失；实现并补齐 review 安全边界后同一命令 13 条通过；执行 `cd datalogue-api && python3 -m py_compile app/models/agentscope_workbench.py app/schemas/agentscope_workbench.py app/services/agentscope_thread_resolver.py app/services/agentscope_mirror.py alembic/versions/p1q2r3s4t5u6_add_agentscope_workbench_mirror.py` 通过。
- 残留风险：本次只完成 C3 mirror 存储基础，不接入 `/chat/stream`、Workbench View Model API、受控 retry 或前端 Panel；这些继续归 PR2-PR6。

### 2026-06-30 12:18 · C3-P0 PR2 Chat Session Bridge

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/app/schemas/chat.py`、`datalogue-api/app/services/agentscope_chat_bridge.py`、`datalogue-api/app/services/agentscope_event_projection.py`、`datalogue-api/app/services/agentscope_mirror.py`、`datalogue-api/tests/test_agentscope_chat_bridge.py`、`datalogue-api/tests/test_agentscope_event_projection.py`、`.codex/project-memory.md`
- 关键改动：把 `/chat/stream` 接入 AgentScope mirror，但不替换 Datalogue 主链；`ChatRequest` 增加 `thread_id`，新主路径创建 `as_*` session/user message/assistant running message，普通请求即使携带 `conversation_id` 也创建 `as_*` mirror 并记录 `legacy_conversation_id`，只有显式 `thread_id=conv_*` 才按旧会话只读；stream final 会把 `thread_id` 回写给前端，event envelope 投影为 AgentScope event/ref，`result_ref/report_ref/subagent_tool_results` 统一规范化为 `primary_ref/related_refs` 后写入 `agentscope_ref`。
- 安全与生命周期：AgentScope message summary、final payload 和 event payload 均阻断 SQL、schema、raw rows、query_plan、field patch 以及 `psycopg2/SQLAlchemy/UndefinedColumn` 等内部错误文本；begin bridge 不再吞异常伪装 `conv_0`；单轮异常、取消、无 final、`error.blocked` final、多轮 `ConversationState` 写回失败等路径都能把 assistant message 收口为 failed/interrupted/completed，mirror 层增加终态幂等保护，避免 complete 后被 finally 覆盖。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_agentscope_chat_bridge.py tests/test_agentscope_event_projection.py tests/test_agentscope_mirror_models.py tests/test_agentscope_thread_resolver.py tests/test_chat.py -q`，151 条通过；执行 `cd datalogue-api && python3 -m py_compile app/api/chat.py app/schemas/chat.py app/services/agentscope_chat_bridge.py app/services/agentscope_event_projection.py app/services/agentscope_mirror.py tests/test_agentscope_chat_bridge.py tests/test_agentscope_event_projection.py` 通过；执行 `git diff --check` 通过。
- 残留风险：PR2 只完成 Chat Session Bridge 和 mirror 生命周期；Workbench View Model API、受控 retry / lease recovery、Chat 右侧 Workbench Panel 和双主路径真实验收仍按 C3-P0 PR3-PR6 继续。

### 2026-06-30 12:57 · C3-P0 PR3 Workbench View Model API

- 涉及文件：`datalogue-api/app/api/workbench.py`、`datalogue-api/app/api/__init__.py`、`datalogue-api/app/api/conversation.py`、`datalogue-api/app/schemas/agentscope_workbench.py`、`datalogue-api/app/services/workbench_view_model.py`、`datalogue-api/tests/test_workbench_view_api.py`、`.codex/project-memory.md`
- 关键改动：新增 `/api/workbench/thread/{thread_id}` 和 `/api/workbench/artifact/{artifact_ref}` 后端 View Model API；`as_*` 从 AgentScope mirror 读取 session/message/event/ref，`conv_*` 从旧 `conversation/message` 只读回放；线程视图统一返回 messages、timeline、primary artifact ref、related refs、available actions 和 legacy notice；artifact 视图只接受 `artifact:<uuid>` 并返回业务级 `preview_payload`，把 `sql_result` 映射为用户可见的 `query_result`，不返回 `content_json/content_text`、raw rows、schema、SQL 或 RepairPlan patch 主体。
- 兼容修复：历史 conversation 回放的 ArtifactCard ref sanitizer 兼容字符串 ref 与 `{ref_id, ref_type}` 对象 ref；旧会话缺少 ArtifactCard 时仍不迁移、不回填、不伪造卡片，只保留原消息展示。
- 验证方式：先执行 `cd datalogue-api && python3 -m pytest tests/test_workbench_view_api.py -q` 确认 RED，失败为 `/api/workbench` 路由缺失；实现后该命令 5 条通过；执行 `cd datalogue-api && python3 -m pytest tests/test_workbench_view_api.py tests/test_artifact_api.py tests/test_legacy_conversation_replay.py tests/test_conversation.py -q`，19 条通过；执行 `cd datalogue-api && python3 -m pytest tests/test_agentscope_chat_bridge.py tests/test_agentscope_event_projection.py tests/test_agentscope_mirror_models.py tests/test_agentscope_thread_resolver.py tests/test_chat.py tests/test_workbench_view_api.py -q`，156 条通过；执行 `cd datalogue-api && python3 -m py_compile app/schemas/agentscope_workbench.py app/services/workbench_view_model.py app/api/workbench.py app/api/conversation.py app/api/__init__.py` 和 `git diff --check` 均通过。
- 残留风险：PR3 只完成后端 View Model API；受控 retry / lease recovery、Chat 右侧 Workbench Panel 和双主路径页面验收仍按 C3-P0 PR4-PR6 继续。

### 2026-06-30 13:22 · C3-P0 PR4 Controlled Retry And Lease Recovery

- 涉及文件：`datalogue-api/app/api/workbench.py`、`datalogue-api/app/schemas/agentscope_workbench.py`、`datalogue-api/app/services/workbench_actions.py`、`datalogue-api/tests/test_workbench_retry_actions.py`、`datalogue-api/tests/test_agentscope_lease_recovery.py`、`.codex/project-memory.md`
- 关键改动：新增 Workbench 受控 retry 契约和动作服务；`POST /api/workbench/actions/retry` 只接受 `thread_id/message_id/checkpoint_ref/selected_action`，拒绝 SQL/schema/raw rows/query_plan/field_patch 等执行面 payload；对 failed/interrupted assistant message 创建新的 AgentScope running message、挂载 checkpoint ref，并记录 `workbench.retry_requested` 业务事件；legacy `conv_*` 返回 `accepted=False` 和只读禁用原因，不启动任何重跑。
- Lease recovery：新增 `run_lease_recovery`，把超过 lease 的 running assistant message 收口为 `interrupted`，写入业务级中断提示、`checkpoint_ref` 和 `recovery_status`，未过期 running message 保持不变；缺少 checkpoint 的过期消息会生成 thread/message 级 fallback checkpoint ref，便于后续受控 retry。
- 验证方式：先执行 `cd datalogue-api && python3 -m pytest tests/test_workbench_retry_actions.py tests/test_agentscope_lease_recovery.py -q` 确认 RED，失败为 `app.services.workbench_actions` 缺失；实现后该命令 6 条通过；执行 `cd datalogue-api && python3 -m pytest tests/test_workbench_retry_actions.py tests/test_agentscope_lease_recovery.py tests/test_workbench_view_api.py -q`，11 条通过；执行 `cd datalogue-api && python3 -m pytest tests/test_agentscope_chat_bridge.py tests/test_agentscope_event_projection.py tests/test_agentscope_mirror_models.py tests/test_agentscope_thread_resolver.py tests/test_workbench_view_api.py tests/test_workbench_retry_actions.py tests/test_agentscope_lease_recovery.py -q`，42 条通过；执行 `cd datalogue-api && python3 -m py_compile app/schemas/agentscope_workbench.py app/services/workbench_actions.py app/api/workbench.py` 通过。
- 残留风险：PR4 只完成后端 retry/lease 动作层；真实 retry 继续依赖后续 chat/checkpoint 流程承接，Chat 右侧 Workbench Panel、隐藏 route 和双主路径 E2E 仍按 C3-P0 PR5-PR6 继续。

### 2026-06-30 13:35 · C3-P0 PR5 Chat Workbench Panel

- 涉及文件：`datalogue-web/src/App.jsx`、`datalogue-web/src/assistant/workbench-api.js`、`datalogue-web/src/assistant/workbench-api.test.js`、`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/chat-adapter.test.js`、`datalogue-web/src/assistant/thread-list-adapter.js`、`datalogue-web/src/components/workbench-panel.jsx`、`datalogue-web/src/components/workbench-panel.test.jsx`、`datalogue-web/src/components/workbench-route.jsx`、`datalogue-web/src/components/workbench-route.test.jsx`、`datalogue-web/src/components/chat-page.jsx`、`datalogue-web/src/components/chat-page.test.jsx`、`datalogue-web/src/styles.css`、`.codex/project-memory.md`
- 关键改动：新增 Chat 右侧 Workbench Panel 和隐藏 `/workbench/:threadId/:artifactRef?` 路由；前端 adapter 支持 `as_* / conv_*` 线程规范化、Workbench View Model 读取、artifact 详情读取和受控 retry 请求白名单；`chat-adapter` 在请求中携带 `thread_id` 并从 final payload 回收 `as_*` 真相源线程；`thread-list-adapter` 支持 `as_*` 历史会话从 Workbench View Model 回放，`conv_*` 继续走旧会话只读路径；Panel 只展示业务摘要、timeline、refs、Artifact 摘要和受控 action 禁用原因，不展示 SQL/schema/raw rows/query_plan/field_patch。
- 前端形态：现有 Chat 入口直接挂载右侧 Panel，不新建独立 BI 工作台页面；隐藏 route 只作为后续独立 Workbench 页面升级出口；移动端 Panel 自动落到消息流下方，桌面固定右侧工作区。
- 验证方式：先执行 `cd datalogue-web && npm run test -- src/assistant/workbench-api.test.js src/components/workbench-panel.test.jsx src/components/workbench-route.test.jsx src/components/chat-page.test.jsx` 确认 RED，失败为 Workbench API、Panel、Route 和 `resolveWorkbenchThreadId` 未实现；实现后执行 `cd datalogue-web && npm run test -- src/assistant/workbench-api.test.js src/components/workbench-panel.test.jsx src/components/workbench-route.test.jsx src/assistant/chat-adapter.test.js src/components/chat-page.test.jsx`，31 条通过；执行 `cd datalogue-web && npm run lint`，0 error、15 个既有 warning；执行 `cd datalogue-web && npm run build` 通过，仅保留既有 chunk size warning；执行 `git diff --check` 通过。
- 残留风险：PR5 只完成 Chat 侧 Workbench Panel 和隐藏 route；PR6 仍需做双主路径验收加固，包括真实 `as_*` 页面回放、`conv_*` 旧会话只读回放、Artifact refs、受控 retry 禁用/发起路径和用户可见层脱敏扫描。

### 2026-06-30 13:55 · C3-P0 PR6 Acceptance Hardening

- 涉及文件：`datalogue-api/app/schemas/bi_workbench.py`、`datalogue-api/tests/test_c3_workbench_acceptance.py`、`datalogue-web/src/assistant/thread-list-adapter.test.js`、`datalogue-web/src/components/chat-page.test.jsx`、`docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md`、`.codex/project-memory.md`
- 关键改动：新增 C3 Workbench 双主路径验收测试；后端覆盖新 `as_*` Chat stream mirror 到 Workbench View Model、lease interrupted + 受控 retry、legacy `conv_*` 只读回放三条路径；前端覆盖 `datalogue:thread-resolved` 后本地 draft thread remap 到 `as_*`、`as_*` Workbench View Model 回放、artifact refs 映射和 Chat route 对 Workbench Panel source 的优先级。
- 契约补洞：PR6 RED 暴露 `agentscope_event_projection` 和 C3 计划已使用 `task.started`，但 `DatalogueEventType` 未纳入该事件；本次将 `task.started` 加入统一 event envelope schema，保证新会话工作台 timeline 可从任务开始事件建立。
- 验收记录：新增 `docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md`，记录路径 A/B/C 的 thread、task、trace、artifact/checkpoint/ref 证据，以及页面、SSE、mirror、Langfuse 和残留风险分层状态；明确本次是自动化 acceptance hardening，未伪造成真实浏览器/Langfuse UI 五件套。
- 验证方式：先执行 `cd datalogue-api && python3 -m pytest tests/test_c3_workbench_acceptance.py -q` 确认 RED，失败为 `task.started` 不在 `DatalogueEventType`；修复后同一命令 3 条通过；执行 `cd datalogue-web && npm run test -- src/assistant/thread-list-adapter.test.js src/components/chat-page.test.jsx src/components/workbench-panel.test.jsx src/assistant/workbench-api.test.js`，22 条通过。
- 残留风险：PR6 不启动真实浏览器或 Langfuse UI；retry action 仍只创建新的 running message 并记录 checkpoint/event，不在本阶段直接驱动 Datalogue 主链重跑。

### 2026-06-30 14:10 · C3-P0 真实浏览器 E2E 补证与 Workbench Panel 切换修复

- 涉及文件：`datalogue-api/app/services/agentscope_event_projection.py`、`datalogue-api/tests/test_agentscope_event_projection.py`、`datalogue-web/src/components/chat-page.jsx`、`datalogue-web/src/components/chat-page.test.jsx`、`docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md`、`.codex/project-memory.md`
- 关键改动：真实浏览器 E2E 暴露两处 C3-P0 缺口并完成修复：一是 `error.blocked` 候选事件投影时 `bound_schema_version` 触发 AgentScope mirror 泄露拦截，改为通用 user-visible payload 递归裁剪内部键后再 fail-closed；二是 `/chat` 候选确认后第二轮 `as_*` mirror 没有接管右侧 Workbench Panel，新增 `shouldAcceptResolvedWorkbenchThread()`，无显式 route 时接受最新 AgentScope thread，显式 `/chat/:id` 继续保持 route source 优先。
- 真实验收：本地 API `127.0.0.1:8000` 和前端 `127.0.0.1:5173` 下，用真实问题“查询杨凯 2024 年工作日志”完成候选确认到成功问数；生成 `conversation_id=31`、`thread_id=as_60b44ad7-cd95-4b2e-a765-c2e82e189c2d`、`trace_id=22b163778f0bbdb422c691997ae6eb60`、`primary_ref=artifact:e1c094ea0d2242a681345f70a2404284`、`report_ref=artifact:5d40ec7b33b04ab199b8d3dc3b46f53f`、`checkpoint_ref=checkpoint://conv-31-msg-74/query_context_ready`；主 Chat 和右侧 Workbench Panel 均显示 completed，隐藏 `/workbench/:threadId/:artifactRef` 路由可打开同一产物，`/chat/25` 旧会话只读回放正常。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_agentscope_event_projection.py tests/test_c3_workbench_acceptance.py tests/test_agentscope_chat_bridge.py tests/test_workbench_view_api.py tests/test_workbench_retry_actions.py -q`，31 条通过；执行 `cd datalogue-web && npm run test -- src/components/chat-page.test.jsx src/assistant/chat-adapter.test.js src/assistant/thread-list-adapter.test.js src/components/workbench-panel.test.jsx`，34 条通过；真实浏览器页面扫描未命中 `SELECT/query_plan/raw_result/schema_summary/field_patch`，console error/warn 为空。
- 残留风险：本次没有打开 Langfuse UI 做人工核对；C3-P1 仍需把 Workbench 受控 retry 从“创建 running message + checkpoint event”推进到真实主链恢复。

### 2026-06-30 14:22 · C3-P1 PR1 Workbench Retry 主链恢复入口

- 涉及文件：`datalogue-api/app/schemas/agentscope_workbench.py`、`datalogue-api/app/services/workbench_actions.py`、`datalogue-api/tests/test_workbench_retry_actions.py`、`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/chat-adapter.test.js`、`datalogue-web/src/components/chat-page.jsx`、`datalogue-web/src/components/workbench-panel.jsx`、`datalogue-web/src/components/workbench-panel.test.jsx`、`docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md`、`.codex/project-memory.md`
- 关键改动：C3-P1 PR1 将 Workbench 受控 retry 从“只创建 running mirror message”推进到 Chat 主链恢复入口；后端新增业务级 `WorkbenchRetryRunRequest`，`request_controlled_retry()` 在 accepted response 中返回 `question/conversation_id/thread_id/dataset_id/retry_checkpoint_ref/display_text`，但不携带 SQL/schema/raw rows/query_plan/field_patch；前端 WorkbenchPanel 接收 `run_request` 后回调 ChatPage，ChatPage 使用 assistant-ui `thread.append()` 发起普通用户消息，chat-adapter 一次性消费 `window.__DATALOGUE_PENDING_WORKBENCH_RETRY__` 并把 `retry_checkpoint_ref` 交给既有 `/chat/stream` checkpoint restore 链路。
- 验证方式：先执行后端和前端定向测试确认 RED，失败点分别为 `run_request` 缺失、Panel 未触发 `onRetryRun`、chat-adapter 未发送 pending retry；实现后执行 `cd datalogue-api && python3 -m pytest tests/test_workbench_retry_actions.py tests/test_retry_checkpoint.py tests/test_c3_workbench_acceptance.py tests/test_workbench_view_api.py -q`，16 条通过；执行 `cd datalogue-web && npm run test -- src/components/workbench-panel.test.jsx src/assistant/chat-adapter.test.js src/components/chat-page.test.jsx`，34 条通过；执行 `cd datalogue-web && npm run lint`，0 error、15 个既有 warning；执行 `cd datalogue-web && npm run build` 通过；执行 `git diff --check` 通过。
- 残留风险：本次完成 retry action 到 `/chat/stream` 的主链恢复入口，不伪造成真实浏览器 retry 成功；下一步需要补真实页面 retry 场景或内部 harness，验证 `retry.checkpoint_restored -> answer.completed` 与 Workbench mirror 同一 thread/trace/ref 一致。
