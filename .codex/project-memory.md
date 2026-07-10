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
- Datalogue 架构头脑风暴若存在多个候选方案，先列出各方案的大体概括，再给出 Codex 的建议和理由，最后让用户选择或确认。
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

### 2026-07-01 Langfuse 移除、DatasetAgent 阻断与 C3-P0 Workbench 收口

- 过期 Langfuse 文档归档：`docs/archive/2026-07-01-langfuse-removal/` 新增归档说明，当前入口、项目介绍、系统设计、验收模板和导出脚本不再把 Langfuse、查询审计页或 `/api/observability/*` 描述为现行能力；历史架构/spec/验收记录保留当时事实，后续如要改写需按历史/当前边界单独处理。
- 删除 Langfuse Python 依赖、Docker Compose 服务、观测 API 挂载、prompt/feedback 外部同步和前端 Trace/查询审计入口；`DatalogueTracer` 改为本地 no-op 兼容壳，运行时代码/依赖/部署/前端源码不再包含 Langfuse 调用链。
- 验证覆盖 Langfuse 残留扫描、observability/conversation pytest、后端 compileall、前端 lint/build；历史文档保留 Langfuse 作为历史事实，当前链路改以后端日志、Workbench refs、SSE 和 DB 状态为主。
- `BIAtomicToolProvider.execute_compiled_query()` 将 MySQL/SQLite/PostgreSQL 字段缺失异常统一收敛为 `FIELD_NOT_FOUND`，AgentScope bridge 只回填 `status=blocked/code=FIELD_NOT_FOUND` 和固定安全摘要。
- 验证覆盖 provider 与 AgentScope bridge 字段缺失回归，确保 DB 异常原文、SQL、schema、raw rows 和 repair patch 主体不穿透到 DatasetAgent Runtime / AgentScope SDK bridge。
- C3-P0 PR2 完成 Chat Session Bridge：`/chat/stream` 接入 AgentScope mirror 但不替换 Datalogue 主链，新增 `thread_id`、新 `as_*` session/message/event/ref 投影、final payload 回写线程和异常/取消/无 final 收口；验证覆盖 chat bridge、event projection、mirror、thread resolver 和 chat pytest。
- C3-P0 PR3 完成 Workbench View Model API：新增 `/api/workbench/thread/{thread_id}` 和 artifact view，支持 `as_*` mirror 视图、`conv_*` 旧会话只读回放、artifact refs 脱敏摘要和用户可见层禁止 SQL/schema/raw rows/query_plan/field_patch。
- C3-P0 PR4 完成 Controlled Retry And Lease Recovery：`POST /api/workbench/actions/retry` 白名单化接收 thread/message/checkpoint/action，过期 running message 收口为 interrupted 并生成可恢复 checkpoint，旧 `conv_*` 只读禁用 retry。
- C3-P0 PR5 完成 Chat Workbench Panel：Chat 右侧挂载工作台 Panel 和隐藏 `/workbench/:threadId/:artifactRef?` 路由，前端 adapter 支持 `as_* / conv_*` 线程规范化、Workbench View Model、artifact 详情和受控 retry 请求白名单，Panel 只展示业务摘要、timeline、refs、Artifact 摘要和 action 禁用原因。
- C3-P0 PR6 完成 Workbench acceptance hardening：后端补新 `as_*` Chat stream mirror、lease interrupted + controlled retry、legacy `conv_*` 只读回放三条验收路径；前端补 thread remap、Workbench View Model 回放、artifact refs 和 Panel source 优先级测试；同步 `task.started` 事件契约与 C3 验收记录。
- C3-P0 真实浏览器 E2E 补证修复 AgentScope mirror payload 泄露拦截和 `/chat` 候选确认后 Workbench Panel 切换问题；真实问题“查询杨凯 2024 年工作日志”完成成功问数，主 Chat、右侧 Workbench Panel、隐藏 route 和旧会话只读回放均补证。
- 过期代码第一/第二批清理：删除未挂载 `/api/observability` API、报表/trace 服务、查询审计页、BIAtomicToolProvider 兼容门面和远端 prompt 同步函数；保留仍被旧验收直接断言的 ObservabilityTraceIndex/chat.py 写入链，后续数据库/契约迁移单独处理。

### 2026-06-30 C3-P1/P2 Workbench Retry 与产品化状态模型

- 完成 Workbench 受控 retry 从 action 到 `/chat/stream` checkpoint restore 的主链恢复入口：后端 `WorkbenchRetryRunRequest` 返回业务级 `run_request`，前端 WorkbenchPanel/ChatPage/chat-adapter 消费 pending retry 并交给既有 checkpoint restore 链路。
- 补 internal-only harness 和统一 `retry.started/checkpoint_restored/completed/failed` event envelope，确保 `workbench.retry_requested -> retry.checkpoint_restored -> answer.completed` 能按同一 thread、trace、artifact、checkpoint refs 追溯。
- 真实浏览器补证修复 `as_*` route 恢复数据集、历史 thread append、Panel running 轮询和 ArtifactCard 重复 refs 等缺口；验证包含后端/前端定向测试、lint/build、真实页面点击 retry 到 completed，以及后端 observability API 可拉取同一 trace。
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
- AS-R0 PR1.3-d `/chat/stream` 单数据集直通 DatasetAgent Runtime：显式 `dataset_id` 新查询绕过 legacy `build_workflow` 和 LeadAgent route，进入受控 atomic runtime，保留澄清、多轮、数据集选择等旧控制面；验证覆盖 atomic runtime cutover、compileall 和 diff check。
- AS-R0 DatasetAgent `repair_dsl` 暴露完成：`repair_dsl` 从 future disabled tools 移入 BI tool whitelist 和 AgentScope external tool 序列，字段缺失后仅通过本会话 `compiled_query_ref` 受控修复，不暴露 SQL/schema/raw rows/query_plan/RepairPatch。
- AS-R0 BI 原子工具 ToolBase/Toolkit 收口完成：`get_dataset_status/list_candidate_assets/compile_dsl_to_sql/execute_compiled_query/repair_dsl/create_query_artifact/get_artifact_summary` 迁入 `app.services.bi_tools` Toolkit，Runtime registry 不再把 Provider 作为主工具提供方。
- AS-R0 direct 入口接入 AgentScope repair_dsl 链路完成：`POST /api/chat/dataset-runtime/direct` 切到 `AgentScopeDatasetRuntimeBridge.run_direct_query()`，compile/execute/repair_dsl/retry/artifact summary 均通过 AgentScope external execution event 状态机执行，direct 入口仍仅限非 production。
- AS-R0 DatasetAgent Runtime 日志收口完成：删除 event-level `DatasetRuntimeLoggingMiddleware`，保留 tool-level 安全日志摘要，日志只输出 refs/计数/状态标志，不输出 SQL、schema、raw rows、query_plan、RepairPatch 或 blueprint 主体。
- 修正数据集页面顶部“数据表”能力卡计数为当前数据集已选表数量，并补组件回归测试、lint 和 build 验证。
- 去重 LeadAgent 两阶段 Planner Prompt，并同步 Langfuse Prompt Management 的 production v4，回读确认远端与本地一致。
- 修复新建对话排序与本地草稿体验：新对话优先显示在最近对话顶部，未发送时不落库，发送首条消息时再创建后端会话。


### 2026-06-23 至 2026-07-05 10:39 AgentScope 主链、Workbench 与 BI Worker 收口

- 2026-06-23 至 2026-07-03：持续收口 SubAgent/Planner、多轮上下文、Agentic Shell、AgentScope Dataset Runtime Bridge、BI atomic toolkit、AgenticLeadAgent/BI Agent 命名边界、Chat 主入口直连、真实浏览器连续追问、结果表格/详情展示和模型选择器；关键边界是 SQL/schema/raw rows/query_plan 只在受控工具和 artifact 内部流转，聊天区保留业务答复、候选确认、结果卡和详情入口。
- 2026-07-03 至 2026-07-04：删除旧 LangGraph/SubAgent/compatibility services、prompts、schemas、middlewares 和 host adapter 分支，切到 AgentScope Service + Agent Team 主入口；修复子应用 lifespan、307 路径、session `chat_model_config` 注入、SSE 读超时、长连接完成态退出、worker 等待回报、HITL 投影、候选数据集筛选和 BI Worker 结构化查询结果回传。
- 2026-07-05 09:24 至 10:39：建立 Agent Team 结构化推理摘要协议、实时 progress bridge、内部规划泄漏过滤、候选数据集兜底终态、BI Worker prompt/tool 约束和 artifact 自有 session commit 修复；真实页面层面不再显示 `Theuserwantstoquery/Ineedtocreate` 等内部规划文本，候选卡、结果卡和 artifact 详情入口可读。
- 验证覆盖：相关阶段均执行 AgentScope/Agent Team/Workbench/Artifact/前端 adapter 和 UI targeted pytest/vitest、ruff、compileall、lint/build、`git diff --check`，并多次用桌面 Playwright 验证 `/chat` 候选卡、推理摘要、结果卡和 artifact 详情。历史截图包括 `datalogue-realtime-agent-progress-desktop.png`、`datalogue-bi-worker-candidate-fallback-desktop.png` 以及 `/tmp` 下若干临时页面验收图。
- 残留风险：这批记录是流水压缩摘要；若需要精确回看某个小修的文件列表和命令输出，应按关键词在 git commit、测试文件或旧会话记录中检索。跨进程 AgentScope Service 仍需要把当前进程内 progress bridge / worker 事件桥迁到 Redis/message bus，并加更强 task/session correlation。


### 2026-07-05 11:22 至 16:28 · AgentScope 模型控制面与本地 LLM 配置层删除

- 涉及文件：AgentScope 控制面代理、LLM/credential 相关 API 与 schema、设置页模型配置、聊天模型选择、Agent Team runner、Alembic 迁移、相关后端/前端测试和 `.codex/project-memory.md`。
- 关键改动：候选数据集确认续跑修复为保留原始问题和确认数据集；模型配置执行链路从 LiteLLM/本地 role binding 迁到 AgentScope credential/ModelCard；逐步删除 `llm_role_binding`、本地 API key 列、`/api/llm/models`、`LLMModelConfig` 和旧本地表；聊天请求改传 AgentScope 原生 `model_credential_id/model_name/model_parameters`；设置页继续保留模型配置体验但资源层完全由 AgentScope credential 接管。
- 真实验收：多次桌面 smoke 覆盖 `/settings` AgentScope credential/ModelCard 展示、发现可用模型、`/chat` 查询“杨凯2025年工作日志”、候选数据集确认、BI Worker 查询、结果卡、artifact 详情、后端日志和 `query_artifact` 数据库记录；典型结果为 dataset 10、100 行、48 列、artifact ref 可通过 API 读取。
- 验证方式：覆盖 AgentScope service/client/control plane、LLM resource boundary、Agent Team runner、chat adapter、settings/chat 页面测试，执行 ruff、compileall、前端 lint/build、Alembic heads/upgrade/current、源码扫描和 `git diff --check`；具体命令与输出可按关键词在历史提交或旧会话中检索。
- 残留风险：`retail_test_mysql` 是真实页面 smoke 外部依赖，后续本地 Docker/OrbStack 重启后需先确认容器可用；这条为压缩记录，精确文件级细节需按模块关键词回查。

### 2026-07-06 09:00 至 10:10 · AgentScope credential 字段、OTel 与架构图收口

- 涉及文件：`app/agentscope_service/credentials.py`、`app/agentscope_service/app_factory.py`、`app/agentscope_service/otel_setup.py`、`app/main.py`、`app/core/config.py`、设置页测试、AgentScope worker logging/factory 测试、OTel 方案文档、系统架构图输出和 `.codex/project-memory.md`。
- 关键改动：注册并使用 `DatalogueLLMCredential` 持久化模型名、状态、描述和超时等设置页字段；补充 AgentScope `on_model_call` 观测方案；生成 Mermaid 与手写 SVG 两版系统/Agent 架构图；移除自定义执行日志，模型、reply、tool execution 观测收口到 AgentScope `TracingMiddleware`/OTel；接入本地 logging span exporter，并在 FastAPI lifespan 中初始化 tracing。
- 验证方式：执行相关 pytest、ruff、compileall、前端测试/lint/build、`mmdc`/Chrome headless 图片渲染、源码扫描和 `git diff --check`；控制面真实创建/读取/删除临时 credential 可读回模型配置字段。
- 残留风险：OTel span attributes 和 raw debug 可能包含敏感上下文，仅建议本地短时排障开启；架构图为当前系统视角，未来新增 Report/Python/Audit worker 后需更新。

### 2026-07-06 18:08 · BI Worker 渐进式上下文执行链路

- 涉及文件：`datalogue-api/app/agentscope_service/bi_worker_contracts.py`、`datalogue-api/app/agentscope_service/bi_worker_context.py`、`datalogue-api/app/agentscope_service/bi_worker_validator.py`、`datalogue-api/app/agentscope_service/bi_worker_runtime.py`、`datalogue-api/app/agentscope_service/tools.py`、`datalogue-api/app/agentscope_service/registry.py`、`datalogue-web/src/assistant/agent-team-event-adapter.js`、`datalogue-web/src/assistant/chat-adapter.js`、`docs/test-reports/2026-07-06-bi-worker-progressive-context.md`、`.codex/project-memory.md`
- 关键改动：完成 Task 9 文档验收记录，明确 Agentic Lead + BI Worker 架构不变，BI Worker 继续通过 AgentScope SDK `FunctionTool` 暴露；记录 L0/L1/L5 固定骨架、L2/L3 按需、L4 强制加载和 Query Plan v1 `relationship_ref` 边界；同步固化 SQL、raw rows、schema、query plan 不进入用户可见输出的安全约束。
- 验证方式：执行 `cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api && python3 -m pytest tests/test_bi_worker_progressive_context_contracts.py tests/test_bi_worker_progressive_context_tools.py tests/test_bi_worker_query_validator.py tests/test_bi_worker_query_runtime.py tests/test_bi_worker_progressive_context_e2e.py tests/test_agentscope_service_tools.py tests/test_agentscope_static_agent_registry.py tests/test_agentscope_agent_team_task_runner.py tests/test_agentscope_service_worker_logging.py -q` 为 `69 passed, 29 warnings`；执行 `cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-web && npm test -- agent-team-event-adapter.test.js chat-adapter.test.js --run` 为 `2 passed (2)`、`37 passed (37)`；执行 `npm run lint` 通过，保留 `0 errors, 13 warnings`；执行 `npm run build` 通过，保留既有 Vite chunk size warning。
- 残留风险：L3 真实值域画像仍需继续收敛；复杂多跳 join 的关系路径选择、弱关系命中和跨主题资产组合仍需继续收口。

### 2026-07-06 18:32 · BI Worker Query Plan 契约提示与重试止损

- 涉及文件：`datalogue-api/app/agentscope_service/registry.py`、`datalogue-api/app/agentscope_service/tools.py`、`datalogue-api/tests/test_agentscope_static_agent_registry.py`、`datalogue-api/tests/test_agentscope_service_tools.py`、`.codex/project-memory.md`
- 关键改动：在 BI Worker prompt 中补充最小合法 Query Plan 形状，明确 `selects`、`metrics`、`target`、`display_name` 结构，并禁止把 `select`、`columns`、`fields`、`dimensions` 当成替代字段。`datalogue_validate_query_support` 与 `datalogue_execute_query_plan` 现在会把 Pydantic/上下文契约错误转换为安全 `bi_worker_repair_request`，首轮返回契约修复提示，同类错误第二次返回 `retry_policy.stop_retry=true`，要求 worker 停止继续猜 Query Plan 并改用 TeamSay 汇报澄清或失败摘要。
- 验证方式：先补失败测试复现 prompt 缺少合法字段示例、L5 直接抛出 Pydantic 错误；实现后执行 `uv run pytest datalogue-api/tests/test_agentscope_static_agent_registry.py::test_prompt_and_tool_boundary_forbid_private_tokens datalogue-api/tests/test_agentscope_service_tools.py::test_execute_query_plan_returns_repair_payload_after_repeated_contract_errors -q` 为 `2 passed, 2 warnings`；执行 `uv run pytest datalogue-api/tests/test_agentscope_service_tools.py datalogue-api/tests/test_agentscope_static_agent_registry.py datalogue-api/tests/test_bi_worker_progressive_context_contracts.py datalogue-api/tests/test_bi_worker_query_validator.py datalogue-api/tests/test_bi_worker_query_runtime.py -q` 为 `29 passed, 2 warnings`；执行 `uv run ruff check datalogue-api/app/agentscope_service/tools.py datalogue-api/app/agentscope_service/registry.py datalogue-api/tests/test_agentscope_service_tools.py datalogue-api/tests/test_agentscope_static_agent_registry.py` 通过。
- 残留风险：本轮验证到工具契约和 prompt 层，未重新做真实页面 smoke；如果 AgentScope 模型忽略 `stop_retry=true` 仍可能多轮自然语言解释，但工具侧已不再抛异常驱动连续重试。

### 2026-07-06 18:40 · AgentScope pending tool call 不再提前结束任务

- 涉及文件：`datalogue-api/app/agentscope_service/runner.py`、`datalogue-api/tests/test_agentscope_agent_team_task_runner.py`、`.codex/project-memory.md`
- 关键改动：修复 AgentScope session stream 中 `message.completed` 带 `tool_calls` 时被 Datalogue runner 当作最终完成的问题。现在如果 completed payload 仍包含 pending/asking 工具调用，会视为 ReAct 中间回复并继续等待 `ToolCall/ToolResult/TeamSay`，避免 BI Worker 发出 `datalogue_describe_dataset_capability` 后 SSE 提前关闭。同时在 `_merge_leader_and_progress_events()` 收尾时显式关闭 leader async iterator，避免 break 后留下悬挂长连接。
- 验证方式：先补失败测试复现“pending tool_call 的 message.completed 被提前终止”；实现后执行 `uv run pytest datalogue-api/tests/test_agentscope_agent_team_task_runner.py::test_agentscope_service_task_runner_keeps_stream_open_for_pending_worker_tool_call -q` 为 `1 passed, 2 warnings`；执行 `uv run pytest datalogue-api/tests/test_agentscope_agent_team_task_runner.py -q` 为 `13 passed, 2 warnings`；执行 `uv run ruff check datalogue-api/app/agentscope_service/runner.py datalogue-api/tests/test_agentscope_agent_team_task_runner.py` 通过。
- 残留风险：本轮按日志形态补 runner 单元回归，未重新跑真实页面 smoke；如果 AgentScope 原始 payload 不带 `tool_calls` 字段而只在 middleware raw_debug 中可见，仍需要再补一层原始事件识别。

### 2026-07-06 18:47 · Leader raw thinking 调试日志

- 涉及文件：`datalogue-api/app/agentscope_service/worker_logging.py`、`datalogue-api/tests/test_agentscope_service_worker_logging.py`、`.codex/project-memory.md`
- 关键改动：新增 `LeaderRawDebugMiddleware`，在识别到 Datalogue Agent Team Leader 时除全局 `TracingMiddleware` 外额外挂载 raw debug 中间件。该中间件不发布前端进度、不写普通生命周期，只在 `AGENT_DEBUG_RAW_LOGS=true` 时把 Leader reply timeline 输出到 `[agentscope.leader.raw_debug]`，与 BI worker 的 `[agentscope.bi_worker.raw_debug]` 分离。
- 验证方式：先补失败测试确认 Leader middleware 未注册、Leader thinking 不会输出 raw debug；实现后执行 `uv run pytest datalogue-api/tests/test_agentscope_service_worker_logging.py::test_extra_agent_middlewares_attaches_only_to_bi_worker datalogue-api/tests/test_agentscope_service_worker_logging.py::test_leader_raw_debug_log_prints_thinking_when_debug_enabled -q` 为 `2 passed, 2 warnings`；执行 `uv run pytest datalogue-api/tests/test_agentscope_service_worker_logging.py -q` 为 `24 passed, 2 warnings`；执行 `uv run ruff check datalogue-api/app/agentscope_service/worker_logging.py datalogue-api/tests/test_agentscope_service_worker_logging.py` 通过。
- 残留风险：Leader raw thinking 仍然只建议本地短时排障打开；开启后会把 Leader 的原始思考、文本和工具输入输出写入后端日志，但不会进入 SSE、前端或 artifact。

### 2026-07-06 18:53 · BI Worker prompt JSON 模板转义修复

- 涉及文件：`datalogue-api/app/agentscope_service/registry.py`、`datalogue-api/tests/test_agentscope_static_agent_registry.py`、`.codex/project-memory.md`
- 关键改动：修复 BI Worker prompt 中 Query Plan JSON 示例被 AgentScope `AgentCreate` 二次 `.format()` 误解析的问题。`BI_WORKER_PROMPT` 不再使用 Python f-string 包住整段模板，改为普通 AgentScope format 模板并在末尾拼接官方团队工具边界；`{member_name}`、`{leader_name}` 等仍由 AgentScope 渲染，JSON 示例中的 `{{"target": ...}}` 保持字面量转义，避免再次出现 `AgentCreate failed: '"target"'`。
- 验证方式：先补失败测试复现 `template.system_prompt_template.format(...)` 抛 `KeyError: '"target"'`；实现后执行 `uv run pytest datalogue-api/tests/test_agentscope_static_agent_registry.py::test_bi_worker_prompt_template_is_agentscope_format_safe -q` 为 `1 passed, 2 warnings`；执行 `uv run pytest datalogue-api/tests/test_agentscope_static_agent_registry.py datalogue-api/tests/test_agentscope_service_worker_logging.py datalogue-api/tests/test_agentscope_agent_team_task_runner.py datalogue-api/tests/test_agentscope_service_tools.py -q` 为 `52 passed, 2 warnings`；执行 `uv run ruff check datalogue-api/app/agentscope_service/registry.py datalogue-api/tests/test_agentscope_static_agent_registry.py` 与 `git diff --check` 均通过。
- 残留风险：本轮修复的是 worker 模板格式化层，未重新做真实页面 smoke；如果 Leader 自己在 AgentCreate prompt 参数里手写未转义 JSON，而 AgentScope 也对用户传入 prompt 再做模板渲染，还需要在 Leader prompt 中进一步禁止裸 JSON 示例或要求用自然语言字段说明。

### 2026-07-06 19:18 · BI Worker Query Plan 重试与上下文状态优化

- 涉及文件：`datalogue-api/app/agentscope_service/tools.py`、`datalogue-api/app/agentscope_service/bi_worker_context.py`、`datalogue-api/app/agentscope_service/bi_worker_contracts.py`、`datalogue-api/tests/test_agentscope_service_tools.py`、`datalogue-api/tests/test_bi_worker_progressive_context_tools.py`、`.codex/project-memory.md`
- 关键改动：`query_plan_contract_hint` 改为贴合真实 Pydantic 契约，显式给出合法 filter operator、join requirement alias 结构和 `context_state` 形状；契约失败 payload 增加脱敏 `validation_error_summary`，能指出 `filters.0.operator`、`join_requirements.0.left_alias`、多余 `left_asset_ref` 等位置；重试策略新增 `total_attempt/signature_attempt`，即使 Agent 改变错误签名也按总失败次数止损。L2 schema slice 新增 `context_state_patch/context_state_usage`，由后端生成 asset/field/relationship refs，避免 Worker 从自然语言摘要手写错误 `context_state`。
- 验证方式：先补失败测试复现缺少合法 operator/join hint、不同错误签名导致重试预算重置、L2 缺少 `context_state_patch`；实现后执行 `uv run pytest datalogue-api/tests/test_agentscope_service_tools.py datalogue-api/tests/test_bi_worker_progressive_context_tools.py datalogue-api/tests/test_bi_worker_progressive_context_contracts.py datalogue-api/tests/test_bi_worker_query_validator.py datalogue-api/tests/test_bi_worker_query_runtime.py -q` 为 `31 passed, 22 warnings`；执行 `uv run ruff check datalogue-api/app/agentscope_service/tools.py datalogue-api/app/agentscope_service/bi_worker_context.py datalogue-api/app/agentscope_service/bi_worker_contracts.py datalogue-api/tests/test_agentscope_service_tools.py datalogue-api/tests/test_bi_worker_progressive_context_tools.py` 通过；执行 `git diff --check` 通过。
- 残留风险：本轮验证到工具契约、Provider 和 runtime 单元层，未重新做真实页面 smoke；若模型完全忽略 `stop_retry=true`，仍可能继续自然语言解释，但工具层不会再因为错误签名变化持续放行 L5 契约重试。

### 2026-07-07 11:02 · LLM 配置页面布局与 UI 修复

- 涉及文件：`datalogue-web/src/components/settings.jsx`、`datalogue-web/src/styles.css`、`.codex/project-memory.md`
- 关键改动：修复设置页 LLM 模型配置表单被空的双栏布局压缩到半宽的问题，移除空白布局列，让 credential 编辑表单占满设置页主内容区；调整 LLM 表单行标签/控件栅格和输入框最小宽度，避免中文说明和长模型名被过早挤压；模型配置列表增加专用 class、稳定列宽、长 URL/模型元信息省略和操作列不换行，防止长文本撑破表格或挤乱按钮。
- 验证方式：执行 `cd datalogue-web && npm test -- src/components/settings.test.jsx` 为 `1 passed / 2 passed`；执行 `npm run lint` 通过，保留既有 `0 errors, 15 warnings`；执行 `npm run build` 通过，保留既有 Vite chunk size warning。使用内置浏览器打开 `http://127.0.0.1:5173/settings`，切到 LLM 模型页，确认表单宽度从修复前约 `380px` 恢复为 `744px`，首个输入控件约 `516px`，页面无横向溢出、控制台无 error/warn；点击“发现模型”后出现预期提示，激活项仍为 LLM 模型。
- 残留风险：本轮按项目默认口径只做桌面 1280x720 验收；内置浏览器 DOM snapshot 接口在当前插件版本报错，因此截图/布局指标通过浏览器 evaluate、locator、console logs 和 screenshot 组合验证。

### 2026-07-07 14:21 · BI Worker QueryPlan 表名与聚合编译修复

