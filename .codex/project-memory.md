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

### 2026-06-22 至 2026-06-23 基础体验、日志与治理收口

- 补齐数据库字典字段、后续新增表和 LangGraph checkpoint 相关表/字段注释迁移，真实 PostgreSQL 抽查确认表注释和字段注释缺失数为 0。
- 替换前端侧栏品牌 Logo 与浏览器 favicon，完成桌面和移动视口可见性检查。
- 修正数据集页面顶部“数据表”能力卡计数为当前数据集已选表数量，并补组件回归测试；压缩 LeadAgent 两阶段 Planner Prompt 重复说明，同步 Langfuse production v4，保持 JSON 输出契约不变。
- 收口新对话本地草稿、最近对话排序、SubAgent 规则规划器金额聚合 fallback、LLM 原始响应诊断、`/chat/stream` 行级日志和关键代码中文注释规范。
- 项目记忆和 AGENTS 规则同步固化“最新详细记录超过 10 条即压缩”的维护约束。

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
- C3 设计落档为 AgentScope Workbench 产品化：入口采用 Chat 右侧 Panel + 隐藏 `/workbench/:threadId/:artifactRef?`，`as_* / conv_*` 线程规则、mirror 四表、Workbench View Model、受控 retry 和旧会话只读策略进入架构文档与 superpowers spec。
- C3-P0 实施计划按 6 个 PR 拆分为 AgentScope mirror 四表、Chat Session Bridge、Workbench View Model API、受控 retry/lease、Chat 右侧 Panel 和双主路径验收，明确 AgentScope 管会话消息、Datalogue 主链管 BI 执行，用户可见层禁止 SQL/schema/raw rows/query_plan/field_patch。
- C3-P0 PR1 完成 AgentScope Workbench 本地 mirror 四表基础：`agentscope_session/message/event/ref`、线程解析、mirror 写入、assistant running lease 和 ref 唯一约束；验证包含 mirror/thread resolver pytest 与 py_compile，后续 PR2-PR6 继续接入 Chat stream、View Model、retry、Panel 和验收。
- C3-P0 PR2 完成 Chat Session Bridge：`/chat/stream` 接入 AgentScope mirror 但不替换 Datalogue 主链，新增 `thread_id`、新 `as_*` session/message/event/ref 投影、final payload 回写线程和异常/取消/无 final 收口；验证覆盖 chat bridge、event projection、mirror、thread resolver 和 chat pytest。
- C3-P0 PR3 完成 Workbench View Model API：新增 `/api/workbench/thread/{thread_id}` 和 artifact view，支持 `as_*` mirror 视图、`conv_*` 旧会话只读回放、artifact refs 脱敏摘要和用户可见层禁止 SQL/schema/raw rows/query_plan/field_patch。
- C3-P0 PR4 完成 Controlled Retry And Lease Recovery：`POST /api/workbench/actions/retry` 白名单化接收 thread/message/checkpoint/action，过期 running message 收口为 interrupted 并生成可恢复 checkpoint，旧 `conv_*` 只读禁用 retry。
- C3-P0 PR5 完成 Chat Workbench Panel：Chat 右侧挂载工作台 Panel 和隐藏 `/workbench/:threadId/:artifactRef?` 路由，前端 adapter 支持 `as_* / conv_*` 线程规范化、Workbench View Model、artifact 详情和受控 retry 请求白名单，Panel 只展示业务摘要、timeline、refs、Artifact 摘要和 action 禁用原因。
- C3-P0 PR6 完成 Workbench acceptance hardening：后端补新 `as_*` Chat stream mirror、lease interrupted + controlled retry、legacy `conv_*` 只读回放三条验收路径；前端补 thread remap、Workbench View Model 回放、artifact refs 和 Panel source 优先级测试；同步 `task.started` 事件契约与 C3 验收记录。
- C3-P0 真实浏览器 E2E 补证修复 AgentScope mirror payload 泄露拦截和 `/chat` 候选确认后 Workbench Panel 切换问题；真实问题“查询杨凯 2024 年工作日志”完成成功问数，主 Chat、右侧 Workbench Panel、隐藏 route 和旧会话只读回放均补证。

### 2026-06-30 C3-P1 Workbench Retry 主链恢复

