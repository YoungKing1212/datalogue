import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  ChatPage,
  conversationRouteIdForDatasetRestore,
  resolveAssistantUiPreviewSkin,
  resolveUrlSyncTarget,
  resolveWorkbenchThreadId,
  runWorkbenchRetryStream,
  shouldAcceptResolvedWorkbenchThread,
  shouldSwitchToRouteThread,
  submitWorkbenchRetryRun,
} from './chat-page.jsx';

const navigateSpy = vi.hoisted(() => vi.fn());

vi.mock('react-router-dom', () => ({
  useParams: () => ({}),
  useNavigate: () => navigateSpy,
}));

vi.mock('@assistant-ui/react', () => {
  return {
    AssistantRuntimeProvider: ({ children }) => <>{children}</>,
    useLocalRuntime: () => ({ kind: 'local-runtime' }),
    useRemoteThreadListRuntime: () => ({ kind: 'thread-list-runtime' }),
    useAui: () => ({
      composer: () => ({
        setText: vi.fn(),
        send: vi.fn(),
      }),
      threads: () => ({
        reload: vi.fn().mockResolvedValue(undefined),
        switchToThread: vi.fn().mockResolvedValue(undefined),
      }),
    }),
    useAuiState: (selector) => selector({
      thread: { isRunning: false },
      threads: {
        mainThreadId: 'local-thread',
        threadItems: [{ id: 'local-thread', remoteId: null }],
      },
    }),
  };
});

vi.mock('../assistant-ui', () => ({
  DatalogueThread: ({ empty, composer }) => (
    <main>
      {empty}
      {composer}
    </main>
  ),
  DatalogueThreadList: () => <nav aria-label="会话列表" />,
  DatalogueComposer: ({ variant }) => (
    <div data-testid={variant === 'welcome' ? 'welcome-composer' : 'bottom-composer'} />
  ),
}));

vi.mock('../api/client', () => ({
  getConversation: vi.fn(),
  listDatasets: vi.fn().mockResolvedValue([]),
  listLLMModels: vi.fn().mockResolvedValue([]),
}));

vi.mock('../assistant/chat-adapter', () => ({
  makeChatAdapter: () => ({
    runAgenticShellTask: vi.fn(),
  }),
}));

vi.mock('../assistant/thread-list-adapter', () => ({
  DatalogueThreadListAdapter: class DatalogueThreadListAdapter {},
}));

vi.mock('../assistant/workbench-api', () => ({
  normalizeWorkbenchThreadId: (value) => (value && /^\d+$/.test(value) ? `conv_${value}` : value || null),
}));

vi.mock('./icons', () => ({
  Icon: ({ name }) => <span data-testid={`icon-${name}`} />,
}));

afterEach(() => {
  window.__DATALOGUE_PENDING_WORKBENCH_RETRY__ = null;
  vi.restoreAllMocks();
});

describe('ChatPage', () => {
  it('does not expose the DatasetAgent prototype test entry in the chat surface', async () => {
    render(
      <ChatPage
        traceOpen={false}
        setTraceOpen={vi.fn()}
        showFollowups={false}
        agentVerbosity="normal"
      />,
    );

    await waitFor(() => {
      expect(screen.queryByText('确认后交接 DatasetAgent')).not.toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: '创建 run' })).not.toBeInTheDocument();
  });
});

describe('shouldSwitchToRouteThread', () => {
  it('skips route sync when no conversation id is present', () => {
    expect(shouldSwitchToRouteThread(undefined, 'thread-1', '1')).toBe(false);
  });

  it('skips route sync when the main thread already matches the route id', () => {
    expect(shouldSwitchToRouteThread('16', '16', undefined)).toBe(false);
  });

  it('skips route sync when the current thread remote id already matches the route id', () => {
    expect(shouldSwitchToRouteThread('16', 'thread-mapping-16', 16)).toBe(false);
  });

  it('requests route sync when direct URL entry is still on a local draft thread', () => {
    expect(shouldSwitchToRouteThread('16', 'local-draft', undefined)).toBe(true);
  });
});

describe('resolveUrlSyncTarget', () => {
  it('does not let initial runtime state override a direct route', () => {
    expect(resolveUrlSyncTarget({
      routeId: '24',
      remoteId: '21',
      mainThreadChanged: true,
      hasObservedThread: false,
    })).toBeNull();
  });

  it('does not roll back the URL while route-driven switch is pending', () => {
    expect(resolveUrlSyncTarget({
      routeId: '1',
      remoteId: '25',
      mainThreadChanged: false,
      hasObservedThread: true,
    })).toBeNull();
  });

  it('syncs URL when the runtime main thread changes to another persisted conversation', () => {
    expect(resolveUrlSyncTarget({
      routeId: '25',
      remoteId: '1',
      mainThreadChanged: true,
      hasObservedThread: true,
    })).toBe('/chat/1');
  });

  it('keeps draft route when no route id is present and runtime did not change', () => {
    expect(resolveUrlSyncTarget({
      routeId: undefined,
      remoteId: '25',
      mainThreadChanged: false,
      hasObservedThread: true,
    })).toBeNull();
  });

  it('syncs URL when a no-route page switches to a persisted runtime thread', () => {
    expect(resolveUrlSyncTarget({
      routeId: undefined,
      remoteId: '25',
      mainThreadChanged: true,
      hasObservedThread: true,
    })).toBe('/chat/25');
  });
});

