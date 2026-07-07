# BI LeadAgent K2 E2E Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 K1 后端契约和最小 API 之上，打通页面确认卡片到 `query_dataset` handoff、DatasetAgent Runtime 执行、最终回答和 Workbench refs 展示的端到端原型。

**Architecture:** K2 不改变 K1 的 Datalogue DB 真相源和 AgentScope 2.0 SDK DatasetAgent handoff 边界。前端新增 BI LeadAgent 确认卡片和 run 状态轮询，后端补齐面向页面的确认响应、final answer synthesis 和 Workbench 投影。页面只消费安全摘要、artifact/checkpoint refs、blocked/failed 用户文案，不接触 SQL、schema、DSL、raw rows 或 DatasetAgent 内部工具。

**Tech Stack:** React 19、Vite、Vitest、Testing Library、FastAPI、SQLAlchemy、pytest、AgentScope 2.0 SDK、Datalogue Workbench View Model。

---

## 0. Scope And Dependencies

K2 依赖 K1 已完成：

- `/api/bi-lead-agent/runs`
- `/api/bi-lead-agent/runs/{run_id}/confirm`
- `/api/bi-lead-agent/runs/{run_id}/handoff`
- `/api/bi-lead-agent/runs/{run_id}`
- `bi_lead_agent_run`
- `bi_lead_agent_confirmation`
- `bi_agent_handoff`
- AgentScope 2.0 SDK DatasetAgent tool-calling adapter

K2 做：

- 页面确认卡片。
- `request_dataset_confirmation` 用户交互闭环。
- 确认后发起 handoff。
- run 状态轮询。
- 最终回答汇总展示。
- Artifact/checkpoint refs 接入 Workbench。
- blocked/failed 用户文案。
- 前后端端到端测试和真实页面验收清单。

K2 不做：

- 高置信度自动执行。
- 多数据集查询。
- 完整 UI 交互记录 H3。
- AgentScope 长生命周期会话 agent。
- AgentScope native agent-to-agent handoff。

## 1. File Structure

Create:

- `datalogue-web/src/assistant/bi-lead-agent-api.js`
  封装 K1 run-centric API 调用，供前端确认卡片和 Chat 页面使用。

- `datalogue-web/src/assistant/bi-lead-agent-api.test.js`
  测试 API request/response 和错误归一化。

- `datalogue-web/src/components/bi-lead-confirmation-card.jsx`
  展示数据集能力摘要、routing rationale、risk notice，并提供确认/取消按钮。

- `datalogue-web/src/components/bi-lead-confirmation-card.test.jsx`
  测试卡片不展示敏感字段、确认按钮回调 payload 正确。

- `datalogue-web/src/components/bi-lead-run-panel.jsx`
  展示 run 阶段、handoff 状态、blocked/failed 文案、artifact/checkpoint refs。

- `datalogue-web/src/components/bi-lead-run-panel.test.jsx`
  测试 running/completed/blocked/failed 状态。

- `datalogue-api/tests/test_bi_lead_agent_e2e_contract.py`
  后端 K2 契约测试：确认、handoff、final answer synthesis、Workbench refs。

- `docs/test-reports/2026-07-01-bi-lead-agent-k2.md`
  K2 验收报告。

Modify:

- `datalogue-web/src/components/chat-page.jsx`
  在 Chat 页面接入 BI LeadAgent run flow。

- `datalogue-web/src/components/workbench-panel.jsx`
  识别并展示 BI LeadAgent handoff refs。

- `datalogue-web/src/styles.css`
  增加确认卡片和 run panel 样式，保持工作台工具界面风格。

- `datalogue-api/app/services/bi_lead_agent/run_service.py`
  增加最终回答汇总 DTO，保证 I2 不新增数值结论。

- `datalogue-api/app/schemas/bi_lead_agent.py`
  在 run response DTO 中增加 `final_answer` 安全汇总字段。

- `datalogue-api/app/services/workbench_view_model.py`
  把 BI LeadAgent handoff artifact/checkpoint refs 投影到 Workbench View Model。

