import { useEffect, useMemo, useState } from 'react';
import { Icon } from './icons';
import {
  analyzeBlueprintSql,
  createAnalysisBlueprint,
  listAnalysisBlueprints,
  testAnalysisBlueprint,
  updateAnalysisBlueprint,
  updateAnalysisBlueprintStatus,
} from '../api/client';

const STATUS_META = {
  draft: { label: 'AI 草稿', color: '#6b7280', bg: '#f3f4f6' },
  reviewing: { label: '审核中', color: '#b45309', bg: '#fef3c7' },
  active: { label: '已发布', color: '#15803d', bg: '#dcfce7' },
  deprecated: { label: '已弃用', color: '#6b7280', bg: '#f3f4f6', strike: true },
};

const emptyBlueprint = {
  name: '',
  description: '',
  trigger_keywords: [],
  trigger_examples: [],
  when_to_use: '',
  parameters: [],
  implementation_type: 'stored_procedure',
  call_template: '',
  output_schema: [],
  timeout_seconds: 30,
  steps: [],
  attribution_hints: '',
  raw_sql: '',
  status: 'draft',
  ai_confidence: null,
  owner: '',
};

function safeJson(value, fallback) {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function formatJson(value) {
  return JSON.stringify(value ?? [], null, 2);
}

function linesToArray(text) {
  return text
    .split('\n')
    .map(s => s.trim())
    .filter(Boolean);
}

function arrayToLines(value) {
  return (value || []).join('\n');
}

function BlueprintStatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.draft;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '2px 7px',
        borderRadius: 5,
        fontSize: 11,
        fontWeight: 500,
        color: meta.color,
        background: meta.bg,
        textDecoration: meta.strike ? 'line-through' : 'none',
        whiteSpace: 'nowrap',
      }}
    >
      {meta.label}
    </span>
  );
}

