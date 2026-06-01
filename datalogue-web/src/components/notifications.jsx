import React, { useState, useEffect } from 'react';
import { Icon } from './icons';

// NotificationsPopover — bell-triggered dropdown in top bar.
// Anomaly-first: spikes/dips/threshold-breaches detected by the system,
// mixed with collaboration and system notices.

const NOTIFICATIONS = [
  {
    id: 'n1',
    kind: 'anomaly',
    severity: 'critical',
    when: '12 分钟前',
    title: '华东区 · 女装 GMV 急剧下滑',
    metric: 'GMV',
    dim: '华东 · 女装',
    current: '¥182k',
    expected: '¥320k',
    delta: -43.2,
    rule: '日同环比同时下跌 > 30%',
    spark: [42, 44, 41, 45, 43, 46, 42, 18],
    action: '查看归因',
  },
  {
    id: 'n2',
    kind: 'anomaly',
    severity: 'critical',
    when: '38 分钟前',
    title: 'API 调用错误率突增',
    metric: '5xx 错误率',
    dim: '/v1/sales/weekly-attribution',
    current: '4.2%',
    expected: '< 0.1%',
    delta: 4100,
    rule: '错误率 > SLO 上限',
    spark: [0.1, 0.1, 0.08, 0.1, 0.12, 0.4, 2.1, 4.2],
    action: '查看日志',
  },
  {
    id: 'n3',
    kind: 'anomaly',
    severity: 'warn',
    when: '1 小时前',
    title: '抖音渠道 ROI 跌破阈值',
    metric: 'ROI',
    dim: '抖音',
    current: '0.82',
    expected: '> 1.5',
    delta: -45.3,
    rule: 'ROI 连续 3 天 < 阈值',
    spark: [1.8, 1.6, 1.4, 1.5, 1.2, 1.0, 0.9, 0.82],
    action: '深度归因',
  },
  {
    id: 'n4',
    kind: 'anomaly',
    severity: 'warn',
    when: '2 小时前',
    title: '高价值用户复购率回升',
    metric: '复购率',
    dim: 'VIP 用户',
    current: '38.4%',
    expected: '31%',
    delta: 23.9,
    rule: '正向异常 · 偏离均值 > 20%',
    spark: [32, 30, 31, 29, 32, 34, 36, 38.4],
    action: '查看原因',
    positive: true,
  },
  {
    id: 'n5',
    kind: 'anomaly',
    severity: 'info',
    when: '今天 09:00',
    title: 'SKU 缺货率周报已生成',
    metric: '缺货率',
    dim: '华东仓',
    current: '2.1%',
    expected: '< 2%',
    delta: 5.0,
    rule: '周度阈值轻微越界',
    spark: [1.4, 1.6, 1.5, 1.7, 1.8, 1.9, 2.0, 2.1],
    action: '查看周报',
  },
  {
    id: 'n6',
    kind: 'collab',
    severity: 'info',
    when: '1 小时前',
    title: '王磊 在「上周华东销售归因」中 @ 了你',
    preview: '"@Yan Lin 这个归因结论可以发到周会吗？"',
    avatar: '王',
  },
  {
    id: 'n7',
    kind: 'system',
    severity: 'info',
    when: '今天',
    title: '接口 /v1/sales/weekly-gmv 月配额已用 80%',
    preview: '本月 400k / 500k · 预计 5月29日 触顶',
  },
];

function bellCount() {
  return NOTIFICATIONS.filter(n => n.severity === 'critical' || n.severity === 'warn').length;
}

function NotificationsPopover({ open, onClose }) {
  const [tab, setTab] = useState('all');
  const [muted, setMuted] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = e => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  if (!open) return null;

  const tabs = [
    { id: 'all',     label: '全部',     count: NOTIFICATIONS.length },
    { id: 'anomaly', label: '数据异常', count: NOTIFICATIONS.filter(n => n.kind === 'anomaly').length, dot: true },
    { id: 'collab',  label: '协作',     count: NOTIFICATIONS.filter(n => n.kind === 'collab').length },
    { id: 'system',  label: '系统',     count: NOTIFICATIONS.filter(n => n.kind === 'system').length },
  ];

  const items = NOTIFICATIONS.filter(n => tab === 'all' ? true : n.kind === tab);

  return (
    <>
      <div className="np-shade" onClick={onClose} />
      <div className="np-popover" onClick={e => e.stopPropagation()}>
        <div className="np-head">
          <div className="np-head-title">
            消息
            <span className="np-head-count">{bellCount()} 个待处理</span>
          </div>
          <div className="np-head-actions">
            <button className="np-link">全部标为已读</button>
            <button className="icon-btn" title="设置"><Icon name="cog" /></button>
          </div>
        </div>

        <div className="np-tabs">
          {tabs.map(t => (
            <button key={t.id} className={'np-tab ' + (tab === t.id ? 'active' : '')} onClick={() => setTab(t.id)}>
              {t.label}
              <span className="count">{t.count}</span>
              {t.dot && t.id !== tab && <span className="np-tab-dot" />}
            </button>
          ))}
        </div>

        <div className="np-list">
          {items.map(n => {
            if (n.kind === 'anomaly') return <AnomalyCard key={n.id} n={n} />;
            if (n.kind === 'collab')  return <CollabRow key={n.id} n={n} />;
            return <SystemRow key={n.id} n={n} />;
          })}
        </div>

        <div className="np-foot">
          <label className="np-foot-mute">
            <input type="checkbox" checked={muted} onChange={e => setMuted(e.target.checked)} />
            <span>静音非关键告警 1 小时</span>
          </label>
          <button className="np-link">查看全部 →</button>
        </div>
      </div>
    </>
  );
}

