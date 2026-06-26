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
- 新对话本地草稿体验修正：新建对话未发送时只保留 assistant-ui 本地草稿，不新增数据库 conversation；首条消息发送时再由 thread-list adapter 创建后端会话，并通过组件测试、lint/build 和真实会话数量检查验证。
- 生成面向业务用户和项目负责人的数语项目整体介绍手册，弱化内部代码细节，说明已具备功能、业务问题、典型场景、使用流程、边界和可交付内容，并通过 DOCX 渲染抽查验证版式。
- Hermes Skill 直连数语只读问数预览：新增 `POST /api/dataset/{ds_id}/sql/preview` 和 `api_assets.py plan-query/execute-sql`，按 dataset datasource、已选表、只读 SQL Guard 和查询约束执行 preview，不进入 `/api/chat/stream`，并用 dataset 12 live SQL 与 DELETE 拦截验证。

### 2026-06-24

- 生成当前项目工作总结与下步计划文档，面向项目负责人、业务使用方和产品/研发协作人员说明整体建设思路、已完成任务、成果截图、当前成熟度判断、下步计划和真实链路验收口径；复用既有用户手册截图和执行链路图，并通过图片存在性检查和 `git diff --check` 验证。
- 工作总结文档从功能点表格改为逐项展开说明，补充每项能力解决的问题、设计思路、当前效果和验收关注点，提升非研发读者可读性。
- 补齐工作总结文档中 27 个已完成功能点对应截图，将截图从集中展示改为跟随功能点展示，并通过图片引用存在性和 `git diff --check` 验证。
- 生成工作总结 Word 增强版，补充数语智能问数执行链路说明图、功能点截图和 ECharts 报表生成、多租户、权限管理体系等后续计划，并通过 DOCX 图片数量与 LibreOffice 渲染抽查验证。
- 将工作总结 Word 截图替换为 2026-06-24 本地运行态截图，重新截取工作台、问数中心、查询审计、数据集治理、数据源 Schema、API 管理、系统设置等页面，生成最新截图版并通过 DOCX 图片数量和 LibreOffice 渲染抽查验证。
- 将工作总结 Word 的执行链路图拆分为总体图、LeadAgent、Dataset SubAgent、QueryGraph/SubGraph、Trace 观测等独立链路图，避免多个功能点复用同一张大图；新版 DOCX 渲染为 36 页并抽查关键页无明显裁剪、重叠或错图。

### 2026-06-25

- AgentScope 2.0 ReAct MVP 真实请求验证：新增独立真实集成测试目录，用 AgentScope 2.0 Agent/Toolkit/ToolBase 封装数语最小工具面，真实调用数据集资产和 guarded SQL preview，不进入 `/api/chat/stream`，并通过 live API、默认跳过测试、真实开关测试、py_compile 和 `git diff --check` 验证。
- AgentScope 真实测试过程日志增强：补充 LLM 配置、工具 HTTP 请求、Plan/Execute 摘要、SQL preview、最终回答和动态数据集选择日志，支持 `pytest -s` 查看完整执行过程。
- AgentScope Hermes-style DatasetAgent MVP：加载 Hermes SOUL/SKILL/capabilities 生成 AgentScope system prompt，用最小工具面验证 DatasetAgent 可通过 guarded SQL preview 自主查数，保留正式 artifact store、trace 和 `/chat/stream` 产品化为后续工作。
- 项目文档多目录治理：将 `docs/` 根目录混放材料迁移到 product/architecture/observability/deliverables/assets/archive 等目录，保留 `docs/上下文入口.md` 和 `docs/README.md` 作为导航，并通过图片/链接和 `git diff --check` 验证。
- Obsidian 智能问数长期知识沉淀：新增受约束 Agent 架构、语义治理与执行安全、真实链路验收方法三篇知识库方法论，沉淀 Capability Manifest、Manifest fail-closed、QueryArtifact/result_ref 和五件套验收原则。

### 2026-06-26

