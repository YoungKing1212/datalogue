// ChatModelAdapter — 把后端 SSE 流式响应包成 assistant-ui 能消费的 async generator
// assistant-ui 通过 unstable_threadId 传入当前 thread 标识。不同版本/阶段可能传 remoteId
//（后端 conversation_id），也可能传本地 thread id；因此这里显式生成业务 session_id，
// 让后端 ConversationStore 不依赖 Langfuse session 或一次性 request id。
//
// 数据流：
//   token 事件          → 累积到 accText（TextMessagePart）
//   step done 事件      → 累积为一条 ReasoningMessagePart（text 是该节点的小结）
//                        同时 window 派发 'datalogue:trace' 给 AgentPanel
//   final 事件          → 收敛 text + metadata.custom（sql/sql_result/...）
//
// 每次 yield content 数组是完整覆盖，所以本地累加器维护 reasonings + accText。

import { streamChatEvents } from '../api/client';

const BUSINESS_SESSION_PREFIX = 'assistant-thread';

// 节点显示名映射（与后端 _NODE_DISPLAY_NAMES 对齐，作为前端兜底）
const NODE_DISPLAY = {
  intent_recognition: '意图识别',
  entry_intent_classification: '入口分类',
  analysis_blueprint_execute: '蓝图执行',
  schema_recall: 'Schema 召回',
  term_normalize_node: '术语归一化',
  semantic_asset_resolution_node: '语义资产解析',
  metric_resolution_node: '指标解析',
  dsl_generate: 'DSL 生成',
  dsl_validate: 'DSL 校验',
  dsl_compiler: 'SQL 编译',
  sql_execute: 'SQL 执行',
  sql_audit: 'SQL 诊断',
  report_generator: '报告生成',
};

/**
 * 把单个 step 事件格式化成 reasoning 文本（一行小卡片式）
 */
