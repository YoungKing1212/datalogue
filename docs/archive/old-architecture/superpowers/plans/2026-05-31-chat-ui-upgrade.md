# Chat UI 升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将对话栏升级为真 token 流打字效果 + 右侧 Agent 面板 + 会话切换支持。

**Architecture:** 后端换用 `graph.astream_events(version="v2")` 发送 `type=token/step/final` 三类 SSE 事件；前端新建 `AgentPanel` 组件接收进度/SQL/意图/执行摘要，`ChatScreen` 改为 flex-row 布局并用 `useParams` 加载历史会话；侧边栏从后端拉取真实会话列表。

**Tech Stack:** Python 3.12 · FastAPI · LangGraph · LangChain · React 19 · Vite

---

## 文件变更清单

| 文件 | 变更 |
|---|---|
| `datalogue-api/app/graph/llm.py` | 新增 `streaming=True` |
| `datalogue-api/app/api/chat.py` | 替换 `astream` → `astream_events`，重构 SSE 事件格式 |
| `datalogue-api/tests/test_chat.py` | 更新测试以匹配新 SSE 格式 |
| `datalogue-web/src/App.jsx` | 修复 TopBar CRUMBS_MAP 崩溃 |
| `datalogue-web/src/styles.css` | 新增 `.agent-panel` 样式，`.chat-layout` 改为 flex-row |
| `datalogue-web/src/api/client.js` | `streamChat` 增加 `onToken` 回调，按 `type` 字段分发 |
| `datalogue-web/src/components/agent-panel.jsx` | 新建：进度/意图/SQL/执行摘要四模块 |
| `datalogue-web/src/components/chat.jsx` | 新增 streaming state + ref、flex-row 布局、history 加载、删除 TracePanel/StreamStepBar |
| `datalogue-web/src/components/sidebar.jsx` | 从后端拉取会话列表，点击导航到 `/chat/:id` |

---

## Task 1: 修复 TopBar 崩溃（App.jsx）

**Files:**
- Modify: `datalogue-web/src/App.jsx:74`

- [ ] **Step 1: 定位问题行**

打开 `datalogue-web/src/App.jsx` 第 74 行，现在的代码是：
```js
const c = CRUMBS_MAP[path] || Object.entries(CRUMBS_MAP).find(([k]) => k !== '/' && path.startsWith(k)) || CRUMBS_MAP['/'];
```
`find()` 返回 `[key, value]` 元组，`c.crumb` 为 undefined 导致 `.map()` 崩溃。

- [ ] **Step 2: 修复**

将第 74 行替换为：
```js
const entry = Object.entries(CRUMBS_MAP).find(([k]) => k !== '/' && path.startsWith(k));
const c = CRUMBS_MAP[path] || (entry ? entry[1] : null) || CRUMBS_MAP['/'];
```

- [ ] **Step 3: 验证**

在浏览器访问 `http://localhost:5173/chat/any-id-here`，页面应正常显示顶栏面包屑「数语 / 问数中心 / 对话问数」，不再白屏。

- [ ] **Step 4: Commit**

```bash
git add datalogue-web/src/App.jsx
git commit -m "fix: TopBar crash on /chat/:id — CRUMBS_MAP find() returns tuple not value"
```

---

## Task 2: CSS — AgentPanel 样式与布局

**Files:**
- Modify: `datalogue-web/src/styles.css`

- [ ] **Step 1: 找到 `.trace-panel` 样式块**

在 `styles.css` 中找到 `.trace-panel {`（约第 664 行）。

- [ ] **Step 2: 在 `.trace-panel` 块之后追加 AgentPanel 样式**

在 `.trace-panel` 相关代码块结束处之后追加：

