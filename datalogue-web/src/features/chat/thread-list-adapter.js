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
  listConversationPage,
  createConversation,
  renameConversation,
  archiveConversation,
  unarchiveConversation,
  deleteConversation,
	getConversation,
} from '../../api/client';
import { fetchWorkbenchThread } from '../../assistant/workbench-api';
import { NODE_DISPLAY_NAMES } from './node-display';
import {
  safeUserVisibleList,
  safeUserVisibleText,
  sanitizeUserVisibleTrace,
} from './user-visible-safety';

// 内存缓存：localThreadId -> { remoteId, externalId }
const idMap = new Map();
const reverseIdMap = new Map();
let lastInitializedThread = null;

// 会话更新时间缓存：remoteId -> ISO 时间字符串。
// assistant-ui 的 ThreadListItem 只暴露内置字段，不透传自定义 updatedAt，
// 因此在 list() 拉取时把时间写入该 map，供 ThreadList 按 remoteId 读取展示。
export const conversationUpdatedAtMap = new Map();

export function resolveRemoteId(localThreadId) {
  return idMap.get(String(localThreadId ?? ''))?.remoteId ?? null;
}

export function resolveRecentInitializedRemoteId(maxAgeMs = 10000) {
  if (!lastInitializedThread) return null;
  return Date.now() - lastInitializedThread.createdAt <= maxAgeMs
    ? lastInitializedThread.remoteId
    : null;
}

/**
 * 返回最近 initialize 的 pending 线程 localId。
 * 供 chat-adapter 在 unstable_threadId 缺失时兜底使用。
 * 仅当 remoteId 为空（pending）时返回，已有真实会话时返回 null。
 */
export function resolveRecentPendingLocalId(maxAgeMs = 30000) {
  if (!lastInitializedThread) return null;
  if (lastInitializedThread.remoteId) return null; // 已有真实 remoteId，无需兜底
  return Date.now() - lastInitializedThread.createdAt <= maxAgeMs
    ? lastInitializedThread.localId
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
function formatStepAsReasoning(step) {
  // 历史 step_trace 保留内部 display_name；回放时必须映射成业务文案。
  const label = NODE_DISPLAY_NAMES[step.node]
    || NODE_DISPLAY_NAMES[step.display_name]
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

function safeDisplayText(value) {
  return safeUserVisibleText(value);
}

function safeDisplayList(values, limit = 6) {
  return safeUserVisibleList(values, { limit });
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
  if (detail?.message_page?.has_more) {
    // ThreadHistoryAdapter 没有增量加载契约；明确提示当前有界窗口，避免旧消息静默消失。
    out.push({
      id: `history-window-${detail?.conversation?.id || 'unknown'}`,
      role: 'assistant',
      content: [{ type: 'text', text: `当前仅展示最近 ${detail.message_page.limit} 条消息，更早记录可通过历史接口分页读取。` }],
      createdAt: msgs[0]?.created_at ? new Date(msgs[0].created_at) : new Date(0),
      status: { type: 'complete', reason: 'stop' },
      metadata: { custom: { historyWindowTruncated: true } },
    });
  }
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
        const detail = await getConversation(remoteId, { messageLimit: 200 });
	        const messages = messagesFromBackend(detail);
	        return ExportedMessageRepository.fromArray(messages);
      } catch (e) {
        console.error('加载历史消息失败', e);
        if (e?.status === 401 || e?.status === 403) {
          throw e; // 鉴权失败必须交给 runtime 展示错误，不能伪装成“历史为空”。
        }
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

/**
 * 懒创建后端会话：首条消息发送时由 chat adapter 调用。
 * 仅在 initialize 阶段标记为 pending 的线程才会触发创建。
 */
export async function ensureConversationForThread(threadId) {
  const localId = String(threadId ?? '');
  const m = idMap.get(localId);
  if (!m) return null;
  // 已有真实 remoteId（非 pending）→ 直接复用
  if (m.remoteId && !m.pending) return m.remoteId;

  try {
    const conv = await createConversation({});
    const remoteId = String(conv.id);
    const externalId = conv.thread_id || undefined;
    idMap.set(localId, { remoteId, externalId });
    reverseIdMap.set(remoteId, localId);
    lastInitializedThread = { localId, remoteId, createdAt: Date.now() };
    return remoteId;
  } catch (error) {
    // 保留 pending 映射，让用户再次发送首条消息时仍可重试创建后端会话。
    console.error('[thread-list] lazy conversation creation failed', error);
    return null;
  }
}

export class DatalogueThreadListAdapter {
  constructor() {
    this.unstable_Provider = DatalogueThreadProvider;
  }

  async list({ after } = {}) {
    const page = await listConversationPage({ after, limit: 50 });
    const items = page?.items || [];
    items.forEach((c) => {
      // 缓存会话时间供左侧列表展示；优先 updated_at，回退 created_at。
      const iso = c.updated_at ?? c.created_at;
      if (iso) conversationUpdatedAtMap.set(String(c.id), iso);
    });
    return {
      threads: items.map((c) => ({
        status: c.archived ? 'archived' : 'regular',
        remoteId: String(c.id),
        externalId: c.thread_id || undefined,
        title: c.title,
        datasetId: c.dataset_id ?? undefined,
        lastMessageAt: c.updated_at || c.created_at ? new Date(c.updated_at || c.created_at) : undefined,
      })),
      nextCursor: page?.next_cursor || undefined,
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
   * 核心：runtime 给 localId（UUID），adapter 返回 remoteId。
   * - 已注册：直接返回
   * - 未注册：仅注册本地 pending 映射，不立即创建后端会话；
   *   后端会话在首条消息发送时由 ensureConversationForThread() 懒创建。
   */
  async initialize(threadId) {
    const localId = String(threadId ?? '');
    if (idMap.has(localId)) {
      const m = idMap.get(localId);
      return { remoteId: m.remoteId, externalId: m.externalId };
    }
    // 仅注册本地映射，不调后端；避免每次点击「新对话」就创建空会话。
    // 记录最近初始化供 chat-adapter fallback：run() 中 unstable_threadId 可能为 undefined。
    idMap.set(localId, { remoteId: null, externalId: undefined, pending: true });
    lastInitializedThread = { localId, remoteId: null, createdAt: Date.now() };
    return { remoteId: null, externalId: undefined };
  }

  /**
   * 切换到已有会话时：runtime 给 localId，adapter 返回元数据
   * 这里 localId 直接当 remoteId 用（URL 里就是 conv_id）
   */
  async fetch(threadId) {
    const localId = String(threadId ?? '');
    const m = idMap.get(localId);
    if (m?.pending) {
      // pending 草稿还没有后端会话，不能把本地 UUID 当 conversation_id 打到后端。
      return {
        status: 'regular',
        remoteId: null,
        externalId: undefined,
        title: '新对话',
      };
    }
    if (!m) {
      idMap.set(localId, { remoteId: localId, externalId: undefined });
      reverseIdMap.set(localId, localId);
    }
    const remoteId = m?.remoteId || localId;
    if (String(remoteId).startsWith('as_')) {
      const view = await fetchWorkbenchThread(remoteId);
      return {
        status: 'regular',
        remoteId: view.thread_id,
        externalId: view.thread_id,
        title: view.messages?.[0]?.content_summary || '问数工作台',
      };
    }
    const detail = await getConversation(remoteId, { messageLimit: 1 });
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
