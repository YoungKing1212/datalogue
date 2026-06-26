import { Icon } from './icons';

const RESERVED_ACTIONS = {
  retry: {
    label: '重试',
    icon: 'refresh',
    disabledReason: '缺少可恢复的 checkpoint',
  },
  export: {
    label: '导出',
    icon: 'download',
    disabledReason: '导出能力将在后续版本开放',
    forceDisabled: true,
  },
  continue_edit: {
    label: '继续编辑',
    icon: 'edit',
    disabledReason: '继续编辑能力将在后续版本开放',
    forceDisabled: true,
  },
};

function actionType(action) {
  return String(action?.action_type || action?.actionType || '').trim();
}

function actionCheckpointRef(action) {
  return action?.checkpoint_ref || action?.checkpointRef || null;
}

function normalizeActions(actions) {
  return (Array.isArray(actions) ? actions : [])
    .map((action) => {
      const type = actionType(action);
      const config = RESERVED_ACTIONS[type];
      if (!config) {
        if (type) console.debug?.('ArtifactCard ignored unknown action', type);
        return null;
      }
      const checkpointRef = actionCheckpointRef(action);
      const enabled = type === 'retry'
        ? Boolean(checkpointRef) && action?.enabled !== false && action?.disabled !== true
        : false;
      return {
        type,
        label: action?.label || config.label,
        icon: config.icon,
        enabled: config.forceDisabled ? false : enabled,
        checkpointRef,
        disabledReason: action?.disabled_reason || action?.disabledReason || config.disabledReason,
      };
    })
    .filter(Boolean);
}

function dispatchRetry(action) {
  if (!action.checkpointRef) return;
  window.dispatchEvent(
    new CustomEvent('datalogue:artifact-action', {
      // retry 只发送 checkpointRef，避免把 SQL/schema/control_plane 回传到前端动作面。
      detail: { actionType: 'retry', checkpointRef: action.checkpointRef },
    }),
  );
}

function normalizePreview(previewPayload) {
  const rows = Array.isArray(previewPayload?.rows) ? previewPayload.rows : [];
  const columns = Array.isArray(previewPayload?.columns) && previewPayload.columns.length
    ? previewPayload.columns
    : Object.keys(rows.find((row) => row && typeof row === 'object' && !Array.isArray(row)) || {});
  return { rows, columns };
}

function formatRef(ref) {
  if (!ref) return '';
  if (typeof ref === 'string') return ref;
  return ref.ref || ref.ref_id || ref.artifact_ref || '';
}

function ArtifactRefs({ primaryRef, relatedRefs }) {
  const refs = [primaryRef, ...(Array.isArray(relatedRefs) ? relatedRefs : [])]
    .map(formatRef)
    .filter(Boolean)
    .slice(0, 4);
  if (!refs.length) return null;
  return (
    <div className="artifact-ref-list">
      {refs.map((ref) => (
        <code className="artifact-ref" key={ref}>{ref}</code>
      ))}
    </div>
  );
}

function ArtifactPreview({ previewPayload }) {
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

  const { rows, columns } = normalizePreview(previewPayload);
  if (!columns.length) return null;
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

function ArtifactAction({ action }) {
  return (
    <span className="artifact-card-action-wrap">
      <button
        className="artifact-card-action"
        type="button"
        disabled={!action.enabled}
        onClick={() => {
          if (action.type === 'retry') dispatchRetry(action);
        }}
      >
        <Icon name={action.icon} />
        <span>{action.label}</span>
      </button>
      {!action.enabled && action.disabledReason && (
        <small className="artifact-card-disabled-reason">{action.disabledReason}</small>
      )}
    </span>
  );
}

export function ArtifactCard({ artifact }) {
  const visibleActions = normalizeActions(artifact?.actions);
  if (!artifact) return null;

  return (
    <section className={`artifact-card artifact-card-${artifact.status || 'unknown'}`} aria-label={artifact.title || 'Artifact'}>
      <div className="artifact-card-head">
        <div>
          <strong>{artifact.title || '查询产物'}</strong>
          {artifact.summary_for_chat && <p>{artifact.summary_for_chat}</p>}
        </div>
        {artifact.status && <span className="artifact-card-status">{artifact.status}</span>}
      </div>
      <ArtifactPreview previewPayload={artifact.preview_payload || artifact.previewPayload} />
      <ArtifactRefs
        primaryRef={artifact.primary_ref || artifact.primaryRef}
        relatedRefs={artifact.related_refs || artifact.relatedRefs}
      />
      {visibleActions.length > 0 && (
        <div className="artifact-card-actions">
          {visibleActions.map((action) => (
            <ArtifactAction action={action} key={action.type} />
          ))}
        </div>
      )}
    </section>
  );
}

export default ArtifactCard;