```css
/* ── Agent Panel ──────────────────────────────── */
.agent-panel {
  width: 280px;
  flex-shrink: 0;
  border-left: 1px solid var(--hairline);
  background: var(--bg-2);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.agent-panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 48px;
  padding: 0 16px;
  border-bottom: 1px solid var(--hairline);
  flex-shrink: 0;
}
.agent-panel-head h3 {
  font-size: 13px;
  font-weight: 500;
  margin: 0;
  flex: 1;
}

.agent-panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.agent-section-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--text-3);
  text-transform: uppercase;
  margin-bottom: 8px;
}

/* 步骤列表 */
.agent-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.agent-step-icon {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.agent-step-icon.done   { background: var(--pos); }
.agent-step-icon.done .icon { width: 9px; height: 9px; color: #0a0a0f; }
.agent-step-icon.running { border: 2px solid var(--accent); border-top-color: transparent; animation: spin 0.8s linear infinite; }
.agent-step-icon.pending { background: var(--surface-2); border: 1px solid var(--hairline); }
.agent-step-label { font-size: 12px; color: var(--text-2); flex: 1; }
.agent-step-label.running { color: var(--accent); }
.agent-step-ms { font-size: 10px; color: var(--text-3); }

/* 意图卡片 */
.intent-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.intent-tag {
  padding: 2px 8px;
  background: var(--accent-soft);
  color: var(--accent);
  border-radius: 10px;
  font-size: 11px;
}

/* SQL 预览 */
.sql-preview {
  border: 1px solid var(--hairline);
  border-radius: 6px;
  overflow: hidden;
}
.sql-preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--hairline);
  font-size: 11px;
  color: var(--accent);
}
.sql-preview pre {
  margin: 0;
  padding: 10px;
  font-size: 11px;
  color: var(--text-2);
  font-family: var(--mono, monospace);
  overflow-x: auto;
  background: var(--bg-1);
}

/* 执行摘要 */
.result-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.result-card {
  background: var(--surface-2);
  border-radius: 6px;
  padding: 8px;
  text-align: center;
}
.result-card .val {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-1);
  line-height: 1.2;
}
.result-card .lbl {
  font-size: 10px;
  color: var(--text-3);
  margin-top: 2px;
}
```

- [ ] **Step 3: 修改 `.chat-layout` 的 `with-trace` class**

找到：
```css
.chat-layout.with-trace { flex-direction: row; }
```
改为：
```css
.chat-layout.with-panel { flex-direction: row; }
```
（class 名改为 `with-panel` 以匹配后续 chat.jsx 的改动）

- [ ] **Step 4: Commit**

```bash
git add datalogue-web/src/styles.css
git commit -m "style: add agent-panel CSS, rename with-trace to with-panel"
```

---

## Task 3: 后端 — 启用 LLM streaming 与 astream_events

**Files:**
- Modify: `datalogue-api/app/graph/llm.py`
- Modify: `datalogue-api/app/api/chat.py`
- Modify: `datalogue-api/tests/test_chat.py`

### 3a — 启用 LLM streaming

- [ ] **Step 1: 修改 `app/graph/llm.py`**

在 `ChatOpenAI(...)` 调用中新增 `streaming=True`：
```python
def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    """获取配置好的 LLM 实例，兼容 OpenAI 格式接口。"""
    return ChatOpenAI(
        model=_settings.LLM_MODEL,
        api_key=_settings.OPENAI_API_KEY or "",
        base_url=_settings.OPENAI_BASE_URL,
        temperature=temperature,
        streaming=True,          # 启用 token 级流式，供 astream_events 捕获
        http_client=httpx.Client(
            proxy="http://127.0.0.1:7897",
            verify=False,
            timeout=60.0,
        ),
    )
```

### 3b — 重构 `app/api/chat.py`

- [ ] **Step 2: 更新测试先（TDD）**

在 `tests/test_chat.py` 找到 `test_chat_stream_basic`，在其后添加新的格式测试：

