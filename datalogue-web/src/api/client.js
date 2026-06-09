// 前端 API 客户端 — 统一封装 fetch，对接后端 FastAPI 服务

const BASE_URL = ''; // Vite proxy 已配置 /api 转发，无需写死域名

/**
 * 通用 GET 请求
 * @param {string} path - API 路径（如 /api/conversation）
 */
export async function get(path) {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return res.json();
}

/**
 * 通用 POST 请求
 * @param {string} path - API 路径
 * @param {object} body - JSON 请求体
 */
export async function post(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return res.json();
}

/**
 * 通用 PUT 请求
 * @param {string} path - API 路径
 * @param {object} body - JSON 请求体
 */
export async function put(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return res.json();
}

/**
 * 通用 PATCH 请求
 * @param {string} path - API 路径
 * @param {object} body - JSON 请求体
 */
export async function patch(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return res.json();
}

/**
 * 通用 DELETE 请求
 * @param {string} path - API 路径
 */
export async function del(path) {
  const res = await fetch(`${BASE_URL}${path}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return res.json();
}

/**
 * SSE 流式问数 — 三类事件：step（节点进度）/ token（LLM字符）/ final（结束）
 * 旧 callback 形式，datasets 页面还在用；新 ChatModelAdapter 改用 streamChatEvents
 * @param {object} payload - { question, conversation_id?, dataset_id? }
 * @param {object} callbacks
 * @param {function} callbacks.onToken - (token: string) => void，每个 LLM token 触发
 * @param {function} callbacks.onEvent - (data: object) => void，step 事件触发
 * @param {function} callbacks.onDone  - (data: object) => void，final 事件触发
 * @param {function} callbacks.onError - (err: Error) => void
 */
export function streamChat(payload, { onToken, onEvent, onError, onDone }) {
  const controller = new AbortController();

  fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok) {
      onError?.(new Error(`HTTP ${res.status}`));
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // 保留不完整行

      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        try {
          const data = JSON.parse(line.slice(5).trim());
          if (data.type === 'token') {
            onToken?.(data.content);
          } else if (data.type === 'step') {
            onEvent?.(data);
          } else if (data.type === 'final') {
            onDone?.(data);
          }
        } catch {
          // 忽略非 JSON 行
        }
      }
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') onError?.(err);
  });

  return controller;
}

/**
 * SSE 流式问数 — async generator 版本
 * 新 ChatModelAdapter（assistant-ui）使用，yield 原始事件对象 {type, ...}
 * @param {object} payload - { question, conversation_id?, dataset_id? }
 * @param {object} opts
 * @param {AbortSignal} opts.signal - 用于中断
 */
export async function* streamChatEvents(payload, { signal } = {}) {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith('data:')) continue;
      try {
        yield JSON.parse(line.slice(5).trim());
      } catch {
        /* 忽略非 JSON 行 */
      }
    }
  }
}

// ── 具体业务 API ─────────────────────────────────────

/** 获取对话列表，archived=false 取常规，true 取归档 */
export function listConversations({ archived = false } = {}) {
  return get(`/api/conversation?archived=${archived}`);
}

/** 创建空对话，返回 ConversationOut */
export function createConversation({ title = '新对话', thread_id = null, dataset_id = null } = {}) {
  return post('/api/conversation', { title, thread_id, dataset_id });
}

/** 重命名对话 */
export function renameConversation(id, title) {
  return patch(`/api/conversation/${id}`, { title });
}

/** 归档对话 */
export function archiveConversation(id) {
  return post(`/api/conversation/${id}/archive`, {});
}

/** 取消归档 */
export function unarchiveConversation(id) {
  return post(`/api/conversation/${id}/unarchive`, {});
}

/** 获取对话详情（含消息） */
export function getConversation(id) {
  return get(`/api/conversation/${id}`);
}

/** 删除对话 */
export function deleteConversation(id) {
  return del(`/api/conversation/${id}`);
}

/** 获取数据源列表 */
export function listDatasources() {
  return get('/api/datasource');
}

/** 创建数据源 */
export function createDatasource(data) {
  return post('/api/datasource', data);
}

/** 更新数据源 */
export function updateDatasource(id, data) {
  return put(`/api/datasource/${id}`, data);
}

/** 测试数据源连接 */
export function testDatasource(id) {
  return post(`/api/datasource/${id}/test`);
}

/** 获取数据源 Schema 列表 */
export function getDatasourceSchemas(id) {
  return get(`/api/datasource/${id}/schemas`);
}

/** 获取数据源指定 Schema 的表 */
export function getDatasourceSchema(id, schema) {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return get(`/api/datasource/${id}/schema${qs}`);
}

/** 删除数据源 */
export function deleteDatasource(id) {
  return del(`/api/datasource/${id}`);
}

/** 获取数据集列表 */
export function listDatasets(datasourceId) {
  const qs = datasourceId ? `?datasource_id=${datasourceId}` : '';
  return get(`/api/dataset${qs}`);
}

/** 创建数据集 */
export function createDataset(data) {
  return post('/api/dataset', data);
}

/** 重命名数据集 */
export function renameDataset(datasetId, name) {
  return put(`/api/dataset/${datasetId}`, { name });
}

/** 删除数据集 */
export function deleteDataset(datasetId) {
  return del(`/api/dataset/${datasetId}`);
}

/** 获取数据集的指标列表 */
export function listDatasetMetrics(datasetId) {
  return get(`/api/dataset/${datasetId}/metrics`);
}

/** 添加指标 */
export function createMetric(datasetId, data) {
  return post(`/api/dataset/${datasetId}/metric`, data);
}

/** 删除指标 */
export function deleteMetric(datasetId, metricId) {
  return del(`/api/dataset/${datasetId}/metric/${metricId}`);
}

/** 获取数据集的维度列表 */
export function listDatasetDimensions(datasetId) {
  return get(`/api/dataset/${datasetId}/dimensions`);
}

/** 添加维度 */
export function createDimension(datasetId, data) {
  return post(`/api/dataset/${datasetId}/dimension`, data);
}

/** 删除维度 */
export function deleteDimension(datasetId, dimensionId) {
  return del(`/api/dataset/${datasetId}/dimension/${dimensionId}`);
}

/** 更新指标 */
export function updateMetric(datasetId, metricId, data) {
  return put(`/api/dataset/${datasetId}/metric/${metricId}`, data);
}

/** 更新维度 */
export function updateDimension(datasetId, dimId, data) {
  return put(`/api/dataset/${datasetId}/dimension/${dimId}`, data);
}

/** 更新数据集 */
export function updateDataset(datasetId, data) {
  return put(`/api/dataset/${datasetId}`, data);
}

/** 同步数据源表结构 */
export function syncDatasourceTables(datasourceId) {
  return post(`/api/datasource/${datasourceId}/sync-tables`);
}

/** 获取数据源下已同步的表 */
export function listSourceTables(datasourceId, schema) {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return get(`/api/datasource/${datasourceId}/source-tables${qs}`);
}

/** 获取表的所有字段 */
export function getSourceTableColumns(tableId) {
  return get(`/api/datasource/source-table/${tableId}/columns`);
}

/** LLM 自动标注字段 */
export function annotateDatasetColumns(datasetId) {
  return post(`/api/dataset/${datasetId}/annotate-columns`);
}

/** YAML 导入 */
export function importDatasetYaml(datasetId, yamlText) {
  return post(`/api/dataset/${datasetId}/import-yaml`, { yaml: yamlText });
}

/** YAML 导出 */
export function exportDatasetYaml(datasetId) {
  return get(`/api/dataset/${datasetId}/export-yaml`);
}

/** 数据预览 */
export function previewTable(datasourceId, schema, table, limit = 5) {
  return post(`/api/datasource/${datasourceId}/preview`, { schema, table, limit });
}

/** 选择表加入数据集 */
export function selectTablesForDataset(datasetId, sourceTableIds) {
  return post(`/api/dataset/${datasetId}/select-tables`, { source_table_ids: sourceTableIds });
}

/** 从数据集移除表 */
export function deselectTableFromDataset(datasetId, sourceTableId) {
  return del(`/api/dataset/${datasetId}/select-tables/${sourceTableId}`);
}

/** 获取数据集已选中的表 */
export function listSelectedTables(datasetId) {
  return get(`/api/dataset/${datasetId}/selected-tables`);
}

/** 获取数据集已选表的字段（合并） */
export function listSelectedColumns(datasetId) {
  return get(`/api/dataset/${datasetId}/selected-columns`);
}

/** 更新单个 source_column 的用户标注 */
export function updateSourceColumn(columnId, data) {
  return put(`/api/datasource/source-column/${columnId}`, data);
}

/** 将字段转换为指标，并回写字段状态 */
export function convertColumnToMetric(datasetId, columnId, data) {
  return post(`/api/dataset/${datasetId}/columns/${columnId}/convert-metric`, data);
}

/** 将字段转换为维度，并回写字段状态 */
export function convertColumnToDimension(datasetId, columnId, data) {
  return post(`/api/dataset/${datasetId}/columns/${columnId}/convert-dimension`, data);
}

/** 更新字段审核状态 */
export function updateColumnReviewStatus(datasetId, columnId, reviewStatus) {
  return patch(`/api/dataset/${datasetId}/columns/${columnId}/review-status`, {
    review_status: reviewStatus,
  });
}

/** 获取业务术语列表 */
export function listBusinessTerms(datasetId, filters = {}) {
  const params = new URLSearchParams();
  if (filters.q) params.set('q', filters.q);
  if (filters.term_type) params.set('term_type', filters.term_type);
  if (filters.status) params.set('status', filters.status);
  if (filters.has_conflict !== undefined && filters.has_conflict !== '') {
    params.set('has_conflict', String(filters.has_conflict));
  }
  const qs = params.toString() ? `?${params.toString()}` : '';
  return get(`/api/dataset/${datasetId}/terms${qs}`);
}

/** 创建业务术语 */
export function createBusinessTerm(datasetId, data) {
  return post(`/api/dataset/${datasetId}/terms`, data);
}

/** 更新业务术语 */
export function updateBusinessTerm(datasetId, termId, data) {
  return put(`/api/dataset/${datasetId}/terms/${termId}`, data);
}

/** 删除业务术语 */
export function deleteBusinessTerm(datasetId, termId) {
  return del(`/api/dataset/${datasetId}/terms/${termId}`);
}

/** 更新术语关联资产 */
export function linkBusinessTermAssets(datasetId, termId, links) {
  return post(`/api/dataset/${datasetId}/terms/${termId}/link-assets`, { links });
}

/** AI/规则发现候选业务术语 */
export function discoverBusinessTerms(datasetId) {
  return post(`/api/dataset/${datasetId}/terms/discover`);
}

/** 检查业务术语冲突 */
export function checkBusinessTermConflicts(datasetId) {
  return post(`/api/dataset/${datasetId}/terms/conflicts/check`);
}

/** 手动触发单张表的 AI 标注 */
export function annotateSourceTable(tableId) {
  return post(`/api/datasource/source-table/${tableId}/annotate`);
}

/** 获取数据集分析蓝图列表 */
export function listAnalysisBlueprints(datasetId, status) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  return get(`/api/dataset/${datasetId}/blueprints${qs}`);
}

/** 创建分析蓝图 */
export function createAnalysisBlueprint(datasetId, data) {
  return post(`/api/dataset/${datasetId}/blueprints`, data);
}

/** 更新分析蓝图 */
export function updateAnalysisBlueprint(datasetId, blueprintId, data) {
  return put(`/api/dataset/${datasetId}/blueprints/${blueprintId}`, data);
}

/** 变更分析蓝图状态 */
export function updateAnalysisBlueprintStatus(datasetId, blueprintId, data) {
  return patch(`/api/dataset/${datasetId}/blueprints/${blueprintId}/status`, data);
}

/** 发起 SQL 分析任务 */
export function analyzeBlueprintSql(datasetId, sql) {
  return post(`/api/dataset/${datasetId}/blueprints/analyze-sql`, { sql });
}

/** 根据业务场景生成分析蓝图草稿 */
export function analyzeBlueprintDescription(datasetId, data) {
  return post(`/api/dataset/${datasetId}/blueprints/analyze-description`, data);
}

/** 查询 SQL 分析任务 */
export function getBlueprintAnalyzeTask(datasetId, taskId) {
  return get(`/api/dataset/${datasetId}/blueprints/analyze-sql/${taskId}`);
}

/** 测试运行分析蓝图 */
export function testAnalysisBlueprint(datasetId, blueprintId, params = {}, question = '') {
  return post(`/api/dataset/${datasetId}/blueprints/${blueprintId}/test`, { params, question });
}

/** 获取蓝图版本 */
export function listAnalysisBlueprintVersions(datasetId, blueprintId) {
  return get(`/api/dataset/${datasetId}/blueprints/${blueprintId}/versions`);
}

/** 回滚蓝图版本 */
export function rollbackAnalysisBlueprint(datasetId, blueprintId, version) {
  return post(`/api/dataset/${datasetId}/blueprints/${blueprintId}/rollback`, { version });
}

/** 获取蓝图使用统计 */
export function getAnalysisBlueprintUsageStats(datasetId, blueprintId) {
  return get(`/api/dataset/${datasetId}/blueprints/${blueprintId}/usage-stats`);
}

/** 获取蓝图使用日志 */
export function listAnalysisBlueprintUsageLogs(datasetId, blueprintId) {
  return get(`/api/dataset/${datasetId}/blueprints/${blueprintId}/usage-logs`);
}
