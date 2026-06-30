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

### 2026-06-26 18:44 · ArtifactCard 保留动作轻量协议验收

- 涉及文件：`datalogue-api/app/services/artifact_actions.py`、`datalogue-api/tests/test_reserved_actions_contract.py`、`datalogue-api/tests/test_llm_config.py`、`datalogue-web/src/components/artifact-card.jsx`、`datalogue-web/src/components/artifact-card.test.jsx`、`.omx/plans/DAT-7-轻量协议验收与全量回归计划.md`、`.codex/project-memory.md`
- 关键改动：新增后端 ArtifactCard action 协议生成器，固定 `export` / `continue_edit` 第一阶段禁用态、忽略未知 action、不透传内部 payload；新增前端 `ArtifactCard` 组件，白名单渲染 title/status/summary/preview/refs/actions，未知 action 只写 debug，不展示；将 LLM 配置测试的 `max_tokens` 断言改为引用 `ROLE_CALL_POLICIES`，对齐 2026-06-23 已调整的角色策略。
- 验证方式：执行 `cd datalogue-api && pytest -q tests/test_reserved_actions_contract.py`，3 条用例通过；执行 `cd datalogue-web && npm run test -- artifact-card`，1 个测试文件 3 条用例通过；执行 `cd datalogue-api && pytest -q tests/test_reserved_actions_contract.py tests/test_multiturn.py tests/test_multiturn_regression.py tests/test_multiturn_context_builder.py tests/test_subagent_tool_adapter.py tests/test_artifact_api.py`，79 条用例通过；执行 `cd datalogue-api && pytest -q`，732 条用例通过；执行 `cd datalogue-web && npm run lint`，0 error、15 个既有 warning；执行 `cd datalogue-web && npm run test`，5 个测试文件 21 条用例通过；执行 `cd datalogue-web && npm run build` 通过，仅 Vite chunk size warning。
- 残留风险：真实链路抽检 `python3 scripts/api_assets.py health` 返回 `GET /health failed: [Errno 61] Connection refused`，本地 Datalogue API 未启动，因此未执行只读 SQL preview；新 `ArtifactCard` 组件当前是协议组件，尚未替换 `MyMessage.jsx` 内的旧 artifact 展示路径。

### 2026-06-26 18:29 · Retry checkpoint 与受控重试动作

- 涉及文件：`datalogue-api/app/services/conversation_store.py`、`datalogue-api/app/api/chat.py`、`datalogue-api/app/schemas/chat.py`、`datalogue-api/tests/test_retry_checkpoint.py`、`datalogue-web/src/components/artifact-card.jsx`、`datalogue-web/src/components/artifact-card.test.jsx`、`datalogue-web/src/styles.css`、`.omx/plans/DAT-12-retry-checkpoint-plan.md`、`.codex/project-memory.md`
- 关键改动：按 DAT-12 先落地开发计划；在 ConversationStore 的 `_thread.retry_checkpoints` 中注册/恢复 `dataset_confirmed`、`query_context_ready`、`artifact_generation_failed` 三类安全 checkpoint，校验 user、conversation、task、permission_scope 和 expires_at，恢复上下文清洗掉 SQL/schema/control_plane；`ChatRequest` 增加可选 `retry_checkpoint_ref`，多轮 wrapper 输出 `retry.started`、`retry.checkpoint_restored`、`retry.fallback_to_whole_task`、`retry.completed`、`retry.failed`，恢复失败时走整任务重试；final payload 回填 `retry_checkpoint`；新增 ArtifactCard，retry action 只派发 checkpointRef。
- 验证方式：先执行 `python3 -m pytest tests/test_retry_checkpoint.py -q` 确认 RED 失败为缺少 `register_retry_checkpoint`；实现后执行 `python3 -m pytest tests/test_retry_checkpoint.py -q` 通过；执行 `python3 -m pytest tests/test_retry_checkpoint.py tests/test_chat.py -q`，120 条通过；执行 `cd datalogue-web && npm run test -- artifact-card`，2 条通过；执行 `npm run lint`，0 error、15 个既有 warning；执行 `npm run build` 通过，保留既有大 chunk warning。
- 残留风险：本次没有把 ArtifactCard 接入现有 MyMessage 渲染入口，只完成组件和受控 retry action 契约；未启动真实页面回放 SSE retry 流，当前以单测模拟 stream 和既有 chat 回归覆盖。

### 2026-06-26 18:24 · DAT-11 AgentScope Shell Adapter 最小验证线

