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

## 高价值判断

- Datalogue 当前业务链路不依赖 Redis 保存多轮业务状态；`last_success_task`、`conversation_state.subagent_capsules` 和 query artifacts 的真相在数据库或应用 ArtifactStore 路径，Langfuse/BullMQ Redis key 不能当成业务状态依据。
- 多轮追问不要从当前自然语言残留硬猜 `person`；应依赖 LLM 结构化槽位、上一轮已确认过滤或澄清。
- 数据集上下文压缩优先采用“轻量候选资产目录 + 按需详情补合”，不要一开始把完整字段、SQL、样例行全部塞进 prompt。
- `.env.example` 中要区分“已被 Settings 读取并生效的配置”和“尚未接入的候选项”。
- `localhost:8080` 等地址返回应用层 `Unauthorized` 时，优先判断服务已启动，继续排查认证、代理或路由，不要直接判定服务未启动。

## 最新详细记录

### 2026-07-01 11:48 · AS-R0 PR1.3 DatasetAgent tool-call runtime

- 涉及文件：`datalogue-api/app/services/agentic_dataset_runtime.py`、`datalogue-api/tests/test_agentic_dataset_runtime.py`、`docs/superpowers/plans/2026-07-01-as-r0-agentic-shell-formal-pr-plan.md`、`docs/test-reports/2026-07-01-as-r0-pr1-3.md`、`.codex/project-memory.md`
- 关键改动：新增 `DatasetAgentToolCallRuntime`，固定串联 `get_dataset_status -> list_candidate_assets -> generate_dsl -> compile_dsl_to_sql -> execute_compiled_query -> get_artifact_summary`；DSL generator 通过注入提供结构化 `QueryPlan` 或 dict，后续可替换为真实 DatasetAgent DSL planner；Runtime 不新增 `plan_bi_query` 黑盒。
- 安全边界：SQL 只在 `BIAtomicToolProvider` private compiled handle 和 execute 工具内部流转；execute 结果写入 ArtifactStore，Runtime 用户/Agent 可见响应只含 artifact ref、row/column count、artifact summary 和清洗后的 tool call 状态，不回传 SQL、schema、raw rows、query_plan、RepairPatch、blueprint body、物理表字段或结果行。
- TDD 记录：先新增 PR1.3 runtime 测试并确认 RED 为缺少 `app.services.agentic_dataset_runtime`；实现最小编排后转 GREEN，覆盖成功链路和 compile 失败不调用 execute。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_agentic_dataset_runtime.py -q`，2 条通过、2 个既有 warning；执行 AS-R0 最小回归 `tests/test_agentic_dataset_runtime.py tests/test_agentic_shell_contract.py tests/test_agentscope_runtime_driver_contract.py tests/test_agentscope_chat_bridge.py tests/test_agentscope_shell_adapter.py tests/test_bi_workbench_tool.py -q`，40 条通过、4 个既有 warning；执行安全矩阵回归 `tests/test_as_r0_security_matrix.py tests/test_event_envelope.py -q`，11 条通过、2 个既有 warning；`py_compile` 和 `git diff --check` 通过。
- 残留风险：PR1.3 尚未把 `/chat/stream` 最终灰度切到新 DatasetAgent runtime；checkpoint/retry writer 迁移和双路径 parity 分别留给 PR1.4、PR1.5。

### 2026-07-01 11:48 · AS-R0 PR1.4 checkpoint/retry 迁移

- 涉及文件：`datalogue-api/app/services/agentic_shell_writers.py`、`datalogue-api/app/services/workbench_actions.py`、`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_agentic_shell_retry_writer.py`、`docs/superpowers/plans/2026-07-01-as-r0-agentic-shell-formal-pr-plan.md`、`docs/test-reports/2026-07-01-as-r0-pr1-4.md`、`.codex/project-memory.md`
- 关键改动：新增 `AgentScopeMirrorShellWriter`，Workbench retry request 改为通过 `DatalogueAgenticShell.record_action()` 写入 `workbench.retry_requested`；Chat SSE event projection 改为先经 `DatalogueAgenticShell.record_event()` 清洗，再由 writer 调用既有 `record_stream_event()` 投影到 AgentScope mirror。
- 安全边界：Shell writer 只桥接 event/action/checkpoint 写回，不执行 BI 查询；`retry.started`、`retry.checkpoint_restored`、`dataset.query.completed`、`answer.completed` 等事件沿用原 envelope/Workbench projection，写回前继续阻断 SQL、schema、raw rows、query_plan 和内部执行载荷。
- TDD 记录：先新增 PR1.4 writer 测试并确认 RED 为 Workbench action 没有 Shell 接入点、Chat SSE projection 没有调用 Shell `record_event()`；接入 writer 后转 GREEN。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_agentic_shell_retry_writer.py -q`，2 条通过、2 个既有 warning；执行 `tests/test_agentic_shell_retry_writer.py tests/test_workbench_retry_actions.py tests/test_c3_workbench_acceptance.py -q`，13 条通过、10 个既有 warning；执行 observability/retry checkpoint 回归 4 条通过、6 个既有 warning；提交前 AS-R0 最小回归 42 条通过、4 个既有 warning，Workbench/observability/retry 回归 15 条通过、14 个既有 warning；`py_compile` 和 `git diff --check` 通过。
- 残留风险：PR1.4 完成 writer ownership 迁移，但新 Shell runtime 与 legacy direct stream 的 final payload/artifact refs/trace contract parity 仍留给 PR1.5。

