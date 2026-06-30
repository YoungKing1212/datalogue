// ChatPage — Chat 页面顶层组件
// 负责：
// 1. 构造 assistant-ui runtime（useRemoteThreadListRuntime + useLocalRuntime）
// 2. URL ↔ mainThreadId 双向同步（/chat ↔ /chat/:id）
// 3. 监听 SSE 'datalogue:trace' 事件，向 AgentPanel 推数据
// 4. 维护 datasetList / selectedDs 顶层状态（保持跨 thread 不变）

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  useLocalRuntime,
  useRemoteThreadListRuntime,
  useAui,
  useAuiState,
} from '@assistant-ui/react';
import { DatalogueThreadListAdapter } from '../assistant/thread-list-adapter';
import { makeChatAdapter } from '../assistant/chat-adapter';
import { Thread, TraceProvider } from '../assistant/Thread';
import { ThreadList } from '../assistant/ThreadList';
import { MyComposer, DatasetChip } from '../assistant/MyComposer';
import { Icon } from './icons';
import { AgentPanel } from './agent-panel';
import { getConversation, listDatasets, streamChatEvents } from '../api/client';
import { normalizeWorkbenchThreadId } from '../assistant/workbench-api';
import WorkbenchPanel from './workbench-panel';

// 单例 adapter（避免每次渲染重建）
const threadListAdapter = new DatalogueThreadListAdapter();

function inferConversationDatasetId(detail) {
  const direct = detail?.conversation?.dataset_id;
  if (direct != null) return Number(direct);
  return null;
}

export function shouldSwitchToRouteThread(routeId, mainThreadId, remoteId) {
  if (!routeId) return false;
  const normalizedRouteId = String(routeId);
  if (mainThreadId && String(mainThreadId) === normalizedRouteId) return false;
  if (remoteId && String(remoteId) === normalizedRouteId) return false;
  return true;
}

export function resolveUrlSyncTarget({ routeId, remoteId, mainThreadChanged, hasObservedThread }) {
  if (!remoteId) return null;
  if (String(remoteId) === String(routeId)) return null;
  if (routeId && !hasObservedThread) return null; // 首次深链加载时，URL 是权威输入，等待 RouteThreadSync 完成。
  if (routeId && !mainThreadChanged) return null; // 路由刚变化但 runtime 仍是旧会话时，避免把地址栏回滚。
  if (mainThreadChanged) return `/chat/${remoteId}`;
  return null;
}

export function resolveWorkbenchThreadId(routeId, remoteId, resolvedThreadId = null) {
  if (routeId) return normalizeWorkbenchThreadId(routeId);
  return normalizeWorkbenchThreadId(resolvedThreadId || remoteId);
}

export function conversationRouteIdForDatasetRestore(routeId) {
  if (!routeId) return null;
  const value = String(routeId).trim();
  if (/^\d+$/.test(value)) return value;
  const legacyMatch = value.match(/^conv_(\d+)$/);
  return legacyMatch ? legacyMatch[1] : null;
}

export function submitWorkbenchRetryRun(runRequest) {
  return runWorkbenchRetryStream(runRequest).catch((e) => {
    console.error('[workbench] retry stream failed', e);
  });
}

function safeRetryConversationId(value) {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) return value;
  if (typeof value === 'string' && /^\d+$/.test(value)) return Number(value);
  return null;
}

function safeRetryDatasetId(value) {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) return value;
  if (typeof value === 'string' && /^\d+$/.test(value)) return Number(value);
  return null;
}

function safeRetryText(value, fallback = '') {
  const text = String(value ?? '').trim();
  return text || fallback;
}

function dispatchWorkbenchTrace(event) {
  if (typeof window === 'undefined' || !event) return;
  window.dispatchEvent(new CustomEvent('datalogue:trace', { detail: event }));
  if (event.type === 'final' && event.thread_id) {
    window.dispatchEvent(
      new CustomEvent('datalogue:thread-resolved', {
        detail: { localThreadId: event.thread_id, threadId: event.thread_id },
      }),
    );
  }
}