```python
def test_chat_stream_event_types(self, client, sample_dataset):
    """SSE 流式接口每个事件必须含 type 字段，值为 step / token / final 之一"""
    payload = {"question": "查询所有订单", "dataset_id": sample_dataset.id}
    with patch("app.api.chat.build_workflow") as mock_wf:
        # 模拟 astream_events 返回两个 step 事件和一个 final 事件
        async def fake_astream_events(state, version):
            yield {"event": "on_chain_start",  "name": "intent_recognition", "data": {}, "metadata": {"langgraph_node": "intent_recognition"}}
            yield {"event": "on_chain_end",    "name": "intent_recognition", "data": {"output": {"intent": "query", "entities": {}}}, "metadata": {"langgraph_node": "intent_recognition"}}
            yield {"event": "on_chain_start",  "name": "report_generator",   "data": {}, "metadata": {"langgraph_node": "report_generator"}}
            yield {"event": "on_chat_model_stream", "name": "ChatOpenAI", "data": {"chunk": type("C", (), {"content": "查"})()}, "metadata": {}}
            yield {"event": "on_chat_model_stream", "name": "ChatOpenAI", "data": {"chunk": type("C", (), {"content": "询"})()}, "metadata": {}}
            yield {"event": "on_chain_end",    "name": "report_generator",   "data": {"output": {"answer": "查询完成", "sql": "SELECT 1"}}, "metadata": {"langgraph_node": "report_generator"}}

        mock_graph = MagicMock()
        mock_graph.astream_events = fake_astream_events
        mock_wf.return_value = mock_graph

        resp = client.post("/api/chat/stream", json=payload)
        assert resp.status_code == 200

        lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
        events = [json.loads(l[5:].strip()) for l in lines]
        types = {e["type"] for e in events}
        assert "step" in types
        assert "token" in types
        assert "final" in types

def test_chat_stream_step_event_structure(self, client, sample_dataset):
    """step 事件必须含 node 和 status 字段"""
    payload = {"question": "测试", "dataset_id": sample_dataset.id}
    with patch("app.api.chat.build_workflow") as mock_wf:
        async def fake_astream_events(state, version):
            yield {"event": "on_chain_start", "name": "intent_recognition", "data": {}, "metadata": {"langgraph_node": "intent_recognition"}}
            yield {"event": "on_chain_end",   "name": "intent_recognition", "data": {"output": {}}, "metadata": {"langgraph_node": "intent_recognition"}}
        mock_graph = MagicMock()
        mock_graph.astream_events = fake_astream_events
        mock_wf.return_value = mock_graph

        resp = client.post("/api/chat/stream", json=payload)
        lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
        step_events = [json.loads(l[5:].strip()) for l in lines if '"step"' in l]
        for e in step_events:
            assert "node" in e
            assert "status" in e
            assert e["status"] in ("running", "done")
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd datalogue-api && source .venv/bin/activate
pytest tests/test_chat.py::TestChatAPI::test_chat_stream_event_types -v
```

期望：FAIL（因为还没改 chat.py）

- [ ] **Step 4: 重构 `app/api/chat.py` 中的 `_stream_chat`**

将现有 `_stream_chat` 函数的工作流循环部分（`try:` 块开始到函数末尾）替换为：