- Multica Datalogue 员工智能体创建与技能绑定：创建 datalogue skill、上传 SOUL/capabilities/API assets，并配置数据问数分析师、后端、前端、QA、文档等员工智能体及 CEO skill。
- Multica 数语智能问数小队创建：创建 `数语智能问数小队`，leader 设为 CEO，将 Datalogue 数据问数、后端、前端、QA、文档等成员加入 roster，并明确小队由 leader 分派而非自动 fan-out。
- C 产品形态优先且 BI 内核 B-governed 工作规划：沉淀 B-first C-ready 决策总览、任务清单、AgentScope 2.0 集成系统设计和二十余条能力路由/Artifact/ask_bi/旧会话边界决策。
- 默认测试套件稳定性修复：恢复 AgentScope live 集成测试显式开关，更新 intent 角色 LLM `max_tokens` 断言，默认后端全量 pytest 和前端 lint/test/build 通过，仅保留既有 warning 与 ruff 历史问题。
- B-first C-ready 计划细化与 Obsidian 同步：拆分后续改造记录、正式开发计划、决策总览和 AgentScope 2.0 集成系统设计，明确 P0/P1/P2 与五件套验收口径。
- Multica 开发测试并行员工扩编：为数语小队新增 LeadAgent、数据治理 SQL、前端工作台、后端回归、前端 E2E、观测链路等 6 个并行员工角色，并验证 squad roster。
- BI_SOUL 内部契约与 Hermes SOUL 同步校验：新增 BI 不可越界 source of truth、同步服务和测试，明确外层 Agent 只能调用 `ask_bi`，raw SQL/raw result/capsule 属于控制面。
- DAT-15 数据集能力清单：新增 `CapabilityManifest` / `CapabilityManifestSummary`、业务级泄露扫描和 `GET /api/dataset/{dataset_id}/capability-manifest` 调试接口，为 LeadAgent Capability Router 提供真实 manifest summary 依赖。

## 高价值判断

- Datalogue 当前业务链路不依赖 Redis 保存多轮业务状态；`last_success_task`、`conversation_state.subagent_capsules` 和 query artifacts 的真相在数据库或应用 ArtifactStore 路径，Langfuse/BullMQ Redis key 不能当成业务状态依据。
- 多轮追问不要从当前自然语言残留硬猜 `person`；应依赖 LLM 结构化槽位、上一轮已确认过滤或澄清。
- 数据集上下文压缩优先采用“轻量候选资产目录 + 按需详情补合”，不要一开始把完整字段、SQL、样例行全部塞进 prompt。
- `.env.example` 中要区分“已被 Settings 读取并生效的配置”和“尚未接入的候选项”。
- `localhost:8080` 等地址返回应用层 `Unauthorized` 时，优先判断服务已启动，继续排查认证、代理或路由，不要直接判定服务未启动。

## 最新详细记录

### 2026-06-26 19:18 · DAT-13 LeadAgent Capability Router 对齐能力清单

