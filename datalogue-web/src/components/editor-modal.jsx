import React, { useState, useEffect, useRef } from 'react';
import { Icon } from './icons';

// Editor Modal — global modal system, opened via openEditor(kind, data)
// Usage: <EditorModalHost /> in App root, then window.openEditor('metric', data)

const _listeners = new Set();
function openEditor(kind, data) { _listeners.forEach(fn => fn({ kind, data })); }
window.openEditor = openEditor;

function EditorModalHost() {
  const [state, setState] = useState(null);
  useEffect(() => {
    const fn = s => setState(s);
    _listeners.add(fn);
    return () => _listeners.delete(fn);
  }, []);
  if (!state) return null;
  return <EditorModal kind={state.kind} data={state.data} onClose={() => setState(null)} />;
}

// ── Config per kind ─────────────────────────────────────────────────────────
const EDITOR_CONFIG = {
  metric: {
    eyebrow: '语义治理 / 指标',
    getTitle: d => d ? '编辑指标 · ' + d.name : '新建指标',
    icon: 'formula', width: 620,
    getCta: d => d ? '保存修改' : '创建指标',
  },
  rule: {
    eyebrow: '知识库 / 业务规则',
    getTitle: d => d ? '编辑业务规则' : '新建业务规则',
    icon: 'book', width: 560,
    cta: '保存规则',
  },
  kb: {
    eyebrow: '知识库 / SQL 样例',
    getTitle: () => '新增知识库条目',
    icon: 'brain', width: 640,
    cta: '添加并向量化',
  },
  saved: {
    eyebrow: '收藏',
    getTitle: () => '新建收藏',
    icon: 'bookmark', width: 540,
    cta: '保存收藏',
  },
  folder: {
    eyebrow: '收藏',
    getTitle: () => '新建文件夹',
    icon: 'folder', width: 460,
    cta: '创建文件夹',
  },
  apikey: {
    eyebrow: '系统设置 / 开发者',
    getTitle: () => '创建 API 密钥',
    icon: 'key', width: 540,
    cta: '生成密钥',
  },
  member: {
    eyebrow: '系统设置 / 成员',
    getTitle: () => '邀请成员',
    icon: 'user', width: 520,
    cta: '发送邀请',
  },
  role: {
    eyebrow: '语义治理 / 行级权限',
    getTitle: () => '新建角色',
    icon: 'shield', width: 520,
    cta: '创建角色',
  },
  term: {
    eyebrow: '语义治理 / 业务术语',
    getTitle: () => '新增术语',
    icon: 'book', width: 520,
    cta: '保存术语',
  },
  webhook: {
    eyebrow: '系统设置 / 开发者',
    getTitle: () => '添加 Webhook',
    icon: 'plug', width: 540,
    cta: '添加 Webhook',
  },
};