function BlueprintWizard({ datasetId, onClose, onSaved }) {
  const [step, setStep] = useState(1);
  const [mode, setMode] = useState('sql');
  const [sqlText, setSqlText] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [savedBlueprint, setSavedBlueprint] = useState(null);
  const [testResult, setTestResult] = useState(null);
  const [form, setForm] = useState(emptyBlueprint);
  const [triggerExamplesText, setTriggerExamplesText] = useState('');
  const [triggerKeywordsText, setTriggerKeywordsText] = useState('');
  const [parametersText, setParametersText] = useState('[]');
  const [outputSchemaText, setOutputSchemaText] = useState('[]');
  const [stepsText, setStepsText] = useState('[]');
  const [testParamsText, setTestParamsText] = useState('{}');
  const [lowConfidenceFields, setLowConfidenceFields] = useState([]);

  const updateForm = (key, value) => setForm(prev => ({ ...prev, [key]: value }));

  const applyAnalysisResult = (result) => {
    const next = {
      ...emptyBlueprint,
      name: result.name || '',
      description: result.description || '',
      trigger_keywords: result.trigger_keywords || [],
      trigger_examples: result.trigger_examples || [],
      when_to_use: result.when_to_use || '',
      parameters: result.parameters || [],
      implementation_type: result.implementation_type || 'stored_procedure',
      call_template: result.call_template || '',
      output_schema: result.output_schema || [],
      steps: result.steps || [],
      attribution_hints: result.attribution_hints || '',
      raw_sql: result.raw_sql || sqlText,
      ai_confidence: result.ai_confidence ?? null,
      status: 'draft',
    };
    setForm(next);
    setTriggerKeywordsText(arrayToLines(next.trigger_keywords));
    setTriggerExamplesText(arrayToLines(next.trigger_examples));
    setParametersText(formatJson(next.parameters));
    setOutputSchemaText(formatJson(next.output_schema));
    setStepsText(formatJson(next.steps));
    setLowConfidenceFields(result.low_confidence_fields || []);
  };

  const handleAnalyze = async () => {
    if (mode === 'manual') {
      setStep(2);
      return;
    }
    if (!sqlText.trim()) {
      alert('请先粘贴 SQL / 存储过程代码');
      return;
    }
    setAnalyzing(true);
    try {
      const task = await analyzeBlueprintSql(datasetId, sqlText);
      applyAnalysisResult(task.result || {});
      setStep(2);
    } catch (err) {
      alert('AI 分析失败: ' + (err.message || '未知错误'));
    } finally {
      setAnalyzing(false);
    }
  };

  const buildPayload = () => ({
    ...form,
    trigger_keywords: linesToArray(triggerKeywordsText),
    trigger_examples: linesToArray(triggerExamplesText),
    parameters: safeJson(parametersText, form.parameters || []),
    output_schema: safeJson(outputSchemaText, form.output_schema || []),
    steps: safeJson(stepsText, form.steps || []),
    raw_sql: sqlText || form.raw_sql,
  });

  const saveDraft = async () => {
    setSaving(true);
    try {
      const payload = buildPayload();
      let bp;
      if (savedBlueprint?.id) {
        bp = await updateAnalysisBlueprint(datasetId, savedBlueprint.id, payload);
      } else {
        bp = await createAnalysisBlueprint(datasetId, payload);
      }
      setSavedBlueprint(bp);
      onSaved?.(bp);
      return bp;
    } catch (err) {
      alert('保存蓝图失败: ' + (err.message || '未知错误'));
      return null;
    } finally {
      setSaving(false);
    }
  };

  const handleRunTest = async () => {
    const bp = savedBlueprint || await saveDraft();
    if (!bp) return;
    setTesting(true);
    try {
      const params = safeJson(testParamsText, {});
      const result = await testAnalysisBlueprint(datasetId, bp.id, params, bp.name);
      setTestResult(result);
      const refreshed = { ...bp, last_test_result: result };
      setSavedBlueprint(refreshed);
      onSaved?.(refreshed);
    } catch (err) {
      alert('测试运行失败: ' + (err.message || '未知错误'));
    } finally {
      setTesting(false);
    }
  };

  const handlePublish = async () => {
    const bp = savedBlueprint || await saveDraft();
    if (!bp) return;
    if (!testResult && !(bp.last_test_result || {}).ok) {
      alert('发布前必须先完成一次测试');
      return;
    }
    try {
      const published = await updateAnalysisBlueprintStatus(datasetId, bp.id, {
        action: 'publish',
        change_summary: '向导发布蓝图',
      });
      onSaved?.(published);
      onClose();
    } catch (err) {
      alert('发布失败: ' + (err.message || '未知错误'));
    }
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.42)', zIndex: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}
      onClick={onClose}
    >
      <div
        style={{ width: 'min(1120px, 96vw)', maxHeight: '92vh', overflow: 'auto', background: 'var(--bg)', border: '1px solid var(--hairline)', borderRadius: 12 }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 18px', borderBottom: '1px solid var(--hairline)' }}>
          <h3 style={{ margin: 0, fontSize: 16 }}>新建分析蓝图</h3>
          <div style={{ display: 'flex', gap: 6, marginLeft: 12 }}>
            {['上传 SQL', 'AI 审核', '精细配置', '触发与测试'].map((label, idx) => (
              <span key={label} style={{ fontSize: 11, color: step === idx + 1 ? 'var(--accent)' : 'var(--text-3)', background: step === idx + 1 ? 'var(--accent-soft)' : 'transparent', padding: '3px 7px', borderRadius: 5 }}>
                {idx + 1}. {label}
              </span>
            ))}
          </div>
          <button className="icon-btn" style={{ marginLeft: 'auto' }} onClick={onClose}><Icon name="x" /></button>
        </div>

        <div style={{ padding: 18 }}>
          {step === 1 && (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
                <button className="btn ghost" style={{ height: 72, justifyContent: 'flex-start', border: mode === 'sql' ? '1px solid var(--accent)' : '1px solid var(--hairline)', background: mode === 'sql' ? 'var(--accent-soft)' : 'var(--surface)' }} onClick={() => setMode('sql')}>
                  <Icon name="sql" />从 SQL 导入
                </button>
                <button className="btn ghost" style={{ height: 72, justifyContent: 'flex-start', border: mode === 'manual' ? '1px solid var(--accent)' : '1px solid var(--hairline)', background: mode === 'manual' ? 'var(--accent-soft)' : 'var(--surface)' }} onClick={() => setMode('manual')}>
                  <Icon name="edit" />手动创建
                </button>
              </div>
              <textarea
                value={sqlText}
                onChange={e => setSqlText(e.target.value)}
                placeholder="粘贴 SQL / 存储过程代码..."
                style={{ width: '100%', minHeight: 300, border: '1px solid var(--hairline)', borderRadius: 8, padding: 12, background: 'var(--surface)', color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.5 }}
              />
            </div>
          )}

          {step === 2 && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>AI 提取，可编辑</div>
                <WizardField label="蓝图名称" value={form.name} onChange={v => updateForm('name', v)} />
                <WizardTextArea label="业务描述" value={form.description} onChange={v => updateForm('description', v)} rows={4} />
                <WizardTextArea label="触发关键词（每行一条）" value={triggerKeywordsText} onChange={setTriggerKeywordsText} rows={4} />
                <WizardTextArea label="触发问法（每行一条）" value={triggerExamplesText} onChange={setTriggerExamplesText} rows={4} />
                <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 6 }}>
                  AI 置信度: <strong>{form.ai_confidence != null ? Math.round(form.ai_confidence * 100) : 0}%</strong>
                </div>
                {lowConfidenceFields.length > 0 && (
                  <div style={{ marginTop: 8, padding: 10, borderRadius: 8, background: 'var(--warn-soft)', color: 'var(--text-2)', fontSize: 12 }}>
                    {lowConfidenceFields.map((f, idx) => (
                      <div key={idx}>需确认: {f.path} · {Math.round((f.confidence || 0) * 100)}%</div>
                    ))}
                  </div>
                )}
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>原始 SQL，只读</div>
                <pre style={{ minHeight: 430, maxHeight: 520, overflow: 'auto', margin: 0, padding: 12, borderRadius: 8, border: '1px solid var(--hairline)', background: 'var(--bg-2)', color: 'var(--text-2)', fontSize: 12, lineHeight: 1.5 }}>{sqlText || form.raw_sql || '手动创建模式暂无 SQL'}</pre>
              </div>
            </div>
          )}

          {step === 3 && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <WizardTextArea label="参数列表 JSON" value={parametersText} onChange={setParametersText} rows={12} mono />
              <WizardTextArea label="输出列语义 JSON" value={outputSchemaText} onChange={setOutputSchemaText} rows={12} mono />
              <WizardTextArea label="业务逻辑步骤 JSON" value={stepsText} onChange={setStepsText} rows={12} mono />
              <WizardTextArea label="结果解读提示" value={form.attribution_hints || ''} onChange={v => updateForm('attribution_hints', v)} rows={12} />
            </div>
          )}

          {step === 4 && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div>
                <WizardTextArea label="触发问法（至少 2 条，每行一条）" value={triggerExamplesText} onChange={setTriggerExamplesText} rows={8} />
                <WizardTextArea label="测试参数 JSON" value={testParamsText} onChange={setTestParamsText} rows={8} mono />
                <button className="btn primary" onClick={handleRunTest} disabled={testing || saving}>
                  <Icon name="play" />{testing ? '测试中…' : '运行测试'}
                </button>
              </div>
              <div style={{ border: '1px solid var(--hairline)', borderRadius: 8, overflow: 'hidden' }}>
                <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--hairline)', background: 'var(--bg-2)', fontSize: 12, color: 'var(--text-3)' }}>测试结果</div>
                {testResult ? (
                  <div style={{ padding: 12, fontSize: 12 }}>
                    <div style={{ color: 'var(--pos)', marginBottom: 8 }}>SQL 执行成功 ({testResult.execution_time_ms}ms)</div>
                    <div style={{ overflow: 'auto', marginBottom: 10 }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead><tr>{testResult.columns.map(c => <th key={c} style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid var(--hairline)', color: 'var(--text-3)' }}>{c}</th>)}</tr></thead>
                        <tbody>{testResult.rows.map((row, idx) => <tr key={idx}>{testResult.columns.map(c => <td key={c} style={{ padding: 6, borderBottom: '1px solid var(--hairline)' }}>{String(row[c] ?? '')}</td>)}</tr>)}</tbody>
                      </table>
                    </div>
                    <div style={{ lineHeight: 1.6, color: 'var(--text-2)' }}>{testResult.interpretation_preview}</div>
                  </div>
                ) : (
                  <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-3)', fontSize: 12 }}>运行测试后显示 SQL 结果和 AI 解读预览</div>
                )}
              </div>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', padding: '14px 18px', borderTop: '1px solid var(--hairline)' }}>
          <button className="btn ghost" onClick={onClose}>取消</button>
          {step > 1 && <button className="btn ghost" onClick={() => setStep(step - 1)}>上一步</button>}
          {step < 4 ? (
            <button className="btn primary" onClick={step === 1 ? handleAnalyze : () => setStep(step + 1)} disabled={analyzing}>
              {analyzing ? 'AI 分析中…' : step === 1 ? '下一步: AI 分析' : '下一步'}
            </button>
          ) : (
            <>
              <button className="btn ghost" onClick={saveDraft} disabled={saving}>存为草稿</button>
              <button className="btn primary" onClick={handlePublish}>发布蓝图</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function WizardField({ label, value, onChange }) {
  return (
    <label style={{ display: 'block', marginBottom: 10 }}>
      <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 4 }}>{label}</div>
      <input value={value || ''} onChange={e => onChange(e.target.value)} style={{ width: '100%', padding: '8px 10px', border: '1px solid var(--hairline)', borderRadius: 6, background: 'var(--surface)', fontSize: 13 }} />
    </label>
  );
}

function WizardTextArea({ label, value, onChange, rows = 6, mono = false }) {
  return (
    <label style={{ display: 'block', marginBottom: 10 }}>
      <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 4 }}>{label}</div>
      <textarea
        value={value || ''}
        onChange={e => onChange(e.target.value)}
        rows={rows}
        style={{ width: '100%', padding: '8px 10px', border: '1px solid var(--hairline)', borderRadius: 6, background: 'var(--surface)', fontSize: 12, lineHeight: 1.5, fontFamily: mono ? 'var(--font-mono)' : 'inherit', resize: 'vertical' }}
      />
    </label>
  );
}

