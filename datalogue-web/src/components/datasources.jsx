import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Icon } from './icons';
import {
  listDatasources,
  listDatasourceCapabilities,
  createDatasource,
  updateDatasource,
  deleteDatasource,
  testDatasource,
  getDatasourceSchemas,
  getDatasourceSchema,
  syncDatasourceTables,
} from '../api/client';

// DatasourcesScreen — 数据源管理完整功能

export const DB_ICON = {
  postgres: '🐘',
  mysql: '🐬',
  doris: '🌊',
  clickhouse: '🪶',
  bigquery: '☁️',
  oracle: '🔶',
  sqlite: '📄',
  hive: '⬢',
  sqlserver: '▣',
  trino: '△',
  presto: '◇',
};

export function datasourceDisplayInfo(datasource = {}, capability = null) {
  const dbType = datasource.db_type || capability?.db_type || '';
  const dialect = datasource.dialect || capability?.dialect || dbType || '—';
  const driver = datasource.driver || capability?.driver || '';
  const defaultPort = capability?.default_port;
  const productLabel = dbType === 'doris'
    ? 'Doris（MySQL 协议）'
    : capability?.label || dbType?.toUpperCase?.() || '—';
  const dialectLabel = dbType === 'doris' && dialect === 'mysql'
    ? 'mysql（Doris 第一阶段执行方言）'
    : dialect;
  const portLabel = datasource.port || defaultPort || '—';
  return {
    icon: DB_ICON[dbType] || '📊',
    dbType,
    productLabel,
    dialectLabel,
    driverLabel: driver || '内置',
    portLabel,
  };
}