// ── Editor Modal ─────────────────────────────────────────────────────────────
function EditorModal({ kind, data, onClose }) {
  const cfg = EDITOR_CONFIG[kind] || {};
  const [form, setForm] = useState({});
  const [step, setStep] = useState(0);

  useEffect(() => {
    // Initialize form with data or defaults
    const defaults = {};
    if (kind === 'metric') {
      defaults.name = data?.name || '';
      defaults.display_name = data?.display_name || '';
      defaults.expr = data?.expr || '';
      defaults.filter_sql = data?.filter_sql || '';
      defaults.synonyms = (data?.synonyms || []).join(', ');
      defaults.description = data?.description || '';
      defaults.owner = data?.owner || '';
    } else if (kind === 'term') {
      defaults.term = data?.term || '';
      defaults.definition = data?.definition || '';
      defaults.owner = data?.owner || '';
    } else if (kind === 'role') {
      defaults.name = data?.name || '';
      defaults.level = data?.level || 'read';
      defaults.desc = data?.desc || '';
    } else if (kind === 'member') {
      defaults.email = data?.email || '';
      defaults.role = data?.role || 'viewer';
    } else if (kind === 'apikey') {
      defaults.name = data?.name || '';
      defaults.env = data?.env || 'prod';
    } else if (kind === 'webhook') {
      defaults.url = data?.url || '';
      defaults.events = data?.events || [];
      defaults.secret = data?.secret || '';
    } else if (kind === 'kb') {
      defaults.sql = data?.sql || '';
      defaults.tags = (data?.tags || []).join(', ');
      defaults.dataset = data?.dataset || '';
    } else if (kind === 'rule') {
      defaults.name = data?.name || '';
      defaults.expr = data?.expr || '';
      defaults.desc = data?.desc || '';
    } else {
      defaults.name = data?.name || '';
    }
    setForm(defaults);
  }, [kind, data]);

  const update = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = () => {
    // TODO: call actual API based on kind
    console.log('Submit:', kind, form);
    onClose();
  };

  const title = cfg.getTitle ? cfg.getTitle(data) : cfg.title || kind;

  return (
    <div style={{position:'fixed', inset:0, background:'rgba(0,0,0,0.45)', zIndex:200, display:'flex', alignItems:'center', justifyContent:'center'}} onClick={onClose}>
      <div style={{width: cfg.width || 520, maxHeight:'85vh', overflow:'auto', background:'var(--bg)', borderRadius:14, border:'1px solid var(--hairline)', boxShadow:'var(--shadow-pop)'}} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={{display:'flex', alignItems:'center', gap:12, padding:'16px 20px', borderBottom:'1px solid var(--hairline)'}}>
          <div style={{width:32, height:32, borderRadius:8, background:'var(--accent-soft)', display:'flex', alignItems:'center', justifyContent:'center'}}>
            <Icon name={cfg.icon || 'code'} style={{width:15, height:15, color:'var(--accent)'}} />
          </div>
          <div>
            <div style={{fontSize:11, color:'var(--text-3)', marginBottom:2}}>{cfg.eyebrow}</div>
            <div style={{fontSize:15, fontWeight:600}}>{title}</div>
          </div>
          <button className="icon-btn" onClick={onClose} style={{marginLeft:'auto'}}><Icon name="x" /></button>
        </div>

        {/* Body */}
        <div style={{padding:'20px 24px'}}>
          {kind === 'metric' && <MetricForm form={form} update={update} data={data} />}
          {kind === 'term' && <TermForm form={form} update={update} />}
          {kind === 'role' && <RoleForm form={form} update={update} />}
          {kind === 'member' && <MemberForm form={form} update={update} />}
          {kind === 'apikey' && <ApiKeyForm form={form} update={update} />}
          {kind === 'webhook' && <WebhookForm form={form} update={update} />}
          {kind === 'kb' && <KbForm form={form} update={update} />}
          {kind === 'rule' && <RuleForm form={form} update={update} />}
          {kind === 'folder' && <FolderForm form={form} update={update} />}
          {kind === 'saved' && <SavedForm form={form} update={update} />}
        </div>

        {/* Footer */}
        <div style={{display:'flex', gap:10, padding:'16px 24px', borderTop:'1px solid var(--hairline)', justifyContent:'flex-end'}}>
          <button className="btn ghost" onClick={onClose}>取消</button>
          <button className="btn primary" onClick={handleSubmit}>{cfg.getCta ? cfg.getCta(data) : cfg.cta}</button>
        </div>
      </div>
    </div>
  );
}

// ── Metric Form ──────────────────────────────────────────────────────────────
function MetricForm({ form, update, data }) {
  return (
    <>
      <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:12}}>
        <EmField label="英文名 *" value={form.name} onChange={v => update('name', v)} placeholder="如: gmv" />
        <EmField label="显示名" value={form.display_name} onChange={v => update('display_name', v)} placeholder="如: 成交金额" />
      </div>
      <EmField label="计算公式 *" value={form.expr} onChange={v => update('expr', v)} placeholder="如: SUM(amount) 或 [GMV] / [订单数]" />
      <EmField label="过滤条件 (可选)" value={form.filter_sql} onChange={v => update('filter_sql', v)} placeholder="如: status = 'paid'" />
      <EmField label="同义词 (逗号分隔)" value={form.synonyms} onChange={v => update('synonyms', v)} placeholder="销售额,GMV,成交额" />
      <EmField label="负责人" value={form.owner} onChange={v => update('owner', v)} placeholder="如: 王雨晴 · 财务" />
      <EmField label="描述 (可选)" value={form.description} onChange={v => update('description', v)} placeholder="指标的业务含义和计算边界" />
      {form.tags && <EmTags label="标签" tags={form.tags} onChange={v => update('tags', v)} />}
    </>
  );
}

