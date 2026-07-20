// DatalogueThread — Datalogue 聊天主区的 assistant-ui 可见壳层。
// 保留 chat-main/chat-scroll/chat-inner 与 empty/composer 插槽，不接线 chat-page、不改变 runtime。

import React, { createContext, useContext } from 'react';
import { ThreadPrimitive } from '@assistant-ui/react';
import { AIMessage, UserMessage as DefaultUserMessage } from '../features/chat/MyMessage';

const TraceContext = createContext({
  traceSteps: [],
  agentVerbosity: 'standard',
});

export function DatalogueTraceProvider({ value, children }) {
  return <TraceContext.Provider value={value}>{children}</TraceContext.Provider>;
}

function AssistantMessageWithTrace() {
  const { traceSteps, agentVerbosity } = useContext(TraceContext);
  return (
    <AIMessage traceSteps={traceSteps} agentVerbosity={agentVerbosity} />
  );
}

/**
 * DatalogueThread — P1 Thread 外壳。
 * 默认复用当前唯一的 MyMessage 可见渲染，不在本层暴露内部查询细节。
 */
export function DatalogueThread({
  empty,
  composer,
  traceSteps = [],
  agentVerbosity = 'standard',
  UserMessage = DefaultUserMessage,
  AssistantMessage = AssistantMessageWithTrace,
}) {
  return (
    <DatalogueTraceProvider value={{ traceSteps, agentVerbosity }}>
      <ThreadPrimitive.Root className="chat-main">
        <ThreadPrimitive.Empty>{empty}</ThreadPrimitive.Empty>

        <ThreadPrimitive.If empty={false}>
          <ThreadPrimitive.Viewport autoScroll className="chat-scroll">
            <div className="chat-inner">
              <ThreadPrimitive.Messages
                components={{
                  UserMessage,
                  AssistantMessage,
                }}
              />
            </div>
          </ThreadPrimitive.Viewport>
          {composer}
        </ThreadPrimitive.If>
      </ThreadPrimitive.Root>
    </DatalogueTraceProvider>
  );
}