- 涉及文件：`datalogue-api/app/services/dataset_router.py`、`datalogue-api/app/services/capability_manifest.py`、`datalogue-api/app/services/conversation_store.py`、`datalogue-api/app/api/chat.py`、`datalogue-api/app/services/lead_agent_routing.py`、`datalogue-api/tests/test_lead_agent_capability_router.py`、`datalogue-api/tests/test_chat.py`、`.omx/plans/DAT-13-leadagent-capability-router.md`、`.codex/project-memory.md`
- 关键改动：将数据集自动路由候选来源改为 `list_capability_manifest_summaries()`，只用业务能力、典型问题、指标/维度名称摘要和路由提示打分，Manifest 表仅用于 current 资格和版本三元组；低置信和 close-score 路径只返回候选数据集，不派发 DatasetAgent；候选输出保持 `dataset_id/dataset_name/reason/confidence/requires_confirmation` 五个业务级字段；Chat 状态写回增加 dataset 确认事实，用户提交 `candidate_id/checkpoint_ref` 后写入 `conversation_state.facts` 的 `confirmed_dataset_id` 和 `retry_checkpoint`，不新增旧会话迁移。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_lead_agent_capability_router.py tests/test_lead_agent_routing.py tests/test_chat.py -q`，138 条用例通过；执行 `cd datalogue-api && python3 -m py_compile app/services/dataset_router.py app/services/capability_manifest.py app/services/conversation_store.py app/api/chat.py app/services/lead_agent_routing.py` 通过；执行 `git diff --check` 通过。
- 残留风险：前端候选确认卡和 event envelope 中的标准化 candidate confirmation 事件仍属于 DAT-16；当前后端状态兼容写在 `facts` JSON 中，后续若要强查询能力可再引入显式列或结构化 state schema。

### 2026-06-26 19:22 · DAT-9 QueryGraph Compiler 方言边界收窄

- 涉及文件：`datalogue-api/app/services/query_plan_compiler.py`、`datalogue-api/app/services/sql_dialect_adapter.py`、`datalogue-api/app/services/dataset_subagent.py`、`datalogue-api/app/graph/nodes.py`、`datalogue-api/app/graph/state.py`、`datalogue-api/app/services/subagent_planning/`、`datalogue-api/tests/test_query_plan_compiler.py`、`datalogue-api/tests/test_sql_dialect_adapter.py`、`datalogue-api/tests/test_subagent_run.py`、`.codex/project-memory.md`
- 关键改动：合入 QueryPlan Compiler 外壳，将 DatasetAgent 内部 `QueryPlan` 编译为 `tool_compiler` 来源 SQL，并把 SQL 只写入 control_plane / query_artifact / trace；保留 `llm_sql/direct_sql/raw_sql/sql` 执行来源检测，命中即 fail closed；将 SQL Dialect Adapter 从静态多方言允许改为当前真实数据源 dialect 单值门禁，QueryPlan 目标方言和当前数据源不一致时返回 `DIALECT_UNSUPPORTED_FOR_CURRENT_DATASOURCE`；DatasetSubAgent 调用处显式传入 `datasource_context.dialect/db_type` 作为当前数据源方言。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_query_plan_compiler.py tests/test_sql_dialect_adapter.py tests/test_subagent_run.py -q`，23 条用例通过；执行 `cd datalogue-api && python3 -m py_compile app/services/query_plan_compiler.py app/services/sql_dialect_adapter.py app/services/dataset_subagent.py app/graph/nodes.py app/graph/state.py` 通过。
- 残留风险：当前 compiler 仍是外壳实现，内部 SELECT 生成能力只覆盖已水合字段资产和少量 schema fallback；完整 QueryGraph/DSL 语义编译替换、更多真实数据源方言支持和多方言矩阵测试属于后续阶段。

### 2026-06-26 19:23 · DAT-8 SubAgent ToolAdapter 三层输出

- 涉及文件：`datalogue-api/app/services/subagent_tool_adapter.py`、`datalogue-api/tests/test_subagent_tool_adapter.py`、`.omx/plans/2026-06-26-p0-4-subagent-tool-adapter-three-layer.md`、`.codex/project-memory.md`
- 关键改动：合入 SubAgent ToolAdapter 三层输出改造，区分 `llm_visible`、`control_plane` 和 `external_artifact`，将大结果、raw SQL、trace 主体等敏感或重载内容限制在控制面/产物面，面向 LLM 的工具输出保持摘要化和低泄露风险。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_subagent_tool_adapter.py -q`，10 条用例通过；执行 `cd datalogue-api && python3 -m py_compile app/services/subagent_tool_adapter.py` 通过。
- 残留风险：当前验证覆盖 ToolAdapter 契约本身；后续 #7 event envelope、#8 ask_bi、Artifact refs 和前端承接还需要继续确保三层输出不会被重新混入用户可见 SSE。

### 2026-06-26 19:25 · DAT-5 SSE Event Envelope 标准化

- 涉及文件：`datalogue-api/app/schemas/bi_workbench.py`、`datalogue-api/app/schemas/__init__.py`、`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_event_envelope.py`、`datalogue-api/tests/test_chat.py`、`.omx/plans/DAT-5-event-envelope-plan.md`、`.codex/project-memory.md`
- 关键改动：合入 `DatalogueEventEnvelope`，为 SSE 输出补统一 envelope 结构，保留 legacy 顶层字段兼容；Chat 流式事件可以同时携带 `event_envelope` 和既有 payload，给后续 AgentScope event adapter 与前端 C-ready timeline 留出口。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_event_envelope.py tests/test_chat.py -q`，121 条用例通过；执行 `cd datalogue-api && python3 -m py_compile app/schemas/bi_workbench.py app/schemas/__init__.py app/api/chat.py` 通过。
- 残留风险：当前只是标准化 envelope，不替换 SSE 主协议；前端 `chat-adapter.js` 解析 envelope、AgentScope event stream adapter 和五件套真实链路验收仍需后续 DAT-16/DAT-18 收口。