### 2026-07-01 11:48 · AS-R0 PR1.5 双路径灰度 parity

- 涉及文件：`datalogue-api/tests/test_agentscope_chat_bridge.py`、`docs/superpowers/plans/2026-07-01-as-r0-agentic-shell-formal-pr-plan.md`、`docs/test-reports/2026-07-01-as-r0-pr1-5.md`、`.codex/project-memory.md`
- 关键改动：新增 `AS_R0_AGENTIC_RUNTIME_ENABLED=false/true` 双路径 parity harness，用同一 `_stream_chat` 请求验证 Shell runtime wrapper 与 legacy path 输出同一 final payload、同一 artifact refs 和同一 trace contract。
- 安全边界：PR1.5 不默认开启新 runtime，不替换 DatasetAgent 主链，不把 P2 legacy 收敛提前；只把 PR1.1 已有 wrapper 行为固化为正式灰度验收闸门。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_agentscope_chat_bridge.py::test_agentic_runtime_flag_preserves_legacy_final_payload_refs_and_trace_contract -q`，1 条通过、2 个既有 warning；执行 AS-R0/chat 回归 `tests/test_agentscope_chat_bridge.py tests/test_agentic_shell_contract.py tests/test_agentscope_runtime_driver_contract.py tests/test_as_r0_security_matrix.py tests/test_event_envelope.py -q`，45 条通过、4 个既有 warning；`py_compile` 和 `git diff --check` 通过。
- 残留风险：P1 已完成；下一步 P2.1 要把 `_stream_chat` 收缩为 transport adapter，并把业务 turn lifecycle 从 `chat.py` 迁出。

### 2026-07-01 11:48 · AS-R0 P2.1 `/chat/stream` transport adapter 收缩

- 涉及文件：`datalogue-api/app/services/agentic_chat_runtime.py`、`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_agentscope_chat_bridge.py`、`docs/superpowers/plans/2026-07-01-as-r0-agentic-shell-formal-pr-plan.md`、`docs/test-reports/2026-07-01-as-r0-p2-1.md`、`.codex/project-memory.md`
- 关键改动：新增 `DatalogueChatStreamRuntime` 和 `DatalogueChatStreamRuntimeHooks`，把 `_stream_chat` 的单轮/多轮 wrapper lifecycle 迁出 `chat.py`；`chat.py` 现在只负责 settings、hook 装配和 SSE event 转发。
- 安全边界：P2.1 不改 DatasetAgent 主链，不改用户可见 SSE payload，不处理 legacy `AgentScopeShellAdapter + ask_bi`；现有 mirror/retry/checkpoint/conversation state/observability helper 均通过 hooks 复用。
- TDD 记录：先新增 transport adapter 委托测试并确认 RED 为 `app.api.chat` 缺少 `DatalogueChatStreamRuntime`；实现 service 后转 GREEN；回归发现 final 重复 yield 后修复为只输出补 thread_id 后的 final，同时保留 retry 终态前置事件顺序。
- 验证方式：adapter 定向测试 1 条通过、2 个既有 warning；AS-R0/chat 回归 46 条通过、4 个既有 warning；Workbench/retry/observability 回归 15 条通过、14 个既有 warning；`py_compile` 和 `git diff --check` 通过。
- 残留风险：P2.2 要继续收敛 `AgentScopeShellAdapter + BIWorkbenchTool(ask_bi)` legacy compatibility，不能让旧 adapter 继续拥有业务 runtime ownership。

### 2026-07-01 11:48 · AS-R0 P2.2 legacy adapter / ask_bi compatibility 收敛

- 涉及文件：`datalogue-api/app/services/agentscope_shell_adapter.py`、`datalogue-api/app/services/bi_workbench_tool.py`、`datalogue-api/app/services/soul_contract_sync.py`、`datalogue-api/app/contracts/BI_SOUL.md`、`hermes-skills/datalogue/SOUL.md`、`datalogue-api/tests/test_agentscope_shell_adapter.py`、`datalogue-api/tests/test_bi_workbench_tool.py`、`datalogue-api/tests/test_bi_soul_contract.py`、`docs/superpowers/plans/2026-07-01-as-r0-agentic-shell-formal-pr-plan.md`、`docs/test-reports/2026-07-01-as-r0-p2-2.md`、`.codex/project-memory.md`
- 关键改动：`AgentScopeShellAdapter` 与 `BIWorkbenchTool` 新增 compatibility contract，显式声明 `compatibility_mode=legacy_compatibility`、`runtime_owner=datalogue_agentic_shell`、`owns_business_runtime=false`。
- 安全边界：legacy `ask_bi` 不再作为 AS-R0 新主链工具，不加回 BI atomic tool whitelist；BI_SOUL、Hermes SOUL 和 AgentScope policy renderer 同步改为 legacy compatibility 口径。
- TDD 记录：先新增 adapter/tool compatibility contract 测试并确认 RED 为缺少 `compatibility_contract()`；实现 contract 后转 GREEN，并同步更新 BI_SOUL 同步测试。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_agentscope_shell_adapter.py tests/test_bi_workbench_tool.py tests/test_bi_soul_contract.py tests/test_agentscope_runtime_driver_contract.py -q`，14 条通过、2 个既有 warning；AS-R0 最小回归 42 条通过、4 个既有 warning；`py_compile` 和 `git diff --check` 通过。
- 残留风险：P2.3 要接入 future tools disabled/admin-gated contract，避免 repair/report/python 类工具被 Runtime 误执行。

