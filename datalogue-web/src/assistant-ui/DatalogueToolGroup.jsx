// DatalogueToolGroup.jsx
// 将连续工具调用归组成可折叠区块，保持消息区信息密度。
// 展开策略：running / requires_action 默认展开；complete/error 默认折叠。
// 折叠键由上游 chat-adapter 提供（workerSessionId/replyId/agent+tool）。

import React from 'react';
import { normalizeStatus, statusLabel } from './message-parts';

function groupTitle(group) {
  if (group.agentRole === 'worker') {
    return group.agentName ? `Worker · ${group.agentName}` : 'Worker 工具执行';
  }
  if (group.agentRole === 'leader') {
    return 'Leader 工具执行';
  }
  return '工具执行';
}

export function DatalogueToolGroup({ group = {}, children }) {
  const status = normalizeStatus(group);
  const shouldExpand = status === 'running' || status === 'confirmation';
  const count = group.indices?.length ?? 0;

  return (
    <details className="artifact-card" open={shouldExpand} data-group-status={status}>
      <summary className="artifact-card-head">
        <span className="artifact-card-head-left">
          <strong>{groupTitle(group)}</strong>
          <span className={`artifact-card-status artifact-card-status-${status === 'failed' ? 'error' : status}`}>
            {statusLabel(status)}
          </span>
        </span>
        <span className="artifact-card-head-right">
          {count > 0 && <span className="artifact-card-summary">{count} 个步骤</span>}
        </span>
      </summary>
      <div className="artifact-card-body">{children}</div>
    </details>
  );
}

export default DatalogueToolGroup;
