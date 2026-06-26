# B-first C-ready 后续改造记录

本文从 22 个已敲定决策中单独抽取“第一阶段先按 B-governed 主链落地，但为 C 产品形态保留出口”的内容。它用于避免后续制定开发计划时把增强能力混进第一阶段主链，也避免未来做 C 形态时找不到已预留的协议口。

---

## 一、总原则

当前路线是：

```text
C-shaped product, B-governed BI core
```

第一阶段优先跑通智能问数核心链路：

```text
用户提问
能力路由
候选数据集确认
受控 DatasetAgent 查询
结果摘要
ArtifactCard
引用句柄
事件 envelope
五件套验收
```

C-ready 的含义不是第一阶段直接实现完整 Agentic Shell、ReportAgent、PythonAgent、AuditAgent、独立 BI 工作台和 AgentScope 主链 runtime，而是第一阶段的接口、事件、产物、引用和动作都按未来 C 形态设计，不把系统继续绑死在一次性 Chat 回答里。

---

## 二、第一阶段必须保留的 C-ready 出口

### 2.1 Chat as Shell Entry

第一阶段继续使用现有 Chat 入口承接用户问题，但数据结构按工作台协议设计：

- `task_id`
- `task_type`
- `task_status`
- 业务级任务时间线
- 子任务事件
- 产物引用
- 下一步动作

后续独立 BI 工作台必须复用同一套任务模型、事件协议和引用句柄，不能另起并行协议。

### 2.2 ask_bi / BIWorkbenchTool

第一阶段定义最小稳定契约，内部复用现有 Chat、LeadAgent、DatasetAgent 和 `/chat/stream` 主链。

最小入参：

```text
question
conversation_id
caller
confirmed_dataset_id
context_refs
request_options
```

最小出参：

```text
task_id
event_envelope
candidate_datasets
answer
artifact_card
primary_ref
related_refs
status
error
```

后续改造方向：

- 从 “Chat 主链适配壳” 升级为 “BI 工作台原生能力入口”。
- 补齐任务生命周期、权限视图、详情面板恢复、多产物状态和 AgentScope adapter。
- 保持外层 Agent 只能通过 `ask_bi` 使用 BI 能力，不得绕过 LeadAgent / DatasetAgent。

### 2.3 DatalogueEventEnvelope

第一阶段先标准化现有 SSE，形成统一 event envelope；AgentScope event stream 通过 `AgentScopeEventAdapter` 做验证映射，但不直接替换主链 SSE。

后续改造方向：

- `AgentScopeEventAdapter` 将 event envelope 映射到 AgentScope event stream。
- 独立 BI 工作台复用同一套事件，不重新定义前端私有事件。
- Langfuse observation、后端 checkpoint 日志和最终 payload 使用同一批事件字段。

### 2.3.1 AgentScopeShellAdapter

第一阶段需要显式保留 AgentScope 2.0 技术落点，但只放在外层 Shell Adapter：

```text
AgentScopeShellAdapter
  -> ask_bi / BIWorkbenchTool
  -> DatalogueEventEnvelope
  -> ArtifactCard / refs
```

第一阶段边界：

- AgentScope 只能调用 `ask_bi`。
- `AgentScopeShellAdapter` 放在 `datalogue-api/app/services/agentscope_shell_adapter.py`，作为正式后端 service，而不是继续停留在实验测试目录。
- AgentScope 只能消费标准 event envelope、`llm_visible`、ArtifactCard 和引用句柄。
- AgentScope 不访问 schema、SQL、raw result、capsule、数据库或 `control_plane`。
- 第一阶段不新增公开 API route、不接前端入口、不做独立 runner 进程。
- AgentScope session / memory 不替代 Datalogue 的 conversation_state、query_artifact、Manifest、SQL Guard 和审计真相源。
- `/chat/stream` 仍由现有 Datalogue 主链提供，AgentScope event stream 只做 adapter 验证。

### 2.3.2 BI_SOUL 内部契约

`SOUL.md` 不再只属于 Hermes skill 包。Datalogue 内部需要维护一份 BI 不可越界契约作为 source of truth：

```text
datalogue-api/app/contracts/BI_SOUL.md
```

同步目标：

- `hermes-skills/datalogue/SOUL.md`
- `AgentScopeShellAdapter` 的 system prompt / policy injection
- 后续外部 Agent 或 skill 包

后续改造方向：

- 将契约同步纳入测试或发布流程。
- 契约变更需要经过审核，避免外部入口和内部主链规则漂移。

### 2.3.3 旧会话兼容边界

旧会话不支持新 ArtifactCard、event envelope、refs 和新 conversation_state 回放。

第一阶段只保证：

- 旧会话能继续展示原始历史消息。
- 缺少 ArtifactCard 时不报错。
- 不为旧会话伪造 ArtifactCard 或引用。
- 新协议上线后的新会话才具备完整 C-ready 回放能力。

### 2.4 ArtifactCard

第一阶段 Chat 内只展示轻量产物卡，不承载完整报告、完整表格、大图表或完整审计链路。

统一外壳：

```text
artifact_type
schema_version
title
status
summary_for_chat
preview_payload
primary_ref
related_refs
actions
detail_view_ref
artifact_panel_ref
```

后续改造方向：

- 右侧详情面板或独立 BI 工作台基于 `detail_view_ref` / `artifact_panel_ref` 打开完整产物。
- `preview_payload` 从半强 schema 逐步收紧到工作台可编辑 schema。
- `primary_ref` / `related_refs.role` 从预留字段升级为强枚举和校验规则。

