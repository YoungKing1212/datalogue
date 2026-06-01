import React from 'react';

// Inline chart primitives — small, dark-theme tuned SVG charts.

// ── Waterfall (for decomposition) ────────────────────────────────────────────
function Waterfall({ steps, h = 220, w = 700 }) {
  // steps: [{label, value, type: 'start'|'plus'|'minus'|'end'}]
  const pad = { l: 50, r: 16, t: 16, b: 38 };
  const innerW = w - pad.l - pad.r;
  const innerH = h - pad.t - pad.b;
  const bw = innerW / steps.length - 14;

  // accumulate running totals
  let running = 0;
  const items = steps.map(s => {
    let y0, y1;
    if (s.type === 'start' || s.type === 'end') {
      const v = s.type === 'start' ? s.value : running;
      y0 = 0; y1 = v;
      if (s.type === 'start') running = v;
    } else {
      y0 = running;
      running = running + s.value;
      y1 = running;
    }
    return { ...s, y0, y1, low: Math.min(y0, y1), high: Math.max(y0, y1) };
  });

  const max = Math.max(...items.map(i => i.high));
  const min = Math.min(0, ...items.map(i => i.low));
  const range = max - min || 1;
  const yScale = v => pad.t + innerH - ((v - min) / range) * innerH;

  const colors = {
    start: 'oklch(0.62 0.14 220)',
    plus: 'oklch(0.55 0.13 165)',
    minus: 'oklch(0.55 0.20 25)',
    end: 'oklch(0.55 0.16 245)',
  };

  // y ticks
  const ticks = 4;
  const tickValues = Array.from({length: ticks + 1}, (_, i) => min + (range * i) / ticks);

  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{display: 'block'}}>
      {/* grid */}
      {tickValues.map((v, i) => (
        <g key={i}>
          <line x1={pad.l} x2={w - pad.r} y1={yScale(v)} y2={yScale(v)}
                stroke="rgba(15,23,42,0.06)" strokeDasharray={i === 0 ? '' : '2 4'} />
          <text x={pad.l - 8} y={yScale(v)} fill="var(--text-3)" fontSize="10.5" textAnchor="end"
                dominantBaseline="middle" fontFamily="var(--font-mono)">
            {v >= 1e6 ? (v/1e6).toFixed(1) + 'M' : v >= 1000 ? (v/1000).toFixed(0) + 'k' : v.toFixed(0)}
          </text>
        </g>
      ))}
      {/* bars */}
      {items.map((it, i) => {
        const x = pad.l + i * (innerW / steps.length) + (innerW / steps.length - bw) / 2;
        const y = yScale(it.high);
        const barH = Math.max(2, yScale(it.low) - yScale(it.high));
        return (
          <g key={i}>
            <rect x={x} y={y} width={bw} height={barH} rx="2"
                  fill={colors[it.type]} opacity="0.85" />
            {/* connector line */}
            {i < items.length - 1 && items[i+1].type !== 'end' && (
              <line x1={x + bw} x2={x + bw + 14}
                    y1={yScale(it.y1)} y2={yScale(it.y1)}
                    stroke="rgba(15,23,42,0.18)" strokeDasharray="2 3" />
            )}
            {/* value label */}
            <text x={x + bw / 2} y={y - 6} fill={it.type === 'minus' ? 'oklch(0.55 0.20 25)' : it.type === 'plus' ? 'oklch(0.50 0.14 165)' : 'var(--text)'}
                  fontSize="11" textAnchor="middle" fontFamily="var(--font-mono)">
              {it.type === 'start' || it.type === 'end'
                ? (it.value >= 1e6 ? (it.value/1e6).toFixed(2) + 'M' : (it.value/1000).toFixed(0) + 'k')
                : (it.value > 0 ? '+' : '') + (it.value/1000).toFixed(0) + 'k'}
            </text>
            {/* category label */}
            <text x={x + bw / 2} y={h - 18} fill="var(--text-2)" fontSize="11" textAnchor="middle">
              {it.label}
            </text>
            <text x={x + bw / 2} y={h - 6} fill="var(--text-3)" fontSize="10" textAnchor="middle" fontFamily="var(--font-mono)">
              {it.sub}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Grouped Bar ──────────────────────────────────────────────────────────────
function GroupedBar({ data, groups, colors, h = 200, w = 700 }) {
  // data: [{label, values: [n,n,...]}]
  const pad = { l: 44, r: 16, t: 18, b: 30 };
  const innerW = w - pad.l - pad.r;
  const innerH = h - pad.t - pad.b;
  const all = data.flatMap(d => d.values);
  const max = Math.max(...all) * 1.1;
  const yScale = v => pad.t + innerH - (v / max) * innerH;
  const gw = innerW / data.length;
  const bw = (gw - 12) / groups.length;

  const ticks = 4;
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{display: 'block'}}>
      {Array.from({length: ticks + 1}, (_, i) => {
        const v = (max * i) / ticks;
        return (
          <g key={i}>
            <line x1={pad.l} x2={w - pad.r} y1={yScale(v)} y2={yScale(v)}
                  stroke="rgba(15,23,42,0.06)" strokeDasharray={i === 0 ? '' : '2 4'} />
            <text x={pad.l - 8} y={yScale(v)} fill="var(--text-3)" fontSize="10.5" textAnchor="end"
                  dominantBaseline="middle" fontFamily="var(--font-mono)">
              {v >= 1e6 ? (v/1e6).toFixed(1) + 'M' : v >= 1000 ? (v/1000).toFixed(0) + 'k' : Math.round(v)}
            </text>
          </g>
        );
      })}
      {data.map((d, i) => {
        const gx = pad.l + i * gw + 6;
        return (
          <g key={i}>
            {d.values.map((v, j) => (
              <rect key={j} x={gx + j * bw} y={yScale(v)} width={bw - 2}
                    height={yScale(0) - yScale(v)} fill={colors[j]} opacity="0.85" rx="1.5" />
            ))}
            <text x={gx + (gw - 12) / 2} y={h - 10} fill="var(--text-2)" fontSize="11" textAnchor="middle">
              {d.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Line Chart ───────────────────────────────────────────────────────────────
function LineChart({ series, labels, h = 180, w = 700, fill = false }) {
  // series: [{name, color, points: [n,...]}]
  const pad = { l: 44, r: 16, t: 18, b: 26 };
  const innerW = w - pad.l - pad.r;
  const innerH = h - pad.t - pad.b;
  const all = series.flatMap(s => s.points);
  const min = Math.min(...all) * 0.92;
  const max = Math.max(...all) * 1.06;
  const xScale = i => pad.l + (i / (labels.length - 1)) * innerW;
  const yScale = v => pad.t + innerH - ((v - min) / (max - min)) * innerH;

  const ticks = 4;
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{display: 'block'}}>
      {Array.from({length: ticks + 1}, (_, i) => {
        const v = min + ((max - min) * i) / ticks;
        return (
          <g key={i}>
            <line x1={pad.l} x2={w - pad.r} y1={yScale(v)} y2={yScale(v)}
                  stroke="rgba(15,23,42,0.06)" strokeDasharray={i === 0 ? '' : '2 4'} />
            <text x={pad.l - 8} y={yScale(v)} fill="var(--text-3)" fontSize="10.5"
                  textAnchor="end" dominantBaseline="middle" fontFamily="var(--font-mono)">
              {v >= 1e6 ? (v/1e6).toFixed(1) + 'M' : v >= 1000 ? (v/1000).toFixed(0) + 'k' : v.toFixed(0)}
            </text>
          </g>
        );
      })}
      {labels.map((l, i) => (
        <text key={i} x={xScale(i)} y={h - 8} fill="var(--text-3)" fontSize="10.5"
              textAnchor="middle" fontFamily="var(--font-mono)">{l}</text>
      ))}
      {series.map((s, si) => {
        const d = s.points.map((p, i) => (i === 0 ? "M" : "L") + xScale(i) + " " + yScale(p)).join(" ");
        const dFill = d + ` L ${xScale(s.points.length - 1)} ${yScale(min)} L ${xScale(0)} ${yScale(min)} Z`;
        return (
          <g key={si}>
            {fill && <path d={dFill} fill={s.color} opacity="0.12" />}
            <path d={d} fill="none" stroke={s.color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            {s.points.map((p, i) => (
              <circle key={i} cx={xScale(i)} cy={yScale(p)} r="2.5" fill={s.color} />
            ))}
          </g>
        );
      })}
    </svg>
  );
}

// ── Donut ────────────────────────────────────────────────────────────────────
function Donut({ segments, size = 130 }) {
  const r = size / 2 - 8;
  const total = segments.reduce((a, b) => a + b.value, 0);
  let acc = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {segments.map((s, i) => {
        const startAngle = (acc / total) * Math.PI * 2 - Math.PI / 2;
        acc += s.value;
        const endAngle = (acc / total) * Math.PI * 2 - Math.PI / 2;
        const x0 = size / 2 + r * Math.cos(startAngle);
        const y0 = size / 2 + r * Math.sin(startAngle);
        const x1 = size / 2 + r * Math.cos(endAngle);
        const y1 = size / 2 + r * Math.sin(endAngle);
        const large = endAngle - startAngle > Math.PI ? 1 : 0;
        return (
          <path key={i} d={`M ${size/2} ${size/2} L ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} Z`}
                fill={s.color} opacity="0.9" stroke="var(--bg)" strokeWidth="2" />
        );
      })}
      <circle cx={size/2} cy={size/2} r={r * 0.62} fill="var(--surface)" />
    </svg>
  );
}

// ── Heat strip ───────────────────────────────────────────────────────────────
function HeatStrip({ values, max, cells, color }) {
  return (
    <div style={{display: 'flex', gap: 2}}>
      {values.map((v, i) => (
        <div key={i} style={{
          flex: 1,
          height: 22,
          background: color,
          opacity: 0.18 + (v / max) * 0.82,
          borderRadius: 2,
        }} title={String(v)} />
      ))}
    </div>
  );
}

export { Waterfall, GroupedBar, LineChart, Donut, HeatStrip };
