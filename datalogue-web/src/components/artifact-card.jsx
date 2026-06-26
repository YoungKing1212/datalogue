import React from 'react';
import { Icon } from './icons';

const ACTION_ICONS = {
  retry: 'refresh',
  export: 'download',
  open_ref: 'link',
};

const ACTION_LABELS = {
  retry: '重试',
  export: '导出',
  open_ref: '打开引用',
};

function actionType(action) {
  return action?.action_type || action?.actionType || '';
}

function actionLabel(action) {
  const type = actionType(action);
  return action?.label || ACTION_LABELS[type] || type;
}

function actionEnabled(action) {
  return action?.enabled !== false && action?.disabled !== true;
}

function actionCheckpointRef(action) {
  return action?.checkpoint_ref || action?.checkpointRef || null;
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

function ArtifactAction({ action }) {
  const type = actionType(action);
  if (!ACTION_ICONS[type]) {
    console.debug?.('ArtifactCard ignored unknown action', type);
    return null;
  }
  const enabled = actionEnabled(action);
  const label = actionLabel(action);
  const disabledReason = action?.disabled_reason || action?.disabledReason || null;

  if (type === 'open_ref' && enabled && action?.href) {
    return (
      <a className="artifact-card-action" href={action.href}>
        <Icon name={ACTION_ICONS[type]} />
        <span>{label}</span>
      </a>
    );
  }

  return (
    <span className="artifact-card-action-wrap">
      <button
        type="button"
        className="artifact-card-action"
        disabled={!enabled}
        onClick={() => {
          if (type === 'retry') dispatchRetry(action);
        }}
      >
        <Icon name={ACTION_ICONS[type]} />
        <span>{label}</span>
      </button>
      {!enabled && disabledReason && (
        <span className="artifact-card-disabled-reason">{disabledReason}</span>
      )}
    </span>
  );
}

export default function ArtifactCard({ artifact }) {
  if (!artifact) return null;
  const actions = Array.isArray(artifact.actions) ? artifact.actions : [];
  const refs = [artifact.primary_ref || artifact.primaryRef, ...(artifact.related_refs || artifact.relatedRefs || [])]
    .filter(Boolean)
    .slice(0, 4);

  return (
    <section className={`artifact-card artifact-card-${artifact.status || 'unknown'}`}>
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
