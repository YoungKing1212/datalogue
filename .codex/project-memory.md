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

## 高价值判断

- Datalogue 当前业务链路不依赖 Redis 保存多轮业务状态；`last_success_task`、`conversation_state.subagent_capsules` 和 query artifacts 的真相在数据库或应用 ArtifactStore 路径，Langfuse/BullMQ Redis key 不能当成业务状态依据。
- 多轮追问不要从当前自然语言残留硬猜 `person`；应依赖 LLM 结构化槽位、上一轮已确认过滤或澄清。
- 数据集上下文压缩优先采用“轻量候选资产目录 + 按需详情补合”，不要一开始把完整字段、SQL、样例行全部塞进 prompt。
- `.env.example` 中要区分“已被 Settings 读取并生效的配置”和“尚未接入的候选项”。
- `localhost:8080` 等地址返回应用层 `Unauthorized` 时，优先判断服务已启动，继续排查认证、代理或路由，不要直接判定服务未启动。

## 最新详细记录

### 2026-06-25 11:24 · AgentScope 2.0 ReAct MVP 真实请求验证

- 涉及文件：`datalogue-api/tests/agentscope_react_mvp/mvp.py`、`datalogue-api/tests/agentscope_react_mvp/test_live_react_agent.py`、`datalogue-api/tests/agentscope_react_mvp/README.md`、`datalogue-api/pyproject.toml`、`.codex/project-memory.md`
- 关键改动：新增独立真实集成测试目录，使用 AgentScope 2.0 `Agent`、`Toolkit` 和 `ToolBase` 封装数语最小工具面；`DataloguePlanQueryTool` 真实请求数据集、已选表、已选字段和语义资产，`DatalogueExecuteSqlTool` 真实调用 `/api/dataset/{id}/sql/preview`；新增 `LiteLLMAgentScopeChatModel`，复用数语数据库中的 `lead_agent` LLM 配置，让 AgentScope ReAct 决策继续由 AgentScope 驱动，同时绕过当前 AgentScope OpenAI SDK 直连 DeepSeek 的连接问题；测试断言 Agent 自主调用两个工具、命中真实 API 路径、不进入 `/api/chat/stream` 和 `/api/conversation`，并以 SQL preview 结构化结果验证最终统计值。
- 验证方式：先在 `main` 回滚非文档测试目录并提交文档更新，再切换到 `codex/agentscope-react-mvp` 分支开发；执行 `curl http://127.0.0.1:8000/health` 返回 `{"status":"ok"}`；执行 Hermes 等价 live `execute-sql 11 --sql "SELECT COUNT(*) AS cnt FROM project_contract_management"` 返回 `cnt=6583`；执行 `.venv/bin/python -m pytest tests/agentscope_react_mvp/test_live_react_agent.py -q` 默认跳过真实请求；执行 `RUN_AGENTSCOPE_REACT_MVP=1 DATALOGUE_BASE_URL=http://127.0.0.1:8000 .venv/bin/python -m pytest tests/agentscope_react_mvp/test_live_react_agent.py -q -s`，1 条真实集成测试通过，Agent 自主调用 `DataloguePlanQueryTool` 和 `DatalogueExecuteSqlTool` 并通过后端 SQL Guard；执行 `.venv/bin/python -m py_compile tests/agentscope_react_mvp/mvp.py tests/agentscope_react_mvp/test_live_react_agent.py` 和 `git diff --check` 通过。
- 残留风险：该目录是实验性 MVP，不是正式生产 Agent 运行时；当前依赖 `agentscope==2.0.2` 需手动安装，且模型底层通过 LiteLLM 适配器复用数语配置，后续产品化还需补正式依赖管理、trace 观测、失败重试、SQL 自动修复和权限策略。

### 2026-06-25 11:39 · AgentScope 真实测试增加过程日志

