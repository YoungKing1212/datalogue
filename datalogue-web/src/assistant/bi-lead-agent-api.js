// BI LeadAgent API client
// 只封装前端需要的 run 生命周期端点；错误统一转成安全文本，避免把 response 内部细节暴露到界面层。

async function parseResponse(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    // 失败时只使用后端显式给出的业务摘要或状态码，避免泄露 url/header/statusText 等内部调试信息。
    throw new Error(payload?.detail || payload?.message || `BI LeadAgent API failed: ${response.status}`);
  }
  return payload;
}

async function postJson(url, body = undefined) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }), // handoff 不发送空 JSON，保持后端动作语义干净。
  });
  return parseResponse(response);
}

export function createBILeadAgentRun(payload) {
  return postJson('/api/bi-lead-agent/runs', payload);
}

export function confirmBILeadAgentRun(runId, payload) {
  return postJson(`/api/bi-lead-agent/runs/${runId}/confirm`, payload);
}

export function handoffBILeadAgentRun(runId) {
  return postJson(`/api/bi-lead-agent/runs/${runId}/handoff`);
}

export async function getBILeadAgentRun(runId) {
  const response = await fetch(`/api/bi-lead-agent/runs/${runId}`);
  return parseResponse(response);
}
