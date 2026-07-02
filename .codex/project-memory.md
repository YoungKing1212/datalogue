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

### 2026-06-15 至 2026-06-18 SubAgent/多轮/DSL 基础收口

- 建立 SubAgent 查询规划层 v1/v2、语义资产渐进式披露、DSL 提示词和 Langfuse Trace，统一 LiteLLM SDK 并修复 Think 标签泄露、慢节点日志和空 DSL 错误提示。
- 建立 Thread Memory、QueryTaskCapsule、ConversationState、多轮槽位承接与 `last_success_task` 最小快照，支持明细追问、数据集选择后恢复原问题和 planner 截断/非法 JSON 时保留槽位。
- 打通 SubAgent/DSL 消费 QueryTaskCapsule、Message Gateway SSE 可观测、历史对话 SQL/结果展示、蓝图结构化视图、ArtifactStore/query_artifacts DB 兜底、fan-out 和 A2A Runner 基础。
- 收口日志明细模板 fallback、LiteLLM 流式报告、assistant-ui 本地线程映射、日志数据集姓名过滤追问、蓝图缺参抢占明细查询、内联产物表格渲染；撤销从当前自然语言硬猜人名的 fallback。

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

### 2026-07-01 15:45 Langfuse 技术栈移除

- 删除 Langfuse Python 依赖、Docker Compose 服务、观测 API 挂载、prompt/feedback 外部同步和前端 Trace/查询审计入口；`DatalogueTracer` 改为本地 no-op 兼容壳，运行时代码/依赖/部署/前端源码不再包含 Langfuse 调用链。
- 验证覆盖 Langfuse 残留扫描、observability/conversation pytest、后端 compileall、前端 lint/build；历史文档保留 Langfuse 作为历史事实，当前链路改以后端日志、Workbench refs、SSE 和 DB 状态为主。

### 2026-07-01 15:54 DatasetAgent Runtime 字段缺失受控阻断

- `BIAtomicToolProvider.execute_compiled_query()` 将 MySQL/SQLite/PostgreSQL 字段缺失异常统一收敛为 `FIELD_NOT_FOUND`，AgentScope bridge 只回填 `status=blocked/code=FIELD_NOT_FOUND` 和固定安全摘要。
- 验证覆盖 provider 与 AgentScope bridge 字段缺失回归，确保 DB 异常原文、SQL、schema、raw rows 和 repair patch 主体不穿透到 DatasetAgent Runtime / AgentScope SDK bridge。
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

### 2026-06-30 C3-P2 Workbench 产品化状态模型

- C3-P2 PR1 启动 Workbench 产品化状态模型：后端新增 `WorkbenchStatusSummary`，统一表达 `empty/running/completed/failed/interrupted/read_only`、actionable、primary artifact、retry checkpoint 和 trace ref。
- Workbench Panel 使用后端 `status_summary` 渲染状态卡、空态、失败诊断摘要、Artifact 详情抽屉和 retry 后主产物自动聚焦；artifact detail 增加 thread ownership scope，用户可见层继续禁止 SQL/schema/raw rows/query_plan/field_patch。
- C3-P2 PR1 浏览器验收闸门补证修复 artifact detail ownership gate，真实 `as_*` completed thread 和隐藏 Workbench route 可打开同一脱敏产物；旧 `/chat/44` 仍只读，页面扫描未命中 raw rows、query_plan、field_patch、direct_sql、llm_sql 或 SELECT 泄露。
- C3-P2 PR1 真实浏览器 retry completed 复验确认 `/api/workbench/actions/retry -> /api/chat/stream -> Workbench Panel completed` 跑通，refs、checkpoint、trace 和 mirror events 对齐。
- 验证覆盖后端 Workbench/ViewModel/retry/event/retry checkpoint pytest、前端 Workbench/route/chat/artifact/thread-list/workbench-api 测试、py_compile、lint/build 和 `git diff --check`。
- C3-P2 Retry Completed 自动化 Harness 将手工浏览器 retry 复验固化为内部-only pytest：构造 `as_*` failed 会话和 checkpoint，驱动 `/api/workbench/actions/retry -> /api/chat/stream` checkpoint restore，并断言 Workbench completed、primary artifact、trace/checkpoint refs 和事件顺序。
- C3-P2 PR2 补齐 Workbench 状态体验：空态、失败诊断、running 轮询提示、artifact drawer 内部 loading/404/无权限错误和 completed 产物重新打开；前端测试、lint/build 和真实浏览器扫描均通过。
- C3-P2 PR2 Provider-neutral Observability Gate 将 `/api/observability/traces/{trace_id}` 收敛为 provider-neutral contract，统一断言 `workbench.retry_requested -> retry.started -> retry.checkpoint_restored -> dataset.query.completed -> answer.completed` 和关键 refs；自动化 harness 改为查询该 contract，不绑定 Langfuse 内部字段。
- C3-P2 发布 Checklist 收口覆盖数据源容器、本地端口、浏览器 retry、自动化 harness、旧会话只读、隐藏 Workbench route 和 provider-neutral observability 发布口径；Langfuse UI 登录核对保留为人工 checklist，不把后端 API 成功写成 UI 通过。