### 2.5 Action Registry

第一阶段固定动作注册表：

```text
open_detail
continue_edit
analyze_more
export
explain
retry
change_dataset
```

C-ready 预留边界：

- `export` 进入注册表，但默认禁用，不生成文件、不开放完整数据导出。
- `continue_edit` 进入注册表，但只禁用或打开详情面板，不启动 ReportAgent。
- `retry` 第一阶段从最后安全检查点恢复，后续再评估完整 DAG 级子任务重试。
- 未知动作安全忽略，并记录 trace-only 事件。

---

## 三、明确后置的 C 能力

### 3.1 ReportAgent

第一阶段不启动 ReportAgent，不实现报告继续编辑、版本管理、保存、回滚或编辑审计链路。

后续接入条件：

- `report_ref` 产物生命周期稳定。
- `ArtifactCard` 与详情面板能承载报告草稿。
- 编辑动作、保存动作和审计动作都有白名单 payload。
- 报告内容只能引用 `display_summary`、`result_ref`、`report_ref` 和用户显式输入。

### 3.2 PythonAgent

第一阶段不开放 PythonAgent 二次分析链路。

后续接入条件：

- `result_ref` 对应的数据切片有行数、列数、敏感字段和权限限制。
- Python 执行沙箱有时间、内存、输出体积和依赖白名单。
- PythonAgent 不能连接业务数据库，只能读取受控 artifact/ref。
- 输出必须落为 `chart_ref` 或 `analysis_ref`，并可审计、可回放、可阻断。

### 3.3 AuditAgent

第一阶段可保留审计解释入口，但不实现完整 AuditAgent 分层视图。

后续接入条件：

- 用户可见解释、管理员审计、开发排障三类视图边界明确。
- 普通用户只看到数据集、指标口径摘要、结果引用和阻断原因。
- 管理员和开发者视图通过权限控制访问 artifact、trace 和 checkpoint 摘要。
- 不直接暴露 raw SQL、raw result、capsule 主体、trace 主体或内部错误主体。

### 3.4 双层可展开时间线

第一阶段只展示业务级任务时间线。

后续接入条件：

- `expandable_details` / `technical_summary` 字段完成脱敏规则和泄露扫描。
- 普通用户、管理员、开发者分别能看到哪些受控技术摘要有清晰权限表。
- 展开内容只包含能力匹配依据、guard 状态、artifact 引用和 trace 关联摘要，不包含内部主体。

### 3.5 完整 BI 工作台

第一阶段不重写完整 BI 工作台运行时。

后续接入条件：

- `ask_bi` 最小契约稳定。
- Chat 阶段的任务模型、事件协议、产物引用和动作协议已在 P0 主链路通过验收。
- 详情面板恢复、多产物状态、权限视图和工作台路由可以复用既有协议。

### 3.6 AgentScope Runtime

第一阶段 AgentScope 有显式技术落点，但只作为 Shell Adapter / event adapter 验证线，不进入 BI 主链 runtime。

后续接入条件：

- `AgentScopeShellAdapter` 已证明只能通过 `ask_bi` 使用 BI 能力。
- `capability_manifest`、Capability Router、ToolAdapter、EventEnvelope 和真实链路验收全部稳定。
- `AgentScopeEventAdapter` 能证明不改变现有业务真相源。
- AgentScope 不替代 Datalogue 的 conversation_state、query_artifact、Manifest、SQL Guard 和业务审计。

---

## 四、后续改造触发条件

只有满足以下条件，才进入 C-ready 增强能力实施：

1. P0 智能问数主链路通过分层验收中的五件套一致。
2. `capability_manifest` 可以稳定支撑 LeadAgent 不看 schema 明细完成路由。
3. `ask_bi` 出参能稳定返回 answer、event envelope、artifact card、主引用和辅助引用。
4. `ArtifactCard`、Action Registry、引用句柄和事件协议在 Chat 中完成最小闭环。
5. `AgentScopeShellAdapter` 已证明只能调用 `ask_bi`，不能绕过 BI 工具面。
6. 预留动作没有触发未实现增强链路，也没有暴露 `control_plane` 主体。

---

## 五、决策映射

- `010`：产品目标直接采用 C 形态，但 BI 内核保持 B-governed。
- `011`：Agentic Shell 第一阶段采用 Chat 入口加工作台协议。
- `012`：Chat 内任务展示采用业务级时间线，并预留双层展开。
- `013`：产物详情采用 Chat 轻量卡，并预留详情面板。
- `014`：轻量产物卡采用统一 `ArtifactCard` 壳。
- `015`：`preview_payload` 采用半强 schema。
- `016`：`actions` 采用固定注册表加受控动作实例。
- `017`：`refs` 拆分为 `primary_ref` 与 `related_refs`。
- `018`：`export` 第一阶段禁用预留。
- `019`：`continue_edit` 第一阶段只作为详情面板预留动作。
- `020`：`ask_bi` 采用最小稳定契约并复用现有主链。
- `021`：`retry` 第一阶段从最后安全检查点重试。
- `022`：主链路验收采用分层验收。
- `025`：AgentScope 第一阶段作为 Shell Adapter 显式接入，但不接管 BI 主链。
- `027`：`SOUL.md` 抽成 Datalogue 内部契约，再同步到外部入口。
- `028`：SQL 方言适配第一阶段只覆盖当前真实数据源。
- `029`：旧会话不支持 ArtifactCard 等新协议历史回放。
