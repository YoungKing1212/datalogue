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
  ActionBarPrimitive,
  groupPartByType,
  useMessageTiming,
} from '@assistant-ui/react';
import { StreamdownTextPrimitive } from '@assistant-ui/react-streamdown';
import { code } from '@streamdown/code';
import { math } from '@streamdown/math';
import { Collapse, Timeline, Tag, Typography } from 'antd';
import 'katex/dist/katex.min.css';
import { Icon } from '../components/icons';
import { LineChart, Donut, GroupedBar } from '../components/charts';
import ArtifactCard from '../components/artifact-card';
import { getArtifact } from '../api/client';

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
  reasoning_summary: '推理摘要',
  live_thinking: '推理过程',
  multi_agent_handoff: 'Agent 协作',
  confirmation: '待确认',
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

const THINK_OPEN_RE = /<think\b[^>]*>/i;
const THINK_CLOSE_RE = /<\/think\s*>/i;
const REASONING_LABEL_BLOCKED_RE = /\b(select|insert|update|delete|from|join|where|schema|raw_rows?|raw_result|query_plan|field_patch|repair_patch|control_plane)\b|[`;]/i;

// 推理标签专用清洗：空值或疑似 SQL/schema 等内部字段不作为标签。
function safeReasoningLabelText(value) {
  const text = String(value ?? '').trim();
  if (!text || REASONING_LABEL_BLOCKED_RE.test(text)) return null;
  return text.slice(0, 40);
}

function reasoningStepLabel(part, node) {
  if (node && String(node).startsWith('agent-')) {
    return part.agentName || (part.agentRole === 'worker' ? 'Worker Agent' : 'Lead Agent');
  }
  if (node === 'reasoning_summary') {
    // 最终摘要每条自带业务标题（如“识别任务”“生成结果”），优先使用，避免全部退化为“任务处理”。
    return safeReasoningLabelText(part.title) || NODE_STEP_NAMES.reasoning_summary;
  }
  return NODE_STEP_NAMES[node] || safeReasoningLabelText(part.title) || '任务处理';
}

function stripThink(raw = '') {
  const openMatch = THINK_OPEN_RE.exec(raw);
  if (!openMatch) return raw;
  const before = raw.slice(0, openMatch.index);
  const rest = raw.slice(openMatch.index + openMatch[0].length);
  const closeMatch = THINK_CLOSE_RE.exec(rest);
  if (!closeMatch) return before;
  return (before + rest.slice(closeMatch.index + closeMatch[0].length)).trim();
}

function balanceFences(src = '') {
  const fences = (src.match(/```/g) || []).length;
  return fences % 2 === 1 ? `${src}\n\`\`\`` : src;
}

const markdownComponents = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
  ),
  table: ({ children }) => (
    <div className="md-table-wrap"><table>{children}</table></div>
  ),
};

function preprocessAssistantMarkdown(text) {
  return balanceFences(stripThink(text || ''));
}

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
 * ChainOfThought 包装组件 — assistant-ui 提供 reasoning parts，Ant Design 负责可见的推理摘要 UI。
 */
// 把长推理文本切成小节：优先按换行，其次按中英文句末标点，便于用户分段阅读一大块思考。
function splitThinkingSegments(text) {
  const raw = String(text || '').trim();
  if (!raw) return [];
  let segments = raw.split(/\n+/).map((s) => s.trim()).filter(Boolean);
  if (segments.length <= 1) {
    segments = raw
      .split(/(?<=[。！？；.!?;])\s*/)
      .map((s) => s.trim())
      .filter(Boolean);
  }
  // 过滤纯标点/过短噪声段（如单独一行的 "." 或 "。"）：至少含 2 个字母/数字/汉字才保留。
  segments = segments.filter((s) => (s.match(/[\p{L}\p{N}]/gu) || []).length >= 2);
  return segments.slice(0, 60);
}

function ReasoningText({ part }) {
  const segments = splitThinkingSegments(part.text);
  if (segments.length <= 1) {
    // 短文本不拆分，pre-wrap 保留原有换行。
    return (
      <Typography.Text
        className="cot-ant-text"
        style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
      >
        {part.text}
      </Typography.Text>
    );
  }
  return (
    <div className="cot-ant-segments">
      {segments.map((seg, index) => (
        <div key={index} className="cot-ant-segment">
          <span className="cot-ant-segment-dot" />
          <span className="cot-ant-segment-text">{seg}</span>
        </div>
      ))}
    </div>
  );
}