### 2026-07-01 AS-R0 P0/P1 初始接入

- AS-R0 P0 Agentic Shell 契约层骨架建立：`DatalogueAgenticShell` 固定只启用 `bi_lead_agent`，Report/Python/Audit 作为 disabled placeholder；新增 BI 业务能力名、工具白名单、上下文投影、输出清洗和 `BIAtomicToolProvider` 安全目录摘要骨架，保留 `/chat/stream` 主链不替换。
- AS-R0 P0 Runtime 边界适配建立：`DatalogueAgentScopeRuntimeDriver` 将 Shell turn contract 投影成 Runtime 可见安全契约，只包含 projected context、BI atomic tool registry、业务能力、disabled tools/agents，不启动真实 AgentScope runner、不调用旧 `ask_bi`。
- AS-R0 P1-prep Chat Stream Runtime Shadow 建立：新增默认关闭的 `AS_R0_AGENTIC_RUNTIME_SHADOW_ENABLED`，开启后只把 Shell/Runtime boundary 安全摘要写入 AgentScope mirror metadata，不改变 SSE 输出和现有主链执行。
- AS-R0 正式 PR 计划口径收口：`docs/superpowers/plans/2026-07-01-as-r0-agentic-shell-formal-pr-plan.md` 成为 PR0.1-PR0.4、PR1.1-PR1.5、P2.1-P2.4 唯一执行口径；任何新增或移动 scope 必须先进入 `Proposed Plan Changes` 等待用户审核。
- AS-R0 PR0.1 架构文档与迁移闸门完成：C3 Workbench / mirror 被明确标注为 AS-R0 foundation，不是 AgentScope Runtime ownership 完成态；P0/P1/P2 迁移闸门和禁暴露边界进入 C3 架构文档、spec、计划和验收记录。
- AS-R0 PR0.2 Agentic Shell Writer 接口完成：`DatalogueAgenticShell` 新增 event/action/checkpoint writer interface、Noop writer 和 InMemory writer，写回前统一走 payload sanitizer。
- AS-R0 PR0.3 BI Atomic Tool Provider 完成：补齐 compile/execute/create artifact 原子工具，SQL 只在 compile/execute 内部通过私有 handle 流转，Agent 可见响应只返回状态、句柄、artifact ref 和摘要。
- AS-R0 PR0.4 安全测试矩阵完成：覆盖 Shell context、BI tool response、SSE 用户可见 payload、trace_only 随流 payload、AgentScope mirror metadata/event 和 Workbench View Model，统一阻断 SQL/schema/raw rows/query_plan/RepairPatch/blueprint body 等禁区内容。
- AS-R0 PR1.1 Runtime adapter 完成：`/chat/stream` 入口经 `DatalogueAgenticShell.run_turn()` 生成 Shell turn contract 后委托既有流式链路，保持 SSE final payload、mirror 写入和 legacy 回退兼容。
- AS-R0 PR1.2 BI LeadAgent 接入 Shell：补齐 `AgenticShellAction`、LeadAgent action routing 和 Runtime `lead_agent_action` 投影；BI LeadAgent 只开放 `query_dataset/query_multiple_datasets`，Report/Python/Audit 继续 disabled placeholder。
- AS-R0 PR1.3 DatasetAgent tool-call runtime 完成：新增固定 BI 原子工具序列和 `DatasetAgentToolCallRuntime`，SQL 通过 private compiled handle 与 ArtifactStore 流转，Agent/用户可见层只暴露状态、artifact ref 和摘要。
- AS-R0 PR1.4 checkpoint/retry writer 迁移完成：`AgentScopeMirrorShellWriter` 接管 Workbench retry action 与 Chat SSE event projection，写回前统一经 Agentic Shell sanitizer 清洗。
- AS-R0 PR1.5 双路径灰度 parity 完成：无论 Shell runtime wrapper 或 legacy path，`_stream_chat` 都保持相同 final payload、artifact refs 和 trace contract；该层只固化灰度验收，不默认开启新 runtime 或替换 DatasetAgent 主链。
- AS-R0 P2.1 `/chat/stream` transport adapter 收缩完成：新增 `DatalogueChatStreamRuntime` 和 hooks，把单轮/多轮 wrapper lifecycle 从 `chat.py` 迁入 service，`chat.py` 只保留 settings、hook 装配和 SSE 转发。
- AS-R0 P2.2 legacy adapter / ask_bi compatibility 收敛完成：`AgentScopeShellAdapter` 与 `BIWorkbenchTool` 标记为 legacy compatibility，`ask_bi` 不再作为 AS-R0 新主链工具，不加回 BI atomic whitelist。
- AS-R0 P2.3 future tools disabled/admin-gated contract 完成：future tools 以结构化 disabled/admin-gated spec 透传到 Shell/Runtime 边界，不进入可执行 tool registry，为后续 optional agent gate 留出安全口径。
- AS-R0 P2.4 业务 Agent 受控启用完成：Report/Python/Audit optional agents 默认 disabled，显式启用时只开放单一白名单工具，Runtime registry 只注册已启用业务 Agent。
- DatasetAgent Runtime direct 测试入口建立：本地/测试环境新增 `POST /api/chat/dataset-runtime/direct`，用最小 routing/route_decision/lead_agent_context 直通受控 DatasetAgent Runtime，作为压测 Runtime 底座；production 禁用，后续仍需替换真正 DatasetAgent-owned planner。
- AS-R0 PR1.3-b BI atomic runtime 直接接管执行核心完成：移除两个主链灰度开关，`/chat/stream` singleturn 默认进入 Agentic Shell，单数据集 BI 查询绕过 legacy `build_workflow(db)` 并由受控 DatasetAgent tool-call runtime 串起 compile、execute、artifact summary 和 final payload。
- AS-R0 PR1.3-c AgentScope 2.0 SDK Runtime Bridge 完成：`AgentScopeDatasetRuntimeBridge` 通过 `RequireExternalExecutionEvent -> ToolResultBlock -> ExternalExecutionResultEvent` 驱动 DatasetAgent external tools，`DatasetAgentScopeExternalTool(ToolBase)` 使用 permission hook 和 ToolMiddlewareBase 日志，安全边界继续禁止 SQL/schema/raw rows/query_plan/RepairPatch/blueprint body 外泄。

