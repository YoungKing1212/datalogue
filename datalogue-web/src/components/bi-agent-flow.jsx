// bi-agent-flow.jsx
// BI Agent K2 页面原型容器：串起 create -> confirmation -> handoff -> polling 的安全闭环。

import React, { useCallback, useMemo, useState } from 'react';

import {
  confirmBIAgentRun,
  createBIAgentRun,
  getBIAgentRun,
  handoffBIAgentRun,
} from '../assistant/bi-agent-api';
import BIAgentConfirmationCard from './bi-agent-confirmation-card';
import BIAgentRunPanel from './bi-agent-run-panel';

const DEFAULT_BI_AGENT_API = {
  createRun: createBIAgentRun,
  confirmRun: confirmBIAgentRun,
  handoffRun: handoffBIAgentRun,
  getRun: getBIAgentRun,
};
const BI_AGENT_LOG_TAG = '[Datalogue][BI Agent]';
const BI_AGENT_ENDPOINT_PREFIX = '/api/bi-agent';

function logBIAgentFlow(stage, payload = {}) {
  console.info(BI_AGENT_LOG_TAG, {
    stage,
    entry: 'BIAgentFlow',
    endpoint: BI_AGENT_ENDPOINT_PREFIX,
    ...payload,
  });
}

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
    routing_rationale: `用户已选择 ${snapshot.name}，BI Agent 将把查询任务交接给 DatasetAgent。`,
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

async function pollRunUntilSettled(runId, { getRun = getBIAgentRun, maxAttempts = 6, delayMs = 400 } = {}) {
  let latest = null;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    latest = await getRun(runId);
    if (isTerminalRun(latest)) return latest;
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  return latest;
}

export function BIAgentFlow({
  selectedDataset,
  initialQuestion = '',
  api = DEFAULT_BI_AGENT_API,
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
      logBIAgentFlow('ui.create_run.completed', {
        run_id: created?.run_id,
        status: created?.status,
        dataset_id: selectedDataset?.id ? Number(selectedDataset.id) : null,
      });
      setRun(created); // 后端 run 是真相源；确认卡片只在 UI 层追加 dataset capability snapshot。
    } catch (err) {
      setError(err instanceof Error ? err.message : 'BI Agent run 创建失败');
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
      logBIAgentFlow('ui.confirm_run.completed', {
        run_id: confirmed?.run_id || run.run_id,
        status: confirmed?.status,
        dataset_id: payload?.dataset_id,
      });
      setRun(confirmed);
      const handedOff = await api.handoffRun(run.run_id);
      logBIAgentFlow('ui.handoff_run.completed', {
        run_id: handedOff?.run_id || run.run_id,
        status: handedOff?.status,
        phase: handedOff?.phase,
        artifact_ref: handedOff?.handoff?.artifact_ref,
      });
      setRun(handedOff);
      if (!isTerminalRun(handedOff)) {
        const settled = await pollRunUntilSettled(run.run_id, { getRun: api.getRun });
        if (settled) setRun(settled);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'BI Agent handoff 失败');
    } finally {
      setBusy(false);
    }
  }, [api, run]);

  return (
    <section className="bi-agent-flow" aria-label="BI Agent 原型">
      <header className="bi-agent-flow__header">
        <span>BI Agent</span>
        <h3>确认后交接 DatasetAgent</h3>
      </header>

      <div className="bi-agent-flow__form">
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          rows={3}
          placeholder="输入要交给 BI Agent 的问数问题"
          aria-label="BI Agent 问题"
        />
        <button type="button" className="btn primary" disabled={!canStart} onClick={startRun}>
          {busy ? '处理中' : '创建 run'}
        </button>
      </div>

      {!selectedDataset?.id && (
        <p className="bi-agent-flow__hint">请选择一个数据集后再启动 BI Agent。</p>
      )}

      {error && <p className="bi-agent-flow__error">{error}</p>}

      {runForConfirmation?.status === 'waiting_confirmation' && (
        <BIAgentConfirmationCard
          run={runForConfirmation}
          onConfirm={confirmAndHandoff}
          onCancel={() => setRun({ ...run, status: 'blocked', phase: 'confirm_run', error_summary: '用户取消查询。' })}
        />
      )}

      {run && run.status !== 'waiting_confirmation' && <BIAgentRunPanel run={run} />}
    </section>
  );
}

export default BIAgentFlow;