- `.codex/project-memory.md`
  K2 完成后记录功能与验证。

## 2. Task List

### Task 1: 前端 BI LeadAgent API client

**Files:**

- Create: `datalogue-web/src/assistant/bi-lead-agent-api.js`
- Create: `datalogue-web/src/assistant/bi-lead-agent-api.test.js`

- [ ] **Step 1: Write failing API client tests**

Create `datalogue-web/src/assistant/bi-lead-agent-api.test.js`:

```js
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  confirmBILeadAgentRun,
  createBILeadAgentRun,
  getBILeadAgentRun,
  handoffBILeadAgentRun,
} from './bi-lead-agent-api';

describe('bi-lead-agent-api', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('creates BI LeadAgent run through run-centric API', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ run_id: 7, status: 'waiting_confirmation', phase: 'confirm_run' }),
    });

    const result = await createBILeadAgentRun({ question: '统计订单金额', trace_id: 'trace-k2-001' });

    expect(fetch).toHaveBeenCalledWith('/api/bi-lead-agent/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: '统计订单金额', trace_id: 'trace-k2-001' }),
    });
    expect(result.run_id).toBe(7);
  });

  it('submits confirmation and starts handoff', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ run_id: 7, confirmation_id: 3 }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ run_id: 7, status: 'running' }) });

    await confirmBILeadAgentRun(7, {
      dataset_id: 12,
      confirmed_question: '统计订单金额',
      task_goal: '执行单数据集问数',
      capability_snapshot: { dataset_id: 12, name: '订单数据集' },
      routing_rationale: '订单金额问题应由订单数据集回答。',
      risk_notice: '只读查询。',
      user_decision: 'approved',
    });
    await handoffBILeadAgentRun(7);

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/bi-lead-agent/runs/7/confirm', expect.objectContaining({ method: 'POST' }));
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/bi-lead-agent/runs/7/handoff', expect.objectContaining({ method: 'POST' }));
  });

  it('normalizes API errors without leaking response internals', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'USER_CONFIRMATION_REQUIRED' }),
    });

    await expect(getBILeadAgentRun(7)).rejects.toThrow('USER_CONFIRMATION_REQUIRED');
  });
});
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd datalogue-web
npm run test -- src/assistant/bi-lead-agent-api.test.js
```

Expected: FAIL with missing module `./bi-lead-agent-api`.

- [ ] **Step 3: Implement API client**

Create `datalogue-web/src/assistant/bi-lead-agent-api.js`:

```js
async function parseResponse(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.message || `BI LeadAgent API failed: ${response.status}`);
  }
  return payload;
}

async function postJson(url, body = undefined) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return parseResponse(response);
}

export function createBILeadAgentRun(payload) {
  return postJson('/api/bi-lead-agent/runs', payload);
}

export function confirmBILeadAgentRun(runId, payload) {
  return postJson(`/api/bi-lead-agent/runs/${runId}/confirm`, payload);
}

export function handoffBILeadAgentRun(runId) {
  return postJson(`/api/bi-lead-agent/runs/${runId}/handoff`);
}

export async function getBILeadAgentRun(runId) {
  const response = await fetch(`/api/bi-lead-agent/runs/${runId}`);
  return parseResponse(response);
}
```

- [ ] **Step 4: Run API client tests**

Run:

```bash
cd datalogue-web
npm run test -- src/assistant/bi-lead-agent-api.test.js
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add datalogue-web/src/assistant/bi-lead-agent-api.js datalogue-web/src/assistant/bi-lead-agent-api.test.js
git commit -m "feat: add BI LeadAgent web API client"
```

### Task 2: 确认卡片组件

**Files:**

- Create: `datalogue-web/src/components/bi-lead-confirmation-card.jsx`
- Create: `datalogue-web/src/components/bi-lead-confirmation-card.test.jsx`
- Modify: `datalogue-web/src/styles.css`

- [ ] **Step 1: Write failing confirmation card tests**

Create `datalogue-web/src/components/bi-lead-confirmation-card.test.jsx`:

```jsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BILeadConfirmationCard } from './bi-lead-confirmation-card';

const run = {
  run_id: 7,
  question: '统计订单金额',
  trace_id: 'trace-k2-card',
  confirmation_request: {
    dataset_id: 12,
    confirmed_question: '统计订单金额',
    task_goal: '执行单数据集问数',
    routing_rationale: '订单金额问题应由订单数据集回答。',
    risk_notice: '只读查询。',
    capability_snapshot: {
      dataset_id: 12,
      name: '订单数据集',
      domain: '销售',
      key_metrics: ['订单金额'],
      key_dimensions: ['月份'],
      availability: 'ready',
      schema: { orders: ['amount'] },
      sql: 'select * from orders',
    },
  },
};

describe('BILeadConfirmationCard', () => {
  it('renders route-level summary without sensitive dataset internals', () => {
    render(<BILeadConfirmationCard run={run} onConfirm={() => {}} onCancel={() => {}} />);

    expect(screen.getByText('订单数据集')).toBeInTheDocument();
    expect(screen.getByText('订单金额问题应由订单数据集回答。')).toBeInTheDocument();
    expect(screen.queryByText(/select \\*/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/schema/i)).not.toBeInTheDocument();
  });

  it('emits approved confirmation payload', () => {
    const onConfirm = vi.fn();
    render(<BILeadConfirmationCard run={run} onConfirm={onConfirm} onCancel={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: '确认查询' }));

    expect(onConfirm).toHaveBeenCalledWith({
      dataset_id: 12,
      confirmed_question: '统计订单金额',
      task_goal: '执行单数据集问数',
      capability_snapshot: {
        dataset_id: 12,
        name: '订单数据集',
        domain: '销售',
        supported_questions: [],
        key_metrics: ['订单金额'],
        key_dimensions: ['月份'],
        freshness: null,
        availability: 'ready',
      },
      routing_rationale: '订单金额问题应由订单数据集回答。',
      risk_notice: '只读查询。',
      user_decision: 'approved',
    });
  });
});
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd datalogue-web
npm run test -- src/components/bi-lead-confirmation-card.test.jsx
```

Expected: FAIL with missing component.

- [ ] **Step 3: Implement confirmation card**

Create `datalogue-web/src/components/bi-lead-confirmation-card.jsx`:

```jsx
function normalizeSnapshot(snapshot = {}) {
  return {
    dataset_id: Number(snapshot.dataset_id),
    name: String(snapshot.name || ''),
    domain: snapshot.domain || null,
    supported_questions: Array.isArray(snapshot.supported_questions) ? snapshot.supported_questions : [],
    key_metrics: Array.isArray(snapshot.key_metrics) ? snapshot.key_metrics : [],
    key_dimensions: Array.isArray(snapshot.key_dimensions) ? snapshot.key_dimensions : [],
    freshness: snapshot.freshness || null,
    availability: snapshot.availability || null,
  };
}

export function BILeadConfirmationCard({ run, onConfirm, onCancel, disabled = false }) {
  const request = run?.confirmation_request || {};
  const snapshot = normalizeSnapshot(request.capability_snapshot || {});

  if (!run || !request.dataset_id) return null;

  return (
    <section className="bi-lead-confirmation-card" data-testid="bi-lead-confirmation-card">
      <div className="bi-lead-confirmation-head">
        <span>BI LeadAgent</span>
        <strong>确认查询范围</strong>
      </div>
      <div className="bi-lead-confirmation-body">
        <p>{request.confirmed_question}</p>
        <dl>
          <div>
            <dt>数据集</dt>
            <dd>{snapshot.name}</dd>
          </div>
          {snapshot.domain && (
            <div>
              <dt>业务域</dt>
              <dd>{snapshot.domain}</dd>
            </div>
          )}
          <div>
            <dt>关键指标</dt>
            <dd>{snapshot.key_metrics.join('、') || '无'}</dd>
          </div>
          <div>
            <dt>关键维度</dt>
            <dd>{snapshot.key_dimensions.join('、') || '无'}</dd>
          </div>
          <div>
            <dt>选择理由</dt>
            <dd>{request.routing_rationale}</dd>
          </div>
          {request.risk_notice && (
            <div>
              <dt>提示</dt>
              <dd>{request.risk_notice}</dd>
            </div>
          )}
        </dl>
      </div>
      <div className="bi-lead-confirmation-actions">
        <button type="button" onClick={onCancel} disabled={disabled}>取消</button>
        <button
          type="button"
          className="primary"
          disabled={disabled}
          onClick={() => onConfirm({
            dataset_id: request.dataset_id,
            confirmed_question: request.confirmed_question,
            task_goal: request.task_goal,
            capability_snapshot: snapshot,
            routing_rationale: request.routing_rationale,
            risk_notice: request.risk_notice || null,
            user_decision: 'approved',
          })}
        >
          确认查询
        </button>
      </div>
    </section>
  );
}

export default BILeadConfirmationCard;
```