- 涉及文件：`.omx/plans/DAT-11-agentscope-shell-adapter.md`、`datalogue-api/app/services/agentscope_shell_adapter.py`、`datalogue-api/app/services/agentscope_event_adapter.py`、`datalogue-api/tests/test_agentscope_shell_adapter.py`、`datalogue-api/tests/test_agentscope_event_adapter.py`、`.codex/project-memory.md`
- 关键改动：按 DAT-11 要求先保存开发计划；新增 AgentScope Shell Adapter service，第一阶段固定只允许 `ask_bi`，不开放公开 API、不接前端、不启动 runner；新增 AgentScope Event Adapter，`control_plane` 事件只计入内部丢弃数，不进入 Shell 可见事件或 trace 事件输出；适配当前已合入的 async `ask_bi`、`DatalogueEventEnvelope` 和 `ArtifactRef.ref_id` 契约。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_agentscope_shell_adapter.py tests/test_agentscope_event_adapter.py tests/test_bi_workbench_tool.py tests/test_event_envelope.py -q` 通过；执行 `cd datalogue-api && python3 -m py_compile app/services/agentscope_shell_adapter.py app/services/agentscope_event_adapter.py app/schemas/bi_workbench.py app/services/bi_workbench_tool.py` 通过；执行 `git diff --check` 通过。
- 残留风险：当前是 contract-first 最小验证线，未接真实 `/chat/stream`、未导入 AgentScope runtime、未做真实 BI 主链回放。

### 2026-06-26 18:26 · P1 Chat Shell：ArtifactCard、任务时间线与候选确认

- 涉及文件：`datalogue-web/src/components/artifact-card.jsx`（新建）、`datalogue-web/src/components/task-timeline.jsx`（新建）、`datalogue-web/src/components/artifact-card.test.jsx`（新建）、`datalogue-web/src/components/task-timeline.test.jsx`（新建）、`datalogue-web/src/assistant/MyMessage.test.jsx`（新建）、`datalogue-web/src/assistant/chat-adapter.test.js`（新建）、`datalogue-web/src/assistant/chat-adapter.js`（修改）、`datalogue-web/src/assistant/MyMessage.jsx`（修改）、`datalogue-web/src/styles.css`（修改）、`.codex/project-memory.md`
- 关键改动：
  - 新增 ArtifactCard 统一产物卡片（title/status/summary/preview/refs/actions），未知 action_type 不渲染，disabled action 仅展示不交互；
  - 新增 TaskTimeline 业务级时间线（五类节点：任务理解/数据集匹配/BI 执行/结果产物/下一步），内置 FORBIDDEN_PATTERNS 安全扫描自动截断 SQL/schema 等关键词；
  - 新增 CandidateDatasetCard 候选确认（只展示 dataset_name + short_reason，不暴露字段/表/资产详情）；
  - chat-adapter.js 新增 taskTimeline 累加器，从 route_decision/step/final 事件推断 C-ready 数据结构，在 metadata.custom 中输出 taskTimeline/artifactCard/candidateDatasets，补充 adapter 单测覆盖业务 session、artifact metadata、候选数据集和 clarification_response 一次性消费；
  - MyMessage.jsx 新增 CandidateDatasetCard 组件并渲染 TaskTimeline + ArtifactCard；
  - styles.css 新增三套 CSS 类（.artifact-card/.task-timeline/.candidate-dataset-card），遵循现有设计令牌体系。
- 验证方式：执行 `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js src/components/task-timeline.test.jsx src/components/artifact-card.test.jsx src/assistant/MyMessage.test.jsx`，4 个测试文件 31 条用例通过；执行 `cd datalogue-web && npm run lint` 通过，保留既有 15 个 warning；执行 `cd datalogue-web && npm run build` 通过，仅保留既有 chunk size warning；执行 `git diff --check` 通过。
- 残留风险：后端 C-ready event envelope 正式上线后，chat-adapter.js 中从 step 推断的 timeline 节点可能需要与后端新 event type 对齐调整；未做深色模式样式适配；MyMessage 测试依赖 assistant-ui mock，真实 assistant-ui 渲染路径未端到端验证。

### 2026-06-26 21:05 · DAT-17 Artifact refs 持久化与旧会话兼容

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/app/schemas/bi_workbench.py`、`datalogue-api/tests/test_artifact_card_contract.py`、`datalogue-api/tests/test_legacy_conversation_replay.py`、`datalogue-web/src/assistant/thread-list-adapter.js`、`datalogue-web/src/components/artifact-card.jsx`、`datalogue-web/src/components/artifact-card.test.jsx`、`datalogue-web/src/components/chat-page.jsx`、`datalogue-web/src/components/chat-page.test.jsx`、`datalogue-web/tests/unit/assistant/artifact-custom.test.js`、`.codex/project-memory.md`
- 关键改动：final payload 统一补齐 `task_id`、`trace_id`、`primary_ref`、`related_refs` 和 `artifact_card`，event envelope 透传同一 task/trace；ArtifactCard 只暴露 `artifact:/trace:/checkpoint://` 引用句柄和禁用态动作，不携带 raw SQL/raw result；assistant message metadata 写回新 refs，`query_artifact` 只按 `artifact:<uuid>` 反连 message_id；`conversation_state.facts` 写入 `artifact_refs` fact，旧会话不迁移、不回填；前端历史回放只渲染真实 `response_metadata.artifact_card`，不会根据旧 `result_ref/report_ref` 伪造卡片；补充 `/chat/:id` 正向线程同步，直接打开历史会话时显式切到路由会话，避免停留在本地草稿导致 ArtifactCard 不回放。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_artifact_card_contract.py tests/test_legacy_conversation_replay.py tests/test_conversation.py tests/test_artifact_api.py -q`，15 条用例通过；执行 `cd datalogue-api && python3 -m pytest tests/test_event_envelope.py tests/test_retry_checkpoint.py tests/test_chat.py -q`，123 条用例通过；执行 `cd datalogue-web && npm run test -- src/components/chat-page.test.jsx src/components/artifact-card.test.jsx tests/unit/assistant/artifact-custom.test.js src/assistant/chat-adapter.test.js`，4 个测试文件 28 条用例通过；执行 `cd datalogue-api && python3 -m py_compile app/api/chat.py app/schemas/bi_workbench.py`、`python3 -m ruff check app/api/chat.py app/schemas/bi_workbench.py tests/test_artifact_card_contract.py tests/test_legacy_conversation_replay.py` 通过；执行 `cd datalogue-web && npm run lint` 通过，保留既有 15 个 warning；执行 `cd datalogue-web && npm run build` 通过，仅保留既有 chunk size warning；执行 `git diff --check` 通过。
- 残留风险：DAT-17 只完成协议与持久化闭环；真实页面、SSE、后端日志、Langfuse、`query_artifact/conversation_state` 五件套一致性仍需 DAT-18 用本地服务和真实问题记录验收。

### 2026-06-26 18:50 · DAT-14 主链路五件套验收用例

- 涉及文件：`.omx/plans/2026-06-26-dat-14-main-chain-acceptance.md`、`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_chat.py`、`datalogue-api/tests/test_bi_main_chain_acceptance.py`、`datalogue-web/src/assistant/chat-adapter.test.js`、`docs/main-chain-acceptance-record-template.md`、`.codex/project-memory.md`
- 关键改动：新增 DAT-14 验收计划和真实链路记录模板；补充主链路验收测试，核对成功问数的 SSE/message metadata/trace index/query_artifact/conversation_state，覆盖低置信候选确认、无法回答拒答和受控失败 retry；扩展 `/chat/stream` 日志摘要，加入 result/report artifact ref 与 Langfuse trace/session；新增前端 adapter 测试，确认 final SSE metadata 映射并保护旧历史缺 ArtifactCard 不伪造。
- 验证方式：先执行 `cd datalogue-api && pytest tests/test_chat.py::TestChatAPI::test_chat_stream_log_summary_extracts_debug_fields tests/test_bi_main_chain_acceptance.py -q` 确认 RED（日志摘要缺 result/report/trace 字段，验收 fixture 调整后复现），修复后该命令 4 passed；执行 `cd datalogue-api && python3 -m pytest tests/test_bi_main_chain_acceptance.py tests/test_chat.py -q`，121 passed；执行 `cd datalogue-api && python3 -m pytest tests/test_observability.py tests/test_artifact_api.py -q`，20 passed；执行 `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js`，1 个文件 6 条用例通过；执行 `cd datalogue-web && npm run lint`，0 error、15 个既有 warning；执行 `cd datalogue-web && npm run build` 通过。
- 残留风险：本轮未连接真实 Langfuse 控制台做外部 observation 截图；自动化使用 no-op trace 与本地 `observability_trace_index` 验证主链路不阻塞。Vite build 仍有既有大 chunk warning，lint 仍有 15 个既有 warning。

### 2026-06-26 21:25 · DAT-18 五件套验收记录落档

- 涉及文件：`docs/main-chain-acceptance-records/2026-06-26-b-first-c-core-chain.md`、`.codex/project-memory.md`
- 关键改动：新增 B-first C-ready 主链路五件套验收记录，明确自动化代表问题 `最近30日GMV趋势如何` 已覆盖 SSE、后端 checkpoint、trace index、query_artifact 和 conversation_state 交叉核对；2026-06-27 补录真实问题 `查询杨凯 2024 年工作日志`，记录 Manifest stale fail-closed、Manifest v3 发布、`conversation_id=16/message_id=34/task_id=conv-16-msg-34/trace_id=dlg-a85416ec39724384b5aa992a23641bb7/artifact:e668a634847a41a4b5489d11092da363` 在页面、SSE、Artifact API、query_artifact、conversation_state 和本地 trace index 的一致性。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_bi_main_chain_acceptance.py tests/test_chat.py tests/test_observability.py tests/test_artifact_api.py -q`，141 条用例通过；执行最终集成套件 `cd datalogue-api && python3 -m pytest tests/test_capability_manifest.py tests/test_bi_soul_contract.py tests/test_lead_agent_capability_router.py tests/test_query_plan_compiler.py tests/test_sql_dialect_adapter.py tests/test_subagent_tool_adapter.py tests/test_event_envelope.py tests/test_bi_workbench_tool.py tests/test_agentscope_shell_adapter.py tests/test_agentscope_event_adapter.py tests/test_artifact_card_contract.py tests/test_retry_checkpoint.py tests/test_legacy_conversation_replay.py tests/test_bi_main_chain_acceptance.py tests/test_chat.py -q`，168 条用例通过；执行 `cd datalogue-web && npm run test`，9 个测试文件 62 条用例通过；执行 `cd datalogue-web && npm run lint` 通过，保留既有 15 个 warning；执行 `cd datalogue-web && npm run build` 通过，仅保留既有 chunk size warning；执行 `git diff --check` 通过；Playwright 打开 `/chat/16` 确认历史问题、错误诊断、`BI 查询结果` ArtifactCard、同一 artifact_ref 和重试按钮可见。
- 残留风险：Langfuse 页面服务可达但后端 Python 环境缺少 `langfuse` SDK，真实 observation 未写入；真实业务 SQL 因语义层错误引用不存在字段 `eas_personofile.create_time` 受控失败，需修正 dataset 10 语义资产后才能把 DAT-18 标为“真实业务成功查询 + Langfuse observation 完整五件套”通过。

