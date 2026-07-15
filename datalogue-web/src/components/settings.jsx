import React, { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Icon } from './icons';
import { del as apiDelete, get, patch, post } from '../api/client';
import { useAuth } from '../auth/auth-context';
import { UserCreateScreen } from './user-create';

// Settings — account, workspace, model, integrations, API keys.

function SettingsScreen() {
  const { user } = useAuth();
  const location = useLocation();
  const canManageUsers = user?.role === 'admin' || user?.is_superuser;
  const [section, setSection] = useState('account');

  useEffect(() => {
    // 兼容旧路由 /users 的跳转：统一收敛到系统设置内的用户管理子页。
    if (location.state?.section === 'users' && canManageUsers) {
      setSection('users');
    }
  }, [location.state, canManageUsers]);

  const groups = [
    { title: '个人', items: [
      { id: 'account',   label: '账号与个人资料', icon: 'user_circle' },
      { id: 'notify',    label: '通知',          icon: 'bell' },
      { id: 'appearance',label: '外观',          icon: 'swatch' },
    ]},
    { title: '工作区', items: [
      { id: 'workspace', label: '工作区设置', icon: 'preset' },
      { id: 'members',   label: '成员与权限', icon: 'user' },
      ...(canManageUsers ? [{ id: 'users', label: '用户管理', icon: 'user_circle' }] : []),
      { id: 'usage',     label: '用量 & 计费', icon: 'chart_bar' },
    ]},
    { title: '数据与模型', items: [
      { id: 'datasources', label: '数据源',     icon: 'database' },
      { id: 'glossary',    label: '业务词典',   icon: 'book' },
    ]},
    { title: '开发者', items: [
      { id: 'apikeys',     label: 'API 密钥',   icon: 'key' },
      { id: 'webhooks',    label: 'Webhooks',  icon: 'plug' },
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
        {section === 'users'      && canManageUsers && <UserCreateScreen />}
        {section === 'usage'      && <UsageSection />}
        {section === 'datasources'&& <DatasourcesSection />}
        {section === 'glossary'   && <GlossarySection />}
        {section === 'apikeys'    && <ApiKeysSection />}
        {section === 'webhooks'   && <WebhooksSection />}
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
  const { user } = useAuth();
  const displayName = user?.full_name || user?.username || '-';
  const displayEmail = user?.email || '-';
  const displayRole = user?.is_superuser
    ? '超级管理员'
    : user?.role === 'admin'
      ? '管理员'
      : '普通用户';
  const avatarText = (displayName || '?').trim().slice(0, 1).toUpperCase();

  return (
    <>
      <SetSection title="账号与个人资料" desc="这些信息会显示给团队其他成员。">
        <div className="st-card">
          <div className="st-profile">
            <div className="avatar lg">{avatarText}</div>
            <div className="st-profile-info">
              <div className="st-profile-name">{displayName}</div>
              <div className="st-profile-email">{displayEmail}</div>
              <div className="st-profile-org">当前角色：{displayRole}</div>
            </div>
            <button className="btn ghost"><Icon name="upload" />更换头像</button>
          </div>
        </div>

        <div className="st-form">
          <SetRow label="姓名" hint="显示在会话与协作中" control={<input className="st-input" value={displayName} readOnly />} />
          <SetRow label="邮箱" hint="登录与通知地址" control={<input className="st-input" value={displayEmail} readOnly />} />
          <SetRow label="角色" hint="角色由管理员统一分配" control={<input className="st-input" value={displayRole} readOnly />} />
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
            <span><button className="icon-btn" data-tip="更多操作" aria-label="更多操作"><Icon name="more" /></button></span>
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

const LLM_PRESETS = [
  {
    id: 'agentscope_openai',
    label: 'AgentScope OpenAI-compatible',
    provider: 'openai-compatible',
    base_url: 'https://api.minimaxi.com/v1',
    description: '通过 AgentScope 接入 OpenAI-compatible 模型服务',
    request_timeout_seconds: 60,
    models: ['MiniMax-M2.7', 'MiniMax-M3', 'gpt-4o-mini', 'gpt-4o'],
  },
  {
    id: 'openai',
    label: 'OpenAI',
    provider: 'openai',
    base_url: 'https://api.openai.com/v1',
    description: 'OpenAI 官方 OpenAI-compatible API',
    request_timeout_seconds: 60,
    models: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini', 'gpt-4.1'],
  },
  {
    id: 'deepseek',
    label: 'DeepSeek',
    provider: 'deepseek',
    base_url: 'https://api.deepseek.com/v1',
    description: 'DeepSeek OpenAI-compatible API',
    request_timeout_seconds: 60,
    models: ['deepseek-chat', 'deepseek-reasoner'],
  },
  {
    id: 'qwen',
    label: '通义千问 DashScope',
    provider: 'qwen',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    description: '阿里云 DashScope OpenAI-compatible API',
    request_timeout_seconds: 60,
    models: ['qwen-plus', 'qwen-max', 'qwen-turbo', 'qwen-long'],
  },
  {
    id: 'minimax',
    label: 'MiniMax',
    provider: 'minimax',
    base_url: 'https://api.minimaxi.com/v1',
    description: 'MiniMax OpenAI-compatible API',
    request_timeout_seconds: 60,
    models: ['MiniMax-M1', 'abab6.5s-chat', 'abab6.5g-chat'],
  },
  {
    id: 'anthropic',
    label: 'Anthropic',
    provider: 'anthropic',
    base_url: 'https://api.anthropic.com',
    description: '通过 AgentScope Anthropic ChatModel 接入 Claude',
    request_timeout_seconds: 60,
    models: ['claude-sonnet-4', 'claude-3-5-sonnet', 'claude-3-5-haiku'],
  },
  {
    id: 'custom',
    label: '自定义 OpenAI-compatible',
    provider: '',
    base_url: '',
    description: '',
    request_timeout_seconds: 60,
    models: [],
  },
];

const LLM_PROVIDER_OPTIONS = [
  { value: 'openai-compatible', label: 'OpenAI-compatible' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qwen', label: '通义千问' },
  { value: 'minimax', label: 'MiniMax' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'custom', label: '自定义' },
];

const PROVIDER_TO_CREDENTIAL_TYPE = {
  'openai-compatible': 'datalogue_llm_credential',
  openai: 'openai_credential',
  deepseek: 'deepseek_credential',
  qwen: 'dashscope_credential',
  minimax: 'datalogue_llm_credential',
  anthropic: 'anthropic_credential',
};

const CREDENTIAL_TYPE_TO_PROVIDER = {
  datalogue_llm_credential: 'openai-compatible',
  openai_credential: 'openai-compatible',
  deepseek_credential: 'deepseek',
  dashscope_credential: 'qwen',
  anthropic_credential: 'anthropic',
};

const emptyModelForm = {
  id: null,
  name: '',
  provider: 'openai-compatible',
  base_url: '',
  model: '',
  preset_id: 'agentscope_openai',
  model_choice: 'MiniMax-M2.7',
  custom_provider: '',
  name_auto: true,
  api_key: '',
  status: 'active',
  description: '',
  request_timeout_seconds: 60,
};

function findPreset(presetId) {
  return LLM_PRESETS.find(preset => preset.id === presetId) || LLM_PRESETS[0];
}

function autoModelName(preset, model) {
  const suffix = model || 'custom-model';
  return `${preset.label} · ${suffix}`;
}

function getModelChoice(preset, model) {
  if (!model) return preset.models[0] || 'custom';
  return preset.models.includes(model) ? model : 'custom';
}

function credentialTypeForProvider(provider) {
  return PROVIDER_TO_CREDENTIAL_TYPE[provider] || 'openai_credential';
}

function providerForCredentialType(type) {
  return CREDENTIAL_TYPE_TO_PROVIDER[type] || 'openai-compatible';
}

function normalizeCredentialRow(item = {}) {
  const data = item.data && typeof item.data === 'object' ? item.data : item;
  const id = data.id || item.id || data.credential_id || item.credential_id;
  const credentialType = data.type || item.type || 'openai_credential';
  const apiKeySet = Boolean(data.api_key_set ?? item.api_key_set);
  const status = data.status || item.status || (apiKeySet ? 'active' : 'disabled');
  if (!id) return null;
  return {
    id: String(id),
    credential_id: String(id),
    name: data.name || item.name || String(id),
    provider: providerForCredentialType(credentialType),
    credential_type: credentialType,
    base_url: data.base_url || data.api_host || data.host || '',
    model: data.model || data.model_name || item.model || item.model_name || '',
    status,
    description: data.description || '',
    request_timeout_seconds: Number(data.request_timeout_seconds || item.request_timeout_seconds || 60),
    api_key_set: apiKeySet,
    last_test_result: null,
    last_error_message: null,
  };
}

function buildCredentialPayload(form, { includeId = false } = {}) {
  const provider = form.provider === 'custom'
    ? form.custom_provider.trim()
    : form.provider.trim();
  const credentialType = credentialTypeForProvider(provider);
  const data = {
    name: form.name.trim(),
    type: credentialType,
  };
  if (includeId && form.id) data.id = form.id;
  if (form.base_url.trim()) data.base_url = form.base_url.trim();
  if (form.api_key.trim()) data.api_key = form.api_key.trim();
  // Datalogue 不再落本地模型配置表；页面上的模型选择和运行参数随 AgentScope credential 一起持久化。
  if (form.model.trim()) data.model = form.model.trim();
  data.status = form.status || 'active';
  if (form.description.trim()) data.description = form.description.trim();
  data.request_timeout_seconds = Number(form.request_timeout_seconds) || 60;
  return { data };
}

function inferPreset(model) {
  const byModel = LLM_PRESETS.find(preset => preset.models.includes(model.model));
  if (byModel) return byModel;
  const byBaseUrl = LLM_PRESETS.find(preset => (
    preset.id !== 'custom'
    && preset.provider === model.provider
    && preset.base_url === model.base_url
  ));
  if (byBaseUrl) return byBaseUrl;
  return LLM_PRESETS.find(preset => preset.id === 'custom');
}

function buildFormFromPreset(presetId, currentForm = emptyModelForm) {
  const preset = findPreset(presetId);
  const nextModel = preset.models[0] || '';
  const provider = preset.provider || currentForm.provider || 'custom';
  const nextName = currentForm.name_auto === false && currentForm.name
    ? currentForm.name
    : autoModelName(preset, nextModel);
  return {
    ...currentForm,
    preset_id: preset.id,
    model_choice: nextModel || 'custom',
    provider,
    custom_provider: provider === 'custom' ? currentForm.custom_provider : '',
    base_url: preset.base_url || currentForm.base_url,
    model: nextModel,
    name: nextName,
    name_auto: currentForm.name_auto !== false,
    description: preset.description || currentForm.description,
    request_timeout_seconds: preset.request_timeout_seconds || currentForm.request_timeout_seconds || 60,
  };
}

function ModelsSection() {
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState(() => buildFormFromPreset('agentscope_openai'));
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState(null);
  const [message, setMessage] = useState('');
  const [editorOpen, setEditorOpen] = useState(false); // 控制 credential 编辑弹窗的显隐
  const [initialFormSnapshot, setInitialFormSnapshot] = useState(null);
  const templateFieldRef = useRef(null);
  const editorTriggerRef = useRef(null);

  const selectedPreset = findPreset(form.preset_id);
  const isTestingCurrentModel = form.id != null && testingId === form.id;
  const providerChoices = LLM_PROVIDER_OPTIONS.some(item => item.value === form.provider)
    ? LLM_PROVIDER_OPTIONS
    : [...LLM_PROVIDER_OPTIONS, { value: form.provider, label: form.provider }];
  const activeModels = models.filter(model => model.status === 'active');
  const configuredKeys = models.filter(model => model.api_key_set).length;
  const latestActiveModel = activeModels.at(-1);
  // 新建和编辑都需要保护用户已填写但尚未保存的连接信息，避免误关闭弹窗造成配置丢失。
  const hasUnsavedChanges = Boolean(initialFormSnapshot && JSON.stringify(form) !== initialFormSnapshot);

  useEffect(() => {
    if (!editorOpen) return;
    // 新增或编辑时让焦点直接进入模板选择，键盘用户无需额外定位。
    const deferFocus = window.requestAnimationFrame || ((callback) => setTimeout(callback, 0));
    deferFocus(() => templateFieldRef.current?.focus());
  }, [editorOpen]);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const credentials = await get('/api/agentscope-control/credentials');
      setModels((Array.isArray(credentials) ? credentials : []).map(normalizeCredentialRow).filter(Boolean));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConfig().catch(err => setMessage(`加载模型配置失败：${err.message}`));
  }, []);

  const startEdit = (model) => {
    const preset = inferPreset(model);
    const modelChoice = getModelChoice(preset, model.model);
    const isKnownProvider = LLM_PROVIDER_OPTIONS.some(item => item.value === model.provider);
    const nextForm = {
      id: model.id,
      name: model.name,
      provider: model.provider,
      base_url: model.base_url,
      model: model.model,
      preset_id: preset.id,
      model_choice: modelChoice,
      custom_provider: isKnownProvider ? '' : model.provider,
      name_auto: false,
      api_key: '',
      status: model.status,
      description: model.description || '',
      request_timeout_seconds: model.request_timeout_seconds || 60,
    };
    editorTriggerRef.current = document.activeElement;
    setForm(nextForm);
    setInitialFormSnapshot(JSON.stringify(nextForm));
    setEditorOpen(true); // 编辑改为在弹窗内进行，避免直接改动顶部表单造成的怪异交互
  };

  const resetForm = () => {
    const nextForm = buildFormFromPreset('agentscope_openai');
    setForm(nextForm);
    setInitialFormSnapshot(JSON.stringify(nextForm));
  };

  const openCreate = () => { // 打开“新增 credential”弹窗（重置为默认模板）
    editorTriggerRef.current = document.activeElement;
    resetForm();
    setMessage('');
    setEditorOpen(true);
  };

  const closeEditor = () => {
    if (hasUnsavedChanges && !window.confirm('尚未保存修改，确定要关闭吗？')) return;
    setEditorOpen(false);
    const deferFocus = window.requestAnimationFrame || ((callback) => setTimeout(callback, 0));
    deferFocus(() => editorTriggerRef.current?.focus());
  };

  const handleEditorKeyDown = (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeEditor();
      return;
    }

    if (event.key === 'Tab') {
      // 弹窗打开期间将键盘焦点限制在编辑器内，避免 Tab 跳到被遮罩的后台页面。
      const focusableItems = [...event.currentTarget.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      )];
      const firstItem = focusableItems[0];
      const lastItem = focusableItems.at(-1);

      if (!firstItem || !lastItem) return;
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem.focus();
      }
    }
  };

  const changePreset = (presetId) => {
    setForm(current => buildFormFromPreset(presetId, {
      ...current,
      name: current.name_auto === false ? '' : current.name,
      name_auto: true,
    }));
  };

  const changeProvider = (provider) => {
    setForm(current => ({
      ...current,
      provider,
      custom_provider: provider === 'custom' ? current.custom_provider : '',
    }));
  };

  const changeModelChoice = (modelChoice) => {
    setForm(current => {
      const preset = findPreset(current.preset_id);
      const modelName = modelChoice === 'custom' ? '' : modelChoice;
      return {
        ...current,
        model_choice: modelChoice,
        model: modelName,
        name: current.name_auto ? autoModelName(preset, modelName) : current.name,
      };
    });
  };

  const changeModelName = (modelName) => {
    setForm(current => ({
      ...current,
      model: modelName,
      name: current.name_auto ? autoModelName(findPreset(current.preset_id), modelName) : current.name,
    }));
  };

  const saveModel = async () => {
    setSaving(true);
    setMessage('');
    try {
      if (!form.name.trim() || !form.base_url.trim()) {
        throw new Error('请填写名称和 Base URL');
      }
      if (form.id) {
        await patch(`/api/agentscope-control/credentials/${encodeURIComponent(form.id)}`, buildCredentialPayload(form));
      } else {
        if (!form.api_key.trim()) throw new Error('新增 AgentScope credential 时必须填写 API Key');
        await post('/api/agentscope-control/credentials', buildCredentialPayload(form, { includeId: true }));
      }
      resetForm();
      setEditorOpen(false); // 保存成功后关闭弹窗
      await loadConfig();
      setMessage('AgentScope credential 已保存');
    } catch (err) {
      setMessage(`保存失败：${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const toggleStatus = async (model) => {
    const nextStatus = model.status === 'active' ? 'disabled' : 'active';
    setMessage('');
    try {
      await patch(`/api/agentscope-control/credentials/${encodeURIComponent(model.id)}`, {
        data: { status: nextStatus },
      });
      await loadConfig();
      setMessage(`${model.name} 已${nextStatus === 'active' ? '启用' : '停用'}`);
    } catch (err) {
      setMessage(`状态更新失败：${err.message}`);
    }
  };

  const testModel = async (model) => {
    setTestingId(model.id);
    setMessage('');
    try {
      const cards = await get(`/api/agentscope-control/model?provider=${encodeURIComponent(model.credential_type || credentialTypeForProvider(model.provider))}`);
      await loadConfig();
      setMessage(`AgentScope ModelCard 发现成功：${Array.isArray(cards) ? cards.length : 0} 个可用模型`);
    } catch (err) {
      setMessage(`测试失败：${err.message}`);
    } finally {
      setTestingId(null);
    }
  };

  const testCurrentModel = () => {
    if (!form.id) {
      setMessage('请先保存 AgentScope credential，再发现可用模型');
      return;
    }
    const model = models.find(item => item.id === form.id) || { id: form.id };
    testModel(model);
  };

  const removeModel = async (model) => {
    await apiDelete(`/api/agentscope-control/credentials/${encodeURIComponent(model.id)}`);
    if (form.id === model.id) { resetForm(); setEditorOpen(false); } // 删除正在编辑的 credential 时同步关闭弹窗
    await loadConfig();
  };

  return (
    <>
      <section className="llm-section" aria-labelledby="llm-control-title">
        <div className="llm-control-panel">
          <div className="llm-panel-copy">
            <div className="llm-eyebrow"><span className="llm-eyebrow-signal" />AGENTSCOPE · 模型运行概览</div>
            <h2 id="llm-control-title">LLM 模型控制台</h2>
            <p>集中管理问数运行时使用的模型凭证。密钥仅托管于 AgentScope，页面不会回显明文。</p>
          </div>
          <div className="llm-runtime-readout" aria-label="模型运行概览">
            <div className="llm-readout-status"><span className="llm-pulse-dot" />当前启用模型</div>
            <div className="llm-readout-model">{latestActiveModel?.model || '等待接入模型'}</div>
            <div className="llm-readout-meta">{latestActiveModel ? `${latestActiveModel.provider} · 已启用` : '创建首个 credential 后开始服务'}</div>
          </div>
        </div>

        <div className="llm-stat-grid" aria-label="模型配置统计">
          <div className="llm-stat-card"><span>已接入 credential</span><strong>{models.length}</strong><small>全部连接配置</small></div>
          <div className="llm-stat-card is-live"><span>运行中</span><strong>{activeModels.length}</strong><small>当前允许被调用</small></div>
          <div className="llm-stat-card"><span>密钥就绪</span><strong>{configuredKeys}<em> / {models.length || 0}</em></strong><small>由 AgentScope 安全托管</small></div>
          <div className="llm-stat-card"><span>供应商</span><strong>{new Set(models.map(model => model.provider)).size}</strong><small>支持多模型切换</small></div>
        </div>

        {message && <div className="st-inline-alert llm-inline-alert" role="status" aria-live="polite">{message}</div>}

        <div className="llm-list-heading">
          <div>
            <div className="llm-list-kicker">CONNECTION INVENTORY</div>
            <h3>模型连接</h3>
            <p>发现模型用于校验接入能力，不会写入或暴露 API Key。</p>
          </div>
          <button ref={editorTriggerRef} className="btn primary llm-add-button" onClick={openCreate}><Icon name="plus" />新增 credential</button>
        </div>

        {loading && models.length === 0 ? (
          <div className="llm-loading-grid" aria-label="正在加载模型连接" aria-busy="true">
            {[0, 1, 2, 3].map(item => <div className="llm-loading-card" key={item}><span /><span /><span /></div>)}
          </div>
        ) : models.length === 0 ? (
          <div className="llm-empty-state">
            <div className="llm-empty-orbit"><Icon name="brain" /></div>
            <div>
              <h3>尚未建立模型连接</h3>
              <p>从一个接入模板开始，完成后可立即发现该服务支持的模型。</p>
            </div>
            <button className="btn ghost llm-action-button" onClick={openCreate}>创建第一个 credential <Icon name="plus" /></button>
          </div>
        ) : (
          <div className="llm-card-grid">
            {models.map(model => {
              const isActive = model.status === 'active';
              const testSummary = model.last_test_result?.ok
                ? `连接通过 · ${model.last_test_result.latency_ms ?? '--'}ms`
                : model.last_error_message || '尚未发现模型';
              return (
                <article className={'llm-credential-card ' + (isActive ? 'is-active' : 'is-disabled')} key={model.id}>
                  <div className="llm-card-topline" aria-hidden="true"><span /><span /><span /></div>
                  <header className="llm-card-header">
                    <div className="llm-provider-mark">{(model.provider || 'AI').slice(0, 2).toUpperCase()}</div>
                    <div className="llm-card-title">
                      <div className="llm-card-title-row"><h3 title={model.name}>{model.name}</h3><span className={'llm-status-chip ' + (isActive ? 'live' : '')}><i />{isActive ? '运行中' : '已停用'}</span></div>
                      <p>{model.provider} <b>·</b> {model.model || 'ModelCard 自动发现'}</p>
                    </div>
                  </header>
                  {model.description && <p className="llm-card-description">{model.description}</p>}
                  <dl className="llm-card-facts">
                    <div><dt>连接端点</dt><dd title={model.base_url}>{model.base_url || '未填写'}</dd></div>
                    <div><dt>密钥状态</dt><dd className={model.api_key_set ? 'is-safe' : 'is-missing'}><span />{model.api_key_set ? '已安全托管' : '等待配置'}</dd></div>
                    <div><dt>请求超时</dt><dd>{model.request_timeout_seconds || 60}s</dd></div>
                  </dl>
                  <div className={'llm-discovery-state ' + (model.last_test_result?.ok ? 'is-success' : '')}>
                    <Icon name="beaker" /><span>{testSummary}</span>
                  </div>
                  <footer className="llm-card-footer">
                    <button className="btn ghost llm-discover-button llm-action-button" disabled={testingId === model.id} onClick={() => testModel(model)}>
                      <Icon name="beaker" />{testingId === model.id ? '发现中' : '发现模型'}
                    </button>
                    <div className="llm-card-actions">
                      <button className="icon-btn" title="编辑" data-tip="编辑" aria-label="编辑" onClick={() => startEdit(model)}><Icon name="edit" /></button>
                      <button className="icon-btn" title={isActive ? '停用' : '启用'} data-tip={isActive ? '停用' : '启用'} aria-label={isActive ? '停用' : '启用'} onClick={() => toggleStatus(model)}><Icon name="pause" /></button>
                      <button className="icon-btn danger" title="删除" data-tip="删除" aria-label="删除" onClick={() => removeModel(model)}><Icon name="trash" /></button>
                    </div>
                  </footer>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {editorOpen && (
        <div className="st-modal-overlay" onClick={closeEditor}>
          <div className="st-modal llm-editor-modal" role="dialog" aria-modal="true" aria-labelledby="llm-editor-title" onKeyDown={handleEditorKeyDown} onClick={e => e.stopPropagation()}>
            <div className="st-modal-header llm-editor-header">
              <div className="st-modal-titles">
                <div className="st-modal-eyebrow">系统设置 / LLM 模型</div>
                <div className="st-modal-title" id="llm-editor-title">{form.id ? `编辑模型连接 · ${form.name || form.id}` : '新增模型连接'}</div>
                <p className="llm-editor-intro">凭证将由 AgentScope 安全托管，保存后即可发现可用模型。</p>
              </div>
              <button className="icon-btn" title="关闭" data-tip="关闭" aria-label="关闭" onClick={closeEditor}><Icon name="x" /></button>
            </div>

            <div className="st-modal-body">
              <form className="llm-editor" onSubmit={event => { event.preventDefault(); saveModel(); }}>
                <section className="llm-form-section" aria-labelledby="llm-access-title">
                  <div className="llm-form-section-heading"><span>01</span><div><h4 id="llm-access-title">接入方式</h4><p>从模板开始，系统会自动填充常用连接信息。</p></div></div>
                  <div className="llm-form-grid">
                    <label className="llm-form-field llm-field-full"><span>接入模板</span><select ref={templateFieldRef} className="st-input" aria-label="接入模板" value={form.preset_id} onChange={e => changePreset(e.target.value)}>{LLM_PRESETS.map(preset => <option key={preset.id} value={preset.id}>{preset.label}</option>)}</select></label>
                    <label className="llm-form-field"><span>名称</span><input className="st-input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value, name_auto: false })} placeholder="MiniMax via AgentScope" /></label>
                    <label className="llm-form-field"><span>供应商</span><select className="st-input" aria-label="供应商" value={form.provider} onChange={e => changeProvider(e.target.value)}>{providerChoices.map(provider => <option key={provider.value} value={provider.value}>{provider.label}</option>)}</select></label>
                    {form.provider === 'custom' && <label className="llm-form-field llm-field-full"><span>供应商标识</span><input className="st-input" value={form.custom_provider} onChange={e => setForm({ ...form, custom_provider: e.target.value })} placeholder="输入供应商标识，如 volcengine" /></label>}
                  </div>
                </section>

                <section className="llm-form-section" aria-labelledby="llm-connection-title">
                  <div className="llm-form-section-heading"><span>02</span><div><h4 id="llm-connection-title">连接信息</h4><p>端点和密钥只用于建立安全的模型连接。</p></div></div>
                  <div className="llm-form-grid">
                    <label className="llm-form-field llm-field-full"><span>Base URL</span><input className="st-input mono" value={form.base_url} onChange={e => setForm({ ...form, base_url: e.target.value })} placeholder="http://localhost:4000/v1" /></label>
                    <label className="llm-form-field"><span>模型名</span><select className="st-input" aria-label="模型名" value={form.model_choice} onChange={e => changeModelChoice(e.target.value)}>{selectedPreset.models.map(model => <option key={model} value={model}>{model}</option>)}<option value="custom">自定义模型</option></select>{form.model_choice === 'custom' && <input className="st-input" value={form.model} onChange={e => changeModelName(e.target.value)} placeholder="输入模型名，如 datalogue-sql" />}</label>
                    <label className="llm-form-field"><span>API Key <small>{form.id ? '留空则不覆盖已保存密钥' : '仅保存，之后不回显'}</small></span><input className="st-input" type="password" value={form.api_key} onChange={e => setForm({ ...form, api_key: e.target.value })} placeholder={form.id ? '不覆盖' : 'sk-...'} /></label>
                  </div>
                </section>

                <section className="llm-form-section" aria-labelledby="llm-runtime-title">
                  <div className="llm-form-section-heading"><span>03</span><div><h4 id="llm-runtime-title">运行参数</h4><p>定义连接启用状态与单次请求的等待上限。</p></div></div>
                  <div className="llm-form-grid">
                    <label className="llm-form-field"><span>状态</span><select className="st-input" aria-label="状态" value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}><option value="active">启用</option><option value="disabled">停用</option></select></label>
                    <label className="llm-form-field"><span>超时（秒）</span><input className="st-input" type="number" min="1" value={form.request_timeout_seconds} onChange={e => setForm({ ...form, request_timeout_seconds: e.target.value })} /></label>
                    <label className="llm-form-field llm-field-full"><span>描述 <small>可选</small></span><textarea className="st-input" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="用途、供应商或路由说明" /></label>
                  </div>
                </section>
              </form>
            </div>

            <div className="st-modal-footer">
              <button className="btn ghost llm-action-button" onClick={closeEditor}>取消</button>
              <div className="llm-form-actions">
                {form.id ? <button className="btn ghost llm-action-button" title={hasUnsavedChanges ? '请先保存连接信息' : '发现可用模型'} disabled={isTestingCurrentModel || hasUnsavedChanges} onClick={testCurrentModel}><Icon name="beaker" />{isTestingCurrentModel ? '发现中' : '发现模型'}</button> : <span className="llm-discover-hint">保存后即可发现可用模型</span>}
                <button className="btn primary llm-action-button" disabled={saving} onClick={saveModel}><Icon name="check" />{saving ? '保存中' : '保存 credential'}</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
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
            <span><button className="icon-btn" data-tip="更多操作" aria-label="更多操作"><Icon name="more" /></button></span>
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
              <button className="icon-btn" data-tip="复制" aria-label="复制"><Icon name="copy" /></button>
              <button className="icon-btn danger" data-tip="撤销" aria-label="撤销"><Icon name="trash" /></button>
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
            <span><button className="icon-btn" data-tip="更多操作" aria-label="更多操作"><Icon name="more" /></button></span>
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

// 独立路由复用同一套模型连接交互，确保主导航与旧设置页不出现两套凭据管理逻辑。
function LLMModelsScreen() {
  return (
    <main className="llm-page" aria-label="LLM 模型配置">
      <ModelsSection />
    </main>
  );
}

// 查询审计与模型配置一样需要被持续访问，因此从设置页迁出并复用唯一的审计内容实现。
function AuditScreen() {
  return (
    <main className="audit-page" aria-label="查询审计">
      <AuditSection />
    </main>
  );
}

export { AuditScreen, LLMModelsScreen, SettingsScreen };
