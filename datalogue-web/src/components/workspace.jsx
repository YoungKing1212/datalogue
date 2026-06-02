import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from './icons';

// Workspace — homepage with ask hero, suggested questions, KPI snapshot, recent threads.

function Sparkline({ points, color = "currentColor", w = 64, h = 18 }) {
  const xs = points.map((_, i) => (i / (points.length - 1)) * w);
  const min = Math.min(...points), max = Math.max(...points);
  const range = max - min || 1;
  const ys = points.map(p => h - ((p - min) / range) * (h - 2) - 1);
  const d = xs.map((x, i) => (i === 0 ? "M" : "L") + x.toFixed(1) + " " + ys[i].toFixed(1)).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <path d={d} fill="none" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Workspace() {
  const navigate = useNavigate();
  const suggested = [
    { icon: "thunder", q: "上周整体销售为什么下降了12%？", tag: "归因分析" },
    { icon: "chart_line", q: "近30天各渠道ROI对比，找出表现最好的", tag: "对比分析" },
    { icon: "chart_pie", q: "今年Q1各品类GMV占比和同比变化", tag: "结构分析" },
    { icon: "insight", q: "高价值用户的复购周期 vs 普通用户", tag: "用户洞察" },
  ];
  const kpis = [
    { label: "GMV (本周)", val: "¥2.84M", delta: "+8.2%", up: true, spark: [3,4,3,5,4,6,7], color: "var(--pos)" },
    { label: "订单数",      val: "18,924", delta: "+3.1%", up: true, spark: [5,4,5,6,5,6,7], color: "var(--pos)" },
    { label: "客单价",      val: "¥150.3", delta: "+4.9%", up: true, spark: [3,3,4,3,4,5,5], color: "var(--pos)" },
    { label: "新客转化率",  val: "3.42%",  delta: "−0.7%", up: false, spark: [6,5,6,5,4,4,3], color: "var(--neg)" },
  ];
  const recents = [
    { title: "上周华东区销售为什么下降了12%", preview: "归因到「华东·女装·订单量」下滑41%，进一步定位到3家头部店铺...", when: "2分钟前", tag: "归因" },
    { title: "今年Q1各品类GMV同环比", preview: "服饰、美妆、家电环比增长，3C数码品类同比下滑6.2%...", when: "今天 14:08", tag: "对比" },
    { title: "高价值用户的复购周期分析", preview: "AOV>500的用户平均复购周期28天，较普通用户短42%...", when: "昨天", tag: "洞察" },
  ];

  return (
    <div className="workspace">
      <h1 className="hello">下午好，Yan Lin <span className="accent">— 想看点什么？</span></h1>
      <p className="sub">输入业务问题，数语会自动选取指标、生成SQL、绘制图表并解释结果。</p>

      <div className="ask-hero">
        <textarea
          className="ask-input"
          rows={2}
          placeholder="例如：上周华东区销售为什么下降了？哪个品类拖累最大？"
          onFocus={() => navigate('/chat')}
          readOnly
        />
        <div className="toolbar">
          <button className="tool-chip" onClick={() => navigate('/chat')}><Icon name="database" />全部数据集</button>
          <button className="tool-chip"><Icon name="calendar" />近7天</button>
          <button className="tool-chip"><Icon name="filter_alt" />筛选条件</button>
          <button className="tool-chip"><Icon name="brain" />深度归因</button>
          <button className="send-btn" onClick={() => navigate('/chat')}><Icon name="send" /></button>
        </div>
      </div>

      <div className="suggested">
        {suggested.map((s, i) => (
          <button key={i} className="item" onClick={() => navigate('/chat')}>
            <div className="icon-wrap"><Icon name={s.icon} /></div>
            <div>
              <div className="q">{s.q}</div>
              <div className="tag">{s.tag}</div>
            </div>
          </button>
        ))}
      </div>

      <div className="section-header">
        <h3>核心指标 · 本周</h3>
        <button className="more">查看看板 →</button>
      </div>
      <div className="kpi-row">
        {kpis.map((k, i) => (
          <div className="kpi" key={i}>
            <div className="label">{k.label}</div>
            <div className="val">{k.val}</div>
            <div className={'delta ' + (k.up ? 'up' : 'down')}>
              <Icon name={k.up ? "arrow_up_right" : "arrow_down"} style={{width: 11, height: 11}} />
              {k.delta}
            </div>
            <div className="spark"><Sparkline points={k.spark} color={k.color} /></div>
          </div>
        ))}
      </div>

      <div className="section-header">
        <h3>最近的会话</h3>
        <button className="more">全部历史 →</button>
      </div>
      <div className="recents">
        {recents.map((r, i) => (
          <button key={i} className="recent-card" onClick={() => navigate('/chat')}>
            <div className="meta">
              <Icon name="chat" style={{width: 11, height: 11}} />
              <span>{r.tag}</span>
              <span className="dot"></span>
              <span>{r.when}</span>
            </div>
            <div className="title">{r.title}</div>
            <div className="preview">{r.preview}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

export { Workspace, Sparkline };
