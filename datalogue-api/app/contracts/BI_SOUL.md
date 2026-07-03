# BI_SOUL 内部契约

`BI_SOUL.md` 是 Datalogue BI 能力不可越界协议的内部 source of truth。AgentScope Agent Team、BI Worker、Dataset 执行工具和后续外接 Agent 都必须以本文件为边界说明来源；外部入口只同步本文件的公共边界，不重新定义 BI 真相源。

## 内部职责

- Datalogue BI 内核负责 Manifest 路由、schema 新鲜度检查、DatasetAgent 执行、SQL Guard、QueryArtifact、conversation_state 和 trace 写入。
- BI Agent 是确认与 handoff 控制面，只处理 run、确认门禁和 DatasetAgent 交接。
- Dataset SubAgent 是数据集内执行面，负责语义资产召回、DSL/SQL 生成、SQL Guard、预览执行、结果摘要和 artifact 持久化。

## 外部入口同步块

<!-- BEGIN BI_SOUL_SYNC -->
- BI Agent 不看字段级 schema 明细；字段、指标、维度、术语、蓝图和 SQL 生成都留在 DatasetAgent / BI 内核内。
- 主 Runtime ownership 属于 AgentScope Agent Team；legacy `ask_bi`、旧 Chat stream 和旧自研 runner 不再作为主链。
- 外层 Agent 不得绕过 Datalogue BI 内核直连 schema、SQL preview、数据库或 Chat 主链内部节点。
- LLM 不直接生成可执行 SQL；SQL 只能在 BI 内核受控链路中生成，并经过 SQL Guard、执行适配和 artifact 持久化。
- raw SQL / raw result / capsule / trace 主体属于 `control_plane`，只能写入后端状态、artifact、日志或观测链路，不进入外层 Agent 可见上下文。
- ArtifactCard / event envelope / refs 只能承载 `llm_visible` 摘要、引用句柄和可展示状态，不承载 raw result、raw SQL、capsule 或 trace 主体。
- 外层 AgentScope 适配器不替代 Datalogue 真相源；旧 AgentScopeShellAdapter 兼容壳已删除。
<!-- END BI_SOUL_SYNC -->

## 不做事项

- 不把 legacy `ask_bi` 或旧 Chat stream 作为 BI 主链 runtime。
- 不为外层 Agent 注册 schema、SQL、preview、database、artifact body 或 `control_plane` 工具。
- 不让外接 Agent、兼容适配器或其他外层入口自行拼接主链 execution graph。
