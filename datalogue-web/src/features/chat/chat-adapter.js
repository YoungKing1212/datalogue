// ChatModelAdapter — 把后端 SSE 流式响应包成 assistant-ui 能消费的 async generator
// assistant-ui 通过 unstable_threadId 传入当前 thread 标识。不同版本/阶段可能传 remoteId
//（后端 conversation_id），也可能传本地 thread id；因此这里显式生成业务 session_id，
// 让后端 ConversationStore 不依赖 Observability session 或一次性 request id。
//
// 数据流：
//   token 事件          → 累积到 accText（TextMessagePart）
//   step done 事件      → 累积为一条 ReasoningMessagePart（text 是该节点的小结）
//                        同时 window 派发 'datalogue:trace' 给 AgentPanel
//   final 事件          → 收敛 text + metadata.custom（result refs / sql_result 摘要等）
//
// 每次 yield content 数组是完整覆盖，所以本地累加器维护 reasonings + accText。
// 普通 Chat 用户可见层不透出 SQL 文本；SQL 只留在后端 control/trace 面。

import { agentTeamEnvelopeToChatEvent } from '../../assistant/agent-team-event-adapter';
import { streamAgentTeamTask } from '../../assistant/agent-team-task-api';
import { resolveRecentInitializedRemoteId, resolveRemoteId, resolveRecentPendingLocalId, ensureConversationForThread } from './thread-list-adapter';

const BUSINESS_SESSION_PREFIX = 'assistant-thread';

// 节点显示名映射（与后端 _NODE_DISPLAY_NAMES 对齐，作为前端兜底）
const NODE_DISPLAY = {
  message_gateway: '任务理解',
  'message-gateway': '任务理解',
  lead_agent_tools: '能力匹配',
  manifest_route: '场景匹配',
  clarification_resolution: '澄清处理',
  intent_recognition: '意图识别',
  entry_intent_classification: '入口判断',
  analysis_blueprint_execute: '分析蓝图执行',
  candidate_assets: '数据资产匹配',
  schema_recall: '数据范围确认',
  term_normalize_node: '术语标准化',
  semantic_asset_resolution_node: '语义资产解析',
  metric_resolution_node: '指标解析',
  dsl_generate: '查询生成',
  dsl_validate: '查询校验',
  dsl_compiler: '执行计划生成',
  sql_execute: '查询执行',
  sql_audit: '结果诊断',
  repair_patch: '自动修复',
  report_generator: '结果整理',
};

function safeStepLabel(node, displayName) {
  // 后端 display_name 可能仍是内部节点名，普通 Chat 可见层统一映射为业务文案。
  return NODE_DISPLAY[node] || NODE_DISPLAY[displayName] || '任务处理';
}



function safeRepairPlanFromPayload(payload = {}, finalPayload = {}) {
  const patchSummary =
    payload.repair_patch_summary
    || payload.repairPatchSummary
    || finalPayload.repair_patch_summary
    || finalPayload.repairPatchSummary
    || null;
  const summary =
    payload.summary
    || payload.business_summary
    || patchSummary?.repair_strategy
    || patchSummary?.validation_summary
    || finalPayload.repair_plan?.business_summary
    || finalPayload.repair_plan?.summary
    || null;
  const repairPlanRef =
    payload.repair_plan_ref
    || finalPayload.repair_plan_ref
    || finalPayload.repair_plan?.repair_plan_ref
    || null;
  if (!summary && !repairPlanRef) return null;
  const eventType = payload.event_type || payload.eventType || '';
  const inferredPatchStatus = patchSummary ? 'patch_applied' : null;
  return {
    summary,
    status: payload.status || finalPayload.repair_status || finalPayload.repair_plan?.status || (
      eventType === 'repair.patch_applied' ? 'patch_applied' : inferredPatchStatus
    ),
    failureClass:
      patchSummary?.failure_class
      || finalPayload.repair_failure_class
      || finalPayload.repair_plan?.failure_class
      || null,
    repairPlanRef,
    checkpointRef: payload.checkpoint_ref || finalPayload.repair_plan?.checkpoint_ref || null,
    requiresUserConfirmation: Boolean(
      payload.requires_user_confirmation
      || finalPayload.repair_requires_user_confirmation
      || finalPayload.repair_plan?.requires_user_confirmation,
    ),
    confidenceBand: patchSummary?.confidence_band || null,
  };
}

function safeRepairPatchSummaryText(summary = {}) {
  if (!summary || typeof summary !== 'object') return null;
  return safeDisplayText(summary.repair_strategy || summary.validation_summary || summary.summary) || null;
}

function mergeRepairPlan(previous, next) {
  if (!next) return previous || null;
  const merged = { ...(previous || {}) };
  for (const [key, value] of Object.entries(next)) {
    if (value !== null && value !== undefined && value !== '') {
      merged[key] = value;
    }
  }
  return merged;
}

function upsertTaskTimelineEvent(taskTimeline, event) {
  const existing = taskTimeline.find((item) => item.type === event.type);
  if (existing) {
    Object.assign(existing, event);
    return existing;
  }
  taskTimeline.push(event);
  return event;
}

function summarizeCandidateAssets(candidateAssets) {
  const summary = candidateAssets?.summary;
  if (!summary || typeof summary !== 'object') return '';

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
    .filter(Boolean)
    .join(' · ');
}


/**
 * 把单个 step 事件格式化成 reasoning 文本（一行小卡片式）
 */
function formatStepAsReasoning(ev) {
  const label = safeStepLabel(ev.node, ev.display_name);
  const elapsed = ev.elapsed_ms != null ? `（${ev.elapsed_ms}ms）` : '';
  let detail = '';

  if (ev.node === 'intent_recognition') {
    const intent = ev.intent || '';
    const entities = ev.entities || {};
    const entKeys = Object.keys(entities).filter((k) => entities[k]);
    detail = `${intent}${entKeys.length ? ' · ' + entKeys.join('/') : ''}`;
  } else if (ev.node === 'schema_recall') {
    const lines = ev.schema_summary || [];
    detail = lines.length ? lines.join(' / ') : '已检索相关表结构';
  } else if (ev.node === 'candidate_assets') {
    detail = summarizeCandidateAssets(ev.candidate_assets) || '已召回候选资产';
  } else if (ev.node === 'term_normalize_node') {
    const normalization = ev.term_normalization || {};
    const matched = normalization.matched_terms?.length ?? 0;
    const conflicts = normalization.conflicts?.length ?? 0;
    detail = conflicts ? `发现 ${conflicts} 个术语冲突` : `命中 ${matched} 个业务术语`;
  } else if (ev.node === 'semantic_asset_resolution_node' || ev.node === 'metric_resolution_node') {
    const resolution = ev.semantic_asset_resolution || {};
    const count = resolution.assets?.length ?? ev.metric_resolution?.metrics?.length ?? 0;
    detail = `命中 ${count} 个语义资产`;
  } else if (ev.node === 'dsl_generate') {
    detail = ev.generation_mode === 'inferred' ? 'AI 推断生成' : '已基于指标生成';
  } else if (ev.node === 'dsl_validate') {
    detail = 'DSL 校验通过';
  } else if (ev.node === 'dsl_compiler') {
    detail = '查询语句已生成并进入执行校验';
  } else if (ev.node === 'sql_execute') {
    const rows = ev.rows ?? 0;
    detail = `返回 ${rows} 行${ev.columns?.length ? ' · ' + ev.columns.length + ' 列' : ''}`;
  } else if (ev.node === 'sql_audit') {
    const diagnosis = ev.sql_diagnosis || ev.sql_audit_result || {};
    const title = diagnosis.title || diagnosis.root_cause || diagnosis.code || '查询执行失败';
    const suggested = diagnosis.suggested_action || diagnosis.suggested_fix || '';
    detail = suggested ? `${title} · ${suggested}` : title;
  } else if (ev.node === 'repair_patch') {
    detail = safeRepairPatchSummaryText(ev.repair_patch_summary) || '已按业务口径自动修复查询引用';
  } else if (ev.node === 'report_generator') {
    detail = '已生成分析报告';
  }

  return detail ? `${label}：${detail} ${elapsed}` : `${label} ${elapsed}`.trim();
}

