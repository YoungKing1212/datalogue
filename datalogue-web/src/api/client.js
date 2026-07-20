// 前端 API 客户端 — 统一封装 fetch，对接后端 FastAPI 服务

const BASE_URL = ''; // Vite proxy 已配置 /api 转发，无需写死域名
let _accessToken = null;
let _refreshHandler = null;
let _authFailureHandler = null;

function assertSecureAuthTransport() {
  const location = globalThis.location;
  if (!location) return;
  const localHosts = new Set(['localhost', '127.0.0.1', '::1']);
  // 本地开发允许 HTTP；任何远端部署都必须由 HTTPS 提供真实的传输机密性。
  if (location.protocol !== 'https:' && !localHosts.has(location.hostname)) {
    throw new Error('登录仅支持 HTTPS，请使用安全地址重新打开本页面');
  }
}

export function setAccessToken(token) {
  _accessToken = token || null;
}

export function setAuthRefreshHandler(handler) {
  _refreshHandler = typeof handler === 'function' ? handler : null;
}

export function setAuthFailureHandler(handler) {
  _authFailureHandler = typeof handler === 'function' ? handler : null;
}

async function parseJsonResponse(res) {
  if (res.status === 204) return null;
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return res.json();
  }
  return null;
}

function normalizePlainErrorText(text) {
  if (typeof text !== 'string') return '';
  const trimmed = text.trim();
  if (!trimmed) return '';
  // 网关/反向代理常返回 HTML 错误页，直接展示给用户可读性很差。
  if (/^<!doctype html/i.test(trimmed) || /^<html/i.test(trimmed)) return '';
  return trimmed.length > 200 ? `${trimmed.slice(0, 200)}...` : trimmed;
}

function extractErrorDetail(payload) {
  if (!payload) return '';
  if (typeof payload === 'string') return normalizePlainErrorText(payload);
  if (typeof payload !== 'object') return '';

  if (typeof payload.detail === 'string') return payload.detail.trim();
  if (Array.isArray(payload.detail)) {
    const lines = payload.detail
      .map((item) => {
        if (typeof item === 'string') return item.trim();
        if (item && typeof item === 'object') {
          return String(item.msg || item.message || item.error || '').trim();
        }
        return '';
      })
      .filter(Boolean);
    if (lines.length) return lines.join('；');
  }
  if (payload.detail && typeof payload.detail === 'object') {
    const nestedDetail = String(
      payload.detail.message || payload.detail.msg || payload.detail.error || payload.detail.reason || '',
    ).trim();
    if (nestedDetail) return nestedDetail;
  }

  const direct = String(payload.message || payload.msg || payload.error || '').trim();
  return direct;
}

function buildFallbackErrorMessage(status) {
  if (status === 401) return '认证失败，请检查账号密码后重试';
  if (status === 403) return '当前账号没有访问权限，请联系管理员';
  if (status === 404) return '请求的资源不存在，请检查配置';
  if (status === 429) return '请求过于频繁，请稍后重试';
  if (status === 502) return '服务暂时不可用（网关异常），请稍后重试';
  if (status >= 500) return '服务暂时不可用，请稍后重试';
  return `请求失败（HTTP ${status}）`;
}

export async function authenticatedFetch(path, options = {}, retried = false) {
  const headers = { ...(options.headers || {}) };
  if (_accessToken && !headers.Authorization) {
    headers.Authorization = `Bearer ${_accessToken}`;
  }
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  });

  const allowRetry =
    !retried &&
    res.status === 401 &&
    typeof _refreshHandler === 'function' &&
    !String(path).startsWith('/api/auth/');

  if (allowRetry) {
    const refreshed = await _refreshHandler();
    if (refreshed) {
      return authenticatedFetch(path, options, true);
    }
    if (typeof _authFailureHandler === 'function') {
      _authFailureHandler();
    }
  }

  return res;
}

