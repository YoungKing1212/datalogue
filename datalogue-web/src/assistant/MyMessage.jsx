// MyMessage — assistant-ui Message 渲染组件
// 使用 MessagePrimitive.Parts + ChainOfThought 接管 reasoning 步骤渲染
// 正文走 MessagePrimitive.Text（含 smooth 流式动画）
// SQL/查询结果/图表/复制按钮从 metadata.custom 取，由 chat-adapter.js 在 final 事件时写入

import React, { useState, useMemo } from 'react';
import {
  useAuiState,
  useAui,
  MessagePrimitive,
  ChainOfThoughtPrimitive,
} from '@assistant-ui/react';
import { Icon } from '../components/icons';
import { LineChart, Donut, GroupedBar } from '../components/charts';
import MessageContent from '../components/message-content';

// ── Step 节点名称映射（agent panel 兼容） ──
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

/**
 * StepCard — 单个流式步骤的视觉卡片（供 AgentPanel 复用）
 */
export function StepCard({ node, display_name, status, elapsed_ms }) {
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
      {elapsed_ms != null && <span className="step-ms">{elapsed_ms}ms</span>}
    </div>
  );
}

/**
 * 单条 reasoning 节点 — ChainOfThoughtPrimitive.Parts 内的 Reasoning 组件
 * 接收 ReasoningMessagePartComponent props（part + status）
 */
function ReasoningPart({ text }) {
  // part 形如 { type: 'reasoning', text: '意图识别：销售归因...', parentId: 'intent_recognition' }
  // 把 parentId 当 step 节点名（chat-adapter.js 用 parentId 写 ev.node）
  const node = useAuiState((s) => s.part?.parentId);
  const label = NODE_STEP_NAMES[node] || '推理步骤';
  const icon = NODE_ICONS[node] || 'brain';
  return (
    <div className="cot-step">
      <div className="cot-step-icon">
        <Icon name={icon} style={{ width: 12, height: 12 }} />
      </div>
      <div className="cot-step-body">
        <div className="cot-step-label">{label}</div>
        <div className="cot-step-text">{text}</div>
      </div>
    </div>
  );
}

/**
 * ChainOfThought 包装组件 — 用 ChainOfThoughtPrimitive 渲染
 * MessagePrimitive.Parts components={{ ChainOfThought: ... }} 接收 ComponentType
 *
 * Root 的 data-state 反映 collapsed 状态（assistant-ui Root 本身是 plain div，
 * 需要我们手动接 collapsed scope 才能在 CSS 里控制箭头旋转）
 */
function ChainOfThought({ children }) {
  const collapsed = useAuiState((s) => s.chainOfThought?.collapsed ?? true);
  return (
    <div className="cot">
      <ChainOfThoughtPrimitive.Root
        className="cot-root"
        data-state={collapsed ? 'collapsed' : 'expanded'}
      >
        <ChainOfThoughtPrimitive.AccordionTrigger asChild>
          <button type="button" className="cot-trigger">
            <span className="cot-trigger-inner">
              <Icon name="brain" style={{ width: 13, height: 13 }} />
              <span>思考过程</span>
              <span className="cot-trigger-arrow">⌃</span>
            </span>
          </button>
        </ChainOfThoughtPrimitive.AccordionTrigger>
        <ChainOfThoughtPrimitive.Parts
          components={{ Reasoning: ReasoningPart }}
        />
      </ChainOfThoughtPrimitive.Root>
    </div>
  );
}

/**
 * 自定义 Text 组件 — 用 MessagePartPrimitive.Text（支持 smooth 流式动画）
 * 把 part 的 text 转给 MessageContent 渲染（含 <think> 折叠、markdown）
 */
function MessageTextPart() {
  const text = useAuiState((s) => s.part?.text);
  const status = useAuiState((s) => s.part?.status);
  const isStreaming = status?.type === 'running';
  if (!text) return null;
  return <MessageContent text={text} streaming={isStreaming} />;
}

/**
 * AIMessage — 助理消息气泡
 * - 用 MessagePrimitive.Parts 把 reasoning / text 分开渲染
 * - ChainOfThought 默认折叠，AccordionTrigger 控制展开
 * - 正文 markdown 走 MessageContent
 * - SQL/查询结果/图表/复制按钮从 metadata.custom 取
 */
