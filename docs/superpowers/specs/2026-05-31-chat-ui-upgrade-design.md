# Chat UI 升级设计文档

**日期**: 2026-05-31  
**状态**: 已审批  
**范围**: `datalogue-web/src/components/chat.jsx`、`datalogue-web/src/api/client.js`、`datalogue-api/app/api/chat.py`

---

## 目标

将现有对话栏升级为：
1. 真正的 token 级流式输出（打字机效果）
2. 右侧可开关的 Agent 执行状态面板
3. 消息气泡保持卡片风格，去掉内嵌步骤 pills

---

## 选型决策

| 维度 | 决定 | 备注 |
|---|---|---|
| 整体布局 | 主聊天区 + 右侧 Agent 面板 | flex-row 布局 |
| 消息气泡 | 卡片气泡（延续现有风格） | 去掉内嵌 step pills |
| 流式效果 | 真 token 流（`astream_events`）| 所有 LLM 节点均推 token |
| 面板内容 | 节点进度 + 意图解析 + SQL预览 + 执行摘要 | 全部 4 个模块 |
| 面板开关 | 顶栏「推理过程」按钮手动切换 | 复用现有 `traceOpen` 状态 |

---

## 后端改造

### 文件：`app/api/chat.py`

**改动**：将 `graph.astream()` 替换为 `graph.astream_events(version="v2")`。

#### SSE 事件格式（新增 `type` 字段）

```jsonc
// 节点进度（原有逻辑保留，新增 type 字段）
{"type": "step", "node": "intent_recognition", "status": "running"}
{"type": "step", "node": "intent_recognition", "status": "done", "intent": "query", "entities": {...}}
{"type": "step", "node": "schema_recall", "status": "done", "schema_summary": [...]}
{"type": "step", "node": "dsl_compiler", "status": "done", "sql": "SELECT ..."}
{"type": "step", "node": "sql_execute", "status": "done", "rows": 100, "columns": [...]}

// LLM token（新增）
{"type": "token", "content": "当"}
{"type": "token", "content": "前"}

// 结束元数据（原 Final 事件，改名并简化）
{"type": "final", "sql": "SELECT ...", "sql_list": [...]}
```

#### 事件监听逻辑

```python
async for event in graph.astream_events(initial_state, version="v2"):
    kind = event["event"]
    node = event.get("name", "")

    if kind == "on_chain_start" and node in NODE_DISPLAY_NAMES:
        yield {"data": json.dumps({"type": "step", "node": node, "status": "running", ...})}

    elif kind == "on_chain_end" and node in NODE_DISPLAY_NAMES:
        # 同现有 _emit_node_event 逻辑，补充 type="step"
        yield {"data": json.dumps({"type": "step", "node": node, "status": "done", ...})}

    elif kind == "on_chat_model_stream":
        token = event["data"]["chunk"].content
        if token:
            yield {"data": json.dumps({"type": "token", "content": token})}
```

**最后**，在所有节点事件推完后推送 `type="final"` 替代现有 `type="Final"` 节点。

---

## 前端改造

### 新增文件：`src/components/agent-panel.jsx`

无内部状态的纯展示组件，所有数据由 `ChatScreen` 通过 props 传入。

```jsx
// Props 接口
AgentPanel({
  open,           // boolean — 是否显示
  onClose,        // () => void
  steps,          // {node, display_name, status, ...}[]
  intent,         // {intent, entities} | null
  sql,            // string | null
  sqlResult,      // {rows, columns, elapsed_ms} | null
})
```

**内部结构**：

```
AgentPanel (width:280px, position in flex-row)
├── Header: "Agent 执行过程" + ✕ 关闭按钮
├── StepList
│   └── 每个节点一行：图标(✓/⟳/○) + 名称 + 耗时
├── IntentCard (intent 非 null 时显示)
│   └── 意图类型 + 指标/维度 tags
├── SqlPreview (sql 非 null 时显示)
│   └── 代码块 + 复制按钮
└── ResultSummary (sqlResult 非 null 时显示)
    └── 返回行数 + 执行耗时 两格卡片
```

---

### 修改：`src/api/client.js`

`streamChat` 回调扩展，增加 `onToken`：

```js
// 新签名
streamChat(payload, { onToken, onEvent, onDone, onError })

// ReadableStream 分发逻辑（现有逻辑基础上按 type 分发）
if (data.type === "token")  → onToken?.(data.content)
if (data.type === "step")   → onEvent?.(data)
if (data.type === "final")  → onDone?.(data)
```