function formatRouteDecisionAsReasoning(ev) {
  const candidates = ev.candidates || [];
  if (ev.decision === 'selected') {
    const name = ev.dataset_name || candidates[0]?.dataset_name || `数据集 ${ev.dataset_id}`;
    return `Manifest 路由：已选择 ${name}（得分 ${ev.score ?? 0}）`;
  }
  if (ev.decision === 'locked') {
    const name = ev.dataset_name || candidates[0]?.dataset_name || `数据集 ${ev.dataset_id}`;
    return `Manifest 路由：沿用已选数据集 ${name}`;
  }
  if (ev.decision === 'ambiguous') {
    const names = candidates.map((item) => item.dataset_name || `数据集 ${item.dataset_id}`).slice(0, 3);
    return `Manifest 路由：候选不唯一${names.length ? ' · ' + names.join(' / ') : ''}`;
  }
  return `Manifest 路由：未找到明确数据集`;
}

function formatLeadAgentToolsAsReasoning(ev) {
  const tools = ev.executed_tool_calls?.length
    ? ev.executed_tool_calls.map((item) => item.tool).filter(Boolean)
    : ev.audit_trace?.tools || [];
  const timeRange = ev.time_context?.detected_time_range?.label;
  const schemaStatus = ev.schema_status?.status;
  const planned = ev.planned_tool_calls?.length ?? 0;
  const inferred = ev.system_inferred_tool_calls?.length ?? 0;
  const violations = ev.policy_violations?.length ?? 0;
  const disclosed = ev.disclosed_tools?.length ?? 0;
  const details = [
    timeRange ? `时间=${timeRange}` : null,
    schemaStatus ? `Schema=${schemaStatus}` : null,
    ev.progressive_disclosure ? '渐进式披露' : null,
    disclosed ? `披露工具=${disclosed}` : null,
    planned ? `计划=${planned}` : null,
    inferred ? `系统补齐=${inferred}` : null,
    violations ? `策略拦截=${violations}` : null,
    ev.planner_fallback ? '降级计划' : null,
    ev.audit_trace?.dispatched ? '已调度 SubAgent' : '等待澄清',
  ].filter(Boolean);
  return `LeadAgent 工具：${tools.length ? tools.join(' / ') : '控制面检查'}${details.length ? ' · ' + details.join(' · ') : ''}`;
}

/**
 * 把 user/assistant 消息数组的 content 拼成后端要的 question 字符串
 */
function extractQuestion(messages) {
  const lastUser = [...messages].reverse().find((m) => m.role === 'user');
  if (!lastUser) return '';
  return (lastUser.content || [])
    .filter((p) => p.type === 'text')
    .map((p) => p.text || '')
    .join('');
}

function normalizeConversationId(threadId) {
  if (threadId == null || threadId === '') return null;
  const value = Number(threadId);
  return Number.isInteger(value) && value > 0 ? value : null;
}

function conversationIdFromCurrentRoute() {
  if (typeof window === 'undefined') return null;
  const match = window.location.pathname.match(/^\/chat\/(\d+)(?:\/|$)/);
  return match ? normalizeConversationId(match[1]) : null;
}