- 涉及文件：`datalogue-api/app/agentscope_service/bi_worker_runtime.py`、`datalogue-api/app/services/query_plan_compiler.py`、`datalogue-api/tests/test_bi_worker_query_runtime.py`、`.codex/project-memory.md`
- 关键改动：修复 `BIWorkerQueryPlan` 转执行 DSL 时丢失物理表名的问题，`selected_assets`、`filters`、`ordering`、`metrics`、`group_by` 现在都会携带 `metadata.table_name/column_name`，避免编译器把字段名误当 `FROM` 表名。查询计划编译器新增 metric 聚合和 `GROUP BY` 编译，支持 `sum/count/avg/min/max/count_distinct`，并在 WHERE/ORDER BY/GROUP BY 中优先使用 runtime 透传的物理表名。
- 验证方式：先补失败测试确认 detail 查询会错误编译表名、metric 查询会退化为普通字段查询；实现后执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_worker_query_runtime.py -q` 为 `8 passed, 2 warnings`；执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_service_tools.py tests/test_bi_worker_progressive_context_tools.py tests/test_bi_worker_query_validator.py tests/test_bi_worker_query_runtime.py -q` 为 `30 passed, 30 warnings`；执行 `cd datalogue-api && .venv/bin/ruff check app/agentscope_service/bi_worker_runtime.py app/services/query_plan_compiler.py tests/test_bi_worker_query_runtime.py` 通过。
- 残留风险：本轮按单元/工具链验证，未重新做真实页面 smoke；复杂 join 仍依赖后续把 `relationship_ref` 解析为真实 join key，否则跨表 group/filter 可能生成引用多表但缺少 JOIN 的 SQL。

### 2026-07-07 15:02 · OpenViking Service 交接记忆整理

- 涉及文件：`docs/architecture/OpenViking-Service交接记忆.md`、`docs/README.md`、`.codex/project-memory.md`
- 关键改动：新增面向 OpenViking Service 的项目交接记忆，整理当前 AS-R0 主链、OpenViking 接入边界、关键 API、关键文件入口、BI Worker 渐进式上下文契约、安全输出边界、本地启动验证和当前风险；同步更新文档索引，避免交接文档成为孤立文件。
- 验证方式：基于 `docs/上下文入口.md`、当前架构文档、CodeGraph 对 `agent_team.py` / `agent_team_runtime.py` / `AgentScopeServiceClient` / `BIWorkerQueryPlan` 等入口的读取，以及项目 memory 关键词检索完成内容核对；执行 Markdown 文件读取检查确认新文档和索引可读。
- 残留风险：本轮是文档整理，未重新跑后端/前端自动化测试或真实页面 smoke；API 细节仍应以当前 OpenAPI 和源码路由为准。

### 2026-07-07 16:27 · Prompt 统一收口到 app/prompts 目录

- 涉及文件：`datalogue-api/app/prompts/__init__.py`、`datalogue-api/app/prompts/unified.py`、`datalogue-api/app/prompts/annotation.py`、`datalogue-api/app/prompts/blueprint_analyzer.py`、`datalogue-api/app/prompts/dataset_agent.py`、`datalogue-api/app/prompts/native_handoff.py`、`datalogue-api/app/prompts/agent_team.py`、`datalogue-api/app/agentscope_service/registry.py`、`datalogue-api/app/agents/bi_agent/dataset_agent_factory.py`、`datalogue-api/app/agents/bi_agent/native_handoff.py`、`datalogue-api/app/services/annotation.py`、`datalogue-api/app/services/blueprint_analyzer.py`、`.codex/project-memory.md`
- 关键改动：把散落在 `app/agentscope_service/registry.py` 的 6 个 Agent Team prompt（`OFFICIAL_TEAM_TOOL_NOTICE`、`LEADER_AGENT_SYSTEM_PROMPT`、`BI_WORKER_PROMPT`、`REPORT_WORKER_PROMPT`、`PYTHON_WORKER_PROMPT`、`AUDIT_WORKER_PROMPT`）收口到新建的 `app/prompts/agent_team.py`；原 `unified.py` 单文件按模块拆分为 `annotation.py`/`blueprint_analyzer.py`/`dataset_agent.py`/`native_handoff.py`/`agent_team.py` 五个权威定义文件，`__init__.py` 统一 re-export 作为 `from app.prompts import XXX` 入口，`unified.py` 兼容 shim 一并删除（全项目无 `from app.prompts.unified` 引用，单一入口收敛到 `__init__.py`）；`registry.py` 改为从 `app.prompts.agent_team` import，`dataset_agent_factory.py`/`native_handoff.py`/`services/annotation.py`/`services/blueprint_analyzer.py` 4 处调用方统一改走 `from app.prompts import`。worker prompt 内 `{member_name}` 等占位符与 f-string 模板逻辑原样保留，未改动任何 prompt 文本内容。
- 验证方式：执行 `python -c` 从 `app.prompts`、`app.prompts.unified`、`app.agentscope_service.registry` 三个入口导入同名常量，`is` 身份断言通过、无循环 import；`ruff check` 通过、`black` 格式化通过；执行 `python -m pytest tests/test_agentscope_static_agent_registry.py tests/test_agentscope_service_imports.py tests/test_bi_lead_agent_dataset_agent_factory.py tests/test_bi_lead_agent_native_handoff.py tests/test_analysis_blueprint.py tests/test_agentscope_agent_team_task_runner.py tests/test_bi_worker_query_runtime.py tests/test_bi_worker_query_validator.py` 为 `72 passed`；`mypy` 在 `registry.py` 报 5 个 `SubAgentTemplate` `**kwargs` 类型错误，经 `git stash` 对比 HEAD 原版 line 98 确认为 pre-existing，与本次改动无关。
- 残留风险：本轮只搬移 prompt 常量与调整 import，未改动 prompt 文本内容；pre-existing 的 mypy `**kwargs` 类型错误未修；`app/api/llm.py` 的连接测试短句未纳入本次收口（非常量）。死代码 `build_schema_prompt`（全项目无调用方）连同 `app/utils/prompt.py` 一并删除，`app/utils/__init__.py` re-export 与 `app/models/dataset.py` 注释同步清理；`prompt_instructions` 字段改由 `app/agentscope_service/tools.py` 的候选数据集匹配评分消费。

### 2026-07-07 14:58 · Chat 推理摘要去重、思考链承载、标题标签与推理过程保留

- 涉及文件：`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/MyMessage.jsx`、`datalogue-web/src/assistant/chat-adapter.test.js`、`datalogue-web/src/assistant/MyMessage.test.jsx`、`.codex/project-memory.md`
- 背景：真实页面反馈三问题——(1) 流式阶段推理摘要堆出几百条“任务处理”，跑完才刷成几条；(2) Leader 的边想边说规划长文本被当成回答正文铺在聊天区；(3) 问完后思考过程消失、且与结果对不上。根因：前端每个 SSE 事件都 `reasonings.push` 从不去重；后端把 `TextBlockDelta/ThinkingBlockDelta` 都投影成 `message.delta`，前端 `token` 事件累进正文 `accText`；final 合并时又把非 agent 的流式推理（含 Leader 思考）过滤丢弃。
- 关键改动：`chat-adapter.js` 新增 `reasoningGroupKey/upsertReasoningPart` 按 parentId 分组 upsert，`route_decision/agent_handoff/agent_progress/confirmation/lead_agent_tools/step` 全改 upsert，重复步骤原地更新，从流式一开始就是紧凑形态；`token` 事件不再进正文，改为 `sanitizeLiveThinkingText` 清洗后 upsert 成 `parentId=live_thinking` 的思考链条目，正文 `buildContent` 流式期恒为空、只在 final 收敛为干净答案（无 final 的兜底分支仍用 accText 落正文）。新增 `isPreservedStreamingReasoning`：final 合并保留 `agent-*` 与 `live_thinking` 的思考过程（`live_thinking` 收尾标记 completed），再拼接后端业务摘要，避免“问完后思考过程消失”；删除已无引用的 `isRealtimeAgentReasoning`。`MyMessage.jsx` 补 `live_thinking=推理过程/reasoning_summary=推理摘要/multi_agent_handoff/confirmation` 标签，`reasoningStepLabel` 对 `reasoning_summary` 优先用每条自带 `title`（识别任务/生成结果）并加 `safeReasoningLabelText` 过滤 SQL/schema，思考链文本加 `white-space: pre-wrap` 便于阅读长文本。
- 验证方式：`cd datalogue-web && npm test -- src/assistant/MyMessage.test.jsx src/assistant/chat-adapter.test.js --run` 为 `2 passed, 43 passed`；`npx eslint` 对四个改动文件 0 error。真实 `/chat/161` 桌面 Playwright 问“统计合同总金额”：流式期推理摘要单条累积（去重生效），Leader 规划独白进入思考链“推理过程”，回答正文块 `.ai-message.md-body` 为空；final 后推理摘要保留 4 条（推理过程 + bi-worker + 识别任务 + 整理回答），思考过程未消失。
- 残留风险：后端 `message.completed` 的最终 answer 仍是 Leader 的中文规划独白（后端内部规划过滤只认英文；且 leader 把候选数据集写成自由文本 markdown 表格而非结构化 `dataset_candidates`），导致 final 后回答正文仍显示大段独白、也无候选确认卡。这是后端/prompt 层根因，需要单独修：让 leader 只输出干净答案+结构化候选，或在投影层把 ThinkingBlock 与 TextBlock 分流。历史回放思考来自 `step_trace`，不含 `live_thinking`，重载后思考细节可能与实时不同。

### 2026-07-07 17:03 · AGENTS.md 更新为反映当前技术架构

- 涉及文件：`datalogue-api/AGENTS.md`、`.codex/project-memory.md`
- 关键改动：更新 `datalogue-api/AGENTS.md` 以反映当前 AS-R0 技术架构；删除过时的"当前上下文状态"和"可丢弃背景"（Jun 20 交接临时内容）；新增"技术架构"章节（技术栈：Python 3.11 + FastAPI 0.111 + SQLAlchemy 2.0 + AgentScope 2.0.3 主链 + LangGraph 旧链残留；核心调用链：`/api/agent-team/tasks/stream` SSE → AgentTeamTaskRuntime → AgentScopeServiceTaskRunner → `/agentscope` 子应用 → Agent Team Leader+Worker → BI 工具 → query_plan_compiler/executor；目录结构表；关键边界：BI Worker 安全边界、Prompt 统一管理 `app/prompts/`、官方团队工具）；保留协作约束与执行偏好；新增参考文档索引（`../docs/`、`../.codex/`）。根 `AGENTS.md`（通用规范，7月7日已更新）未动。
- 验证方式：基于 `../docs/上下文入口.md`、`pyproject.toml` 依赖、`app/main.py` 挂载（`/api` 路由 + `/agentscope` 子应用）、`app/api/agent_team.py` 路由、`app/` 目录结构核对；引用路径 `../docs/`、`../.codex/` 经 `ls` 确认存在。
- 残留风险：本轮是文档更新，未跑自动化测试；架构随 AS-R0 演进，后续若主链再次迁移需同步更新本文件与 `../docs/上下文入口.md`。


### 2026-07-07 18:20 · P0 架构收口：唯一主链、Leader 控制面与 repair 一等闭环

- 涉及文件：`docs/上下文入口.md`、`docs/architecture/系统架构.md`、`docs/architecture/执行链路.md`、`docs/architecture/AgentScope集成.md`、`docs/architecture/OpenViking-Service交接记忆.md`、`datalogue-api/AGENTS.md`、`datalogue-api/tests/test_architecture_docs_p0_closure.py`、`.codex/project-memory.md`
- 关键改动：将当前唯一产品主链明确为 `POST /api/agent-team/tasks/stream → AgentScope Agent Team → BI Worker Tools`，旧 LangGraph、direct-query、legacy payload 和 BI LeadAgent 目录降级为历史迁移层、内部 fallback 或兼容说明；明确 Leader 控制面不可绕过，BI Worker 只作为执行/诊断面；明确 repair 一等可信闭环为 Failure Classifier、Private Diagnosis、Repair Planner、User Confirmation、Retry Executor、Artifact Writer 六阶段。
- 验证方式：新增 `datalogue-api/tests/test_architecture_docs_p0_closure.py` 扫描当前权威文档和后端 AGENTS 规则，防止唯一主链、Leader 边界、repair 阶段、raw rows 私有诊断边界和旧 L4/L5 主叙事回退；执行 `python -m pytest datalogue-api/tests/test_architecture_docs_p0_closure.py` 与 `git diff --check`。
- 残留风险：本轮是 P0 架构口径与协作规则收口，不改 runtime 行为；QueryPlan 原生执行替代 legacy DSL、Workbench/event 复杂度压缩、assistant-ui runtime 守护和部署健康检查等 P1/P2 项需要后续按同样工作树与计划流程继续处理。


### 2026-07-07 18:36 · P0 后剩余架构问题治理收口

- 涉及文件：`docs/architecture/系统架构.md`、`docs/architecture/执行链路.md`、`docs/architecture/AgentScope集成.md`、`docs/api/API概览.md`、`docs/operations/运行时健康检查.md`、`docs/README.md`、`docs/上下文入口.md`、`datalogue-api/tests/test_architecture_docs_remaining_closure.py`、`.codex/project-memory.md`
- 关键改动：把 P1/P2 审计剩余问题落成仓库治理边界：QueryPlan 是 BI Worker 契约、legacy DSL 是执行器兼容层和迁移债务，中期目标是 QueryPlan 原生执行或 `ControlledQuerySpec`；事件分为用户可见、Workbench、Debug 三层，`legacy_payload` 冻结不再扩字段；assistant-ui 近期只做可见层稳定，禁止 headless primitives / runtime 级大重构；新增运行时健康检查规格；Report/Python/Audit Worker 暂缓并明确解除标准。
- 验证方式：新增 `datalogue-api/tests/test_architecture_docs_remaining_closure.py`，与 P0 架构文档守护测试一起执行；执行 `python3 -m pytest datalogue-api/tests/test_architecture_docs_p0_closure.py datalogue-api/tests/test_architecture_docs_remaining_closure.py` 与 `git diff --check`。
- 残留风险：本轮继续保持治理收口，不改 runtime 行为；真正移除 QueryPlan→legacy DSL 转换、实现更完整的机器可读 health endpoint、以及恢复 Report/Python/Audit Worker 扩展，需要后续在 BI 主链稳定证据达标后单独开任务。


### 2026-07-07 17:49 · BI Worker Query Plan 契约错误详细诊断

- 涉及文件：`datalogue-api/app/agentscope_service/tools.py`、`datalogue-api/tests/test_agentscope_service_tools.py`、`.codex/project-memory.md`
- 关键改动：`bi_worker_repair_request` 新增 `validation_error_details`，在保持不回显 SQL、schema、raw input 的前提下，为每个 Query Plan 契约错误输出中文 `message` 和 `expected`；针对 `join_requirements.*.left/right/type` 明确提示应改用 `left_alias/right_alias/join_type`，针对 filter operator 明确提示等值筛选应使用 `=` 而不是 `eq`；顶层额外字段名继续收敛为 `root.extra_field`，避免暴露模
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_service_tools.py -q` 为 `10 passed, 2 warnings`；执行 `cd datalogue-api && .venv/bin/ruff check app/agentscope_service/tools.py tests/test_agentscope_service_tools.py` 通过；执行 `git diff --check -- datalogue-api/app/agentscope_service/tools.py datalogue-api/tests/test_agentscope_service_tools.py` 通过。
- 残留风险：本轮只增强工具返回的安全诊断 payload，未做真实页面 smoke；如果前端需要把 `validation_error_details` 做成可视化折叠面板，还需另补 UI 展示和前端测试。

### 2026-07-09 17:08 · 系统设置与用户管理视觉层级精修

- 涉及文件：`datalogue-web/src/styles.css`、`.codex/project-memory.md`
- 关键改动：在不改信息架构的前提下优化“系统设置 > 用户管理”页面观感。设置页布局从固定窄主栏调整为自适应双栏，减小左侧与主内容区割裂感；设置侧栏改为轻量卡片容器并优化 active 态权重；用户管理嵌入设置页时去掉外层冗余留白和重阴影，避免卡片套卡片；优化筛选工具条和表头层级，使标题区、表格区视觉更统一。
- 验证方式：执行 `cd datalogue-web && npm run lint && npm run build` 通过；lint 保留仓库既有 warning（无新增 error），build 正常产出。
- 残留风险：本轮主要是 CSS 精修，未额外做跨浏览器逐项截图回归；若后续新增设置子页存在超宽表格，可能仍需按子模块补充横向滚动与列宽策略。

### 2026-07-09 17:17 · 系统管理子页面配色统一 + 表格图标操作按钮

- 涉及文件：`datalogue-web/src/styles.css`、`datalogue-web/src/components/settings.jsx`、`datalogue-web/src/components/user-create.jsx`、`.codex/project-memory.md`
- 关键改动：统一系统管理页（设置各子页）的视觉样式，收敛标题字重与色彩、卡片/表单/表格边框与 hover 背景，形成一致的蓝灰配色层级；设置页所有表格操作按钮统一为紧凑图标按钮，并增加 `data-tip` 气泡提示样式（hover/focus 可见）；用户管理（Antd Table）将“编辑/重置密码/删除”改为图标按钮并使用 Tooltip，显著节省操作列宽度。
- 验证方式：执行 `cd datalogue-web && npm run lint && npm run build` 通过；lint 保留仓库既有 warning（无新增 error），build 正常。
- 残留风险：设置页的 `data-tip` 是 CSS 气泡，若后续某些容器调整为 `overflow: hidden`，个别位置的气泡可能被裁剪；用户管理页已使用 Antd Tooltip，不受该限制。

### 2026-07-09 17:04 · 登录与网关错误提示可读性修复 + 用户管理入口归位

- 涉及文件：`datalogue-web/src/api/client.js`、`datalogue-web/src/components/sidebar.jsx`、`.codex/project-memory.md`
- 关键改动：前端 API 客户端 `request()` 在非 2xx 响应时新增统一错误解析，优先提取后端 JSON `detail/message/error`，支持 `detail` 数组和嵌套对象；对反向代理 HTML 错误页做过滤，避免弹窗展示整段 `HTTP 401: Unauthorized` 或 HTML 垃圾文本；当后端无可读文案时按状态码回退为中文提示（含 502 网关异常专用文案）。这样登录接口 `POST /api/auth/login` 返回 `{detail: "用户名或密码错误"}` 时会直接展示该文案，同时 502 也会给用户可理解提示。侧边栏把“系统管理”分组内“用户管理”顺序提前到“系统设置”之前，入口更符合信息架构。
- 验证方式：执行 `cd datalogue-web && npm run lint`（通过，0 error/13 warning，均为仓库既有 warning）；执行 `cd datalogue-web && npm run build`（通过，Vite 正常构建产物）。
- 残留风险：本轮未启动 dev server 做手工登录弹窗截图复验；如果后端未来返回非标准错误体（既非 JSON 也非纯文本），前端仍会使用状态码兜底文案。

### 2026-07-09 16:05 · 用户管理列表页与新建用户弹框

- 涉及文件：`datalogue-api/app/api/auth.py`、`datalogue-api/app/schemas/auth.py`、`datalogue-web/src/components/user-create.jsx`、`datalogue-web/src/api/client.js`、`datalogue-web/src/components/sidebar.jsx`、`datalogue-web/src/App.jsx`、`datalogue-web/src/styles.css`、`.codex/project-memory.md`
- 关键改动：后端新增 `GET /api/auth/users`（管理员权限、支持 `limit/offset`）用于用户列表；前端将原“新建用户独立页”改为“用户管理页”，展示用户表格（用户名/姓名/邮箱/角色/状态），顶部按钮打开“新建用户”弹框，提交后调用注册接口并自动刷新列表；系统管理导航文案改为“用户管理”，路由统一为 `/users`。
- 验证方式：执行 `cd datalogue-web && npm run lint` 两次，结果均为 `0 errors, 14 warnings`（均为仓库既有告警，无本次新增错误）。
- 残留风险：当前后端注册接口 `POST /api/auth/register` 仍未限制为管理员调用；虽然列表接口已做管理员鉴权，但如普通登录态可直接调用注册接口，仍有越权创建用户风险。

### 2026-07-09 16:34 · 角色权限与默认超级管理员初始化

- 涉及文件：`datalogue-api/app/models/user.py`、`datalogue-api/app/schemas/auth.py`、`datalogue-api/app/api/auth.py`、`datalogue-api/app/api/deps.py`、`datalogue-api/app/main.py`、`datalogue-api/alembic/versions/a8b9c0d1e2f3_add_user_role.py`、`datalogue-api/tests/test_auth.py`、`datalogue-web/src/components/sidebar.jsx`、`datalogue-web/src/App.jsx`、`datalogue-web/src/components/user-create.jsx`、`.codex/project-memory.md`
- 关键改动：新增用户角色字段 `role`（字典：`admin`/`user`）；注册接口收口为管理员权限；管理员鉴权支持 `is_superuser=true` 或 `role=admin`；启动初始化在空库时固定创建 `admin/admin` 且 `role=admin,is_superuser=true` 的超级管理员；前端“用户管理”菜单与 `/users` 路由都增加管理员可见控制，普通用户不可见且不可直接访问。
- 验证方式：执行 `cd datalogue-api && pytest tests/test_auth.py -q`，结果 `4 passed`；执行 `cd datalogue-web && npm run lint`，结果 `0 errors, 14 warnings`（均为仓库既有告警）。
- 残留风险：新增 `role` 字段需要执行 Alembic 迁移后数据库才会持久化该字段；若环境未升级到新 revision，会出现模型与库表结构不一致。

### 2026-07-09 17:02 · 用户管理编辑能力与账号资料同步

- 涉及文件：`datalogue-api/app/schemas/auth.py`、`datalogue-api/app/schemas/__init__.py`、`datalogue-api/app/api/auth.py`、`datalogue-api/tests/test_auth.py`、`datalogue-web/src/api/client.js`、`datalogue-web/src/components/user-create.jsx`、`datalogue-web/src/components/settings.jsx`、`.codex/project-memory.md`
- 关键改动：后端新增管理员用户管理接口（`PATCH /api/auth/users/{id}` 编辑信息/角色/状态、`POST /api/auth/users/{id}/reset-password` 重置密码、`DELETE /api/auth/users/{id}` 删除用户）；前端用户管理页新增“编辑/重置密码/删除”操作和对应弹框；“账号与个人资料”页面改为读取当前登录用户，姓名/邮箱/角色与登录态实时一致，不再使用静态演示数据。
- 验证方式：执行 `cd datalogue-api && pytest tests/test_auth.py -q`，结果 `5 passed`（新增用户管理接口回归用例）；执行 `cd datalogue-web && npm run lint`，结果 `0 errors, 14 warnings`（均为仓库既有告警）。
- 残留风险：当前“删除用户”对超级管理员做了硬性保护，若未来需要多超级管理员治理（可转移 owner 后删除旧 owner），需补充更细粒度策略与审计流程。

### 2026-07-09 17:18 · 重置密码规则与密码存储 base64 包装

- 涉及文件：`datalogue-api/app/core/security.py`、`datalogue-api/app/api/auth.py`、`datalogue-api/app/schemas/auth.py`、`datalogue-api/app/schemas/__init__.py`、`datalogue-api/tests/test_auth.py`、`datalogue-web/src/api/client.js`、`datalogue-web/src/components/user-create.jsx`、`.codex/project-memory.md`
- 关键改动：重置密码接口改为固定规则，管理员触发重置后目标用户密码统一变为“用户名 + @123456”；前端重置弹框改为确认提示，不再手工输入新密码。密码存储策略改为“pbkdf2 哈希后再做 base64 包装入库（`b64$` 前缀）”，并兼容历史未包装哈希的登录校验，避免旧数据失效。
- 验证方式：执行 `cd datalogue-api && pytest tests/test_auth.py -q`，结果 `5 passed`；执行 `cd datalogue-web && npm run lint`，结果 `0 errors, 14 warnings`（均为仓库既有告警）。
- 残留风险：base64 仅是编码包装，不是可替代密码学加密；安全性核心仍依赖 pbkdf2 哈希。若后续有更高合规要求，建议升级为 Argon2 并配套密码轮换策略。

### 2026-07-09 17:33 · 登录请求前后端联合加解密改造

- 涉及文件：`datalogue-api/app/core/config.py`、`datalogue-api/app/core/security.py`、`datalogue-api/app/schemas/auth.py`、`datalogue-api/app/api/auth.py`、`datalogue-api/tests/test_auth.py`、`datalogue-web/src/api/client.js`、`.codex/project-memory.md`
- 关键改动：登录接口从明文 `password` 改为仅接收密文 `password_enc`；前端通过 Web Crypto（AES-GCM）用 `VITE_AUTH_TRANSPORT_KEY` 对密码加密后提交，后端用 `AUTH_TRANSPORT_KEY` 解密再进行密码校验。密码存储取消旧格式兼容，统一要求 `b64$` 包装后的 pbkdf2 哈希。
- 验证方式：执行 `cd datalogue-api && pytest tests/test_auth.py -q`，结果 `6 passed`（新增“明文登录请求应失败”用例）；执行 `cd datalogue-web && npm run lint`，结果 `0 errors, 14 warnings`（均为仓库既有告警）。
- 残留风险：前后端传输密钥必须保持一致（`AUTH_TRANSPORT_KEY == VITE_AUTH_TRANSPORT_KEY`），若环境变量不一致会导致登录返回“密码密文无效”。

### 2026-07-09 17:42 · 启动时默认管理员账号强制校准

- 涉及文件：`datalogue-api/app/main.py`、`.codex/project-memory.md`
- 关键改动：`_bootstrap_admin_if_needed` 从“仅空库创建 admin”改为“启动时确保 admin 存在且可登录”：若不存在则创建；若已存在则强制校准为 `admin/admin`、`role=admin`、`is_superuser=true`、`is_active=true`，避免历史密码存储格式导致管理员无法登录。
- 验证方式：执行 `cd datalogue-api && pytest tests/test_auth.py -q`，结果 `6 passed`。
- 残留风险：该策略会在每次启动重置 admin 密码为默认值，仅适合当前上线初期；后续进入生产阶段需切换为一次性初始化或受控运维重置流程。

### 2026-07-09 00:10 · 登录认证设计方案文档整理

- 涉及文件：`docs/登录认证设计方案.md`、`.codex/project-memory.md`
- 关键改动：新增登录认证方案文档，基于当前项目实际技术栈给出可落地路线：后端采用同步 SQLAlchemy 兼容的轻量 JWT 方案（Access + Refresh）、前端沿用 Ant Design 体系实现登录页与路由守卫，并补充 CORS/Cookie、安全边界、分阶段实施清单与验收标准。
- 验证方式：检查目标文档已在 `docs/` 落盘并完成内容复核（背景、选型结论、后端改造点、前端改造点、安全要求、验收标准完整）。
- 残留风险：本次仅产出设计文档，尚未落地代码与自动化测试；后续实施阶段需同步补齐 Alembic 迁移、后端鉴权测试与前端登录流程回归。

### 2026-07-07 18:07 · BI Worker Timeline 临时 Redis 调试缓存

- 涉及文件：`datalogue-api/app/agentscope_service/bi_worker_timeline_cache.py`（新增）、`datalogue-api/app/agentscope_service/worker_logging.py`、`datalogue-api/tests/test_bi_worker_timeline_cache.py`（新增）、`datalogue-api/tests/test_agentscope_service_worker_logging.py`、`datalogue-api/app/agentscope_service/tools.py`（顺带修复 `DatalogueSearchAssetsTool.check_permissions` 签名错误：由 `(self, **kwargs)` 改为 `(self, tool_input, context)` 与 `ToolBase` 基类一致，解决 `TypeError: takes 1 positional argument but 3 were given`）。
- 关键改动：新增 `bi_worker_timeline_cache` 模块暴露 `store_bi_worker_timeline` / `read_bi_worker_timeline`，key 前缀 `datalogue:bi_worker_timeline:{worker_session_id}:{reply_id}`，TTL 3600s；复用 `StorageBase.get_client()` 复用 AgentScope RedisStorage 连接池，任何 Redis 异常降级 debug 日志不影响主链。`BIWorkerProgressMiddleware` 接收 `storage`，reply 成功后调用 `_cache_bi_worker_timeline_if_enabled`，受 `raw_agent_logs_enabled()` 开关控制，默认关闭避免生产写入含 SQL/表结构/思维链的 raw 内容；`build_datalogue_extra_agent_middlewares` 透传 storage。全链路标 `TODO(后期删除): 由 AgentScope TracingMiddleware / OpenTelemetry 取代`。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_worker_timeline_cache.py tests/test_agentscope_service_worker_logging.py -v` 为 `39 passed, 2 warnings`；`black`、`ruff check`（新增/改动文件）、`mypy app/agentscope_service/bi_worker_timeline_cache.py app/agentscope_service/worker_logging.py` 全部通过；全量 ruff/mypy 剩余错误均为预先存在的历史技术债，非本次引入。
- 残留风险：raw timeline 含 SQL/表结构/原始思考链，仅依赖 `AGENT_DEBUG_RAW_LOGS` 环境开关（默认关）+ TTL 1h 缓解落盘泄露风险；后期 AgentScope TracingMiddleware / OpenTelemetry 落地后需删除 `bi_worker_timeline_cache` 模块及 `worker_logging._cache_bi_worker_timeline_if_enabled` 调用点。