- 完成 Workbench 受控 retry 从 action 到 `/chat/stream` checkpoint restore 的主链恢复入口：后端 `WorkbenchRetryRunRequest` 返回业务级 `run_request`，前端 WorkbenchPanel/ChatPage/chat-adapter 消费 pending retry 并交给既有 checkpoint restore 链路。
- 补 internal-only harness 和统一 `retry.started/checkpoint_restored/completed/failed` event envelope，确保 `workbench.retry_requested -> retry.checkpoint_restored -> answer.completed` 能按同一 thread、trace、artifact、checkpoint refs 追溯。
- 真实浏览器补证修复 `as_*` route 恢复数据集、历史 thread append、Panel running 轮询和 ArtifactCard 重复 refs 等缺口；验证包含后端/前端定向测试、lint/build、真实页面点击 retry 到 completed，以及后端 observability API 可拉取同一 trace。

## 高价值判断

- Datalogue 当前业务链路不依赖 Redis 保存多轮业务状态；`last_success_task`、`conversation_state.subagent_capsules` 和 query artifacts 的真相在数据库或应用 ArtifactStore 路径，Langfuse/BullMQ Redis key 不能当成业务状态依据。
- 多轮追问不要从当前自然语言残留硬猜 `person`；应依赖 LLM 结构化槽位、上一轮已确认过滤或澄清。
- 数据集上下文压缩优先采用“轻量候选资产目录 + 按需详情补合”，不要一开始把完整字段、SQL、样例行全部塞进 prompt。
- `.env.example` 中要区分“已被 Settings 读取并生效的配置”和“尚未接入的候选项”。
- `localhost:8080` 等地址返回应用层 `Unauthorized` 时，优先判断服务已启动，继续排查认证、代理或路由，不要直接判定服务未启动。

## 最新详细记录

### 2026-06-30 16:08 · C3-P2 PR1 Workbench 产品化状态模型