### 2026-06-28 15:32 · C2 RepairPatch Engine 设计与开发计划

- 涉及文件：`docs/architecture/C2-RepairPatch-字段漂移自动修复设计.md`、`docs/superpowers/specs/2026-06-28-c2-repair-patch-engine-design.md`、`docs/superpowers/plans/2026-06-28-c2-repair-patch-engine.md`、`.codex/project-memory.md`
- 关键改动：固化 C2 阶段设计，明确 P0 聚焦字段不存在 / 字段漂移自动修复；字段候选采用语义资产优先、selected columns fallback；Patch IR 使用统一 `RepairPatch` envelope，支持 `query_graph_patch` 与 `compiler_binding_patch`，禁止直接 patch SQL；confidence 采用规则打底 + LLM 业务语义裁判 + Tool merge/clamp；高置信自动修复，中置信只保留确认协议和占位 UI，低置信阻断；真实验收用 `查询杨凯 2024 年工作日志`，通过 compiler binding 注入字段漂移，不污染真实语义资产。
- 开发计划：C2 等 C1 合并到 `b-first-c` 后启动，拆成 3 个 stacked PR：PR1 离线 Patch Engine 内核；PR2 RepairPlan 协议与真实链路；PR3 前端 timeline、ArtifactCard 承接和页面 E2E。
- 验证方式：执行 `rg -n "TODO|TBD|待定|placeholder|FIXME" docs/architecture/C2-RepairPatch-字段漂移自动修复设计.md docs/superpowers/specs/2026-06-28-c2-repair-patch-engine-design.md docs/superpowers/plans/2026-06-28-c2-repair-patch-engine.md`，仅命中“中置信占位 UI”等已确认范围；执行关键约束扫描，确认 `selected columns`、`compiler_binding_patch`、`repair.patch_validated`、真实问题和五件套验收已写入；执行 `git diff --check` 通过。
- 残留风险：这是设计和开发计划落档，尚未实现 C2 代码；C2 开发需要先完成 C1 合并，再从合并后的 `b-first-c` 拉 PR1 分支。

