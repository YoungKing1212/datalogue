import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Icon } from './icons';
import { LineChart, Donut, HeatStrip, GroupedBar } from './charts';
import { streamChat, listDatasets, listDatasources, getConversation } from '../api/client';
import { AgentPanel } from './agent-panel';

// ── 工具函数 ────────────────────────────────────────

function cleanAnswer(text) {
  if (!text) return '';
  return text.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();
}

function renderAnswer(text) {
  if (!text) return null;
  const lines = text.split('\n');
  const elements = [];
  let key = 0;
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 跳过空的 thought 残留
    if (line.trim() === '') { i++; continue; }

    // 代码块
    if (line.startsWith('```')) {
      const lang = line.slice(3).trim() || 'code';
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      elements.push(
        <pre key={key++} className="code-block" data-lang={lang}>
          <code>{codeLines.join('\n')}</code>
        </pre>
      );
      i++; // 跳过结束的 ```
      continue;
    }

    // 标题 ## xxx
    if (line.startsWith('## ')) {
      elements.push(<h3 key={key++} className="msg-h2">{renderInlineText(line.slice(3), key++)}</h3>);
      i++;
      continue;
    }

    // 标题 # xxx
    if (line.startsWith('# ')) {
      elements.push(<h2 key={key++} className="msg-h1">{renderInlineText(line.slice(2), key++)}</h2>);
      i++;
      continue;
    }

    // 列表项 - xxx 或 * xxx
    if (line.match(/^[-*]\s/)) {
      const items = [];
      while (i < lines.length && lines[i].match(/^[-*]\s/)) {
        items.push(<li key={key++}>{renderInlineText(lines[i].replace(/^[-*]\s/, ''), key++)}</li>);
        i++;
      }
      elements.push(<ul key={key++} className="msg-ul">{items}</ul>);
      continue;
    }

    // 序号列表 1. xxx
    if (line.match(/^\d+\.\s/)) {
      const items = [];
      while (i < lines.length && lines[i].match(/^\d+\.\s/)) {
        items.push(<li key={key++}>{renderInlineText(lines[i].replace(/^\d+\.\s/, ''), key++)}</li>);
        i++;
      }
      elements.push(<ol key={key++} className="msg-ol">{items}</ol>);
      continue;
    }

    // 普通段落
    const paraLines = [];
    while (i < lines.length && lines[i].trim() !== '' && !lines[i].startsWith('#') && !lines[i].startsWith('```') && !lines[i].match(/^[-*]\s/) && !lines[i].match(/^\d+\.\s/)) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length > 0) {
      elements.push(<p key={key++} className="msg-p">{renderInlineText(paraLines.join(' '), key++)}</p>);
    }
  }

  return elements.length > 0 ? elements : renderInlineText(text, 0);
}

function renderInlineText(text, baseKey) {
  if (!text) return null;
  const parts = [];
  let remaining = text;
  let key = baseKey;

  const boldRegex = /\*\*(.*?)\*\*/g;
  let lastIndex = 0;
  let match;

  while ((match = boldRegex.exec(remaining)) !== null) {
    if (match.index > lastIndex) parts.push(remaining.slice(lastIndex, match.index));
    parts.push(<strong key={key++}>{match[1]}</strong>);
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < remaining.length) parts.push(remaining.slice(lastIndex));
  return parts.length > 0 ? <span key={key}>{parts}</span> : <span key={key}>{remaining}</span>;
}

// ── Step 节点名称映射 ──────────────────────────────

const NODE_STEP_NAMES = {
  intent_recognition: '意图识别',
  schema_recall: 'Schema 召回',
  dsl_generate: 'DSL 生成',
  dsl_validate: 'DSL 校验',
  dsl_compiler: 'SQL 编译',
  sql_execute: 'SQL 执行',
  report_generator: '报告生成',
};

const NODE_ICONS = {
  intent_recognition: 'brain',
  schema_recall: 'database',
  dsl_generate: 'code',
  dsl_validate: 'check',
  dsl_compiler: 'compile',
  sql_execute: 'play',
  report_generator: 'chart_bar',
};

// ── StepCard 组件 ──────────────────────────────

function StepCard({ node, display_name, status }) {
  const icon = NODE_ICONS[node] || 'circle';
  const label = display_name || NODE_STEP_NAMES[node] || node;

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
    </div>
  );
}

// ── AI 消息气泡 ──────────────────────────────