### 2026-07-07 18:12 · BI Worker 蓝图路径与 display_semantic 校验修复

- 涉及文件：`datalogue-api/app/prompts/agent_team.py`、`datalogue-api/app/agentscope_service/bi_worker_context.py`、`datalogue-api/app/agentscope_service/bi_worker_validator.py`、`datalogue-api/app/agentscope_service/tools.py`、`datalogue-api/tests/test_bi_worker_query_validator.py`、`datalogue-api/tests/test_bi_worker_progressive_context_tools.py`、`.codex/project-memory.md`
- 关键改动：根据 BI Worker raw timeline 定位到蓝图提示词与真实工具签名不一致：prompt/usage hint 误导 worker 按 `call_template` 构造 SQL，但 `datalogue_execute_query_plan_bundle` 实际只接受 `BIWorkerQueryPlan + context_state`。本轮把蓝图收口为 QueryPlan 生成参考，要求先用 `datalogue_prepare_query_context` 和必要的 `datalogue_request_schema_slice` 获取安全引用，再把蓝图参数、字段、筛选和排序语义转换为 QueryPlan。同步修复 L4 校验器把普通 `display_semantic` 误判为 lookup dependency 的问题，只有 `requires_decoding=true` 才要求 lookup 依赖，避免普通展示字段反复触发 `FIELD_NOT_FOUND`。`prepare_query_context.context_state.asset_refs` 改为 `table:schema.table` 格式，减少 worker 从第一步拿到错误资产引用。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_worker_query_validator.py tests/test_bi_worker_progressive_context_tools.py tests/test_agentscope_static_agent_registry.py -q` 为 `21 passed, 30 warnings`；执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_service_tools.py tests/test_bi_worker_query_runtime.py tests/test_bi_worker_query_validator.py tests/test_bi_worker_progressive_context_tools.py tests/test_agentscope_static_agent_registry.py -q` 为 `39 passed, 30 warnings`；执行 `cd datalogue-api && .venv/bin/ruff check app/agentscope_service/bi_worker_validator.py app/agentscope_service/bi_worker_context.py app/agentscope_service/tools.py app/prompts/agent_team.py tests/test_bi_worker_query_validator.py tests/test_bi_worker_progressive_context_tools.py tests/test_agentscope_static_agent_registry.py` 通过。
- 残留风险：本轮修复到 prompt、工具说明和校验器层，未重新跑真实页面 smoke；复杂蓝图跨表查询仍依赖后续把 `relationship_ref` 稳定解析到真实 join key，否则 QueryPlan 通过校验后仍可能在执行编译阶段失败。

### 2026-07-08 · BI Worker Repair 链路三处修复（bridge status/code + 空结果映射 + join_keys 契约）

- 涉及文件：`datalogue-api/app/agentscope_service/bi_worker_contracts.py`、`datalogue-api/app/agentscope_service/bi_worker_runtime.py`、`datalogue-api/app/agentscope_service/tools.py`、`datalogue-api/tests/test_bi_worker_query_runtime.py`、`datalogue-api/tests/test_agentscope_service_tools.py`、`.codex/project-memory.md`。
- 关键改动：从 BI Worker timeline 定位 repair 链路三个联动缺陷：(1) `_execute_plan` 忽略 `run_direct_query` 的 `status="blocked"` / `code`，把静默失败当成 completed；(2) `execute_query_plan` 空结果映射用 `row_count == 0` 判定，`row_count is None + artifact_ref is None` 会掉进 completed 默认分支导致 LLM 看不到 `failure_type`，repair 链路 B 不触发；(3) `JoinRequirement` 契约无合法通道承载真实 join 键，LLM 一开始用 `join_condition: "main.account=person.person_card"` 走私 SQL 片段被契约拒绝后 join 语义彻底丢失。本轮：`bi_worker_contracts.py` 新增 `JoinKey`（`left_field`/`right_field` 都要求 min_length=1），`JoinRequirement` 追加可选 `join_keys: list[JoinKey]`；`tools.py` 同步 `BI_WORKER_QUERY_PLAN_CONTRACT_HINT["join_requirement_shape"]` 追加 `join_keys` 示例，并让 `_plan_contract_error_expected` 对 `join_requirements.*.join_condition` 明确引导 LLM 删除 join_condition 改用结构化 `join_keys=[{left_field, right_field}]`；`bi_worker_runtime.py` 新增顶层 `_map_bridge_code_to_failure(code, error_summary)`，`_execute_plan` 在 `bridge_status == "blocked"` 或缺 artifact 时把 code 映射为 `QueryFailureType` 并写进 `BIWorkerQueryResult.failure_type`，`execute_query_plan` 感知 `result.failure_type` 后直接透传，空结果判定放宽为 `row_count == 0 or (row_count is None and not artifact_ref)`；`_query_plan_to_legacy_query_plan` 把 `join_requirements`（含 `join_keys`）透传到 legacy DSL 供下游后续消费。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_worker_query_runtime.py tests/test_agentscope_service_tools.py tests/test_bi_worker_progressive_context_contracts.py tests/test_bi_worker_query_validator.py tests/test_bi_worker_progressive_context_tools.py tests/test_bi_worker_progressive_context_e2e.py tests/test_agentscope_service_worker_logging.py tests/test_bi_worker_timeline_cache.py --tb=short` 为 `85 passed, 30 warnings`；`black` 已重新格式化 5 个改动文件、`ruff check` 全部通过；`mypy` 仅剩本仓库预先存在的 4 处历史类型债（`session_kwargs`、`RepairRequest.failure_stage` Literal、`_execute_supported_plan` 联合类型），非本次引入。
- 残留风险：`join_keys` 目前仅在 legacy DSL 里透传，`app/services/query_plan_compiler.py` 等下游编译器暂未消费该字段，因此 join 键校准还没真正落到 SQL 层；LLM 拿到 join_keys 通道后能显式声明关联字段，但真实 join 是否能命中数据库物理键需要下一轮把编译器接上 `join_keys`。本次只保证 repair 链路 A 修完契约后不再假成功、失败会走 repair 链路 B、LLM 有合法通道声明 join 键；未跑真实页面 smoke。

### 2026-07-08 · query_plan_compiler 消费 join_keys 生成显式 JOIN（Workflow 多 subagent 并行 + 自主验证）

- 涉及文件：`datalogue-api/app/agentscope_service/bi_worker_runtime.py`、`datalogue-api/app/services/query_plan_compiler.py`、`datalogue-api/tests/test_query_plan_compiler.py`、`datalogue-api/tests/test_bi_worker_query_runtime.py`、`.codex/project-memory.md`。
- 关键改动：把上一轮"join_keys 已在契约和 legacy DSL 里就位但编译器不消费"的残留风险闭环。runtime `_query_plan_to_legacy_query_plan` 的 `compiled_joins` 生成时通过复用 `_alias_table_names(query_plan)`（bi_worker_runtime.py:462-471）把 QueryPlan 内部 `left_alias`/`right_alias` 解析为物理 `left_table`/`right_table` 写入 DSL；compiler 侧新增 `_compile_join_clauses(query_plan, main_table, allowed_tables, dialect)`（query_plan_compiler.py:323-418）严格校验每个 `join_requirement` 元素（`left_table`/`right_table` 非空、`join_type` ∈ `{inner, left}` 大小写归一化、`join_keys` 非空 list、每对 `left_field`/`right_field` 非空、当 `allowed_tables` 非空 list 时两侧表都必须在白名单），任一违反即返回 `None` 触发 `PLAN_NOT_COMPILABLE`；`_compile_select_sql` 签名新增 `allowed_tables` 参数并在 `FROM` 子句后追加 `INNER|LEFT JOIN "<right_table>" ON "<left_table>"."<lf>" = "<right_table>"."<rf>" [AND ...]`，标识符全部走 `quote_identifier(name, dialect)`；`compile_query_plan_to_sql` 主入口把 `allowed_tables` 一路透传下去。测试：`test_query_plan_compiler.py` 追加 6 条覆盖 inner/left/复合 join_keys/缺 join_keys/表不在 allowed_tables/join_type=cross/空 join_requirements 的用例；`test_bi_worker_query_runtime.py` 追加 2 条覆盖 alias→table 解析和端到端 runtime→compiler 的 SQL 输出（断言含 `LEFT JOIN "departments"` 等真实子句），并顺带修补了旧用例 `test_query_plan_conversion_preserves_table_name_for_detail_sql`（`_plan()` 默认 `join_keys=[]` 与新 fail-closed 契约不兼容，在测试内为该 JoinRequirement 补 `JoinKey(dept_id, id)` + 对应 table_schema 列，保留 `test_query_plan_join_keys_default_empty_list` 对 `_plan()` 默认 empty 语义的断言不变）。
- 协作方式：用 Workflow 多 subagent 并行调度（4 个 subagent，共 253347 tokens，60 次工具调用）—— 3 个 Implement subagent 并行做 runtime/compiler/tests（契约由 plan 兜底不冲突），1 个 Verify subagent adversarially 跑 pytest 并自主定位 + 修复兼容性问题。整个链路从设计到全绿测试单次通过，未回滚任何改动。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_query_plan_compiler.py tests/test_bi_worker_query_runtime.py tests/test_bi_worker_progressive_context_contracts.py tests/test_bi_worker_query_validator.py tests/test_agentscope_service_tools.py tests/test_agentscope_service_worker_logging.py tests/test_bi_worker_timeline_cache.py tests/test_bi_worker_progressive_context_tools.py tests/test_bi_worker_progressive_context_e2e.py --tb=short` 为 `102 passed, 30 warnings`（其中 compiler 侧新增 6 条 + runtime 新增 2 条 + 修补旧 1 条）；`black` 已重新格式化改动文件、`ruff check` 全部通过；`mypy app/services/query_plan_compiler.py app/agentscope_service/bi_worker_runtime.py` 剩余错误均为 `handoff_service.py` / `registry.py` 等仓库预先存在的历史类型债，非本次引入。
- 残留风险：本轮已把 LLM 声明的 `join_keys` 全链路串通到 SQL 层（QueryPlan → legacy DSL → compiler → SQL），但真实业务查询是否能命中数据库物理键，仍依赖 LLM 正确从蓝图 `call_template` 或 L2 schema slice 推断出 join 字段名；本轮未跑真实页面 smoke，等待用户重启后端后用"查询杨凯 2025 年工作日志"实际验证。

### 2026-07-08 11:07 · BI Worker thinking 流式推理摘要与 debug 原文通道

- 涉及文件：`datalogue-api/app/agentscope_service/worker_logging.py`、`datalogue-api/app/agentscope_service/projection.py`、`datalogue-api/tests/test_agentscope_service_worker_logging.py`、`datalogue-api/tests/test_agentscope_service_projection.py`、`datalogue-web/src/assistant/agent-team-event-adapter.js`、`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/MyMessage.jsx` 与对应前端测试。
- 关键改动：按 AgentScope + assistant-ui 当前链路把 BI Worker thinking 分成安全摘要与调试原文两条通道。后端 `BIWorkerProgressMiddleware` 对 `ThinkingBlock*` 事件发布 `agent.progress` 安全摘要，默认只显示“BI Worker 思考中/完成思考”；仅当 `DATALOGUE_DEBUG_STREAM_RAW_THINKING=true` 时，才以 `reasoning_kind=bi_worker_raw_thinking_delta`、`debug_raw=true`、`raw_delta` 受控透传 delta 原文。`projection.py` 增加 fail-closed 保护，避免 `ThinkingBlockDeltaEvent` 被泛化成 `message.delta` 后进入正文或 `live_thinking`。前端 adapter 只在 debug 标记与 reasoning kind 同时满足时保留 `rawDelta`，`chat-adapter` 将安全摘要/upsert 和 debug 原文累积进推理摘要，`MyMessage` 显示“BI Worker 思考 / BI Worker 调试原文”标签；默认路径禁止 raw delta 进入 `content`、trace custom 或最终 `reasoning_summary`。
- 验证方式：执行 `cd datalogue-api && /Users/yangkai/code_place/study/python/Datalogue/datalogue-api/.venv/bin/python -m pytest tests/test_agentscope_service_worker_logging.py tests/test_agentscope_service_projection.py tests/test_agentscope_agent_team_task_runner.py tests/test_agentscope_event_projection.py -q` 为 `58 passed, 2 warnings`；执行 `cd datalogue-web && npm test -- agent-team-event-adapter chat-adapter MyMessage` 为 `3 passed (3), 60 passed (60)`；执行 `cd datalogue-web && npm run lint && npm run build` 通过，保留项目既有 lint warnings 与 Vite large chunk warning。worker 并行验证记录：worker-1 后端提交 `8a5dbca5`、worker-2 前端提交 `0351d844`，worker-3 先发现旧 projection 泄露风险，leader 集成后已补回归。
- 残留风险：debug 原文通道是调试阶段能力，开启后会把模型原始 thinking delta 显示在前端推理摘要中，只允许本地/排障短时开启，后期稳定后应删除或收紧该 raw delta 通道；本轮未重新做真实浏览器页面 smoke，若要确认视觉滚动体验，需要启动前后端后在 `/chat` 做桌面验收。

### 2026-07-08 11:28 · BI Worker raw thinking 配置读取修复

- 涉及文件：`datalogue-api/app/core/config.py`、`datalogue-api/app/agentscope_service/worker_logging.py`、`datalogue-api/tests/test_agentscope_service_worker_logging.py`、`.codex/project-memory.md`。
- 关键改动：修复 `DATALOGUE_DEBUG_STREAM_RAW_THINKING=true` 写在 `datalogue-api/.env` 但前端仍只显示安全摘要的问题。根因是 `_debug_stream_raw_thinking_enabled()` 只读 `os.getenv()`，而项目 `Settings(env_file=".env")` 读取 `.env` 不会保证把值同步回 `os.environ`；本轮在 `Settings` 增加 `DATALOGUE_DEBUG_STREAM_RAW_THINKING` 字段，并让 worker logging 在进程环境变量缺失时 fallback 到 `get_settings()`。补充回归覆盖“未 export、仅写入 `.env` 也能开启 raw delta 调试通道”。
- 验证方式：执行 `cd datalogue-api && /Users/yangkai/code_place/study/python/Datalogue/datalogue-api/.venv/bin/python -m pytest tests/test_agentscope_service_worker_logging.py tests/test_agentscope_service_projection.py tests/test_agentscope_agent_team_task_runner.py tests/test_agentscope_event_projection.py -q` 为 `59 passed, 2 warnings`；执行 `cd datalogue-api && /Users/yangkai/code_place/study/python/Datalogue/datalogue-api/.venv/bin/python -m ruff check app/core/config.py app/agentscope_service/worker_logging.py tests/test_agentscope_service_worker_logging.py` 通过；执行 `git diff --check` 通过。
- 残留风险：修改配置文件后仍需重启正在运行的后端进程；debug 模式下安全摘要 start/end 仍会保留，真实 delta 以额外“BI Worker 调试原文”推理条目流式追加。如果模型/AgentScope 本轮没有产出 `ThinkingBlockDeltaEvent.delta`，前端也不会凭空显示 raw delta。

### 2026-07-08 · L2 Schema Slice 三层修复（explicit fields + [:32] + 蓝图 SQL 解析真实 FK）

- 涉及文件：`datalogue-api/app/agentscope_service/bi_worker_context.py`、`datalogue-api/tests/test_bi_worker_progressive_context_tools.py`、`.codex/project-memory.md`。
- 关键改动：从新一次 BI Worker timeline 定位 Repair 链路耗尽 retry 后仍失败的真实上游根因——不是编译器/repair 层的问题（上两轮已修好），而是 L2 schema slice 工具本身的三处缺陷：(1) `columns[:8]` 硬截断导致蓝图 SQL 需要的 `account`/`deptcode` 等 join key 列被挤掉；(2) `_matched_columns` 只做 `focus.values()` 拼串模糊匹配，LLM 无法精确点名要哪些字段；(3) `_relationships` 只输出 `dataset_selected_together` 软关系，无 join key，LLM 只能靠猜——而项目里没有任何持久化 FK 元数据，唯一真实 join 信息在 `AnalysisBlueprint.call_template` SQL 文本里。本轮：(A) `bi_worker_context.py:180` `columns[:8]` → `columns[:32]`；(B) `_matched_columns` 新增 `focus["fields"]` 精确通道，按名称大小写不敏感命中即返回不受截断，未命中/未提供时 fall back 到模糊匹配（focus_text 排除 `fields` key 避免污染）；(C) 新增顶层函数 `_safe_parse_sql`（mysql/sqlite/postgres 多方言降级）、`_extract_joins_from_ast`（遍历 `exp.Join`，只识别 `exp.EQ` 等值 ON、支持 alias 顺序颠倒，RIGHT/FULL/CROSS 一律 skip）、`_parse_blueprint_joins`（遍历 active 蓝图 call_template/raw_sql，异常 swallow 到 debug）。`_relationships` 签名扩展为 `(entities, dataset)`，输出合并原软关系 + 新硬关系 `relationship_type="blueprint_join"`（含 `join_keys`、`join_type`、`source_blueprint_id`），按 `(left_asset_ref, right_asset_ref)` 去重时硬关系优先。LLM 拿到 `blueprint_join:*` relationship 后可直接把结构化 `join_keys` 抄进 QueryPlan，不再靠"看 SQL 猜字段名"。
- 协作方式：Workflow 4 subagent 并行调度（307031 tokens、87 次工具调用）——3 个 Implement subagent 并行做 A/B/C（契约由 plan 兜底不冲突），1 个 Verify subagent adversarially 跑 pytest 亲眼核对 6 项边界并主动修复 1 处 mypy 错误（`_safe_parse_sql` 返回类型不匹配 `sqlglot.parse_one` 的 `exp.Expr` → 改用 `isinstance(parsed, exp.Expression)`），单次通过全绿。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_worker_progressive_context_tools.py tests/test_bi_worker_progressive_context_contracts.py tests/test_bi_worker_progressive_context_e2e.py tests/test_bi_worker_query_runtime.py tests/test_query_plan_compiler.py tests/test_agentscope_service_tools.py tests/test_bi_worker_query_validator.py tests/test_agentscope_service_worker_logging.py tests/test_bi_worker_timeline_cache.py --tb=short` 为 `112 passed, 54 warnings`（含 6 条本轮新增：`test_l2_returns_exact_fields_when_focus_lists_column_names` / `test_l2_returns_up_to_32_columns_when_all_match` / `test_l2_returns_blueprint_join_relationships_from_call_template` / `test_l2_ignores_malformed_blueprint_sql` / `test_l2_ignores_non_equi_join` / `test_l2_multi_join_and_inner_join`）；`black` / `ruff check` / `mypy` 全部通过，mypy 与 baseline 46 errors 完全一致未引入新错误。
- 残留风险：本轮 SQL 解析器只处理简单单层 SELECT + INNER/LEFT JOIN，子查询/UNION/CTE/CROSS/RIGHT/FULL/非等值 ON 全部跳过（保守策略，风险最小但可能漏掉某些复杂蓝图的 join）；只依赖 `AnalysisBlueprint.call_template` 存了真实 SQL，历史遗留蓝图如果 call_template 为空或不含 JOIN 则退化为原软关系；本轮未跑真实页面 smoke，等待用户重启后端后用"查询杨凯 2025 年工作日志"实际验证，期望 L2 一次调用后 relationships 里含 blueprint_join:* 且 join_keys 明确写出 `account/person_card`、`deptcode/dept_id`、`xmid/XMID` 三对键。

### 2026-07-08 12:30 · BI Worker raw thinking 英文分片空格修复

- 涉及文件：`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/chat-adapter.test.js`、`.codex/project-memory.md`。
- 关键改动：修复 `DATALOGUE_DEBUG_STREAM_RAW_THINKING=true` 时 BI Worker raw thinking 英文分片直接拼接导致 `Theuserwants` 这类无空格文本的问题。前端 `chat-adapter` 新增 `appendRawThinkingDelta`，仅在上一片以英文/数字结尾且下一片以英文/数字开头、双方都没有显式空白时补一个空格；中文分片、标点、已有前导/尾随空白保持原样，让 BI Worker debug 原文阅读体验与 Leader live thinking 一致。
- 验证方式：先补失败测试 `preserves readable spaces between english BI Worker raw thinking deltas`，确认修复前输出为 `Theuser wants`；实现后执行 `cd datalogue-web && npm test -- src/assistant/chat-adapter.test.js` 为 `30 passed`；执行 `npm run lint` 通过，保留既有 `0 errors, 14 warnings`；执行 `npm run build` 通过，保留既有 Vite large chunk warning。
- 残留风险：本轮只修复前端 debug raw thinking 的展示拼接，未改变后端 `raw_delta` 发布协议和安全开关；如果模型分片发生在英文单词内部（如 `anal` + `ysis`），当前保守规则会插入空格，后续可在拿到真实 AgentScope 分片样本后再收紧为更精确的 token 边界策略。

### 2026-07-08 12:55 · BI Worker QueryPlan 修复请求 timeline 安全诊断展示

- 涉及文件：`datalogue-web/src/assistant/agent-team-event-adapter.js`、`datalogue-web/src/assistant/agent-team-event-adapter.test.js`、`.codex/project-memory.md`。
- 关键改动：修复 `datalogue_execute_query_plan_bundle` 返回 `bi_worker_repair_request` 后，前端 timeline 只显示泛化 `safe_reason`、看不到模型实际收到的契约失败原因的问题。`safeProgressiveSummary` 新增 `safeRepairRequestSummary` 分支，只对白名单格式的 `validation_error_summary`（如 `missing:join_requirements.0.left_alias`）生成用户可见摘要 `Query Plan 契约错误：... 等 N 项`；继续禁止 SQL、schema、raw rows、模型原始输入等私有信息进入 timeline 文本。
- 验证方式：先补失败测试 `surfaces BI Worker repair request contract paths without leaking private query details`，确认修复前摘要只有 `Query Plan JSON 未符合 BI Worker 安全契约...`；实现后执行 `cd datalogue-web && npm test -- src/assistant/agent-team-event-adapter.test.js` 为 `14 passed`；执行 `pytest datalogue-api/tests/test_agentscope_service_tools.py -q` 为 `12 passed, 2 warnings`，确认后端 ToolChunk 仍保留 `validation_error_summary/details` 和 `query_plan_contract_hint` 给 BI Worker；执行 `cd datalogue-web && npm run lint && npm run build` 通过，保留既有 lint warnings 与 Vite large chunk warning。
- 残留风险：本轮只把后端已脱敏的契约路径摘要投影到前端 timeline，没有把 `validation_error_details.expected` 做成可展开诊断面板；若后续需要给研发调试更完整解释，可在 Workbench 调试视图单独展示 details，但不应放进普通用户 timeline。

### 2026-07-08 · L2 Schema Slice 表列表 vs 详情工具解耦（新增 describe_tables）

- 涉及文件：`datalogue-api/app/agentscope_service/bi_worker_context.py`、`datalogue-api/app/agentscope_service/bi_worker_contracts.py`、`datalogue-api/app/agentscope_service/tools.py`、`datalogue-api/app/prompts/agent_team.py`、`datalogue-api/tests/test_bi_worker_progressive_context_tools.py`、`datalogue-api/tests/test_agentscope_service_tools.py`、`datalogue-api/tests/test_agentscope_static_agent_registry.py`、`.codex/project-memory.md`。
- 关键改动：用户指出上一轮 L2 修复里的 `_matched_tables` 是"后端用字段/描述模糊匹配猜 LLM 该看哪几张表"，这一步完全没有 LLM 介入，准确性差且漏表严重（typical 3-列子串命中）。本轮把 L2 拆成两个正交 read-only 工具：(1) `datalogue_request_schema_slice` 职责收窄为"返回 dataset 全量表清单 + 关系"，不再做模糊过滤、不再返回 fields，entities 元素含 `asset_ref/table/schema/description/row_count_approx/column_count`；`_matched_tables/_matched_columns/focus["fields"] 精确通道/columns[:32] 截断/精确补齐块` 全部从主链移除但函数本身保留（L0/L1/L3 还在用）；`_relationships(entities, dataset)` 完整保留（含蓝图 SQL 硬关系解析）。(2) 新增 `datalogue_describe_tables(dataset_id, table_names: list[str])`，由 LLM 显式点名要哪几张表，一次调用可传多个，返回每张表的字段清单/注释/前 3 条样例值；样例值来源为 `SourceColumn.sample_values`（同步 schema 时已采集的 JSON），有则取 `sample_source="metadata"`，无则空列表 + `sample_source="unavailable"`；不存在的表以 `status="not_found"` 占位不影响其他表；`table_names` 空或非 list 时 fail-closed 返回 `code="TABLE_NAMES_REQUIRED"`。契约层新增 `TableDetailContext(bi_worker_l2_table_detail)`；tools.py 注册 `datalogue_describe_tables` FunctionTool（is_read_only + concurrency_safe）；prompt 更新标准查询路径为四步链路 `prepare_query_context -> request_schema_slice(拿全表清单+关系) -> 按需 describe_tables(拿指定表的字段+样例值) -> execute_query_plan_bundle`，并明确 join 关系走 relationships 里的 `blueprint_join:*`。
- 协作方式：Workflow 4 subagent 并行调度（315319 tokens、74 工具调用）—— 3 个 Implement subagent 并行做 context/contracts+tools+prompt/tests，1 个 Verify subagent adversarially 跑 pytest 亲眼核对 5 项边界，主动修复 2 处遗漏（subagent E 漏更新的 `test_agentscope_static_agent_registry.py` 期望列表 + black 未格式化的 3 个文件），单次通过全绿。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_worker_progressive_context_tools.py tests/test_agentscope_service_tools.py tests/test_bi_worker_progressive_context_contracts.py tests/test_bi_worker_query_runtime.py tests/test_query_plan_compiler.py tests/test_bi_worker_query_validator.py tests/test_agentscope_service_worker_logging.py tests/test_bi_worker_timeline_cache.py tests/test_agentscope_static_agent_registry.py --tb=short` 为 `126 passed, 74 warnings`（含删除 3 条被废弃测试 + 修改 4 条 + 新增 8 条本轮测试）；`black` / `ruff check` 全通过；`mypy app/agentscope_service/bi_worker_context.py app/agentscope_service/tools.py` 剩余 46 个错误全部是 SQLAlchemy `Column[X]` 泛型友好度问题，与 baseline 完全一致未引入新错误。
- 残留风险：样例数据来源为元数据里预先采集的 `SourceColumn.sample_values`，非实时；若数据集同步阶段样例采集失败（SAMPLE_UNREADABLE），LLM 只能拿到 `sample_source="unavailable"` 信号。`_matched_tables/_matched_columns` 保留但仅供 L0/L1/L3 内部使用，L2 主链完全走"LLM 显式点名 + 全量表"路径；未跑真实页面 smoke，等待用户重启后端后用"查询杨凯 2025 年工作日志"实际验证，期望 timeline：LLM 一次调 `request_schema_slice` 拿全 5 张表 + `blueprint_join:*` 关系，然后一次调 `describe_tables(table_names=["plan_task_daily_record","eas_personofile","sys_dept","project_manager"])` 拿全 4 张表的字段+样例，直接生成正确 QueryPlan 命中真实数据。


