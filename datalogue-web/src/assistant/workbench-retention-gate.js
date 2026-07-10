// WorkbenchRetentionGate — Workbench 去常驻化的机器可判定闸门
// 只汇总窗口内的 UI/API 流量与 Chat 侧 artifact 详情承接情况，不回看 Workbench 旧日志语义。

import {
  RETENTION_UI_EVENT_NAMES,
  hasExpectedArtifactDetailProjection,
} from './workbench-retention-events.js';

const ALLOWED_RECOVERY_SOURCE_KINDS = new Set([
  'hidden_recovery_shell',
  'legacy_mirror',
  'explicit_recovery',
]);

const MAIN_PATH_SOURCE_KINDS = new Set([
  'ordinary_chat',
  'ordinary_chat_history',
]);

const ARTIFACT_DETAIL_EXPECTED_EVENT_NAMES = new Set([
  'artifact_card_projection',
  'artifact_card_expected_detail',
  RETENTION_UI_EVENT_NAMES.artifactDetailExpected,
]);

const ARTIFACT_DETAIL_ACTUAL_EVENT_NAMES = new Set([
  RETENTION_UI_EVENT_NAMES.artifactDetailView,
  'artifact_detail_click',
  'artifact_card_view',
  'artifact_card_detail_view',
]);

function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function toCount(event) {
  const candidates = [
    event?.count,
    event?.total,
    event?.value,
    event?.event_count,
    event?.request_count,
  ];
  for (const candidate of candidates) {
    if (isFiniteNumber(candidate) && candidate > 0) return candidate;
  }
  return 1;
}

function sumBy(events, predicate) {
  return (Array.isArray(events) ? events : []).reduce((total, event) => {
    if (!predicate(event)) return total;
    return total + toCount(event);
  }, 0);
}