function BlueprintDetail({ datasetId, blueprint, onChanged }) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  if (!blueprint) {
    return (
      <div className="blueprint-detail blueprint-detail-empty">
        <div className="blueprint-detail-empty-icon"><Icon name="eye" /></div>
        <h3>蓝图详情预览</h3>
        <p>选中蓝图后，这里展示触发问法、参数、输出列、测试结果和发布状态。</p>
        <div className="blueprint-checklist">
          {['AI 草稿审核', '参数与输出列确认', '测试通过', '发布生成版本'].map(item => (
            <span key={item}><Icon name="check" />{item}</span>
          ))}
        </div>
      </div>
    );
  }

  const runQuickTest = async () => {
    setTesting(true);
    try {
      const result = await testAnalysisBlueprint(datasetId, blueprint.id, {}, blueprint.name);
      setTestResult(result);
      onChanged?.({ ...blueprint, last_test_result: result });
    } catch (err) {
      alert('测试失败: ' + (err.message || '未知错误'));
    } finally {
      setTesting(false);
    }
  };

  const changeStatus = async (action) => {
    try {
      const updated = await updateAnalysisBlueprintStatus(datasetId, blueprint.id, { action });
      onChanged?.(updated);
    } catch (err) {
      alert('操作失败: ' + (err.message || '未知错误'));
    }
  };

  return (
    <div className="blueprint-detail">
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--hairline)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{blueprint.name}</div>
          <div style={{ fontSize: 11, color: 'var(--text-3)' }}>v{blueprint.version} · {blueprint.owner || '数据团队'}</div>
        </div>
        <BlueprintStatusBadge status={blueprint.status} />
      </div>
      <div style={{ display: 'flex', gap: 4, padding: '8px 10px', borderBottom: '1px solid var(--hairline)', overflow: 'auto' }}>
        {['概览', '参数·L1', '输出列·L1', '业务逻辑·L2', '测试', '使用记录'].map(t => (
          <span key={t} style={{ fontSize: 11, color: t === '概览' ? 'var(--text)' : 'var(--text-3)', background: t === '概览' ? 'var(--bg-2)' : 'transparent', padding: '3px 6px', borderRadius: 4, whiteSpace: 'nowrap' }}>{t}</span>
        ))}
      </div>
      <div style={{ padding: 12 }}>
        <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, marginBottom: 12 }}>{blueprint.description || '暂无描述'}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
          <Stat label="AI 置信度" value={blueprint.ai_confidence != null ? `${Math.round(blueprint.ai_confidence * 100)}%` : '—'} />
          <Stat label="参数" value={(blueprint.parameters || []).length} />
          <Stat label="输出列" value={(blueprint.output_schema || []).length} />
          <Stat label="最近验证" value={blueprint.last_validated_at ? blueprint.last_validated_at.slice(0, 10) : '未验证'} />
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 6 }}>触发问法</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          {(blueprint.trigger_examples || []).slice(0, 4).map(t => (
            <span key={t} style={{ padding: '2px 6px', borderRadius: 4, background: 'var(--bg-2)', color: 'var(--text-2)', fontSize: 11 }}>{t}</span>
          ))}
        </div>
        {testResult && (
          <div style={{ padding: 8, borderRadius: 6, background: 'var(--pos-soft)', color: 'var(--text-2)', fontSize: 12, marginBottom: 10 }}>
            测试成功: {testResult.rows.length} 行 · {testResult.columns.length} 列
          </div>
        )}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button className="btn ghost" onClick={runQuickTest} disabled={testing}><Icon name="play" />{testing ? '测试中…' : '测试'}</button>
          <button className="btn ghost" onClick={() => changeStatus('publish')}><Icon name="check" />发布</button>
          <button className="btn ghost" onClick={() => changeStatus('deprecated')}><Icon name="archive" />弃用</button>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div style={{ padding: 8, borderRadius: 6, background: 'var(--bg-2)' }}>
      <div style={{ fontSize: 10, color: 'var(--text-3)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 600 }}>{value}</div>
    </div>
  );
}

