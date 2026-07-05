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


### 2026-07-05 11:22 · AgentScope 候选确认续跑与真实页面 smoke 闭环

- 涉及文件：`datalogue-api/app/runtime/agent_team_runtime.py`、`datalogue-api/app/agentscope_service/runner.py`、`datalogue-api/app/agentscope_service/registry.py`、`datalogue-api/tests/test_agent_team_task_runtime.py`、`datalogue-api/tests/test_agentscope_agent_team_task_runner.py`、`datalogue-api/tests/test_agentscope_static_agent_registry.py`、`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/agent-team-event-adapter.js`、`datalogue-web/src/assistant/MyMessage.jsx`、对应前端测试、`.codex/project-memory.md`
- 关键改动：修复候选数据集卡点击后把“确认使用：生产经营管理系统日志数据集”误当新问题的问题。候选确认 final payload、前端 pending clarification 和候选卡点击响应现在都会保留 `original_question`，第二轮请求以原始问题作为 `question`，只把确认数据集放在 `dataset_id/clarification_response`。同时在 AgentScope runner 中把已确认 `dataset_id` 显式写成 `confirmed_dataset_id/confirmed_question` 执行上下文，不再把 `clarification_response` 暴露给 LLM，并强化 Leader/BI Worker prompt：已确认数据集时必须直接调用 `datalogue_query_dataset(dataset_id=..., confirmed_question=原问题)`，严禁再次调用候选筛选工具或要求用户重新确认。
- 真实页面 smoke：桌面 Playwright 走 `http://localhost:5173/chat`，问题为“查询杨凯2025年工作日志”。页面先出现候选数据集卡，包含“运营双周会议数据集”“生产经营管理系统日志数据集”“生产经营管理系统供应商数据集”，且不含 `Theuserwantstoquery/Ineedtocreate/Letmebreak` 等内部规划文本；点击“生产经营管理系统日志数据集”后，第二轮请求体为 `question=查询杨凯2025年工作日志`、`dataset_id=10`、`clarification_response.original_question=查询杨凯2025年工作日志`。页面可见 BI Worker 调用 `datalogue_query_dataset`、结果卡 100 行 48 列、artifact 引用 `artifact:10ade05804c44191a36607ef04d2aae5`；点击“查看详情”后详情表格正常加载，Workbench 产物详情同一 ref。
- 日志与数据库核验：后端日志包含 `[agentscope.bi_worker.dataset_query.completed]`，同一 artifact ref、`dataset_id=10`、`row_count=100`、`column_count=48`；`[datalogue.output]` 的 `message.completed` 也带同一 artifact ref。数据库 `query_artifact` 表中 `artifact_id=artifact:10ade05804c44191a36607ef04d2aae5` 存在，`kind=sql_result`、`dataset_id=10`、`content_mime=application/json`、`rows=100`、`columns=48`；真实 `GET /api/artifacts/artifact%3A10ade05804c44191a36607ef04d2aae5` 返回 200 并可读取结果内容。
- 验证方式：执行 Agent Team/AgentScope 相关后端 pytest、前端 adapter/UI 测试、ruff、compileall、lint 和 build；真实页面 smoke 覆盖候选数据集卡、BI Worker 查询、结果卡、artifact 详情、后端日志和数据库 artifact 记录对齐。
- 残留风险：本轮只按桌面真实页面验证，未做移动视口；`.codex/project-memory.md` 最新详细记录仍超过 10 条，后续应单独做项目记忆压缩，避免和功能提交混在一起扩大改动面。

### 2026-07-05 12:08 · AgentScope 模型控制面代理与迁移目标修订