### 2026-06-26 19:28 · DAT-4 ask_bi 外层工具契约

- 涉及文件：`datalogue-api/app/schemas/bi_workbench.py`、`datalogue-api/app/schemas/__init__.py`、`datalogue-api/app/services/bi_workbench_tool.py`、`datalogue-api/tests/test_bi_workbench_tool.py`、`.codex/project-memory.md`
- 关键改动：合入 `AskBIRequest`、`AskBIResponse`、`ArtifactRef`、`ArtifactAction` 和 `ArtifactCard`，新增 `ask_bi` 外层工具入口，把现有 Chat 主链流式结果转成 C-ready 外层响应；解决 `bi_workbench.py` add/add 冲突，保留 #7 的 `DatalogueEventEnvelope`、事件类型、可见性、sanitize 和 builder，同时保留 #8 的 ask_bi / Artifact 契约；用户可见响应继续 fail closed 阻断 raw SQL、schema、capsule、control_plane 和 raw result。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_bi_workbench_tool.py tests/test_event_envelope.py -q`，5 条用例通过；执行 `cd datalogue-api && python3 -m py_compile app/schemas/bi_workbench.py app/services/bi_workbench_tool.py app/schemas/__init__.py` 通过。
- 残留风险：`ask_bi` 目前是外层工具契约和 Chat 转接封装，尚未由 AgentScopeShellAdapter 或前端独立工作台实际调用；Artifact refs 的持久化和旧会话兼容仍需 DAT-17 收口。

### 2026-06-26 19:30 · DAT-7 Artifact Action 安全协议