- [ ] **Step 4: Add styles**

Append to `datalogue-web/src/styles.css`:

```css
.bi-lead-confirmation-card {
  border: 1px solid var(--border-color, #d8dee8);
  border-radius: 8px;
  background: #ffffff;
  padding: 14px;
  display: grid;
  gap: 12px;
}

.bi-lead-confirmation-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.bi-lead-confirmation-head span {
  color: #5b6472;
  font-size: 12px;
}

.bi-lead-confirmation-body dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.bi-lead-confirmation-body dl > div {
  display: grid;
  grid-template-columns: 80px minmax(0, 1fr);
  gap: 8px;
}

.bi-lead-confirmation-body dt {
  color: #5b6472;
}

.bi-lead-confirmation-body dd {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
}

.bi-lead-confirmation-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
```

- [ ] **Step 5: Run card tests**

Run:

```bash
cd datalogue-web
npm run test -- src/components/bi-lead-confirmation-card.test.jsx
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add datalogue-web/src/components/bi-lead-confirmation-card.jsx datalogue-web/src/components/bi-lead-confirmation-card.test.jsx datalogue-web/src/styles.css
git commit -m "feat: add BI LeadAgent confirmation card"
```

### Task 3: Run 状态面板和最终回答展示

**Files:**

- Create: `datalogue-web/src/components/bi-lead-run-panel.jsx`
- Create: `datalogue-web/src/components/bi-lead-run-panel.test.jsx`
- Modify: `datalogue-web/src/styles.css`

- [ ] **Step 1: Write failing run panel tests**

Create `datalogue-web/src/components/bi-lead-run-panel.test.jsx`:

```jsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BILeadRunPanel } from './bi-lead-run-panel';

describe('BILeadRunPanel', () => {
  it('shows completed safe summary and refs', () => {
    render(<BILeadRunPanel run={{
      status: 'completed',
      phase: 'summarize_run',
      handoff: {
        handoff_status: 'completed',
        answer_summary: '订单金额汇总完成。',
        artifact_ref: 'artifact-001',
        checkpoint_ref: 'checkpoint-001',
        row_count: 10,
        column_count: 3,
      },
    }} />);

    expect(screen.getByText('订单金额汇总完成。')).toBeInTheDocument();
    expect(screen.getByText('artifact-001')).toBeInTheDocument();
    expect(screen.getByText('10 行 / 3 列')).toBeInTheDocument();
  });

  it('shows blocked message without internal details', () => {
    render(<BILeadRunPanel run={{
      status: 'blocked',
      phase: 'handoff_run',
      error_code: 'USER_CONFIRMATION_REQUIRED',
      error_summary: '需要用户确认数据集。',
    }} />);

    expect(screen.getByText('需要补充条件')).toBeInTheDocument();
    expect(screen.getByText('需要用户确认数据集。')).toBeInTheDocument();
    expect(screen.queryByText(/traceback/i)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd datalogue-web
npm run test -- src/components/bi-lead-run-panel.test.jsx
```

Expected: FAIL with missing component.

- [ ] **Step 3: Implement run panel**

Create `datalogue-web/src/components/bi-lead-run-panel.jsx`:

