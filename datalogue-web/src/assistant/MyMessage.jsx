// MyMessage — assistant-ui Message 渲染组件
// 使用 MessagePrimitive.Parts + ChainOfThought 接管 reasoning 步骤渲染
// 正文走 MessagePrimitive.Text（含 smooth 流式动画）
// 图表、产物引用和业务卡片从 metadata.custom 取，由 chat-adapter.js 在 final 事件时写入。
// 普通 Chat 用户可见层不展示 SQL 文本，SQL 仅保留在后端 control/trace 面。

import React, { useState, useMemo } from 'react';
import {
  useAuiState,
  useAui,
  MessagePrimitive,
  ChainOfThoughtPrimitive,
} from '@assistant-ui/react';
import { Icon } from '../components/icons';
import { LineChart, Donut, GroupedBar } from '../components/charts';
import MessageContent from '../components/message-content';
import TaskTimeline from '../components/task-timeline';
import ArtifactCard from '../components/artifact-card';
import { getArtifact, submitMessageFeedback } from '../api/client';

// ── Step 节点名称映射（agent panel 兼容） ──
const NODE_STEP_NAMES = {
  message_gateway: '任务理解',
  'message-gateway': '任务理解',
  lead_agent_tools: '能力匹配',
  manifest_route: '场景匹配',
  clarification_resolution: '澄清处理',
  intent_recognition: '意图识别',
  entry_intent_classification: '入口判断',
  analysis_blueprint_execute: '分析蓝图执行',
  candidate_assets: '数据资产匹配',
  query_plan: '查询规划',
  schema_recall: '数据范围确认',
  term_normalize_node: '术语标准化',
  semantic_asset_resolution_node: '语义资产解析',
  metric_resolution_node: '指标解析',
  dsl_generate: '查询生成',
  dsl_validate: '查询校验',
  dsl_compiler: '执行计划生成',
  sql_execute: '查询执行',
  sql_audit: '结果诊断',
  report_generator: '结果整理',
};

const NODE_ICONS = {
  clarification_resolution: 'book',
  intent_recognition: 'brain',
  schema_recall: 'database',
  dsl_generate: 'code',
  dsl_validate: 'check',
  dsl_compiler: 'compile',
  sql_execute: 'play',
  report_generator: 'chart_bar',
};

/**
 * StepCard — 单个流式步骤的视觉卡片（供 AgentPanel 复用）
 */
export function StepCard({ node, display_name, status, elapsed_ms }) {
  const label = NODE_STEP_NAMES[node] || NODE_STEP_NAMES[display_name] || '任务处理';
  return (
    <div className={`step-card step-card-${status}`}>
      <div className="step-icon">
        {status === 'done' ? (
          <Icon name="check" style={{ width: 11, height: 11, color: 'var(--pos)' }} />
        ) : status === 'running' ? (
          <span className="pulse" />
        ) : (
          <span className="step-pending-dot" />
        )}
      </div>
      <span className="step-label">{label}</span>
      {elapsed_ms != null && <span className="step-ms">{elapsed_ms}ms</span>}
    </div>
  );
}

/**
 * 单条 reasoning 节点 — ChainOfThoughtPrimitive.Parts 内的 Reasoning 组件
 * 接收 ReasoningMessagePartComponent props（part + status）
 */
function ReasoningPart({ text }) {
  // part 形如 { type: 'reasoning', text: '意图识别：销售归因...', parentId: 'intent_recognition' }
  // 把 parentId 当 step 节点名（chat-adapter.js 用 parentId 写 ev.node）
  const node = useAuiState((s) => s.part?.parentId);
  const label = NODE_STEP_NAMES[node] || '任务处理';
  const icon = NODE_ICONS[node] || 'brain';
  return (
    <div className="cot-step">
      <div className="cot-step-icon">
        <Icon name={icon} style={{ width: 12, height: 12 }} />
      </div>
      <div className="cot-step-body">
        <div className="cot-step-label">{label}</div>
        <div className="cot-step-text">{text}</div>
      </div>
    </div>
  );
}

/**
 * ChainOfThought 包装组件 — 用 ChainOfThoughtPrimitive 渲染
 * MessagePrimitive.Parts components={{ ChainOfThought: ... }} 接收 ComponentType
 *
 * Root 的 data-state 反映 collapsed 状态（assistant-ui Root 本身是 plain div，
 * 需要我们手动接 collapsed scope 才能在 CSS 里控制箭头旋转）
 */