// ── Term Form ─────────────────────────────────────────────────────────────────
function TermForm({ form, update }) {
  return (
    <>
      <EmField label="术语名称 *" value={form.term} onChange={v => update('term', v)} placeholder="如: GMV" />
      <div style={{marginBottom:12}}>
        <label style={{display:'block', fontSize:12, color:'var(--text-2)', marginBottom:4}}>定义 *</label>
        <textarea value={form.definition} onChange={e => update('definition', e.target.value)} rows={3} placeholder="输入术语的业务定义…" style={{width:'100%', padding:'8px 10px', borderRadius:6, border:'1px solid var(--hairline)', background:'var(--surface)', color:'var(--text)', fontSize:13, resize:'vertical'}} />
      </div>
      <EmField label="负责人" value={form.owner} onChange={v => update('owner', v)} placeholder="如: 王雨晴" />
    </>
  );
}

// ── Role Form ─────────────────────────────────────────────────────────────────
function RoleForm({ form, update }) {
  return (
    <>
      <EmField label="角色名称 *" value={form.name} onChange={v => update('name', v)} placeholder="如: 区域运营" />
      <div style={{marginBottom:12}}>
        <label style={{display:'block', fontSize:12, color:'var(--text-2)', marginBottom:4}}>权限级别</label>
        <select value={form.level} onChange={e => update('level', e.target.value)} style={{width:'100%', padding:'8px 10px', borderRadius:6, border:'1px solid var(--hairline)', background:'var(--surface)', color:'var(--text)', fontSize:13}}>
          <option value="read">可读（全部数据集）</option>
          <option value="row">行级限制（按区域/部门筛选）</option>
          <option value="aggregate">仅聚合指标（屏蔽明细）</option>
          <option value="public">公开（脱敏数据）</option>
        </select>
      </div>
      <EmField label="描述" value={form.desc} onChange={v => update('desc', v)} placeholder="角色权限的详细说明" />
    </>
  );
}

// ── Member Form ─────────────────────────────────────────────────────────────
function MemberForm({ form, update }) {
  return (
    <>
      <EmField label="邮箱 *" value={form.email} onChange={v => update('email', v)} placeholder="zhangsan@company.com" type="email" />
      <div style={{marginBottom:12}}>
        <label style={{display:'block', fontSize:12, color:'var(--text-2)', marginBottom:4}}>角色</label>
        <select value={form.role} onChange={e => update('role', e.target.value)} style={{width:'100%', padding:'8px 10px', borderRadius:6, border:'1px solid var(--hairline)', background:'var(--surface)', color:'var(--text)', fontSize:13}}>
          <option value="viewer">查看者</option>
          <option value="editor">编辑者</option>
          <option value="admin">管理员</option>
        </select>
      </div>
    </>
  );
}

// ── ApiKey Form ─────────────────────────────────────────────────────────────
function ApiKeyForm({ form, update }) {
  return (
    <>
      <EmField label="密钥名称 *" value={form.name} onChange={v => update('name', v)} placeholder="如: 生产环境密钥" />
      <div style={{marginBottom:12}}>
        <label style={{display:'block', fontSize:12, color:'var(--text-2)', marginBottom:4}}>环境</label>
        <select value={form.env} onChange={e => update('env', e.target.value)} style={{width:'100%', padding:'8px 10px', borderRadius:6, border:'1px solid var(--hairline)', background:'var(--surface)', color:'var(--text)', fontSize:13}}>
          <option value="dev">开发环境</option>
          <option value="staging">预发环境</option>
          <option value="prod">生产环境</option>
        </select>
      </div>
      <div style={{padding:'10px 12px', background:'var(--warn-soft)', borderRadius:6, fontSize:12, color:'var(--warn)'}}>
        密钥仅在创建时显示一次，请妥善保存。
      </div>
    </>
  );
}

// ── Webhook Form ─────────────────────────────────────────────────────────────
function WebhookForm({ form, update }) {
  return (
    <>
      <EmField label="Webhook URL *" value={form.url} onChange={v => update('url', v)} placeholder="https://your-app.com/webhook" type="url" />
      <div style={{marginBottom:12}}>
        <label style={{display:'block', fontSize:12, color:'var(--text-2)', marginBottom:4}}>触发事件</label>
        <div style={{display:'flex', gap:8, flexWrap:'wrap'}}>
          {['query.done', 'query.err', 'review.pending', 'metric.updated'].map(ev => (
            <label key={ev} style={{display:'flex', alignItems:'center', gap:6, fontSize:12, cursor:'pointer'}}>
              <input type="checkbox" checked={form.events?.includes(ev)} onChange={e => {
                const cur = form.events || [];
                const next = e.target.checked ? [...cur, ev] : cur.filter(x => x !== ev);
                update('events', next);
              }} />
              <code style={{fontFamily:'var(--font-mono)', fontSize:11}}>{ev}</code>
            </label>
          ))}
        </div>
      </div>
      <EmField label="签名密钥 (可选)" value={form.secret} onChange={v => update('secret', v)} placeholder="用于校验请求来源" type="password" />
    </>
  );
}

