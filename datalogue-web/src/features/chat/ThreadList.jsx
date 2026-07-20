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
import { Icon } from '../../shared/components/icons';
import { conversationUpdatedAtMap } from './thread-list-adapter';

// 会话时间格式化：今天=HH:mm、昨天=昨天 HH:mm、更早=MM-DD HH:mm（贴近设计稿）。
function formatConversationTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dayDiff = Math.round((startOfToday - startOfDay) / 86400000);
  if (dayDiff <= 0) return hm; // 今天只显时分
  if (dayDiff === 1) return `昨天 ${hm}`;
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`;
}

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
  const updatedAt = useAuiState((s) => s.threadListItem?.updatedAt);
  if (!remoteId) return null; // 只渲染后端已持久化的会话；本地草稿由 DraftThreadListItem 单独承载。
  const onClick = () => {
    navigate(`/chat/${remoteId}`); // 点击历史会话时同步地址栏，避免消息区已切换但深链仍停在旧会话。
  };
  // updatedAt 优先取 assistant-ui 状态，回退到 adapter 写入的模块级缓存（自定义字段不透传）。
  const timeText = formatConversationTime(updatedAt || conversationUpdatedAtMap.get(String(remoteId)));
  return (
    <ThreadListItemPrimitive.Root className={`thread-list-item ${isActive ? 'active' : ''}`}>
      <ThreadListItemPrimitive.Trigger
        className="thread-list-item-trigger"
        data-conversation-id={remoteId}
        aria-label={remoteId ? `${title || '新对话'}，会话 ${remoteId}` : undefined}
        onClick={onClick}
      >
        <span className="thread-list-item-title">{title || '新对话'}</span>
        {timeText && <span className="thread-list-item-time">{timeText}</span>}
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
        <span className="thread-list-item-title">新对话</span>
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
      <Icon name="plus" style={{ width: 15, height: 15 }} />
      新建问数
    </button>
  );
}

/**
 * ThreadList — 左侧列：新对话按钮 + 常规列表 + 归档列表
 */
export function ThreadList() {
  const navigate = useNavigate();
  return (
    <aside className="thread-list-col">
      <ThreadListPrimitive.Root className="thread-list-root">
        <NewThreadButton />

        <div className="thread-list-section">
          <div className="thread-list-section-head">
            <span>最近会话</span>
            <button
              type="button"
              className="thread-list-section-filter"
              title="筛选会话"
              aria-label="筛选会话"
            >
              <Icon name="filter" style={{ width: 14, height: 14 }} />
            </button>
          </div>
          <div className="thread-list-items">
            <DraftThreadListItem />
            <ThreadListPrimitive.Items components={{ ThreadListItem }} />
          </div>
          <ThreadListPrimitive.LoadMore className="thread-list-load-more">
            加载更多
          </ThreadListPrimitive.LoadMore>
        </div>

        <div className="thread-list-section">
          <div className="thread-list-section-head">
            <span>已归档</span>
          </div>
          <div className="thread-list-items">
            <ThreadListPrimitive.Items archived components={{ ThreadListItem }} />
          </div>
        </div>
      </ThreadListPrimitive.Root>

      <button
        type="button"
        className="thread-list-viewall"
        onClick={() => navigate('/history')}
      >
        查看全部会话
        <Icon name="chev" style={{ width: 13, height: 13 }} />
      </button>
    </aside>
  );
}