export async function runWorkbenchRetryStream(
  runRequest,
  {
    streamEvents = streamChatEvents,
    dispatchTrace = dispatchWorkbenchTrace,
  } = {},
) {
  if (!runRequest) return null;
  const threadId = safeRetryText(runRequest.thread_id);
  const retryCheckpointRef = safeRetryText(runRequest.retry_checkpoint_ref);
  if (!threadId || !retryCheckpointRef) return null;
  const payload = {
    question: safeRetryText(runRequest.question, safeRetryText(runRequest.display_text, '重试上一步')),
    conversation_id: safeRetryConversationId(runRequest.conversation_id),
    thread_id: threadId,
    dataset_id: safeRetryDatasetId(runRequest.dataset_id),
    retry_checkpoint_ref: retryCheckpointRef,
  };
  let finalPayload = null;
  for await (const event of streamEvents(payload)) {
    // Workbench retry 只消费业务级 SSE envelope；后端 checkpoint 恢复真实执行上下文。
    dispatchTrace(event);
    if (event?.type === 'final') finalPayload = event;
  }
  return finalPayload;
}

export function shouldAcceptResolvedWorkbenchThread({
  routeId,
  threadId,
}) {
  if (!threadId || !String(threadId).startsWith('as_')) return false;
  return !routeId; // `/chat` 候选确认可能用 remote conv id 触发 run，仍应切到最新 as_* mirror。
}

/**
 * 在 runtime context 内部：URL 正向同步
 * 直接打开 /chat/:id 时，assistant-ui 的首帧本地草稿可能还没有 remoteId，
 * 这里显式切到路由会话，保证历史消息和 ArtifactCard 从后端 fetch 后回放。
 */
function RouteThreadSync({ routeId }) {
  const aui = useAui();
  const pendingRouteRef = useRef(null);
  const mainThreadId = useAuiState((s) => s.threads?.mainThreadId);
  const remoteId = useAuiState((s) => {
    const id = s.threads?.mainThreadId;
    const item = s.threads?.threadItems?.find((t) => t.id === id);
    return item?.remoteId;
  });

  useEffect(() => {
    const normalizedRouteId = routeId ? String(routeId) : null;
    if (!shouldSwitchToRouteThread(routeId, mainThreadId, remoteId)) {
      if (
        normalizedRouteId &&
        (String(mainThreadId) === normalizedRouteId || String(remoteId) === normalizedRouteId)
      ) {
        pendingRouteRef.current = null;
      }
      return;
    }
    if (pendingRouteRef.current === normalizedRouteId) return;
    pendingRouteRef.current = normalizedRouteId;
    aui.threads().switchToThread(normalizedRouteId).catch((e) => {
      pendingRouteRef.current = null; // 切换失败必须允许后续路由变化重试，不能把页面永久卡在草稿态。
      console.error('[thread-list] route thread switch failed', e);
    });
  }, [aui, routeId, mainThreadId, remoteId]);

  return null;
}

/**
 * 在 runtime context 内部：URL 反向同步
 * 当 mainThread 切换时，把 URL 推到 /chat/:remoteId
 */
function UrlSync({ routeId }) {
  const navigate = useNavigate();
  const previousMainThreadIdRef = useRef(null);
  const mainThreadId = useAuiState((s) => s.threads?.mainThreadId);
  const remoteId = useAuiState((s) => {
    const id = s.threads?.mainThreadId;
    const item = s.threads?.threadItems?.find((t) => t.id === id);
    return item?.remoteId;
  });

  useEffect(() => {
    const previousMainThreadId = previousMainThreadIdRef.current;
    const hasObservedThread = previousMainThreadId != null;
    const mainThreadChanged = previousMainThreadId !== mainThreadId;
    previousMainThreadIdRef.current = mainThreadId;
    const target = resolveUrlSyncTarget({
      routeId,
      remoteId,
      mainThreadChanged,
      hasObservedThread,
    });
    if (target) navigate(target, { replace: true }); // 只有 runtime 主线程真实变更时，才反向同步 URL。
  }, [remoteId, routeId, navigate, mainThreadId]);

  return null;
}

/**
 * Empty 状态 — 欢迎屏 + 居中 ask hero
 * 设计：品牌 mark（渐变方块 + 3 根升序条）+ eyebrow + 标题 + 副标题
 *      + hero composer（textarea + 3 个 pill + 圆形 send 按钮）
 *      + 4 张带色相 hue 的预设问题卡
 */