function normalizeSessionPart(value) {
  return String(value || '')
    .trim()
    .replace(/[^\w.-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}

function createFallbackBusinessSessionId() {
  const random =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${BUSINESS_SESSION_PREFIX}-${normalizeSessionPart(random)}`;
}

export function buildBusinessSessionId({ threadId, conversationId, fallbackSessionId }) {
  if (conversationId != null) return `conversation-${conversationId}`;
  const normalizedThreadId = normalizeSessionPart(threadId);
  if (normalizedThreadId) return `${BUSINESS_SESSION_PREFIX}-${normalizedThreadId}`;
  return fallbackSessionId;
}

const USER_VISIBLE_TRACE_FORBIDDEN_KEYS = new Set([
  'sql',
  'sql_result',
  'sqlResult',
  'sql_diagnosis',
  'sqlDiagnosis',
  'sql_audit_result',
  'sqlAuditResult',
  'raw_sql',
  'direct_sql',
  'llm_sql',
  'compiled_sql',
  'sql_list',
  'candidate_assets',
  'candidateAssets',
  'dsl',
  'rows',
  'columns',
  'column_labels',
  'columnLabels',
  'schema',
  'schemas',
  'table',
  'tables',
  'field',
  'fields',
  'raw_result',
  'rawResult',
  'repair_patch',
  'repairPatch',
  'RepairPatch',
  'node',
  'display_name',
  'displayName',
  'trace_only_metadata',
  'traceOnlyMetadata',
  'replacement_field_ref',
  'replacementFieldRef',
  'raw_rows',
  'rawRows',
  'debug_raw',
  'debugRaw',
  'raw_delta',
  'rawDelta',
  'blueprint',
  'blueprints',
]);

function sanitizeUserVisibleTrace(value) {
  if (Array.isArray(value)) return value.map(sanitizeUserVisibleTrace);
  if (!value || typeof value !== 'object') return value;
  const out = {};
  for (const [key, item] of Object.entries(value)) {
    if (USER_VISIBLE_TRACE_FORBIDDEN_KEYS.has(key)) continue;
    out[key] = sanitizeUserVisibleTrace(item);
  }
  return out;
}

const INTERNAL_TEXT_PATTERN = /\b(select|insert|update|delete|delete\s+from|from|join|where|group\s+by|order\s+by|having|union|with)\b|[`;]|hidden_table|\b\w+_col\b|raw_result|raw_row|schema/i;
const INTERNAL_PLANNING_PATTERN = /\b(the\s+user\s+wants?\s+to|let\s+me\s+break|i\s+need\s+to\s+create|worker\s+type\s+should\s+be|i\s+should\s+present|teamsay)\b/i;
const INTERNAL_PLANNING_COMPACT_MARKERS = [
  'theuserwantstoquery',
  'letmebreakthisdown',
  'ineedtocreate',
  'theworkertypeshouldbe',
  'bothhaveascore',
  'ishouldpresent',
  'taskcompletedteamdissolved',
];

function looksLikeInternalPlanningText(value) {
  if (value == null) return false;
  const text = String(value).trim();
  if (!text) return false;
  const compact = text.toLowerCase().replace(/[^a-z0-9]/g, '');
  return INTERNAL_PLANNING_PATTERN.test(text)
    || INTERNAL_PLANNING_COMPACT_MARKERS.some((marker) => compact.includes(marker));
}

function safeDisplayText(value) {
  if (value == null) return null;
  const text = String(value).trim();
  if (!text || INTERNAL_TEXT_PATTERN.test(text) || looksLikeInternalPlanningText(text)) return null;
  return text.slice(0, 160);
}

function datasetConfirmationAnswer(routeDecision) {
  const candidates = Array.isArray(routeDecision?.candidates)
    ? routeDecision.candidates.slice(0, 5)
    : [];
  if (!candidates.length) return '候选数据集不唯一，需要你确认后继续。';
  const lines = candidates
    .map((candidate, index) => {
      const datasetName = candidate.dataset_name || `数据集 ${candidate.dataset_id || ''}`.trim();
      const prefix = candidate.dataset_id
        ? `${index + 1}. 数据集 ${candidate.dataset_id}：${datasetName}`
        : `${index + 1}. ${datasetName}`;
      return candidate.reason ? `${prefix}（${candidate.reason}）` : prefix;
    })
    .join('\n');
  return `已筛选出可能匹配的候选数据集，需要你确认后继续。\n\n${lines}\n\n请回复要查询的数据集编号，或说明两个都需要查询。`;
}

function safeDisplayList(values, limit = 6) {
  if (!Array.isArray(values)) return [];
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const text = safeDisplayText(value);
    if (!text || seen.has(text)) continue;
    seen.add(text);
    result.push(text);
    if (result.length >= limit) break;
  }
  return result;
}

function reasoningGroupKey(part = {}) {
  const parentId = String(part.parentId || '').trim();
  if (parentId) return parentId; // 同一节点/同一 Agent 复用同一分组键
  const title = String(part.title || '').trim();
  return title ? `title:${title}` : 'reasoning';
}

// 流式阶段按分组键 upsert：同一节点或同一 Agent 的重复事件原地更新，避免推理摘要堆出几百条“任务处理”。
function upsertReasoningPart(reasonings, part) {
  if (!part) return;
  const key = reasoningGroupKey(part);
  const index = reasonings.findIndex((existing) => reasoningGroupKey(existing) === key);
  if (index >= 0) {
    reasonings[index] = { ...reasonings[index], ...part }; // 保留最新文本与状态
    return;
  }
  reasonings.push(part);
}

const LIVE_THINKING_SQL_RE = /\b(select|insert|update|delete)\b[\s\S]{0,80}\bfrom\b|hidden_table|raw_result|raw_rows?|schema_context/i;

// 流式 message.delta 是 Leader 的“边想边说”，只作为思考链展示；命中 SQL/schema 等执行细节时整体丢弃。
function sanitizeLiveThinkingText(text) {
  const value = String(text || '').trim();
  if (!value || LIVE_THINKING_SQL_RE.test(value)) return '';
  return value.slice(0, 4000);
}

function appendRawThinkingDelta(previous = '', delta = '') {
  const next = String(delta || '');
  if (!previous) return next;
  if (!next) return previous;
  // AgentScope raw thinking delta 的切分边界不是自然语言词边界；补空格会破坏
  // 标识符、数字与 SQL 关键字（例如 plan_task_d + aily_record、202 + 5、LIM + IT）。
  // 前端只做忠实拼接，可读性由 bi_worker_thinking_summary 通道保证。
  return `${previous}${next}`;
}

function safeReasoningSummary(reasoningSummary) {
  if (!Array.isArray(reasoningSummary)) return [];
  return reasoningSummary
    .slice(0, 6)
    .map((item, index) => {
      if (!item || typeof item !== 'object') return null;
      const title = safeDisplayText(item.title) || `推理摘要 ${index + 1}`;
      const summary = safeDisplayText(item.summary || item.text || item.reason);
      if (!summary) return null;
      const ref = safeDisplayText(item.ref || item.artifact_ref || item.artifactRef) || null;
      const status = safeDisplayText(item.status) || 'completed';
      const countParts = [];
      if (Number.isInteger(item.row_count) && item.row_count >= 0) countParts.push(`${item.row_count} 行`);
      if (Number.isInteger(item.column_count) && item.column_count >= 0) countParts.push(`${item.column_count} 列`);
      return compactObject({
        type: 'reasoning',
        text: `${title}：${summary}${countParts.length ? `（${countParts.join('、')}）` : ''}`,
        parentId: 'reasoning_summary',
        title,
        summary,
        status,
        refs: ref ? { artifactRef: ref } : null,
        rowCount: Number.isInteger(item.row_count) && item.row_count >= 0 ? item.row_count : null,
      });
    })
    .filter(Boolean);
}

function safeAnswerExplanation(payload = {}) {
  const explanation = payload.answer_explanation || payload.answerExplanation || null;
  if (!explanation || typeof explanation !== 'object') return null;

  const caliber = explanation.caliber && typeof explanation.caliber === 'object'
    ? {
        metrics: safeDisplayList(explanation.caliber.metrics),
        dimensions: safeDisplayList(explanation.caliber.dimensions),
        terms: safeDisplayList(explanation.caliber.terms),
        blueprints: safeDisplayList(explanation.caliber.blueprints),
      }
    : {};
  const risks = Array.isArray(explanation.risks)
    ? explanation.risks
        .map((item) => ({ message: safeDisplayText(item?.message || item) }))
        .filter((item) => item.message)
        .slice(0, 5)
    : [];
  return {
    caliber,
    confidence: explanation.confidence || null,
    confirmation: explanation.confirmation || null,
    risks,
    // 只保留是否经过校验的业务级提示，不携带 SQL 摘要正文或数据源表字段。
    sql_summary: explanation.sql_summary ? { preview: Boolean(explanation.sql_summary.preview) } : null,
    data_sources: [],
  };
}

function safeQueryCaliber(payload = {}) {
  const source =
    payload.query_caliber
    || payload.queryCaliber
    || payload.business_caliber
    || payload.businessCaliber
    || payload.answer_explanation?.caliber
    || payload.answerExplanation?.caliber
    || null;
  if (!source || typeof source !== 'object') return null;

  const caliber = {
    metrics: safeDisplayList(source.metrics),
    dimensions: safeDisplayList(source.dimensions),
    timeRange: safeDisplayText(source.time_range || source.timeRange) || null,
    filters: safeDisplayList(source.filters),
    routePath: safeDisplayText(source.route_path || source.routePath) || null,
    inheritedText: safeDisplayText(source.inherited_text || source.inheritedText) || null,
    generationMode: safeDisplayText(source.generation_mode || source.generationMode) || '',
  };
  const hasAny =
    caliber.metrics.length
    || caliber.dimensions.length
    || caliber.timeRange
    || caliber.filters.length
    || caliber.routePath
    || caliber.inheritedText;
  return hasAny ? caliber : null;
}

function safeRouteDecision(routeDecision) {
  if (!routeDecision || typeof routeDecision !== 'object') return null;
  const candidates = Array.isArray(routeDecision.candidates)
    ? routeDecision.candidates.map((candidate) => ({
        dataset_id: candidate?.dataset_id ?? candidate?.datasetId ?? null,
        dataset_name: safeDisplayText(candidate?.dataset_name || candidate?.datasetName) || null,
        reason: safeDisplayText(candidate?.reason || candidate?.match_reason || candidate?.short_reason) || null,
      })).filter((candidate) => candidate.dataset_id != null || candidate.dataset_name || candidate.reason)
    : [];
  return {
    decision: safeDisplayText(routeDecision.decision) || null,
    dataset_id: routeDecision.dataset_id ?? routeDecision.datasetId ?? null,
    dataset_name: safeDisplayText(routeDecision.dataset_name || routeDecision.datasetName) || null,
    score: routeDecision.score ?? null,
    candidates,
  };
}

function safeSubagentToolResults(results) {
  if (!Array.isArray(results)) return null;
  const safeResults = results
    .map((item) => ({
      result_ref: item?.result_ref || item?.resultRef || null,
      report_ref: item?.report_ref || item?.reportRef || null,
      dataset_id: item?.dataset_id ?? item?.datasetId ?? null,
    }))
    .filter((item) => item.result_ref || item.report_ref || item.dataset_id != null);
  return safeResults.length ? safeResults : null;
}

function safeArtifactCard(artifactCard) {
  if (!artifactCard || typeof artifactCard !== 'object') return null;
  return {
    title: safeDisplayText(artifactCard.title) || '查询结果',
    status: safeDisplayText(artifactCard.status) || null,
    summary_for_chat: safeDisplayText(artifactCard.summary_for_chat || artifactCard.summaryForChat) || null,
    preview_payload: null,
    primary_ref: artifactCard.primary_ref || artifactCard.primaryRef || null,
    related_refs: Array.isArray(artifactCard.related_refs || artifactCard.relatedRefs)
      ? (artifactCard.related_refs || artifactCard.relatedRefs).filter(Boolean)
      : [],
    actions: Array.isArray(artifactCard.actions)
      ? artifactCard.actions.map((action) => ({
          action_type: safeDisplayText(
            action?.action_type || action?.actionType || action?.action_id || action?.actionId,
          ) || null,
          label: safeDisplayText(action?.label) || null,
          ref: action?.ref || action?.payload_ref || action?.payloadRef || '',
          checkpoint_ref: action?.checkpoint_ref || action?.checkpointRef || action?.payload_ref || action?.payloadRef || null,
          disabled_reason: safeDisplayText(action?.disabled_reason || action?.disabledReason) || null,
          disabled: Boolean(action?.disabled || action?.enabled === false),
        }))
      : [],
  };
}

function safeClarificationCandidate(candidate, index) {
  if (!candidate || typeof candidate !== 'object') return null;
  const nested = candidate.term || candidate.business_term || candidate.businessTerm || {};
  const label = safeDisplayText(
    candidate.display_name
      || candidate.displayName
      || candidate.dataset_name
      || candidate.datasetName
      || candidate.label
      || candidate.title
      || candidate.name
      || candidate.term_name
      || candidate.termName
      || nested.display_name
      || nested.displayName
      || nested.name
      || nested.term_name
      || nested.termName,
  );
  const definition = safeDisplayText(
    candidate.definition
      || candidate.description
      || candidate.desc
      || nested.definition
      || nested.description
      || nested.desc,
  );
  if (!label && !definition && candidate.dataset_id == null && candidate.term_id == null && candidate.id == null) {
    return null;
  }
  return {
    index: candidate.index || index + 1,
    id: candidate.id ?? null,
    dataset_id: candidate.dataset_id ?? candidate.datasetId ?? null,
    term_id: candidate.term_id ?? candidate.termId ?? null,
    display_name: label,
    definition,
    term_type: safeDisplayText(candidate.term_type || candidate.termType || nested.term_type || nested.termType),
  };
}

function safeClarification(clarification, routePayload) {
  const source = routePayload?.kind === 'term_conflict_clarification'
    ? {
        kind: 'term_conflict',
        clarificationId: routePayload.clarification_id,
        candidates: routePayload.candidates,
        expiresAt: routePayload.expires_at,
      }
    : clarification;
  if (!source || typeof source !== 'object') return null;
  const candidates = Array.isArray(source.candidates)
    ? source.candidates
        .map((candidate, index) => safeClarificationCandidate(candidate, index))
        .filter(Boolean)
    : [];
  return {
    kind: safeDisplayText(source.kind) || null,
    clarificationId: source.clarificationId || source.clarification_id || null,
    candidates,
    expiresAt: source.expiresAt || source.expires_at || null,
  };
}

/**
 * 在 SSE 事件来时 dispatch window 自定义事件给 AgentPanel
 * 不走 assistant-ui runtime，保持面板的低耦合
 */
function emitTrace(ev) {
  try {
    window.dispatchEvent(new CustomEvent('datalogue:trace', { detail: sanitizeUserVisibleTrace(ev) }));
  } catch (_e) {
    /* SSR 保护 */
  }
}

function emitResolvedConversation(localThreadId, actualConvId) {
  if (actualConvId == null) return;
  try {
    window.dispatchEvent(
      new CustomEvent('datalogue:conv-resolved', {
        detail: { localThreadId, actualConvId },
      }),
    );
  } catch (_e) {
    /* SSR 保护 */
  }
}

function emitResolvedThread(localThreadId, threadId) {
  if (!threadId) return;
  try {
    window.dispatchEvent(
      new CustomEvent('datalogue:thread-resolved', {
        detail: { localThreadId, threadId },
      }),
    );
  } catch (_e) {
    /* SSR 保护 */
  }
}

function requestThreadIdFromRemoteId(remoteId) {
  if (!remoteId) return null;
  const value = String(remoteId);
  return value.startsWith('as_') ? value : null;
}

function consumePendingWorkbenchRetry() {
  if (typeof window === 'undefined') return null;
  const request = window.__DATALOGUE_PENDING_WORKBENCH_RETRY__ || null;
  if (request) {
    window.__DATALOGUE_PENDING_WORKBENCH_RETRY__ = null;
  }
  return request && typeof request === 'object' ? request : null;
}

function normalizeDatasetId(value) {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) return value;
  if (typeof value === 'string' && /^\d+$/.test(value)) return Number(value);
  return null;
}