### 2026-07-08 13:35 · BI Worker Schema Slice 字段别名与 schema-qualified 表引用修复

- 涉及文件：`datalogue-api/app/agentscope_service/bi_worker_context.py`、`datalogue-api/app/agentscope_service/bi_worker_runtime.py`、`datalogue-api/app/services/query_plan_compiler.py`、`datalogue-api/app/prompts/agent_team.py`、`datalogue-api/tests/test_bi_worker_progressive_context_tools.py`、`datalogue-api/tests/test_bi_worker_query_runtime.py`、`.codex/project-memory.md`。
- 关键改动：根据“查询杨凯2024年日志” timeline 定位到后续 `FIELD_NOT_FOUND` 的当前代码侧根因：L2/describe_tables 返回的表级 ref 是 `table:schema.table`，runtime/compiler 旧 `_table_from_field_ref()` 看到点号就认为无法解析表，导致 `join_requirements.left_table/right_table` 为空或表级 target metadata 丢表；本轮识别 `table:` 前缀并保留 schema-qualified 表名。同步给 compiler 增加 `_quote_table_name()`，按 schema/table 分段 quote，避免把 `pm_tenant.plan_task_daily_record` 整体 quote 成单个标识符后被 SQL Guard 判为未授权表。继续补齐 `describe_tables.context_state_patch/context_state_usage`，让字段详情工具直接产出可合并的 `field_refs`，避免 Worker 从字段列表手写 context_state；同步更新 BI Worker prompt 与 `search_assets.usage_hint`，明确蓝图路径需 `request_schema_slice` 拿表/关系、`describe_tables` 拿字段/field_refs。
- 验证方式：执行 `datalogue-api/.venv/bin/python -m py_compile datalogue-api/app/agentscope_service/bi_worker_context.py datalogue-api/app/prompts/agent_team.py datalogue-api/app/agentscope_service/bi_worker_runtime.py datalogue-api/app/services/query_plan_compiler.py` 通过；执行后端 targeted pytest `datalogue-api/.venv/bin/pytest datalogue-api/tests/test_query_plan_compiler.py datalogue-api/tests/test_bi_worker_progressive_context_tools.py datalogue-api/tests/test_bi_worker_query_runtime.py datalogue-api/tests/test_agentscope_service_tools.py datalogue-api/tests/test_agentscope_static_agent_registry.py datalogue-api/tests/test_agentscope_service_worker_logging.py datalogue-api/tests/test_agentscope_service_projection.py -q` 为 `111 passed, 74 warnings`；执行前端 targeted `cd datalogue-web && npm test -- agent-team-event-adapter chat-adapter MyMessage` 为 `3 files passed, 62 tests passed`；执行后端相关文件 `ruff check` 通过；执行 `cd datalogue-web && npm run lint && npm run build` 通过，保留既有 14 条 lint warning 与 Vite large chunk warning；执行 `git diff --check` 通过。
- 残留风险：当前代码的 `request_schema_slice` 已演进为“只列全量表和关系、不返回字段”，字段详情应走 `datalogue_describe_tables`；本轮验证到 describe field_refs、runtime alias→schema.table、compiler JOIN/SQL Guard 编译层，尚未重新启动后端做真实数据库查询 smoke。用户需要重启后端后再用 dataset_id=10 的“查询杨凯2024年日志”复测，若仍失败，应优先看 `execute_compiled_query` 的底层数据库错误（例如真实库字段大小写/方言/权限）。

### 2026-07-08 · BI Worker 只读工具统一绕过 AgentScope 权限引擎误拦截

- 涉及文件：`datalogue-api/app/agentscope_service/tools.py`、`datalogue-api/tests/test_agentscope_service_tools.py`、`.codex/project-memory.md`。
- 关键改动：用户 timeline 观察到「BI Worker 调试原文：datalogue_describe_tables 再次被拒绝」——AgentScope 2.0.3 的 DONT_ASK 权限引擎在 SubAgentTemplate 场景下会把裸 `FunctionTool` 判定为需要 confirmation 或直接 DENY,导致 progressive tools 被拒。此前 `datalogue_search_assets` 已踩过同一坑并通过自定义子类 `DatalogueSearchAssetsTool.check_permissions` 返回 ALLOW 绕过,但本轮新增的 `datalogue_describe_tables` 以及既有的 `prepare_query_context / request_schema_slice / repair_query_plan / select_candidate_datasets` 都还是裸 `FunctionTool`,同样会被拦。本轮把绕过逻辑抽成通用基类 `DatalogueBIWorkerReadOnlyTool(FunctionTool)`,`check_permissions` 直接返回 `PermissionBehavior.ALLOW + decision_reason="ALLOWED_BY_TOOL"`;`DatalogueSearchAssetsTool` 保留为别名指向新基类以兼容既有引用;`build_datalogue_progressive_bi_worker_tools` 里除 `datalogue_execute_query_plan_bundle`(is_read_only=False,故意走原权限引擎需要用户/leader 授权)外,`prepare_query_context / request_schema_slice / describe_tables / repair_query_plan` 全部改用新基类;`build_datalogue_select_candidate_datasets_tool` 同步改用新基类。所有 `is_read_only=True` 的 BI Worker 内部工具都是安全内省能力(不执行 SQL、不写数据),统一 ALLOW。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_service_tools.py tests/test_bi_worker_progressive_context_tools.py tests/test_agentscope_static_agent_registry.py tests/test_bi_worker_progressive_context_contracts.py tests/test_bi_worker_query_runtime.py tests/test_query_plan_compiler.py tests/test_bi_worker_query_validator.py tests/test_agentscope_service_worker_logging.py --tb=short` 为 `116 passed, 74 warnings`（含新增 1 条防回归测试 `test_progressive_readonly_tools_bypass_permission_engine`,断言所有 is_read_only=True 的 progressive/candidate 工具必须继承 DatalogueBIWorkerReadOnlyTool 且 check_permissions 返回 ALLOW/ALLOWED_BY_TOOL,覆盖 5 个核心只读工具）；`black` / `ruff check` 全部通过。
- 残留风险：这是对 AgentScope 2.0.3 权限引擎行为的补丁性绕过,若 AgentScope 版本升级修好了 DONT_ASK 分支的默认行为,本基类可以撤下。执行类工具 `datalogue_execute_query_plan_bundle` 保留 is_read_only=False + 裸 FunctionTool,继续依赖 AgentScope 权限引擎做用户授权确认,未来若需要静默执行需单独审慎评估。未跑真实页面 smoke,等待用户重启后端后 timeline 里应看到 `datalogue_describe_tables` 顺利执行不再出现「被拒绝」文本。

### 2026-07-08 · FIELD_NOT_FOUND 死循环系统性修复（契约+L4+runtime+prompt 四层）

- 涉及文件：`datalogue-api/app/agentscope_service/bi_worker_contracts.py`、`datalogue-api/app/agentscope_service/bi_worker_validator.py`、`datalogue-api/app/agentscope_service/bi_worker_runtime.py`、`datalogue-api/app/agentscope_service/bi_worker_context.py`、`datalogue-api/app/services/query_plan_compiler.py`、`datalogue-api/app/prompts/agent_team.py`、`datalogue-api/tests/test_bi_worker_progressive_context_contracts.py`、`datalogue-api/tests/test_bi_worker_query_validator.py`、`datalogue-api/tests/test_bi_worker_query_runtime.py`、`datalogue-api/tests/test_bi_worker_progressive_context_tools.py`、`.codex/project-memory.md`。
- 关键改动：用户报告即便 LLM 已经调完四步链路(prepare/slice/describe/bundle),execute_query_plan_bundle 仍持续报 FIELD_NOT_FOUND 并循环建议再调 request_schema_slice。系统性诊断出三个耦合根因:(1) FieldTarget.asset_ref 契约无格式约束,LLM 可以写 "asset:primary" / "log.rzrq" / 纯字段名等错误格式;(2) L4 用精确字符串成员判断,LLM 忘 merge describe_tables 的 context_state_patch 就必挂;(3) FIELD_NOT_FOUND 的 recommended_action 让 LLM 再调 request_schema_slice —— 但该工具解耦后只返表清单不返字段,循环。本轮四层同步修复:(A) `bi_worker_contracts.py:52-94` FieldTarget.asset_ref 增加 pydantic pattern 白名单(前缀必须是 table/asset/field + 冒号 + 至少一个 . 分隔的路径,支持中文表名 一-龥),并新增 `normalized_field_ref` property 把表级 ref+field 拼成字段级 ref;`bi_worker_contracts.py:313-321` 更新 FAILURE_DIAGNOSIS_MAP[FIELD_NOT_FOUND].recommended_action 为对症引导(明确 table:schema.table.field 规范格式 + context_state_patch.field_refs 合并 + describe_tables 二次确认字段名)。(B) `bi_worker_validator.py:105-114` _collect_missing_context 用 normalized_field_ref 优先匹配 field_refs,允许 LLM 传表级 ref+field 拆分形式命中。(C) `bi_worker_runtime.py:37,54-64,397-421` 新增顶层 `_derive_dataset_field_refs` 从 dataset 元数据推导所有 (schema, table, column) 组合成字段级 ref 集合,并新增实例方法 `_get_dataset` 返回 SemanticDataset | None(db=None 时返回 None 而非抛错),`execute_query_plan` 在 L4 校验前主动 union 到 context_state.field_refs/asset_refs,让 LLM 完全忘 merge 时也能通过校验。(D) `agent_team.py:50-53` 强化 asset_ref 规范格式约束 + 新增 context_state 三次 patch 合并强制引导条 + minimal_detail_query_plan 示例从 asset:primary.* 替换为 table:<schema>.<table>[.<field>]。(E) 顺带补漏 `bi_worker_context.py:describe_tables` 加 context_state_patch 输出(此前解耦时漏了),`query_plan_compiler.py:_table_from_field_ref` 修复表级 ref (table:schema.table) 被错误解析成 (schema, table 字段) 的边界。
- 协作方式：Workflow 4 subagent 并行调度(316568 tokens、84 工具调用)—— 2 个 Implement subagent 并行做 contracts+validator / runtime+prompt,1 个 Tests subagent 覆盖 4 层新增 16 条测试,1 个 Verify subagent adversarially 主动发现并修复 2 处问题(`_get_dataset` fail-closed 太激进导致 8 个 pre-existing 老测试炸掉 + `_derive_dataset_field_refs` 对残缺元数据不够鲁棒需要 getattr 全防),单次通过全绿。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_worker_progressive_context_contracts.py tests/test_bi_worker_query_validator.py tests/test_bi_worker_query_runtime.py tests/test_bi_worker_progressive_context_tools.py tests/test_agentscope_service_tools.py tests/test_bi_worker_progressive_context_e2e.py tests/test_query_plan_compiler.py tests/test_agentscope_service_worker_logging.py --tb=short` 为 `126 passed, 74 warnings`(含新增 16 条:11 契约层 pattern/normalized_ref/recommended_action + 1 validator normalized 匹配 + 4 runtime dataset 兜底);`black` / `ruff check` 全通过;`mypy` 剩余错误全部是仓库预先存在的历史类型债,本轮改动文件未引入新错误。
- 残留风险：契约层 asset_ref pattern 是**破坏性变更**,若有历史 test/prod 里存在 "asset:primary" 之类的旧格式会挂;本轮已识别并同步更新所有测试。runtime 自动 merge dataset 全部字段 ref 意味着 LLM 引用未在 describe_tables 里看到的字段也能通过 L4——这不是安全漏洞(字段属于 dataset,不越权),但可能让 LLM 决策不完整(建议 recommended_action 里已提示"建议先调 describe_tables 确认字段语义")。未跑真实页面 smoke,等待用户重启后端后用"查询杨凯 2025 年工作日志"实际验证,期望 timeline:LLM 用规范 asset_ref 格式一次成功,或即便格式错也被契约 Repair 链路 A 拦下并给出正确格式引导,不再走到 L4 死循环。

### 2026-07-08 17:05 · BI Worker context_state list/set 类型错误与执行异常日志兜底