### 2026-06-28 16:13 · C1/C2 RepairPlan 文档边界 review 收口

- 涉及文件：`docs/architecture/C1-RepairPlan-真实成功链路设计.md`、`docs/superpowers/specs/2026-06-28-c1-repair-plan-real-acceptance-design.md`、`docs/main-chain-acceptance-records/2026-06-28-c1-repair-plan-acceptance.md`、`.codex/project-memory.md`
- 关键改动：按 review 结论修正 C1/C2 边界，明确 C1 只交付 RepairPlan 协议、`repair.*` 事件、Artifact refs、失败分类、受控 retry / fixture 验证和现有可信 template 路径下的真实业务成功链路；“真实成功链路”不等于字段漂移自动修复闭环；`FIELD_NOT_FOUND` / `FIELD_MAPPING_DRIFT` 的字段候选、RepairPatch IR、apply、重新编译和真实漂移验收统一归 C2 RepairPatch Engine。
- 验收记录：补充 Review 收口结论和 C2 后续闸门，要求 C2 禁止直接 patch raw SQL，并用可复现字段漂移注入完成五件套验收，避免把 C1 的 template / fixture 成功误标为完整自动修复。
- 验证方式：执行 C1/C2 边界关键词扫描，确认 C1 文档不再声称已实现真实字段级 patch / apply / recompile；执行 `git diff --check` 通过。
- 残留风险：本次仅做文档边界收口，不实现 C2 RepairPatch Engine；后续 C2 仍需按独立设计和开发计划落地真实字段漂移修复。

### 2026-06-28 16:31 · C1 review 阻断项代码收口

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_event_envelope.py`、`datalogue-api/tests/test_chat.py`、`datalogue-api/tests/test_bi_main_chain_acceptance.py`、`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/thread-list-adapter.js`、`datalogue-web/src/assistant/MyMessage.jsx`、`datalogue-web/src/assistant/chat-adapter.test.js`、`datalogue-web/src/assistant/MyMessage.test.jsx`、`datalogue-web/tests/unit/assistant/artifact-custom.test.js`、`.codex/project-memory.md`
- 关键改动：按多智能体 review 的阻断意见补齐公开层脱敏，`/chat/stream` 的顶层兼容 payload 不再旁路输出 `sql/sql_result/query_plan/candidate_assets/dsl/query_task_capsule` 等内部执行字段，`sql_execute` step 只暴露 `row_count/column_count`；前端 live 和历史回放统一用安全 mapper 提炼业务口径、Artifact refs、候选确认和 RepairPlan 摘要，不再保存或渲染 SQL 结果表、query plan、candidate assets、DSL、diagnosis、raw rows；ArtifactCard 历史对象也经过安全清洗，preview payload 不再携带 raw rows。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_repair_plan_contract.py tests/test_event_envelope.py tests/test_artifact_card_contract.py tests/test_artifact_api.py tests/test_bi_main_chain_acceptance.py tests/test_chat.py -q`，154 条通过；执行 `cd datalogue-web && npm run test`，9 个测试文件 75 条通过；执行 `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js src/assistant/MyMessage.test.jsx && npm run lint && npm run build`，目标测试 19 条通过、lint 0 error 15 个既有 warning、build 通过；执行 `git diff --check` 通过。
- 残留风险：本次只收口 C1 review 阻断项，不启动 C2 RepairPatch Engine；真实字段漂移自动修复仍需等 C1 合并后按 C2 独立 PR 落地。

