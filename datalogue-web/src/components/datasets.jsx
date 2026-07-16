import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Icon } from './icons';
import { AnalysisBlueprintsPanel } from './analysis-blueprints';
import {
  listDatasets,
  createDataset,
  updateDataset,
  renameDataset,
  deleteDataset,
  listDatasetMetrics,
  createMetric,
  deleteMetric,
  updateMetric,
  listDatasetDimensions,
  createDimension,
  deleteDimension,
  updateDimension,
  listDatasources,
  getDatasourceSchemas,
  syncDatasourceTables,
  listSourceTables,
  getSourceTableColumns,
  annotateDatasetColumns,
  importDatasetYaml,
  exportDatasetYaml,
  previewTable,
  selectTablesForDataset,
  deselectTableFromDataset,
  listSelectedTables,
  listSelectedColumns,
  updateSourceColumn,
  convertColumnToMetric,
  convertColumnToDimension,
  updateColumnReviewStatus,
  listBusinessTerms,
  createBusinessTerm,
  updateBusinessTerm,
  deleteBusinessTerm,
  linkBusinessTermAssets,
  discoverBusinessTerms,
  checkBusinessTermConflicts,
  listSemanticValidationCases,
  createSemanticValidationCase,
  getDatasetSubAgentManifest,
  saveDatasetSubAgentManifest,
  publishDatasetSubAgentManifest,
  rollbackDatasetSubAgentManifest,
  routeCheckDatasetSubAgentManifest,
} from '../api/client';
import { streamAgentTeamTask } from '../assistant/agent-team-task-api';
import { agentTeamEnvelopeToChatEvent } from '../assistant/agent-team-event-adapter';

// ── DatasetsScreen — 语义层配置（三栏式）────────────────────

// 右键菜单项共享样式
const ctxMenuItemStyle = {
  display: 'flex', alignItems: 'center', gap: 8,
  width: '100%', padding: '6px 10px', fontSize: 12,
  background: 'transparent', border: 'none', borderRadius: 4,
  color: 'var(--text)', cursor: 'pointer', textAlign: 'left',
};

const TERM_TYPE_OPTIONS = [
  { value: 'business_object', label: '业务对象' },
  { value: 'metric_concept', label: '指标口径' },
  { value: 'dimension_enum', label: '维度枚举' },
  { value: 'status_enum', label: '状态枚举' },
  { value: 'business_process', label: '业务流程' },
  { value: 'org_scope', label: '组织口径' },
];

const TERM_STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'active', label: '已启用' },
  { value: 'deprecated', label: '已废弃' },
];

const termTypeLabel = (type) => TERM_TYPE_OPTIONS.find(item => item.value === type)?.label || type || '未分类';
const termStatusLabel = (status) => TERM_STATUS_OPTIONS.find(item => item.value === status)?.label || status || '未知';
const DEFAULT_QUERY_CONSTRAINTS = {
  enabled: true,
  default_time_range_days: 30,
  default_limit: 100,
  max_limit: 1000,
};

const DEFAULT_MANIFEST_MANUAL_FIELDS = {
  description: '',
  business_domain: [],
  sample_questions: [],
  routing_negative_examples: [],
  permission_scope: {
    status: 'not_configured',
    description: '',
  },
};

const MANIFEST_STATUS_LABEL = {
  missing: '未发布',
  draft: '草稿',
  current: '当前有效',
  needs_review: '需复核',
  archived: '历史版本',
};

const splitManifestList = (value) => String(value || '')
  .split(/[\n；;]+/)
  .map(item => item.trim())
  .filter(Boolean);

const joinManifestList = (value) => (value || []).join('\n');

const manifestManualFieldsFromForm = (form) => ({
  description: String(form.description || '').trim(),
  business_domain: splitManifestList(form.business_domain_text),
  sample_questions: splitManifestList(form.sample_questions_text),
  routing_negative_examples: splitManifestList(form.routing_negative_examples_text),
  permission_scope: {
    status: form.permission_scope_status || 'not_configured',
    description: String(form.permission_scope_description || '').trim(),
  },
});

const manifestFormFromManualFields = (manual = DEFAULT_MANIFEST_MANUAL_FIELDS) => ({
  description: manual.description || '',
  business_domain_text: joinManifestList(manual.business_domain),
  sample_questions_text: joinManifestList(manual.sample_questions),
  routing_negative_examples_text: joinManifestList(manual.routing_negative_examples),
  permission_scope_status: manual.permission_scope?.status || 'not_configured',
  permission_scope_description: manual.permission_scope?.description || '',
});

const normalizeQueryConstraints = (value) => {
  const raw = value || {};
  const maxLimit = Math.max(1, Math.min(10000, Number(raw.max_limit ?? DEFAULT_QUERY_CONSTRAINTS.max_limit) || DEFAULT_QUERY_CONSTRAINTS.max_limit));
  const defaultLimit = Math.min(
    maxLimit,
    Math.max(1, Number(raw.default_limit ?? DEFAULT_QUERY_CONSTRAINTS.default_limit) || DEFAULT_QUERY_CONSTRAINTS.default_limit)
  );
  const defaultDays = Math.max(
    1,
    Math.min(3650, Number(raw.default_time_range_days ?? DEFAULT_QUERY_CONSTRAINTS.default_time_range_days) || DEFAULT_QUERY_CONSTRAINTS.default_time_range_days)
  );
  return {
    enabled: raw.enabled ?? DEFAULT_QUERY_CONSTRAINTS.enabled,
    default_time_range_days: defaultDays,
    default_limit: defaultLimit,
    max_limit: maxLimit,
  };
};

const validationAssetLabel = (asset) => (
  asset?.display_name || asset?.name || asset?.asset_name || asset?.matched_text || String(asset?.id || '')
);