function AIMessage({ msg, onCopy }) {
  const [showActions, setShowActions] = useState(false);

  return (
    <div className="msg-row msg-ai">
      <div className="ai-head">
        <div className="ai-mark" />
        <span className="name">数语</span>
        <span className="stage">
          {msg.status === 'streaming' ? (
            <><span className="pulse" />正在生成…</>
          ) : (
            <><Icon name="check" style={{ width: 11, height: 11, color: 'var(--pos)' }} />已生成</>
          )}
        </span>
      </div>

      <div className="ans-body">{renderAnswer(msg.content)}</div>

      {/* 图表 — 有 chartType 时渲染 */}
      {msg.chartType && (
        <div className="chart-card">
          <div className="chart-head">
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{msg.chartTitle || '数据图表'}</span>
                <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 4, background: 'var(--bg-2)', color: 'var(--text-3)' }}>
                  <Icon name={msg.chartType === 'bar' ? 'chart_bar' : msg.chartType === 'line' ? 'chart_line' : 'chart_pie'} style={{ width: 11, height: 11 }} />
                  {msg.chartType} · 自动推荐
                </span>
              </div>
              {msg.chartSubtitle && <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{msg.chartSubtitle}</div>}
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button className="icon-btn"><Icon name="chart_bar" /></button>
              <button className="icon-btn"><Icon name="share" /></button>
              <button className="icon-btn"><Icon name="expand" /></button>
              <button className="icon-btn"><Icon name="more" /></button>
            </div>
          </div>
          {msg.chartType === 'bar' && <GroupedBar data={msg.chartData} h={200} w={640} />}
          {msg.chartType === 'line' && <LineChart data={msg.chartData} h={200} w={640} />}
          {msg.chartType === 'pie' && <Donut data={msg.chartData} h={200} w={640} />}
        </div>
      )}

      {/* SQL 可折叠 */}
      {msg.sql && (
        <div className={'collapse ' + (msg.sqlOpen ? 'open' : '')}>
          <div className="collapse-head" onClick={() => msg.setSqlOpen?.(!msg.sqlOpen)}>
            <Icon name="sql" />生成的 SQL
          </div>
          {msg.sqlOpen && <div className="collapse-body"><pre className="sql">{msg.sql}</pre></div>}
        </div>
      )}

      {/* 引用来源 */}
      {msg.citations && msg.citations.length > 0 && (
        <div className="citations">
          <span className="citations-label">数据来源：</span>
          {msg.citations.map((c, i) => (
            <span key={i} className="citation-tag">{c}</span>
          ))}
        </div>
      )}

      {/* 操作栏 — hover 显示 */}
      <div className={`msg-actions ${showActions ? 'visible' : ''}`}
           onMouseEnter={() => setShowActions(true)}
           onMouseLeave={() => setShowActions(false)}>
        <button className="action-btn" title="复制回答" onClick={() => onCopy(msg.content)}>
          <Icon name="copy" />
        </button>
        <button className="action-btn" title="点赞">
          <Icon name="thumbs_up" />
        </button>
        <button className="action-btn" title="点踩">
          <Icon name="thumbs_down" />
        </button>
        <button className="action-btn" title="重新生成">
          <Icon name="refresh" />
        </button>
      </div>
    </div>
  );
}

// ── 用户消息气泡 ──────────────────────────────

function UserMessage({ msg }) {
  return <div className="bubble">{msg.content}</div>;
}

// ── ChatScreen 主组件 ──────────────────────────────