### 2026-06-28 16:52 · C1 页面可见层内部节点名终审修复

- 涉及文件：`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/thread-list-adapter.js`、`datalogue-web/src/assistant/MyMessage.jsx`、`datalogue-web/src/components/agent-panel.jsx`、`.codex/project-memory.md`
- 关键改动：C1 最终页面复验发现 Chain-of-Thought 和 AgentPanel 仍显示 `query_plan`、`candidate_assets`、`subagent.query_plan`、`Query Task Capsule` 等内部节点或 control-plane 标题；本次统一将 live reasoning、历史回放、消息气泡和 AgentPanel 步骤标签映射为业务级中文文案，并移除 AgentPanel 中 message gateway 的原始 `turn_event/query_task_capsule` JSON 展示，只保留任务理解业务摘要。
- 验证方式：执行 Playwright 页面冒烟，打开 `http://127.0.0.1:5180/chat/25`，确认 ArtifactCard 可见，切到会话 1 后旧 artifact 不残留，再切回 25 后 ArtifactCard 恢复，页面 body 对 `SELECT`、`SQL 复制`、`复制 SQL`、`显示生成的 SQL`、`query_plan`、`candidate_assets`、`raw_result`、`Query Task Capsule`、`Turn Event`、`subagent.query_plan`、`subagent.candidate_assets` 的扫描均为空；执行 `cd datalogue-web && npm run test && npm run lint && npm run build`，75 条前端用例通过、lint 0 error 15 个既有 warning、build 通过；执行 `cd datalogue-api && python3 -m pytest tests/test_event_envelope.py tests/test_bi_main_chain_acceptance.py tests/test_chat.py -q`，131 条通过；执行 `git diff --check` 通过。
- 残留风险：本次只处理普通 Chat 页面和 AgentPanel 可见层文案，不改变后端 trace/control-plane 内部节点名。

### 2026-06-28 17:07 · C1 公共 API 红action终审修复

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/app/api/conversation.py`、`datalogue-api/app/services/repair_plan.py`、`datalogue-api/tests/test_chat.py`、`datalogue-api/tests/test_conversation.py`、`datalogue-api/tests/test_event_envelope.py`、`datalogue-api/tests/test_repair_plan_contract.py`、`datalogue-web/src/assistant/thread-list-adapter.js`、`datalogue-web/src/components/artifact-card.jsx`、`datalogue-web/src/components/artifact-card.test.jsx`、`.codex/project-memory.md`
- 关键改动：按 C1 终审阻断项把服务端公共层补齐为 fail-closed：`/chat/stream` 的 `event_envelope.payload` 和旧 SSE 顶层统一阻断 `query_profile/explainability/response_metadata/result_artifact/schema_summary` 等内部执行面；`/api/conversation/{id}` 不再原样返回落库 `response_metadata/step_trace/sql_list`，改为公共 DTO，只保留正文、业务摘要、Artifact refs、RepairPlan 摘要、trace 链接和安全 SubAgent 摘要；历史 step_trace 节点名映射为业务级 `display_name`；ArtifactCard 彻底取消 raw rows/columns 预览；RepairPlan 服务层修正类型构造和脱敏返回类型。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_repair_plan_contract.py tests/test_event_envelope.py tests/test_conversation.py tests/test_artifact_card_contract.py tests/test_artifact_api.py tests/test_bi_main_chain_acceptance.py tests/test_chat.py -q`，161 条通过；执行 `cd datalogue-web && npm run test && npm run lint && npm run build`，75 条前端用例通过、lint 0 error 15 个既有 warning、build 通过；执行 `python3 -m py_compile datalogue-api/app/api/conversation.py datalogue-api/app/api/chat.py datalogue-api/app/services/repair_plan.py` 和 `git diff --check` 通过；Browser 打开 `/chat/25`，确认 ArtifactCard 与会话 25 refs 可见，`SELECT/SQL 复制/复制 SQL/显示生成的 SQL/query_plan/candidate_assets/raw_result/schema_summary/Query Task Capsule/Turn Event/subagent.query_plan/subagent.candidate_assets` 均未出现在页面；执行 `/chat/25 -> /chat/1 -> /chat/25` 切换，旧 25 artifact 不残留、切回后 refs 恢复，console error/warning 为空。
- 残留风险：C1 仍不实现 C2 RepairPatch Engine；`query_profile/explainability` 只保留在数据库内部 metadata、trace 和日志，普通 SSE/history API 不再暴露，后续 C2 需要继续遵守公共层红action边界。

### 2026-06-28 17:20 · C2 PR1 RepairPatch Engine 离线内核

