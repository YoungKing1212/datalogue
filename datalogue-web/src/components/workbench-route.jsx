// workbench-route.jsx
// 隐藏 Workbench 路由入口，仅作为受控恢复壳使用；普通 Chat 不再默认挂载该面板。

import React from 'react';
import { useParams } from 'react-router-dom';
import { normalizeWorkbenchThreadId } from '../assistant/workbench-api';
import {
  classifyWorkbenchMountSource,
  isAllowedWorkbenchRecoverySource,
} from '../assistant/workbench-mount-source';
import WorkbenchPanel from './workbench-panel';

export default function WorkbenchRoute() {
  const { threadId, artifactRef } = useParams();
  const normalizedThreadId = normalizeWorkbenchThreadId(threadId);
  const mountSource = classifyWorkbenchMountSource({
    route_path: artifactRef ? `/workbench/${threadId}/${artifactRef}` : `/workbench/${threadId}`,
    routeId: normalizedThreadId,
    remoteId: normalizedThreadId,
    source_kind: artifactRef ? 'legacy_mirror' : 'hidden_recovery_shell',
    is_hidden_recovery: !artifactRef,
    deep_link_intent: false,
  });

  if (!isAllowedWorkbenchRecoverySource(mountSource)) return null;

  return (
    <div className="workbench-route">
      <WorkbenchPanel threadId={normalizedThreadId} initialArtifactRef={artifactRef || null} />
    </div>
  );
}