function DatasourcesScreen() {
  const [datasources, setDatasources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedDs, setSelectedDs] = useState(null);
  const [dsTab, setDsTab] = useState('overview');
  const [showDrawer, setShowDrawer] = useState(false);
  const [editingDs, setEditingDs] = useState(null);
  const [testingId, setTestingId] = useState(null);
  const [testResult, setTestResult] = useState(null);
  const [schemas, setSchemas] = useState([]);
  const [capabilities, setCapabilities] = useState([]);
  const [selectedSchema, setSelectedSchema] = useState(null);
  const [schema, setSchema] = useState([]);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [expandedTable, setExpandedTable] = useState(null); // 展开的行索引
  const [tableSearch, setTableSearch] = useState('');
  const [tablePage, setTablePage] = useState(1);
  const [syncResult, setSyncResult] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const schemaRequestSeqRef = useRef(0);
  const TABLE_PAGE_SIZE = 10;

  // 新建/编辑表单

  // 新建/编辑表单
  const defaultForm = useCallback((dbType = 'postgres') => {
    const cap = capabilities.find(c => c.db_type === dbType);
    return {
      name: '',
      db_type: dbType,
      host: '',
      port: cap?.default_port ?? 5432,
      database_name: '',
      username: '',
      password: '',
      dialect: cap?.dialect || dbType,
      driver: cap?.driver || '',
      default_schema: cap?.default_schema || '',
      connection_options: {},
      connect_timeout_seconds: 10,
      query_timeout_seconds: 30,
    };
  }, [capabilities]);

  const [form, setForm] = useState(defaultForm());

  useEffect(() => {
    loadDatasources();
    listDatasourceCapabilities().then(setCapabilities).catch(err => console.error('加载数据源能力失败:', err));
  }, []);

  const loadDatasources = useCallback(() => {
    setLoading(true);
    listDatasources()
      .then(data => {
        setDatasources(data);
        if (selectedDs && !data.find(d => d.id === selectedDs.id)) {
          setSelectedDs(null);
        }
      })
      .catch(err => console.error('加载数据源失败:', err))
      .finally(() => setLoading(false));
  }, [selectedDs]);

  const handleSelectDs = async (ds) => {
    const seq = ++schemaRequestSeqRef.current;
    setSelectedDs(ds);
    setDsTab('overview');
    setSchemas([]);
    setSelectedSchema(null);
    setSchema([]);
    setTestResult(null);
    setSyncResult(null);
    setTableSearch('');
    setTablePage(1);
    setExpandedTable(null);
    setSchemaLoading(true);
    try {
      const res = await getDatasourceSchemas(ds.id);
      if (seq !== schemaRequestSeqRef.current) return;
      const schemaList = res?.schemas || [];
      setSchemas(schemaList);
      // 如果有 schema，默认选中第一个并加载其表
      if (schemaList.length > 0) {
        const firstSchema = schemaList[0];
        setSelectedSchema(firstSchema);
        const tableRes = await getDatasourceSchema(ds.id, firstSchema);
        if (seq !== schemaRequestSeqRef.current) return;
        setSchema(tableRes?.tables || []);
      }
    } catch (err) {
      console.error('加载 Schema 失败:', err);
    } finally {
      if (seq === schemaRequestSeqRef.current) setSchemaLoading(false);
    }
  };

  const handleSelectSchema = async (schemaName) => {
    if (!selectedDs || schemaName === selectedSchema) return;
    const seq = ++schemaRequestSeqRef.current;
    const datasourceId = selectedDs.id;
    setSelectedSchema(schemaName);
    setSchema([]);
    setSchemaLoading(true);
    setTableSearch('');
    setTablePage(1);
    setExpandedTable(null);
    try {
      const res = await getDatasourceSchema(datasourceId, schemaName);
      if (seq !== schemaRequestSeqRef.current) return;
      setSchema(res?.tables || []);
    } catch (err) {
      console.error('加载表失败:', err);
    } finally {
      if (seq === schemaRequestSeqRef.current) setSchemaLoading(false);
    }
  };

  const handleTest = async (id) => {
    setTestingId(id);
    setTestResult(null);
    try {
      const res = await testDatasource(id);
      const diagnostic = res.diagnostic || res;
      setTestResult({
        ok: !!res.ok,
        msg: res.ok
          ? (res.message || `连接成功! 版本: ${res.version || '未知'}`)
          : `${diagnostic.code || 'CONNECTION_FAILED'}：${diagnostic.message || res.message || '连接失败'}${diagnostic.suggested_action ? `。建议：${diagnostic.suggested_action}` : ''}`,
      });
      const nextStatus = res.ok ? 'connected' : 'disconnected';
      setDatasources(prev => prev.map(ds => ds.id === id ? { ...ds, status: nextStatus, last_test_result: res, last_error_code: diagnostic.code, last_error_message: diagnostic.message } : ds));
      if (selectedDs?.id === id) setSelectedDs(prev => prev ? { ...prev, status: nextStatus, last_test_result: res, last_error_code: diagnostic.code, last_error_message: diagnostic.message } : prev);
    } catch (err) {
      setTestResult({ ok: false, msg: err.message || '连接失败' });
    } finally {
      setTestingId(null);
    }
  };

  const handleOpenCreate = () => {
    setEditingDs(null);
    setForm(defaultForm());
    setShowDrawer(true);
  };

  const handleOpenEdit = (ds) => {
    setEditingDs(ds);
    setForm({
      name: ds.name,
      db_type: ds.db_type,
      host: ds.host,
      port: ds.port,
      database_name: ds.database_name,
      username: ds.username,
      password: '',
      dialect: ds.dialect || ds.db_type,
      driver: ds.driver || '',
      default_schema: ds.default_schema || '',
      connection_options: ds.connection_options || {},
      connect_timeout_seconds: ds.connect_timeout_seconds || 10,
      query_timeout_seconds: ds.query_timeout_seconds || 30,
    });
    setShowDrawer(true);
  };

  const handleDbTypeChange = (dbType) => {
    const cap = capabilities.find(c => c.db_type === dbType);
    setForm({
      ...form,
      db_type: dbType,
      port: cap?.default_port ?? form.port,
      dialect: cap?.dialect || dbType,
      driver: cap?.driver || '',
      default_schema: cap?.default_schema || '',
      connection_options: {},
    });
  };

  const handleSave = async () => {
    if (!form.name || !form.host || !form.database_name) {
      alert('请填写名称、主机和数据库名');
      return;
    }
    try {
      let savedDatasource = null;
      if (editingDs) {
        const data = { ...form };
        if (!data.password) delete data.password;
        savedDatasource = await updateDatasource(editingDs.id, data);
      } else {
        savedDatasource = await createDatasource(form);
      }
      setShowDrawer(false);
      setEditingDs(null);
      if (savedDatasource) {
        setDatasources((prev) => {
          const exists = prev.some((item) => item.id === savedDatasource.id);
          return exists
            ? prev.map((item) => item.id === savedDatasource.id ? savedDatasource : item)
            : [savedDatasource, ...prev];
        });
      }
      if (editingDs && selectedDs?.id === editingDs.id) {
        // 保存响应是真相源，避免详情继续显示请求前缓存值。
        setSelectedDs(savedDatasource || { ...selectedDs, ...form, password: undefined });
      }
      loadDatasources();
    } catch (err) {
      alert((editingDs ? '更新' : '创建') + '失败: ' + err.message);
    }
  };

  const handleDelete = async (ds) => {
    if (!confirm(`确定删除数据源「${ds.name}」？删除后所有关联数据集和指标将无法使用。`)) return;
    setDeletingId(ds.id);
    try {
      await deleteDatasource(ds.id);
      if (selectedDs?.id === ds.id) setSelectedDs(null);
      loadDatasources();
    } catch (err) {
      alert('删除失败: ' + err.message);
    } finally {
      setDeletingId(null);
    }
  };

  const handleSyncTables = async () => {
    if (!selectedDs) return;
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await syncDatasourceTables(selectedDs.id, selectedSchema);
      setSyncResult(res);
      await handleSelectDs(selectedDs);
    } catch (err) {
      setSyncResult({ ok: false, message: err.message || '同步失败' });
    } finally {
      setSyncing(false);
    }
  };

  const totalTables = schema.length;
  const statusColor = (s) => {
    if (s === 'connected') return 'var(--pos)';
    if (s === 'syncing') return 'var(--warn)';
    return 'var(--neg)';
  };
  const filteredTables = tableSearch ? schema.filter(t => t.name.toLowerCase().includes(tableSearch.toLowerCase())) : schema;
  const totalPages = Math.max(1, Math.ceil(filteredTables.length / TABLE_PAGE_SIZE));
  const paginatedTables = filteredTables.slice((tablePage - 1) * TABLE_PAGE_SIZE, tablePage * TABLE_PAGE_SIZE);

  const dbTypeOptions = capabilities.length
    ? capabilities.map(c => ({ value: c.db_type, label: `${c.label}${c.stable ? '' : '（可选驱动）'}` }))
    : ['postgres', 'mysql', 'sqlite'].map(v => ({ value: v, label: v }));
  const activeCapability = capabilities.find(c => c.db_type === form.db_type);
  const selectedCapability = capabilities.find(c => c.db_type === selectedDs?.db_type);
  const selectedDisplay = selectedDs ? datasourceDisplayInfo(selectedDs, selectedCapability) : null;
  const activeDisplay = datasourceDisplayInfo(form, activeCapability);
  const optionValue = (key) => form.connection_options?.[key] || '';
  const setOptionValue = (key, value) => {
    setForm({
      ...form,
      connection_options: { ...(form.connection_options || {}), [key]: value },
    });
  };
  const driverStatusLabel = (status) => {
    if (status === 'installed') return '驱动已安装';
    if (status === 'builtin') return '内置驱动';
    if (status === 'missing') return '驱动未安装';
    return '驱动未知';
  };
  const driverStatusColor = (status) => {
    if (status === 'installed' || status === 'builtin') return 'var(--pos)';
    if (status === 'missing') return 'var(--warn)';
    return 'var(--text-3)';
  };

  return (
    <div className="ds-wrap" style={{padding: 24}}>
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24}}>
        <div>
          <h1 style={{margin: '0 0 6px', fontSize: 22, fontWeight: 500}}>数据源管理</h1>
          <p style={{color: 'var(--text-3)', fontSize: 13, margin: 0}}>配置数据库连接，自动扫描 DDL，同步 Schema 到语义层</p>
        </div>
        <button className="btn primary" onClick={handleOpenCreate}>
          <Icon name="plus" /> 新建数据源
        </button>
      </div>

      {/* KPI Strip */}
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24}}>
        {[
          { label: '已连接', val: datasources.filter(d => d.status === 'connected').length, unit: '个' },
          { label: '总表数', val: totalTables, unit: '张' },
          { label: '数据源数', val: datasources.length, unit: '个' },
          { label: 'P95 延迟', val: '—', unit: 'ms' },
        ].map(s => (
          <div key={s.label} style={{padding: 14, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 8}}>
            <div style={{fontSize: 12, color: 'var(--text-3)', marginBottom: 4}}>{s.label}</div>
            <div style={{fontSize: 24, fontWeight: 600, fontFamily: 'var(--font-mono)'}}>{s.val}<span style={{fontSize: 12, color: 'var(--text-3)'}}>{s.unit}</span></div>
          </div>
        ))}
      </div>

      <div style={{display: 'flex', gap: 20, alignItems: 'flex-start'}}>
        {/* 左侧: 数据源列表 */}
        <div style={{width: 280, flexShrink: 0}}>
          <div style={{fontSize: 12, color: 'var(--text-3)', marginBottom: 8, fontWeight: 500, padding: '0 4px'}}>数据源列表</div>
          {loading && <div style={{color: 'var(--text-3)', padding: 16, textAlign: 'center'}}>加载中…</div>}
          {datasources.map(ds => (
            <div
              key={ds.id}
              onClick={() => handleSelectDs(ds)}
              style={{
                padding: 12, border: '1px solid var(--hairline)', borderRadius: 8, marginBottom: 8,
                cursor: 'pointer', background: selectedDs?.id === ds.id ? 'var(--accent-soft)' : 'var(--surface)',
                borderColor: selectedDs?.id === ds.id ? 'var(--accent)' : 'var(--hairline)',
                opacity: deletingId === ds.id ? 0.5 : 1,
              }}
            >
              <div style={{display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6}}>
                <span style={{fontSize: 18}}>{datasourceDisplayInfo(ds, capabilities.find(c => c.db_type === ds.db_type)).icon}</span>
                <span style={{fontWeight: 500, fontSize: 13, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{ds.name}</span>
                <span style={{fontSize: 10, padding: '1px 6px', borderRadius: 4, background: statusColor(ds.status) + '22', color: statusColor(ds.status), flexShrink: 0}}>
                  {ds.status === 'connected' ? '已连接' : ds.status === 'syncing' ? '同步中' : '断开'}
                </span>
              </div>
              <div style={{fontSize: 11, color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{ds.host}:{ds.port}/{ds.database_name}</div>
            </div>
          ))}
          {!loading && datasources.length === 0 && (
            <div style={{padding: 24, textAlign: 'center', color: 'var(--text-3)', fontSize: 13}}>
              暂无数据源<br />点击右上角「新建数据源」
            </div>
          )}
        </div>

        {/* 右侧: 数据源详情 */}
        {selectedDs ? (
          <div style={{flex: 1, minWidth: 0}}>
            {/* 详情头部 */}
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16}}>
              <div>
                <h2 style={{margin: 0, fontSize: 16, fontWeight: 500}}>{selectedDs.name}</h2>
                <div style={{fontSize: 12, color: 'var(--text-3)', marginTop: 2}}>
                  {selectedDisplay.icon} {selectedDisplay.productLabel} · {selectedDs.host}:{selectedDs.port}/{selectedDs.database_name}
                </div>
              </div>
              <div style={{display: 'flex', gap: 8}}>
                <button className="btn ghost" style={{height: 28, fontSize: 12}} onClick={() => handleTest(selectedDs.id)} disabled={testingId === selectedDs.id}>
                  {testingId === selectedDs.id ? '测试中…' : '测试连接'}
                </button>
                <button className="btn ghost" style={{height: 28, fontSize: 12}} onClick={() => handleOpenEdit(selectedDs)}>
                  编辑
                </button>
                <button className="btn ghost" style={{height: 28, fontSize: 12, color: 'var(--neg)'}} onClick={() => handleDelete(selectedDs)} disabled={deletingId === selectedDs.id}>
                  {deletingId === selectedDs.id ? '删除中…' : '删除'}
                </button>
              </div>
            </div>

            {/* 测试结果提示 */}
            {testResult && (
              <div style={{padding: 10, borderRadius: 6, marginBottom: 12, background: testResult.ok ? 'var(--pos-soft)' : 'var(--neg-soft)', color: testResult.ok ? 'var(--pos)' : 'var(--neg)', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8}}>
                <Icon name={testResult.ok ? 'check' : 'warn'} style={{width: 14, height: 14}} />
                {testResult.msg}
              </div>
            )}

            {/* Tab 切换 */}
            <div style={{display: 'flex', gap: 4, marginBottom: 16, borderBottom: '1px solid var(--hairline)'}}>
              {[
                { id: 'overview', label: '概览' },
                { id: 'schemas', label: 'Schema', badge: schemas.length },
                { id: 'ddl', label: 'DDL 同步' },
              ].map(t => (
                <button key={t.id} onClick={() => setDsTab(t.id)} style={{
                  padding: '6px 12px', border: 'none', background: 'none', cursor: 'pointer', fontSize: 13,
                  color: dsTab === t.id ? 'var(--accent)' : 'var(--text-2)',
                  borderBottom: dsTab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
                  marginBottom: -1, display: 'flex', alignItems: 'center', gap: 6,
                }}>
                  {t.label}
                  {t.badge != null && <span style={{fontSize: 11, padding: '0 5px', borderRadius: 4, background: 'var(--bg-2)', color: 'var(--text-3)', fontFamily: 'var(--font-mono)'}}>{t.badge}</span>}
                </button>
              ))}
            </div>

            {/* 概览 Tab */}
            {dsTab === 'overview' && (
              <div>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 20}}>
                  {[
                    { label: '数据库类型', val: selectedDisplay.productLabel },
                    { label: '表数量', val: schema.length + ' 张' },
                    { label: '驱动状态', val: driverStatusLabel(selectedCapability?.driver_status) },
                  ].map(s => (
                    <div key={s.label} style={{padding: 12, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 6}}>
                      <div style={{fontSize: 11, color: 'var(--text-3)', marginBottom: 4}}>{s.label}</div>
                      <div style={{fontSize: 15, fontWeight: 500, fontFamily: 'var(--font-mono)'}}>{s.val}</div>
                    </div>
                  ))}
                </div>
                <div style={{padding: 14, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 8}}>
                  <div style={{fontSize: 13, fontWeight: 500, marginBottom: 10}}>连接信息</div>
                  <div style={{display: 'grid', gridTemplateColumns: '80px 1fr', gap: '6px 0', fontSize: 12}}>
                    <span style={{color: 'var(--text-3)'}}>主机地址</span><code style={{fontFamily: 'var(--font-mono)', color: 'var(--accent)'}}>{selectedDs.host}:{selectedDs.port}</code>
                    <span style={{color: 'var(--text-3)'}}>数据库名</span><code style={{fontFamily: 'var(--font-mono)', color: 'var(--accent)'}}>{selectedDs.database_name}</code>
                    <span style={{color: 'var(--text-3)'}}>用户名</span><code style={{fontFamily: 'var(--font-mono)', color: 'var(--text)'}}>{selectedDs.username}</code>
                    <span style={{color: 'var(--text-3)'}}>方言</span><code style={{fontFamily: 'var(--font-mono)', color: 'var(--text)'}}>{selectedDisplay.dialectLabel}</code>
                    <span style={{color: 'var(--text-3)'}}>驱动</span><span style={{color: driverStatusColor(selectedCapability?.driver_status)}}>{selectedDisplay.driverLabel} · {driverStatusLabel(selectedCapability?.driver_status)}</span>
                    <span style={{color: 'var(--text-3)'}}>创建时间</span><span style={{fontFamily: 'var(--font-mono)', color: 'var(--text-3)'}}>{selectedDs.created_at ? new Date(selectedDs.created_at).toLocaleString('zh-CN') : '—'}</span>
                  </div>
                  {selectedCapability?.driver_status === 'missing' && (
                    <div style={{marginTop: 12, padding: 10, borderRadius: 6, background: 'var(--warn-soft)', color: 'var(--warn)', fontSize: 12, lineHeight: 1.6}}>
                      {selectedCapability.install_hint || '当前环境未安装该数据源驱动，请先安装企业驱动离线包。'}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Schema Tab */}
            {dsTab === 'schemas' && (
              <div style={{display: 'grid', gridTemplateColumns: '200px 1fr', gap: 16, alignItems: 'start'}}>
                {/* 左侧：Schema 列表 */}
                <div>
                  <div style={{fontSize: 12, color: 'var(--text-3)', marginBottom: 8, fontWeight: 500}}>Schema</div>
                  {schemas.length === 0 && (
                    <div style={{fontSize: 12, color: 'var(--text-3)', padding: 12}}>暂无 Schema</div>
                  )}
                  {schemas.map(s => (
                    <div
                      key={s}
                      onClick={() => handleSelectSchema(s)}
                      style={{
                        padding: '8px 10px', border: '1px solid var(--hairline)', borderRadius: 6, marginBottom: 6,
                        cursor: 'pointer', background: selectedSchema === s ? 'var(--accent-soft)' : 'var(--surface)',
                        borderColor: selectedSchema === s ? 'var(--accent)' : 'var(--hairline)',
                        display: 'flex', alignItems: 'center', gap: 8,
                      }}
                    >
                      <Icon name="database" style={{width: 13, height: 13, color: selectedSchema === s ? 'var(--accent)' : 'var(--text-3)', flexShrink: 0}} />
                      <div style={{overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12, fontWeight: 500}}>{s}</div>
                    </div>
                  ))}
                </div>
                {/* 右侧：表列表 */}
                <div>
                  {schemaLoading && <div style={{color: 'var(--text-3)', padding: 16, textAlign: 'center', fontSize: 13}}>加载中…</div>}
                  {!schemaLoading && schema.length === 0 && (
                    <div style={{padding: 32, textAlign: 'center', color: 'var(--text-3)', fontSize: 13}}>
                      暂无表信息<br />请先选择一个 Schema
                    </div>
                  )}
                  {!schemaLoading && schema.length > 0 && (
                    <>
                      {/* 搜索 + 分页 */}
                      <div style={{display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center'}}>
                        <input
                          value={tableSearch}
                          onChange={e => { setTableSearch(e.target.value); setTablePage(1); }}
                          placeholder="搜索表名…"
                          style={{flex: 1, padding: '5px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--surface)', color: 'var(--text)', fontSize: 12}}
                        />
                        <span style={{fontSize: 11, color: 'var(--text-3)', flexShrink: 0}}>{filteredTables.length} 张表</span>
                      </div>
                      {paginatedTables.map((table, i) => {
                        const realIdx = (tablePage - 1) * TABLE_PAGE_SIZE + i;
                        return (
                          <div key={realIdx} style={{marginBottom: 10, border: '1px solid var(--hairline)', borderRadius: 8, overflow: 'hidden'}}>
                            <div style={{padding: '8px 12px', background: 'var(--bg-2)', display: 'flex', alignItems: 'center', gap: 8}}>
                              <Icon name="table" style={{width: 13, height: 13, color: 'var(--accent)'}} />
                              <span style={{fontWeight: 600, fontSize: 13, fontFamily: 'var(--font-mono)'}}>{table.name}</span>
                              <span style={{fontSize: 11, color: 'var(--text-3)', background: 'var(--surface-2)', padding: '1px 6px', borderRadius: 3}}>{table.row_count != null ? `${Number(table.row_count).toLocaleString()} 行` : '— 行'}</span>
                              {table.size && <span style={{fontSize: 11, color: 'var(--text-3)', background: 'var(--surface-2)', padding: '1px 6px', borderRadius: 3}}>{table.size}</span>}
                              <span style={{fontSize: 11, color: 'var(--text-3)', marginLeft: 'auto'}}>{table.columns?.length || 0} 列</span>
                              {table.primary_key?.length > 0 && (
                                <span style={{fontSize: 10, padding: '1px 5px', borderRadius: 3, background: 'var(--accent-soft)', color: 'var(--accent)'}}>PK</span>
                              )}
                              <span
                                onClick={() => setExpandedTable(expandedTable === realIdx ? null : realIdx)}
                                style={{marginLeft: 4, cursor: 'pointer', color: 'var(--text-3)', fontSize: 10, display: 'flex', alignItems: 'center'}}
                              >
                                {expandedTable === realIdx ? '▲' : '▶'}
                              </span>
                            </div>
                            {expandedTable === realIdx && (
                              <div style={{padding: '6px 12px', display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '2px 12px', fontSize: 11}}>
                                {table.columns?.map((col, j) => (
                                  <React.Fragment key={j}>
                                    <span style={{overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text)'}} title={col.name}>{col.name}</span>
                                    <span style={{color: 'var(--text-2)', fontFamily: 'var(--font-mono)', fontSize: 10}}>{col.type}</span>
                                    <span style={{color: col.nullable ? 'var(--text-3)' : 'var(--neg)', textAlign: 'right'}}>{col.nullable ? 'NULL' : 'NOT NULL'}</span>
                                  </React.Fragment>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {/* 分页 */}
                      {totalPages > 1 && (
                        <div style={{display: 'flex', gap: 6, justifyContent: 'center', marginTop: 12}}>
                          <button onClick={() => setTablePage(p => Math.max(1, p - 1))} disabled={tablePage === 1} style={{padding: '4px 10px', borderRadius: 4, border: '1px solid var(--hairline)', background: 'var(--surface)', cursor: 'pointer', fontSize: 12}}>上一页</button>
                          <span style={{fontSize: 12, color: 'var(--text-3)', alignSelf: 'center'}}>{tablePage} / {totalPages}</span>
                          <button onClick={() => setTablePage(p => Math.min(totalPages, p + 1))} disabled={tablePage === totalPages} style={{padding: '4px 10px', borderRadius: 4, border: '1px solid var(--hairline)', background: 'var(--surface)', cursor: 'pointer', fontSize: 12}}>下一页</button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            )}

            {/* DDL 同步 Tab */}
            {dsTab === 'ddl' && (
              <div>
                <div style={{display: 'flex', justifyContent: 'flex-end', marginBottom: 12}}>
                  <button className="btn primary" onClick={handleSyncTables} disabled={syncing}>
                    <Icon name="refresh" /> {syncing ? '同步中…' : '同步表结构'}
                  </button>
                </div>
                {syncResult && (
                  <div style={{padding: 10, borderRadius: 6, marginBottom: 12, background: syncResult.ok === false ? 'var(--neg-soft)' : 'var(--pos-soft)', color: syncResult.ok === false ? 'var(--neg)' : 'var(--pos)', fontSize: 13}}>
                    {syncResult.ok === false
                      ? (syncResult.message || '同步失败')
                      : `同步完成：新增 ${syncResult.created || 0}，更新 ${syncResult.updated || 0}，总表 ${syncResult.total_tables || 0}，跳过 ${(syncResult.skipped || []).length}，错误 ${(syncResult.errors || []).length}`}
                  </div>
                )}
                {schema.length > 0 ? (
                  <div>
                    <div style={{display: 'flex', alignItems: 'center', gap: 12, padding: 16, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 8, marginBottom: 16}}>
                      <div style={{width: 44, height: 44, borderRadius: 8, background: 'var(--pos-soft)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0}}>
                        <Icon name="database" style={{width: 20, height: 20, color: 'var(--pos)'}} />
                      </div>
                      <div style={{flex: 1}}>
                        <div style={{fontWeight: 600, fontSize: 14, marginBottom: 2}}>DDL 同步完成</div>
                        <div style={{fontSize: 12, color: 'var(--text-3)'}}>已扫描 <span style={{fontFamily: 'var(--font-mono)', color: 'var(--accent)'}}>{schema.length}</span> 张表，写入语义层</div>
                      </div>
                      <span style={{fontSize: 11, padding: '2px 8px', borderRadius: 4, background: 'var(--pos-soft)', color: 'var(--pos)'}}>已完成</span>
                    </div>
                    <div style={{marginBottom: 16}}>
                      <div style={{fontSize: 12, fontWeight: 500, color: 'var(--text-3)', marginBottom: 8}}>同步进度</div>
                      <div style={{height: 6, borderRadius: 3, background: 'var(--bg-2)', overflow: 'hidden'}}>
                        <div style={{height: '100%', width: '100%', background: 'var(--pos)', borderRadius: 3}} />
                      </div>
                      <div style={{fontSize: 11, color: 'var(--text-3)', marginTop: 4}}>全部 {schema.length} 张表已同步</div>
                    </div>
                    <div style={{fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6}}>
                      DDL 同步会将数据源的表结构写入语义层，供指标、维度、字段召回和 SQL Guard 使用；字段样例采集失败会计入跳过项，不阻断表字段同步。
                    </div>
                  </div>
                ) : (
                  <div style={{padding: 32, textAlign: 'center', color: 'var(--text-3)', fontSize: 13}}>
                    <Icon name="database" style={{fontSize: 28, marginBottom: 8, opacity: 0.4}} />
                    <div>暂无同步数据</div>
                    <div style={{marginTop: 4, fontSize: 12}}>请先测试连接并加载 Schema</div>
                  </div>
                )}
              </div>
            )}

            {/* 配置 Tab */}
            {dsTab === 'config' && (
              <div>
                <div style={{fontSize: 13, fontWeight: 500, marginBottom: 14}}>连接配置</div>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12}}>
                  <FormField label="名称" value={form.name} onChange={v => setForm({...form, name: v})} placeholder="如: electric_dwh" />
                  <FormField label="类型" type="select" value={form.db_type} options={dbTypeOptions} onChange={handleDbTypeChange} />
                  <FormField label="主机地址" value={form.host} onChange={v => setForm({...form, host: v})} placeholder="如: localhost" />
                  <FormField label="端口" type="number" value={form.port} onChange={v => setForm({...form, port: parseInt(v) || 0})} />
                  <FormField label="数据库名" value={form.database_name} onChange={v => setForm({...form, database_name: v})} />
                  <FormField label="用户名" value={form.username} onChange={v => setForm({...form, username: v})} />
                </div>
                <FormField label="密码" type="password" value={form.password} onChange={v => setForm({...form, password: v})} placeholder={editingDs ? '留空则不修改' : '输入密码'} />
                <div style={{display: 'flex', gap: 8, marginTop: 16}}>
                  <button className="btn primary" onClick={handleSave}>保存配置</button>
                  <button className="btn ghost" onClick={() => handleOpenEdit(selectedDs)}>重置</button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div style={{flex: 1, padding: 48, textAlign: 'center', color: 'var(--text-3)', background: 'var(--surface)', borderRadius: 8, border: '1px dashed var(--hairline)'}}>
            <Icon name="plug" style={{fontSize: 32, marginBottom: 8, opacity: 0.4}} />
            <div style={{fontSize: 14, marginBottom: 4}}>选择左侧数据源查看详情</div>
            <div style={{fontSize: 12}}>或点击右上角「新建数据源」添加连接</div>
          </div>
        )}
      </div>

      {/* 新建/编辑 Drawer */}
      {showDrawer && (
        <div style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 100, display: 'flex', justifyContent: 'flex-end'}} onClick={() => setShowDrawer(false)}>
          <div style={{width: 440, height: '100%', background: 'var(--bg)', borderLeft: '1px solid var(--hairline)', padding: 24, overflow: 'auto', display: 'flex', flexDirection: 'column'}} onClick={e => e.stopPropagation()}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24}}>
              <h3 style={{margin: 0, fontSize: 16, fontWeight: 600}}>{editingDs ? '编辑数据源' : '新建数据源'}</h3>
              <button className="icon-btn" onClick={() => setShowDrawer(false)}><Icon name="x" /></button>
            </div>
            <div style={{flex: 1}}>
              <FormField label="名称 *" value={form.name} onChange={v => setForm({...form, name: v})} placeholder="如: electric_dwh" />
              <FormField label="数据库类型" type="select" value={form.db_type} options={dbTypeOptions} onChange={handleDbTypeChange} />
              {activeCapability && (
                <div style={{margin: '-6px 0 14px', padding: 10, borderRadius: 6, background: activeCapability.driver_status === 'missing' ? 'var(--warn-soft)' : 'var(--surface)', border: '1px solid var(--hairline)', fontSize: 12, lineHeight: 1.6}}>
                  <span style={{color: driverStatusColor(activeCapability.driver_status), fontWeight: 600}}>
                    {driverStatusLabel(activeCapability.driver_status)}
                  </span>
                  <span style={{color: 'var(--text-3)'}}> · {activeDisplay.driverLabel || 'Python 内置'} · 方言 {activeDisplay.dialectLabel} · 默认端口 {activeDisplay.portLabel}</span>
                  {activeCapability.driver_status === 'missing' && (
                    <div style={{color: 'var(--warn)', marginTop: 4}}>
                      {activeCapability.install_hint}
                    </div>
                  )}
                </div>
              )}
              <FormField label="主机地址 *" value={form.host} onChange={v => setForm({...form, host: v})} placeholder="如: localhost 或 192.168.1.100" />
              <FormField label="端口" type="number" value={form.port} onChange={v => setForm({...form, port: parseInt(v) || 0})} />
              <FormField label="数据库名 *" value={form.database_name} onChange={v => setForm({...form, database_name: v})} placeholder="如: electric_dwh" />
              <FormField label="默认 Schema" value={form.default_schema} onChange={v => setForm({...form, default_schema: v})} placeholder={activeCapability?.default_schema || '可选'} />
              <FormField label="用户名" value={form.username} onChange={v => setForm({...form, username: v})} />
              <FormField label={editingDs ? '密码（留空不修改）' : '密码 *'} type="password" value={form.password} onChange={v => setForm({...form, password: v})} />
              {form.db_type === 'oracle' && (
                <>
                  <FormField label="Service Name" value={optionValue('service_name')} onChange={v => setOptionValue('service_name', v)} placeholder="如: ORCLPDB1" />
                  <FormField label="SID" value={optionValue('sid')} onChange={v => setOptionValue('sid', v)} placeholder="使用 SID 时填写" />
                </>
              )}
              {form.db_type === 'hive' && (
                <>
                  <FormField label="认证方式" type="select" value={optionValue('auth')} options={[{ value: '', label: '默认' }, { value: 'NONE', label: 'NONE' }, { value: 'LDAP', label: 'LDAP' }, { value: 'KERBEROS', label: 'KERBEROS' }]} onChange={v => setOptionValue('auth', v)} />
                  <FormField label="Kerberos Service" value={optionValue('kerberos_service_name')} onChange={v => setOptionValue('kerberos_service_name', v)} placeholder="如: hive" />
                </>
              )}
              {['trino', 'presto'].includes(form.db_type) && (
                <>
                  <FormField label="Catalog" value={optionValue('catalog')} onChange={v => setOptionValue('catalog', v)} placeholder="如: hive" />
                  <FormField label="Schema" value={optionValue('schema')} onChange={v => setOptionValue('schema', v)} placeholder="如: default" />
                </>
              )}
              {form.db_type === 'sqlserver' && (
                <>
                  <FormField label="ODBC Driver" value={optionValue('driver_name')} onChange={v => setOptionValue('driver_name', v)} placeholder="如: ODBC Driver 18 for SQL Server" />
                  <FormField label="Instance" value={optionValue('instance')} onChange={v => setOptionValue('instance', v)} placeholder="可选实例名" />
                </>
              )}
              {form.db_type === 'bigquery' && (
                <>
                  <FormField label="Project" value={optionValue('project')} onChange={v => setOptionValue('project', v)} />
                  <FormField label="Dataset" value={optionValue('dataset')} onChange={v => setOptionValue('dataset', v)} />
                  <FormField label="Credentials Path" value={optionValue('credentials_path')} onChange={v => setOptionValue('credentials_path', v)} />
                </>
              )}
              <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12}}>
                <FormField label="连接超时（秒）" type="number" value={form.connect_timeout_seconds} onChange={v => setForm({...form, connect_timeout_seconds: parseInt(v) || 10})} />
                <FormField label="查询超时（秒）" type="number" value={form.query_timeout_seconds} onChange={v => setForm({...form, query_timeout_seconds: parseInt(v) || 30})} />
              </div>
            </div>
            <div style={{display: 'flex', gap: 10, marginTop: 24, paddingTop: 16, borderTop: '1px solid var(--hairline)'}}>
              <button className="btn ghost" style={{flex: 1}} onClick={() => setShowDrawer(false)}>取消</button>
              <button className="btn primary" style={{flex: 1}} onClick={handleSave} disabled={!form.name || !form.host || !form.database_name}>
                {editingDs ? '保存修改' : '创建数据源'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FormField({ label, type = 'text', value, onChange, options = [], placeholder = '' }) {
  return (
    <div style={{marginBottom: 14}}>
      <label style={{display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 4}}>{label}</label>
      {type === 'select' ? (
        <select value={value} onChange={e => onChange(e.target.value)} style={{width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--surface)', color: 'var(--text)', fontSize: 13}}>
          {options.map(opt => {
            const optionValueText = typeof opt === 'string' ? opt : opt.value;
            const label = typeof opt === 'string' ? opt : opt.label;
            return <option key={optionValueText} value={optionValueText}>{label}</option>;
          })}
        </select>
      ) : (
        <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={{width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--hairline)', background: 'var(--surface)', color: 'var(--text)', fontSize: 13}} />
      )}
    </div>
  );
}

export { DatasourcesScreen };