function formatStepAsReasoning(ev) {
  const label = ev.display_name || NODE_DISPLAY[ev.node] || ev.node;
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
    detail = ev.sql ? `已生成：${ev.sql.slice(0, 60)}${ev.sql.length > 60 ? '…' : ''}` : '编译完成';
  } else if (ev.node === 'sql_execute') {
    const rows = ev.rows ?? 0;
    detail = `返回 ${rows} 行${ev.columns?.length ? ' · ' + ev.columns.length + ' 列' : ''}`;
  } else if (ev.node === 'sql_audit') {
    const diagnosis = ev.sql_diagnosis || ev.sql_audit_result || {};
    const title = diagnosis.title || diagnosis.root_cause || diagnosis.code || 'SQL 执行失败';
    const suggested = diagnosis.suggested_action || diagnosis.suggested_fix || '';
    detail = suggested ? `${title} · ${suggested}` : title;
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

/**
 * 在 SSE 事件来时 dispatch window 自定义事件给 AgentPanel
 * 不走 assistant-ui runtime，保持面板的低耦合
 */
function emitTrace(ev) {
  try {
    window.dispatchEvent(new CustomEvent('datalogue:trace', { detail: ev }));
  } catch (_e) {
    /* SSR 保护 */
  }
}

/**
 * 构造 ChatModelAdapter
 * @param {object} opts
 * @param {{current: string|null}} opts.datasetIdRef - 数据集 ID 共享 ref，ChatPage 更新
 */
export function makeChatAdapter({ datasetIdRef }) {
  const fallbackSessionId = createFallbackBusinessSessionId();

  return {
    async *run({ messages, abortSignal, unstable_threadId }) {
      const question = extractQuestion(messages);
      if (!question) return;

      const convId = normalizeConversationId(unstable_threadId);
      const businessSessionId = buildBusinessSessionId({
        threadId: unstable_threadId,
        conversationId: convId,
        fallbackSessionId,
      });
      const datasetId = datasetIdRef?.current ?? null;
      const clarificationResponse =
        typeof window !== 'undefined'
          ? window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ || null
          : null;
      if (clarificationResponse && typeof window !== 'undefined') {
        window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = null;
      }

      let stream;
      try {
        stream = streamChatEvents(
          {
            question,
            session_id: businessSessionId,
            conversation_id: convId,
            dataset_id: datasetId,
            clarification_response: clarificationResponse,
          },
          { signal: abortSignal },
        );
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
      let accText = '';      // 已累积的 text
      let finalPayload = null;

      // 工具：构造当前 message content
      const buildContent = () => [
        ...reasonings,
        { type: 'text', text: accText },
      ];

      for await (const ev of stream) {
        if (abortSignal.aborted) break;

        if (ev.type === 'token') {
          accText += ev.content || '';
          yield { content: buildContent() };
        } else if (ev.type === 'route_decision') {
          emitTrace(ev);
          reasonings.push({
            type: 'reasoning',
            text: formatRouteDecisionAsReasoning(ev),
            parentId: 'manifest_route',
          });
          yield { content: buildContent() };
        } else if (ev.type === 'lead_agent_tools') {
          emitTrace(ev);
          reasonings.push({
            type: 'reasoning',
            text: formatLeadAgentToolsAsReasoning(ev),
            parentId: 'lead_agent_tools',
          });
          yield { content: buildContent() };
        } else if (ev.type === 'step') {
          // 通知 AgentPanel（保持现有行为）
          emitTrace(ev);
          // 只把"完成"的节点累积为 reasoning（running 状态等完成时再算）
          if (ev.status === 'done' && ev.node !== 'error') {
            reasonings.push({
              type: 'reasoning',
              text: formatStepAsReasoning(ev),
              parentId: ev.node,
            });
            yield { content: buildContent() };
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

        // 收敛：text 用 final.answer 兜底（report_generator token 可能没全到）
        const finalText = finalPayload.answer || accText;

        // 首条消息后端会自动用首句作为对话标题
        // 派发窗口事件让 ThreadList 刷新 + 局部更新缓存
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

        yield {
          content: [...reasonings, { type: 'text', text: finalText }],
          status: { type: 'complete', reason: 'stop' },
          metadata: {
            custom: {
              sql: finalPayload.sql || null,
              sqlResult: finalPayload.sql_result || null,
              sqlDiagnosis: finalPayload.sql_diagnosis || null,
              sqlAuditResult: finalPayload.sql_audit_result || null,
              answerExplanation: finalPayload.answer_explanation || null,
              queryProfile: finalPayload.query_profile || finalPayload.explainability?.query_profile || null,
              explainability: finalPayload.explainability || null,
              routeDecision: finalPayload.route_decision || null,
              dsl: finalPayload.dsl || null,
              routePayload: finalPayload.route_payload || null,
              clarification: finalPayload.route_payload?.kind === 'term_conflict_clarification'
                ? {
                    kind: 'term_conflict',
                    clarificationId: finalPayload.route_payload.clarification_id,
                    candidates: finalPayload.route_payload.candidates || [],
                    expiresAt: finalPayload.route_payload.expires_at || null,
                  }
                : finalPayload.clarification || null,
              clarificationResolution: finalPayload.clarification_resolution || null,
              termNormalization: finalPayload.term_normalization || null,
              semanticAssetResolution: finalPayload.semantic_asset_resolution || null,
              metricResolution: finalPayload.metric_resolution || null,
              generationMode: finalPayload.generation_mode || null,
              intent: finalPayload.intent || null,
              messageId: finalPayload.message_id || null,
              langfuseTraceId: finalPayload.langfuse_trace_id || null,
              langfuseSessionId: finalPayload.langfuse_session_id || null,
              observability: finalPayload.observability || null,
            },
          },
        };
      } else {
        yield { content: buildContent(), status: { type: 'complete', reason: 'stop' } };
      }
    },
  };
}
