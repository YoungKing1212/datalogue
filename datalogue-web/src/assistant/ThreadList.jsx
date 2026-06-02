// ThreadList — 独立左侧列，列出所有对话
// 用 ThreadListPrimitive + ThreadListItemPrimitive 渲染，自动接 ThreadListAdapter
// "新对话"按钮改成自定义：直接调 createConversation 拿到 remoteId 并 navigate

import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ThreadListPrimitive,
  ThreadListItemPrimitive,
  useAuiState,
} from '@assistant-ui/react';
import { Icon } from '../components/icons';
import { createConversation } from '../api/client';

/**
 * 单条 thread item：标题 + hover 删除按钮
 * - active 状态：当前主 thread → 高亮
 */
function ThreadListItem() {
  const isActive = useAuiState(
    (s) => s.threads?.mainThreadId === s.threadListItem?.id,
  );
  return (
    <ThreadListItemPrimitive.Root className={`thread-list-item ${isActive ? 'active' : ''}`}>
      <ThreadListItemPrimitive.Trigger className="thread-list-item-trigger">
        <Icon name="chat" style={{ width: 13, height: 13, color: 'var(--text-3)' }} />
        <ThreadListItemPrimitive.Title fallback="新对话" />
      </ThreadListItemPrimitive.Trigger>
      <ThreadListItemPrimitive.Delete className="thread-list-item-del" aria-label="删除对话">
        <Icon name="trash" style={{ width: 12, height: 12 }} />
      </ThreadListItemPrimitive.Delete>
    </ThreadListItemPrimitive.Root>
  );
}

/**
 * 自定义"新对话"按钮：直接调 createConversation 创建空会话并跳到 /chat/:id
 * useRemoteThreadListRuntime({threadId: routeId}) 会自动同步 runtime
 */
function NewThreadButton() {
  const navigate = useNavigate();
  const onClick = async () => {
    try {
      const conv = await createConversation({});
      const newRemoteId = String(conv.id);
      navigate(`/chat/${newRemoteId}`);
    } catch (e) {
      console.error('[新对话] 创建失败', e);
    }
  };
  return (
    <button type="button" className="thread-list-new" onClick={onClick}>
      <Icon name="plus" style={{ width: 13, height: 13 }} />
      新对话
    </button>
  );
}

/**
 * ThreadList — 左侧列：新对话按钮 + 常规列表 + 归档列表
 */
export function ThreadList() {
  return (
    <aside className="thread-list-col">
      <ThreadListPrimitive.Root className="thread-list-root">
        <NewThreadButton />

        <div className="thread-list-section">
          <div className="thread-list-section-head">最近对话</div>
          <div className="thread-list-items">
            <ThreadListPrimitive.Items components={{ ThreadListItem }} />
          </div>
        </div>

        <div className="thread-list-section">
          <div className="thread-list-section-head">已归档</div>
          <div className="thread-list-items">
            <ThreadListPrimitive.Items archived components={{ ThreadListItem }} />
          </div>
        </div>
      </ThreadListPrimitive.Root>
    </aside>
  );
}