## 高价值判断

- Datalogue 当前业务链路不依赖 Redis 保存多轮业务状态；`last_success_task`、`conversation_state.subagent_capsules` 和 query artifacts 的真相在数据库或应用 ArtifactStore 路径，Langfuse/BullMQ Redis key 不能当成业务状态依据。
- 多轮追问不要从当前自然语言残留硬猜 `person`；应依赖 LLM 结构化槽位、上一轮已确认过滤或澄清。
- 数据集上下文压缩优先采用“轻量候选资产目录 + 按需详情补合”，不要一开始把完整字段、SQL、样例行全部塞进 prompt。
- `.env.example` 中要区分“已被 Settings 读取并生效的配置”和“尚未接入的候选项”。
- `localhost:8080` 等地址返回应用层 `Unauthorized` 时，优先判断服务已启动，继续排查认证、代理或路由，不要直接判定服务未启动。

## 最新详细记录

### 2026-07-01 15:58 · `/chat/stream` 单数据集直通 DatasetAgent Runtime

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_as_r0_atomic_runtime_cutover.py`、`.codex/project-memory.md`
- 关键改动：在 message gateway 之后、LeadAgent span 之前新增单数据集直通分支；当请求显式携带 `dataset_id`、无澄清响应、无 pending clarification，且 gateway 判定为新查询时，直接构造最小 `routing/route_decision/lead_agent_context/initial_state` 并调用既有 `_stream_dataset_atomic_runtime_return()`，不再进入 `build_lead_agent_context()`、`route_query_intent()` 或 legacy `build_workflow(db)`。
- 安全边界：直通路径只覆盖最窄的新查询；dataset select、clarify、pending clarification、interpret result 和多轮 refinement 继续走原控制面，避免跳过现有澄清/多轮保护；用户可见 SSE 仍复用 atomic runtime final、artifact ref 和清洗逻辑，不暴露 SQL、schema、raw rows 或 query_plan。
- TDD 记录：先加严 `test_chat_stream_atomic_runtime_bypasses_legacy_graph_core_without_flag`，让 `build_lead_agent_context()` 与 `route_query_intent()` 被调用即失败，确认 RED 暴露主链仍进入 LeadAgent；新增直通判断和上下文构造后转 GREEN。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_as_r0_atomic_runtime_cutover.py -q`，2 条通过、2 个既有 warning；执行 `python3 -m compileall -q app/api/chat.py tests/test_as_r0_atomic_runtime_cutover.py` 通过；执行 `git diff --check -- datalogue-api/app/api/chat.py datalogue-api/tests/test_as_r0_atomic_runtime_cutover.py` 通过；清理 `.DS_Store`、`__pycache__/`、`*.pyc` 缓存后排除 `.venv/node_modules/.worktrees/.git` 的缓存扫描为 0。
- 残留风险：多数据集 fanout、澄清、多轮 refinement 和内部 subagent API 仍保留 legacy Graph/LeadAgent 分支；direct runtime 的 DSL generator 仍复用 `recall_candidate_assets + plan_query`，真正 DatasetAgent-owned planner 仍需后续替换。

### 2026-07-01 16:08 · AgentScope DatasetAgent 暴露 `repair_dsl`