function AnalysisBlueprintsPanel({ datasetId }) {
  const [blueprints, setBlueprints] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);

  const loadBlueprints = async () => {
    if (!datasetId) return;
    setLoading(true);
    try {
      const data = await listAnalysisBlueprints(datasetId, status || undefined);
      setBlueprints(data);
      if (!selectedId && data.length) setSelectedId(data[0].id);
    } catch (err) {
      console.error('[blueprints] load failed:', err);
      setBlueprints([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBlueprints();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, status]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return blueprints;
    return blueprints.filter(bp => {
      const hay = [
        bp.name,
        bp.description,
        ...(bp.trigger_keywords || []),
        ...(bp.trigger_examples || []),
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [blueprints, query]);

  const selected = blueprints.find(bp => bp.id === selectedId) || filtered[0] || null;
  const statusCounts = useMemo(() => {
    return blueprints.reduce((acc, bp) => {
      acc[bp.status] = (acc[bp.status] || 0) + 1;
      return acc;
    }, {});
  }, [blueprints]);
  const testedCount = blueprints.filter(bp => (bp.last_test_result || {}).ok).length;

  const upsertBlueprint = (bp) => {
    setBluePrintsSafe(setBlueprints, bp);
    setSelectedId(bp.id);
  };

  return (
    <div className="blueprint-panel">
      <div className="blueprint-hero">
        <div className="blueprint-hero-main">
          <div className="blueprint-kicker"><Icon name="branch" />分析蓝图工作台</div>
          <h2>把复杂分析路径固化成可复用问数能力</h2>
          <p>从 SQL、存储过程或手工业务步骤生成蓝图，审核参数和输出列，通过测试后发布到问数链路。</p>
          <div className="blueprint-flow">
            {['SQL 导入', 'AI 拆解', '人工审核', '测试发布'].map((item, idx) => (
              <span key={item}>
                <strong>{idx + 1}</strong>{item}
              </span>
            ))}
          </div>
        </div>
        <div className="blueprint-hero-stats">
          <Stat label="蓝图总数" value={blueprints.length} />
          <Stat label="已发布" value={statusCounts.active || 0} />
          <Stat label="待审核" value={(statusCounts.draft || 0) + (statusCounts.reviewing || 0)} />
          <Stat label="已测试" value={testedCount} />
        </div>
      </div>

      <div className="blueprint-toolbar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, padding: '6px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--surface)' }}>
          <Icon name="search" style={{ width: 13, height: 13, color: 'var(--text-3)' }} />
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="搜索蓝图名称或触发词…"
            style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontSize: 13 }}
          />
        </div>
        <select value={status} onChange={e => setStatus(e.target.value)} style={{ height: 32, border: '1px solid var(--hairline)', borderRadius: 6, background: 'var(--surface)', fontSize: 12, color: 'var(--text-2)', padding: '0 8px' }}>
          <option value="">状态: 全部</option>
          <option value="draft">AI 草稿</option>
          <option value="reviewing">审核中</option>
          <option value="active">已发布</option>
          <option value="deprecated">已弃用</option>
        </select>
        <button className="btn primary" onClick={() => setWizardOpen(true)}><Icon name="plus" />新建蓝图</button>
      </div>

      <div className="blueprint-layout">
        <div className="blueprint-list">
          {loading ? (
            <div style={{ padding: 24, color: 'var(--text-3)', fontSize: 12 }}>加载中…</div>
          ) : blueprints.length === 0 ? (
            <BlueprintEmptyState onCreate={() => setWizardOpen(true)} />
          ) : filtered.length === 0 ? (
            <div className="blueprint-empty compact">
              <Icon name="search" />
              <h3>没有匹配的蓝图</h3>
              <p>调整关键词或状态筛选后重试。</p>
            </div>
          ) : (
            filtered.map(bp => (
              <button
                key={bp.id}
                onClick={() => setSelectedId(bp.id)}
                className={'blueprint-row ' + (selected?.id === bp.id ? 'selected' : '')}
              >
                <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: bp.status === 'active' ? 'var(--pos)' : bp.status === 'reviewing' ? 'var(--warn)' : 'var(--text-4)', marginTop: 7, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{bp.name}</div>
                      <BlueprintStatusBadge status={bp.status} />
                    </div>
                    <div style={{ color: 'var(--text-3)', fontSize: 12, marginTop: 4 }}>
                      触发: {(bp.trigger_keywords || []).join(' · ') || '—'}
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, color: 'var(--text-3)', fontSize: 11, marginTop: 6 }}>
                      <span>使用 {bp.usage_count || 0} 次 · v{bp.version}</span>
                      <span>参数: {(bp.parameters || []).map(p => p.name).join(', ') || '—'}</span>
                      <span>最近验证: {bp.last_validated_at ? bp.last_validated_at.slice(0, 10) : '未验证'}</span>
                    </div>
                    {bp.status === 'draft' && (
                      <div style={{ marginTop: 6, color: 'var(--warn)', fontSize: 11 }}>
                        待审核: AI 已生成草稿，需要数据团队确认
                      </div>
                    )}
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
        <BlueprintDetail datasetId={datasetId} blueprint={selected} onChanged={upsertBlueprint} />
      </div>

      <div style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap', color: 'var(--text-3)', fontSize: 11 }}>
        {['数据表选择', '字段标注', '指标管理', '维度管理', '语义验证', 'YAML 导入导出'].map(t => (
          <span key={t} style={{ padding: '3px 7px', border: '1px solid var(--hairline)', borderRadius: 5, background: 'var(--surface)' }}>{t}</span>
        ))}
      </div>

      {wizardOpen && (
        <BlueprintWizard
          datasetId={datasetId}
          onClose={() => setWizardOpen(false)}
          onSaved={(bp) => {
            upsertBlueprint(bp);
            loadBlueprints();
          }}
        />
      )}
    </div>
  );
}

function BlueprintEmptyState({ onCreate }) {
  return (
    <div className="blueprint-empty">
      <div className="blueprint-empty-head">
        <div className="blueprint-empty-icon"><Icon name="sparkle" /></div>
        <div>
          <h3>从第一条分析蓝图开始</h3>
          <p>适合沉淀“经营日报、库存预警、销售漏斗、NPS 归因”等跨表、跨步骤的高频分析。</p>
        </div>
      </div>

      <div className="blueprint-empty-grid">
        <div className="blueprint-empty-card primary">
          <div className="card-label">推荐入口</div>
          <h4>粘贴 SQL，让 AI 拆成蓝图</h4>
          <p>自动提取触发问法、参数、输出列和业务步骤，人工审核后即可测试发布。</p>
          <button className="btn primary" onClick={onCreate}><Icon name="plus" />新建蓝图</button>
        </div>
        {[
          ['经营日报', '按日期、区域、产品线汇总收入、毛利和异常波动。'],
          ['库存预警', '识别缺货风险、补货优先级和影响门店。'],
          ['客户价值', '按会员等级、渠道和生命周期拆解复购贡献。'],
        ].map(([title, desc]) => (
          <div key={title} className="blueprint-empty-card">
            <div className="card-label">样例场景</div>
            <h4>{title}</h4>
            <p>{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function setBluePrintsSafe(setter, bp) {
  setter(prev => {
    const exists = prev.some(item => item.id === bp.id);
    if (exists) return prev.map(item => item.id === bp.id ? bp : item);
    return [bp, ...prev];
  });
}

export { AnalysisBlueprintsPanel, BlueprintStatusBadge };
