import { describe, expect, it, vi } from 'vitest';

const exportedRepositoryMock = vi.hoisted(() => ({
  fromArray: vi.fn((messages) => ({ messages })),
}));

const fetchWorkbenchThreadMock = vi.hoisted(() => vi.fn());

vi.mock('@assistant-ui/react', () => ({
  ExportedMessageRepository: exportedRepositoryMock,
  RuntimeAdapterProvider: ({ children }) => children,
  useAuiState: () => null,
}));

vi.mock('assistant-stream', () => ({
  createAssistantStream: vi.fn(() => ({})),
}));

vi.mock('../api/client', () => ({
  listConversations: vi.fn(async () => []),
  createConversation: vi.fn(async () => ({ id: 25, thread_id: 'legacy-thread-25' })),
  renameConversation: vi.fn(async () => {}),
  archiveConversation: vi.fn(async () => {}),
  unarchiveConversation: vi.fn(async () => {}),
  deleteConversation: vi.fn(async () => {}),
  getConversation: vi.fn(async () => ({ conversation: { id: 25, title: '旧会话' }, messages: [] })),
}));

vi.mock('./workbench-api', () => ({
  fetchWorkbenchThread: fetchWorkbenchThreadMock,
}));

import {
  DatalogueThreadListAdapter,
  messagesFromWorkbench,
  resolveRecentInitializedRemoteId,
  resolveRemoteId,
} from './thread-list-adapter';

const AGENTSCOPE_THREAD_ID = 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

function sampleWorkbenchView() {
  return {
    thread_id: AGENTSCOPE_THREAD_ID,
    read_only: false,
    messages: [
      {
        message_id: 'msg_user_1',
        role: 'user',
        status: 'completed',
        content_summary: '查询杨凯 2024 年工作日志',
        created_at: '2026-06-30T05:00:00Z',
      },
      {
        message_id: 'msg_assistant_1',
        role: 'assistant',
        status: 'completed',
        content_summary: '已完成查询，共 3 条工作日志。',
        created_at: '2026-06-30T05:00:01Z',
      },
    ],
    primary_artifact_ref: 'artifact:result-1',
    related_refs: [{ ref_type: 'trace', ref: 'trace:trace-1', relation: 'trace' }],
  };
}

describe('thread-list AgentScope handoff', () => {
  it('remaps local draft thread to as_* after chat final resolves thread id', async () => {
    fetchWorkbenchThreadMock.mockResolvedValue(sampleWorkbenchView());
    window.dispatchEvent(
      new CustomEvent('datalogue:thread-resolved', {
        detail: { localThreadId: 'local-thread-1', threadId: AGENTSCOPE_THREAD_ID },
      }),
    );

    const adapter = new DatalogueThreadListAdapter();
    const item = await adapter.fetch('local-thread-1');

    expect(resolveRemoteId('local-thread-1')).toBe(AGENTSCOPE_THREAD_ID);
    expect(resolveRecentInitializedRemoteId()).toBe(AGENTSCOPE_THREAD_ID);
    expect(fetchWorkbenchThreadMock).toHaveBeenCalledWith(AGENTSCOPE_THREAD_ID);
    expect(item).toMatchObject({
      status: 'regular',
      remoteId: AGENTSCOPE_THREAD_ID,
      externalId: AGENTSCOPE_THREAD_ID,
      title: '查询杨凯 2024 年工作日志',
    });
  });

  it('maps Workbench View Model messages into assistant-ui history with artifact refs', () => {
    const messages = messagesFromWorkbench(sampleWorkbenchView());

    expect(messages).toHaveLength(2);
    expect(messages[1].metadata.custom).toMatchObject({
      workbenchThreadId: AGENTSCOPE_THREAD_ID,
      artifactCard: {
        title: '查询结果',
        status: 'completed',
        primary_ref: 'artifact:result-1',
        related_refs: [{ ref_type: 'trace', ref: 'trace:trace-1', relation: 'trace' }],
      },
    });
    expect(JSON.stringify(messages)).not.toMatch(/sql|schema|raw_rows|query_plan|field_patch/i);
  });
});