- 涉及文件：`datalogue-api/app/services/agentic_shell.py`、`datalogue-api/app/services/agentic_bi_tools.py`、`datalogue-api/app/services/agentscope_dataset_runtime.py`、`datalogue-api/tests/test_agentic_shell_contract.py`、`datalogue-api/tests/test_agentscope_dataset_runtime_bridge.py`、`datalogue-api/tests/test_agentscope_runtime_driver_contract.py`、`.codex/project-memory.md`
- 关键改动：`repair_dsl` 从 AS-R0 future disabled tools 移入 BI tool whitelist 和 AgentScope external tool 序列；`BIAtomicToolProvider` 保存私有 QueryPlan/编译上下文和字段缺失失败上下文，新增 `repair_dsl(compiled_query_ref)`，字段缺失后按同表同业务标签候选修复 DSL 并返回新的 private compiled handle；AgentScope bridge 动态状态机允许 `execute_compiled_query -> FIELD_NOT_FOUND -> repair_dsl -> execute_compiled_query`。
- 安全边界：Agent 只能向 `repair_dsl` 传当前会话的 `compiled_query_ref`，不能传 RepairPatch body、schema、SQL 或字段候选；`repair_dsl` 仅在上一次 execute 返回 `FIELD_NOT_FOUND` 且本会话未修复过时允许调用一次；ToolResultBlock 只回填 `status=repaired`、新 `compiled_query_ref`、`agent_context` 和 `repair_count`，不暴露旧字段名、新字段名、SQL、schema、raw rows、query_plan 或 RepairPatch 主体。
- TDD 记录：先把 Shell 白名单测试和 AgentScope bridge 字段缺失测试改成目标行为，确认 RED 分别为 `repair_dsl` 仍不在 allowed tools、bridge 对 `repair_dsl` 返回 DENIED；实现 provider 修复 handle、bridge permission/dynamic sequence 后转 GREEN；同步 Runtime driver disabled future tools 测试移除 `repair_dsl` 旧期望。
- 验证方式：执行 `datalogue-api/.venv/bin/python -m pytest datalogue-api/tests/test_agentic_shell_contract.py datalogue-api/tests/test_agentscope_dataset_runtime_bridge.py -q`，22 条通过、3 个既有 warning；执行 `datalogue-api/.venv/bin/python -m pytest datalogue-api/tests/test_agentscope_runtime_driver_contract.py datalogue-api/tests/test_as_r0_security_matrix.py datalogue-api/tests/test_agentic_dataset_runtime.py -q`，19 条通过、3 个既有 warning；执行 `datalogue-api/.venv/bin/python -m compileall -q datalogue-api/app/services/agentic_shell.py datalogue-api/app/services/agentic_bi_tools.py datalogue-api/app/services/agentscope_dataset_runtime.py datalogue-api/tests/test_agentic_shell_contract.py datalogue-api/tests/test_agentscope_dataset_runtime_bridge.py` 通过；`git diff --check` 通过。
- 残留风险：当前修复候选来自本次编译上下文中的同表同业务标签字段，尚未接入完整 `repair_patch.py` 的语义裁判、类型组兼容和持久化 patch/ref；真实 `project_manager.ZTGZL` 能否自动修复取决于 schema context 中是否已有同业务标签的替代字段。

### 2026-07-01 16:31 · BI 原子工具 ToolBase/Toolkit 收口

