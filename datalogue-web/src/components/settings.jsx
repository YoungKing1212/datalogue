import React, { useState } from 'react';
import { Icon } from './icons';

// Settings — account, workspace, model, integrations, API keys.

function SettingsScreen() {
  const [section, setSection] = useState('account');

  const groups = [
    { title: '个人', items: [
      { id: 'account',   label: '账号与个人资料', icon: 'user_circle' },
      { id: 'notify',    label: '通知',          icon: 'bell' },
      { id: 'appearance',label: '外观',          icon: 'swatch' },
    ]},
    { title: '工作区', items: [
      { id: 'workspace', label: '工作区设置', icon: 'preset' },
      { id: 'members',   label: '成员与权限', icon: 'user' },
      { id: 'usage',     label: '用量 & 计费', icon: 'chart_bar' },
    ]},
    { title: '数据与模型', items: [
      { id: 'datasources', label: '数据源',     icon: 'database' },
      { id: 'models',      label: 'LLM 模型',  icon: 'brain' },
      { id: 'glossary',    label: '业务词典',   icon: 'book' },
    ]},
    { title: '开发者', items: [
      { id: 'apikeys',     label: 'API 密钥',   icon: 'key' },
      { id: 'webhooks',    label: 'Webhooks',  icon: 'plug' },
      { id: 'audit',       label: '审计日志',   icon: 'log' },
    ]},
  ];

  return (
    <div className="st-wrap">
      <div className="st-sidebar">
        {groups.map(g => (
          <div key={g.title}>
            <div className="group-title">{g.title}</div>
            {g.items.map(i => (
              <button key={i.id} className={'sb-item ' + (section === i.id ? 'active' : '')} onClick={() => setSection(i.id)}>
                <Icon name={i.icon} />
                <span>{i.label}</span>
              </button>
            ))}
          </div>
        ))}
      </div>

      <div className="st-main">
        {section === 'account'    && <AccountSection />}
        {section === 'notify'     && <NotifySection />}
        {section === 'appearance' && <AppearanceSection />}
        {section === 'workspace'  && <WorkspaceSection />}
        {section === 'members'    && <MembersSection />}
        {section === 'usage'      && <UsageSection />}
        {section === 'datasources'&& <DatasourcesSection />}
        {section === 'models'     && <ModelsSection />}
        {section === 'glossary'   && <GlossarySection />}
        {section === 'apikeys'    && <ApiKeysSection />}
        {section === 'webhooks'   && <WebhooksSection />}
        {section === 'audit'      && <AuditSection />}
      </div>
    </div>
  );
}

// ── Reusable settings primitives ────────────────────────────────
function SetSection({ title, desc, children }) {
  return (
    <section className="st-section">
      <h2>{title}</h2>
      {desc && <p className="desc">{desc}</p>}
      {children}
    </section>
  );
}
function SetRow({ label, hint, control, danger }) {
  return (
    <div className={'st-row ' + (danger ? 'danger' : '')}>
      <div className="st-row-l">
        <div className="st-row-label">{label}</div>
        {hint && <div className="st-row-hint">{hint}</div>}
      </div>
      <div className="st-row-r">{control}</div>
    </div>
  );
}
function Toggle({ value, onChange }) {
  return (
    <button className={'st-toggle ' + (value ? 'on' : '')} onClick={() => onChange && onChange(!value)}>
      <span className="st-toggle-knob" />
    </button>
  );
}