- 涉及文件：`datalogue-api/app/services/repair_patch.py`、`datalogue-api/app/prompts/repair_patch.py`、`datalogue-api/tests/test_repair_patch_engine.py`、`.codex/project-memory.md`
- 关键改动：从合并后的 `b-first-c` 新建 `c2-repair-patch-engine-pr1`，按 TDD 新增 RepairPatch 离线内核；定义 `RepairPatch` envelope、字段候选 `FieldCandidate`、patch operation、Tool validation 和 apply 结果；候选生成优先使用当前数据集 `SemanticDimension`，再 fallback 到已选 source columns，拒绝未选字段和跨数据集；新增粗粒度类型归一、MockSemanticJudge、语义裁判 prompt input sanitizer、confidence merge/clamp；实现 `query_graph_patch` 与 `compiler_binding_patch` 纯函数 apply，返回脱敏 diff summary 和 trace-only 字段详情；新增本地 fallback prompt `repair_plan_field_semantic_judge`，约束 LLM 只判定业务语义等价，不生成 SQL/字段 patch。
- 验证方式：先执行 `cd datalogue-api && python3 -m pytest tests/test_repair_patch_engine.py -q`，确认因 `app.services.repair_patch` 缺失 RED；补实现后执行 `cd datalogue-api && python3 -m pytest tests/test_repair_patch_engine.py tests/test_repair_plan_contract.py -q`，28 条通过；执行 `cd datalogue-api && python3 -m py_compile app/services/repair_patch.py app/services/repair_plan.py app/prompts/repair_patch.py` 通过。
- 残留风险：PR1 只实现离线 Patch Engine，不接 `/chat/stream`、RepairPlan 生命周期、Langfuse observation 或前端 timeline；真实字段漂移自动重跑成功链路属于 C2 PR2/PR3。

### 2026-06-28 17:36 · C2 PR1 终审安全边界修复

- 涉及文件：`datalogue-api/app/services/repair_patch.py`、`datalogue-api/tests/test_repair_patch_engine.py`、`.codex/project-memory.md`
- 关键改动：#18 终审发现两个合并前风险并修复：字段候选缺少业务注释时，语义裁判 prompt 不再把物理列名或表名 fallback 给 LLM，而是统一替换为“当前数据集候选字段”；用户可见 RepairPatch summary 不再原样透传 validation summary / risk flags，命中 SQL、schema、raw result、query_plan 等执行细节时退回固定业务文案，并只保留稳定枚举型 risk flag；同时补齐 confidence clamp，避免异常分数越过 `0..1` 契约。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_repair_patch_engine.py tests/test_repair_plan_contract.py tests/test_query_plan_compiler.py -q`，34 条通过；执行 `cd datalogue-api && python3 -m py_compile app/services/repair_patch.py app/prompts/repair_patch.py` 通过；执行 `git diff --check` 通过。
- 残留风险：本次仍保持 PR1 范围，不接 `/chat/stream` 和真实重跑；PR2 接主链时需要继续验证 RepairPatch trace-only metadata 不进入 SSE/history/API 用户可见面。

### 2026-06-28 17:45 · C2 PR2 RepairPatch 接入主链重跑

- 涉及文件：`datalogue-api/app/graph/nodes.py`、`datalogue-api/app/graph/workflow.py`、`datalogue-api/app/graph/state.py`、`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_repair_patch_stream.py`、`.codex/project-memory.md`
- 关键改动：按 TDD 把 C2 PR1 的 RepairPatch Engine 接入 RepairPlan 后的真实重跑生命周期；新增 `repair_patch_node`，在 `sql_audit` 生成 `FIELD_NOT_FOUND` RepairPlan 后生成字段候选、构造 query_graph patch、Tool 校验、apply 到 QueryPlan、重新调用 `compile_query_plan_to_sql`，再通过 `dsl_compiler -> sql_execute` 继续真实执行；`workflow` 新增 `repair_patch` 路由和 fail-closed router，非字段漂移仍保留旧 retry 链；`AgentState` 增加 RepairPatch 内部态和脱敏摘要；`chat.py` 加入 `repair_patch` 节点展示名；安全边界上只允许 trace-only metadata 保存字段级 patch，用户可见 `repair_patch_summary` 不包含表、字段、SQL、schema 或 raw result。
- 验证方式：先执行 `cd datalogue-api && python3 -m pytest tests/test_repair_patch_stream.py -q` 确认 RED，失败表现为 `_sql_audit_router` 仍返回 `retry` 且 `repair_patch_node` 不存在；实现后该命令 3 条通过；执行 `cd datalogue-api && python3 -m pytest tests/test_repair_patch_stream.py tests/test_repair_patch_engine.py tests/test_sql_audit.py tests/test_query_plan_compiler.py tests/test_chat.py -q`，171 条通过。
- 残留风险：PR2 完成后端主链接入和自动化重跑 fixture；前端 repair timeline 细化、ArtifactCard repair ref 展示、页面 E2E 以及真实问题字段漂移注入五件套验收仍归 C2 PR3。

### 2026-06-28 17:50 · C2 PR3 前端 RepairPatch timeline 承接