```python
    # 构建并运行工作流
    app_graph = build_workflow(db)
    final_state: dict = dict(initial_state)
    last_node: str | None = None
    node_start_times: dict[str, float] = {}

    try:
        import time
        logger.info("[_stream_chat] 开始 astream_events 工作流...")
        async for event in app_graph.astream_events(initial_state, version="v2"):
            kind: str = event["event"]
            name: str = event.get("name", "")
            meta: dict = event.get("metadata", {})
            # langgraph_node 元数据标识当前所属节点
            lg_node: str = meta.get("langgraph_node", name)

            # ── 节点开始 ────────────────────────────────────
            if kind == "on_chain_start" and lg_node in _NODE_DISPLAY_NAMES:
                node_start_times[lg_node] = time.monotonic()
                payload = {
                    "type": "step",
                    "node": lg_node,
                    "display_name": _NODE_DISPLAY_NAMES[lg_node],
                    "status": "running",
                }
                logger.info(f"[_stream_chat] step running: {lg_node}")
                yield {"data": json.dumps(payload, ensure_ascii=False)}

            # ── 节点完成 ────────────────────────────────────
            elif kind == "on_chain_end" and lg_node in _NODE_DISPLAY_NAMES:
                elapsed_ms = int((time.monotonic() - node_start_times.get(lg_node, 0)) * 1000)
                output: dict = event.get("data", {}).get("output", {}) or {}
                # 合并节点输出到 final_state
                if isinstance(output, dict):
                    for k, v in output.items():
                        if v is not None:
                            final_state[k] = v

                payload = {
                    "type": "step",
                    "node": lg_node,
                    "display_name": _NODE_DISPLAY_NAMES[lg_node],
                    "status": "done",
                    "elapsed_ms": elapsed_ms,
                }
                # 节点特定数据
                if lg_node == "intent_recognition":
                    payload["intent"]   = final_state.get("intent") or ""
                    payload["entities"] = final_state.get("entities") or {}
                elif lg_node == "schema_recall":
                    schema = final_state.get("schema_context", "") or ""
                    lines_  = [l for l in schema.split("\n") if l.strip() and not l.startswith("-")]
                    payload["schema_summary"] = lines_[:3]
                elif lg_node == "dsl_compiler":
                    payload["sql"] = final_state.get("sql") or ""
                elif lg_node == "sql_execute":
                    result = final_state.get("sql_result") or {}
                    payload["rows"]       = result.get("row_count", 0)
                    payload["columns"]    = result.get("columns", [])
                    payload["elapsed_ms"] = elapsed_ms
                last_node = lg_node
                logger.info(f"[_stream_chat] step done: {lg_node} ({elapsed_ms}ms)")
                yield {"data": json.dumps(payload, ensure_ascii=False)}

            # ── LLM token ───────────────────────────────────
            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                token: str = getattr(chunk, "content", "") or ""
                if token:
                    yield {"data": json.dumps({"type": "token", "content": token}, ensure_ascii=False)}

        logger.info(f"[_stream_chat] astream_events 完成, last_node={last_node}")

    except Exception as e:
        logger.exception(f"[_stream_chat] 工作流异常: {e}")
        yield {"data": json.dumps({"type": "step", "node": "error", "display_name": "错误", "status": "done"}, ensure_ascii=False)}
        yield {"data": json.dumps({"type": "final", "sql": None, "sql_list": [], "answer": f"处理出错：{e}"}, ensure_ascii=False)}
        return

    # ── 保存助手消息并发送 final 事件 ────────────────
    answer: str = str(final_state.get("answer") or "抱歉，暂时无法回答这个问题。")
    sql       = final_state.get("sql")
    sql_list  = final_state.get("sql_list") or []

    final_payload = {
        "type": "final",
        "sql": sql,
        "sql_list": sql_list,
        "answer": answer,
    }
    logger.info(f"[_stream_chat] final: answer_len={len(answer)}, sql={sql}")
    yield {"data": json.dumps(final_payload, ensure_ascii=False)}

    token_usage = final_state.get("token_usage")
    db.add(models.Message(
        conversation_id=conv_id,
        role="assistant",
        content=answer,
        sql_list=sql_list,
        token_usage=token_usage,
    ))
    db.commit()
```

- [ ] **Step 5: 运行测试确认通过**

```bash
pytest tests/test_chat.py -v
```

期望：全部 PASS（包括新增的两个测试）

- [ ] **Step 6: Commit**

```bash
git add datalogue-api/app/graph/llm.py datalogue-api/app/api/chat.py datalogue-api/tests/test_chat.py
git commit -m "feat(backend): switch to astream_events for token-level SSE streaming

- Add streaming=True to ChatOpenAI
- Replace astream() with astream_events(version='v2')
- New SSE format: type=step/token/final
- Include elapsed_ms in step done events"
```

---

## Task 4: 前端 API — streamChat 增加 onToken

**Files:**
- Modify: `datalogue-web/src/api/client.js:62-104`

- [ ] **Step 1: 修改 `streamChat` 函数签名和分发逻辑**

将 `streamChat` 函数完整替换为：

