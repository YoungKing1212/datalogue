import React, { Fragment } from 'react';
import { Icon } from './icons';
import { LineChart, Donut, HeatStrip, GroupedBar } from './charts';
import { Sparkline } from './workspace';
import { PrototypeNotice } from '../shared/components/prototype-notice';

// Dashboard — auto-generated dashboard editor with cards saved from chat.

function DashboardScreen() {
  return (
    <div className="dash-wrap">
      <PrototypeNotice />
      <div className="dash-topbar">
        <div className="title">销售周度复盘</div>
        <div className="filters">
          <button className="filter-chip"><Icon name="calendar" /><strong>近4周</strong></button>
          <button className="filter-chip"><Icon name="globe" />地区<strong>: 全部</strong></button>
          <button className="filter-chip"><Icon name="folder" />品类<strong>: 全部</strong></button>
          <button className="filter-chip" style={{borderStyle: 'dashed'}}><Icon name="plus" />筛选</button>
        </div>
        <div className="actions">
          <span className="mono text-3" style={{fontSize: 11}}>更新于 2分钟前</span>
          <button className="icon-btn"><Icon name="refresh" /></button>
          <button className="icon-btn"><Icon name="share" /></button>
          <button className="btn"><Icon name="sparkle" />AI 改进看板</button>
        </div>
      </div>

      <div className="dash-grid">
        {/* KPI tiles row */}
        <div className="tile col-3">
          <div className="tile-head">
            <div className="h">
              <div className="t">GMV (本周)</div>
              <div className="big">¥2.84M</div>
              <div className="d up"><Icon name="arrow_up_right" style={{width:11,height:11}} />+8.2% wow</div>
            </div>
            <div className="a">
              <button className="icon-btn"><Icon name="drag" /></button>
              <button className="icon-btn"><Icon name="more" /></button>
            </div>
          </div>
          <Sparkline points={[2.1, 2.3, 2.4, 2.2, 2.5, 2.6, 2.84]} color="oklch(0.55 0.13 165)" w={220} h={36} />
        </div>

        <div className="tile col-3">
          <div className="tile-head">
            <div className="h">
              <div className="t">订单数</div>
              <div className="big">18,924</div>
              <div className="d up"><Icon name="arrow_up_right" style={{width:11,height:11}} />+3.1% wow</div>
            </div>
            <div className="a">
              <button className="icon-btn"><Icon name="drag" /></button>
              <button className="icon-btn"><Icon name="more" /></button>
            </div>
          </div>
          <Sparkline points={[16, 17, 17.5, 16.8, 17.9, 18.4, 18.9]} color="oklch(0.62 0.14 220)" w={220} h={36} />
        </div>

        <div className="tile col-3">
          <div className="tile-head">
            <div className="h">
              <div className="t">客单价 (AOV)</div>
              <div className="big">¥150.3</div>
              <div className="d up"><Icon name="arrow_up_right" style={{width:11,height:11}} />+4.9% wow</div>
            </div>
            <div className="a">
              <button className="icon-btn"><Icon name="drag" /></button>
              <button className="icon-btn"><Icon name="more" /></button>
            </div>
          </div>
          <Sparkline points={[140, 142, 145, 143, 147, 149, 150.3]} color="oklch(0.65 0.15 60)" w={220} h={36} />
        </div>

        <div className="tile col-3">
          <div className="tile-head">
            <div className="h">
              <div className="t">新客转化率</div>
              <div className="big">3.42%</div>
              <div className="d down"><Icon name="arrow_down" style={{width:11,height:11}} />−0.7% wow</div>
            </div>
            <div className="a">
              <button className="icon-btn"><Icon name="drag" /></button>
              <button className="icon-btn"><Icon name="more" /></button>
            </div>
          </div>
          <Sparkline points={[4.0, 3.9, 4.1, 3.8, 3.7, 3.55, 3.42]} color="oklch(0.55 0.20 25)" w={220} h={36} />
        </div>

        {/* Big trend line */}
        <div className="tile col-8">
          <div className="tile-head">
            <div className="h">
              <div className="tile-title">GMV 趋势 · 近12周</div>
              <div className="tile-sub">分区域拆解 · 单位 ¥</div>
            </div>
            <div className="a">
              <button className="icon-btn"><Icon name="expand" /></button>
              <button className="icon-btn"><Icon name="drag" /></button>
              <button className="icon-btn"><Icon name="more" /></button>
            </div>
          </div>
          <LineChart
            series={[
              { name: '华东', color: 'oklch(0.55 0.16 245)', points: [820,860,880,910,890,940,960,990,1020,1010,1050,920] },
              { name: '华南', color: 'oklch(0.62 0.14 220)',  points: [620,640,670,680,690,720,710,740,760,770,810,760] },
              { name: '华北', color: 'oklch(0.55 0.13 165)', points: [480,490,510,520,540,560,580,600,610,640,690,710] },
              { name: '西南', color: 'oklch(0.65 0.15 60)',  points: [320,340,330,350,360,370,380,390,400,420,430,450] },
            ]}
            labels={['W09','W10','W11','W12','W13','W14','W15','W16','W17','W18','W19','W20']}
            w={760} h={210}
          />
          <div className="legend">
            <span className="lg"><span className="sw" style={{background:'oklch(0.55 0.16 245)'}} />华东</span>
            <span className="lg"><span className="sw" style={{background:'oklch(0.62 0.14 220)'}} />华南</span>
            <span className="lg"><span className="sw" style={{background:'oklch(0.55 0.13 165)'}} />华北</span>
            <span className="lg"><span className="sw" style={{background:'oklch(0.65 0.15 60)'}} />西南</span>
          </div>
        </div>

        {/* Donut */}
        <div className="tile col-4">
          <div className="tile-head">
            <div className="h">
              <div className="tile-title">品类 GMV 占比</div>
              <div className="tile-sub">本周</div>
            </div>
            <div className="a">
              <button className="icon-btn"><Icon name="expand" /></button>
              <button className="icon-btn"><Icon name="drag" /></button>
              <button className="icon-btn"><Icon name="more" /></button>
            </div>
          </div>
          <div style={{display: 'flex', alignItems: 'center', gap: 18, marginTop: 12}}>
            <Donut
              size={140}
              segments={[
                { value: 38, color: 'oklch(0.55 0.16 245)' },
                { value: 24, color: 'oklch(0.62 0.14 220)' },
                { value: 18, color: 'oklch(0.55 0.13 165)' },
                { value: 12, color: 'oklch(0.65 0.15 60)' },
                { value: 8,  color: 'oklch(0.5 0.14 30)' },
              ]}
            />
            <div style={{display: 'flex', flexDirection: 'column', gap: 6, flex: 1}}>
              {[
                {l: '服饰', v: '38%', c: 'oklch(0.55 0.16 245)'},
                {l: '美妆', v: '24%', c: 'oklch(0.62 0.14 220)'},
                {l: '家电', v: '18%', c: 'oklch(0.55 0.13 165)'},
                {l: '3C 数码', v: '12%', c: 'oklch(0.65 0.15 60)'},
                {l: '食品生鲜', v: '8%', c: 'oklch(0.5 0.14 30)'},
              ].map((row, i) => (
                <div key={i} style={{display: 'flex', alignItems: 'center', gap: 8, fontSize: 12}}>
                  <span style={{width: 9, height: 9, borderRadius: 2, background: row.c}}></span>
                  <span style={{color: 'var(--text-2)'}}>{row.l}</span>
                  <span className="mono" style={{marginLeft: 'auto', color: 'var(--text)', fontVariantNumeric: 'tabular-nums'}}>{row.v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Grouped bar — region performance */}
        <div className="tile col-6">
          <div className="tile-head">
            <div className="h">
              <div className="tile-title">区域 GMV · 本周 vs 上周</div>
              <div className="tile-sub">从问数中保存 · 2分钟前</div>
            </div>
            <div className="a">
              <button className="icon-btn"><Icon name="expand" /></button>
              <button className="icon-btn"><Icon name="drag" /></button>
              <button className="icon-btn"><Icon name="more" /></button>
            </div>
          </div>
          <GroupedBar
            data={[
              { label: '华东', values: [920_000, 1_050_000] },
              { label: '华南', values: [760_000, 810_000] },
              { label: '华北', values: [710_000, 690_000] },
              { label: '西南', values: [450_000, 430_000] },
            ]}
            groups={['本周', '上周']}
            colors={['oklch(0.55 0.16 245)', 'rgba(15,23,42,0.18)']}
            w={520} h={200}
          />
          <div className="legend">
            <span className="lg"><span className="sw" style={{background:'oklch(0.55 0.16 245)'}} />本周</span>
            <span className="lg"><span className="sw" style={{background:'rgba(15,23,42,0.18)'}} />上周</span>
          </div>
        </div>

        {/* Heat strip table — channel ROI */}
        <div className="tile col-6">
          <div className="tile-head">
            <div className="h">
              <div className="tile-title">渠道 ROAS · 近 14 天</div>
              <div className="tile-sub">按日热力</div>
            </div>
            <div className="a">
              <button className="icon-btn"><Icon name="expand" /></button>
              <button className="icon-btn"><Icon name="drag" /></button>
              <button className="icon-btn"><Icon name="more" /></button>
            </div>
          </div>
          <div style={{display: 'grid', gridTemplateColumns: '88px 1fr 48px', gap: 8, alignItems: 'center', marginTop: 6}}>
            {[
              { ch: '抖音',   vals: [3.2, 3.4, 2.9, 3.1, 3.5, 3.6, 3.8, 3.2, 3.0, 2.8, 3.1, 3.4, 3.7, 3.9], avg: '3.4' },
              { ch: '小红书', vals: [2.8, 2.9, 2.7, 2.6, 2.4, 2.5, 2.7, 2.8, 2.9, 3.0, 2.8, 2.6, 2.5, 2.7], avg: '2.7' },
              { ch: '微信',   vals: [4.1, 4.3, 4.0, 4.4, 4.5, 4.7, 4.6, 4.8, 4.5, 4.4, 4.2, 4.0, 4.3, 4.6], avg: '4.4' },
              { ch: '搜索',   vals: [5.2, 5.1, 5.3, 5.4, 5.6, 5.5, 5.7, 5.8, 5.6, 5.5, 5.3, 5.4, 5.6, 5.8], avg: '5.5' },
              { ch: '私域',   vals: [6.8, 6.7, 6.9, 7.0, 7.2, 7.1, 7.3, 7.4, 7.2, 7.1, 7.0, 7.2, 7.4, 7.5], avg: '7.1' },
            ].map((row, i) => (
              <Fragment key={i}>
                <span style={{fontSize: 12, color: 'var(--text-2)'}}>{row.ch}</span>
                <HeatStrip values={row.vals} max={8} cells={14} color="oklch(0.55 0.16 245)" />
                <span className="mono" style={{fontSize: 12, color: 'var(--text)', textAlign: 'right'}}>{row.avg}</span>
              </Fragment>
            ))}
          </div>
        </div>

        {/* AI suggestion tile */}
        <div className="tile col-8" style={{borderColor: 'var(--accent-line)', background: 'linear-gradient(135deg, oklch(0.55 0.16 245 / 0.05), var(--surface))'}}>
          <div className="tile-head">
            <div className="h" style={{display:'flex', alignItems:'center', gap: 10}}>
              <Icon name="sparkle" style={{width:16, height:16, color: 'var(--accent)'}} />
              <div>
                <div className="tile-title">数语发现 · 3 个值得关注的异常</div>
                <div className="tile-sub">基于本看板的指标自动巡检</div>
              </div>
            </div>
            <div className="a">
              <button className="icon-btn"><Icon name="more" /></button>
            </div>
          </div>
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginTop: 6}}>
            {[
              { tag: '异常下降', tone: 'neg', title: '华东·女装订单量', delta: '−41%', body: '集中于3家头部店铺，疑似流量分配调整' },
              { tag: '机会点',   tone: 'pos', title: '私域 ROAS 持续抬升', delta: '+18%', body: '建议加大私域投放预算 20%' },
              { tag: '关注',     tone: 'warn',title: '复购率定义冲突', delta: '×',     body: '4个看板口径不一致，影响数据可信度' },
            ].map((it, i) => (
              <div key={i} style={{padding: 12, background: 'var(--bg-2)', border: '1px solid var(--hairline)', borderRadius: 8}}>
                <div style={{display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6}}>
                  <span style={{
                    fontSize: 10.5, padding: '2px 6px', borderRadius: 4, fontFamily: 'var(--font-mono)',
                    background: it.tone === 'neg' ? 'oklch(0.55 0.20 25 / 0.10)' :
                               it.tone === 'pos' ? 'oklch(0.55 0.13 165 / 0.12)' :
                                                   'oklch(0.65 0.15 60 / 0.12)',
                    color: it.tone === 'neg' ? 'var(--neg)' : it.tone === 'pos' ? 'var(--pos)' : 'var(--warn)',
                  }}>{it.tag}</span>
                  <span className="mono" style={{fontSize: 12, color: it.tone === 'neg' ? 'var(--neg)' : it.tone === 'pos' ? 'var(--pos)' : 'var(--warn)', marginLeft: 'auto'}}>{it.delta}</span>
                </div>
                <div style={{fontSize: 13, fontWeight: 500, marginBottom: 4}}>{it.title}</div>
                <div style={{fontSize: 12, color: 'var(--text-3)', lineHeight: 1.5}}>{it.body}</div>
              </div>
            ))}
          </div>
        </div>

        <button className="add-tile col-4">
          <div className="stack">
            <Icon name="plus" />
            <span>从问数添加 / 询问 AI 生成</span>
          </div>
        </button>
      </div>
    </div>
  );
}

export { DashboardScreen };