- 涉及文件：`datalogue-api/app/services/bi_tools/__init__.py`、`datalogue-api/app/services/bi_tools/atomic.py`、`datalogue-api/app/services/agentic_bi_tools.py`、`datalogue-api/app/services/agentic_dataset_runtime.py`、`datalogue-api/app/services/agentscope_dataset_runtime.py`、`datalogue-api/app/services/agentscope_runtime_driver.py`、`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_agentscope_dataset_runtime_bridge.py`、`datalogue-api/tests/test_agentscope_runtime_driver_contract.py`、`datalogue-api/tests/test_as_r0_atomic_runtime_cutover.py`、`.codex/project-memory.md`
- 关键改动：新增 `app.services.bi_tools` 包，`get_dataset_status/list_candidate_assets/compile_dsl_to_sql/execute_compiled_query/repair_dsl/create_query_artifact/get_artifact_summary` 均迁为 `ToolBase` 子类，并由 `DatalogueBIAtomicToolkit` / AgentScope `Toolkit` 容器统一暴露；`AgentScopeDatasetRuntimeBridge`、`DatasetAgentToolCallRuntime` 和 `/chat` 主链改为依赖 `toolkit=`；旧 `BIAtomicToolProvider` 仅保留为兼容门面并委托 Toolkit 执行。
- 安全边界：compiled query 私有句柄、SQL、query_plan 主体、字段缺失 repair context 和 artifact 写入状态仍只保存在 Toolkit 受控上下文；ToolBase permission 继续 fail-closed 拦截未白名单工具、敏感入参、缺少 DSL 或伪造 compiled handle；Runtime registry 不再把 Provider 作为主工具提供方。
- TDD 记录：先新增 `test_bi_atomic_tools_are_toolbase_classes_exposed_by_toolkit`，确认 RED 为缺少 `app.services.bi_tools`；实现独立工具包、Provider 兼容门面和 Runtime 依赖反转后转 GREEN，并同步 direct endpoint 与 runtime driver 测试口径。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_agentscope_dataset_runtime_bridge.py tests/test_agentic_dataset_runtime.py tests/test_agentscope_runtime_driver_contract.py -q`，21 条通过、2 个既有 warning；执行 AS-R0 宽回归 `tests/test_agentic_shell_contract.py tests/test_as_r0_security_matrix.py tests/test_as_r0_atomic_runtime_cutover.py tests/test_agentscope_chat_bridge.py tests/test_agentscope_dataset_runtime_bridge.py tests/test_agentic_dataset_runtime.py tests/test_agentscope_runtime_driver_contract.py -q`，64 条通过、6 个既有 warning；执行 `python3 -m compileall app/services/bi_tools app/services/agentic_bi_tools.py app/services/agentic_dataset_runtime.py app/services/agentscope_dataset_runtime.py app/services/agentscope_runtime_driver.py app/api/chat.py` 和 `git diff --check` 通过。
- 残留风险：旧 `BIAtomicToolProvider` 名称仍因测试和部分兼容调用保留；确认外部调用已迁到 Toolkit 后，可另起清理 PR 删除 Provider 兼容门面并同步文档/测试中的历史命名。

### 2026-07-01 16:44 · direct 入口接入 AgentScope repair_dsl 链路

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/app/services/agentscope_dataset_runtime.py`、`datalogue-api/app/services/agentscope_middlewares/dataset_tool_logging.py`、`datalogue-api/app/services/agentscope_middlewares/safe_log_summary.py`、`datalogue-api/tests/test_as_r0_atomic_runtime_cutover.py`、`datalogue-api/tests/test_agentscope_dataset_runtime_bridge.py`、`.codex/project-memory.md`
- 关键改动：`POST /api/chat/dataset-runtime/direct` 从旧 `DatasetAgentToolCallRuntime` 切到 `AgentScopeDatasetRuntimeBridge.run_direct_query()`；direct 入口仍复用现有 DSL generator，但 compile、execute、`FIELD_NOT_FOUND` 后的 `repair_dsl`、重跑、artifact summary 均通过 AgentScope external execution event 状态机执行；返回新增 `execution_path=agentscope_dataset_runtime_direct` 和 `tool_results`，同时保留 `tool_calls` 兼容别名；后端日志收敛为 ToolMiddlewareBase 层工具调用安全摘要，不再补 event-level `DatasetRuntimeLoggingMiddleware`。
- 安全边界：direct 入口继续仅限非 production；`repair_dsl` 仍只能使用当前会话 `compiled_query_ref`，不能由调用方传 SQL/schema/query_plan/RepairPatch；ToolResult 只返回状态、refs、row/column count 和受控错误码；工具调用日志直接使用 AgentScope 2.0 `ToolMiddlewareBase` 和 `ToolBase(middlewares=...)`，事件回填层不再使用 AgentScope `MiddlewareBase` 单独打印。
- TDD 记录：先新增 direct endpoint repair 测试并确认 RED 为旧 `execution_path=dataset_agent_runtime_direct` 且无 `repair_dsl`；实现 bridge direct 驱动和 route 接线后转 GREEN；同步修正旧 direct 旁路测试为新 helper 口径，并为 AgentScope SDK middleware API 差异补兼容测试。
- 验证方式：执行 `datalogue-api/.venv/bin/python -m pytest datalogue-api/tests/test_as_r0_atomic_runtime_cutover.py datalogue-api/tests/test_agentscope_dataset_runtime_bridge.py datalogue-api/tests/test_agentic_shell_contract.py datalogue-api/tests/test_agentscope_runtime_driver_contract.py -q`，33 条通过、5 个既有 warning。
- 残留风险：`/chat/stream` 主链仍未切到 `AgentScopeDatasetRuntimeBridge`；direct endpoint 可用于你现在手工验证 repair_dsl，但生产流式问数要看到同样日志还需要后续把 stream atomic runtime 也切到 bridge。

### 2026-07-01 16:49 · 删除 Dataset Runtime event-level Middleware 日志

