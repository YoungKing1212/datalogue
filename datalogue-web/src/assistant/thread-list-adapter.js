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

if (typeof window !== 'undefined') {
  window.addEventListener('datalogue:conv-resolved', (event) => {
    const { localThreadId, actualConvId } = event.detail || {};
    rememberResolvedConversation(localThreadId, actualConvId);
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
  intent_recognition: 'intent_recognition',
  entry_intent_classification: 'entry_intent_classification',
  analysis_blueprint_execute: 'analysis_blueprint_execute',
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

function formatStepAsReasoning(step) {
  const label = step.display_name || NODE_DISPLAY[step.node] || step.node;
  const elapsed = step.elapsed_ms != null ? `（${step.elapsed_ms}ms）` : '';
  let detail = '';

  if (step.node === 'intent_recognition') {
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
    detail = step.sql ? `已生成：${step.sql.slice(0, 60)}${step.sql.length > 60 ? '…' : ''}` : '编译完成';
  } else if (step.node === 'sql_execute') {
    const rows = step.rows ?? 0;
    detail = `返回 ${rows} 行${step.columns?.length ? ' · ' + step.columns.length + ' 列' : ''}`;
  } else if (step.node === 'sql_audit') {
    const diagnosis = step.sql_diagnosis || step.sql_audit_result || {};
    const title = diagnosis.title || diagnosis.root_cause || diagnosis.code || 'SQL 执行失败';
    const suggested = diagnosis.suggested_action || diagnosis.suggested_fix || '';
    detail = suggested ? `${title} · ${suggested}` : title;
  } else if (step.node === 'report_generator') {
    detail = '已生成分析报告';
  }

  return detail ? `${label}：${detail} ${elapsed}` : `${label} ${elapsed}`.trim();
}

function messagesFromBackend(detail) {
  const msgs = detail?.messages || [];
  const out = [];
  for (let i = 0; i < msgs.length; i++) {
    const m = msgs[i];
    const parts = [];
    // 先从 step_trace 构建 reasoning parts
    const traces = m.step_trace || [];
    for (const step of traces) {
      if (step.status === 'done' && step.node !== 'error') {
        parts.push({
          type: 'reasoning',
          text: formatStepAsReasoning(step),
          parentId: step.node,
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
        custom: {
          routePayload: m.response_metadata?.route_payload || null,
          answerExplanation: m.response_metadata?.answer_explanation || null,
          queryProfile: m.response_metadata?.query_profile || m.response_metadata?.explainability?.query_profile || null,
          explainability: m.response_metadata?.explainability || null,
          messageId: m.id || null,
          langfuseTraceId: m.response_metadata?.langfuse?.trace_id || null,
          langfuseSessionId: m.response_metadata?.langfuse?.session_id || null,
          observability: m.response_metadata?.observability || m.response_metadata?.langfuse || null,
          stepTrace: traces,
          feedback: m.response_metadata?.feedback || null,
        },
      },
    });
  }
  return out;
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
      // 我们的真实持久化由后端 streamChat 完成，这里 no-op 即可
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