- 涉及文件：`docs/superpowers/plans/2026-07-05-agentscope-service-model-control-plane.md`、`datalogue-api/app/agentscope_service/client.py`、`datalogue-api/app/api/agentscope_control_plane.py`、`datalogue-api/app/api/__init__.py`、`datalogue-api/tests/test_agentscope_service_client.py`、`datalogue-api/tests/test_agentscope_control_plane_api.py`、`.codex/project-memory.md`
- 关键改动：按最新决策修订阶段方案，明确保留现有 LLM 模型配置功能，但删除 role binding，并且模型配置的执行、连接测试和生产 LLM 调用最终都必须由 AgentScope 实现，不能继续依赖 LiteLLM。后端新增 AgentScope 控制面代理，支持 credential schema、credential CRUD 和 ModelCard 查询，为模型配置保存时同步 AgentScope credential、运行时生成 `chat_model_config` 打基础。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_service_client.py tests/test_agentscope_control_plane_api.py -q` 为 `11 passed, 2 warnings`；执行 `cd datalogue-api && .venv/bin/ruff check app/agentscope_service/client.py app/api/agentscope_control_plane.py app/api/__init__.py tests/test_agentscope_service_client.py tests/test_agentscope_control_plane_api.py` 通过；执行 `cd datalogue-api && .venv/bin/python -m compileall app -q`、`git diff --check` 通过。
- 残留风险：本阶段只完成 AgentScope 控制面代理和总计划修订；模型配置 API 仍需后续移除 role binding、保存时同步 credential，并把 LiteLLM 连接测试和生产调用迁到 AgentScope。

### 2026-07-05 13:51 · 后端模型配置保留并改用 AgentScope 执行

- 涉及文件：`datalogue-api/app/api/llm.py`、`datalogue-api/app/graph/llm.py`、`datalogue-api/app/models/llm.py`、`datalogue-api/app/models/__init__.py`、`datalogue-api/app/schemas/llm.py`、`datalogue-api/app/schemas/__init__.py`、`datalogue-api/app/services/llm_config.py`、`datalogue-api/app/services/subagent_planning/planner.py`、`datalogue-api/tests/test_llm_config.py`、`.codex/project-memory.md`
- 关键改动：保留 `/api/llm/models` 模型配置 CRUD 和连接测试，但删除 `/api/llm/roles`、`/api/llm/role-bindings`、`LLMRoleBinding` ORM/Schema 导出和按角色绑定解析逻辑。新增 `AgentScopeChatClient`，用 AgentScope `OpenAIChatModel`、`DashScopeChatModel`、`DeepSeekChatModel` 等替代 LiteLLM 适配器，连接测试和 `get_llm()` 均通过 AgentScope 执行；历史 `provider=openai-compatible/qwen/deepseek/...` 继续兼容。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_llm_config.py tests/test_agentscope_service_client.py tests/test_agentscope_control_plane_api.py tests/test_agentscope_agent_team_task_runner.py tests/test_agent_team_task_runtime.py -q` 为 `30 passed, 2 warnings`；执行 `cd datalogue-api && .venv/bin/ruff check app/api/llm.py app/graph/llm.py app/services/llm_config.py app/models/llm.py app/models/__init__.py app/schemas/llm.py app/schemas/__init__.py app/services/subagent_planning/planner.py tests/test_llm_config.py` 通过；执行 `cd datalogue-api && .venv/bin/python -m compileall app -q` 通过；执行生产代码扫描 `rg "LLMRoleBinding|llm_role_binding|role-bindings|LiteLLMChatClient|litellm|_litellm" datalogue-api/app -n` 无命中；手动构造 `AgentScopeChatClient._build_model()` 验证 `openai-compatible/qwen/deepseek` provider 均能创建 AgentScope 模型对象。
- 残留风险：数据库中的旧 `llm_role_binding` 表尚未通过 Alembic 删除，前端设置页仍需后续移除 role binding UI；`tests/agentscope_react_mvp/mvp.py` 仍是历史 MVP 样例并包含 LiteLLM，后续最终清理时需要迁移或归档。

### 2026-07-05 13:55 · 前端设置页保留模型配置并移除 Role Binding

