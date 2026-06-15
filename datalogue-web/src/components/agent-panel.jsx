import React, { useState } from 'react';
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
//   traceMeta        {traceId, sessionId, messageId, observability} Langfuse 观测元数据

const BUSINESS_STEP_NAMES = {
  lead_agent_tools: 'lead_agent_tools',
  manifest_route: 'manifest_route',
  clarification_resolution: 'clarification_resolution',
  intent_recognition: 'intent_recognition',
  entry_intent_classification: 'entry_intent_classification',
  analysis_blueprint_execute: 'analysis_blueprint_execute',
  candidate_assets: 'subagent.candidate_assets',
  query_plan: 'subagent.query_plan',
  schema_recall: 'schema_recall',
  term_normalize_node: 'term_normalize_node',
  semantic_asset_resolution_node: 'semantic_asset_resolution_node',
  metric_resolution_node: 'metric_resolution_node',
  dsl_generate: 'dsl_generate',
  dsl_validate: 'dsl_validate',
  dsl_compiler: 'dsl_compiler',
  sql_execute: 'sql_execute',
  sql_audit: 'sql_audit',
  report_generator: 'report_generator',
};

const QUERY_TYPE_LABELS = {
  detail_query: '明细查询',
  metric_query: '指标查询',
  blueprint_query: '蓝图查询',
  knowledge_qa: '知识问答',
  ambiguous: '需要澄清',
  unsupported: '暂不支持',
};

const EXECUTION_STRATEGY_LABELS = {
  blueprint_execute: '直接执行蓝图',
  blueprint_as_reference: '参考蓝图生成查询',
  query_graph: '普通查询生成',
  clarify: '需要补充信息',
  reject: '无法处理',
};

function enumLabel(labels, value) {
  return value ? labels[value] || value : null;
}

function businessStepName(step) {
  return BUSINESS_STEP_NAMES[step?.node] || step?.display_name || step?.node || 'step';
}

function summarizeCompletedSteps(steps, sqlResult) {
  const doneSteps = (steps || []).filter((step) => step.status === 'done');
  const blocked = (steps || []).find((step) => step.status === 'blocked' || step.status === 'error');
  const lastDone = doneSteps[doneSteps.length - 1];
  const names = doneSteps.map(businessStepName).slice(-4);
  const rows = resultRowCount(sqlResult);
  const rowText = rows != null ? ` · 返回 ${rows} 行` : '';
  if (blocked) {
    return `已停在${businessStepName(blocked)}${rowText}`;
  }
  if (names.length === 0) {
    return `已完成回答${rowText}`;
  }
  return `已完成 ${names.join(' / ')}${lastDone?.elapsed_ms != null ? ` · ${lastDone.elapsed_ms}ms` : ''}${rowText}`;
}

function resultRowCount(sqlResult) {
  if (!sqlResult) return null;
  if (Array.isArray(sqlResult.rows)) return sqlResult.rows.length;
  return sqlResult.rows ?? sqlResult.rowCount ?? sqlResult.row_count ?? null;
}

function formatQueryPlanDetails(queryPlan) {
  if (!queryPlan || typeof queryPlan !== 'object') return [];
  const explanation = queryPlan.explanation || {};
  const queryType = enumLabel(QUERY_TYPE_LABELS, queryPlan.query_type);
  const executionStrategy = enumLabel(EXECUTION_STRATEGY_LABELS, queryPlan.execution_strategy);
  const decisionFactors = Array.isArray(queryPlan.decision_factors)
    ? queryPlan.decision_factors
    : [];
  const plannerWarnings = Array.isArray(queryPlan.planner_warnings)
    ? queryPlan.planner_warnings
    : [];
  const governanceSuggestions = Array.isArray(queryPlan.governance_suggestions)
    ? queryPlan.governance_suggestions
    : [];
  const firstFactor = decisionFactors.find((item) => item?.message)?.message;
  const firstWarning = plannerWarnings.find((item) => item?.message)?.message;
  const firstSuggestion = governanceSuggestions.find((item) => item?.message)?.message;
  return [
    queryType ? `查询类型：${queryType}` : null,
    executionStrategy ? `执行策略：${executionStrategy}` : null,
    explanation.summary ? `说明：${explanation.summary}` : null,
    firstFactor ? `依据：${firstFactor}` : null,
    firstWarning ? `提示：${firstWarning}` : null,
    firstSuggestion ? `治理建议：${firstSuggestion}` : null,
  ].filter(Boolean);
}