function WelcomeHero({ selectedDs, setSelectedDs, datasetList, setComposerText }) {
  // 4 个示例问题 — hue 决定图标块底色
  const presets = [
    { icon: 'thunder',    q: '上周整体销售为什么下降了 12%？', cat: '归因分析', hue: 245 },
    { icon: 'chart_line', q: '近 30 天各渠道 ROI 对比',       cat: '趋势对比', hue: 195 },
    { icon: 'chart_pie',  q: '本月各品类 GMV 结构占比',       cat: '构成拆解', hue: 285 },
    { icon: 'insight',    q: '高价值用户的复购特征',          cat: '用户洞察', hue: 60 },
  ];

  return (
    <div className="chat-main chat-empty">
      <div className="ce-stage">
        <div className="ce-inner">

          {/* —— 头部：品牌 mark + eyebrow + 标题 + 副标题 —— */}
          <div className="ce-head">
            <div className="ce-mark">
              <div className="bars"><i /><i /><i /></div>
            </div>
            <div className="ce-eyebrow">AI 原生 · 自动问数</div>
            <h1 className="ce-title">问点什么？</h1>
            <p className="ce-sub">用一句话描述你的业务问题，数语会自动选取数据集、生成 SQL、绘制图表，并解释结论。</p>
          </div>

          {/* —— Hero composer —— */}
          <ComposerPrimitive.Root className="ce-composer">
            <ComposerPrimitive.Input
              className="ce-input"
              rows={2}
              placeholder="例如：上周华东区销售为什么下降？哪个品类拖累最大？"
            />
            <div className="ce-bar">
              <DatasetChip
                variant="ce"
                selectedDs={selectedDs}
                setSelectedDs={setSelectedDs}
                datasetList={datasetList}
              />
              <button type="button" className="ce-pill">
                <Icon name="calendar" />
                <span>近 7 天</span>
                <Icon name="chev_down" className="chev" />
              </button>
              <button type="button" className="ce-pill">
                <Icon name="brain" />
                <span>深度归因</span>
              </button>
              <ComposerPrimitive.Send className="ce-send" aria-label="发送">
                <Icon name="send" />
              </ComposerPrimitive.Send>
            </div>
          </ComposerPrimitive.Root>

          {/* —— 预设问题 —— */}
          <div className="ce-sughead">
            <div className="l">
              试试这些<span>点击直接提问</span>
            </div>
            <button type="button" className="r">
              查看全部模板<Icon name="chev" />
            </button>
          </div>
          <div className="ce-suggrid">
            {presets.map((s, i) => (
              <button
                key={i}
                type="button"
                className="ce-sug"
                onClick={() => setComposerText(s.q)}
              >
                <div className="tile" style={{ '--h': s.hue }}>
                  <Icon name={s.icon} />
                </div>
                <div className="body">
                  <div className="q">{s.q}</div>
                  <div className="cat">{s.cat}</div>
                </div>
                <span className="go">
                  <Icon name="arrow_up_right" />
                </span>
              </button>
            ))}
          </div>

        </div>
      </div>
    </div>
  );
}

/**
 * 接管 composer 文本设置 — 需要在 AssistantRuntime context 内调用
 * v0.14 API: aui.composer().setText(text) （注意不是 thread().composer）
 */
function ComposerTextSetter({ register }) {
  const api = useAui();
  useEffect(() => {
    register(() => (text) => {
      api.composer().setText(text);
    });
  }, [api, register]);
  useEffect(() => {
    const handler = (event) => {
      const text = event.detail?.text || '';
      if (!text) return;
      api.composer().setText(text);
      api.composer().send();
    };
    window.addEventListener('datalogue:composer-submit', handler);
    return () => window.removeEventListener('datalogue:composer-submit', handler);
  }, [api]);
  return null;
}

/**
 * ChatPage 内部主体（在 AssistantRuntimeProvider 之内）
 */