function normalizeIsoTimestamp(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function windowSpanDays(windowStart, windowEnd) {
  const start = normalizeIsoTimestamp(windowStart);
  const end = normalizeIsoTimestamp(windowEnd);
  if (!start || !end) return null;
  return (end.getTime() - start.getTime()) / 86400000;
}

function isMainPathSourceKind(sourceKind) {
  return MAIN_PATH_SOURCE_KINDS.has(String(sourceKind || '').trim());
}

function isRecoverySourceKind(sourceKind) {
  return ALLOWED_RECOVERY_SOURCE_KINDS.has(String(sourceKind || '').trim());
}

function isExcludedFromMainPath(event) {
  return Boolean(event?.is_test_bot || event?.is_crawler || event?.is_hidden_recovery);
}

function isWorkbenchApiPath(path) {
  return String(path || '').startsWith('/api/workbench/');
}

function isWorkbenchUiPath(path) {
  return String(path || '').startsWith('/workbench/');
}

function isChatArtifactApiPath(path) {
  return String(path || '').startsWith('/api/artifacts/');
}

function isChatUiPath(path) {
  return String(path || '').startsWith('/chat');
}

function isChatSideUiEvent(event) {
  return (
    isChatUiPath(event?.route_path)
    && isMainPathSourceKind(event?.source_kind)
    && !isExcludedFromMainPath(event)
  );
}

function isChatSideArtifactApiEvent(event) {
  return (
    isChatArtifactApiPath(event?.api_path)
    && isMainPathSourceKind(event?.source_kind)
    && !isExcludedFromMainPath(event)
  );
}

function countExpectedArtifactDetails(input, uiEvents) {
  if (isFiniteNumber(input?.expected_artifact_detail_total)) {
    return input.expected_artifact_detail_total;
  }
  return sumBy(uiEvents, (event) => {
    // 去常驻化只认可普通 Chat 的 artifact 详情投影，恢复壳/旧镜像不能反向证明主路径已承接。
    if (!isChatSideUiEvent(event)) return false;
    if (event?.artifact_detail_expected === true || event?.expected_artifact_detail === true) return true;
    if (ARTIFACT_DETAIL_EXPECTED_EVENT_NAMES.has(String(event?.event_name || ''))) return true;
    const artifactCard = event?.artifact_card || event?.artifactCard;
    return hasExpectedArtifactDetailProjection(artifactCard); // 只统计 Chat 侧确实可点开的详情投影，避免把纯摘要卡误算为“应出现详情”。
  });
}

function countActualArtifactDetails(uiEvents, apiEvents) {
  const uiTotal = sumBy(uiEvents, (event) => (
    isChatSideUiEvent(event)
    && (
      event?.artifact_detail_visible === true
      || event?.artifact_detail_shown === true
      || ARTIFACT_DETAIL_ACTUAL_EVENT_NAMES.has(String(event?.event_name || ''))
    )
  ));
  const apiTotal = sumBy(apiEvents, isChatSideArtifactApiEvent);
  return uiTotal + apiTotal;
}

function buildReason(kind, message) {
  return `${kind}: ${message}`;
}

export function evaluateWorkbenchRetentionGate(input = {}) {
  const uiEvents = Array.isArray(input.ui_events) ? input.ui_events : [];
  const apiEvents = Array.isArray(input.api_events) ? input.api_events : [];
  const windowDays = windowSpanDays(input.window_start, input.window_end);

  const apiWorkbenchMainPathTotal = sumBy(apiEvents, (event) => (
    isWorkbenchApiPath(event?.api_path)
    && isMainPathSourceKind(event?.source_kind)
    && !isExcludedFromMainPath(event)
  ));
  const uiWorkbenchMainPathTotal = sumBy(uiEvents, (event) => (
    String(event?.event_name || '') === 'page_view'
    && isWorkbenchUiPath(event?.route_path)
    && isMainPathSourceKind(event?.source_kind)
    && !isExcludedFromMainPath(event)
  ));
  const apiWorkbenchRecoveryTotal = sumBy(apiEvents, (event) => (
    isWorkbenchApiPath(event?.api_path)
    && isRecoverySourceKind(event?.source_kind)
  ));
  const uiWorkbenchRecoveryTotal = sumBy(uiEvents, (event) => (
    String(event?.event_name || '') === 'page_view'
    && isWorkbenchUiPath(event?.route_path)
    && isRecoverySourceKind(event?.source_kind)
  ));
  const mainPathTotal = apiWorkbenchMainPathTotal + uiWorkbenchMainPathTotal;
  const expectedArtifactDetailTotal = countExpectedArtifactDetails(input, uiEvents);
  const chatArtifactDetailTotal = countActualArtifactDetails(uiEvents, apiEvents);

  const reasons = [];
  if (windowDays == null) {
    reasons.push(buildReason('window_invalid', 'window_start 或 window_end 不是有效的 UTC ISO 8601 时间戳'));
  } else if (windowDays < 14) {
    reasons.push(buildReason('window_too_short', `时间窗仅 ${windowDays.toFixed(2)} 天，未达到 14 天`));
  }
  if (mainPathTotal !== 0) {
    reasons.push(buildReason('main_path_non_zero', `主路径流量仍有 ${mainPathTotal} 次`));
  }
  if (chatArtifactDetailTotal !== expectedArtifactDetailTotal) {
    reasons.push(
      buildReason(
        'artifact_detail_mismatch',
        `Chat 侧详情承接 ${chatArtifactDetailTotal} 次，与应出现详情 ${expectedArtifactDetailTotal} 次不一致`,
      ),
    );
  }

  return {
    pass: reasons.length === 0,
    metrics: {
      main_path_total: mainPathTotal,
      api_workbench_main_path_total: apiWorkbenchMainPathTotal,
      ui_workbench_main_path_total: uiWorkbenchMainPathTotal,
      api_workbench_recovery_total: apiWorkbenchRecoveryTotal,
      ui_workbench_recovery_total: uiWorkbenchRecoveryTotal,
      chat_artifact_detail_total: chatArtifactDetailTotal,
      expected_artifact_detail_total: expectedArtifactDetailTotal,
    },
    reasons,
  };
}
