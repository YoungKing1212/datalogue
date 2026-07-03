// DatalogueThreadList — 基于 assistant-ui 官网 Thread List Component anatomy 的会话列表。
// 使用 ThreadListPrimitive.New / Items 与 ThreadListItemPrimitive.Root / Trigger / Title / Archive / Delete。

import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ThreadListPrimitive,
  ThreadListItemPrimitive,
} from '@assistant-ui/react';
import { Icon } from '../components/icons';

function DatalogueThreadListItem({ archived = false }) {
  return (
    <ThreadListItemPrimitive.Root className="thread-list-item">
      <ThreadListItemPrimitive.Trigger className="thread-list-item-trigger">
        <Icon name="chat" style={{ width: 13, height: 13, color: 'var(--text-3)' }} />
        <ThreadListItemPrimitive.Title fallback="新对话" />
      </ThreadListItemPrimitive.Trigger>

      {archived ? (
        <ThreadListItemPrimitive.Unarchive className="thread-list-item-action" aria-label="恢复对话">
          <Icon name="refresh" style={{ width: 12, height: 12 }} />
        </ThreadListItemPrimitive.Unarchive>
      ) : (
        <ThreadListItemPrimitive.Archive className="thread-list-item-action" aria-label="归档对话">
          <Icon name="archive" style={{ width: 12, height: 12 }} />
        </ThreadListItemPrimitive.Archive>
      )}

      <ThreadListItemPrimitive.Delete className="thread-list-item-action thread-list-item-del" aria-label="删除对话">
        <Icon name="trash" style={{ width: 12, height: 12 }} />
      </ThreadListItemPrimitive.Delete>
    </ThreadListItemPrimitive.Root>
  );
}

function ArchivedThreadListItem() {
  return <DatalogueThreadListItem archived />;
}

function OfficialNewThreadButton() {
  const navigate = useNavigate();
  return (
    <ThreadListPrimitive.New className="thread-list-new" onClick={() => navigate('/chat')}>
      <Icon name="plus" style={{ width: 13, height: 13 }} />
      新对话
    </ThreadListPrimitive.New>
  );
}

/**
 * DatalogueThreadList — 官网 Thread List Component 结构。
 * URL 仍由 ChatPage 的 UrlSync/RouteThreadSync 负责，列表项只承担 assistant-ui 官方切换语义。
 */
export function DatalogueThreadList() {
  return (
    <aside className="thread-list-col">
      <ThreadListPrimitive.Root className="thread-list-root">
        <OfficialNewThreadButton />

        <div className="thread-list-section">
          <div className="thread-list-section-head">最近对话</div>
          <div className="thread-list-items">
            <ThreadListPrimitive.Items components={{ ThreadListItem: DatalogueThreadListItem }} />
          </div>
          <ThreadListPrimitive.LoadMore className="thread-list-load-more">
            加载更多
          </ThreadListPrimitive.LoadMore>
        </div>

        <div className="thread-list-section">
          <div className="thread-list-section-head">已归档</div>
          <div className="thread-list-items">
            <ThreadListPrimitive.Items archived components={{ ThreadListItem: ArchivedThreadListItem }} />
          </div>
        </div>
      </ThreadListPrimitive.Root>
    </aside>
  );
}
