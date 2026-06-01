import React, { useState, Fragment } from 'react';
import { Icon } from './icons';
import { Sparkline } from './workspace';

// APIs — list and detail view of "published as API" sessions.
// This is the headline feature: turn a shaped data-agent question into a stable endpoint.

const APIS = [
  {
    id: 'api-01',
    name: '周度销售归因',
    path: '/v1/sales/weekly-attribution',
    desc: '基于上周 vs 上上周差异，归因到「区域 × 品类 × 子类」拆解结果',
    question: '上周{region}销售为什么{direction}了{threshold}%？哪个区域和品类拖累最大？',
    status: 'published',
    version: 'v1.2',
    method: 'GET',
    owner: 'Yan Lin',
    createdAt: '2025-11-08',
    updatedAt: '今天 11:24',
    dataset: 'electric_dwh.dws_sales_daily',
    qps24h: 0.34,
    calls24h: 29_412,
    p95: 142,
    success: 99.91,
    quota: { used: 128_402, total: 500_000 },
    spark: [10, 14, 11, 18, 22, 19, 24, 21, 27, 30, 25, 28],
    params: [
      { key: 'region',    type: 'enum',   required: false, default: '华东', enums: ['华东','华南','华北','华中','西南','西北','东北'], desc: '区域，对应 dim_region 表' },
      { key: 'compare_to',type: 'string', required: false, default: 'last_week', desc: '基准期，可选 last_week / last_month / yoy' },
      { key: 'threshold', type: 'number', required: false, default: 5, desc: '差异阈值（%），低于此值不输出归因项' },
      { key: 'top_n',     type: 'number', required: false, default: 5, desc: '返回的拖累/拉动项数量' },
      { key: 'format',    type: 'enum',   required: false, default: 'json', enums: ['json','csv','markdown'], desc: '响应格式' },
    ],
  },
  {
    id: 'api-02',
    name: '渠道 ROI 排行',
    path: '/v1/marketing/channel-roi',
    desc: '按渠道维度计算近 N 天 ROI 并排序，支持按品类筛选',
    status: 'published',
    version: 'v2.0',
    method: 'GET',
    owner: 'Yan Lin',
    createdAt: '2025-09-12',
    updatedAt: '昨天',
    dataset: 'electric_dwh.dwd_marketing_event',
    qps24h: 0.58,
    calls24h: 50_212,
    p95: 98,
    success: 100,
    quota: { used: 218_900, total: 500_000 },
    spark: [22, 28, 25, 30, 32, 28, 36, 34, 40, 38, 42, 45],
    params: [],
  },
  {
    id: 'api-03',
    name: '本周 GMV 快照',
    path: '/v1/sales/weekly-gmv',
    desc: '返回本周累计 GMV、订单数、客单价及 WoW 变化',
    status: 'published',
    version: 'v1.0',
    method: 'GET',
    owner: '王磊',
    createdAt: '2025-12-01',
    updatedAt: '5月20日',
    dataset: 'electric_dwh.dws_sales_daily',
    qps24h: 0.12,
    calls24h: 10_482,
    p95: 56,
    success: 100,
    quota: { used: 42_108, total: 500_000 },
    spark: [8, 12, 10, 14, 12, 15, 14, 16, 17, 18, 16, 19],
    params: [],
  },
  {
    id: 'api-04',
    name: 'SKU 缺货率周报',
    path: '/v1/inventory/oos-weekly',
    desc: '各仓 × 品类 SKU 缺货率，含异常预警',
    status: 'published',
    version: 'v1.1',
    method: 'GET',
    owner: '王磊',
    createdAt: '2026-01-18',
    updatedAt: '5月22日',
    dataset: 'inventory_mysql.t_oos_daily',
    qps24h: 0.08,
    calls24h: 6_904,
    p95: 184,
    success: 98.4,
    quota: { used: 28_220, total: 500_000 },
    spark: [4, 5, 4, 6, 5, 7, 6, 8, 7, 9, 8, 10],
    params: [],
  },
  {
    id: 'api-05',
    name: 'NPS 月度分布',
    path: '/v1/customer/nps-monthly',
    desc: '按月聚合 NPS 评分与文本主题分类',
    status: 'testing',
    version: 'v0.3',
    method: 'GET',
    owner: '陈思',
    createdAt: '2026-05-12',
    updatedAt: '今天 09:42',
    dataset: 'electric_dwh.dws_nps_monthly',
    qps24h: 0.02,
    calls24h: 124,
    p95: 220,
    success: 96.8,
    quota: { used: 412, total: 50_000 },
    spark: [0, 0, 1, 1, 2, 3, 2, 4, 5, 6, 4, 8],
    params: [],
  },
  {
    id: 'api-06',
    name: '高价值用户名单',
    path: '/v1/users/vip-list',
    desc: '近 90 天累计消费 ¥500+ 的用户清单（脱敏）',
    status: 'draft',
    version: '草稿',
    method: 'POST',
    owner: 'Yan Lin',
    createdAt: '2026-05-22',
    updatedAt: '今天 16:08',
    dataset: 'electric_dwh.dws_user_value',
    qps24h: 0,
    calls24h: 0,
    p95: 0,
    success: 0,
    quota: { used: 0, total: 50_000 },
    spark: [0,0,0,0,0,0,0,0,0,0,0,0],
    params: [],
  },
  {
    id: 'api-07',
    name: '直播带货效果',
    path: '/v1/livestream/perf',
    desc: '主播 × 时段 × 品类的 GMV/UV/转化漏斗',
    status: 'paused',
    version: 'v1.0',
    method: 'GET',
    owner: '王磊',
    createdAt: '2026-02-04',
    updatedAt: '5月14日',
    dataset: 'electric_dwh.dws_live_perf',
    qps24h: 0,
    calls24h: 0,
    p95: 0,
    success: 0,
    quota: { used: 1_240, total: 50_000 },
    spark: [3, 4, 5, 3, 0, 0, 0, 0, 0, 0, 0, 0],
    params: [],
  },
];

