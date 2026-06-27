// chat-adapter.test.js
// 验证 Chat adapter 将后端 SSE/final payload 收敛为 C-ready 消息 metadata。

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { makeChatAdapter, buildBusinessSessionId } from './chat-adapter';
import { streamChatEvents } from '../api/client';

vi.mock('../api/client', () => ({
  streamChatEvents: vi.fn(),
}));

vi.mock('./thread-list-adapter', () => ({
  resolveRecentInitializedRemoteId: vi.fn(() => null),
  resolveRemoteId: vi.fn(() => null),
}));

async function* events(items) {
  for (const item of items) {
    yield item;
  }
}

async function collectRun(adapter, options = {}) {
  const chunks = [];
  for await (const chunk of adapter.run({
    messages: [
      {
        role: 'user',
        content: [{ type: 'text', text: options.question || '查询销售趋势' }],
      },
    ],
    abortSignal: options.abortSignal || new AbortController().signal,
    unstable_threadId: options.threadId,
  })) {
    chunks.push(chunk);
  }
  return chunks;
}

describe('chat-adapter C-ready metadata', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = null;
    window.history.pushState({}, '', '/chat');
  });

  it('builds stable business session ids from conversation or thread context', () => {
    expect(buildBusinessSessionId({ conversationId: 12, threadId: 'local', fallbackSessionId: 'fallback' }))
      .toBe('conversation-12');
    expect(buildBusinessSessionId({ conversationId: null, threadId: 'thread/abc', fallbackSessionId: 'fallback' }))
      .toBe('assistant-thread-thread-abc');
    expect(buildBusinessSessionId({ conversationId: null, threadId: '', fallbackSessionId: 'fallback' }))
      .toBe('fallback');
  });

  it('converts route, step and final events into timeline and artifact metadata', async () => {
    streamChatEvents.mockReturnValue(events([
      {
        type: 'route_decision',
        decision: 'selected',
        dataset_name: '销售明细',
        dataset_id: 7,
        score: 0.91,
      },
      {
        type: 'step',
        node: 'intent_recognition',
        status: 'done',
        intent: '销售趋势分析',
      },
      {
        type: 'step',
        node: 'sql_execute',
        status: 'done',
        rows: 2,
        columns: ['date', 'gmv'],
      },
      {
        type: 'final',
        answer: '销售趋势整体上升',
        conversation_id: 42,
        message_id: 99,
        result_ref: 'artifact:result:42',
        sql_result: {
          columns: ['date', 'gmv'],
          rows: [{ date: '2026-01-01', gmv: 100 }],
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, { threadId: 'local-thread' });
    const finalChunk = chunks.at(-1);

    expect(streamChatEvents).toHaveBeenCalledWith(
      expect.objectContaining({
        question: '查询销售趋势',
        session_id: 'assistant-thread-local-thread',
        conversation_id: null,
        dataset_id: 7,
        clarification_response: null,
      }),
      expect.any(Object),
    );
    expect(finalChunk.status).toEqual({ type: 'complete', reason: 'stop' });
    expect(finalChunk.metadata.custom.taskTimeline.map((item) => item.type)).toEqual([
      'dataset_matching',
      'task_understood',
      'bi_execution',
      'artifact_created',
      'next_action',
    ]);
    expect(finalChunk.metadata.custom.artifactCard).toMatchObject({
      title: '查询结果',
      primary_ref: 'artifact:result:42',
    });
    expect(finalChunk.metadata.custom.stepTrace).toHaveLength(2);
  });

  it('exposes only business-level candidate dataset confirmation metadata', async () => {
    streamChatEvents.mockReturnValue(events([
      {
        type: 'final',
        answer: '请选择数据集',
        route_decision: {
          decision: 'ambiguous',
          candidates: [
            {
              dataset_id: 1,
              dataset_name: '销售明细',
              reason: '匹配销售分析问题',
              fields: ['raw_field'],
              raw_sql: 'SELECT * FROM t',
            },
          ],
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: null } });
    const chunks = await collectRun(adapter);
    const candidateDatasets = chunks.at(-1).metadata.custom.candidateDatasets;

    expect(candidateDatasets).toEqual({
      candidates: [
        {
          dataset_id: 1,
          dataset_name: '销售明细',
          short_reason: '匹配销售分析问题',
        },
      ],
    });
    expect(JSON.stringify(candidateDatasets)).not.toMatch(/raw_field|SELECT/i);
  });

  it('passes pending clarification response once and then clears it', async () => {
    streamChatEvents.mockReturnValue(events([{ type: 'final', answer: '已确认' }]));
    window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = {
      selected_dataset_id: 7,
      selected_text: '销售明细',
    };

    const adapter = makeChatAdapter({ datasetIdRef: { current: null } });
    await collectRun(adapter);

    expect(streamChatEvents).toHaveBeenCalledWith(
      expect.objectContaining({
        clarification_response: {
          selected_dataset_id: 7,
          selected_text: '销售明细',
        },
      }),
      expect.any(Object),
    );
    expect(window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__).toBeNull();
  });
});