- 涉及文件：`datalogue-api/tests/agentscope_react_mvp/mvp.py`、`datalogue-api/tests/agentscope_react_mvp/test_live_react_agent.py`、`datalogue-api/tests/agentscope_react_mvp/README.md`、`.codex/project-memory.md`
- 关键改动：为 AgentScope ReAct MVP 增加控制台日志，输出测试入口、LLM 配置、tool-call 请求、每个真实 HTTP GET/POST 路径、Plan 工具返回的数据集/表/字段规模、Execute 工具生成的 SQL、SQL preview 的 guard/columns/row_count/rows 摘要、最终中文回答和 preview 结果；测试断言改为动态验证 selected tables、selected columns 和 sql preview 路径，不再绑定固定 dataset 11，适配用户将用例改成“查询杨凯2024年的工作日志”后的 Agent 自主选 dataset 行为；README 补充 `-s` 查看日志和 `AGENTSCOPE_MVP_LOG_FULL_RESULT=1` 打印完整结果。
- 验证方式：执行 `.venv/bin/python -m py_compile tests/agentscope_react_mvp/mvp.py tests/agentscope_react_mvp/test_live_react_agent.py` 通过；执行 `.venv/bin/python -m pytest tests/agentscope_react_mvp/test_live_react_agent.py -q` 默认跳过真实请求；执行 `git diff --check` 通过；执行 `RUN_AGENTSCOPE_REACT_MVP=1 DATALOGUE_BASE_URL=http://127.0.0.1:8000 .venv/bin/python -m pytest tests/agentscope_react_mvp/test_live_react_agent.py -q -s`，1 条真实集成测试通过，日志显示 Agent 自主查看 dataset 12 后补调 dataset 10，执行 3 次 SQL preview，最终返回 100 行杨凯 2024 年工作日志和中文汇总。
- 残留风险：日志输出依赖 `pytest -s`；完整 preview 结果可能较长，默认只打印前 5 行，必要时用 `AGENTSCOPE_MVP_LOG_FULL_RESULT=1` 查看全量。

### 2026-06-25 13:38 · AgentScope Hermes-style DatasetAgent MVP

- 涉及文件：`datalogue-api/tests/agentscope_react_mvp/mvp.py`、`datalogue-api/tests/agentscope_react_mvp/test_live_react_agent.py`、`datalogue-api/tests/agentscope_react_mvp/README.md`、`.codex/project-memory.md`
- 关键改动：将原本的自由 ReAct 测试升级为 Hermes-style DatasetAgent MVP；加载 `hermes-skills/datalogue/SOUL.md`、`SKILL.md` 和 `references/capabilities.md` 生成 AgentScope system prompt；新增 `CapabilityManifest` 控制 DatasetAgent 内部工具注册，LeadAgent 只作为窄工具面边界写入 prompt；工具面改为 `recall_assets`、`plan_query`、`guard_sql`、`preview_sql`、`execute_query`、`persist_artifact`、`summarize_result`，其中真正执行仍只走 Datalogue guarded SQL preview；工具结果改为返回 `result_ref`、`artifact`、`summary`、`sql_guard` 和 `tool_trace`，保留 `conversation_state/query_artifact/Manifest/SQL audit/Langfuse trace` 是业务真相源的边界；新增 `react_trace`，记录每轮 LLM request/response、assistant 可见文本、tool_call、工具 observation 和 HTTP 执行结果，便于在控制台查看 AgentScope 可观测 ReAct 链路。
- 验证方式：执行 `.venv/bin/python -m py_compile tests/agentscope_react_mvp/mvp.py tests/agentscope_react_mvp/test_live_react_agent.py` 通过；执行 `curl -sS -m 5 http://127.0.0.1:8000/health` 返回 `{"status":"ok"}`；执行 `RUN_AGENTSCOPE_REACT_MVP=1 DATALOGUE_BASE_URL=http://127.0.0.1:8000 .venv/bin/python -m pytest tests/agentscope_react_mvp/test_live_react_agent.py -q -s`，2 条测试通过；真实日志显示 AgentScope 仅看到 manifest 暴露工具，先查 dataset 12 后自主切到 dataset 10，调用 `guard_sql`、`preview_sql`、`summarize_result`，第一次 preview 返回 0 行后根据 observation 修正 SQL，第二次 preview 返回 100 行杨凯 2024 年工作日志，`result_ref=mvp://query_artifact/10/a9df15689cc39b42`；`react_trace` 中可见 `llm_request`、`llm_response`、`assistant_visible_text`、`tool_call` 和 `tool_observation`；执行 `git diff --check` 通过。
- 残留风险：当前仍是测试目录内的实验性 MVP，`artifact.persisted=false`，没有真实写入 `query_artifact` 或接入 `/chat/stream` 事件流；`execute_query` 在 MVP 中复用 SQL preview；`react_trace` 打印的是 AgentScope 可观测执行事件，不暴露模型内部隐藏思维；后续产品化需要接入正式 artifact store、权限策略、trace observation、失败重试和 SQL 修复。