function normalizeModelParameters(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const forbidden = new Set(['api_key', 'base_url', 'credential_id', 'model', 'type']);
  return Object.fromEntries(
    Object.entries(value).filter(([key, parameter]) => !forbidden.has(key) && parameter != null),
  );
}

function normalizeAgentScopeModelSelection(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {
      modelCredentialId: null,
      modelName: null,
      modelParameters: {},
    };
  }
  const modelCredentialId = safeDisplayText(
    value.model_credential_id || value.credential_id || value.credentialId,
  );
  const modelName = safeDisplayText(value.model_name || value.model || value.name);
  const modelParameters = normalizeModelParameters(value.model_parameters || value.parameters);
  return {
    // credential/model 成对存在时走 AgentScope Service 原生资源；缺一项则交给后端默认 AgentScope credential。
    modelCredentialId: modelCredentialId && modelName ? modelCredentialId : null,
    modelName: modelCredentialId && modelName ? modelName : null,
    modelParameters,
  };
}

function safeTiming(timing) {
  if (!timing || typeof timing !== 'object') return null;
  const allowed = [
    'started_at',
    'ended_at',
    'elapsed_ms',
    'duration_ms',
    'total_ms',
    'queued_ms',
    'startedAt',
    'endedAt',
    'elapsedMs',
    'durationMs',
  ];
  const out = {};
  for (const key of allowed) {
    const value = timing[key];
    if (typeof value === 'number' && Number.isFinite(value)) out[key] = value;
    if (typeof value === 'string' && safeDisplayText(value)) out[key] = value.slice(0, 80);
  }
  return Object.keys(out).length ? out : null;
}