- 涉及文件：`datalogue-api/app/services/agentscope_middlewares/dataset_runtime_logging.py`、`datalogue-api/app/services/agentscope_middlewares/dataset_tool_logging.py`、`datalogue-api/app/services/agentscope_middlewares/safe_log_summary.py`、`datalogue-api/app/services/agentscope_middlewares/__init__.py`、`datalogue-api/app/services/agentic_dataset_runtime.py`、`datalogue-api/app/services/agentscope_dataset_runtime.py`、`datalogue-api/tests/test_agentic_dataset_runtime.py`、`docs/test-reports/2026-07-01-as-r0-pr1-3-b.md`、`docs/test-reports/2026-07-01-as-r0-pr1-3-c-agentscope-sdk-runtime.md`、`.codex/project-memory.md`
- 关键改动：删除 `dataset_runtime_logging.py` 和 `DatasetRuntimeLoggingMiddleware(MiddlewareBase)`；旧固定 `DatasetAgentToolCallRuntime` 与 `AgentScopeDatasetRuntimeBridge` 不再为了日志构造/打印 `RequireExternalExecutionEvent` 与 `ExternalExecutionResultEvent`；新增 `safe_log_summary.py` 承接工具日志的安全摘要 helper，`DatasetRuntimeToolLoggingMiddleware(ToolMiddlewareBase)` 继续作为唯一 DatasetAgent Runtime 日志入口。
- 安全边界：日志仍只输出安全计数与标志位，例如 `has_compiled_query_ref`、`has_artifact_ref`、`blocked_*_key_count`；不输出 SQL、schema、raw rows、物理字段、`query_plan` 主体、RepairPatch 主体或 blueprint 主体。
- TDD 记录：先新增/改写测试，确认 RED 为 `DatasetRuntimeLoggingMiddleware` 仍导出且旧 runtime 仍打印 `[agentscope.dataset_runtime.*]`；移除导出、调用和文件本体后转 GREEN。
- 验证方式：定向 RED/GREEN 测试 2 条通过、2 个既有 warning；`tests/test_agentscope_dataset_runtime_bridge.py tests/test_agentic_dataset_runtime.py -q` 16 条通过、2 个既有 warning。
- 残留风险：真实 `agent.reply_stream()` 暂停/回填事件不再单独打印 event-level 日志；后续如要观察外部执行事件，应在 AgentScope SDK 标准 tracing/observability 层新增计划，而不是恢复 Datalogue 自研 Runtime 日志。

### 2026-07-01 18:21 · 过期 Langfuse 文档清理

- 涉及文件：`docs/archive/2026-07-01-langfuse-removal/`、`docs/上下文入口.md`、`docs/数语项目介绍手册.md`、`docs/数语系统设计方案.md`、`docs/main-chain-acceptance-record-template.md`、`docs/llm-eval-baseline-design.md`、`docs/golden-fixture-test-plan.md`、`scripts/export_langfuse_docs_to_docx.py`、`.codex/project-memory.md`
- 关键改动：将 Langfuse 需求、开发、docx 和 metadata schema 专题文档移入归档目录并新增归档说明；当前入口、项目介绍、系统设计和五件套模板不再把 Langfuse、查询审计页、`/api/observability/*` 或 Trace 深链描述为现行能力；评估/fixture 文档改为使用历史 trace 归档、后端日志或 fixture 捕获结果作为样本来源。
- 安全边界：历史验收记录和 C1/C2/C3 设计中的 Langfuse 描述保留为当时事实，不改写历史证据；新任务路由优先按 SSE step、response metadata、Workbench refs、数据库状态和后端日志核对当前链路。
- 验证方式：执行 `rg` 扫描当前入口/手册/模板/脚本中的旧路径、`/audit-query`、`/api/observability`、`ObservabilityTraceIndex`、`langfuse_trace_id` 等引用；执行 `git diff --check` 通过。
- 残留风险：部分历史架构、spec、计划和验收记录仍保留 Langfuse 作为历史上下文；如后续要彻底替换旧 C1/C2/C3 验收口径，需要另起任务按历史/当前边界分层改写。

### 2026-07-01 18:40 · 过期代码第一/第二批清理

- 涉及文件：`datalogue-api/app/api/observability.py`、`datalogue-api/app/services/observability/report.py`、`datalogue-api/app/services/observability/traces.py`、`datalogue-api/app/services/observability/prompt_registry.py`、`datalogue-api/app/services/agentic_bi_tools.py`、`datalogue-api/app/services/agentic_dataset_runtime.py`、`datalogue-api/tests/test_agentic_shell_contract.py`、`datalogue-api/tests/test_as_r0_security_matrix.py`、`datalogue-api/tests/workbench_retry_harness.py`、`datalogue-web/src/components/audit-query.jsx`、`datalogue-web/src/assistant/MyMessage.jsx`、`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/thread-list-adapter.js`、`datalogue-web/src/styles.css`、`scripts/export_user_manual_docx.py`、`scripts/export_user_operation_manual_docx.py`、`.codex/project-memory.md`
- 关键改动：删除未挂载的 `/api/observability` API 文件、报表/trace 服务、前端查询审计页组件和对应样式；消息卡片移除空 `TraceLinkCard` 与 observability 专属 metadata；`BIAtomicToolProvider` 兼容门面删除，测试改为直接使用 `build_bi_atomic_toolkit(...).execute_tool(...)`，`DatasetAgentToolCallRuntime` 构造函数只接受 `toolkit=`；Prompt Registry 收缩为本地 prompt 清单，移除远端同步函数和测试。
- 安全边界：`ObservabilityTraceIndex` DB 模型与 `chat.py` 写入链暂保留，因为旧主链验收仍直接断言该表；Workbench retry harness 不再调用已下线 `/api/observability/traces/{trace_id}`，改为基于本次 stream/persisted events 组装 provider-neutral contract。
- 验证方式：执行 `pytest datalogue-api/tests/test_agentic_shell_contract.py datalogue-api/tests/test_as_r0_security_matrix.py datalogue-api/tests/test_observability.py datalogue-api/tests/test_c3_workbench_acceptance.py -q`，40 条通过、11 个既有 warning；执行 `npm test -- --run src/assistant/chat-adapter.test.js`，12 条通过；执行 `npm run lint` 通过但保留 13 个既有 warning；执行 `npm run build` 通过并保留 Vite chunk size warning；执行残留 `rg` 扫描，当前代码和生成脚本不再引用已删 API、审计页组件、Provider 兼容壳或远端 prompt 同步函数。
- 残留风险：第三批清理应单独处理 `ObservabilityTraceIndex` 模型、迁移、`chat.py` 写入链和旧五件套验收断言；这需要数据库/测试契约级迁移，不能和本次未挂载代码清理混在同一刀里。

