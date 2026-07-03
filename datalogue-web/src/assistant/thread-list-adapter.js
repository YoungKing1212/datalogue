// RemoteThreadListAdapter — 把现有 /api/conversation REST 包成 assistant-ui 的线程列表适配器
// 接口来自 @assistant-ui/core/dist/runtimes/remote-thread-list/types.d.ts
// 通过 unstable_Provider 注入 ThreadHistoryAdapter，加载历史消息（用 getConversation）

import { useMemo, createElement } from 'react';
import { useAuiState } from '@assistant-ui/react';
import { RuntimeAdapterProvider } from '@assistant-ui/react';
import {
  ExportedMessageRepository,
} from '@assistant-ui/react';
import { createAssistantStream } from 'assistant-stream';
import {
  listConversations,
  createConversation,
  renameConversation,
  archiveConversation,
  unarchiveConversation,
  deleteConversation,
	getConversation,
} from '../api/client';
import { fetchWorkbenchThread } from './workbench-api';

// 内存缓存：localThreadId -> { remoteId, externalId }
const idMap = new Map();
const reverseIdMap = new Map();
let lastInitializedThread = null;

export function resolveRemoteId(localThreadId) {
  return idMap.get(String(localThreadId ?? ''))?.remoteId ?? null;
}

export function resolveRecentInitializedRemoteId(maxAgeMs = 10000) {
  if (!lastInitializedThread) return null;
  return Date.now() - lastInitializedThread.createdAt <= maxAgeMs
    ? lastInitializedThread.remoteId
    : null;
}

function rememberResolvedConversation(localThreadId, actualConvId) {
  if (localThreadId == null || actualConvId == null) return;
  const localId = String(localThreadId);
  const remoteId = String(actualConvId);
  if (!localId || !remoteId) return;

  const previous = idMap.get(localId);
  if (previous?.remoteId && previous.remoteId !== remoteId) {
    reverseIdMap.delete(previous.remoteId);
  }
  idMap.set(localId, { remoteId, externalId: previous?.externalId });
  reverseIdMap.set(remoteId, localId);
}

function rememberResolvedThread(localThreadId, threadId) {
  if (localThreadId == null || !threadId) return;
  const localId = String(localThreadId);
  const remoteId = String(threadId);
  if (!localId || !remoteId) return;
  const previous = idMap.get(localId);
  if (previous?.remoteId && previous.remoteId !== remoteId) {
    reverseIdMap.delete(previous.remoteId);
  }
  idMap.set(localId, { remoteId, externalId: previous?.externalId });
  reverseIdMap.set(remoteId, localId);
  lastInitializedThread = { localId, remoteId, createdAt: Date.now() };
}

if (typeof window !== 'undefined') {
	window.addEventListener('datalogue:conv-resolved', (event) => {
	  const { localThreadId, actualConvId } = event.detail || {};
	  rememberResolvedConversation(localThreadId, actualConvId);
	});
	window.addEventListener('datalogue:thread-resolved', (event) => {
	  const { localThreadId, threadId } = event.detail || {};
	  rememberResolvedThread(localThreadId, threadId);
	});
}

/**
 * 把后端 MessageOut 转成 assistant-ui 的 ThreadMessage
 *
 * assistant content 可能含 <think>…</think> 段（历史数据未必已剥离），
 * MessageContent 用 splitThink 把它从正文剥离——不再额外拆出 reasoning part，
 * 避免与 ChainOfThought 重复展示。
 */
// 节点显示名映射（与后端 _NODE_DISPLAY_NAMES 对齐）
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

