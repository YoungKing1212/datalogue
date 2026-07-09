// DatalogueSubAgentMessages.jsx
// 阶段 4：多智能体嵌套消息的本地只读渲染入口。
//
// 数据来源：chat-adapter 生成的 sub-agent ThreadMessage 数组
// （见 metadata.custom.subAgentMessages，也会同步挂到 ToolCallMessagePart.messages）。
// 每条 sub-agent message 对齐 assistant-ui ThreadMessage：
//   { id, role: 'assistant', content: [reasoning | tool-call], status, metadata.custom }
//
// 展示策略：
//   - 折叠头：Worker · <agentName>，副标题带步骤数；
//   - 折叠体：递归复用 DatalogueReasoning / DatalogueToolUI；
//   - 不引入 ArtifactCard 或 DataMessagePart 分支，避免主线卡片重复。
//
// 安全约束：sub-agent parts 已经在 chat-adapter 层做过白名单收敛，
// 这里只做纯展示，不再引入 SQL / schema / raw_rows / query_plan 通道。

import React from 'react';
import { DatalogueReasoning } from './DatalogueReasoning';
import { DatalogueToolUI } from './DatalogueToolUI';
import { normalizeStatus, statusLabel } from './message-parts';

function subAgentTitle(message) {
  const custom = message?.metadata?.custom || {};
  const role = String(custom.agentRole || '').toLowerCase();
  const name = custom.agentName || '';
  if (role === 'worker') return name ? `Worker · ${name}` : 'Worker 协作';
  if (role === 'leader') return name ? `Leader · ${name}` : 'Leader 协作';
  return name || 'Agent 协作';
}

function renderSubAgentPart(part, index) {
  if (!part) return null;
  if (part.type === 'reasoning') {
    return <DatalogueReasoning key={`sub-reasoning-${index}`} part={part} />;
  }
  if (part.type === 'tool-call') {
    return <DatalogueToolUI key={`sub-tool-${index}`} part={part} />;
  }
  // text/data 走不到这里；sub-agent messages 只承载 reasoning / tool-call。
  return null;
}

function SubAgentMessage({ message }) {
  const status = normalizeStatus(message);
  const shouldExpand = status === 'running' || status === 'confirmation';
  const parts = Array.isArray(message?.content) ? message.content : [];
  const stepCount = parts.length;

  return (
    <details className="artifact-card sub-agent-message" open={shouldExpand} data-sub-agent-status={status}>
      <summary className="artifact-card-head">
        <span className="artifact-card-head-left">
          <strong>{subAgentTitle(message)}</strong>
          <span className={`artifact-card-status artifact-card-status-${status === 'failed' ? 'error' : status}`}>
            {statusLabel(status)}
          </span>
        </span>
        <span className="artifact-card-head-right">
          {stepCount > 0 && <span className="artifact-card-summary">{stepCount} 步</span>}
        </span>
      </summary>
      <div className="artifact-card-body">{parts.map(renderSubAgentPart)}</div>
    </details>
  );
}

/**
 * DatalogueSubAgentMessages
 *
 * @param {object} props
 * @param {Array} props.messages - assistant-ui ThreadMessage[] shape 的 sub-agent 消息数组。
 */
export function DatalogueSubAgentMessages({ messages = [] }) {
  if (!Array.isArray(messages) || messages.length === 0) return null;
  return (
    <div className="sub-agent-messages" data-testid="sub-agent-messages">
      {messages.map((message) => (
        <SubAgentMessage key={message?.id || message?.metadata?.custom?.workerSessionId} message={message} />
      ))}
    </div>
  );
}

export default DatalogueSubAgentMessages;