- 涉及文件：`datalogue-api/app/api/workbench.py`、`datalogue-api/app/schemas/agentscope_workbench.py`、`datalogue-api/app/services/workbench_view_model.py`、`datalogue-api/app/services/workbench_actions.py`、`datalogue-api/tests/test_workbench_view_api.py`、`datalogue-api/tests/test_workbench_retry_actions.py`、`datalogue-web/src/assistant/workbench-api.js`、`datalogue-web/src/assistant/workbench-api.test.js`、`datalogue-web/src/components/workbench-panel.jsx`、`datalogue-web/src/components/workbench-panel.test.jsx`、`datalogue-web/src/components/workbench-route.test.jsx`、`datalogue-web/src/styles.css`、`docs/superpowers/plans/2026-06-30-c3-p2-workbench-productization.md`、`docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md`。
- 关键改动：按“方案 1 产品化、方案 2 作验收闸门”启动 C3-P2 PR1；后端新增 `WorkbenchStatusSummary` 作为 Workbench thread-level 产品态，统一表达 `empty/running/completed/failed/interrupted/read_only`、actionable、primary artifact、retry checkpoint 和 trace ref；`_build_agentscope_actions()` 收紧为只使用最新终态 assistant message 自身 checkpoint；`POST /api/workbench/actions/retry` 对同一 running checkpoint 幂等返回既有 retry message，避免重复 running；artifact detail 支持可选 `thread_id` ownership scope，非当前 thread refs 中的 artifact fail-closed。
- 前端改动：Workbench Panel 使用后端 `status_summary` 渲染状态卡、空态、失败诊断摘要、Artifact 详情抽屉和 retry 后主产物自动聚焦；隐藏 `/workbench/:threadId/:artifactRef?` 继续复用同一 Panel；`fetchWorkbenchArtifact()` 支持携带规范化 `thread_id`，前端不读取或拼接 SQL/schema/raw rows/query_plan/field_patch。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_c3_workbench_acceptance.py tests/test_workbench_view_api.py tests/test_workbench_retry_actions.py tests/test_event_envelope.py tests/test_agentscope_event_projection.py tests/test_retry_checkpoint.py -q`，34 条通过；执行 `cd datalogue-web && npm run test -- src/components/workbench-panel.test.jsx src/components/workbench-route.test.jsx src/components/chat-page.test.jsx src/components/artifact-card.test.jsx src/assistant/chat-adapter.test.js src/assistant/thread-list-adapter.test.js src/assistant/workbench-api.test.js`，66 条通过；执行 `cd datalogue-api && python3 -m py_compile app/api/workbench.py app/schemas/agentscope_workbench.py app/services/workbench_view_model.py app/services/workbench_actions.py` 通过；执行 `cd datalogue-web && npm run lint` 通过，保留 15 个既有 warning；执行 `cd datalogue-web && npm run build` 通过，仅保留既有 chunk warning；执行 `git diff --check` 通过，diff 泄露扫描只命中 schema 文件路径和测试禁止词断言。
- 残留风险：本轮完成自动化验收闸门和产品态加固，尚未重新跑真实浏览器点击 retry；C3-P2 PR1 发布前仍应复用 C3-P1 的真实 seed，再确认页面点击、Network SSE、Workbench Panel 刷新和 `/api/observability/traces/{trace_id}` 一致。

### 2026-06-30 16:24 · C3-P2 PR1 浏览器验收闸门补证

- 涉及文件：`datalogue-api/app/services/workbench_view_model.py`、`datalogue-api/tests/test_workbench_view_api.py`、`docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md`、`.codex/project-memory.md`
- 关键改动：真实浏览器打开成功 `as_*` 线程时发现 `GET /api/workbench/artifact/{artifact_ref}?thread_id=as_*` 返回 404，导致 Panel 显示 `工作台暂不可用`；修复 ownership gate 只认 `ref_type="artifact"` 的过窄判断，改为按 `thread_id + ref_value == artifact:<uuid>` 精确校验，兼容真实业务 ref_type 为 `result/report` 的 artifact refs。
- 浏览器验收：`/chat/as_c63b713b-06c7-41be-8961-c49b37f88709` 显示 completed 状态、Artifact Drawer 脱敏摘要和主产物 ref；隐藏 `/workbench/as_c63b713b-06c7-41be-8961-c49b37f88709/artifact%3A8abdec61952740248e21a49a45517afd` 可打开同一产物；`/chat/44` 旧会话显示只读 notice，不展示可执行 retry；三条页面扫描均未命中 raw rows、query_plan、field_patch、direct_sql、llm_sql 或 SELECT 泄露。
- retry 闸门：临时 `as_8829d210-687c-4ccd-a88e-d5e94b046b15` 点击 Workbench `重试` 能触发 `/api/workbench/actions/retry` 200 并返回 `accepted=true` 与业务级 `run_request`，随后进入 `/api/chat/stream` 并记录 `workbench.retry_requested -> retry.started -> retry.fallback_to_whole_task -> dataset.query.completed`；完整 `answer.completed` 未重新声称通过，因为第一次验收脚本刷新页面打断 SSE，第二次点击时本地 Postgres 已停止监听 `localhost:5432`。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_workbench_view_api.py tests/test_workbench_retry_actions.py -q`，14 条通过；执行 `cd datalogue-web && npm run test -- src/components/workbench-panel.test.jsx src/components/workbench-route.test.jsx src/assistant/workbench-api.test.js`，13 条通过；`GET /api/workbench/artifact/artifact%3A8abdec61952740248e21a49a45517afd?thread_id=as_c63b713b-06c7-41be-8961-c49b37f88709` 从 404 修复为 200。
- 残留风险：当前本地 Postgres/OrbStack 未运行，无法继续做 C3-P2 retry 完整完成态的真实浏览器复验；完整 `retry.checkpoint_restored -> answer.completed` 仍以 C3-P1 真实浏览器记录和 C3-P2 自动化闸门作为当前证据，恢复数据库服务后应再补一次页面点击到 completed 的复验。

### 2026-06-30 17:05 · C3-P2 PR1 真实浏览器 Retry Completed 复验

