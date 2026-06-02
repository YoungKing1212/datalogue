// Thread — assistant-ui Thread 主组件
// 用 primitives 自定义渲染：Empty 状态 + Viewport + Messages + Composer
// 通过 TraceContext 把流式 trace 步骤从 ChatPage 传给 AIMessage

import React, { createContext, useContext } from 'react';
import { ThreadPrimitive } from '@assistant-ui/react';
import { AIMessage, UserMessage } from './MyMessage';

/**
 * TraceContext — 桥接 ChatPage 监听到的 SSE trace 步骤到 AIMessage
 * - traceSteps: 当前流式中的节点步骤数组
 * - showSql: 是否展示生成的 SQL 折叠块
 * - agentVerbosity: 'minimal' | 'standard' | 'full' — 控制 step 详细度
 */
const TraceContext = createContext({
  traceSteps: [],
  showSql: true,
  agentVerbosity: 'standard',
});

export function TraceProvider({ value, children }) {
  return <TraceContext.Provider value={value}>{children}</TraceContext.Provider>;
}

function AssistantMessageWithTrace() {
  const { traceSteps, showSql, agentVerbosity } = useContext(TraceContext);
  return (
    <AIMessage traceSteps={traceSteps} showSql={showSql} agentVerbosity={agentVerbosity} />
  );
}

/**
 * Thread — 顶层 Thread 容器（不含 Composer，Composer 由 ChatPage 在外面布局）
 * @param {React.ReactNode} props.empty - 空状态时渲染的内容（欢迎屏 + 输入框）
 * @param {React.ReactNode} props.composer - 输入区组件（消息列表非空时显示在底部）
 */
export function Thread({ empty, composer }) {
  return (
    <ThreadPrimitive.Root className="chat-main">
      <ThreadPrimitive.Empty>{empty}</ThreadPrimitive.Empty>

      <ThreadPrimitive.If empty={false}>
        <ThreadPrimitive.Viewport autoScroll className="chat-scroll">
          <div className="chat-inner">
            <ThreadPrimitive.Messages
              components={{
                UserMessage,
                AssistantMessage: AssistantMessageWithTrace,
              }}
            />
          </div>
        </ThreadPrimitive.Viewport>
        {composer}
      </ThreadPrimitive.If>
    </ThreadPrimitive.Root>
  );
}
