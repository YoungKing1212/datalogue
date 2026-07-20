// Workbench API adapter
// 负责调用 C3 后端 View Model API；前端只消费业务级 view，不拼接内部执行细节。

import { authenticatedFetch } from '../api/client';

async function requestJson(path, options = {}) {
  const res = await authenticatedFetch(path, options);
  if (!res.ok) {
    let detail;
    try {
      const payload = await res.json();
      detail = typeof payload?.detail === 'string' ? payload.detail : payload?.detail?.message || '';
    } catch { /* 非 JSON 错误响应统一走状态码兜底文案。 */ }
    const error = new Error(detail || `工作台请求失败（HTTP ${res.status}）`);
    error.status = res.status;
    throw error;
  }
  return res.json();
}

export function normalizeWorkbenchThreadId(routeId) {
  if (routeId == null || routeId === '') return null;
  const value = String(routeId).trim();
  if (!value) return null;
  if (/^\d+$/.test(value)) return `conv_${value}`;
  if (value.startsWith('conv_') || value.startsWith('as_')) return value;
  return value;
}

export async function fetchWorkbenchThread(threadId) {
  const normalized = normalizeWorkbenchThreadId(threadId);
  if (!normalized) return null;
  return requestJson(`/api/workbench/thread/${encodeURIComponent(normalized)}`);
}

export async function fetchWorkbenchArtifact(artifactRef, threadId = null) {
  if (!artifactRef) return null;
  const query = threadId ? `?${new URLSearchParams({ thread_id: normalizeWorkbenchThreadId(threadId) }).toString()}` : '';
  return requestJson(`/api/workbench/artifact/${encodeURIComponent(artifactRef)}${query}`);
}

export async function requestWorkbenchRetry(payload = {}) {
  const body = {
    thread_id: payload.thread_id,
    message_id: payload.message_id,
    checkpoint_ref: payload.checkpoint_ref,
    selected_action: payload.selected_action || 'retry_last_step',
  };
  return requestJson('/api/workbench/actions/retry', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body), // 只发送受控 retry 所需 ref，丢弃 SQL/schema/raw rows 等调用方多余字段。
  });
}