### 2026-06-25 17:25 · 项目文档多目录治理

- 涉及文件：`docs/README.md`、`docs/上下文入口.md`、`docs/product/`、`docs/architecture/`、`docs/observability/`、`docs/agent-planning/`、`docs/deliverables/`、`docs/assets/`、`docs/archive/2026-06-legacy-docx/`、`.codex/project-memory.md`
- 关键改动：将 `docs/` 根目录混放的项目介绍、阶段总结、系统设计、Langfuse 可观测、渐进式资产注入设计、DOCX 交付物、链路图和用户手册截图按内容迁移到多目录结构；保留 `docs/上下文入口.md` 作为 Agent 固定入口；新增 `docs/README.md` 说明目录用途、当前入口、归档内容和整理规则；把旧版合并 `Langfuse可观测能力需求与开发文档.docx` 归档到 `archive/`，不直接删除。
- 验证方式：执行 Markdown 图片/链接检查确认 `docs/product/当前项目工作总结与下步计划.md` 中 37 个图片引用均存在；执行 `rg` 扫描当前入口文档无旧路径；执行 `git diff --check -- docs .codex/project-memory.md` 通过；检查最新详细记录数量保持 10 条。
- 残留风险：`.codex/project-memory.md` 中早期历史记录保留当时的旧路径，用于追溯原始完成记录；后续如果有新的 DOCX 或截图交付物，需要继续按 `docs/README.md` 目录规则放置。

### 2026-06-25 20:24 · Obsidian 智能问数长期知识沉淀

- 涉及文件：`/Users/yangkai/KenYang/文档库/develop-doc-repositry/项目知识库/智能问数/企业级智能问数受约束 Agent 架构.md`、`/Users/yangkai/KenYang/文档库/develop-doc-repositry/项目知识库/智能问数/智能问数语义治理与执行安全.md`、`/Users/yangkai/KenYang/文档库/develop-doc-repositry/项目知识库/智能问数/智能问数真实链路验收方法.md`、`.codex/project-memory.md`
- 关键改动：将当前 Datalogue 实践从工作记录抽象为 Obsidian 项目知识库长期沉淀，新增三篇方法论文档，分别沉淀受约束 Agent 架构、语义治理与执行安全、真实链路验收方法；内容强调 LeadAgent/DatasetAgent 边界、Capability Manifest、Manifest fail-closed、QueryArtifact/result_ref、多轮状态真相源、SQL Guard、Trace/日志/payload/页面交叉取证等可复用原则。
- 验证方式：执行 `wc -l` 确认三篇文档已写入且总计 889 行；执行占位词扫描确认三篇文档未残留占位内容；按项目记忆规则将最早一条最新详细记录压缩进历史区，保持最新详细记录不超过 10 条。
- 残留风险：本次是长期知识库文字沉淀，没有重新运行 Datalogue 真实问数链路；后续如果 AgentScope 产品化方案、Manifest 字段或 Trace 事件名继续演进，需要同步更新这些方法论文档。

### 2026-06-26 12:10 · Multica Datalogue 员工智能体创建与技能绑定