- 涉及文件：`datalogue-web/src/components/settings.jsx`、`datalogue-web/src/assistant/MyComposer.jsx`、`datalogue-web/src/assistant-ui/DatalogueComposer.jsx`、`datalogue-web/src/components/chat-page.jsx`、`.codex/project-memory.md`
- 关键改动：设置页继续保留 LLM 模型配置创建、编辑、删除、启停和测试连接入口，但移除 role binding state、加载 `/api/llm/role-bindings`、保存绑定按钮和角色绑定 UI。模型接入模板默认改为 `AgentScope OpenAI-compatible`，删除 LiteLLM preset/provider 文案；聊天模型选择器的默认模型说明改为“后端默认模型配置”，不再提角色绑定。
- 验证方式：执行 `rg "role-bindings|角色绑定|LiteLLM|litellm|litellm_proxy|LLM_ROLES|保存绑定" datalogue-web/src -n` 无命中；执行 `cd datalogue-web && npm run lint` 通过，保留 13 个既有 warning；执行 `cd datalogue-web && npm run build` 通过，保留既有 chunk size warning；执行 `cd datalogue-web && npm test -- src/assistant/chat-adapter.test.js src/assistant/MyMessage.test.jsx src/assistant/agent-team-event-adapter.test.js --run` 为 `3 passed (3), 50 passed (50)`。`src/components/settings.test.jsx` 当前不存在，单独运行会报 No test files found。
- 残留风险：本阶段只完成前端设置页和模型选择文案收口；真实页面仍需后续 smoke 验证模型配置保存、AgentScope credential 同步和 Agent Team 执行链路。

### 2026-07-05 14:02 · 删除 LiteLLM 依赖并迁移旧表