// ── Anomaly card (rich, primary content type) ────────────────
function AnomalyCard({ n }) {
  const sev = {
    critical: { color: 'var(--neg)',  soft: 'var(--neg-soft)',  label: '严重' },
    warn:     { color: 'var(--warn)', soft: 'oklch(0.65 0.15 60 / 0.10)', label: '警告' },
    info:     { color: 'var(--info)', soft: 'oklch(0.6 0.14 220 / 0.08)', label: '提示' },
  }[n.severity];

  const deltaColor = n.positive ? 'var(--pos)' : (n.severity === 'critical' ? 'var(--neg)' : 'var(--warn)');
  const arrow = n.delta > 0 ? '↑' : '↓';

  return (
    <div className="np-anomaly" style={{borderLeft: `3px solid ${sev.color}`}}>
      <div className="np-anomaly-row1">
        <span className="np-sev-pill" style={{color: sev.color, background: sev.soft, borderColor: sev.color}}>
          <span className="dot" style={{background: sev.color}} />
          {sev.label}
        </span>
        <span className="np-anomaly-title">{n.title}</span>
        <span className="np-when">{n.when}</span>
      </div>

      <div className="np-anomaly-row2">
        <div className="np-anomaly-stat">
          <div className="np-anomaly-label">{n.metric} · {n.dim}</div>
          <div className="np-anomaly-vals">
            <span className="np-anomaly-current mono">{n.current}</span>
            <span className="np-anomaly-vs">vs</span>
            <span className="np-anomaly-expected mono">{n.expected}</span>
            <span className="np-anomaly-delta mono" style={{color: deltaColor}}>
              {arrow} {Math.abs(n.delta).toFixed(1)}%
            </span>
          </div>
          <div className="np-anomaly-rule">
            <Icon name="bolt" /> {n.rule}
          </div>
        </div>
        <div className="np-anomaly-spark">
          <AnomalySpark points={n.spark} color={sev.color} />
        </div>
      </div>

      <div className="np-anomaly-actions">
        <button className="np-btn primary"><Icon name="thunder" />{n.action}</button>
        <button className="np-btn">订阅此指标</button>
        <button className="np-btn ghost">忽略</button>
      </div>
    </div>
  );
}

function AnomalySpark({ points, color }) {
  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = max - min || 1;
  const W = 130, H = 38;
  const pts = points.map((v, i) => {
    const x = (i / (points.length - 1)) * (W - 6) + 3;
    const y = H - 4 - ((v - min) / range) * (H - 8);
    return [x, y];
  });
  const path = pts.map(([x,y], i) => (i===0?'M':'L') + x.toFixed(1) + ' ' + y.toFixed(1)).join(' ');
  const area = path + ` L ${(W-3).toFixed(1)} ${H-2} L 3 ${H-2} Z`;
  const last = pts[pts.length-1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H}>
      <defs>
        <linearGradient id="anog" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#anog)" />
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="3" fill={color} />
      <circle cx={last[0]} cy={last[1]} r="6" fill={color} opacity="0.18" />
    </svg>
  );
}

function CollabRow({ n }) {
  return (
    <div className="np-row">
      <div className="np-row-avatar">{n.avatar}</div>
      <div className="np-row-body">
        <div className="np-row-title">{n.title}</div>
        <div className="np-row-preview">{n.preview}</div>
      </div>
      <div className="np-when">{n.when}</div>
    </div>
  );
}

function SystemRow({ n }) {
  return (
    <div className="np-row">
      <div className="np-row-icon"><Icon name="api" /></div>
      <div className="np-row-body">
        <div className="np-row-title">{n.title}</div>
        <div className="np-row-preview">{n.preview}</div>
      </div>
      <div className="np-when">{n.when}</div>
    </div>
  );
}

export { NotificationsPopover, bellCount };
