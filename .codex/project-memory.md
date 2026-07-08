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

### 2026-07-07 17:49 · BI Worker Query Plan 契约错误详细诊断

- 涉及文件：`datalogue-api/app/agentscope_service/tools.py`、`datalogue-api/tests/test_agentscope_service_tools.py`、`.codex/project-memory.md`
- 关键改动：`bi_worker_repair_request` 新增 `validation_error_details`，在保持不回显 SQL、schema、raw input 的前提下，为每个 Query Plan 契约错误输出中文 `message` 和 `expected`；针对 `join_requirements.*.left/right/type` 明确提示应改用 `left_alias/right_alias/join_type`，针对 filter operator 明确提示等值筛选应使用 `=` 而不是 `eq`；顶层额外字段名继续收敛为 `root.extra_field`，避免暴露模型臆造字段原文。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_service_tools.py -q` 为 `10 passed, 2 warnings`；执行 `cd datalogue-api && .venv/bin/ruff check app/agentscope_service/tools.py tests/test_agentscope_service_tools.py` 通过；执行 `git diff --check -- datalogue-api/app/agentscope_service/tools.py datalogue-api/tests/test_agentscope_service_tools.py` 通过。
- 残留风险：本轮只增强工具返回的安全诊断 payload，未做真实页面 smoke；如果前端需要把 `validation_error_details` 做成可视化折叠面板，还需另补 UI 展示和前端测试。

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

### 2026-07-08 10:58 · BI Worker thinking 流式摘要集成验证阻断记录（worker-3）

- 涉及文件：`.codex/project-memory.md`；只读核对 `datalogue-api/app/agentscope_service/worker_logging.py`、`datalogue-api/app/agentscope_service/projection.py`、`datalogue-api/app/runtime/agent_team_runtime.py`、`datalogue-web/src/assistant/agent-team-event-adapter.js`、`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/MyMessage.jsx` 与对应测试。
- 关键结论：当前 worker-3 worktree 尚未集成计划要求的 `DATALOGUE_DEBUG_STREAM_RAW_THINKING`、`bi_worker_thinking_summary`、`bi_worker_raw_thinking_delta`、`debug_raw/raw_delta`、`reasoningKind/streamGroupId` 实现；源码扫描这些关键字均为 0 命中，因此不能宣称“BI Worker thinking 事件已按 debug 开关流式进入推理摘要”。并行探针发现当前投影层仍可能把 `ThinkingBlockDeltaEvent` 按泛化 delta 规则转成 `message.delta`，前端又会把 `message.delta` 累积为 `live_thinking` reasoning 并在 final 后保留；如果该 delta 承载 raw thinking，会违反“raw delta 默认关闭、仅 debug 开关透传、不得进入 artifact/final reasoning_summary”的边界。前端 trace/custom denylist 也尚未覆盖 `raw_delta/rawDelta/thinking_delta/thinkingDelta`。
- 验证方式：执行 `cd datalogue-api && uv run --python /Users/yangkai/.local/bin/python3.11 pytest tests/test_agentscope_service_worker_logging.py tests/test_agentscope_agent_team_task_runner.py tests/test_agentscope_event_projection.py -q` 为 `47 passed, 2 warnings`；执行 `cd datalogue-web && npm test -- src/assistant/agent-team-event-adapter.test.js src/assistant/chat-adapter.test.js src/assistant/MyMessage.test.jsx --run` 为 `3 passed, 55 passed`，以及 `npm test -- agent-team-event-adapter chat-adapter --run` 为 `2 passed, 38 passed`；`npm run lint` 通过但保留既有 `0 errors, 15 warnings`；`npm run build` 通过但保留既有 Vite large chunk warning；`uv run --python /Users/yangkai/.local/bin/python3.11 ruff check app/agentscope_service/worker_logging.py tests/test_agentscope_service_worker_logging.py` 通过；`mypy app/agentscope_service/worker_logging.py` 因仓库既有 159 个跨模块类型债失败，非本次文档改动引入。
- 残留风险：worker-1/worker-2 代码面合并前，worker-3 只能确认现有安全日志/前端基础回归未破坏，不能确认新增 thinking streaming 功能完成。合并前建议补后端回归：`ThinkingBlockDeltaEvent` 默认不得产生用户可见 `message.delta`，仅 `DATALOGUE_DEBUG_STREAM_RAW_THINKING=true` 允许受控 debug 事件；补前端回归：`message.delta`/final payload 中的 raw/thinking delta 不进入 `content`、`metadata.custom`、`datalogue:trace` 或 final `reasoning_summary`。