- 涉及文件：`datalogue-api/alembic/versions/v2w3x4y5z6a7_drop_llm_role_binding.py`、`datalogue-api/pyproject.toml`、`datalogue-api/uv.lock`、`datalogue-api/tests/agentscope_react_mvp/mvp.py`、`datalogue-api/app/agentscope_service/client.py`、`datalogue-api/app/api/agentscope_control_plane.py`、`datalogue-api/app/api/llm.py`、`datalogue-api/app/services/llm_config.py`、`.codex/project-memory.md`
- 关键改动：新增 Alembic head `v2w3x4y5z6a7`，upgrade 只删除旧模型角色映射表，保留 `llm_model_config`；downgrade 按旧结构恢复。`pyproject.toml` 移除 `litellm`，`uv lock` 后锁文件移除 LiteLLM 及其间接依赖。历史 AgentScope ReAct MVP 测试样例从自定义 LiteLLM 调用改为继承 AgentScope 原生 `OpenAIChatModel`，继续保留 `llm_request/llm_response` trace。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_llm_config.py tests/test_agentscope_control_plane_api.py tests/test_agentscope_service_client.py tests/agentscope_react_mvp/test_live_react_agent.py::test_capability_manifest_filters_dataset_agent_tools tests/test_agentscope_agent_team_task_runner.py tests/test_agent_team_task_runtime.py -q` 为 `31 passed, 2 warnings`；执行 `cd datalogue-api && .venv/bin/ruff check app/api/llm.py app/graph/llm.py app/services/llm_config.py app/models/llm.py app/models/__init__.py app/schemas/llm.py app/schemas/__init__.py app/services/subagent_planning/planner.py app/agentscope_service/client.py app/api/agentscope_control_plane.py tests/test_llm_config.py tests/agentscope_react_mvp/mvp.py alembic/versions/v2w3x4y5z6a7_drop_llm_role_binding.py` 通过；执行 `cd datalogue-api && .venv/bin/python -m compileall app tests/agentscope_react_mvp alembic/versions/v2w3x4y5z6a7_drop_llm_role_binding.py -q` 通过；执行 `cd datalogue-api && .venv/bin/alembic heads` 返回 `v2w3x4y5z6a7 (head)`；执行 `rg "LiteLLM|litellm|_litellm|litellm_sdk|litellm-sdk" datalogue-api/app datalogue-api/tests datalogue-api/pyproject.toml datalogue-api/uv.lock datalogue-web/src -n` 无命中。
- 残留风险：旧数据库实际升级需要运行 Alembic；本阶段未执行真实页面 smoke，也未实测设置页保存模型配置后 AgentScope credential 同步。

### 2026-07-05 14:12 · AgentScope 模型配置迁移真实 smoke 与本机库升级

- 涉及文件：`.codex/project-memory.md`、`docs/superpowers/plans/2026-07-05-agentscope-service-model-control-plane.md`、已提交的 AgentScope 模型配置与前后端相关改动。
- 关键改动：在本机数据库执行 `alembic stamp u1v2w3x4y5z6 && alembic upgrade head`，把历史已存在但版本号滞后的本地库推进到 `v2w3x4y5z6a7`；确认 `llm_model_config` 表保留，`llm_role_binding` 表删除。真实页面进入 `/settings` 的 `LLM 模型` 页，确认模型配置创建/保存/测试入口仍可见，页面文案为 AgentScope 执行和连接测试，无 `LiteLLM`、`角色绑定` 或 `/api/llm/role-bindings` 入口；`GET /api/llm/models` 返回现有模型配置，`GET /api/llm/role-bindings` 返回 404。
- 真实页面 smoke：桌面 Playwright 访问 `http://localhost:5173/chat`，提交“查询杨凯2025年的工作日志”。页面先展示候选数据集卡，包含“生产经营管理系统日志数据集”“运营双周会议数据集”“生产经营管理系统供应商数据集”；点击“生产经营管理系统日志数据集”后，BI Worker 调用 `datalogue_query_dataset`，页面结果卡显示 `100 行、48 列`，artifact 为 `artifact:e66de692025b4ea0b6787fca821e6487`，点击 Workbench artifact 引用后详情面板打开并显示同一 ref。
- 日志与数据库核验：`logs/app.log` 包含 `[agentscope.bi_worker.dataset_query.completed]`，同一 artifact ref、`dataset_id=10`、`row_count=100`、`column_count=48`；`[datalogue.output]` 的 `message.completed` 也带同一 artifact ref。`GET /api/artifacts/artifact%3Ae66de692025b4ea0b6787fca821e6487` 返回 `kind=sql_result`、`dataset_id=10`、`rows=100`、`columns=48`；数据库 `query_artifact` 表同一记录存在，`kind=sql_result`、`dataset_id=10`、`content_mime=application/json`、`rows=100`、`columns=48`。
- 验证方式：执行服务健康检查 `GET /health` 为 `{"status":"ok"}`；执行生产代码扫描 `rg "LiteLLM|litellm|role-bindings|角色绑定|LLMRoleBinding|llm_role_binding" datalogue-api/app datalogue-web/src -n` 无命中；设置页和聊天页均使用当前本地 8000/5173 服务真实访问。
- 残留风险：本轮只做桌面真实页面 smoke，未补移动视口；本机 Alembic 因历史本地库版本号滞后先 `stamp` 到已存在表对应版本再升级，其他环境应按自身 `alembic_version` 正常 upgrade，不能无脑照搬 stamp。

### 2026-07-05 14:38 · 模型配置密钥迁移到 AgentScope credential