function formatCandidateAssetSummary(candidateAssets) {
  const summary = candidateAssets?.summary;
  if (!summary || typeof summary !== 'object') return [];
  const summaryFields = [
    ['fields', '字段'],
    ['field_count', '字段'],
    ['columns', '字段'],
    ['column_count', '字段'],
    ['tables', '表'],
    ['table_count', '表'],
    ['blueprints', '蓝图'],
    ['blueprint_count', '蓝图'],
    ['metrics', '指标'],
    ['metric_count', '指标'],
    ['dimensions', '维度'],
    ['dimension_count', '维度'],
    ['terms', '术语'],
    ['term_count', '术语'],
  ];
  const seen = new Set();
  return summaryFields
    .map(([key, label]) => {
      if (seen.has(label)) return null;
      const value = summary[key];
      const count = Array.isArray(value) ? value.length : value;
      if (count == null || count === '' || count === 0) return null;
      seen.add(label);
      return `${label} ${count} 个`;
    })
    .filter(Boolean);
}

function StepDetail({ step }) {
  const details =
    step.node === 'query_plan' && step.query_plan
      ? formatQueryPlanDetails(step.query_plan)
      : step.node === 'candidate_assets' && step.candidate_assets
      ? formatCandidateAssetSummary(step.candidate_assets)
      : [];

  if (details.length === 0) return null;
  return (
    <div style={{ marginLeft: 22, marginTop: -2, marginBottom: 8, fontSize: 11, color: 'var(--text-3)', lineHeight: 1.5 }}>
      {details.join(' · ')}
    </div>
  );
}

// ── 步骤列表 ──────────────────────────────────────────────
function StepList({ steps, compact = false, sqlResult = null }) {
  if (!steps || steps.length === 0) return null;
  if (compact) {
    return (
      <div>
        <div className="agent-section-label">执行摘要</div>
        <div className="agent-process-summary">
          <Icon name="check" />
          <span>{summarizeCompletedSteps(steps, sqlResult)}</span>
        </div>
      </div>
    );
  }
  return (
    <div>
      <div className="agent-section-label">执行过程</div>
      {steps.map((step, i) => {
        const key = `${step.node || 'step'}-${i}`;
        return (
          <div key={key}>
            <div className="agent-step">
              <div className={`agent-step-icon ${step.status}`}>
                {step.status === 'done' && <Icon name="check" />}
              </div>
              <span className={`agent-step-label ${step.status === 'running' ? 'running' : ''}`}>
                {businessStepName(step)}
              </span>
              {step.elapsed_ms != null && step.status === 'done' && (
                <span className="agent-step-ms">{step.elapsed_ms}ms</span>
              )}
            </div>
            <StepDetail step={step} />
          </div>
        );
      })}
    </div>
  );
}

