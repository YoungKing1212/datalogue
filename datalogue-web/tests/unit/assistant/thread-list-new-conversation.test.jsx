// ThreadList 新对话测试：验证点击新对话只创建本地草稿，不提前持久化数据库会话。

import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const assistantUiMocks = vi.hoisted(() => {
  const state = {
    threads: {
      mainThreadId: null,
      newThreadId: null,
    },
    threadListItem: null,
    persistedThreadRemoteId: '1',
    persistedThreadTitle: '查询杨凯2025年的工作日志',
  };
  return {
    state,
    switchToNewThread: vi.fn(async () => {}),
  };
});

const navigateMock = vi.hoisted(() => vi.fn());

vi.mock('react-router-dom', () => ({
  useNavigate: () => navigateMock,
}));

vi.mock('@assistant-ui/react', () => ({
  ThreadListPrimitive: {
    Root: ({ children, className }) => <div className={className}>{children}</div>,
    Items: ({ archived, components }) => {
      if (archived) return null;
      const ThreadListItem = components?.ThreadListItem;
      assistantUiMocks.state.threadListItem = {
        id: 'conversation-1',
        remoteId: assistantUiMocks.state.persistedThreadRemoteId,
        title: assistantUiMocks.state.persistedThreadTitle,
      };
      return ThreadListItem ? <ThreadListItem /> : <div data-testid="persisted-thread-items" />;
    },
    LoadMore: ({ children, className }) => <button className={className}>{children}</button>,
  },
  ThreadListItemPrimitive: {
    Root: ({ children, className }) => <div className={className}>{children}</div>,
    Trigger: ({ children, className, ...props }) => <button type="button" className={className} {...props}>{children}</button>,
    Title: ({ className, fallback }) => (
      <span className={className}>{assistantUiMocks.state.threadListItem?.title || fallback}</span>
    ),
    Delete: ({ children, className, ...props }) => <button type="button" className={className} {...props}>{children}</button>,
  },
  useAui: () => ({
    threads: () => ({
      switchToNewThread: assistantUiMocks.switchToNewThread,
    }),
  }),
  useAuiState: (selector) => selector(assistantUiMocks.state),
}));

import { startNewConversationDraft, ThreadList } from '../../../src/features/chat/ThreadList';

describe('startNewConversationDraft', () => {
  it('只切换到本地新 thread 并回到 /chat，不调用创建或刷新接口', async () => {
    const events = [];
    const switchToNewThread = vi.fn(async () => {
      events.push('switch:new');
    });
    const navigate = vi.fn((url) => {
      events.push(`navigate:${url}`);
    });

    const started = await startNewConversationDraft({
      switchToNewThread,
      navigate,
      logger: { error: vi.fn() },
    });

    expect(started).toBe(true);
    expect(switchToNewThread).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith('/chat');
    expect(events).toEqual(['switch:new', 'navigate:/chat']);
  });

  it('本地新 thread 切换失败时不跳转，避免 URL 和 runtime 状态不一致', async () => {
    const logger = { error: vi.fn() };
    const switchToNewThread = vi.fn(async () => {
      throw new Error('switch failed');
    });
    const navigate = vi.fn();

    const started = await startNewConversationDraft({
      switchToNewThread,
      navigate,
      logger,
    });

    expect(started).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
    expect(logger.error).toHaveBeenCalledWith('[thread-list] switch to draft failed', expect.any(Error));
  });
});

describe('ThreadList draft item', () => {
  it('本地新 thread 存在时，在最近对话顶部显示草稿项', () => {
    navigateMock.mockClear();
    assistantUiMocks.state.threads.mainThreadId = '__LOCALID_draft';
    assistantUiMocks.state.threads.newThreadId = '__LOCALID_draft';

    render(<ThreadList />);

    const draftItem = screen.getByTestId('thread-list-draft-item');
    expect(draftItem).toHaveClass('active');
    expect(draftItem).toHaveTextContent('新对话');
  });

  it('点击草稿项只切回本地 new thread，不触发后端列表刷新', async () => {
    navigateMock.mockClear();
    assistantUiMocks.state.threads.mainThreadId = 'conversation-1';
    assistantUiMocks.state.threads.newThreadId = '__LOCALID_draft';
    assistantUiMocks.switchToNewThread.mockClear();

    render(<ThreadList />);

    fireEvent.click(screen.getByTestId('thread-list-draft-trigger'));

    expect(assistantUiMocks.switchToNewThread).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith('/chat');
    });
  });

  it('点击历史会话时同步 URL 到对应 remoteId', async () => {
    navigateMock.mockClear();
    assistantUiMocks.state.threads.mainThreadId = 'conversation-25';
    assistantUiMocks.state.threads.newThreadId = null;
    assistantUiMocks.state.persistedThreadRemoteId = '1';
    assistantUiMocks.state.persistedThreadTitle = '查询杨凯2025年的工作日志';

    render(<ThreadList />);

    const persistedThread = screen.getByRole('button', { name: '查询杨凯2025年的工作日志，会话 1' });
    expect(persistedThread).toHaveAttribute('data-conversation-id', '1');

    fireEvent.click(persistedThread);

    expect(navigateMock).toHaveBeenCalledWith('/chat/1');
  });

  it('不渲染没有 remoteId 的本地悬空 thread，避免出现不可删除的新对话', () => {
    navigateMock.mockClear();
    assistantUiMocks.state.threads.mainThreadId = 'local-draft';
    assistantUiMocks.state.threads.newThreadId = null;
    assistantUiMocks.state.persistedThreadRemoteId = null;

    render(<ThreadList />);

    expect(screen.queryByRole('button', { name: /新对话，会话/ })).not.toBeInTheDocument();
    expect(screen.queryByText('查询杨凯2025年的工作日志')).not.toBeInTheDocument();

    assistantUiMocks.state.persistedThreadRemoteId = '1';
  });

  it('历史会话标题使用单行省略样式承载长名称', () => {
    navigateMock.mockClear();
    assistantUiMocks.state.threads.mainThreadId = 'conversation-1';
    assistantUiMocks.state.threads.newThreadId = null;
    assistantUiMocks.state.persistedThreadRemoteId = '1';
    assistantUiMocks.state.persistedThreadTitle = '这是一个非常长的 Thread 名称，用于验证左侧列表不要换行而是省略显示';

    render(<ThreadList />);

    const title = screen.getByText('这是一个非常长的 Thread 名称，用于验证左侧列表不要换行而是省略显示');
    expect(title).toHaveClass('thread-list-item-title');

    assistantUiMocks.state.persistedThreadTitle = '查询杨凯2025年的工作日志';
  });
});