- 涉及文件：`datalogue-api/app/services/artifact_actions.py`、`datalogue-api/tests/test_reserved_actions_contract.py`、`datalogue-api/tests/test_llm_config.py`、`datalogue-web/src/components/artifact-card.jsx`、`datalogue-web/src/components/artifact-card.test.jsx`、`.omx/plans/DAT-7-轻量协议验收与全量回归计划.md`、`.codex/project-memory.md`
- 关键改动：合入 ArtifactCard action 安全协议，前端卡片只渲染声明式 action、禁用态和 disabled reason，不直接启动 ReportAgent/导出副作用；后端保留 reserved action 合约测试；解决 `test_llm_config.py` 冲突，改为按 `ROLE_CALL_POLICIES["intent"]["max_tokens"]` 断言，保留当前策略修复。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_reserved_actions_contract.py tests/test_llm_config.py::test_get_llm_uses_database_role_config -q`，4 条用例通过；执行 `cd datalogue-api && python3 -m py_compile app/services/artifact_actions.py` 通过；执行 `cd datalogue-web && npm run test -- src/components/artifact-card.test.jsx`，1 个测试文件 3 条用例通过。
- 残留风险：#10 retry action 后续需要合入同一个 `artifact-card.jsx`，必须以本安全 action 协议为基础；真正 export / continue_edit / ReportAgent 仍保持禁用或详情面板，不启动链路。

### 2026-06-26 19:35 · DAT-12 Retry Checkpoint 安全恢复

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/app/schemas/chat.py`、`datalogue-api/app/services/conversation_store.py`、`datalogue-api/tests/test_retry_checkpoint.py`、`datalogue-web/src/components/artifact-card.jsx`、`datalogue-web/src/components/artifact-card.test.jsx`、`datalogue-web/src/styles.css`、`.omx/plans/DAT-12-retry-checkpoint-plan.md`、`.codex/project-memory.md`
- 关键改动：合入 retry checkpoint 注册与恢复链路，final payload 发出前注册安全 `checkpoint_ref` 并写入 `retry_checkpoint`，前端 ArtifactCard 的 `retry` action 只发送 checkpointRef；合并 #7 event envelope 和 #10 final 注册顺序，先挂载 checkpoint 再生成用户可见 envelope；保留 #11 安全 action 协议，`export/continue_edit` 仍禁用，只有 retry 可在存在 checkpoint 时触发自定义事件。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_retry_checkpoint.py tests/test_chat.py::TestLangGraphNodes::test_dataset_confirmation_fact_persists_checkpoint -q`，4 条用例通过；执行 `cd datalogue-api && python3 -m pytest tests/test_chat.py tests/test_event_envelope.py -q`，121 条用例通过；执行 `cd datalogue-api && python3 -m py_compile app/api/chat.py app/services/conversation_store.py app/schemas/chat.py` 通过；执行 `cd datalogue-web && npm run test -- src/components/artifact-card.test.jsx`，1 个测试文件 4 条用例通过。
- 残留风险：retry 恢复当前只回放安全业务上下文，不回放 SQL/schema/control_plane；前端还没有 DAT-16 的统一 Chat adapter 接管该自定义事件。

### 2026-06-26 19:45 · DAT-11 AgentScope Shell Adapter 最小验证线

- 涉及文件：`.omx/plans/DAT-11-agentscope-shell-adapter.md`、`datalogue-api/app/schemas/bi_workbench.py`、`datalogue-api/app/services/bi_workbench_tool.py`、`datalogue-api/app/services/agentscope_shell_adapter.py`、`datalogue-api/app/services/agentscope_event_adapter.py`、`datalogue-api/tests/test_agentscope_shell_adapter.py`、`datalogue-api/tests/test_agentscope_event_adapter.py`、`datalogue-api/tests/test_bi_workbench_tool.py`、`datalogue-api/tests/test_event_envelope.py`、`.codex/project-memory.md`
- 关键改动：合入 AgentScope Shell Adapter 最小验证线，固定第一阶段只允许 `ask_bi`，不开放公开 API、不启动 AgentScope runner、不替换 `/chat/stream`；`AgentScopeEventAdapter` 只把 `DatalogueEventEnvelope` 映射为 Shell 可见事件或 trace 事件，并丢弃 `control_plane`；解决 #9 与 #7/#8 的 add/add 冲突，保留真实异步 `ask_bi` 主链转接，同时兼容 `ref/ref_id`、`summary/summary_for_chat` 等前后端历史字段。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_agentscope_shell_adapter.py tests/test_agentscope_event_adapter.py tests/test_bi_workbench_tool.py tests/test_event_envelope.py -q`，16 条用例通过；执行 `cd datalogue-api && python3 -m py_compile app/schemas/bi_workbench.py app/services/bi_workbench_tool.py app/services/agentscope_shell_adapter.py app/services/agentscope_event_adapter.py` 通过。
- 残留风险：当前仍是 contract-first Shell Adapter，不接真实 AgentScope runtime、不接公开 API；后续若要完整 AgentScope 2.0 集成，需要在 event stream adapter、runner adapter 和多 Agent 产品链路成熟后再打开。

### 2026-06-26 19:50 · DAT-16 前端 C-ready Chat Shell