```jsx
function phaseLabel(phase) {
  return {
    route_run: '路由',
    confirm_run: '确认',
    handoff_run: '交接执行',
    summarize_run: '汇总',
  }[phase] || phase || '运行';
}

function statusTitle(status) {
  if (status === 'blocked') return '需要补充条件';
  if (status === 'failed') return '查询失败';
  if (status === 'completed') return '查询完成';
  return '正在处理';
}

export function BILeadRunPanel({ run }) {
  if (!run) return null;
  const handoff = run.handoff || {};
  const summary = handoff.answer_summary || run.error_summary || 'BI LeadAgent 正在处理本次查询。';

  return (
    <section className={`bi-lead-run-panel bi-lead-run-panel-${run.status}`} data-testid="bi-lead-run-panel">
      <div className="bi-lead-run-head">
        <span>{phaseLabel(run.phase)}</span>
        <strong>{statusTitle(run.status)}</strong>
      </div>
      <p>{summary}</p>
      {handoff.row_count != null && handoff.column_count != null && (
        <span className="bi-lead-run-count">{handoff.row_count} 行 / {handoff.column_count} 列</span>
      )}
      <div className="bi-lead-run-refs">
        {handoff.artifact_ref && <code>{handoff.artifact_ref}</code>}
        {handoff.checkpoint_ref && <code>{handoff.checkpoint_ref}</code>}
      </div>
    </section>
  );
}

export default BILeadRunPanel;
```

- [ ] **Step 4: Add styles**

Append to `datalogue-web/src/styles.css`:

```css
.bi-lead-run-panel {
  border: 1px solid var(--border-color, #d8dee8);
  border-radius: 8px;
  background: #ffffff;
  padding: 14px;
  display: grid;
  gap: 10px;
}

.bi-lead-run-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.bi-lead-run-head span,
.bi-lead-run-count {
  color: #5b6472;
  font-size: 12px;
}

.bi-lead-run-refs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
```

- [ ] **Step 5: Run panel tests**

Run:

```bash
cd datalogue-web
npm run test -- src/components/bi-lead-run-panel.test.jsx
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add datalogue-web/src/components/bi-lead-run-panel.jsx datalogue-web/src/components/bi-lead-run-panel.test.jsx datalogue-web/src/styles.css
git commit -m "feat: add BI LeadAgent run panel"
```

### Task 4: Chat 页面接入确认和 handoff flow

**Files:**

- Modify: `datalogue-web/src/components/chat-page.jsx`
- Modify: `datalogue-web/src/components/chat-page.test.jsx`

- [ ] **Step 1: Add failing Chat page flow test**

Append to `datalogue-web/src/components/chat-page.test.jsx`:

```jsx
it('renders BI LeadAgent confirmation card and submits handoff after approval', async () => {
  global.fetch = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        run_id: 7,
        status: 'waiting_confirmation',
        phase: 'confirm_run',
        question: '统计订单金额',
        trace_id: 'trace-chat-k2',
        confirmation_request: {
          dataset_id: 12,
          confirmed_question: '统计订单金额',
          task_goal: '执行单数据集问数',
          capability_snapshot: { dataset_id: 12, name: '订单数据集', key_metrics: ['订单金额'] },
          routing_rationale: '订单金额问题应由订单数据集回答。',
          risk_notice: '只读查询。',
        },
      }),
    })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ run_id: 7, confirmation_id: 3 }) })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        run_id: 7,
        status: 'completed',
        phase: 'summarize_run',
        handoff: { handoff_status: 'completed', answer_summary: '订单金额汇总完成。' },
      }),
    });

  render(<ChatPage />);

  fireEvent.change(screen.getByLabelText('BI LeadAgent 问题'), {
    target: { value: '统计订单金额' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'BI LeadAgent 查询' }));
  expect(await screen.findByText('订单数据集')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: '确认查询' }));
  expect(await screen.findByText('订单金额汇总完成。')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run Chat page test to verify failure**

Run:

```bash
cd datalogue-web
npm run test -- src/components/chat-page.test.jsx
```

Expected: FAIL because `BI LeadAgent 查询` flow is not wired.

- [ ] **Step 3: Wire BI LeadAgent UI state**

Modify `datalogue-web/src/components/chat-page.jsx` by importing:

```jsx
import { createBILeadAgentRun, confirmBILeadAgentRun, handoffBILeadAgentRun } from '../assistant/bi-lead-agent-api';
import { BILeadConfirmationCard } from './bi-lead-confirmation-card';
import { BILeadRunPanel } from './bi-lead-run-panel';
```

Add component state near existing Chat page state:

```jsx
const [biLeadQuestion, setBiLeadQuestion] = useState('');
const [biLeadRun, setBiLeadRun] = useState(null);
const [biLeadLoading, setBiLeadLoading] = useState(false);
const [biLeadError, setBiLeadError] = useState(null);
```

Add handlers:

```jsx
const startBILeadRun = async () => {
  const question = biLeadQuestion.trim();
  if (!question) return;
  setBiLeadLoading(true);
  setBiLeadError(null);
  try {
    const run = await createBILeadAgentRun({ question });
    setBiLeadRun(run);
  } catch (err) {
    setBiLeadError(err);
  } finally {
    setBiLeadLoading(false);
  }
};

