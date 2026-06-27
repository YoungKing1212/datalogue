const RESERVED_ACTIONS = {
  export: {
    label: '导出',
    disabledReason: '导出能力将在后续版本开放',
  },
  continue_edit: {
    label: '继续编辑',
    disabledReason: '继续编辑能力将在后续版本开放',
  },
};

function normalizeActions(actions) {
  return (Array.isArray(actions) ? actions : [])
    .map((action) => {
      const actionType = String(action?.action_type || '').trim();
      const config = RESERVED_ACTIONS[actionType];
      if (!config) {
        if (actionType) console.debug('ArtifactCard ignored unknown action', actionType);
        return null;
      }
      return {
        actionType,
        label: action?.label || config.label,
        disabledReason: action?.disabled_reason || config.disabledReason,
      };
    })
    .filter(Boolean);
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
  return ref.ref || ref.artifact_ref || '';
}

function ArtifactRefs({ primaryRef, relatedRefs }) {
  const refs = [primaryRef, ...(Array.isArray(relatedRefs) ? relatedRefs : [])]
    .map(formatRef)
    .filter(Boolean);
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

export function ArtifactCard({ artifact }) {
  const visibleActions = normalizeActions(artifact?.actions);
  if (!artifact) return null;

  return (
    <section className="artifact-card" aria-label={artifact.title || 'Artifact'}>
      <div className="artifact-card-head">
        <strong>{artifact.title || '查询产物'}</strong>
        {artifact.status && <span>{artifact.status}</span>}
      </div>
      {artifact.summary_for_chat && <p>{artifact.summary_for_chat}</p>}
      <ArtifactPreview previewPayload={artifact.preview_payload} />
      <ArtifactRefs primaryRef={artifact.primary_ref} relatedRefs={artifact.related_refs} />
      {visibleActions.length > 0 && (
        <div className="artifact-card-actions">
          {visibleActions.map((action) => (
            <div className="artifact-card-action-wrap" key={action.actionType}>
              <button className="artifact-card-action" type="button" disabled>
                {action.label}
              </button>
              <small>{action.disabledReason}</small>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default ArtifactCard;
