import React, { useState } from 'react';
import { Icon } from './icons';

// PublishDrawer — modal/drawer flow: turn a chat session into a published API.
// Steps: 1) 基本信息 → 2) 参数化变量 → 3) 响应 & 缓存 → 4) 发布

function PublishDrawer({ onClose }) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    name: '周度销售归因',
    path: '/v1/sales/weekly-attribution',
    method: 'GET',
    desc: '基于上周 vs 上上周差异，归因到「区域 × 品类 × 子类」拆解结果',
    visibility: 'workspace',
    cache: 900,
    rateLimit: 100,
    timeout: 8,
    quota: 50000,
  });

  const update = (k, v) => setForm({ ...form, [k]: v });

  return (
    <div className="pd-backdrop" onClick={onClose}>
      <div className="pd-drawer" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="pd-head">
          <div>
            <div className="pd-head-eyebrow">从会话发布</div>
            <h2 className="pd-head-title">上周华东区销售为什么下降了12%？</h2>
            <div className="pd-head-meta">
              <span><Icon name="chat" />8 条消息</span>
              <span><Icon name="database" />electric_dwh</span>
              <span><Icon name="user" />Yan Lin</span>
              <span><Icon name="calendar" />创建于 2025-11-08</span>
            </div>
          </div>
          <button className="icon-btn" onClick={onClose}><Icon name="x" /></button>
        </div>

        {/* Stepper */}
        <div className="pd-stepper">
          {['基本信息', '参数化', '响应 & 限流', '发布'].map((s, i) => (
            <div key={i} className={'pd-step ' + (step === i+1 ? 'active' : step > i+1 ? 'done' : '')}>
              <span className="pd-step-num">{step > i+1 ? <Icon name="check" /> : (i+1)}</span>
              <span className="pd-step-label">{s}</span>
              {i < 3 && <span className="pd-step-bar" />}
            </div>
          ))}
        </div>

        <div className="pd-body">
          {step === 1 && <PdBasics form={form} update={update} />}
          {step === 2 && <PdParams form={form} update={update} />}
          {step === 3 && <PdLimits form={form} update={update} />}
          {step === 4 && <PdReview form={form} />}
        </div>

        <div className="pd-foot">
          <div className="pd-foot-l">
            <span className="text-3" style={{fontSize: 12}}>第 {step} 步，共 4 步</span>
          </div>
          <div className="pd-foot-r">
            <button className="btn ghost" onClick={onClose}>取消</button>
            {step > 1 && <button className="btn" onClick={() => setStep(step-1)}>上一步</button>}
            {step < 4
              ? <button className="btn primary" onClick={() => setStep(step+1)}>下一步 →</button>
              : <button className="btn primary"><Icon name="api" />发布接口</button>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Step 1: basics ──────────────────────────────────────
function PdBasics({ form, update }) {
  return (
    <div className="pd-step-body">
      <div className="pd-grid-2">
        <PdField label="接口名称" hint="供成员检索，将出现在 API 列表">
          <input className="st-input" value={form.name} onChange={e => update('name', e.target.value)} />
        </PdField>
        <PdField label="HTTP 方法">
          <div className="st-segmented">
            {['GET','POST'].map(m => (
              <button key={m} className={form.method === m ? 'on' : ''} onClick={() => update('method', m)}>{m}</button>
            ))}
          </div>
        </PdField>
      </div>

      <PdField label="访问路径" hint="支持 RESTful 风格。{} 包围的部分会作为参数">
        <div className="pd-path-input">
          <span className="pd-path-prefix mono">https://api.datalogue.cn</span>
          <input className="st-input mono" value={form.path} onChange={e => update('path', e.target.value)} />
        </div>
      </PdField>

      <PdField label="描述" hint="对接方在文档中看到的简短说明">
        <textarea className="st-input" rows="2" value={form.desc} onChange={e => update('desc', e.target.value)} />
      </PdField>

      <PdField label="可见范围">
        <div className="pd-radio-cards">
          {[
            { v: 'private',   label: '仅自己',   hint: '只有 API 密钥拥有者能调用', icon: 'user_circle' },
            { v: 'workspace', label: '工作区',   hint: '所有成员的密钥都可调用',     icon: 'preset' },
            { v: 'public',    label: '公开',     hint: '匿名访问。建议配合配额使用',   icon: 'globe' },
          ].map(o => (
            <button key={o.v} className={'pd-radio-card ' + (form.visibility === o.v ? 'on' : '')} onClick={() => update('visibility', o.v)}>
              <Icon name={o.icon} />
              <div className="pd-radio-card-label">{o.label}</div>
              <div className="pd-radio-card-hint">{o.hint}</div>
            </button>
          ))}
        </div>
      </PdField>

      <PdField label="标签" hint="便于在 API 列表分组">
        <div className="pd-tags">
          {['销售', '归因', '周报', '华东'].map(t => (
            <span key={t} className="pd-tag">{t} <Icon name="x" /></span>
          ))}
          <button className="pd-tag add"><Icon name="plus" />添加</button>
        </div>
      </PdField>
    </div>
  );
}

// ── Step 2: params ──────────────────────────────────────
function PdParams() {
  // Visualize the extracted variables from the original question
  const extracted = [
    { key: 'region',    detected: '华东',     type: 'enum',   confidence: 0.96, hint: '从「华东区」识别' },
    { key: 'direction', detected: '下降',     type: 'enum',   confidence: 0.99, hint: '从「为什么下降了」识别' },
    { key: 'threshold', detected: '12',       type: 'number', confidence: 1.00, hint: '从「12%」识别' },
    { key: 'compare_to',detected: 'last_week',type: 'string', confidence: 0.84, hint: '从「上周」相对时间识别' },
  ];

  return (
    <div className="pd-step-body">
      <div className="pd-extract-banner">
        <Icon name="sparkle" />
        <div>
          数语在原问题中识别了 <strong>{extracted.length} 个变量</strong>。点击参数右侧的图标可固化为常量或调整类型。
        </div>
      </div>

      <div className="pd-question-vis">
        <div className="pd-q-label">原问题</div>
        <div className="pd-q-text">
          上周
          <span className="pd-var" data-key="region">华东区<span className="pd-var-key">region</span></span>
          销售为什么
          <span className="pd-var" data-key="direction">下降<span className="pd-var-key">direction</span></span>
          了
          <span className="pd-var" data-key="threshold">12<span className="pd-var-key">threshold</span></span>
          %？
        </div>
      </div>

      <div className="pd-params-table">
        <div className="pd-params-th">
          <span>变量</span><span>类型</span><span>默认值</span><span>必填</span><span>枚举值</span><span></span>
        </div>
        {extracted.map((e, i) => (
          <div className="pd-params-tr" key={i}>
            <span>
              <span className="mono">{e.key}</span>
              <div className="text-3" style={{fontSize: 11.5, marginTop: 2}}>
                <span className="pd-confidence">置信度 {(e.confidence*100).toFixed(0)}%</span>
                · {e.hint}
              </div>
            </span>
            <span>
              <select className="st-input small" defaultValue={e.type}>
                <option value="string">string</option>
                <option value="number">number</option>
                <option value="enum">enum</option>
                <option value="boolean">boolean</option>
                <option value="date">date</option>
              </select>
            </span>
            <span><input className="st-input small mono" defaultValue={e.detected} /></span>
            <span><PdToggle defaultValue={false} /></span>
            <span>
              {e.type === 'enum'
                ? <input className="st-input small mono" placeholder="华东, 华南, 华北…" defaultValue="华东, 华南, 华北, 华中, 西南, 西北" />
                : <span className="text-3" style={{fontSize: 11.5}}>—</span>}
            </span>
            <span>
              <button className="icon-btn" title="固化为常量"><Icon name="pin" /></button>
              <button className="icon-btn" title="删除"><Icon name="trash" /></button>
            </span>
          </div>
        ))}
      </div>

      <button className="btn ghost" style={{marginTop: 10}}><Icon name="plus" />手动添加参数</button>
    </div>
  );
}

function PdToggle({ defaultValue }) {
  const [v, setV] = useState(defaultValue);
  return (
    <button className={'st-toggle ' + (v ? 'on' : '')} onClick={() => setV(!v)}>
      <span className="st-toggle-knob" />
    </button>
  );
}

// ── Step 3: limits & cache ──────────────────────────────
function PdLimits({ form, update }) {
  return (
    <div className="pd-step-body">
      <h3 className="pd-sect-title">响应</h3>

      <div className="pd-grid-2">
        <PdField label="响应格式">
          <div className="st-segmented">
            <button className="on">JSON</button>
            <button>CSV</button>
            <button>Markdown</button>
          </div>
        </PdField>
        <PdField label="是否包含图表">
          <PdToggle defaultValue={true} />
        </PdField>
      </div>

      <div className="pd-grid-2">
        <PdField label="缓存时长" hint="相同参数命中缓存的有效期">
          <div className="pd-slider-row">
            <input type="range" min="0" max="3600" step="60" value={form.cache} onChange={e => update('cache', +e.target.value)} />
            <span className="mono">{form.cache === 0 ? '不缓存' : form.cache >= 60 ? Math.floor(form.cache/60) + ' 分钟' : form.cache + ' 秒'}</span>
          </div>
        </PdField>

        <PdField label="超时时间">
          <div className="pd-slider-row">
            <input type="range" min="1" max="30" value={form.timeout} onChange={e => update('timeout', +e.target.value)} />
            <span className="mono">{form.timeout} 秒</span>
          </div>
        </PdField>
      </div>

      <h3 className="pd-sect-title">限流 & 配额</h3>

      <div className="pd-grid-2">
        <PdField label="每分钟最大请求 (RPM)" hint="单密钥维度">
          <input className="st-input mono" type="number" value={form.rateLimit} onChange={e => update('rateLimit', +e.target.value)} />
        </PdField>
        <PdField label="月配额" hint="超出后返回 429 Too Many Requests">
          <input className="st-input mono" type="number" value={form.quota} onChange={e => update('quota', +e.target.value)} />
        </PdField>
      </div>

      <h3 className="pd-sect-title">定时刷新（可选）</h3>
      <PdField label="自动刷新结果到缓存" hint="开启后，调用方总能拿到最新数据，无需自行调度">
        <div className="pd-cron-row">
          <PdToggle defaultValue={true} />
          <select className="st-input">
            <option>每天 09:00</option>
            <option>每小时</option>
            <option>每周一 09:00</option>
            <option>自定义 Cron</option>
          </select>
          <span className="text-3 mono" style={{fontSize: 11.5}}>下次运行: 明天 09:00</span>
        </div>
      </PdField>

      <h3 className="pd-sect-title">安全</h3>
      <div className="pd-form">
        <PdInlineRow label="鉴权方式" right={<span className="mono text-2">Bearer Token (API Key)</span>} />
        <PdInlineRow label="IP 白名单" hint="留空表示不限制" right={<input className="st-input small mono" placeholder="10.0.0.0/8, 192.168.0.0/16" />} />
        <PdInlineRow label="对返回数据进行脱敏" hint="自动掩码手机号、身份证、邮箱" right={<PdToggle defaultValue={true} />} />
        <PdInlineRow label="启用审计日志" hint="所有调用记录到审计页" right={<PdToggle defaultValue={true} />} />
      </div>
    </div>
  );
}

function PdInlineRow({ label, hint, right }) {
  return (
    <div className="pd-inline-row">
      <div>
        <div className="st-row-label">{label}</div>
        {hint && <div className="st-row-hint">{hint}</div>}
      </div>
      <div>{right}</div>
    </div>
  );
}

// ── Step 4: review ──────────────────────────────────────
function PdReview({ form }) {
  return (
    <div className="pd-step-body">
      <div className="pd-review-grid">
        <div className="pd-review-left">
          <SectionCard title="基本信息" icon="api">
            <div className="pd-kv"><span>名称</span><span>{form.name}</span></div>
            <div className="pd-kv"><span>方法</span><span className="mono">{form.method}</span></div>
            <div className="pd-kv"><span>路径</span><span className="mono">{form.path}</span></div>
            <div className="pd-kv"><span>可见范围</span><span>{form.visibility === 'workspace' ? '工作区' : form.visibility === 'private' ? '仅自己' : '公开'}</span></div>
            <div className="pd-kv"><span>标签</span><span>销售 · 归因 · 周报 · 华东</span></div>
          </SectionCard>

          <SectionCard title="限流配置" icon="shield">
            <div className="pd-kv"><span>缓存时长</span><span className="mono">{Math.floor(form.cache/60)} 分钟</span></div>
            <div className="pd-kv"><span>超时</span><span className="mono">{form.timeout} 秒</span></div>
            <div className="pd-kv"><span>RPM</span><span className="mono">{form.rateLimit}</span></div>
            <div className="pd-kv"><span>月配额</span><span className="mono">{form.quota.toLocaleString()}</span></div>
            <div className="pd-kv"><span>定时刷新</span><span>每天 09:00</span></div>
          </SectionCard>
        </div>

        <div className="pd-review-right">
          <SectionCard title="预览：cURL" icon="code">
            <pre className="api-ex-code mono">{`curl -X ${form.method} \\
  'https://api.datalogue.cn${form.path}?region=华东&compare_to=last_week&threshold=12' \\
  -H 'Authorization: Bearer dlg_live_••••f2a7' \\
  -H 'Accept: application/json'`}</pre>
          </SectionCard>

          <SectionCard title="将立刻发生" icon="bolt">
            <ul className="pd-checklist">
              <li><Icon name="check" /> 接口将以 <span className="mono">v1.0</span> 状态发布到 <span className="mono">{form.path}</span></li>
              <li><Icon name="check" /> 工作区所有成员可在 API 列表中看到</li>
              <li><Icon name="check" /> 自动生成 OpenAPI 3.1 schema 与 Python/JS SDK</li>
              <li><Icon name="check" /> 添加到「定时刷新」队列：明天 09:00 首次运行</li>
              <li><Icon name="check" /> 在 Slack #data-ops 频道通知团队</li>
            </ul>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

function PdField({ label, hint, children }) {
  return (
    <div className="pd-field">
      <label className="pd-field-label">{label}</label>
      {hint && <div className="pd-field-hint">{hint}</div>}
      {children}
    </div>
  );
}

export { PublishDrawer };
