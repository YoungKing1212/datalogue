// DatalogueToolUI.jsx
// Dataset/Toolkit 工具调用的安全展示卡，只显示摘要、状态、耗时、refs 和行数。
// 覆盖四态：running / completed / failed / confirmation（对应契约 running/complete/error/requires_action）。
// 严禁把 SQL、schema、raw_rows、query_plan 等控制面 payload 投进 DOM——只用安全摘要字段。

import React from 'react';
import {
  collectSafeRefs,
  elapsedLabel,
  firstSafeText,
  normalizeStatus,
  partMetadata,
  partResult,
  rowCountFrom,
  safeNumber,
  statusLabel,
  toolDisplayName,
} from './message-parts';

function toolSummary(part, result, metadata) {
  return firstSafeText(
    [
      result.summary,
      result.business_summary,
      result.businessSummary,
      result.message,
      metadata.summary,
      metadata.business_summary,
      metadata.businessSummary,
      part.summary,
      part.text,
    ],
    '工具调用已记录，详细执行过程请在 Workbench 查看。',
  );
}

function columnCountFrom(...sources) {
  for (const source of sources) {
    const count = safeNumber(
      source?.column_count ?? source?.columnCount ?? source?.columns_count ?? source?.columnsCount,
    );
    if (count != null) return count;
  }
  return null;
}

export function DatalogueToolUI({ part = {} }) {
  const result = partResult(part);
  const metadata = partMetadata(part);
  const status = normalizeStatus(part, result);
  const elapsed = elapsedLabel(
    result.elapsed_ms
      ?? result.elapsedMs
      ?? metadata.elapsed_ms
      ?? metadata.elapsedMs
      ?? part.elapsed_ms
      ?? part.elapsedMs
      ?? part.timing?.elapsed_ms
      ?? part.timing?.elapsedMs,
  );
  const rowCount = rowCountFrom(result, metadata, part, part.args || {});
  const columnCount = columnCountFrom(result, metadata, part, part.args || {});
  const refs = collectSafeRefs(
    result.artifact_ref,
    result.artifactRef,
    result.checkpoint_ref,
    result.checkpointRef,
    result.run_id,
    result.runId,
    result.refs,
    metadata.artifact_ref,
    metadata.artifactRef,
    metadata.checkpoint_ref,
    metadata.checkpointRef,
    metadata.refs,
    part.args?.refs,
  );

  return (
    <div className="artifact-card" data-tool-status={status}>
      <div className="artifact-card-head" aria-expanded="true">
        <span className="artifact-card-head-left">
          <strong>{toolDisplayName(part.toolName || part.tool_name || result.tool_name)}</strong>
          <span className={`artifact-card-status artifact-card-status-${status === 'failed' ? 'error' : status}`}>
            {statusLabel(status)}
          </span>
        </span>
        <span className="artifact-card-head-right">
          {elapsed && <span className="artifact-card-summary">{elapsed}</span>}
        </span>
      </div>
      <div className="artifact-card-body">
        <p className="artifact-card-preview-text">{toolSummary(part, result, metadata)}</p>
        {(rowCount != null || columnCount != null || refs.length > 0) && (
          <div className="artifact-card-refs">
            {rowCount != null && <span className="artifact-card-ref">{rowCount} 行</span>}
            {columnCount != null && <span className="artifact-card-ref">{columnCount} 列</span>}
            {refs.map((ref) => <code key={ref} className="artifact-card-ref">{ref}</code>)}
          </div>
        )}
      </div>
    </div>
  );
}

export default DatalogueToolUI;
