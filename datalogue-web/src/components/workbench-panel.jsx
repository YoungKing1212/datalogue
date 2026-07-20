// workbench-panel.jsx
// Chat 右侧 Workbench Panel：消费后端 View Model，只展示业务摘要、refs、状态和受控 action。

import React, { useEffect, useMemo, useState } from 'react';
import { fetchWorkbenchArtifact, fetchWorkbenchThread, requestWorkbenchRetry } from '../assistant/workbench-api';
import { Icon } from './icons';
import DataTable from '../shared/components/DataTable';

const RUNNING_REFRESH_INTERVAL_MS = 2000;

function safeText(value, fallback = '') {
  const text = String(value ?? '').trim();
  if (!text) return fallback;
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

export function hasRunningWorkbenchMessage(view) {
  if (view?.status_summary?.status === 'running') return true;
  const messages = view?.messages || [];
  const latestMessage = messages[messages.length - 1];
  return latestMessage?.status === 'running';
}

function statusToneClass(tone = 'neutral') {
  if (tone === 'success') return 'workbench-status workbench-status-success';
  if (tone === 'warning') return 'workbench-status workbench-status-warning';
  if (tone === 'pending') return 'workbench-status workbench-status-pending';
  return 'workbench-status';
}

function artifactErrorMessage(error) {
  const message = String(error?.message || error || '').toLowerCase();
  if (message.includes('403') || message.includes('forbidden')) return '无权限查看该产物。';
  if (message.includes('409') || message.includes('current thread') || message.includes('belong')) {
    return '该产物不属于当前会话。';
  }
  if (message.includes('404') || message.includes('not found')) return '产物不存在或已过期。';
  return '产物详情暂不可用。';
}

function retryAvailability(actions = []) {
  const retryAction = actions.find((action) => action.action_id === 'retry');
  if (!retryAction) {
    return { label: '暂无可用重试', reason: '当前状态没有声明 retry action。' };
  }
  if (retryAction.enabled) {
    return { label: '重试可用', reason: retryAction.checkpoint_ref || '可从检查点恢复。' };
  }
  return { label: '重试暂不可用', reason: retryAction.disabled_reason || '当前状态不允许重试。' };
}

function fallbackStatusSummary(view) {
  if (!view) return null;
  const messages = view.messages || [];
  const latestMessage = messages[messages.length - 1];
  if (view.read_only) {
    return {
      status: 'read_only',
      label: '只读回放',
      tone: 'neutral',
      read_only: true,
      actionable: false,
      summary: view.legacy_notice || '旧会话以只读方式展示。',
      primary_artifact_ref: view.primary_artifact_ref,
    };
  }
  if (!latestMessage) {
    return {
      status: 'empty',
      label: '等待问数',
      tone: 'neutral',
      actionable: false,
      summary: '当前线程还没有可展示的 BI 结果。',
      primary_artifact_ref: view.primary_artifact_ref,
    };
  }
  return {
    status: latestMessage.status,
    label: latestMessage.status === 'completed' ? '已完成' : latestMessage.status,
    tone: latestMessage.status === 'completed' ? 'success' : latestMessage.status === 'running' ? 'pending' : 'neutral',
    actionable: false,
    summary: latestMessage.content_summary,
    primary_artifact_ref: view.primary_artifact_ref,
  };
}

export function WorkbenchStatusSummary({ summary }) {
  if (!summary) return null;
  return (
    <section className={statusToneClass(summary.tone)}>
      <div>
        <span>{safeText(summary.label, '工作台状态')}</span>
        <strong>{safeText(summary.summary, '等待工作台状态更新')}</strong>
      </div>
      {summary.primary_artifact_ref && (
        <code>{safeText(summary.primary_artifact_ref)}</code>
      )}
      {summary.retry_checkpoint_ref && (
        <small>{safeText(summary.retry_checkpoint_ref)}</small>
      )}
    </section>
  );
}

function WorkbenchEmptySection({ title, children }) {
  return (
    <section className="workbench-section">
      <h4>{title}</h4>
      <p className="workbench-empty">{children}</p>
    </section>
  );
}

export function WorkbenchRunningState({ running = false }) {
  if (!running) return null;
  return (
    <section className="workbench-running" aria-live="polite">
      <strong>正在轮询工作台状态</strong>
      <span>运行结束后会自动刷新最新产物。</span>
    </section>
  );
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

export function WorkbenchArtifactRefs({ refs = [], onOpen, showEmpty = false }) {
  if (!refs.length) {
    return showEmpty ? <WorkbenchEmptySection title="引用">暂无可打开产物。</WorkbenchEmptySection> : null;
  }
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

export function WorkbenchActions({ threadId, actions = [], onRetried, onRetryRun, showEmpty = false }) {
  if (!actions.length) {
    return showEmpty ? <WorkbenchEmptySection title="动作">暂无可用动作。</WorkbenchEmptySection> : null;
  }
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
              if (response?.accepted && response?.task_request) {
                // Workbench retry 创建新的 Agent Team task，不再绕回旧 chat stream。
                onRetryRun?.(response.task_request);
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

export function WorkbenchDiagnosticDrawer({ open = false, diagnostic = null, retryInfo = null }) {
  if (!open || !diagnostic) return null;
  return (
    <aside className="workbench-diagnostic">
      <h4>诊断摘要</h4>
      <p>{safeText(diagnostic.summary, '当前任务可从检查点继续处理。')}</p>
      {diagnostic.retry_checkpoint_ref && <code>{safeText(diagnostic.retry_checkpoint_ref)}</code>}
      {retryInfo && (
        <div className="workbench-retry-state">
          <strong>{safeText(retryInfo.label, '重试状态')}</strong>
          <span>{safeText(retryInfo.reason, '等待重试状态更新。')}</span>
        </div>
      )}
    </aside>
  );
}

export function WorkbenchArtifactDrawer({ artifact = null, artifactRef = null, loading = false, error = null, onClose }) {
  if (!artifact && !loading && !error) return null;
  const refs = artifact?.related_refs || [];
  const preview = artifact?.preview_payload || {};
  const hasTableData = Array.isArray(preview?.columns) && preview.columns.length > 0 && Array.isArray(preview?.rows);
  return (
    <section className="workbench-artifact-drawer" data-testid="workbench-artifact-drawer">
      <div className="workbench-artifact-head">
        <div>
          <span>{safeText(artifact?.kind, 'artifact')}</span>
          <h4>产物详情</h4>
        </div>
        <button type="button" className="workbench-close" onClick={onClose} aria-label="关闭产物详情">
          <Icon name="x" />
        </button>
      </div>
      {loading && <p className="workbench-muted">正在加载产物详情...</p>}
      {error && <p className="workbench-error">{artifactErrorMessage(error)}</p>}
      {!loading && !error && artifact && (
        <>
          {hasTableData ? (
            <DataTable
              columns={preview.columns}
              rows={preview.rows}
              totalRowCount={preview.total_row_count}
              truncated={preview.truncated}
            />
          ) : (
            <>
              <p>{safeText(preview.summary || artifact.summary, '产物摘要已生成')}</p>
              <code>{safeText(artifact.artifact_ref || artifactRef)}</code>
            </>
          )}
        </>
      )}
      {!!refs.length && (
        <div className="workbench-refs">
          {refs.map((ref) => (
            <span className="workbench-ref workbench-ref-static" key={`${ref.ref_type}-${ref.ref}`}>
              <Icon name="link" />
              <code>{safeText(ref.ref)}</code>
            </span>
          ))}
        </div>
      )}
    </section>
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

export function WorkbenchPanel({
  threadId,
  initialArtifactRef = null,
  onRetryRun = null,
  refreshIntervalMs = RUNNING_REFRESH_INTERVAL_MS,
}) {
  const [view, setView] = useState(null);
  const [artifact, setArtifact] = useState(null);
  const [error, setError] = useState(null);
  const [artifactLoading, setArtifactLoading] = useState(false);
  const [artifactError, setArtifactError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [focusedArtifactRef, setFocusedArtifactRef] = useState(initialArtifactRef);

  useEffect(() => {
    if (!threadId) {
      setView(null);
      setArtifact(null);
      setArtifactError(null);
      return undefined;
    }
    let cancelled = false;
    const load = () => {
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
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [threadId]);

  useEffect(() => {
    if (!threadId || !hasRunningWorkbenchMessage(view)) return undefined;
    let cancelled = false;
    const refreshTimer = window.setTimeout(() => {
      fetchWorkbenchThread(threadId)
        .then((nextView) => {
          if (cancelled) return;
          setView(nextView); // running 期间由 view 状态驱动轮询，覆盖 retry action 的手工刷新快照。
          setError(null);
        })
        .catch((err) => {
          if (!cancelled) setError(err);
        });
    }, refreshIntervalMs);
    return () => {
      cancelled = true;
      window.clearTimeout(refreshTimer);
    };
  }, [threadId, view, refreshIntervalMs]);

  useEffect(() => {
    if (!initialArtifactRef) return;
    setFocusedArtifactRef(initialArtifactRef);
    setArtifactLoading(true);
    setArtifactError(null);
    fetchWorkbenchArtifact(initialArtifactRef, threadId)
      .then((nextArtifact) => {
        setArtifact(nextArtifact);
        setArtifactError(null);
      })
      .catch((err) => {
        setArtifact(null);
        setArtifactError(err);
      })
      .finally(() => setArtifactLoading(false));
  }, [initialArtifactRef, threadId]);

  const refs = useMemo(() => collectRefs(view), [view]);
  const statusSummary = view?.status_summary || fallbackStatusSummary(view);
  const running = hasRunningWorkbenchMessage(view);
  const hasThreadView = Boolean(threadId && view);
  const primaryArtifactRef = statusSummary?.primary_artifact_ref || view?.primary_artifact_ref;
  useEffect(() => {
    if (!primaryArtifactRef || running) return;
    if (focusedArtifactRef === primaryArtifactRef) return;
    setFocusedArtifactRef(primaryArtifactRef);
    // completed 快照出现新主产物时自动聚焦，避免 retry 结束后用户仍停在旧失败状态。
    setArtifactLoading(true);
    setArtifactError(null);
    fetchWorkbenchArtifact(primaryArtifactRef, threadId)
      .then((nextArtifact) => {
        setArtifact(nextArtifact);
        setArtifactError(null);
      })
      .catch((err) => {
        setArtifact(null);
        setArtifactError(err);
      })
      .finally(() => setArtifactLoading(false));
  }, [primaryArtifactRef, running, focusedArtifactRef, threadId]);

  const openArtifact = async (artifactRef) => {
    setFocusedArtifactRef(artifactRef);
    setArtifact(null);
    setArtifactLoading(true);
    setArtifactError(null);
    try {
      const next = await fetchWorkbenchArtifact(artifactRef, view?.thread_id || threadId);
      setArtifact(next);
    } catch (err) {
      setArtifactError(err);
    } finally {
      setArtifactLoading(false);
    }
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

      {!threadId && <p className="workbench-muted">选择一个会话后查看工作台。</p>}
      {threadId && !loading && !view && !error && <p className="workbench-muted">暂无工作台数据。</p>}
      <WorkbenchStatusSummary summary={statusSummary} />
      <WorkbenchRunningState running={running} />
      <WorkbenchMessages messages={view?.messages || []} />
      <WorkbenchTimeline timeline={view?.timeline || []} />
      <WorkbenchArtifactRefs refs={refs} onOpen={openArtifact} showEmpty={hasThreadView} />
      <WorkbenchArtifactDrawer
        artifact={artifact}
        artifactRef={focusedArtifactRef}
        loading={artifactLoading}
        error={artifactError}
        onClose={() => {
          setArtifact(null);
          setArtifactError(null);
          setArtifactLoading(false);
        }}
      />
      <WorkbenchActions
        threadId={view?.thread_id || threadId}
        actions={view?.available_actions || []}
        onRetried={() => fetchWorkbenchThread(threadId).then(setView)}
        onRetryRun={onRetryRun}
        showEmpty={hasThreadView}
      />
      <WorkbenchDiagnosticDrawer
        open={statusSummary?.actionable}
        diagnostic={statusSummary}
        retryInfo={retryAvailability(view?.available_actions || [])}
      />
    </aside>
  );
}

export default WorkbenchPanel;