- 涉及文件：`datalogue-api/app/api/llm.py`、`datalogue-api/app/services/llm_config.py`、`datalogue-api/app/api/agentscope_control_plane.py`、`datalogue-api/app/models/llm.py`、`datalogue-api/app/schemas/llm.py`、`datalogue-api/tests/test_llm_config.py`、`datalogue-api/tests/test_agentscope_control_plane_api.py`、`datalogue-web/src/components/settings.jsx`、`.codex/project-memory.md`
- 关键改动：保留现有 LLM 模型配置 CRUD 和设置页体验，但新建/更新模型时 API Key 不再写入 `llm_model_config.api_key_enc`，而是写入稳定命名的 AgentScope `openai_credential`：`datalogue-openai-compatible-model-{config_id}`。历史本地加密 Key 在 `/api/llm/models` 列表读取时按需补注册到 AgentScope credential，成功后清空本地 `api_key_enc`；无 Key 的草稿模型只保存配置投影，不创建空 credential。控制面代理 `/api/agentscope-control/credentials` 增加统一脱敏，响应移除 `api_key` 明文，只保留 `api_key_set`。
- 真实状态核验：本机 `/api/llm/models` 返回两条模型配置，分别指向 `datalogue-openai-compatible-model-1` 和 `datalogue-openai-compatible-model-2`，`api_key_set=true`；`/api/agentscope-control/credentials` 返回 `lead-agent/model-1/model-2` 三条 credential，均只有 `api_key_set=true`、不回传明文 Key；数据库 `LLMModelConfig` 两条历史记录的 `api_key_enc` 均为空。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_llm_config.py tests/test_agentscope_service_client.py tests/test_agentscope_control_plane_api.py tests/test_agentscope_agent_team_task_runner.py tests/test_agent_team_task_runtime.py -q` 为 `32 passed, 2 warnings`；执行 `cd datalogue-api && .venv/bin/ruff check app/api/llm.py app/services/llm_config.py app/schemas/llm.py app/models/llm.py app/api/agentscope_control_plane.py tests/test_llm_config.py tests/test_agentscope_control_plane_api.py` 通过；执行 `cd datalogue-api && .venv/bin/python -m compileall app -q` 通过；执行 `cd datalogue-web && npm run lint` 通过，保留 13 个既有 warning；执行 `cd datalogue-web && npm run build` 通过，保留既有 chunk size warning。
- 残留风险：`llm_model_config` 表仍作为模型配置投影保留，`api_key_enc` 列暂未通过 Alembic 删除，只在运行时迁移后清空并保持兼容；后续若要彻底删除该列，需要新增数据库迁移和环境升级步骤。`resolve_llm_config()` 的同步 credential 读取仍是迁移桥，未来可改为运行时直接传递 AgentScope `credential_id`，减少同步 HTTP 读取。

### 2026-07-05 14:55 · 删除 LLM 模型配置本地密钥列

- 涉及文件：`datalogue-api/alembic/versions/w3x4y5z6a7b8_drop_llm_model_api_key_enc.py`、`datalogue-api/app/api/llm.py`、`datalogue-api/app/services/llm_config.py`、`datalogue-api/app/models/llm.py`、`datalogue-api/tests/test_llm_config.py`、`.codex/project-memory.md`
- 关键改动：新增 Alembic head `w3x4y5z6a7b8` 删除 `llm_model_config.api_key_enc`。迁移在升级前检查是否仍有非空本地密钥，若存在则 fail-closed，要求先通过当前应用把历史密钥迁入 AgentScope credential，避免静默丢失。ORM、模型配置 API、`resolve_llm_config()` 和测试全部移除对本地 LLM 密钥列的读写，运行时只从 AgentScope credential 读取 API Key。
- 真实状态核验：本机执行 `alembic upgrade head` 后当前版本为 `w3x4y5z6a7b8 (head)`；真实 PostgreSQL `llm_model_config` 列清单不再包含 `api_key_enc`；`GET /api/llm/models` 和 `GET /api/llm/models/1` 仍返回 `credential_id` 与 `api_key_set=true`；`GET /api/agentscope-control/credentials` 返回 `lead-agent/model-1/model-2`，均不回传明文 `api_key`。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_llm_config.py tests/test_agentscope_service_client.py tests/test_agentscope_control_plane_api.py tests/test_agentscope_agent_team_task_runner.py tests/test_agent_team_task_runtime.py -q` 为 `31 passed, 2 warnings`；执行 `cd datalogue-api && .venv/bin/ruff check app/api/llm.py app/services/llm_config.py app/models/llm.py tests/test_llm_config.py alembic/versions/w3x4y5z6a7b8_drop_llm_model_api_key_enc.py` 通过；执行 `cd datalogue-api && .venv/bin/python -m compileall app alembic/versions/w3x4y5z6a7b8_drop_llm_model_api_key_enc.py -q` 通过；执行生产路径扫描 `rg "LiteLLM|litellm|role-bindings|角色绑定|LLMRoleBinding|llm_role_binding" datalogue-api/app datalogue-web/src -n` 无命中。
- 残留风险：`llm_model_config` 表本身仍作为 Datalogue 模型配置投影存在，尚未完全迁出到 AgentScope Service model/session 资源；`resolve_llm_config()` 仍有同步读取 AgentScope credential 的过渡桥。下一阶段需要把模型配置元数据和运行时选择继续迁到 AgentScope model/session 控制面，最终删除本地投影表。