- 涉及文件：`.codex/project-memory.md`、`hermes-skills/datalogue/SKILL.md`、`hermes-skills/datalogue/SOUL.md`、`hermes-skills/datalogue/references/capabilities.md`、`hermes-skills/datalogue/scripts/api_assets.py`、`.codex/config.toml`
- 关键改动：在 Multica workspace 创建 `datalogue` skill，并上传 SOUL、capabilities 和 API assets 脚本支持文件；创建 5 个员工智能体：`Datalogue-数据问数分析师`、`Datalogue-后端工程师`、`Datalogue-前端体验工程师`、`Datalogue-QA观测工程师`、`Datalogue-文档交付专员`；为新员工配置中文职责 Prompt、workspace 可见性、项目 MCP 配置（dbhub/playwright，平台红acted 回显）和对应 skills；同时为现有 `CEO` 智能体补充规划、分析、问询、wiki、互联网调研和 Datalogue skill。
- 验证方式：执行 `multica agent get` 抽查 5 个新员工，确认 agent 存在、`mcp_config_redacted=true`、skills 已绑定；执行 `multica skill files list 84c3f7db-9aad-4b1e-95f5-8fb6d16818b8 --output json` 确认 `SOUL.md`、`references/capabilities.md`、`scripts/api_assets.py` 已上传；执行 `multica agent skills list 75b45fd3-2dbb-49b2-86b0-f8074822da91 --output json` 确认 CEO 已绑定新 skill；按项目记忆规则将最早一条最新详细记录压缩进历史区，保持最新详细记录不超过 10 条。
- 残留风险：本次只创建和配置 Multica agent/skill，没有创建 squad、自动分派规则或真实 issue 流转演练；MCP 配置来自项目现有 `.codex/config.toml`，后续若本地 PostgreSQL、Playwright 或 npx 环境不可用，相关 MCP 需要单独排查。

### 2026-06-26 12:13 · Multica 数语智能问数小队创建

- 涉及文件：`.codex/project-memory.md`
- 关键改动：创建 Multica squad `数语智能问数小队`（`2f19d9dd-97ac-42bf-a7ac-2bacfb1151c1`），leader 设为 `CEO`；将 `Datalogue-数据问数分析师`、`Datalogue-后端工程师`、`Datalogue-前端体验工程师`、`Datalogue-QA观测工程师`、`Datalogue-文档交付专员` 加入小队，并分别设置 roster role；补充 squad leader instructions，明确小队不会自动 fan-out，任务先路由到 CEO，由 CEO 按目标、约束、风险和成员能力创建子 issue 或直接处理。
- 验证方式：执行 `multica squad get 2f19d9dd-97ac-42bf-a7ac-2bacfb1151c1 --output json` 确认 `member_count=6`、leader 为 CEO、instructions 已写入；执行 `multica squad member list 2f19d9dd-97ac-42bf-a7ac-2bacfb1151c1 --output json` 确认 leader 和 5 个员工成员均存在且 role 正确；按项目记忆规则将最早一条最新详细记录压缩进历史区，保持最新详细记录不超过 10 条。
- 残留风险：Multica squad 当前产品行为是路由到 leader，不会自动把任务分发给所有成员；后续如果要实现阶段化自动协作，还需要基于 issue stage、子 issue 或 autopilot 单独设计流程。

### 2026-06-26 12:33 · C 产品形态优先且 BI 内核 B-governed 工作规划

