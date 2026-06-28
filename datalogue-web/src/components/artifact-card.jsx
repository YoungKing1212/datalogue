// artifact-card.jsx
// C-ready ArtifactCard 统一渲染组件：title、status、summary_for_chat、
// preview_payload、primary_ref、related_refs 和 actions。第一阶段 export /
// continue_edit 只展示禁用态；retry 只派发 checkpointRef。

import React, { useMemo, useState } from 'react';
import { Icon } from './icons';
import MessageContent from './message-content';

const KNOWN_ACTION_TYPES = new Set([
  'view',
  'export',
  'copy',
  'retry',
  'download',
  'continue_edit',
  'open_ref',
]);

const ACTION_LABELS = {
  view: '查看详情',
  export: '导出',
  copy: '复制',
  retry: '重试',
  download: '下载',
  continue_edit: '继续编辑',
  open_ref: '打开引用',
};

const FIRST_PHASE_DISABLED_ACTIONS = {
  export: '导出能力将在后续版本开放',
  continue_edit: '继续编辑能力将在后续版本开放',
};

const DISABLED_REASONS = {
  export: '导出能力将在后续版本开放',
  download: '下载能力将在后续版本开放',
  continue_edit: '继续编辑能力将在后续版本开放',
};

function actionType(action) {
  return String(action?.action_type || action?.actionType || action?.action_id || action?.actionId || '').trim();
}

function actionLabel(action) {
  const type = actionType(action);
  return action?.label || ACTION_LABELS[type] || type;
}

function actionIcon(actionTypeValue) {
  switch (actionTypeValue) {
    case 'view': return 'eye';
    case 'export': return 'download';
    case 'copy': return 'copy';
    case 'retry': return 'refresh';
    case 'download': return 'download';
    case 'continue_edit': return 'edit';
    default: return 'link';
  }
}

function actionCheckpointRef(action) {
  return action?.checkpoint_ref || action?.checkpointRef || action?.payload_ref || action?.payloadRef || null;
}

function normalizeAction(action) {
  const type = actionType(action);
  if (!KNOWN_ACTION_TYPES.has(type)) {
    if (type) console.debug?.('ArtifactCard ignored unknown action', type);
    return null;
  }
  const forcedDisabledReason = FIRST_PHASE_DISABLED_ACTIONS[type];
  const disabled = Boolean(forcedDisabledReason) || action?.disabled === true || action?.enabled === false;
  return {
    ...action,
    actionType: type,
    label: actionLabel(action),
    disabled,
    disabledReason:
      forcedDisabledReason ||
      action?.disabled_reason ||
      action?.disabledReason ||
      (disabled ? DISABLED_REASONS[type] || '该操作暂不可用' : null),
  };
}

function dispatchRetry(action) {
  const checkpointRef = actionCheckpointRef(action);
  if (!checkpointRef) return;
  window.dispatchEvent(
    new CustomEvent('datalogue:artifact-action', {
      // retry 只发送 checkpointRef，避免把 SQL/schema/control_plane 回传到前端动作面。
      detail: { actionType: 'retry', checkpointRef },
    }),
  );
}

function formatRef(ref) {
  if (!ref) return '';
  if (typeof ref === 'string') return ref;
  return ref.ref || ref.artifact_ref || ref.ref_id || ref.artifactRef || '';
}

function isSafePreviewKey(key) {
  const value = String(key || '').toLowerCase();
  return !(
    value === 'patch'
    || value === 'schema'
    || value === 'control_plane'
    || value === 'raw_result'
    || value === 'raw_sql'
    || value.includes('sql')
  );
}

