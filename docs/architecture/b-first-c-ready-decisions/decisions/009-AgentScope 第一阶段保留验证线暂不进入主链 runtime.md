# 009 · AgentScope 第一阶段保留验证线暂不进入主链 runtime

## 状态

- 状态：已敲定
- 时间：2026-06-26 11:44
- 触发：用户确认“先按照方案3来做，然后记录后续要做的工作”

---

## 决策

AgentScope 第一阶段不进入 Datalogue 主链 runtime。

第一阶段主链先完成：

```text
B-first 能力路由
capability_manifest
LeadAgent Capability Router
DatasetAgentToolAdapter
DatalogueEventEnvelope
query_dataset / query_multiple_datasets
llm_visible / control_plane / trace_metadata
```

AgentScope 暂时保留为：

```text
MVP 验证线
runner 验证线
event adapter 验证线
```

等 B 的业务边界稳定后，再评估 AgentScope runtime、event stream、remote runner、middleware、permission、workspace 等能力进入主链的顺序。

---

## 背景

前面已经确认：

```text
001：capability_manifest 定位为轻量能力广告
002：capability_manifest 采用固化主体 + 运行态叠加
003：static_capability 字段边界只到业务摘要层
004：can_answer 等能力文案采用模型辅助生成 + 人工审核，发布时固化
005：LeadAgent 低置信路由采用候选数据集确认式澄清
006：query_multiple_datasets 采用保守 + 少量半自动 fan-out
007：DatasetAgentToolAdapter 先兼容迁移，后续强制细分语义块
008：SSE 先标准化为统一 event envelope，并预留 AgentScope event stream adapter
```

在这个基础上，需要决定 AgentScope 第一阶段接入位置。当前最核心的风险不是 AgentScope 能不能跑，而是 Datalogue 的业务能力边界还在收敛：LeadAgent 看什么、DatasetAgent 藏什么、结果怎么分层、事件怎么标准化、业务真相源在哪里。

---

## 选择理由

选择“先保留验证线，暂不进入主链 runtime”的原因：

- 避免把第一阶段变成框架迁移，而不是能力路由治理。
- 先保证 Datalogue 的业务边界、状态真相源、Artifact、Trace 和 event envelope 稳定。
- 防止 AgentScope session/memory/event stream 与 Datalogue conversation_state/query_artifact/Manifest 产生真相源混淆。
- 保留 AgentScope 的价值验证，不把它丢掉，只是延后进入主链。
- 现有 AgentScope MVP 已能验证 tool calling、LiteLLM 适配、Hermes-style tool exposure 和 ReAct-style 执行链路，可以继续作为实验线推进。

---

## 被排除方案

### 方案一：第一阶段先接 runtime / event stream adapter

未采用。

原因：

- 会过早把主任务从能力边界收敛变成运行时适配。
- 当前 `DatalogueEventEnvelope` 还未落地，直接接 AgentScope event stream 容易导致事件语义和业务状态一起漂移。
- 与 `008` 决策冲突：第一阶段不直接替换 SSE。

### 方案二：第一阶段先接 remote DatasetAgent runner

未采用为主线。

原因：

- remote runner 会提前引入认证、权限上下文、trace 贯通、artifact 写入、失败重试、跨进程错误脱敏等生产级问题。
- DatasetAgentToolAdapter v1/v2 还未稳定，远程化接口容易反复改。
- 可以作为验证线继续推进，但不应成为第一阶段主链任务。

---

## 对架构的影响

第一阶段主链：

```text
Datalogue Web Chat
  -> /chat/stream
  -> LeadAgent Capability Router
  -> DatasetAgentToolAdapter
  -> DatasetAgent Runtime
  -> QueryArtifact / Trace / Final Answer
```

AgentScope 验证线：

```text
AgentScope MVP
  -> Datalogue capability tools
  -> guarded SQL preview / DatasetAgent capability
  -> react_trace / tool observation
```

未来接入路径：