```js
/**
 * SSE 流式问数 — 三类事件：step（节点进度）/ token（LLM字符）/ final（结束）
 * @param {object} payload - { question, conversation_id?, dataset_id? }
 * @param {object} callbacks
 * @param {function} callbacks.onToken - (token: string) => void，每个 LLM token 触发
 * @param {function} callbacks.onEvent - (data: object) => void，step 事件触发
 * @param {function} callbacks.onDone  - (data: object) => void，final 事件触发
 * @param {function} callbacks.onError - (err: Error) => void
 */
export function streamChat(payload, { onToken, onEvent, onError, onDone }) {
  const controller = new AbortController();

  fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok) {
      onError?.(new Error(`HTTP ${res.status}`));
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // 保留不完整行

      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        try {
          const data = JSON.parse(line.slice(5).trim());
          if (data.type === 'token') {
            onToken?.(data.content);
          } else if (data.type === 'step') {
            onEvent?.(data);
          } else if (data.type === 'final') {
            onDone?.(data);
          }
        } catch {
          // 忽略非 JSON 行
        }
      }
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') onError?.(err);
  });

  return controller;
}
```

- [ ] **Step 2: Commit**

```bash
git add datalogue-web/src/api/client.js
git commit -m "feat(client): streamChat dispatches token/step/final by type field"
```

---

## Task 5: 新建 AgentPanel 组件

**Files:**
- Create: `datalogue-web/src/components/agent-panel.jsx`

- [ ] **Step 1: 创建文件**

创建 `datalogue-web/src/components/agent-panel.jsx`，完整内容：

```jsx
import React from 'react';
import { Icon } from './icons';

// AgentPanel — 右侧 Agent 执行状态面板
// 纯展示组件，所有数据由 ChatScreen 通过 props 注入，无内部状态。
//
// Props:
//   open       boolean             面板是否可见
//   onClose    () => void          关闭回调
//   steps      StepObj[]           节点进度列表
//   intent     {intent, entities}  意图识别结果（null = 未就绪）
//   sql        string              生成的 SQL（null = 未就绪）
//   sqlResult  {rows, columns, elapsed_ms}  执行摘要（null = 未就绪）

// ── 步骤列表 ──────────────────────────────────────────────
function StepList({ steps }) {
  if (!steps || steps.length === 0) return null;
  return (
    <div>
      <div className="agent-section-label">执行过程</div>
      {steps.map((step, i) => (
        <div key={i} className="agent-step">
          <div className={`agent-step-icon ${step.status}`}>
            {step.status === 'done' && <Icon name="check" />}
            {step.status === 'running' && null /* spin via CSS */}
            {step.status === 'pending' && null}
          </div>
          <span className={`agent-step-label ${step.status === 'running' ? 'running' : ''}`}>
            {step.display_name || step.node}
          </span>
          {step.elapsed_ms != null && step.status === 'done' && (
            <span className="agent-step-ms">{step.elapsed_ms}ms</span>
          )}
        </div>
      ))}
    </div>
  );
}

// ── 意图卡片 ──────────────────────────────────────────────
function IntentCard({ intent }) {
  if (!intent) return null;
  const tags = [
    intent.intent && `意图: ${intent.intent}`,
    ...(intent.entities?.metrics  || []).map(m => `指标: ${m}`),
    ...(intent.entities?.dimensions || []).map(d => `维度: ${d}`),
    intent.entities?.time_range && `时间: ${intent.entities.time_range}`,
  ].filter(Boolean);

  if (tags.length === 0) return null;
  return (
    <div>
      <div className="agent-section-label">意图解析</div>
      <div className="intent-tags">
        {tags.map((t, i) => <span key={i} className="intent-tag">{t}</span>)}
      </div>
    </div>
  );
}

// ── SQL 预览 ──────────────────────────────────────────────
function SqlPreview({ sql }) {
  if (!sql) return null;
  const copy = () => navigator.clipboard.writeText(sql).catch(console.error);
  return (
    <div>
      <div className="agent-section-label">生成的 SQL</div>
      <div className="sql-preview">
        <div className="sql-preview-head">
          <span><Icon name="sql" /> SQL</span>
          <button className="btn ghost" style={{ fontSize: 11, padding: '2px 8px' }} onClick={copy}>
            复制
          </button>
        </div>
        <pre>{sql}</pre>
      </div>
    </div>
  );
}

// ── 执行摘要 ──────────────────────────────────────────────
function ResultSummary({ sqlResult }) {
  if (!sqlResult) return null;
  return (
    <div>
      <div className="agent-section-label">执行结果</div>
      <div className="result-grid">
        <div className="result-card">
          <div className="val">{sqlResult.rows ?? '—'}</div>
          <div className="lbl">返回行数</div>
        </div>
        <div className="result-card">
          <div className="val">{sqlResult.elapsed_ms != null ? `${sqlResult.elapsed_ms}ms` : '—'}</div>
          <div className="lbl">执行耗时</div>
        </div>
      </div>
      {sqlResult.columns && sqlResult.columns.length > 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 6 }}>
          字段：{sqlResult.columns.join(' · ')}
        </div>
      )}
    </div>
  );
}

// ── 主组件 ────────────────────────────────────────────────
function AgentPanel({ open, onClose, steps = [], intent = null, sql = null, sqlResult = null }) {
  if (!open) return null;

  return (
    <div className="agent-panel">
      <div className="agent-panel-head">
        <Icon name="trace" style={{ width: 14, height: 14, color: 'var(--accent)' }} />
        <h3>Agent 执行过程</h3>
        <button className="icon-btn" onClick={onClose} title="关闭">
          <Icon name="x" />
        </button>
      </div>
      <div className="agent-panel-body">
        <StepList steps={steps} />
        <IntentCard intent={intent} />
        <SqlPreview sql={sql} />
        <ResultSummary sqlResult={sqlResult} />
        {steps.length === 0 && !intent && !sql && !sqlResult && (
          <div style={{ color: 'var(--text-3)', fontSize: 12, textAlign: 'center', paddingTop: 32 }}>
            发问后此处显示 Agent 执行详情
          </div>
        )}
      </div>
    </div>
  );
}

export { AgentPanel };
```