function ChatPageInner({ routeId, traceOpen, setTraceOpen, showFollowups, agentVerbosity }) {
  const [selectedDs, setSelectedDs] = useState(null);
  const [datasetList, setDatasetList] = useState([]);

  // AgentPanel 数据 —— 来自 window 'datalogue:trace' 事件
  const [traceSteps, setTraceSteps] = useState([]);
  const [intent, setIntent] = useState(null);
  const [metricResolution, setMetricResolution] = useState(null);
  const [generationMode, setGenerationMode] = useState(null);
  const [sqlResult, setSqlResult] = useState(null);
  const [traceMeta, setTraceMeta] = useState(null);

  // composer 文本设置回调（供 WelcomeHero 快捷词条调用）
  const setComposerTextRef = useRef(() => {});
  const handleRegisterSetter = (fn) => {
    setComposerTextRef.current = fn();
  };

  // 拉取 dataset 列表
  useEffect(() => {
    listDatasets().then(setDatasetList).catch(console.error);
  }, []);

  // 切换历史会话时恢复该会话绑定的数据集，保证后续追问仍带 dataset_id
  useEffect(() => {
    const conversationRouteId = conversationRouteIdForDatasetRestore(routeId);
    if (!conversationRouteId || datasetList.length === 0) return undefined;
    let cancelled = false;
    getConversation(conversationRouteId)
      .then((detail) => {
        if (cancelled) return;
        const datasetId = inferConversationDatasetId(detail);
        if (datasetId == null) {
          setSelectedDs(null);
          return;
        }
        const matched = datasetList.find((item) => Number(item.id) === Number(datasetId));
        setSelectedDs(matched || null);
      })
      .catch((err) => {
        if (!cancelled) console.error('恢复会话数据集失败', err);
      });
    return () => {
      cancelled = true;
    };
  }, [routeId, datasetList]);

  // 把 selectedDs 变化同步到 datasetIdRef（通过 window 事件桥接给 DatasetSync）
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent('datalogue:dataset-change', {
        detail: selectedDs?.id ?? null,
      }),
    );
  }, [selectedDs]);

  // 监听 SSE 转发的 trace 事件
  useEffect(() => {
    const handler = (e) => {
      const ev = e.detail;
      if (!ev) return;

      const syncSelectedDataset = (routeDecision) => {
        const datasetId = routeDecision?.dataset_id == null ? null : Number(routeDecision.dataset_id);
        if (routeDecision?.decision === 'selected' && datasetId != null) {
          const matched = datasetList.find((item) => Number(item.id) === datasetId);
          if (matched) setSelectedDs(matched);
        }
      };

      if (ev.type === 'lead_agent_tools') {
        setTraceSteps((prev) => {
          const toolStep = {
            node: 'lead_agent_tools',
            display_name: 'lead_agent_tools',
            status: ev.should_continue ? 'done' : 'blocked',
            elapsed_ms: null,
            audit_trace: ev.audit_trace,
            schema_status: ev.schema_status,
            selected_skills: ev.selected_skills || [],
            planned_tool_calls: ev.planned_tool_calls || [],
            executed_tool_calls: ev.executed_tool_calls || [],
            system_inferred_tool_calls: ev.system_inferred_tool_calls || [],
            progressive_disclosure: ev.progressive_disclosure,
            disclosed_tools: ev.disclosed_tools || [],
            skill_selection_reasoning_summary: ev.skill_selection_reasoning_summary,
            tool_planning_reasoning_summary: ev.tool_planning_reasoning_summary,
            policy_violations: ev.policy_violations || [],
            planner_fallback: ev.planner_fallback,
          };
          const exists = prev.find((s) => s.node === 'lead_agent_tools');
          return exists
            ? prev.map((s) => (s.node === 'lead_agent_tools' ? { ...s, ...toolStep } : s))
            : [toolStep, ...prev];
        });
      } else if (ev.type === 'route_decision') {
        syncSelectedDataset(ev);
        setTraceSteps((prev) => {
          const routeStep = {
            node: 'manifest_route',
            display_name: 'manifest_route',
            status: 'done',
            elapsed_ms: null,
            decision: ev.decision,
            dataset_id: ev.dataset_id,
            dataset_name: ev.dataset_name,
            score: ev.score,
          };
          const exists = prev.find((s) => s.node === 'manifest_route');
          return exists
            ? prev.map((s) => (s.node === 'manifest_route' ? { ...s, ...routeStep } : s))
            : [routeStep, ...prev];
        });
      } else if (ev.type === 'step' && ev.node && ev.node !== 'error') {
        setTraceSteps((prev) => {
          const exists = prev.find((s) => s.node === ev.node);
          if (exists) {
            return prev.map((s) =>
              s.node === ev.node ? { ...s, ...ev } : s,
            );
          }
          return [
            ...prev,
            {
              ...ev,
              node: ev.node,
              display_name: ev.display_name,
              status: ev.status,
              elapsed_ms: ev.elapsed_ms,
            },
          ];
        });

        if (ev.node === 'intent_recognition' && ev.status === 'done') {
          setIntent({ intent: ev.intent, entities: ev.entities });
        }
        if (
          (ev.node === 'semantic_asset_resolution_node' || ev.node === 'metric_resolution_node') &&
          ev.status === 'done'
        ) {
          setMetricResolution(ev.metric_resolution || null);
        }
        if (ev.node === 'dsl_generate' && ev.status === 'done') {
          setGenerationMode(ev.generation_mode || null);
        }
        if (ev.node === 'sql_execute' && ev.status === 'done') {
          setSqlResult({
            rows: ev.rows,
            columns: ev.columns,
            column_labels: ev.column_labels || {},
            elapsed_ms: ev.elapsed_ms,
          });
        }
      } else if (ev.type === 'final') {
        syncSelectedDataset(ev.route_decision || ev.response_metadata?.route_decision);
        setTraceMeta({
          traceId: ev.langfuse_trace_id || null,
          sessionId: ev.langfuse_session_id || null,
          messageId: ev.message_id || null,
          observability: ev.observability || null,
        });
        if (ev.sql_result) {
          setSqlResult({
            rows: ev.sql_result.rows,
            columns: ev.sql_result.columns,
            column_labels: ev.sql_result.column_labels || {},
            elapsed_ms: ev.sql_result.elapsed_ms,
          });
        }
      }
    };
    window.addEventListener('datalogue:trace', handler);
    return () => window.removeEventListener('datalogue:trace', handler);
  }, [datasetList]);

  // 切换 thread 时重置 trace 数据
  const mainThreadId = useAuiState((s) => s.threads?.mainThreadId);
  const remoteId = useAuiState((s) => {
    const id = s.threads?.mainThreadId;
    const item = s.threads?.threadItems?.find((t) => t.id === id);
    return item?.remoteId;
  });
  const [resolvedWorkbenchThreadId, setResolvedWorkbenchThreadId] = useState(null);
  const workbenchThreadId = resolveWorkbenchThreadId(routeId, remoteId, resolvedWorkbenchThreadId);

  useEffect(() => {
    const onResolvedThread = (event) => {
      const { localThreadId, threadId } = event.detail || {};
      if (!shouldAcceptResolvedWorkbenchThread({
        routeId,
        threadId,
        mainThreadId,
        localThreadId,
      })) return;
      setResolvedWorkbenchThreadId(threadId); // 新会话 final 返回 as_* 后，右侧工作台立即切到 AgentScope 真相源。
    };
    window.addEventListener('datalogue:thread-resolved', onResolvedThread);
    return () => window.removeEventListener('datalogue:thread-resolved', onResolvedThread);
  }, [mainThreadId, routeId]);

  useEffect(() => {
    setTraceSteps([]);
    setIntent(null);
    setMetricResolution(null);
    setGenerationMode(null);
    setSqlResult(null);
    setTraceMeta(null);
    setResolvedWorkbenchThreadId(null); // 切换会话时必须让 route/remoteId 重新决定 Panel source，避免串旧 as_*。
  }, [mainThreadId]);

  // 开始新 run 时清空 trace
  useEffect(() => {
    const onRunStart = () => {
      setTraceSteps([]);
      setIntent(null);
      setMetricResolution(null);
      setGenerationMode(null);
      setSqlResult(null);
      setTraceMeta(null);
    };
    window.addEventListener('datalogue:run-start', onRunStart);
    return () => window.removeEventListener('datalogue:run-start', onRunStart);
  }, []);

  // 历史消息里的“查看链路”按钮会主动打开右侧 Trace 面板。
  useEffect(() => {
    const onOpenTracePanel = () => setTraceOpen(true);
    window.addEventListener('datalogue:trace-panel-open', onOpenTracePanel);
    return () => window.removeEventListener('datalogue:trace-panel-open', onOpenTracePanel);
  }, [setTraceOpen]);

  // 监听标题自动更新事件（首条消息后端写入 title 后）— 触发 thread list 重新拉取
  const aui = useAui();
  const handleWorkbenchRetryRun = useCallback((runRequest) => {
    submitWorkbenchRetryRun(runRequest);
  }, []);
  useEffect(() => {
    const onRename = () => {
      // 后端已写入新 title；让 assistant-ui 重新拉一次 list，覆盖本地缓存
      aui.threads().reload().catch((e) => {
        console.error('[thread-list] reload failed', e);
      });
    };
    window.addEventListener('datalogue:thread-rename', onRename);
    return () => window.removeEventListener('datalogue:thread-rename', onRename);
  }, [aui]);

  const traceContextValue = useMemo(
    () => ({ traceSteps, showFollowups, agentVerbosity }),
    // traceSteps 仅供 AgentPanel 展示；AIMessage 自身从 message.content 读 reasoning
    [traceSteps, showFollowups, agentVerbosity],
  );

  return (
    <>
      <RouteThreadSync routeId={routeId} />
      <UrlSync routeId={routeId} />
      <ComposerTextSetter register={handleRegisterSetter} />

      <div className={`chat-layout${traceOpen ? ' with-panel' : ''}`}>
        <ThreadList />

        <TraceProvider value={traceContextValue}>
          <Thread
            empty={
              <WelcomeHero
                selectedDs={selectedDs}
                setSelectedDs={setSelectedDs}
                datasetList={datasetList}
                setComposerText={(t) => setComposerTextRef.current(t)}
              />
            }
            composer={
              <MyComposer
                selectedDs={selectedDs}
                setSelectedDs={setSelectedDs}
                datasetList={datasetList}
              />
            }
          />
        </TraceProvider>

        {workbenchThreadId && (
          <WorkbenchPanel threadId={workbenchThreadId} onRetryRun={handleWorkbenchRetryRun} />
        )}

        <AgentPanel
          open={traceOpen}
          onClose={() => setTraceOpen(false)}
          steps={traceSteps}
          intent={intent}
          metricResolution={metricResolution}
          generationMode={generationMode}
          sqlResult={sqlResult}
          traceMeta={traceMeta}
        />
      </div>
    </>
  );
}

