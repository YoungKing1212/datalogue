import React, { useState, useEffect } from 'react';
import { Icon } from './icons';
import {
  listDatasets,
  createDataset,
  listDatasetMetrics,
  createMetric,
  deleteMetric,
  listDatasetDimensions,
  createDimension,
  deleteDimension,
} from '../api/client';

// DatasetsScreen — 语义层管理：指标/维度/术语/权限/版本 5个 Tab

function DatasetsScreen() {
  const [tab, setTab] = useState('metrics');
  const [q, setQ] = useState('');
  const [datasets, setDatasets] = useState([]);
  const [activeDsId, setActiveDsId] = useState(null);
  const [loading, setLoading] = useState(false);

  // 指标/维度数据
  const [metrics, setMetrics] = useState([]);
  const [dimensions, setDimensions] = useState([]);

  // 表单状态
  const [showMetricForm, setShowMetricForm] = useState(false);
  const [showDimForm, setShowDimForm] = useState(false);
  const [metricForm, setMetricForm] = useState({ name: '', display_name: '', expr: '', filter_sql: '', synonyms: '', description: '' });
  const [dimForm, setDimForm] = useState({ name: '', display_name: '', column_name: '', enum_values: '', synonyms: '' });

  useEffect(() => {
    loadDatasets();
  }, []);

  useEffect(() => {
    if (activeDsId) {
      loadDsMeta(activeDsId);
    }
  }, [activeDsId]);

  const loadDatasets = () => {
    setLoading(true);
    listDatasets().then(setDatasets).catch(console.error).finally(() => setLoading(false));
  };

  const loadDsMeta = async (dsId) => {
    try {
      const [ms, ds] = await Promise.all([listDatasetMetrics(dsId), listDatasetDimensions(dsId)]);
      setMetrics(ms);
      setDimensions(ds);
    } catch (err) { console.error(err); }
  };

  const activeDs = datasets.find(d => d.id === activeDsId) || datasets[0];
  const currentDsId = activeDsId || activeDs?.id;

  const handleAddMetric = async () => {
    if (!metricForm.name || !metricForm.expr) { alert('请填写指标名和表达式'); return; }
    if (!currentDsId) { alert('请先选择数据集'); return; }
    try {
      await createMetric(currentDsId, { ...metricForm, synonyms: metricForm.synonyms ? metricForm.synonyms.split(',').map(s => s.trim()) : [] });
      setShowMetricForm(false);
      setMetricForm({ name: '', display_name: '', expr: '', filter_sql: '', synonyms: '', description: '' });
      loadDsMeta(currentDsId);
    } catch (err) { alert('添加失败: ' + err.message); }
  };

  const handleDelMetric = async (mid) => {
    if (!confirm('确定删除？')) return;
    try { await deleteMetric(currentDsId, mid); loadDsMeta(currentDsId); } catch (err) { alert(err.message); }
  };

  const handleAddDim = async () => {
    if (!dimForm.name || !dimForm.column_name) { alert('请填写维度名和字段名'); return; }
    if (!currentDsId) { alert('请先选择数据集'); return; }
    try {
      await createDimension(currentDsId, { ...dimForm, synonyms: dimForm.synonyms ? dimForm.synonyms.split(',').map(s => s.trim()) : [], enum_values: dimForm.enum_values ? dimForm.enum_values.split(',').map(s => s.trim()) : [] });
      setShowDimForm(false);
      setDimForm({ name: '', display_name: '', column_name: '', enum_values: '', synonyms: '' });
      loadDsMeta(currentDsId);
    } catch (err) { alert('添加失败: ' + err.message); }
  };

  const handleDelDim = async (did) => {
    if (!confirm('确定删除？')) return;
    try { await deleteDimension(currentDsId, did); loadDsMeta(currentDsId); } catch (err) { alert(err.message); }
  };

  const metricStates = ['ok', 'draft', 'conflict'];
  const stateLabel = { ok: '已上线', draft: '草稿', conflict: '冲突' };

  const tabs = [
    { id: 'metrics',    label: '指标',     icon: 'formula', count: metrics.length },
    { id: 'dimensions', label: '维度',     icon: 'layers',  count: dimensions.length },
    { id: 'glossary',   label: '业务术语', icon: 'book',    count: 65 },
    { id: 'permission', label: '行级权限', icon: 'shield',  count: 12 },
    { id: 'versions',    label: '版本历史', icon: 'history', count: null },
  ];

  return (
    <div className="ds-wrap">
      <div style={{display: 'grid', gridTemplateColumns: '220px 1fr', gap: 28}}>
        {/* 左侧边栏 */}
        <aside style={{paddingTop: 10}}>
          <div style={{fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', padding: '0 8px 8px', fontWeight: 500}}>数据集</div>
          {datasets.map(d => (
            <button key={d.id} onClick={() => { setActiveDsId(d.id); loadDsMeta(d.id); }}
              style={{display:'flex', alignItems:'center', gap:10, padding:'7px 10px', fontSize:13, borderRadius:6, width:'100%', textAlign:'left', cursor:'pointer', background:activeDsId === d.id || (!activeDsId && d === activeDs) ? 'var(--surface-2)' : 'transparent', color:activeDsId === d.id || (!activeDsId && d === activeDs) ? 'var(--text)' : 'var(--text-2)', border:'none'}}>
              <span style={{width:8, height:8, borderRadius:'50%', background:'var(--accent)', flexShrink:0}} />
              <span style={{flex:1}}>{d.name}</span>
              <span style={{fontSize:10.5, color:'var(--text-3)', fontFamily:'var(--font-mono)'}}>{d.id}</span>
            </button>
          ))}
          {datasets.length === 0 && !loading && (
            <div style={{padding:'16px 8px', fontSize:12, color:'var(--text-3)'}}>暂无数据集</div>
          )}
          <button style={{display:'flex', alignItems:'center', gap:6, padding:'6px 10px', fontSize:12, color:'var(--text-3)', background:'none', border:'none', cursor:'pointer', marginTop:4}}>
            <Icon name="plus" style={{width:12, height:12}} />新建数据集
          </button>

          <div style={{fontSize:11, color:'var(--text-3)', textTransform:'uppercase', letterSpacing:'0.08em', padding:'14px 8px 8px', fontWeight:500}}>分类</div>
          {[{icon:'formula', label:'计算指标', count:38}, {icon:'database', label:'原子指标', count:8}].map(item => (
            <button key={item.label} style={{display:'flex', alignItems:'center', gap:10, padding:'7px 10px', fontSize:13, borderRadius:6, width:'100%', textAlign:'left', cursor:'pointer', background:'transparent', color:'var(--text-2)', border:'none'}}>
              <Icon name={item.icon} style={{width:14, height:14}} />
              <span>{item.label}</span>
              <span style={{marginLeft:'auto', fontSize:11, color:'var(--text-3)', fontFamily:'var(--font-mono)'}}>{item.count}</span>
            </button>
          ))}

          <div style={{fontSize:11, color:'var(--text-3)', textTransform:'uppercase', letterSpacing:'0.08em', padding:'14px 8px 8px', fontWeight:500}}>状态</div>
          {[{color:'var(--pos)', label:'已上线', count:38}, {color:'var(--warn)', label:'草稿', count:8}].map(item => (
            <button key={item.label} style={{display:'flex', alignItems:'center', gap:10, padding:'7px 10px', fontSize:13, borderRadius:6, width:'100%', textAlign:'left', cursor:'pointer', background:'transparent', color:'var(--text-2)', border:'none'}}>
              <span style={{width:6, height:6, borderRadius:'50%', background:item.color}} />
              <span>{item.label}</span>
              <span style={{marginLeft:'auto', fontSize:11, color:'var(--text-3)', fontFamily:'var(--font-mono)'}}>{item.count}</span>
            </button>
          ))}
        </aside>

        {/* 右侧主区 */}
        <div>
          <div style={{display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom: 22}}>
            <div>
              <div style={{display:'flex', alignItems:'center', gap:8, marginBottom:4}}>
                {activeDs && <span style={{width:8, height:8, borderRadius:'50%', background:'var(--accent)'}} />}
                <span style={{fontSize:12, color:'var(--text-3)'}}>语义治理 / 数据集</span>
              </div>
              <h1 style={{fontSize:22, fontWeight:500, margin:'0 0 4px', letterSpacing:'-0.02em'}}>{activeDs?.name || '数据集 & 指标'}</h1>
              <p style={{color:'var(--text-3)', fontSize:13, margin:0}}>数语在生成 SQL 时会优先匹配这里的定义。同义词、版本和行级权限是保证回答口径一致与合规的关键。</p>
            </div>
            <div style={{display:'flex', gap:8}}>
              <button className="btn ghost"><Icon name="upload" />导入 YAML</button>
              <button className="btn primary" onClick={() => tab === 'metrics' ? setShowMetricForm(true) : tab === 'dimensions' ? setShowDimForm(true) : null}>
                <Icon name="plus" />新建
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div style={{display:'flex', gap:4, borderBottom:'1px solid var(--hairline)', marginBottom:18}}>
            {tabs.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                padding:'8px 12px', fontSize:13, cursor:'pointer', border:'none', background:'none',
                color: tab === t.id ? 'var(--text)' : 'var(--text-3)',
                borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
                display:'flex', alignItems:'center', gap:6,
              }}>
                <Icon name={t.icon} />
                {t.label}
                {t.count !== null && <span style={{fontSize:11, color:'var(--text-4)', fontFamily:'var(--font-mono)'}}>{t.count}</span>}
              </button>
            ))}
          </div>

          {tab === 'metrics'    && <MetricsTab metrics={metrics} q={q} setQ={setQ} onDel={handleDelMetric} />}
          {tab === 'dimensions' && <DimensionsTab dimensions={dimensions} q={q} setQ={setQ} onDel={handleDelDim} />}
          {tab === 'glossary'   && <GlossaryTab q={q} setQ={setQ} />}
          {tab === 'permission' && <PermissionTab />}
          {tab === 'versions'   && <VersionsTab />}
        </div>
      </div>

      {/* 添加指标弹窗 */}
      {showMetricForm && (
        <div style={{position:'fixed', inset:0, background:'rgba(0,0,0,0.4)', zIndex:101, display:'flex', alignItems:'center', justifyContent:'center'}} onClick={() => setShowMetricForm(false)}>
          <div style={{background:'var(--bg)', borderRadius:12, padding:24, width:480, border:'1px solid var(--hairline)'}} onClick={e => e.stopPropagation()}>
            <h3 style={{margin:'0 0 16px'}}>添加指标</h3>
            <FormField label="英文名" value={metricForm.name} onChange={v => setMetricForm({...metricForm, name: v})} placeholder="如: gmv" />
            <FormField label="显示名" value={metricForm.display_name} onChange={v => setMetricForm({...metricForm, display_name: v})} placeholder="如: 成交金额" />
            <FormField label="表达式" value={metricForm.expr} onChange={v => setMetricForm({...metricForm, expr: v})} placeholder="如: SUM(amount)" />
            <FormField label="过滤 SQL (可选)" value={metricForm.filter_sql} onChange={v => setMetricForm({...metricForm, filter_sql: v})} />
            <FormField label="同义词 (逗号分隔)" value={metricForm.synonyms} onChange={v => setMetricForm({...metricForm, synonyms: v})} placeholder="销售额,GMV" />
            <FormField label="描述 (可选)" value={metricForm.description} onChange={v => setMetricForm({...metricForm, description: v})} />
            <div style={{display:'flex', gap:10, marginTop:16, justifyContent:'flex-end'}}>
              <button className="btn ghost" onClick={() => setShowMetricForm(false)}>取消</button>
              <button className="btn primary" onClick={handleAddMetric}>添加</button>
            </div>
          </div>
        </div>
      )}

      {/* 添加维度弹窗 */}
      {showDimForm && (
        <div style={{position:'fixed', inset:0, background:'rgba(0,0,0,0.4)', zIndex:101, display:'flex', alignItems:'center', justifyContent:'center'}} onClick={() => setShowDimForm(false)}>
          <div style={{background:'var(--bg)', borderRadius:12, padding:24, width:480, border:'1px solid var(--hairline)'}} onClick={e => e.stopPropagation()}>
            <h3 style={{margin:'0 0 16px'}}>添加维度</h3>
            <FormField label="英文名" value={dimForm.name} onChange={v => setDimForm({...dimForm, name: v})} placeholder="如: region" />
            <FormField label="显示名" value={dimForm.display_name} onChange={v => setDimForm({...dimForm, display_name: v})} placeholder="如: 区域" />
            <FormField label="字段名" value={dimForm.column_name} onChange={v => setDimForm({...dimForm, column_name: v})} placeholder="如: region_code" />
            <FormField label="枚举值 (逗号分隔)" value={dimForm.enum_values} onChange={v => setDimForm({...dimForm, enum_values: v})} placeholder="华北,华东,华南" />
            <FormField label="同义词 (逗号分隔)" value={dimForm.synonyms} onChange={v => setDimForm({...dimForm, synonyms: v})} placeholder="地区,省份" />
            <div style={{display:'flex', gap:10, marginTop:16, justifyContent:'flex-end'}}>
              <button className="btn ghost" onClick={() => setShowDimForm(false)}>取消</button>
              <button className="btn primary" onClick={handleAddDim}>添加</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Metrics Tab ─────────────────────────────────────────────
function MetricsTab({ metrics, q, setQ, onDel }) {
  const [expanded, setExpanded] = useState(null);

  const mockMetrics = [
    { id: 1, name: 'GMV', display_name: '成交金额', desc: '商品交易总额（含未支付）', formula: 'SUM(orders.gross_amount)', synonyms: ['销售额', '成交额'], owner: '王雨晴·财务', ver: 'v3.2', state: 'ok', type: 'calc', hits: 4218 },
    { id: 2, name: '订单数', display_name: '订单数', desc: '已支付订单去重数量', formula: 'COUNT(DISTINCT order_id)', synonyms: ['单量', 'order count'], owner: '张磊·BI', ver: 'v2.1', state: 'ok', type: 'raw', hits: 3142 },
    { id: 3, name: '客单价', display_name: '客单价', desc: 'GMV / 订单数', formula: '[GMV] / [订单数]', synonyms: ['AOV', '平均订单金额'], owner: '王雨晴·财务', ver: 'v1.4', state: 'ok', type: 'calc', hits: 2418 },
    { id: 4, name: '复购率', display_name: '复购率', desc: '过去30天有2单及以上用户比例', formula: 'repeat_users_30d / total_users_30d', synonyms: ['回购率'], owner: '李婷·增长', ver: 'v0.9', state: 'draft', type: 'calc', hits: 218, conflict: true },
  ];
  const displayMetrics = metrics.length > 0 ? metrics : mockMetrics;
  const filtered = displayMetrics.filter(m => !q || m.name.includes(q) || m.synonyms?.some(s => s.includes(q)) || m.desc?.includes(q));

  return (
    <div>
      <div className="search-bar" style={{marginBottom:14}}>
        <Icon name="search" />
        <input placeholder="搜索指标名 / 同义词 / 公式…" value={q} onChange={e => setQ(e.target.value)} style={{flex:1, background:'transparent', border:'none', outline:'none', fontSize:13}} />
        <span style={{fontSize:11, color:'var(--text-3)', fontFamily:'var(--font-mono)'}}>⌘ F</span>
      </div>

      <div style={{border:'1px solid var(--hairline)', borderRadius:8, overflow:'hidden'}}>
        <div style={{display:'grid', gridTemplateColumns:'28px 1.4fr 0.8fr 1.2fr 100px 80px 48px', alignItems:'center', padding:'8px 12px', fontSize:11, color:'var(--text-3)', borderBottom:'1px solid var(--hairline)', background:'var(--bg-2)'}}>
          <span></span>
          <span>指标名称</span>
          <span>同义词</span>
          <span>计算公式</span>
          <span>负责人</span>
          <span>版本/状态</span>
          <span></span>
        </div>
        {filtered.map(m => (
          <div key={m.id || m.name}>
            <div onClick={() => setExpanded(expanded === (m.id || m.name) ? null : (m.id || m.name))}
              style={{display:'grid', gridTemplateColumns:'28px 1.4fr 0.8fr 1.2fr 100px 80px 48px', alignItems:'center', padding:'10px 12px', fontSize:13, cursor:'pointer', borderBottom:'1px solid var(--hairline)', background: expanded === (m.id || m.name) ? 'var(--bg-2)' : 'var(--surface)'}}>
              <div style={{width:22, height:22, borderRadius:4, background: m.type === 'calc' ? 'var(--accent-soft)' : 'var(--bg-2)', display:'flex', alignItems:'center', justifyContent:'center'}}>
                <Icon name={m.type === 'calc' ? 'formula' : 'database'} style={{width:12, height:12, color:'var(--accent)'}} />
              </div>
              <div>
                <div style={{fontWeight:500}}>{m.name}</div>
                <div style={{fontSize:11, color:'var(--text-3)'}}>{m.desc}</div>
              </div>
              <div style={{display:'flex', gap:4, flexWrap:'wrap'}}>
                {(m.synonyms || []).slice(0, 3).map(s => <span key={s} style={{fontSize:10.5, padding:'1px 6px', borderRadius:4, background:'var(--bg-2)', color:'var(--text-2)'}}>{s}</span>)}
              </div>
              <div>
                <code style={{fontSize:12, color:'var(--accent)'}}>{m.formula}</code>
              </div>
              <div style={{fontSize:12, color:'var(--text-2)'}}>{m.owner}</div>
              <div style={{display:'flex', alignItems:'center', gap:6}}>
                <span style={{fontFamily:'var(--font-mono)', fontSize:11}}>{m.ver}</span>
                <span style={{fontSize:10, padding:'1px 6px', borderRadius:4, background: m.state === 'ok' ? 'var(--pos-soft)' : 'var(--warn-soft)', color: m.state === 'ok' ? 'var(--pos)' : 'var(--warn)'}}>
                  {m.state === 'ok' ? '已上线' : '草稿'}
                </span>
              </div>
              <button className="icon-btn" style={{color:'var(--neg)'}} onClick={(e) => { e.stopPropagation(); onDel(m.id); }}><Icon name="trash" /></button>
            </div>
            {expanded === (m.id || m.name) && (
              <div style={{padding:'12px 16px', background:'var(--bg-2)', borderBottom:'1px solid var(--hairline)', fontSize:12}}>
                <div style={{marginBottom:8}}><span style={{color:'var(--text-3)'}}>命中:</span> {m.hits} 次 · <span style={{color:'var(--text-3)'}}>冲突:</span> {m.conflict ? '是（口径不一致）' : '无'}</div>
                <code style={{fontSize:12, color:'var(--accent)', background:'var(--surface)', padding:'4px 8px', borderRadius:4}}>{m.formula}</code>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Dimensions Tab ───────────────────────────────────────────
function DimensionsTab({ dimensions, q, setQ, onDel }) {
  const mockDims = [
    { id: 1, name: 'region', display_name: '区域', column_name: 'region_code', enum_values: ['华北', '华东', '华南', '西南'], synonyms: ['地区', '省份'], owner: '王雨晴', state: 'ok' },
    { id: 2, name: 'category', display_name: '品类', column_name: 'category_id', enum_values: ['服饰', '美妆', '家电', '食品'], synonyms: ['类目', '商品分类'], owner: '张磊', state: 'ok' },
    { id: 3, name: 'store', display_name: '店铺', column_name: 'store_id', enum_values: null, synonyms: ['门店', '商店'], owner: '李婷', state: 'ok' },
  ];
  const displayDims = dimensions.length > 0 ? dimensions : mockDims;
  const filtered = displayDims.filter(d => !q || d.name.includes(q) || d.display_name.includes(q));

  return (
    <div>
      <div className="search-bar" style={{marginBottom:14}}>
        <Icon name="search" />
        <input placeholder="搜索维度名 / 字段…" value={q} onChange={e => setQ(e.target.value)} style={{flex:1, background:'transparent', border:'none', outline:'none', fontSize:13}} />
      </div>
      <div style={{display:'flex', flexDirection:'column', gap:8}}>
        {filtered.map(d => (
          <div key={d.id || d.name} style={{padding:12, background:'var(--surface)', border:'1px solid var(--hairline)', borderRadius:8, display:'flex', alignItems:'center', gap:12}}>
            <div style={{width:28, height:28, borderRadius:6, background:'var(--accent-soft)', display:'flex', alignItems:'center', justifyContent:'center'}}>
              <Icon name="layers" style={{width:14, height:14, color:'var(--accent)'}} />
            </div>
            <div style={{flex:1}}>
              <div style={{fontWeight:500, fontSize:14}}>{d.display_name} <span style={{fontFamily:'var(--font-mono)', fontSize:12, color:'var(--text-3)'}}>({d.name})</span></div>
              <div style={{fontSize:11, color:'var(--text-3)', marginTop:2}}>字段: <code style={{color:'var(--accent)'}}>{d.column_name}</code> · {d.owner}</div>
            </div>
            {d.enum_values && (
              <div style={{display:'flex', gap:4, flexWrap:'wrap'}}>
                {(d.enum_values).map(v => <span key={v} style={{fontSize:10.5, padding:'1px 6px', borderRadius:4, background:'var(--bg-2)', color:'var(--text-2)'}}>{v}</span>)}
              </div>
            )}
            <span style={{fontSize:10, padding:'1px 6px', borderRadius:4, background: d.state === 'ok' ? 'var(--pos-soft)' : 'var(--warn-soft)', color: d.state === 'ok' ? 'var(--pos)' : 'var(--warn)'}}>
              {d.state === 'ok' ? '已上线' : '草稿'}
            </span>
            <button className="icon-btn" style={{color:'var(--neg)'}} onClick={() => onDel(d.id)}><Icon name="trash" /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Glossary Tab ─────────────────────────────────────────────
function GlossaryTab({ q, setQ }) {
  const terms = [
    { term: 'GMV', definition: '商品交易总额，指已完成支付的所有订单金额总和，含退款订单。', owner: '王雨晴', updated: '2025-11-08' },
    { term: 'AOV', definition: '平均订单金额，GMV / 订单数。', owner: '王雨晴', updated: '2025-09-22' },
    { term: 'CVR', definition: '转化率，完成付款用户 / 访客数。', owner: '李婷', updated: '2025-10-04' },
    { term: 'ROAS', definition: '广告回报率，广告带来的 GMV / 广告花费。', owner: '陈昊', updated: '2025-12-15' },
  ];
  const filtered = terms.filter(t => !q || t.term.includes(q) || t.definition.includes(q));

  return (
    <div>
      <div className="search-bar" style={{marginBottom:14}}>
        <Icon name="search" />
        <input placeholder="搜索业务术语…" value={q} onChange={e => setQ(e.target.value)} style={{flex:1, background:'transparent', border:'none', outline:'none', fontSize:13}} />
      </div>
      <div style={{display:'flex', flexDirection:'column', gap:10}}>
        {filtered.map(t => (
          <div key={t.term} style={{padding:14, background:'var(--surface)', border:'1px solid var(--hairline)', borderRadius:8}}>
            <div style={{display:'flex', alignItems:'center', gap:8, marginBottom:6}}>
              <span style={{fontWeight:600, fontSize:14, fontFamily:'var(--font-mono)', color:'var(--accent)'}}>{t.term}</span>
              <span style={{fontSize:11, color:'var(--text-3)'}}>{t.owner} · {t.updated}</span>
            </div>
            <p style={{fontSize:13, color:'var(--text-2)', margin:0, lineHeight:1.5}}>{t.definition}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Permission Tab ────────────────────────────────────────────
function PermissionTab() {
  const roles = [
    { name: '数据分析师', desc: '可查询所有数据集，限制敏感字段', level: 'read', users: 12 },
    { name: '区域运营', desc: '仅可看本区域（华东/华南/华北/西南）数据', level: 'row', users: 34 },
    { name: '高管', desc: '仅可看聚合指标，屏蔽店铺级明细', level: 'aggregate', users: 5 },
    { name: '外部合作方', desc: '仅可看脱敏后的公开指标', level: 'public', users: 8 },
  ];

  return (
    <div>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16}}>
        <h3 style={{margin:0, fontSize:15, fontWeight:500}}>行级权限</h3>
        <button className="btn primary" style={{height:28, fontSize:12}}><Icon name="plus" />新建角色</button>
      </div>
      <div style={{display:'flex', flexDirection:'column', gap:10}}>
        {roles.map(r => (
          <div key={r.name} style={{display:'flex', alignItems:'center', gap:14, padding:14, background:'var(--surface)', border:'1px solid var(--hairline)', borderRadius:8}}>
            <div style={{width:36, height:36, borderRadius:8, background:'var(--bg-2)', display:'flex', alignItems:'center', justifyContent:'center'}}>
              <Icon name="shield" style={{width:16, height:16, color:'var(--accent)'}} />
            </div>
            <div style={{flex:1}}>
              <div style={{fontWeight:500, fontSize:14}}>{r.name}</div>
              <div style={{fontSize:12, color:'var(--text-3)', marginTop:2}}>{r.desc}</div>
            </div>
            <div style={{display:'flex', alignItems:'center', gap:8}}>
              <span style={{fontSize:10, padding:'2px 8px', borderRadius:4, background:'var(--accent-soft)', color:'var(--accent)', fontFamily:'var(--font-mono)'}}>{r.level}</span>
              <span style={{fontSize:12, color:'var(--text-3)'}}>{r.users} 人</span>
            </div>
            <button className="btn ghost" style={{height:28, fontSize:12}}>编辑</button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Versions Tab ─────────────────────────────────────────────
function VersionsTab() {
  const history = [
    { ver: 'v3.2', when: '2025-11-08', who: '王雨晴', note: '增加退款剔除逻辑，与财务口径对齐', metric: 'GMV' },
    { ver: 'v3.1', when: '2025-10-15', who: '张磊', note: '修正 region 映射错误，新增华南区', metric: 'GMV' },
    { ver: 'v3.0', when: '2025-09-01', who: '王雨晴', note: '口径升级：gross_amount → net_amount', metric: 'GMV' },
    { ver: 'v2.9', when: '2025-08-12', who: '李婷', note: '新增复购率指标定义（草稿）', metric: '复购率' },
    { ver: 'v2.1', when: '2025-06-20', who: '张磊', note: '订单数排除取消订单', metric: '订单数' },
  ];

  return (
    <div>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16}}>
        <h3 style={{margin:0, fontSize:15, fontWeight:500}}>版本历史</h3>
        <button className="btn ghost" style={{height:28, fontSize:12}}><Icon name="download" />导出</button>
      </div>
      <div style={{border:'1px solid var(--hairline)', borderRadius:8, overflow:'hidden'}}>
        <div style={{display:'grid', gridTemplateColumns:'80px 100px 80px 1fr', padding:'8px 14px', fontSize:11, color:'var(--text-3)', background:'var(--bg-2)', borderBottom:'1px solid var(--hairline)'}}>
          <span>版本</span><span>时间</span><span>操作人</span><span>变更说明</span>
        </div>
        {history.map(h => (
          <div key={h.ver} style={{display:'grid', gridTemplateColumns:'80px 100px 80px 1fr', padding:'10px 14px', fontSize:13, borderBottom:'1px solid var(--hairline)', alignItems:'center'}}>
            <span style={{fontFamily:'var(--font-mono)', color:'var(--accent)', fontSize:12}}>{h.ver}</span>
            <span style={{fontSize:12, color:'var(--text-3)'}}>{h.when}</span>
            <span style={{fontSize:12}}>{h.who}</span>
            <div>
              <span style={{fontSize:12, padding:'1px 6px', borderRadius:4, background:'var(--bg-2)', color:'var(--text-2)', marginRight:8}}>{h.metric}</span>
              <span style={{fontSize:12, color:'var(--text-2)'}}>{h.note}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Shared ───────────────────────────────────────────────────
function FormField({ label, type = 'text', value, onChange, options = [], placeholder = '' }) {
  return (
    <div style={{marginBottom:12}}>
      <label style={{display:'block', fontSize:12, color:'var(--text-2)', marginBottom:4}}>{label}</label>
      {type === 'select' ? (
        <select value={value} onChange={e => onChange(e.target.value)} style={{width:'100%', padding:'8px 10px', borderRadius:6, border:'1px solid var(--hairline)', background:'var(--surface)', color:'var(--text)', fontSize:13}}>
          {options.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={{width:'100%', padding:'8px 10px', borderRadius:6, border:'1px solid var(--hairline)', background:'var(--surface)', color:'var(--text)', fontSize:13}} />
      )}
    </div>
  );
}

export { DatasetsScreen };