- 涉及文件：`datalogue-web/src/assistant/chat-adapter.js`、`datalogue-web/src/assistant/MyMessage.jsx`、`datalogue-web/src/assistant/chat-adapter.test.js`、`datalogue-web/src/assistant/MyMessage.test.jsx`、`datalogue-web/src/components/task-timeline.jsx`、`datalogue-web/src/components/task-timeline.test.jsx`、`datalogue-web/src/components/artifact-card.jsx`、`datalogue-web/src/components/artifact-card.test.jsx`、`datalogue-web/src/styles.css`、`.codex/project-memory.md`
- 关键改动：在现有 Chat 入口内解析 `event_envelope` 并兼容旧 SSE 顶层字段，将 final payload 收敛为 `taskTimeline`、`candidateConfirmation`、`artifactCard`、`primaryRef/relatedRefs` 等 C-ready metadata；新增业务阶段任务时间线组件；新增候选数据集确认卡，点击后只提交 `candidate_id/checkpoint_ref/selected_dataset_id/selected_text`，不提交 schema/字段/资产细节；ArtifactCard 支持 `ref/ref_id`、`refs`、`summary`、`action_id/payload_ref` 兼容，`export/continue_edit` 继续禁用。
- 验证方式：执行 `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js src/components/task-timeline.test.jsx src/components/artifact-card.test.jsx src/assistant/MyMessage.test.jsx`，4 个测试文件 11 条用例通过；执行 `cd datalogue-web && npm run lint` 通过，保留既有 15 个 warning；执行 `cd datalogue-web && npm run build` 通过，仅保留既有 chunk size warning。
- 残留风险：当前仍承接在现有 Chat 页面，未新建独立 BI 工作台；真实页面点击候选后继续同一任务、retry 自定义事件接 composer 的端到端验收需要 DAT-18 五件套记录继续覆盖。

### 2026-06-26 21:05 · DAT-17 Artifact refs 持久化与旧会话兼容

- 涉及文件：`datalogue-api/app/api/chat.py`、`datalogue-api/tests/test_artifact_card_contract.py`、`datalogue-api/tests/test_legacy_conversation_replay.py`、`datalogue-web/src/assistant/thread-list-adapter.js`、`datalogue-web/src/components/artifact-card.jsx`、`datalogue-web/src/components/artifact-card.test.jsx`、`datalogue-web/tests/unit/assistant/artifact-custom.test.js`、`.codex/project-memory.md`
- 关键改动：final payload 统一补齐 `task_id`、`trace_id`、`primary_ref`、`related_refs` 和 `artifact_card`，event envelope 透传同一 task/trace；ArtifactCard 只暴露 `artifact:/trace:/checkpoint://` 引用句柄和禁用态动作，不携带 raw SQL/raw result；assistant message metadata 写回新 refs，`query_artifact` 只按 `artifact:<uuid>` 反连 message_id；`conversation_state.facts` 写入 `artifact_refs` fact，旧会话不迁移、不回填；前端历史回放只渲染真实 `response_metadata.artifact_card`，不会根据旧 `result_ref/report_ref` 伪造卡片。
- 验证方式：执行 `cd datalogue-api && python3 -m pytest tests/test_artifact_card_contract.py tests/test_legacy_conversation_replay.py tests/test_conversation.py tests/test_artifact_api.py -q`，15 条用例通过；执行 `cd datalogue-api && python3 -m pytest tests/test_event_envelope.py tests/test_retry_checkpoint.py tests/test_chat.py -q`，129 条用例通过；执行 `cd datalogue-web && npm run test -- src/components/artifact-card.test.jsx tests/unit/assistant/artifact-custom.test.js src/assistant/chat-adapter.test.js`，3 个测试文件 14 条用例通过；执行 `cd datalogue-web && npm run lint` 通过，保留既有 15 个 warning；执行 `cd datalogue-web && npm run build` 通过，仅保留既有 chunk size warning；执行 `git diff --check` 通过。
- 残留风险：DAT-17 只完成协议与持久化闭环；真实页面、SSE、后端日志、Langfuse、`query_artifact/conversation_state` 五件套一致性仍需 DAT-18 用本地服务和真实问题记录验收。
