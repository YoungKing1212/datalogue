// WorkbenchRetentionEvents — Workbench 退役闸门的前端事件口径
// 这里不直接上报远端，只派发稳定 CustomEvent，后续 analytics/e2e/日志采集可按同一契约接入。

export const WORKBENCH_RETENTION_EVENT_TYPE = 'datalogue:workbench-retention-event';

export const RETENTION_UI_EVENT_NAMES = {
  artifactDetailExpected: 'artifact_detail_expected',
  artifactDetailView: 'artifact_detail_view',
};

function safeText(value) {
  const text = String(value ?? '').trim();
  return text || null;
}

function actionType(action) {
  return safeText(action?.action_type || action?.actionType || action?.action_id || action?.actionId);
}

function actionRef(action) {
  return safeText(action?.ref || action?.payload_ref || action?.payloadRef || action?.checkpoint_ref || action?.checkpointRef);
}

function isDetailAction(action) {
  const type = actionType(action);
  return (type === 'view' || type === 'open_ref') && action?.disabled !== true && action?.enabled !== false;
}

function cardPrimaryRef(artifactCard) {
  if (!artifactCard || typeof artifactCard !== 'object') return null;
  const refs = Array.isArray(artifactCard.refs) ? artifactCard.refs : [];
  const firstRef = refs[0];
  if (typeof firstRef === 'string') return safeText(firstRef);
  return safeText(
    artifactCard.primary_ref
    || artifactCard.primaryRef
    || firstRef?.ref
    || firstRef?.ref_id
    || firstRef?.artifact_ref
    || firstRef?.artifactRef,
  );
}

export function artifactDetailRefFromCard(artifactCard) {
  if (!artifactCard || typeof artifactCard !== 'object') return null;
  const actions = Array.isArray(artifactCard.actions) ? artifactCard.actions : [];
  const detailAction = actions.find(isDetailAction);
  return actionRef(detailAction) || cardPrimaryRef(artifactCard);
}

export function hasExpectedArtifactDetailProjection(artifactCard) {
  return Boolean(artifactDetailRefFromCard(artifactCard));
}

function currentRoutePath() {
  if (typeof window === 'undefined') return null;
  return safeText(window.location?.pathname) || null;
}

export function buildArtifactDetailExpectedEvent({
  artifactCard,
  messageId = null,
  routePath = currentRoutePath(),
} = {}) {
  const artifactRef = artifactDetailRefFromCard(artifactCard);
  if (!artifactRef) return null;
  return {
    event_name: RETENTION_UI_EVENT_NAMES.artifactDetailExpected,
    route_path: routePath,
    source_kind: 'ordinary_chat',
    artifact_ref: artifactRef,
    message_id: messageId,
    artifact_detail_expected: true,
    count: 1,
  };
}

export function buildArtifactDetailViewEvent({
  artifactRef,
  messageId = null,
  routePath = currentRoutePath(),
  status = 'opened',
} = {}) {
  const ref = safeText(artifactRef);
  if (!ref) return null;
  return {
    event_name: RETENTION_UI_EVENT_NAMES.artifactDetailView,
    route_path: routePath,
    source_kind: 'ordinary_chat',
    artifact_ref: ref,
    message_id: messageId,
    artifact_detail_visible: true,
    status,
    count: 1,
  };
}

export function emitWorkbenchRetentionUiEvent(detail) {
  if (!detail || typeof window === 'undefined') return false;
  window.dispatchEvent(new CustomEvent(WORKBENCH_RETENTION_EVENT_TYPE, { detail }));
  return true;
}