/**
 * ChatPage —— /chat 与 /chat/:id 的入口组件
 */
export function ChatPage({ traceOpen, setTraceOpen, showFollowups, agentVerbosity }) {
  const { id: routeId } = useParams();

  // datasetId 共享 ref：ChatPage 维护 selectedDs，通过 ref 传给 chat adapter
  const datasetIdRef = useRef(null);
  const useChatRuntimeHook = () => useLocalRuntime(makeChatAdapter({ datasetIdRef }));

  // runtime 单例：只有 chatAdapter 通过 ref 拿到最新 datasetId
  const runtime = useRemoteThreadListRuntime({
    adapter: threadListAdapter,
    runtimeHook: useChatRuntimeHook,
    threadId: routeId,
  });

  // 由于 ChatPageInner 持有 selectedDs，我们需要把变化同步到 datasetIdRef
  // 用单独的 wrapper 把 setter 注入
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <DatasetSync datasetIdRef={datasetIdRef} />
      <ChatPageInner
        routeId={routeId}
        traceOpen={traceOpen}
        setTraceOpen={setTraceOpen}
        showFollowups={showFollowups}
        agentVerbosity={agentVerbosity}
      />
    </AssistantRuntimeProvider>
  );
}

/**
 * 把 ChatPageInner 里的 selectedDs 同步到 datasetIdRef（供 chat adapter 读取）
 * 通过 window 自定义事件桥接，避免循环依赖
 */
function DatasetSync({ datasetIdRef }) {
  useEffect(() => {
    const handler = (e) => {
      datasetIdRef.current = e.detail ?? null;
    };
    window.addEventListener('datalogue:dataset-change', handler);
    return () => window.removeEventListener('datalogue:dataset-change', handler);
  }, [datasetIdRef]);
  return null;
}