- 涉及文件：`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/chat-adapter.test.js`、`datalogue-web/src/components/task-timeline.jsx`、`datalogue-web/src/components/task-timeline.test.jsx`、`.codex/project-memory.md`
- 关键改动：按 TDD 承接 C2 PR2 的 `repair_patch` 主链输出；`chat-adapter` 支持从 `repair_patch` graph step、`repair.patch_applied` event envelope 和 final payload 的 `repair_patch_summary` 生成业务级 `repairPlan`、`repairTimeline` 和 `taskTimeline`，同时保留 `artifact_card.related_refs` 中的 `repair_plan` ref；`TaskTimeline` 增加一等业务节点 `repair_patch/自动修复`，排序在 BI 执行和结果产物之间；前端 trace 清洗新增 `repair_patch/trace_only_metadata/replacement_field_ref` 等字段级 patch 主体黑名单，普通用户可见层不展示表、字段、SQL、raw result。
- 验证方式：先执行 `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js src/components/task-timeline.test.jsx` 确认 RED，失败表现为 `repair_patch_summary` 未映射、`repair_patch` timeline 节点被当未知节点；实现后该命令 20 条通过；执行 `cd datalogue-web && npm run test`，9 个测试文件 78 条通过；执行 `cd datalogue-web && npm run lint`，0 error、15 个既有 warning；执行 `cd datalogue-web && npm run build` 通过，仅保留既有 chunk warning；执行 `cd datalogue-api && python3 -m pytest tests/test_repair_patch_stream.py tests/test_repair_patch_engine.py tests/test_sql_audit.py tests/test_query_plan_compiler.py tests/test_chat.py -q`，171 条通过。
- 残留风险：本次完成前端协议和组件承接；真实页面 E2E、字段漂移注入五件套验收和 Langfuse UI 证据仍需在本地服务启动后补充记录。

### 2026-06-28 17:56 · C2 PR3 终审 RepairPatch 时间线去重

- 涉及文件：`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/chat-adapter.test.js`、`.codex/project-memory.md`
- 关键改动：终审 #20 与 #19 stacked diff 时发现真实 repair 序列会连续发 `repair.evaluated / repair.plan_created / repair.rerun_started / repair.rerun_completed`，前端若逐条追加会产生多条“自动修复”节点且部分保持 running；本次新增 `upsertTaskTimelineEvent`，将 repair 业务时间线收敛为单个 `repair_patch/自动修复` 节点，并用完整 repair event 序列补测试。
- 验证方式：执行 `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js src/components/task-timeline.test.jsx`，20 条通过；执行 `cd datalogue-web && npm run lint`，0 error、15 个既有 warning；执行 `git diff --check` 通过。
- 残留风险：本次只修复前端时间线重复节点；真实页面 E2E 和五件套验收仍需在 PR2/PR3 Ready 后用本地服务补证。