### 2026-07-01 20:26 · BI LeadAgent K1 后端契约与 AgentScope 2.0 handoff

- 涉及文件：`datalogue-api/app/models/bi_lead_agent.py`、`datalogue-api/alembic/versions/r2s3t4u5v6w7_add_bi_lead_agent_handoff.py`、`datalogue-api/app/schemas/bi_lead_agent.py`、`datalogue-api/app/services/bi_lead_agent/*`、`datalogue-api/app/api/bi_lead_agent.py`、`datalogue-api/tests/test_bi_lead_agent_*.py`、`docs/test-reports/2026-07-01-bi-lead-agent-k1.md`、`.codex/project-memory.md`
- 关键改动：建立 BI LeadAgent K1 三开一藏能力面、run/confirmation/handoff DB 契约、H2 用户确认快照、D2 `query_dataset` 安全返回、AgentScope 2.0 `UserMsg + run_reply_stream()` Host Handoff Adapter、DatasetAgent factory、run-centric API 和 `/runs/{run_id}/handoff` endpoint；`query_multiple_datasets` 继续只作为 disabled capability 预留。
- 安全边界：BI LeadAgent 不直接调用 `list_candidate_assets/compile_dsl_to_sql/execute_compiled_query/repair_dsl/create_query_artifact` 等 Dataset 原子工具；handoff adapter 不走 `run_direct_query()`；异常路径只返回固定安全摘要，SQL/schema/raw rows/DSL/result_rows/compiled refs/candidate assets/blueprint body/repair patch 均不进入 API response、handoff DTO 或测试可见 payload。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_bi_lead_agent_models.py tests/test_bi_lead_agent_capabilities.py tests/test_bi_lead_agent_services.py tests/test_bi_lead_agent_handoff_adapter.py tests/test_bi_lead_agent_api.py tests/test_agentscope_dataset_runtime_bridge.py tests/test_as_r0_security_matrix.py -q`，46 条通过、2 个既有 warning；Task 3/4/5/6 均经过只读 code review，修复过确认一致性、重复确认、非法状态、AgentScope dict 消息、异常泄漏和 API `NoReturn` 类型问题。
- 残留风险：K2 仍需把前端确认卡片、run polling、Workbench refs 和页面端到端原型接到 K1 API；K3 后续再抽象 `BIHandoffPort` 并实现 AgentScope native handoff；真实 LLM DatasetAgent live handoff 需有凭据后单独做 smoke。

### 2026-07-01 20:38 · BI LeadAgent K2 页面原型与端到端契约

- 涉及文件：`datalogue-web/src/assistant/bi-lead-agent-api.js`、`datalogue-web/src/components/bi-lead-confirmation-card.jsx`、`datalogue-web/src/components/bi-lead-run-panel.jsx`、`datalogue-web/src/components/bi-lead-agent-flow.jsx`、`datalogue-web/src/components/chat-page.jsx`、`datalogue-web/src/styles.css`、`datalogue-api/tests/test_bi_lead_agent_e2e_contract.py`、`docs/test-reports/2026-07-01-bi-lead-agent-k2.md`、`.codex/project-memory.md`
- 关键改动：新增 Web API client、确认卡片、运行状态面板和 `BILeadAgentFlow`，在 ChatPage 右侧原型工作区串起 `create -> confirmation -> handoff -> final run`，并保留现有 WorkbenchPanel；后端新增 E2E contract，验证页面依赖的 refs 和 safe DTO 不是只在前端 mock 中成立。
- 安全边界：确认 payload 只取数据集能力摘要，不携带 schema/sql/dsl/raw rows；运行面板只展示 answer summary、artifact/checkpoint refs 和数字结果规模；后端 E2E 仅替换 DatasetAgent runtime adapter，仍走真实 endpoint、service、DB 写入和 response DTO。
- 验证方式：后端 `tests/test_bi_lead_agent_models.py tests/test_bi_lead_agent_capabilities.py tests/test_bi_lead_agent_services.py tests/test_bi_lead_agent_handoff_adapter.py tests/test_bi_lead_agent_api.py tests/test_bi_lead_agent_e2e_contract.py tests/test_agentscope_dataset_runtime_bridge.py tests/test_as_r0_security_matrix.py -q`，47 条通过、2 个既有 warning；前端相关 vitest 5 个文件 42 条通过；`npm run lint` 通过但保留 13 个既有 warning；`npm run build` 通过并保留 Vite chunk size warning；只读 code review 未发现阻断问题。
- 残留风险：K2 仍是页面原型闭环，尚未做真实浏览器截图验收；真实 LLM DatasetAgent live handoff 需要凭据后单独 smoke；多数据集 capability 仍保持 disabled。

### 2026-07-01 20:40 · BI LeadAgent K3 AgentScope native handoff 演进

- 涉及文件：`datalogue-api/app/core/config.py`、`datalogue-api/app/services/bi_lead_agent/handoff_port.py`、`datalogue-api/app/services/bi_lead_agent/handoff_service.py`、`datalogue-api/app/services/bi_lead_agent/handoff_events.py`、`datalogue-api/app/services/bi_lead_agent/native_handoff.py`、`datalogue-api/tests/test_bi_lead_agent_handoff_port.py`、`datalogue-api/tests/test_bi_lead_agent_native_handoff.py`、`datalogue-api/tests/test_bi_lead_agent_handoff_parity.py`、`docs/test-reports/2026-07-01-bi-lead-agent-k3.md`、`.codex/project-memory.md`
- 关键改动：新增 `BIHandoffPort`，`BIHandoffService` 改为依赖可替换 handoff port；新增 `BI_LEAD_AGENT_HANDOFF_MODE=host_adapter|agentscope_native` 且默认保持 `host_adapter`；新增 `AgentScopeNativeBIHandoff`，通过 AgentScope 2.0 DatasetAgent 子运行执行 handoff，并把 native child-run 事件投影为 Datalogue `BILeadAgentHandoffResult`；session artifact/error fallback 会覆盖 accepted/running 过渡态，避免终态 handoff 被持久化为 running。
- 安全边界：K3 不让 AgentScope session/event 取代 Datalogue DB 真相源；native event 映射只保留 handoff 状态、child_run_id、artifact/checkpoint refs、安全摘要和结果规模，继续过滤 SQL/schema/DSL/raw rows/result internals；BI LeadAgent 仍不直接调用 Dataset 原子工具。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_bi_lead_agent_models.py tests/test_bi_lead_agent_capabilities.py tests/test_bi_lead_agent_services.py tests/test_bi_lead_agent_handoff_adapter.py tests/test_bi_lead_agent_api.py tests/test_bi_lead_agent_handoff_port.py tests/test_bi_lead_agent_native_handoff.py tests/test_bi_lead_agent_handoff_parity.py tests/test_agentscope_dataset_runtime_bridge.py tests/test_as_r0_security_matrix.py -q`，59 条通过、2 个既有 warning。
- 残留风险：`agentscope_native` 默认不启用，生产切换前还需要真实凭据和 live smoke；完整 F3 长生命周期会话 Agent、Report/Python/Audit 可选 Agent 和多数据集 native handoff 仍是后续任务。

