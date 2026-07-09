// DatalogueMessage.jsx
// 统一承接 User/Assistant 消息展示；当前仅作为组件层入口，不接线到 chat-page。

import React from 'react';
import { MessagePrimitive, groupPartByType, useAuiState } from '@assistant-ui/react';
import ArtifactCard from '../components/artifact-card';
import { DatalogueDataUI } from './DatalogueDataUI';
import { DatalogueMarkdown } from './DatalogueMarkdown';
import { DatalogueReasoning } from './DatalogueReasoning';
import { DatalogueSubAgentMessages } from './DatalogueSubAgentMessages';
import { DatalogueToolGroup } from './DatalogueToolGroup';
import { DatalogueToolUI } from './DatalogueToolUI';

const groupByDatalogueParts = groupPartByType({
  reasoning: ['group-chainOfThought', 'group-reasoning'],
  'tool-call': ['group-chainOfThought', 'group-tool'],
  'standalone-tool-call': [],
});

function messageRole(message) {
  return message?.role === 'user' ? 'user' : 'assistant';
}

function messageStatus(message) {
  const type = message?.status?.type || message?.status || '';
  return type === 'running' ? '正在生成...' : '已生成';
}

function customMetadata(message) {
  return message?.metadata?.custom || message?.custom || {};
}

// 阶段 4：从 metadata.custom.subAgentMessages 与 tool-call parts 的 `messages` 中
// 收敛去重后的 sub-agent messages。首选 metadata（chat-adapter 生成的全集），tool-call
// 的 messages 是 assistant-ui ToolCallMessagePart 契约补齐——两者按 workerSessionId 去重。
function collectSubAgentMessages(custom = {}, parts = []) {
  const seen = new Set();
  const result = [];
  const push = (message) => {
    if (!message) return;
    const workerSessionId = message?.metadata?.custom?.workerSessionId || message?.id;
    if (!workerSessionId || seen.has(workerSessionId)) return;
    seen.add(workerSessionId);
    result.push(message);
  };
  const metadataList = Array.isArray(custom?.subAgentMessages) ? custom.subAgentMessages : [];
  metadataList.forEach(push);
  parts.forEach((part) => {
    if (!part || part.type !== 'tool-call') return;
    const nested = Array.isArray(part.messages) ? part.messages : [];
    nested.forEach(push);
  });
  return result;
}

function renderLegacyPart(part, index) {
  if (!part) return null;
  if (part.type === 'text') {
    return (
      <DatalogueMarkdown
        key={`text-${index}`}
        text={part.text || ''}
        className="ai-message md-body"
      />
    );
  }
  if (part.type === 'reasoning') {
    return <DatalogueReasoning key={`reasoning-${index}`} part={part} />;
  }
  if (part.type === 'tool-call' || part.type === 'tool') {
    return <DatalogueToolUI key={`tool-${index}`} part={part} />;
  }
  if (part.type === 'data') {
    return <DatalogueDataUI key={`data-${index}`} part={part} />;
  }
  if (part.type === 'artifact') {
    return <ArtifactCard key={`artifact-${index}`} artifact={part.artifact || part} />;
  }
  return null;
}

function RuntimeParts() {
  return (
    <MessagePrimitive.GroupedParts groupBy={groupByDatalogueParts}>
      {({ part, children }) => {
        switch (part.type) {
          case 'group-chainOfThought':
            return <div className="cot">{children}</div>;
          case 'group-reasoning':
            return <DatalogueReasoning part={part} group={part}>{children}</DatalogueReasoning>;
          case 'group-tool':
            return <DatalogueToolGroup group={part}>{children}</DatalogueToolGroup>;
          case 'text':
            return <DatalogueMarkdown />;
          case 'reasoning':
            return <DatalogueReasoning part={part} />;
          case 'tool-call':
            return <DatalogueToolUI part={part} />;
          case 'data':
            return <DatalogueDataUI part={part} />;
          default:
            return null;
        }
      }}
    </MessagePrimitive.GroupedParts>
  );
}

function DatalogueMessageBody({ message }) {
  const role = messageRole(message);
  const custom = customMetadata(message);
  const parts = Array.isArray(message?.content)
    ? message.content
    : Array.isArray(message?.parts)
      ? message.parts
      : [];
  // 兼容旧路径：只有当消息里没有 datalogue-artifact-card DataMessagePart 时，才回退
  // 使用 metadata.custom.artifactCard，避免同一个卡片渲染两次。
  const hasArtifactDataPart = parts.some(
    (part) => part && part.type === 'data' && part.name === 'datalogue-artifact-card',
  );
  // 阶段 4：sub-agent 消息优先取 metadata.custom.subAgentMessages（chat-adapter 生成），
  // 否则从 tool-call parts 的 `messages` 字段（assistant-ui ToolCallMessagePart.messages 契约）
  // 合并去重，避免同一 workerSessionId 重复渲染。
  const subAgentMessages = collectSubAgentMessages(custom, parts);

  return (
    <>
      <div className={role === 'user' ? 'msg-row msg-user' : 'msg-row msg-ai'}>
        {role === 'assistant' && (
          <div className="ai-head">
            <div className="ai-mark" />
            <span className="name">数语</span>
            <span className="stage">{messageStatus(message)}</span>
          </div>
        )}
        {role === 'user' ? (
          <div className="user-bubble">
            {parts.length
              ? parts.map(renderLegacyPart)
              : <DatalogueMarkdown text={message?.text || ''} className="ai-message md-body" />}
          </div>
        ) : (
          <>
            {parts.length ? parts.map(renderLegacyPart) : <RuntimeParts />}
            {subAgentMessages.length > 0 && (
              <DatalogueSubAgentMessages messages={subAgentMessages} />
            )}
            {!hasArtifactDataPart && (
              <ArtifactCard artifact={custom.artifactCard || custom.artifact_card} />
            )}
          </>
        )}
      </div>
    </>
  );
}

function RuntimeMessage() {
  const message = useAuiState((s) => s.message);
  return (
    <MessagePrimitive.Root data-role={messageRole(message)}>
      <DatalogueMessageBody message={message} />
    </MessagePrimitive.Root>
  );
}

export function DatalogueMessage({ message }) {
  if (message) return <DatalogueMessageBody message={message} />;
  return <RuntimeMessage />;
}

export default DatalogueMessage;