function safeRefs(refs = {}) {
  if (!refs || typeof refs !== 'object') return {};
  return Object.fromEntries(
    Object.entries({
      artifactRef: refs.artifactRef || refs.artifact_ref || null,
      reportRef: refs.reportRef || refs.report_ref || null,
      checkpointRef: refs.checkpointRef || refs.checkpoint_ref || null,
    }).filter(([, value]) => typeof value === 'string' && value.trim()),
  );
}

function safeStepTraceEvent(event = {}) {
  const title = safeStepLabel(event.node, event.display_name);
  const text = safeDisplayText(formatStepAsReasoning(event));
  return compactObject({
    type: 'step',
    status: safeDisplayText(event.status) || null,
    title,
    text,
    refs: safeRefs(event.refs),
  });
}

function safeToolCalls(calls = []) {
  if (!Array.isArray(calls)) return [];
  return calls.slice(0, 8).map((call = {}) => compactObject({
    id: safeDisplayText(call.id || call.tool_call_id || call.toolCallId) || null,
    name: safeDisplayText(call.name || call.tool_name || call.toolName) || null,
    state: safeDisplayText(call.state || call.status) || null,
  })).filter((call) => Object.keys(call).length > 0);
}

function compactObject(value = {}) {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => (
      item !== null
      && item !== undefined
      && item !== ''
      && !(Array.isArray(item) && item.length === 0)
      && !(typeof item === 'object' && !Array.isArray(item) && Object.keys(item).length === 0)
    )),
  );
}

function structuredEventSummary(event = {}) {
  return compactObject({
    kind: event.kind,
    status: event.status,
    title: safeDisplayText(event.title) || null,
    summary: safeDisplayText(event.summary) || null,
    agent: safeDisplayText(event.agent || event.to_agent || event.from_agent) || null,
    agentRole: safeDisplayText(event.agentRole || event.agent_role) || null,
    agentName: safeDisplayText(event.agentName || event.agent_name) || null,
    phase: safeDisplayText(event.phase) || null,
    toolName: safeDisplayText(event.toolName || event.tool_name) || null,
    toolCallId: safeDisplayText(event.toolCallId || event.tool_call_id) || null,
    replyId: safeDisplayText(event.replyId || event.reply_id) || null,
    workerSessionId: safeDisplayText(event.workerSessionId || event.worker_session_id) || null,
    workerAgentId: safeDisplayText(event.workerAgentId || event.worker_agent_id) || null,
    reasoningKind: safeDisplayText(event.reasoningKind || event.reasoning_kind) || null,
    streamGroupId: safeDisplayText(event.streamGroupId || event.stream_group_id) || null,
    sequence: Number.isInteger(event.sequence) && event.sequence >= 0 ? event.sequence : null,
    blockId: safeDisplayText(event.blockId || event.block_id) || null,
    debugRaw: event.debugRaw === true || event.debug_raw === true ? true : null,
    rawDelta: event.debugRaw === true || event.debug_raw === true
      ? String(event.rawDelta ?? event.raw_delta ?? '').slice(0, 4000)
      : null,
    toolCalls: safeToolCalls(event.toolCalls || event.tool_calls),
    timing: safeTiming(event.timing),
    refs: safeRefs(event.refs),
    rowCount: event.rowCount ?? event.row_count ?? null,
  });
}

function buildStructuredReasoningPart(event = {}) {
  const summary = structuredEventSummary(event);
  let text = summary.summary
    ? `${summary.title || '执行进展'}：${summary.summary}`
    : (summary.title || '执行进展');
  let parentId = event.kind === 'agent_progress' && summary.agentRole
    ? `agent-${summary.agentRole}`
    : event.kind === 'handoff' ? 'multi_agent_handoff' : event.kind;
  if (summary.reasoningKind === 'bi_worker_thinking_summary') {
    parentId = `agent-worker-thinking${summary.streamGroupId ? `:${summary.streamGroupId}` : ''}`;
  } else if (summary.reasoningKind === 'bi_worker_raw_thinking_delta') {
    parentId = `agent-worker-raw-thinking${summary.streamGroupId ? `:${summary.streamGroupId}` : ''}`;
    text = `BI Worker 调试原文：${summary.rawDelta || ''}`;
  }
  return compactObject({
    type: 'reasoning',
    text,
    parentId,
    ...summary,
  });
}

// final 后需要保留的流式思考：Leader 推理（live_thinking）与 Agent 进度（agent-*），
// 避免“问完后思考过程消失”；trace/step 等状态噪声仍由业务摘要收敛。
function isPreservedStreamingReasoning(part = {}) {
  if (part.type !== 'reasoning') return false;
  const parentId = String(part.parentId || '');
  return parentId.startsWith('agent-')
    || parentId === 'live_thinking'
    || part.reasoningKind === 'bi_worker_thinking_summary'
    || part.reasoningKind === 'bi_worker_raw_thinking_delta';
}

function upsertToolCallPart(toolParts, event = {}) {
  const summary = structuredEventSummary(event);
  const toolName = summary.toolName || 'dataset_tool';
  const toolCallId = event.toolCallId || event.tool_call_id || `${toolName}-${toolParts.length + 1}`;
  const args = compactObject({
    kind: 'tool',
    status: summary.status,
    title: summary.title || toolName,
    summary: summary.summary,
    agent: summary.agent,
    toolName,
    timing: summary.timing,
    refs: summary.refs,
    rowCount: summary.rowCount,
  });
  const result = summary.status === 'completed' || summary.status === 'failed'
    ? compactObject({
        kind: 'tool',
        status: summary.status,
        summary: summary.summary,
        refs: summary.refs,
        rowCount: summary.rowCount,
      })
    : undefined;
  const nextPart = compactObject({
    type: 'tool-call',
    toolCallId,
    toolName,
    args,
    argsText: JSON.stringify(args),
    result,
    isError: summary.status === 'failed',
    timing: summary.timing,
    parentId: 'dataset_tool_group',
  });
  const existingIndex = toolParts.findIndex((part) => part.toolCallId === toolCallId);
  if (existingIndex >= 0) {
    toolParts[existingIndex] = {
      ...toolParts[existingIndex],
      ...nextPart,
      args: {
        ...toolParts[existingIndex].args,
        ...nextPart.args,
      },
    };
  } else {
    toolParts.push(nextPart);
  }
  return existingIndex >= 0 ? toolParts[existingIndex] : nextPart;
}