// ── Sections ────────────────────────────────────────────────────
function AccountSection() {
  return (
    <>
      <SetSection title="账号与个人资料" desc="这些信息会显示给团队其他成员。">
        <div className="st-card">
          <div className="st-profile">
            <div className="avatar lg">YL</div>
            <div className="st-profile-info">
              <div className="st-profile-name">Yan Lin</div>
              <div className="st-profile-email">yan.lin@datalogue.cn</div>
              <div className="st-profile-org">运营 · 华东区 · Datalogue 工作区</div>
            </div>
            <button className="btn ghost"><Icon name="upload" />更换头像</button>
          </div>
        </div>

        <div className="st-form">
          <SetRow label="姓名" hint="显示在会话与协作中" control={<input className="st-input" defaultValue="Yan Lin" />} />
          <SetRow label="邮箱" hint="登录与通知地址" control={<input className="st-input" defaultValue="yan.lin@datalogue.cn" />} />
          <SetRow label="语言" control={
            <select className="st-input">
              <option>简体中文</option><option>English</option><option>日本語</option>
            </select>} />
          <SetRow label="时区" control={
            <select className="st-input">
              <option>Asia/Shanghai (UTC+8)</option><option>America/Los_Angeles</option>
            </select>} />
        </div>
      </SetSection>

      <SetSection title="安全">
        <div className="st-form">
          <SetRow label="密码" hint="上次更新于 2025-04-12"
            control={<button className="btn ghost">修改密码</button>} />
          <SetRow label="两步验证 (2FA)" hint="使用 Authenticator App 增强账号安全"
            control={<Toggle value={true} />} />
          <SetRow label="活跃会话" hint="3 台设备登录中"
            control={<button className="btn ghost">查看 →</button>} />
        </div>
      </SetSection>

      <SetSection title="危险操作">
        <div className="st-form">
          <SetRow danger label="导出我的数据" hint="可下载所有问数会话、收藏、接口配置的 JSON 归档"
            control={<button className="btn ghost"><Icon name="download" />导出</button>} />
          <SetRow danger label="删除账号" hint="不可恢复。所有会话与你创建的接口将被永久删除"
            control={<button className="btn danger"><Icon name="trash" />删除</button>} />
        </div>
      </SetSection>
    </>
  );
}

function NotifySection() {
  const [s, setS] = useState({ dailyDigest: true, weekly: true, mentions: true, apiAlert: true, apiQuota: false, slack: true, email: false });
  return (
    <SetSection title="通知" desc="选择你想在哪些渠道收到通知。">
      <div className="st-form">
        <div className="st-notify-head">
          <span></span>
          <span>站内</span>
          <span>邮件</span>
          <span>Slack</span>
        </div>
        {[
          { k: 'dailyDigest', label: '每日数据摘要', hint: '每天 09:00，收藏的指标日变化' },
          { k: 'weekly',      label: '周度复盘',     hint: '每周一 09:00 自动发送' },
          { k: 'mentions',    label: '协作 @我',     hint: '有人在会话或看板中提到你' },
          { k: 'apiAlert',    label: '接口异常告警', hint: '已发布接口报错或超时' },
          { k: 'apiQuota',    label: '接口用量预警', hint: '调用量达到配额 80%' },
        ].map(row => (
          <div className="st-notify-row" key={row.k}>
            <div>
              <div className="st-row-label">{row.label}</div>
              <div className="st-row-hint">{row.hint}</div>
            </div>
            <Toggle value={s[row.k]} onChange={v => setS({...s, [row.k]: v})} />
            <Toggle value={false} />
            <Toggle value={s.slack && row.k !== 'apiQuota'} />
          </div>
        ))}
      </div>
    </SetSection>
  );
}

function AppearanceSection() {
  const [theme, setTheme] = useState('light');
  return (
    <SetSection title="外观">
      <div className="st-form">
        <SetRow label="主题模式" control={
          <div className="st-segmented">
            {['light', 'dark', 'system'].map(t => (
              <button key={t} className={theme === t ? 'on' : ''} onClick={() => setTheme(t)}>
                {t === 'light' ? '浅色' : t === 'dark' ? '深色' : '跟随系统'}
              </button>
            ))}
          </div>} />
        <SetRow label="主题色" control={
          <div className="st-swatches">
            {['#3b82f6','#0ea5e9','#6366f1','#0d9488','oklch(0.55 0.20 25)','oklch(0.6 0.15 60)'].map(c => (
              <button key={c} className="st-swatch" style={{background: c, ...(c==='#3b82f6'?{outline:'2px solid var(--text)', outlineOffset: 2}:{})}} />
            ))}
          </div>} />
        <SetRow label="界面密度" control={
          <div className="st-segmented">
            <button>紧凑</button><button className="on">常规</button><button>宽松</button>
          </div>} />
        <SetRow label="字体大小" hint="基础字号" control={
          <div className="st-slider-wrap">
            <input type="range" min="12" max="16" defaultValue="14" />
            <span className="mono">14px</span>
          </div>} />
      </div>
    </SetSection>
  );
}

function WorkspaceSection() {
  return (
    <SetSection title="工作区设置" desc="影响整个 Datalogue 工作区的所有成员。">
      <div className="st-form">
        <SetRow label="工作区名称" control={<input className="st-input" defaultValue="Datalogue · 蓝鲸电商" />} />
        <SetRow label="默认数据集" hint="新会话默认绑定" control={
          <select className="st-input"><option>电商核心数仓 · DWS</option><option>用户行为埋点</option></select>} />
        <SetRow label="结果缓存" hint="相同问题在 15 分钟内返回缓存"
          control={<Toggle value={true} />} />
        <SetRow label="允许公开分享会话" hint="生成只读链接，无需登录访问"
          control={<Toggle value={false} />} />
        <SetRow label="自动归档" hint="30 天未访问的会话移入归档"
          control={<Toggle value={true} />} />
      </div>
    </SetSection>
  );
}

