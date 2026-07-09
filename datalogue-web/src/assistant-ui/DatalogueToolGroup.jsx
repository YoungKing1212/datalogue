// DatalogueToolGroup.jsx
// 将连续工具调用归组成可折叠区块，保持消息区信息密度。

import React from 'react';
import { normalizeStatus, statusLabel } from './message-parts';

export function DatalogueToolGroup({ group = {}, children }) {
  const status = normalizeStatus(group);
  const running = status === 'running';
  const count = group.indices?.length ?? 0;

  return (
    <details className="artifact-card" open={running || status === 'confirmation'}>
      <summary className="artifact-card-head">
        <span className="artifact-card-head-left">
          <strong>工具执行</strong>
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