### 2026-07-01 11:48 · AS-R0 P2.3 future tools disabled/admin-gated contract

- 涉及文件：`datalogue-api/app/services/agentic_shell.py`、`datalogue-api/app/services/agentscope_runtime_driver.py`、`datalogue-api/tests/test_agentic_shell_contract.py`、`datalogue-api/tests/test_agentscope_runtime_driver_contract.py`、`docs/superpowers/plans/2026-07-01-as-r0-agentic-shell-formal-pr-plan.md`、`docs/test-reports/2026-07-01-as-r0-p2-3.md`、`.codex/project-memory.md`
- 关键改动：新增 `AgenticDisabledToolSpec`，`AgenticToolPolicy` 和 `AgentScopeRuntimeBoundaryContract` 均透传 future tools 的结构化 disabled/admin-gated 状态。
- 安全边界：`repair_dsl`、`create_report_from_artifact`、`run_sandboxed_analysis_on_artifact` 默认 `admin_gated/admin_only`；`classify_query_failure` 默认 `disabled/not_enabled`；这些工具不进入 Runtime executable `tool_registry`。
- TDD 记录：先新增 Shell/Runtime future tool contract 测试并确认 RED 为缺少 `disabled_tool_specs`；实现结构化 spec 和 Runtime 透传后转 GREEN。
- 验证方式：future tool 定向测试 2 条通过、2 个既有 warning；Shell/Runtime 契约回归 18 条通过、2 个既有 warning；AS-R0 最小回归 47 条通过、4 个既有 warning；`py_compile` 和 `git diff --check` 通过。
- 残留风险：P2.4 要为 ReportAgent/PythonAgent/AuditAgent 做单独 enablement gate、单独白名单和单独验收。

