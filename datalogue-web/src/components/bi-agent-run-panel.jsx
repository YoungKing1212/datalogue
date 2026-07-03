// bi-agent-run-panel.jsx
// BI Agent run 状态面板：展示用户可见进度、摘要和 refs，过滤执行层敏感信息。

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
  return (
    /traceback|stack trace|\bsql\b|\bselect\b|\bfrom\b|\bdrop\b|\bdelete\b|\binsert\b|\bupdate\b|\balter\b|create\s+table|\bschema\b|\bdsl\b|raw[_\s-]*rows?|result[_\s-]*rows?|result[_\s-]*columns?/i
      .test(line)
  );
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

function summaryFallback(status) {
  if (status === 'blocked') return '需要补充查询条件。';
  if (status === 'failed') return '查询失败，请稍后重试。';
  return 'BI Agent 正在处理本次查询。';
}

function resultShape(handoff = {}) {
  const rowCount = handoff.row_count;
  const columnCount = handoff.column_count;
  if (!Number.isFinite(rowCount) || !Number.isFinite(columnCount)) return null; // 结果规模只信任 K1/K2 数字契约字段，避免数组/兼容字段把原始行列内容带到 UI。
  return `${rowCount} 行 / ${columnCount} 列`;
}

function RefRow({ label, value }) {
  if (!value) return null;
  return (
    <div className="bi-agent-run-panel__ref">
      <span>{label}</span>
      <code>{String(value)}</code>
    </div>
  );
}

export function BIAgentRunPanel({ run }) {
  if (!run) return null;

  const handoff = run.handoff || {};
  const status = run.status || 'running';
  const summary = safeSummary(firstValue(handoff.answer_summary, run.error_summary))
    || summaryFallback(status); // 敏感摘要被全部过滤后，按状态给业务兜底，避免失败/阻塞态误显示为仍在处理。
  const artifactRef = firstValue(handoff.artifact_ref, handoff.artifactRef, run.artifact_ref, run.artifactRef);
  const checkpointRef = firstValue(
    handoff.checkpoint_ref,
    handoff.checkpointRef,
    run.checkpoint_ref,
    run.checkpointRef,
  );
  const shape = resultShape(handoff);

  return (
    <section className={`bi-agent-run-panel bi-agent-run-panel--${status}`} aria-label="BI Agent 运行状态">
      <header className="bi-agent-run-panel__header">
        <div>
          <p className="bi-agent-run-panel__eyebrow">BI Agent</p>
          <h3>{statusTitle(status)}</h3>
        </div>
        <span className="bi-agent-run-panel__phase">{phaseLabel(run.phase)}</span>
      </header>

      <p className="bi-agent-run-panel__summary">{summary}</p>

      {(artifactRef || checkpointRef || shape) && (
        <div className="bi-agent-run-panel__meta">
          <RefRow label="Artifact" value={artifactRef} />
          <RefRow label="Checkpoint" value={checkpointRef} />
          {shape && (
            <div className="bi-agent-run-panel__shape">
              <span>结果规模</span>
              <strong>{shape}</strong>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default BIAgentRunPanel;