function upsertToolGroup(toolGroups, event = {}) {
  const summary = structuredEventSummary(event);
  const toolName = summary.toolName || 'dataset_tool';
  const key = `${summary.agent || 'agent'}:${toolName}`;
  const existing = toolGroups.find((group) => group.groupId === key);
  const next = compactObject({
    groupId: key,
    kind: 'tool_group',
    status: summary.status,
    title: summary.title || toolName,
    summary: summary.summary,
    agent: summary.agent,
    toolName,
    timing: summary.timing,
    refs: summary.refs,
    rowCount: summary.rowCount,
  });
  if (existing) {
    Object.assign(existing, compactObject({
      ...next,
      timing: next.timing || existing.timing,
      refs: Object.keys(next.refs || {}).length ? next.refs : existing.refs,
      rowCount: next.rowCount ?? existing.rowCount,
    }));
    return existing;
  }
  toolGroups.push(next);
  return next;
}

function buildTimingMetadata(messageTiming, toolGroups = []) {
  const message = safeTiming(messageTiming);
  const tools = toolGroups
    .map((group) => {
      const timing = safeTiming(group.timing);
      if (!timing) return null;
      return compactObject({
        toolName: group.toolName,
        agent: group.agent,
        ...timing,
      });
    })
    .filter(Boolean);
  return compactObject({ message, tools });
}

/**
 * 构造 ChatModelAdapter
 * @param {object} opts
 * @param {{current: string|null}} opts.datasetIdRef - 数据集 ID 共享 ref，ChatPage 更新
 * @param {{current: object|number|null}} opts.modelConfigIdRef - 本轮 AgentScope 模型选择；null 表示后端默认模型
 */