- 涉及文件：`docs/architecture/B-first C-ready 头脑风暴决策总览.md`、`docs/architecture/B-first C-ready 智能问数能力路由改造任务清单.md`、`docs/architecture/b-first-c-ready-decisions/02-决策沉淀 Hook 规则.md`、`docs/architecture/b-first-c-ready-decisions/decisions/001-capability_manifest 定位为轻量能力广告.md`、`docs/architecture/b-first-c-ready-decisions/decisions/010-C 产品形态优先且 BI 内核保持 B-governed.md`、`docs/architecture/b-first-c-ready-decisions/decisions/011-Agentic Shell 第一阶段采用 Chat 入口加工作台协议.md`、`docs/architecture/b-first-c-ready-decisions/decisions/012-Chat 内任务展示采用业务级时间线并预留双层展开.md`、`docs/architecture/b-first-c-ready-decisions/decisions/013-产物详情采用 Chat 轻量卡并预留详情面板.md`、`docs/architecture/b-first-c-ready-decisions/decisions/014-轻量产物卡采用统一壳加类型化 preview_payload.md`、`docs/architecture/b-first-c-ready-decisions/decisions/015-preview_payload 采用半强 schema.md`、`docs/architecture/b-first-c-ready-decisions/decisions/016-actions 采用固定注册表加受控动作实例.md`、`docs/architecture/b-first-c-ready-decisions/decisions/017-refs 拆分为 primary_ref 与 related_refs 并预留 role.md`、`docs/architecture/b-first-c-ready-decisions/decisions/018-export 第一阶段进入 Action Registry 但默认禁用.md`、`docs/architecture/b-first-c-ready-decisions/decisions/019-continue_edit 第一阶段只作为详情面板预留动作.md`、`docs/architecture/b-first-c-ready-decisions/decisions/020-ask_bi 采用最小稳定契约并复用现有主链.md`、`docs/architecture/b-first-c-ready-decisions/decisions/021-retry 第一阶段从最后安全检查点重试.md`、`docs/architecture/b-first-c-ready-decisions/decisions/022-主链路验收采用分层验收.md`、`/Users/yangkai/KenYang/文档库/develop-doc-repositry/工作知识库/2026/数语/2026-06-26 B-first C-ready 能力路由头脑风暴/`、`.codex/project-memory.md`
- 关键改动：将总路线从 `B-first, C-ready` 升级为 `C-shaped product, B-governed BI core`，明确产品形态直接采用 C，但 BI 查询内核保持 B-governed；新增第十个已敲定决策，规定 Agentic Shell、ReportAgent、PythonAgent、AuditAgent 都必须通过 `BIWorkbenchTool` / `ask_bi` 使用 BI 能力，不得绕过 BI 工具访问 schema、SQL、数据库或 `control_plane` 主体；新增第十一个已敲定决策，规定 Agentic Shell 第一阶段采用现有 Chat 入口，同时按未来 BI 工作台协议设计任务模型、事件流、产物引用和状态结构；新增第十二个已敲定决策，规定 Chat 内第一版任务展示采用业务级任务时间线，并把方案 3 双层可展开时间线记录为后续必须改造项；新增第十三个已敲定决策，规定报告、图表、审计解释等产物详情第一阶段采用 Chat 轻量产物卡，并预留 `detail_view_ref` / `artifact_panel_ref` 给后续详情面板或独立 BI 工作台承载完整产物；新增第十四个已敲定决策，规定轻量产物卡采用统一 `ArtifactCard` 壳，并用类型化 `preview_payload` 表达 report/chart/audit/analysis 的差异；新增第十五个已敲定决策，规定 `ArtifactCard` 外层采用强 schema，`preview_payload` 采用半强 schema，并通过最小必填字段、`optional_details`、`schema_version`、size guard、敏感字段扫描和 `visibility` 约束控制扩展边界；新增第十六个已敲定决策，规定 `actions` 采用固定 Action Registry 加后端受控动作实例，后端只能返回白名单 `action_type` 和白名单 payload，前端按 registry 渲染并安全忽略未知动作；新增第十七个已敲定决策，规定 `refs` 拆分为 `primary_ref` 与 `related_refs`，`actions` 默认绑定 `primary_ref`，并预留 `role` 字段给后续引用角色体系；新增第十八个已敲定决策，规定 `export` 第一阶段进入 Action Registry，但默认作为预留禁用态，不生成导出文件、不开放完整数据导出、不导出 raw result；新增第十九个已敲定决策，规定 `continue_edit` 第一阶段只作为详情面板或未来工作台预留动作，不启动 ReportAgent，不实现编辑、版本、保存、回滚和编辑审计链路；新增第二十个已敲定决策，规定 `ask_bi` / `BIWorkbenchTool` 采用最小稳定契约，内部第一阶段复用现有 Chat、LeadAgent、DatasetAgent 和 `/chat/stream` 主链，后续再升级为 BI 工作台原生能力入口；新增第二十一个已敲定决策，规定 `retry` 第一阶段从最后安全检查点重试，不可恢复时降级整任务重试，不实现完整任务 DAG 或任意子任务重试；新增第二十二个已敲定决策，规定真实链路验收采用分层验收，P0 主链路强制真实页面、SSE event envelope、后端日志、Langfuse trace 和 query_artifact / conversation_state 五件套一致，预留项只做轻量协议验收；任务清单继续保留 P0-P4 作为能力清单、Capability Router、共享 DatasetAgent Runtime、DatasetAgentToolAdapter、事件观测协议等 BI 内核治理工作包，并把 P5 升级为 C 产品形态入口与 C-ready 工作规划，拆出 Agentic Shell、BIWorkbenchTool、ReportAgent、PythonAgent、AuditAgent、产物引用和任务事件协议；P6 继续保留 AgentScope MVP / runner / adapter 验证线，不让 AgentScope 第一阶段直接接管主链 runtime。
- 验证方式：执行 Markdown 占位扫描，确认文档未残留占位内容；执行 `wc -l` 检查仓库副本与 Obsidian 副本行数一致；执行 `git diff --check -- docs/architecture .codex/project-memory.md` 通过。
- 残留风险：本次仍是头脑风暴后的任务清单，不是已批准的正式开发计划；后续需要继续收敛 capability manifest schema、接口协议和里程碑后再进入实施计划。