function MembersSection() {
  const members = [
    { name: 'Yan Lin', email: 'yan.lin@datalogue.cn', role: 'Owner', team: '运营', last: '正在线' },
    { name: '王磊',    email: 'wang.lei@datalogue.cn',  role: 'Admin', team: '数据', last: '5 分钟前' },
    { name: '陈思',    email: 'chen.si@datalogue.cn',   role: 'Editor', team: '运营', last: '今天' },
    { name: '李娜',    email: 'li.na@datalogue.cn',     role: 'Editor', team: '市场', last: '昨天' },
    { name: '周扬',    email: 'zhou.yang@datalogue.cn', role: 'Viewer', team: '高管', last: '本周' },
    { name: 'API · 财务对账系统', email: 'svc-fin@datalogue', role: 'Service', team: '集成', last: '调用中' },
  ];
  return (
    <SetSection title="成员与权限" desc="6 人 · 1 个服务账号">
      <div className="search-bar" style={{maxWidth: 320, marginBottom: 14}}>
        <Icon name="search" />
        <input placeholder="搜索成员…" />
      </div>
      <div className="st-table">
        <div className="st-th">
          <span>成员</span><span>团队</span><span>角色</span><span>最近活跃</span><span></span>
        </div>
        {members.map((m, i) => (
          <div className="st-tr" key={i}>
            <span className="st-member">
              <div className={'avatar' + (m.role==='Service' ? ' svc' : '')}>{m.role==='Service' ? <Icon name="api" /> : m.name.slice(0,1)}</div>
              <div>
                <div className="st-member-name">{m.name}</div>
                <div className="st-member-email">{m.email}</div>
              </div>
            </span>
            <span>{m.team}</span>
            <span><span className={'st-role role-' + m.role.toLowerCase()}>{m.role}</span></span>
            <span className="text-3">{m.last}</span>
            <span><button className="icon-btn"><Icon name="more" /></button></span>
          </div>
        ))}
      </div>
      <button className="btn primary" style={{marginTop: 12}}><Icon name="plus" />邀请成员</button>
    </SetSection>
  );
}

function UsageSection() {
  return (
    <SetSection title="用量 & 计费" desc="当前账单周期 · 2026-05-01 → 2026-05-31">
      <div className="st-usage-grid">
        {[
          { label: '问数对话', used: '4,218', total: '10,000', pct: 0.42 },
          { label: 'API 调用', used: '128,402', total: '500,000', pct: 0.26 },
          { label: 'LLM Tokens', used: '8.4M', total: '20M', pct: 0.42 },
          { label: '向量检索', used: '12,894', total: '50,000', pct: 0.26 },
        ].map(u => (
          <div key={u.label} className="st-usage-card">
            <div className="st-usage-label">{u.label}</div>
            <div className="st-usage-val mono">{u.used} <span className="text-3">/ {u.total}</span></div>
            <div className="st-usage-bar"><span style={{width: (u.pct*100)+'%'}} /></div>
          </div>
        ))}
      </div>
      <div className="st-form" style={{marginTop: 16}}>
        <SetRow label="当前套餐" hint="Team · ¥3,800/月 · 续费日 2026-06-01"
          control={<button className="btn">升级套餐</button>} />
        <SetRow label="预算告警" hint="月用量达到 80% 时邮件提醒"
          control={<Toggle value={true} />} />
      </div>
    </SetSection>
  );
}

