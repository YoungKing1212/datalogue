// ChatModelAdapter — 把后端 SSE 流式响应包成 assistant-ui 能消费的 async generator
// assistant-ui 通过 unstable_threadId 传入当前 thread 的 remoteId（即后端 conversation_id）
// 新 thread 已经在 useRemoteThreadListRuntime 的 initialize() 阶段由 ThreadListAdapter 调
// POST /api/conversation 创建，并把 conv_id 写入 threadListItem.remoteId
//
// 数据流：
//   token 事件          → 累积到 accText（TextMessagePart）
//   step done 事件      → 累积为一条 ReasoningMessagePart（text 是该节点的小结）
//                        同时 window 派发 'datalogue:trace' 给 AgentPanel
//   final 事件          → 收敛 text + metadata.custom（sql/sql_result/...）
//
// 每次 yield content 数组是完整覆盖，所以本地累加器维护 reasonings + accText。

import { streamChatEvents } from '../api/client';

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
    const retries = ev.sql_retry_trace?.length ?? 0;
    const retryText = retries ? ` · 自动修复第 ${retries} 次` : '';
    detail = suggested ? `${title} · ${suggested}${retryText}` : `${title}${retryText}`;
  } else if (ev.node === 'report_generator') {
    detail = '已生成分析报告';
  }

  return detail ? `${label}：${detail} ${elapsed}` : `${label} ${elapsed}`.trim();
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
  return {
    async *run({ messages, abortSignal, unstable_threadId }) {
      const question = extractQuestion(messages);
      if (!question) return;

      const convId = unstable_threadId ? Number(unstable_threadId) : null;
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
              sqlRetryTrace: finalPayload.sql_retry_trace || null,
              answerExplanation: finalPayload.answer_explanation || null,
              dsl: finalPayload.dsl || null,
              routePayload: finalPayload.route_payload || null,
              clarification: finalPayload.route_payload?.kind === 'term_conflict_clarification'
                ? {
                    clarificationId: finalPayload.route_payload.clarification_id,
                    candidates: finalPayload.route_payload.candidates || [],
                    expiresAt: finalPayload.route_payload.expires_at || null,
                  }
                : null,
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