function ChainOfThought() {
  const collapsed = useAuiState((s) => s.chainOfThought?.collapsed ?? true);
  return (
    <div className="cot">
      <ChainOfThoughtPrimitive.Root
        className="cot-root"
        data-state={collapsed ? 'collapsed' : 'expanded'}
      >
        <ChainOfThoughtPrimitive.AccordionTrigger asChild>
          <button type="button" className="cot-trigger">
            <span className="cot-trigger-inner">
              <Icon name="brain" style={{ width: 13, height: 13 }} />
              <span>思考过程</span>
              <span className="cot-trigger-arrow">⌃</span>
            </span>
          </button>
        </ChainOfThoughtPrimitive.AccordionTrigger>
        <ChainOfThoughtPrimitive.Parts
          components={{ Reasoning: ReasoningPart }}
        />
      </ChainOfThoughtPrimitive.Root>
    </div>
  );
}

/**
 * 自定义 Text 组件 — 用 MessagePartPrimitive.Text（支持 smooth 流式动画）
 * 把 part 的 text 转给 MessageContent 渲染（剥离 <think>，保留 markdown）
 */
function MessageTextPart() {
  const text = useAuiState((s) => s.part?.text);
  const status = useAuiState((s) => s.part?.status);
  const isStreaming = status?.type === 'running';
  if (!text) return null;
  return <MessageContent text={text} streaming={isStreaming} />;
}

function joinValues(values, fallback = '未识别') {
  if (!Array.isArray(values) || values.length === 0) return fallback;
  return values.filter(Boolean).slice(0, 6).join('、') || fallback;
}

function sourceLabel(item) {
  if (!item) return '';
  const path = [item.table, item.column].filter(Boolean).join('.');
  return path || item.name || '';
}

function candidateValue(candidate, keys) {
  for (const key of keys) {
    const value = candidate?.[key];
    if (value != null && String(value).trim()) return value;
  }
  return null;
}

function termCandidateId(candidate) {
  return candidateValue(candidate, ['term_id', 'termId', 'id', 'asset_id', 'assetId']);
}

function datasetCandidateId(candidate) {
  return candidateValue(candidate, ['dataset_id', 'datasetId', 'id']);
}

function clarificationKind(clarification, routePayload) {
  const kind = clarification?.kind || routePayload?.kind || '';
  if (String(kind).startsWith('dataset_') || routePayload?.kind === 'manifest_route') {
    return 'dataset';
  }
  return 'term';
}

function termCandidateLabel(candidate, optionIndex) {
  const nested = candidate?.term || candidate?.business_term || candidate?.businessTerm || {};
  return (
    candidateValue(candidate, [
      'display_name',
      'displayName',
      'label',
      'title',
      'name',
      'term_name',
      'termName',
      'asset_name',
      'assetName',
    ]) ||
    candidateValue(nested, ['display_name', 'displayName', 'name', 'term_name', 'termName']) ||
    (termCandidateId(candidate) ? `术语 ${termCandidateId(candidate)}` : `候选 ${optionIndex}`)
  );
}

function datasetCandidateLabel(candidate, optionIndex) {
  return (
    candidateValue(candidate, [
      'dataset_name',
      'datasetName',
      'display_name',
      'displayName',
      'label',
      'title',
      'name',
    ]) ||
    (datasetCandidateId(candidate) ? `数据集 ${datasetCandidateId(candidate)}` : `选项 ${optionIndex}`)
  );
}

function termCandidateSubLabel(candidate, label) {
  const nested = candidate?.term || candidate?.business_term || candidate?.businessTerm || {};
  const name = candidateValue(candidate, ['name', 'term_name', 'termName']) ||
    candidateValue(nested, ['name', 'term_name', 'termName']);
  if (name && name !== label) return name;
  return candidateValue(candidate, ['term_type', 'termType']) ||
    candidateValue(nested, ['term_type', 'termType']) ||
    '业务术语';
}

function datasetCandidateSubLabel(candidate) {
  const parts = [];
  const domains = candidate?.business_domain || candidate?.businessDomain || [];
  if (Array.isArray(domains) && domains.length) {
    parts.push(domains.filter(Boolean).slice(0, 2).join('、'));
  }
  if (candidate?.score != null) {
    parts.push(`得分 ${candidate.score}`);
  }
  if (candidate?.review_status || candidate?.reviewStatus) {
    parts.push(candidate.review_status || candidate.reviewStatus);
  }
  return parts.length ? parts.join(' · ') : '数据集';
}

function termCandidateDefinition(candidate) {
  const nested = candidate?.term || candidate?.business_term || candidate?.businessTerm || {};
  return candidateValue(candidate, ['definition', 'description', 'desc']) ||
    candidateValue(nested, ['definition', 'description', 'desc']);
}

