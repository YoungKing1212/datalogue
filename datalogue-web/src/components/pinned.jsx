import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from './icons';

// Pinned — favorites organized by folders, with quick re-run and pin-to-dashboard.

function PinnedScreen() {
  const navigate = useNavigate();
  const [activeFolder, setActiveFolder] = useState('weekly');

  const folders = [
    { id: 'all',     label: '全部收藏', icon: 'bookmark', count: 14 },
    { id: 'weekly',  label: '周度复盘',  icon: 'calendar', count: 5, color: 'var(--accent)' },
    { id: 'monthly', label: '月度报告',  icon: 'calendar', count: 3, color: 'oklch(0.6 0.15 60)' },
    { id: 'ops',     label: '运营巡检',  icon: 'preset',   count: 4, color: 'oklch(0.55 0.13 165)' },
    { id: 'exec',    label: '高管简报',  icon: 'flag',     count: 2, color: 'oklch(0.55 0.20 25)' },
  ];

  const cards = [
    { id: 'c1', folder: 'weekly', title: 'GMV 周度走势', q: '本周各品类GMV vs 上周对比', viz: 'bar', stat: '¥2.84M', delta: '+8.2%', up: true, lastRun: '今天 09:00 (自动)', apiPath: '/v1/sales/weekly-gmv' },
    { id: 'c2', folder: 'weekly', title: '销售额异常归因', q: '上周销售为什么下降12%', viz: 'waterfall', stat: '−12%', delta: '主因·华东女装', up: false, lastRun: '今天 09:02 (自动)', apiPath: '/v1/sales/weekly-attribution' },
    { id: 'c3', folder: 'weekly', title: '渠道ROI对比', q: '近7天各渠道ROI排行', viz: 'bar', stat: '2.43', delta: '抖音领先', up: true, lastRun: '今天 09:00', apiPath: '/v1/marketing/channel-roi' },
    { id: 'c4', folder: 'weekly', title: '新客转化漏斗', q: '本周新客从浏览到支付的漏斗', viz: 'funnel', stat: '3.42%', delta: '−0.7pp', up: false, lastRun: '今天 09:00', apiPath: null },
    { id: 'c5', folder: 'weekly', title: '会员等级迁徙', q: '本周会员等级升/降迁徙人数', viz: 'sankey', stat: '+218', delta: '净升级', up: true, lastRun: '今天 09:01', apiPath: null },
    { id: 'c6', folder: 'monthly', title: '月度品类结构', q: '本月品类GMV占比和同比', viz: 'pie', stat: '5类', delta: '美妆领跑', up: true, lastRun: '5月25日 08:00', apiPath: null },
    { id: 'c7', folder: 'monthly', title: '复购周期分布', q: '高价值用户复购周期 vs 普通', viz: 'line', stat: '28天', delta: '−42%', up: true, lastRun: '5月25日 08:01', apiPath: null },
    { id: 'c8', folder: 'monthly', title: '客单价分布直方图', q: '本月客单价分布', viz: 'hist', stat: '¥150.3', delta: '+4.9%', up: true, lastRun: '5月25日 08:02', apiPath: null },
    { id: 'c9', folder: 'ops', title: 'SKU缺货率', q: '华东仓SKU缺货率周报', viz: 'line', stat: '2.1%', delta: '+0.4pp', up: false, lastRun: '今天 07:30 (定时)', apiPath: '/v1/inventory/oos-weekly' },
    { id: 'c10', folder: 'ops', title: '客服情感分布', q: '近7天客服会话情感分布', viz: 'pie', stat: '18%', delta: '负向上升', up: false, lastRun: '今天 07:30', apiPath: null },
    { id: 'c11', folder: 'ops', title: '物流时效达成率', q: '各仓物流时效达成率', viz: 'bar', stat: '96.4%', delta: '+1.2pp', up: true, lastRun: '今天 07:30', apiPath: null },
    { id: 'c12', folder: 'ops', title: '退款率监控', q: '本周退款率 vs 历史均值', viz: 'line', stat: '4.2%', delta: '正常区间', up: true, lastRun: '今天 07:30', apiPath: null },
    { id: 'c13', folder: 'exec', title: '北极星指标 · 月度', q: 'MAU & GMV 月度趋势', viz: 'line', stat: '128万', delta: '+12.6%', up: true, lastRun: '5月25日 06:00', apiPath: null },
    { id: 'c14', folder: 'exec', title: 'NPS 月度报告', q: '本月NPS和驱动因子', viz: 'bar', stat: '+42', delta: '+3', up: true, lastRun: '5月25日 06:00', apiPath: null },
  ];

  const visible = activeFolder === 'all' ? cards : cards.filter(c => c.folder === activeFolder);

  // Tiny inline viz placeholder
  const Viz = ({ kind }) => {
    if (kind === 'bar') {
      const heights = [0.4, 0.7, 0.5, 0.9, 0.6, 0.75];
      return (
        <svg viewBox="0 0 120 40" width="100%" height="40">
          {heights.map((h, i) => (
            <rect key={i} x={i*20+2} y={40 - h*36} width={14} height={h*36} rx={1.5}
                  fill="var(--accent-soft)" stroke="var(--accent)" strokeWidth="1" />
          ))}
        </svg>
      );
    }
    if (kind === 'line') {
      return (
        <svg viewBox="0 0 120 40" width="100%" height="40">
          <path d="M2 30 L22 22 L42 26 L62 14 L82 18 L102 10 L118 6"
                fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M2 30 L22 22 L42 26 L62 14 L82 18 L102 10 L118 6 L118 38 L2 38 Z"
                fill="var(--accent-soft)" />
        </svg>
      );
    }
    if (kind === 'pie') {
      return (
        <svg viewBox="0 0 40 40" width="40" height="40">
          <circle cx="20" cy="20" r="16" fill="var(--surface-2)" stroke="var(--hairline-strong)" />
          <path d="M20 4 A16 16 0 0 1 34 28 L20 20 Z" fill="var(--accent)" />
          <path d="M34 28 A16 16 0 0 1 12 33 L20 20 Z" fill="oklch(0.55 0.13 165)" opacity="0.7" />
        </svg>
      );
    }
    if (kind === 'waterfall') {
      return (
        <svg viewBox="0 0 120 40" width="100%" height="40">
          <rect x="2"  y="6"  width="14" height="28" fill="var(--accent-soft)" stroke="var(--accent)" />
          <rect x="20" y="14" width="14" height="14" fill="var(--neg-soft)" stroke="var(--neg)" />
          <rect x="38" y="18" width="14" height="10" fill="var(--neg-soft)" stroke="var(--neg)" />
          <rect x="56" y="22" width="14" height="6"  fill="var(--neg-soft)" stroke="var(--neg)" />
          <rect x="74" y="20" width="14" height="4"  fill="var(--pos-soft)" stroke="var(--pos)" />
          <rect x="92" y="14" width="14" height="20" fill="var(--accent-soft)" stroke="var(--accent)" />
        </svg>
      );
    }
    if (kind === 'funnel') {
      return (
        <svg viewBox="0 0 120 40" width="100%" height="40">
          <path d="M2 4 L118 4 L96 14 L24 14 Z"  fill="var(--accent-soft)" stroke="var(--accent)" />
          <path d="M24 16 L96 16 L80 26 L40 26 Z" fill="var(--accent-soft)" stroke="var(--accent)" opacity="0.7" />
          <path d="M40 28 L80 28 L70 38 L50 38 Z" fill="var(--accent-soft)" stroke="var(--accent)" opacity="0.5" />
        </svg>
      );
    }
    if (kind === 'hist') {
      const h = [0.2, 0.45, 0.75, 0.95, 0.7, 0.4, 0.25, 0.1];
      return (
        <svg viewBox="0 0 120 40" width="100%" height="40">
          {h.map((v, i) => (
            <rect key={i} x={i*15+2} y={40 - v*36} width={13} height={v*36} fill="var(--accent)" opacity="0.85" />
          ))}
        </svg>
      );
    }
    if (kind === 'sankey') {
      return (
        <svg viewBox="0 0 120 40" width="100%" height="40">
          <path d="M2 6 C 50 6, 70 14, 118 14 L118 22 C 70 22, 50 30, 2 30 Z" fill="var(--accent-soft)" stroke="var(--accent)" />
          <path d="M2 8 C 50 8, 70 12, 118 12" stroke="oklch(0.55 0.13 165)" strokeWidth="3" fill="none" />
        </svg>
      );
    }
    return null;
  };

  return (
    <div className="pin-wrap">
      <div className="pin-head">
        <div>
          <h1>收藏</h1>
          <p className="desc">已钉选的问题和结果。固定为接口或定时刷新后，会自动出现在工作台和看板。</p>
        </div>
        <div className="hp-head-actions">
          <button className="btn ghost"><Icon name="folder" />新建文件夹</button>
          <button className="btn primary"><Icon name="plus" />新建收藏</button>
        </div>
      </div>

      <div className="pin-grid">
        <div className="pin-folders">
          <div className="group-title">文件夹</div>
          {folders.map(f => (
            <button key={f.id} className={'pin-folder ' + (activeFolder === f.id ? 'active' : '')} onClick={() => setActiveFolder(f.id)}>
              <span className="pin-folder-dot" style={{background: f.color || 'var(--text-4)'}} />
              <Icon name={f.icon} />
              <span>{f.label}</span>
              <span className="badge">{f.count}</span>
            </button>
          ))}
          <div className="group-title" style={{marginTop: 18}}>智能集合</div>
          <button className="pin-folder"><Icon name="bolt" /><span>最近运行失败</span><span className="badge">2</span></button>
          <button className="pin-folder"><Icon name="api" /><span>已发布为接口</span><span className="badge">7</span></button>
          <button className="pin-folder"><Icon name="refresh" /><span>定时刷新中</span><span className="badge">9</span></button>
        </div>

        <div className="pin-cards">
          {visible.map(c => (
            <div key={c.id} className="pin-card" onClick={() => navigate('/chat')}>
              <div className="pin-card-head">
                <div className="pin-card-title">{c.title}</div>
                <button className="icon-btn pin-more" onClick={e=>e.stopPropagation()}><Icon name="more" /></button>
              </div>
              <div className="pin-card-q">"{c.q}"</div>
              <div className="pin-card-viz"><Viz kind={c.viz} /></div>
              <div className="pin-card-stat">
                <div className="pin-stat-val">{c.stat}</div>
                <div className={'pin-stat-delta ' + (c.up ? 'up' : 'down')}>
                  <Icon name={c.up ? 'arrow_up_right' : 'arrow_down'} style={{width: 11, height: 11}} />
                  {c.delta}
                </div>
              </div>
              <div className="pin-card-foot">
                <span className="pin-foot-meta"><Icon name="refresh" />{c.lastRun}</span>
                {c.apiPath
                  ? <span className="pin-foot-api"><Icon name="api" /><span className="mono">{c.apiPath}</span></span>
                  : <button className="pin-foot-publish" onClick={e=>{e.stopPropagation(); navigate('/apis');}}>
                      <Icon name="api" />发布为接口
                    </button>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export { PinnedScreen };
