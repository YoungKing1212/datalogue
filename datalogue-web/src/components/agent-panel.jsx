import React from 'react';
import { Icon } from './icons';

// AgentPanel — 右侧 Agent 执行状态面板
// 纯展示组件，所有数据由 ChatPage 通过 props 注入，无内部状态。
//
// Props:
//   open             boolean             面板是否可见
//   onClose          () => void          关闭回调
//   steps            StepObj[]           节点进度列表
//   intent           {intent, entities}  意图识别结果（null = 未就绪）
//   metricResolution {metrics, dimensions, all_matched, unresolved} 指标解析结果
//   generationMode   'semantic'|'inferred'|null  DSL 生成模式
//   sql              string              生成的 SQL（null = 未就绪）
//   sqlResult        {rows, columns, elapsed_ms}  执行摘要（null = 未就绪）

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
function IntentCard({ intent, metricResolution, generationMode }) {
  if (!intent) return null;

  const badge = generationMode === 'semantic'
    ? { text: '已定义指标', bg: '#e8f5e9', color: '#2e7d32', border: '#c8e6c9' }
    : generationMode === 'inferred'
    ? { text: 'AI 推断，建议验证', bg: '#fff8e1', color: '#f57c00', border: '#ffecb3' }
    : null;

  // 指标/维度解析详情
  const resolvedMetrics = metricResolution?.metrics || [];
  const resolvedDimensions = metricResolution?.dimensions || [];

  const matchTypeLabel = {
    exact: '精确匹配',
    display_name: '显示名匹配',
    synonym: '同义词匹配',
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <div className="agent-section-label" style={{ marginBottom: 0 }}>意图解析</div>
        {badge && (
          <span style={{
            fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 10,
            background: badge.bg, color: badge.color, border: `1px solid ${badge.border}`,
          }}>{badge.text}</span>
        )}
      </div>

      {/* 原始意图标签 */}
      <div className="intent-tags" style={{ marginBottom: 8 }}>
        {intent.intent && <span className="intent-tag">意图: {intent.intent}</span>}
        {intent.entities?.time_range && <span className="intent-tag">时间: {intent.entities.time_range}</span>}
      </div>

      {/* 指标解析结果 */}
      {resolvedMetrics.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>指标解析</div>
          <div className="intent-tags">
            {resolvedMetrics.map((r, i) => (
              <span key={i} className="intent-tag" style={{
                background: r.status === 'matched' ? 'var(--surface)' : '#ffebee',
                color: r.status === 'matched' ? 'var(--text)' : '#c62828',
                borderColor: r.status === 'matched' ? 'var(--hairline)' : '#ef9a9a',
              }}>
                {r.entity}
                {r.status === 'matched' ? (
                  <> → <strong>{r.resolved}</strong> <span style={{ opacity: 0.7 }}>({matchTypeLabel[r.match_type] || r.match_type})</span></>
                ) : (
                  <> <span style={{ opacity: 0.7 }}>(未定义)</span></>
                )}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 维度解析结果 */}
      {resolvedDimensions.length > 0 && (
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>维度解析</div>
          <div className="intent-tags">
            {resolvedDimensions.map((r, i) => (
              <span key={i} className="intent-tag" style={{
                background: r.status === 'matched' ? 'var(--surface)' : '#ffebee',
                color: r.status === 'matched' ? 'var(--text)' : '#c62828',
                borderColor: r.status === 'matched' ? 'var(--hairline)' : '#ef9a9a',
              }}>
                {r.entity}
                {r.status === 'matched' ? (
                  <> → <strong>{r.resolved}</strong> <span style={{ opacity: 0.7 }}>({matchTypeLabel[r.match_type] || r.match_type})</span></>
                ) : (
                  <> <span style={{ opacity: 0.7 }}>(未定义)</span></>
                )}
              </span>
            ))}
          </div>
        </div>
      )}
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
function AgentPanel({ open, onClose, steps = [], intent = null, metricResolution = null, generationMode = null, sql = null, sqlResult = null }) {
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
        <IntentCard intent={intent} metricResolution={metricResolution} generationMode={generationMode} />
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
