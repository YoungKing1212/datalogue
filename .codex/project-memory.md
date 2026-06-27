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

### 2026-06-26 16:44 · BI_SOUL 内部契约与外部入口同步校验

- 涉及文件：`datalogue-api/app/contracts/BI_SOUL.md`、`datalogue-api/app/services/soul_contract_sync.py`、`datalogue-api/tests/test_bi_soul_contract.py`、`hermes-skills/datalogue/SOUL.md`、`.omx/plans/DAT-6-BI_SOUL-内部契约同步计划.md`、`.codex/project-memory.md`
- 关键改动：新增 BI 不可越界内部 source of truth，明确 LeadAgent 不看字段级 schema 明细、外层 Agent 只能调用 `ask_bi`、LLM 不直接生成可执行 SQL、raw SQL/raw result/capsule/trace 主体属于 `control_plane`；新增同步服务抽取并规范化 `BI_SOUL_SYNC` 块，校验 Hermes SOUL 与内部契约一致，并为未来 AgentScopeShellAdapter 渲染只允许 `ask_bi` 的 policy；Hermes SOUL 嵌入同一同步块。
- 验证方式：先执行 `cd datalogue-api && python3 -m pytest tests/test_bi_soul_contract.py -q` 确认红灯，失败为 `ModuleNotFoundError: app.services.soul_contract_sync`；实现后执行 `cd datalogue-api && python3 -m pytest tests/test_bi_soul_contract.py -q`，3 条用例通过；执行 `cd datalogue-api && python3 -m py_compile app/services/soul_contract_sync.py` 通过；创建被 `.gitignore` 忽略的本地 `.venv` 链接后执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_soul_contract.py -q`，3 条用例通过、仅有既有依赖弃用告警。
- 残留风险：当前仓库尚无 `AgentScopeShellAdapter` 实现，本次只提供可注入的 policy 文本和同步校验；未实现 `ask_bi`、未新增公开 API、未接管 BI 主链 runtime。

### 2026-06-26 17:02 · LeadAgent Capability Router 路由收窄

- 涉及文件：`datalogue-api/app/services/dataset_router.py`、`datalogue-api/app/services/lead_agent_routing.py`、`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_lead_agent_capability_router.py`、`.omx/plans/DAT-13-leadagent-capability-router.md`、`.codex/project-memory.md`
- 关键改动：新增 DAT-13 计划文件；`dataset_router` 内部改用 Manifest capability 摘要打分，但对外候选只暴露 `dataset_id/dataset_name/reason/confidence/requires_confirmation`；低置信和多数据集近分均标记需确认且不 dispatch；`lead_agent_routing` 在未确认数据集时阻断指标/明细问法直接进入 `query_graph`；`chat` 阻断提示改读 `confidence/reason`。
- 验证方式：先执行 `python3 -m pytest tests/test_lead_agent_capability_router.py -q` 确认旧候选字段导致 3 条红灯，再实现后通过；最终执行 `python3 -m pytest tests/test_lead_agent_capability_router.py tests/test_lead_agent_routing.py tests/test_lead_agent_tools.py -q`，52 条通过；执行 `python3 -m ruff check app/services/dataset_router.py app/services/lead_agent_routing.py app/api/chat.py tests/test_lead_agent_capability_router.py` 通过；执行 `python3 -m py_compile app/services/dataset_router.py app/services/lead_agent_routing.py app/api/chat.py` 通过。
- 残留风险：本次覆盖后端路由与阻断提示，未启动真实 `/chat/stream` SSE 回放；pytest 仍输出 starlette/pydantic/pytest-asyncio 既有弃用 warning。

### 2026-06-26 17:10 · QueryGraph Compiler 与当前数据源方言门禁

- 涉及文件：`datalogue-api/app/services/query_plan_compiler.py`、`datalogue-api/app/services/sql_dialect_adapter.py`、`datalogue-api/app/services/dataset_subagent.py`、`datalogue-api/app/services/subagent_planning/contracts.py`、`datalogue-api/app/services/subagent_planning/sql_context.py`、`datalogue-api/app/services/subagent_planning/__init__.py`、`datalogue-api/app/graph/nodes.py`、`datalogue-api/app/graph/state.py`、`datalogue-api/tests/test_query_plan_compiler.py`、`datalogue-api/tests/test_sql_dialect_adapter.py`、`datalogue-api/tests/test_subagent_run.py`
- 关键改动：新增 QueryPlan 工具编译器与方言适配外壳，编译产物统一输出 `execution_source=tool_compiler`；SQL 执行来源拒绝 `llm_sql/direct_sql/raw_sql/sql` 等模型 SQL 字段；运行期只允许当前选中数据源 dialect，QueryPlan 目标方言与当前数据源不一致或当前数据源方言未启用时返回 `DIALECT_UNSUPPORTED_FOR_CURRENT_DATASOURCE`；SubAgent 初始态写入 `query_plan_compilation`、`control_plane`、`query_artifact`，Graph 在编译产物可用时跳过 DSL LLM SQL 生成，执行层只透传工具编译 SQL。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_query_plan_compiler.py tests/test_sql_dialect_adapter.py tests/test_subagent_run.py -q` 通过；执行 `cd datalogue-api && python3 -m py_compile app/services/query_plan_compiler.py app/services/sql_dialect_adapter.py app/services/dataset_subagent.py app/graph/nodes.py app/graph/state.py` 通过；执行 `git diff --check` 通过。
- 残留风险：第一阶段编译器只覆盖明细字段/表资产到 SELECT 的保守编译，不覆盖复杂指标表达式、JOIN 拓扑和全部数据源方言；后续需要按真实资产口径扩展 metric/dimension 编译能力。