const confirmBILeadRun = async (payload) => {
  if (!biLeadRun?.run_id) return;
  setBiLeadLoading(true);
  setBiLeadError(null);
  try {
    await confirmBILeadAgentRun(biLeadRun.run_id, payload);
    const nextRun = await handoffBILeadAgentRun(biLeadRun.run_id);
    setBiLeadRun(nextRun);
  } catch (err) {
    setBiLeadError(err);
  } finally {
    setBiLeadLoading(false);
  }
};
```

Render a dedicated BI LeadAgent prototype entry strip near the current composer/result area:

```jsx
<section className="bi-lead-entry" aria-label="BI LeadAgent 原型入口">
  <label htmlFor="bi-lead-question">BI LeadAgent 问题</label>
  <textarea
    id="bi-lead-question"
    value={biLeadQuestion}
    onChange={(event) => setBiLeadQuestion(event.target.value)}
    placeholder="输入需要显式确认后查询的业务问题"
    rows={3}
  />
  <button
    type="button"
    className="secondary"
    onClick={startBILeadRun}
    disabled={biLeadLoading || !biLeadQuestion.trim()}
  >
    BI LeadAgent 查询
  </button>
</section>
{biLeadError && <p className="form-error">{biLeadError.message}</p>}
<BILeadConfirmationCard
  run={biLeadRun}
  disabled={biLeadLoading}
  onConfirm={confirmBILeadRun}
  onCancel={() => setBiLeadRun(null)}
/>
<BILeadRunPanel run={biLeadRun?.handoff ? biLeadRun : null} />
```

This K2 prototype uses a dedicated BI LeadAgent entry strip so the first closed loop does not depend on assistant-ui composer internals. A later UI consolidation can merge this entry with the main composer once K2 behavior is verified.

- [ ] **Step 4: Run Chat page tests**

Run:

```bash
cd datalogue-web
npm run test -- src/components/chat-page.test.jsx
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add datalogue-web/src/components/chat-page.jsx datalogue-web/src/components/chat-page.test.jsx
git commit -m "feat: wire BI LeadAgent e2e prototype"
```

### Task 5: 后端 final answer 和 Workbench refs 投影

**Files:**

- Modify: `datalogue-api/app/services/bi_lead_agent/run_service.py`
- Modify: `datalogue-api/app/schemas/bi_lead_agent.py`
- Modify: `datalogue-api/app/services/workbench_view_model.py`
- Test: `datalogue-api/tests/test_bi_lead_agent_e2e_contract.py`

- [ ] **Step 1: Write failing backend K2 contract test**

Create `datalogue-api/tests/test_bi_lead_agent_e2e_contract.py`:

```python
# ============================================================
# File Name   : test_bi_lead_agent_e2e_contract.py
# Description:
#   BI LeadAgent K2 端到端契约测试。
#
# Responsibilities:
#   - 验证最终回答只基于 DatasetAgent 安全摘要。
#   - 验证 artifact/checkpoint refs 可进入 Workbench 投影。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from app.models.bi_lead_agent import BIAgentHandoff, BILeadAgentRun
from app.services.bi_lead_agent.run_service import BILeadAgentRunService