// ── KB Form ──────────────────────────────────────────────────────────────────
function KbForm({ form, update }) {
  return (
    <>
      <div style={{marginBottom:12}}>
        <label style={{display:'block', fontSize:12, color:'var(--text-2)', marginBottom:4}}>SQL 样例 *</label>
        <textarea value={form.sql} onChange={e => update('sql', e.target.value)} rows={5} placeholder="SELECT region, SUM(amount) FROM orders WHERE ..." style={{width:'100%', padding:'8px 10px', borderRadius:6, border:'1px solid var(--hairline)', background:'var(--surface)', color:'var(--text)', fontSize:13, fontFamily:'var(--font-mono)', resize:'vertical'}} />
      </div>
      <EmField label="数据集" value={form.dataset} onChange={v => update('dataset', v)} placeholder="关联的数据集名称" />
      <EmField label="标签 (逗号分隔)" value={form.tags} onChange={v => update('tags', v)} placeholder="销售,区域,汇总" />
    </>
  );
}

// ── Rule Form ────────────────────────────────────────────────────────────────
function RuleForm({ form, update }) {
  return (
    <>
      <EmField label="规则名称 *" value={form.name} onChange={v => update('name', v)} placeholder="如: 销售额定义" />
      <EmField label="表达式 *" value={form.expr} onChange={v => update('expr', v)} placeholder="SUM(order_amount) WHERE status IN ('paid')" />
      <EmField label="描述" value={form.desc} onChange={v => update('desc', v)} placeholder="规则的适用范围和业务含义" />
    </>
  );
}

// ── Folder Form ──────────────────────────────────────────────────────────────
function FolderForm({ form, update }) {
  return (
    <>
      <EmField label="文件夹名称 *" value={form.name} onChange={v => update('name', v)} placeholder="如: 华东区分析" />
    </>
  );
}

// ── Saved Form ──────────────────────────────────────────────────────────────
function SavedForm({ form, update }) {
  return (
    <>
      <EmField label="收藏名称 *" value={form.name} onChange={v => update('name', v)} placeholder="如: 周度销售看板" />
    </>
  );
}

// ── Shared primitives ────────────────────────────────────────────────────────
function EmField({ label, value, onChange, type = 'text', placeholder = '' }) {
  return (
    <div style={{marginBottom:12}}>
      <label style={{display:'block', fontSize:12, color:'var(--text-2)', marginBottom:4}}>{label}</label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={{width:'100%', padding:'8px 10px', borderRadius:6, border:'1px solid var(--hairline)', background:'var(--surface)', color:'var(--text)', fontSize:13}} />
    </div>
  );
}

function EmTags({ label, tags, onChange }) {
  const [input, setInput] = useState('');
  const add = (t) => { if (t && !tags.includes(t)) onChange([...tags, t]); setInput(''); };
  const remove = (t) => onChange(tags.filter(x => x !== t));
  return (
    <div style={{marginBottom:12}}>
      <label style={{display:'block', fontSize:12, color:'var(--text-2)', marginBottom:4}}>{label}</label>
      <div style={{display:'flex', gap:6, flexWrap:'wrap', marginBottom:6}}>
        {tags.map(t => (
          <span key={t} style={{display:'flex', alignItems:'center', gap:4, padding:'2px 8px', borderRadius:4, background:'var(--accent-soft)', color:'var(--accent)', fontSize:12}}>
            {t}
            <button onClick={() => remove(t)} style={{background:'none', border:'none', cursor:'pointer', color:'inherit', padding:0, lineHeight:1}}>×</button>
          </span>
        ))}
        <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(input.trim()); } }} placeholder="添加标签…" style={{border:'none', outline:'none', fontSize:12, background:'transparent', minWidth:80}} />
      </div>
    </div>
  );
}

export { EditorModalHost, openEditor };