export function makeChatAdapter({ datasetIdRef, modelConfigIdRef }) {
  const fallbackSessionId = createFallbackBusinessSessionId();

  return {
    async *run({ messages, abortSignal, unstable_threadId }) {
      const question = extractQuestion(messages);
      if (!question) return;

      const resolvedRemoteId =
        resolveRemoteId(unstable_threadId) || resolveRecentInitializedRemoteId();
      let routeConvId = resolvedRemoteId
        ? normalizeConversationId(resolvedRemoteId)
        : conversationIdFromCurrentRoute() || normalizeConversationId(unstable_threadId);

      // 首条消息：懒创建后端会话（此前 initialize 仅在本地注册 pending 映射）。
      // assistant-ui useLocalRuntime 对草稿 thread 可能不传 unstable_threadId，
      // 此时通过 resolveRecentPendingLocalId 找到最近 init 的 pending 线程。
      const effectiveThreadId = unstable_threadId || resolveRecentPendingLocalId();
      if (!routeConvId && effectiveThreadId) {
        const newRemoteId = await ensureConversationForThread(effectiveThreadId);
        if (newRemoteId) {
          routeConvId = normalizeConversationId(newRemoteId);
          emitResolvedConversation(effectiveThreadId, newRemoteId);
          // 触发 sidebar 刷新与 thread 切换，让新会话出现在列表中并获得真实 remoteId
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('datalogue:thread-rename', {
              detail: { remoteId: newRemoteId },
            }));
          }
        }
      }

      const workbenchRetryRequest = consumePendingWorkbenchRetry();
      const convId = normalizeConversationId(workbenchRetryRequest?.conversation_id) || routeConvId;
      const retryThreadId = requestThreadIdFromRemoteId(workbenchRetryRequest?.thread_id);
      const requestThreadId = retryThreadId || requestThreadIdFromRemoteId(resolvedRemoteId);
      const businessSessionId = buildBusinessSessionId({
        threadId: unstable_threadId,
        conversationId: convId,
        fallbackSessionId,
      });
      const clarificationResponse =
        typeof window !== 'undefined'
          ? window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ || null
          : null;
      if (clarificationResponse && typeof window !== 'undefined') {
        window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = null;
      }
      const clarificationQuestion = safeDisplayText(
        clarificationResponse?.confirmed_question
          || clarificationResponse?.original_question
          || clarificationResponse?.question,
      );
      const selectedDatasetId = normalizeDatasetId(clarificationResponse?.selected_dataset_id);
      const datasetId = selectedDatasetId
        ?? normalizeDatasetId(workbenchRetryRequest?.dataset_id)
        ?? datasetIdRef?.current
        ?? null;
      const modelSelection = normalizeAgentScopeModelSelection(modelConfigIdRef?.current);
      // Workbench retry 只覆盖业务问题和 checkpoint ref；真实上下文由后端 checkpoint 恢复。
      const effectiveQuestion = safeDisplayText(workbenchRetryRequest?.question) || clarificationQuestion || question;
      const retryCheckpointRef =
        typeof workbenchRetryRequest?.retry_checkpoint_ref === 'string'
          ? workbenchRetryRequest.retry_checkpoint_ref
          : null;

      const taskRequest = {
        task_source: 'chat',
        task_type: 'bi_query',
        question: effectiveQuestion,
        session_id: businessSessionId,
        conversation_id: convId,
        thread_id: requestThreadId,
        dataset_id: datasetId,
        model_credential_id: modelSelection.modelCredentialId,
        model_name: modelSelection.modelName,
        model_parameters: modelSelection.modelParameters,
        retry_checkpoint_ref: retryCheckpointRef,
        clarification_response: clarificationResponse,
      };

      // Chat 主发送入口统一交给 Agent Team；数据集为空、澄清回复、重试恢复都由同一条 SSE 契约处理。
      yield* this.runTaskStream(taskRequest, { abortSignal, unstable_threadId });
    },

    async runAgentTeamTask(taskRequest) {
      let finalChunk = null;
      const abortController = new AbortController();
      for await (const chunk of this.runTaskStream(taskRequest, {
        abortSignal: abortController.signal,
        unstable_threadId: taskRequest?.thread_id,
      })) {
        finalChunk = chunk;
      }
      return finalChunk;
    },

    async *runTaskStream(taskRequest, {
      abortSignal = new AbortController().signal,
      unstable_threadId,
    } = {}) {
      let stream;
      try {
        stream = streamAgentTeamTask(taskRequest, { signal: abortSignal });
      } catch (err) {
        if (err.name !== 'AbortError') {
          yield {
            content: [{ type: 'text', text: `连接失败：${err.message}` }],
            status: { type: 'incomplete', reason: 'error' },
          };
        }
        return;
      }

      // 流式累加器
      const reasonings = []; // ReasoningMessagePart[]
      const toolParts = []; // ToolCallMessagePart[]，供 assistant-ui ToolUI/ToolGroup 直接消费。
      const toolGroups = [];
      const confirmations = [];
      const stepTrace = [];
      let accText = '';      // 已累积的 text（final 收敛与兜底用）
      let liveThinkingText = ''; // 流式 Leader 独白，只进思考链，不铺回答正文
      let finalPayload = null;
      const repairTimeline = [];
      let repairPlan = null;
      const rawThinkingDeltas = new Map();

      // C-ready 业务时间线累加器：从 SSE 事件推断五类节点
      const taskTimeline = [];

      // 工具：构造当前 message content
      // 流式阶段正文保持为空，Leader 独白与步骤只在思考链呈现；正文只在 final 收敛为干净答案。
      const buildContent = () => [
        ...reasonings,
        ...toolParts,
        { type: 'text', text: '' },
      ];

      for await (const rawEvent of stream) {
        if (abortSignal.aborted) break;
        const ev = agentTeamEnvelopeToChatEvent(rawEvent);
        if (!ev) continue;

        if (ev.type === 'token') {
          accText += ev.content || '';
          liveThinkingText += ev.content || '';
          const safeThinking = sanitizeLiveThinkingText(liveThinkingText);
          if (safeThinking) {
            // 把流式正文改投思考链，避免 Leader 规划长文本直接铺在回答区。
            upsertReasoningPart(reasonings, {
              type: 'reasoning',
              text: safeThinking,
              parentId: 'live_thinking',
              title: '推理过程',
              status: 'running',
            });
          }
          yield { content: buildContent() };
        } else if (ev.type === 'route_decision') {
          emitTrace(ev);
          upsertReasoningPart(reasonings, {
            type: 'reasoning',
            text: formatRouteDecisionAsReasoning(ev),
            parentId: 'manifest_route',
          });
          // 业务时间线：数据集匹配节点
          const datasetName = ev.dataset_name || (ev.candidates || [])[0]?.dataset_name || '';
          taskTimeline.push({
            type: 'dataset_matching',
            label: '数据集匹配',
            text: datasetName ? `已匹配数据集「${datasetName}」` : '正在匹配数据集',
            status: ev.decision === 'selected' || ev.decision === 'locked' ? 'done' : 'running',
          });
          yield { content: buildContent() };
        } else if (ev.type === 'agent_handoff') {
          emitTrace(ev);
          upsertReasoningPart(reasonings, buildStructuredReasoningPart(ev));
          upsertTaskTimelineEvent(taskTimeline, {
            type: 'task_understood',
            label: '任务理解',
            text: ev.summary || '已完成 Agent 路由',
            status: ev.status === 'failed' ? 'error' : 'done',
          });
          yield { content: buildContent() };
        } else if (ev.type === 'agent_progress') {
          emitTrace(ev);
          let progressEvent = ev;
          if (ev.reasoningKind === 'bi_worker_raw_thinking_delta' && ev.debugRaw === true) {
            const key = ev.streamGroupId || ev.replyId || 'default';
            const nextRaw = appendRawThinkingDelta(rawThinkingDeltas.get(key) || '', ev.rawDelta || '');
            rawThinkingDeltas.set(key, nextRaw);
            progressEvent = { ...ev, rawDelta: nextRaw };
          }
          upsertReasoningPart(reasonings, buildStructuredReasoningPart(progressEvent));
          upsertTaskTimelineEvent(taskTimeline, {
            type: ev.agentRole === 'worker' ? 'bi_execution' : 'task_understood',
            label: ev.agentRole === 'worker' ? 'BI 执行' : '任务理解',
            text: ev.summary || ev.title || '正在处理任务',
            status: ev.status === 'completed' ? 'done' : ev.status === 'failed' ? 'error' : 'running',
          });
          yield { content: buildContent() };
        } else if (ev.type === 'tool_call') {
          emitTrace(ev);
          upsertToolCallPart(toolParts, ev);
          upsertToolGroup(toolGroups, ev);
          upsertTaskTimelineEvent(taskTimeline, {
            type: 'bi_execution',
            label: 'BI 执行',
            text: ev.summary || '正在完成查询处理',
            status: ev.status === 'completed' ? 'done' : ev.status === 'failed' ? 'error' : 'running',
          });
          yield { content: buildContent() };
        } else if (ev.type === 'confirmation') {
          emitTrace(ev);
          const confirmation = structuredEventSummary(ev);
          confirmations.push(confirmation);
          upsertReasoningPart(reasonings, buildStructuredReasoningPart(ev));
          upsertTaskTimelineEvent(taskTimeline, {
            type: 'next_action',
            label: '下一步',
            text: ev.summary || '需要确认后继续执行',
            status: 'running',
          });
          yield { content: buildContent() };
        } else if (ev.type === 'artifact_ref') {
          emitTrace(ev);
          const refs = safeRefs(ev.refs);
          upsertTaskTimelineEvent(taskTimeline, {
            type: 'artifact_created',
            label: '结果产物',
            text: ev.summary || '已生成查询结果',
            status: 'done',
            primaryRef: refs.artifactRef || refs.reportRef || null,
            rowCount: ev.rowCount ?? null,
          });
          yield { content: buildContent() };
        } else if (ev.type === 'lead_agent_tools') {
          emitTrace(ev);
          emitResolvedConversation(unstable_threadId, ev.thread_context?.conversation_id);
          upsertReasoningPart(reasonings, {
            type: 'reasoning',
            text: formatLeadAgentToolsAsReasoning(ev),
            parentId: 'lead_agent_tools',
          });
          yield { content: buildContent() };
        } else if (ev.type === 'step') {
          // 通知 AgentPanel（保持现有行为）
          emitTrace(ev);
          stepTrace.push(safeStepTraceEvent(ev));
          // 只把"完成"的节点累积为 reasoning（running 状态等完成时再算）
          if (ev.status === 'done' && ev.node !== 'error') {
            const stepLabel = safeStepLabel(ev.node, ev.display_name);
            let stepReasoningText = formatStepAsReasoning(ev);
            if (!NODE_DISPLAY[ev.node]) {
              // 未知节点：优先展示安全 summary；退化为纯“任务处理”标签、无业务 detail 的兜底步骤直接跳过，避免噪声堆叠。
              const summary = safeDisplayText(ev.display_name);
              stepReasoningText = summary && summary !== stepLabel && summary !== ev.node ? summary : null;
            }
            if (stepReasoningText) {
              upsertReasoningPart(reasonings, {
                type: 'reasoning',
                text: stepReasoningText,
                parentId: ev.node,
              });
              yield { content: buildContent() };
            }
          }
          // 业务时间线：将 step 映射为业务级节点
          if (ev.node === 'intent_recognition' && ev.status === 'done') {
            const intentText = ev.intent ? `理解为您想查询「${ev.intent}」` : '已理解您的分析需求';
            taskTimeline.push({ type: 'task_understood', label: '任务理解', text: intentText, status: 'done' });
          }
          if (ev.node === 'repair_patch' && ev.status === 'done') {
            const text = safeRepairPatchSummaryText(ev.repair_patch_summary) || '已按业务口径自动修复查询引用';
            upsertTaskTimelineEvent(taskTimeline, { type: 'repair_patch', label: '自动修复', text, status: 'done' });
          } else if (ev.status === 'done' && ev.node !== 'intent_recognition') {
            // 后续 step 归入 BI 执行阶段（多个 step 合并为一条，更新文本）
            const existing = taskTimeline.find((t) => t.type === 'bi_execution');
            if (existing) {
              existing.text = '正在完成查询处理';
            } else {
              taskTimeline.push({ type: 'bi_execution', label: 'BI 执行', text: '正在完成查询处理', status: 'running' });
            }
          }
        } else if (ev.event_envelope?.event_type?.startsWith('repair.')) {
          emitTrace(ev);
          const repairPayload = ev.event_envelope.payload || {};
          const eventType = ev.event_envelope.event_type;
          const safeRepair = safeRepairPlanFromPayload({
            ...repairPayload,
            event_type: eventType,
          });
          if (safeRepair) {
            repairPlan = mergeRepairPlan(repairPlan, safeRepair);
            repairTimeline.push({
              eventType,
              status: safeRepair.status,
              summary: safeRepair.summary,
              repairPlanRef: safeRepair.repairPlanRef,
            });
            upsertTaskTimelineEvent(taskTimeline, {
              type: 'repair_patch',
              label: '自动修复',
              text: safeRepair.summary || '已更新自动修复状态',
              status: eventType === 'repair.rerun_completed' || eventType === 'repair.patch_applied' ? 'done' : 'running',
            });
          }
        } else if (ev.type === 'final') {
          finalPayload = ev;
        }
      }

      if (abortSignal.aborted) {
        yield {
          content: buildContent(),
          status: { type: 'incomplete', reason: 'cancelled' },
        };
        return;
      }

      if (finalPayload) {
	        emitTrace(finalPayload);
	        emitResolvedConversation(unstable_threadId, finalPayload.conversation_id);
	        emitResolvedThread(unstable_threadId, finalPayload.thread_id);

        // 收敛：text 用 final.answer 兜底（report_generator token 可能没全到）
        let finalText = finalPayload.answer || accText;

        // 首条消息后端会自动用首句作为对话标题
        // 派发窗口事件让 ThreadList 刷新 + 局部更新缓存
        // 业务时间线收尾：BI 执行完成、结果产物、下一步
        const biExec = taskTimeline.find((t) => t.type === 'bi_execution');
        if (biExec) biExec.status = 'done';
        if (finalPayload.answer || finalPayload.sql_result || finalPayload.result_ref || finalPayload.report_ref) {
          taskTimeline.push({
            type: 'artifact_created',
            label: '结果产物',
            text: finalPayload.result_ref ? '已生成查询结果' : finalPayload.report_ref ? '已生成分析报告' : '已生成回答',
            status: 'done',
          });
        }
        taskTimeline.push({
          type: 'next_action',
          label: '下一步',
          text: '您可以查看详细结果、继续追问或导出数据',
          status: 'done',
        });

        // 构建 C-ready ArtifactCard 数据
        let artifactCard = null;
        if (finalPayload.artifact_card) {
          // 后端已提供 C-ready ArtifactCard 时仍需过一层清洗，避免 preview 携带 raw rows。
          artifactCard = safeArtifactCard(finalPayload.artifact_card);
        } else {
          // 从现有 final 字段推断生成 ArtifactCard
          const hasResult = finalPayload.result_ref;
          const hasReport = finalPayload.report_ref;
          if (hasResult || hasReport) {
            artifactCard = {
              title: hasReport ? '分析报告' : '查询结果',
              status: 'completed',
              summary_for_chat: safeDisplayText(finalPayload.answer)
                ? safeDisplayText(finalPayload.answer).slice(0, 120)
                : '查询已执行完成',
              preview_payload: null,
              primary_ref: finalPayload.result_ref || finalPayload.report_ref || null,
              related_refs: [],
              actions: [
                { action_type: 'view', label: '查看详情', ref: finalPayload.result_ref || finalPayload.report_ref || '', disabled: false },
                { action_type: 'copy', label: '复制结果', ref: '', disabled: false },
                { action_type: 'export', label: '导出', ref: '', disabled: true },
              ],
            };
          }
        }

        // 构建候选数据集确认数据（从 route_decision 提取）
        let candidateDatasets = null;
        const routeDecision = safeRouteDecision(finalPayload.route_decision);
        if (routeDecision) {
          const rd = routeDecision;
          if ((rd.decision === 'ambiguous' || rd.decision === 'no_match') && Array.isArray(rd.candidates) && rd.candidates.length > 0) {
            const originalQuestion = safeDisplayText(
              finalPayload.original_question
                || finalPayload.originalQuestion
                || finalPayload.question,
            );
            candidateDatasets = {
              ...(originalQuestion ? { original_question: originalQuestion } : {}),
              candidates: rd.candidates.map((c) => ({
                dataset_name: c.dataset_name || `数据集 ${c.dataset_id || ''}`,
                dataset_id: c.dataset_id || null,
                short_reason: c.reason || '根据您的查询匹配',
              })),
            };
          }
        }
        if (looksLikeInternalPlanningText(finalText)) {
          finalText = candidateDatasets
            ? datasetConfirmationAnswer(routeDecision)
            : '任务已完成。';
        }

        const finalRepairPlan = safeRepairPlanFromPayload({}, finalPayload);
        if (finalRepairPlan) {
          repairPlan = mergeRepairPlan(repairPlan, finalRepairPlan);
        }

        if (finalPayload.title && finalPayload.conversation_id) {
          try {
            window.dispatchEvent(
              new CustomEvent('datalogue:thread-rename', {
                detail: {
                  remoteId: String(finalPayload.conversation_id),
                  title: finalPayload.title,
                },
              }),
            );
          } catch (_e) {
            /* SSR 保护 */
          }
        }

        const finalReasonings = safeReasoningSummary(finalPayload.reasoning_summary);
        // 保留完整推理过程：流式阶段的 Leader 思考和 Agent 进度在 final 后不丢弃，live_thinking 收尾标记完成态。
        const preservedStreaming = reasonings
          .filter(isPreservedStreamingReasoning)
          .map((part) => (
            part.parentId === 'live_thinking' && part.status === 'running'
              ? { ...part, status: 'completed' }
              : part
          ));
        const mergedReasonings = finalReasonings.length
          ? [...preservedStreaming, ...finalReasonings]
          : reasonings;

        yield {
          content: [
            ...mergedReasonings,
            ...toolParts,
            { type: 'text', text: finalText },
          ],
          status: { type: 'complete', reason: 'stop' },
          metadata: {
            timing: finalPayload.timing || null,
            custom: {
              answerExplanation: safeAnswerExplanation(finalPayload),
              queryCaliber: safeQueryCaliber(finalPayload),
              resultRef: finalPayload.result_ref
                || finalPayload.response_metadata?.subagent_tool_result?.result_ref
                || null,
              reportRef: finalPayload.report_ref
                || finalPayload.response_metadata?.subagent_tool_result?.report_ref
                || null,
              subagentToolResults: safeSubagentToolResults(
                finalPayload.subagent_tool_results
                  || finalPayload.response_metadata?.subagent_tool_results,
              ),
              routeDecision,
              routePayload: null,
              clarification: safeClarification(finalPayload.clarification, finalPayload.route_payload),
              messageId: finalPayload.message_id || null,
              stepTrace,
              // C-ready 数据结构
              taskTimeline,
              artifactCard: safeArtifactCard(artifactCard),
              candidateDatasets,
              repairPlan,
              repairTimeline,
              toolGroups,
              confirmations,
              timing: buildTimingMetadata(finalPayload.timing, toolGroups),
            },
          },
        };
      } else {
        // 没有 final 时兜底：把已累积文本落到正文，避免答案丢失。
        yield {
          content: [...reasonings, ...toolParts, { type: 'text', text: accText }],
          status: { type: 'complete', reason: 'stop' },
        };
      }
    },
  };
}