### 2026-07-01 12:43 · AS-R0 P2.4 业务 Agent 受控启用

- 涉及文件：`datalogue-api/app/services/agentic_shell.py`、`datalogue-api/app/services/agentscope_runtime_driver.py`、`datalogue-api/tests/test_agentic_shell_contract.py`、`datalogue-api/tests/test_agentscope_runtime_driver_contract.py`、`docs/superpowers/plans/2026-07-01-as-r0-agentic-shell-formal-pr-plan.md`、`docs/test-reports/2026-07-01-as-r0-p2-4.md`、`.codex/project-memory.md`
- 关键改动：`DatalogueAgenticShell` 新增 `enabled_optional_agents` 受控启用入口；ReportAgent、PythonAgent、AuditAgent 默认仍是 disabled placeholder，显式启用时分别只开放 `create_report_from_artifact`、`run_sandboxed_analysis_on_artifact`、`classify_query_failure` 单一白名单；Runtime driver 只注册已启用 optional agent 的对应 tool spec。
- 安全边界：未知 optional agent 配置 fail-closed；单个业务 Agent 启用不会连带启用其他 Agent 或 future tools；context projection 继续阻断 SQL、schema、raw rows、query_plan、RepairPatch、blueprint body 等禁区内容；P2.4 不实现真实业务执行器、不改变 `/chat/stream` 默认主链。
- TDD 记录：先补三个 Shell enablement gate 测试和一个 Runtime registry 测试，确认 RED 为 `DatalogueAgenticShell.__init__()` 不支持 `enabled_optional_agents`；实现 registry gate、单 Agent whitelist 和 disabled spec 过滤后转 GREEN。
- 验证方式：P2.4 定向测试 4 条通过、2 个既有 warning；Shell/Runtime 契约回归 22 条通过、2 个既有 warning；AS-R0 核心回归 51 条通过、4 个既有 warning；Workbench/retry/observability 回归 15 条通过、14 个既有 warning；`py_compile` 和 `git diff --check` 通过。
- 残留风险：AS-R0 P0/P1/P2 正式计划已完成；后续真实 Report/Python/Audit Agent 业务执行器或多数据集 fanout 迁出 legacy 需要新增已批准计划。