function ChainOfThought({ children: _children }) {
  const message = useAuiState((s) => s.message);
  const reasonings = (message?.content || []).filter((part) => part.type === 'reasoning');
  const isStreaming = message?.status?.type === 'running';
  if (!reasonings.length) return null;

  const items = reasonings.map((part, index) => {
    const node = part.parentId;
    const label = reasoningStepLabel(part, node);
    const icon = NODE_ICONS[node] || 'brain';
    return {
      key: `${node || 'reasoning'}-${index}`,
      color: index === reasonings.length - 1 && isStreaming ? 'processing' : 'blue',
      content: (
        <div className="cot-ant-step">
          <Tag variant="filled" className="cot-ant-tag">
            <Icon name={icon} style={{ width: 12, height: 12 }} />
            {label}
          </Tag>
          <ReasoningText part={part} />
        </div>
      ),
    };
  });

  return (
    <div className="cot">
      <Collapse
        ghost
        size="small"
        className="cot-ant"
        defaultActiveKey={isStreaming ? ['thinking'] : []}
        items={[
          {
            key: 'thinking',
            label: (
              <span className="cot-ant-label">
                <Icon name="brain" style={{ width: 13, height: 13 }} />
                <span>推理摘要</span>
                <Tag variant="filled">{reasonings.length}</Tag>
              </span>
            ),
            children: <Timeline className="cot-ant-timeline" items={items} />,
          },
        ]}
      />
    </div>
  );
}

/**
 * 自定义 Text 组件 — 用 MessagePartPrimitive.Text（支持 smooth 流式动画）
 * 把 part 的 text 转给 MessageContent 渲染（剥离 <think>，保留 markdown）
 */