// ── Langfuse Trace 概览 ───────────────────────────────────
function TraceSummary({ traceMeta }) {
  if (!traceMeta) return null;

  const observability = traceMeta.observability || {};
  const hasTrace = Boolean(traceMeta.traceId || traceMeta.sessionId);
  const disabled = observability.enabled === false;
  const active = observability.active === true;
  const statusText = disabled ? '未启用' : active ? '已上报' : hasTrace ? '可追踪' : '本地记录';
  const statusClass = disabled ? 'disabled' : active ? 'active' : 'local';

  const copy = (value) => {
    if (!value) return;
    navigator.clipboard.writeText(value).catch(console.error);
  };
  const openAuditTrace = () => {
    if (!traceMeta.traceId) return;
    window.location.href = `/audit-query?trace_id=${encodeURIComponent(traceMeta.traceId)}`;
  };

  return (
    <div>
      <div className="agent-section-label">Langfuse Trace</div>
      <div className="trace-summary">
        <div className="trace-summary-head">
          <span className={`trace-status ${statusClass}`}>{statusText}</span>
          {traceMeta.traceId && (
            <button className="trace-action" type="button" onClick={openAuditTrace} title="打开查询审计">
              <Icon name="log" />
            </button>
          )}
        </div>

        <div className="trace-kv">
          <span>环境</span>
          <strong>{observability.environment || '—'}</strong>
        </div>
        <div className="trace-kv">
          <span>版本</span>
          <strong>{observability.release || '—'}</strong>
        </div>
        <div className="trace-id-row">
          <span>Trace ID</span>
          <code>{traceMeta.traceId || '—'}</code>
          {traceMeta.traceId && (
            <button className="trace-action" type="button" onClick={() => copy(traceMeta.traceId)} title="复制 Trace ID">
              <Icon name="copy" />
            </button>
          )}
        </div>
        <div className="trace-id-row">
          <span>Session</span>
          <code>{traceMeta.sessionId || '—'}</code>
          {traceMeta.sessionId && (
            <button className="trace-action" type="button" onClick={() => copy(traceMeta.sessionId)} title="复制 Session ID">
              <Icon name="copy" />
            </button>
          )}
        </div>
      </div>
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
  const [open, setOpen] = useState(false);
  if (!sql) return null;
  const copy = (event) => {
    event.stopPropagation();
    navigator.clipboard.writeText(sql).catch(console.error);
  };
  return (
    <div>
      <div className="agent-section-label">生成的 SQL</div>
      <div className={`sql-preview ${open ? 'open' : ''}`}>
        <div
          role="button"
          tabIndex={0}
          className="sql-preview-head"
          onClick={() => setOpen((v) => !v)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              setOpen((v) => !v);
            }
          }}
          aria-expanded={open}
        >
          <span><Icon name="sql" /> SQL 已生成</span>
          <button className="btn ghost" style={{ fontSize: 11, padding: '2px 8px' }} onClick={copy}>
            复制
          </button>
          <Icon name="chev_down" className="sql-preview-chev" />
        </div>
        {open && <pre>{sql}</pre>}
      </div>
    </div>
  );
}

// ── 执行摘要 ──────────────────────────────────────────────
function ResultSummary({ sqlResult }) {
  if (!sqlResult) return null;
  const rows = resultRowCount(sqlResult);
  return (
    <div>
      <div className="agent-section-label">执行结果</div>
      <div className="result-grid">
        <div className="result-card">
          <div className="val">{rows ?? '—'}</div>
          <div className="lbl">返回行数</div>
        </div>
        <div className="result-card">
          <div className="val">{sqlResult.elapsed_ms != null ? `${sqlResult.elapsed_ms}ms` : '—'}</div>
          <div className="lbl">执行耗时</div>
        </div>
      </div>
      {sqlResult.columns && sqlResult.columns.length > 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 6 }}>
          字段：{(sqlResult.columns || []).map(c => sqlResult.column_labels?.[c] || c).join(' · ')}
        </div>
      )}
    </div>
  );
}

// ── 主组件 ────────────────────────────────────────────────
function AgentPanel({
  open,
  onClose,
  steps = [],
  intent = null,
  metricResolution = null,
  generationMode = null,
  sql = null,
  sqlResult = null,
  traceMeta = null,
}) {
  if (!open) return null;
  const executionSettled = Boolean(traceMeta) && !steps.some((step) => step.status === 'running');

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
        <TraceSummary traceMeta={traceMeta} />
        <StepList steps={steps} compact={executionSettled} sqlResult={sqlResult} />
        <IntentCard intent={intent} metricResolution={metricResolution} generationMode={generationMode} />
        <SqlPreview sql={sql} />
        <ResultSummary sqlResult={sqlResult} />
        {steps.length === 0 && !intent && !sql && !sqlResult && !traceMeta && (
          <div style={{ color: 'var(--text-3)', fontSize: 12, textAlign: 'center', paddingTop: 32 }}>
            发问后此处显示 Agent 执行详情
          </div>
        )}
      </div>
    </div>
  );
}

export { AgentPanel };