### 2026-07-01 15:15 · AS-R0 PR1.3-b BI atomic runtime 直接接管执行核心

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/app/core/config.py`、`datalogue-api/app/services/agentic_dataset_runtime.py`、`datalogue-api/tests/test_agentic_dataset_runtime.py`、`datalogue-api/tests/test_as_r0_atomic_runtime_cutover.py`、`datalogue-api/tests/test_agentscope_chat_bridge.py`、`docs/superpowers/plans/2026-07-01-as-r0-agentic-shell-formal-pr-plan.md`、`docs/test-reports/2026-07-01-as-r0-pr1-3-b.md`、`.codex/project-memory.md`
- 关键改动：正式计划追加已批准的 PR1.3-b，用于补齐 PR1.3 只建 runtime、不接 `/chat/stream` 执行核心的验收缺口；按用户新要求删除 `AS_R0_AGENTIC_RUNTIME_ENABLED` 与 `AS_R0_DATASET_ATOMIC_RUNTIME_ENABLED` 两个主链灰度开关，`/chat/stream` singleturn 默认进入 `DatalogueAgenticShell.run_turn()`，单数据集 BI 查询默认绕过 legacy `build_workflow(db)`，改用 `DatasetAgentToolCallRuntime + BIAtomicToolProvider` 串起 DSL compile、execute、artifact summary 和 final payload；同时新增 `DatasetAgentToolCallSession`、`DatasetAgentNextToolCall` 和 `handle_agent_tool_call()`，以 AgentScope 2.0 external tool event 模型承载“Agent 提出下一步 tool call，Datalogue Runtime 受控执行并回填结果”；后端日志改为 `dataset_agent.runtime.start/tool/result` 和 `chat.stream.dataset_agent_runtime_start/completed`，不再用 LangGraph / DatasetSubAgent 口径描述当前主链。
- 安全边界：DatasetAgent 仍只能生成 DSL，SQL 只在 compile/execute tool 内部通过私有 handle 流转；compile 给 Agent 的可见响应只包含 `compiled_query_ref`，execute 只能接受同一会话内 compile 产生的 handle；Runtime fail-closed 校验工具白名单、固定调用顺序和敏感参数，明确阻断 SQL、sql_list、sql_result、schema、raw rows、query_plan、RepairPatch、blueprint body、物理字段明细进入 Agent context、SSE 用户可见层和 Workbench refs。
- TDD 记录：先把 cutover 测试改为无 flag 场景并让 `build_workflow(db)` 抛错，确认 RED 暴露 `/chat/stream` 仍因开关缺失落回 legacy graph；再为 Agent next tool call、白名单、顺序、敏感参数和 forged compiled ref 增加 RED 测试；实现去灰度默认分支、受控会话状态机和 handle 绑定后转 GREEN；同步把 AgentScope chat bridge parity 测试从 flag on/off 改成无 flag 默认 Shell wrapper。
- 验证方式：`cd datalogue-api && python3 -m pytest tests/test_agentic_dataset_runtime.py -q`，7 条通过、2 个既有 warning；`tests/test_as_r0_atomic_runtime_cutover.py` 1 条通过、2 个既有 warning；AS-R0 核心回归 `tests/test_agentic_dataset_runtime.py tests/test_as_r0_atomic_runtime_cutover.py tests/test_agentscope_chat_bridge.py tests/test_agentic_shell_contract.py tests/test_as_r0_security_matrix.py` 共 46 条通过、4 个既有 warning；`python3 -m compileall -q app/services/agentic_dataset_runtime.py app/api/chat.py app/core/config.py` 和 `git diff --check` 通过；去灰度后真实 `/api/chat/stream` 返回 `Atomic runtime 查询完成，共返回 0 行、0 列。`，Workbench mirror 线程 `as_b54341d8-2a07-4077-a514-3564a53910df` 状态为 completed，timeline 为 `dataset.selected -> dataset.query.completed -> answer.completed`，SSE/Workbench/后端日志扫描未命中 SQL/raw_rows/query_plan 等禁词。
- 残留风险：多数据集 fanout 当前仍有 legacy `build_workflow(db)` 分支；`/chat/49` 右侧 Workbench Panel 按 `conv_49` 旧会话只读显示，`as_*` completed 状态通过 Workbench API 验证；`tests/test_bi_main_chain_acceptance.py` 中 2 条旧验收仍要求内部 `query_plan` 节点可见，和当前 provider-neutral/user-visible 安全口径存在存量漂移，未在本刀中改写。

### 2026-07-01 15:32 · DatasetAgent Runtime 直通测试入口

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_as_r0_atomic_runtime_cutover.py`、`.codex/project-memory.md`
- 关键改动：新增 `POST /api/chat/dataset-runtime/direct`，本地/测试环境可用 `question + dataset_id` 直接调用 `DatasetAgentToolCallRuntime + BIAtomicToolProvider`；入口构造最小 `routing/route_decision/lead_agent_context`，不调用 `build_lead_agent_context`、`route_query_intent` 或 legacy `build_workflow(db)`，用于单独压测 DatasetAgent Runtime 底座。
- 安全边界：direct 入口在 `APP_ENV=production` 时返回 403；`dataset_id` 缺失返回 400，数据集不存在返回 404；仍复用 atomic runtime 的 SQL private handle、artifact ref 和输出清洗，不把 SQL/schema/raw rows/query_plan 暴露给调用方。
- TDD 记录：先新增 `test_dataset_runtime_direct_entry_bypasses_lead_agent_and_legacy_graph`，确认 RED 为 `app.api.chat` 缺少 `dataset_runtime_direct`；实现 direct endpoint 后转 GREEN。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_as_r0_atomic_runtime_cutover.py::test_dataset_runtime_direct_entry_bypasses_lead_agent_and_legacy_graph -q`，1 条通过、2 个既有 warning；执行 `python3 -m compileall -q app/api/chat.py tests/test_as_r0_atomic_runtime_cutover.py` 通过。
- 残留风险：direct 入口只是测试底座，不代表 `/chat/stream` 前置 LeadAgent 控制面已完全移除；当前 direct runtime 的 DSL generator 仍复用现有 `recall_candidate_assets + plan_query`，后续需要替换成真正 DatasetAgent-owned planner。整组 `tests/test_as_r0_atomic_runtime_cutover.py` 中既有 `/chat/stream` 测试在 observability disabled 时仍因 `trace_id` 为 `null` 断言失败，本次未扩大范围改写。

### 2026-07-01 15:45 · 移除 Langfuse 技术栈并暂时关闭 Trace

- 涉及文件：`datalogue-api/app/services/observability/tracer.py`、`datalogue-api/app/services/observability/prompts.py`、`datalogue-api/app/services/observability/feedback.py`、`datalogue-api/app/services/observability/traces.py`、`datalogue-api/app/api/__init__.py`、`datalogue-api/app/api/conversation.py`、`datalogue-api/app/core/config.py`、`datalogue-api/docker-compose.yml`、`datalogue-api/.env.example`、`datalogue-api/pyproject.toml`、`datalogue-api/requirements.txt`、`datalogue-api/uv.lock`、`datalogue-web/src/App.jsx`、`datalogue-web/src/api/client.js`、`datalogue-web/src/assistant/MyMessage.jsx`、`datalogue-web/src/components/agent-panel.jsx`、`datalogue-web/src/components/sidebar.jsx`、`datalogue-api/tests/test_remove_langfuse_stack.py`、`datalogue-api/tests/test_observability.py`、`datalogue-api/tests/test_conversation.py`、`docs/superpowers/plans/2026-07-01-remove-langfuse-stack.md`、`.codex/project-memory.md`
- 关键改动：删除 Langfuse Python 依赖、锁文件依赖、Docker Compose 服务、初始化脚本、seed prompt 脚本和 `.env.example` 配置；`DatalogueTracer` 改为本地 no-op 兼容壳，不分配 trace_id、不 flush、不 score、不生成 trace_url；PromptManager 只使用本地 fallback prompt；feedback 不再向外部观测系统同步；`/api/observability/*` 不再挂载；前端移除查询审计入口、Trace 面板入口和 trace link 卡片。
- 安全边界：本次不引入 provider-neutral Trace 替代实现；历史 metadata 中已有的 `trace_id/session_id` 只作为旧记录公开索引保留，不再拼外部跳转地址；运行时代码、依赖、部署和前端源码扫描不再包含 `langfuse` 字符串。
- TDD 记录：先新增 `test_runtime_stack_has_no_langfuse_references`，确认活动运行时/依赖/部署仍有 Langfuse 残留后 RED；移除依赖、配置、服务、API 挂载和前端入口后转 GREEN，并同步调整 observability/conversation 测试为 no Trace 语义。
- 验证方式：`python3 -m pytest tests/test_remove_langfuse_stack.py tests/test_observability.py tests/test_conversation.py -q`，21 条通过、8 个既有 warning；`python3 -m compileall -q app` 通过；`npm run lint` 通过但保留 13 个既有 warning；`npm run build` 通过并保留 Vite chunk size warning；活动运行时/依赖/部署/前端源码 `rg -i langfuse` 无命中。
- 残留风险：历史文档、项目记忆和旧迁移文件仍记录 Langfuse 作为历史事实，不属于运行时调用链；`tests/test_bi_main_chain_acceptance.py` 仍受 AS-R0 atomic runtime 接管和 trace index 下线影响失败，需另起任务重写旧五件套验收口径。
