// DatalogueThread — Datalogue 聊天主区的 assistant-ui 可见壳层。
// 保留 chat-main/chat-scroll/chat-inner 与 empty/composer 插槽，不接线 chat-page、不改变 runtime。

import React, { createContext, useContext } from 'react';
import { ThreadPrimitive } from '@assistant-ui/react';
import { AIMessage, UserMessage as DefaultUserMessage } from '../assistant/MyMessage';
import { DatalogueMessage } from './DatalogueMessage';

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
 * DatalogueThread — P1/P2 Thread 外壳。
 * 默认使用 assistant-ui 迁移后的 DatalogueMessage 渲染主消息（tool-call parts / Data UI / sub-agent messages 全集）。
 * 传入 useLegacyMessage={true} 可以回滚到旧 MyMessage，仅在真实回归时用作 feature flag。
 * 也可以直接通过 AssistantMessage prop 注入自定义组件，测试、Storybook 或 Workbench 独立线程都走这条路径。
 */
export function DatalogueThread({
  empty,
  composer,
  traceSteps = [],
  agentVerbosity = 'standard',
  UserMessage = DefaultUserMessage,
  AssistantMessage,
  useLegacyMessage = false,
}) {
  // 默认走新入口 DatalogueMessage；显式 legacy flag 或外部注入优先。
  const ResolvedAssistantMessage = AssistantMessage
    || (useLegacyMessage ? AssistantMessageWithTrace : DatalogueMessage);
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
                  AssistantMessage: ResolvedAssistantMessage,
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
