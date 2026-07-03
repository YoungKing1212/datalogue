# Datalogue QueryGraph 子 Agent 架构设计

> Phase 4.3 产物 — 2026-07-03

## 背景

当前 Datalogue 的 BI Agent 执行链路是一个单一黑盒：LeadAgent 路由 → BI Agent 工具链（7 个原子工具串行执行）→ 最终结果。前端只能看到"已转交问数 Agent"和工具执行进度，无法感知 query graph 各节点的内部推理状态。

## 目标

将 query graph 的核心节点建模为**独立子 Agent**，每个子 Agent 产生独立的 reasoning + tool_call 流，前端通过 `MessagePartPrimitive.Messages` 递归渲染，实现完整的 Agent 工作台可视化。

## 节点 → 子 Agent 映射

| QueryGraph 节点 | 子 Agent 名称 | 职责 | 输入 | 输出 |
|----------------|-------------|------|------|------|
| `schema_recall` | SchemaAgent | 召回并过滤相关表/Schema | dataset_id, question | filtered_schema_context |
| `term_normalize` | TermAgent | 术语归一化、歧义消解 | question, business_terms | normalized_terms |
| `semantic_asset_resolution` | AssetAgent | 解析语义指标/维度 | normalized_terms, schema | resolved_metrics, resolved_dimensions |
| `dsl_generate` | DSLAgent | 生成 DSL | resolved_assets, schema, question | dsl_v2_json |
| `dsl_validate` | ValidatorAgent | 校验 DSL | dsl_v2_json, schema | validation_result |
| `dsl_compiler` | CompilerAgent | 编译 DSL → SQL | validated_dsl, schema | compiled_sql |
| `sql_execute` | ExecutorAgent | 只读执行 SQL | compiled_sql | query_result |
| `sql_audit` | AuditAgent | 失败诊断与修复 | error, sql, schema | diagnosis, repair_plan |
| `report_generator` | ReportAgent | 生成中文洞察 | question, query_result, caliber | report_text |

## SSE 事件协议设计

### 新增事件类型

```
agent.handoff.started     → 父 Agent 将任务委派给子 Agent
agent.handoff.completed   → 子 Agent 完成任务，回传结果
agent.reasoning.delta     → 子 Agent 推理增量
agent.tool_call.started   → 子 Agent 工具调用开始
agent.tool_call.completed → 子 Agent 工具调用完成
```

### 嵌套模型

```json
{
  "event_type": "agent.handoff.started",
  "parent_agent": "bi_agent",
  "child_agent": "dsl_agent",
  "handoff_id": "handoff-abc123",
  "input": { "question": "...", "resolved_metrics": [...] }
}
```

子 Agent 的所有流式事件（reasoning.delta、tool_call.*）在 `handoff_id` 作用域内产生，直到 `agent.handoff.completed` 关闭作用域。

## 后端实现要点

### 1. 核心文件改动

```
app/agents/sub_agents/          ← 新增目录
  schema_agent.py               ← Schema 召回子 Agent
  term_agent.py                  ← 术语归一化子 Agent
  dsl_agent.py                   ← DSL 生成子 Agent
  compiler_agent.py              ← SQL 编译子 Agent
  executor_agent.py              ← SQL 执行子 Agent
  audit_agent.py                 ← 审计修复子 Agent
  report_agent.py                ← 报告生成子 Agent

app/runtime/task_runtime.py     ← AgenticShellTaskRuntime.stream() 支持嵌套 handoff
app/events/projection.py         ← agent.* 事件映射
app/schemas/bi_workbench.py      ← agent.handoff.* 事件 schema
```

### 2. SubAgent 基类设计

```python
class QueryGraphSubAgent:
    agent_id: str                 # 子 Agent 唯一标识
    parent_agent_id: str          # 父 Agent ID
    handoff_id: str               # handoff 作用域 ID

    async def execute(self, context: SubAgentContext) -> AsyncIterator[dict]:
        """执行子 Agent 逻辑，yield 标准化事件流。"""
        ...
```

### 3. 事件流透传

```python
# AgenticShellTaskRuntime.stream() 中：
async for event in runner.stream(...):
    if event.type == "agent.handoff.started":
        # 创建嵌套作用域
        child_scope = ChildAgentScope(
            handoff_id=event.handoff_id,
            parent_agent=event.parent_agent,
            child_agent=event.child_agent,
        )
```

## 前端实现要点

### Multi-Agent ChatUI 渲染

```jsx
// MyMessage.jsx — GroupedParts 中新增
case 'group-agent-handoff':
  return (
    <div className="agent-handoff-card">
      <div className="agent-handoff-header">
        <Icon name="agent" />
        <span>{fromLabel} → {toLabel}</span>
      </div>
      <div className="agent-handoff-body">
        {/* MessagePartPrimitive.Messages 递归渲染子 Agent 消息 */}
        {children}
      </div>
    </div>
  );
```

### 子 Agent 消息卡片

```
┌─ 🔄 路由 Agent → 问数 Agent ──────────┐
│  📊 指标解析 · 2.3s                    │
│  📝 DSL 生成 · 正在执行…                │
│  ⚡ SQL 执行 · 42 行 8 列 · 1.2s       │
│  📋 结果整理 · 已完成                    │
└────────────────────────────────────────┘
```

## 分阶段推进路线

| 阶段 | 内容 | 工期 |
|------|------|------|
| M1 | 定义 SubAgent 基类和事件协议 | 2 天 |
| M2 | 拆分 `schema_recall` + `dsl_generate` 为独立子 Agent | 3 天 |
| M3 | 后端 SSE 流支持嵌套 handoff | 3 天 |
| M4 | 前端 Multi-Agent Card 渲染 | 3 天 |
| M5 | 拆分剩余节点（audit/report/executor） | 2 天 |
| M6 | 端到端联调 + 回归测试 | 2 天 |

**总计**: 约 15 个工作日

## 当前 Phase 4 已实现的 MVP

- ✅ `agent.handoff.started` 事件（LeadAgent → BI Agent）
- ✅ 前端 Agent 切换标识（reasoning part: "已转交 问数 Agent"）
- ✅ `agent.handoff.*` 事件类型在 schema 中已定义
- ✅ 工具调用事件透传（`tool_call.started/completed/failed`）
- ✅ 消息分组框架（`MessagePrimitive.GroupedParts` + `groupPartByType`）