function datasetCandidateDefinition(candidate) {
  const reasons = candidate?.reasons || [];
  if (Array.isArray(reasons) && reasons.length) {
    return reasons.filter(Boolean).slice(0, 2).join('；');
  }
  return candidateValue(candidate, ['reason', 'description', 'desc']);
}

function confidenceText(level) {
  if (level === 'high') return '高';
  if (level === 'medium') return '中';
  if (level === 'low') return '低';
  return '未知';
}

function toArray(value) {
  if (Array.isArray(value)) return value;
  return value == null || value === '' ? [] : [value];
}

function dedupeValues(values, limit = 6) {
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const text = String(value || '').trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    result.push(text);
    if (result.length >= limit) break;
  }
  return result;
}

function labelFromValue(value) {
  if (value == null) return null;
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value);
  }
  if (typeof value !== 'object') return null;
  const nested = value.term || value.metric || value.dimension || value.asset || {};
  const label =
    candidateValue(value, [
      'display_name',
      'displayName',
      'label',
      'title',
      'resolved',
      'entity',
      'name',
      'metric_name',
      'metricName',
      'dimension_name',
      'dimensionName',
      'term_name',
      'termName',
      'asset_name',
      'assetName',
      'field',
      'column',
    ]) ||
    candidateValue(nested, ['display_name', 'displayName', 'name', 'label']);
  if (label) return label;
  const path = [value.table, value.column].filter(Boolean).join('.');
  return path || null;
}

function labelsFromValues(...sources) {
  return dedupeValues(
    sources.flatMap((source) => toArray(source).map(labelFromValue).filter(Boolean)),
  );
}

function formatTimeRange(value) {
  if (!value) return null;
  if (typeof value === 'string') return value;
  if (typeof value !== 'object') return null;
  return (
    value.label ||
    value.display_name ||
    value.displayName ||
    [value.start, value.end].filter(Boolean).join(' 至 ') ||
    [value.start_date, value.end_date].filter(Boolean).join(' 至 ') ||
    null
  );
}

function buildQueryCaliber(custom) {
  const explicit = custom.queryCaliber || {};
  const explanationCaliber = custom.answerExplanation?.caliber || {};
  const source = custom.queryCaliber ? explicit : explanationCaliber;

  const metrics = labelsFromValues(source.metrics);
  const dimensions = labelsFromValues(source.dimensions);
  const timeRange = formatTimeRange(source.timeRange || source.time_range);
  const filters = dedupeValues(toArray(source.filters).map((item) => String(item || '').trim()).filter(Boolean));
  const routePath = source.routePath || source.route_path || '业务口径';
  const inheritedText = source.inheritedText || source.inherited_text || '未继承上一轮口径。';
  const generationMode = source.generationMode || source.generation_mode || '';
  const hasCaliberSignal = Boolean(custom.queryCaliber || custom.answerExplanation);
  const hasAny = hasCaliberSignal && (metrics.length || dimensions.length || timeRange || filters.length || routePath);

  if (!hasAny) return null;
  return {
    metrics,
    dimensions,
    timeRange: timeRange || '未识别',
    filters,
    routePath,
    inheritedText,
    generationMode,
  };
}

function correctionTextFromCaliber(caliber) {
  const parts = [
    caliber.metrics.length ? `指标=${caliber.metrics.join('、')}` : null,
    caliber.dimensions.length ? `维度=${caliber.dimensions.join('、')}` : null,
    caliber.timeRange && caliber.timeRange !== '未识别' ? `时间=${caliber.timeRange}` : null,
    caliber.filters.length ? `过滤=${caliber.filters.join('、')}` : null,
  ].filter(Boolean);
  return `纠正口径：${parts.length ? parts.join('；') : '请补充正确指标、维度、时间和过滤条件'}。请按这个口径重新查询。`;
}