function MessageTextPart() {
  return (
    <StreamdownTextPrimitive
      containerClassName="ai-message md-body"
      plugins={{ code, math }}
      components={markdownComponents}
      preprocess={preprocessAssistantMarkdown}
    />
  );
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

function termCandidateSubLabel(candidate, label) {
  const nested = candidate?.term || candidate?.business_term || candidate?.businessTerm || {};
  const name = candidateValue(candidate, ['name', 'term_name', 'termName']) ||
    candidateValue(nested, ['name', 'term_name', 'termName']);
  if (name && name !== label) return name;
  return candidateValue(candidate, ['term_type', 'termType']) ||
    candidateValue(nested, ['term_type', 'termType']) ||
    '业务术语';
}

function termCandidateDefinition(candidate) {
  const nested = candidate?.term || candidate?.business_term || candidate?.businessTerm || {};
  return candidateValue(candidate, ['definition', 'description', 'desc']) ||
    candidateValue(nested, ['definition', 'description', 'desc']);
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

const DETAIL_ROW_LIMIT = 100;
const DETAIL_CELL_LIMIT = 240;
const DETAIL_BLOCKED_TEXT_RE = /\b(select|from|join|where|schema|raw_rows|raw_result|query_plan|field_patch|repair_patch|control_plane)\b/i;

function formatArtifactRef(ref) {
  if (!ref) return '';
  if (typeof ref === 'string') return ref;
  if (typeof ref !== 'object') return '';
  return ref.ref_id || ref.ref || ref.artifact_ref || ref.artifactRef || '';
}

function primaryArtifactRef(artifactCard) {
  const refs = Array.isArray(artifactCard?.refs) ? artifactCard.refs : [];
  return formatArtifactRef(
    artifactCard?.primary_ref || artifactCard?.primaryRef || refs[0],
  );
}

function actionArtifactRef(action, artifactCard) {
  return formatArtifactRef(
    action?.ref ||
      action?.payload_ref ||
      action?.payloadRef ||
      action?.artifact_ref ||
      action?.artifactRef ||
      primaryArtifactRef(artifactCard),
  );
}

function isReadableArtifactRef(ref) {
  return /^artifact:/.test(String(ref || ''));
}

function safeDetailColumnText(value) {
  const text = String(value || '').trim();
  if (
    !text ||
    DETAIL_BLOCKED_TEXT_RE.test(text) ||
    /sql|schema|raw|hidden|secret|queryplan|query_plan|patch|control|dsl/i.test(text)
  ) {
    return '';
  }
  return text;
}

function detailRowsFromArtifact(artifact) {
  const rows = artifact?.content_json?.rows;
  return Array.isArray(rows) ? rows : [];
}

function detailColumnsFromArtifact(artifact) {
  const json = artifact?.content_json || {};
  const rows = detailRowsFromArtifact(artifact);
  const declared = Array.isArray(json.columns) ? json.columns : [];
  const inferred = rows[0] && typeof rows[0] === 'object' && !Array.isArray(rows[0])
    ? Object.keys(rows[0])
    : [];
  const labels = json.column_labels && typeof json.column_labels === 'object'
    ? json.column_labels
    : {};
  const source = declared.length ? declared : inferred;
  return source
    .map((column, index) => {
      const key = String(column || '').trim();
      const label = safeDetailColumnText(labels[key] || labels[index] || key);
      return { key, index, label };
    })
    .filter((column) => column.key && column.label && safeDetailColumnText(column.key));
}

function detailCellText(value) {
  if (value === null || value === undefined) return '';
  const raw = typeof value === 'string'
    ? value
    : typeof value === 'number' || typeof value === 'boolean'
      ? String(value)
      : JSON.stringify(value);
  const text = String(raw || '').replace(/\r?\n/g, ' ').trim();
  if (!text || DETAIL_BLOCKED_TEXT_RE.test(text)) return '';
  return text.length > DETAIL_CELL_LIMIT ? `${text.slice(0, DETAIL_CELL_LIMIT)}...` : text;
}

function detailRowValue(row, column) {
  if (Array.isArray(row)) return row[column.index];
  if (row && typeof row === 'object') return row[column.key];
  return null;
}

function ArtifactDetailPanel({ detail, onClose }) {
  if (!detail || detail.status === 'idle') return null;
  const artifact = detail.artifact || null;
  const rows = detailRowsFromArtifact(artifact);
  const columns = detailColumnsFromArtifact(artifact);
  const visibleRows = rows.slice(0, DETAIL_ROW_LIMIT);
  const declaredRowCount = Number(artifact?.content_json?.row_count);
  const rowCount = Number.isFinite(declaredRowCount) ? declaredRowCount : rows.length;

  return (
    <div className="artifact-detail-panel">
      <div className="artifact-detail-head">
        <div>
          <strong>查询结果详情</strong>
          <span>{detail.ref || '结果产物'}</span>
        </div>
        <button type="button" className="artifact-detail-close" onClick={onClose}>
          <Icon name="x" />
        </button>
      </div>

      {detail.status === 'loading' && (
        <div className="artifact-card-empty">正在加载结果数据...</div>
      )}

      {detail.status === 'error' && (
        <div className="artifact-card-empty">{detail.error || '结果数据暂不可读取'}</div>
      )}

      {detail.status === 'ready' && (!rows.length || !columns.length) && (
        <div className="artifact-card-empty">当前产物没有可展示的表格数据</div>
      )}

      {detail.status === 'ready' && rows.length > 0 && columns.length > 0 && (
        <>
          <div className="artifact-detail-meta">
            <span>{rowCount} 行</span>
            <span>{columns.length} 列</span>
          </div>
          <div className="artifact-card-table-wrap artifact-detail-table-wrap">
            <table className="artifact-card-table">
              <thead>
                <tr>
                  {columns.map((column) => (
                    <th key={`${column.key}-${column.index}`}>{column.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {columns.map((column) => (
                      <td key={`${rowIndex}-${column.key}-${column.index}`}>
                        {detailCellText(detailRowValue(row, column))}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rowCount > visibleRows.length && (
            <div className="artifact-card-table-more">
              当前展示前 {visibleRows.length} 行，共 {rowCount} 行
            </div>
          )}
        </>
      )}
    </div>
  );
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
  // 数据集选择统一交给 CandidateDatasetCard，避免同一轮弹出两套选择组件。
  if (kind === 'dataset') return null;
  return (
    <div className="term-clarification-card">
      <div className="term-clarification-head">
        <span className="term-clarification-icon">
          <Icon name="book" />
        </span>
        <div>
          <strong>请选择业务术语口径</strong>
          <span>点击候选后发送，或直接回复序号 / 术语名称</span>
        </div>
      </div>
      <div className="term-clarification-options">
        {candidates.map((candidate, index) => {
          const optionIndex = candidate.index || index + 1;
          const label = termCandidateLabel(candidate, optionIndex);
          const subLabel = termCandidateSubLabel(candidate, label);
          const definition = termCandidateDefinition(candidate);
          const candidateId = termCandidateId(candidate);
          return (
            <button
              key={`${candidateId || optionIndex}-${label}`}
              type="button"
              className="term-clarification-option"
              onClick={() => onSelect(candidate, optionIndex, label)}
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
      const originalQuestion = String(
        candidate.original_question
          || candidate.originalQuestion
          || candidateDatasets.original_question
          || candidateDatasets.originalQuestion
          || candidateDatasets.question
          || '',
      ).trim();
      // 构造 clarification response；dataset_id 用于锁定数据集，原始问题用于确认后续跑同一 BI 查询。
      const clarificationResponse = {
        clarification_id: candidateDatasets.clarification_id || null,
        selected_index: candidate.index,
        selected_text: candidate.dataset_name,
        selected_dataset_id: candidate.dataset_id,
      };
      if (originalQuestion) {
        clarificationResponse.original_question = originalQuestion;
      }
      window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = clarificationResponse;
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
  const [artifactDetail, setArtifactDetail] = useState({ status: 'idle' });

  const isStreaming = message?.status?.type === 'running';
  const timing = useMessageTiming();
  const custom = message?.metadata?.custom || {};
  const chartType = custom.chartType || null;
  const chartTitle = custom.chartTitle || null;
  const chartSubtitle = custom.chartSubtitle || null;
  const chartData = custom.chartData || null;
  const citations = custom.citations || null;
  const answerExplanation = custom.answerExplanation || null;
  const routePayload = custom.routePayload || null;
  const clarification = custom.clarification || null;
  // C-ready 数据结构
  const artifactCard = custom.artifactCard || null;
  const candidateDatasets = custom.candidateDatasets || null;
  const repairPlan = custom.repairPlan || null;

  const handleSelectClarification = (candidate, optionIndex, label) => {
    const clarificationId =
      clarification?.clarificationId || routePayload?.clarification_id || null;
    const clarificationResponse = {
      clarification_id: clarificationId,
      selected_index: optionIndex,
      selected_text: label,
    };
    clarificationResponse.selected_term_id = termCandidateId(candidate);
    window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = clarificationResponse;
    window.dispatchEvent(new CustomEvent('datalogue:composer-submit', {
      detail: { text: `选择：${label}` },
    }));
  };

  const handleRegenerate = () => {
    api.message().reload();
  };

  const handleArtifactAction = async (action) => {
    const actionType = action?.actionType || action?.action_type || action?.action_id || action?.actionId;
    if (actionType === 'copy') {
      const ref = actionArtifactRef(action, artifactCard);
      if (ref) navigator.clipboard?.writeText(ref).catch(console.error);
      return;
    }
    if (actionType !== 'view' && actionType !== 'open_ref') return;

    const ref = actionArtifactRef(action, artifactCard);
    if (!isReadableArtifactRef(ref)) {
      setArtifactDetail({
        status: 'error',
        ref,
        error: '当前结果引用不可直接读取',
      });
      return;
    }

    setArtifactDetail({ status: 'loading', ref });
    try {
      const artifact = await getArtifact(ref);
      setArtifactDetail({ status: 'ready', ref, artifact });
    } catch (_e) {
      setArtifactDetail({
        status: 'error',
        ref,
        error: '结果数据已过期或暂不可读取',
      });
    }
  };

  return (
    <div className="msg-row msg-ai">
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
              {timing && (
                <span className="msg-timing">
                  {timing.totalStreamTime ? `${(timing.totalStreamTime / 1000).toFixed(1)}s` : ''}
                  {timing.tokenCount ? ` · ${timing.tokenCount} 字符` : ''}
                </span>
              )}
            </>
          )}
        </span>
      </div>

      {/* 内容区 — reasoning 由 ChainOfThought 接管，text 走 markdown */}
      <MessagePrimitive.GroupedParts
        groupBy={groupPartByType({
          reasoning: ['group-reasoning'],
          'tool-call': ['group-tool'],
        })}
      >
        {({ part, children }) => {
          if (part.type === 'group-reasoning') return <ChainOfThought>{children}</ChainOfThought>;
          if (part.type === 'group-tool') return <div className="tool-group">{children}</div>;
          if (part.type === 'text') return <MessageTextPart />;
          if (part.type === 'reasoning') return null;
          if (part.type === 'tool-call') return null;
          return null;
        }}
      </MessagePrimitive.GroupedParts>

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

      {/* C-ready ArtifactCard — 统一产物卡片 */}
      <ArtifactCard artifact={artifactCard} onAction={handleArtifactAction} />
      <ArtifactDetailPanel
        detail={artifactDetail}
        onClose={() => setArtifactDetail({ status: 'idle' })}
      />

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

      {/* 操作栏 — assistant-ui ActionBarPrimitive */}
      <ActionBarPrimitive.Root hideWhenRunning className="msg-actions">
        <ActionBarPrimitive.Copy className="icon-btn" title="复制回答" aria-label="复制回答">
          <Icon name="copy" />
        </ActionBarPrimitive.Copy>
        <ActionBarPrimitive.Reload className="icon-btn" title="重新生成" aria-label="重新生成">
          <Icon name="refresh" />
        </ActionBarPrimitive.Reload>
        <ActionBarPrimitive.Speak className="icon-btn" title="朗读回答" aria-label="朗读回答">
          <Icon name="play" />
        </ActionBarPrimitive.Speak>
        <ActionBarPrimitive.Edit className="icon-btn" title="编辑消息" aria-label="编辑消息">
          <Icon name="edit" />
        </ActionBarPrimitive.Edit>
      </ActionBarPrimitive.Root>
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
