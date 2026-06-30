// workbench-panel.jsx
// Chat 右侧 Workbench Panel：消费后端 View Model，只展示业务摘要、refs、状态和受控 action。

import React, { useEffect, useMemo, useState } from 'react';
import { fetchWorkbenchArtifact, fetchWorkbenchThread, requestWorkbenchRetry } from '../assistant/workbench-api';
import { Icon } from './icons';

const FORBIDDEN_TEXT_RE = /\b(select|from|join|where|schema|raw_rows|raw_result|query_plan|field_patch)\b/i;

function safeText(value, fallback = '') {
  const text = String(value ?? '').trim();
  if (!text || FORBIDDEN_TEXT_RE.test(text)) return fallback;
  return text.slice(0, 180);
}

function refValue(ref) {
  if (!ref) return '';
  if (typeof ref === 'string') return ref;
  return ref.ref || ref.ref_id || ref.artifact_ref || '';
}

function collectRefs(view) {
  if (!view) return [];
  const refs = [];
  if (view.primary_artifact_ref) {
    refs.push({ ref_type: 'artifact', ref: view.primary_artifact_ref, relation: 'primary' });
  }
  for (const ref of view.related_refs || []) refs.push(ref);
  const seen = new Set();
  return refs.filter((item) => {
    const value = refValue(item);
    if (!value || seen.has(value)) return false;
    seen.add(value);
    return true;
  });
}

export function WorkbenchTimeline({ timeline = [] }) {
  if (!timeline.length) return null;
  return (
    <section className="workbench-section">
      <h4>任务时间线</h4>
      <div className="workbench-timeline">
        {timeline.map((item) => (
          <div className="workbench-timeline-item" key={item.event_id || item.event_type}>
            <span className="workbench-dot" />
            <div>
              <strong>{safeText(item.summary || item.event_type, '任务处理')}</strong>
              <span>{safeText(item.event_type)}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function WorkbenchArtifactRefs({ refs = [], onOpen }) {
  if (!refs.length) return null;
  return (
    <section className="workbench-section">
      <h4>引用</h4>
      <div className="workbench-refs">
        {refs.map((ref) => {
          const value = refValue(ref);
          const clickable = value.startsWith('artifact:');
          return (
            <button
              key={value}
              type="button"
              className="workbench-ref"
              disabled={!clickable}
              onClick={() => clickable && onOpen(value)}
            >
              <Icon name={clickable ? 'table' : 'link'} />
              <code>{value}</code>
            </button>
          );
        })}
      </div>
    </section>
  );
}

export function WorkbenchActions({ threadId, actions = [], onRetried, onRetryRun }) {
  if (!actions.length) return null;
  return (
    <section className="workbench-section">
      <h4>动作</h4>
      <div className="workbench-actions">
        {actions.map((action) => (
          <button
            key={`${action.action_id}-${action.message_id || ''}`}
            type="button"
            className="workbench-action"
            disabled={!action.enabled}
            title={action.disabled_reason || action.label}
            onClick={async () => {
              if (!action.enabled) return;
              const response = await requestWorkbenchRetry({
                thread_id: threadId,
                message_id: action.message_id,
                checkpoint_ref: action.checkpoint_ref,
                selected_action: action.action_id === 'retry' ? 'retry_last_step' : action.action_id,
              });
              onRetried?.(response);
              if (response?.accepted && response?.run_request) {
                // Workbench 只发起恢复请求，真正重跑交回 Chat 主链和 retry checkpoint。
                onRetryRun?.(response.run_request);
              }
            }}
          >
            <Icon name={action.action_id === 'retry' ? 'refresh' : 'play'} />
            <span>{action.label || action.action_id}</span>
            {!action.enabled && action.disabled_reason && (
              <small>{safeText(action.disabled_reason)}</small>
            )}
          </button>
        ))}
      </div>
    </section>
  );
}

export function WorkbenchDiagnosticDrawer({ open = false, diagnostic = null }) {
  if (!open || !diagnostic) return null;
  return (
    <aside className="workbench-diagnostic">
      <h4>诊断详情</h4>
      <pre>{JSON.stringify(diagnostic, null, 2)}</pre>
    </aside>
  );
}

function WorkbenchMessages({ messages = [] }) {
  if (!messages.length) return null;
  return (
    <section className="workbench-section">
      <h4>消息</h4>
      <div className="workbench-messages">
        {messages.slice(-4).map((message) => (
          <div className="workbench-message" key={message.message_id}>
            <span>{message.role === 'user' ? '用户' : '助手'} · {message.status}</span>
            <p>{safeText(message.content_summary, '消息摘要已隐藏')}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export function WorkbenchPanel({ threadId, initialArtifactRef = null, onRetryRun = null }) {
  const [view, setView] = useState(null);
  const [artifact, setArtifact] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!threadId) {
      setView(null);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    fetchWorkbenchThread(threadId)
      .then((nextView) => {
        if (cancelled) return;
        setView(nextView);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [threadId]);

  useEffect(() => {
    if (!initialArtifactRef) return;
    fetchWorkbenchArtifact(initialArtifactRef).then(setArtifact).catch(setError);
  }, [initialArtifactRef]);

  const refs = useMemo(() => collectRefs(view), [view]);
  const openArtifact = async (artifactRef) => {
    const next = await fetchWorkbenchArtifact(artifactRef);
    setArtifact(next);
  };

  return (
    <aside className="workbench-panel" data-testid="workbench-panel">
      <div className="workbench-panel-head">
        <div>
          <span className="workbench-eyebrow">BI Workbench</span>
          <h3>工作台</h3>
        </div>
        {view?.read_only && <span className="workbench-readonly">只读</span>}
      </div>

      {loading && <p className="workbench-muted">加载中...</p>}
      {error && <p className="workbench-error">工作台暂不可用</p>}
      {view?.legacy_notice && <p className="workbench-notice">{safeText(view.legacy_notice)}</p>}

      <WorkbenchMessages messages={view?.messages || []} />
      <WorkbenchTimeline timeline={view?.timeline || []} />
      <WorkbenchArtifactRefs refs={refs} onOpen={openArtifact} />
      {artifact?.preview_payload && (
        <section className="workbench-section">
          <h4>产物详情</h4>
          <p>{safeText(artifact.preview_payload.summary, '产物摘要已生成')}</p>
        </section>
      )}
      <WorkbenchActions
        threadId={view?.thread_id || threadId}
        actions={view?.available_actions || []}
        onRetried={() => fetchWorkbenchThread(threadId).then(setView)}
        onRetryRun={onRetryRun}
      />
      <WorkbenchDiagnosticDrawer open={false} diagnostic={null} />
    </aside>
  );
}

export default WorkbenchPanel;
