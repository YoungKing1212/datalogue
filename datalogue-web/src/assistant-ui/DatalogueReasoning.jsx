// DatalogueReasoning.jsx
// 展示 ChainOfThought/Reason 的安全业务摘要，避免暴露控制面与查询细节。

import React from 'react';
import {
  collectSafeRefs,
  elapsedLabel,
  firstSafeText,
  normalizeStatus,
  partMetadata,
  rowCountFrom,
  statusLabel,
} from './message-parts';

function reasoningSummary(part, fallback = '已完成一个处理步骤') {
  const metadata = partMetadata(part);
  return firstSafeText(
    [
      metadata.summary,
      metadata.business_summary,
      metadata.businessSummary,
      metadata.reason,
      part?.summary,
      part?.text,
    ],
    fallback,
  );
}

export function DatalogueReasoning({ part = {}, children, group }) {
  const metadata = partMetadata(part);
  const status = normalizeStatus(part);
  const running = status === 'running';
  const refs = collectSafeRefs(
    metadata.artifact_ref,
    metadata.artifactRef,
    metadata.checkpoint_ref,
    metadata.checkpointRef,
    metadata.run_id,
    metadata.runId,
    metadata.refs,
    part.refs,
  );
  const elapsed = elapsedLabel(metadata.elapsed_ms ?? metadata.elapsedMs ?? part.elapsed_ms ?? part.elapsedMs);
  const rowCount = rowCountFrom(metadata, part);
  const count = group?.indices?.length ?? part?.indices?.length ?? null;
  const summary = reasoningSummary(part, children ? '正在整理处理过程' : '已完成一个处理步骤');

  return (
    <details className="cot cot-root" open={running}>
      <summary className="cot-trigger">
        <span className="cot-trigger-inner">
          <span>思考过程</span>
          <span className={`artifact-card-status artifact-card-status-${status === 'failed' ? 'error' : status}`}>
            {statusLabel(status)}
          </span>
          {count != null && <span className="artifact-card-ref">{count} 步</span>}
          {elapsed && <span className="artifact-card-ref">{elapsed}</span>}
        </span>
      </summary>
      <div className="cot-step">
        <div className="cot-step-icon">{running ? '...' : '✓'}</div>
        <div className="cot-step-body">
          <div className="cot-step-label">业务摘要</div>
          <div className="cot-step-text">{children || summary}</div>
          {(rowCount != null || refs.length > 0) && (
            <div className="artifact-card-refs" style={{ marginTop: 8 }}>
              {rowCount != null && <span className="artifact-card-ref">{rowCount} 行</span>}
              {refs.map((ref) => <code key={ref} className="artifact-card-ref">{ref}</code>)}
            </div>
          )}
        </div>
      </div>
    </details>
  );
}

export default DatalogueReasoning;
