// ChatPage — Chat 页面顶层组件
// 负责：
// 1. 构造 assistant-ui runtime（useRemoteThreadListRuntime + useLocalRuntime）
// 2. URL ↔ mainThreadId 双向同步（/chat ↔ /chat/:id）
// 3. 监听 SSE 'datalogue:trace' 事件，向 AgentPanel 推数据
// 4. 维护 datasetList / selectedDs 顶层状态（保持跨 thread 不变）

import React, { useEffect, useMemo, useRef, useState } from 'react';
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
import { listDatasets } from '../api/client';

// 单例 adapter（避免每次渲染重建）
const threadListAdapter = new DatalogueThreadListAdapter();

/**
 * 在 runtime context 内部：URL 反向同步
 * 当 mainThread 切换时，把 URL 推到 /chat/:remoteId
 */
function UrlSync({ routeId }) {
  const navigate = useNavigate();
  const mainThreadId = useAuiState((s) => s.threads?.mainThreadId);
  const remoteId = useAuiState((s) => {
    const id = s.threads?.mainThreadId;
    const item = s.threads?.threadItems?.find((t) => t.id === id);
    return item?.remoteId;
  });

  useEffect(() => {
    if (remoteId && String(remoteId) !== String(routeId)) {
      navigate(`/chat/${remoteId}`, { replace: true });
    } else if (!remoteId && routeId) {
      // 当前 thread 没有 remoteId（new thread 未初始化）且路由有 id，保持 URL
      // 不处理：等用户发消息触发 initialize 后再同步
    }
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
  return null;
}

/**
 * ChatPage 内部主体（在 AssistantRuntimeProvider 之内）
 */
function ChatPageInner({ routeId, traceOpen, setTraceOpen, showFollowups, showSql, agentVerbosity }) {
  const [selectedDs, setSelectedDs] = useState(null);
  const [datasetList, setDatasetList] = useState([]);

  // AgentPanel 数据 —— 来自 window 'datalogue:trace' 事件
  const [traceSteps, setTraceSteps] = useState([]);
  const [intent, setIntent] = useState(null);
  const [metricResolution, setMetricResolution] = useState(null);
  const [generationMode, setGenerationMode] = useState(null);
  const [sqlText, setSqlText] = useState('');
  const [sqlResult, setSqlResult] = useState(null);

  // composer 文本设置回调（供 WelcomeHero 快捷词条调用）
  const setComposerTextRef = useRef(() => {});
  const handleRegisterSetter = (fn) => {
    setComposerTextRef.current = fn();
  };

  // 拉取 dataset 列表
  useEffect(() => {
    listDatasets().then(setDatasetList).catch(console.error);
  }, []);

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

      if (ev.type === 'step' && ev.node && ev.node !== 'error') {
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
        if (ev.node === 'metric_resolution' && ev.status === 'done') {
          setMetricResolution(ev.metric_resolution || null);
        }
        if (ev.node === 'dsl_generate' && ev.status === 'done') {
          setGenerationMode(ev.generation_mode || null);
        }
        if (ev.node === 'dsl_compiler' && ev.status === 'done') {
          setSqlText(ev.sql || '');
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
        if (ev.sql) setSqlText(ev.sql);
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
  }, []);

  // 切换 thread 时重置 trace 数据
  const mainThreadId = useAuiState((s) => s.threads?.mainThreadId);
  useEffect(() => {
    setTraceSteps([]);
    setIntent(null);
    setMetricResolution(null);
    setGenerationMode(null);
    setSqlText('');
    setSqlResult(null);
  }, [mainThreadId]);

  // 开始新 run 时清空 trace
  useEffect(() => {
    const onRunStart = () => {
      setTraceSteps([]);
      setIntent(null);
      setMetricResolution(null);
      setGenerationMode(null);
      setSqlText('');
      setSqlResult(null);
    };
    window.addEventListener('datalogue:run-start', onRunStart);
    return () => window.removeEventListener('datalogue:run-start', onRunStart);
  }, []);

  // 监听标题自动更新事件（首条消息后端写入 title 后）— 触发 thread list 重新拉取
  const aui = useAui();
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
    () => ({ traceSteps, showSql, showFollowups, agentVerbosity }),
    // traceSteps 仅供 AgentPanel 展示；AIMessage 自身从 message.content 读 reasoning
    [traceSteps, showSql, showFollowups, agentVerbosity],
  );

  return (
    <>
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

        <AgentPanel
          open={traceOpen}
          onClose={() => setTraceOpen(false)}
          steps={traceSteps}
          intent={intent}
          metricResolution={metricResolution}
          generationMode={generationMode}
          sql={sqlText}
          sqlResult={sqlResult}
        />
      </div>
    </>
  );
}

/**
 * ChatPage —— /chat 与 /chat/:id 的入口组件
 */
export function ChatPage({ traceOpen, setTraceOpen, showFollowups, showSql, agentVerbosity }) {
  const { id: routeId } = useParams();

  // datasetId 共享 ref：ChatPage 维护 selectedDs，通过 ref 传给 chat adapter
  const datasetIdRef = useRef(null);

  // runtime 单例：只有 chatAdapter 通过 ref 拿到最新 datasetId
  const runtime = useRemoteThreadListRuntime({
    adapter: threadListAdapter,
    runtimeHook: () => useLocalRuntime(makeChatAdapter({ datasetIdRef })),
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
        showSql={showSql}
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
