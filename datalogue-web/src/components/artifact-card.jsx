import React from 'react';

import { Icon } from './icons';

const ACTION_ICONS = {
  retry: 'refresh',
  export: 'download',
  continue_edit: 'edit',
  open_ref: 'link',
};

const ACTION_LABELS = {
  retry: '重试',
  export: '导出',
  continue_edit: '继续编辑',
  open_ref: '打开引用',
};

const FIRST_PHASE_DISABLED_ACTIONS = {
  export: '导出能力将在后续版本开放',
  continue_edit: '继续编辑能力将在后续版本开放',
};

function actionType(action) {
  return String(action?.action_type || action?.actionType || '').trim();
}

function actionLabel(action) {
  const type = actionType(action);
  return action?.label || ACTION_LABELS[type] || type;
}

function actionCheckpointRef(action) {
  return action?.checkpoint_ref || action?.checkpointRef || null;
}

function normalizeAction(action) {
  const type = actionType(action);
  if (!ACTION_ICONS[type]) {
    if (type) console.debug?.('ArtifactCard ignored unknown action', type);
    return null;
  }

  const forcedDisabledReason = FIRST_PHASE_DISABLED_ACTIONS[type];
  const enabled = forcedDisabledReason
    ? false
    : action?.enabled !== false && action?.disabled !== true;

  return {
    ...action,
    actionType: type,
    label: actionLabel(action),
    enabled,
    disabledReason: forcedDisabledReason || action?.disabled_reason || action?.disabledReason || null,
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

function renderPreview(preview) {
  if (!preview) return null;
  if (typeof preview === 'string') {
    return <p className="artifact-card-preview-text">{preview}</p>;
  }
  if (Array.isArray(preview)) {
    return (
      <ul className="artifact-card-preview-list">
        {preview.slice(0, 5).map((item, index) => (
          <li key={`${index}-${String(item).slice(0, 20)}`}>{String(item)}</li>
        ))}
      </ul>
    );
  }
  if (typeof preview === 'object') {
    const rows = Array.isArray(preview.rows) ? preview.rows : [];
    const columns = Array.isArray(preview.columns) && preview.columns.length
      ? preview.columns
      : Object.keys(rows.find((row) => row && typeof row === 'object' && !Array.isArray(row)) || {});
    if (columns.length) {
      return (
        <div className="artifact-preview-payload">
          <table>
            <thead>
              <tr>
                {columns.map((column) => <th key={column}>{column}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 5).map((row, index) => (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column}>{row?.[column] == null ? '' : String(row[column])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    return (
      <dl className="artifact-card-preview-grid">
        {Object.entries(preview)
          .filter(([, value]) => value != null && value !== '')
          .slice(0, 6)
          .map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{Array.isArray(value) ? value.join('、') : String(value)}</dd>
            </div>
          ))}
      </dl>
    );
  }
  return null;
}

function formatRef(ref) {
  if (!ref) return '';
  if (typeof ref === 'string') return ref;
  return ref.ref || ref.artifact_ref || ref.ref_id || ref.artifactRef || '';
}

function ArtifactAction({ action }) {
  const normalized = normalizeAction(action);
  if (!normalized) return null;

  if (normalized.actionType === 'open_ref' && normalized.enabled && normalized.href) {
    return (
      <a className="artifact-card-action" href={normalized.href}>
        <Icon name={ACTION_ICONS[normalized.actionType]} />
        <span>{normalized.label}</span>
      </a>
    );
  }

  return (
    <span className="artifact-card-action-wrap">
      <button
        type="button"
        className="artifact-card-action"
        disabled={!normalized.enabled}
        onClick={() => {
          if (normalized.actionType === 'retry') dispatchRetry(normalized);
        }}
      >
        <Icon name={ACTION_ICONS[normalized.actionType]} />
        <span>{normalized.label}</span>
      </button>
      {!normalized.enabled && normalized.disabledReason && (
        <span className="artifact-card-disabled-reason">{normalized.disabledReason}</span>
      )}
    </span>
  );
}

export function ArtifactCard({ artifact }) {
  if (!artifact) return null;

  const actions = Array.isArray(artifact.actions) ? artifact.actions : [];
  const refs = [
    artifact.primary_ref || artifact.primaryRef,
    ...(artifact.related_refs || artifact.relatedRefs || []),
  ]
    .map(formatRef)
    .filter(Boolean)
    .slice(0, 4);

  return (
    <section className={`artifact-card artifact-card-${artifact.status || 'unknown'}`} aria-label={artifact.title || 'Artifact'}>
      <div className="artifact-card-head">
        <div>
          <h3>{artifact.title || '查询产物'}</h3>
          {artifact.summary_for_chat && <p>{artifact.summary_for_chat}</p>}
        </div>
        {artifact.status && <span className="artifact-card-status">{artifact.status}</span>}
      </div>

      {renderPreview(artifact.preview_payload || artifact.previewPayload)}

      {refs.length > 0 && (
        <div className="artifact-card-refs">
          {refs.map((ref) => (
            <code className="artifact-ref" key={ref}>{ref}</code>
          ))}
        </div>
      )}

      {actions.length > 0 && (
        <div className="artifact-card-actions">
          {actions.map((action, index) => (
            <ArtifactAction action={action} key={`${actionType(action)}-${index}`} />
          ))}
        </div>
      )}
    </section>
  );
}

export default ArtifactCard;
