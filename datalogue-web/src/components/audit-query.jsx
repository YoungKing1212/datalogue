import React, { useEffect, useMemo, useState } from 'react';
import { Icon } from './icons';
import { getObservabilityTrace, listObservabilityTraces } from '../api/client';

const STATUS_LABEL = {
  success: '成功',
  failed: '失败',
  unknown: '未知',
};

const STATUS_CLASS = {
  success: 'ok',
  failed: 'err',
  unknown: 'unknown',
};

function formatTime(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function formatNumber(value) {
  if (value == null) return '—';
  return Number(value).toLocaleString();
}

function statusLabel(status) {
  return STATUS_LABEL[status] || status || '未知';
}

function toJsonText(value) {
  if (value == null || value === '') return '—';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function stripThinkText(value) {
  const text = toJsonText(value);
  return text.replace(/<think>[\s\S]*?<\/think>/g, '').trim() || '—';
}

function previewText(value, limit = 360) {
  const text = stripThinkText(value).replace(/\s+/g, ' ');
  return text.length > limit ? `${text.slice(0, limit).trim()}...` : text;
}

function latencyText(ms) {
  if (ms == null) return '—';
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms}ms`;
}

function SummaryStrip({ summary }) {
  const successRate = summary?.success_rate == null
    ? '—'
    : `${Math.round(summary.success_rate * 1000) / 10}%`;
  const items = [
    { label: '查询总数', value: formatNumber(summary?.total_traces || 0), icon: 'log' },
    { label: '成功率', value: successRate, icon: 'check' },
    { label: '失败数', value: formatNumber(summary?.failed_traces || 0), icon: 'warn', tone: 'warn' },
    { label: 'Token', value: formatNumber(summary?.total_tokens || 0), icon: 'number' },
    { label: '成本', value: `$${Number(summary?.total_cost || 0).toFixed(4)}`, icon: 'chart_line' },
  ];
  return (
    <div className="audit-kpis">
      {items.map((item) => (
        <div className="audit-kpi" key={item.label}>
          <Icon name={item.icon} />
          <div>
            <span>{item.label}</span>
            <strong className={item.tone || ''}>{item.value}</strong>
          </div>
        </div>
      ))}
    </div>
  );
}

function TraceList({ items, selectedId, onSelect }) {
  if (!items.length) {
    return (
      <div className="audit-empty-list">
        <Icon name="inbox" />
        <span>暂无查询审计记录</span>
      </div>
    );
  }
  return (
    <div className="audit-list">
      {items.map((item) => {
        const status = item.status || 'unknown';
        return (
          <button
            key={`${item.trace_id}-${item.id}`}
            type="button"
            className={`audit-list-item ${selectedId === item.trace_id ? 'active' : ''}`}
            onClick={() => onSelect(item.trace_id)}
          >
            <div className="audit-list-head">
              <span className={`audit-status ${STATUS_CLASS[status] || 'unknown'}`}>
                {statusLabel(status)}
              </span>
              <code>{item.trace_id}</code>
            </div>
            <strong>{item.question || item.conversation_title || '未记录问题'}</strong>
            <p>{item.answer_preview || item.sql_preview || '暂无输出摘要'}</p>
            <div className="audit-list-meta">
              <span>{formatTime(item.created_at)}</span>
              <span>{item.entry_route || 'unknown'}</span>
              <span>{formatNumber(item.total_tokens)} tokens</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function ObservationWaterfall({ detail }) {
  const observations = detail?.observations || [];
  const fallback = detail?.fallback_steps || [];
  const rows = observations.length
    ? observations.map((item) => ({
        id: item.id,
        name: item.name,
        type: item.type || 'observation',
        latency: item.latency_ms,
        status: item.level || item.status_message || 'OK',
        model: item.model,
        output: item.output,
      }))
    : fallback.map((item) => ({
        id: item.id,
        name: item.name,
        type: 'local_step',
        latency: item.latency_ms,
        status: item.status,
      }));

  if (!rows.length) {
    return (
      <div className="audit-empty-panel">
        <Icon name="trace" />
        <span>暂无 observation，已保留 Trace ID，可继续用消息 metadata 审计。</span>
      </div>
    );
  }

  return (
    <div className="audit-waterfall">
      {rows.map((row, index) => (
        <details className="audit-observation" key={`${row.id || row.name}-${index}`}>
          <summary>
            <span className="audit-observation-index">{index + 1}</span>
            <span className="audit-observation-name">{row.name || row.id}</span>
            <span className="audit-observation-type">{row.type}</span>
            {row.model && <span className="audit-observation-model">{row.model}</span>}
            <span className="audit-observation-ms">{latencyText(row.latency)}</span>
          </summary>
          <div className="audit-observation-body">
            <div>
              <span>状态</span>
              <pre>{toJsonText({ status: row.status, model: row.model || undefined, latency_ms: row.latency })}</pre>
            </div>
            <div>
              <span>输出摘要</span>
              <pre>{previewText(row.output)}</pre>
            </div>
          </div>
        </details>
      ))}
    </div>
  );
}

function ScoresPanel({ scores }) {
  if (!scores?.length) return null;
  return (
    <div className="audit-section">
      <div className="audit-section-title">Scores</div>
      <div className="audit-scores">
        {scores.map((score) => (
          <div className="audit-score" key={score.id || score.name}>
            <span>{score.name || 'score'}</span>
            <strong>{String(score.value ?? '—')}</strong>
            {score.comment && <em>{score.comment}</em>}
          </div>
        ))}
      </div>
    </div>
  );
}

function DetailPanel({ detail, loading }) {
  if (loading) {
    return (
      <div className="audit-detail-placeholder">
        <Icon name="refresh" />
        <span>正在加载 Trace 详情...</span>
      </div>
    );
  }
  if (!detail?.found) {
    return (
      <div className="audit-detail-placeholder">
        <Icon name="search" />
        <span>选择左侧查询记录查看链路详情</span>
      </div>
    );
  }

  const item = detail.item || {};
  const trace = detail.trace || {};
  return (
    <div className="audit-detail">
      <div className="audit-detail-head">
        <div>
          <div className="audit-detail-title">{item.question || '查询链路'}</div>
          <div className="audit-detail-meta">
            <span>{item.trace_id}</span>
            <span>{formatTime(item.created_at || trace.timestamp)}</span>
            <span>{detail.source === 'langfuse' ? 'Langfuse + 本地索引' : '本地 fallback'}</span>
          </div>
        </div>
        <span className={`audit-status ${STATUS_CLASS[item.status] || 'unknown'}`}>
          {statusLabel(item.status)}
        </span>
      </div>

      {detail.langfuse_error && (
        <div className="audit-warning">
          <Icon name="warn" />
          <span>Langfuse trace 拉取失败，当前展示本地 fallback：{detail.langfuse_error}</span>
        </div>
      )}

      <div className="audit-section">
        <div className="audit-section-title">Trace Waterfall</div>
        <ObservationWaterfall detail={detail} />
      </div>

      <div className="audit-grid">
        <div className="audit-section">
          <div className="audit-section-title">输入</div>
          <pre className="audit-code">{toJsonText(item.question || '未记录问题')}</pre>
        </div>
        <div className="audit-section">
          <div className="audit-section-title">输出</div>
          <pre className="audit-code">{previewText(item.answer_preview || trace.output)}</pre>
        </div>
      </div>

      <div className="audit-section">
        <div className="audit-section-title">SQL</div>
        <pre className="audit-code">{item.sql_preview || '本次未记录 SQL'}</pre>
      </div>

      {item.error && (
        <div className="audit-error-box">
          <Icon name="warn" />
          <div>
            <strong>失败原因</strong>
            <p>{item.error}</p>
          </div>
        </div>
      )}

      <ScoresPanel scores={detail.scores} />
    </div>
  );
}

function AuditQueryScreen() {
  const initialTraceId = useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('trace_id');
  }, []);
  const [filter, setFilter] = useState('all');
  const [data, setData] = useState({ summary: {}, items: [] });
  const [selectedId, setSelectedId] = useState(initialTraceId);
  const [detail, setDetail] = useState(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoadingList(true);
    setError('');
    listObservabilityTraces({ status: filter, limit: 80 })
      .then((result) => {
        if (cancelled) return;
        setData(result || { summary: {}, items: [] });
        const firstId = result?.items?.[0]?.trace_id || null;
        if (firstId) setSelectedId((current) => current || firstId);
      })
      .catch((err) => {
        if (!cancelled) setError(`查询审计列表加载失败：${err.message}`);
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filter]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return undefined;
    }
    let cancelled = false;
    setLoadingDetail(true);
    setError('');
    getObservabilityTrace(selectedId)
      .then((result) => {
        if (cancelled) return;
        setDetail(result);
        const url = new URL(window.location.href);
        url.searchParams.set('trace_id', selectedId);
        window.history.replaceState(null, '', url.toString());
      })
      .catch((err) => {
        if (!cancelled) setError(`Trace 详情加载失败：${err.message}`);
      })
      .finally(() => {
        if (!cancelled) setLoadingDetail(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const filters = [
    { id: 'all', label: '全部' },
    { id: 'success', label: '成功' },
    { id: 'failed', label: '失败' },
  ];

  return (
    <div className="audit-page">
      <div className="audit-page-head">
        <div>
          <h1>查询审计</h1>
          <p>在 Datalogue 内查看问数链路、Langfuse observations、scores、SQL 与本地 fallback。</p>
        </div>
        <button className="btn ghost" type="button" onClick={() => window.location.reload()}>
          <Icon name="refresh" />
          刷新
        </button>
      </div>

      <SummaryStrip summary={data.summary} />
      {error && <div className="audit-warning"><Icon name="warn" /><span>{error}</span></div>}

      <div className="audit-layout">
        <aside className="audit-sidebar">
          <div className="audit-filters">
            {filters.map((item) => (
              <button
                key={item.id}
                type="button"
                className={filter === item.id ? 'active' : ''}
                onClick={() => setFilter(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {loadingList ? (
            <div className="audit-empty-list"><Icon name="refresh" /><span>正在加载...</span></div>
          ) : (
            <TraceList items={data.items || []} selectedId={selectedId} onSelect={setSelectedId} />
          )}
        </aside>

        <main className="audit-main">
          <DetailPanel detail={detail} loading={loadingDetail} />
        </main>
      </div>
    </div>
  );
}

export { AuditQueryScreen };