def test_bi_lead_agent_final_answer_uses_safe_handoff_summary_only(db_session):
    run = BILeadAgentRun(
        status="completed",
        phase="summarize_run",
        question="统计订单金额",
        trace_id="trace-k2-final",
        task_id="task-k2-final",
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        BIAgentHandoff(
            run_id=run.id,
            handoff_id="handoff-k2-final",
            parent_agent="bi_lead_agent",
            child_agent="dataset_agent",
            child_run_id="dataset-run-k2-final",
            dataset_id=12,
            trace_id="trace-k2-final",
            task_id="task-k2-final",
            handoff_status="completed",
            answer_summary="订单金额汇总完成。",
            artifact_ref="artifact-k2-final",
            checkpoint_ref="checkpoint-k2-final",
            row_count=10,
            column_count=3,
        )
    )
    db_session.commit()

    response = BILeadAgentRunService(db_session).get_response(run.id)

    assert response.handoff.answer_summary == "订单金额汇总完成。"
    assert response.handoff.artifact_ref == "artifact-k2-final"
    assert response.final_answer == "订单金额汇总完成。\n\n本次结果包含 10 行、3 列。\n\n结果产物：artifact-k2-final"
    assert "select " not in response.model_dump_json().lower()
    assert "schema" not in response.model_dump_json().lower()
```

- [ ] **Step 2: Run backend K2 test**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_e2e_contract.py -q
```

Expected: FAIL with missing `final_answer` response field.

- [ ] **Step 3: Add explicit final answer response field and helper**

Modify `datalogue-api/app/schemas/bi_lead_agent.py` and add the field to `BILeadAgentRunResponse`:

```python
final_answer: str | None = None
```

Add to `BILeadAgentRunService`:

```python
def synthesize_final_answer(self, run: BILeadAgentRun) -> str | None:
    if run.handoff is None or run.handoff.handoff_status != "completed":
        return None
    summary = run.handoff.answer_summary or "查询已完成。"
    count_text = ""
    if run.handoff.row_count is not None and run.handoff.column_count is not None:
        count_text = f"\n\n本次结果包含 {run.handoff.row_count} 行、{run.handoff.column_count} 列。"
    artifact_text = f"\n\n结果产物：{run.handoff.artifact_ref}" if run.handoff.artifact_ref else ""
    return f"{summary}{count_text}{artifact_text}"
```

When building `BILeadAgentRunResponse` inside `get_response()`, set:

```python
final_answer=self.synthesize_final_answer(run)
```

Do not add any SQL/schema/raw rows to the synthesized answer.

- [ ] **Step 4: Run backend K2 test**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_e2e_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add datalogue-api/app/services/bi_lead_agent/run_service.py datalogue-api/app/schemas/bi_lead_agent.py datalogue-api/app/services/workbench_view_model.py datalogue-api/tests/test_bi_lead_agent_e2e_contract.py
git commit -m "feat: project BI LeadAgent handoff refs"
```

### Task 6: K2 verification and documentation

**Files:**

- Create: `docs/test-reports/2026-07-01-bi-lead-agent-k2.md`
- Modify: `.codex/project-memory.md`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_models.py \
  tests/test_bi_lead_agent_capabilities.py \
  tests/test_bi_lead_agent_services.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_bi_lead_agent_api.py \
  tests/test_bi_lead_agent_e2e_contract.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd datalogue-web
npm run test -- \
  src/assistant/bi-lead-agent-api.test.js \
  src/components/bi-lead-confirmation-card.test.jsx \
  src/components/bi-lead-run-panel.test.jsx \
  src/components/chat-page.test.jsx \
  src/components/workbench-panel.test.jsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend lint and build**

Run:

```bash
cd datalogue-web
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 4: Create test report**

Create `docs/test-reports/2026-07-01-bi-lead-agent-k2.md`:

```markdown
# BI LeadAgent K2 Test Report

## Scope

- 页面确认卡片。
- BI LeadAgent run API client。
- 确认后 handoff flow。
- 最终安全摘要和 refs 展示。
- Workbench artifact/checkpoint refs 投影。

## Backend Commands

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_models.py \
  tests/test_bi_lead_agent_capabilities.py \
  tests/test_bi_lead_agent_services.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_bi_lead_agent_api.py \
  tests/test_bi_lead_agent_e2e_contract.py \
  -q
```

## Frontend Commands

```bash
cd datalogue-web
npm run test -- \
  src/assistant/bi-lead-agent-api.test.js \
  src/components/bi-lead-confirmation-card.test.jsx \
  src/components/bi-lead-run-panel.test.jsx \
  src/components/chat-page.test.jsx \
  src/components/workbench-panel.test.jsx
npm run lint
npm run build
```

## Result

执行时写入上述命令的真实结果。

## Residual Risk

- 真实浏览器验收需要在后端和前端 dev server 同时启动后完成。
- 高置信度自动执行仍属于 B2 后续代办。
- AgentScope native handoff 属于 K3。
```

- [ ] **Step 5: Update project memory**

Append to `.codex/project-memory.md`:

```markdown
### 2026-07-01 19:30 BI LeadAgent K2 端到端原型

- 涉及文件：`datalogue-web/src/assistant/bi-lead-agent-api.js`、`datalogue-web/src/components/bi-lead-confirmation-card.jsx`、`datalogue-web/src/components/bi-lead-run-panel.jsx`、`datalogue-web/src/components/chat-page.jsx`、`datalogue-api/app/services/bi_lead_agent/run_service.py`、`datalogue-api/app/services/workbench_view_model.py`。
- 关键改动：打通页面显式确认、handoff 提交、run 状态展示、最终安全摘要和 artifact/checkpoint refs。
- 验证方式：记录 K2 test report 中的后端 pytest、前端 vitest、lint 和 build 结果。
- 残留风险：真实浏览器验收、B2 自动执行策略和 K3 native handoff 仍为后续项。
```

- [ ] **Step 6: Commit Task 6**

```bash
git add docs/test-reports/2026-07-01-bi-lead-agent-k2.md .codex/project-memory.md
git commit -m "docs: record BI LeadAgent K2 validation"
```

## 3. Final Verification

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_models.py \
  tests/test_bi_lead_agent_capabilities.py \
  tests/test_bi_lead_agent_services.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_bi_lead_agent_api.py \
  tests/test_bi_lead_agent_e2e_contract.py \
  tests/test_agentscope_dataset_runtime_bridge.py \
  -q
```

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-web
npm run test -- \
  src/assistant/bi-lead-agent-api.test.js \
  src/components/bi-lead-confirmation-card.test.jsx \
  src/components/bi-lead-run-panel.test.jsx \
  src/components/chat-page.test.jsx \
  src/components/workbench-panel.test.jsx
npm run lint
npm run build
```

Expected: all pass.

Manual browser acceptance:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
uvicorn app.main:app --reload --port 8001
```

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-web
npm run dev -- --port 5173
```

Open `http://localhost:5173` and verify:

- `BI LeadAgent 查询` creates a confirmation card.
- Confirmation card shows only dataset route-level summary.
- Confirming starts handoff and eventually shows final safe summary.
- Artifact/checkpoint refs appear.
- No SQL/schema/raw rows/DSL text appears in DOM.

## 4. Self-Review

Spec coverage:

- K2 page confirmation flow: Task 2 and Task 4.
- Confirmation -> handoff -> final answer: Task 1, Task 4, Task 5.
- Workbench refs: Task 5.
- blocked/failed display: Task 3.
- Frontend test/lint/build verification: Task 6 and Final Verification.

Consistency checks:

- K2 uses K1 M2 run-centric API only.
- K2 does not enable `query_multiple_datasets`.
- K2 does not add high-confidence auto execution.
- K2 never displays SQL/schema/raw rows/DSL.