- 涉及文件：`datalogue-api/app/agentscope_service/bi_worker_runtime.py`、`datalogue-api/app/agentscope_service/tools.py`、`datalogue-api/tests/test_bi_worker_query_runtime.py`、`datalogue-api/tests/test_agentscope_service_tools.py`、`.codex/project-memory.md`。
- 关键改动：修复 `datalogue_execute_query_plan_bundle` 在 dataset 字段 ref 兜底阶段执行 `context_state.field_refs | derived_refs` 时，因为工具 JSON 入参把 `asset_refs/relationship_refs/field_refs` 反序列化为 list 而触发 `unsupported operand type(s) for |: 'list' and 'set'` 的后端类型错误。`BIWorkerQueryRuntime.execute_query_plan()` 入口新增 `_normalize_context_state_refs()`，在任何集合运算和 L4 校验前统一把三类 refs 收敛为 `set`；`tools.py` 对 runtime 未预期异常新增 `logger.exception`，并返回结构化 `dataset_query_result/status=failed/failure_type=FIELD_NOT_FOUND`，避免异常只以 AgentScope tool error 出现在 timeline 而不进后端错误日志。
- 验证方式：先补失败测试 `test_execute_query_plan_normalizes_json_list_refs_before_dataset_merge` 复现 `list | set` TypeError，再补 `test_execute_query_plan_bundle_logs_runtime_exception` 复现工具层无日志、无结构化失败 payload；实现后执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_worker_query_runtime.py::test_execute_query_plan_normalizes_json_list_refs_before_dataset_merge tests/test_agentscope_service_tools.py::test_execute_query_plan_bundle_logs_runtime_exception -q` 为 `2 passed, 2 warnings`；执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_worker_query_runtime.py -q` 为 `22 passed, 2 warnings`；执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_service_tools.py -q` 为 `16 passed, 2 warnings`。
- 残留风险：本轮修复到单元/工具层，未重新启动后端做真实页面 smoke；如果正在运行的后端进程未重启，仍会使用旧代码。工具层异常兜底目前映射到既有 `FIELD_NOT_FOUND` 安全诊断，后续如果需要更准确区分平台内部异常，可新增独立 `INTERNAL_RUNTIME_ERROR` failure type。

### 2026-07-08 · BI Worker execute_query_plan_bundle 后端日志增强

- 涉及文件: datalogue-api/app/agentscope_service/bi_worker_runtime.py, datalogue-api/app/agentscope_service/tools.py, .codex/project-memory.md
- 关键改动: 用户报告排查 FIELD_NOT_FOUND 时后端日志缺少上下文——原代码只在抛异常时 logger.exception, 但 90% 的失败(L4 校验/FILTER_MISSING/bridge blocked/EMPTY_RESULT)都是正常返回 payload, 不进 except, 日志空白。本轮:(A) bi_worker_runtime.py 顶部初始化 logger, execute_query_plan 每个分支加结构化日志:START 摘要(dataset_id/trace_id/intent/primary_asset/dimension counts)、dataset ref 兜底前后 counts、L4 每条 missing_context 逐条 warning + L4 FAILED 汇总、FILTER_MISSING、EXECUTE EXCEPTION 用 logger.exception 保留 traceback、BRIDGE FAILED、EMPTY_RESULT、SUCCESS。(B) tools.py wrapper 加 REQUEST 摘要、context_state 过滤后 dropped_keys、CONTRACT ERROR 摘要、结尾按 status/failure_type 分类打 RESPONSE OK/RESPONSE FAILED。所有日志避免 raw SQL / raw values, 只打安全 dimension(count/failure_type/asset_ref 前缀/missing_context 列表)。
- 验证方式: cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_worker_query_runtime.py tests/test_agentscope_service_tools.py tests/test_bi_worker_progressive_context_contracts.py tests/test_bi_worker_progressive_context_e2e.py tests/test_query_plan_compiler.py --tb=short 为 71 passed; --log-cli-level=INFO 实测输出确认 START/dataset ref 兜底/SUCCESS 三行结构化日志。black/ruff 通过。
- 残留风险: 异常路径的 logger.exception 会包含完整 traceback(可能含 SQL 片段), 只写文件日志不进用户可见通道, 但生产环境如果 log 采集到 SIEM 需注意脱敏。若后续有必要, 可用 hash 或 sanitize 替换 exc_msg。

### 2026-07-08 17:57 · datalogue_execute_query_plan_bundle 完整链路文档

- 涉及文件：`docs/architecture/datalogue_execute_query_plan_bundle完整链路.md`、`.codex/project-memory.md`。
- 关键改动：根据当前代码梳理 `datalogue_execute_query_plan_bundle` 从 Agent Team / BI Worker 上游工具顺序，到 wrapper 契约校验、`BIWorkerQueryRuntime.execute_query_plan` L4/L5 分界、`QueryPlan -> legacy query_plan dict` 投影、`AgentScopeDatasetRuntimeBridge.run_direct_query` 状态机、BI Atomic Toolkit compile/execute/artifact、失败与 repair 分支、TeamSay/message.completed/Workbench 消费的完整链路。文档补充两张 Mermaid 图：主流程图和 Bridge/Atomic Toolkit 时序图，并给出排障日志关键词索引。
- 验证方式：基于 CodeGraph 读取 `tools.py`、`bi_worker_runtime.py`、`bi_worker_contracts.py`、`runtime_bridge.py`、`atomic.py`、`bi_worker_context.py` 和 `agent_team.py` 相关片段；新增文档后执行人工通读，确认 Mermaid 代码块、章节编号和关键代码入口路径完整。
- 残留风险：本轮是只读链路文档生成，未运行后端/前端测试，也未做真实页面 smoke；若后续代码继续调整 `AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE`、`BIWorkerQueryPlan` 契约或 Workbench 投影，需要同步更新本文档。

### 2026-07-08 18:32 · datalogue_execute_query_plan_bundle 工具设计图与 Obsidian 同步

- 涉及文件：`docs/architecture/datalogue_execute_query_plan_bundle完整链路.md`、`docs/architecture/assets/datalogue_execute_query_plan_bundle_internal_chain.png`、`/Users/yangkai/KenYang/文档库/develop-doc-repositry/工作知识库/2026/数语/工具链路文档/datalogue_execute_query_plan_bundle/datalogue_execute_query_plan_bundle 工具设计.md`、`/Users/yangkai/KenYang/文档库/develop-doc-repositry/工作知识库/2026/数语/工具链路文档/datalogue_execute_query_plan_bundle/assets/datalogue_execute_query_plan_bundle_internal_chain.png`、`.codex/project-memory.md`。
- 关键改动：按用户要求把 imagegen 生成的聚焦版工具内部执行链路图复制进项目文档 assets 和 Obsidian 知识库；在项目 markdown 顶部插入图片，并在 Obsidian 的“数语/工具链路文档/datalogue_execute_query_plan_bundle”下新建单独工具设计文档。Obsidian 文档不再按完整对话链路叙述，而是围绕工具设计展开：设计定位、输入契约、wrapper 校验层、Runtime L4、L5 受控执行、Bridge direct query、Atomic Toolkit、输出契约、失败/repair 策略、安全边界和排障索引。
- 验证方式：执行 `view_image` 确认选用的是仅包含 `datalogue_execute_query_plan_bundle` tool 内部链路的聚焦版图片；复制后检查 Obsidian 目录、项目 assets、markdown 图片引用和文档正文均存在。
- 残留风险：图片是 imagegen 生成的 raster infographic，局部英文/符号排版可能不如手工 Mermaid 精准；后续若作为正式设计评审材料，建议基于当前文档再补一版可维护 Mermaid 或 draw.io 源文件。

### 2026-07-08 18:38 · 其他 BI Worker 工具设计文档与工具族图

- 涉及文件：`docs/architecture/BI Worker工具族设计.md`、`docs/architecture/assets/bi_worker_tool_family_design.png`、`/Users/yangkai/KenYang/文档库/develop-doc-repositry/工作知识库/2026/数语/工具链路文档/BI Worker 工具族设计.md`、Obsidian 下 `datalogue_select_candidate_datasets`、`datalogue_search_assets`、`datalogue_prepare_query_context`、`datalogue_request_schema_slice`、`datalogue_describe_tables`、`datalogue_repair_query_plan` 六个工具目录与设计文档、`.codex/project-memory.md`。
- 关键改动：根据当前 `tools.py` 与 `BIWorkerContextProvider` 真实实现，为 execute bundle 之外的 6 个 BI Worker 工具生成单独工具设计文档；每篇按设计定位、所在位置、输入契约、输出契约、内部执行、设计重点、安全边界、失败/降级和排障入口组织。使用 Image Gen 生成一张“BI Worker 工具族设计图（execute_query_plan_bundle 之外）”，并复制到项目文档 assets 和 Obsidian `工具链路文档/assets`。
- 验证方式：使用 CodeGraph 读取 `build_datalogue_search_assets_tool`、`build_datalogue_progressive_bi_worker_tools`、`build_datalogue_select_candidate_datasets_tool` 的真实签名和工具注册；使用 `view_image` 检查生成图聚焦工具族设计而非完整对话链路；检查项目与 Obsidian 文件路径均存在。
- 残留风险：本轮是文档与图片整理，未运行后端/前端测试；Image Gen 生成的图片属于 raster 资产，若后续要做精确版本管理，建议追加 Mermaid/draw.io 源文件。

### 2026-07-08 18:59 · BI Worker 单工具内部执行链路图补齐

- 涉及文件：Obsidian 下 `datalogue_select_candidate_datasets`、`datalogue_search_assets`、`datalogue_prepare_query_context`、`datalogue_request_schema_slice`、`datalogue_describe_tables`、`datalogue_repair_query_plan` 六份工具设计文档、`.codex/project-memory.md`。
- 关键改动：针对用户指出“单工具文档没有内部执行链路图”的问题，为 6 份 Obsidian 工具设计文档逐一补充 Mermaid `内部执行链路图`。每张图按当前代码真实执行顺序展开，包括入参校验、SessionLocal/ContextProvider 调用、payload 组装、失败/降级分支、安全边界和后续工具约束。
- 验证方式：执行 `rg -n "内部执行链路图" .../工具链路文档` 确认 6 个目标工具文档均已新增该章节，并抽查 `datalogue_describe_tables`、`datalogue_prepare_query_context` 文档内容。
- 残留风险：本轮补的是 Obsidian Mermaid 可维护图，不是 Image Gen raster 图；若后续需要对外汇报版视觉图，可基于这些 Mermaid 再单独生成正式图片。

### 2026-07-08 19:12 · BI Worker 单工具 Image Gen 内部链路图补齐

- 涉及文件：Obsidian 下 `datalogue_select_candidate_datasets/assets/datalogue_select_candidate_datasets_internal_chain.png`、`datalogue_search_assets/assets/datalogue_search_assets_internal_chain.png`、`datalogue_prepare_query_context/assets/datalogue_prepare_query_context_internal_chain.png`、`datalogue_request_schema_slice/assets/datalogue_request_schema_slice_internal_chain.png`、`datalogue_describe_tables/assets/datalogue_describe_tables_internal_chain.png`、`datalogue_repair_query_plan/assets/datalogue_repair_query_plan_internal_chain.png`，以及对应 6 份工具设计文档、`.codex/project-memory.md`。
- 关键改动：按用户明确要求，为 6 个 BI Worker 单工具分别使用 Image Gen 生成 raster 内部执行链路图，并复制到每个工具目录的 `assets/` 下；每份工具设计文档的“内部执行链路图”章节现在优先展示 Image Gen 图片，原 Mermaid 图仅保留为后续可维护的结构化补充。
- 验证方式：复制后检查 6 张 PNG 均存在；使用 `rg -n "Image Gen 生成的工具内部执行链路图|internal_chain.png" .../工具链路文档/datalogue_*/*.md` 确认 6 份文档均引用对应图片。
- 残留风险：Image Gen 图片是位图资产，文字和节点排版不可像 Mermaid 一样直接版本化编辑；后续如果代码链路变化，需要重新生成图片或同步维护下方 Mermaid。

### 2026-07-09 09:40 · BI Worker 调试原文格式错乱修复（前端保真 + 后端 delta 缓冲）

- 涉及文件：`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/chat-adapter.test.js`、`datalogue-web/src/assistant/MyMessage.jsx`、`datalogue-web/src/assistant/MyMessage.test.jsx`、`datalogue-web/src/styles.css`、`datalogue-api/app/agentscope_service/worker_logging.py`、`datalogue-api/tests/test_agentscope_service_worker_logging.py`。
- 关键改动：
  - 前端 `appendRawThinkingDelta` 收敛为纯拼接，删除按 `[A-Za-z0-9]` 边界补空格的分支，避免破坏 `plan_task_daily_record`/`2025`/`LIMIT` 等标识符/数字/关键字。
  - 前端 `ReasoningText` 增加 raw debug 分支：`part.debugRaw === true || part.reasoningKind === 'bi_worker_raw_thinking_delta'` 命中时用 `<pre className="cot-ant-raw" aria-label="BI Worker 调试原文">` 忠实渲染，跳过 `splitThinkingSegments`；新增 `.cot-ant-raw` 等宽 + `pre-wrap` + 320px 最大高度样式。
  - 后端 `_publish_thinking_progress` 引入 per-stream_group_id raw delta 缓冲：delta 累积到"结尾为空白/中英标点/换行"或"长度 ≥ 64"才 emit，`phase='end'` 与 `on_reply` 主循环走完后各兜底 flush 一次，解决模型 API 按 tokenizer 边界切碎 delta 导致 UI 词内断裂。
- 验证方式：`pytest tests/test_agentscope_service_worker_logging.py`（33/33 通过，含新增 `test_bi_worker_thinking_debug_merges_tokenizer_split_deltas`）；`black + ruff` 无 diff/告警；前端 `vitest run src/assistant/chat-adapter.test.js src/assistant/MyMessage.test.jsx`（50/50 通过）；`eslint` 4 个改动文件全绿。
- 残留风险：如果 LLM 供应商返回的单个 chunk **本身**就带前导空格（例如 `left_al` + ` ias`），后端缓冲策略无法在不误伤合法空格（如 `alias: "p"`）的前提下消除该空格；这类情况需在后端"完整 thinking end-only 一次性 emit"通道另行处理。

### 2026-07-09 12:18 · Datalogue 目录治理 Phase A/B 完成记录

- 涉及文件：`docs/architecture/目录治理与模块边界.md`、`.omx/context/directory-planning/current-directory-snapshot.md`、`datalogue-api/app/domains/**`、`datalogue-api/app/agentscope_runtime/**`、`datalogue-api/tests/test_directory_facades.py`、`.codex/project-memory.md`。
- 关键改动：Phase A 完成目录治理设计落档，新增架构文档说明当前目录边界、模块职责和迁移约束，并在 `.omx` ignored 上下文中记录当前目录快照；Phase B 新增 `domains` 与 `agentscope_runtime` facade-first 包骨架，用轻量门面先稳定未来迁移入口，同时补 `test_directory_facades.py` 固化导入边界。全程不移动旧源码、不改旧调用方导入、不改变 AgentScope 主链、不改变 BI Worker 查询语义。
- 验证方式：执行 `cd datalogue-api && ../datalogue-api/.venv/bin/python -m py_compile $(find app/domains app/agentscope_runtime -name '*.py' | sort) tests/test_directory_facades.py && ../datalogue-api/.venv/bin/pytest tests/test_directory_facades.py`，结果为 `4 passed, 2 warnings in 0.02s`。
- 残留风险或后续事项：本轮只是目录治理 Phase A/B 的文档与 facade 骨架，不做旧源码搬迁和调用方切换；后续如推进真实模块迁移，需要继续保持 facade-first、分批改导入、补回归测试，并确认 AgentScope 主链与 BI Worker 查询语义不发生漂移。

### 2026-07-09 13:50 · Workbench 去常驻化第一批（普通 Chat 退面板 + 隐藏恢复壳分类器）

- 涉及文件：`datalogue-web/src/components/chat-page.jsx`、`datalogue-web/src/components/chat-page.test.jsx`、`datalogue-web/src/components/workbench-route.jsx`、`datalogue-web/src/assistant/workbench-mount-source.js`、`datalogue-web/src/assistant/workbench-mount-source.test.js`。
- 关键改动：普通 `/chat` 与 `/chat/:id` 不再默认挂载 `WorkbenchPanel`，把 Workbench 常驻侧栏从 Chat 主链上摘掉；新增 `classifyWorkbenchMountSource` 和 `isAllowedWorkbenchRecoverySource`，把普通聊天、隐藏恢复壳、旧镜像、显式恢复分成 fail-closed 的受控来源；`/workbench` 隐藏路由仍保留，但仅在恢复来源合法时渲染；补测试确认普通 Chat 不再出现工作台面板，同时覆盖普通聊天、隐藏恢复壳、旧镜像、显式恢复与冲突输入的分类结果。


- 完成时间：2026-07-09 12:45。
- 功能名称：数据源适配 domain 下沉与 Workbench 挂载源收口。
- 涉及文件：`.gitignore`、`datalogue-api/app/domains/data_source/adapters/base.py`、`datalogue-api/app/domains/data_source/adapters/hive.py`、`datalogue-api/app/domains/data_source/adapters/oracle.py`、`datalogue-api/app/domains/data_source/adapters/registry.py`、`datalogue-api/app/domains/data_source/service.py`、`datalogue-api/tests/test_directory_facades.py`、`datalogue-web/src/assistant/workbench-mount-source.js`、`datalogue-web/src/assistant/workbench-mount-source.test.js`、`datalogue-web/src/components/chat-page.jsx`、`datalogue-web/src/components/chat-page.test.jsx`、`datalogue-web/src/components/workbench-route.jsx`，并删除根目录临时验收截图 `chat-e2e-initial.png`、`chat-e2e-thread.png`。
- 关键改动：将数据源能力、上下文、诊断、adapter 注册和 Oracle/Hive 连接逻辑继续下沉到 `domains/data_source/adapters` 边界，`service.py` 收敛为面向 API 的应用服务入口；补强目录 facade 测试，确保旧服务入口仍能稳定导入；前端新增 `workbench-mount-source` 统一判断 Workbench 挂载来源，Chat 页面和 Workbench 路由按同一来源语义展示/挂载，避免页面侧重复推断；`.gitignore` 补充 E2E 临时图规则并移除已追踪临时截图。
- 验证方式：执行 `cd datalogue-api && ../datalogue-api/.venv/bin/python -m py_compile app/services/datasource.py $(find app/domains/data_source -name '*.py' | sort) tests/test_directory_facades.py` 通过；执行 `cd datalogue-api && ../datalogue-api/.venv/bin/pytest tests/test_directory_facades.py tests/test_datasource.py -q`，结果 `14 passed, 2 warnings`；执行 `cd datalogue-api && ../datalogue-api/.venv/bin/pytest tests/test_dataset.py -q -k "sql_preview or datasource"`，结果 `6 passed, 27 deselected, 10 warnings`。


### 2026-07-09 14:10 · 查询执行 SQL Guard 与方言基础工具 domain 下沉

- 完成时间：2026-07-09 14:10。
- 功能名称：查询执行 SQL Guard 与方言基础工具 domain 下沉。
- 涉及文件：`datalogue-api/app/domains/query_execution/__init__.py`、`datalogue-api/app/domains/query_execution/guard.py`、`datalogue-api/app/domains/query_execution/dialect/__init__.py`、`datalogue-api/app/domains/query_execution/dialect/names.py`、`datalogue-api/app/utils/__init__.py`、`datalogue-api/app/utils/sql_dialect.py`、`datalogue-api/app/utils/sql_guard.py`、`datalogue-api/app/services/sql_dialect_adapter.py`、`datalogue-api/app/services/sql_preview.py`、`datalogue-api/app/services/analysis_blueprint.py`、`datalogue-api/tests/test_directory_facades.py`。
- 关键改动：将 `quote_ident`、`resolve_dialect`、`sanitize_filter_sql`、`contains_forbidden_keyword` 等方言基础工具下沉到 `domains/query_execution/dialect/names.py`；将 `SQLGuardResult` 与 `guard_readonly_sql` 的真实实现下沉到 `domains/query_execution/guard.py`；旧 `app/utils/sql_dialect.py`、`app/utils/sql_guard.py` 改为兼容 re-export 门面；`query_execution` 与 `dialect` 包入口改为懒加载，避免新旧路径并存期间触发 query_plan_compiler / sql_guard 循环导入；上层 `sql_dialect_adapter`、`sql_preview`、`analysis_blueprint` 改用 domain 实现源。
- 验证方式：执行 `cd datalogue-api && ../datalogue-api/.venv/bin/pytest tests/test_directory_facades.py tests/test_sql_guard.py tests/test_sql_dialect_adapter.py -q`，结果 `24 passed, 2 warnings`；执行 `cd datalogue-api && ../datalogue-api/.venv/bin/python -m py_compile app/domains/query_execution/__init__.py app/domains/query_execution/guard.py app/domains/query_execution/dialect/__init__.py app/domains/query_execution/dialect/names.py app/services/sql_dialect_adapter.py app/services/sql_preview.py app/services/analysis_blueprint.py app/utils/__init__.py app/utils/sql_dialect.py app/utils/sql_guard.py tests/test_directory_facades.py && ../datalogue-api/.venv/bin/pytest tests/test_query_plan_compiler.py tests/test_dataset.py -q -k "sql_preview or datasource or dialect"`，结果 `8 passed, 40 deselected, 10 warnings`。
- 残留风险或后续事项：本轮完成 G040 的纯工具下沉与旧路径 facade；尚未迁移 `sql_dialect_adapter.py`、`query_plan_compiler.py`、`sql_preview.py` 的真实实现主体，对应 G041-G043 仍待后续分批推进。


### 2026-07-09 14:35 · 查询计划编译器与 SQL 方言适配器 domain 下沉

- 完成时间：2026-07-09 14:35。
- 功能名称：查询计划编译器与 SQL 方言适配器 domain 下沉。
- 涉及文件：`datalogue-api/app/domains/query_execution/compiler.py`、`datalogue-api/app/domains/query_execution/dialect/adapter.py`、`datalogue-api/app/services/query_plan_compiler.py`、`datalogue-api/app/services/sql_dialect_adapter.py`、`datalogue-api/app/bi/toolkit/atomic.py`、`datalogue-api/tests/test_directory_facades.py`。
- 关键改动：将 `adapt_sql_for_execution`、`normalize_supported_dialect`、`quote_identifier` 真实实现下沉到 `domains/query_execution/dialect/adapter.py`；将 `compile_query_plan_to_sql` 真实实现下沉到 `domains/query_execution/compiler.py`；旧 `app/services/sql_dialect_adapter.py` 与 `app/services/query_plan_compiler.py` 改为兼容 re-export 门面；BI Toolkit 内部调用切到 domain compiler，测试和历史调用方仍可走旧 service facade；补 facade 测试确保旧路径与新 domain 对象同源，避免迁移期出现两套 SQL 编译/适配规则。
- 验证方式：执行 `cd datalogue-api && ../datalogue-api/.venv/bin/python -m py_compile app/domains/query_execution/compiler.py app/domains/query_execution/dialect/adapter.py app/services/query_plan_compiler.py app/services/sql_dialect_adapter.py app/bi/toolkit/atomic.py tests/test_directory_facades.py && ../datalogue-api/.venv/bin/pytest tests/test_directory_facades.py tests/test_sql_dialect_adapter.py tests/test_query_plan_compiler.py -q`，结果 `26 passed, 2 warnings`；执行 `cd datalogue-api && ../datalogue-api/.venv/bin/pytest tests/test_dataset.py -q -k "sql_preview or datasource" && ../datalogue-api/.venv/bin/pytest tests/test_bi_worker_query_runtime.py -q`，结果分别为 `6 passed, 27 deselected, 10 warnings` 与 `22 passed, 2 warnings`。
- 残留风险或后续事项：本轮完成 G041；`sql_preview.py` 真实实现仍在 `app/services`，按计划由 G042 单独迁移，并继续保持执行器通过 `create_engine_for_datasource()`。


### 2026-07-09 14:55 · SQL Preview 执行服务 domain 下沉

- 完成时间：2026-07-09 14:55。
- 功能名称：SQL Preview 执行服务 domain 下沉。
- 涉及文件：`datalogue-api/app/domains/query_execution/preview.py`、`datalogue-api/app/services/sql_preview.py`、`datalogue-api/app/api/dataset.py`、`datalogue-api/app/agents/bi_agent/runtime_context.py`、`datalogue-api/tests/test_dataset.py`、`datalogue-api/tests/test_directory_facades.py`。
- 关键改动：将 `preview_dataset_sql` 真实实现下沉到 `domains/query_execution/preview.py`，并继续通过 `domains.data_source.service.create_engine_for_datasource()` 创建数据源执行引擎；旧 `app/services/sql_preview.py` 改为兼容 re-export 门面；Dataset API 与 BI runtime context 改用 domain preview；测试 monkeypatch 路径切到 domain preview 的 `create_engine_for_datasource`，并补 facade 测试确认旧 service 与新 domain 对象同源。
- 验证方式：执行 `cd datalogue-api && ../datalogue-api/.venv/bin/python -m py_compile app/domains/query_execution/preview.py app/services/sql_preview.py app/api/dataset.py app/agents/bi_agent/runtime_context.py tests/test_dataset.py tests/test_directory_facades.py && ../datalogue-api/.venv/bin/pytest tests/test_directory_facades.py tests/test_dataset.py -q -k "sql_preview or datasource or query_execution_preview"`，结果 `8 passed, 33 deselected, 10 warnings`；执行 `cd datalogue-api && ../datalogue-api/.venv/bin/pytest tests/test_bi_worker_query_runtime.py tests/test_query_plan_compiler.py tests/test_sql_dialect_adapter.py -q`，结果 `41 passed, 2 warnings`。
- 残留风险或后续事项：本轮完成 G042；`artifact_store.py`、`repair_plan.py` 仍待 G043 迁移，SQL 不泄露与 artifact ref 约束测试仍在 G048 汇总验证。

### 2026-07-09 14:24 · Workbench 去常驻化第二批（Chat retry 承接 + 退役闸门）

- 完成时间：2026-07-09 14:24。
- 功能名称：Workbench 去常驻化第二批（Chat retry 承接 + 退役闸门）。
- 涉及文件：`datalogue-web/src/assistant/MyMessage.jsx`、`datalogue-web/src/assistant/MyMessage.test.jsx`、`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/chat-adapter.test.js`、`datalogue-web/src/assistant/workbench-retention-gate.js`、`datalogue-web/src/assistant/workbench-retention-gate.test.js`。
- 关键改动：Chat 侧 `ArtifactCard` 的 retry 动作改为先发起受控 `/api/workbench/actions/retry`，成功后把后端返回的 `task_request` 写入 `window.__DATALOGUE_PENDING_WORKBENCH_RETRY__` 并通过 `datalogue:composer-submit` 交给既有 Chat 主链；`chat-adapter` 继续消费 pending retry 并把 `retry_checkpoint_ref` 交给 Agent Team；新增纯函数 `evaluateWorkbenchRetentionGate`，按 14 天 UTC 窗口汇总 `/api/workbench/*` 与 `/workbench/*` 的主路径/恢复流量，并用 Chat 侧 artifact 详情承接总量对比 `expected_artifact_detail_total`，作为 Workbench 彻底退役的机器闸门。
- 验证方式：执行 `cd datalogue-web && npm test -- src/assistant/workbench-retention-gate.test.js src/assistant/MyMessage.test.jsx`，结果 `25 passed`；执行 `cd datalogue-web && npm run lint`，结果 0 errors、14 个既有 warnings；执行 `cd datalogue-web && npm run build` 成功产出前端构建。
- 残留风险或后续事项：`expected_artifact_detail_total` 目前支持显式输入与前端投影式兜底两种口径，后续若要接入真实埋点，还需要把 Chat 侧 artifact 详情“应出现”指标标准化到统一事件名；`/workbench` 隐藏壳与 `/api/workbench/*` 仍保留，需等主路径流量归零后再做最终退役。

### 2026-07-09 14:42 · Workbench retention gate 标准事件测试补强

- 完成时间：2026-07-09 14:42。
- 功能名称：Workbench retention gate 标准事件测试补强。
- 涉及文件：`datalogue-web/src/assistant/workbench-retention-gate.js`、`datalogue-web/src/assistant/workbench-retention-gate.test.js`、`.codex/project-memory.md`。
- 关键改动：`workbench-retention-gate.test.js` 引入 `buildArtifactDetailExpectedEvent` 与 `buildArtifactDetailViewEvent`，补齐标准 Chat 侧 `artifact_detail_expected/artifact_detail_view` 事件能驱动退役闸门通过的覆盖；新增恢复/旧镜像来源误计数回归，确保 `/workbench` 来源即使带标准详情事件名，也不能被算作 Chat 侧详情承接。`workbench-retention-gate.js` 将 expected/actual artifact 详情统计收紧为普通 `/chat` 路由和 `ordinary_chat/ordinary_chat_history` 来源，避免 Workbench 隐藏恢复壳或 legacy mirror 事件反向证明主路径已完成承接。
- 验证方式：先执行 `cd datalogue-web && npm test -- src/assistant/workbench-retention-gate.test.js`，新增回归用例按预期失败，错误为 `expected true to be false`；实现后同一命令通过，结果 `7 passed`。继续执行 `cd datalogue-web && npm test -- src/assistant/workbench-retention-gate.test.js src/assistant/workbench-retention-events.test.js src/assistant/MyMessage.test.jsx`，结果 `31 passed`；执行 `cd datalogue-web && npm run lint`，结果 0 errors、14 个既有 warnings；执行 `cd datalogue-web && npm run build` 成功。
- 残留风险或后续事项：当前闸门仍依赖前端 UI/API 事件输入，尚未接入真实线上 analytics；后续做最终退役时，需要用真实 14 天窗口事件数据喂给 `evaluateWorkbenchRetentionGate`，并继续保留隐藏恢复壳的恢复流量统计。


### 2026-07-09 15:15 · ArtifactStore 与 RepairPlan 服务 domain 下沉

- 完成时间：2026-07-09 15:15。
- 功能名称：ArtifactStore 与 RepairPlan 服务 domain 下沉。
- 涉及文件：`datalogue-api/app/domains/query_execution/artifact_store.py`、`datalogue-api/app/domains/query_execution/repair_plan.py`、`datalogue-api/app/services/artifact_store.py`、`datalogue-api/app/services/repair_plan.py`、`datalogue-api/app/api/artifacts.py`、`datalogue-api/app/services/workbench_view_model.py`、`datalogue-api/app/agents/bi_agent/native_handoff.py`、`datalogue-api/app/bi/toolkit/atomic.py`、`datalogue-api/tests/test_directory_facades.py`。
- 关键改动：将 `ArtifactStore`、`ArtifactPayloadTooLargeError` 与 `ArtifactKind` 真实实现下沉到 `domains/query_execution/artifact_store.py`；将 RepairPlan 分类、校验、脱敏摘要与 artifact payload 清洗能力下沉到 `domains/query_execution/repair_plan.py`；旧 `app/services/artifact_store.py`、`app/services/repair_plan.py` 改为兼容 re-export 门面；Artifacts API、Workbench ViewModel、BI native handoff、BI Toolkit 内部调用切到 domain 实现源；补 facade 测试确保旧 service 与新 domain 对象同源，避免 Artifact/RepairPlan 出现两套安全边界。
- 验证方式：执行 `cd datalogue-api && ../datalogue-api/.venv/bin/python -m py_compile app/domains/query_execution/artifact_store.py app/domains/query_execution/repair_plan.py app/services/artifact_store.py app/services/repair_plan.py app/api/artifacts.py app/services/workbench_view_model.py app/agents/bi_agent/native_handoff.py app/bi/toolkit/atomic.py tests/test_directory_facades.py && ../datalogue-api/.venv/bin/pytest tests/test_directory_facades.py tests/test_artifact_api.py tests/test_repair_plan_contract.py -q`，结果 `29 passed, 2 warnings`；执行 `cd datalogue-api && ../datalogue-api/.venv/bin/pytest tests/test_workbench_view_api.py tests/test_agentscope_dataset_query_executor.py tests/test_bi_lead_agent_native_handoff.py tests/test_bi_worker_query_runtime.py -q`，结果 `45 passed, 2 warnings`。
- 残留风险或后续事项：本轮完成 G043；G044-G048 将继续以测试闸门形式复核 SQL Guard、方言适配、QueryPlan 编译、BI worker runtime 与 SQL/artifact 安全边界。
### 2026-07-09 15:16 · 管理员密码手动重置

- 涉及文件：`.codex/project-memory.md`
- 关键改动：通过一次性数据库脚本将 `admin` 用户 `hashed_password` 重置为 `admin` 对应哈希，避免因历史引导密码与 `.env` 预期不一致导致登录 401。
- 验证方式：执行 `python -c` 重置后即时调用 `verify_password('admin', u.hashed_password)`，输出 `reset_done=True`。
- 残留风险：`admin/admin` 仅适用于本地临时调试，后续应尽快改回强密码并通过环境变量/运维流程管理。

### 2026-07-09 15:28 · 新建用户功能页面上线

- 涉及文件：`datalogue-web/src/components/user-create.jsx`、`datalogue-web/src/App.jsx`、`datalogue-web/src/components/sidebar.jsx`、`datalogue-web/src/api/client.js`、`datalogue-web/src/styles.css`、`.codex/project-memory.md`
- 关键改动：新增独立页面 `/users-new`，提供用户名、邮箱、姓名、初始密码表单并调用 `/api/auth/register` 创建用户；侧边栏“系统管理”新增“新建用户”入口；顶部面包屑补充用户管理路径；客户端新增 `createUserAccount` API 方法。
- 验证方式：执行 `cd datalogue-web && npm run lint`，结果 `0 errors, 14 warnings`（均为仓库既有告警）；新页面编译无异常。
- 残留风险：当前后端 `register` 仍未加管理员鉴权，理论上任意登录态均可调用；后续建议把创建用户能力限制为管理员角色。

### 2026-07-09 01:05 · 登录认证功能第一阶段落地

- 涉及文件：`datalogue-api/app/core/config.py`、`datalogue-api/app/core/security.py`、`datalogue-api/app/models/user.py`、`datalogue-api/app/models/__init__.py`、`datalogue-api/app/schemas/auth.py`、`datalogue-api/app/schemas/__init__.py`、`datalogue-api/app/api/deps.py`、`datalogue-api/app/api/auth.py`、`datalogue-api/app/api/__init__.py`、`datalogue-api/app/main.py`、`datalogue-api/alembic/versions/z6a7b8c9d0e1_add_app_user.py`、`datalogue-api/tests/test_auth.py`、`datalogue-web/src/api/client.js`、`datalogue-web/src/auth/auth-context.jsx`、`datalogue-web/src/components/login-page.jsx`、`datalogue-web/src/App.jsx`、`datalogue-web/src/styles.css`、`.codex/project-memory.md`
- 关键改动：后端新增 `app_user` 用户模型与 Alembic 迁移，落地 `/api/auth/register|login|refresh|logout|me` 认证接口、Bearer 鉴权依赖与启动管理员引导；配置新增 token/cookie/cors 认证参数并在主应用切换到可携带 Cookie 的白名单 CORS。前端新增 AuthContext、登录页、路由守卫、顶部退出入口，并把 API 客户端改为自动注入 Access Token、401 静默 refresh 后重放请求。
- 验证方式：执行 `cd datalogue-api && pytest tests/test_auth.py -q` 结果 `3 passed`；执行 `cd datalogue-web && npm run lint` 结果 `0 errors, 14 warnings`（均为历史告警）；执行 `cd datalogue-web && npm run build` 构建通过。
- 残留风险：业务路由尚未全面接入 `get_current_user` 强制鉴权（当前先完成认证能力与前端登录闭环）；`BOOTSTRAP_ADMIN_PASSWORD`、`SECRET_KEY` 仍需部署环境变量覆盖；迁移文件已新增但生产环境需手动执行 `alembic upgrade head`。

### 2026-07-09 15:08 · 登录页视觉升级（现代双栏）

- 涉及文件：`datalogue-web/src/components/login-page.jsx`、`datalogue-web/src/styles.css`、`.codex/project-memory.md`
- 关键改动：登录页由单卡片升级为双栏布局（左侧品牌价值展示 + 右侧登录表单卡片），新增分层背景光晕、玻璃感容器、表单按钮视觉强化与移动端响应式适配；保持现有 Ant Design 技术栈与登录逻辑不变。
- 验证方式：执行 `cd datalogue-web && npm run lint` 与 `cd datalogue-web && npm run build` 均通过（lint 仅保留仓库既有 warnings，无新增 errors）。
- 残留风险：当前仅完成视觉升级，未接入品牌插画或动态运营素材；如需进一步品牌化，可追加自定义 SVG 背景和轻量入场动画。

### 2026-07-09 17:05 · Report Worker 智能报告闭环

- 完成时间：2026-07-09 17:05。
- 功能名称：Report Worker 智能报告闭环。
- 涉及文件：`datalogue-api/app/domains/query_execution/report_input.py`、`datalogue-api/app/domains/agent_team/worker_identity.py`、`datalogue-api/app/runtime/engine/tools.py`、`datalogue-api/app/runtime/engine/registry.py`、`datalogue-api/app/prompts/agent_team.py`、`datalogue-api/app/domains/bi/toolkit/atomic.py`、`datalogue-api/app/domains/bi/agent/native_handoff.py`、`datalogue-api/conf/report_worker_permissions.json`、`datalogue-api/conf/bi_worker_permissions.json`、`datalogue-web/src/assistant-ui/DatalogueMarkdown.jsx`、`datalogue-web/src/assistant-ui/DatalogueChartBlocks.jsx`、`datalogue-web/src/styles.css`、`datalogue-web/package.json`、`datalogue-web/package-lock.json` 及相关测试。
- 关键改动：新增 `report_input` 安全投影，三处 `sql_result` 写入点统一写入 `report_input_meta` 与裁剪后的用户可见 rows/columns；新增 `datalogue_get_artifact_report_input` 工具，只按 artifact_ref 读取并校验报告输入，不查业务库、不接收 SQL/schema/raw rows；新增 `resolve_team_worker_type`，按 team agent system_prompt marker fail-closed 区分 BI/Report worker，Report Worker 只拿报告读取工具并使用独立权限上下文；Leader prompt 支持 BI 成功后按用户语义和结果复杂度自主决策是否生成报告，Report Worker 输出中文 Markdown，并允许 Mermaid/ECharts 图表；前端 Markdown fallback 与 Streamdown 主路径都支持 `mermaid`/`echarts` fenced code block，ECharts 仅接受纯 JSON option 并拒绝原型污染键。
- 验证方式：执行 `PYTHONPATH=.../datalogue-api .../.venv/bin/python -m pytest datalogue-api/tests/test_report_worker_artifact_input.py datalogue-api/tests/test_agentscope_service_tools.py datalogue-api/tests/test_agentscope_static_agent_registry.py -q`，结果 `33 passed`；执行 `pytest datalogue-api/tests/test_artifact_api.py datalogue-api/tests/test_bi_lead_agent_native_handoff.py datalogue-api/tests/test_agentscope_service_worker_logging.py -q`，结果 `53 passed`；执行 `cd datalogue-web && npm run test -- DatalogueMessage.test.jsx`，结果 `6 passed`；执行 `npm run lint`，结果 0 errors、13 个既有 warnings；执行 `npm run build` 成功，保留现有大 chunk warning；调用 Claude Code review，结论为无阻塞问题，并按建议补强了 report input 边界测试与 `create_query_artifact` 链路。
- 残留风险或后续事项：本轮不新增报告持久化表、不新增报告文件 artifact 类型、不新增 Workbench 报告面板；Leader 何时派生 Report Worker 仍依赖模型遵循 prompt，后续如需更强确定性，可在 Agent Team runner 层增加成功查询后的策略性 report worker 创建闸门。

### 2026-07-09 17:06 · Datalogue 2026 下半年工作规划

- 完成时间：2026-07-09 17:06。
- 功能名称：Datalogue 2026 下半年工作规划。
- 涉及文件：`.omx/plans/2026-07-09-datalogue-h2-work-plan.md`、`.codex/project-memory.md`。
- 关键改动：新增下半年工作规划文档，按 BI Worker 查询可靠性、Report Worker、assistant-ui 聊天体验、Workbench 退役、AgentScope 原生化与观测、数据源语义治理、认证权限、工程治理八条主线组织；拆分 2026 年 7 月至 12 月月度路线图、P0/P1/P2 优先级、风险控制和近期两周行动清单。
- 验证方式：文档型变更，基于 `docs/上下文入口.md`、`.omx/plans/2026-07-09-assistant-ui-stream-tool-multi-agent-plan.md`、`.omx/plans/workbench-retention-consensus-plan.md`、`.omx/interviews/report-agent-20260709T075403Z.md`、`docs/architecture/系统架构.md` 与 `.codex/project-memory.md` 当前记录交叉整理；未运行代码测试。
- 残留风险或后续事项：规划需要随 BI Worker E2E、Report Worker 实施、Workbench retention gate 真实埋点和权限闭环进展持续更新；当前尚未拆成飞书任务或具体执行分支。

### 2026-07-09 17:12 · Datalogue 下半年规划同步 Obsidian

- 完成时间：2026-07-09 17:12。
- 功能名称：Datalogue 下半年规划同步 Obsidian。
- 涉及文件：`/Users/yangkai/KenYang/文档库/develop-doc-repositry/工作知识库/2026/数语/规划/Datalogue 2026 下半年工作规划.md`、`.codex/project-memory.md`。
- 关键改动：将 `.omx/plans/2026-07-09-datalogue-h2-work-plan.md` 同步到默认 Obsidian vault 的数语规划目录，保留原 Markdown 内容和中文标题，便于在个人知识库中继续查阅和迭代。
- 验证方式：执行 `ls -l /Users/yangkai/KenYang/文档库/develop-doc-repositry/工作知识库/2026/数语/规划`，确认目标文件已生成，文件大小为 14411 bytes。
- 残留风险或后续事项：本次是单次复制同步，后续若项目内规划继续修改，需要再次同步到 Obsidian，避免两边内容漂移。

### 2026-07-09 18:45 · AgentScope runtime 新目录边界 facade

- 完成时间：2026-07-09 18:45。
- 功能名称：AgentScope runtime 新目录边界 facade。
- 涉及文件：`datalogue-api/app/agentscope_runtime/__init__.py`、`datalogue-api/app/agentscope_runtime/app_factory.py`、`datalogue-api/app/agentscope_runtime/client.py`、`datalogue-api/app/agentscope_runtime/credentials.py`、`datalogue-api/app/agentscope_runtime/otel_setup.py`、`datalogue-api/app/agentscope_runtime/projection.py`、`datalogue-api/app/agentscope_runtime/registry.py`、`datalogue-api/app/agentscope_runtime/runner.py`、`datalogue-api/app/agentscope_runtime/worker_logging.py`、`datalogue-api/tests/test_directory_facades.py`、`datalogue-api/tests/test_agentscope_service_imports.py`、`.omx/artifacts/ask-claude-g049-agentscope-runtime-facade-20260709T184426+0800.md`、`.codex/project-memory.md`。
- 关键改动：新增 `app.agentscope_runtime` 作为 AgentScope Service runtime 的稳定导入边界，按 facade-first 方式 re-export Service 嵌入、runner、registry、projection、OTel、worker logging、client 与 credentials，不搬移旧 `app.runtime.engine` 实现、不切换调用方、不暴露 BI worker 工具链顶层入口；补目录治理测试确认新 facade 与旧实现对象同源，并断言 `build_datalogue_extra_agent_tools` 不进入新包顶层 API。
- 验证方式：执行 `PYTHONPATH=.../datalogue-api .../.venv/bin/python -m pytest datalogue-api/tests/test_directory_facades.py datalogue-api/tests/test_agentscope_service_imports.py datalogue-api/tests/test_agentscope_service_factory.py datalogue-api/tests/test_agentscope_static_agent_registry.py datalogue-api/tests/test_agentscope_service_worker_logging.py datalogue-api/tests/test_agentscope_service_projection.py -q`，结果 `66 passed, 3 warnings`；调用 Claude Code review，结论为 `APPROVE`、无阻塞问题，并按非阻塞建议补齐 worker logging 顶层导出。
- 残留风险或后续事项：本轮只建立新目录 facade 边界，旧 `app.runtime.engine` 仍保留为真实实现源；后续若推进调用方迁移或物理文件搬迁，需要继续分批改导入、保持旧路径兼容，并用 AgentScope 主链与 BI/Report Worker 回归测试证明业务语义不漂移。

### 2026-07-09 19:20 · BI 业务域目录边界收口

- 完成时间：2026-07-09 19:20。
- 功能名称：BI 业务域目录边界收口。
- 涉及文件：`datalogue-api/app/domains/bi/__init__.py`、`datalogue-api/app/domains/bi/agent_services.py`、`datalogue-api/app/domains/bi/worker_query.py`、`datalogue-api/app/domains/bi/skill/__init__.py`、`datalogue-api/app/domains/bi/toolkit/__init__.py`、`datalogue-api/app/domains/bi/worker/__init__.py`、`datalogue-api/app/domains/bi/toolchain/__init__.py`、`datalogue-api/tests/test_directory_facades.py`、`.codex/project-memory.md`。
- 关键改动：将 `domains/bi` 根包和兼容聚合入口的注释从“旧 app/bi / app/agents/bi_agent 迁移中”修正为当前 canonical domain source；明确 `agent`、`skill`、`toolkit`、`worker` 四类边界分别承载 BI 应用服务、Dataset Query Skill、受控原子工具、BI Worker QueryPlan 契约/运行时/上下文；删除未使用的空 `toolchain` 包入口；新增目录边界测试，确认旧 `app/bi` 与 `app/agents/bi_agent` 不存在，`domains/bi` 不包含非 BI 源码入口，并验证 Skill、Toolkit、QueryPlan 契约、runtime context 的真实实现源都在 `app.domains.bi` 下。
- 验证方式：执行 `PYTHONPATH=.../datalogue-api .../.venv/bin/python -m pytest datalogue-api/tests/test_directory_facades.py datalogue-api/tests/test_bi_lead_agent_capabilities.py datalogue-api/tests/test_bi_lead_agent_services.py datalogue-api/tests/test_bi_lead_agent_handoff_port.py datalogue-api/tests/test_bi_worker_progressive_context_contracts.py datalogue-api/tests/test_bi_worker_query_validator.py -q`，结果 `60 passed, 3 warnings`；执行 `pytest datalogue-api/tests/test_bi_worker_query_runtime.py datalogue-api/tests/test_bi_worker_progressive_context_tools.py datalogue-api/tests/test_bi_worker_progressive_context_e2e.py datalogue-api/tests/test_bi_lead_agent_native_handoff.py datalogue-api/tests/test_agentscope_service_tools.py datalogue-api/tests/test_report_worker_artifact_input.py -q`，结果 `80 passed, 75 warnings`。
- 残留风险或后续事项：本轮只收口 BI 领域目录边界和注释，不迁移调用方到新 facade、不移动 `runtime.engine.tools`，后续 G053/G054 再按测试覆盖决定是否切调用方或继续物理整理。

### 2026-07-09 19:25 · Agent Team 业务域边界 facade 收口

- 完成时间：2026-07-09 19:25。
- 功能名称：Agent Team 业务域边界 facade 收口。
- 涉及文件：`datalogue-api/app/domains/agent_team/__init__.py`、`datalogue-api/app/domains/agent_team/contracts.py`、`datalogue-api/app/domains/agent_team/event_projection.py`、`datalogue-api/app/domains/agent_team/retry_actions.py`、`datalogue-api/app/domains/agent_team/task_runtime.py`、`datalogue-api/app/domains/agent_team/workbench_view.py`、`datalogue-api/app/api/agent_team.py`、`datalogue-api/app/api/workbench.py`、`datalogue-api/app/runtime/agent_team_runtime.py`、`datalogue-api/app/domains/workbench/actions.py`、`datalogue-api/app/core/schemas/agentscope_workbench.py`、`datalogue-api/app/domains/agent_team/registry.py`、`datalogue-api/app/domains/agent_team/runner.py`、`datalogue-api/app/domains/agent_team/projection.py`、`datalogue-api/app/domains/agent_team/team_templates.py`、`datalogue-api/app/agentscope_runtime/__init__.py`、`datalogue-api/tests/test_directory_facades.py`、`.codex/project-memory.md`。
- 关键改动：新增 `contracts`、`event_projection`、`retry_actions`、`task_runtime`、`workbench_view` 五个 canonical facade，明确 `domains/agent_team` 只承载 Datalogue 对外 task 真相源、Workbench view/retry action 和 AgentScope event 到 Datalogue event envelope 的投影；API、Workbench、AgentTeamTaskRuntime 与 Workbench DTO 调用方切到新 facade；旧 `registry`、`runner`、`projection`、`team_templates` 继续作为兼容门面并在注释中标清 AgentScope runtime 入口归 `app.agentscope_runtime`，其中 `team_templates` 保持直连旧实现以避免旧 app_factory 启动链反向导入新包造成循环。
- 验证方式：执行 `PYTHONPATH=.../datalogue-api .../.venv/bin/python -m py_compile datalogue-api/app/agentscope_runtime/__init__.py datalogue-api/app/domains/agent_team/__init__.py datalogue-api/app/domains/agent_team/contracts.py datalogue-api/app/domains/agent_team/event_projection.py datalogue-api/app/domains/agent_team/retry_actions.py datalogue-api/app/domains/agent_team/task_runtime.py datalogue-api/app/domains/agent_team/workbench_view.py datalogue-api/app/api/agent_team.py datalogue-api/app/api/workbench.py datalogue-api/app/runtime/agent_team_runtime.py datalogue-api/app/domains/workbench/actions.py datalogue-api/app/core/schemas/agentscope_workbench.py datalogue-api/app/domains/agent_team/registry.py datalogue-api/app/domains/agent_team/runner.py datalogue-api/app/domains/agent_team/projection.py datalogue-api/app/domains/agent_team/team_templates.py datalogue-api/tests/test_directory_facades.py` 通过；执行 `PYTHONPATH=.../datalogue-api .../.venv/bin/python -m pytest datalogue-api/tests/test_directory_facades.py datalogue-api/tests/test_agent_team_task_contracts.py datalogue-api/tests/test_agent_team_task_runtime.py datalogue-api/tests/test_agentscope_agent_team_task_runner.py datalogue-api/tests/test_workbench_agent_team_retry_writer.py datalogue-api/tests/test_workbench_agent_team_task_actions.py datalogue-api/tests/test_workbench_view_api.py datalogue-api/tests/test_agentscope_service_imports.py datalogue-api/tests/test_agentscope_service_worker_logging.py -q`，结果 `81 passed, 3 warnings`；执行 `git diff --check` 通过；调用 Claude Code Review，产物 `.omx/artifacts/ask-claude-g051-domains-agent-team-boundary-20260709T191834+0800.md`，结论 `APPROVE`、无阻塞问题。
### 2026-07-09 17:30 · Doris/Oracle 数据源问数链路集成基线验证

- 完成时间：2026-07-09 17:30。
- 功能名称：Doris/Oracle 数据源问数链路集成基线验证。
- 涉及文件：`docs/test-reports/2026-07-09-doris-oracle-datasource-verification.md`、`.codex/project-memory.md`。
- 关键改动：新增集成验证记录，明确只读规划来源、Doris/Oracle 完整问数链路验收点、当前基线命令结果，以及上游实现完成后的复验清单；当前 worktree 中 `doris` 全仓命中为 0，Oracle capability/SQL Guard 已有基础覆盖，但 QueryPlan compiler/adapter 仍只支持 `mysql/sqlite`，`oracle` 当前仍按 unsupported fail-closed 处理，因此本轮不把完整 Doris/Oracle 链路写成已完成。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest ... -q` 覆盖 datasource/query_execution/preview/analysis_blueprint，结果 `17 passed, 10 warnings`；执行 BI Worker runtime targeted pytest，结果 `7 passed, 2 warnings`；前端初次 targeted vitest 因 `vitest: command not found` 失败，执行 `cd datalogue-web && npm install` 后复验 artifact/workbench 测试 `31 passed`；执行 `npm run lint` 为 `0 errors, 13 warnings`，执行 `npm run build` 成功。
- 残留风险或后续事项：Doris capability、服务端执行方言归一化、Oracle compiler/adapter/URL/preview/BI runtime 完整链路仍需后续实现并复验；真实 Doris/Oracle 连接验收仅能连接用户已有环境，不在本轮本地搭建数据库。


### 2026-07-09 17:31 · Doris/Oracle leader HEAD 集成复核补证

- 完成时间：2026-07-09 17:31。
- 功能名称：Doris/Oracle 数据源问数链路 leader HEAD 复核补证。
- 涉及文件：`docs/test-reports/2026-07-09-doris-oracle-datasource-verification.md`、`.codex/project-memory.md`。
- 关键改动：根据 leader mailbox 指令，以 detached commit `adddfd24` 复核当前 team branch，确认 Doris capability、服务端执行方言归一化、Oracle compiler/adapter、preview_dataset_sql、build_bi_runtime_context、analysis_blueprint、preview_table、前端 datasources 与 artifact/DatalogueMessage 可见性测试已集成；同步修正早前基于旧 detached HEAD 的 Doris 0 命中/Oracle fail-closed 结论。
- 验证方式：执行 Doris/Oracle 后端 targeted pytest，覆盖 datasource capability/defaults/update stale dialect、build_datasource_context、build_bi_runtime_context、analysis_blueprint timeout stale path、preview_dataset_sql guard dialect、preview_table Doris SQL、Oracle FETCH FIRST 和 URL，结果 `16 passed, 6 warnings`；执行 `cd datalogue-web && npm test -- src/components/datasources.test.jsx src/components/artifact-card.test.jsx src/assistant-ui/DatalogueMessage.test.jsx`，结果 `3 passed / 28 passed`。
- 残留风险或后续事项：仍未搭建真实 Doris/Oracle 数据库，真实页面最终 answer 与 Workbench artifact 截图/payload 需连接用户已有环境补证；当前自动化证明代码路径和用户可见投影基线通过。
=======

### 2026-07-09 19:35 · Agent Team runtime 自动标题测试隔离

- 完成时间：2026-07-09 19:35。
- 功能名称：Agent Team runtime 自动标题测试隔离。
- 涉及文件：`datalogue-api/app/core/config.py`、`datalogue-api/app/runtime/agent_team_runtime.py`、`datalogue-api/tests/test_agent_team_task_runtime.py`、`.codex/project-memory.md`。
- 关键改动：新增 `DATALOGUE_AUTO_TITLE_ENABLED` 配置并默认开启；runtime 在启动 `maybe_auto_title_async` 前检查该开关；Agent Team runtime 单元测试默认关闭自动标题后台 DB 线程，并新增关闭开关防回归测试，避免 pytest teardown 时 daemon 线程连库触发 C 扩展 segfault。
- 验证方式：先新增失败测试 `test_agent_team_task_runtime_skips_auto_title_when_disabled`，确认关闭环境变量后仍调用 auto-title；实现后执行 `test_agent_team_task_runtime.py`，结果 `6 passed, 3 warnings`；执行 G051 目标回归，结果 `82 passed, 3 warnings`；`py_compile`、`git diff --check` 通过；Claude Code Review 产物 `.omx/artifacts/ask-claude-g051-auto-title-test-isolation-20260709T192714+0800.md`，结论 `APPROVE`、无阻塞问题。
- 残留风险或后续事项：生产默认仍开启自动标题；daemon 线程模式长期仍建议改为可管理任务队列或生命周期可 join 的后台任务。

### 2026-07-09 19:45 · G052 AgentScope runtime facade 验证与 lifespan 测试隔离

- 完成时间：2026-07-09 19:45。
- 功能名称：G052 AgentScope runtime facade 验证与 lifespan 测试隔离。
- 涉及文件：`datalogue-api/tests/test_agentscope_service_factory.py`、`.omx/artifacts/claude-review-datalogue-g052-g052-app-agentscope-service-app-agents-2026-07-09T11-35-55-764Z.md`、`.codex/project-memory.md`。
- 关键改动：确认 `app.agentscope_runtime` facade 已存在且旧 `app/agentscope_service` 目录未直接回流；修复 AgentScope Service factory 的两个 FastAPI lifespan 单测隔离缺口，在验证子应用 lifespan 和 OTel 顺序时显式 mock `_bootstrap_admin_if_needed`，避免测试误连真实 PostgreSQL。
- 验证方式：RED 证据为原始 `test_main_lifespan_enters_mounted_agentscope_service_lifespan` 触发 `main.lifespan -> _bootstrap_admin_if_needed -> SessionLocal -> psycopg2.connect` segfault；补丁后两个最小 lifespan 测试 `2 passed, 3 warnings`；隔离工作树 G052 回归 `68 passed, 3 warnings`；主工作区 G052 直接 facade 证据 `test_directory_facades.py test_agentscope_service_imports.py test_agentscope_service_projection.py` 为 `23 passed, 3 warnings`，并通过脚本确认 `app.agentscope_runtime` 存在、`app/agentscope_service` 不存在、facade 不暴露 `build_datalogue_extra_agent_tools`；Claude Code Review 结论 `可以合并，无阻塞问题`。
- 残留风险或后续事项：主工作区仍有未提交 `datalogue-api/app/runtime/engine/registry.py` 改动，把 worker 模板从 `bi/report/python/audit` 临时变为 `bi/report`，因此完整 `tests/test_agentscope_service_factory.py tests/test_agentscope_static_agent_registry.py` 在主工作区当前态会因测试期待不一致失败；该业务边界变更未在本轮擅自提交或回滚。

### 2026-07-09 19:50 · G053 BI runtime context 与 Skill/Toolkit 边界文档

- 完成时间：2026-07-09 19:50。
- 功能名称：G053 BI runtime context 与 Skill/Toolkit 边界文档。
- 涉及文件：`docs/architecture/目录治理与模块边界.md`、`docs/architecture/系统架构.md`、`docs/architecture/datalogue_execute_query_plan_bundle完整链路.md`、`.omx/artifacts/claude-review-g053-bi-boundary-doc-20260709T194901+0800.md`、`.codex/project-memory.md`。
- 关键改动：在目录治理文档新增 `BI runtime context / Skill / Toolkit 边界` 表，明确旧 `app/agents/bi_agent/runtime_context.py`、`app/bi/skill`、`app/bi/toolkit` 已退役，不作为当前实现或导入入口；当前 canonical owner 为 `app.domains.bi.agent.runtime_context`、`app.domains.bi.skill`、`app.domains.bi.toolkit`、`app.domains.bi.worker`。同步更新系统架构的 `agentscope_runtime` 与 `domains/bi` 文件清单，并修正 `datalogue_execute_query_plan_bundle` 链路文档中的当前真实代码入口。
- 验证方式：执行 `PYTHONPATH=.../datalogue-api .../.venv/bin/python -m pytest datalogue-api/tests/test_directory_facades.py::test_domains_bi_boundary_is_canonical_source_for_bi_capabilities -q`，结果 `1 passed, 3 warnings`；执行 `domains_bi_boundary_imports_ok` smoke，确认 `build_bi_runtime_context`、`DatasetQuerySkill`、`AgentScopeDatasetRuntimeBridge`、`build_bi_atomic_toolkit` 均归属 `app.domains.bi.*`；执行 `git diff --check HEAD~1..HEAD` 通过；Claude Code Review 首轮发现旧路径残留，修复后复核结论为 `阻塞项已关闭，可以合并`。
- 残留风险或后续事项：`docs/architecture/OpenViking-Service交接记忆.md` 仍保留历史交接视角中的 `agentscope_service` 旧路径，本轮按 G053 范围未展开整理；后续若要把 `docs/architecture` 全量变为当前态，需要单独做历史文档归档或加明确过期标记。

### 2026-07-09 20:05 · G054 AgentScope runtime 调用方 facade 迁移

- 完成时间：2026-07-09 20:05。
- 功能名称：G054 AgentScope runtime 调用方 facade 迁移。
- 涉及文件：`datalogue-api/app/agentscope_runtime/client.py`、`datalogue-api/app/main.py`、`datalogue-api/app/api/agent_team.py`、`datalogue-api/app/api/agentscope_control_plane.py`、`datalogue-api/app/api/llm.py`、`datalogue-api/app/core/llm_config.py`、`datalogue-api/tests/test_agentscope_service_imports.py`、`datalogue-api/tests/test_directory_facades.py`、`.omx/artifacts/claude-review-g054-callers-to-facade-20260709T200500+0800.md`、`.codex/project-memory.md`。
- 关键改动：将已有测试覆盖的生产调用方从旧 `app.runtime.engine` 入口迁移到 `app.agentscope_runtime` facade，包括 FastAPI 主入口的嵌入式 AgentScope app/OTel、Agent Team runner 构造、AgentScope 控制面、LLM API 和 LLM 配置默认用户常量；`app.agentscope_runtime.client` 增补 `DEFAULT_AGENTSCOPE_USER_ID` re-export，保持与旧实现常量同源；新增静态回归测试，防止这批已覆盖调用方重新直接导入 `app.runtime.engine`。
- 验证方式：在干净 G054 工作树执行 `PYTHONPATH=.../datalogue-api .../.venv/bin/python -m pytest datalogue-api/tests/test_directory_facades.py datalogue-api/tests/test_agentscope_service_imports.py datalogue-api/tests/test_agentscope_service_factory.py datalogue-api/tests/test_agent_team_task_runtime.py datalogue-api/tests/test_agentscope_service_client.py datalogue-api/tests/test_agentscope_control_plane_api.py datalogue-api/tests/test_agentscope_llm_resource_boundary.py -q`，结果 `41 passed, 3 warnings`；执行 `py_compile` 覆盖本轮变更的 6 个生产文件，通过；执行 `git diff --check` 通过；Claude Code Review 复审结论为无阻塞问题，可以合并。
- 残留风险或后续事项：主工作区当前仍有未提交 `datalogue-api/app/runtime/engine/registry.py` 改动，将 worker 模板临时限制为 `bi/report`，因此合并后在主工作区直接跑同一验证集时 `test_agentscope_service_factory.py::test_create_embedded_runtime_app_wires_redis_and_workspace` 会因测试期望仍包含 `python/audit` 而失败；该失败与 G054 facade 调用方迁移无关，本轮未擅自回滚或提交该既有业务边界改动。

### 2026-07-09 20:22 · G055 物理搬迁决策

- 完成时间：2026-07-09 20:22。
- 功能名称：G055 物理搬迁决策。
- 涉及文件：`docs/architecture/目录治理与模块边界.md`、`.omx/artifacts/claude-review-g055-physical-move-decision-20260709T202200+0800.md`、`.codex/project-memory.md`。
- 关键改动：在 facade-first ADR 中新增 `G055 物理搬迁决策` 小节，明确当前暂不启动 AgentScope runtime、Agent Team、BI runtime 或前端目录的物理文件搬迁；确认 G049-G054 已完成 facade 入口和已有测试覆盖调用方迁移，但旧实现文件继续保留在原路径；定义后续重新评估物理搬迁的四个开放条件，包括 G056-G059 回归闸门、无重叠未提交改动、旧路径兼容壳/静态导入测试、单 owner 域小闭环移动。
- 验证方式：执行 `git diff --check HEAD~1..HEAD` 通过；执行 `rg -n "G055|G056|G057|G058|G059|物理搬迁" docs/architecture/目录治理与模块边界.md`，确认 G055 决策和 G056-G059 验收标准均已落档；Claude Code Review 首轮指出 G056-G059 未定义，补齐后复审结论为无阻塞问题。
- 残留风险或后续事项：G056-G059 当前是文档闸门定义，后续各故事需要在自身交付中补充可计数测试清单；物理移动仍需等这些闸门通过后重新评估并单独提交。

### 2026-07-09 20:38 · G056 Agent Team SSE API 测试闸门

- 完成时间：2026-07-09 20:38。
- 功能名称：G056 Agent Team SSE API 测试闸门。
- 涉及文件：`datalogue-api/tests/test_agent_team_stream_api.py`、`.codex/project-memory.md`。
- 关键改动：新增 `/api/agent-team/tasks/stream` 接口级测试，使用 fake AgentScope runner 直接打 FastAPI SSE 路由，覆盖成功流 `task.started -> agent.selected -> message.delta -> message.completed -> task.completed`，并覆盖 runner 异常时 API 仍输出 `task.failed`、只暴露 `AGENT_TEAM_TASK_FAILED` 安全摘要、不泄露 `select * from hidden_table` 或内部表名；测试 fixture 关闭自动标题线程并重置 `sse_starlette` 的 `AppStatus` 全局事件，避免多次 TestClient 流请求跨 event loop 污染。
- 验证方式：在独立工作树和主工作区均执行 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.../datalogue-api .../.venv/bin/python -m pytest datalogue-api/tests/test_agent_team_stream_api.py datalogue-api/tests/test_agent_team_task_runtime.py datalogue-api/tests/test_agent_team_task_contracts.py -q`，结果均为 `13 passed, 3 warnings`；执行 `py_compile datalogue-api/tests/test_agent_team_stream_api.py` 和 `git diff --check` 通过；Claude Code Review 对首版测试给出无阻断结论，并提出事件空流断言、避免固定索引等 Major 建议，均已修复并重新验证通过；最终版 Claude 复审因 CLI 超时未返回正文。
- 残留风险或后续事项：本轮只补 API SSE 测试闸门，不改生产实现；主工作区仍保留既有未提交 `registry.py` worker 模板改动，该改动会影响 broader AgentScope factory 期望，本轮未回滚或纳入提交。

### 2026-07-09 20:46 · G057 AgentScope Service 关键子集测试闸门

- 完成时间：2026-07-09 20:46。
- 功能名称：G057 AgentScope Service 关键子集测试闸门。
- 涉及文件：`datalogue-api/tests/test_agentscope_service_factory.py`、`.omx/artifacts/claude-review-g057-agentscope-service-tests-20260709T204625+0800.md`、`.codex/project-memory.md`。
- 关键改动：将 `test_create_embedded_runtime_app_wires_redis_and_workspace` 中 `custom_subagent_templates` 的硬编码四类 worker 断言改为对齐 `build_datalogue_worker_template_specs()` 当前 registry 输出，明确 factory 测试只验证 AgentScope create_app 装配与 registry 透传语义；精确 worker 类型快照继续由 `test_agentscope_static_agent_registry.py` 负责兜底。该改动兼容主工作区当前未提交的 `registry.py` worker 模板边界调整，不回滚用户改动。
- 验证方式：在独立工作树执行 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.../.worktrees/codex-g057-agentscope-service-tests/datalogue-api .../.venv/bin/python -m pytest datalogue-api/tests/test_agentscope_service_imports.py datalogue-api/tests/test_agentscope_service_factory.py datalogue-api/tests/test_agentscope_service_worker_logging.py datalogue-api/tests/test_agentscope_service_projection.py datalogue-api/tests/test_agentscope_service_client.py datalogue-api/tests/test_agentscope_service_tools.py -q`，结果 `75 passed, 3 warnings`；合入主工作区后用当前未提交 registry 改动再次执行同一 service 子集，结果 `75 passed, 3 warnings`；`py_compile datalogue-api/tests/test_agentscope_service_factory.py` 和 `git diff --check HEAD -- datalogue-api/tests/test_agentscope_service_factory.py` 通过；Claude Code Review 结论为无阻断、无 Major，Minor 建议已通过注释和现有 static registry 测试职责说明收口。
- 残留风险或后续事项：主工作区 `datalogue-api/app/runtime/engine/registry.py` 仍是未提交业务边界改动，`test_agentscope_static_agent_registry.py` 若在当前主工作区直接执行仍会按硬编码四类 worker 快照失败；该问题属于 registry 业务决策本身，不在 G057 service 子集范围内。

### 2026-07-09 20:47 · G058 BI Lead Agent native handoff 测试闸门

- 完成时间：2026-07-09 20:47。
- 功能名称：G058 BI Lead Agent native handoff 测试闸门。
- 涉及文件：`.codex/project-memory.md`、`.omx/artifacts/get-goal-g058-bi-lead-agent-native-handoff-20260709T204746+0800.json`。
- 关键改动：本轮为验证型 story，无生产代码或测试代码改动；确认当前主工作区状态下 `tests/test_bi_lead_agent_native_handoff.py` 可通过，作为 AgentScope / BI 主链后续目录治理前的 native handoff 回归闸门。
- 验证方式：执行 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/yangkai/code_place/study/python/Datalogue/datalogue-api /Users/yangkai/code_place/study/python/Datalogue/datalogue-api/.venv/bin/python -m pytest datalogue-api/tests/test_bi_lead_agent_native_handoff.py -q`，结果 `14 passed, 3 warnings`。
- 残留风险或后续事项：本轮未处理主工作区既有未提交 `registry.py` worker 模板边界改动；该改动与 G058 native handoff 单测无直接冲突。

### 2026-07-09 20:48 · G059 Workbench retry/action/view 测试闸门

- 完成时间：2026-07-09 20:48。
- 功能名称：G059 Workbench retry/action/view 测试闸门。
- 涉及文件：`.codex/project-memory.md`、`.omx/artifacts/get-goal-g059-workbench-retry-action-view-20260709T204842+0800.json`。
- 关键改动：本轮为验证型 story，无生产代码或测试代码改动；确认 Workbench retry writer、Agent Team task action、Workbench view API 三组测试在当前主工作区可通过，作为目录边界继续推进前的 Workbench 回归闸门。
- 验证方式：执行 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/yangkai/code_place/study/python/Datalogue/datalogue-api /Users/yangkai/code_place/study/python/Datalogue/datalogue-api/.venv/bin/python -m pytest datalogue-api/tests/test_workbench_agent_team_retry_writer.py datalogue-api/tests/test_workbench_agent_team_task_actions.py datalogue-api/tests/test_workbench_view_api.py -q`，结果 `10 passed, 3 warnings`。
- 残留风险或后续事项：本轮只完成后端 Workbench retry/action/view 单测闸门；后续前端目录规划和页面 smoke 仍由 G060-G067 继续处理。

### 2026-07-09 21:01 · G060 前端 src/app 应用壳规划

- 完成时间：2026-07-09 21:01。
- 功能名称：G060 前端 `src/app` 应用壳规划。
- 涉及文件：`datalogue-web/src/app/README.md`、`docs/architecture/目录治理与模块边界.md`、`.omx/artifacts/claude-review-g060-frontend-app-shell-plan-20260709T205900+0800.md`、`.codex/project-memory.md`。
- 关键改动：新建 `datalogue-web/src/app/README.md`，只落前端应用壳目标域规划，不搬迁 `src/App.jsx`、`src/components/sidebar.jsx` 或任何页面源码；明确当前 App shell、TopBar、Sidebar、routes、auth guard、theme tweak 的现有归属，规划后续 `app-root.jsx`、`app-shell.jsx`、`routes.jsx`、`topbar.jsx`、`sidebar.jsx`、`navigation.js`、`theme.js` 的边界与迁移顺序；同步在目录治理 ADR 中新增 G060 小节，要求后续源码拆分先建薄 re-export、保持 `/login`、`/chat/:id`、`/workbench/:threadId`、`/workbench/:threadId/:artifactRef`、`/users` 路由和鉴权语义不变，并执行 `npm run lint`、`npm run build`、`npm run test`。
- 验证方式：执行 `git diff --check` 通过；执行 `rg -n "G060|src/app|RequireAuth|RequireSuperuser|npm run test|/workbench/:threadId" datalogue-web/src/app/README.md docs/architecture/目录治理与模块边界.md`，确认关键锚点齐全；调用 Claude Code Review，最终复审产物 `.omx/artifacts/claude-review-g060-frontend-app-shell-plan-20260709T205900+0800.md`，结论为 Blocker/Major/Minor 均为 0、无阻断问题。
- 残留风险或后续事项：本轮是文档规划和目标目录占位，不执行前端源码拆分、不跑 `npm run lint/build/test`；后续真正迁移 `TopBar`、`Sidebar`、routes 或 theme 时必须单独提交并执行上述前端验证与桌面 smoke。

### 2026-07-09 21:28 · G061 Chat 功能域搬迁与旧入口兼容

- 完成时间：2026-07-09 21:28。
- 功能名称：G061 Chat 功能域搬迁与旧入口兼容。
- 涉及文件：`datalogue-web/src/features/chat/*`、`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/thread-list-adapter.js`、`datalogue-web/src/assistant/Thread.jsx`、`datalogue-web/src/assistant/ThreadList.jsx`、`datalogue-web/src/assistant/MyComposer.jsx`、`datalogue-web/src/assistant/MyMessage.jsx`、`datalogue-web/src/assistant/chat-adapter.test.js`、`docs/architecture/目录治理与模块边界.md`、`.omx/artifacts/claude-review-g061-features-chat-reexports-20260709T212447+0800.md`、`.codex/project-memory.md`。
- 关键改动：新建 `datalogue-web/src/features/chat` 功能域，迁入普通 Chat 的 `chat-adapter`、`thread-list-adapter`、`Thread`、`ThreadList`、`MyComposer`、`MyMessage` 实现；旧 `src/assistant/*` 同名入口缩为薄 re-export，保证现有调用方继续可用；保留并补强主工作区已有的首条消息懒创建后端会话逻辑，新增 pending 草稿 fetch 防御、懒创建失败重试边界和成功后的 `datalogue:conv-resolved` 事件派发；同步更新 Chat 功能域 README 与目录治理 ADR 的 G061 边界记录。
- 验证方式：在 G061 独立工作树执行 `git diff --check` 通过；执行 `npm run test -- src/assistant/chat-adapter.test.js src/assistant/thread-list-adapter.test.js src/assistant/MyMessage.test.jsx src/components/chat-page.test.jsx`，结果 `4 passed, 80 passed`；执行 `npm run lint` 通过，保留既有 `13 warnings, 0 errors`；执行 `npm run build` 通过，保留 Vite 大 chunk warning；完整 `npm run test` 在本轮中曾因既有 `assistant-ui/DatalogueMessage.test.jsx` 缺少 `echarts` 依赖和 `components/settings.test.jsx` 缺少 `AuthProvider` 包裹失败，属于 G061 外部测试债务；Claude Code Review 最终产物 `.omx/artifacts/claude-review-g061-features-chat-reexports-20260709T212447+0800.md`，结论为 Blocker 0、Major 0、可以合并。
- 残留风险或后续事项：主工作区合并前将旧 `src/assistant/chat-adapter.js` 与 `src/assistant/thread-list-adapter.js` 的未提交脏改动以 `git stash push -m "pre-g061 assistant adapter dirty backup" -- ...` 方式保存备份；最终提交已吸收这些懒创建会话改动到 `src/features/chat`。后续应把 `src/assistant/chat-adapter.test.js` 迁入 `src/features/chat/__tests__` 或同等测试目录，并在所有生产调用方收口到 `src/features/chat` 后再删除旧兼容壳。

### 2026-07-09 21:36 · G062 Assistant 与 assistant-ui 前端边界

- 完成时间：2026-07-09 21:36。
- 功能名称：G062 Assistant 与 assistant-ui 前端边界。
- 涉及文件：`datalogue-web/src/assistant/README.md`、`datalogue-web/src/assistant-ui/README.md`、`docs/architecture/目录治理与模块边界.md`、`.omx/artifacts/claude-review-g062-assistant-boundaries-20260709T213420+0800.md`、`.codex/project-memory.md`。
- 关键改动：新增 `src/assistant` 目录护栏，明确该目录只保留 runtime adapter、API adapter、event adapter，以及已存在 Chat re-export 兼容壳，不再承载普通 Chat UI 实现；新增 `src/assistant-ui` 目录护栏，明确该目录只保留 assistant-ui 视觉组件、message parts 用户可见渲染和展示层安全过滤，不直接访问后端 HTTP/SSE 或 Workbench API；在目录治理 ADR 新增 G062 小节，固化 `src/assistant`、`src/assistant-ui`、`src/features/chat` 三者边界和测试迁移策略。
- 验证方式：执行 `git diff --check` 通过；执行 `rg -n "协议层清洗|展示层安全过滤|DatalogueThread|__tests__|lint/build/test|API adapter|event adapter|message parts" ...`，确认关键锚点齐全；Claude Code Review 最终产物 `.omx/artifacts/claude-review-g062-assistant-boundaries-20260709T213420+0800.md`，结论为 Blocker 0、Major 0、可以合并。
- 残留风险或后续事项：Claude 提出非阻塞 Minor：架构文档 2.2 仍是 Phase A 初始快照，可后续在前端目录继续迁移时加注指向 G055-G062 细化小节；`message-parts.js` 中部分多字段 fallback 仍是历史兼容逻辑，后续协议稳定后可评估是否迁回 adapter 层。

### 2026-07-09 21:55 · G063 Chat 页面与 shared 通用图标迁移

- 完成时间：2026-07-09 21:55。
- 功能名称：G063 Chat 页面与 shared 通用图标迁移。
- 涉及文件：`datalogue-web/src/features/chat/chat-page.jsx`、`datalogue-web/src/features/chat/chat-page.test.jsx`、`datalogue-web/src/components/chat-page.jsx`、`datalogue-web/src/components/chat-page.test.jsx`、`datalogue-web/src/shared/components/icons.jsx`、`datalogue-web/src/shared/components/README.md`、`datalogue-web/src/components/icons.jsx`、`datalogue-web/src/App.jsx`、`datalogue-web/src/features/chat/README.md`、`datalogue-web/src/features/chat/MyComposer.jsx`、`datalogue-web/src/features/chat/MyMessage.jsx`、`datalogue-web/src/features/chat/ThreadList.jsx`、`datalogue-web/src/assistant-ui/DatalogueActionBar.jsx`、`datalogue-web/src/assistant-ui/DatalogueComposer.jsx`、`datalogue-web/src/assistant-ui/DatalogueThreadList.jsx`、`datalogue-web/src/assistant/MyMessage.test.jsx`、`docs/architecture/目录治理与模块边界.md`、`.omx/artifacts/claude-review-g063-components-features-shared-final-20260709T215205+0800.md`、`.codex/project-memory.md`。
- 关键改动：将页面级 `ChatPage` 实现和完整测试迁入 `src/features/chat`，旧 `src/components/chat-page.jsx` 保留薄 re-export 兼容壳，旧 `src/components/chat-page.test.jsx` 改为兼容入口 smoke 测试，避免重复执行完整页面测试；将通用 `Icon` 组件迁入 `src/shared/components/icons.jsx`，旧 `src/components/icons.jsx` 保留 re-export，应用入口、Chat 功能域和 assistant-ui 组件统一改用 shared 图标入口；同步补充 shared README、Chat README 和目录治理 ADR 的 G063 边界记录。
- 验证方式：在独立工作树完成并 fast-forward 合并到 `main` 后，执行 `git diff --check HEAD^ HEAD` 通过；执行 `npm run test -- src/features/chat/chat-page.test.jsx src/components/chat-page.test.jsx src/assistant/chat-adapter.test.js src/assistant/thread-list-adapter.test.js src/assistant/MyMessage.test.jsx`，结果 `5 passed, 81 passed`；执行 `npm run lint` 通过，保留既有 `13 warnings, 0 errors`；执行 `npm run build` 通过，保留 Vite 大 chunk warning；Claude Code Review 最终产物 `.omx/artifacts/claude-review-g063-components-features-shared-final-20260709T215205+0800.md`，结论为 Blocker 0、Major 0、可以合并。
- 残留风险或后续事项：Claude 提出非阻塞 Minor：`src/assistant/MyMessage.test.jsx` 仍在旧 assistant 测试目录，后续可随测试目录治理迁入 `features/chat`；旧 `components` 兼容壳当前仍以 `export *` 暴露历史命名导出，后续待调用方完全收口后再缩窄或删除；主工作区仍有既有未提交 `registry.py` 业务边界改动和两张截图，本轮未纳入提交或回滚。

### 2026-07-09 22:08 · G064-G066 前端验证闸门与测试稳定化

- 完成时间：2026-07-09 22:08。
- 功能名称：G064-G066 前端验证闸门与测试稳定化。
- 涉及文件：`datalogue-web/src/components/settings.test.jsx`、`datalogue-web/vite.config.js`、`datalogue-web/tests/mocks/echarts.js`、`.omx/artifacts/claude-review-g066-frontend-tests-20260709T220401+0800.md`、`.codex/project-memory.md`。
- 关键改动：G064/G065 在主工作区确认 `npm run lint` 与 `npm run build` 可通过；G066 在独立工作树补齐前端完整单测的测试隔离，给 `settings.test.jsx` 增加 `auth-context` mock，避免默认账号页渲染时缺少 `AuthProvider`；在 Vitest `test.alias` 中把 `echarts` 指向测试专用轻量 mock，解决动态导入 `echarts` 在测试环境无法解析的问题，且 alias 只在 Vitest 生效，不影响生产构建。
- 验证方式：G064 执行 `npm run lint`，结果 `0 errors, 13 warnings`；G065 执行 `npm run build`，结果成功，仅保留既有 Vite chunk-size warning；G066 独立工作树和合入主工作区后均执行 `npm run test`，结果 `21 passed, 186 passed`，合入后再次执行 `npm run lint` 与 `npm run build` 均通过；`git diff --check HEAD^ HEAD` 通过；Claude Code Review 产物 `.omx/artifacts/claude-review-g066-frontend-tests-20260709T220401+0800.md` 结论为 APPROVE，无 Blocker/Major，并已采纳其对 ECharts mock 分工注释的 Minor 建议。
- 残留风险或后续事项：lint 仍有 13 个既有 warning，分布在 `agent-panel.jsx`、`apis.jsx`、`charts.jsx`、`datasets.jsx`、`datasources.jsx`、`editor-modal.jsx`、`notifications.jsx`、`features/chat/MyComposer.jsx`，本轮只保证不新增 error；Vite 大 chunk warning 仍为既有构建体积提示，后续如需处理应单独做代码分包。

### 2026-07-09 22:18 · G067 前端桌面路由 smoke 截图

- 完成时间：2026-07-09 22:18。
- 功能名称：G067 `/chat`、`/datasets`、`/datasources`、Workbench 桌面 smoke 截图对齐。
- 涉及文件：`.omx/artifacts/g067-desktop-smoke-20260709T221420+0800/results.json`、`.omx/artifacts/g067-desktop-smoke-20260709T221420+0800/chat.png`、`.omx/artifacts/g067-desktop-smoke-20260709T221420+0800/datasets.png`、`.omx/artifacts/g067-desktop-smoke-20260709T221420+0800/datasources.png`、`.omx/artifacts/g067-desktop-smoke-20260709T221420+0800/workbench.png`、`.omx/artifacts/g067-desktop-smoke-20260709T221420+0800/workbench-real.png`、`.codex/project-memory.md`。
- 关键改动：本轮为验证型 story，无生产代码或测试代码改动；使用本地前端 `http://localhost:5173` 和后端 `http://127.0.0.1:8000` 的真实运行服务，登录 `admin` 后完成 `/chat`、`/datasets`、`/datasources` 桌面首屏截图和轻量前端交互验证；Workbench 裸 `/workbench` 实际路由为隐藏恢复壳 `/workbench/:threadId`，先保留 fake thread 错误态截图，再用本地已有真实 `as_c63b713b-06c7-41be-8961-c49b37f88709` 补测成功态恢复壳截图。
- 验证方式：应用内 Browser 插件可连接但 `tab.playwright.domSnapshot()` 触发 `TypeError: o.incrementalAriaSnapshot is not a function`，因此改用同一 Browser 通道的 `evaluate`、locator、console logs 和 screenshot API；四个目标 surface 均无 Vite/React error overlay，console `error/warn` 为空；`/chat` 点击“查看全部模板”、`/datasets` 点击“新建数据集”、`/datasources` 点击“新建数据源”均能触发可见前端状态；Workbench 真实恢复壳显示 `BI WORKBENCH`、消息、任务时间线、引用和产物详情区。
- 残留风险或后续事项：本轮只覆盖桌面默认视口，不覆盖移动端；Workbench fake thread 只验证错误态外壳，成功态证据依赖当前本地数据库已有历史 `as_*` 线程；Browser 插件 DOM snapshot API 与当前运行时存在兼容问题，后续若要做更细 DOM 断言需升级或修复插件运行时。

### 2026-07-09 22:27 · G068-G069 E2E 截图资产目录治理

- 完成时间：2026-07-09 22:27。
- 功能名称：G068 根目录 E2E PNG 清点与 G069 文档截图资产迁移。
- 涉及文件：`.gitignore`、`docs/assets/screenshots/e2e/README.md`、`docs/assets/screenshots/e2e/datalogue-bi-worker-candidate-fallback-desktop.png`、`docs/assets/screenshots/e2e/datalogue-realtime-agent-progress-desktop.png`、`docs/assets/screenshots/e2e/workbench-e2e.png`、`.omx/artifacts/claude-review-g068-g069-doc-assets-20260709T222358+0800.md`、`.codex/project-memory.md`。
- 关键改动：在独立工作树 `codex/g068-g069-doc-assets` 中将 3 张已跟踪的根目录 E2E 截图以 `git mv` 迁入 `docs/assets/screenshots/e2e/`，保留 Git 历史；新增截图资产清单 README，明确长期文档资产与临时 Browser/Playwright 验证截图的边界；在 `.gitignore` 增加 `/*.png`，阻止新的根目录临时 PNG 被误加入仓库。主工作区已有未跟踪 `chat-after-login.png`、`chat-page-screenshot.png` 被界定为本地临时验证图，本轮不移动、不删除。
- 验证方式：执行 `git ls-files '*.png' | awk -F/ 'NF==1 {print}'` 无输出，确认已无被 Git 跟踪的根目录 PNG；执行 `git grep -nE '!\\[[^]]*\\]\\((datalogue-bi-worker-candidate-fallback-desktop|datalogue-realtime-agent-progress|workbench-e2e)\\.png\\)' || true` 无输出，确认没有旧路径 markdown 图片引用被破坏；执行 `git diff --check HEAD^ HEAD` 通过；Claude Code Review 产物 `.omx/artifacts/claude-review-g068-g069-doc-assets-20260709T222358+0800.md` 结论为 `APPROVE`，无阻塞问题。
- 残留风险或后续事项：Claude 提出非阻塞 Minor：`.gitignore` 中既有 `feishu-cli-auth-qrcode.png` 已被新的根目录 `/*.png` 覆盖，后续可在单独清理中移除冗余；本轮未处理主工作区既有未提交 `datalogue-api/app/runtime/engine/registry.py` 业务边界改动。

### 2026-07-09 22:34 · G070-G072 文档入口、归档边界与图片引用治理

- 完成时间：2026-07-09 22:34。
- 功能名称：G070 `docs/README.md` / `docs/上下文入口.md` 目录说明、G071 `docs/archive/` 只读归档边界、G072 markdown 图片引用验证。
- 涉及文件：`docs/README.md`、`docs/上下文入口.md`、`docs/archive/README.md`、`docs/archive/old-architecture/assets`、`.omx/artifacts/claude-review-g070-g072-docs-index-20260709T223113+0800.md`、`.codex/project-memory.md`。
- 关键改动：在文档总索引中补充“入口与当前上下文”“资产与交付物”“历史归档”三类导航；在 AI Agent 上下文入口中新增文档目录边界，明确 `architecture`、`api`、`assets`、`test-reports`、`deliverables`、`archive` 的读取策略；新增 `docs/archive/README.md`，声明 archive 只读、不参与常规上下文；为旧归档 `docs/archive/old-architecture/product/*` 的历史相对图片路径增加 `docs/archive/old-architecture/assets -> ../../assets` 兼容链接，不改写归档正文。
- 验证方式：执行限定 `docs/` 范围的 `python3` markdown PNG 引用解析脚本，结果 `all docs markdown png image references resolved (39)`；执行 `git diff --check HEAD^ HEAD` 通过；Claude Code Review 产物 `.omx/artifacts/claude-review-g070-g072-docs-index-20260709T223113+0800.md` 结论为 `APPROVE`，确认 symlink 是最小兼容方案且不破坏文档导航。
- 残留风险或后续事项：本轮没有改写 archive 历史正文；若未来跨平台环境无法保留 symlink，需要再评估复制资产或重写归档路径的替代方案。

### 2026-07-09 22:39 · G073-G074 根目录入口与文档主链说明验证

- 完成时间：2026-07-09 22:39。
- 功能名称：G073 根目录一级入口文件边界验证与 G074 文档入口主链/目录规划说明验证。
- 涉及文件：`.codex/project-memory.md`、`.omx/artifacts/get-goal-g073-readme-agents-claude-todos-docker-compose-20260709T223900+0800.json`、`.omx/artifacts/get-goal-g074-doc-entry-main-chain-directory-plan-20260709T224000+0800.json`。
- 关键改动：本轮为验证型 story，无生产代码或文档代码改动；确认根目录被 Git 跟踪的一级文件只剩 `.gitignore`、`AGENTS.md`、`CLAUDE.md`、`TODOS.md`、`docker-compose.yml`，符合根目录只保留项目入口文件的约束；确认 `docs/上下文入口.md` 已说明当前 AS-R0 主链、AgentScope Service 挂载、Agent Team API 入口和旧 LangGraph 归档边界，`docs/README.md` 已把目录治理文档作为当前上下文入口。
- 验证方式：执行 `git ls-files | awk -F/ 'NF==1 {print}' | sort`，输出 `.gitignore`、`AGENTS.md`、`CLAUDE.md`、`TODOS.md`、`docker-compose.yml`；读取 `docs/上下文入口.md` 和 `docs/README.md`，确认包含 `AgentScopeServiceTaskRunner`、`/agentscope`、`/api/agent-team/tasks/stream`、`docs/architecture/目录治理与模块边界.md`、`docs/archive/` 只读边界；G070-G072 的 Claude Code Review `.omx/artifacts/claude-review-g070-g072-docs-index-20260709T223113+0800.md` 已对这两个入口文档给出 `APPROVE`。
- 残留风险或后续事项：根目录仍有未跟踪/忽略的本地运行产物和缓存目录，例如 `.omx/`、`.codex/`、`.worktrees/`、`outputs/`、`logs/`、`chat-after-login.png`、`chat-page-screenshot.png`；它们不属于 Git 跟踪入口文件，本轮不删除。

### 2026-07-09 22:42 · G075-G079 停机闸门未触发确认

- 完成时间：2026-07-09 22:42。
- 功能名称：G075 facade-only 回退条件、G076 AgentScope E 阶段停机条件、G077 前端 build 停机条件、G078 文档资产暂停条件、G079 用户保持现状条件确认。
- 涉及文件：`.codex/project-memory.md`、`.omx/ultragoal/ledger.jsonl`、`.omx/ultragoal/goals.json`。
- 关键改动：本轮为验证型 story，无生产代码或文档代码改动；确认 G075-G079 都是执行计划的条件闸门，而不是需要新增实现的功能。当前执行没有出现大面积循环导入，后端 AgentScope/Agent Team/Workbench 关键子集测试在 G056-G059 已通过，前端 `npm run lint` / `npm run build` / `npm run test` 在 G064-G066 已通过，文档资产引用在 G068-G072 已清点、迁移并验证，用户明确要求继续 `$ultragoal` 开发而不是保持现状。
- 验证方式：引用前序已 checkpoint 证据：G056-G059 后端关键子集测试、G064-G066 前端 lint/build/test、G068-G072 文档资产与引用验证、G073-G074 入口边界验证均为 complete；`.omx/ultragoal/ledger.jsonl` 记录这些 checkpoint，当前 `omx ultragoal checkpoint` 输出显示 `0 failed, 0 review-blocked, 0 needs-user-decision`。
- 残留风险或后续事项：这些闸门只说明截至 G079 未触发停机/回退条件；后续 E/F/G 阶段如果出现新的循环导入、AgentScope 主链测试失败、前端构建失败或用户改变方向，仍需要按对应闸门重新停机处理。

### 2026-07-09 22:48 · G080-G085 执行顺序与 Ultragoal 工作流采用确认

- 完成时间：2026-07-09 22:48。
- 功能名称：G080 Phase A+B、G081 Phase C+D、G082 Phase E、G083 Phase F+G、G084 推荐 Ultragoal 工作流、G085 建议启动执行确认。
- 涉及文件：`.codex/project-memory.md`、`.omx/ultragoal/goals.json`、`.omx/ultragoal/ledger.jsonl`。
- 关键改动：本轮为验证型 story，无生产代码或文档代码改动；确认实际执行顺序遵循原计划：先完成目录规划、矩阵和 facade 骨架；再完成数据源/SQL 执行层拆分与测试；随后完成 AgentScope / BI / Agent Team 高风险关键子集测试；最后用独立 worktree 串行合并前端目录治理和文档资产治理，并以 Ultragoal ledger 串行 checkpoint。
- 验证方式：`.omx/ultragoal/ledger.jsonl` 已记录 G001-G079 的连续完成证据；前端与文档阶段均使用独立 worktree、Claude Code Review 和 fast-forward merge；`$Team` 因当前不在 tmux 中未启动，符合 Team skill 对非 tmux 场景的约束，当前 leader 直接负责 Ultragoal checkpoint。
- 残留风险或后续事项：这些目标确认的是执行策略已被采用；后续若要真正启用 tmux Team，需要在 `$TMUX` 可用的 OMX CLI 会话中启动。

### 2026-07-09 22:55 · G086-G089 四条执行 lane 收口确认

- 完成时间：2026-07-09 22:55。
- 功能名称：G086 backend-inventory/facade lane、G087 data-source lane、G088 frontend lane、G089 docs-assets lane 收口确认。
- 涉及文件：`.codex/project-memory.md`、`.omx/ultragoal/goals.json`、`.omx/ultragoal/ledger.jsonl`、`docs/architecture/目录治理与模块边界.md`、`docs/README.md`、`docs/上下文入口.md`、`docs/assets/screenshots/e2e/README.md`。
- 关键改动：本轮为验证型 story，无生产代码或文档代码改动；确认四条推荐执行 lane 均已落地：backend-inventory/facade lane 覆盖 G018-G031 和后端域边界；data-source lane 覆盖 G032-G039 的数据源适配拆分与测试；frontend lane 覆盖 G060-G067 的 features/shared/assistant-ui 迁移、lint/build/test 与桌面 smoke；docs-assets lane 覆盖 G068-G074 的根目录 PNG 清理、文档资产目录、文档索引和归档边界。
- 验证方式：引用前序 checkpoint 证据和 Claude Code Review 产物：G063、G066、G068-G069、G070-G072 均有 `APPROVE` 或无 Blocker/Major 的 review 结果；`omx ultragoal checkpoint` 输出显示截至 G085 为 `0 failed, 0 review-blocked, 0 needs-user-decision`。
- 残留风险或后续事项：这些节点是对已完成 lane 的审计收口；主工作区仍保留既有未提交 `datalogue-api/app/runtime/engine/registry.py` 业务边界改动，未纳入本轮 lane 收口提交或回滚。

### 2026-07-09 23:00 · G090-G093 Ultragoal 最终质量门禁收口

- 完成时间：2026-07-09 23:00。
- 功能名称：G090 durable plan 路径确认、G091 context snapshot 路径确认、G092 Team/Ultragoal 授权边界确认、G093 最终质量门禁。
- 涉及文件：`datalogue-api/app/domains/query_execution/report_input.py`、`datalogue-api/tests/test_report_worker_artifact_input.py`、`.codex/project-memory.md`、`.omx/ultragoal/goals.json`、`.omx/ultragoal/ledger.jsonl`、`.omx/plans/prometheus-strict/deep-directory-planning.md`、`.omx/context/deep-directory-planning-20260709T032633Z.md`、`.omx/artifacts/final-quality-gate-g093-*.json`、`.omx/artifacts/claude-review-final-g093-*.md`。
- 关键改动：确认 durable plan 与 context snapshot 文件仍存在，确认 `$Team` 因当前 Codex App 会话不在 tmux 中未启动，实际执行采用 Ultragoal ledger、独立 worktree、Claude Code Review 与最终质量门禁串行收口；最终独立代码审查发现 Report Worker rows 清洗只拦截精确字段名，可能让 `query_plan_dump`、`raw_payload`、`schema_notes` 等行字段变体进入报告输入面，因此补充 `_contains_forbidden_report_token()` 并让 source 与 row key 共用包含式 denylist，确保 `sql/schema/query_plan/raw/repair/dsl/debug/internal` 字段名变体都被剔除；同步补充嵌套 dict/list 回归测试。
- 验证方式：修复前 `test_report_worker_artifact_input.py` 失败并复现 `query_plan_dump/raw_payload/schema_notes/raw_score` 泄漏；修复后 `test_report_worker_artifact_input.py` 为 `7 passed, 3 warnings`，后端关键测试子集加 Report Worker 为 `189 passed, 3 warnings`；执行 `git diff --check` 通过；执行 `git ls-files '*.png' | awk -F/ 'NF==1 {print}'` 无输出；执行 docs markdown PNG 引用解析脚本通过；前端 `npm run test` 为 `21 passed, 186 passed`；`npm run lint` 为 `0 errors, 13 warnings`；`npm run build` 通过，仅保留既有 Vite chunk-size warning；最终 Claude Code Review 和独立代理复审无阻塞问题后，生成 G093 quality gate JSON 并 checkpoint。
- 残留风险或后续事项：主工作区仍保留既有未提交 `datalogue-api/app/runtime/engine/registry.py` 现场改动，该现场会导致 `test_agentscope_static_agent_registry.py` 的 worker 模板期望和当前运行结果不一致，本轮不回滚；lint 既有 13 个 warning 和 Vite chunk-size warning 后续可单独治理。

### 2026-07-09 23:33 · 左侧功能栏真实数量

- 完成时间：2026-07-09 23:33。
- 功能名称：左侧功能栏真实数量。
- 涉及文件：`datalogue-api/app/api/navigation.py`、`datalogue-api/app/api/__init__.py`、`datalogue-api/tests/test_navigation_counts.py`、`datalogue-web/src/api/client.js`、`datalogue-web/src/components/sidebar.jsx`、`datalogue-web/src/components/sidebar.test.jsx`、`.codex/project-memory.md`。
- 关键改动：新增 `/api/navigation/counts` 统一导航统计接口并接入登录鉴权，侧栏数量改为读取数据库真实数量；`dashboard/history/datasets/knowledge/review/datasources` 分别来自 Agent Team task、未归档会话、语义数据集、业务术语加分析蓝图、未通过语义验证项、数据源。当前 API 发布页仍无持久化真相源，因此 `apis` 返回 `null`，前端不再显示原写死 `7`。
- 验证方式：先按 TDD 确认后端测试因 404 失败、前端测试因仍渲染硬编码数量失败；Claude Code review 首轮指出统计接口缺少认证保护、历史数量包含归档会话，已补充未登录 401 测试和未归档会话口径，复审结论 `APPROVE`、无 Blocker/Major；实现后执行 `./.venv/bin/python -m pytest tests/test_navigation_counts.py tests/test_dataset.py tests/test_datasource.py tests/test_conversation.py -q`，结果 `49 passed, 29 warnings`；执行 `npm run test`，结果 `22 passed, 188 passed`；执行 `npm run lint`，结果 `0 errors, 13 existing warnings`；执行 `npm run build` 通过，仅保留既有 Vite chunk-size warning；最终 `git diff --check` 通过。
- 残留风险或后续事项：`API 接口` 数量当前不显示，因为仓库尚无发布 API 持久化表；如果后续把 `apis.jsx` 从静态演示页改为真实发布接口管理，需要把该表纳入 `/api/navigation/counts`。
>>>>>>> Stashed changes
>>>>>>> main

### 2026-07-10 11:18 · 修复选择数据集后首次对话前端无反馈

- 完成时间：2026-07-10 11:18。
- 功能名称：修复选择数据集后首次对话前端无反馈。
- 涉及文件：`datalogue-web/src/features/chat/chat-adapter.js`、`datalogue-web/src/assistant/chat-adapter.test.js`、`.codex/project-memory.md`。
- 关键改动：
  1. `chat-adapter.js` 首条消息懒创建后端会话（`ensureConversationForThread`）成功后，删除此前立即派发的 `datalogue:thread-rename` 事件，仅保留 `datalogue:conv-resolved` 更新 idMap；sidebar/URL 切换留在 SSE `final` 事件后再处理。
  2. 新增中文注释说明提前切换会导致 stream 仍挂在草稿 thread 上、页面跳到空会话、用户消息与流式反馈丢失。
  3. `chat-adapter.test.js` 新增回归测试，验证懒创建阶段只触发 `conv-resolved`，`thread-rename` 仅由 final 事件触发一次；使用 `mockImplementationOnce` 避免污染后续测试用例。
- 验证方式：
  - Playwright 真机复现：修复后选择数据集发送消息，页面出现用户消息气泡和“正在生成…”助手回复，`.chat-inner` 不再为空。
  - `npx vitest run src/assistant/chat-adapter.test.js`：32 passed。
  - `npm run test -- --run`：190 passed，2 failed（`settings.test.jsx` 的 `useLocation() may be used only in the context of a <Router>`），为本次改动前已存在的 pre-existing 失败。
  - `npm run build`：构建成功，仅保留既有 Vite chunk-size warning。
- 残留风险或后续事项：`settings.test.jsx` 的 Router 上下文失败与 chat 无关，但属于 pre-existing 测试债务；后续若需要可在前端测试稳定化专题中处理。Playwright 复现脚本 `/tmp/pw-test/`、`/tmp/repro_chat_dataset.js`、`/tmp/login_api.py` 为本地临时文件，未纳入仓库，可手动清理。

### 2026-07-10 16:30 · /chat/{id} 历史消息 rehydrate（后端聚合 agentscope_message）

- 完成时间：2026-07-10 16:30。
- 功能名称：`/chat/{id}` 打开历史会话时无法回放对话内容，后端 `get_conversation` 只读旧 `messages` 表导致 agentscope 主链会话空白。
- 涉及文件：`datalogue-api/app/api/conversation.py`、`datalogue-api/tests/test_conversation_history_agentscope.py`。
- 关键改动：
  1. `get_conversation` 消息主数据源改为 `agentscope_message`：先按 `legacy_conversation_id` 聚合所有 `AgentScopeSession.thread_id`（同一 conversation 前端未稳定传 thread_id 时会新建多个 session），再按 `created_at, id` 排序读取全部 `AgentScopeMessage`。
  2. 新增 `_agentscope_message_to_public / _agentscope_payload_to_metadata / _reasoning_summary_to_step_trace`：把 agentscope 消息映射成前端 `MessageOut` 契约——`business_payload_json.artifact_ref` → `response_metadata.result_ref` + `artifact_card.primary_ref`，`reasoning_summary` status `completed` 统一改为前端只识别的 `done` 才会渲染 reasoning part，可选 `task_id/checkpoint_ref` 也一并透出。
  3. 无 agentscope session 关联时回退老 `messages` 表，保证 rehydrate 前的旧会话仍能打开。
  4. 新增 `tests/test_conversation_history_agentscope.py`：覆盖单 session、多 session 聚合排序、无 agentscope 回退 legacy、无任何消息返回空、reasoning `completed→done` 与 `artifact_ref→result_ref` 映射五种场景。
- 验证方式：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python -m pytest tests/test_conversation_history_agentscope.py -q` 全部通过；Playwright 真机复现 `/chat/200` 会话正常回放 3 轮问答 + artifact 卡片。
- 残留风险或后续事项：agentscope 侧 `business_payload_json` 仍以 `artifact_ref` 单主 ref 为主，多 artifact 的 `related_refs` 目前不回放；后续若 Report Worker 输出多 artifact 需要一起展示，需要扩 `_agentscope_payload_to_metadata`。

### 2026-07-10 15:25 · 移除 max_limit 硬上限 + 查询结果分页表格

- 完成时间：2026-07-10 15:25。
- 功能名称：移除 SQL 生成阶段 max_limit 硬上限，改为查询时先 COUNT 再按需截断到 10000；前端产物详情展示分页表格，每页 100 行。
- 涉及文件：
  - `datalogue-api/app/core/config.py`、`datalogue-api/app/domains/query_execution/artifact_store.py` — `QUERY_ARTIFACT_MAX_BYTES` 从 2MB 提升到 50MB
  - `datalogue-api/app/domains/bi/worker/runtime.py` — fallback DSL `limit` 从 500 提升到 10000
  - `datalogue-api/app/domains/query_execution/query_constraints.py` — `default_limit=10000`、`max_limit=10000`、`max_limit` 上限 10000→1000000000
  - `datalogue-api/app/domains/query_execution/report_input.py` — `REPORT_RESULT_MAX_ROWS` 默认 30→10000；`total_row_count` 优先取 `execution_result.total_row_count`，同步写回 payload
  - `datalogue-api/app/domains/workbench/view_model.py` — `_artifact_preview_payload` 对 `sql_result` 返回 `columns/rows/row_count/total_row_count/truncated`；`_FORBIDDEN_OUTPUT_KEYS` 移除 columns/rows 屏蔽，允许前端拿到表格数据
  - `datalogue-web/src/shared/components/DataTable.jsx` — 新增分页表格组件（100 条/页，含翻页控件和统计栏）
  - `datalogue-web/src/components/workbench-panel.jsx` — `WorkbenchArtifactDrawer` 检测 `preview_payload` 有表格数据时渲染 DataTable
  - `datalogue-web/src/styles.css` — DataTable 全部样式
- 关键改动：
  - SQL 生成阶段不再硬卡 10000 上限；运行时按查询总量决定是否截断。
  - 产物的行数上限从 30 行提升到 10000 行，前端客户端分页每页 100 行。
  - 产物预览增加 `total_row_count` 和 `truncated` 元信息。
- 验证方式：`pytest tests/test_sql_guard.py -x -q` 14 passed；`pytest tests/test_preview_count.py -x -q` 3 passed；前端 `npm run lint` 0 errors、`npm run build` 成功。
- 残留风险：10000 写在 `report_input.py` 硬编码值，未抽取为环境变量；10000 行 × 多列的数据在 artifact 存储和传输时带宽/延迟增加，artifact max_bytes=50MB 理论够用但需观察。

### 2026-07-10 12:26 · Preview COUNT(*) 前置修复与回归测试补齐

- 完成时间：2026-07-10 12:26。
- 功能名称：修复 preview_dataset_sql 前置 COUNT(*) 生成缺少 `*` 的 bug，并补齐三条回归测试。
- 涉及文件：`datalogue-api/app/domains/query_execution/preview.py`、`datalogue-api/tests/test_preview_count.py`。
- 关键改动：
  1. `_build_count_sql` 里 `exp.Count()` 缺 `this=exp.Star()`，导致某些方言渲染为 `SELECT COUNT() FROM (...) cnt`，实际执行必然失败。修复为 `exp.Count(this=exp.Star())`，同时对 `inner.subquery()` 加 `# type: ignore[attr-defined]` 消除 mypy 因 `Expression` 基类无 `subquery` 属性产生的 attr-defined 错误（运行时 Query 子类均实现）。
  2. 新增 `tests/test_preview_count.py` 三条测试：总量未超过 10,000 时 row_count/total_row_count 都等于真实总量；总量超过 10,000 时实际返回 10,000 行但 row_count 记录真实总量；COUNT 执行失败时降级为直接执行且不报错。fallback 测试的 fake connection 补齐了 `_mapping` 包装，避免 preview 层访问 `row._mapping` 时炸 `'tuple' object has no attribute '_mapping'`。
- 验证方式：`pytest tests/test_preview_count.py -q` 3 passed；联跑相关测试 48 passed；`black + ruff + mypy` 通过。
- 残留风险：`_MAX_PREVIEW_ROWS = 10000` 与 `query_constraints.max_limit=10000`、`sql_guard` 默认上限保持一致；如后续调整全局上限，需同步这三处。

### 2026-07-10 11:47 · Leader Prompt 强制触发 Report Worker + Worker 注册表收敛

- 完成时间：2026-07-10 11:47。
- 功能名称：Leader Prompt 增加用户明确报告意图时强制调用 Report Worker，同时把 worker 注册表收敛到 bi/report 两类。
- 涉及文件：`datalogue-api/app/prompts/agent_team.py`、`datalogue-api/app/runtime/engine/registry.py`、`datalogue-api/tests/test_agentscope_static_agent_registry.py`。
- 关键改动：
  1. `LEADER_AGENT_SYSTEM_PROMPT` 结构化 report worker 判断规则：用户原始问题中出现"报告/总结/分析/汇报/以报告方式/用报告展示/写成报告/生成报告"等表达，或要求分析、总结、对比、归因、趋势、经营解读、汇报材料时，**必须创建 report worker**，不得以结果简单为由跳过；只有当用户只要原始列表、单值或极少行明细时才可以不创建。
  2. `registry.py` 注释掉 python/audit worker 模板；`tests/test_agentscope_static_agent_registry.py` 的 `EXPECTED_WORKER_TEMPLATE_TYPES` 同步收敛为 `("bi", "report")`。
  3. `tools.py` `build_datalogue_progressive_bi_worker_tools` 里未知 failure_type 的兜底从 `FIELD_NOT_FOUND` 改为 `EXECUTE_FAILED`，避免误把执行失败归类到字段缺失导致 repair 走错分支。
- 验证方式：`black + ruff + mypy` 通过；`pytest tests/test_agentscope_static_agent_registry.py -v` 8 passed。
- 残留风险：chat 入口 `task_type` 仍固定 `bi_query`，report worker 依赖 BI Worker 先成功返回 `artifact_ref` 后 Leader 才创建；若 BI 失败或无 artifact，report 仍无法触发。

### 2026-07-10 12:40 · datasource dialect 归一化只在缺省时覆盖 + Doris/MariaDB→MySQL

- 完成时间：2026-07-10 12:40。
- 功能名称：数据源方言归一化仅在用户未显式设置时覆盖，Doris 与 MariaDB 统一落到 MySQL 执行方言。
- 涉及文件：`datalogue-api/app/domains/data_source/service.py`。
- 关键改动：
  1. `enrich_datasource_defaults` 判断 `data["dialect"]` 是否为空：非空则以用户值经 `normalize_execution_dialect` 归一化；空才补默认。
  2. `normalize_execution_dialect` 内 Doris 强制映射到 `mysql`；显式传入 `mariadb` 也归一化为 `mysql`（MySQL 兼容产品统一执行方言）。
- 验证方式：现存单测 `tests/test_datasource.py` 未新增用例，本次是最小增量修补。
- 残留风险：如果未来引入其他 MySQL 兼容产品（TiDB、OceanBase 等），需在此显式加入映射。

### 2026-07-10 11:00 · Onboarding 快速指南

- 完成时间：2026-07-10 11:00。
- 功能名称：整理项目 Onboarding 快速指南。
- 涉及文件：`docs/Onboarding快速指南.md`、`docs/README.md`。
- 关键改动：综合项目现有架构文档、执行链路、数据模型、目录治理、API 参考、编码规范、Docker 部署等全部材料，整理成一份面向新开发者的快速上手指南。指南包含：项目定位与产品形态、技术栈速览、环境搭建（Docker 与本地两种方案）、核心架构 5 分钟理解、关键文件速查表、开发规范门禁、常见开发任务速查、测试验证路径、问题排查速查、术语表、推荐阅读顺序。文档索引 `docs/README.md` 同步加入新指南入口。
- 验证方式：指南内容交叉验证自 `docs/architecture/` 系列文档、`datalogue-api/README.md`、`.codex/project-memory.md`、`AGENTS.md`、`datalogue-api/docs/CODE_STYLE.md`、`datalogue-api/docs/CHECKLIST.md`、`.env.example`、`docker-compose.yml` 等源文件，确保技术细节准确。
- 残留风险：指南为当前架构（AS-R0）快照，若后续架构发生重大变更（如 AgentScope 版本升级、目录物理搬迁完成），需同步更新指南对应章节。

### 2026-07-10 16:58 · Chat 查询结果详情组件支持分页

- 完成时间：2026-07-10 16:58。
- 功能名称：Chat 消息中的查询结果详情（ArtifactDetailPanel）支持客户端分页。
- 涉及文件：
  - `datalogue-web/src/features/chat/MyMessage.jsx` — `ArtifactDetailPanel` 复用 `DataTable`，移除原有的 100 行硬截断与“展示前 N 行”提示。
  - `datalogue-web/src/shared/components/DataTable.jsx` — 新增可选 `className` prop，方便外部控制布局。
  - `datalogue-web/src/styles.css` — 新增 `.artifact-detail-data-table` 及 `.artifact-detail-data-table .data-table-scroll` 样式，限定聊天详情表格区高度并保留统计栏/分页控件固定。
  - `datalogue-web/src/assistant/MyMessage.test.jsx` — 新增超过 100 行时的分页切换回归测试。
  - `.codex/project-memory.md` — 追加完成记录。
- 关键改动：
  1. `ArtifactDetailPanel` 不再自行渲染 `<table>`，而是把脱敏/截断后的列标签与行数据转换成 `DataTable` 需要的 `{ [label]: value }` 格式，统一走通用分页表格组件。
  2. 保留原有的单元格安全过滤（`DETAIL_BLOCKED_TEXT_RE`、240 字符截断、空值处理），避免 SQL/schema/内部字段泄露到用户可见层。
  3. `DataTable` 增加 `className` 扩展点；聊天详情通过 `artifact-detail-data-table` 类把表格滚动区限制在 320px，避免 100 行数据撑破消息气泡。
  4. 切换产物引用（`detail.ref`）时通过 `key={detail.ref}` 重置 `DataTable` 内部页码，防止上一个产物的分页状态残留。
- 验证方式：
  - `npm run test -- MyMessage.test.jsx`：`22 passed`。
  - `npm run lint`：`0 errors`，仅保留 14 个 pre-existing warnings。
  - `npm run build`：构建成功，仅保留既有 Vite chunk-size warning。
- 残留风险或后续事项：当前仍为客户端全量加载后分页；若单产物行数接近或超过后端 10000 行截断上限，首次 `getArtifact` 请求的响应体积和解析耗时可能较高，后续可按需改为服务端分页或流式加载。

### 2026-07-10 17:06 · 修复聊天查询结果详情只展示前 30 行及分页误导

- 完成时间：2026-07-10 17:06。
- 功能名称：修复聊天查询结果详情实际只展示 30 行、分页页码虚假的问题。
- 涉及文件：
  - `datalogue-api/app/core/config.py` — `REPORT_RESULT_MAX_ROWS` 默认值从 30 改为 10000，使 sql_result artifact 落库时保留更多明细行。
  - `datalogue-web/src/shared/components/DataTable.jsx` — 分页总页数改为按实际返回行数（`effectiveTotal`）计算，避免总行数大于返回行数时生成空白页码。
  - `datalogue-web/src/assistant/MyMessage.test.jsx` — 新增“后端截断时不展示虚假分页”回归测试。
  - `datalogue-api/tests/test_workbench_view_api.py` — 同步更新 Workbench artifact 预览测试，移除对 `columns/rows` 的全局禁用断言，匹配当前已暴露表格数据的接口行为。
  - `.codex/project-memory.md` — 追加完成记录。
- 关键改动：
  1. 之前前端分页组件已就绪，但后端 `build_sql_result_report_payload` 仍按 `REPORT_RESULT_MAX_ROWS=30` 截断落库，导致 `row_count=243` 时实际只存 30 行，前端出现“3 页但每页都只有前 30 行”的假象。
  2. 将默认值提升到 10000 后，新查询的 artifact 会保留最多 10000 行，前端每页 100 行可正常翻页。
  3. 同时修复 `DataTable` 分页逻辑：当后端返回行数小于总行数时，按实际返回行数计算页码并隐藏无法点击的“下一页”，仅展示“展示前 N 行”提示，避免用户切到空白页。
- 验证方式：
  - 后端：`pytest tests/test_report_worker_artifact_input.py tests/test_conversation.py tests/test_sql_guard.py tests/test_preview_count.py tests/test_agentscope_service_tools.py tests/test_artifact_api.py tests/test_workbench_view_api.py -q`，结果 `61 passed`。
  - 前端：`npm run test -- MyMessage.test.jsx`，结果 `23 passed`；`npm run lint` 0 errors；`npm run build` 成功。
- 残留风险或后续事项：已生成的旧 artifact 仍只存了 30 行，无法通过本次改动恢复；用户需重新发起查询才能体验到完整分页。10000 行 × 多列的 artifact 体积需继续观察 `QUERY_ARTIFACT_MAX_BYTES=50MB` 是否足够。