### 2026-07-02 09:10 · BI LeadAgent K1/K2/K3 真实浏览器 E2E

- 涉及文件：`datalogue-web/vite.config.js`、`.codex/project-memory.md`
- 关键改动：为 Vite `/api/` 代理增加 `VITE_API_PROXY_TARGET` 覆盖能力，默认仍指向 `http://localhost:8000`；E2E 时在集成 worktree 使用隔离后端 `8002` 和前端 `5174`，避免误用主仓库已有 `8000/5173` 服务。
- 验证方式：使用 `/tmp/datalogue-bi-lead-e2e.db` 种入 `E2E 销售分析数据集`，API 级跑通 `POST /api/bi-lead-agent/runs -> confirm -> handoff -> GET run`；浏览器打开 `/chat`，选择数据集、填写问题、创建 run、确认查询并触发 handoff；网络记录中 `/api/dataset`、`/api/bi-lead-agent/runs`、`confirm`、`handoff` 均为 200，无 console error/warning 和 request failed；桌面截图保存到 `/tmp/datalogue-bi-lead-e2e-desktop.png`，移动截图保存到 `/tmp/datalogue-bi-lead-e2e-mobile.png`；执行 `npm run build` 通过，仅保留既有 Vite chunk size warning。
- 安全边界：页面确认卡片只展示数据集级摘要；终态面板只展示安全失败摘要；浏览器检查未发现 `select/from/schema_context/compiled_query/raw rows/candidate_assets/repair_patch` 等内部执行态泄露；落库确认 `handoff_id/parent_agent/child_agent/child_run_id/dataset_id/task_id/trace_id/handoff_status` 均写入。
- 残留风险：当前 live handoff 真实执行失败，根因是 AgentScope DatasetAgent 调用模型 `MiniMax-M2.7` 时返回 401，缺少有效 Authorization；这次 E2E 验证的是无凭据环境下的安全失败闭环。移动视口无水平溢出，但受固定侧栏影响 BI LeadAgent 右侧面板宽度偏窄，后续移动端适配可单独优化。