- [ ] **Step 2: Commit**

```bash
git add datalogue-web/src/components/agent-panel.jsx
git commit -m "feat: add AgentPanel component (steps/intent/SQL/result modules)"
```

---

## Task 6: 重构 ChatScreen

**Files:**
- Modify: `datalogue-web/src/components/chat.jsx`

### 6a — 新增 state/ref，更新 imports

- [ ] **Step 1: 更新 import 行**

将第 1-4 行替换为：
```jsx
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Icon } from './icons';
import { LineChart, Donut, HeatStrip, GroupedBar } from './charts';
import { streamChat, listDatasets, listDatasources, getConversation } from '../api/client';
import { AgentPanel } from './agent-panel';
```

- [ ] **Step 2: 在 `ChatScreen` 函数体顶部增加新 state 和 ref**

在 `const abortRef = useRef(null);` 这行**之后**插入：

```js
  // ── 会话 ID（来自路由参数 /chat/:id）──────────────────
  const { id: convId } = useParams();

  // ── 真 token 流 state ─────────────────────────────────
  const [streamingAnswer, setStreamingAnswer] = useState('');
  const streamingAnswerRef = useRef('');   // onDone 闭包里读最新值

  // ── Agent 面板数据 ────────────────────────────────────
  const [intent,    setIntent]    = useState(null);
  const [sqlResult, setSqlResult] = useState(null);
```

- [ ] **Step 3: 加载历史消息 useEffect**

在现有的 `listDatasources().then(...)` 那个 `useEffect` **之后**插入：

```js
  // 路由参数有 convId 时，加载该对话的历史消息
  useEffect(() => {
    if (!convId) return;
    getConversation(convId)
      .then(data => {
        const msgs = (data.messages || []).map(m => ({
          role:    m.role,
          content: m.content,
          sql:     (m.sql_list && m.sql_list[0]) ?? null,
          status:  'done',
        }));
        setMessages(msgs);
      })
      .catch(err => console.error('加载历史会话失败:', err));
  }, [convId]);
```

### 6b — 更新 handleSend 回调

- [ ] **Step 4: 在 `handleSend` 的 `setIsComplex(false);` 后追加 intent/sqlResult 重置**

找到：
```js
    setIsComplex(false);
```
改为：
```js
    setIsComplex(false);
    setIntent(null);
    setSqlResult(null);
    setStreamingAnswer('');
    streamingAnswerRef.current = '';
```

- [ ] **Step 5: 替换 `onToken`/`onEvent`/`onDone` 回调**

找到 `const controller = streamChat(` 调用，将整个回调对象替换为：