### 2026-06-26 12:43 · 默认测试套件稳定性修复

- 涉及文件：`datalogue-api/tests/agentscope_react_mvp/test_live_react_agent.py`、`datalogue-api/tests/test_llm_config.py`、`.codex/project-memory.md`
- 关键改动：恢复 AgentScope ReAct MVP live integration 测试的 `RUN_AGENTSCOPE_REACT_MVP=1` 显式开关，避免默认后端 pytest 在本地 Datalogue API 未启动时调用真实服务和真实 LLM；同步将 `intent` 角色 LLM 策略测试中的 `max_tokens` 断言更新为当前 `ROLE_CALL_POLICIES` 的 `20480`，对齐 2026-06-23 的策略调整。
- 验证方式：执行 `.venv/bin/python -m pytest tests/test_llm_config.py::test_get_llm_uses_database_role_config -q` 通过；执行 `.venv/bin/python -m pytest tests/agentscope_react_mvp/test_live_react_agent.py -q` 得到 `1 passed, 1 skipped`；执行 `.venv/bin/python -m pytest` 得到 `726 passed, 5 skipped, 327 warnings`；前端已执行 `npm run lint`、`npm run test`、`npm run build`，其中 lint/build 仅有 warning。
- 残留风险：`ruff check .` 仍报告 64 个既有静态问题，其中 `app/services/lead_agent_routing.py:914` 存在 `json` 未定义风险；后端 `.venv` 未安装 ruff，本次使用系统 ruff 只做发现，不顺手清理历史 lint。

### 2026-06-26 13:00 · B-first C-ready 后续改造记录与正式开发计划

- 涉及文件：`docs/architecture/B-first C-ready 后续改造记录.md`、`docs/architecture/B-first C-ready 正式开发计划.md`、`docs/architecture/B-first C-ready 头脑风暴决策总览.md`、`/Users/yangkai/KenYang/文档库/develop-doc-repositry/工作知识库/2026/数语/2026-06-26 B-first C-ready 能力路由头脑风暴/`、`.codex/project-memory.md`
- 关键改动：将今天头脑风暴中所有 B-first 但 C-ready 的出口单独整理成后续改造记录，明确 Chat as Shell Entry、`ask_bi`、event envelope、ArtifactCard、Action Registry、ReportAgent、PythonAgent、AuditAgent、双层时间线、完整 BI 工作台和 AgentScope runtime 的预留边界与接入条件；新增正式开发计划，按 P0/P1/P2 拆出 `capability_manifest`、Capability Router、ToolAdapter 分层、event envelope、`ask_bi`、ArtifactCard、候选数据集确认、retry checkpoint 和五件套验收任务，并标注依赖、涉及文件、测试文件和验收用例；同步把两个新文档纳入总览的文档拆分建议。
- 验证方式：执行 Markdown 占位扫描，确认新增文档和更新文档未残留占位内容；执行 `wc -l` 检查仓库副本与 Obsidian 副本行数一致；执行 `git diff --check -- docs/architecture .codex/project-memory.md` 通过。
- 残留风险：本次产物是正式开发计划文档，不包含代码实现；计划中的新增文件和测试需要后续按任务分批实施并进行真实链路五件套验收。
