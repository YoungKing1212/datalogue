import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Icon } from './icons';
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
  syncDatasourceTables,
  listSourceTables,
  getSourceTableColumns,
  annotateDatasetColumns,
  importDatasetYaml,
  exportDatasetYaml,
  previewTable,
  streamChat,
  selectTablesForDataset,
  deselectTableFromDataset,
  listSelectedTables,
  listSelectedColumns,
  updateSourceColumn,
} from '../api/client';

// ── DatasetsScreen — 语义层配置（三栏式）────────────────────

// 右键菜单项共享样式
const ctxMenuItemStyle = {
  display: 'flex', alignItems: 'center', gap: 8,
  width: '100%', padding: '6px 10px', fontSize: 12,
  background: 'transparent', border: 'none', borderRadius: 4,
  color: 'var(--text)', cursor: 'pointer', textAlign: 'left',
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
  const [syncing, setSyncing] = useState(false);
  const [annotating, setAnnotating] = useState(false);
  const [tableSearch, setTableSearch] = useState('');

  // 查看中的表（只读预览其字段，不加入数据集；与勾选状态相互独立）
  const [inspectingTableId, setInspectingTableId] = useState(null);
  const [inspectColumns, setInspectColumns] = useState([]);
  const [inspectLoading, setInspectLoading] = useState(false);
  const inspectSeqRef = useRef(0); // 防止旧请求覆盖新结果

  // ── 字段编辑状态 ──
  const [editingColumnId, setEditingColumnId] = useState(null);
  const [columnEditForm, setColumnEditForm] = useState({ user_description: '', user_semantic_role: '' });

  const filteredTables = useMemo(() => {
    const q = tableSearch.trim().toLowerCase();
    if (!q) return allSourceTables;
    return allSourceTables.filter(t => t.table_name.toLowerCase().includes(q));
  }, [allSourceTables, tableSearch]);

  // ── 指标/维度数据 ──
  const [metrics, setMetrics] = useState([]);
  const [dimensions, setDimensions] = useState([]);

  // ── 表单状态 ──
  const [showMetricForm, setShowMetricForm] = useState(false);
  const [showDimForm, setShowDimForm] = useState(false);
  const [showDsForm, setShowDsForm] = useState(false);
  const [showYamlImport, setShowYamlImport] = useState(false);
  const [editingMetricId, setEditingMetricId] = useState(null);
  const [editingDimId, setEditingDimId] = useState(null);

  const [metricForm, setMetricForm] = useState({
    name: '', display_name: '', expr: '', table_name: '', time_field: '',
    granularity: '', format_str: '', filter_sql: '', synonyms: '', description: ''
  });
  const [dimForm, setDimForm] = useState({
    name: '', display_name: '', column_name: '', table_name: '',
    join_to: '', join_key: '', enum_values: '', synonyms: ''
  });
  const [dsForm, setDsForm] = useState({ name: '', datasource_id: '', description: '', prompt_instructions: '' });
  const [showPromptForm, setShowPromptForm] = useState(false);
  const [promptFormDs, setPromptFormDs] = useState(null);
  const [datasources, setDatasources] = useState([]);
  const [yamlText, setYamlText] = useState('');

  // ── 数据预览 ──
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // ── 试问验证 ──
  const [testQuestion, setTestQuestion] = useState('');
  const [testStreaming, setTestStreaming] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testSql, setTestSql] = useState('');
  const testAbortRef = useRef(null);

  // ── 数据集列表：右键菜单 + 二次确认删除 ──
  const [ctxMenu, setCtxMenu] = useState(null); // {x, y, ds} | null
  const ctxMenuRef = useRef(null); // 菜单 DOM 引用，用于判断点击是否在菜单内
  const [confirmDelete, setConfirmDelete] = useState(null); // 待删除的 dataset | null
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');

  // ── 初始化 ──
  useEffect(() => { loadDatasets(); loadDatasources(); }, []);

  useEffect(() => {
    if (activeDsId) {
      loadDsMeta(activeDsId);
      loadAllSourceTables(activeDsId);
      loadSelectedTables(activeDsId);
    }
  }, [activeDsId]);

  useEffect(() => {
    if (previewTableId) {
      loadPreview(previewTableId);
    }
  }, [previewTableId]);

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
  const loadDatasets = () => {
    setLoading(true);
    listDatasets().then(setDatasets).catch(console.error).finally(() => setLoading(false));
  };

  const loadDatasources = () => {
    listDatasources().then(setDatasources).catch(console.error);
  };

  const loadDsMeta = async (dsId) => {
    try {
      const [ms, ds] = await Promise.all([listDatasetMetrics(dsId), listDatasetDimensions(dsId)]);
      setMetrics(ms);
      setDimensions(ds);
    } catch (err) { console.error(err); }
  };

  // 加载数据源所有表（目录）
  const loadAllSourceTables = async (dsId) => {
    const ds = datasets.find(d => d.id === dsId);
    if (!ds) return;
    try {
      const tables = await listSourceTables(ds.datasource_id);
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
      setSelectedTableIds(new Set(selectedTables.map(t => t.id)));
      setSelectedColumns(cols);
      if (selectedTables.length > 0 && !previewTableId) {
        setPreviewTableId(selectedTables[0].id);
      }
    } catch (err) {
      console.error(err);
      setSelectedTableIds(new Set());
      setSelectedColumns([]);
    }
  };

  const loadPreview = async (tableId) => {
    const table = allSourceTables.find(t => t.id === tableId);
    if (!table) return;
    const ds = datasets.find(d => d.id === activeDsId);
    if (!ds) return;
    setPreviewLoading(true);
    try {
      const data = await previewTable(ds.datasource_id, table.schema_name, table.table_name, 5);
      setPreviewData(data);
    } catch (err) {
      console.error(err);
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
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
        const cols = await listSelectedColumns(activeDsId);
        setSelectedColumns(cols);
      }
    } catch (err) {
      console.error('保存字段标注失败:', err);
      alert('保存失败: ' + (err.message || '未知错误'));
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
      await syncDatasourceTables(ds.datasource_id);
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
        setPreviewTableId(sourceTableId);
      } else {
        await deselectTableFromDataset(activeDsId, sourceTableId);
      }
      await loadSelectedTables(activeDsId);
    } catch (err) {
      alert('操作失败: ' + (err.message || '未知错误'));
    }
  };

  // ── 查看表信息（不加入数据集）──
  const handleInspectTable = (sourceTableId) => {
    if (!sourceTableId) return;
    // 点击同一行再次点 → 收起
    if (inspectingTableId === sourceTableId) {
      setInspectingTableId(null);
      return;
    }
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
    try {
      await createDataset({
        name: dsForm.name,
        datasource_id: Number(dsForm.datasource_id),
        description: dsForm.description || undefined,
        prompt_instructions: dsForm.prompt_instructions || undefined,
        tables_json: {},
        status: 'draft',
      });
      setShowDsForm(false);
      setDsForm({ name: '', datasource_id: '', description: '', prompt_instructions: '' });
      loadDatasets();
    } catch (err) { alert('创建失败: ' + (err.message || '未知错误')); }
  };

  // ── 数据集右键菜单 ──
  const openCtxMenu = (e, ds) => {
    e.preventDefault();
    e.stopPropagation();
    // 防止菜单超出右/下边界：菜单大约宽 160、高 ~88
    const menuW = 160, menuH = 88;
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
      } else {
        await createMetric(activeDsId, payload);
      }
      setShowMetricForm(false);
      setEditingMetricId(null);
      setMetricForm({ name: '', display_name: '', expr: '', table_name: '', time_field: '', granularity: '', format_str: '', filter_sql: '', synonyms: '', description: '' });
      loadDsMeta(activeDsId);
    } catch (err) { alert('保存失败: ' + (err.message || '未知错误')); }
  };

  const handleEditMetric = (m) => {
    setEditingMetricId(m.id);
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
      } else {
        await createDimension(activeDsId, payload);
      }
      setShowDimForm(false);
      setEditingDimId(null);
      setDimForm({ name: '', display_name: '', column_name: '', table_name: '', join_to: '', join_key: '', enum_values: '', synonyms: '' });
      loadDsMeta(activeDsId);
    } catch (err) { alert('保存失败: ' + (err.message || '未知错误')); }
  };

  const handleEditDim = (d) => {
    setEditingDimId(d.id);
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

  // ── 从字段快速创建指标/维度 ──
  const handleCreateMetricFromColumn = (col) => {
    const timeCol = selectedColumns.find(c => c.semantic_role === 'time_field');
    setEditingMetricId(null);
    setMetricForm({
      name: col.business_desc || col.column_name,
      display_name: col.business_desc || col.column_name,
      expr: col.default_agg ? `${col.default_agg}(${col.column_name})` : `SUM(${col.column_name})`,
      table_name: col.table_name,
      time_field: timeCol ? timeCol.column_name : '',
      granularity: 'daily',
      format_str: '',
      filter_sql: '',
      synonyms: '',
      description: '',
    });
    setShowMetricForm(true);
  };

  const handleCreateDimFromColumn = (col) => {
    setEditingDimId(null);
    setDimForm({
      name: col.business_desc || col.column_name,
      display_name: col.business_desc || col.column_name,
      column_name: col.column_name,
      table_name: col.table_name,
      join_to: '',
      join_key: '',
      enum_values: '',
      synonyms: '',
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
    if (!testQuestion.trim() || !activeDsId) return;
    setTestStreaming(true);
    setTestResult(null);
    setTestSql('');

    const ctrl = streamChat(
      { question: testQuestion.trim(), dataset_id: activeDsId },
      {
        onToken: (tok) => {
          setTestResult(prev => (prev || '') + tok);
        },
        onEvent: (ev) => {
          if (ev.step === 'dsl_compiler' && ev.status === 'done' && ev.output?.sql) {
            setTestSql(ev.output.sql);
          }
        },
        onDone: (data) => {
          setTestStreaming(false);
          if (data.sql) setTestSql(data.sql);
          if (data.answer) setTestResult(data.answer);
        },
        onError: (err) => {
          setTestStreaming(false);
          setTestResult('验证失败: ' + err.message);
        },
      }
    );
    testAbortRef.current = ctrl;
  };

  // ── 当前数据集 ──
  const activeDs = datasets.find(d => d.id === activeDsId) || datasets[0];
  const currentDsId = activeDsId || activeDs?.id;

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
      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 20 }}>
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
                onClick={() => { setActiveDsId(d.id); setPreviewTableId(null); setSelectedColumns([]); setPreviewData(null); }}
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
              onClick={() => { setPromptFormDs({ ...ctxMenu.ds }); setShowPromptForm(true); setCtxMenu(null); }}
              style={ctxMenuItemStyle}
            >
              <Icon name="bookmark" style={{ width: 14, height: 14, color: 'var(--text-3)' }} />
              <span>编辑约束</span>
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

        {/* 右侧：三栏布局 */}
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
                  try { await selectTablesForDataset(activeDsId, ids); await loadSelectedTables(activeDsId); }
                  catch (err) { alert('全选失败: ' + (err.message || '未知错误')); }
                }
              }}>全选</button>
              <button className="btn ghost" style={{ height: 24, fontSize: 10, padding: '0 8px', flex: 1 }} onClick={async () => {
                const ids = filteredTables.map(t => t.id).filter(id => selectedTableIds.has(id));
                for (const id of ids) {
                  try { await deselectTableFromDataset(activeDsId, id); } catch (e) { console.error(e); }
                }
                await loadSelectedTables(activeDsId);
              }}>取消全选</button>
            </div>
            {/* 表列表 */}
            <div style={{ maxHeight: 360, overflow: 'auto' }}>
              {filteredTables.map(t => {
                const checked = selectedTableIds.has(t.id);
                const inspecting = inspectingTableId === t.id;
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
                  ? 'var(--surface-2)'
                  : inspecting
                  ? 'var(--accent-soft)'
                  : 'transparent';
                const rowBorder = inspecting
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
                        color: checked ? 'var(--text)' : inspecting ? 'var(--accent)' : 'var(--text-2)',
                        fontWeight: inspecting ? 500 : 400,
                      }}
                    >
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%' }}>
                        <Icon name={inspecting ? 'eye' : 'table'} style={{ width: 14, height: 14, flexShrink: 0 }} />
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
                      <div style={{ border: '1px solid var(--hairline)', borderRadius: 8, overflow: 'hidden' }}>
                        <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
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
                    已选表字段 {selectedColumns.length > 0 && `(${selectedColumns.length})`}
                  </div>
                  {selectedColumns.length === 0 ? (
                    <div style={{ padding: '32px 8px', fontSize: 12, color: 'var(--text-3)', textAlign: 'center' }}>
                      <Icon name="inbox" style={{ width: 24, height: 24, marginBottom: 8, opacity: 0.4 }} />
                      <div>从左栏勾选表加入数据集</div>
                      <div style={{ marginTop: 6, fontSize: 11, opacity: 0.85 }}>
                        点击表名仅查看表信息，不会加入数据集
                      </div>
                    </div>
                  ) : (
                    <div style={{ border: '1px solid var(--hairline)', borderRadius: 8, overflow: 'hidden' }}>
                <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
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
                    {selectedColumns.map(col => {
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
              <div style={{ marginTop: 16, border: '1px solid var(--hairline)', borderRadius: 8, overflow: 'hidden' }}>
                <div style={{ padding: '8px 12px', fontSize: 11, color: 'var(--text-3)', background: 'var(--bg-2)', borderBottom: '1px solid var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>数据预览</span>
                    <select
                      value={previewTableId || ''}
                      onChange={e => setPreviewTableId(Number(e.target.value))}
                      style={{ padding: '2px 6px', borderRadius: 4, border: '1px solid var(--hairline)', background: 'var(--surface)', color: 'var(--text)', fontSize: 11 }}
                    >
                      {allSourceTables.filter(t => selectedTableIds.has(t.id)).map(t => (
                        <option key={t.id} value={t.id}>{t.table_name}</option>
                      ))}
                    </select>
                  </div>
                  {previewLoading && <span style={{ fontSize: 10 }}>加载中…</span>}
                </div>
                {previewData && previewData.rows?.length > 0 ? (
                  <div style={{ overflow: 'auto', maxHeight: 200 }}>
                    <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ background: 'var(--bg-2)' }}>
                          {previewData.columns.map(c => (
                            <th key={c} style={{ padding: '6px 10px', textAlign: 'left', fontWeight: 500, color: 'var(--text-3)', borderBottom: '1px solid var(--hairline)', whiteSpace: 'nowrap' }}>{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {previewData.rows.map((row, i) => (
                          <tr key={i}>
                            {previewData.columns.map(c => (
                              <td key={c} style={{ padding: '6px 10px', borderBottom: '1px solid var(--hairline)', color: 'var(--text-2)', whiteSpace: 'nowrap', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {row[c] ?? <span style={{ color: 'var(--text-4)' }}>NULL</span>}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div style={{ padding: 16, fontSize: 12, color: 'var(--text-3)' }}>暂无数据</div>
                )}
              </div>
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
      </div>

      {/* ── 底部：试问验证 ── */}
      {activeDsId && (
        <div style={{ marginTop: 24, border: '1px solid var(--hairline)', borderRadius: 10, padding: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Icon name="beaker" style={{ width: 14, height: 14, color: 'var(--accent)' }} />
            语义层验证
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input
              placeholder="例如：上周各区域销售额"
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
          {testSql && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>生成的 SQL</div>
              <pre style={{ background: 'var(--bg-2)', padding: 10, borderRadius: 6, fontSize: 12, overflow: 'auto', margin: 0, color: 'var(--accent)' }}>{testSql}</pre>
            </div>
          )}
          {testResult && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>回答</div>
              <div style={{ background: 'var(--bg-2)', padding: 10, borderRadius: 6, fontSize: 13, lineHeight: 1.6 }}>{testResult}</div>
            </div>
          )}
        </div>
      )}

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
            <FormField label="数据源" type="select" value={dsForm.datasource_id} onChange={v => setDsForm({ ...dsForm, datasource_id: v })} options={[{ value: '', label: '请选择数据源' }, ...datasources.map(d => ({ value: String(d.id), label: d.name }))]} />
            <FormField label="描述 (可选)" value={dsForm.description} onChange={v => setDsForm({ ...dsForm, description: v })} placeholder="数据集用途说明…" />
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
              <button className="btn primary" onClick={handleCreateDataset}>创建</button>
            </div>
          </div>
        </div>
      )}

      {/* ── 弹窗：编辑数据集级 LLM 约束（右键菜单触发）── */}
      {showPromptForm && promptFormDs && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 101, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setShowPromptForm(false)}>
          <div style={{ background: 'var(--bg)', borderRadius: 12, padding: 24, width: 560, border: '1px solid var(--hairline)' }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 6px' }}>编辑 LLM 约束 — {promptFormDs.name}</h3>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 14, lineHeight: 1.5 }}>
              问数时会作为「硬性要求」注入到 LLM 提示词中，覆盖 DSL 生成 / SQL 审计 / 报告生成全链路。
            </div>
            <FormField
              label="数据集级 LLM 约束"
              type="textarea"
              rows={10}
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
                    await updateDataset(promptFormDs.id, { prompt_instructions: promptFormDs.prompt_instructions || '' });
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