function DatasourcesSection() {
  const ds = [
    { name: 'electric_dwh',    type: 'PostgreSQL', host: 'pg-prod.lan:5432', tables: 248, status: 'connected' },
    { name: 'user_events',     type: 'ClickHouse', host: 'ch-events.lan:9000', tables: 36, status: 'connected' },
    { name: 'inventory_mysql', type: 'MySQL', host: 'mysql-inv.lan:3306', tables: 92, status: 'syncing' },
    { name: 'marketing_bq',    type: 'BigQuery', host: 'gcp-mkt.dataset', tables: 18, status: 'error' },
  ];
  return (
    <SetSection title="数据源" desc="数语会从这些数据源中匹配指标和表结构。">
      {ds.map(d => (
        <div className="st-ds-row" key={d.name}>
          <div className="st-ds-logo"><Icon name="database" /></div>
          <div className="st-ds-info">
            <div className="st-ds-name">{d.name} <span className="text-3 mono">· {d.type}</span></div>
            <div className="st-ds-meta mono">{d.host} · {d.tables} 张表</div>
          </div>
          <span className={'st-ds-status ' + d.status}>
            <span className="dot" />
            {d.status === 'connected' ? '已连接' : d.status === 'syncing' ? '同步中' : '连接异常'}
          </span>
          <button className="btn ghost"><Icon name="cog" />配置</button>
        </div>
      ))}
      <button className="btn" style={{marginTop: 10}}><Icon name="plus" />添加数据源</button>
    </SetSection>
  );
}

function ModelsSection() {
  return (
    <SetSection title="LLM 模型" desc="不同任务可以使用不同模型。所有调用都会记录到审计日志。">
      <div className="st-form">
        <SetRow label="意图理解 & 路由" hint="低延迟，处理用户问题分类" control={
          <select className="st-input"><option>Claude Haiku 4.5</option><option>GPT-4o-mini</option></select>} />
        <SetRow label="SQL 生成" hint="精度优先，处理复杂归因" control={
          <select className="st-input"><option>Claude Sonnet 4.5</option><option>DeepSeek-Coder-V3</option></select>} />
        <SetRow label="解释 & 洞察" hint="文本输出，可读性优先" control={
          <select className="st-input"><option>Claude Sonnet 4.5</option><option>Qwen-2.5-72B</option></select>} />
        <SetRow label="Embedding" hint="用于指标/列匹配" control={
          <select className="st-input"><option>bge-large-zh-v1.5</option><option>text-embedding-3-large</option></select>} />
        <SetRow label="脱敏调用" hint="向云端模型发送前掩码业务字段"
          control={<Toggle value={true} />} />
        <SetRow label="温度" control={
          <div className="st-slider-wrap"><input type="range" min="0" max="100" defaultValue="20" /><span className="mono">0.20</span></div>} />
      </div>
    </SetSection>
  );
}

function GlossarySection() {
  const terms = [
    { term: 'GMV',     def: '商品交易总额，含取消未支付订单', alias: 'Gross Merchandise Volume', usage: 248 },
    { term: '客单价',  def: 'GMV / 已支付订单数',           alias: 'AOV', usage: 192 },
    { term: '新客',    def: '首次成功支付订单的用户',        alias: 'New Buyer', usage: 156 },
    { term: '高价值',  def: '近90天累计消费 ¥500 以上',      alias: 'VIP', usage: 89 },
    { term: '复购率',  def: '当月有两次及以上下单的用户占比', alias: 'Repurchase Rate', usage: 78 },
  ];
  return (
    <SetSection title="业务词典" desc="统一你团队的业务术语和指标口径。数语会优先使用这里的定义。">
      <div className="search-bar" style={{maxWidth: 360, marginBottom: 14}}>
        <Icon name="search" />
        <input placeholder="搜索术语…" />
      </div>
      <div className="st-table">
        <div className="st-th glossary">
          <span>术语</span><span>定义</span><span>别名</span><span>使用次数</span><span></span>
        </div>
        {terms.map((t, i) => (
          <div className="st-tr glossary" key={i}>
            <span className="mono">{t.term}</span>
            <span>{t.def}</span>
            <span className="text-3 mono">{t.alias}</span>
            <span className="mono text-3">{t.usage}</span>
            <span><button className="icon-btn"><Icon name="more" /></button></span>
          </div>
        ))}
      </div>
      <button className="btn" style={{marginTop: 12}}><Icon name="plus" />新增术语</button>
    </SetSection>
  );
}