function ChatScreen({ traceOpen, setTraceOpen, empty, density }) {
  const [composer, setComposer] = useState('');
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [streamSql, setStreamSql] = useState('');
  const [leadAgentSubs, setLeadAgentSubs] = useState([]);
  const [traceSteps, setTraceSteps] = useState([]);
  const [isComplex, setIsComplex] = useState(false);
  const [dsList, setDsList] = useState([]);
  const [datasetList, setDatasetList] = useState([]);
  const [selectedDs, setSelectedDs] = useState(null);
  const [showDsDropdown, setShowDsDropdown] = useState(false);
  const abortRef = useRef(null);
  const scrollRef = useRef(null);
  // useRef 镜像最新 traceSteps，解决 onDone 闭包里读到旧值 [] 的问题
  const traceStepsRef = useRef([]);

  // 会话 ID（来自路由参数 /chat/:id）
  const { id: convId } = useParams();

  // Token 流 state — 逐字追加
  const [streamingAnswer, setStreamingAnswer] = useState('');
  const streamingAnswerRef = useRef('');  // onDone 闭包里读最新值

  // Agent 面板数据
  const [intent,    setIntent]    = useState(null);
  const [sqlResult, setSqlResult] = useState(null);

  // 滚动到底部
  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingAnswer]);

  useEffect(() => {
    listDatasources().then(setDsList).catch(console.error);
    listDatasets().then(setDatasetList).catch(console.error);
  }, []);

  // 路由参数有 convId 时，加载该对话的历史消息
  useEffect(() => {
    if (!convId) return;
    getConversation(convId)
      .then(data => {
        const msgs = (data.messages || []).map(m => ({
          role:    m.role,
          content: m.content,
          sql:     (m.sql_list && m.sql_list[0]) ?? null,
          status:  'done',
        }));
        setMessages(msgs);
      })
      .catch(err => console.error('加载历史会话失败:', err));
  }, [convId]);

  // 快捷问题预设
  const quickChips = [
    { label: '周度GMV走势', q: '本周各品类GMV走势' },
    { label: '归因分析', q: '上周整体销售为什么下降了12%？' },
    { label: 'ROI对比', q: '近30天各渠道ROI对比' },
    { label: '新客分析', q: '本周新客转化率分析' },
  ];

  const handleSend = () => {
    const question = composer.trim();
    if (!question || isStreaming) return;

    // 乐观 UI：立即显示用户消息
    setMessages(prev => [...prev, { role: 'user', content: question }]);
    setComposer('');
    setIsStreaming(true);
    setStreamSql('');
    setTraceSteps([]);
    traceStepsRef.current = []; // 重置 ref 与 state 保持同步
    setLeadAgentSubs([]);
    setIsComplex(false);
    setIntent(null);
    setSqlResult(null);
    setStreamingAnswer('');
    streamingAnswerRef.current = '';

    if (abortRef.current) abortRef.current.abort();
    const controller = streamChat(
      { question, dataset_id: selectedDs?.dataset_id || selectedDs?.id },
      {
        onToken: (token) => {
          streamingAnswerRef.current += token;
          setStreamingAnswer(prev => prev + token);
        },
        onEvent: (data) => {
          if (data.node && data.node !== 'error') {
            const cur = traceStepsRef.current;
            const exists = cur.find(s => s.node === data.node);
            const next = exists
              ? cur.map(s => s.node === data.node ? { ...s, ...data } : s)
              : [...cur, { node: data.node, display_name: data.display_name, status: data.status, elapsed_ms: data.elapsed_ms }];
            traceStepsRef.current = next;
            setTraceSteps(next);
          }
          if (data.node === 'intent_recognition' && data.status === 'done') {
            setIntent({ intent: data.intent, entities: data.entities });
          }
          if (data.node === 'dsl_compiler' && data.status === 'done') {
            setStreamSql(data.sql || '');
          }
          if (data.node === 'sql_execute' && data.status === 'done') {
            setSqlResult({ rows: data.rows, columns: data.columns, elapsed_ms: data.elapsed_ms });
          }
        },
        onError: (err) => {
          console.error('[SSE error]', err);
          streamingAnswerRef.current = '连接出错，请稍后重试。';
          setStreamingAnswer('连接出错，请稍后重试。');
          setIsStreaming(false);
        },
        onDone: (finalData) => {
          const answer = cleanAnswer(streamingAnswerRef.current || finalData?.answer || '已生成回答');
          streamingAnswerRef.current = '';
          setIsStreaming(false);
          setStreamingAnswer('');
          setMessages(prev => [...prev, {
            role:    'assistant',
            content: answer,
            status:  'done',
            sql:     finalData?.sql ?? streamSql,
            sqlOpen: false,
            setSqlOpen: (v) => setMessages(ms =>
              ms.map((m, i) => i === ms.length - 1 ? { ...m, sqlOpen: v } : m)
            ),
          }]);
          // intent/sqlResult/traceSteps 保留，直到用户关闭面板
          setStreamSql('');
          traceStepsRef.current = [];
          window.dispatchEvent(new Event('new-conversation'));
        },
      }
    );
    abortRef.current = controller;
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text).catch(console.error);
  };

  // 外部传 empty prop 或消息列表为空时都显示欢迎屏
  if (empty || messages.length === 0) {
    return <ChatEmpty onSend={handleSend} composer={composer} setComposer={setComposer} isStreaming={isStreaming} quickChips={quickChips} />;
  }

  return (
    <div className={`chat-layout${traceOpen ? ' with-panel' : ''}`}>
      <div className="chat-main">
        {/* 消息区域 */}
        <div className="chat-scroll" ref={scrollRef}>
          <div className="chat-inner">
            {messages.map((msg, idx) => (
              msg.role === 'user' ? (
                <UserMessage key={idx} msg={msg} />
              ) : (
                <AIMessage key={idx} msg={msg} onCopy={handleCopy} />
              )
            ))}

            {/* 流式气泡：token 到达时打字效果 */}
            {isStreaming && streamingAnswer && (
              <div className="msg-row msg-ai">
                <div className="ai-head">
                  <div className="ai-mark" />
                  <span className="name">数语</span>
                  <span className="stage"><span className="pulse" />正在生成…</span>
                </div>
                <div className="ans-body streaming-text">
                  {renderAnswer(streamingAnswer)}
                  <span className="cursor-blink">▋</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 快捷词条 */}
        {!isStreaming && (
          <div className="quick-chips">
            {quickChips.map((chip, i) => (
              <button key={i} className="quick-chip" onClick={() => setComposer(chip.q)}>
                <Icon name="bolt" style={{ width: 11, height: 11 }} />
                {chip.label}
              </button>
            ))}
          </div>
        )}

        {/* 输入区 */}
        <div className="composer-wrap">
          <div className="composer">
            <div className="composer-inner">
              <textarea
                className="composer-input"
                rows={1}
                placeholder={isStreaming ? '数语正在思考中…' : '问个数，或者点击上面的快捷词'}
                value={composer}
                onChange={(e) => setComposer(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isStreaming}
              />
              <div className="composer-toolbar">
                <div style={{ position: 'relative' }}>
                  <button className="tool-chip" onClick={() => setShowDsDropdown(v => !v)}>
                    <Icon name="database" />
                    {selectedDs ? selectedDs.name : '全部数据源'}
                  </button>
                  {showDsDropdown && (
                    <div className="ds-dropdown">
                      <div className="ds-dropdown-head">选择数据源</div>
                      <div className="ds-dropdown-item" onClick={() => { setSelectedDs(null); setShowDsDropdown(false); }}>全部数据源</div>
                      {dsList.map(ds => (
                        <div key={ds.id} className={`ds-dropdown-item ${selectedDs?.id === ds.id ? 'active' : ''}`}
                             onClick={() => { setSelectedDs(ds); setShowDsDropdown(false); }}>
                          {ds.name}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <button className="tool-chip"><Icon name="calendar" />近7天</button>
                <button className="tool-chip"><Icon name="brain" />深度归因</button>
                <div className="spacer" />
                <button className="send-btn" onClick={handleSend} disabled={isStreaming || !composer.trim()}>
                  <Icon name="send" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <AgentPanel
        open={traceOpen}
        onClose={() => setTraceOpen(false)}
        steps={traceSteps}
        intent={intent}
        sql={streamSql}
        sqlResult={sqlResult}
      />
    </div>
  );
}

// ── Empty state ──────────────────────────────

function ChatEmpty({ onSend, composer, setComposer, isStreaming, quickChips = [] }) {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend?.(); }
  };

  return (
    <div className="chat-main chat-empty">
      <div className="empty-hero">
        <div className="ai-mark empty-mark" />
        <h1 className="empty-title">问点什么？</h1>
        <p className="empty-sub">数语会自动选取数据集、生成 SQL、绘制图表，并解释结果。</p>

        <div className="ask-hero">
          <textarea
            className="ask-input"
            rows={2}
            placeholder="例如：上周华东区销售为什么下降？"
            value={composer}
            onChange={(e) => setComposer(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
          />
          <div className="toolbar">
            <button className="tool-chip"><Icon name="database" />全部数据集</button>
            <button className="tool-chip"><Icon name="calendar" />近7天</button>
            <button className="tool-chip"><Icon name="brain" />深度归因</button>
            <button className="send-btn" onClick={onSend} disabled={isStreaming || !composer.trim()}>
              <Icon name="send" />
            </button>
          </div>
        </div>

        {/* 快捷问题 */}
        <div className="quick-section">
          <div className="quick-label">试试这些</div>
          <div className="quick-list">
            {quickChips.map((s, i) => (
              <button key={i} className="quick-item" onClick={() => setComposer(s.q)} disabled={isStreaming}>
                <div className="quick-item-icon">
                  <Icon name="lightbulb" style={{ width: 14, height: 14 }} />
                </div>
                <div>
                  <div className="quick-q">{s.q}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export { ChatScreen, ChatEmpty };