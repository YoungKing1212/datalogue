import React from 'react';
import { Icon } from './icons';

// AgentPanel — 右侧 Agent 执行状态面板
// 纯展示组件，所有数据由 ChatScreen 通过 props 注入，无内部状态。
//
// Props:
//   open       boolean             面板是否可见
//   onClose    () => void          关闭回调
//   steps      StepObj[]           节点进度列表
//   intent     {intent, entities}  意图识别结果（null = 未就绪）
//   sql        string              生成的 SQL（null = 未就绪）
//   sqlResult  {rows, columns, elapsed_ms}  执行摘要（null = 未就绪）

// ── 步骤列表 ──────────────────────────────────────────────
function StepList({ steps }) {
  if (!steps || steps.length === 0) return null;
  return (
    <div>
      <div className="agent-section-label">执行过程</div>
      {steps.map((step, i) => (
        <div key={i} className="agent-step">
          <div className={`agent-step-icon ${step.status}`}>
            {step.status === 'done' && <Icon name="check" />}
          </div>
          <span className={`agent-step-label ${step.status === 'running' ? 'running' : ''}`}>
            {step.display_name || step.node}
          </span>
          {step.elapsed_ms != null && step.status === 'done' && (
            <span className="agent-step-ms">{step.elapsed_ms}ms</span>
          )}
        </div>
      ))}
    </div>
  );
}

// ── 意图卡片 ──────────────────────────────────────────────
function IntentCard({ intent }) {
  if (!intent) return null;
  const tags = [
    intent.intent && `意图: ${intent.intent}`,
    ...(intent.entities?.metrics   || []).map(m => `指标: ${m}`),
    ...(intent.entities?.dimensions || []).map(d => `维度: ${d}`),
    intent.entities?.time_range && `时间: ${intent.entities.time_range}`,
  ].filter(Boolean);

  if (tags.length === 0) return null;
  return (
    <div>
      <div className="agent-section-label">意图解析</div>
      <div className="intent-tags">
        {tags.map((t, i) => <span key={i} className="intent-tag">{t}</span>)}
      </div>
    </div>
  );
}

// ── SQL 预览 ──────────────────────────────────────────────
function SqlPreview({ sql }) {
  if (!sql) return null;
  const copy = () => navigator.clipboard.writeText(sql).catch(console.error);
  return (
    <div>
      <div className="agent-section-label">生成的 SQL</div>
      <div className="sql-preview">
        <div className="sql-preview-head">
          <span><Icon name="sql" /> SQL</span>
          <button className="btn ghost" style={{ fontSize: 11, padding: '2px 8px' }} onClick={copy}>
            复制
          </button>
        </div>
        <pre>{sql}</pre>
      </div>
    </div>
  );
}

// ── 执行摘要 ──────────────────────────────────────────────
function ResultSummary({ sqlResult }) {
  if (!sqlResult) return null;
  return (
    <div>
      <div className="agent-section-label">执行结果</div>
      <div className="result-grid">
        <div className="result-card">
          <div className="val">{sqlResult.rows ?? '—'}</div>
          <div className="lbl">返回行数</div>
        </div>
        <div className="result-card">
          <div className="val">{sqlResult.elapsed_ms != null ? `${sqlResult.elapsed_ms}ms` : '—'}</div>
          <div className="lbl">执行耗时</div>
        </div>
      </div>
      {sqlResult.columns && sqlResult.columns.length > 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 6 }}>
          字段：{sqlResult.columns.join(' · ')}
        </div>
      )}
    </div>
  );
}

// ── 主组件 ────────────────────────────────────────────────
function AgentPanel({ open, onClose, steps = [], intent = null, sql = null, sqlResult = null }) {
  if (!open) return null;

  return (
    <div className="agent-panel">
      <div className="agent-panel-head">
        <Icon name="trace" style={{ width: 14, height: 14, color: 'var(--accent)' }} />
        <h3>Agent 执行过程</h3>
        <button className="icon-btn" onClick={onClose} title="关闭">
          <Icon name="x" />
        </button>
      </div>
      <div className="agent-panel-body">
        <StepList steps={steps} />
        <IntentCard intent={intent} />
        <SqlPreview sql={sql} />
        <ResultSummary sqlResult={sqlResult} />
        {steps.length === 0 && !intent && !sql && !sqlResult && (
          <div style={{ color: 'var(--text-3)', fontSize: 12, textAlign: 'center', paddingTop: 32 }}>
            发问后此处显示 Agent 执行详情
          </div>
        )}
      </div>
    </div>
  );
}

export { AgentPanel };