```text
DatalogueEventEnvelope
  -> AgentScopeEventAdapter

DatasetAgentToolAdapter
  -> AgentScope Remote Runner Adapter

BIWorkbenchTool / ask_bi
  -> AgentScope Agentic Shell
```

强约束：

```text
AgentScope 不替代 Datalogue conversation_state
AgentScope 不替代 query_artifact
AgentScope 不替代 Manifest / SQL Guard / Audit
AgentScope 第一阶段不接管 /chat/stream
```

---

## 后续要做的工作

### A. 保留并强化 AgentScope MVP 验证线

- 继续维护 `tests/agentscope_react_mvp` 或同等实验目录。
- 保留 Hermes-style 最小能力暴露验证。
- 保留 LiteLLM AgentScope 适配验证。
- 保留 react_trace / tool observation 输出。
- 增加与 `capability_manifest`、`DatasetAgentToolAdapter`、`DatalogueEventEnvelope` 对齐的实验用例。

### B. 准备 AgentScopeEventAdapter

- 等 `DatalogueEventEnvelope` schema 稳定后，设计 `AgentScopeEventAdapter`。
- 验证哪些事件适合映射到 AgentScope event stream。
- 明确 `user_visible`、`trace_only`、`control_plane` 三类事件在 AgentScope 里的承接方式。
- 确认 raw SQL、完整结果集、capsule 主体不会进入 AgentScope 可见上下文。

### C. 准备 Remote Runner Adapter

- 等 `DatasetAgentToolAdapter` v1 稳定后，设计 remote runner 调用协议。
- 验证 `dataset_id/question/context/runtime_overlay` 如何跨进程传递。
- 验证 `llm_visible/control_plane/trace_metadata` 如何跨进程返回。
- 验证 artifact、trace_id、权限上下文和错误脱敏的传递规则。

### D. 准备 Agentic Shell 接入

- 等 `BIWorkbenchTool` 或 `ask_bi` 入口稳定后，验证 AgentScope 外层 Agent 如何调用 BI 能力。
- 外层 Agent 只能消费 `llm_visible`。
- 外层 Agent 只能引用 `result_ref/report_ref`，不能展开 control plane 主体。
- ReportAgent / PythonAgent / AuditAgent 通过 BI 能力入口协作，不绕过 DatasetAgent。

### E. 定义进入主链的闸门

AgentScope 进入主链 runtime 前，至少要满足：

- `capability_manifest` 已稳定。
- LeadAgent Capability Router 已稳定。
- `DatasetAgentToolAdapter` v1 已稳定，并且 v2 迁移计划明确。
- `DatalogueEventEnvelope` 已接入现有 SSE。
- 页面、SSE、后端日志、Langfuse trace、query_artifact、final payload 可以交叉核对。
- AgentScope adapter 验证线证明不会替代业务真相源。

---

## 对开发计划的影响

后续计划需要把 AgentScope 拆成“验证线”和“主链接入线”：

- 第一阶段：AgentScope 只在验证线推进。
- 第二阶段：根据 B-first 主链稳定情况，选择 event adapter 或 remote runner adapter 作为主链接入试点。
- 第三阶段：再考虑 Agentic Shell、ReportAgent、PythonAgent、AuditAgent 的多 Agent runtime。

---

## 后续问题

下一个需要敲定的问题：

```text
ReportAgent、PythonAgent、AuditAgent 与 BIWorkbenchTool 的协作边界是什么？
```

可选方向：

```text
先不设计这些 Agent，只保留接口名
先定义 BIWorkbenchTool 为唯一 BI 入口，再让其他 Agent 调用它
直接按 C 架构设计完整 Agentic Shell
```

当前初始倾向：

```text
先定义 BIWorkbenchTool / ask_bi 为唯一 BI 入口；ReportAgent、PythonAgent、AuditAgent 只能消费 BI 返回的 llm_visible 和 result_ref/report_ref，不能绕过 BI 入口访问 schema、SQL 或数据库。
```