### 2026-06-28 18:04 · C2 PR2 终审 RepairPatch 契约收口

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/app/graph/nodes.py`、`datalogue-api/app/graph/workflow.py`、`datalogue-api/app/schemas/bi_workbench.py`、`datalogue-api/app/schemas/repair_plan.py`、`datalogue-api/app/services/repair_plan.py`、`datalogue-api/app/utils/sql_diagnosis.py`、`datalogue-api/tests/test_event_envelope.py`、`datalogue-api/tests/test_repair_patch_stream.py`、`datalogue-api/tests/test_repair_plan_contract.py`、`datalogue-api/tests/test_sql_audit.py`、`.codex/project-memory.md`
- 关键改动：按 #19/#20 终审阻断项补齐 C2 后端契约；新增 `FIELD_MAPPING_DRIFT` failure class、重跑预算和 `repair_patch` 路由，语义资产字段存在但当前表不可用时归类为可修复字段映射漂移；`sql_audit_node` 优先采用确定性诊断 code 生成 RepairPlan，避免被原始 DB 错误降回 `FIELD_NOT_FOUND`；统一事件类型新增 `repair.patch_applied`，`repair_patch` 节点完成后发 canonical patch-applied envelope；公开 SSE 顶层阻断 `repair_patch/repair_patch_apply/trace_only_metadata`，只暴露脱敏 `repair_patch_summary`、`repair_plan_ref` 和状态。
- 验证方式：先执行 targeted pytest 确认 RED，失败覆盖 `repair.patch_applied` 事件类型缺失、RepairPatch 内部 body 进入公开 payload、`FIELD_MAPPING_DRIFT` 未路由；修复后执行 `cd datalogue-api && python3 -m pytest tests/test_repair_patch_stream.py tests/test_repair_patch_engine.py tests/test_repair_plan_contract.py tests/test_event_envelope.py tests/test_sql_audit.py tests/test_query_plan_compiler.py tests/test_chat.py -q`，193 条通过；执行 `cd datalogue-api && python3 -m py_compile app/api/chat.py app/graph/nodes.py app/graph/workflow.py app/schemas/bi_workbench.py app/schemas/repair_plan.py app/services/repair_plan.py app/utils/sql_diagnosis.py` 通过。
- 残留风险：PR2 仍未做真实浏览器 E2E 和 Langfuse UI 五件套验收；这些随 PR3 前端承接后统一补证。

### 2026-06-28 18:26 · C2 真实链路 E2E 与 LangGraph 节点名修复

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/app/graph/workflow.py`、`datalogue-api/tests/test_repair_patch_stream.py`、`.codex/project-memory.md`
- 关键改动：真实 `/api/chat/stream` 链路触发 LangGraph `ValueError: 'repair_patch' is already being used as a state key`，原因是 graph node 名称与 `AgentState.repair_patch` 状态字段重名；本次将内部 graph node 改为 `repair_patch_step`，并在 Chat SSE、trace、日志和前端协议层继续映射为公开业务节点 `repair_patch`，避免破坏既有 RepairPatch event contract。
- 真实验收：重启当前仓库 API `127.0.0.1:8000` 和前端 `localhost:5173` 后，用真实问题“查询杨凯 2024 年工作日志”完成主链查询，生成 `conversation_id=28`、`message_id=64`、`trace_id=d6109d98c33ff11eaf127da63dde6440`、`primary_ref=artifact:5d8fa59013334b07b20caf442eb04774`、`report_ref=artifact:cb87023d36744a199ca00e0e4f27ec6b`；页面 `/chat/28` 可见答案、任务时间线和 ArtifactCard，切换 `/chat/28 -> /chat/1 -> /chat/28` 无旧会话残留，浏览器 console error/warning 为空，用户可见层未命中 `query_plan/candidate_assets/raw_result/schema_summary/SQL` 等内部细节。
- 数据核对：`query_artifact` 中主结果和报告 artifact 均存在并指向同一 `conversation_id/message_id/trace_id`；`conversation_state` 存在 `session_id=e2e-c2-fixed-1782641948`、`active_dataset_id=10`、`turn_index=1`；`observability_trace_index` 有同一 trace，状态为 `success`。
- 验证方式：先执行 `.venv/bin/python -m pytest tests/test_repair_patch_stream.py::test_build_workflow_registers_repair_patch_without_state_key_collision -q` 确认 RED；修复后执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_repair_patch_stream.py tests/test_repair_patch_engine.py tests/test_repair_plan_contract.py tests/test_event_envelope.py tests/test_sql_audit.py tests/test_query_plan_compiler.py tests/test_chat.py -q`，191 条通过、3 条 skipped；执行 `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js src/components/task-timeline.test.jsx src/components/artifact-card.test.jsx src/assistant/MyMessage.test.jsx`，48 条通过；执行 `cd datalogue-web && npm run lint && npm run build` 通过，仅保留 15 个既有 lint warning 和既有 chunk size warning；执行 `git diff --check` 通过。
- 残留风险：真实问题当前走可信模板一次成功，没有触发 RepairPatch 自动修复事件；本次 E2E 证明主链、页面回放、会话切换、Artifact/trace 持久化和 LangGraph 注册问题已收口，字段漂移自动修复的真实 RepairPatch 五件套仍需要用注入式漂移场景单独补证。

### 2026-06-30 09:26 · C2 RepairPatch 字段漂移内部 E2E pytest 固化

- 涉及文件：`datalogue-api/tests/test_repair_patch_stream.py`、`.codex/project-memory.md`
- 关键改动：把“注入旧字段触发字段映射漂移”的方案 1 固化为正式 pytest 内部 harness：临时 SQLite 真实执行首轮坏 SQL，模拟语义资产仍指向旧字段，确认 `sql_execute -> sql_audit -> repair_patch -> dsl_compiler -> sql_execute` 链路自动生成 RepairPatch、重编译为合法 QueryGraph SQL 并二次执行成功；测试同时校验 RepairPatch 用户可见摘要不泄露表名、字段名、SQL、query_plan、trace-only metadata 或 raw result。
- 验证方式：先执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_repair_patch_stream.py::test_workflow_e2e_repairs_injected_field_mapping_drift -q` 确认 RED，初始失败为 helper 未实现；补齐 harness 后同一单例通过；执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_repair_patch_stream.py tests/test_repair_patch_engine.py tests/test_repair_plan_contract.py tests/test_event_envelope.py tests/test_sql_audit.py tests/test_query_plan_compiler.py tests/test_chat.py -q`，192 条通过、3 条 skipped。
- 残留风险：本次是内部-only workflow pytest，不启动真实 `/chat/stream` HTTP 服务、浏览器页面或 Langfuse UI；它用于稳定覆盖字段漂移自动修复主链，真实页面五件套仍需在本地服务验收记录中单独补证。

### 2026-06-30 09:45 · C2 RepairPatch 合并后验收落档

- 涉及文件：`docs/main-chain-acceptance-records/2026-06-30-c2-repairpatch-post-merge.md`、`.codex/project-memory.md`
- 关键改动：在 `b-first-c@3ad8bb2c` 上补充 C2 RepairPatch 合并后验收记录，明确 #19/#20 已进入主线；记录字段映射漂移内部 E2E 的事件顺序、关键断言、公开层脱敏边界、前端 timeline 承接和五件套分层状态；如实标注本次未启动浏览器真实会话和 Langfuse UI，不伪造成完整发布级五件套通过。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_repair_patch_stream.py::test_workflow_e2e_repairs_injected_field_mapping_drift -q`，1 条通过；执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_repair_patch_stream.py tests/test_repair_patch_engine.py tests/test_repair_plan_contract.py tests/test_event_envelope.py tests/test_sql_audit.py tests/test_query_plan_compiler.py tests/test_chat.py -q`，192 条通过、3 条 skipped；执行 `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js src/components/task-timeline.test.jsx src/components/artifact-card.test.jsx src/assistant/MyMessage.test.jsx`，48 条通过；执行 `cd datalogue-web && npm run lint && npm run build` 通过，保留既有 15 个 lint warning 和 Vite chunk warning；执行 `git diff --check` 通过。
- 残留风险：C2 RepairPatch 自动修复主链已有合并后可重复证据；发布级浏览器页面、Langfuse observation、真实 `query_artifact/conversation_state` 同一 trace 五件套仍需用本地服务单独补证。

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