- 涉及文件：`docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md`、`.codex/project-memory.md`
- 关键改动：恢复真实 MySQL 数据源 `retail_test_mysql` 后，重新种入基于完整 checkpoint 上下文的 `as_*` failed 会话，使用真实浏览器在 Chat 右侧 Workbench 点击 `重试`，完整跑通 `/api/workbench/actions/retry -> /api/chat/stream -> Workbench Panel completed`；本次没有改业务代码，只补验收证据和项目记录。
- 真实验收：复验线程 `thread_id=as_e5ccbdd5-d026-45cc-b6bd-720bcae88dff`、原 retry checkpoint `checkpoint://c3-p2-browser-answer-ef401505/query_context_ready`；页面最终显示 `已完成`、`retry.checkpoint_restored -> dataset.query.completed -> retry.completed -> answer.completed`，主产物 `artifact:4359f70b36344dfeb07afa884f81bbe1`、报告占位 `artifact:ae88e62df89f44d2be8bcab5e1dd4f70`、trace `0afae92c6ece62037d78e9a7e21e84c8`、新 checkpoint `checkpoint://conv-43-msg-125/query_context_ready`。
- 后端核验：AgentScope mirror 中同一 thread 持久化 `assistant failed -> assistant running -> user completed -> assistant completed`，events 包含 `workbench.retry_requested`、`retry.started`、`retry.checkpoint_restored`、`dataset.query.completed`、`retry.completed`、`answer.completed`；Workbench View Model 返回 `status_summary.status=completed` 和同一 primary artifact ref。
- 验证方式：真实浏览器页面 DOM 扫描未命中 `raw_rows/raw_result/query_plan/field_patch/direct_sql/llm_sql/SELECT`；随后执行后端 C3-P2 验收 pytest、前端 Workbench/Chat 相关测试、`npm run lint`、`npm run build` 和 `git diff --check`。
- 残留风险：本次复验确认浏览器 retry 到 completed 和 refs 持久化一致；Langfuse UI 仍受本地登录权限限制，后续如要做人工 UI 深链核对，需要先登录对应 Langfuse 项目。

### 2026-06-30 17:35 · C3-P2 Retry Completed 自动化 Harness

- 涉及文件：`datalogue-api/tests/test_c3_workbench_acceptance.py`、`datalogue-api/tests/workbench_retry_harness.py`、`docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md`、`.codex/project-memory.md`
- 关键改动：新增内部-only `run_workbench_retry_completed_harness()`，把手工浏览器复验动作固化为 pytest 可复现流程：构造 `as_*` failed 会话和 retry checkpoint，调用 `POST /api/workbench/actions/retry`，用返回的业务级 `run_request` 驱动 `/chat/stream` checkpoint restore，再拉取 Workbench View Model 断言 completed、primary artifact、trace/checkpoint refs 和事件顺序。
- TDD 记录：先新增 `test_browser_retry_completed_harness_replays_workbench_click_to_completed` 并确认 RED 失败为 `ModuleNotFoundError: No module named 'workbench_retry_harness'`；随后实现 harness，单测转 GREEN。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_c3_workbench_acceptance.py::test_browser_retry_completed_harness_replays_workbench_click_to_completed -q`，1 条通过；执行 `cd datalogue-api && python3 -m pytest tests/test_c3_workbench_acceptance.py -q`，5 条通过。
- 残留风险：该 harness 复刻浏览器点击后的 API/stream/Workbench 状态闭环，但不启动真实浏览器、不连接真实 MySQL；真实浏览器和真实数据源复验仍按发布前手工闸门保留。

### 2026-06-30 18:19 · C3-P2 PR2 Workbench 状态体验补齐

- 涉及文件：`datalogue-web/src/components/workbench-panel.jsx`、`datalogue-web/src/components/workbench-panel.test.jsx`、`datalogue-web/src/styles.css`、`.codex/project-memory.md`
- 关键改动：补齐 Workbench 发布可用性第一项状态体验：空线程显示无产物/无动作说明；失败态诊断摘要明确 retry 可用性和禁用原因；running 态显示轮询提示与完成后自动刷新说明；artifact drawer 独立承载 loading、404、无权限和非当前 thread 产物错误，不再把抽屉错误升级为整个工作台不可用。
- TDD 记录：先新增 `workbench-panel.test.jsx` 状态体验用例并确认 RED，失败点为缺少空态 section、running 轮询提示和 drawer 内部 loading/error；随后实现最小组件状态与样式，定向测试转 GREEN。
- 验证方式：执行 `cd datalogue-web && npm test -- workbench-panel.test.jsx`，12 条通过；执行 `cd datalogue-web && npm test -- workbench-panel.test.jsx workbench-route.test.jsx`，13 条通过；执行 `cd datalogue-web && npm run lint` 通过，保留 15 个既有 warning；执行 `cd datalogue-web && npm run build` 通过，仅保留既有 chunk size warning；执行 `git diff --check` 通过；内置浏览器打开 `http://localhost:5173/chat/as_e5ccbdd5-d026-45cc-b6bd-720bcae88dff`，确认 Workbench completed、产物抽屉可关闭并从 artifact ref 重新打开、console error/warn 为 0、页面扫描未命中 `raw_rows/raw_result/query_plan/field_patch/direct_sql/llm_sql/SELECT`。
- 残留风险：本次只收口 Workbench 前端状态体验；C3-P2 PR2 后续仍需补 API 级 Langfuse trace 查询断言和发布 checklist，真实浏览器 retry 手工闸门仍按发布前 checklist 保留。

