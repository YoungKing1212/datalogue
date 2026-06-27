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
import { resolveRecentInitializedRemoteId, resolveRemoteId } from './thread-list-adapter';

const BUSINESS_SESSION_PREFIX = 'assistant-thread';

// 节点显示名映射（与后端 _NODE_DISPLAY_NAMES 对齐，作为前端兜底）
const NODE_DISPLAY = {
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

function summarizeQueryPlan(queryPlan) {
  if (!queryPlan || typeof queryPlan !== 'object') return '';
  const explanation = queryPlan.explanation || {};
  const decisionFactors = Array.isArray(queryPlan.decision_factors)
    ? queryPlan.decision_factors
    : [];
  const plannerWarnings = Array.isArray(queryPlan.planner_warnings)
    ? queryPlan.planner_warnings
    : [];
  const firstFactor = decisionFactors.find((item) => item?.message)?.message;
  const firstWarning = plannerWarnings.find((item) => item?.message)?.message;
  return [
    queryPlan.query_type ? `类型 ${enumLabel(QUERY_TYPE_LABELS, queryPlan.query_type)}` : null,
    queryPlan.execution_strategy
      ? `策略 ${enumLabel(EXECUTION_STRATEGY_LABELS, queryPlan.execution_strategy)}`
      : null,
    explanation.summary || null,
    firstFactor ? `依据 ${firstFactor}` : null,
    firstWarning ? `提示 ${firstWarning}` : null,
  ]
    .filter(Boolean)
    .join(' · ');
}

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
  } else if (ev.node === 'candidate_assets') {
    detail = summarizeCandidateAssets(ev.candidate_assets) || '已召回候选资产';
  } else if (ev.node === 'query_plan') {
    detail = summarizeQueryPlan(ev.query_plan) || '已生成查询规划';
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

      const resolvedRemoteId =
        resolveRemoteId(unstable_threadId) || resolveRecentInitializedRemoteId();
      const convId = resolvedRemoteId
        ? normalizeConversationId(resolvedRemoteId)
        : conversationIdFromCurrentRoute() || normalizeConversationId(unstable_threadId);
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
      const stepTrace = [];
      let accText = '';      // 已累积的 text
      let finalPayload = null;

      // C-ready 业务时间线累加器：从 SSE 事件推断五类节点
      const taskTimeline = [];

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
          // 业务时间线：数据集匹配节点
          const datasetName = ev.dataset_name || (ev.candidates || [])[0]?.dataset_name || '';
          taskTimeline.push({
            type: 'dataset_matching',
            label: '数据集匹配',
            text: datasetName ? `已匹配数据集「${datasetName}」` : '正在匹配数据集',
            status: ev.decision === 'selected' || ev.decision === 'locked' ? 'done' : 'running',
          });
          yield { content: buildContent() };
        } else if (ev.type === 'lead_agent_tools') {
          emitTrace(ev);
          emitResolvedConversation(unstable_threadId, ev.thread_context?.conversation_id);
          reasonings.push({
            type: 'reasoning',
            text: formatLeadAgentToolsAsReasoning(ev),
            parentId: 'lead_agent_tools',
          });
          yield { content: buildContent() };
        } else if (ev.type === 'step') {
          // 通知 AgentPanel（保持现有行为）
          emitTrace(ev);
          stepTrace.push(ev);
          // 只把"完成"的节点累积为 reasoning（running 状态等完成时再算）
          if (ev.status === 'done' && ev.node !== 'error') {
            reasonings.push({
              type: 'reasoning',
              text: formatStepAsReasoning(ev),
              parentId: ev.node,
            });
            yield { content: buildContent() };
          }
          // 业务时间线：将 step 映射为业务级节点
          if (ev.node === 'intent_recognition' && ev.status === 'done') {
            const intentText = ev.intent ? `理解为您想查询「${ev.intent}」` : '已理解您的分析需求';
            taskTimeline.push({ type: 'task_understood', label: '任务理解', text: intentText, status: 'done' });
          }
          if (ev.status === 'done' && ev.node !== 'intent_recognition') {
            // 后续 step 归入 BI 执行阶段（多个 step 合并为一条，更新文本）
            const existing = taskTimeline.find((t) => t.type === 'bi_execution');
            const stepLabel = ev.display_name || NODE_DISPLAY[ev.node] || ev.node;
            if (existing) {
              existing.text = existing.text ? `${existing.text}、${stepLabel}` : stepLabel;
            } else {
              taskTimeline.push({ type: 'bi_execution', label: 'BI 执行', text: `已完成：${stepLabel}`, status: 'running' });
            }
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

        // 收敛：text 用 final.answer 兜底（report_generator token 可能没全到）
        const finalText = finalPayload.answer || accText;

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
          // 后端已提供 C-ready ArtifactCard，直接使用
          artifactCard = finalPayload.artifact_card;
        } else {
          // 从现有 final 字段推断生成 ArtifactCard
          const hasResult = finalPayload.result_ref || finalPayload.sql_result;
          const hasReport = finalPayload.report_ref;
          if (hasResult || hasReport) {
            artifactCard = {
              title: hasReport ? '分析报告' : '查询结果',
              status: 'completed',
              summary_for_chat: finalPayload.answer
                ? finalPayload.answer.slice(0, 120)
                : '查询已执行完成',
              preview_payload: finalPayload.sql_result
                ? { rows: finalPayload.sql_result.rows || [], columns: finalPayload.sql_result.columns || [] }
                : null,
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
        if (finalPayload.route_decision) {
          const rd = finalPayload.route_decision;
          if (rd.decision === 'ambiguous' && Array.isArray(rd.candidates) && rd.candidates.length > 0) {
            candidateDatasets = {
              candidates: rd.candidates.map((c) => ({
                dataset_name: c.dataset_name || `数据集 ${c.dataset_id || ''}`,
                dataset_id: c.dataset_id || null,
                short_reason: c.reason || c.match_reason || '根据您的查询匹配',
              })),
            };
          }
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
              queryPlan: finalPayload.query_plan || finalPayload.queryPlan || null,
              candidateAssets: finalPayload.candidate_assets || finalPayload.candidateAssets || null,
              queryPlanDebug: finalPayload.query_plan_debug || finalPayload.queryPlanDebug || null,
              query_plan: finalPayload.query_plan || null,
              candidate_assets: finalPayload.candidate_assets || null,
              query_plan_debug: finalPayload.query_plan_debug || null,
              queryProfile: finalPayload.query_profile || finalPayload.explainability?.query_profile || null,
              explainability: finalPayload.explainability || null,
              resultRef: finalPayload.result_ref
                || finalPayload.response_metadata?.subagent_tool_result?.result_ref
                || null,
              reportRef: finalPayload.report_ref
                || finalPayload.response_metadata?.subagent_tool_result?.report_ref
                || null,
              subagentToolResults: finalPayload.subagent_tool_results
                || finalPayload.response_metadata?.subagent_tool_results
                || null,
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
              stepTrace,
              // C-ready 数据结构
              taskTimeline,
              artifactCard,
              candidateDatasets,
            },
          },
        };
      } else {
        yield { content: buildContent(), status: { type: 'complete', reason: 'stop' } };
      }
    },
  };
}
