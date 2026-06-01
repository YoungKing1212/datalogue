import React, { useState } from 'react';
import { Icon } from './icons';

// KnowledgeScreen — 知识库 + 审核队列 (review queue)
// isReview mode = initialTab === 'queue'

function KnowledgeScreen({ initialTab }) {
  const [tab, setTab] = useState(initialTab || 'sql');
  const isReview = initialTab === 'queue';

  const tabs = [
    { id: 'queue',  label: '审核队列',  icon: 'check',    count: 5,  dot: true },
    { id: 'sql',    label: 'SQL 样例库', icon: 'code',    count: 234 },
    { id: 'rules',  label: '业务规则',   icon: 'book',    count: 28 },
    { id: 'ddl',    label: 'DDL 管理',  icon: 'database', count: 142 },
  ];

  return (
    <div className="kb-wrap" style={{padding: 24}}>
      {/* Header */}
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24}}>
        <div>
          <h1 style={{margin: '0 0 6px', fontSize: 22, fontWeight: 500}}>{isReview ? '审核队列' : '知识库'}</h1>
          <p style={{color: 'var(--text-3)', fontSize: 13, margin: 0}}>
            {isReview
              ? '数据团队在此审核用户与 AI 生成的 SQL。通过后写入向量库，构成自学习闭环。'
              : 'RAG 检索的底座。审核后的 SQL 样例 + DDL + 业务规则 → 下次同类问题自动命中。'}
          </p>
        </div>
        <div style={{display: 'flex', gap: 8}}>
          {isReview ? (
            <>
              <button className="btn ghost"><Icon name="user" />指派规则</button>
              <button className="btn primary"><Icon name="check" />批量通过</button>
            </>
          ) : (
            <>
              <button className="btn ghost"><Icon name="upload" />批量导入</button>
              <button className="btn"><Icon name="download" />导出向量库</button>
              <button className="btn primary"><Icon name="plus" />新增条目</button>
            </>
          )}
        </div>
      </div>

      {/* KPI Strip */}
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 24}}>
        {[
          { label: '本月新入库', val: '42', unit: '条', hint: '+18 vs 上月', pos: true },
          { label: '命中率 (近7天)', val: '87.4', unit: '%', hint: '+3.2pp', pos: true },
          { label: '平均检索延迟', val: '38', unit: 'ms', hint: 'pgvector · HNSW' },
          { label: '向量库大小', val: '12.4', unit: 'k', hint: 'bge-large-zh-v1.5' },
          { label: '待审核', val: '5', unit: '', hint: '最久等待 12 小时', warn: true },
        ].map(s => (
          <div key={s.label} style={{padding: 12, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 8, ...(s.warn ? {borderColor: 'var(--warn)', borderWidth: 1.5} : {})}}>
            <div style={{fontSize: 11, color: 'var(--text-3)', marginBottom: 4}}>{s.label}</div>
            <div style={{fontSize: 20, fontWeight: 600, fontFamily: 'var(--font-mono)', color: s.warn ? 'var(--warn)' : 'var(--text)'}}>{s.val}<span style={{fontSize: 11, color: 'var(--text-3)'}}>{s.unit}</span></div>
            <div style={{fontSize: 11, color: s.pos ? 'var(--pos)' : 'var(--text-3)', marginTop: 2}}>{s.hint}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid var(--hairline)'}}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: '8px 16px', border: 'none', background: 'none', cursor: 'pointer', fontSize: 13,
            color: tab === t.id ? 'var(--accent)' : 'var(--text-2)',
            borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <Icon name={t.icon} />
            {t.label}
            <span style={{fontSize: 11, padding: '1px 6px', borderRadius: 4, background: 'var(--bg-2)', color: 'var(--text-3)'}}>{t.count}</span>
            {t.dot && tab !== t.id && <span style={{width: 6, height: 6, borderRadius: '50%', background: 'var(--neg)'}} />}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === 'queue' && <ReviewQueue />}
      {tab === 'sql' && <SqlLibrary />}
      {tab === 'rules' && <BusinessRules />}
      {tab === 'ddl' && <DdlManagement />}
    </div>
  );
}

