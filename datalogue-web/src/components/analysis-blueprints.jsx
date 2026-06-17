import { useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from './icons';
import {
  analyzeBlueprintDescription,
  analyzeBlueprintSql,
  createBusinessTerm,
  createAnalysisBlueprint,
  getAnalysisBlueprintUsageStats,
  listAnalysisBlueprints,
  listAnalysisBlueprintUsageLogs,
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

const SOURCE_META = {
  sql_ai_analysis: { label: 'AI SQL分析', color: '#0369a1', bg: '#e0f2fe' },
  manual_ai_draft: { label: 'AI业务草稿', color: '#7c3aed', bg: '#ede9fe' },
  manual: { label: '手动填写', color: '#475569', bg: '#f1f5f9' },
};

const TERM_TYPE_LABELS = {
  business_object: '业务对象',
  metric_concept: '指标口径',
  dimension_enum: '维度枚举',
  status_enum: '状态枚举',
  business_process: '业务流程',
  org_scope: '组织口径',
};

const termTypeLabel = (type) => TERM_TYPE_LABELS[type] || type || '未分类';

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
  creation_source: 'manual',
  ai_generated: false,
  ai_generation_type: null,
  ai_confidence: null,
  owner: '',
};

const MANUAL_BLUEPRINT_EXAMPLE = {
  name: '区域销售波动分析',
  questions: '上周华东区销售为什么下降？\n本月哪些区域拖累了 GMV？',
  scenario: '当业务负责人询问某个区域、渠道或品类的销售变化原因时，先判断核心指标的环比/同比变化，再拆解订单量、客单价、转化率、退款等可能影响因素，最后给出主要贡献项。',
  output: '输出变化结论、影响最大的维度、关键指标变化和可继续追问的方向。优先用表格展示拆解结果，最后补充一段业务解读。',
  rules: '销售额只统计已支付订单；退款金额需要从销售额中扣除；默认按自然周比较，用户指定时间时以用户时间为准。',
};

const BLUEPRINT_MODE_META = {
  sql: {
    title: '从 SQL 导入',
    icon: 'sql',
    desc: '适合已有 SQL、存储过程或报表脚本，AI 会拆解参数、输出列和业务步骤。',
    badge: '工程迁移',
  },
  manual: {
    title: '手动创建',
    icon: 'edit',
    desc: '适合从业务问题出发，让 AI 根据场景、问法和口径生成语义蓝图草稿。',
    badge: '业务共创',
  },
};

const WIZARD_STEP_HELP = {
  sql: [
    '粘贴可运行 SQL 或存储过程，AI 会先做结构化拆解。',
    '确认 AI 提取的名称、触发词、问法和低置信字段。',
    '校准参数、输出列、业务逻辑和结果解读提示。',
    '保存草稿、按需运行测试，再发布到问数链路。',
  ],
  manual: [
    '用业务语言描述用户会问什么、判断逻辑和统计口径。',
    '确认 AI 生成的语义蓝图草稿，补齐触发问法。',
    '校准参数、输出列、业务逻辑和结果解读提示。',
    '保存草稿、按需运行测试，再发布到问数链路。',
  ],
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

function normalizeTermCandidateName(value) {
  return String(value || '')
    .replace(/[，。；;:：、,.!?！？()[\]{}"'`]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 48);
}

function buildBlueprintTermSuggestions({ blueprint, triggerKeywords, triggerExamples, businessRules }) {
  const candidates = [];
  const seen = new Set();
  const addCandidate = (rawName, sourceLabel, termType = 'business_object', definition = '', aliases = []) => {
    const name = normalizeTermCandidateName(rawName);
    if (!name || name.length < 2) return;
    const key = name.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    candidates.push({
      id: `${sourceLabel}-${key}`,
      name,
      display_name: name,
      term_type: termType,
      definition,
      aliases: aliases.filter(Boolean).slice(0, 5),
      examples: [],
      sourceLabel,
      status: 'pending',
      message: '',
    });
  };

  addCandidate(blueprint.name, '蓝图名称', 'business_process', blueprint.description || blueprint.when_to_use || '');
  (triggerKeywords || []).forEach(item => addCandidate(item, '触发关键词', 'business_object', blueprint.description || ''));
  (triggerExamples || []).slice(0, 3).forEach(item => addCandidate(item, '触发问法', 'business_process', blueprint.when_to_use || '', [blueprint.name]));
  (blueprint.parameters || []).forEach(param => {
    const label = typeof param === 'string' ? param : (param.label || param.name || param.key);
    addCandidate(label, '参数别名', 'dimension_enum', typeof param === 'string' ? '' : (param.description || ''), [typeof param === 'string' ? '' : param.name]);
  });
  (blueprint.output_schema || []).forEach(col => {
    const label = typeof col === 'string' ? col : (col.label || col.name || col.column || col.key);
    addCandidate(label, '输出口径', 'metric_concept', typeof col === 'string' ? '' : (col.description || ''), [typeof col === 'string' ? '' : col.name]);
  });

  const rules = String(businessRules || '').split(/[。\n；;]/).map(item => item.trim()).filter(Boolean);
  rules.slice(0, 2).forEach(item => {
    const shortName = item.length > 18 ? item.slice(0, 18) : item;
    addCandidate(shortName, '口径约束', 'metric_concept', item);
  });

  return candidates.slice(0, 8);
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

function BlueprintSourceBadge({ blueprint }) {
  const source = blueprint?.creation_source || (blueprint?.ai_generated ? 'sql_ai_analysis' : 'manual');
  const meta = SOURCE_META[source] || SOURCE_META.manual;
  return (
    <span className="blueprint-source-badge" style={{ color: meta.color, background: meta.bg }}>
      {meta.label}
    </span>
  );
}

function BlueprintWizard({ datasetId, onClose, onSaved }) {
  const [step, setStep] = useState(1);
  const [mode, setMode] = useState('sql');
  const [sqlText, setSqlText] = useState('');
  const [manualName, setManualName] = useState('');
  const [businessScenario, setBusinessScenario] = useState('');
  const [manualQuestionsText, setManualQuestionsText] = useState('');
  const [expectedOutput, setExpectedOutput] = useState('');
  const [businessRules, setBusinessRules] = useState('');
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
  const [termSuggestions, setTermSuggestions] = useState([]);
  const [termSuggestionBusyId, setTermSuggestionBusyId] = useState('');
  const [termSuggestionsOpen, setTermSuggestionsOpen] = useState(false);
  const stepLabels = mode === 'manual'
    ? ['描述场景', 'AI 草稿', '高级配置', '发布与测试']
    : ['上传 SQL', 'AI 审核', '精细配置', '触发与测试'];
  const stepHelp = WIZARD_STEP_HELP[mode];
  const currentStepHelp = stepHelp[step - 1] || '';
  const stepProgress = Math.round((step / stepLabels.length) * 100);
  const manualSummary = [
    ['蓝图名称', manualName],
    ['业务场景', businessScenario],
    ['用户可能问法', manualQuestionsText],
    ['希望输出', expectedOutput],
    ['数据口径约束', businessRules],
  ];
  const manualFilledCount = manualSummary.filter(([, value]) => String(value || '').trim()).length;

  const updateForm = (key, value) => setForm(prev => ({ ...prev, [key]: value }));

  const fillManualExample = () => {
    setManualName(MANUAL_BLUEPRINT_EXAMPLE.name);
    setManualQuestionsText(MANUAL_BLUEPRINT_EXAMPLE.questions);
    setBusinessScenario(MANUAL_BLUEPRINT_EXAMPLE.scenario);
    setExpectedOutput(MANUAL_BLUEPRINT_EXAMPLE.output);
    setBusinessRules(MANUAL_BLUEPRINT_EXAMPLE.rules);
  };

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
      creation_source: result.creation_source || (mode === 'manual' ? 'manual_ai_draft' : 'sql_ai_analysis'),
      ai_generated: result.ai_generated ?? true,
      ai_generation_type: result.ai_generation_type || (mode === 'manual' ? 'description_analysis' : 'sql_analysis'),
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
    setTermSuggestions(buildBlueprintTermSuggestions({
      blueprint: next,
      triggerKeywords: next.trigger_keywords || [],
      triggerExamples: next.trigger_examples || [],
      businessRules,
    }));
    const defaultOpen = typeof window !== 'undefined'
      ? window.matchMedia('(min-width: 761px)').matches
      : true;
    setTermSuggestionsOpen(defaultOpen);
  };

  const updateTermSuggestion = (id, patch) => {
    setTermSuggestions(prev => prev.map(item => (item.id === id ? { ...item, ...patch } : item)));
  };

  const handleAcceptTermSuggestion = async (suggestion) => {
    setTermSuggestionBusyId(suggestion.id);
    try {
      const saved = await createBusinessTerm(datasetId, {
        name: suggestion.name,
        display_name: suggestion.display_name || suggestion.name,
        term_type: suggestion.term_type || 'business_object',
        definition: suggestion.definition || '',
        aliases: suggestion.aliases || [],
        examples: suggestion.examples || [],
        status: 'draft',
        source: 'blueprint_wizard',
        extra_metadata: {
          source: 'analysis_blueprint_wizard',
          source_label: suggestion.sourceLabel,
          blueprint_name: form.name || manualName || '',
        },
      });
      updateTermSuggestion(suggestion.id, {
        status: 'accepted',
        termId: saved.id,
        message: '已沉淀到语义词典',
      });
    } catch (err) {
      const message = err.message || '未知错误';
      updateTermSuggestion(suggestion.id, {
        status: /409|同名|存在|duplicate/i.test(message) ? 'duplicate' : 'error',
        message: /409|同名|存在|duplicate/i.test(message)
          ? '已存在，建议复用已有词条'
          : `保存失败，不影响蓝图继续：${message}`,
      });
    } finally {
      setTermSuggestionBusyId('');
    }
  };

  const handleIgnoreTermSuggestion = (suggestion) => {
    updateTermSuggestion(suggestion.id, {
      status: 'ignored',
      message: '已忽略，不影响蓝图保存',
    });
  };

  const handleAnalyze = async () => {
    if (mode === 'manual') {
      if (!businessScenario.trim()) {
        alert('请先填写业务场景');
        return;
      }
      setAnalyzing(true);
      try {
        const task = await analyzeBlueprintDescription(datasetId, {
          name: manualName,
          business_scenario: businessScenario,
          example_questions: linesToArray(manualQuestionsText),
          expected_output: expectedOutput,
          business_rules: businessRules,
        });
        if (task.status === 'failed') {
          throw new Error(task.error || '分析任务失败');
        }
        applyAnalysisResult(task.result || {});
        setStep(2);
      } catch (err) {
        alert('AI 分析失败: ' + (err.message || '未知错误'));
      } finally {
        setAnalyzing(false);
      }
      return;
    }
    if (!sqlText.trim()) {
      alert('请先粘贴 SQL / 存储过程代码');
      return;
    }
    setAnalyzing(true);
    try {
      const task = await analyzeBlueprintSql(datasetId, sqlText);
      if (task.status === 'failed') {
        throw new Error(task.error || '分析任务失败');
      }
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
    raw_sql: mode === 'sql' ? (sqlText || form.raw_sql) : (form.raw_sql || ''),
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
      className="blueprint-wizard-backdrop"
      onClick={onClose}
    >
      <div
        className="blueprint-wizard"
        onClick={e => e.stopPropagation()}
      >
        <div className="blueprint-wizard-head">
          <div>
            <div className="blueprint-wizard-kicker"><Icon name="branch" />分析蓝图向导</div>
            <h3>新建分析蓝图</h3>
          </div>
          <div className="blueprint-wizard-progress" aria-label={`当前进度 ${stepProgress}%`}>
            <span>{stepProgress}%</span>
            <div><i style={{ width: `${stepProgress}%` }} /></div>
          </div>
          <button className="icon-btn" onClick={onClose} title="关闭"><Icon name="x" /></button>
        </div>

        <div className="blueprint-wizard-shell">
          <aside className="blueprint-wizard-side">
            <div className="blueprint-side-section">
              <div className="blueprint-side-title">创建方式</div>
              {Object.entries(BLUEPRINT_MODE_META).map(([key, item]) => (
                <BlueprintModeButton
                  key={key}
                  item={item}
                  active={mode === key}
                  onClick={() => setMode(key)}
                />
              ))}
            </div>
            <div className="blueprint-side-section">
              <div className="blueprint-side-title">流程</div>
              <BlueprintWizardStepper labels={stepLabels} activeStep={step} help={stepHelp} />
            </div>
            <div className="blueprint-assistant-note">
              <Icon name="sparkle" />
              <div>
                <strong>{mode === 'manual' ? 'AI 会读取业务语义' : 'AI 会解析 SQL 结构'}</strong>
                <span>{currentStepHelp}</span>
              </div>
            </div>
          </aside>

          <main className="blueprint-wizard-main">
            <BlueprintWizardStage
              eyebrow={stepLabels[step - 1]}
              title={mode === 'manual' && step === 1 ? '描述你要沉淀的业务分析能力' : mode === 'sql' && step === 1 ? '粘贴已有 SQL 或存储过程' : step === 2 ? '确认 AI 生成的蓝图草稿' : step === 3 ? '校准高级结构化配置' : '测试、保存并发布'}
              desc={currentStepHelp}
            />

            {step === 1 && (
              mode === 'sql' ? (
                <textarea
                  className="blueprint-sql-composer"
                  value={sqlText}
                  onChange={e => setSqlText(e.target.value)}
                  placeholder={'粘贴 SQL / 存储过程代码...\n\n示例：\nSELECT region, SUM(order_amount) AS gmv\nFROM orders\nWHERE pay_status = :status AND order_date BETWEEN :start_date AND :end_date\nGROUP BY region'}
                />
              ) : (
                <div className="blueprint-manual-workbench">
                  <section className="blueprint-manual-form">
                    <ManualBlueprintExample onUseExample={fillManualExample} />
                    <WizardField
                      label="蓝图名称"
                      value={manualName}
                      onChange={setManualName}
                      placeholder={`例如：${MANUAL_BLUEPRINT_EXAMPLE.name}`}
                      hint="用业务人员能搜索到的名称，不需要写数据表或 SQL。"
                    />
                    <WizardTextArea
                      label="用户可能问法"
                      value={manualQuestionsText}
                      onChange={setManualQuestionsText}
                      rows={4}
                      placeholder={MANUAL_BLUEPRINT_EXAMPLE.questions}
                      hint="每行一条，写真实用户会问出口的问题。"
                    />
                    <WizardTextArea
                      label="业务场景"
                      value={businessScenario}
                      onChange={setBusinessScenario}
                      rows={7}
                      placeholder={MANUAL_BLUEPRINT_EXAMPLE.scenario}
                      hint="说明这个蓝图要解决什么业务问题、通常怎么判断结果。"
                    />
                    <WizardTextArea
                      label="希望输出"
                      value={expectedOutput}
                      onChange={setExpectedOutput}
                      rows={6}
                      placeholder={MANUAL_BLUEPRINT_EXAMPLE.output}
                      hint="描述希望 AI 返回哪些结论、表格或拆解维度。"
                    />
                    <WizardTextArea
                      label="数据口径约束"
                      value={businessRules}
                      onChange={setBusinessRules}
                      rows={5}
                      placeholder={MANUAL_BLUEPRINT_EXAMPLE.rules}
                      hint="填写统计边界、默认时间、排除条件、业务口径等约束。"
                    />
                  </section>
                  <BlueprintInputDigest items={manualSummary} filledCount={manualFilledCount} />
                </div>
              )
            )}

            {step === 2 && (
              <div className="blueprint-review-grid">
                <section className="blueprint-editor-stack">
                  <div className="blueprint-section-label">AI 提取，可编辑</div>
                  <WizardField label="蓝图名称" value={form.name} onChange={v => updateForm('name', v)} />
                  <WizardTextArea label="业务描述" value={form.description} onChange={v => updateForm('description', v)} rows={4} />
                  <WizardTextArea label="触发关键词（每行一条）" value={triggerKeywordsText} onChange={setTriggerKeywordsText} rows={4} />
                  <WizardTextArea label="触发问法（每行一条）" value={triggerExamplesText} onChange={setTriggerExamplesText} rows={4} />
                  <div className="blueprint-confidence">
                    AI 置信度: <strong>{form.ai_confidence != null ? Math.round(form.ai_confidence * 100) : 0}%</strong>
                  </div>
                  {lowConfidenceFields.length > 0 && (
                    <div className="blueprint-warn-box">
                      {lowConfidenceFields.map((f, idx) => (
                        <div key={idx}>需确认: {f.path} · {Math.round((f.confidence || 0) * 100)}%</div>
                      ))}
                    </div>
                  )}
                </section>
                <div style={{ display: 'grid', gap: 12 }}>
                  <section className="blueprint-source-preview">
                    <div className="blueprint-section-label">{mode === 'manual' ? '业务场景输入' : '原始 SQL，只读'}</div>
                    <pre>
                      {mode === 'manual'
                        ? [
                            manualName && `蓝图名称：${manualName}`,
                            businessScenario && `业务场景：${businessScenario}`,
                            manualQuestionsText && `用户可能问法：\n${manualQuestionsText}`,
                            expectedOutput && `希望输出：${expectedOutput}`,
                            businessRules && `数据口径约束：${businessRules}`,
                          ].filter(Boolean).join('\n\n')
                        : (sqlText || form.raw_sql)}
                    </pre>
                  </section>
                  <section className={'blueprint-source-preview blueprint-term-suggestions ' + (termSuggestionsOpen ? 'expanded' : '')} aria-label="建议别名与口径">
                    <button
                      type="button"
                      className="blueprint-term-suggestions-head"
                      onClick={() => setTermSuggestionsOpen(open => !open)}
                      aria-expanded={termSuggestionsOpen}
                    >
                      <span>
                        <span className="blueprint-section-label">建议别名与口径</span>
                        <small>{termSuggestions.length ? `${termSuggestions.length} 个候选，可接受或忽略` : '未发现候选，不影响保存'}</small>
                      </span>
                      <Icon name="chev_down" />
                    </button>
                    <div className="blueprint-term-suggestions-body">
                      {termSuggestions.length === 0 ? (
                        <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
                          未发现需要沉淀的别名。可以继续保存蓝图，语义词典不是必填项。
                        </div>
                      ) : termSuggestions.map(suggestion => (
                        <div key={suggestion.id} className="term-candidate blueprint-term-suggestion-row" style={{ alignItems: 'flex-start' }}>
                          <div>
                            <strong>{suggestion.display_name || suggestion.name}</strong>
                            <span>{suggestion.sourceLabel} · {termTypeLabel(suggestion.term_type)}</span>
                            {suggestion.message && (
                              <span style={{
                                display: 'block',
                                marginTop: 4,
                                color: suggestion.status === 'error' ? 'var(--neg)' : suggestion.status === 'duplicate' ? 'var(--warn)' : 'var(--text-3)',
                              }}>
                                {suggestion.message}
                              </span>
                            )}
                          </div>
                          <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                            {suggestion.status === 'pending' ? (
                              <>
                                <button
                                  className="btn ghost"
                                  onClick={() => handleIgnoreTermSuggestion(suggestion)}
                                  disabled={Boolean(termSuggestionBusyId)}
                                  type="button"
                                >
                                  忽略
                                </button>
                                <button
                                  className="btn ghost"
                                  onClick={() => handleAcceptTermSuggestion(suggestion)}
                                  disabled={Boolean(termSuggestionBusyId)}
                                  type="button"
                                >
                                  {termSuggestionBusyId === suggestion.id ? '保存中…' : '接受'}
                                </button>
                              </>
                            ) : (
                              <span className={'term-status ' + (suggestion.status === 'accepted' ? 'active' : 'draft')}>
                                {suggestion.status === 'accepted' ? '已沉淀' : suggestion.status === 'ignored' ? '已忽略' : suggestion.status === 'duplicate' ? '可复用' : '失败'}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                </div>
              </div>
            )}

            {step === 3 && (
              <div className="blueprint-config-grid">
                <WizardTextArea label="参数列表 JSON" value={parametersText} onChange={setParametersText} rows={12} mono />
                <WizardTextArea label="输出列语义 JSON" value={outputSchemaText} onChange={setOutputSchemaText} rows={12} mono />
                <WizardTextArea label="业务逻辑步骤 JSON" value={stepsText} onChange={setStepsText} rows={12} mono />
                <WizardTextArea label="结果解读提示" value={form.attribution_hints || ''} onChange={v => updateForm('attribution_hints', v)} rows={12} />
              </div>
            )}

            {step === 4 && (
              <div className="blueprint-review-grid">
                <section className="blueprint-editor-stack">
                  <WizardTextArea label="触发问法（至少 2 条，每行一条）" value={triggerExamplesText} onChange={setTriggerExamplesText} rows={8} />
                  <WizardTextArea label="测试参数 JSON" value={testParamsText} onChange={setTestParamsText} rows={8} mono />
                  <button className="btn primary" onClick={handleRunTest} disabled={testing || saving}>
                    <Icon name="play" />{testing ? '测试中…' : '运行测试'}
                  </button>
                </section>
                <section className="blueprint-test-panel">
                  <div className="blueprint-test-head">测试结果</div>
                  {testResult ? (
                    <div className="blueprint-test-body">
                      <div className="blueprint-test-ok">SQL 执行成功 ({testResult.execution_time_ms}ms)</div>
                      <div className="blueprint-result-table">
                        <table>
                          <thead><tr>{testResult.columns.map(c => <th key={c}>{c}</th>)}</tr></thead>
                          <tbody>{testResult.rows.map((row, idx) => <tr key={idx}>{testResult.columns.map(c => <td key={c}>{String(row[c] ?? '')}</td>)}</tr>)}</tbody>
                        </table>
                      </div>
                      <div className="blueprint-test-copy">{testResult.interpretation_preview}</div>
                    </div>
                  ) : (
                    <div className="blueprint-test-empty">运行测试后显示 SQL 结果和 AI 解读预览</div>
                  )}
                </section>
              </div>
            )}
          </main>
        </div>

        <div className="blueprint-wizard-actions">
          <div className="blueprint-action-hint">
            {step === 1 && mode === 'manual'
              ? `已填写 ${manualFilledCount}/5 项，业务场景为必填。`
              : currentStepHelp}
          </div>
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

function BlueprintModeButton({ item, active, onClick }) {
  return (
    <button className={'blueprint-mode-option ' + (active ? 'active' : '')} onClick={onClick}>
      <span className="blueprint-mode-icon"><Icon name={item.icon} /></span>
      <span>
        <strong>{item.title}</strong>
        <em>{item.desc}</em>
      </span>
      <small>{item.badge}</small>
    </button>
  );
}

function BlueprintWizardStepper({ labels, activeStep, help }) {
  return (
    <div className="blueprint-stepper">
      {labels.map((label, idx) => {
        const stepNo = idx + 1;
        const done = stepNo < activeStep;
        const active = stepNo === activeStep;
        return (
          <button
            key={label}
            className={'blueprint-step-item ' + (active ? 'active ' : '') + (done ? 'done' : '')}
            type="button"
            disabled
          >
            <span>{done ? <Icon name="check" /> : stepNo}</span>
            <strong>{label}</strong>
            <em>{help[idx]}</em>
          </button>
        );
      })}
    </div>
  );
}

function BlueprintWizardStage({ eyebrow, title, desc }) {
  return (
    <div className="blueprint-stage-head">
      <div className="blueprint-section-label">{eyebrow}</div>
      <h4>{title}</h4>
      <p>{desc}</p>
    </div>
  );
}

function ManualBlueprintExample({ onUseExample }) {
  return (
    <div className="blueprint-example-panel">
      <div className="blueprint-example-head">
        <span><Icon name="sparkle" />填写示例</span>
        <button type="button" className="btn ghost" onClick={onUseExample}>套用示例</button>
      </div>
      <div className="blueprint-example-grid">
        <ExampleLine label="业务场景" text={MANUAL_BLUEPRINT_EXAMPLE.scenario} />
        <ExampleLine label="希望输出" text={MANUAL_BLUEPRINT_EXAMPLE.output} />
        <ExampleLine label="用户问法" text={MANUAL_BLUEPRINT_EXAMPLE.questions.replace('\n', ' / ')} />
        <ExampleLine label="口径约束" text={MANUAL_BLUEPRINT_EXAMPLE.rules} />
      </div>
    </div>
  );
}

function ExampleLine({ label, text }) {
  return (
    <div className="blueprint-example-line">
      <span>{label}: </span>
      <span>{text}</span>
    </div>
  );
}

function BlueprintInputDigest({ items, filledCount }) {
  return (
    <aside className="blueprint-input-digest">
      <div className="blueprint-digest-head">
        <div>
          <div className="blueprint-section-label">AI 输入摘要</div>
          <strong>{filledCount}/5 项已填写</strong>
        </div>
        <Icon name="sparkle" />
      </div>
      <div className="blueprint-digest-list">
        {items.map(([label, value]) => (
          <DigestLine key={label} label={label} value={value} />
        ))}
      </div>
      <div className="blueprint-digest-note">
        这里展示 AI 将读取的业务语义。保持描述清楚即可，不需要写 SQL、表名或字段名。
      </div>
    </aside>
  );
}

function DigestLine({ label, value }) {
  const text = String(value || '').trim();
  return (
    <div className={'blueprint-digest-line ' + (text ? 'filled' : '')}>
      <span>{label}</span>
      <p>{text || '待填写'}</p>
    </div>
  );
}

function WizardField({ label, value, onChange, placeholder = '', hint = '' }) {
  return (
    <label className="blueprint-form-field">
      <div>{label}</div>
      {hint && <span>{hint}</span>}
      <input value={value || ''} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
    </label>
  );
}

function WizardTextArea({ label, value, onChange, rows = 6, mono = false, placeholder = '', hint = '' }) {
  return (
    <label className="blueprint-form-field">
      <div>{label}</div>
      {hint && <span>{hint}</span>}
      <textarea
        className={mono ? 'mono' : ''}
        value={value || ''}
        onChange={e => onChange(e.target.value)}
        rows={rows}
        placeholder={placeholder}
      />
    </label>
  );
}

function BlueprintDetail({ datasetId, blueprint, onChanged }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [testing, setTesting] = useState(false);
  const [actionBusy, setActionBusy] = useState('');
  const [testResult, setTestResult] = useState(blueprint?.last_test_result || null);
  const [testQuestion, setTestQuestion] = useState('');
  const [testParams, setTestParams] = useState({});
  const [usageStats, setUsageStats] = useState(null);
  const [usageLogs, setUsageLogs] = useState([]);
  const [usageLoading, setUsageLoading] = useState(false);
  const previousBlueprintId = useRef(null);
  const blueprintId = blueprint?.id;
  const blueprintName = blueprint?.name || '';
  const blueprintParameters = useMemo(() => blueprint?.parameters || [], [blueprint?.parameters]);
  const blueprintTriggerExamples = useMemo(() => blueprint?.trigger_examples || [], [blueprint?.trigger_examples]);
  const blueprintLastTestResult = blueprint?.last_test_result || null;
  const detailTabs = [
    { id: 'overview', label: '概览' },
    { id: 'parameters', label: `参数·L1 (${blueprintParameters.length})` },
    { id: 'outputs', label: `输出列·L1 (${(blueprint?.output_schema || []).length})` },
    { id: 'steps', label: `业务逻辑·L2 (${(blueprint?.steps || []).length})` },
    { id: 'test', label: '测试' },
    { id: 'usage', label: '使用记录' },
  ];

  useEffect(() => {
    if (!blueprintId) return;
    const switchedBlueprint = previousBlueprintId.current !== blueprintId;
    previousBlueprintId.current = blueprintId;
    setTestResult(blueprintLastTestResult);
    if (switchedBlueprint) {
      setActiveTab('overview');
      setTestQuestion(blueprintTriggerExamples[0] || blueprintName);
      setTestParams(buildDefaultParams(blueprintParameters));
      setUsageStats(null);
      setUsageLogs([]);
    }
  }, [blueprintId, blueprintLastTestResult, blueprintName, blueprintParameters, blueprintTriggerExamples]);

  useEffect(() => {
    if (!blueprintId || activeTab !== 'usage') return;
    let cancelled = false;
    const loadUsage = async () => {
      setUsageLoading(true);
      try {
        const [stats, logs] = await Promise.all([
          getAnalysisBlueprintUsageStats(datasetId, blueprintId),
          listAnalysisBlueprintUsageLogs(datasetId, blueprintId),
        ]);
        if (!cancelled) {
          setUsageStats(stats);
          setUsageLogs(logs || []);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('[blueprints] usage load failed:', err);
          setUsageStats(null);
          setUsageLogs([]);
        }
      } finally {
        if (!cancelled) setUsageLoading(false);
      }
    };
    loadUsage();
    return () => {
      cancelled = true;
    };
  }, [activeTab, blueprintId, datasetId]);

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
      const result = await testAnalysisBlueprint(datasetId, blueprint.id, testParams, testQuestion || blueprint.name);
      setTestResult(result);
      onChanged?.({ ...blueprint, last_test_result: result, last_validated_at: new Date().toISOString() });
      setActiveTab('test');
    } catch (err) {
      alert('测试失败: ' + (err.message || '未知错误'));
    } finally {
      setTesting(false);
    }
  };

  const changeStatus = async (action) => {
    setActionBusy(action);
    try {
      const updated = await updateAnalysisBlueprintStatus(datasetId, blueprint.id, {
        action,
        change_summary: action === 'publish' ? '详情页发布蓝图' : action === 'deprecate' ? '详情页弃用蓝图' : '详情页重新启用蓝图',
      });
      onChanged?.(updated);
    } catch (err) {
      alert('操作失败: ' + (err.message || '未知错误'));
    } finally {
      setActionBusy('');
    }
  };

  const statusAction = blueprint.status === 'deprecated'
    ? { action: 'reactivate', label: '重新启用', icon: 'check' }
    : { action: 'deprecate', label: '弃用', icon: 'archive' };

  return (
    <div className="blueprint-detail">
      <div className="blueprint-detail-head">
        <div>
          <div className="blueprint-detail-title">{blueprint.name}</div>
          <div className="blueprint-detail-meta">
            v{blueprint.version} · {blueprint.owner || '数据团队'} · <BlueprintSourceBadge blueprint={blueprint} />
          </div>
        </div>
        <BlueprintStatusBadge status={blueprint.status} />
      </div>
      <div className="blueprint-detail-tabs">
        {detailTabs.map(tab => (
          <button key={tab.id} className={activeTab === tab.id ? 'active' : ''} onClick={() => setActiveTab(tab.id)}>
            {tab.label}
          </button>
        ))}
      </div>
      <div className="blueprint-detail-body">
        {activeTab === 'overview' && (
          <BlueprintOverview blueprint={blueprint} testResult={testResult} onOpenTab={setActiveTab} />
        )}
        {activeTab === 'parameters' && (
          <StructuredList
            emptyText="暂无参数定义"
            items={blueprint.parameters || []}
            renderItem={(item, idx) => <ParameterCard key={item.name || idx} item={item} />}
          />
        )}
        {activeTab === 'outputs' && (
          <StructuredList
            emptyText="暂无输出列定义"
            items={blueprint.output_schema || []}
            renderItem={(item, idx) => <OutputColumnCard key={item.name || idx} item={item} />}
          />
        )}
        {activeTab === 'steps' && (
          <BlueprintStepView steps={blueprint.steps || []} />
        )}
        {activeTab === 'test' && (
          <BlueprintTestPanel
            blueprint={blueprint}
            params={testParams}
            question={testQuestion}
            result={testResult}
            testing={testing}
            onParamChange={(name, value) => setTestParams(prev => ({ ...prev, [name]: value }))}
            onQuestionChange={setTestQuestion}
            onRun={runQuickTest}
          />
        )}
        {activeTab === 'usage' && (
          <BlueprintUsagePanel loading={usageLoading} stats={usageStats} logs={usageLogs} />
        )}
        <div className="blueprint-detail-actions">
          <button className="btn ghost" onClick={() => setActiveTab('test')} disabled={testing}>
            <Icon name="play" />测试
          </button>
          <button className="btn ghost" onClick={() => changeStatus('publish')} disabled={actionBusy === 'publish' || blueprint.status === 'active'}>
            <Icon name="check" />{actionBusy === 'publish' ? '发布中…' : '发布'}
          </button>
          <button className="btn ghost" onClick={() => changeStatus(statusAction.action)} disabled={Boolean(actionBusy)}>
            <Icon name={statusAction.icon} />{actionBusy === statusAction.action ? '处理中…' : statusAction.label}
          </button>
        </div>
      </div>
    </div>
  );
}

function BlueprintOverview({ blueprint, testResult, onOpenTab }) {
  return (
    <div className="blueprint-overview">
      <div className="blueprint-description">{blueprint.description || '暂无描述'}</div>
      <div className="blueprint-stat-grid">
        <Stat label="AI 置信度" value={blueprint.ai_confidence != null ? `${Math.round(blueprint.ai_confidence * 100)}%` : '—'} />
        <Stat label="参数" value={(blueprint.parameters || []).length} onClick={() => onOpenTab('parameters')} />
        <Stat label="输出列" value={(blueprint.output_schema || []).length} onClick={() => onOpenTab('outputs')} />
        <Stat label="最近验证" value={blueprint.last_validated_at ? blueprint.last_validated_at.slice(0, 10) : '未验证'} />
      </div>
      <InfoBlock label="触发关键词" values={blueprint.trigger_keywords || []} emptyText="暂无触发关键词" />
      <InfoBlock label="触发问法" values={(blueprint.trigger_examples || []).slice(0, 8)} emptyText="暂无触发问法" />
      {blueprint.when_to_use && <InfoText label="适用条件" text={blueprint.when_to_use} />}
      {testResult && (
        <div className={testResult.ok ? 'blueprint-test-status ok' : 'blueprint-test-status failed'}>
          {testResult.ok
            ? `最近测试成功：${(testResult.rows || []).length} 行 · ${(testResult.columns || []).length} 列`
            : `最近测试失败：${testResult.error_message || '未知错误'}`}
        </div>
      )}
    </div>
  );
}

function InfoBlock({ label, values, emptyText }) {
  return (
    <div className="blueprint-info-block">
      <div className="blueprint-mini-label">{label}</div>
      <div className="blueprint-chip-list">
        {values.length ? values.map(value => <span key={value}>{value}</span>) : <em>{emptyText}</em>}
      </div>
    </div>
  );
}

function InfoText({ label, text }) {
  return (
    <div className="blueprint-info-block">
      <div className="blueprint-mini-label">{label}</div>
      <p>{text}</p>
    </div>
  );
}

function StructuredList({ items, renderItem, emptyText }) {
  if (!items.length) {
    return <div className="blueprint-empty-inline">{emptyText}</div>;
  }
  return <div className="blueprint-structured-list">{items.map(renderItem)}</div>;
}

function ParameterCard({ item }) {
  if (typeof item === 'string') {
    return (
      <div className="blueprint-structured-card">
        <div className="blueprint-structured-head">
          <strong>{item}</strong>
          <span>string</span>
        </div>
        <p>暂无说明</p>
      </div>
    );
  }

  return (
    <div className="blueprint-structured-card">
      <div className="blueprint-structured-head">
        <strong>{item.name || item.key || '未命名参数'}</strong>
        <span>{item.type || item.data_type || 'string'}</span>
      </div>
      <p>{item.description || item.business_meaning || item.label || '暂无说明'}</p>
      <div className="blueprint-card-meta">
        <span>必填: {item.required === false ? '否' : '是'}</span>
        {item.default != null && <span>默认值: {String(item.default)}</span>}
        {item.enum_values?.length ? <span>枚举: {item.enum_values.join(', ')}</span> : null}
      </div>
    </div>
  );
}

function OutputColumnCard({ item }) {
  if (typeof item === 'string') {
    return (
      <div className="blueprint-structured-card">
        <div className="blueprint-structured-head">
          <strong>{item}</strong>
          <span>字段</span>
        </div>
        <p>来自分析 SQL 的输出列</p>
      </div>
    );
  }
  const columnName = item.name || item.key || item.column || item.field || item.path || item.column_name || item.alias;
  const columnType = item.type || item.data_type || item.role || item.semantic_type || '字段';
  const columnDescription = item.description || item.business_meaning || item.semantic || item.reason || item.label || '暂无说明';

  return (
    <div className="blueprint-structured-card">
      <div className="blueprint-structured-head">
        <strong>{columnName || '未命名输出列'}</strong>
        <span>{columnType}</span>
      </div>
      <p>{columnDescription}</p>
      <div className="blueprint-card-meta">
        {item.format && <span>格式: {item.format}</span>}
        {item.source && <span>来源: {item.source}</span>}
      </div>
    </div>
  );
}

function BlueprintStepView({ steps }) {
  if (!steps || steps.length === 0) {
    return (
      <div className="blueprint-empty-inline" data-testid="blueprint-steps-empty">
        暂无业务步骤
      </div>
    );
  }

  return (
    <div className="blueprint-step-view" data-testid="blueprint-step-view">
      {steps.map((item, index) => (
        <StepCard key={item.id || item.name || index} item={item} index={index} />
      ))}
    </div>
  );
}

function StepCard({ item, index }) {
  const [jsonOpen, setJsonOpen] = useState(false);

  if (typeof item === 'string') {
    return (
      <div className="blueprint-step-card" data-testid="step-card">
        <span className="step-badge">{index + 1}</span>
        <div>
          <strong>{`步骤 ${index + 1}`}</strong>
          <p>{item}</p>
        </div>
      </div>
    );
  }

  const stepNo = item.step || index + 1;
  const name = item.name || item.title || `步骤 ${index + 1}`;
  const purpose = item.purpose || item.description || item.action || item.logic || '';
  const rules = item.key_rules || item.rules || [];
  const outputs = item.output_columns || item.outputs || [];
  const confidence = item.confidence;

  const showAllOutputs = outputs.length <= 10;
  const visibleOutputs = showAllOutputs ? outputs : outputs.slice(0, 10);
  const hiddenCount = outputs.length - visibleOutputs.length;

  return (
    <div className="blueprint-step-card" data-testid="step-card">
      <div className="step-card-header">
        <span className="step-badge" data-testid="step-number">{stepNo}</span>
        <strong data-testid="step-name">{name}</strong>
      </div>

      <div className="step-card-body">
        <div className="step-section" data-testid="step-purpose">
          <div className="step-section-label">业务描述</div>
          <p>{purpose || '暂无业务描述'}</p>
        </div>

        {rules.length > 0 && (
          <div className="step-section" data-testid="step-rules">
            <div className="step-section-label">关键规则</div>
            <ul className="step-rule-list">
              {rules.map((rule, idx) => (
                <li key={idx} data-testid="step-rule-item">{rule}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="step-section" data-testid="step-outputs">
          <div className="step-section-label">输出列</div>
          {outputs.length === 0 ? (
            <span className="step-empty-text">无输出列</span>
          ) : (
            <div className="step-output-tags">
              {visibleOutputs.map((col, idx) => (
                <span key={idx} className="step-output-tag" data-testid="step-output-tag">{col}</span>
              ))}
              {!showAllOutputs && (
                <span className="step-output-tag step-output-tag-more" data-testid="step-output-more">
                  +{hiddenCount}
                </span>
              )}
            </div>
          )}
        </div>

        {confidence != null && (
          <div className="step-section" data-testid="step-confidence">
            <div className="step-section-label">置信度</div>
            <div className="step-confidence-bar">
              <div
                className="step-confidence-fill"
                style={{ width: `${Math.round(confidence * 100)}%` }}
                data-testid="step-confidence-fill"
              />
            </div>
            <span className="step-confidence-text">{Math.round(confidence * 100)}%</span>
          </div>
        )}
      </div>

      <div className="step-card-footer">
        <button
          className="btn ghost step-json-toggle"
          onClick={() => setJsonOpen(open => !open)}
          data-testid="step-json-toggle"
        >
          {jsonOpen ? '收起原始 JSON' : '展开原始 JSON'}
        </button>
        {jsonOpen && (
          <pre className="step-json-block" data-testid="step-json-block">
            {formatJson(item)}
          </pre>
        )}
      </div>
    </div>
  );
}

function BlueprintTestPanel({ blueprint, params, question, result, testing, onParamChange, onQuestionChange, onRun }) {
  return (
    <div className="blueprint-test-workbench">
      <div className="blueprint-test-form">
        <label className="blueprint-form-field">
          <div>测试问法</div>
          <span>用于模拟用户问题，也会写入本次测试请求。</span>
          <input value={question || ''} onChange={e => onQuestionChange(e.target.value)} placeholder={blueprint.name} />
        </label>
        <div className="blueprint-mini-label">测试参数</div>
        {(blueprint.parameters || []).length ? (
          <div className="blueprint-param-grid">
            {(blueprint.parameters || []).map((param, idx) => {
              const paramKey = getParameterKey(param, idx);
              const placeholder = typeof param === 'string' ? '输入测试值' : (param.description || param.type || '输入测试值');
              return (
                <label key={paramKey} className="blueprint-param-input">
                  <span>{paramKey}</span>
                  <input
                    value={params[paramKey] ?? ''}
                    onChange={e => onParamChange(paramKey, e.target.value)}
                    placeholder={placeholder}
                  />
                </label>
              );
            })}
          </div>
        ) : (
          <div className="blueprint-empty-inline">当前蓝图没有参数，测试会直接运行。</div>
        )}
        <button className="btn primary" onClick={onRun} disabled={testing}>
          <Icon name="play" />{testing ? '测试中…' : '运行测试'}
        </button>
      </div>
      <BlueprintTestResult result={result} />
    </div>
  );
}

function BlueprintTestResult({ result }) {
  if (!result) {
    return <div className="blueprint-empty-inline">运行测试后显示 SQL 预览、结果数据和错误信息。</div>;
  }
  return (
    <div className="blueprint-test-result">
      <div className={result.ok ? 'blueprint-test-status ok' : 'blueprint-test-status failed'}>
        {result.ok ? `执行成功 · ${result.execution_time_ms}ms` : `执行失败 · ${result.error_message || '未知错误'}`}
      </div>
      {result.sql_preview && (
        <pre className="blueprint-sql-preview">{result.sql_preview}</pre>
      )}
      {(result.columns || []).length > 0 && (
        <div className="blueprint-result-table">
          <table>
            <thead><tr>{result.columns.map(c => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>{(result.rows || []).slice(0, 20).map((row, idx) => <tr key={idx}>{result.columns.map(c => <td key={c}>{String(row[c] ?? '')}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
      {result.interpretation_preview && <p>{result.interpretation_preview}</p>}
    </div>
  );
}

function BlueprintUsagePanel({ loading, stats, logs }) {
  if (loading) return <div className="blueprint-empty-inline">使用记录加载中…</div>;
  return (
    <div className="blueprint-usage-panel">
      <div className="blueprint-stat-grid">
        <Stat label="调用次数" value={stats?.usage_count ?? 0} />
        <Stat label="日志总数" value={stats?.total_logs ?? 0} />
        <Stat label="成功率" value={`${Math.round((stats?.execution_success_rate || 0) * 100)}%`} />
        <Stat label="平均耗时" value={`${stats?.avg_execution_time_ms || 0}ms`} />
      </div>
      <div className="blueprint-mini-label">最近调用</div>
      {(logs || []).length ? (
        <div className="blueprint-usage-list">
          {logs.map(log => (
            <div key={log.id} className="blueprint-usage-row">
              <strong>{log.question || '未记录问题'}</strong>
              <span>{log.execution_success ? '成功' : '失败'} · {log.execution_time_ms ?? 0}ms · {formatDateTime(log.created_at)}</span>
              {log.error_message && <p>{log.error_message}</p>}
            </div>
          ))}
        </div>
      ) : (
        <div className="blueprint-empty-inline">暂无真实调用记录。</div>
      )}
    </div>
  );
}

function buildDefaultParams(parameters) {
  return (parameters || []).reduce((acc, param) => {
    const name = getParameterKey(param, Object.keys(acc).length);
    if (!name) return acc;
    acc[name] = typeof param === 'string' ? '' : (param.default ?? param.default_value ?? param.example ?? '');
    return acc;
  }, {});
}

function getParameterKey(param, index) {
  if (typeof param === 'string') return param;
  return param.name || param.key || `param_${index + 1}`;
}

function formatDateTime(value) {
  if (!value) return '未知时间';
  return String(value).replace('T', ' ').slice(0, 19);
}

function Stat({ label, value, onClick }) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag className={'blueprint-stat-card ' + (onClick ? 'clickable' : '')} onClick={onClick}>
      <div>{label}</div>
      <strong>{value}</strong>
    </Tag>
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
                      <BlueprintSourceBadge blueprint={bp} />
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