function QueryCaliberCard({ custom, onRerun }) {
  const caliber = buildQueryCaliber(custom);
  if (!caliber) return null;

  const dispatchCorrection = () => {
    const detail = { text: correctionTextFromCaliber(caliber), caliber };
    window.dispatchEvent(new CustomEvent('datalogue:query-caliber-correction', { detail }));
    window.dispatchEvent(new CustomEvent('datalogue:composer-submit', { detail }));
  };

  const dispatchRerun = () => {
    window.dispatchEvent(new CustomEvent('datalogue:query-caliber-rerun', { detail: { caliber } }));
    onRerun?.();
  };

  const items = [
    ['指标', caliber.metrics.length ? caliber.metrics.join('、') : '未识别'],
    ['维度', caliber.dimensions.length ? caliber.dimensions.join('、') : '未识别'],
    ['时间', caliber.timeRange],
    ['过滤', caliber.filters.length ? caliber.filters.join('、') : '无'],
  ];

  return (
    <div className="query-caliber-card">
      <div className="query-caliber-head">
        <span className="query-caliber-icon">
          <Icon name="filter_alt" />
        </span>
        <div className="query-caliber-title">
          <strong>查询口径</strong>
          <span>{caliber.routePath}</span>
        </div>
        <button type="button" className="query-caliber-action" onClick={dispatchRerun}>
          <Icon name="refresh" />
          重跑
        </button>
      </div>
      <div className="query-caliber-grid">
        {items.map(([label, value]) => (
          <div key={label} className="query-caliber-item">
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="query-caliber-foot">
        <span>{caliber.inheritedText}</span>
        <button type="button" onClick={dispatchCorrection}>发送纠正</button>
      </div>
    </div>
  );
}

/**
 * AnswerExplanation — 结构化展示后端确定性解释包。
 */
function AnswerExplanation({ explanation }) {
  const [open, setOpen] = useState(false);
  if (!explanation) return null;
  const caliber = explanation.caliber || {};
  const confidence = explanation.confidence || {};
  const sqlSummary = explanation.sql_summary || {};
  const risks = explanation.risks || [];
  const confirmation = explanation.confirmation || {};
  const sources = (explanation.data_sources || []).map(sourceLabel).filter(Boolean);
  const level = confidence.level || 'unknown';
  const riskCount = risks.length;

  return (
    <div className={`answer-explanation answer-explanation-${level} ${open ? 'open' : ''}`}>
      <button
        type="button"
        className="answer-explanation-head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="answer-explanation-icon">
          <Icon name={level === 'low' ? 'warn' : 'shield'} />
        </span>
        <div className="answer-explanation-title">
          <strong>口径与可信度</strong>
          <span>
            {confidenceText(level)} · {Number(confidence.score ?? 0).toFixed(2)}
            {riskCount ? ` · ${riskCount} 条风险` : ' · 无明显风险'}
            {confirmation.required ? ' · 需要确认' : ''}
          </span>
        </div>
        <Icon name="chev_down" className="answer-explanation-chev" />
      </button>

      {open && (
        <div className="answer-explanation-body">
          {confirmation.required && (
            <div className="answer-explanation-confirm">
              <Icon name="warn" />
              <span>{confirmation.message || '当前回答置信度偏低，请先确认口径。'}</span>
            </div>
          )}

          <div className="answer-explanation-grid">
            <div>
              <span>指标</span>
              <strong>{joinValues(caliber.metrics)}</strong>
            </div>
            <div>
              <span>维度</span>
              <strong>{joinValues(caliber.dimensions)}</strong>
            </div>
            <div>
              <span>术语</span>
              <strong>{joinValues(caliber.terms)}</strong>
            </div>
            <div>
              <span>蓝图</span>
              <strong>{joinValues(caliber.blueprints, '未命中')}</strong>
            </div>
          </div>

          <div className="answer-explanation-lines">
            <div>
              <span>数据来源</span>
              <p>{sources.length ? sources.slice(0, 8).join('、') : '未能确定具体数据来源'}</p>
            </div>
            <div>
              <span>查询校验</span>
              <p>
                {sqlSummary.preview
                  ? '查询语句已通过执行前校验'
                  : '本次未生成查询语句'}
              </p>
            </div>
            <div>
              <span>风险提示</span>
              {risks.length ? (
                <ol className="answer-risk-list">
                  {risks
                    .map((item) => item.message)
                    .filter(Boolean)
                    .map((message, index) => (
                      <li key={`${index}-${message}`}>{message}</li>
                    ))}
                </ol>
              ) : (
                <p>未发现明显风险</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TermClarificationCard({ clarification, routePayload, onSelect }) {
  const candidates = clarification?.candidates || routePayload?.candidates || [];
  if (!candidates.length) return null;
  const kind = clarificationKind(clarification, routePayload);
  const isDataset = kind === 'dataset';
  return (
    <div className="term-clarification-card">
      <div className="term-clarification-head">
        <span className="term-clarification-icon">
          <Icon name={isDataset ? 'database' : 'book'} />
        </span>
        <div>
          <strong>{isDataset ? '请选择数据集' : '请选择业务术语口径'}</strong>
          <span>{isDataset ? '点击数据集后发送，或直接回复序号 / 数据集名称' : '点击候选后发送，或直接回复序号 / 术语名称'}</span>
        </div>
      </div>
      <div className="term-clarification-options">
        {candidates.map((candidate, index) => {
          const optionIndex = candidate.index || index + 1;
          const label = isDataset
            ? datasetCandidateLabel(candidate, optionIndex)
            : termCandidateLabel(candidate, optionIndex);
          const subLabel = isDataset
            ? datasetCandidateSubLabel(candidate)
            : termCandidateSubLabel(candidate, label);
          const definition = isDataset
            ? datasetCandidateDefinition(candidate)
            : termCandidateDefinition(candidate);
          const candidateId = isDataset ? datasetCandidateId(candidate) : termCandidateId(candidate);
          return (
            <button
              key={`${candidateId || optionIndex}-${label}`}
              type="button"
              className="term-clarification-option"
              onClick={() => onSelect(candidate, optionIndex, label, kind)}
            >
              <span className="term-clarification-index">{optionIndex}</span>
              <span className="term-clarification-body">
                <strong>{label}</strong>
                <em>{subLabel}</em>
                {definition && <small>{definition}</small>}
              </span>
            </button>
          );
        })}
      </div>
      {clarification?.expiresAt && (
        <div className="term-clarification-expire">
          有效期至 {new Date(clarification.expiresAt).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}

/**
 * CandidateDatasetCard — C-ready 候选数据集确认卡片
 * 只展示 dataset_name 和 short_reason（业务原因），
 * 不展示字段、表、资产详情。提供 confirm / change_dataset 操作。
 */
function CandidateDatasetCard({ candidateDatasets, onConfirm }) {
  if (!candidateDatasets || !Array.isArray(candidateDatasets.candidates) || !candidateDatasets.candidates.length) {
    return null;
  }

  const handleConfirm = (candidate) => {
    if (onConfirm) onConfirm(candidate);
    if (candidate.dataset_id != null) {
      // 构造 clarification response，与 TermClarificationCard 保持一致
      window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = {
        clarification_id: candidateDatasets.clarification_id || null,
        selected_index: candidate.index,
        selected_text: candidate.dataset_name,
        selected_dataset_id: candidate.dataset_id,
      };
    }
    window.dispatchEvent(new CustomEvent('datalogue:composer-submit', {
      detail: { text: `确认使用：${candidate.dataset_name}` },
    }));
  };

  return (
    <div className="candidate-dataset-card">
      <div className="candidate-dataset-head">
        <span className="candidate-dataset-icon">
          <Icon name="database" />
        </span>
        <div>
          <strong>候选数据集确认</strong>
          <span>根据您的问题，匹配到以下候选数据集，请确认</span>
        </div>
      </div>
      <div className="candidate-dataset-options">
        {candidateDatasets.candidates.map((candidate, index) => (
          <button
            key={candidate.dataset_id || index}
            type="button"
            className="candidate-dataset-option"
            onClick={() => handleConfirm({ ...candidate, index: index + 1 })}
          >
            <span className="candidate-dataset-index">{index + 1}</span>
            <span className="candidate-dataset-body">
              <strong>{candidate.dataset_name || `候选数据集 ${index + 1}`}</strong>
              {candidate.short_reason && <em>{candidate.short_reason}</em>}
            </span>
            <span className="candidate-dataset-action">
              <Icon name="arrow_up_right" style={{ width: 12, height: 12 }} />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function RepairPlanCard({ repairPlan }) {
  if (!repairPlan || (!repairPlan.summary && !repairPlan.repairPlanRef)) return null;

  const confirmRepair = () => {
    window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = {
      repair_plan_ref: repairPlan.repairPlanRef || null,
      checkpoint_ref: repairPlan.checkpointRef || null,
      selected_action: 'confirm',
    };
    window.dispatchEvent(new CustomEvent('datalogue:composer-submit', {
      detail: { text: '确认修复' },
    }));
  };

  return (
    <div className="candidate-dataset-card repair-plan-card">
      <div className="candidate-dataset-head">
        <span className="candidate-dataset-icon">
          <Icon name="branch" />
        </span>
        <div>
          <strong>查询修复</strong>
          <span>{repairPlan.summary || '已生成自动修复方案'}</span>
        </div>
      </div>
      {repairPlan.repairPlanRef && (
        <div className="artifact-card-refs">
          <span className="artifact-card-ref-label">修复引用</span>
          <code className="artifact-card-ref">{repairPlan.repairPlanRef}</code>
        </div>
      )}
      {repairPlan.requiresUserConfirmation && (
        <div className="candidate-dataset-options">
          <button
            type="button"
            className="candidate-dataset-option"
            onClick={confirmRepair}
          >
            <span className="candidate-dataset-index">1</span>
            <span className="candidate-dataset-body">
              <strong>确认修复</strong>
              <em>继续同一任务并使用该修复方案</em>
            </span>
            <span className="candidate-dataset-action">
              <Icon name="arrow_up_right" style={{ width: 12, height: 12 }} />
            </span>
          </button>
        </div>
      )}
    </div>
  );
}

function TraceLinkCard({ traceId, sessionId, observability, stepTrace = [] }) {
  if (!traceId && !sessionId) return null;

  const baseUrl = observability?.base_url || observability?.baseUrl || null;
  const projectId = observability?.project_id || observability?.projectId || null;
  const traceUrl = observability?.trace_url || observability?.traceUrl || (
    baseUrl && projectId && traceId
      ? `${baseUrl.replace(/\/$/, '')}/project/${encodeURIComponent(projectId)}/traces/${encodeURIComponent(traceId)}`
      : null
  );
  const enabled = observability?.enabled;
  const active = observability?.active;
  const statusText = enabled === false ? '未启用' : active === false ? '本地记录' : '可追踪';
  const environment = observability?.environment || '—';
  const release = observability?.release || '—';

  const copyTrace = (event) => {
    event.stopPropagation();
    if (!traceId) return;
    navigator.clipboard.writeText(traceId).catch(console.error);
  };
  const openAuditPage = (event) => {
    event.stopPropagation();
    if (!traceId) return;
    window.location.href = `/audit-query?trace_id=${encodeURIComponent(traceId)}`;
  };
  const showInPanel = () => {
    const panelObservability = observability
      ? { ...observability, trace_url: traceUrl || observability.trace_url || observability.traceUrl || null }
      : { trace_url: traceUrl, base_url: baseUrl, project_id: projectId };
    window.dispatchEvent(new CustomEvent('datalogue:run-start'));
    if (Array.isArray(stepTrace)) {
      for (const step of stepTrace) {
        if (step && typeof step === 'object') {
          window.dispatchEvent(new CustomEvent('datalogue:trace', {
            detail: { ...step, type: 'step' },
          }));
        }
      }
    }
    const detail = {
      type: 'final',
      langfuse_trace_id: traceId || null,
      langfuse_session_id: sessionId || null,
      observability: panelObservability,
    };
    window.dispatchEvent(new CustomEvent('datalogue:trace', { detail }));
    window.dispatchEvent(new CustomEvent('datalogue:trace-panel-open', { detail }));
  };

  return (
    <div className="message-trace-link">
      <button type="button" className="message-trace-main" onClick={openAuditPage}>
        <Icon name="trace" />
        <span>查看链路</span>
        <em>{statusText} · {environment} · {release}</em>
      </button>
      <code title={traceId || sessionId}>{traceId || sessionId}</code>
      {traceId && (
        <button type="button" className="message-trace-btn" onClick={copyTrace} title="复制 Trace ID">
          <Icon name="copy" />
        </button>
      )}
      <button type="button" className="message-trace-btn" onClick={showInPanel} title="在右侧面板查看">
        <Icon name="branch" />
      </button>
    </div>
  );
}

function artifactEntries({ resultRef, reportRef, subagentToolResults }) {
  const entries = [];
  const seen = new Set();
  const push = (kind, ref, datasetId = null) => {
    if (!ref || seen.has(ref)) return;
    seen.add(ref);
    entries.push({ kind, ref, datasetId });
  };
  push('result', resultRef);
  push('report', reportRef);
  for (const item of Array.isArray(subagentToolResults) ? subagentToolResults : []) {
    push('result', item?.result_ref, item?.dataset_id);
    push('report', item?.report_ref, item?.dataset_id);
  }
  return entries;
}

function artifactTitle(entry) {
  const label = entry.kind === 'report' ? '报告' : '结果';
  return entry.datasetId ? `数据集 ${entry.datasetId} ${label}` : `查看${label}`;
}

function ArtifactPreviewBody({ artifact }) {
  const json = artifact?.content_json;
  const text = artifact?.content_text;
  const isSqlResult = artifact?.kind === 'sql_result' || Array.isArray(json?.rows);
  if (isSqlResult) {
    return <div className="artifact-empty">结果产物已生成，请通过受控详情页查看。</div>;
  }

  const reportText = text || json?.markdown || json?.report || json?.text || json?.content;
  if (artifact?.kind === 'report' && reportText) {
    return (
      <div className="artifact-report">
        <MessageContent text={String(reportText)} />
      </div>
    );
  }

  const fallback = text ?? (json ? JSON.stringify(json, null, 2) : '');
  if (!fallback) return <div className="artifact-empty">暂无可展示内容</div>;
  return <pre>{fallback}</pre>;
}

function ArtifactAccessCard({ resultRef, reportRef, subagentToolResults }) {
  const entries = useMemo(
    () => artifactEntries({ resultRef, reportRef, subagentToolResults }),
    [resultRef, reportRef, subagentToolResults],
  );
  const [activeRef, setActiveRef] = useState(null);
  const [artifact, setArtifact] = useState(null);
  const [loadingRef, setLoadingRef] = useState(null);
  const [error, setError] = useState('');

  if (!entries.length) return null;

  const loadArtifact = async (entry) => {
    if (activeRef === entry.ref && artifact) {
      setActiveRef(null);
      setArtifact(null);
      setError('');
      return;
    }
    setActiveRef(entry.ref);
    setLoadingRef(entry.ref);
    setError('');
    try {
      setArtifact(await getArtifact(entry.ref));
    } catch (_e) {
      setArtifact(null);
      setError('产物已过期或不可用');
    } finally {
      setLoadingRef(null);
    }
  };

  return (
    <div className="artifact-card">
      <div className="artifact-actions">
        {entries.map((entry) => (
          <button
            key={entry.ref}
            type="button"
            className={`artifact-btn ${activeRef === entry.ref ? 'active' : ''}`}
            onClick={() => loadArtifact(entry)}
            title={entry.ref}
          >
            <Icon name={entry.kind === 'report' ? 'book' : 'table'} style={{ width: 13, height: 13 }} />
            <span>{artifactTitle(entry)}</span>
            {loadingRef === entry.ref && <em>加载中</em>}
          </button>
        ))}
      </div>
      {error && <div className="artifact-error">{error}</div>}
      {artifact && activeRef && (
        <div className="artifact-preview">
          <div className="artifact-preview-head">
            <span>{artifact.kind}</span>
            <span>{artifact.content_mime}</span>
          </div>
          <ArtifactPreviewBody artifact={artifact} />
        </div>
      )}
    </div>
  );
}

/**
 * AIMessage — 助理消息气泡
 * - 用 MessagePrimitive.Parts 把 reasoning / text 分开渲染
 * - ChainOfThought 默认折叠，AccordionTrigger 控制展开
 * - 正文 markdown 走 MessageContent
 * - 图表、产物引用和业务卡片从 metadata.custom 取
 */
export function AIMessage() {
  const api = useAui();
  const message = useAuiState((s) => s.message);
  const [showActions, setShowActions] = useState(false);
  const [feedbackState, setFeedbackState] = useState(null);

  const isStreaming = message?.status?.type === 'running';
  const custom = message?.metadata?.custom || {};
  const chartType = custom.chartType || null;
  const chartTitle = custom.chartTitle || null;
  const chartSubtitle = custom.chartSubtitle || null;
  const chartData = custom.chartData || null;
  const citations = custom.citations || null;
  const answerExplanation = custom.answerExplanation || null;
  const routePayload = custom.routePayload || null;
  const clarification = custom.clarification || null;
  const messageId = custom.messageId || null;
  const langfuseTraceId = custom.langfuseTraceId || null;
  const langfuseSessionId = custom.langfuseSessionId || null;
  const observability = custom.observability || null;
  const stepTrace = custom.stepTrace || [];
  const savedFeedback = custom.feedback || null;
  const resultRef = custom.resultRef || null;
  const reportRef = custom.reportRef || null;
  const subagentToolResults = custom.subagentToolResults || null;
  // C-ready 数据结构
  const taskTimeline = custom.taskTimeline || null;
  const artifactCard = custom.artifactCard || null;
  const candidateDatasets = custom.candidateDatasets || null;
  const repairPlan = custom.repairPlan || null;

  const handleSelectClarification = (candidate, optionIndex, label, kind = 'term') => {
    const clarificationId =
      clarification?.clarificationId || routePayload?.clarification_id || null;
    const clarificationResponse = {
      clarification_id: clarificationId,
      selected_index: optionIndex,
      selected_text: label,
    };
    if (kind === 'dataset') {
      clarificationResponse.selected_dataset_id = datasetCandidateId(candidate);
    } else {
      clarificationResponse.selected_term_id = termCandidateId(candidate);
    }
    window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = clarificationResponse;
    window.dispatchEvent(new CustomEvent('datalogue:composer-submit', {
      detail: { text: `选择：${label}` },
    }));
  };

  const handleCopy = () => {
    const text = (message?.content || [])
      .filter((p) => p.type === 'text')
      .map((p) => p.text)
      .join('');
    navigator.clipboard.writeText(text).catch(console.error);
  };

  const handleFeedback = async (action) => {
    if (!messageId) {
      setFeedbackState('当前消息暂不支持反馈');
      return;
    }
    setFeedbackState('提交中...');
    try {
      await submitMessageFeedback(messageId, {
        action,
        trace_id: langfuseTraceId,
      });
      setFeedbackState(action === 'approve' ? '已点赞' : '已点踩');
    } catch (_e) {
      setFeedbackState('反馈失败');
    }
  };

  const handleRegenerate = () => {
    api.message().reload();
  };

  return (
    <div
      className="msg-row msg-ai"
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      <div className="ai-head">
        <div className="ai-mark" />
        <span className="name">数语</span>
        <span className="stage">
          {isStreaming ? (
            <>
              <span className="pulse" />
              正在生成…
            </>
          ) : (
            <>
              <Icon name="check" style={{ width: 11, height: 11, color: 'var(--pos)' }} />
              已生成
            </>
          )}
        </span>
      </div>

      {/* 业务时间线 — 展示任务理解 / 数据集匹配 / BI 执行 / 结果产物 / 下一步 */}
      <TaskTimeline events={taskTimeline} />

      {/* 内容区 — reasoning 由 ChainOfThought 接管，text 走 markdown */}
      <MessagePrimitive.Parts
        components={{
          ChainOfThought,
          Text: MessageTextPart,
        }}
      />

      <QueryCaliberCard custom={custom} onRerun={handleRegenerate} />

      <AnswerExplanation explanation={answerExplanation} />

      <TermClarificationCard
        clarification={clarification}
        routePayload={routePayload}
        onSelect={handleSelectClarification}
      />

      {/* C-ready 候选数据集确认 — 只展示 dataset_name + 业务原因 */}
      <CandidateDatasetCard candidateDatasets={candidateDatasets} />

      <RepairPlanCard repairPlan={repairPlan} />

      <TraceLinkCard
        traceId={langfuseTraceId}
        sessionId={langfuseSessionId}
        observability={observability}
        stepTrace={stepTrace}
      />

      <ArtifactAccessCard
        resultRef={resultRef}
        reportRef={reportRef}
        subagentToolResults={subagentToolResults}
      />

      {/* C-ready ArtifactCard — 统一产物卡片 */}
      <ArtifactCard artifact={artifactCard} />

      {/* 图表 — 有 chartType 时渲染 */}
      {chartType && (
        <div className="chart-card">
          <div className="chart-head">
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{chartTitle || '数据图表'}</span>
                <span
                  style={{
                    fontSize: 11,
                    padding: '2px 7px',
                    borderRadius: 4,
                    background: 'var(--bg-2)',
                    color: 'var(--text-3)',
                  }}
                >
                  <Icon
                    name={
                      chartType === 'bar'
                        ? 'chart_bar'
                        : chartType === 'line'
                          ? 'chart_line'
                          : 'chart_pie'
                    }
                    style={{ width: 11, height: 11 }}
                  />
                  {chartType} · 自动推荐
                </span>
              </div>
              {chartSubtitle && (
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                  {chartSubtitle}
                </div>
              )}
            </div>
          </div>
          {chartType === 'bar' && <GroupedBar data={chartData} h={200} w={640} />}
          {chartType === 'line' && <LineChart data={chartData} h={200} w={640} />}
          {chartType === 'pie' && <Donut data={chartData} h={200} w={640} />}
        </div>
      )}

      {/* 引用来源 */}
      {citations && citations.length > 0 && (
        <div className="citations">
          <span className="citations-label">数据来源：</span>
          {citations.map((c, i) => (
            <span key={i} className="citation-tag">
              {c}
            </span>
          ))}
        </div>
      )}

      {/* 操作栏 — hover 显示 */}
      {!isStreaming && (
        <div className={`msg-actions ${showActions ? 'visible' : ''}`}>
          <button className="action-btn" title="复制回答" onClick={handleCopy}>
            <Icon name="copy" />
          </button>
          <button className="action-btn" title={feedbackState || savedFeedback?.action || '点赞'} onClick={() => handleFeedback('approve')}>
            <Icon name="thumbs_up" />
          </button>
          <button className="action-btn" title={feedbackState || savedFeedback?.action || '点踩'} onClick={() => handleFeedback('reject')}>
            <Icon name="thumbs_down" />
          </button>
          <button className="action-btn" title="重新生成" onClick={handleRegenerate}>
            <Icon name="refresh" />
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * UserMessage — 用户消息气泡
 */
export function UserMessage() {
  const content = useAuiState((s) => s.message?.content);
  const text = useMemo(
    () =>
      (content || [])
        .filter((p) => p.type === 'text')
        .map((p) => p.text || '')
        .join(''),
    [content],
  );
  return (
    <div className="msg-row msg-user">
      <div className="bubble">{text}</div>
    </div>
  );
}