function ApiKeysSection() {
  const keys = [
    { name: 'BI 仪表盘 (Production)', token: 'dlg_live_••••••••••••f2a7', created: '2025-11-04', last: '2 分钟前', scope: 'read', calls: '42,108' },
    { name: '财务对账系统',           token: 'dlg_live_••••••••••••91c4', created: '2025-08-22', last: '1 小时前', scope: 'read', calls: '8,902' },
    { name: '本地开发 · YL',          token: 'dlg_test_••••••••••••ab12', created: '2026-04-01', last: '昨天',     scope: 'read+write', calls: '142' },
  ];
  return (
    <SetSection title="API 密钥" desc="使用密钥作为 Bearer Token 调用你已发布的问数接口。绝不要把密钥提交到公开仓库。">
      <div className="st-table">
        <div className="st-th apikeys">
          <span>名称</span><span>Token</span><span>权限</span><span>调用 · 30d</span><span>最近使用</span><span></span>
        </div>
        {keys.map((k, i) => (
          <div className="st-tr apikeys" key={i}>
            <span>
              <div className="st-row-label">{k.name}</div>
              <div className="st-row-hint">创建于 {k.created}</div>
            </span>
            <span className="mono text-2">{k.token}</span>
            <span><span className={'st-role role-' + (k.scope.includes('write') ? 'admin' : 'viewer')}>{k.scope}</span></span>
            <span className="mono">{k.calls}</span>
            <span className="text-3">{k.last}</span>
            <span>
              <button className="icon-btn" title="复制"><Icon name="copy" /></button>
              <button className="icon-btn" title="撤销"><Icon name="x" /></button>
            </span>
          </div>
        ))}
      </div>
      <div style={{display: 'flex', gap: 8, marginTop: 12}}>
        <button className="btn primary"><Icon name="plus" />创建新密钥</button>
        <button className="btn ghost"><Icon name="book" />查看 API 文档</button>
      </div>
    </SetSection>
  );
}

function WebhooksSection() {
  const hooks = [
    { url: 'https://hooks.slack.com/services/T0/…/api-alert', events: 'api.error · api.quota', status: 'active' },
    { url: 'https://ops.datalogue.cn/webhook/sessions',        events: 'session.published',     status: 'active' },
    { url: 'https://test.lan/webhook/echo',                    events: 'all',                   status: 'paused' },
  ];
  return (
    <SetSection title="Webhooks" desc="当问数会话发布为接口、定时任务运行或异常发生时，主动推送到你的服务。">
      <div className="st-table">
        <div className="st-th webhooks">
          <span>URL</span><span>事件</span><span>状态</span><span></span>
        </div>
        {hooks.map((h, i) => (
          <div className="st-tr webhooks" key={i}>
            <span className="mono text-2" style={{whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>{h.url}</span>
            <span className="mono text-3">{h.events}</span>
            <span><span className={'st-ds-status ' + (h.status === 'active' ? 'connected' : 'syncing')}><span className="dot" />{h.status === 'active' ? '生效中' : '已暂停'}</span></span>
            <span><button className="icon-btn"><Icon name="more" /></button></span>
          </div>
        ))}
      </div>
      <button className="btn" style={{marginTop: 12}}><Icon name="plus" />添加 Webhook</button>
    </SetSection>
  );
}

function AuditSection() {
  const logs = [
    { when: '2 分钟前', who: 'Yan Lin',  action: '发布接口', target: '/v1/sales/weekly-attribution v1.2' },
    { when: '14 分钟前',who: 'API · BI', action: '调用',     target: '/v1/marketing/channel-roi · 200 OK · 142ms' },
    { when: '1 小时前', who: '王磊',     action: '修改密钥', target: 'BI 仪表盘 (Production) 权限 read → read' },
    { when: '今天 11:24', who: 'Yan Lin', action: '创建会话', target: '上周华东区销售为什么下降了12%' },
    { when: '昨天 18:02', who: '陈思',   action: '邀请成员', target: '李娜 → Editor' },
    { when: '昨天 09:00', who: 'System', action: '定时刷新', target: '收藏 · 周度复盘 (5/5 成功)' },
  ];
  return (
    <SetSection title="审计日志" desc="敏感操作的不可篡改记录。保留 365 天。">
      <div className="st-toolbar-row">
        <div className="search-bar" style={{flex: 1}}><Icon name="search" /><input placeholder="搜索人员、操作或资源…" /></div>
        <button className="btn ghost"><Icon name="calendar" />近7天</button>
        <button className="btn ghost"><Icon name="download" />导出 CSV</button>
      </div>
      <div className="st-table">
        <div className="st-th audit">
          <span>时间</span><span>操作者</span><span>动作</span><span>目标</span>
        </div>
        {logs.map((l, i) => (
          <div className="st-tr audit" key={i}>
            <span className="text-3">{l.when}</span>
            <span>{l.who}</span>
            <span><span className="st-audit-action">{l.action}</span></span>
            <span className="mono text-2">{l.target}</span>
          </div>
        ))}
      </div>
    </SetSection>
  );
}

export { SettingsScreen };