export function AIMessage({ showSql = true }) {
  const api = useAui();
  const message = useAuiState((s) => s.message);
  const [sqlOpen, setSqlOpen] = useState(false);
  const [showActions, setShowActions] = useState(false);

  const isStreaming = message?.status?.type === 'running';
  const custom = message?.metadata?.custom || {};
  const sql = custom.sql || null;
  const sqlResult = custom.sqlResult || null;
  const chartType = custom.chartType || null;
  const chartTitle = custom.chartTitle || null;
  const chartSubtitle = custom.chartSubtitle || null;
  const chartData = custom.chartData || null;
  const citations = custom.citations || null;

  const handleCopy = () => {
    const text = (message?.content || [])
      .filter((p) => p.type === 'text')
      .map((p) => p.text)
      .join('');
    navigator.clipboard.writeText(text).catch(console.error);
  };

  const handleRegenerate = () => {
    api.message().reload();
  };

  return (
    <div
      className="msg-row msg-ai"
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      <div className="ai-head">
        <div className="ai-mark" />
        <span className="name">数语</span>
        <span className="stage">
          {isStreaming ? (
            <>
              <span className="pulse" />
              正在生成…
            </>
          ) : (
            <>
              <Icon name="check" style={{ width: 11, height: 11, color: 'var(--pos)' }} />
              已生成
            </>
          )}
        </span>
      </div>

      {/* 内容区 — reasoning 由 ChainOfThought 接管，text 走 markdown */}
      <MessagePrimitive.Parts
        components={{
          ChainOfThought,
          Text: MessageTextPart,
        }}
      />

      {/* SQL 执行结果表格 */}
      {sqlResult && sqlResult.rows && sqlResult.rows.length > 0 && (
        <div className="sql-result-card">
          <div className="sql-result-head">
            <Icon name="table" style={{ width: 13, height: 13 }} />
            <span>查询结果</span>
            <span className="sql-result-count">
              {sqlResult.rowCount ?? sqlResult.row_count ?? sqlResult.rows.length} 行
            </span>
          </div>
          <div className="sql-result-table-wrap">
            <table className="sql-result-table">
              <thead>
                <tr>
                  {(sqlResult.columns || []).map((col, i) => (
                    <th key={i}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sqlResult.rows.map((row, i) => (
                  <tr key={i}>
                    {(sqlResult.columns || []).map((col, j) => (
                      <td key={j}>{row[col] ?? ''}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 图表 — 有 chartType 时渲染 */}
      {chartType && (
        <div className="chart-card">
          <div className="chart-head">
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{chartTitle || '数据图表'}</span>
                <span
                  style={{
                    fontSize: 11,
                    padding: '2px 7px',
                    borderRadius: 4,
                    background: 'var(--bg-2)',
                    color: 'var(--text-3)',
                  }}
                >
                  <Icon
                    name={
                      chartType === 'bar'
                        ? 'chart_bar'
                        : chartType === 'line'
                          ? 'chart_line'
                          : 'chart_pie'
                    }
                    style={{ width: 11, height: 11 }}
                  />
                  {chartType} · 自动推荐
                </span>
              </div>
              {chartSubtitle && (
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                  {chartSubtitle}
                </div>
              )}
            </div>
          </div>
          {chartType === 'bar' && <GroupedBar data={chartData} h={200} w={640} />}
          {chartType === 'line' && <LineChart data={chartData} h={200} w={640} />}
          {chartType === 'pie' && <Donut data={chartData} h={200} w={640} />}
        </div>
      )}

      {/* SQL 可折叠 */}
      {showSql && sql && (
        <div className={'collapse ' + (sqlOpen ? 'open' : '')}>
          <div className="collapse-head" onClick={() => setSqlOpen((v) => !v)}>
            <Icon name="sql" />
            生成的 SQL
          </div>
          {sqlOpen && (
            <div className="collapse-body">
              <pre className="sql">{sql}</pre>
            </div>
          )}
        </div>
      )}

      {/* 引用来源 */}
      {citations && citations.length > 0 && (
        <div className="citations">
          <span className="citations-label">数据来源：</span>
          {citations.map((c, i) => (
            <span key={i} className="citation-tag">
              {c}
            </span>
          ))}
        </div>
      )}

      {/* 操作栏 — hover 显示 */}
      {!isStreaming && (
        <div className={`msg-actions ${showActions ? 'visible' : ''}`}>
          <button className="action-btn" title="复制回答" onClick={handleCopy}>
            <Icon name="copy" />
          </button>
          <button className="action-btn" title="点赞">
            <Icon name="thumbs_up" />
          </button>
          <button className="action-btn" title="点踩">
            <Icon name="thumbs_down" />
          </button>
          <button className="action-btn" title="重新生成" onClick={handleRegenerate}>
            <Icon name="refresh" />
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * UserMessage — 用户消息气泡
 */
export function UserMessage() {
  const content = useAuiState((s) => s.message?.content);
  const text = useMemo(
    () =>
      (content || [])
        .filter((p) => p.type === 'text')
        .map((p) => p.text || '')
        .join(''),
    [content],
  );
  return (
    <div className="msg-row msg-user">
      <div className="bubble">{text}</div>
    </div>
  );
}
