// bi-lead-run-panel.jsx
// BI LeadAgent run 状态面板：展示用户可见进度、摘要和 refs，过滤执行层敏感信息。

import React from 'react';

const PHASE_LABELS = {
  route_run: '路由',
  confirm_run: '确认',
  handoff_run: '交接执行',
  summarize_run: '汇总',
};

const STATUS_TITLES = {
  blocked: '需要补充条件',
  failed: '查询失败',
  completed: '查询完成',
};

function phaseLabel(phase) {
  return PHASE_LABELS[phase] || '处理中';
}

function statusTitle(status) {
  return STATUS_TITLES[status] || '正在处理';
}

function isSensitiveLine(line) {
  return /traceback|stack trace|\bselect\b|\bfrom\b|\bschema\b|\bdsl\b|raw[_\s-]*rows?/i.test(line);
}

function safeSummary(value) {
  if (!value) return '';
  return String(value)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !isSensitiveLine(line)) // 摘要按行过滤，保留业务提示，丢弃 traceback/SQL/schema/raw rows/DSL。
    .join('\n');
}

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== '');
}

function resultShape(handoff = {}, run = {}) {
  const rowCount = firstValue(handoff.row_count, handoff.rows_count, handoff.result_rows, run.row_count, run.rows_count);
  const columnCount = firstValue(
    handoff.column_count,
    handoff.columns_count,
    handoff.result_columns,
    run.column_count,
    run.columns_count,
  );
  if (rowCount === undefined || columnCount === undefined) return null;
  return `${rowCount} 行 / ${columnCount} 列`;
}

function RefRow({ label, value }) {
  if (!value) return null;
  return (
    <div className="bi-lead-run-panel__ref">
      <span>{label}</span>
      <code>{String(value)}</code>
    </div>
  );
}

export function BILeadRunPanel({ run }) {
  if (!run) return null;

  const handoff = run.handoff || {};
  const summary = safeSummary(firstValue(handoff.answer_summary, run.error_summary))
    || 'BI LeadAgent 正在处理本次查询。';
  const artifactRef = firstValue(handoff.artifact_ref, handoff.artifactRef, run.artifact_ref, run.artifactRef);
  const checkpointRef = firstValue(
    handoff.checkpoint_ref,
    handoff.checkpointRef,
    run.checkpoint_ref,
    run.checkpointRef,
  );
  const shape = resultShape(handoff, run);
  const status = run.status || 'running';

  return (
    <section className={`bi-lead-run-panel bi-lead-run-panel--${status}`} aria-label="BI LeadAgent 运行状态">
      <header className="bi-lead-run-panel__header">
        <div>
          <p className="bi-lead-run-panel__eyebrow">BI LeadAgent</p>
          <h3>{statusTitle(status)}</h3>
        </div>
        <span className="bi-lead-run-panel__phase">{phaseLabel(run.phase)}</span>
      </header>

      <p className="bi-lead-run-panel__summary">{summary}</p>

      {(artifactRef || checkpointRef || shape) && (
        <div className="bi-lead-run-panel__meta">
          <RefRow label="Artifact" value={artifactRef} />
          <RefRow label="Checkpoint" value={checkpointRef} />
          {shape && (
            <div className="bi-lead-run-panel__shape">
              <span>结果规模</span>
              <strong>{shape}</strong>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default BILeadRunPanel;