const uniqueValidationAssets = (items) => {
  const seen = new Set();
  return (items || []).filter(item => {
    const key = `${item?.asset_type || item?.type || ''}:${item?.asset_id || item?.id || validationAssetLabel(item)}`;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

const validationRouteLabel = (route) => {
  if (route === 'analysis_blueprint') return '分析蓝图路径';
  if (route === 'query_graph') return '普通问数路径';
  if (route === 'clarify') return '澄清路径';
  if (route === 'reject') return '拒答路径';
  if (route === 'knowledge_qa') return '知识解释路径';
  return route || '未识别';
};

const buildValidationReport = ({ question, finalData = {}, stepEvents = [], fallbackError = '' }) => {
  const semantic = finalData.semantic_asset_resolution || {};
  const termNormalization = finalData.term_normalization || {};
  const routePayload = finalData.route_payload || {};
  const diagnosis = finalData.sql_diagnosis || finalData.sql_audit_result || {};
  const answerExplanation = finalData.answer_explanation || {};
  const blueprintMatch = finalData.blueprint_match || {};
  const terms = uniqueValidationAssets([
    ...(termNormalization.matched_terms || []),
    ...(semantic.terms || []),
  ]);
  const blueprints = uniqueValidationAssets([
    ...(finalData.blueprint_id ? [{
      id: finalData.blueprint_id,
      name: blueprintMatch.name || routePayload.name || routePayload.blueprint_name,
      matched_terms: blueprintMatch.matched_terms || routePayload.matched_terms || [],
      score: blueprintMatch.score || routePayload.score,
    }] : []),
    ...(semantic.blueprints || []),
  ]);
  const failureReason = (
    fallbackError
    || finalData.error
    || diagnosis.title
    || diagnosis.detail
    || diagnosis.original_error
    || (['clarify', 'reject'].includes(finalData.entry_route) ? finalData.entry_reason : '')
    || ''
  );
  const routeType = finalData.entry_route === 'analysis_blueprint'
    ? 'analysis_blueprint'
    : finalData.entry_route === 'query_graph'
      ? 'query_graph'
      : finalData.entry_route || 'unknown';
  const status = failureReason || diagnosis.code ? 'failed' : 'passed';
  return {
    question,
    status,
    route_type: routeType,
    entry_intent: finalData.entry_intent || '',
    entry_route: finalData.entry_route || '',
    entry_reason: finalData.entry_reason || '',
    terms,
    term_conflicts: termNormalization.conflicts || [],
    blueprints,
    normal_query_path: finalData.entry_route === 'query_graph',
    sql: finalData.sql || '',
    sql_list: finalData.sql_list || [],
    failure_reason: failureReason,
    answer: finalData.answer || '',
    generation_mode: finalData.generation_mode || '',
    risks: answerExplanation.risks || [],
    confidence: answerExplanation.confidence || null,
    steps: stepEvents.map(ev => ({
      node: ev.node,
      display_name: ev.display_name,
      status: ev.status,
      elapsed_ms: ev.elapsed_ms,
    })),
    raw: {
      route_payload: routePayload,
      sql_diagnosis: diagnosis,
      dataset_context_debug: finalData.dataset_context_debug || null,
    },
  };
};

function DatasetsScreen() {
  // ── 数据集状态 ──
  const [datasets, setDatasets] = useState([]);
  const [activeDsId, setActiveDsId] = useState(null);
  const [loading, setLoading] = useState(false);

  // ── 表结构同步状态 ──
  const [allSourceTables, setAllSourceTables] = useState([]);      // 数据源所有表（目录）
  const [selectedTableIds, setSelectedTableIds] = useState(new Set()); // 数据集已选表ID
  const [selectedColumns, setSelectedColumns] = useState([]);      // 已选表的合并字段
  const [previewTableId, setPreviewTableId] = useState(null);      // 当前预览的表
  const [focusedTableId, setFocusedTableId] = useState(null);      // 当前聚焦的已选表（字段/预览联动）
  const [syncing, setSyncing] = useState(false);
  const [annotating, setAnnotating] = useState(false);
  const [tableSearch, setTableSearch] = useState('');
  const [fieldSearch, setFieldSearch] = useState('');
  const [fieldTableFilter, setFieldTableFilter] = useState('');
  const [fieldRoleFilter, setFieldRoleFilter] = useState('');
  const [fieldSourceFilter, setFieldSourceFilter] = useState('');
  const [convertingColumnId, setConvertingColumnId] = useState(null);

  // 查看中的表（只读预览其字段，不加入数据集；与勾选状态相互独立）
  const [inspectingTableId, setInspectingTableId] = useState(null);
  const [inspectColumns, setInspectColumns] = useState([]);
  const [inspectLoading, setInspectLoading] = useState(false);
  const inspectSeqRef = useRef(0); // 防止旧请求覆盖新结果
  const previewSeqRef = useRef(0); // 防止旧预览请求覆盖新结果

  // ── 字段编辑状态 ──
  const [editingColumnId, setEditingColumnId] = useState(null);
  const [columnEditForm, setColumnEditForm] = useState({ user_description: '', user_semantic_role: '' });

  const filteredTables = useMemo(() => {
    const q = tableSearch.trim().toLowerCase();
    const base = q
      ? allSourceTables.filter(t => t.table_name.toLowerCase().includes(q))
      : allSourceTables;
    return [...base].sort((a, b) => {
      const aSelected = selectedTableIds.has(a.id);
      const bSelected = selectedTableIds.has(b.id);
      if (aSelected !== bSelected) return aSelected ? -1 : 1;
      return String(a.table_name || '').localeCompare(String(b.table_name || ''));
    });
  }, [allSourceTables, selectedTableIds, tableSearch]);

  const tableListItems = useMemo(() => {
    const selected = filteredTables.filter(t => selectedTableIds.has(t.id));
    const unselected = filteredTables.filter(t => !selectedTableIds.has(t.id));
    const items = [];
    if (selected.length) {
      items.push({ type: 'group', id: 'selected', label: '已选择', count: selected.length });
      selected.forEach(table => items.push({ type: 'table', table }));
    }
    if (unselected.length) {
      items.push({ type: 'group', id: 'unselected', label: '未选择', count: unselected.length });
      unselected.forEach(table => items.push({ type: 'table', table }));
    }
    return items;
  }, [filteredTables, selectedTableIds]);

  // ── 指标/维度数据 ──
  const [metrics, setMetrics] = useState([]);
  const [dimensions, setDimensions] = useState([]);
  const [businessTerms, setBusinessTerms] = useState([]);
  const [validationCases, setValidationCases] = useState([]);
  const [termSearch, setTermSearch] = useState('');
  const [termTypeFilter, setTermTypeFilter] = useState('');
  const [termStatusFilter, setTermStatusFilter] = useState('');
  const [selectedTermId, setSelectedTermId] = useState(null);
  const [showTermForm, setShowTermForm] = useState(false);
  const [editingTermId, setEditingTermId] = useState(null);
  const [termCandidates, setTermCandidates] = useState([]);
  const [termConflicts, setTermConflicts] = useState([]);
  const [termBusy, setTermBusy] = useState(false);
  const [termStatusMessage, setTermStatusMessage] = useState('');
  const [termDetailOpen, setTermDetailOpen] = useState(false);
  const termRowRefs = useRef({});
  const [activeCapabilityTab, setActiveCapabilityTab] = useState(() => {
    try {
      return localStorage.getItem('datalogue.dataset.capabilityTab.v2') || 'blueprints';
    } catch {
      return 'blueprints';
    }
  });

  // ── 表单状态 ──
  const [showMetricForm, setShowMetricForm] = useState(false);
  const [showDimForm, setShowDimForm] = useState(false);
  const [showDsForm, setShowDsForm] = useState(false);
  const [creatingDataset, setCreatingDataset] = useState(false);
  const [showYamlImport, setShowYamlImport] = useState(false);
  const [editingMetricId, setEditingMetricId] = useState(null);
  const [editingDimId, setEditingDimId] = useState(null);
  const [metricSourceColumnId, setMetricSourceColumnId] = useState(null);
  const [dimSourceColumnId, setDimSourceColumnId] = useState(null);

  const [metricForm, setMetricForm] = useState({
    name: '', display_name: '', expr: '', table_name: '', time_field: '',
    granularity: '', format_str: '', filter_sql: '', synonyms: '', description: ''
  });
  const [dimForm, setDimForm] = useState({
    name: '', display_name: '', column_name: '', table_name: '',
    join_to: '', join_key: '', enum_values: '', synonyms: ''
  });
  const [termForm, setTermForm] = useState({
    name: '',
    display_name: '',
    term_type: 'business_object',
    definition: '',
    aliases: '',
    forbidden_aliases: '',
    examples: '',
    owner: '',
    status: 'draft',
  });
  const [dsForm, setDsForm] = useState({
    name: '',
    datasource_id: '',
    schema_name: '',
    description: '',
    prompt_instructions: '',
    query_constraints: DEFAULT_QUERY_CONSTRAINTS,
  });
  const [showPromptForm, setShowPromptForm] = useState(false);
  const [promptFormDs, setPromptFormDs] = useState(null);
  const [datasources, setDatasources] = useState([]);
  const [datasetSchemas, setDatasetSchemas] = useState([]);
  const [datasetSchemaLoading, setDatasetSchemaLoading] = useState(false);
  const [datasetSchemaError, setDatasetSchemaError] = useState('');
  const datasetSchemaSeqRef = useRef(0); // 快速切换数据源时，旧 Schema 请求不得覆盖当前表单。
  const [yamlText, setYamlText] = useState('');

  // ── 数据预览 ──
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // ── 试问验证 ──
  const [testQuestion, setTestQuestion] = useState('');
  const [testStreaming, setTestStreaming] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testSql, setTestSql] = useState('');
  const [testReport, setTestReport] = useState(null);
  const [testStepEvents, setTestStepEvents] = useState([]);
  const [savingValidationCase, setSavingValidationCase] = useState(false);
  const testAbortRef = useRef(null);

  // ── SubAgent Manifest 治理 ──
  const [manifestDetail, setManifestDetail] = useState(null);
  const [manifestForm, setManifestForm] = useState(() => manifestFormFromManualFields());
  const [manifestLoading, setManifestLoading] = useState(false);
  const [manifestSaving, setManifestSaving] = useState(false);
  const [manifestPublishing, setManifestPublishing] = useState(false);
  const [manifestRollingBackVersion, setManifestRollingBackVersion] = useState('');
  const [manifestRouteQuestions, setManifestRouteQuestions] = useState('');
  const [manifestRouteExpected, setManifestRouteExpected] = useState('');
  const [manifestRouteResults, setManifestRouteResults] = useState([]);
  const [manifestRouteChecking, setManifestRouteChecking] = useState(false);
  const [manifestMessage, setManifestMessage] = useState('');

  // ── 数据集列表：右键菜单 + 二次确认删除 ──
  const [ctxMenu, setCtxMenu] = useState(null); // {x, y, ds} | null
  const ctxMenuRef = useRef(null); // 菜单 DOM 引用，用于判断点击是否在菜单内
  const [confirmDelete, setConfirmDelete] = useState(null); // 待删除的 dataset | null
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');

  // ── 初始化 ──
  useEffect(() => { loadDatasets(); loadDatasources(); }, []);

  useEffect(() => {
    try {
      localStorage.setItem('datalogue.dataset.capabilityTab.v2', activeCapabilityTab);
    } catch {
      // localStorage may be unavailable in embedded previews.
    }
  }, [activeCapabilityTab]);

  useEffect(() => {
    if (activeDsId) {
      loadDsMeta(activeDsId);
      loadAllSourceTables(activeDsId);
      loadSelectedTables(activeDsId);
    }
  }, [activeDsId]);

  useEffect(() => {
    if (previewTableId && allSourceTables.length > 0 && activeDsId) {
      loadPreview(previewTableId);
    }
  }, [previewTableId, allSourceTables, activeDsId]);

  // 切换/选中状态变化时清理 inspect：若该表已被勾选，就交给已选字段视图展示
  useEffect(() => {
    if (inspectingTableId && selectedTableIds.has(inspectingTableId)) {
      setInspectingTableId(null);
      setInspectColumns([]);
    }
  }, [inspectingTableId, selectedTableIds]);

  // 加载查看中表的字段（只读）
  useEffect(() => {
    if (!inspectingTableId) {
      setInspectColumns([]);
      return;
    }
    const seq = ++inspectSeqRef.current;
    setInspectLoading(true);
    getSourceTableColumns(inspectingTableId)
      .then(cols => {
        if (seq !== inspectSeqRef.current) return; // 旧请求忽略
        setInspectColumns(cols || []);
      })
      .catch(err => {
        console.error('[inspect] load columns failed:', err);
        if (seq === inspectSeqRef.current) setInspectColumns([]);
      })
      .finally(() => {
        if (seq === inspectSeqRef.current) setInspectLoading(false);
      });
  }, [inspectingTableId]);

  // 点击外部 / ESC 关闭右键菜单
  useEffect(() => {
    if (!ctxMenu) return;
    const onDown = (e) => {
      // 点击落在菜单内时，由菜单本身的 onMouseDown stopPropagation 阻止关闭；
      // 落在菜单外时关闭菜单。用 ref 判断目标是否在菜单节点内。
      if (ctxMenuRef.current && ctxMenuRef.current.contains(e.target)) return;
      setCtxMenu(null);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setCtxMenu(null);
    };
    // 冒泡阶段（不传 capture=true），让菜单内的 onMouseDown 先 stopPropagation
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [ctxMenu]);

  // ── 数据加载 ──
  const loadDatasets = async (preferredDsId = null) => {
    setLoading(true);
    try {
      const items = await listDatasets();
      setDatasets(items);
      setActiveDsId(prev => {
        if (preferredDsId && items.some(item => item.id === preferredDsId)) return preferredDsId;
        if (prev && items.some(item => item.id === prev)) return prev;
        return items[0]?.id || null;
      });
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadDatasources = () => {
    listDatasources().then(setDatasources).catch(console.error);
  };

  const handleDatasetDatasourceChange = async (datasourceId) => {
    const seq = ++datasetSchemaSeqRef.current;
    setDsForm(prev => ({ ...prev, datasource_id: datasourceId, schema_name: '' }));
    setDatasetSchemas([]);
    setDatasetSchemaError('');
    if (!datasourceId) {
      setDatasetSchemaLoading(false);
      return;
    }
    setDatasetSchemaLoading(true);
    try {
      const result = await getDatasourceSchemas(Number(datasourceId));
      if (seq !== datasetSchemaSeqRef.current) return;
      const schemas = result?.schemas || [];
      const datasource = datasources.find(item => String(item.id) === String(datasourceId));
      const preferred = datasource?.default_schema || datasource?.database_name || '';
      const selectedSchema = schemas.includes(preferred) ? preferred : (schemas[0] || '');
      setDatasetSchemas(schemas);
      setDsForm(prev => (
        String(prev.datasource_id) === String(datasourceId)
          ? { ...prev, schema_name: selectedSchema }
          : prev
      ));
      if (schemas.length === 0) setDatasetSchemaError('当前数据源没有可用 Schema');
    } catch (err) {
      if (seq !== datasetSchemaSeqRef.current) return;
      setDatasetSchemaError(err.message || 'Schema 加载失败');
    } finally {
      if (seq === datasetSchemaSeqRef.current) setDatasetSchemaLoading(false);
    }
  };

  const loadDsMeta = async (dsId) => {
    try {
      const [ms, ds, terms, cases, manifest] = await Promise.all([
        listDatasetMetrics(dsId),
        listDatasetDimensions(dsId),
        listBusinessTerms(dsId),
        listSemanticValidationCases(dsId),
        getDatasetSubAgentManifest(dsId),
      ]);
      setMetrics(ms);
      setDimensions(ds);
      setBusinessTerms(terms);
      setValidationCases(cases);
      setManifestDetail(manifest);
      setManifestForm(manifestFormFromManualFields(manifest?.manual_fields));
      setManifestRouteResults([]);
      setManifestMessage('');
      setSelectedTermId(prev => (prev && terms.some(t => t.id === prev) ? prev : terms[0]?.id ?? null));
    } catch (err) {
      console.error(err);
      setManifestDetail(null);
    }
  };

  // 加载数据源所有表（目录）
  const loadAllSourceTables = async (dsId) => {
    const ds = datasets.find(d => d.id === dsId);
    if (!ds) return;
    try {
      const tables = await listSourceTables(ds.datasource_id, ds.schema_name);
      setAllSourceTables(tables);
    } catch (err) {
      console.error(err);
      setAllSourceTables([]);
    }
  };

  // 加载数据集已选表 + 合并字段
  const loadSelectedTables = async (dsId) => {
    try {
      const [selectedTables, cols] = await Promise.all([
        listSelectedTables(dsId),
        listSelectedColumns(dsId),
      ]);
      const nextSelectedIds = new Set(selectedTables.map(t => t.id));
      setSelectedTableIds(nextSelectedIds);
      setSelectedColumns(cols);
      if (selectedTables.length > 0) {
        const nextFocus = focusedTableId && nextSelectedIds.has(focusedTableId)
          ? focusedTableId
          : selectedTables[0].id;
        setFocusedTableId(nextFocus);
        if (!previewTableId || !nextSelectedIds.has(previewTableId)) {
          setPreviewTableId(nextFocus);
        }
      } else {
        setFocusedTableId(null);
        setPreviewTableId(null);
        setPreviewData(null);
      }
    } catch (err) {
      console.error(err);
      setSelectedTableIds(new Set());
      setSelectedColumns([]);
      setFocusedTableId(null);
      setPreviewTableId(null);
      setPreviewData(null);
    }
  };

  const loadPreview = async (tableId) => {
    const seq = ++previewSeqRef.current;
    const table = allSourceTables.find(t => t.id === tableId);
    if (!table) {
      setPreviewData(null);
      setPreviewLoading(false);
      return;
    }
    const ds = datasets.find(d => d.id === activeDsId);
    if (!ds) {
      setPreviewData(null);
      setPreviewLoading(false);
      return;
    }
    setPreviewLoading(true);
    try {
      const data = await previewTable(ds.datasource_id, table.schema_name, table.table_name, 5);
      if (seq !== previewSeqRef.current) return;
      setPreviewData(data);
    } catch (err) {
      console.error(err);
      if (seq === previewSeqRef.current) setPreviewData(null);
    } finally {
      if (seq === previewSeqRef.current) setPreviewLoading(false);
    }
  };

  // ── 字段编辑 ──
  const handleStartEditColumn = (col) => {
    setEditingColumnId(col.id);
    setColumnEditForm({
      user_description: col.user_description || col.effective_desc || col.business_desc || '',
      user_semantic_role: col.user_semantic_role || col.ai_semantic_role || col.semantic_role || '',
    });
  };

  const handleSaveColumnEdit = async (colId) => {
    try {
      await updateSourceColumn(colId, {
        user_description: columnEditForm.user_description || null,
        user_semantic_role: columnEditForm.user_semantic_role || null,
      });
      setEditingColumnId(null);
      // 刷新字段列表
      if (activeDsId) {
        await refreshSelectedColumns(activeDsId);
      }
    } catch (err) {
      console.error('保存字段标注失败:', err);
      alert('保存失败: ' + (err.message || '未知错误'));
    }
  };

  const refreshSelectedColumns = async (dsId = activeDsId) => {
    if (!dsId) return;
    const cols = await listSelectedColumns(dsId);
    setSelectedColumns(cols);
  };

  const applyColumnUpdate = (column) => {
    if (!column?.id) return;
    setSelectedColumns(prev => prev.map(c => (c.id === column.id ? { ...c, ...column } : c)));
  };

  const handleColumnReviewStatus = async (col, status) => {
    if (!activeDsId) return;
    try {
      const result = await updateColumnReviewStatus(activeDsId, col.id, status);
      applyColumnUpdate(result.column);
    } catch (err) {
      alert('状态更新失败: ' + (err.message || '未知错误'));
    }
  };

  const handleCancelColumnEdit = () => {
    setEditingColumnId(null);
    setColumnEditForm({ user_description: '', user_semantic_role: '' });
  };

  // ── 同步 & 标注 ──
  const handleSyncTables = async () => {
    const ds = datasets.find(d => d.id === activeDsId);
    if (!ds) { alert('请先选择数据集'); return; }
    setSyncing(true);
    try {
      await syncDatasourceTables(ds.datasource_id, ds.schema_name);
      await loadAllSourceTables(activeDsId);
    } catch (err) {
      alert('同步失败: ' + (err.message || '未知错误'));
    } finally {
      setSyncing(false);
    }
  };

  const handleAnnotate = async () => {
    if (!activeDsId) { alert('请先选择数据集'); return; }
    setAnnotating(true);
    try {
      await annotateDatasetColumns(activeDsId);
      // 标注会更新 effective_desc / ai_description：必须 reload 两个列表
      // - loadAllSourceTables：刷新左侧"所有表"目录的表名注释
      // - loadSelectedTables：刷新已选表 + 字段的描述
      await Promise.all([
        loadAllSourceTables(activeDsId),
        loadSelectedTables(activeDsId),
      ]);
    } catch (err) {
      alert('标注失败: ' + (err.message || '未知错误'));
    } finally {
      setAnnotating(false);
    }
  };

  // ── 勾选/取消勾选表 ──
  const handleToggleTable = async (sourceTableId, checked) => {
    if (!activeDsId) return;
    try {
      if (checked) {
        await selectTablesForDataset(activeDsId, [sourceTableId]);
        // 勾选后自动预览该表
        setFocusedTableId(sourceTableId);
        setPreviewTableId(sourceTableId);
      } else {
        await deselectTableFromDataset(activeDsId, sourceTableId);
        if (focusedTableId === sourceTableId) setFocusedTableId(null);
        if (previewTableId === sourceTableId) setPreviewTableId(null);
      }
      await loadSelectedTables(activeDsId);
    } catch (err) {
      alert('操作失败: ' + (err.message || '未知错误'));
    }
  };

  // ── 查看表信息（不加入数据集）──
  const handleInspectTable = (sourceTableId) => {
    if (!sourceTableId) return;
    if (selectedTableIds.has(sourceTableId)) {
      setInspectingTableId(null);
      setInspectColumns([]);
      setFocusedTableId(sourceTableId);
      setPreviewTableId(sourceTableId);
      return;
    }
    // 点击同一行再次点 → 收起
    if (inspectingTableId === sourceTableId) {
      setInspectingTableId(null);
      return;
    }
    setFocusedTableId(null);
    setInspectingTableId(sourceTableId);
    // 同时触发该表的数据预览
    setPreviewTableId(sourceTableId);
  };

  const handleCloseInspect = () => {
    setInspectingTableId(null);
    setInspectColumns([]);
  };

  // ── 新建数据集 ──
  const handleCreateDataset = async () => {
    if (!dsForm.name) { alert('请输入数据集名称'); return; }
    if (!dsForm.datasource_id) { alert('请选择数据源'); return; }
    if (!dsForm.schema_name) { alert('请选择 Schema'); return; }
    const datasourceId = Number(dsForm.datasource_id);
    setCreatingDataset(true);
    try {
      const catalogTables = await listSourceTables(datasourceId, dsForm.schema_name);
      if (catalogTables.length === 0) {
        // 首次使用某个 Schema 时先建立本地表目录，创建完成后即可直接选表。
        await syncDatasourceTables(datasourceId, dsForm.schema_name);
      }
      const created = await createDataset({
        name: dsForm.name,
        datasource_id: datasourceId,
        schema_name: dsForm.schema_name,
        description: dsForm.description || undefined,
        prompt_instructions: dsForm.prompt_instructions || undefined,
        query_constraints: normalizeQueryConstraints(dsForm.query_constraints),
        tables_json: {},
        status: 'draft',
      });
      setShowDsForm(false);
      setDsForm({
        name: '',
        datasource_id: '',
        schema_name: '',
        description: '',
        prompt_instructions: '',
        query_constraints: DEFAULT_QUERY_CONSTRAINTS,
      });
      await loadDatasets(created.id);
    } catch (err) {
      alert('创建失败: ' + (err.message || 'Schema 表目录同步失败'));
    } finally {
      setCreatingDataset(false);
    }
  };

  // ── 数据集右键菜单 ──
  const openCtxMenu = (e, ds) => {
    e.preventDefault();
    e.stopPropagation();
    // 防止菜单超出右/下边界：菜单大约宽 160、高 ~116
    const menuW = 160, menuH = 116;
    const x = Math.min(e.clientX, window.innerWidth - menuW - 8);
    const y = Math.min(e.clientY, window.innerHeight - menuH - 8);
    setCtxMenu({ x, y, ds });
  };

  const startRename = (ds) => {
    setCtxMenu(null);
    setRenamingId(ds.id);
    setRenameValue(ds.name);
  };

  const commitRename = async () => {
    if (!renamingId) return;
    const next = renameValue.trim();
    const orig = datasets.find(d => d.id === renamingId)?.name;
    if (!next || next === orig) {
      setRenamingId(null);
      return;
    }
    try {
      await renameDataset(renamingId, next);
      setRenamingId(null);
      await loadDatasets();
    } catch (err) {
      alert('重命名失败: ' + (err.message || '未知错误'));
      setRenamingId(null);
    }
  };

  const requestDelete = (ds) => {
    setCtxMenu(null);
    setConfirmDelete(ds);
  };

  const confirmDeleteDataset = async () => {
    if (!confirmDelete) return;
    const id = confirmDelete.id;
    try {
      await deleteDataset(id);
      setConfirmDelete(null);
      // 如果删的是当前激活的，切换到第一个
      if (activeDsId === id) {
        const rest = datasets.filter(d => d.id !== id);
        setActiveDsId(rest[0]?.id ?? null);
        setSelectedTableIds(new Set());
        setSelectedColumns([]);
        setFocusedTableId(null);
        setPreviewTableId(null);
        setPreviewData(null);
        setInspectingTableId(null);
        setInspectColumns([]);
      }
      await loadDatasets();
    } catch (err) {
      alert('删除失败: ' + (err.message || '未知错误'));
      setConfirmDelete(null);
    }
  };

  // ── 指标 CRUD ──
  const handleAddMetric = async () => {
    if (!metricForm.name || !metricForm.expr) { alert('请填写指标名和表达式'); return; }
    if (!activeDsId) { alert('请先选择数据集'); return; }
    try {
      const payload = {
        ...metricForm,
        synonyms: metricForm.synonyms ? metricForm.synonyms.split(',').map(s => s.trim()) : [],
      };
      if (editingMetricId) {
        await updateMetric(activeDsId, editingMetricId, payload);
      } else if (metricSourceColumnId) {
        setConvertingColumnId(metricSourceColumnId);
        const result = await convertColumnToMetric(activeDsId, metricSourceColumnId, payload);
        applyColumnUpdate(result.column);
        alert(result.existing ? '指标已存在，已关联到该字段' : '指标创建成功');
      } else {
        await createMetric(activeDsId, payload);
      }
      setShowMetricForm(false);
      setEditingMetricId(null);
      setMetricSourceColumnId(null);
      setMetricForm({ name: '', display_name: '', expr: '', table_name: '', time_field: '', granularity: '', format_str: '', filter_sql: '', synonyms: '', description: '' });
      await loadDsMeta(activeDsId);
    } catch (err) {
      alert('保存失败: ' + (err.message || '未知错误'));
    } finally {
      setConvertingColumnId(null);
    }
  };

  const handleEditMetric = (m) => {
    setEditingMetricId(m.id);
    setMetricSourceColumnId(null);
    setMetricForm({
      name: m.name,
      display_name: m.display_name || '',
      expr: m.expr || '',
      table_name: m.table_name || '',
      time_field: m.time_field || '',
      granularity: m.granularity || '',
      format_str: m.format_str || '',
      filter_sql: m.filter_sql || '',
      synonyms: (m.synonyms || []).join(', '),
      description: m.description || '',
    });
    setShowMetricForm(true);
  };

  const handleDelMetric = async (mid) => {
    if (!confirm('确定删除？')) return;
    try { await deleteMetric(activeDsId, mid); loadDsMeta(activeDsId); } catch (err) { alert(err.message); }
  };

  // ── 维度 CRUD ──
  const handleAddDim = async () => {
    if (!dimForm.name || !dimForm.column_name) { alert('请填写维度名和字段名'); return; }
    if (!activeDsId) { alert('请先选择数据集'); return; }
    try {
      const payload = {
        ...dimForm,
        synonyms: dimForm.synonyms ? dimForm.synonyms.split(',').map(s => s.trim()) : [],
        enum_values: dimForm.enum_values ? dimForm.enum_values.split(',').map(s => s.trim()) : [],
      };
      if (editingDimId) {
        await updateDimension(activeDsId, editingDimId, payload);
      } else if (dimSourceColumnId) {
        setConvertingColumnId(dimSourceColumnId);
        const result = await convertColumnToDimension(activeDsId, dimSourceColumnId, payload);
        applyColumnUpdate(result.column);
        alert(result.existing ? '维度已存在，已关联到该字段' : '维度创建成功');
      } else {
        await createDimension(activeDsId, payload);
      }
      setShowDimForm(false);
      setEditingDimId(null);
      setDimSourceColumnId(null);
      setDimForm({ name: '', display_name: '', column_name: '', table_name: '', join_to: '', join_key: '', enum_values: '', synonyms: '' });
      await loadDsMeta(activeDsId);
    } catch (err) {
      alert('保存失败: ' + (err.message || '未知错误'));
    } finally {
      setConvertingColumnId(null);
    }
  };

  const handleEditDim = (d) => {
    setEditingDimId(d.id);
    setDimSourceColumnId(null);
    setDimForm({
      name: d.name,
      display_name: d.display_name || '',
      column_name: d.column_name || '',
      table_name: d.table_name || '',
      join_to: d.join_to || '',
      join_key: d.join_key || '',
      enum_values: (d.enum_values || []).join(', '),
      synonyms: (d.synonyms || []).join(', '),
    });
    setShowDimForm(true);
  };

  const handleDelDim = async (did) => {
    if (!confirm('确定删除？')) return;
    try { await deleteDimension(activeDsId, did); loadDsMeta(activeDsId); } catch (err) { alert(err.message); }
  };

  // ── 业务术语 CRUD / 发现 / 冲突 ──
  const resetTermForm = () => {
    setEditingTermId(null);
    setTermForm({
      name: '',
      display_name: '',
      term_type: 'business_object',
      definition: '',
      aliases: '',
      forbidden_aliases: '',
      examples: '',
      owner: '',
      status: 'draft',
    });
    setShowTermForm(true);
  };

  const handleEditTerm = (term) => {
    setEditingTermId(term.id);
    setTermForm({
      name: term.name || '',
      display_name: term.display_name || '',
      term_type: term.term_type || 'business_object',
      definition: term.definition || '',
      aliases: (term.aliases || []).join(', '),
      forbidden_aliases: (term.forbidden_aliases || []).join(', '),
      examples: (term.examples || []).join(', '),
      owner: term.owner || '',
      status: term.status || 'draft',
    });
    setShowTermForm(true);
  };

  const termFormPayload = () => ({
    name: termForm.name.trim(),
    display_name: termForm.display_name.trim() || termForm.name.trim(),
    term_type: termForm.term_type,
    definition: termForm.definition.trim() || null,
    aliases: termForm.aliases ? termForm.aliases.split(',').map(s => s.trim()).filter(Boolean) : [],
    forbidden_aliases: termForm.forbidden_aliases ? termForm.forbidden_aliases.split(',').map(s => s.trim()).filter(Boolean) : [],
    examples: termForm.examples ? termForm.examples.split(',').map(s => s.trim()).filter(Boolean) : [],
    owner: termForm.owner.trim() || null,
    status: termForm.status,
  });

  const handleSaveTerm = async () => {
    if (!activeDsId) { alert('请先选择数据集'); return; }
    if (!termForm.name.trim()) { alert('请填写术语名称'); return; }
    setTermBusy(true);
    try {
      const payload = termFormPayload();
      const saved = editingTermId
        ? await updateBusinessTerm(activeDsId, editingTermId, payload)
        : await createBusinessTerm(activeDsId, payload);
      setShowTermForm(false);
      setEditingTermId(null);
      setSelectedTermId(saved.id);
      await loadDsMeta(activeDsId);
    } catch (err) {
      alert('保存术语失败: ' + (err.message || '未知错误'));
    } finally {
      setTermBusy(false);
    }
  };

  const handleDeleteTerm = async (termId) => {
    if (!activeDsId || !confirm('确定删除该业务术语？')) return;
    setTermBusy(true);
    try {
      await deleteBusinessTerm(activeDsId, termId);
      if (selectedTermId === termId) setSelectedTermId(null);
      await loadDsMeta(activeDsId);
    } catch (err) {
      alert('删除术语失败: ' + (err.message || '未知错误'));
    } finally {
      setTermBusy(false);
    }
  };

  const handleDiscoverTerms = async () => {
    if (!activeDsId) return;
    setTermBusy(true);
    setTermStatusMessage('正在从指标、维度和字段标注中检查可沉淀的别名。');
    try {
      const result = await discoverBusinessTerms(activeDsId);
      const candidates = result.candidates || [];
      setTermCandidates(candidates);
      setTermStatusMessage(candidates.length ? `发现 ${candidates.length} 个候选别名，可按需纳入语义词典。` : '未发现新的候选别名，当前词典不影响问数。');
    } catch (err) {
      setTermStatusMessage('候选别名生成失败，不影响主路径配置。' + (err.message ? ` ${err.message}` : ''));
    } finally {
      setTermBusy(false);
    }
  };

  const handleAcceptTermCandidate = async (candidate) => {
    if (!activeDsId) return;
    setTermBusy(true);
    try {
      const saved = await createBusinessTerm(activeDsId, {
        name: candidate.name,
        display_name: candidate.display_name || candidate.name,
        term_type: candidate.term_type || 'business_object',
        definition: candidate.definition || '',
        aliases: candidate.aliases || [],
        examples: candidate.examples || [],
        status: 'draft',
        source: 'ai',
        confidence: candidate.confidence,
        extra_metadata: { discovered_from: candidate.source || 'unknown' },
      });
      if (candidate.asset_links?.length) {
        await linkBusinessTermAssets(activeDsId, saved.id, candidate.asset_links);
      }
      setTermCandidates(prev => prev.filter(item => item.name !== candidate.name));
      setSelectedTermId(saved.id);
      setTermStatusMessage(`已将“${candidate.display_name || candidate.name}”纳入语义词典。`);
      await loadDsMeta(activeDsId);
    } catch (err) {
      setTermStatusMessage('纳入候选失败。若已存在同名词条，请在语义词典中复用已有词条。' + (err.message ? ` ${err.message}` : ''));
    } finally {
      setTermBusy(false);
    }
  };

  const handleSelectTerm = (termId) => {
    setSelectedTermId(termId);
    setTermDetailOpen(true);
  };

  const closeTermDetail = () => {
    const termId = selectedTerm?.id;
    setTermDetailOpen(false);
    window.requestAnimationFrame(() => {
      if (termId && termRowRefs.current[termId]) {
        termRowRefs.current[termId].focus();
      }
    });
  };

  const handleCheckTermConflicts = async () => {
    if (!activeDsId) return;
    setTermBusy(true);
    setTermStatusMessage('正在检测同义词重叠、禁用词和同名冲突。');
    try {
      const result = await checkBusinessTermConflicts(activeDsId);
      const conflicts = result.conflicts || [];
      setTermConflicts(conflicts);
      setTermStatusMessage(conflicts.length ? `发现 ${conflicts.length} 条冲突，请在右侧逐项处理。` : '当前未发现术语冲突。');
    } catch (err) {
      setTermStatusMessage('冲突检测失败，语义词典列表仍可继续使用。' + (err.message ? ` ${err.message}` : ''));
    } finally {
      setTermBusy(false);
    }
  };

  // ── 从字段快速创建指标/维度 ──
  const handleCreateMetricFromColumn = (col) => {
    if (!activeDsId) { alert('请先选择数据集'); return; }
    const displayName = col.user_description || col.ai_description || col.business_desc || col.effective_desc || col.column_comment || col.column_name;
    const agg = (col.ai_suggested_agg || col.default_agg || 'SUM').toUpperCase();
    const timeCol = selectedColumns.find(c => c.source_table_id === col.source_table_id && getColumnRole(c) === 'time_field');
    setEditingMetricId(null);
    setMetricSourceColumnId(col.id);
    setMetricForm({
      name: displayName || col.column_name,
      display_name: displayName || col.column_name,
      expr: `${agg === 'NONE' ? 'SUM' : agg}(${col.column_name})`,
      table_name: col.table_name || '',
      time_field: timeCol ? timeCol.column_name : '',
      granularity: 'daily',
      format_str: '',
      filter_sql: '',
      synonyms: (col.suggested_synonyms || []).join(', '),
      description: col.ai_reason || col.ai_description || col.effective_desc || '',
    });
    setShowMetricForm(true);
  };

  const handleCreateDimFromColumn = (col) => {
    if (!activeDsId) { alert('请先选择数据集'); return; }
    const displayName = col.user_description || col.ai_description || col.business_desc || col.effective_desc || col.column_comment || col.column_name;
    const enumValues = (col.suggested_enum_values?.length ? col.suggested_enum_values : col.sample_values || []).slice(0, 20);
    setEditingDimId(null);
    setDimSourceColumnId(col.id);
    setDimForm({
      name: displayName || col.column_name,
      display_name: displayName || col.column_name,
      column_name: col.column_name,
      table_name: col.table_name || '',
      join_to: '',
      join_key: '',
      enum_values: enumValues.join(', '),
      synonyms: (col.suggested_synonyms || []).join(', '),
    });
    setShowDimForm(true);
  };

  // ── YAML 导入/导出 ──
  const handleImportYaml = async () => {
    if (!yamlText.trim()) { alert('YAML 内容不能为空'); return; }
    if (!activeDsId) { alert('请先选择数据集'); return; }
    try {
      await importDatasetYaml(activeDsId, yamlText.trim());
      setShowYamlImport(false);
      setYamlText('');
      loadDsMeta(activeDsId);
      alert('导入成功');
    } catch (err) { alert('导入失败: ' + (err.message || '未知错误')); }
  };

  const handleExportYaml = async () => {
    if (!activeDsId) { alert('请先选择数据集'); return; }
    try {
      const res = await exportDatasetYaml(activeDsId);
      const blob = new Blob([res.yaml], { type: 'text/yaml' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `dataset-${activeDsId}.yaml`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) { alert('导出失败: ' + (err.message || '未知错误')); }
  };

  // ── 试问验证 ──
  const handleTestQuery = () => {
    const dsId = activeDsId || datasets[0]?.id;
    if (!testQuestion.trim() || !dsId) return;
    const question = testQuestion.trim();
    const stepEvents = [];
    setTestStreaming(true);
    setTestResult(null);
    setTestSql('');
    setTestReport(null);
    setTestStepEvents([]);

    const ctrl = new AbortController();
    testAbortRef.current = { abort: () => ctrl.abort() };
    (async () => {
      try {
        for await (const rawEvent of streamAgentTeamTask(
          {
            task_source: 'chat',
            task_type: 'bi_query',
            question,
            dataset_id: dsId,
          },
          { signal: ctrl.signal },
        )) {
          const ev = agentTeamEnvelopeToChatEvent(rawEvent);
          if (ev.type === 'token') {
            setTestResult(prev => (prev || '') + (ev.content || ''));
            continue;
          }
          if (ev.type === 'final') {
            setTestStreaming(false);
            if (ev.sql) setTestSql(ev.sql);
            if (ev.answer) setTestResult(ev.answer);
            setTestReport(buildValidationReport({ question, finalData: ev, stepEvents }));
            return;
          }
          stepEvents.push(ev);
          setTestStepEvents([...stepEvents]);
          if (ev.step === 'dsl_compiler' && ev.status === 'done' && ev.output?.sql) {
            setTestSql(ev.output.sql);
          } else if (ev.node === 'dsl_compiler' && ev.status === 'done' && ev.sql) {
            setTestSql(ev.sql);
          }
        }
        setTestStreaming(false);
      } catch (err) {
        if (err.name === 'AbortError') {
          setTestStreaming(false);
          return;
        }
        setTestStreaming(false);
        const message = '验证失败: ' + err.message;
        setTestResult(message);
        setTestReport(buildValidationReport({
          question,
          finalData: { answer: message, error: err.message },
          stepEvents,
          fallbackError: err.message,
        }));
      }
    })();
  };

  const handleSaveValidationCase = async () => {
    const dsId = activeDsId || datasets[0]?.id;
    if (!dsId || !testReport) return;
    setSavingValidationCase(true);
    try {
      await createSemanticValidationCase(dsId, {
        question: testReport.question,
        status: testReport.status,
        route_type: testReport.route_type,
        entry_intent: testReport.entry_intent,
        entry_route: testReport.entry_route,
        blueprint_id: testReport.blueprints?.[0]?.id || testReport.blueprints?.[0]?.asset_id || null,
        sql: testReport.sql,
        answer: testReport.answer,
        error: testReport.failure_reason,
        report: testReport,
      });
      const cases = await listSemanticValidationCases(dsId);
      setValidationCases(cases);
    } catch (err) {
      alert('保存验证用例失败: ' + (err.message || '未知错误'));
    } finally {
      setSavingValidationCase(false);
    }
  };

  const loadManifestDetail = async (dsId = currentDsId) => {
    if (!dsId) return;
    setManifestLoading(true);
    try {
      const detail = await getDatasetSubAgentManifest(dsId);
      setManifestDetail(detail);
      setManifestForm(manifestFormFromManualFields(detail?.manual_fields));
      setManifestMessage('');
    } catch (err) {
      console.error(err);
      setManifestMessage('Manifest 加载失败: ' + (err.message || '未知错误'));
    } finally {
      setManifestLoading(false);
    }
  };

  const handleManifestSave = async () => {
    if (!currentDsId) return;
    setManifestSaving(true);
    setManifestMessage('');
    try {
      await saveDatasetSubAgentManifest(currentDsId, manifestManualFieldsFromForm(manifestForm), 'yangkai');
      await loadManifestDetail(currentDsId);
      setManifestMessage('草稿已保存。');
    } catch (err) {
      setManifestMessage('保存失败: ' + (err.message || '未知错误'));
    } finally {
      setManifestSaving(false);
    }
  };

  const handleManifestPublish = async () => {
    if (!currentDsId) return;
    setManifestPublishing(true);
    setManifestMessage('');
    try {
      await publishDatasetSubAgentManifest(currentDsId, manifestManualFieldsFromForm(manifestForm), 'yangkai');
      await loadManifestDetail(currentDsId);
      setManifestMessage('Manifest 已发布为当前版本。');
    } catch (err) {
      const lint = err?.data?.detail?.lint || err?.detail?.lint;
      if (Array.isArray(lint) && lint.length) {
        setManifestMessage('发布失败: ' + lint.map(item => item.message).join('；'));
      } else {
        setManifestMessage('发布失败: ' + (err.message || '未知错误'));
      }
    } finally {
      setManifestPublishing(false);
    }
  };

  const handleManifestRollback = async (version) => {
    if (!currentDsId || !version || manifestRollingBackVersion) return;
    setManifestRollingBackVersion(version);
    setManifestMessage('');
    try {
      await rollbackDatasetSubAgentManifest(currentDsId, version, 'yangkai', '治理页手动回滚');
      await loadManifestDetail(currentDsId);
      setManifestMessage(`已基于 ${version} 生成新的 current 版本。`);
    } catch (err) {
      const lint = err?.data?.detail?.lint || err?.detail?.lint;
      if (Array.isArray(lint) && lint.length) {
        setManifestMessage('回滚失败: ' + lint.map(item => item.message).join('；'));
      } else {
        setManifestMessage('回滚失败: ' + (err.message || '未知错误'));
      }
    } finally {
      setManifestRollingBackVersion('');
    }
  };

  const handleManifestRouteCheck = async () => {
    if (!currentDsId) return;
    const questions = splitManifestList(manifestRouteQuestions);
    if (!questions.length) {
      setManifestMessage('请先输入至少一个测试问题。');
      return;
    }
    setManifestRouteChecking(true);
    setManifestMessage('');
    try {
      const data = await routeCheckDatasetSubAgentManifest(
        currentDsId,
        questions,
        manifestRouteExpected || null
      );
      setManifestRouteResults(data.results || []);
    } catch (err) {
      setManifestMessage('路由自检失败: ' + (err.message || '未知错误'));
    } finally {
      setManifestRouteChecking(false);
    }
  };

  const handleSaveManifestRouteCase = async (result) => {
    if (!currentDsId || !result) return;
    try {
      await createSemanticValidationCase(currentDsId, {
        question: result.question,
        status: result.decision === 'hit' ? 'passed' : 'failed',
        route_type: 'subagent_manifest',
        entry_intent: 'manifest_route_check',
        entry_route: result.decision,
        answer: result.reasons.join(' '),
        error: result.suggestions.join(' '),
        report: {
          source: 'subagent_manifest_route_check',
          expected: manifestRouteExpected || null,
          ...result,
        },
      });
      const cases = await listSemanticValidationCases(currentDsId);
      setValidationCases(cases);
      setManifestMessage('路由自检用例已保存。');
    } catch (err) {
      setManifestMessage('保存自检用例失败: ' + (err.message || '未知错误'));
    }
  };

  // ── 当前数据集 ──
  const activeDs = datasets.find(d => d.id === activeDsId) || datasets[0];
  const currentDsId = activeDsId || activeDs?.id;
  const primaryCapabilityTabs = [
    { id: 'tables', label: '数据表', count: selectedTableIds.size, icon: 'table', stage: '资产', desc: '同步表结构并选择进入语义层的物理表。' },
    { id: 'fields', label: '字段标注', count: selectedColumns.length, icon: 'string', stage: '标注', desc: '审核字段语义、描述和时间/枚举等角色。' },
    { id: 'metrics', label: '指标', count: metrics.length, icon: 'formula', stage: '口径', desc: '维护可复用指标口径和聚合规则。' },
    { id: 'dimensions', label: '维度', count: dimensions.length, icon: 'layers', stage: '口径', desc: '维护分析维度、枚举和值域解释。' },
    { id: 'blueprints', label: '分析蓝图', count: null, icon: 'branch', stage: '路径', desc: '把复杂 SQL 和业务步骤固化为可触发的分析能力。' },
    { id: 'validation', label: '语义验证', count: null, icon: 'beaker', stage: '验收', desc: '用真实问法验证语义层召回和 SQL 生成效果。' },
  ];
  const advancedGovernanceTabs = [
    { id: 'manifest', label: 'SubAgent Manifest', count: manifestDetail?.current_manifest ? 1 : 0, icon: 'brain', stage: manifestDetail?.stale ? '需复核' : '契约', desc: '维护数据集路由契约、版本和自检样例。' },
    { id: 'terms', label: '语义词典', count: businessTerms.length, icon: 'book', stage: '治理', desc: '治理跨资产别名、冲突和解释口径。' },
    { id: 'scenarios', label: '分析场景', count: 0, icon: 'insight', stage: '场景', desc: '组织高频问数场景和运营分析任务。' },
    { id: 'permissions', label: '权限', count: null, icon: 'shield', stage: '治理', desc: '控制数据集、指标和蓝图的可见范围。' },
    { id: 'versions', label: '版本历史', count: null, icon: 'history', stage: '治理', desc: '追踪语义资产变更和发布记录。' },
  ];
  const capabilityTabs = [...primaryCapabilityTabs, ...advancedGovernanceTabs];
  const selectedTableNames = [...new Set(selectedColumns.map(c => c.table_name).filter(Boolean))];
  const selectedPreviewTables = allSourceTables.filter(t => selectedTableIds.has(t.id));
  const activePreviewTable = previewTableId
    ? allSourceTables.find(t => t.id === previewTableId)
    : selectedPreviewTables[0];
  const focusedSelectedTable = focusedTableId
    ? allSourceTables.find(t => t.id === focusedTableId)
    : null;
  const selectedColumnsForFocusedTable = focusedTableId
    ? selectedColumns.filter(c => c.source_table_id === focusedTableId)
    : selectedColumns;
  const getColumnRole = (col) => col.user_semantic_role || col.ai_semantic_role || col.semantic_role || 'unknown';
  const isColumnConverted = (col) => Boolean(col.converted_metric_id || col.converted_dimension_id || String(col.review_status || '').startsWith('converted_to_'));
  const isColumnIgnored = (col) => col.review_status === 'ignored';
  const metricCandidateColumns = selectedColumns.filter(c => getColumnRole(c) === 'metric_candidate');
  const dimensionCandidateColumns = selectedColumns.filter(c => ['dimension_candidate', 'time_field', 'id_field'].includes(getColumnRole(c)));
  const convertedColumnsCount = selectedColumns.filter(isColumnConverted).length;
  const ignoredColumnsCount = selectedColumns.filter(isColumnIgnored).length;
  const annotatedColumnsCount = selectedColumns.filter(c => c.effective_desc || c.business_desc || c.user_description || c.user_semantic_role || c.ai_semantic_role).length;
  const userAnnotatedColumnsCount = selectedColumns.filter(c => c.user_description || c.user_semantic_role).length;
  const aiAnnotatedColumnsCount = selectedColumns.filter(c => c.desc_source === 'ai' || c.ai_description || c.ai_semantic_role).length;
  const pendingReviewColumnsCount = selectedColumns.filter(c => {
    const role = getColumnRole(c);
    if (isColumnConverted(c) || isColumnIgnored(c) || c.review_status === 'confirmed') return false;
    return !role || !c.effective_desc || ['unknown', 'fallback', 'stale'].includes(c.desc_source);
  }).length;
  const filteredAnnotationColumns = useMemo(() => {
    const q = fieldSearch.trim().toLowerCase();
    return selectedColumns.filter(col => {
      const role = getColumnRole(col);
      const source = col.desc_source || 'unknown';
      const converted = isColumnConverted(col);
      const ignored = isColumnIgnored(col);
      const hay = [
        col.column_name,
        col.table_name,
        col.data_type,
        col.effective_desc,
        col.business_desc,
        col.ai_description,
        col.user_description,
      ].filter(Boolean).join(' ').toLowerCase();
      if (q && !hay.includes(q)) return false;
      if (fieldTableFilter && col.table_name !== fieldTableFilter) return false;
      if (fieldRoleFilter && role !== fieldRoleFilter) return false;
      if (fieldSourceFilter === 'manual' && !(col.user_description || col.user_semantic_role)) return false;
      if (fieldSourceFilter === 'ai' && !(source === 'ai' || col.ai_description || col.ai_semantic_role)) return false;
      if (fieldSourceFilter === 'pending' && (converted || ignored || col.review_status === 'confirmed' || (role && col.effective_desc && !['unknown', 'fallback', 'stale'].includes(source)))) return false;
      if (fieldSourceFilter === 'convert_metric' && (role !== 'metric_candidate' || converted || ignored)) return false;
      if (fieldSourceFilter === 'convert_dimension' && (!['dimension_candidate', 'time_field', 'id_field'].includes(role) || converted || ignored)) return false;
      if (fieldSourceFilter === 'converted' && !converted) return false;
      if (fieldSourceFilter === 'ignored' && !ignored) return false;
      if (fieldSourceFilter && !['manual', 'ai', 'pending', 'convert_metric', 'convert_dimension', 'converted', 'ignored'].includes(fieldSourceFilter) && source !== fieldSourceFilter) return false;
      return true;
    });
  }, [fieldRoleFilter, fieldSearch, fieldSourceFilter, fieldTableFilter, selectedColumns]);
  const annotationTableGroups = useMemo(() => {
    const groups = new Map();
    filteredAnnotationColumns.forEach(col => {
      const key = col.source_table_id || col.table_name || 'unknown';
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          tableName: col.table_name || '未知表',
          schemaName: col.schema_name || '',
          columns: [],
        });
      }
      groups.get(key).columns.push(col);
    });
    return Array.from(groups.values())
      .map(group => {
        const metricCount = group.columns.filter(col => getColumnRole(col) === 'metric_candidate' && !isColumnConverted(col) && !isColumnIgnored(col)).length;
        const dimensionCount = group.columns.filter(col => ['dimension_candidate', 'time_field', 'id_field'].includes(getColumnRole(col)) && !isColumnConverted(col) && !isColumnIgnored(col)).length;
        const convertedCount = group.columns.filter(isColumnConverted).length;
        const ignoredCount = group.columns.filter(isColumnIgnored).length;
        const pendingCount = group.columns.filter(col => {
          const role = getColumnRole(col);
          return !isColumnConverted(col)
            && !isColumnIgnored(col)
            && col.review_status !== 'confirmed'
            && (!role || !col.effective_desc || ['unknown', 'fallback', 'stale'].includes(col.desc_source));
        }).length;
        return { ...group, metricCount, dimensionCount, convertedCount, ignoredCount, pendingCount };
      })
      .sort((a, b) => String(a.tableName).localeCompare(String(b.tableName)));
  }, [filteredAnnotationColumns]);
  const filteredBusinessTerms = useMemo(() => {
    const q = termSearch.trim().toLowerCase();
    return businessTerms.filter(term => {
      const hay = [
        term.name,
        term.display_name,
        term.definition,
        ...(term.aliases || []),
        ...(term.asset_links || []).map(link => link.asset_name),
      ].filter(Boolean).join(' ').toLowerCase();
      if (q && !hay.includes(q)) return false;
      if (termTypeFilter && term.term_type !== termTypeFilter) return false;
      if (termStatusFilter && term.status !== termStatusFilter) return false;
      return true;
    });
  }, [businessTerms, termSearch, termStatusFilter, termTypeFilter]);
  const selectedTerm = businessTerms.find(term => term.id === selectedTermId) || filteredBusinessTerms[0] || null;
  const activeTermsCount = businessTerms.filter(term => term.status === 'active').length;
  const aliasedTermsCount = businessTerms.filter(term => (term.aliases || []).length > 0).length;
  const linkedTermsCount = businessTerms.filter(term => (term.asset_links || []).length > 0).length;

  const resetMetricForm = () => {
    setEditingMetricId(null);
    setMetricSourceColumnId(null);
    setMetricForm({ name: '', display_name: '', expr: '', table_name: '', time_field: '', granularity: '', format_str: '', filter_sql: '', synonyms: '', description: '' });
    setShowMetricForm(true);
  };

  const resetDimForm = () => {
    setEditingDimId(null);
    setDimSourceColumnId(null);
    setDimForm({ name: '', display_name: '', column_name: '', table_name: '', join_to: '', join_key: '', enum_values: '', synonyms: '' });
    setShowDimForm(true);
  };

  const handlePreviewTableChange = (nextId) => {
    if (!nextId) return;
    setPreviewTableId(nextId);
    if (selectedTableIds.has(nextId)) setFocusedTableId(nextId);
  };

  const getColumnRoleBadge = (col) => {
    const effectiveRole = col.user_semantic_role || col.ai_semantic_role || col.semantic_role;
    return {
      metric_candidate: { label: 'M', text: '度量候选', color: 'var(--accent)', bg: 'var(--accent-soft)' },
      dimension_candidate: { label: 'D', text: '维度候选', color: 'var(--pos)', bg: 'var(--pos-soft)' },
      time_field: { label: 'T', text: '时间字段', color: 'var(--warn)', bg: 'var(--warn-soft)' },
      id_field: { label: 'ID', text: '标识字段', color: 'var(--text-3)', bg: 'var(--bg-2)' },
      unused: { label: '—', text: '未使用', color: 'var(--text-4)', bg: 'var(--bg-2)' },
    }[effectiveRole] || { label: '?', text: '待确认', color: 'var(--text-3)', bg: 'var(--bg-2)' };
  };

  const renderManifestPanel = () => {
    const detail = manifestDetail || {};
    const autoFields = detail.auto_fields_preview || {};
    const current = detail.current_manifest;
    const guard = detail.manifest_guard || {};
    const permissionScope = current?.permission_scope || autoFields.permission_scope || {};
    const qualityStatus = current?.quality_status || {};
    const versions = detail.versions || [];
    const lint = detail.lint || [];
    const lintErrors = lint.filter(item => item.severity === 'error');
    const manual = manifestManualFieldsFromForm(manifestForm);
    const status = detail.stale ? 'needs_review' : (current?.review_status || detail.review_status || 'missing');
    return (
      <div className="capability-manifest-panel" style={{ border: '1px solid var(--hairline)', borderRadius: 10, padding: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Icon name="brain" style={{ width: 14, height: 14, color: 'var(--accent)' }} />
              SubAgent Manifest
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>
              数据集路由契约，当前不改聊天主路由；发布后的 current manifest 供后续 LeadAgent 使用。
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            <span style={{ padding: '4px 8px', borderRadius: 6, fontSize: 12, background: detail.stale ? 'rgba(245,158,11,0.12)' : 'var(--surface)', color: detail.stale ? '#b45309' : 'var(--text-2)', border: '1px solid var(--hairline)' }}>
              {MANIFEST_STATUS_LABEL[status] || status}
            </span>
            <button className="btn ghost" onClick={() => loadManifestDetail()} disabled={manifestLoading}>
              <Icon name="refresh" />{manifestLoading ? '刷新中…' : '刷新'}
            </button>
            <button className="btn" onClick={handleManifestSave} disabled={manifestSaving}>
              <Icon name="bookmark" />{manifestSaving ? '保存中…' : '保存草稿'}
            </button>
            <button className="btn primary" onClick={handleManifestPublish} disabled={manifestPublishing}>
              <Icon name="check" />{manifestPublishing ? '发布中…' : '发布 current'}
            </button>
          </div>
        </div>

        {manifestMessage && (
          <div style={{ marginBottom: 12, border: '1px solid var(--hairline)', borderRadius: 6, padding: 9, background: 'var(--surface)', color: manifestMessage.includes('失败') ? 'var(--neg)' : 'var(--text-2)', fontSize: 12 }}>
            {manifestMessage}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14 }}>
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ border: '1px solid var(--hairline)', borderRadius: 8, padding: 12, background: 'var(--surface)' }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>自动派生字段</div>
              <div style={{ display: 'grid', gap: 8, fontSize: 12 }}>
                {[
                  ['数据集', autoFields.name || activeDs?.name || '—'],
                  ['Manifest 版本', current?.manifest_version || '未发布'],
                  ['Schema 绑定', current?.bound_schema_version || autoFields.bound_schema_version || '—'],
                  ['最新 Schema', detail.latest_schema_version || autoFields.bound_schema_version || '—'],
                  ['权限状态', permissionScope.status || 'not_configured'],
                  ['质量状态', qualityStatus.status || '未发布'],
                  ['执行门禁', guard.status ? `${guard.status}${guard.block_reason ? ` / ${guard.block_reason}` : ''}` : '—'],
                  ['指标数', `${autoFields.key_metrics?.length || 0}`],
                  ['维度数', `${autoFields.key_dimensions?.length || 0}`],
                ].map(([label, value]) => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <span style={{ color: 'var(--text-3)' }}>{label}</span>
                    <span style={{ color: 'var(--text)', fontFamily: label.includes('Schema') ? 'var(--font-mono)' : undefined, textAlign: 'right' }}>{value}</span>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {(autoFields.key_metrics || []).slice(0, 6).map(item => (
                  <span key={`m-${item.id || item.name}`} style={{ padding: '3px 7px', borderRadius: 5, background: 'var(--bg-2)', color: 'var(--text-2)', fontSize: 11 }}>
                    {item.display_name || item.name}
                  </span>
                ))}
                {(autoFields.key_dimensions || []).slice(0, 6).map(item => (
                  <span key={`d-${item.id || item.name}`} style={{ padding: '3px 7px', borderRadius: 5, background: 'rgba(14,165,233,0.10)', color: 'var(--accent)', fontSize: 11 }}>
                    {item.display_name || item.name}
                  </span>
                ))}
              </div>
            </div>

            <div style={{ border: '1px solid var(--hairline)', borderRadius: 8, padding: 12, background: 'var(--surface)' }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>质量校验</div>
              {lint.length ? (
                <div style={{ display: 'grid', gap: 7 }}>
                  {lint.map(item => (
                    <div key={item.code} style={{ display: 'flex', gap: 7, alignItems: 'flex-start', fontSize: 12, color: item.severity === 'error' ? 'var(--neg)' : '#b45309' }}>
                      <Icon name={item.severity === 'error' ? 'warn' : 'flag'} style={{ width: 13, height: 13, marginTop: 2 }} />
                      <span>{item.message}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--pos)' }}>
                  <Icon name="check" style={{ width: 13, height: 13 }} />
                  当前字段满足发布校验。
                </div>
              )}
              <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-3)' }}>
                发布会阻断 error；草稿允许保存并保留校验提示。
              </div>
            </div>
          </div>

          <div style={{ border: '1px solid var(--hairline)', borderRadius: 8, padding: 12, background: 'var(--surface)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 600 }}>人工维护字段</div>
              <div style={{ fontSize: 11, color: lintErrors.length ? 'var(--neg)' : 'var(--text-3)' }}>
                正例 {manual.sample_questions.length}/5-10 · 负例 {manual.routing_negative_examples.length}/3-5
              </div>
            </div>
            <div style={{ display: 'grid', gap: 10 }}>
              <label style={{ display: 'grid', gap: 5, fontSize: 12 }}>
                <span style={{ color: 'var(--text-2)' }}>description</span>
                <textarea
                  value={manifestForm.description}
                  onChange={e => setManifestForm(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="用途 + 核心实体 + 适合回答的问题类型 + 明确不覆盖的范围"
                  rows={5}
                  style={{ width: '100%', resize: 'vertical', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--bg)', color: 'var(--text)', fontSize: 13, lineHeight: 1.5 }}
                />
                <span style={{ color: 'var(--text-3)', fontSize: 11 }}>{manifestForm.description.length} 字，建议 80-200 字。</span>
              </label>
              <label style={{ display: 'grid', gap: 5, fontSize: 12 }}>
                <span style={{ color: 'var(--text-2)' }}>business_domain</span>
                <textarea
                  value={manifestForm.business_domain_text}
                  onChange={e => setManifestForm(prev => ({ ...prev, business_domain_text: e.target.value }))}
                  placeholder="每行一个，例如：销售运营"
                  rows={3}
                  style={{ width: '100%', resize: 'vertical', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--bg)', color: 'var(--text)', fontSize: 13, lineHeight: 1.5 }}
                />
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(160px, 220px) 1fr', gap: 10 }}>
                <label style={{ display: 'grid', gap: 5, fontSize: 12 }}>
                  <span style={{ color: 'var(--text-2)' }}>permission_scope.status</span>
                  <select
                    value={manifestForm.permission_scope_status}
                    onChange={e => setManifestForm(prev => ({ ...prev, permission_scope_status: e.target.value }))}
                    style={{ padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--bg)', color: 'var(--text)', fontSize: 13 }}
                  >
                    <option value="not_configured">not_configured</option>
                    <option value="allowed">allowed</option>
                    <option value="denied">denied</option>
                  </select>
                </label>
                <label style={{ display: 'grid', gap: 5, fontSize: 12 }}>
                  <span style={{ color: 'var(--text-2)' }}>permission_scope.description</span>
                  <input
                    value={manifestForm.permission_scope_description}
                    onChange={e => setManifestForm(prev => ({ ...prev, permission_scope_description: e.target.value }))}
                    placeholder="说明当前可执行范围和人工确认依据"
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--bg)', color: 'var(--text)', fontSize: 13 }}
                  />
                </label>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 10 }}>
                <label style={{ display: 'grid', gap: 5, fontSize: 12 }}>
                  <span style={{ color: 'var(--text-2)' }}>sample_questions</span>
                  <textarea
                    value={manifestForm.sample_questions_text}
                    onChange={e => setManifestForm(prev => ({ ...prev, sample_questions_text: e.target.value }))}
                    placeholder="每行一个正例，5-10 条"
                    rows={8}
                    style={{ width: '100%', resize: 'vertical', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--bg)', color: 'var(--text)', fontSize: 13, lineHeight: 1.5 }}
                  />
                </label>
                <label style={{ display: 'grid', gap: 5, fontSize: 12 }}>
                  <span style={{ color: 'var(--text-2)' }}>routing_negative_examples</span>
                  <textarea
                    value={manifestForm.routing_negative_examples_text}
                    onChange={e => setManifestForm(prev => ({ ...prev, routing_negative_examples_text: e.target.value }))}
                    placeholder="每行一个易混淆负例，3-5 条"
                    rows={8}
                    style={{ width: '100%', resize: 'vertical', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--bg)', color: 'var(--text)', fontSize: 13, lineHeight: 1.5 }}
                  />
                </label>
              </div>
            </div>
          </div>
        </div>

        {versions.length > 0 && (
          <div style={{ marginTop: 14, border: '1px solid var(--hairline)', borderRadius: 8, padding: 12, background: 'var(--surface)' }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 10 }}>版本记录</div>
            <div style={{ display: 'grid', gap: 8 }}>
              {versions.map(version => {
                const isCurrent = version.is_current;
                const quality = version.quality_status || {};
                const permission = version.permission_scope || {};
                return (
                  <div key={version.manifest_version} style={{ display: 'grid', gridTemplateColumns: 'minmax(90px, 130px) 1fr auto', gap: 10, alignItems: 'center', border: '1px solid var(--hairline)', borderRadius: 7, padding: 9, background: 'var(--bg)' }}>
                    <div>
                      <div className="mono" style={{ fontSize: 12, fontWeight: 700 }}>{version.manifest_version}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{MANIFEST_STATUS_LABEL[version.review_status] || version.review_status}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-3)' }}>
                      <span className="mono">schema {version.schema_hash || version.bound_schema_version}</span>
                      <span>permission {permission.status || 'not_configured'}</span>
                      <span>quality {quality.status || 'unknown'}</span>
                      {version.created_by && <span>by {version.created_by}</span>}
                    </div>
                    <button
                      className="btn ghost"
                      disabled={isCurrent || manifestRollingBackVersion === version.manifest_version}
                      onClick={() => handleManifestRollback(version.manifest_version)}
                    >
                      <Icon name="refresh" />{manifestRollingBackVersion === version.manifest_version ? '回滚中…' : isCurrent ? '当前' : '回滚'}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div style={{ marginTop: 14, border: '1px solid var(--hairline)', borderRadius: 8, padding: 12, background: 'var(--surface)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 600 }}>路由自检</div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>输入测试问题，检查 manifest 是否稳定命中或避让。</div>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <select
                value={manifestRouteExpected}
                onChange={e => setManifestRouteExpected(e.target.value)}
                style={{ padding: '7px 9px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--bg)', color: 'var(--text)', fontSize: 12 }}
              >
                <option value="">不设预期</option>
                <option value="positive">期望命中</option>
                <option value="negative">期望避让</option>
              </select>
              <button className="btn primary" onClick={handleManifestRouteCheck} disabled={manifestRouteChecking}>
                <Icon name="beaker" />{manifestRouteChecking ? '自检中…' : '运行自检'}
              </button>
            </div>
          </div>
          <textarea
            value={manifestRouteQuestions}
            onChange={e => setManifestRouteQuestions(e.target.value)}
            placeholder="每行一个测试问题。可直接粘贴 sample_questions 或负例。"
            rows={4}
            style={{ width: '100%', resize: 'vertical', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--bg)', color: 'var(--text)', fontSize: 13, lineHeight: 1.5, marginBottom: 10 }}
          />
          {manifestRouteResults.length > 0 && (
            <div style={{ display: 'grid', gap: 8 }}>
              {manifestRouteResults.map((result, idx) => (
                <div key={`${result.question}-${idx}`} style={{ border: '1px solid var(--hairline)', borderRadius: 7, padding: 10, background: 'var(--bg)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{result.question}</div>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <span style={{ padding: '2px 7px', borderRadius: 5, fontSize: 11, color: result.decision === 'hit' ? 'var(--pos)' : result.decision === 'miss' ? 'var(--neg)' : '#b45309', background: result.decision === 'hit' ? 'rgba(34,197,94,0.10)' : result.decision === 'miss' ? 'rgba(239,68,68,0.10)' : 'rgba(245,158,11,0.12)' }}>
                        {result.decision} · {Math.round((result.score || 0) * 100)}%
                      </span>
                      <span style={{ padding: '2px 7px', borderRadius: 5, fontSize: 11, color: result.executable ? 'var(--pos)' : 'var(--neg)', background: result.executable ? 'rgba(34,197,94,0.10)' : 'rgba(239,68,68,0.10)' }}>
                        {result.matched_manifest_version || '—'} · {result.executable ? '可执行' : '不可执行'}
                      </span>
                      <button className="btn ghost" onClick={() => handleSaveManifestRouteCase(result)}>
                        <Icon name="bookmark" />保存用例
                      </button>
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 6 }}>
                    {(result.reasons || []).join(' ')}
                    {result.suggestions?.length ? ` 建议：${result.suggestions.join(' ')}` : ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderFieldAnnotationPanel = () => (
    <div className="semantic-tab-panel">
      <div className="tab-panel-head">
        <div>
          <div className="tab-panel-kicker"><Icon name="string" />字段标注工作台</div>
          <h3>审核字段语义，快速沉淀指标和维度</h3>
          <p>已选表字段在这里集中审核。字段角色、业务描述、AI 标注来源都可见，候选字段可一键进入指标/维度创建流程。</p>
        </div>
        <div className="tab-panel-actions">
          <button className="btn ghost" onClick={() => setActiveCapabilityTab('tables')}><Icon name="table" />选择数据表</button>
          <button className="btn primary" onClick={handleAnnotate} disabled={annotating || !activeDsId}>
            <Icon name="brain" />{annotating ? '标注中…' : 'AI 自动标注'}
          </button>
        </div>
      </div>
      <div className="semantic-stats">
        <StatCard label="已选表" value={selectedTableIds.size} hint={`可用表 ${allSourceTables.length}`} />
        <StatCard label="AI 标注" value={aiAnnotatedColumnsCount} hint={`覆盖 ${selectedColumns.length} 个字段`} />
        <StatCard label="人工确认" value={userAnnotatedColumnsCount} hint={`已标注 ${annotatedColumnsCount}`} />
        <StatCard label="已转化" value={convertedColumnsCount} hint={`忽略 ${ignoredColumnsCount} 个`} />
      </div>
      <div className="annotation-command-center">
        <div className="annotation-flow">
          {[
            ['1', 'AI 初标', `${aiAnnotatedColumnsCount} 个字段已有 AI 建议`],
            ['2', '人工审核', `${pendingReviewColumnsCount} 个待确认 / ${userAnnotatedColumnsCount} 个已确认`],
            ['3', '资产沉淀', `${metricCandidateColumns.length} 个度量 / ${dimensionCandidateColumns.length} 个维度候选`],
          ].map(([step, title, desc]) => (
            <div key={step} className="annotation-flow-step">
              <strong>{step}</strong>
              <span>{title}</span>
              <small>{desc}</small>
            </div>
          ))}
        </div>
        <div className="annotation-filters">
          <div className="annotation-search">
            <Icon name="search" />
            <input
              value={fieldSearch}
              onChange={e => setFieldSearch(e.target.value)}
              placeholder="搜索字段、表名、描述..."
            />
            {fieldSearch && (
              <button className="icon-btn" onClick={() => setFieldSearch('')}><Icon name="x" /></button>
            )}
          </div>
          <select value={fieldTableFilter} onChange={e => setFieldTableFilter(e.target.value)}>
            <option value="">全部表</option>
            {selectedTableNames.map(name => <option key={name} value={name}>{name}</option>)}
          </select>
          <select value={fieldRoleFilter} onChange={e => setFieldRoleFilter(e.target.value)}>
            <option value="">全部角色</option>
            <option value="metric_candidate">度量候选</option>
            <option value="dimension_candidate">维度候选</option>
            <option value="time_field">时间字段</option>
            <option value="id_field">标识字段</option>
            <option value="unused">未使用</option>
          </select>
          <select value={fieldSourceFilter} onChange={e => setFieldSourceFilter(e.target.value)}>
            <option value="">全部来源</option>
            <option value="pending">待确认</option>
            <option value="convert_metric">可建指标</option>
            <option value="convert_dimension">可建维度</option>
            <option value="converted">已转化</option>
            <option value="ignored">已忽略</option>
            <option value="manual">人工确认</option>
            <option value="ai">AI 标注</option>
            <option value="db_comment">数据库注释</option>
            <option value="fallback">回退字段名</option>
            <option value="stale">待更新</option>
          </select>
          {(fieldSearch || fieldTableFilter || fieldRoleFilter || fieldSourceFilter) && (
            <button
              className="btn ghost"
              onClick={() => {
                setFieldSearch('');
                setFieldTableFilter('');
                setFieldRoleFilter('');
                setFieldSourceFilter('');
              }}
            >
              重置
            </button>
          )}
        </div>
      </div>
      {selectedColumns.length === 0 ? (
        <GuidedEmpty
          icon="inbox"
          title="还没有可标注字段"
          desc="先到数据表 Tab 勾选进入语义层的表，然后回到这里审核字段标注。"
          actionLabel="去选择数据表"
          onAction={() => setActiveCapabilityTab('tables')}
        />
      ) : (
        <>
        <div className="annotation-review-head">
          <div>
            <span>审核队列</span>
            <strong>{filteredAnnotationColumns.length}</strong>
          </div>
          <div>
            <button className="btn ghost" onClick={() => setFieldSourceFilter('pending')}>只看待确认</button>
            <button className="btn ghost" onClick={() => setFieldSourceFilter('convert_metric')}>可建指标</button>
            <button className="btn ghost" onClick={() => setFieldSourceFilter('convert_dimension')}>可建维度</button>
            <button className="btn ghost" onClick={() => setFieldSourceFilter('converted')}>已转化</button>
          </div>
        </div>

        {filteredAnnotationColumns.length === 0 ? (
          <GuidedEmpty
            icon="search"
            title="没有匹配的字段"
            desc="调整表、角色、来源或搜索关键词后重试。"
            actionLabel="清空筛选"
            onAction={() => {
              setFieldSearch('');
              setFieldTableFilter('');
              setFieldRoleFilter('');
              setFieldSourceFilter('');
            }}
          />
        ) : (
        <div className="annotation-table-groups">
          {annotationTableGroups.map((group, groupIndex) => (
            <details
              key={group.key}
              className="annotation-table-group"
              open={Boolean(fieldTableFilter) || annotationTableGroups.length <= 1 || groupIndex === 0}
            >
              <summary className="annotation-table-summary">
                <div className="annotation-table-title">
                  <Icon name="table" />
                  <strong>{group.tableName}</strong>
                  {group.schemaName && <code>{group.schemaName}</code>}
                </div>
                <div className="annotation-table-counters">
                  <span>{group.columns.length} 字段</span>
                  {group.pendingCount > 0 && <em className="warn">{group.pendingCount} 待确认</em>}
                  {group.metricCount > 0 && <em>{group.metricCount} 可建指标</em>}
                  {group.dimensionCount > 0 && <em>{group.dimensionCount} 可建维度</em>}
                  {group.convertedCount > 0 && <em className="converted">{group.convertedCount} 已转化</em>}
                  {group.ignoredCount > 0 && <em className="muted">{group.ignoredCount} 已忽略</em>}
                </div>
              </summary>
              <div className="field-worklist annotation-worklist">
                {group.columns.map(col => {
                  const roleBadge = getColumnRoleBadge(col);
                  const isEditing = editingColumnId === col.id;
                  const sourceLabel = col.converted_metric_id
                    ? '已建指标'
                    : col.converted_dimension_id
                    ? '已建维度'
                    : col.review_status === 'ignored'
                    ? '已忽略'
                    : col.review_status === 'confirmed'
                    ? '人工确认'
                    : col.user_description || col.user_semantic_role
                    ? '人工确认'
                    : col.desc_source === 'ai' || col.ai_description || col.ai_semantic_role
                    ? 'AI 建议'
                    : col.desc_source === 'db_comment'
                    ? '数据库注释'
                    : col.desc_source === 'stale'
                    ? '待更新'
                    : '待确认';
                  return (
                    <div key={col.id} className={'field-card ' + (isEditing ? 'editing' : '')}>
                      <div className="field-role" style={{ background: roleBadge.bg, color: roleBadge.color }}>{roleBadge.label}</div>
                      <div className="field-main">
                        <div className="field-title-row">
                          <strong>{col.column_name}</strong>
                          <code>{col.data_type}</code>
                          <em className={'field-source-chip ' + (sourceLabel === '待确认' || sourceLabel === '待更新' ? 'warn' : sourceLabel === '人工确认' ? 'manual' : sourceLabel.startsWith('已建') ? 'converted' : sourceLabel === '已忽略' ? 'ignored' : '')}>{sourceLabel}</em>
                        </div>
                        {isEditing ? (
                          <div className="field-edit-row">
                            <select
                              value={columnEditForm.user_semantic_role}
                              onChange={e => setColumnEditForm(prev => ({ ...prev, user_semantic_role: e.target.value }))}
                            >
                              <option value="">自动</option>
                              <option value="metric_candidate">M 度量</option>
                              <option value="dimension_candidate">D 维度</option>
                              <option value="time_field">T 时间</option>
                              <option value="id_field">ID 标识</option>
                              <option value="unused">— 未用</option>
                            </select>
                            <input
                              value={columnEditForm.user_description}
                              onChange={e => setColumnEditForm(prev => ({ ...prev, user_description: e.target.value }))}
                              placeholder="输入业务描述…"
                            />
                          </div>
                        ) : (
                          <p>{col.effective_desc || col.business_desc || '暂无业务描述'}</p>
                        )}
                        {(col.ai_description || col.ai_semantic_role) && !isEditing && (
                          <div className="field-ai-hint">
                            <Icon name="brain" />
                            <span>
                              AI 建议: {col.ai_description || '暂无描述建议'}
                              {col.ai_semantic_role ? ` · ${getColumnRoleBadge({ ...col, user_semantic_role: '', semantic_role: col.ai_semantic_role }).text}` : ''}
                              {col.ai_confidence ? ` · 置信度 ${Math.round(col.ai_confidence * 100)}%` : ''}
                              {col.ai_reason ? ` · ${col.ai_reason}` : ''}
                            </span>
                          </div>
                        )}
                        <div className="field-meta">
                          <span>{roleBadge.text}</span>
                          <span>来源: {col.desc_source || 'unknown'}</span>
                          {col.suggested_synonyms?.length > 0 && <span>同义词: {col.suggested_synonyms.slice(0, 3).join(', ')}</span>}
                          {col.suggested_enum_values?.length > 0 && <span>推荐枚举: {col.suggested_enum_values.slice(0, 3).join(', ')}</span>}
                          <span>样例: {col.sample_values?.length > 0 ? col.sample_values.slice(0, 3).join(', ') : '—'}</span>
                        </div>
                      </div>
                      <div className="field-actions">
                        {isEditing ? (
                          <>
                            <button className="icon-btn" title="保存" onClick={() => handleSaveColumnEdit(col.id)}><Icon name="check" /></button>
                            <button className="icon-btn" title="取消" onClick={handleCancelColumnEdit}><Icon name="x" /></button>
                          </>
                        ) : (
                          <>
                            {getColumnRole(col) === 'metric_candidate' && !col.converted_metric_id && col.review_status !== 'ignored' && (
                              <button className="icon-btn" title="创建指标" onClick={() => handleCreateMetricFromColumn(col)} disabled={convertingColumnId === col.id}><Icon name="formula" /></button>
                            )}
                            {['dimension_candidate', 'time_field', 'id_field'].includes(getColumnRole(col)) && !col.converted_dimension_id && col.review_status !== 'ignored' && (
                              <button className="icon-btn" title="创建维度" onClick={() => handleCreateDimFromColumn(col)} disabled={convertingColumnId === col.id}><Icon name="layers" /></button>
                            )}
                            {col.review_status !== 'confirmed' && !isColumnConverted(col) && col.review_status !== 'ignored' && (
                              <button className="icon-btn" title="标记已确认" onClick={() => handleColumnReviewStatus(col, 'confirmed')}><Icon name="check" /></button>
                            )}
                            {col.review_status !== 'ignored' && !isColumnConverted(col) && (
                              <button className="icon-btn" title="忽略字段" onClick={() => handleColumnReviewStatus(col, 'ignored')}><Icon name="x" /></button>
                            )}
                            <button className="icon-btn" title="编辑标注" onClick={() => handleStartEditColumn(col)}><Icon name="edit" /></button>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </details>
          ))}
        </div>
        )}
        </>
      )}
    </div>
  );

  const renderMetricsPanel = () => (
    <div className="semantic-tab-panel">
      <div className="tab-panel-head">
        <div>
          <div className="tab-panel-kicker"><Icon name="formula" />指标管理</div>
          <h3>管理可复用指标口径</h3>
          <p>指标定义、表达式、主表、时间字段和同义词集中维护，供问数、蓝图和语义验证共同使用。</p>
        </div>
        <div className="tab-panel-actions">
          <button className="btn ghost" onClick={() => setActiveCapabilityTab('fields')}><Icon name="string" />从字段选择</button>
          <button className="btn primary" onClick={resetMetricForm}><Icon name="plus" />新建指标</button>
        </div>
      </div>
      <div className="semantic-stats">
        <StatCard label="指标总数" value={metrics.length} hint="当前数据集" />
        <StatCard label="候选字段" value={metricCandidateColumns.length} hint="字段标注推荐" />
        <StatCard label="关联表" value={new Set(metrics.map(m => m.table_name).filter(Boolean)).size} hint={`${selectedTableNames.length} 张已选表`} />
        <StatCard label="有同义词" value={metrics.filter(m => (m.synonyms || []).length).length} hint="提升问法召回" />
      </div>
      <div className="semantic-two-col">
        <div className="asset-list-panel">
          {metrics.length === 0 ? (
            <GuidedEmpty icon="formula" title="暂无指标" desc="可以手动新建，也可以在字段标注里从度量候选字段快速创建。" actionLabel="新建指标" onAction={resetMetricForm} />
          ) : metrics.map(m => (
            <div key={m.id} className="semantic-asset-row">
              <div className="asset-icon metric"><Icon name="formula" /></div>
              <div className="asset-main">
                <div className="asset-title"><strong>{m.display_name || m.name}</strong><code>{m.name}</code></div>
                <div className="asset-desc">{m.description || m.expr || '暂无描述'}</div>
                <div className="asset-meta">
                  <span>表达式: {m.expr || '—'}</span>
                  <span>主表: {m.table_name || '—'}</span>
                  <span>时间字段: {m.time_field || '—'}</span>
                </div>
              </div>
              <div className="asset-actions">
                <button className="icon-btn" title="编辑" onClick={() => handleEditMetric(m)}><Icon name="edit" /></button>
                <button className="icon-btn danger" title="删除" onClick={() => handleDelMetric(m.id)}><Icon name="trash" /></button>
              </div>
            </div>
          ))}
        </div>
        <CandidateRail
          title="度量候选字段"
          empty="暂无度量候选字段"
          items={metricCandidateColumns}
          onPick={handleCreateMetricFromColumn}
          icon="formula"
          actionLabel="建指标"
        />
      </div>
    </div>
  );

  const renderDimensionsPanel = () => (
    <div className="semantic-tab-panel">
      <div className="tab-panel-head">
        <div>
          <div className="tab-panel-kicker"><Icon name="layers" />维度管理</div>
          <h3>管理分析维度和值域解释</h3>
          <p>维度定义关联字段、枚举值、同义词和关联键，帮助问数理解“区域、产品、渠道、状态”等业务切片。</p>
        </div>
        <div className="tab-panel-actions">
          <button className="btn ghost" onClick={() => setActiveCapabilityTab('fields')}><Icon name="string" />从字段选择</button>
          <button className="btn primary" onClick={resetDimForm}><Icon name="plus" />新建维度</button>
        </div>
      </div>
      <div className="semantic-stats">
        <StatCard label="维度总数" value={dimensions.length} hint="当前数据集" />
        <StatCard label="候选字段" value={dimensionCandidateColumns.length} hint="字段标注推荐" />
        <StatCard label="有关联键" value={dimensions.filter(d => d.join_key).length} hint="支持跨表分析" />
        <StatCard label="有枚举值" value={dimensions.filter(d => (d.enum_values || []).length).length} hint="提升解释质量" />
      </div>
      <div className="semantic-two-col">
        <div className="asset-list-panel">
          {dimensions.length === 0 ? (
            <GuidedEmpty icon="layers" title="暂无维度" desc="可以手动新建，也可以在字段标注里从维度候选字段快速创建。" actionLabel="新建维度" onAction={resetDimForm} />
          ) : dimensions.map(d => (
            <div key={d.id} className="semantic-asset-row">
              <div className="asset-icon dimension"><Icon name="layers" /></div>
              <div className="asset-main">
                <div className="asset-title"><strong>{d.display_name || d.name}</strong><code>{d.name}</code></div>
                <div className="asset-desc">{d.column_name || '暂无字段'} {d.table_name ? `· ${d.table_name}` : ''}</div>
                <div className="asset-meta">
                  <span>关联事实表: {d.join_to || '—'}</span>
                  <span>关联键: {d.join_key || '—'}</span>
                  <span>枚举: {(d.enum_values || []).slice(0, 3).join(', ') || '—'}</span>
                </div>
              </div>
              <div className="asset-actions">
                <button className="icon-btn" title="编辑" onClick={() => handleEditDim(d)}><Icon name="edit" /></button>
                <button className="icon-btn danger" title="删除" onClick={() => handleDelDim(d.id)}><Icon name="trash" /></button>
              </div>
            </div>
          ))}
        </div>
        <CandidateRail
          title="维度候选字段"
          empty="暂无维度候选字段"
          items={dimensionCandidateColumns}
          onPick={handleCreateDimFromColumn}
          icon="layers"
          actionLabel="建维度"
        />
      </div>
    </div>
  );

  const renderTermsPanel = () => (
    <div className="semantic-tab-panel">
      <div className="tab-panel-head">
        <div>
          <div className="tab-panel-kicker"><Icon name="book" />高级治理</div>
          <h3>语义词典 / 别名与口径</h3>
          <p>治理跨资产别名、同词多义冲突和解释口径。普通问数主路径不依赖先建词典，蓝图、指标和维度可顺手沉淀别名。</p>
        </div>
        <div className="tab-panel-actions">
          <button className="btn ghost" onClick={handleCheckTermConflicts} disabled={termBusy || !activeDsId}><Icon name="warn" />冲突检测</button>
          <button className="btn ghost" onClick={handleDiscoverTerms} disabled={termBusy || !activeDsId}><Icon name="brain" />建议别名</button>
          <button className="btn primary" onClick={resetTermForm} disabled={!activeDsId}><Icon name="plus" />新建词条</button>
        </div>
      </div>
      {termStatusMessage && (
        <div className="term-muted-box" role="status" style={{ marginBottom: 12 }}>
          {termStatusMessage}
        </div>
      )}
      <div className="semantic-stats">
        <StatCard label="词条总数" value={businessTerms.length} hint="当前数据集" />
        <StatCard label="已启用" value={activeTermsCount} hint="可用于问数解释" />
        <StatCard label="有同义词" value={aliasedTermsCount} hint="支持别名召回" />
        <StatCard label="有关联资产" value={linkedTermsCount} hint="字段/指标/维度/蓝图" />
      </div>
      <div className="term-workbench">
        <section className="term-list-panel">
          <div className="term-toolbar">
            <div className="annotation-search">
              <Icon name="search" />
              <input
                aria-label="搜索语义词典"
                value={termSearch}
                onChange={e => setTermSearch(e.target.value)}
                placeholder="搜索词条、同义词、定义..."
              />
            </div>
            <select value={termTypeFilter} onChange={e => setTermTypeFilter(e.target.value)}>
              <option value="">全部类型</option>
              {TERM_TYPE_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <select value={termStatusFilter} onChange={e => setTermStatusFilter(e.target.value)}>
              <option value="">全部状态</option>
              {TERM_STATUS_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </div>
          <div className="term-list">
            {filteredBusinessTerms.length === 0 ? (
              <GuidedEmpty
                icon="book"
                title={businessTerms.length === 0 ? '暂无语义词条' : '没有匹配的词条'}
                desc={businessTerms.length === 0 ? '当前无词条不影响问数。建议优先在蓝图、指标和维度中沉淀别名；治理人员也可以在这里集中维护。' : '调整搜索或筛选条件后继续查看词条。'}
                actionLabel={businessTerms.length === 0 ? '建议别名' : ''}
                onAction={handleDiscoverTerms}
              />
            ) : filteredBusinessTerms.map(term => (
              <button
                key={term.id}
                ref={node => {
                  if (node) termRowRefs.current[term.id] = node;
                  else delete termRowRefs.current[term.id];
                }}
                className={'term-row ' + (selectedTerm?.id === term.id ? 'active' : '')}
                onClick={() => handleSelectTerm(term.id)}
              >
                <span className="term-row-head">
                  <strong>{term.display_name || term.name}</strong>
                  <em className={'term-status ' + term.status}>{termStatusLabel(term.status)}</em>
                </span>
                <span className="term-row-meta">
                  <span>{termTypeLabel(term.term_type)}</span>
                  <span>{(term.aliases || []).length} 同义词</span>
                  <span>{(term.asset_links || []).length} 关联</span>
                </span>
              </button>
            ))}
          </div>
        </section>
        <section className={'term-detail-panel ' + (termDetailOpen ? 'mobile-open' : '')} aria-label="语义词条详情">
          {selectedTerm ? (
            <>
              <div className="term-detail-head">
                <div>
                  <div className="tab-panel-kicker"><Icon name="book" />{termTypeLabel(selectedTerm.term_type)}</div>
                  <h3>{selectedTerm.display_name || selectedTerm.name}</h3>
                  <code>{selectedTerm.name}</code>
                </div>
                <div className="asset-actions">
                  <button className="icon-btn term-detail-close" title="关闭详情" onClick={closeTermDetail}><Icon name="x" /></button>
                  <button className="icon-btn" title="编辑" onClick={() => handleEditTerm(selectedTerm)}><Icon name="edit" /></button>
                  <button className="icon-btn danger" title="删除" onClick={() => handleDeleteTerm(selectedTerm.id)}><Icon name="trash" /></button>
                </div>
              </div>
              <p className="term-definition">{selectedTerm.definition || '暂无定义说明'}</p>
              <div className="term-chip-section">
                <span>同义词</span>
                <div>
                  {(selectedTerm.aliases || []).length
                    ? selectedTerm.aliases.map(alias => <em key={alias}>{alias}</em>)
                    : <small>暂无</small>}
                </div>
              </div>
              <div className="term-chip-section">
                <span>禁用词</span>
                <div>
                  {(selectedTerm.forbidden_aliases || []).length
                    ? selectedTerm.forbidden_aliases.map(alias => <em key={alias} className="muted">{alias}</em>)
                    : <small>暂无</small>}
                </div>
              </div>
              <div className="term-asset-links">
                <div className="term-section-title">关联语义资产</div>
                {(selectedTerm.asset_links || []).length === 0 ? (
                  <div className="term-muted-box">暂无关联资产。AI 候选纳入时会自动带入来源资产。</div>
                ) : selectedTerm.asset_links.map(link => (
                  <div key={link.id || `${link.asset_type}-${link.asset_id}`} className="term-asset-link">
                    <span>{link.asset_type}</span>
                    <strong>{link.asset_name || `#${link.asset_id}`}</strong>
                  </div>
                ))}
              </div>
              <div className="term-examples">
                <div className="term-section-title">示例问法 / 枚举</div>
                {(selectedTerm.examples || []).length
                  ? selectedTerm.examples.map(item => <span key={item}>{item}</span>)
                  : <small>暂无</small>}
              </div>
            </>
          ) : (
            <GuidedEmpty icon="book" title="选择一个词条查看详情" desc="词条详情会展示定义、同义词、关联资产和示例问法。" />
          )}
        </section>
        <aside className="term-side-panel">
          <div className="term-side-block">
            <div className="term-section-title">AI 候选术语</div>
            {termCandidates.length === 0 ? (
              <div className="term-muted-box">点击“建议别名”后，会从指标、维度和字段标注中提取候选。未维护词条不会阻塞问数主路径。</div>
            ) : termCandidates.slice(0, 8).map(candidate => (
              <div key={`${candidate.source}-${candidate.name}`} className="term-candidate">
                <div>
                  <strong>{candidate.display_name || candidate.name}</strong>
                  <span>{termTypeLabel(candidate.term_type)} · {Math.round((candidate.confidence || 0) * 100)}%</span>
                </div>
                <button className="btn ghost" onClick={() => handleAcceptTermCandidate(candidate)} disabled={termBusy}>纳入</button>
              </div>
            ))}
          </div>
          <div className="term-side-block">
            <div className="term-section-title">冲突检测</div>
            {termConflicts.length === 0 ? (
              <div className="term-muted-box">暂无冲突结果。点击“冲突检测”可检查同义词重叠和禁用词冲突。</div>
            ) : termConflicts.map((conflict, idx) => (
              <div key={`${conflict.type}-${conflict.token}-${idx}`} className={'term-conflict ' + conflict.severity}>
                <strong>{conflict.token}</strong>
                <span>{conflict.message}</span>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );

  // ── 渲染 ──
  return (
    <div className="ds-wrap">
      {/* ── 顶部操作栏 ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
        <div>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 2 }}>语义治理 / 数据集</div>
          <h1 style={{ fontSize: 20, fontWeight: 500, margin: 0, letterSpacing: '-0.02em' }}>
            {activeDs?.name || '数据集 & 指标'}
          </h1>
          {activeDs?.schema_name && (
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
              Schema：<span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{activeDs.schema_name}</span>
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className="btn ghost" onClick={() => setShowYamlImport(true)}><Icon name="upload" />导入 YAML</button>
          <button className="btn ghost" onClick={handleExportYaml}><Icon name="download" />导出 YAML</button>
          <button className="btn ghost" onClick={handleSyncTables} disabled={syncing || !activeDsId}>
            <Icon name="refresh" />{syncing ? '同步中…' : '同步表结构'}
          </button>
          <button className="btn ghost" onClick={handleAnnotate} disabled={annotating || !activeDsId}>
            <Icon name="brain" />{annotating ? '标注中…' : 'AI 自动标注'}
          </button>
          <button className="btn primary" onClick={() => setShowDsForm(true)}><Icon name="plus" />新建数据集</button>
        </div>
      </div>

      {/* ── 主体：左侧数据集 + 右侧三栏 ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '200px minmax(0, 1fr)', gap: 20 }}>
        {/* 左侧：数据集列表 */}
        <aside style={{ borderRight: '1px solid var(--hairline)', paddingRight: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', padding: '0 8px 8px', fontWeight: 500 }}>数据集</div>
          {datasets.map(d => (
            renamingId === d.id ? (
              <div key={d.id} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 6px' }}>
                <input
                  autoFocus
                  value={renameValue}
                  onChange={e => setRenameValue(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') commitRename();
                    else if (e.key === 'Escape') { setRenamingId(null); }
                  }}
                  onBlur={commitRename}
                  onClick={e => e.stopPropagation()}
                  onMouseDown={e => e.stopPropagation()}
                  style={{ flex: 1, padding: '4px 8px', fontSize: 13, borderRadius: 4, border: '1px solid var(--accent)', background: 'var(--surface)', color: 'var(--text)', outline: 'none' }}
                />
              </div>
            ) : (
              <button
                key={d.id}
                onClick={() => { setActiveDsId(d.id); setFocusedTableId(null); setPreviewTableId(null); setSelectedColumns([]); setPreviewData(null); }}
                onContextMenu={e => openCtxMenu(e, d)}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 10px', fontSize: 13, borderRadius: 6, width: '100%', textAlign: 'left', cursor: 'pointer', background: activeDsId === d.id ? 'var(--surface-2)' : 'transparent', color: activeDsId === d.id ? 'var(--text)' : 'var(--text-2)', border: 'none' }}
              >
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', flexShrink: 0 }} />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</span>
              </button>
            )
          ))}
          {datasets.length === 0 && !loading && (
            <div style={{ padding: '16px 8px', fontSize: 12, color: 'var(--text-3)' }}>暂无数据集</div>
          )}
        </aside>

        {/* ── 数据集右键菜单浮层 ── */}
        {ctxMenu && (
          <div
            ref={ctxMenuRef}
            style={{
              position: 'fixed', top: ctxMenu.y, left: ctxMenu.x, zIndex: 200,
              background: 'var(--surface)', border: '1px solid var(--hairline)',
              borderRadius: 8, padding: 4, minWidth: 160,
              boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
            }}
          >
            <button
              onClick={() => startRename(ctxMenu.ds)}
              style={ctxMenuItemStyle}
            >
              <Icon name="edit" style={{ width: 14, height: 14, color: 'var(--text-3)' }} />
              <span>重命名</span>
            </button>
            <button
              onClick={() => {
                setPromptFormDs({
                  ...ctxMenu.ds,
                  query_constraints: normalizeQueryConstraints(ctxMenu.ds.query_constraints),
                });
                setShowPromptForm(true);
                setCtxMenu(null);
              }}
              style={ctxMenuItemStyle}
            >
              <Icon name="cog" style={{ width: 14, height: 14, color: 'var(--text-3)' }} />
              <span>查询约束</span>
            </button>
            <div style={{ height: 1, background: 'var(--hairline)', margin: '4px 2px' }} />
            <button
              onClick={() => requestDelete(ctxMenu.ds)}
              style={{ ...ctxMenuItemStyle, color: 'var(--neg)' }}
            >
              <Icon name="trash" style={{ width: 14, height: 14, color: 'var(--neg)' }} />
              <span>删除</span>
            </button>
          </div>
        )}

        {/* 右侧：能力工作区 */}
        <div style={{ minWidth: 0 }}>
          <div className="capability-workbench">
            <div className="capability-workbench-head">
              <div>
                <div className="capability-eyebrow">语义能力工作区</div>
                <div className="capability-title-row">
                  <span className="capability-stage">工作台</span>
                  <h2>数据集语义能力</h2>
                </div>
                <p>按主路径配置数据资产、语义口径、分析蓝图和验证；高级治理用于语义词典、权限和版本。</p>
              </div>
              <div className="capability-route">
                <span>表资产</span>
                <Icon name="chev" />
                <span>语义口径</span>
                <Icon name="chev" />
                <strong>分析能力</strong>
              </div>
            </div>
          <div className="ds-tabs capability-tabs">
            {primaryCapabilityTabs.map(tab => (
              <button
                key={tab.id}
                className={'ds-tab ' + (activeCapabilityTab === tab.id ? 'active' : '')}
                onClick={() => setActiveCapabilityTab(tab.id)}
              >
                <span className="tab-icon"><Icon name={tab.icon} /></span>
                <span className="tab-copy">
                  <span className="tab-label">{tab.label}</span>
                  <span className="tab-stage">{tab.stage}</span>
                </span>
                {tab.count != null && <span className="count">{tab.count}</span>}
              </button>
            ))}
          </div>
          <div className="capability-advanced-tabs">
            <div className="capability-advanced-title">
              <Icon name="shield" />
              高级治理
            </div>
            <div className="ds-tabs capability-tabs secondary">
              {advancedGovernanceTabs.map(tab => (
                <button
                  key={tab.id}
                  className={'ds-tab ' + (activeCapabilityTab === tab.id ? 'active' : '')}
                  onClick={() => setActiveCapabilityTab(tab.id)}
                >
                  <span className="tab-icon"><Icon name={tab.icon} /></span>
                  <span className="tab-copy">
                    <span className="tab-label">{tab.label}</span>
                    <span className="tab-stage">{tab.stage}</span>
                  </span>
                  {tab.count != null && <span className="count">{tab.count}</span>}
                </button>
              ))}
            </div>
          </div>
          </div>

          <div className="capability-page-slot">
            {activeCapabilityTab === 'blueprints' && currentDsId ? (
              <AnalysisBlueprintsPanel datasetId={currentDsId} />
            ) : activeCapabilityTab === 'fields' ? (
              renderFieldAnnotationPanel()
            ) : activeCapabilityTab === 'metrics' ? (
              renderMetricsPanel()
            ) : activeCapabilityTab === 'dimensions' ? (
              renderDimensionsPanel()
            ) : activeCapabilityTab === 'terms' ? (
              renderTermsPanel()
            ) : activeCapabilityTab === 'manifest' ? (
              renderManifestPanel()
            ) : activeCapabilityTab === 'tables' ? (
        <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 320px', gap: 16, minHeight: 480 }}>
          {/* 左栏：数据源表目录（带勾选 + 搜索） */}
          <div style={{ borderRight: '1px solid var(--hairline)', paddingRight: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 0 8px' }}>
              <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 500 }}>数据源表目录</div>
            </div>
            {/* 搜索框 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, padding: '5px 8px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--surface)' }}>
              <Icon name="search" style={{ width: 12, height: 12, color: 'var(--text-3)', flexShrink: 0 }} />
              <input
                placeholder="搜索表名…"
                value={tableSearch}
                onChange={e => setTableSearch(e.target.value)}
                style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 12, color: 'var(--text)', padding: 0 }}
              />
              {tableSearch && (
                <button className="icon-btn" style={{ width: 16, height: 16 }} onClick={() => setTableSearch('')}>
                  <Icon name="x" style={{ width: 10, height: 10 }} />
                </button>
              )}
            </div>
            {/* 全选 / 取消全选 */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
              <button className="btn ghost" style={{ height: 24, fontSize: 10, padding: '0 8px', flex: 1 }} onClick={async () => {
                const ids = filteredTables.map(t => t.id).filter(id => !selectedTableIds.has(id));
                if (ids.length) {
                  try {
                    await selectTablesForDataset(activeDsId, ids);
                    setFocusedTableId(ids[0]);
                    setPreviewTableId(ids[0]);
                    await loadSelectedTables(activeDsId);
                  }
                  catch (err) { alert('全选失败: ' + (err.message || '未知错误')); }
                }
              }}>全选</button>
              <button className="btn ghost" style={{ height: 24, fontSize: 10, padding: '0 8px', flex: 1 }} onClick={async () => {
                const ids = filteredTables.map(t => t.id).filter(id => selectedTableIds.has(id));
                for (const id of ids) {
                  try { await deselectTableFromDataset(activeDsId, id); } catch (e) { console.error(e); }
                }
                setFocusedTableId(null);
                setPreviewTableId(null);
                setPreviewData(null);
                await loadSelectedTables(activeDsId);
              }}>取消全选</button>
            </div>
            {/* 表列表 */}
            <div style={{ maxHeight: 360, overflow: 'auto' }}>
              {tableListItems.map(item => {
                if (item.type === 'group') {
                  return (
                    <div
                      key={item.id}
                      style={{
                        position: 'sticky',
                        top: 0,
                        zIndex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '6px 4px 4px',
                        marginTop: item.id === 'selected' ? 0 : 6,
                        background: 'var(--bg)',
                        color: item.id === 'selected' ? 'var(--accent)' : 'var(--text-3)',
                        fontSize: 10,
                        fontWeight: 700,
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                      }}
                    >
                      <span>{item.label}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', letterSpacing: 0 }}>{item.count}</span>
                    </div>
                  );
                }
                const t = item.table;
                const checked = selectedTableIds.has(t.id);
                const inspecting = inspectingTableId === t.id;
                const focused = focusedTableId === t.id;
                const tableSourceBadge = {
                  db_comment: { label: '注', color: '#16a34a', bg: '#dcfce7' },
                  ai:         { label: 'AI', color: '#2563eb', bg: '#dbeafe' },
                  user:       { label: '用', color: '#ca8a04', bg: '#fef9c3' },
                  fallback:   { label: '退', color: '#6b7280', bg: '#f3f4f6' },
                  unknown:    { label: '?', color: '#9ca3af', bg: '#f3f4f6' },
                  stale:      { label: '旧', color: '#ea580c', bg: '#ffedd5' },
                }[t.desc_source] || { label: '?', color: '#6b7280', bg: '#f3f4f6' };
                // 行底色：已选优先 → 蓝灰；查看中 → 浅紫；普通 → 透明
                const rowBg = checked
                  ? focused
                    ? 'var(--accent-soft)'
                    : 'var(--surface-2)'
                  : inspecting
                  ? 'var(--accent-soft)'
                  : 'transparent';
                const rowBorder = focused || inspecting
                  ? '1px solid var(--accent)'
                  : '1px solid transparent';
                return (
                  <div
                    key={t.id}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8, padding: '5px 8px',
                      fontSize: 12, borderRadius: 6, marginBottom: 2,
                      background: rowBg, border: rowBorder,
                    }}
                  >
                    {/* 勾选框 — 独立 onClick；点它只切换是否加入数据集 */}
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={e => handleToggleTable(t.id, e.target.checked)}
                      onClick={e => e.stopPropagation()}
                      style={{ cursor: 'pointer', flexShrink: 0 }}
                      title={checked ? '已加入数据集' : '加入数据集'}
                    />
                    {/* 表名可点击区域：触发"查看"模式（不切换勾选） */}
                    <button
                      type="button"
                      onClick={() => handleInspectTable(t.id)}
                      title={t.effective_desc || t.table_comment || t.table_name || ''}
                      style={{
                        flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 2,
                        background: 'transparent', border: 'none', padding: 0,
                        cursor: 'pointer', minWidth: 0, textAlign: 'left',
                        color: focused || inspecting ? 'var(--accent)' : checked ? 'var(--text)' : 'var(--text-2)',
                        fontWeight: focused || inspecting ? 600 : 400,
                      }}
                    >
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%' }}>
                        <Icon name={inspecting ? 'eye' : focused ? 'pin' : 'table'} style={{ width: 14, height: 14, flexShrink: 0 }} />
                        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.table_name}</span>
                      </span>
                      {t.effective_desc && (
                        <span style={{
                          fontSize: 10, color: 'var(--text-3)', lineHeight: 1.3,
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          maxWidth: '100%', paddingLeft: 20,
                        }}>{t.effective_desc}</span>
                      )}
                    </button>
                    <span style={{
                      display: 'inline-block', padding: '0 4px', borderRadius: 3, fontSize: 9, fontWeight: 600,
                      color: tableSourceBadge.color, background: tableSourceBadge.bg, flexShrink: 0,
                    }}>{tableSourceBadge.label}</span>
                    {checked && (
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 2,
                        padding: '0 4px',
                        borderRadius: 3,
                        fontSize: 9,
                        fontWeight: 700,
                        color: 'var(--accent)',
                        background: 'var(--accent-soft)',
                        flexShrink: 0,
                      }}>
                        <Icon name="check" style={{ width: 9, height: 9 }} />
                        已选
                      </span>
                    )}
                    <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>{t.column_count}</span>
                  </div>
                );
              })}
              {filteredTables.length === 0 && (
                <div style={{ padding: '16px 4px', fontSize: 12, color: 'var(--text-3)' }}>
                  {allSourceTables.length === 0 ? (
                    <><span>暂无同步的表</span><br /><span style={{ fontSize: 11, opacity: 0.7 }}>点击「同步表结构」拉取</span></>
                  ) : '没有匹配的表'}
                </div>
              )}
            </div>
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--hairline)', fontSize: 11, color: 'var(--text-3)' }}>
              已选 {selectedTableIds.size} / {allSourceTables.length} 张表
            </div>
          </div>

          {/* 中栏：字段列表（查看模式 / 已选模式 / 空状态 三态） */}
          <div>
            {(() => {
              const inspectTable = inspectingTableId
                ? allSourceTables.find(t => t.id === inspectingTableId)
                : null;
              if (inspectTable) {
                // ── 查看模式：只读展示表元信息 + 字段（不影响数据集）
                const sourceBadge = {
                  db_comment: { label: '注释', color: '#16a34a', bg: '#dcfce7' },
                  ai:         { label: 'AI',   color: '#2563eb', bg: '#dbeafe' },
                  user:       { label: '用户', color: '#ca8a04', bg: '#fef9c3' },
                  fallback:   { label: '回退', color: '#6b7280', bg: '#f3f4f6' },
                  unknown:    { label: '识别中…', color: '#9ca3af', bg: '#f3f4f6' },
                  stale:      { label: '待更新', color: '#ea580c', bg: '#ffedd5' },
                }[inspectTable.desc_source] || { label: '?', color: '#6b7280', bg: '#f3f4f6' };
                return (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <div style={{
                        display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 0,
                        fontSize: 11, color: 'var(--accent)', textTransform: 'uppercase',
                        letterSpacing: '0.08em', fontWeight: 600,
                      }}>
                        <Icon name="eye" style={{ width: 12, height: 12 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          查看中 · {inspectTable.table_name}
                        </span>
                      </div>
                      <button
                        className="icon-btn"
                        onClick={handleCloseInspect}
                        title="关闭查看"
                        style={{ width: 22, height: 22 }}
                      >
                        <Icon name="x" style={{ width: 12, height: 12, color: 'var(--text-3)' }} />
                      </button>
                    </div>
                    {/* 表元信息卡片 */}
                    <div style={{
                      padding: '10px 12px', marginBottom: 10,
                      background: 'var(--surface-2)', border: '1px solid var(--hairline)', borderRadius: 8,
                      fontSize: 12,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                        <span style={{
                          display: 'inline-block', padding: '1px 6px', borderRadius: 4,
                          fontSize: 10, fontWeight: 500,
                          color: sourceBadge.color, background: sourceBadge.bg,
                        }}>{sourceBadge.label}</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)' }}>
                          {inspectTable.schema_name ? `${inspectTable.schema_name}.` : ''}{inspectTable.table_name}
                        </span>
                      </div>
                      <div style={{ color: 'var(--text-2)', lineHeight: 1.5, marginBottom: 6 }}>
                        {inspectTable.effective_desc || inspectTable.table_comment || <span style={{ color: 'var(--text-4)' }}>暂无描述</span>}
                      </div>
                      <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-3)' }}>
                        <span>字段数 <strong style={{ color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{inspectTable.column_count}</strong></span>
                        {inspectTable.row_count_approx != null && (
                          <span>约 <strong style={{ color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{inspectTable.row_count_approx.toLocaleString()}</strong> 行</span>
                        )}
                      </div>
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-3)', marginBottom: 6 }}>
                      字段列表{inspectColumns.length > 0 && `（${inspectColumns.length}）`}
                      {inspectLoading && <span style={{ marginLeft: 6 }}>加载中…</span>}
                    </div>
                    {inspectColumns.length === 0 && !inspectLoading ? (
                      <div style={{ padding: '24px 8px', fontSize: 12, color: 'var(--text-3)', textAlign: 'center' }}>
                        暂无字段
                      </div>
                    ) : (
                      <div className="dataset-field-table-wrap">
                        <table className="dataset-field-table inspect">
                          <colgroup>
                            <col className="col-role" />
                            <col className="col-name" />
                            <col className="col-type" />
                            <col className="col-desc" />
                            <col className="col-source" />
                            <col className="col-sample" />
                          </colgroup>
                          <thead>
                            <tr style={{ background: 'var(--bg-2)', fontSize: 11, color: 'var(--text-3)' }}>
                              <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)', width: 40 }}>角色</th>
                              <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)' }}>字段名</th>
                              <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)', width: 80 }}>类型</th>
                              <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)' }}>业务描述</th>
                              <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)' }}>来源</th>
                              <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)' }}>样例值</th>
                            </tr>
                          </thead>
                          <tbody>
                            {inspectColumns.map(col => {
                              const effectiveRole = col.user_semantic_role || col.ai_semantic_role || col.semantic_role;
                              const roleBadge = {
                                metric_candidate:    { label: 'M', color: 'var(--accent)', bg: 'var(--accent-soft)' },
                                dimension_candidate: { label: 'D', color: 'var(--pos)', bg: 'var(--pos-soft)' },
                                time_field:          { label: 'T', color: 'var(--warn)', bg: 'var(--warn-soft)' },
                                id_field:            { label: 'ID', color: 'var(--text-3)', bg: 'var(--bg-2)' },
                                unused:              { label: '—', color: 'var(--text-4)', bg: 'var(--bg-2)' },
                              }[effectiveRole] || { label: '?', color: 'var(--text-3)', bg: 'var(--bg-2)' };
                              const colSrcBadge = {
                                db_comment: { label: '注释', color: '#16a34a', bg: '#dcfce7', tip: '来自数据库注释' },
                                ai:         { label: 'AI',   color: '#2563eb', bg: '#dbeafe', tip: 'AI 自动生成' },
                                user:       { label: '用户', color: '#ca8a04', bg: '#fef9c3', tip: '用户手动修改' },
                                fallback:   { label: '回退', color: '#6b7280', bg: '#f3f4f6', tip: '无描述，退回字段名' },
                                unknown:    { label: '识别中…', color: '#9ca3af', bg: '#f3f4f6', tip: '正在识别业务语义…' },
                                stale:      { label: '待更新', color: '#ea580c', bg: '#ffedd5', tip: '注释已变更，待重新标注' },
                              }[col.desc_source] || { label: '?', color: '#6b7280', bg: '#f3f4f6' };
                              return (
                                <tr key={col.id} style={{ borderBottom: '1px solid var(--hairline)' }}>
                                  <td style={{ padding: '7px 10px' }}>
                                    <span style={{
                                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                      width: 22, height: 22, borderRadius: 4, background: roleBadge.bg,
                                      fontSize: 10, fontWeight: 600, color: roleBadge.color,
                                    }}>{roleBadge.label}</span>
                                  </td>
                                  <td style={{ padding: '7px 10px', fontWeight: 500, color: 'var(--text)' }}>{col.column_name}</td>
                                  <td style={{ padding: '7px 10px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)' }}>{col.data_type}</td>
                                  <td style={{ padding: '7px 10px', color: 'var(--text-2)' }}>
                                    {col.effective_desc || col.business_desc || <span style={{ color: 'var(--text-4)' }}>—</span>}
                                  </td>
                                  <td style={{ padding: '7px 10px' }}>
                                    <span title={colSrcBadge.tip} style={{
                                      display: 'inline-block', padding: '1px 6px', borderRadius: 4,
                                      fontSize: 10, fontWeight: 500, whiteSpace: 'nowrap',
                                      color: colSrcBadge.color, background: colSrcBadge.bg,
                                    }}>{colSrcBadge.label}</span>
                                  </td>
                                  <td style={{ padding: '7px 10px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {col.sample_values?.length > 0 ? col.sample_values.slice(0, 3).join(', ') : <span style={{ color: 'var(--text-4)' }}>—</span>}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                    <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-3)' }}>
                      这是只读预览。如需将此表加入数据集进行编辑，请点击该行最左边的 <strong>□ 复选框</strong>。
                    </div>
                  </div>
                );
              }
              // ── 已选模式（编辑）/ 空状态 ──
              return (
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', padding: '0 0 8px', fontWeight: 500 }}>
                    {focusedSelectedTable ? `当前表字段 · ${focusedSelectedTable.table_name}` : '已选表字段'}
                    {selectedColumnsForFocusedTable.length > 0 && ` (${selectedColumnsForFocusedTable.length})`}
                    {focusedSelectedTable && selectedColumns.length !== selectedColumnsForFocusedTable.length && (
                      <button
                        className="btn ghost"
                        style={{ height: 22, fontSize: 10, padding: '0 7px', marginLeft: 8 }}
                        onClick={() => setFocusedTableId(null)}
                      >
                        查看全部已选字段
                      </button>
                    )}
                  </div>
                  {selectedColumnsForFocusedTable.length === 0 ? (
                    <div style={{ padding: '32px 8px', fontSize: 12, color: 'var(--text-3)', textAlign: 'center' }}>
                      <Icon name="inbox" style={{ width: 24, height: 24, marginBottom: 8, opacity: 0.4 }} />
                      <div>从左栏勾选表加入数据集</div>
                      <div style={{ marginTop: 6, fontSize: 11, opacity: 0.85 }}>
                        点击表名仅查看表信息，不会加入数据集
                      </div>
                    </div>
                  ) : (
                    <div className="dataset-field-table-wrap">
                <table className="dataset-field-table selected">
                  <colgroup>
                    <col className="col-role" />
                    <col className="col-name" />
                    <col className="col-type" />
                    <col className="col-table" />
                    <col className="col-desc" />
                    <col className="col-source" />
                    <col className="col-sample" />
                    <col className="col-actions" />
                  </colgroup>
                  <thead>
                    <tr style={{ background: 'var(--bg-2)', fontSize: 11, color: 'var(--text-3)' }}>
                      <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)', width: 40 }}>角色</th>
                      <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)' }}>字段名</th>
                      <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)', width: 80 }}>类型</th>
                      <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)' }}>所属表</th>
                      <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)' }}>业务描述</th>
                      <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)' }}>来源</th>
                      <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)' }}>样例值</th>
                      <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 500, borderBottom: '1px solid var(--hairline)', width: 50 }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedColumnsForFocusedTable.map(col => {
                      const effectiveRole = col.user_semantic_role || col.ai_semantic_role || col.semantic_role;
                      const roleBadge = {
                        metric_candidate: { label: 'M', color: 'var(--accent)', bg: 'var(--accent-soft)' },
                        dimension_candidate: { label: 'D', color: 'var(--pos)', bg: 'var(--pos-soft)' },
                        time_field: { label: 'T', color: 'var(--warn)', bg: 'var(--warn-soft)' },
                        id_field: { label: 'ID', color: 'var(--text-3)', bg: 'var(--bg-2)' },
                        unused: { label: '—', color: 'var(--text-4)', bg: 'var(--bg-2)' },
                      }[effectiveRole] || { label: '?', color: 'var(--text-3)', bg: 'var(--bg-2)' };

                      const sourceBadge = {
                        db_comment: { label: '注释', color: '#16a34a', bg: '#dcfce7', tip: '来自数据库注释' },
                        ai:         { label: 'AI',   color: '#2563eb', bg: '#dbeafe', tip: 'AI 自动生成' },
                        user:       { label: '用户', color: '#ca8a04', bg: '#fef9c3', tip: '用户手动修改' },
                        fallback:   { label: '回退', color: '#6b7280', bg: '#f3f4f6', tip: '无描述，退回字段名' },
                        unknown:    { label: '识别中…', color: '#9ca3af', bg: '#f3f4f6', tip: '正在识别业务语义…' },
                        stale:      { label: '待更新', color: '#ea580c', bg: '#ffedd5', tip: '注释已变更，待重新标注' },
                      }[col.desc_source] || { label: '?', color: '#6b7280', bg: '#f3f4f6', tip: '' };

                      const isEditing = editingColumnId === col.id;
                      return (
                        <tr key={col.id} style={{ borderBottom: '1px solid var(--hairline)', background: isEditing ? 'var(--bg-2)' : undefined }}>
                          {isEditing ? (
                            <>
                              {/* 编辑模式 */}
                              <td style={{ padding: '7px 10px' }}>
                                <select
                                  value={columnEditForm.user_semantic_role}
                                  onChange={e => setColumnEditForm(prev => ({ ...prev, user_semantic_role: e.target.value }))}
                                  style={{ padding: '3px 6px', borderRadius: 4, border: '1px solid var(--hairline)', fontSize: 11, background: 'var(--surface)', color: 'var(--text)' }}
                                >
                                  <option value="">自动</option>
                                  <option value="metric_candidate">M 度量</option>
                                  <option value="dimension_candidate">D 维度</option>
                                  <option value="time_field">T 时间</option>
                                  <option value="id_field">ID 标识</option>
                                  <option value="unused">— 未用</option>
                                </select>
                              </td>
                              <td style={{ padding: '7px 10px', fontWeight: 500, color: 'var(--text)' }}>{col.column_name}</td>
                              <td style={{ padding: '7px 10px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)' }}>{col.data_type}</td>
                              <td style={{ padding: '7px 10px', fontSize: 11, color: 'var(--text-2)' }}>{col.table_name}</td>
                              <td style={{ padding: '7px 10px' }} colSpan={2}>
                                <input
                                  type="text"
                                  value={columnEditForm.user_description}
                                  onChange={e => setColumnEditForm(prev => ({ ...prev, user_description: e.target.value }))}
                                  placeholder="输入业务描述…"
                                  style={{ width: '100%', padding: '4px 8px', borderRadius: 4, border: '1px solid var(--hairline)', fontSize: 12, background: 'var(--surface)', color: 'var(--text)' }}
                                />
                              </td>
                              <td style={{ padding: '7px 10px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {col.sample_values?.length > 0 ? col.sample_values.slice(0, 3).join(', ') : <span style={{ color: 'var(--text-4)' }}>—</span>}
                              </td>
                              <td style={{ padding: '7px 10px', display: 'flex', gap: 4, alignItems: 'center' }}>
                                <button className="icon-btn" title="保存" onClick={() => handleSaveColumnEdit(col.id)} style={{ width: 22, height: 22 }}>
                                  <Icon name="check" style={{ width: 12, height: 12, color: 'var(--pos)' }} />
                                </button>
                                <button className="icon-btn" title="取消" onClick={handleCancelColumnEdit} style={{ width: 22, height: 22 }}>
                                  <Icon name="x" style={{ width: 12, height: 12, color: 'var(--text-4)' }} />
                                </button>
                              </td>
                            </>
                          ) : (
                            <>
                              {/* 只读模式 */}
                              <td style={{ padding: '7px 10px' }}>
                                <span style={{
                                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                  width: 22, height: 22, borderRadius: 4, background: roleBadge.bg,
                                  fontSize: 10, fontWeight: 600, color: roleBadge.color,
                                }}>{roleBadge.label}</span>
                              </td>
                              <td style={{ padding: '7px 10px', fontWeight: 500, color: 'var(--text)' }}>{col.column_name}</td>
                              <td style={{ padding: '7px 10px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)' }}>{col.data_type}</td>
                              <td style={{ padding: '7px 10px', fontSize: 11, color: 'var(--text-2)' }}>{col.table_name}</td>
                              <td style={{ padding: '7px 10px', color: 'var(--text-2)' }}>
                                {col.effective_desc || col.business_desc || <span style={{ color: 'var(--text-4)' }}>—</span>}
                              </td>
                              <td style={{ padding: '7px 10px' }}>
                                <span title={sourceBadge.tip} style={{
                                  display: 'inline-block',
                                  padding: '1px 6px',
                                  borderRadius: 4,
                                  fontSize: 10,
                                  fontWeight: 500,
                                  color: sourceBadge.color,
                                  background: sourceBadge.bg,
                                  whiteSpace: 'nowrap',
                                }}>{sourceBadge.label}</span>
                              </td>
                              <td style={{ padding: '7px 10px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {col.sample_values?.length > 0 ? col.sample_values.slice(0, 3).join(', ') : <span style={{ color: 'var(--text-4)' }}>—</span>}
                              </td>
                              <td style={{ padding: '7px 10px', display: 'flex', gap: 4, alignItems: 'center' }}>
                                {effectiveRole === 'metric_candidate' && (
                                  <button className="icon-btn" title="新建指标" onClick={() => handleCreateMetricFromColumn(col)} style={{ width: 22, height: 22 }}>
                                    <Icon name="plus" style={{ width: 12, height: 12, color: 'var(--accent)' }} />
                                  </button>
                                )}
                                {effectiveRole === 'dimension_candidate' && (
                                  <button className="icon-btn" title="新建维度" onClick={() => handleCreateDimFromColumn(col)} style={{ width: 22, height: 22 }}>
                                    <Icon name="plus" style={{ width: 12, height: 12, color: 'var(--pos)' }} />
                                  </button>
                                )}
                                <button className="icon-btn" title="编辑标注" onClick={() => handleStartEditColumn(col)} style={{ width: 22, height: 22 }}>
                                  <Icon name="edit" style={{ width: 12, height: 12, color: 'var(--text-3)' }} />
                                </button>
                              </td>
                            </>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              )}
            </div>
            );
            })()}

            {/* 数据预览 */}
            {selectedTableIds.size > 0 && (
              <DataPreviewPanel
                tables={selectedPreviewTables}
                previewTableId={previewTableId}
                previewTable={activePreviewTable}
                previewData={previewData}
                loading={previewLoading}
                onSelectTable={handlePreviewTableChange}
                onRefresh={() => {
                  const nextId = previewTableId || activePreviewTable?.id;
                  if (nextId) loadPreview(nextId);
                }}
              />
            )}
          </div>

          {/* 右栏：指标/维度定义 */}
          <div style={{ borderLeft: '1px solid var(--hairline)', paddingLeft: 12 }}>
            <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', padding: '0 0 8px', fontWeight: 500 }}>已定义指标</div>
            {metrics.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '8px 0' }}>暂无指标</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
                {metrics.map(m => (
                  <div key={m.id} style={{ padding: '8px 10px', background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 6, fontSize: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 500 }}>{m.name}</span>
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="icon-btn" style={{ width: 20, height: 20 }} onClick={() => handleEditMetric(m)}><Icon name="edit" style={{ width: 12, height: 12 }} /></button>
                        <button className="icon-btn" style={{ width: 20, height: 20, color: 'var(--neg)' }} onClick={() => handleDelMetric(m.id)}><Icon name="trash" style={{ width: 12, height: 12 }} /></button>
                      </div>
                    </div>
                    <code style={{ fontSize: 11, color: 'var(--accent)' }}>{m.expr}</code>
                  </div>
                ))}
              </div>
            )}
            <button className="btn ghost" style={{ width: '100%', fontSize: 12, marginBottom: 16 }} onClick={() => { setEditingMetricId(null); setMetricForm({ name: '', display_name: '', expr: '', table_name: '', time_field: '', granularity: '', format_str: '', filter_sql: '', synonyms: '', description: '' }); setShowMetricForm(true); }}>
              <Icon name="plus" />新建指标
            </button>

            <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', padding: '12px 0 8px', fontWeight: 500 }}>已定义维度</div>
            {dimensions.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '8px 0' }}>暂无维度</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
                {dimensions.map(d => (
                  <div key={d.id} style={{ padding: '8px 10px', background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 6, fontSize: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 500 }}>{d.name}</span>
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="icon-btn" style={{ width: 20, height: 20 }} onClick={() => handleEditDim(d)}><Icon name="edit" style={{ width: 12, height: 12 }} /></button>
                        <button className="icon-btn" style={{ width: 20, height: 20, color: 'var(--neg)' }} onClick={() => handleDelDim(d.id)}><Icon name="trash" style={{ width: 12, height: 12 }} /></button>
                      </div>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{d.column_name} {d.table_name && `· ${d.table_name}`}</div>
                  </div>
                ))}
              </div>
            )}
            <button className="btn ghost" style={{ width: '100%', fontSize: 12 }} onClick={() => { setEditingDimId(null); setDimForm({ name: '', display_name: '', column_name: '', table_name: '', join_to: '', join_key: '', enum_values: '', synonyms: '' }); setShowDimForm(true); }}>
              <Icon name="plus" />新建维度
            </button>
          </div>
        </div>
            ) : activeCapabilityTab === 'validation' ? null : (
              <CapabilityEmptyPane tab={capabilityTabs.find(t => t.id === activeCapabilityTab)} />
            )}
          </div>

      {/* ── 底部：试问验证 ── */}
      {currentDsId && activeCapabilityTab === 'validation' && (
        <div className="capability-validation-panel" style={{ border: '1px solid var(--hairline)', borderRadius: 10, padding: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Icon name="beaker" style={{ width: 14, height: 14, color: 'var(--accent)' }} />
              语义层验证
            </div>
            {testReport && (
              <button className="btn ghost" onClick={handleSaveValidationCase} disabled={savingValidationCase}>
                <Icon name="bookmark" />{savingValidationCase ? '保存中…' : '保存用例'}
              </button>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input
              placeholder="例如：净销售额最近 7 天趋势 / 运行门店经营分析蓝图"
              value={testQuestion}
              onChange={e => setTestQuestion(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleTestQuery(); }}
              style={{ flex: 1, padding: '8px 12px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--surface)', color: 'var(--text)', fontSize: 13, outline: 'none' }}
            />
            <button className="btn primary" onClick={handleTestQuery} disabled={testStreaming || !testQuestion.trim()}>
              {testStreaming ? '验证中…' : '试问'}
            </button>
            {testStreaming && (
              <button className="btn ghost" onClick={() => { testAbortRef.current?.abort(); setTestStreaming(false); }}>停止</button>
            )}
          </div>

          {testStepEvents.length > 0 && !testReport && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
              {testStepEvents.slice(-6).map((step, idx) => (
                <span key={`${step.node}-${idx}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 7px', borderRadius: 5, border: '1px solid var(--hairline)', background: 'var(--surface)', fontSize: 11, color: 'var(--text-2)' }}>
                  <Icon name={step.status === 'done' ? 'check' : 'refresh'} style={{ width: 11, height: 11, color: step.status === 'done' ? 'var(--pos)' : 'var(--accent)' }} />
                  {step.display_name || step.node}
                </span>
              ))}
            </div>
          )}

          {testReport && (
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(260px, 0.8fr)', gap: 12, marginBottom: 16 }}>
              <div style={{ border: '1px solid var(--hairline)', borderRadius: 8, padding: 12, background: 'var(--surface)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>验证报告</div>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 7px', borderRadius: 5, fontSize: 11, color: testReport.status === 'passed' ? 'var(--pos)' : 'var(--neg)', background: testReport.status === 'passed' ? 'rgba(34,197,94,0.10)' : 'rgba(239,68,68,0.10)' }}>
                    <Icon name={testReport.status === 'passed' ? 'check' : 'warn'} style={{ width: 11, height: 11 }} />
                    {testReport.status === 'passed' ? '通过' : '需复核'}
                  </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8, marginBottom: 12 }}>
                  {[
                    ['路径', validationRouteLabel(testReport.entry_route)],
                    ['词典证据', `${testReport.terms.length}`],
                    ['蓝图命中', `${testReport.blueprints.length}`],
                    ['置信度', testReport.confidence?.score != null ? `${Math.round(testReport.confidence.score * 100)}%` : '—'],
                  ].map(([label, value]) => (
                    <div key={label} style={{ border: '1px solid var(--hairline)', borderRadius: 6, padding: 8, background: 'var(--bg)' }}>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 3 }}>{label}</div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</div>
                    </div>
                  ))}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 5 }}>语义词典证据</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                      {testReport.terms.length ? testReport.terms.map((term, idx) => (
                        <span key={`${validationAssetLabel(term)}-${idx}`} style={{ padding: '3px 7px', borderRadius: 5, background: 'var(--bg-2)', color: 'var(--text-2)', fontSize: 11 }}>
                          {validationAssetLabel(term)}
                        </span>
                      )) : <span style={{ color: 'var(--text-4)', fontSize: 12 }}>未命中</span>}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 5 }}>分析蓝图</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                      {testReport.blueprints.length ? testReport.blueprints.map((bp, idx) => (
                        <span key={`${validationAssetLabel(bp)}-${idx}`} style={{ padding: '3px 7px', borderRadius: 5, background: 'rgba(245,158,11,0.12)', color: '#b45309', fontSize: 11 }}>
                          {validationAssetLabel(bp)}
                        </span>
                      )) : <span style={{ color: 'var(--text-4)', fontSize: 12 }}>未命中</span>}
                    </div>
                  </div>
                </div>

                {testReport.failure_reason && (
                  <div style={{ marginBottom: 12, border: '1px solid rgba(239,68,68,0.25)', borderRadius: 6, padding: 9, background: 'rgba(239,68,68,0.06)', color: 'var(--neg)', fontSize: 12, lineHeight: 1.5 }}>
                    {testReport.failure_reason}
                  </div>
                )}

                {(testSql || testReport.sql) && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>生成 SQL</div>
                    <pre style={{ background: 'var(--bg-2)', padding: 10, borderRadius: 6, fontSize: 12, overflow: 'auto', margin: 0, color: 'var(--accent)', maxHeight: 180 }}>{testSql || testReport.sql}</pre>
                  </div>
                )}

                {testResult && (
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>回答</div>
                    <div style={{ background: 'var(--bg-2)', padding: 10, borderRadius: 6, fontSize: 13, lineHeight: 1.6 }}>{testResult}</div>
                  </div>
                )}
              </div>

              <div style={{ border: '1px solid var(--hairline)', borderRadius: 8, padding: 12, background: 'var(--surface)' }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 10 }}>链路轨迹</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {testReport.steps.map((step, idx) => (
                    <div key={`${step.node}-${idx}`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 6, background: 'var(--bg)', border: '1px solid var(--hairline)' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                        <Icon name="trace" style={{ width: 12, height: 12, color: 'var(--text-3)' }} />
                        {step.display_name || step.node}
                      </span>
                      <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{step.elapsed_ms != null ? `${step.elapsed_ms}ms` : step.status}</span>
                    </div>
                  ))}
                  {!testReport.steps.length && <div style={{ color: 'var(--text-4)', fontSize: 12 }}>暂无步骤事件</div>}
                </div>
              </div>
            </div>
          )}

          <div style={{ borderTop: '1px solid var(--hairline)', paddingTop: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>最近保存用例</div>
            {validationCases.length ? (
              <div style={{ display: 'grid', gap: 8 }}>
                {validationCases.slice(0, 5).map(item => (
                  <div key={item.id} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto auto', gap: 10, alignItems: 'center', padding: '8px 10px', border: '1px solid var(--hairline)', borderRadius: 7, background: 'var(--surface)' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.question}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{validationRouteLabel(item.entry_route)} · {item.created_at ? new Date(item.created_at).toLocaleString() : '未记录时间'}</div>
                    </div>
                    <span style={{ fontSize: 11, color: item.status === 'passed' ? 'var(--pos)' : 'var(--neg)' }}>{item.status === 'passed' ? '通过' : '需复核'}</span>
                    <button className="btn ghost" style={{ fontSize: 12 }} onClick={() => {
                      const report = item.report || null;
                      setTestQuestion(item.question);
                      setTestReport(report);
                      setTestSql(item.sql || report?.sql || '');
                      setTestResult(item.answer || report?.answer || '');
                      setTestStepEvents(report?.steps || []);
                    }}>查看</button>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ color: 'var(--text-4)', fontSize: 12, padding: '8px 0' }}>暂无保存的验证用例</div>
            )}
          </div>
        </div>
      )}

        </div>
      </div>

      {/* ── 弹窗：删除数据集（二次确认）── */}
      {confirmDelete && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 201, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          onClick={() => setConfirmDelete(null)}
        >
          <div
            style={{ background: 'var(--bg)', borderRadius: 12, padding: 24, width: 420, border: '1px solid var(--hairline)' }}
            onClick={e => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Icon name="warn" style={{ width: 16, height: 16, color: 'var(--neg)' }} />
              删除数据集
            </h3>
            <p style={{ margin: '0 0 16px', fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>
              确认要删除 <strong style={{ color: 'var(--text)' }}>「{confirmDelete.name}」</strong> 吗？<br />
              该数据集下所有指标和维度定义也会被一并删除，且不可恢复。
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button className="btn ghost" onClick={() => setConfirmDelete(null)}>取消</button>
              <button
                className="btn primary"
                onClick={confirmDeleteDataset}
                style={{ background: 'var(--neg)', borderColor: 'var(--neg)' }}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── 弹窗：新建数据集 ── */}
      {showDsForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 101, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setShowDsForm(false)}>
          <div style={{ background: 'var(--bg)', borderRadius: 12, padding: 24, width: 480, border: '1px solid var(--hairline)' }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 16px' }}>新建数据集</h3>
            <FormField label="名称" value={dsForm.name} onChange={v => setDsForm({ ...dsForm, name: v })} placeholder="如: 零售业务数据集" />
            <FormField label="数据源" type="select" value={dsForm.datasource_id} onChange={handleDatasetDatasourceChange} options={[{ value: '', label: '请选择数据源' }, ...datasources.map(d => ({ value: String(d.id), label: d.name }))]} />
            <FormField
              label="Schema"
              type="select"
              value={dsForm.schema_name}
              onChange={v => setDsForm({ ...dsForm, schema_name: v })}
              options={[
                { value: '', label: datasetSchemaLoading ? '正在加载 Schema…' : '请选择 Schema' },
                ...datasetSchemas.map(schema => ({ value: schema, label: schema })),
              ]}
            />
            {datasetSchemaError && (
              <div style={{ marginTop: -6, marginBottom: 12, fontSize: 11, color: 'var(--neg)' }}>
                {datasetSchemaError}
              </div>
            )}
            <FormField label="描述 (可选)" value={dsForm.description} onChange={v => setDsForm({ ...dsForm, description: v })} placeholder="数据集用途说明…" />
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, padding: '8px 10px', border: '1px solid var(--hairline)', borderRadius: 6, background: 'var(--surface-2)', fontSize: 12, color: 'var(--text-2)' }}>
              <Icon name="cog" style={{ width: 14, height: 14, color: 'var(--accent)' }} />
              <span>新建数据集默认开启 SQL 查询约束：未指定时间查最近 30 天，默认返回 100 条。</span>
            </div>
            <FormField
              label="LLM 约束 (可选)"
              type="textarea"
              rows={5}
              value={dsForm.prompt_instructions}
              onChange={v => setDsForm({ ...dsForm, prompt_instructions: v })}
              placeholder="例：金额统一保留两位小数；用户说'杨凯'时翻译为 person_name='杨凯'；订单状态枚举：1=待支付, 2=已支付, 4=已退款"
            />
            <div style={{ display: 'flex', gap: 10, marginTop: 16, justifyContent: 'flex-end' }}>
              <button className="btn ghost" onClick={() => setShowDsForm(false)}>取消</button>
              <button className="btn primary" onClick={handleCreateDataset} disabled={creatingDataset}>
                {creatingDataset ? '正在同步表结构…' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── 弹窗：编辑数据集级查询约束（右键菜单触发）── */}
      {showPromptForm && promptFormDs && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 101, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setShowPromptForm(false)}>
          <div style={{ background: 'var(--bg)', borderRadius: 12, padding: 24, width: 560, border: '1px solid var(--hairline)' }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 6px' }}>查询约束 — {promptFormDs.name}</h3>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 14, lineHeight: 1.5 }}>
              这些规则会作为硬性要求进入 SQL / DSL 生成提示词，并影响语义 DSL 编译时的默认 LIMIT。
            </div>
            <div style={{ border: '1px solid var(--hairline)', borderRadius: 8, padding: 12, marginBottom: 14, background: 'var(--surface-2)' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 500, color: 'var(--text)', marginBottom: 10 }}>
                <input
                  type="checkbox"
                  checked={promptFormDs.query_constraints?.enabled ?? true}
                  onChange={e => setPromptFormDs({
                    ...promptFormDs,
                    query_constraints: {
                      ...normalizeQueryConstraints(promptFormDs.query_constraints),
                      enabled: e.target.checked,
                    },
                  })}
                />
                开启默认查询约束
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>默认时间范围（天）</label>
                  <input
                    type="number"
                    min="1"
                    max="3650"
                    value={normalizeQueryConstraints(promptFormDs.query_constraints).default_time_range_days}
                    onChange={e => setPromptFormDs({
                      ...promptFormDs,
                      query_constraints: {
                        ...normalizeQueryConstraints(promptFormDs.query_constraints),
                        default_time_range_days: e.target.value,
                      },
                    })}
                    disabled={!(promptFormDs.query_constraints?.enabled ?? true)}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--surface)', color: 'var(--text)', fontSize: 13, boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>默认返回条数</label>
                  <input
                    type="number"
                    min="1"
                    max="10000"
                    value={normalizeQueryConstraints(promptFormDs.query_constraints).default_limit}
                    onChange={e => setPromptFormDs({
                      ...promptFormDs,
                      query_constraints: {
                        ...normalizeQueryConstraints(promptFormDs.query_constraints),
                        default_limit: e.target.value,
                      },
                    })}
                    disabled={!(promptFormDs.query_constraints?.enabled ?? true)}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--surface)', color: 'var(--text)', fontSize: 13, boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>最大返回条数</label>
                  <input
                    type="number"
                    min="1"
                    max="10000"
                    value={normalizeQueryConstraints(promptFormDs.query_constraints).max_limit}
                    onChange={e => setPromptFormDs({
                      ...promptFormDs,
                      query_constraints: {
                        ...normalizeQueryConstraints(promptFormDs.query_constraints),
                        max_limit: e.target.value,
                      },
                    })}
                    disabled={!(promptFormDs.query_constraints?.enabled ?? true)}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--surface)', color: 'var(--text)', fontSize: 13, boxSizing: 'border-box' }}
                  />
                </div>
              </div>
              <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-3)', lineHeight: 1.5 }}>
                例如用户只问“查询日报”，系统会默认补最近 N 天；用户没说返回几条时会补默认 LIMIT。
              </div>
            </div>
            <FormField
              label="其他 LLM 约束"
              type="textarea"
              rows={6}
              value={promptFormDs.prompt_instructions || ''}
              onChange={v => setPromptFormDs({ ...promptFormDs, prompt_instructions: v })}
              placeholder="例：金额统一保留两位小数；用户说'杨凯'时翻译为 person_name='杨凯'；订单状态枚举：1=待支付, 2=已支付, 4=已退款"
            />
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button className="btn ghost" onClick={() => setShowPromptForm(false)}>取消</button>
              <button
                className="btn primary"
                onClick={async () => {
                  try {
                    await updateDataset(promptFormDs.id, {
                      prompt_instructions: promptFormDs.prompt_instructions || '',
                      query_constraints: normalizeQueryConstraints(promptFormDs.query_constraints),
                    });
                    setShowPromptForm(false);
                    await loadDatasets();
                  } catch (err) {
                    alert('保存失败: ' + (err.message || '未知错误'));
                  }
                }}
              >保存</button>
            </div>
          </div>
        </div>
      )}

      {/* ── 弹窗：语义词典表单 ── */}
      {showTermForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 101, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setShowTermForm(false)}>
          <div style={{ background: 'var(--bg)', borderRadius: 12, padding: 24, width: 560, border: '1px solid var(--hairline)', maxHeight: '90vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 16px' }}>{editingTermId ? '编辑语义词条' : '新建语义词条'}</h3>
            <FormField label="标准名称" value={termForm.name} onChange={v => setTermForm({ ...termForm, name: v })} placeholder="如: gmv" />
            <FormField label="显示名称" value={termForm.display_name} onChange={v => setTermForm({ ...termForm, display_name: v })} placeholder="如: 商品交易总额" />
            <FormField label="词条类型" type="select" value={termForm.term_type} onChange={v => setTermForm({ ...termForm, term_type: v })} options={TERM_TYPE_OPTIONS} />
            <FormField label="状态" type="select" value={termForm.status} onChange={v => setTermForm({ ...termForm, status: v })} options={TERM_STATUS_OPTIONS} />
            <FormField label="定义说明" type="textarea" rows={4} value={termForm.definition} onChange={v => setTermForm({ ...termForm, definition: v })} placeholder="说明业务含义、统计边界或适用场景…" />
            <FormField label="同义词 (逗号分隔)" value={termForm.aliases} onChange={v => setTermForm({ ...termForm, aliases: v })} placeholder="销售额, 成交额, 流水" />
            <FormField label="禁用词 (逗号分隔)" value={termForm.forbidden_aliases} onChange={v => setTermForm({ ...termForm, forbidden_aliases: v })} placeholder="容易混淆或禁止召回的词" />
            <FormField label="示例问法 / 枚举 (逗号分隔)" value={termForm.examples} onChange={v => setTermForm({ ...termForm, examples: v })} placeholder="查看本月GMV, 华东, 已支付" />
            <FormField label="负责人" value={termForm.owner} onChange={v => setTermForm({ ...termForm, owner: v })} placeholder="如: 数据治理负责人" />
            <div style={{ display: 'flex', gap: 10, marginTop: 16, justifyContent: 'flex-end' }}>
              <button className="btn ghost" onClick={() => setShowTermForm(false)}>取消</button>
              <button className="btn primary" onClick={handleSaveTerm} disabled={termBusy}>保存</button>
            </div>
          </div>
        </div>
      )}

      {/* ── 弹窗：指标表单 ── */}
      {showMetricForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 101, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setShowMetricForm(false)}>
          <div style={{ background: 'var(--bg)', borderRadius: 12, padding: 24, width: 520, border: '1px solid var(--hairline)', maxHeight: '90vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 16px' }}>{editingMetricId ? '编辑指标' : '新建指标'}</h3>
            <FormField label="名称" value={metricForm.name} onChange={v => setMetricForm({ ...metricForm, name: v })} placeholder="如: 销售额" />
            <FormField label="显示名" value={metricForm.display_name} onChange={v => setMetricForm({ ...metricForm, display_name: v })} placeholder="如: 销售金额" />
            <FormField label="表达式" value={metricForm.expr} onChange={v => setMetricForm({ ...metricForm, expr: v })} placeholder="如: SUM(order_amount)" />
            <FormField label="主表" type="select" value={metricForm.table_name} onChange={v => setMetricForm({ ...metricForm, table_name: v, time_field: '' })} options={[{ value: '', label: '请选择表' }, ...[...new Set(selectedColumns.map(c => c.table_name))].map(t => ({ value: t, label: t }))]} />
            <FormField label="时间字段" type="select" value={metricForm.time_field} onChange={v => setMetricForm({ ...metricForm, time_field: v })} options={metricForm.table_name ? [{ value: '', label: '请选择时间字段' }, ...selectedColumns.filter(c => c.table_name === metricForm.table_name && (c.ai_semantic_role === 'time_field' || c.semantic_role === 'time_field')).map(c => ({ value: c.column_name, label: `${c.column_name} (${c.effective_desc || c.column_name})` }))] : [{ value: '', label: '请先选择主表' }]} />
            <FormField label="粒度" type="select" value={metricForm.granularity} onChange={v => setMetricForm({ ...metricForm, granularity: v })} options={[{ value: '', label: '无' }, { value: 'daily', label: '日' }, { value: 'weekly', label: '周' }, { value: 'monthly', label: '月' }]} />
            <FormField label="展示格式" value={metricForm.format_str} onChange={v => setMetricForm({ ...metricForm, format_str: v })} placeholder="如: ¥{value:,.0f}" />
            <FormField label="过滤条件 (可选)" value={metricForm.filter_sql} onChange={v => setMetricForm({ ...metricForm, filter_sql: v })} placeholder="如: status != 'cancelled'" />
            <FormField label="同义词 (逗号分隔)" value={metricForm.synonyms} onChange={v => setMetricForm({ ...metricForm, synonyms: v })} placeholder="GMV, 流水, 成交额" />
            <FormField label="描述 (可选)" value={metricForm.description} onChange={v => setMetricForm({ ...metricForm, description: v })} />
            <div style={{ display: 'flex', gap: 10, marginTop: 16, justifyContent: 'flex-end' }}>
              <button className="btn ghost" onClick={() => setShowMetricForm(false)}>取消</button>
              <button className="btn primary" onClick={handleAddMetric}>保存</button>
            </div>
          </div>
        </div>
      )}

      {/* ── 弹窗：维度表单 ── */}
      {showDimForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 101, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setShowDimForm(false)}>
          <div style={{ background: 'var(--bg)', borderRadius: 12, padding: 24, width: 520, border: '1px solid var(--hairline)', maxHeight: '90vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 16px' }}>{editingDimId ? '编辑维度' : '新建维度'}</h3>
            <FormField label="名称" value={dimForm.name} onChange={v => setDimForm({ ...dimForm, name: v })} placeholder="如: 区域" />
            <FormField label="显示名" value={dimForm.display_name} onChange={v => setDimForm({ ...dimForm, display_name: v })} placeholder="如: 销售区域" />
            <FormField label="所属表" type="select" value={dimForm.table_name} onChange={v => setDimForm({ ...dimForm, table_name: v, column_name: '' })} options={[{ value: '', label: '请选择表' }, ...[...new Set(selectedColumns.map(c => c.table_name))].map(t => ({ value: t, label: t }))]} />
            <FormField label="字段名" type="select" value={dimForm.column_name} onChange={v => setDimForm({ ...dimForm, column_name: v })} options={dimForm.table_name ? [{ value: '', label: '请选择字段' }, ...selectedColumns.filter(c => c.table_name === dimForm.table_name).map(c => ({ value: c.column_name, label: `${c.column_name} (${c.effective_desc || c.column_name})` }))] : [{ value: '', label: '请先选择所属表' }]} />
            <FormField label="关联事实表 (可选)" value={dimForm.join_to} onChange={v => setDimForm({ ...dimForm, join_to: v })} placeholder="如: orders" />
            <FormField label="关联键 (可选)" value={dimForm.join_key} onChange={v => setDimForm({ ...dimForm, join_key: v })} placeholder="如: region_code" />
            <FormField label="枚举值 (逗号分隔)" value={dimForm.enum_values} onChange={v => setDimForm({ ...dimForm, enum_values: v })} placeholder="华北,华东,华南" />
            <FormField label="同义词 (逗号分隔)" value={dimForm.synonyms} onChange={v => setDimForm({ ...dimForm, synonyms: v })} placeholder="地区,区" />
            <div style={{ display: 'flex', gap: 10, marginTop: 16, justifyContent: 'flex-end' }}>
              <button className="btn ghost" onClick={() => setShowDimForm(false)}>取消</button>
              <button className="btn primary" onClick={handleAddDim}>保存</button>
            </div>
          </div>
        </div>
      )}

      {/* ── 弹窗：YAML 导入 ── */}
      {showYamlImport && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 101, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setShowYamlImport(false)}>
          <div style={{ background: 'var(--bg)', borderRadius: 12, padding: 24, width: 640, border: '1px solid var(--hairline)', maxHeight: '90vh', display: 'flex', flexDirection: 'column' }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 16px' }}>导入 YAML</h3>
            <textarea
              value={yamlText}
              onChange={e => setYamlText(e.target.value)}
              placeholder="粘贴 YAML 配置…"
              style={{ flex: 1, minHeight: 300, padding: 12, borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--surface)', color: 'var(--text)', fontSize: 13, fontFamily: 'var(--font-mono)', resize: 'vertical', outline: 'none' }}
            />
            <div style={{ display: 'flex', gap: 10, marginTop: 16, justifyContent: 'flex-end' }}>
              <button className="btn ghost" onClick={() => setShowYamlImport(false)}>取消</button>
              <button className="btn primary" onClick={handleImportYaml}>导入</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DataPreviewPanel({ tables, previewTableId, previewTable, previewData, loading, onSelectTable, onRefresh }) {
  const columns = previewData?.columns || [];
  const rows = previewData?.rows || [];
  const selectedValue = previewTableId || previewTable?.id || '';
  const columnCount = columns.length || previewTable?.column_count || 0;
  const tableLabel = previewTable
    ? [previewTable.schema_name, previewTable.table_name].filter(Boolean).join('.')
    : '未选择数据表';
  const hasRows = rows.length > 0;

  return (
    <section className="data-preview-card">
      <div className="data-preview-head">
        <div className="data-preview-title">
          <span className="data-preview-icon"><Icon name="table" /></span>
          <div>
            <h3>数据预览</h3>
            <p>{tableLabel}</p>
          </div>
        </div>
        <div className="data-preview-actions">
          <div className="data-preview-stats" aria-label="预览摘要">
            <span><strong>{columnCount}</strong> 字段</span>
            <span><strong>{rows.length}</strong> 样例行</span>
          </div>
          <select
            className="data-preview-select"
            value={selectedValue}
            onChange={e => onSelectTable(Number(e.target.value))}
          >
            {tables.map(t => (
              <option key={t.id} value={t.id}>
                {[t.schema_name, t.table_name].filter(Boolean).join('.')}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="icon-btn data-preview-refresh"
            title="刷新预览"
            onClick={onRefresh}
            disabled={!selectedValue || loading}
          >
            <Icon name="refresh" />
          </button>
        </div>
      </div>

      {loading && !hasRows ? (
        <div className="data-preview-empty">
          <Icon name="refresh" />
          <span>正在读取样例数据…</span>
        </div>
      ) : hasRows ? (
        <div className="data-preview-table-wrap">
          {loading && <div className="data-preview-loading">刷新中…</div>}
          <table className="data-preview-table">
            <thead>
              <tr>
                {columns.map((c, idx) => (
                  <th key={`${c}-${idx}`} title={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIdx) => (
                <tr key={rowIdx}>
                  {columns.map((c, colIdx) => (
                    <td key={`${c}-${colIdx}`}>
                      <PreviewCellValue value={row[c]} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="data-preview-empty">
          <Icon name="inbox" />
          <span>暂无样例数据</span>
        </div>
      )}
    </section>
  );
}

function PreviewCellValue({ value }) {
  if (value === null || value === undefined) {
    return <span className="data-preview-null">NULL</span>;
  }

  let text;
  if (typeof value === 'object') {
    try {
      text = JSON.stringify(value);
    } catch {
      text = String(value);
    }
  } else if (typeof value === 'boolean') {
    text = value ? 'true' : 'false';
  } else {
    text = String(value);
  }

  return <span className="data-preview-value" title={text}>{text}</span>;
}

function CapabilityEmptyPane({ tab }) {
  return (
    <div style={{
      minHeight: 360,
      border: '1px dashed var(--hairline-strong)',
      borderRadius: 10,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      textAlign: 'center',
      color: 'var(--text-3)',
      background: 'var(--surface)',
      padding: 32,
    }}>
      <div>
        <Icon name="inbox" style={{ width: 28, height: 28, opacity: 0.45, marginBottom: 10 }} />
        <div style={{ fontSize: 14, color: 'var(--text-2)', marginBottom: 4 }}>{tab?.label || '能力'} 暂未配置</div>
        <div style={{ fontSize: 12 }}>入口已保留，后续可在不重构数据集页面的前提下继续扩展。</div>
      </div>
    </div>
  );
}

function StatCard({ label, value, hint }) {
  return (
    <div className="semantic-stat-card">
      <div>{label}</div>
      <strong>{value}</strong>
      {hint && <span>{hint}</span>}
    </div>
  );
}

function GuidedEmpty({ icon, title, desc, actionLabel, onAction }) {
  return (
    <div className="guided-empty">
      <div className="guided-empty-icon"><Icon name={icon} /></div>
      <h3>{title}</h3>
      <p>{desc}</p>
      {actionLabel && onAction && (
        <button className="btn primary" onClick={onAction}><Icon name="plus" />{actionLabel}</button>
      )}
    </div>
  );
}

function CandidateRail({ title, empty, items, onPick, icon, actionLabel }) {
  return (
    <aside className="candidate-rail">
      <div className="candidate-rail-head">
        <span>{title}</span>
        <strong>{items.length}</strong>
      </div>
      {items.length === 0 ? (
        <div className="candidate-empty">{empty}</div>
      ) : (
        <div className="candidate-list">
          {items.map(col => (
            <button key={col.id} className="candidate-item" onClick={() => onPick(col)}>
              <span className="candidate-icon"><Icon name={icon} /></span>
              <span className="candidate-copy">
                <strong>{col.effective_desc || col.business_desc || col.column_name}</strong>
                <small>{col.table_name}.{col.column_name}</small>
              </span>
              <span className="candidate-action">{actionLabel}</span>
            </button>
          ))}
        </div>
      )}
    </aside>
  );
}

// ── FormField — 通用表单字段 ────────────────────────────
function FormField({ label, type = 'text', value, onChange, options = [], placeholder = '', rows = 5 }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 4 }}>{label}</label>
      {type === 'select' ? (
        <CustomSelect value={value} onChange={onChange} options={options} />
      ) : type === 'textarea' ? (
        <textarea
          value={value ?? ''}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          rows={rows}
          style={{
            width: '100%', padding: '8px 10px', borderRadius: 6,
            border: '1px solid var(--hairline)', background: 'var(--surface)',
            color: 'var(--text)', fontSize: 12, lineHeight: 1.5,
            resize: 'vertical', fontFamily: 'inherit', boxSizing: 'border-box',
          }}
        />
      ) : (
        <input type={type} value={value ?? ''} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--surface)', color: 'var(--text)', fontSize: 13 }} />
      )}
    </div>
  );
}

function CustomSelect({ value, onChange, options = [] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const safeValue = value === undefined || value === null ? '' : String(value);
  const selected = options.find(o => {
    const v = typeof o === 'string' ? o : o.value;
    return String(v) === safeValue;
  });
  const selectedLabel = typeof selected === 'string' ? selected : (selected?.label ?? '请选择');

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        style={{
          width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)',
          background: 'var(--surface)', color: 'var(--text)', fontSize: 13, cursor: 'pointer',
          textAlign: 'left', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}
      >
        <span>{selectedLabel}</span>
        <Icon name="chev_down" style={{ width: 12, height: 12, flexShrink: 0 }} />
      </button>
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0,
          background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 6,
          boxShadow: '0 4px 16px rgba(0,0,0,0.12)', zIndex: 200, maxHeight: 240, overflow: 'auto',
        }}>
          {options.map((o, idx) => {
            const opt = typeof o === 'string' ? { value: o, label: o } : o;
            const isActive = String(opt.value) === safeValue;
            return (
              <div
                key={opt.value ?? idx}
                onClick={() => { onChange(opt.value ?? ''); setOpen(false); }}
                style={{
                  padding: '8px 10px', fontSize: 13, cursor: 'pointer',
                  background: isActive ? 'var(--bg-2)' : 'transparent',
                  color: isActive ? 'var(--text)' : 'var(--text-2)',
                }}
              >
                {opt.label ?? opt.value}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export { DatasetsScreen };
