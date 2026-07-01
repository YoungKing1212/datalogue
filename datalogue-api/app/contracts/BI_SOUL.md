# BI_SOUL 内部契约

`BI_SOUL.md` 是 Datalogue BI 能力不可越界协议的内部 source of truth。LeadAgent、Dataset SubAgent、Hermes Skill 和 legacy AgentScopeShellAdapter compatibility 都必须以本文件为边界说明来源；外部入口只同步本文件的公共边界，不重新定义 BI 真相源。

## 内部职责

- Datalogue BI 内核负责 Manifest 路由、schema 新鲜度检查、Dataset SubAgent 执行、SQL Guard、QueryArtifact、conversation_state 和 trace 写入。
- LeadAgent 是控制面，只处理时间、会话、Manifest 路由、schema 状态、澄清、SubAgent 调度和审计。
- Dataset SubAgent 是数据集内执行面，负责语义资产召回、DSL/SQL 生成、SQL Guard、预览执行、结果摘要和 artifact 持久化。

## 外部入口同步块

<!-- BEGIN BI_SOUL_SYNC -->
- LeadAgent 不看字段级 schema 明细；字段、指标、维度、术语、蓝图和 SQL 生成都留在 Dataset SubAgent / BI 内核内。
- AS-R0 主 Runtime ownership 属于 Datalogue Agentic Shell；legacy `ask_bi` 只作为兼容入口，不再作为新主链工具。
- 外层 Agent 不得绕过 Datalogue BI 内核直连 schema、SQL preview、数据库或 Chat 主链内部节点。
- LLM 不直接生成可执行 SQL；SQL 只能在 BI 内核受控链路中生成，并经过 SQL Guard、执行适配和 artifact 持久化。
- raw SQL / raw result / capsule / trace 主体属于 `control_plane`，只能写入后端状态、artifact、日志或观测链路，不进入外层 Agent 可见上下文。
- ArtifactCard / event envelope / refs 只能承载 `llm_visible` 摘要、引用句柄和可展示状态，不承载 raw result、raw SQL、capsule 或 trace 主体。
- AgentScopeShellAdapter 不替代 Datalogue 真相源；P2 起只保留 legacy compatibility 标记，不拥有业务 Runtime ownership。
<!-- END BI_SOUL_SYNC -->

## 不做事项

- 不把 AgentScopeShellAdapter 或 legacy `ask_bi` 作为 BI 主链 runtime。
- 不为外层 Agent 注册 schema、SQL、preview、database、artifact body 或 `control_plane` 工具。
- 不让 Hermes Skill、AgentScope Shell 或其他外层 Agent 自行拼接主链 execution graph。