// ── 审核队列 ─────────────────────────────────────────────

function ReviewQueue() {
  const items = [
    { id: 'r1', q: '华东区上月各品类销售额同环比', ds: '交易数据集', status: 'pending', conf: 0.78, score: 'B', owner: '王磊', when: '12分钟前' },
    { id: 'r2', q: '为什么 DAU 下降？拆解渠道和品类', ds: '用户行为集', status: 'pending', conf: 0.65, score: 'C', owner: null, when: '2小时前' },
    { id: 'r3', q: '高价值用户的复购周期分析', ds: '交易数据集', status: 'pending', conf: 0.91, score: 'A', owner: '吴明', when: '3小时前' },
    { id: 'r4', q: '库存不足 SKU 按城市统计', ds: '供应链数据集', status: 'pending', conf: 0.72, score: 'B', owner: null, when: '5小时前' },
    { id: 'r5', q: '明天哪些 SKU 需要补货', ds: '供应链数据集', status: 'err', conf: 0.41, score: 'C', owner: null, when: '1天前' },
  ];

  return (
    <div>
      {items.map(item => (
        <div key={item.id} style={{
          padding: 16, background: 'var(--surface)', border: '1px solid var(--hairline)',
          borderRadius: 8, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 16
        }}>
          <div style={{width: 40, textAlign: 'center'}}>
            <div style={{fontSize: 11, color: 'var(--text-3)'}}>置信</div>
            <div style={{fontSize: 18, fontWeight: 600, color: item.conf > 0.8 ? 'var(--pos)' : item.conf > 0.6 ? 'var(--warn)' : 'var(--neg)'}}>{Math.round(item.conf * 100)}</div>
          </div>
          <div style={{width: 24, height: 24, borderRadius: 4, background: item.score === 'A' ? 'var(--pos-soft)' : item.score === 'B' ? 'var(--warn-soft)' : 'var(--neg-soft)', color: item.score === 'A' ? 'var(--pos)' : item.score === 'B' ? 'var(--warn)' : 'var(--neg)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700}}>
            {item.score}
          </div>
          <div style={{flex: 1}}>
            <div style={{fontWeight: 500, fontSize: 14, marginBottom: 4}}>{item.q}</div>
            <div style={{fontSize: 12, color: 'var(--text-3)'}}>{item.ds} · {item.owner || '未指派'} · {item.when}</div>
          </div>
          <div style={{display: 'flex', gap: 8}}>
            <button className="btn ghost" style={{height: 28, fontSize: 12}}><Icon name="eye" />查看</button>
            <button className="btn ghost" style={{height: 28, fontSize: 12, color: 'var(--pos)'}}><Icon name="check" />通过</button>
            <button className="btn ghost" style={{height: 28, fontSize: 12, color: 'var(--neg)'}}><Icon name="x" />拒绝</button>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── SQL 样例库 ────────────────────────────────────────────

function SqlLibrary() {
  const items = [
    { id: 1, sql: 'SELECT region, SUM(amount) FROM orders WHERE dt >= :start GROUP BY region ORDER BY SUM(amount) DESC', tags: ['销售', '区域', '汇总'], ds: '交易数据集', hits: 128, owner: '王磊', rating: 5 },
    { id: 2, sql: 'SELECT user_id, COUNT(*) as orders, AVG(amount) as avg_order FROM orders WHERE status = \'paid\' GROUP BY user_id HAVING COUNT(*) > 5', tags: ['用户', '复购', 'RFM'], ds: '交易数据集', hits: 89, owner: '吴明', rating: 4 },
    { id: 3, sql: 'SELECT channel, SUM(revenue) FROM marketing WHERE dt >= :start GROUP BY channel ORDER BY SUM(revenue) DESC', tags: ['营销', '渠道', '收入'], ds: '财务数据集', hits: 67, owner: '王磊', rating: 5 },
  ];

  return (
    <div>
      <div style={{display: 'grid', gridTemplateColumns: '1fr 80px 80px 60px', gap: 12, padding: '8px 12px', fontSize: 11, color: 'var(--text-3)', borderBottom: '1px solid var(--hairline)', marginBottom: 8}}>
        <span>SQL 样例</span>
        <span>数据集</span>
        <span>命中</span>
        <span>操作</span>
      </div>
      {items.map(item => (
        <div key={item.id} style={{padding: '12px', background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 6, marginBottom: 8}}>
          <div style={{fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent)', marginBottom: 8, padding: 8, background: 'var(--bg-2)', borderRadius: 4}}>{item.sql}</div>
          <div style={{display: 'flex', alignItems: 'center', gap: 8, fontSize: 12}}>
            <span style={{color: 'var(--text-2)'}}>{item.ds}</span>
            {item.tags.map(tag => <span key={tag} style={{padding: '1px 6px', borderRadius: 4, background: 'var(--bg-2)', color: 'var(--text-3)', fontSize: 11}}>{tag}</span>)}
            <span style={{marginLeft: 'auto', color: 'var(--text-3)'}}>{item.hits}次命中 · {item.owner}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── 业务规则 ──────────────────────────────────────────────

function BusinessRules() {
  const rules = [
    { id: 1, name: '销售额定义', kind: '指标口径', expr: 'SUM(order_amount) WHERE status IN (\'paid\', \'completed\')', desc: '排除已退款和已取消订单，仅统计实际付款成功的金额' },
    { id: 2, name: '活跃用户定义', kind: '用户圈选', expr: 'COUNT(DISTINCT user_id) WHERE event_type IN (\'purchase\', \'browse\', \'cart\')', desc: '30天内有任何购买/浏览/加购行为的用户' },
    { id: 3, name: '新客户定义', kind: '用户圈选', expr: 'FIRST_ORDER_USER WHERE first_order_dt >= :start', desc: '在统计周期内完成首单的 用户' },
  ];

  return (
    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12}}>
      {rules.map(r => (
        <div key={r.id} style={{padding: 16, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 8}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8}}>
            <span style={{fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--accent-soft)', color: 'var(--accent)'}}>{r.kind}</span>
            <span style={{fontWeight: 600, fontSize: 14}}>{r.name}</span>
          </div>
          <code style={{fontSize: 12, color: 'var(--accent)', display: 'block', marginBottom: 8, padding: 6, background: 'var(--bg-2)', borderRadius: 4}}>{r.expr}</code>
          <p style={{fontSize: 12, color: 'var(--text-3)', margin: 0}}>{r.desc}</p>
        </div>
      ))}
    </div>
  );
}

// ── DDL 管理 ──────────────────────────────────────────────

function DdlManagement() {
  const tables = [
    { name: 'orders', cols: 12, ds: '交易数据集', sync: 'synced' },
    { name: 'order_items', cols: 18, ds: '交易数据集', sync: 'synced' },
    { name: 'users', cols: 8, ds: '用户行为集', sync: 'synced' },
    { name: 'products', cols: 15, ds: '交易数据集', sync: 'synced' },
  ];

  return (
    <div>
      {tables.map(t => (
        <div key={t.name} style={{display: 'flex', alignItems: 'center', gap: 12, padding: 12, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 6, marginBottom: 6}}>
          <Icon name="table" />
          <code style={{fontFamily: 'var(--font-mono)', fontSize: 13, flex: 1}}>{t.name}</code>
          <span style={{fontSize: 11, color: 'var(--text-3)'}}>{t.cols} 列 · {t.ds}</span>
          <span style={{fontSize: 11, padding: '2px 8px', borderRadius: 4, background: 'var(--pos-soft)', color: 'var(--pos)'}}>已同步</span>
        </div>
      ))}
    </div>
  );
}

export { KnowledgeScreen };