describe('resolveWorkbenchThreadId', () => {
  it('maps numeric chat routes to legacy conv threads', () => {
    expect(resolveWorkbenchThreadId('25', null)).toBe('conv_25');
  });

  it('keeps AgentScope chat routes as the workbench thread source', () => {
    expect(resolveWorkbenchThreadId('as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', null)).toBe(
      'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    );
  });

  it('uses runtime remote id when the URL has no route id', () => {
    expect(resolveWorkbenchThreadId(undefined, 'as_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', null)).toBe(
      'as_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    );
  });

  it('keeps the route as the panel source while runtime remote id is catching up', () => {
    expect(resolveWorkbenchThreadId('25', 'as_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', null)).toBe('conv_25');
    expect(resolveWorkbenchThreadId('as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '25', null)).toBe(
      'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    );
  });

  it('prefers resolved AgentScope thread over numeric runtime id for a new chat draft', () => {
    expect(resolveWorkbenchThreadId(undefined, '29', 'as_cccccccc-cccc-cccc-cccc-cccccccccccc')).toBe(
      'as_cccccccc-cccc-cccc-cccc-cccccccccccc',
    );
  });
});

describe('conversationRouteIdForDatasetRestore', () => {
  it('allows legacy numeric and conv-prefixed routes', () => {
    expect(conversationRouteIdForDatasetRestore('25')).toBe('25');
    expect(conversationRouteIdForDatasetRestore('conv_25')).toBe('25');
  });

  it('does not call legacy conversation APIs for AgentScope routes', () => {
    expect(conversationRouteIdForDatasetRestore('as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')).toBeNull();
  });
});

describe('resolveAssistantUiPreviewSkin', () => {
  it('keeps bare preview compatible with the previous query flag', () => {
    expect(resolveAssistantUiPreviewSkin('?bare=1')).toBe('bare');
    expect(resolveAssistantUiPreviewSkin('?skin=bare')).toBe('bare');
  });

  it('enables the AgentScope-inspired preview without affecting the default chat route', () => {
    expect(resolveAssistantUiPreviewSkin('?skin=agentscope')).toBe('agentscope');
    expect(resolveAssistantUiPreviewSkin('')).toBeNull();
  });
});

describe('submitWorkbenchRetryRun', () => {
  it('logs retry stream failures without leaking pending checkpoint state', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await submitWorkbenchRetryRun(null);

    expect(window.__DATALOGUE_PENDING_WORKBENCH_RETRY__).toBeNull();
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});

describe('runWorkbenchRetryStream', () => {
  it('streams retry through chat stream with only controlled checkpoint payload', async () => {
    const seenPayloads = [];
    const dispatchTrace = vi.fn();
    async function* streamEvents(payload) {
      seenPayloads.push(payload);
      yield { type: 'step', node: 'retry', status: 'done' };
      yield { type: 'final', thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', answer: '完成' };
    }

    const finalPayload = await runWorkbenchRetryStream(
      {
        question: '查询工作日志',
        conversation_id: '31',
        thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        retry_checkpoint_ref: 'checkpoint://retry',
        dataset_id: '7',
        display_text: '重试上一步',
      },
      { streamEvents, dispatchTrace },
    );

    expect(seenPayloads).toEqual([{
      question: '查询工作日志',
      conversation_id: 31,
      thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      dataset_id: 7,
      retry_checkpoint_ref: 'checkpoint://retry',
    }]);
    expect(dispatchTrace).toHaveBeenCalledTimes(2);
    expect(finalPayload).toEqual({
      type: 'final',
      thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      answer: '完成',
    });
    expect(JSON.stringify(seenPayloads)).not.toMatch(/select|schema|raw_rows|query_plan/i);
  });
});

describe('shouldAcceptResolvedWorkbenchThread', () => {
  it('accepts the latest AgentScope mirror on a route-less chat page', () => {
    expect(shouldAcceptResolvedWorkbenchThread({
      routeId: undefined,
      threadId: 'as_dddddddd-dddd-dddd-dddd-dddddddddddd',
      mainThreadId: 'local-thread',
      localThreadId: '30',
    })).toBe(true);
  });

  it('keeps explicit history routes as the panel source', () => {
    expect(shouldAcceptResolvedWorkbenchThread({
      routeId: '25',
      threadId: 'as_dddddddd-dddd-dddd-dddd-dddddddddddd',
      mainThreadId: 'local-thread',
      localThreadId: 'local-thread',
    })).toBe(false);
  });

  it('rejects non-AgentScope thread ids', () => {
    expect(shouldAcceptResolvedWorkbenchThread({
      routeId: undefined,
      threadId: 'conv_25',
      mainThreadId: 'local-thread',
      localThreadId: 'local-thread',
    })).toBe(false);
  });
});