function ApisScreen() {
  const [selected, setSelected] = useState(APIS[0].id);
  const [tab, setTab] = useState('overview');
  const [filter, setFilter] = useState('all');
  const [showPublish, setShowPublish] = useState(false);

  const filtered = APIS.filter(a => {
    if (filter === 'all') return true;
    return a.status === filter;
  });

  const api = APIS.find(a => a.id === selected) || APIS[0];

  return (
    <>
      <div className="api-wrap">
        {/* ─── KPI strip ─── */}
        <div className="api-kpi-strip">
          <div>
            <div className="api-kpi-label">已发布接口</div>
            <div className="api-kpi-val mono">{APIS.filter(a=>a.status==='published').length} <span className="text-3">/ {APIS.length}</span></div>
            <div className="api-kpi-hint">2 个草稿 · 1 个测试</div>
          </div>
          <div>
            <div className="api-kpi-label">24h 总调用</div>
            <div className="api-kpi-val mono">97,134</div>
            <div className="api-kpi-hint pos"><Icon name="arrow_up_right" style={{width: 11, height: 11}} />+12.4% vs 昨天</div>
          </div>
          <div>
            <div className="api-kpi-label">综合 P95 延迟</div>
            <div className="api-kpi-val mono">128<span className="text-3 mono" style={{fontSize: 13}}> ms</span></div>
            <div className="api-kpi-hint pos">SLO 内</div>
          </div>
          <div>
            <div className="api-kpi-label">成功率 (24h)</div>
            <div className="api-kpi-val mono">99.7<span className="text-3 mono" style={{fontSize: 13}}>%</span></div>
            <div className="api-kpi-hint">SLO 99.5%</div>
          </div>
          <div className="api-kpi-cta">
            <button className="btn primary" onClick={() => setShowPublish(true)}>
              <Icon name="plus" />从会话发布
            </button>
            <button className="btn ghost"><Icon name="book" />API 文档</button>
          </div>
        </div>

        <div className="api-body">
          {/* ─── Left: list ─── */}
          <div className="api-list-pane">
            <div className="api-list-head">
              <div className="api-list-tabs">
                {[
                  { id: 'all', label: '全部', count: APIS.length },
                  { id: 'published', label: '已发布', count: APIS.filter(a=>a.status==='published').length },
                  { id: 'testing', label: '测试中', count: APIS.filter(a=>a.status==='testing').length },
                  { id: 'draft', label: '草稿', count: APIS.filter(a=>a.status==='draft').length },
                  { id: 'paused', label: '已暂停', count: APIS.filter(a=>a.status==='paused').length },
                ].map(t => (
                  <button key={t.id} className={'api-list-tab ' + (filter===t.id?'active':'')} onClick={() => setFilter(t.id)}>
                    {t.label}<span className="count">{t.count}</span>
                  </button>
                ))}
              </div>
              <div className="search-bar" style={{height: 30, marginBottom: 0}}>
                <Icon name="search" />
                <input placeholder="搜索接口…" />
              </div>
            </div>

            <div className="api-list">
              {filtered.map(a => (
                <button key={a.id} className={'api-row ' + (selected === a.id ? 'active' : '')} onClick={() => setSelected(a.id)}>
                  <StatusDot status={a.status} />
                  <div className="api-row-body">
                    <div className="api-row-top">
                      <span className="api-row-name">{a.name}</span>
                      <span className="api-row-method mono">{a.method}</span>
                    </div>
                    <div className="api-row-path mono">{a.path}</div>
                    <div className="api-row-meta">
                      <span className="mono">{a.version}</span>
                      <span className="dot-sep">·</span>
                      <span className="mono">{a.calls24h.toLocaleString()} /24h</span>
                      <span className="dot-sep">·</span>
                      <span className="mono">{a.p95}ms</span>
                    </div>
                  </div>
                  <Sparkline points={a.spark.length ? a.spark : [0,0,0]} color={a.status === 'published' ? 'var(--accent)' : 'var(--text-4)'} w={56} h={22} />
                </button>
              ))}
            </div>
          </div>

          {/* ─── Right: detail ─── */}
          <div className="api-detail-pane">
            <ApiDetailHeader api={api} />

            <div className="api-detail-tabs">
              {[
                { id: 'overview', label: '概览' },
                { id: 'params',   label: '参数', count: api.params.length || 5 },
                { id: 'examples', label: '调用示例' },
                { id: 'logs',     label: '调用日志', count: 1_204 },
                { id: 'versions', label: '版本', count: 5 },
              ].map(t => (
                <button key={t.id} className={'api-tab ' + (tab === t.id ? 'active' : '')} onClick={() => setTab(t.id)}>
                  {t.label}
                  {t.count !== undefined && <span className="count">{t.count}</span>}
                </button>
              ))}
            </div>

            <div className="api-detail-body">
              {tab === 'overview' && <ApiOverview api={api} />}
              {tab === 'params'   && <ApiParams api={api} />}
              {tab === 'examples' && <ApiExamples api={api} />}
              {tab === 'logs'     && <ApiLogs />}
              {tab === 'versions' && <ApiVersions />}
            </div>
          </div>
        </div>
      </div>

      {showPublish && <PublishDrawer onClose={() => setShowPublish(false)} />}
    </>
  );
}

