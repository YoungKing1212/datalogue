// bi-lead-agent-flow.jsx
// BI LeadAgent K2 页面原型容器：串起 create -> confirmation -> handoff -> polling 的安全闭环。

import React, { useCallback, useMemo, useState } from 'react';

import {
  confirmBILeadAgentRun,
  createBILeadAgentRun,
  getBILeadAgentRun,
  handoffBILeadAgentRun,
} from '../assistant/bi-lead-agent-api';
import BILeadConfirmationCard from './bi-lead-confirmation-card';
import BILeadRunPanel from './bi-lead-run-panel';

const DEFAULT_BI_LEAD_AGENT_API = {
  createRun: createBILeadAgentRun,
  confirmRun: confirmBILeadAgentRun,
  handoffRun: handoffBILeadAgentRun,
  getRun: getBILeadAgentRun,
};

function datasetCapabilitySnapshot(dataset) {
  if (!dataset?.id) return null;
  return {
    dataset_id: Number(dataset.id),
    name: dataset.name || dataset.display_name || `数据集 ${dataset.id}`,
    domain: dataset.domain || dataset.business_domain || null,
    supported_questions: dataset.supported_questions || [],
    key_metrics: dataset.key_metrics || [],
    key_dimensions: dataset.key_dimensions || [],
    freshness: dataset.freshness || null,
    availability: dataset.availability || dataset.status || null,
  };
}

export function buildConfirmationRequest({ run, dataset }) {
  const snapshot = datasetCapabilitySnapshot(dataset);
  if (!run?.run_id || !snapshot?.dataset_id) return null;
  return {
    dataset_id: snapshot.dataset_id,
    confirmed_question: run.question,
    task_goal: '执行单数据集问数',
    capability_snapshot: snapshot,
    routing_rationale: `用户已选择 ${snapshot.name}，BI LeadAgent 将把查询任务交接给 DatasetAgent。`,
    risk_notice: '本次只执行已确认数据集上的只读查询。',
  };
}

function runWithConfirmationRequest(run, dataset) {
  if (!run) return null;
  return {
    ...run,
    confirmation_request: buildConfirmationRequest({ run, dataset }),
  };
}

function isTerminalRun(run) {
  return ['completed', 'blocked', 'failed', 'cancelled'].includes(run?.status);
}

async function pollRunUntilSettled(runId, { getRun = getBILeadAgentRun, maxAttempts = 6, delayMs = 400 } = {}) {
  let latest = null;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    latest = await getRun(runId);
    if (isTerminalRun(latest)) return latest;
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  return latest;
}

export function BILeadAgentFlow({
  selectedDataset,
  initialQuestion = '',
  api = DEFAULT_BI_LEAD_AGENT_API,
}) {
  const [question, setQuestion] = useState(initialQuestion);
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const runForConfirmation = useMemo(
    () => runWithConfirmationRequest(run, selectedDataset),
    [run, selectedDataset],
  );
  const canStart = Boolean(question.trim() && selectedDataset?.id && !busy);

  const startRun = useCallback(async () => {
    if (!canStart) return;
    setBusy(true);
    setError('');
    try {
      const created = await api.createRun({
        question: question.trim(),
      });
      setRun(created); // 后端 run 是真相源；确认卡片只在 UI 层追加 dataset capability snapshot。
    } catch (err) {
      setError(err instanceof Error ? err.message : 'BI LeadAgent run 创建失败');
    } finally {
      setBusy(false);
    }
  }, [api, canStart, question]);

  const confirmAndHandoff = useCallback(async (payload) => {
    if (!run?.run_id) return;
    setBusy(true);
    setError('');
    try {
      const confirmed = await api.confirmRun(run.run_id, payload);
      setRun(confirmed);
      const handedOff = await api.handoffRun(run.run_id);
      setRun(handedOff);
      if (!isTerminalRun(handedOff)) {
        const settled = await pollRunUntilSettled(run.run_id, { getRun: api.getRun });
        if (settled) setRun(settled);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'BI LeadAgent handoff 失败');
    } finally {
      setBusy(false);
    }
  }, [api, run]);

  return (
    <section className="bi-lead-agent-flow" aria-label="BI LeadAgent 原型">
      <header className="bi-lead-agent-flow__header">
        <span>BI LeadAgent</span>
        <h3>确认后交接 DatasetAgent</h3>
      </header>

      <div className="bi-lead-agent-flow__form">
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          rows={3}
          placeholder="输入要交给 BI LeadAgent 的问数问题"
          aria-label="BI LeadAgent 问题"
        />
        <button type="button" className="btn primary" disabled={!canStart} onClick={startRun}>
          {busy ? '处理中' : '创建 run'}
        </button>
      </div>

      {!selectedDataset?.id && (
        <p className="bi-lead-agent-flow__hint">请选择一个数据集后再启动 BI LeadAgent。</p>
      )}

      {error && <p className="bi-lead-agent-flow__error">{error}</p>}

      {runForConfirmation?.status === 'waiting_confirmation' && (
        <BILeadConfirmationCard
          run={runForConfirmation}
          onConfirm={confirmAndHandoff}
          onCancel={() => setRun({ ...run, status: 'blocked', phase: 'confirm_run', error_summary: '用户取消查询。' })}
        />
      )}

      {run && run.status !== 'waiting_confirmation' && <BILeadRunPanel run={run} />}
    </section>
  );
}

export default BILeadAgentFlow;