async function request(path, options = {}) {
  const res = await authenticatedFetch(path, options);

  if (!res.ok) {
    const contentType = res.headers.get('content-type') || '';
    let payload = null;
    let plainText = '';

    if (contentType.includes('application/json')) {
      try {
        payload = await res.json();
      } catch {
        payload = null;
      }
    } else {
      try {
        plainText = normalizePlainErrorText(await res.text());
      } catch {
        plainText = '';
      }
    }

    const detailMessage = extractErrorDetail(payload) || plainText;
    const message = detailMessage || buildFallbackErrorMessage(res.status);
    const error = new Error(message);
    error.status = res.status;
    error.statusText = res.statusText;
    error.path = path;
    if (payload && typeof payload === 'object') {
      error.data = payload;
    }
    throw error;
  }

  return parseJsonResponse(res);
}

/**
 * 通用 GET 请求
 * @param {string} path - API 路径（如 /api/conversation）
 */
export async function get(path) {
  return request(path, { method: 'GET' });
}

/**
 * 通用 POST 请求
 * @param {string} path - API 路径
 * @param {object} body - JSON 请求体
 */
export async function post(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/**
 * 通用 PUT 请求
 * @param {string} path - API 路径
 * @param {object} body - JSON 请求体
 */
export async function put(path, body) {
  return request(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/**
 * 通用 PATCH 请求
 * @param {string} path - API 路径
 * @param {object} body - JSON 请求体
 */
export async function patch(path, body) {
  return request(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/**
 * 通用 DELETE 请求
 * @param {string} path - API 路径
 */
export async function del(path) {
  return request(path, { method: 'DELETE' });
}

export async function loginAuth(payload) {
  assertSecureAuthTransport();
  const data = await post('/api/auth/login', {
    username: payload.username,
    password: payload.password || '',
  });
  setAccessToken(data?.access_token || null);
  return data;
}

export async function refreshAuth() {
  const data = await post('/api/auth/refresh', {});
  setAccessToken(data?.access_token || null);
  return data;
}

export async function logoutAuth() {
  try {
    await post('/api/auth/logout', {});
  } finally {
    setAccessToken(null);
  }
}

export function getCurrentUser() {
  return get('/api/auth/me');
}

export function changeCurrentPassword(payload) {
  return post('/api/auth/change-password', payload);
}

export function createUserAccount(payload) {
  return post('/api/auth/register', payload);
}

export function listUserAccounts({ limit = 100, offset = 0 } = {}) {
  return get(`/api/auth/users?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`);
}

export function updateUserAccount(userId, payload) {
  return patch(`/api/auth/users/${encodeURIComponent(userId)}`, payload);
}

export function resetUserAccountPassword(userId) {
  return post(`/api/auth/users/${encodeURIComponent(userId)}/reset-password`, {});
}

export function deleteUserAccount(userId) {
  return del(`/api/auth/users/${encodeURIComponent(userId)}`);
}

// ── 具体业务 API ─────────────────────────────────────

/** 获取对话列表，archived=false 取常规，true 取归档 */
export function listConversations({ archived = false } = {}) {
  return get(`/api/conversation?archived=${archived}`);
}

/** assistant-ui 线程列表游标分页；after 由后端生成，调用方不得解析。 */
export function listConversationPage({ after = null, limit = 50 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (after) params.set('after', after);
  return get(`/api/conversation/page?${params.toString()}`);
}

/** 获取左侧功能栏导航数量。 */
export function listNavigationCounts() {
  return get('/api/navigation/counts');
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
export function getConversation(id, { messageLimit = 200, beforeMessageId = null } = {}) {
  const params = new URLSearchParams({ message_limit: String(messageLimit) });
  if (beforeMessageId != null) params.set('before_message_id', String(beforeMessageId));
  return get(`/api/conversation/${id}?${params.toString()}`);
}

/** 按需读取查询产物 */
export function getArtifact(artifactRef) {
  return get(`/api/artifacts/${encodeURIComponent(artifactRef)}`);
}

/** 提交 assistant 消息反馈 */
export function submitMessageFeedback(messageId, data) {
  return post(`/api/messages/${messageId}/feedback`, {
    message_id: messageId,
    ...data,
  });
}

/** 删除对话 */
export function deleteConversation(id) {
  return del(`/api/conversation/${id}`);
}

/** 获取数据源列表 */
export function listDatasources() {
  return get('/api/datasource');
}

/** 获取数据源类型能力 */
export function listDatasourceCapabilities() {
  return get('/api/datasource/capabilities');
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

function normalizeAgentScopeCredential(item = {}) {
  const data = item.data && typeof item.data === 'object' ? item.data : item;
  const id = data.id || item.id || data.credential_id || item.credential_id;
  const type = data.type || item.type;
  if (!id || !type) return null;
  return {
    id: String(id),
    name: data.name || item.name || String(id),
    type: String(type),
    api_key_set: Boolean(data.api_key_set ?? item.api_key_set),
  };
}

function normalizeAgentScopeModelCard(card = {}) {
  const name = card.name || card.model || card.id;
  if (!name) return null;
  const rawStatus = String(card.status || 'available').toLowerCase();
  return {
    name: String(name),
    label: card.label || card.display_name || String(name),
    status: rawStatus === 'deprecated' || rawStatus === 'disabled' ? 'inactive' : 'active',
  };
}

/** 获取 AgentScope credential + ModelCard 组合后的聊天模型选项。 */
export async function listAgentScopeChatModels() {
  const rawCredentials = await get('/api/agentscope-control/credentials');
  const credentials = (Array.isArray(rawCredentials) ? rawCredentials : [])
    .map(normalizeAgentScopeCredential)
    .filter(Boolean);
  const providers = [...new Set(credentials.map((item) => item.type))];
  const modelGroups = await Promise.all(
    providers.map(async (provider) => {
      const rawCards = await get(`/api/agentscope-control/model?provider=${encodeURIComponent(provider)}`);
      const cards = Array.isArray(rawCards) ? rawCards : [];
      return {
        provider,
        models: cards.map(normalizeAgentScopeModelCard).filter(Boolean),
      };
    }),
  );
  const modelsByProvider = new Map(modelGroups.map((group) => [group.provider, group.models]));
  return credentials.flatMap((credential) => {
    const cards = modelsByProvider.get(credential.type) || [];
    return cards.map((card) => ({
      id: `${credential.id}:${card.name}`,
      credential_id: credential.id,
      name: `${credential.name} / ${card.label}`,
      provider: credential.type,
      model: card.name,
      status: credential.api_key_set ? card.status : 'inactive',
      description: credential.api_key_set ? null : 'AgentScope credential 未配置密钥',
      thinking_enabled: false,
    }));
  });
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

/** 获取当前数据集 SubAgent Manifest 治理详情 */
export function getDatasetSubAgentManifest(datasetId) {
  return get(`/api/dataset/${datasetId}/subagent-manifest`);
}

/** 保存当前数据集 SubAgent Manifest 草稿 */
export function saveDatasetSubAgentManifest(datasetId, manualFields) {
  return put(`/api/dataset/${datasetId}/subagent-manifest`, {
    manual_fields: manualFields,
  });
}

/** 发布当前数据集 SubAgent Manifest */
export function publishDatasetSubAgentManifest(datasetId, manualFields = null) {
  return post(`/api/dataset/${datasetId}/subagent-manifest/publish`, {
    manual_fields: manualFields,
  });
}

/** 回滚历史 SubAgent Manifest 为新的 current 版本 */
export function rollbackDatasetSubAgentManifest(datasetId, manifestVersion, reason = '') {
  return post(`/api/dataset/${datasetId}/subagent-manifest/${encodeURIComponent(manifestVersion)}/rollback`, {
    reason,
  });
}

/** 当前数据集 SubAgent Manifest 路由自检 */
export function routeCheckDatasetSubAgentManifest(datasetId, questions, expected = null) {
  return post(`/api/dataset/${datasetId}/subagent-manifest/route-check`, {
    questions,
    expected,
  });
}

/** 获取所有 current SubAgent Manifest 摘要 */
export function listCurrentSubAgentManifests() {
  return get('/api/dataset/subagent-manifests/current');
}

/** 同步数据源指定 Schema 的表结构 */
export function syncDatasourceTables(datasourceId, schema) {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return post(`/api/datasource/${datasourceId}/sync-tables${qs}`);
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

/** 获取语义验证用例列表 */
export function listSemanticValidationCases(datasetId, limit = 20) {
  return get(`/api/dataset/${datasetId}/validation-cases?limit=${encodeURIComponent(limit)}`);
}

/** 保存语义验证用例 */
export function createSemanticValidationCase(datasetId, data) {
  return post(`/api/dataset/${datasetId}/validation-cases`, data);
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
