# 007 · DatasetAgentToolAdapter 先兼容迁移后强制细分语义块

## 状态

- 状态：已敲定
- 时间：2026-06-26 11:34
- 触发：用户确认“先做方案3，然后后续改造成方案2，要明确方案2一定要做”

---

## 决策

`DatasetAgentToolAdapter` 的出参协议采用两阶段路线：

```text
第一阶段：方案 3，兼容迁移协议
后续阶段：必须改造成方案 2，三段式 + 细分语义块
```

也就是说，第一阶段可以用 adapter 包裹现有 `SubAgentToolResult`，但这只是迁移手段，不是最终形态。最终必须形成明确的三段式协议，并在三段内细分 `result / artifact / error / clarification` 等语义块。

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
```

在这些决策下，DatasetAgent 必须成为 LeadAgent 和未来外层 Agentic Shell 可安全调用的稳定能力。因此，DatasetAgent 的出参边界必须明确：哪些内容可以进入 LLM context，哪些内容只能在控制面流转，哪些内容用于 trace 和审计。

---

## 选择理由

选择“两阶段路线”的原因：

- 第一阶段直接做方案 2 会牵动现有 `SubAgentToolResult`、conversation_state、artifact、多轮状态和 `/chat/stream`，风险较高。
- 方案 3 可以先把安全边界立起来：LeadAgent 只读 `llm_visible`，控制面细节只放 `control_plane`。
- 方案 3 不应成为长期状态，否则 legacy 结构会长期滞留在控制面，影响测试、前端展示、trace 分类和未来 Agentic Shell 调用。
- 方案 2 是更适合生产治理的最终协议，必须进入后续计划，而不是“以后有空再说”。

---

## 被排除方案

### 方案一：只做三段式基础协议，不继续细分

未采用。

原因：

- 只能表达大边界，不能很好地区分结果、产物、错误、澄清等业务语义。
- 对前端展示、测试断言、Langfuse metadata 和错误治理不够友好。
- 容易让 `llm_visible` 内部继续混杂多种语义。

### 方案二：第一阶段直接全量改成细分语义块

未采用为第一阶段方案，但确认为后续必须目标。

原因：

- 目标正确，但第一阶段直接全量改造风险偏大。
- 会同时牵动 SubAgent、Artifact、ConversationState、多轮回放、SSE 和测试。
- 更合理的路径是先包一层兼容 adapter，再逐步把 legacy 字段迁移到正式语义块。

### 方案三：长期停留在兼容 wrapper

明确不采用。

原因：

- legacy 结构长期存在会让控制面越来越重。
- 未来 Agentic Shell、ReportAgent、PythonAgent 等外层能力很难稳定依赖。
- 会导致“表面有三段式，内部仍然不可治理”的问题。

---

## 对架构的影响

第一阶段目标结构：

```yaml
DatasetAgentToolAdapterResult:
  llm_visible:
    status: success | clarification_required | blocked | failed
    display_summary: ...
    clarification_question: ...
    error_summary: ...
    dataset_id: ...
    result_ref: ...
    report_ref: ...

  control_plane:
    legacy_subagent_result: ...
    capsule: ...
    query_artifact_id: ...
    last_success_task: ...
    raw_error: ...

  trace_metadata:
    schema_version: datalogue.dataset_agent_tool_result.v1
    adapter_mode: legacy_wrapped
    dataset_id: ...
    guard_status: ...
```

后续必须目标结构：

```yaml
DatasetAgentToolAdapterResult:
  llm_visible:
    status: ...
    result:
      display_summary: ...
      key_findings: ...
      result_ref: ...
      report_ref: ...
    clarification:
      question: ...
      options: ...
      reason: ...
    error:
      code: ...
      message: ...
      recoverable: ...

  control_plane:
    artifact:
      query_artifact_id: ...
      result_ref: ...
      report_ref: ...
    capsule:
      last_success_task: ...
      selected_assets_ref: ...
    execution:
      raw_sql_ref: ...
      sql_guard: ...
      raw_result_ref: ...
      row_count: ...
    error:
      raw_error_ref: ...
      stack_ref: ...

  trace_metadata:
    schema_version: datalogue.dataset_agent_tool_result.v2
    route: ...
    guard: ...
    timing: ...
```

强约束：

```text
legacy_subagent_result 只能存在于 control_plane
legacy_subagent_result 永不进入 llm_visible
外层 Agentic Shell 永远只能消费 llm_visible
方案 2 必须进入后续里程碑，不能被标记为 optional
```

---

## 对开发计划的影响

后续至少需要拆出这些任务：

- 定义 v1 兼容迁移协议。
- 在 v1 中包裹现有 `SubAgentToolResult`，但只允许它进入 `control_plane`。
- 增加 `llm_visible` size guard 和泄露扫描。
- 增加 `trace_metadata.schema_version` 和 `adapter_mode`。
- 定义 v2 细分语义块 schema。
- 规划 v1 -> v2 迁移任务，明确 v2 是必做里程碑。
- 为 `result / artifact / error / clarification` 分别补测试。
- 在 v2 完成后逐步移除 `legacy_subagent_result` 对上层链路的依赖。

---

## 后续问题

下一个需要敲定的问题：

```text
当前 SSE 事件如何映射未来 AgentScope event stream？
```

可选方向：

```text
只做业务事件抽象，不急着接 AgentScope
先映射现有 SSE 到统一 event envelope
直接引入 AgentScope event stream 做外层承载
```

当前初始倾向：

```text
先映射现有 SSE 到统一业务 event envelope，再为 AgentScope event stream 预留 adapter；不要第一阶段直接替换 SSE。
```