// ── helpers ─────────────────────────────────────────────────
function StatusDot({ status }) {
  const map = {
    published: { c: 'var(--pos)',  label: '已发布' },
    testing:   { c: 'var(--info)', label: '测试中' },
    draft:     { c: 'var(--text-4)', label: '草稿' },
    paused:    { c: 'var(--warn)', label: '已暂停' },
  };
  const m = map[status] || map.draft;
  return <span className="api-status-dot" title={m.label} style={{background: m.c}} />;
}

function StatusPill({ status }) {
  const map = {
    published: { c: 'var(--pos)',  label: '已发布', soft: 'var(--pos-soft)' },
    testing:   { c: 'var(--info)', label: '测试中', soft: 'oklch(0.6 0.14 220 / 0.10)' },
    draft:     { c: 'var(--text-3)', label: '草稿', soft: 'var(--surface-2)' },
    paused:    { c: 'var(--warn)', label: '已暂停', soft: 'oklch(0.65 0.15 60 / 0.12)' },
  };
  const m = map[status] || map.draft;
  return (
    <span className="api-status-pill" style={{color: m.c, background: m.soft, borderColor: m.c}}>
      <span className="dot" style={{background: m.c}} />
      {m.label}
    </span>
  );
}

function ApiDetailHeader({ api }) {
  return (
    <div className="api-detail-head">
      <div className="api-detail-title-row">
        <div>
          <div className="api-detail-name-row">
            <h2>{api.name}</h2>
            <StatusPill status={api.status} />
            <span className="api-version-tag mono">{api.version}</span>
          </div>
          <p className="api-detail-desc">{api.desc}</p>
        </div>
        <div className="api-detail-actions">
          {api.status === 'published'
            ? <button className="btn ghost"><Icon name="pause" />暂停</button>
            : <button className="btn primary"><Icon name="play" />发布</button>}
          <button className="btn ghost"><Icon name="branch" />新版本</button>
          <button className="btn ghost"><Icon name="share" />分享</button>
          <button className="icon-btn"><Icon name="more" /></button>
        </div>
      </div>

      <div className="api-endpoint-bar">
        <span className={'api-method method-' + api.method.toLowerCase()}>{api.method}</span>
        <span className="api-endpoint-url mono">https://api.datalogue.cn{api.path}</span>
        <button className="api-endpoint-copy"><Icon name="copy" />复制</button>
        <button className="api-endpoint-try"><Icon name="bolt" />试一下</button>
      </div>

      <div className="api-detail-stats">
        {[
          { label: '24h 调用',  val: api.calls24h.toLocaleString(), delta: '+8.4%', up: true },
          { label: '成功率',    val: api.success.toFixed(2) + '%', delta: '稳定', up: true },
          { label: 'P95 延迟', val: api.p95 + ' ms', delta: '−12ms', up: true },
          { label: 'QPS',      val: api.qps24h.toFixed(2), delta: '高峰 0.92', up: null },
          { label: '月配额',   val: pct(api.quota.used, api.quota.total), delta: api.quota.used.toLocaleString() + ' / ' + (api.quota.total/1000) + 'k', up: null },
        ].map((s, i) => (
          <div className="api-stat" key={i}>
            <div className="api-stat-label">{s.label}</div>
            <div className="api-stat-val mono">{s.val}</div>
            <div className={'api-stat-delta ' + (s.up === true ? 'up' : s.up === false ? 'down' : '')}>{s.delta}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function pct(used, total) {
  return ((used / total) * 100).toFixed(1) + '%';
}

// ── Overview ────────────────────────────────────────────────
function ApiOverview({ api }) {
  return (
    <div className="api-overview">
      <div className="api-overview-main">
        <SectionCard title="来源问题" icon="chat">
          <div className="api-source-q">"{api.question}"</div>
          <div className="api-source-meta">
            <span><Icon name="database" />{api.dataset}</span>
            <span><Icon name="user" />{api.owner}</span>
            <span><Icon name="calendar" />创建于 {api.createdAt}</span>
            <a href="#" className="api-source-link">查看原始会话 →</a>
          </div>
        </SectionCard>

        <SectionCard title="响应结构" icon="code">
          <pre className="api-schema mono">{`{
  "headline": "上周华东区销售下降12%，主要由女装品类拖累",
  "summary":  "归因总额 −¥520k，其中订单量贡献 −68%，客单价 +32%",
  "delta_pct": -12.0,
  "drivers": [
    { "name": "华东·女装",   "value": -260000, "share": 0.5 },
    { "name": "华南·美妆",   "value": -120000, "share": 0.23 },
    { "name": "订单量整体", "value":  -90000, "share": 0.17 }
  ],
  "chart_url": "https://api.datalogue.cn/v1/charts/abc123.png",
  "sql":       "/* see /v1/sales/weekly-attribution/sql */",
  "generated_at": "2026-05-25T16:42:00+08:00"
}`}</pre>
        </SectionCard>
      </div>

      <div className="api-overview-side">
        <SectionCard title="调用趋势 · 7天" icon="chart_line" compact>
          <CallTrend />
          <div className="api-trend-meta mono">
            <span>峰值 1,820 /h · 13:00</span>
            <span>低谷 42 /h · 04:00</span>
          </div>
        </SectionCard>

        <SectionCard title="健康度" icon="shield" compact>
          <div className="api-health-row">
            <span>可用性</span>
            <div className="api-health-bar"><span style={{width: '99.9%', background: 'var(--pos)'}} /></div>
            <span className="mono">99.9%</span>
          </div>
          <div className="api-health-row">
            <span>延迟 SLO</span>
            <div className="api-health-bar"><span style={{width: '96%', background: 'var(--pos)'}} /></div>
            <span className="mono">达成</span>
          </div>
          <div className="api-health-row">
            <span>错误率</span>
            <div className="api-health-bar"><span style={{width: '8%', background: 'var(--warn)'}} /></div>
            <span className="mono">0.08%</span>
          </div>
        </SectionCard>

        <SectionCard title="使用方" icon="plug" compact>
          {[
            { name: 'BI 仪表盘 (Prod)',  calls: '21,402', pct: 0.72 },
            { name: 'Slack /sales 命令', calls: '4,902',  pct: 0.17 },
            { name: '财务对账系统',      calls: '2,108',  pct: 0.07 },
            { name: '其他',              calls: '1,000',  pct: 0.04 },
          ].map((u, i) => (
            <div key={i} className="api-consumer-row">
              <span>{u.name}</span>
              <div className="api-consumer-bar"><span style={{width: (u.pct*100)+'%'}} /></div>
              <span className="mono text-3">{u.calls}</span>
            </div>
          ))}
        </SectionCard>
      </div>
    </div>
  );
}

function SectionCard({ title, icon, compact, children }) {
  return (
    <div className={'api-card ' + (compact ? 'compact' : '')}>
      <div className="api-card-head">
        <Icon name={icon} />
        <span>{title}</span>
      </div>
      <div className="api-card-body">{children}</div>
    </div>
  );
}

function CallTrend() {
  const data = [12, 18, 24, 30, 28, 36, 44, 52, 48, 58, 62, 70, 68, 72, 64, 50, 38, 30];
  const max = Math.max(...data);
  return (
    <svg viewBox="0 0 200 70" width="100%" height="70" preserveAspectRatio="none">
      <defs>
        <linearGradient id="trendg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.25" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {data.map((v, i) => {
        const x = (i / (data.length - 1)) * 200;
        const y = 65 - (v / max) * 60;
        return null;
      })}
      {(() => {
        const pts = data.map((v, i) => [(i / (data.length-1)) * 200, 65 - (v / max) * 60]);
        const path = pts.map(([x,y], i) => (i===0?'M':'L') + x.toFixed(1) + ' ' + y.toFixed(1)).join(' ');
        const area = path + ` L 200 65 L 0 65 Z`;
        return <>
          <path d={area} fill="url(#trendg)" />
          <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
        </>;
      })()}
    </svg>
  );
}

// ── Parameters ──────────────────────────────────────────────
function ApiParams({ api }) {
  const typeIcon = { enum: 'enum_list', string: 'string', number: 'number', boolean: 'bool' };
  return (
    <div className="api-params">
      <div className="api-params-toolbar">
        <div>
          <h3 style={{margin: '0 0 4px'}}>参数 · 抽取自原问题</h3>
          <p className="text-3" style={{margin: 0, fontSize: 12.5}}>数语在你发布时识别了 {api.params.length} 个变量。可设默认值、枚举与必填。</p>
        </div>
        <button className="btn ghost"><Icon name="plus" />添加参数</button>
      </div>

      <div className="api-params-table">
        <div className="api-params-th">
          <span>参数</span><span>类型</span><span>必填</span><span>默认值</span><span>说明</span><span></span>
        </div>
        {api.params.map((p, i) => (
          <div className="api-params-tr" key={i}>
            <span className="mono">{p.key}</span>
            <span className="api-type-cell">
              <Icon name={typeIcon[p.type] || 'string'} />
              <span className="mono">{p.type}</span>
            </span>
            <span><Toggle value={p.required} /></span>
            <span>
              {p.type === 'enum'
                ? <select className="st-input small" defaultValue={p.default}>{p.enums.map(e => <option key={e}>{e}</option>)}</select>
                : <input className="st-input small" defaultValue={p.default} />}
              {p.type === 'enum' && (
                <div className="api-enum-list mono">枚举：{p.enums.join(' · ')}</div>
              )}
            </span>
            <span className="text-3">{p.desc}</span>
            <span>
              <button className="icon-btn"><Icon name="more" /></button>
            </span>
          </div>
        ))}
      </div>

      <div className="api-params-source">
        <div className="api-params-source-head">
          <Icon name="brain" />原问题模板（占位符与上面的参数对应）
        </div>
        <div className="api-params-source-body">
          {tokenize(api.question)}
        </div>
      </div>
    </div>
  );
}

function tokenize(template) {
  const parts = template.split(/(\{[^}]+\})/g);
  return parts.map((p, i) =>
    p.startsWith('{') && p.endsWith('}')
      ? <span key={i} className="api-token-var mono">{p}</span>
      : <Fragment key={i}>{p}</Fragment>
  );
}

// ── Examples ────────────────────────────────────────────────
function ApiExamples({ api }) {
  const [lang, setLang] = useState('curl');
  const snippets = {
    curl: `curl -X ${api.method} 'https://api.datalogue.cn${api.path}?region=华东&compare_to=last_week&threshold=5' \\
  -H 'Authorization: Bearer dlg_live_••••••••••••f2a7' \\
  -H 'Accept: application/json'`,
    python: `from datalogue import Client

client = Client(api_key="dlg_live_••••••••••••f2a7")

result = client.call("${api.path}",
    region="华东",
    compare_to="last_week",
    threshold=5,
)

print(result.headline)
print(result.drivers)`,
    javascript: `import { Datalogue } from "@datalogue/sdk";

const dl = new Datalogue({ apiKey: process.env.DATALOGUE_KEY });

const result = await dl.call("${api.path}", {
  region: "华东",
  compare_to: "last_week",
  threshold: 5,
});

console.log(result.headline);
console.log(result.drivers);`,
    slack: `/sales 上周{region}销售归因 region:华东 threshold:5

→ 数语会自动调用 ${api.path}
   并把图表 + 摘要发到当前频道。`,
  };

  return (
    <div className="api-examples">
      <div className="api-ex-row">
        <div className="api-ex-pane">
          <div className="api-ex-lang-tabs">
            {[
              { id: 'curl',       label: 'cURL',       icon: 'code' },
              { id: 'python',     label: 'Python',     icon: 'code' },
              { id: 'javascript', label: 'JavaScript', icon: 'code' },
              { id: 'slack',      label: 'Slack 命令', icon: 'chat' },
            ].map(t => (
              <button key={t.id} className={'api-ex-lang ' + (lang === t.id ? 'active' : '')} onClick={() => setLang(t.id)}>
                <Icon name={t.icon} />{t.label}
              </button>
            ))}
            <button className="icon-btn" style={{marginLeft: 'auto'}}><Icon name="copy" /></button>
          </div>
          <pre className="api-ex-code mono">{snippets[lang]}</pre>
        </div>

        <div className="api-ex-pane">
          <div className="api-ex-resp-head">
            <span className="api-method method-200 mono">200 OK</span>
            <span className="text-3 mono">142 ms · application/json</span>
            <button className="icon-btn" style={{marginLeft: 'auto'}}><Icon name="copy" /></button>
          </div>
          <pre className="api-ex-code mono">{`{
  "headline": "上周华东区销售下降 12.0%，主要由女装品类拖累",
  "delta_pct": -12.0,
  "drivers": [
    {
      "name": "华东 · 女装",
      "value": -260000,
      "share": 0.50,
      "subdrivers": [
        { "name": "订单量",   "value": -210000, "share": 0.81 },
        { "name": "客单价",   "value":  -50000, "share": 0.19 }
      ]
    },
    {
      "name": "华南 · 美妆",
      "value": -120000,
      "share": 0.23
    }
  ],
  "chart_url": "https://api.datalogue.cn/v1/charts/abc123.png",
  "generated_at": "2026-05-25T16:42:00+08:00"
}`}</pre>
        </div>
      </div>

      <div className="api-ex-tip">
        <Icon name="bolt" />
        <div>
          <strong>试一下 →</strong> 在浏览器中打开
          <span className="mono"> {api.path}?region=华东&compare_to=last_week </span>
          直接看到 JSON，或访问
          <a href="#" className="api-link">/docs{api.path}</a> 调试器。
        </div>
      </div>
    </div>
  );
}

// ── Logs ────────────────────────────────────────────────────
function ApiLogs() {
  const logs = [
    { when: '11:24:02', caller: 'BI 仪表盘 (Prod)', token: 'dlg_live_•f2a7', status: 200, latency: 142, params: 'region=华东' },
    { when: '11:23:58', caller: 'BI 仪表盘 (Prod)', token: 'dlg_live_•f2a7', status: 200, latency: 138, params: 'region=华南' },
    { when: '11:23:14', caller: 'Slack /sales',     token: 'dlg_live_•f2a7', status: 200, latency: 102, params: 'region=华东&threshold=10' },
    { when: '11:22:01', caller: '财务对账系统',     token: 'dlg_live_•91c4', status: 200, latency: 188, params: 'region=华北' },
    { when: '11:18:42', caller: 'BI 仪表盘 (Prod)', token: 'dlg_live_•f2a7', status: 400, latency: 12,  params: 'region=未知区域', err: '参数 region 不在枚举范围内' },
    { when: '11:17:30', caller: 'BI 仪表盘 (Prod)', token: 'dlg_live_•f2a7', status: 200, latency: 144, params: 'region=华东' },
    { when: '11:15:08', caller: '本地开发 · YL',    token: 'dlg_test_•ab12', status: 200, latency: 220, params: 'region=华东&top_n=10' },
    { when: '11:12:55', caller: 'BI 仪表盘 (Prod)', token: 'dlg_live_•f2a7', status: 200, latency: 96,  params: '(默认参数)' },
    { when: '11:10:42', caller: 'BI 仪表盘 (Prod)', token: 'dlg_live_•f2a7', status: 504, latency: 5000,params: 'region=华东', err: '上游 ClickHouse 超时' },
    { when: '11:08:18', caller: 'BI 仪表盘 (Prod)', token: 'dlg_live_•f2a7', status: 200, latency: 132, params: 'region=华东' },
  ];
  return (
    <div className="api-logs">
      <div className="api-logs-toolbar">
        <div className="search-bar" style={{flex: 1, height: 30, marginBottom: 0}}><Icon name="search" /><input placeholder="搜索请求 ID、参数或错误…" /></div>
        <button className="btn ghost"><Icon name="calendar" />近1小时</button>
        <button className="btn ghost"><Icon name="filter_alt" />状态码</button>
        <button className="btn ghost"><Icon name="download" />导出</button>
      </div>

      <div className="api-logs-table">
        <div className="api-logs-th">
          <span>时间</span><span>调用方</span><span>密钥</span><span>状态</span><span>延迟</span><span>参数</span>
        </div>
        {logs.map((l, i) => (
          <div className={'api-logs-tr ' + (l.status >= 400 ? 'err' : '')} key={i}>
            <span className="mono text-3">{l.when}</span>
            <span>{l.caller}</span>
            <span className="mono text-3">{l.token}</span>
            <span>
              <span className={'api-status-code code-' + Math.floor(l.status/100)}>{l.status}</span>
            </span>
            <span className={'mono ' + (l.latency > 1000 ? 'neg' : '')}>{l.latency}ms</span>
            <span className="mono text-2">
              {l.params}
              {l.err && <span className="api-log-err">{l.err}</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Versions ────────────────────────────────────────────────
function ApiVersions() {
  const versions = [
    { v: 'v1.2', when: '今天 11:24', who: 'Yan Lin', current: true, summary: '增加 top_n 参数；归因结果加入子拆解 subdrivers 字段', diff: '+1 参数 · +1 响应字段', breaking: false },
    { v: 'v1.1', when: '5月12日',     who: 'Yan Lin', summary: '默认 threshold 从 10 → 5；优化拖累项排序逻辑', diff: '参数默认值变更', breaking: false },
    { v: 'v1.0', when: '2025-11-08',  who: 'Yan Lin', summary: '首次发布，从会话「上周华东销售为什么下降12%」归档', diff: '初始版本', breaking: false },
    { v: 'v0.3', when: '2025-11-05',  who: 'Yan Lin', summary: '内部测试，调整 region 枚举范围', diff: 'pre-release', breaking: true },
    { v: 'v0.1', when: '2025-11-02',  who: 'Yan Lin', summary: '草稿初始化', diff: 'draft', breaking: false },
  ];
  return (
    <div className="api-versions">
      <div className="api-versions-head">
        <h3 style={{margin: 0}}>版本历史</h3>
        <button className="btn"><Icon name="branch" />创建新版本</button>
      </div>
      <div className="api-versions-timeline">
        {versions.map((v, i) => (
          <div key={i} className={'api-version-item ' + (v.current ? 'current' : '')}>
            <div className="api-version-marker">
              <span className="api-version-dot" />
              <span className="api-version-line" />
            </div>
            <div className="api-version-content">
              <div className="api-version-row">
                <span className="api-version-tag mono">{v.v}</span>
                {v.current && <span className="api-version-current">当前版本</span>}
                {v.breaking && <span className="api-version-breaking">破坏性变更</span>}
                <span className="text-3" style={{marginLeft: 'auto'}}>{v.when} · {v.who}</span>
              </div>
              <div className="api-version-summary">{v.summary}</div>
              <div className="api-version-diff mono">{v.diff}</div>
              {!v.current && (
                <div className="api-version-actions">
                  <button className="btn ghost"><Icon name="diff" />对比当前</button>
                  <button className="btn ghost"><Icon name="history" />回滚到此版本</button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export { ApisScreen };
