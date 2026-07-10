// workbench-mount-source.js
// 统一判定 Workbench 的挂载来源：普通 Chat、历史会话、隐藏恢复壳、旧镜像或显式恢复。
// 这层判定必须 fail-closed，避免仅凭 conv_/as_ ID 就把普通 Chat 误当成 Workbench 入口。

const ORDINARY_SOURCE_KINDS = new Set(['ordinary_chat', 'ordinary_chat_history']);
const RECOVERY_SOURCE_KINDS = new Set(['hidden_recovery_shell', 'legacy_mirror', 'explicit_recovery']);

function normalizeText(value) {
  const text = String(value ?? '').trim();
  return text || null;
}

function normalizeRoutePath(routePath) {
  const path = normalizeText(routePath);
  return path && path.startsWith('/') ? path : null;
}

function normalizeSourceKind(sourceKind) {
  const kind = normalizeText(sourceKind);
  return kind && (ORDINARY_SOURCE_KINDS.has(kind) || RECOVERY_SOURCE_KINDS.has(kind)) ? kind : null;
}

function pathSuggestsWorkbenchShell(routePath) {
  return Boolean(routePath && routePath.startsWith('/workbench'));
}

function pathSuggestsChat(routePath) {
  return Boolean(routePath && routePath.startsWith('/chat'));
}

function routeSuggestsHistory(routePath, routeId) {
  if (!pathSuggestsChat(routePath)) return false;
  return Boolean(normalizeText(routeId));
}

/**
 * 判定当前挂载来源。
 *
 * @returns {'ordinary_chat'|'ordinary_chat_history'|'hidden_recovery_shell'|'legacy_mirror'|'explicit_recovery'|null}
 */
export function classifyWorkbenchMountSource({
  route_path: routePath,
  routeId,
  remoteId,
  source_kind: sourceKind,
  is_hidden_recovery: isHiddenRecovery = false,
  deep_link_intent: deepLinkIntent = false,
} = {}) {
  const normalizedRoutePath = normalizeRoutePath(routePath);
  const normalizedSourceKind = normalizeSourceKind(sourceKind);
  const normalizedRouteId = normalizeText(routeId);
  const normalizedRemoteId = normalizeText(remoteId);
  const hiddenRecovery = Boolean(isHiddenRecovery);
  const deepLink = Boolean(deepLinkIntent);

  const pathFamily = pathSuggestsWorkbenchShell(normalizedRoutePath)
    ? 'workbench'
    : pathSuggestsChat(normalizedRoutePath)
      ? 'chat'
      : null;

  if (pathFamily === 'chat') {
    const expectedKind = routeSuggestsHistory(normalizedRoutePath, normalizedRouteId || normalizedRemoteId)
      ? 'ordinary_chat_history'
      : 'ordinary_chat';
    if (normalizedSourceKind && normalizedSourceKind !== expectedKind) return null;
    return normalizedSourceKind || expectedKind;
  }

  if (pathFamily === 'workbench') {
    const expectedKind = hiddenRecovery
      ? 'hidden_recovery_shell'
      : deepLink
        ? 'explicit_recovery'
        : (normalizedRouteId || normalizedRemoteId)
          ? 'legacy_mirror'
          : null;
    if (!expectedKind) return null;
    if (normalizedSourceKind && normalizedSourceKind !== expectedKind) return null;
    return normalizedSourceKind || expectedKind;
  }

  if (normalizedSourceKind) return normalizedSourceKind;
  if (hiddenRecovery) return 'hidden_recovery_shell';
  if (deepLink) return 'explicit_recovery';
  return null;
}

export function isAllowedWorkbenchRecoverySource(sourceKind) {
  return RECOVERY_SOURCE_KINDS.has(normalizeSourceKind(sourceKind));
}