function PreviewTable({ columns, rows, maxRows = 5 }) {
  const trimmedRows = useMemo(() => rows.slice(0, maxRows), [rows, maxRows]);
  const colKeys = useMemo(() => {
    if (Array.isArray(columns) && columns.length) return columns;
    const firstRow = rows.find((row) => row && typeof row === 'object' && !Array.isArray(row));
    return firstRow ? Object.keys(firstRow) : [];
  }, [columns, rows]);

  if (!colKeys.length) {
    return <div className="artifact-card-empty">暂无可预览的数据</div>;
  }

  return (
    <div className="artifact-card-table-wrap">
      <table className="artifact-card-table">
        <thead>
          <tr>
            {colKeys.map((col, index) => (
              <th key={`${col}-${index}`}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trimmedRows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {colKeys.map((col, colIndex) => {
                const val = row?.[col];
                const text = val == null ? '' : typeof val === 'object' ? JSON.stringify(val) : String(val);
                return <td key={`${col}-${colIndex}`}>{text}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > maxRows && (
        <div className="artifact-card-table-more">… 共 {rows.length} 行，仅预览前 {maxRows} 行</div>
      )}
    </div>
  );
}

function PreviewBody({ previewPayload }) {
  if (!previewPayload) return null;

  if (typeof previewPayload === 'string') {
    return <p className="artifact-card-preview-text">{previewPayload}</p>;
  }

  if (Array.isArray(previewPayload)) {
    return (
      <ul className="artifact-card-preview-list">
        {previewPayload.slice(0, 5).map((item, index) => (
          <li key={`${index}-${String(item).slice(0, 20)}`}>{String(item)}</li>
        ))}
      </ul>
    );
  }

  const { rows, columns, markdown, text, content, chartType } = previewPayload || {};
  if (Array.isArray(rows) && rows.length > 0) {
    return <PreviewTable columns={columns} rows={rows} />;
  }

  const mdText = markdown || text || content;
  if (mdText) {
    return (
      <div className="artifact-card-report">
        <MessageContent text={String(mdText)} />
      </div>
    );
  }

  if (chartType) {
    return (
      <div className="artifact-card-chart-hint">
        <Icon name="chart_bar" style={{ width: 16, height: 16 }} />
        <span>图表类型：{chartType}</span>
      </div>
    );
  }

  const entries = Object.entries(previewPayload || {})
    .filter(([key]) => isSafePreviewKey(key))
    .filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value));
  if (entries.length > 0) {
    return (
      <dl className="artifact-card-preview-grid">
        {entries.map(([key, value]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{String(value)}</dd>
          </div>
        ))}
      </dl>
    );
  }

  return null;
}

function ActionButton({ action, onAction }) {
  const normalized = normalizeAction(action);
  if (!normalized) return null;

  return (
    <button
      type="button"
      className="artifact-card-action"
      disabled={normalized.disabled}
      title={normalized.disabledReason || normalized.label}
      onClick={() => {
        if (normalized.disabled) return;
        if (normalized.actionType === 'retry') {
          dispatchRetry(normalized);
          return;
        }
        if (onAction) onAction(normalized);
      }}
    >
      <Icon name={actionIcon(normalized.actionType)} style={{ width: 13, height: 13 }} />
      <span>{normalized.label}</span>
      {normalized.disabled && normalized.disabledReason && (
        <span className="artifact-card-action-hint">{normalized.disabledReason}</span>
      )}
    </button>
  );
}

function StatusBadge({ status }) {
  if (!status) return null;
  const cls = `artifact-card-status artifact-card-status-${status}`;
  const labels = {
    ready: '已就绪',
    completed: '已完成',
    generating: '生成中',
    error: '异常',
    partial: '部分完成',
  };
  return (
    <span className={cls}>
      {status === 'generating' && <span className="pulse" />}
      {status === 'completed' && (
        <Icon name="check" style={{ width: 11, height: 11, color: 'var(--pos)' }} />
      )}
      {status === 'error' && (
        <Icon name="warn" style={{ width: 11, height: 11, color: 'var(--neg)' }} />
      )}
      {labels[status] || status}
    </span>
  );
}

export function ArtifactCard({ artifact, onAction, collapsed: initialCollapsed = false }) {
  const [collapsed, setCollapsed] = useState(initialCollapsed);

  if (!artifact || typeof artifact !== 'object') return null;

  const {
    title = '产物',
    status,
    preview_payload: previewPayload,
    actions = [],
  } = artifact;
  const summary = artifact.summary_for_chat || artifact.summaryForChat || artifact.summary || '';
  const refsFromList = Array.isArray(artifact.refs) ? artifact.refs : [];
  const refs = [
    artifact.primary_ref || artifact.primaryRef || refsFromList[0],
    ...(artifact.related_refs || artifact.relatedRefs || refsFromList.slice(1) || []),
  ]
    .map(formatRef)
    .filter(Boolean)
    .slice(0, 4);

  return (
    <div className="artifact-card">
      <button
        type="button"
        className="artifact-card-head"
        onClick={() => setCollapsed((value) => !value)}
        aria-expanded={!collapsed}
      >
        <span className="artifact-card-head-left">
          <Icon name="table" style={{ width: 14, height: 14 }} />
          <strong>{title}</strong>
          <StatusBadge status={status} />
        </span>
        <span className="artifact-card-head-right">
          {summary && <span className="artifact-card-summary">{summary}</span>}
          <Icon
            name="chev_down"
            className="artifact-card-chev"
            style={{ width: 12, height: 12 }}
          />
        </span>
      </button>

      {!collapsed && (
        <div className="artifact-card-body">
          {refs.length > 0 && (
            <div className="artifact-card-refs">
              <span className="artifact-card-ref-label">产物引用</span>
              {refs.map((ref) => (
                <code key={ref} className="artifact-card-ref">{ref}</code>
              ))}
            </div>
          )}

          <PreviewBody previewPayload={previewPayload} />

          {actions.length > 0 && (
            <div className="artifact-card-actions">
              {actions.map((action, index) => (
                <ActionButton
                  key={`${actionType(action)}-${action.ref || actionCheckpointRef(action) || index}`}
                  action={action}
                  onAction={onAction}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ArtifactCard;
