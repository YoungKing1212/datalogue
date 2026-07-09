// message-parts.js
// Datalogue assistant-ui 消息组件的安全摘要、状态和引用归一化工具。

export const UNSAFE_FIELD_NAMES = new Set([
  'sql',
  'raw_sql',
  'direct_sql',
  'compiled_sql',
  'schema',
  'schemas',
  'table',
  'tables',
  'field',
  'fields',
  'rows',
  'raw_rows',
  'rawRows',
  'raw_result',
  'rawResult',
  'repair_patch',
  'repairPatch',
  'patch',
  'dsl',
  'control_plane',
  'controlPlane',
]);

const UNSAFE_TEXT_RE =
  /\b(select|insert|update|delete|from|join|where|group\s+by|order\s+by|having|union|with|schema|raw_rows|raw_result|repair_patch|control_plane|dsl)\b|[`;]/i;

// safeMarkdownText 专用：允许 Markdown 常用符号（反引号短代码、分号），
// 只拦截控制面 / 查询计划关键字，保证 reasoning summary 可以用 Markdown 表达列表 / 链接 / 短代码块。
const UNSAFE_MARKDOWN_RE =
  /\b(select|insert|update|delete|from|join|where|group\s+by|order\s+by|having|union|schema|raw_rows|raw_result|repair_patch|control_plane|query_plan|dsl)\b/i;

const THINK_BLOCK_RE = /<think\b[^>]*>[\s\S]*?(?:<\/think\s*>|$)/gi;
// 捕获 <think> 内容的正则（惰性匹配到闭合标签或流式末尾），用于剥离时同步收集正文外的自吐推理。
const THINK_CAPTURE_RE = /<think\b[^>]*>([\s\S]*?)(?:<\/think\s*>|$)/gi;
const MAX_TEXT_LENGTH = 220;
const MAX_REF_LENGTH = 160;

export function stripThinkBlocks(value = '') {
  return String(value || '').replace(THINK_BLOCK_RE, '').trim();
}

export function balanceMarkdownFences(value = '') {
  const text = String(value || '');
  const fences = (text.match(/```/g) || []).length;
  return fences % 2 === 1 ? `${text}\n\`\`\`` : text;
}

/**
 * sanitizeThinkAndMarkdown —— 统一的 <think> 剥离 + Markdown 预处理入口。
 *
 * 用于让旧 MyMessage 和新 DatalogueMessage / DatalogueReasoning 共用同一份
 * <think> 处理逻辑，避免正文和思考折叠框之间行为漂移。
 *
 * 返回：
 * - mainMarkdown: 去掉全部 <think>...</think> 之后的正文（未闭合的 <think> 也会
 *   被剥离，防止流式中间态把后续内容一起吞掉）；同时补齐奇数个 ``` 围栏。
 * - thinkBlocks: 每个 <think> 块内部内容按顺序返回；空块自动丢弃。这些内容
 *   仅供 reasoning 折叠框展示，且必须显式标注是模型自吐 <think>，不是后端
 *   经过治理的安全 reasoning_summary。
 */
export function sanitizeThinkAndMarkdown(value = '') {
  const raw = String(value ?? '');
  const thinkBlocks = [];
  const stripped = raw.replace(THINK_CAPTURE_RE, (_, inner) => {
    const text = String(inner || '').trim();
    if (text) thinkBlocks.push(text);
    return '';
  });
  return {
    mainMarkdown: balanceMarkdownFences(stripped.trim()),
    thinkBlocks,
  };
}

export function preprocessDatalogueMarkdown(value = '') {
  return sanitizeThinkAndMarkdown(value).mainMarkdown;
}

export function isUnsafeKey(key) {
  const value = String(key || '');
  const lowered = value.toLowerCase();
  return (
    UNSAFE_FIELD_NAMES.has(value)
    || UNSAFE_FIELD_NAMES.has(lowered)
    || lowered.includes('sql')
    || lowered.includes('schema')
    || lowered.includes('raw')
    || lowered.includes('queryplan')
    || lowered.includes('repairpatch')
    || lowered.includes('repair_patch')
    || lowered.includes('control')
    || lowered.includes('dsl')
    || lowered.includes('patch')
  );
}

export function safeVisibleText(value, fallback = null) {
  if (value == null) return fallback;
  const text = stripThinkBlocks(String(value)).replace(/\s+/g, ' ').trim();
  if (!text || UNSAFE_TEXT_RE.test(text)) return fallback;
  return text.length > MAX_TEXT_LENGTH ? `${text.slice(0, MAX_TEXT_LENGTH)}...` : text;
}

export function firstSafeText(values, fallback = null) {
  for (const value of values) {
    const text = safeVisibleText(value);
    if (text) return text;
  }
  return fallback;
}

