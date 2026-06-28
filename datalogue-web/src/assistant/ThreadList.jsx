// ThreadList — 独立左侧列，列出所有对话
// 用 ThreadListPrimitive + ThreadListItemPrimitive 渲染，自动接 ThreadListAdapter
// "新对话"按钮只切换本地草稿，首条消息发送时再持久化数据库会话

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ThreadListPrimitive,
  ThreadListItemPrimitive,
  useAui,
  useAuiState,
} from '@assistant-ui/react';
import { Icon } from '../components/icons';

/**
 * 单条 thread item：标题 + hover 删除按钮
 * - active 状态：当前主 thread → 高亮
 */
function ThreadListItem() {
  const navigate = useNavigate();
  const isActive = useAuiState(
    (s) => s.threads?.mainThreadId === s.threadListItem?.id,
  );
  const remoteId = useAuiState((s) => s.threadListItem?.remoteId);
  const title = useAuiState((s) => s.threadListItem?.title);
  const onClick = () => {
    if (!remoteId) return;
    navigate(`/chat/${remoteId}`); // 点击历史会话时同步地址栏，避免消息区已切换但深链仍停在旧会话。
  };
  return (
    <ThreadListItemPrimitive.Root className={`thread-list-item ${isActive ? 'active' : ''}`}>
      <ThreadListItemPrimitive.Trigger
        className="thread-list-item-trigger"
        data-conversation-id={remoteId}
        aria-label={remoteId ? `${title || '新对话'}，会话 ${remoteId}` : undefined}
        onClick={onClick}
      >
        <Icon name="chat" style={{ width: 13, height: 13, color: 'var(--text-3)' }} />
        <ThreadListItemPrimitive.Title fallback="新对话" />
      </ThreadListItemPrimitive.Trigger>
      <ThreadListItemPrimitive.Delete className="thread-list-item-del" aria-label="删除对话">
        <Icon name="trash" style={{ width: 12, height: 12 }} />
      </ThreadListItemPrimitive.Delete>
    </ThreadListItemPrimitive.Root>
  );
}

function DraftThreadListItem() {
  const navigate = useNavigate();
  const aui = useAui();
  const newThreadId = useAuiState((s) => s.threads?.newThreadId);
  const mainThreadId = useAuiState((s) => s.threads?.mainThreadId);
  if (!newThreadId) return null;

  const isActive = newThreadId === mainThreadId;
  const onClick = async () => {
    await aui.threads().switchToNewThread(); // 切回内存草稿，不触发后端 conversation 创建。
    navigate('/chat');
  };

  return (
    <div
      className={`thread-list-item ${isActive ? 'active' : ''}`}
      data-testid="thread-list-draft-item"
      data-draft="true"
    >
      <button
        type="button"
        className="thread-list-item-trigger"
        data-testid="thread-list-draft-trigger"
        onClick={onClick}
      >
        <Icon name="chat" style={{ width: 13, height: 13, color: 'var(--text-3)' }} />
        <span>新对话</span>
      </button>
    </div>
  );
}

/**
 * 自定义"新对话"按钮：只创建 assistant-ui 本地草稿。
 * 用户发送首条消息时，thread-list adapter.initialize() 才会创建后端 conversation。
 */
export async function startNewConversationDraft({
  switchToNewThread,
  navigate,
  logger = console,
}) {
  try {
    await switchToNewThread(); // 只切换本地 new thread，避免空会话提前写入数据库。
    navigate('/chat');
    return true;
  } catch (e) {
    logger.error('[thread-list] switch to draft failed', e);
    return false;
  }
}

function NewThreadButton() {
  const navigate = useNavigate();
  const aui = useAui();
  const [isCreating, setIsCreating] = useState(false);
  const onClick = async () => {
    if (isCreating) return;
    setIsCreating(true);
    try {
      await startNewConversationDraft({
        switchToNewThread: () => aui.threads().switchToNewThread(),
        navigate,
      });
    } finally {
      setIsCreating(false);
    }
  };
  return (
    <button type="button" className="thread-list-new" onClick={onClick} disabled={isCreating}>
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
            <DraftThreadListItem />
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