function formatStepAsReasoning(step) {
  // 历史 step_trace 保留内部 display_name；回放时必须映射成业务文案。
  const label = NODE_DISPLAY[step.node]
    || NODE_DISPLAY[step.display_name]
    || safeDisplayText(step.display_name)
    || safeDisplayText(step.label)
    || '任务处理';
  const elapsed = step.elapsed_ms != null ? `（${step.elapsed_ms}ms）` : '';
  let detail = '';

  if (step.detail) {
    detail = safeDisplayText(step.detail) || '';
  } else if (step.node === 'intent_recognition') {
    const intent = step.intent || '';
    const entities = step.entities || {};
    const entKeys = Object.keys(entities).filter((k) => entities[k]);
    detail = `${intent}${entKeys.length ? ' · ' + entKeys.join('/') : ''}`;
  } else if (step.node === 'schema_recall') {
    const lines = step.schema_summary || [];
    detail = lines.length ? lines.join(' / ') : '已检索相关表结构';
  } else if (step.node === 'term_normalize_node') {
    const normalization = step.term_normalization || {};
    const matched = normalization.matched_terms?.length ?? 0;
    const conflicts = normalization.conflicts?.length ?? 0;
    detail = conflicts ? `发现 ${conflicts} 个术语冲突` : `命中 ${matched} 个业务术语`;
  } else if (step.node === 'semantic_asset_resolution_node' || step.node === 'metric_resolution_node') {
    const resolution = step.semantic_asset_resolution || {};
    const count = resolution.assets?.length ?? step.metric_resolution?.metrics?.length ?? 0;
    detail = `命中 ${count} 个语义资产`;
  } else if (step.node === 'dsl_generate') {
    detail = step.generation_mode === 'inferred' ? 'AI 推断生成' : '已基于指标生成';
  } else if (step.node === 'dsl_validate') {
    detail = 'DSL 校验通过';
  } else if (step.node === 'dsl_compiler') {
    detail = '查询语句已生成并进入执行校验';
  } else if (step.node === 'sql_execute') {
    const rows = step.rows ?? 0;
    detail = `返回 ${rows} 行${step.columns?.length ? ' · ' + step.columns.length + ' 列' : ''}`;
  } else if (step.node === 'sql_audit') {
    const diagnosis = step.sql_diagnosis || step.sql_audit_result || {};
    const title = diagnosis.title || diagnosis.root_cause || diagnosis.code || '查询执行失败';
    const suggested = diagnosis.suggested_action || diagnosis.suggested_fix || '';
    detail = suggested ? `${title} · ${suggested}` : title;
  } else if (step.node === 'report_generator') {
    detail = '已生成分析报告';
  }

  return detail ? `${label}：${detail} ${elapsed}` : `${label} ${elapsed}`.trim();
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
  'query_plan',
  'queryPlan',
  'candidate_assets',
  'candidateAssets',
  'query_plan_debug',
  'queryPlanDebug',
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
  'node',
  'display_name',
  'displayName',
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

function safeDisplayText(value) {
  if (value == null) return null;
  const text = String(value).trim();
  if (!text || INTERNAL_TEXT_PATTERN.test(text)) return null;
  return text.slice(0, 160);
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

function safeAnswerExplanation(metadata = {}) {
  const explanation = metadata.answer_explanation || metadata.answerExplanation || null;
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
    sql_summary: explanation.sql_summary ? { preview: Boolean(explanation.sql_summary.preview) } : null,
    data_sources: [],
  };
}

function safeQueryCaliber(metadata = {}) {
  const source =
    metadata.query_caliber
    || metadata.queryCaliber
    || metadata.business_caliber
    || metadata.businessCaliber
    || metadata.answer_explanation?.caliber
    || metadata.answerExplanation?.caliber
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

export function buildHistoryMessageCustom(message, traces = []) {
  const metadata = message?.response_metadata || {};
  const safeTraces = sanitizeUserVisibleTrace(traces);
  return {
    answerExplanation: safeAnswerExplanation(metadata),
    queryCaliber: safeQueryCaliber(metadata),
    resultRef: metadata.result_ref || metadata.subagent_tool_result?.result_ref || null,
    reportRef: metadata.report_ref || metadata.subagent_tool_result?.report_ref || null,
    artifactCard: safeArtifactCard(metadata.artifact_card),
    primaryRef: metadata.primary_ref || null,
    relatedRefs: metadata.related_refs || null,
    taskId: metadata.task_id || null,
    traceId: metadata.trace_id || metadata.observability?.trace_id || null,
    subagentToolResults: safeSubagentToolResults(metadata.subagent_tool_results),
    routeDecision: safeRouteDecision(metadata.route_decision),
    routePayload: null,
    clarification: safeClarification(metadata.clarification, metadata.route_payload),
    messageId: message?.id || null,
    stepTrace: safeTraces,
    feedback: metadata.feedback || null,
  };
}

export function messagesFromBackend(detail) {
  const msgs = detail?.messages || [];
  const out = [];
  for (let i = 0; i < msgs.length; i++) {
    const m = msgs[i];
    const parts = [];
    // 先从 step_trace 构建 reasoning parts
    const traces = m.step_trace || [];
    for (const [stepIndex, step] of traces.entries()) {
      if (step.status === 'done' && step.node !== 'error') {
        parts.push({
          type: 'reasoning',
          text: formatStepAsReasoning(step),
          parentId: step.node || step.display_name || `step-${stepIndex}`,
        });
      }
    }
    // 再添加 text part
    parts.push({ type: 'text', text: m.content || '' });
    out.push({
      id: `m-${m.id}`,
      role: m.role === 'user' ? 'user' : 'assistant',
      content: parts,
      createdAt: m.created_at ? new Date(m.created_at) : new Date(),
      status: m.role === 'assistant' ? { type: 'complete', reason: 'stop' } : undefined,
      metadata: {
        custom: buildHistoryMessageCustom(m, traces),
      },
    });
  }
  return out;
}

export function messagesFromWorkbench(view) {
  const msgs = view?.messages || [];
  return msgs.map((message) => ({
    id: message.message_id,
    role: message.role === 'user' ? 'user' : 'assistant',
    content: [{ type: 'text', text: message.content_summary || '' }],
    createdAt: message.created_at ? new Date(message.created_at) : new Date(),
    status: message.role === 'assistant' ? { type: 'complete', reason: 'stop' } : undefined,
    metadata: {
      custom: {
        workbenchThreadId: view.thread_id,
        artifactCard: view.primary_artifact_ref
          ? {
              title: '查询结果',
              status: 'completed',
              primary_ref: view.primary_artifact_ref,
              related_refs: view.related_refs || [],
            }
          : null,
      },
    },
  }));
}

/**
 * 自定义 history adapter — 每次 load() 都从后端拉取
 */
function makeHistoryAdapter(getRemoteId) {
  return {
	    async load() {
	      const remoteId = getRemoteId();
	      if (!remoteId) return { messages: [] };
	      try {
	        if (String(remoteId).startsWith('as_')) {
	          const view = await fetchWorkbenchThread(remoteId);
	          return ExportedMessageRepository.fromArray(messagesFromWorkbench(view));
	        }
	        const detail = await getConversation(remoteId);
	        const messages = messagesFromBackend(detail);
	        return ExportedMessageRepository.fromArray(messages);
      } catch (e) {
        console.error('加载历史消息失败', e);
        return { messages: [] };
      }
    },
    async append(_item) {
      // assistant-ui 默认会调这个把新消息存到 history；
      // 真实持久化由后端 Agent Team task stream 完成，这里 no-op 即可
    },
  };
}

/**
 * Provider 组件：把 history 适配器注入当前 thread 的 context
 */
function DatalogueThreadProvider({ children }) {
  const remoteId = useAuiState((s) => s.threadListItem.remoteId);
  const adapters = useMemo(
    () => ({
      history: makeHistoryAdapter(() => remoteId),
    }),
    [remoteId],
  );
  return createElement(RuntimeAdapterProvider, { adapters }, children);
}

export class DatalogueThreadListAdapter {
  constructor() {
    this.unstable_Provider = DatalogueThreadProvider;
  }

  async list({ archived = false } = {}) {
    const items = await listConversations({ archived });
    return {
      threads: items.map((c) => ({
        status: c.archived ? 'archived' : 'regular',
        remoteId: String(c.id),
        externalId: c.thread_id || undefined,
        title: c.title,
        datasetId: c.dataset_id ?? undefined,
      })),
    };
  }

  async rename(remoteId, newTitle) {
    await renameConversation(remoteId, newTitle);
  }

  async archive(remoteId) {
    await archiveConversation(remoteId);
  }

  async unarchive(remoteId) {
    await unarchiveConversation(remoteId);
  }

  async delete(remoteId) {
    await deleteConversation(remoteId);
    const localId = reverseIdMap.get(remoteId);
    if (localId) {
      idMap.delete(localId);
      reverseIdMap.delete(remoteId);
    }
  }

  /**
   * 核心：runtime 给 localId（UUID），adapter 返回 remoteId
   * - 已注册：直接返回
   * - 未注册：调 POST /api/conversation 建空会话，注册后返回
   */
  async initialize(threadId) {
    if (idMap.has(threadId)) {
      const m = idMap.get(threadId);
      return { remoteId: m.remoteId, externalId: m.externalId };
    }
    const conv = await createConversation({});
    const remoteId = String(conv.id);
    const externalId = conv.thread_id || undefined;
    idMap.set(threadId, { remoteId, externalId });
    reverseIdMap.set(remoteId, threadId);
    lastInitializedThread = { localId: String(threadId), remoteId, createdAt: Date.now() };
    return { remoteId, externalId };
  }

  /**
   * 切换到已有会话时：runtime 给 localId，adapter 返回元数据
   * 这里 localId 直接当 remoteId 用（URL 里就是 conv_id）
   */
	  async fetch(threadId) {
	    const m = idMap.get(threadId);
	    if (!m) {
	      idMap.set(threadId, { remoteId: threadId, externalId: undefined });
	      reverseIdMap.set(threadId, threadId);
	    }
	    const remoteId = m?.remoteId || threadId;
	    if (String(remoteId).startsWith('as_')) {
	      const view = await fetchWorkbenchThread(remoteId);
	      return {
	        status: 'regular',
	        remoteId: view.thread_id,
	        externalId: view.thread_id,
	        title: view.messages?.[0]?.content_summary || '问数工作台',
	      };
	    }
	    const detail = await getConversation(remoteId);
    const c = detail?.conversation || {};
    return {
      status: c.archived ? 'archived' : 'regular',
      remoteId: String(c.id),
      externalId: c.thread_id || undefined,
      title: c.title,
      datasetId: c.dataset_id ?? undefined,
    };
  }

  /**
   * 标题生成 — 后端 chat 流程会自动写标题，前端 no-op
   * 返回空 AssistantStream 满足类型约束
   */
  async generateTitle(_remoteId, _messages) {
    return createAssistantStream(() => {});
  }
}