```js
      {
        onToken: (token) => {
          streamingAnswerRef.current += token;
          setStreamingAnswer(prev => prev + token);
        },
        onEvent: (data) => {
          // 节点进度 → traceSteps
          if (data.node && data.node !== 'error') {
            const cur = traceStepsRef.current;
            const exists = cur.find(s => s.node === data.node);
            const next = exists
              ? cur.map(s => s.node === data.node ? { ...s, ...data } : s)
              : [...cur, { node: data.node, display_name: data.display_name, status: data.status, elapsed_ms: data.elapsed_ms }];
            traceStepsRef.current = next;
            setTraceSteps(next);
          }
          // 意图解析完成
          if (data.node === 'intent_recognition' && data.status === 'done') {
            setIntent({ intent: data.intent, entities: data.entities });
          }
          // SQL 编译完成
          if (data.node === 'dsl_compiler' && data.status === 'done') {
            setStreamSql(data.sql || '');
          }
          // SQL 执行完成
          if (data.node === 'sql_execute' && data.status === 'done') {
            setSqlResult({ rows: data.rows, columns: data.columns, elapsed_ms: data.elapsed_ms });
          }
        },
        onError: (err) => {
          console.error('[SSE error]', err);
          setStreamingAnswer('连接出错，请稍后重试。');
          streamingAnswerRef.current = '连接出错，请稍后重试。';
          setIsStreaming(false);
        },
        onDone: (finalData) => {
          const answer = cleanAnswer(streamingAnswerRef.current || finalData?.answer || '已生成回答');
          streamingAnswerRef.current = '';

          setIsStreaming(false);
          setStreamingAnswer('');
          setMessages(prev => [...prev, {
            role:     'assistant',
            content:  answer,
            status:   'done',
            sql:      finalData?.sql ?? streamSql,
            sqlOpen:  false,
            setSqlOpen: (v) => setMessages(ms =>
              ms.map((m, i) => i === ms.length - 1 ? { ...m, sqlOpen: v } : m)
            ),
          }]);
          // traceSteps / intent / sqlResult 保留，直到用户关闭面板
          setStreamSql('');
          traceStepsRef.current = [];
        },
      }
```

### 6c — 更新 JSX 布局

- [ ] **Step 6: 替换流式气泡条件块**

找到：
```jsx
            {/* 流式气泡：有推理步骤或最终文字时都显示 */}
            {isStreaming && (traceSteps.length > 0 || streamingText) && (
```
改为：
```jsx
            {/* 流式气泡：token 到达时显示打字效果 */}
            {isStreaming && streamingAnswer && (
```

找到 `streamingText` 出现的地方（气泡内容），替换为 `streamingAnswer`，共两处：
```jsx
                {streamingAnswer && (
                  <div className="ans-body streaming-text">
                    {renderAnswer(streamingAnswer)}
                    <span className="cursor-blink">▋</span>
                  </div>
                )}
```

- [ ] **Step 7: 替换 TracePanel 为 AgentPanel**

找到：
```jsx
      {traceOpen && <TracePanel steps={traceSteps} onClose={() => setTraceOpen(false)} />}
```
替换为：
```jsx
      <AgentPanel
        open={traceOpen}
        onClose={() => setTraceOpen(false)}
        steps={traceSteps}
        intent={intent}
        sql={streamSql}
        sqlResult={sqlResult}
      />
```

- [ ] **Step 8: 给 `.chat-layout` 加 `with-panel` class**

找到：
```jsx
    <div className="chat-layout">
```
改为：
```jsx
    <div className={`chat-layout${traceOpen ? ' with-panel' : ''}`}>
```

- [ ] **Step 9: 更新 export，删除 TracePanel**

找到最后一行：
```js
export { ChatScreen, ChatEmpty, TracePanel };
```
改为：
```js
export { ChatScreen, ChatEmpty };
```

- [ ] **Step 10: 删除 StreamStepBar 和 TracePanel 组件定义**

删除以下两个函数体（约第 158-171 行的 `StreamStepBar`，约第 573-618 行的 `TracePanel`）。

- [ ] **Step 11: 确认页面正常渲染**