### 2026-06-30 18:32 · C3-P2 PR2 Provider-neutral Observability Gate

- 涉及文件：`datalogue-api/app/services/observability/traces.py`、`datalogue-api/tests/test_observability.py`、`datalogue-api/tests/test_c3_workbench_acceptance.py`、`datalogue-api/tests/workbench_retry_harness.py`、`.codex/project-memory.md`
- 关键改动：把原“API 级 Langfuse 闸门”收口为 provider-neutral observability contract；`GET /api/observability/traces/{trace_id}` 新增 `provider`、`local_events` 和 `observability_contract`，统一断言 `workbench.retry_requested -> retry.started -> retry.checkpoint_restored -> dataset.query.completed -> answer.completed` 以及 `thread_id/conversation_id/checkpoint_ref/artifact_ref`，不绑定 Langfuse 内部字段名，后续可由 OTel adapter 填同一契约。
- harness 改动：C3-P2 browser retry completed harness 写入 `ObservabilityTraceIndex` 后直接查询 `/api/observability/traces/{trace_id}`，并断言 contract passed；模拟成功 retry 流补 `dataset.query.completed` trace-only envelope，保证自动化闸门证明数据查询阶段存在，而不是只看到最终回答。
- TDD 记录：先新增 API contract 单测和 harness trace detail 断言，RED 分别为缺少 `provider` 响应字段、harness 结果缺少 `observability_detail`；实现后再暴露缺失 `dataset.query.completed`，补齐 trace-only event 后转 GREEN。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_observability.py::test_query_audit_trace_list_and_detail tests/test_observability.py::test_query_audit_trace_detail_exposes_provider_neutral_contract -q`，2 条通过；执行 `cd datalogue-api && python3 -m pytest tests/test_c3_workbench_acceptance.py -q`，5 条通过；执行 `cd datalogue-api && python3 -m py_compile app/services/observability/traces.py tests/workbench_retry_harness.py tests/test_observability.py tests/test_c3_workbench_acceptance.py` 通过；执行 `git diff --check` 通过。
- 残留风险：本次不要求浏览器登录 Langfuse UI；发布前 checklist 仍需保留 UI 人工核对项。若后续切换 OTel，应只替换 provider adapter，保持 `observability_contract` 响应和 harness 断言不变。

### 2026-07-01 09:16 · C3-P2 发布 Checklist 收口

- 涉及文件：`docs/superpowers/plans/2026-06-30-c3-p2-workbench-productization.md`、`.codex/project-memory.md`
- 关键改动：在 C3-P2 Workbench productization plan 中新增发布 checklist，覆盖数据源容器依赖、本地服务端口、浏览器 retry 手工闸门、自动化 harness、旧会话只读策略、隐藏 Workbench route 策略和 provider-neutral observability 发布口径；Final Review Gate 增加 checklist owner/status 确认项。
- 发布边界：自动化闸门以 `/api/observability/traces/{trace_id}` 的 `observability_contract` 为准，不绑定 Langfuse 内部字段名；Langfuse UI 登录核对保留为发布前人工 checklist，无权限时必须记录未完成，不能把后端 API 成功写成 UI 通过。
- 验证方式：执行 `git diff --check` 通过；文档检查确认“最新详细记录”保持 10 条，较早 C3-P0 真实浏览器 E2E 记录已压缩进历史压缩记录。
- 残留风险：本次是文档和项目记忆收口，不重新运行浏览器 retry 或自动化测试；发布前仍需按 checklist 逐项补 owner/status 和真实环境证据。

### 2026-07-01 10:21 · AS-R0 P0 Agentic Shell 契约层骨架

- 涉及文件：`datalogue-api/app/services/agentic_shell.py`、`datalogue-api/app/services/agentic_bi_tools.py`、`datalogue-api/tests/test_agentic_shell_contract.py`、`.codex/project-memory.md`
- 关键改动：新增 `DatalogueAgenticShell` AS-R0 契约层，固定 registry 只启用 `bi_lead_agent`，`report_agent/python_agent/audit_agent` 作为 disabled placeholder；新增 AS-R0 BI 业务能力名、当前可注册工具白名单、reserved/disabled 工具列表、上下文投影和 fail-closed 输出清洗；新增 `BIAtomicToolProvider` 安全骨架，提供 `get_dataset_status`、`list_candidate_assets`、artifact ref 写入与 artifact 摘要能力，其中 `list_candidate_assets` 第一阶段不使用 question 召回，只返回 blueprint/metric/dimension/metadata_schema_summary 安全目录摘要。
- 安全边界：本阶段不替换 `/chat/stream`，不修改旧 `AgentScopeShellAdapter` 的 C3 外层验证线；SQL、schema 全量、raw rows、query_plan、repair_patch 和 blueprint 主体仍禁止进入 Agent 上下文，DatasetAgent 后续只能生成 DSL，不能让 Agent 直接生成最终可执行 SQL。
- TDD 记录：先新增 `test_agentic_shell_contract.py` 并确认 RED 为 `ModuleNotFoundError: No module named 'app.services.agentic_bi_tools'`；实现契约后暴露 `ProjectedContext` 空字段 dump 和 blueprint 摘要被清洗的问题，分别补默认 `exclude_none` 与上下文/输出禁用键拆分后转 GREEN；review 后补 camelCase `queryPlan/repairPatch`、`rows`、`fields` 和物理字段串脱敏断言，并把未实现的 compile/execute/create artifact 从当前 runtime allowed tools 移到 reserved/disabled。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_agentic_shell_contract.py -q`，4 条通过；执行 `cd datalogue-api && python3 -m pytest tests/test_agentscope_shell_adapter.py tests/test_bi_workbench_tool.py -q`，5 条通过；执行 `cd datalogue-api && python3 -m py_compile app/services/agentic_shell.py app/services/agentic_bi_tools.py tests/test_agentic_shell_contract.py` 通过；执行 `git diff --check` 通过。
- 残留风险：AS-R0 P0 当前只是契约层和安全 provider 骨架，尚未把 `/chat/stream` 主链迁到 AgentScope Runtime 驱动；`compile_dsl_to_sql`、`execute_compiled_query`、`repair_dsl` 等仍需在后续 P0/P1 中接入 DatasetAgent Runtime 的真实受控工具实现。