### 2026-06-26 17:40 · SubAgent ToolAdapter 三层出参协议

- 涉及文件：`datalogue-api/app/services/subagent_tool_adapter.py`、`datalogue-api/tests/test_subagent_tool_adapter.py`、`.omx/plans/2026-06-26-p0-4-subagent-tool-adapter-three-layer.md`、`.codex/project-memory.md`
- 关键改动：先落地 P0.4 实施计划，明确兼容迁移、调用点顺序和泄露扫描规则；将 `SubAgentToolResult` 固化为 `llm_visible`、`control_plane`、`trace_metadata` 三层；`control_plane` 增加 `raw_sql` / `raw_result` 承接内部执行 payload；`trace_metadata` 增加 `schema_version`、`tool_name`、`dataset_id`、`guard_status`、`artifact_id` 等稳定追踪字段；`llm_visible` 增加 raw/control 关键字与 SQL 形态扫描，命中后降级为安全引用摘要。
- 验证方式：先执行 `cd datalogue-api && python3 -m pytest tests/test_subagent_tool_adapter.py -q` 确认 3 个新增用例红灯，失败点分别是 control plane 拒绝 raw 字段、trace metadata 缺 schema/tool 字段、display summary 泄露 raw 内容；实现后执行 `python3 -m pytest tests/test_subagent_tool_adapter.py -q`，10 条通过；执行 `python3 -m pytest tests/test_subagent_run.py -q`，14 条通过；执行 `python3 -m pytest tests/test_subagent_tool_adapter.py tests/test_subagent_run.py -q`，24 条通过；执行 `python3 -m ruff check app/services/subagent_tool_adapter.py tests/test_subagent_tool_adapter.py`、`python3 -m py_compile app/services/subagent_tool_adapter.py app/services/subagent_fanout.py app/api/chat.py` 和 `git diff --check` 均通过。
- 残留风险：本次聚焦 ToolAdapter 协议与现有 Chat/fanout 调用点静态审查，未启动真实 `/chat/stream` 做端到端 SSE 回放；当前本地 checkout 没有 `.venv/bin/python`，验证使用系统 `python3`。

### 2026-06-26 17:55 · DatalogueEventEnvelope 与 `/chat/stream` SSE 映射

- 涉及文件：`.omx/plans/DAT-5-event-envelope-plan.md`、`datalogue-api/app/schemas/bi_workbench.py`、`datalogue-api/app/schemas/__init__.py`、`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_event_envelope.py`、`.codex/project-memory.md`
- 关键改动：新增统一 `DatalogueEventEnvelope` schema，覆盖 `route.started`、`dataset.selected`、`clarification.required`、`dataset.query.started`、`dataset.query.completed`、`artifact.created`、`answer.completed`、`error.blocked` 与 `user_visible` / `trace_only` / `control_plane`；在 `/chat/stream` 关键 SSE payload 上追加 `event_envelope`，保留旧 `type`、`answer`、`sql`、`response_metadata` 等顶层字段；对 `user_visible` envelope 递归清理 raw SQL、完整结果集、schema、capsule 和 control_plane 主体。
- 验证方式：先执行 `cd datalogue-api && pytest tests/test_event_envelope.py` 确认新增测试红灯，失败原因为 `app.schemas.bi_workbench` 与 `_with_event_envelope` 缺失；实现后再次执行通过；执行 `cd datalogue-api && pytest tests/test_chat.py`，117 条用例通过。
- 残留风险：本次未启动真实前端页面回放 SSE Network，只用 schema/helper 单测和现有 `_stream_chat` 近真实测试验证；未来 AgentScope event stream 仍需在消费端接入时补端到端契约测试。

### 2026-06-26 18:07 · ask_bi / BIWorkbenchTool 最小稳定契约

- 涉及文件：`datalogue-api/app/schemas/bi_workbench.py`、`datalogue-api/app/services/bi_workbench_tool.py`、`datalogue-api/app/schemas/__init__.py`、`datalogue-api/tests/test_bi_workbench_tool.py`、`.codex/project-memory.md`
- 关键改动：新增 `AskBIRequest`、`AskBIResponse`、`DatalogueEventEnvelope`、`ArtifactCard`、`ArtifactRef` 等外层契约；新增 `BIWorkbenchTool` / `ask_bi` async 入口，将 `confirmed_dataset_id` 转为现有 `ChatRequest.dataset_id` 并复用 `_stream_chat`；响应只投影 answer、候选数据集、事件信封和引用句柄，公开 ref 会把内部 `sql_result` 命名归一化为 `result`，并在 schema 层拒绝 `raw_sql`、`raw_result`、`schema`、`capsule`、`control_plane` 等内部字段进入用户可见面。
- 验证方式：先执行 `cd datalogue-api && python3 -m pytest tests/test_bi_workbench_tool.py -q` 确认红灯为缺少 `app.schemas.bi_workbench`；实现后执行 `cd datalogue-api && python3 -m pytest tests/test_bi_workbench_tool.py tests/test_chat.py -q`，119 条用例通过；执行 `cd datalogue-api && python3 -m ruff check app/schemas/bi_workbench.py app/services/bi_workbench_tool.py app/schemas/__init__.py tests/test_bi_workbench_tool.py` 通过；执行 `git diff --check -- datalogue-api/app/schemas/bi_workbench.py datalogue-api/app/services/bi_workbench_tool.py datalogue-api/app/schemas/__init__.py datalogue-api/tests/test_bi_workbench_tool.py .codex/project-memory.md` 无输出。
- 残留风险：本次是 P0.6 最小后端工具契约，未新增公开 API 路由，也未把现有 `/chat/stream` SSE 全量改造成 event envelope；真实链路仍依赖现有 Chat/LeadAgent/DatasetAgent 主链。