---

### 修改：`src/components/chat.jsx`

#### 新增 state

```js
const [streamingAnswer, setStreamingAnswer] = useState('');  // token 追加目标
const [intent, setIntent]         = useState(null);
const [sqlResult, setSqlResult]   = useState(null);
```

#### handleSend 回调变更

```js
onToken: (token) => {
  setStreamingAnswer(prev => prev + token);   // 真打字效果
},
onEvent: (data) => {
  // step 类型分发到对应 state
  if (data.node === 'intent_recognition' && data.status === 'done')
    setIntent({ intent: data.intent, entities: data.entities });
  if (data.node === 'dsl_compiler' && data.status === 'done')
    setStreamSql(data.sql);
  if (data.node === 'sql_execute' && data.status === 'done')
    setSqlResult({ rows: data.rows, columns: data.columns });
  // step 进度继续写 traceStepsRef（不变）
  ...
},
onDone: (finalData) => {
  const answer = cleanAnswer(streamingAnswerRef.current);  // ref 读最新值
  setMessages(prev => [...prev, { role:'assistant', content: answer, sql: finalData.sql, ... }]);
  setStreamingAnswer('');
  setIntent(null);
  setSqlResult(null);
  setStreamSql('');
  setIsStreaming(false);
},
```

> `streamingAnswer` 同样需要用 `useRef` 镜像（`streamingAnswerRef`），原因同 `traceStepsRef`。

#### 布局变更

```jsx
// 现有
<div className="chat-layout">
  <div className="chat-main">...</div>
  {traceOpen && <TracePanel />}   // ← 删除
</div>

// 新布局
<div className="chat-layout">           {/* flex-row */}
  <div className="chat-main">
    ...
    {/* 流式气泡：token 到达即显示 */}
    {isStreaming && (streamingAnswer || traceSteps.length > 0) && (
      <AIMessageStreaming answer={streamingAnswer} />
    )}
  </div>
  <AgentPanel
    open={traceOpen}
    onClose={() => setTraceOpen(false)}
    steps={traceSteps}
    intent={intent}
    sql={streamSql}
    sqlResult={sqlResult}
  />
</div>
```

#### CSS 变更（`styles.css`）

```css
.chat-layout {
  display: flex;
  flex-direction: row;  /* 改为横向 */
  height: 100%;
}

.chat-main {
  flex: 1;
  min-width: 0;  /* 防止 flex 子元素溢出 */
}

.agent-panel {
  width: 280px;
  flex-shrink: 0;
  border-left: 1px solid var(--border);
  overflow-y: auto;
}
```

#### 删除

- `StreamStepBar` 组件（逻辑移入 `AgentPanel`）
- `TracePanel` 组件（被 `AgentPanel` 替代）
- AI 消息气泡内的 `{msg.steps && <StreamStepBar />}`（steps 不再存入 message 对象）

---

## 数据流

```
用户发送问题
    │
    ▼
streamChat() — fetch /api/chat/stream (ReadableStream)
    │
    ├─ type="step" ──→ setTraceSteps / setIntent / setStreamSql / setSqlResult
    │                  (AgentPanel 实时更新)
    │
    ├─ type="token" ─→ setStreamingAnswer(prev + token)
    │                  (AIMessageStreaming 打字效果)
    │
    └─ type="final" ─→ setMessages([...prev, { role:'assistant', content, sql }])
                       清空所有 streaming state
                       (AgentPanel 内容保留到用户关闭)
```

---

## 不在本次范围内

- 会话列表（独立侧边栏）— 留到后续迭代
- Tool 调用可视化 — 留到后续迭代
- 图表在面板内展示 — 留到后续迭代
- `TracePanel` 的「推理过程」右侧抽屉 — 由 `AgentPanel` 替代，旧代码删除

---

## 文件变更清单

| 文件 | 变更类型 |
|---|---|
| `app/api/chat.py` | 修改：astream → astream_events，SSE 格式加 type 字段 |
| `src/api/client.js` | 修改：streamChat 增加 onToken 回调 |
| `src/components/agent-panel.jsx` | **新建** |
| `src/components/chat.jsx` | 修改：新增 streaming state、布局改为 flex-row、删除 TracePanel/StreamStepBar |
| `src/styles.css` | 修改：chat-layout flex-direction、新增 .agent-panel 样式 |
