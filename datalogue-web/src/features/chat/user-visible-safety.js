// Chat 流式事件与历史回放共用的浏览器可见边界，避免两条链路的禁用字段和文本判定继续漂移。

const USER_VISIBLE_TRACE_FORBIDDEN_KEYS = new Set([
  'sql', 'sql_result', 'sqlResult', 'sql_diagnosis', 'sqlDiagnosis',
  'sql_audit_result', 'sqlAuditResult', 'raw_sql', 'direct_sql', 'llm_sql',
  'compiled_sql', 'sql_list', 'candidate_assets', 'candidateAssets', 'dsl',
  'rows', 'columns', 'column_labels', 'columnLabels', 'schema', 'schemas',
  'table', 'tables', 'field', 'fields', 'raw_result', 'rawResult',
  'repair_patch', 'repairPatch', 'RepairPatch', 'node', 'display_name',
  'displayName', 'trace_only_metadata', 'traceOnlyMetadata',
  'replacement_field_ref', 'replacementFieldRef', 'raw_rows', 'rawRows',
  'debug_raw', 'debugRaw', 'raw_delta', 'rawDelta', 'blueprint', 'blueprints',
]);

const INTERNAL_TEXT_PATTERN = /\b(select|insert|update|delete|delete\s+from|from|join|where|group\s+by|order\s+by|having|union|with)\b|[`;]|hidden_table|\b\w+_col\b|raw_result|raw_row|schema/i;
const INTERNAL_PLANNING_PATTERN = /\b(the\s+user\s+wants?\s+to|let\s+me\s+break|i\s+need\s+to\s+create|worker\s+type\s+should\s+be|i\s+should\s+present|teamsay)\b/i;
const INTERNAL_PLANNING_COMPACT_MARKERS = [
  'theuserwantstoquery',
  'letmebreakthisdown',
  'ineedtocreate',
  'theworkertypeshouldbe',
  'bothhaveascore',
  'ishouldpresent',
  'taskcompletedteamdissolved',
];

export function sanitizeUserVisibleTrace(value) {
  if (Array.isArray(value)) return value.map(sanitizeUserVisibleTrace);
  if (!value || typeof value !== 'object') return value;
  const out = {};
  for (const [key, item] of Object.entries(value)) {
    if (USER_VISIBLE_TRACE_FORBIDDEN_KEYS.has(key)) continue;
    out[key] = sanitizeUserVisibleTrace(item);
  }
  return out;
}

export function looksLikeInternalPlanningText(value) {
  if (value == null) return false;
  const text = String(value).trim();
  if (!text) return false;
  const compact = text.toLowerCase().replace(/[^a-z0-9]/g, '');
  return INTERNAL_PLANNING_PATTERN.test(text)
    || INTERNAL_PLANNING_COMPACT_MARKERS.some((marker) => compact.includes(marker));
}

export function safeUserVisibleText(value, { maxLength = 160, rejectPlanning = false } = {}) {
  if (value == null) return null;
  const text = String(value).trim();
  if (!text || INTERNAL_TEXT_PATTERN.test(text)) return null;
  if (rejectPlanning && looksLikeInternalPlanningText(text)) return null;
  return text.slice(0, maxLength);
}

export function safeUserVisibleList(values, { limit = 6, rejectPlanning = false } = {}) {
  if (!Array.isArray(values)) return [];
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const text = safeUserVisibleText(value, { rejectPlanning });
    if (!text || seen.has(text)) continue;
    seen.add(text);
    result.push(text);
    if (result.length >= limit) break;
  }
  return result;
}