/**
 * safeMarkdownText —— 保留换行/多空白的安全 Markdown 文本。
 *
 * 与 safeVisibleText 的区别：不把连续空白折叠成一个空格，用于 reasoning
 * summary 这类希望渲染为 Markdown 列表 / 表格 / 短代码块的字段。仍然会先
 * 剥离 <think> 段并按 UNSAFE_TEXT_RE 拒绝 SQL / schema / raw_rows / query_plan
 * 等控制面关键字，避免通过 Markdown 通道回落到界面上。
 */
export function safeMarkdownText(value, fallback = null) {
  if (value == null) return fallback;
  const stripped = stripThinkBlocks(String(value));
  if (!stripped) return fallback;
  if (UNSAFE_MARKDOWN_RE.test(stripped)) return fallback;
  return stripped;
}

/**
 * firstSafeMarkdown —— 按顺序挑选第一个安全的 Markdown 源。
 * 用于 DatalogueReasoning 的 reasoning_summary > text > <think> 兜底优先级。
 */
export function firstSafeMarkdown(values, fallback = null) {
  for (const value of values) {
    const text = safeMarkdownText(value);
    if (text) return text;
  }
  return fallback;
}

export function safeNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

export function elapsedLabel(value) {
  const number = safeNumber(value);
  if (number == null) return null;
  return `${Math.round(number)}ms`;
}

function refValue(value) {
  if (!value) return null;
  if (typeof value === 'string') return value;
  if (typeof value !== 'object') return null;
  return (
    value.ref
    || value.ref_id
    || value.refId
    || value.artifact_ref
    || value.artifactRef
    || value.checkpoint_ref
    || value.checkpointRef
    || value.run_id
    || value.runId
    || null
  );
}

export function collectSafeRefs(...sources) {
  const seen = new Set();
  const refs = [];
  const visit = (source) => {
    if (!source) return;
    if (Array.isArray(source)) {
      source.forEach(visit);
      return;
    }
    const ref = refValue(source);
    const text = safeVisibleText(ref);
    if (!text || text.length > MAX_REF_LENGTH || seen.has(text)) return;
    seen.add(text);
    refs.push(text);
  };
  sources.forEach(visit);
  return refs.slice(0, 6);
}

export function safeObjectLookup(source, names) {
  if (!source || typeof source !== 'object') return null;
  for (const name of names) {
    if (isUnsafeKey(name)) continue;
    const value = source[name];
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return null;
}

export function normalizeStatus(partOrStatus, result = {}) {
  const rawStatus =
    typeof partOrStatus === 'string'
      ? partOrStatus
      : partOrStatus?.status?.type || partOrStatus?.status || result?.status || result?.state || '';
  const value = String(rawStatus || '').toLowerCase();
  if (
    value === 'requires-action'
    || value === 'requires_action'
    || value === 'confirmation'
    || value === 'confirm'
  ) {
    return 'confirmation';
  }
  if (value === 'running' || value === 'pending' || value === 'in_progress' || value === 'generating') {
    return 'running';
  }
  if (value === 'failed' || value === 'error' || value === 'incomplete') return 'failed';
  if (value === 'blocked' || value === 'cancelled' || value === 'canceled') return 'blocked';
  if (value === 'completed' || value === 'complete' || value === 'success' || value === 'done') {
    return 'completed';
  }
  return result?.requires_user_confirmation || result?.requiresUserConfirmation ? 'confirmation' : 'completed';
}

export const STATUS_LABELS = {
  running: '运行中',
  completed: '已完成',
  failed: '执行失败',
  blocked: '已阻塞',
  confirmation: '需要确认',
};

export function statusLabel(status) {
  return STATUS_LABELS[status] || STATUS_LABELS.completed;
}

export function partMetadata(part = {}) {
  return part.metadata || part.meta || {};
}

export function partResult(part = {}) {
  const result = part.result || part.output || part.data || {};
  return result && typeof result === 'object' ? result : {};
}

export function rowCountFrom(...sources) {
  for (const source of sources) {
    const count = safeNumber(
      source?.row_count
        ?? source?.rowCount
        ?? source?.rows_count
        ?? source?.rowsCount
        ?? source?.result_count
        ?? source?.resultCount,
    );
    if (count != null) return count;
  }
  return null;
}

export function toolDisplayName(name) {
  const value = String(name || '').trim();
  const labels = {
    dataset_query: '数据查询',
    query_dataset: '数据查询',
    sql_execute: '查询执行',
    compile_query: '查询编译',
    list_assets: '资产匹配',
    get_status: '状态检查',
    artifact: '产物生成',
  };
  return labels[value] || safeVisibleText(value, '工具调用');
}
