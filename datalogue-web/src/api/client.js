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

// ── 具体业务 API ─────────────────────────────────────

/** 获取对话列表 */
export function listConversations() {
  return get('/api/conversation');
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

/** 获取数据源 Schema */
export function getDatasourceSchema(id) {
  return get(`/api/datasource/${id}/schema`);
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
