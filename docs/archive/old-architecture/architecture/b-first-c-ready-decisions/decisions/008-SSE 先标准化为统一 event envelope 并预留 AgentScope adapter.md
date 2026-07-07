# 008 · SSE 先标准化为统一 event envelope 并预留 AgentScope adapter

## 状态

- 状态：已敲定
- 时间：2026-06-26 11:37
- 触发：用户确认“先把现有 SSE 标准化成统一 event envelope，再为 AgentScope event stream 预留 adapter；不要第一阶段直接替换 SSE”

---

## 决策

当前 `/chat/stream` 的 SSE 不在第一阶段被 AgentScope event stream 直接替换。

第一阶段采用：

```text
现有 SSE
  -> 标准化为统一业务 event envelope
  -> 为未来 AgentScope event stream 预留 adapter
```

也就是说，业务事件先统一命名、统一 payload、统一 trace metadata 和安全边界；AgentScope event stream 后续作为外层 runtime adapter 接入，而不是第一阶段接管现有 Web Chat 流式链路。

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
007：DatasetAgentToolAdapter 先兼容迁移，后续强制改造成细分语义块
```

在这个基础上，需要决定事件流如何演进。当前 Datalogue 已有 `/chat/stream`、SSE、前端展示、后端 checkpoint 日志、conversation_state、artifact 和 Langfuse trace。如果第一阶段直接替换成 AgentScope event stream，会同时影响用户可见流式体验、状态落库和真实链路验收面。

---

## 选择理由

选择“现有 SSE 标准化 + AgentScope adapter 预留”的原因：

- 保持当前 Web Chat 流式链路稳定，避免第一阶段替换运行时外壳带来大范围回归。
- 先把业务事件语义标准化，后续无论 SSE、AgentScope event stream 还是外部 Agentic Shell 都能复用。
- 事件标准化比 runtime 替换更接近当前 B-first 目标：先收业务边界，再接运行时能力。
- 可以继续沿用现有真实链路验收口径：页面、SSE、后端日志、Langfuse trace、query_artifact、final payload 交叉核对。
- 为 AgentScope 接管 event stream 留出 adapter，而不是把 AgentScope 直接嵌进当前所有状态流转。

---

## 被排除方案

### 方案一：只做业务事件抽象，不改现有 SSE 输出

未采用。

原因：

- 抽象如果不落到现有 SSE envelope，就难以被前端、trace 和测试真实使用。
- 后续 AgentScope adapter 仍需要再次整理事件结构。
- 不能及时解决当前事件命名、payload、trace metadata 不统一的问题。

### 方案二：第一阶段直接引入 AgentScope event stream

未采用。

原因：

- 改动面过大，会牵动 `/chat/stream`、前端流式展示、状态落库、多轮回放、trace 和测试。
- 容易把“运行时接入”提前成主任务，偏离 B-first 的能力路由收敛目标。
- AgentScope 的 session/event stream 不应替代 Datalogue 的 conversation_state、query_artifact、Manifest 和业务审计真相源。

---

## 对架构的影响

统一 event envelope 建议形态：

```yaml
event:
  type: dataset.query.completed
  version: datalogue.event.v1
  run_id: ...
  conversation_id: ...
  message_id: ...
  trace_id: ...
  timestamp: ...
  visibility: user_visible | trace_only | control_plane
  payload:
    ...
  refs:
    result_ref: ...
    report_ref: ...
    query_artifact_id: ...
  metadata:
    dataset_id: ...
    schema_version: ...
    source: lead_agent | dataset_agent | adapter
```

第一阶段事件流：

```text
业务链路
  -> event envelope
  -> SSE serializer
  -> Web Chat 前端
```

未来 AgentScope 接入：

```text
业务链路
  -> event envelope
  -> AgentScopeEventAdapter
  -> AgentScope event stream
```

强约束：

```text
event envelope 不携带 raw SQL、完整结果集、capsule 主体
control_plane 事件不直接发给前端或外层 Agentic Shell
AgentScope event stream 只消费标准化事件，不反向替代业务真相源
```

---

## 对开发计划的影响

后续至少需要拆出这些任务：

- 定义 `DatalogueEventEnvelope` schema。
- 定义事件类型枚举，例如 `route.started`、`dataset.selected`、`clarification.required`、`dataset.query.started`、`dataset.query.completed`、`artifact.created`、`answer.completed`、`error.blocked`。
- 定义 `visibility` 语义：`user_visible`、`trace_only`、`control_plane`。
- 将现有 `/chat/stream` SSE 输出映射到 event envelope。
- 增加 SSE serializer，确保前端仍能消费现有流式输出。
- 增加 AgentScope event stream adapter 的接口占位，但第一阶段不替换 SSE。
- 增加事件泄露扫描，阻止 raw SQL、完整结果集、capsule 主体进入 user-visible event。
- 增加链路验收：页面事件、SSE payload、后端日志、Langfuse observation、artifact 写入必须能互相对齐。

---

## 后续问题

下一个需要敲定的问题：

```text
AgentScope 第一阶段优先接 runtime/event stream，还是先接 remote runner？
```

可选方向：

```text
先接 runtime/event stream adapter
先接 remote DatasetAgent runner
先只保留 AgentScope MVP 测试线，不进入主链
```

当前初始倾向：

```text
第一阶段主链先不接 AgentScope runtime；先完成 event envelope 和 adapter 预留。AgentScope 继续作为 MVP / runner 验证线，等 B 的业务边界稳定后再接主链 runtime。
```