### 2026-07-01 10:31 · AS-R0 P0 Runtime 边界适配契约

- 涉及文件：`datalogue-api/app/services/agentscope_runtime_driver.py`、`datalogue-api/tests/test_agentscope_runtime_driver_contract.py`、`.codex/project-memory.md`
- 关键改动：新增 `DatalogueAgentScopeRuntimeDriver`，把 `DatalogueAgenticShell.prepare_turn()` 产物转换成 AgentScope Runtime 接入前的安全边界契约；Runtime contract 只包含 `projected_context`、当前可注册的 `BIAtomicToolProvider` tool registry、业务能力名、disabled tools 和 disabled agents，不包含 callable、schema、SQL、raw rows、query_plan 或旧 `ask_bi` 外层桥接。
- 安全边界：第二刀仍不替换 `/chat/stream`、不启动真实 AgentScope runner、不修改 `AgentScopeShellAdapter`；非 BI placeholder 任务 fail-closed，`tool_registry=[]`，后续只有显式启用对应 Agent 和工具实现后才能进入 Runtime。
- TDD 记录：先新增 `test_agentscope_runtime_driver_contract.py` 并确认 RED 为 `ModuleNotFoundError: No module named 'app.services.agentscope_runtime_driver'`；实现 driver 后转 GREEN，覆盖只接受 `AgenticShellTurnContract`、BI atomic tool registry 不含 `ask_bi`、上下文投影脱敏、report placeholder 无工具四类断言。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_agentscope_runtime_driver_contract.py -q`，4 条通过；后续合并验证继续覆盖 Agentic Shell skeleton、旧 adapter 和 ask_bi 契约。
- 残留风险：当前只是 Runtime 边界 contract，尚未接 AgentScope SDK runner，也未把 DatasetAgent compile/execute/create artifact 工具注册为可执行；下一步应在 feature flag 下做 `/chat/stream -> AgenticShell -> Runtime driver` 的只读/影子路径对齐。