访问 `http://localhost:5173/chat`，发送「查询所有商品信息」，确认：
- 输入后出现打字机效果（token 逐字显示）
- 点击顶栏「推理过程」，右侧面板滑出显示步骤进度
- 回答完成后面板仍保留，点击 ✕ 关闭

- [ ] **Step 12: Commit**

```bash
git add datalogue-web/src/components/chat.jsx
git commit -m "feat(chat): token streaming, AgentPanel layout, load history on mount

- Replace StreamingAnswer with true token accumulation
- Integrate AgentPanel (replace TracePanel)
- flex-row layout via .with-panel class
- Load /chat/:id conversation history on mount"
```

---

## Task 7: Sidebar — 真实会话列表 + 路由导航

**Files:**
- Modify: `datalogue-web/src/components/sidebar.jsx`

- [ ] **Step 1: 更新 imports**

将现有 import 块替换为：
```js
import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Icon } from './icons';
import { listConversations } from '../api/client';
```

- [ ] **Step 2: 在 `Sidebar` 函数体中添加会话 state 和拉取逻辑**

在 `const go = ...` 行之后插入：
```js
  const [recentConvs, setRecentConvs] = useState([]);

  // 拉取最近会话（最多 8 条），并监听 new-conversation 事件刷新
  useEffect(() => {
    const load = () =>
      listConversations()
        .then(data => setRecentConvs((data || []).slice(0, 8)))
        .catch(console.error);
    load();
    window.addEventListener('new-conversation', load);
    return () => window.removeEventListener('new-conversation', load);
  }, []);
```

- [ ] **Step 3: 替换最近会话渲染部分**

找到：
```jsx
      <div className="nav-section">最近会话</div>
      {recent.map(r => (
        <button key={r.id} className="recent-thread" onClick={() => go('chat')}>
          {r.title}
        </button>
      ))}
```
替换为：
```jsx
      <div className="nav-section">最近会话</div>
      {recentConvs.map(r => (
        <button
          key={r.id}
          className={'recent-thread' + (path === `/chat/${r.id}` ? ' active' : '')}
          onClick={() => navigate(`/chat/${r.id}`)}
          title={r.title}
        >
          {r.title}
        </button>
      ))}
      {recentConvs.length === 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-3)', padding: '4px 16px' }}>
          暂无会话
        </div>
      )}
```

- [ ] **Step 4: 在 `onDone` 触发后通知 sidebar 刷新**

在 `datalogue-web/src/components/chat.jsx` 的 `onDone` 回调中，`setIsStreaming(false)` 之后添加一行：
```js
          window.dispatchEvent(new Event('new-conversation'));
```

- [ ] **Step 5: 删除 sidebar 中硬编码的 `recent` 数组**

删除第 55-60 行的：
```js
  const recent = [
    { id: 'r1', title: '上周华东区销售为什么下降了12%', when: '2分钟前' },
    ...
  ];
```

- [ ] **Step 6: 验证**

1. 访问 `http://localhost:5173/chat`，发送一个问题
2. 回答完成后，侧边栏「最近会话」应出现这条新会话
3. 点击该会话，URL 变为 `/chat/:id`，历史消息正确加载

- [ ] **Step 7: Commit**

```bash
git add datalogue-web/src/components/sidebar.jsx datalogue-web/src/components/chat.jsx
git commit -m "feat(sidebar): fetch real conversations, navigate to /chat/:id

- Replace hardcoded recent list with API-driven listConversations()
- Click navigates to /chat/:id and loads history
- Refresh on new-conversation event after each chat completion"
```

---

## 完成验证

访问 `http://localhost:5173/chat`，依次测试：

- [ ] 输入「查询所有商品信息」，观察打字机逐 token 效果
- [ ] 点击顶栏「推理过程」，右侧面板展开：步骤进度 → 意图解析 → SQL → 执行摘要全部显示
- [ ] 回答完成后面板保留，点击 ✕ 关闭
- [ ] 侧边栏出现新会话，点击后 URL 变为 `/chat/:id`，消息历史正确加载
- [ ] 直接访问 `http://localhost:5173/chat/some-nonexistent-id` 不崩溃（TopBar 正常）
