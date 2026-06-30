// workbench-route.jsx
// 隐藏 Workbench 路由入口，复用 Chat 右侧 WorkbenchPanel 的同一套 View Model。

import React from 'react';
import { useParams } from 'react-router-dom';
import { normalizeWorkbenchThreadId } from '../assistant/workbench-api';
import WorkbenchPanel from './workbench-panel';

export default function WorkbenchRoute() {
  const { threadId, artifactRef } = useParams();
  const normalizedThreadId = normalizeWorkbenchThreadId(threadId);

  return (
    <div className="workbench-route">
      <WorkbenchPanel threadId={normalizedThreadId} initialArtifactRef={artifactRef || null} />
    </div>
  );
}