### 2026-07-05 14:59 · 聊天模型选择改走 AgentScope credential/model

- 涉及文件：`datalogue-api/app/schemas/agentscope_agent_team_task.py`、`datalogue-api/app/agentscope_service/runner.py`、`datalogue-api/app/agentscope_service/client.py`、`datalogue-api/tests/test_agent_team_task_contracts.py`、`datalogue-api/tests/test_agentscope_agent_team_task_runner.py`、`datalogue-api/tests/test_agentscope_service_client.py`、`datalogue-web/src/api/client.js`、`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/components/chat-page.jsx`、对应前端测试、`.codex/project-memory.md`
- 关键改动：`AgentTeamTaskRequest` 新增 `model_credential_id/model_name/model_parameters`，运行时优先使用 AgentScope credential/model 直接生成 session `chat_model_config`，不再为新路径解析本地 `llm_model_config` 或 upsert 过渡 credential；旧 `model_config_id` 仅作为历史请求兼容。聊天页模型列表改为从 `/api/agentscope-control/credentials` 与 `/api/agentscope-control/model?provider=...` 组合，composer 选择后发送 AgentScope 原生模型资源。AgentScope ModelCard 代理修复 `/model/` 尾斜杠，避免 307 透传到前端。
- 真实状态核验：`GET /api/agentscope-control/credentials` 返回 `datalogue-openai-compatible-lead-agent/model-1/model-2` 等 AgentScope credential，响应只含 `api_key_set` 不含明文 Key；`GET /api/agentscope-control/model?provider=openai_credential` 返回 `o4-mini/gpt-4.1-mini/gpt-4o/gpt-4o-mini/...` ModelCard，状态为 active。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_agentscope_agent_team_task_runner.py tests/test_agent_team_task_contracts.py tests/test_agentscope_service_client.py tests/test_agentscope_control_plane_api.py -q` 为 `22 passed, 2 warnings`；执行 `cd datalogue-api && .venv/bin/ruff check app/agentscope_service/runner.py app/agentscope_service/client.py app/schemas/agentscope_agent_team_task.py tests/test_agentscope_agent_team_task_runner.py tests/test_agent_team_task_contracts.py tests/test_agentscope_service_client.py tests/test_agentscope_control_plane_api.py` 通过；执行 `cd datalogue-web && npm test -- --run src/assistant/chat-adapter.test.js src/components/chat-page.test.jsx` 为 `2 passed (2), 50 passed (50)`；执行 `cd datalogue-web && npm run lint` 通过，保留 13 个既有 warning；执行 `cd datalogue-web && npm run build` 通过，保留既有 chunk size warning；执行 `cd datalogue-api && .venv/bin/python -m compileall app` 通过。
- 残留风险：设置页的 CRUD 仍通过 `/api/llm/models` 维护本地模型配置投影，`llm_model_config` 表尚未删除；下一阶段需要把设置页保存/编辑/删除完全迁到 AgentScope credential/model 资源，并移除 `resolve_llm_config()` 的本地表兼容桥。
