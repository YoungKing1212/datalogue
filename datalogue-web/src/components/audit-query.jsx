import React, { useState } from 'react';
import { Icon } from './icons';

// AuditQueryScreen — 查询审计：node 级执行 trace，可标记修正写入知识库

const AUDIT_NODES = [
  { id: 'nl',     label: 'NL 输入',     icon: 'chat' },
  { id: 'lead',   label: 'LeadAgent',  icon: 'brain' },
  { id: 'intent', label: '意图识别',    icon: 'sparkle' },
  { id: 'schema', label: 'Schema 召回', icon: 'database' },
  { id: 'dsl',    label: 'DSL 生成',    icon: 'code' },
  { id: 'verify', label: 'DSL 校验',    icon: 'check' },
  { id: 'sql',    label: 'SQL 编译',    icon: 'code' },
  { id: 'exec',   label: '执行',        icon: 'bolt' },
  { id: 'report', label: '报告',        icon: 'chart_bar' },
];

const STATUS_COLOR = { done: 'var(--pos)', err: 'var(--neg)', retry: 'var(--warn)', clarify: 'var(--warn)', skipped: 'var(--text-3)' };

function AuditQueryScreen() {
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState('all');

  const logs = [
    {
      id: '#q-9b41', q: '分析华东区上月各品类销售额，和去年同期对比', user: 'Yan Lin', when: '今天 14:32', status: 'ok',
      path: 'Simple', dataset: '交易数据集', total: 1186, rows: 6, ms: 1176,
      trace: [
        { id: 'nl',     status: 'done', ms: 0 },
        { id: 'lead',   status: 'done', ms: 8,    note: '分类: Simple' },
        { id: 'intent', status: 'done', ms: 12 },
        { id: 'schema', status: 'done', ms: 38, hits: 4 },
        { id: 'dsl',    status: 'done', ms: 820 },
        { id: 'verify', status: 'done', ms: 2 },
        { id: 'sql',    status: 'done', ms: 4 },
        { id: 'exec',   status: 'done', ms: 302 },
        { id: 'report', status: 'done', ms: 0 },
      ],
    },
    {
      id: '#q-9b40', q: '为什么华东订单量下降这么多？拆解到品类和子类', user: 'Yan Lin', when: '今天 14:28', status: 'ok',
      path: 'Complex', dataset: '交易数据集', total: 4218, rows: 18, ms: 4222,
      trace: [
        { id: 'nl',     status: 'done', ms: 0 },
        { id: 'lead',   status: 'done', ms: 18,  note: '拆解为 3 个子任务' },
        { id: 'intent', status: 'done', ms: 28, sub: 3 },
        { id: 'schema', status: 'done', ms: 92 },
        { id: 'dsl',    status: 'done', ms: 1640, sub: 3 },
        { id: 'verify', status: 'done', ms: 4 },
        { id: 'sql',    status: 'done', ms: 12, sub: 3 },
        { id: 'exec',   status: 'done', ms: 1820, note: '并行执行' },
        { id: 'report', status: 'done', ms: 604, note: '综合解读' },
      ],
    },
    {
      id: '#q-9b3e', q: '明天库存不足的 SKU 有哪些', user: 'lisi', when: '今天 11:04', status: 'err',
      path: 'Simple → Failed', dataset: '供应链数据集', total: 2402, rows: 0, ms: 2402, errMsg: 'DSL 校验失败：未来时间过滤词「明天」无法应用于历史事实表 t_inventory_daily',
      trace: [
        { id: 'nl',     status: 'done', ms: 0 },
        { id: 'lead',   status: 'done', ms: 6 },
        { id: 'intent', status: 'done', ms: 14 },
        { id: 'schema', status: 'done', ms: 36 },
        { id: 'dsl',    status: 'done', ms: 902 },
        { id: 'verify', status: 'err',  ms: 12, note: '时间词与表性质不匹配' },
        { id: 'sql',    status: 'skipped', ms: 0 },
        { id: 'exec',   status: 'skipped', ms: 0 },
        { id: 'report', status: 'skipped', ms: 0 },
      ],
    },
  ];

  const filtered = filter === 'all' ? logs : logs.filter(l => l.status === filter.replace('err', 'err').replace('ok', 'ok'));

  return (
    <div style={{padding: 24}}>
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24}}>
        <div>
          <h1 style={{margin: '0 0 6px', fontSize: 22, fontWeight: 500}}>查询审计</h1>
          <p style={{color: 'var(--text-3)', fontSize: 13, margin: 0}}>NL → LeadAgent → 意图 → Schema → DSL → 校验 → SQL → 执行 → 报告 全链路追踪</p>
        </div>
      </div>

      {/* KPI Strip */}
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 24}}>
        {[
          { label: '今日查询', val: '284', unit: '次' },
          { label: '成功率', val: '96.8', unit: '%', pos: true },
          { label: 'P95 延迟', val: '1.2', unit: 's' },
          { label: '复杂拆解率', val: '18%', unit: '' },
          { label: '待修正', val: '3', unit: '', warn: true },
        ].map(s => (
          <div key={s.label} style={{padding: 12, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 8}}>
            <div style={{fontSize: 11, color: 'var(--text-3)', marginBottom: 4}}>{s.label}</div>
            <div style={{fontSize: 20, fontWeight: 600, fontFamily: 'var(--font-mono)', color: s.warn ? 'var(--warn)' : 'var(--text)'}}>{s.val}<span style={{fontSize: 11, color: 'var(--text-3)'}}>{s.unit}</span></div>
          </div>
        ))}
      </div>

      <div style={{display: 'flex', gap: 20}}>
        {/* 左侧: 列表 */}
        <div style={{width: 360, flexShrink: 0}}>
          {/* Filter tabs */}
          <div style={{display: 'flex', gap: 4, marginBottom: 12}}>
            {[
              { id: 'all', label: '全部' },
              { id: 'ok', label: '成功' },
              { id: 'err', label: '失败' },
              { id: 'complex', label: '复杂' },
            ].map(f => (
              <button key={f.id} onClick={() => setFilter(f.id)} style={{
                padding: '4px 10px', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12,
                background: filter === f.id ? 'var(--accent-soft)' : 'var(--surface)',
                color: filter === f.id ? 'var(--accent)' : 'var(--text-2)',
              }}>{f.label}</button>
            ))}
          </div>

          {filtered.map(log => (
            <div key={log.id} onClick={() => setSelected(log)} style={{
              padding: 12, background: 'var(--surface)', border: '1px solid var(--hairline)',
              borderRadius: 8, marginBottom: 8, cursor: 'pointer',
              borderColor: selected?.id === log.id ? 'var(--accent)' : 'var(--hairline)',
            }}>
              <div style={{display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6}}>
                <span style={{fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)'}}>{log.id}</span>
                <span style={{fontSize: 10, padding: '1px 6px', borderRadius: 4, background: log.status === 'ok' ? 'var(--pos-soft)' : 'var(--neg-soft)', color: log.status === 'ok' ? 'var(--pos)' : 'var(--neg)'}}>
                  {log.status === 'ok' ? '成功' : '失败'}
                </span>
              </div>
              <div style={{fontSize: 13, fontWeight: 500, marginBottom: 4}}>{log.q}</div>
              <div style={{fontSize: 11, color: 'var(--text-3)'}}>{log.user} · {log.when} · {log.path} · {log.total} 结果 · {log.ms}ms</div>
            </div>
          ))}
        </div>

        {/* 右侧: 详情 */}
        {selected ? (
          <div style={{flex: 1, minWidth: 0}}>
            <div style={{marginBottom: 16}}>
              <h3 style={{margin: '0 0 8px', fontSize: 15}}>{selected.q}</h3>
              <div style={{fontSize: 12, color: 'var(--text-3)'}}>{selected.user} · {selected.when} · {selected.dataset}</div>
            </div>

            {/* Trace Grid */}
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(9, 1fr)', gap: 4, marginBottom: 20}}>
              {selected.trace.map(node => {
                const def = AUDIT_NODES.find(n => n.id === node.id);
                return (
                  <div key={node.id} style={{textAlign: 'center', padding: '8px 4px', background: 'var(--surface)', borderRadius: 6, border: '1px solid ' + (STATUS_COLOR[node.status] || 'var(--hairline)')}}>
                    <div style={{fontSize: 16, marginBottom: 4, opacity: 0.6}}><Icon name={def?.icon || 'circle'} /></div>
                    <div style={{fontSize: 10, fontWeight: 600, marginBottom: 2}}>{def?.label || node.id}</div>
                    <div style={{fontSize: 11, color: STATUS_COLOR[node.status] || 'var(--text-3)'}}>
                      {node.status === 'done' ? `${node.ms}ms` : node.status === 'err' ? '失败' : node.status === 'retry' ? '重试' : '跳过'}
                    </div>
                    {node.note && <div style={{fontSize: 9, color: 'var(--text-3)', marginTop: 2}}>{node.note}</div>}
                  </div>
                );
              })}
            </div>

            {/* Error message if failed */}
            {selected.errMsg && (
              <div style={{padding: 12, background: 'var(--neg-soft)', border: '1px solid var(--neg)', borderRadius: 8, marginBottom: 16}}>
                <div style={{fontSize: 12, fontWeight: 600, color: 'var(--neg)', marginBottom: 4}}>错误信息</div>
                <div style={{fontSize: 12, color: 'var(--neg)'}}>{selected.errMsg}</div>
                <button className="btn" style={{marginTop: 8, height: 28, fontSize: 12}}>
                  <Icon name="book" /> 标记修正 → 写入知识库
                </button>
              </div>
            )}

            {/* Artifacts */}
            <div style={{padding: 16, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 8}}>
              <div style={{fontSize: 13, fontWeight: 600, marginBottom: 12}}>NL → DSL → SQL</div>
              <div style={{marginBottom: 12}}>
                <div style={{fontSize: 11, color: 'var(--text-3)', marginBottom: 4}}>用户问题 (NL)</div>
                <div style={{fontSize: 12, padding: 8, background: 'var(--bg-2)', borderRadius: 4}}>{selected.q}</div>
              </div>
              <div style={{marginBottom: 12}}>
                <div style={{fontSize: 11, color: 'var(--text-3)', marginBottom: 4}}>DSL 语义</div>
                <code style={{fontSize: 12, display: 'block', padding: 8, background: 'var(--bg-2)', borderRadius: 4, fontFamily: 'var(--font-mono)', color: 'var(--accent)'}}>
                  {selected.path === 'Complex' ? 'multi_relation_split{ relations: [orders, order_items, products] }' : 'simple_agg{ metric: "sales", group_by: ["region", "category"] }'}
                </code>
              </div>
              <div>
                <div style={{fontSize: 11, color: 'var(--text-3)', marginBottom: 4}}>生成 SQL</div>
                <code style={{fontSize: 12, display: 'block', padding: 8, background: 'var(--bg-2)', borderRadius: 4, fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', color: 'var(--text)'}}>
                  {selected.status === 'err'
                    ? '-- SQL 生成失败\n-- ' + (selected.errMsg || '未知错误')
                    : selected.path === 'Complex'
                    ? 'SELECT ... FROM orders o\nJOIN order_items oi ON o.id = oi.order_id\nJOIN products p ON oi.product_id = p.id\nGROUP BY o.region, p.category'
                    : 'SELECT region, category, SUM(amount) FROM orders\nWHERE dt >= date_trunc(\'month\', NOW()) - interval \'1\' month\nGROUP BY region, category'}
                </code>
              </div>
            </div>
          </div>
        ) : (
          <div style={{flex: 1, padding: 48, textAlign: 'center', color: 'var(--text-3)', background: 'var(--surface)', borderRadius: 8, border: '1px dashed var(--hairline)'}}>
            <Icon name="log" style={{fontSize: 32, marginBottom: 8, opacity: 0.4}} />
            <div>选择左侧查询记录查看详情</div>
          </div>
        )}
      </div>
    </div>
  );
}

export { AuditQueryScreen };