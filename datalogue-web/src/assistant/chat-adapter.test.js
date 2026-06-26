// chat-adapter.test.js
// 验证 Chat adapter 将后端 SSE/final payload 收敛为 C-ready 消息 metadata。

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { makeChatAdapter, buildBusinessSessionId } from './chat-adapter';
import { buildHistoryMessageCustom } from './thread-list-adapter';

vi.mock('../api/client', () => ({
  streamChatEvents: vi.fn(),
}));

vi.mock('./thread-list-adapter', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    resolveRemoteId: vi.fn(() => null),
    resolveRecentInitializedRemoteId: vi.fn(() => null),
  };
});

const { streamChatEvents } = await import('../api/client');

async function* events(items) {
  for (const item of items) {
    yield item;
  }
}

function runInput(options = {}) {
  return {
    messages: [
      {
        role: 'user',
        content: [{ type: 'text', text: options.question || '查询销售趋势' }],
      },
    ],
    abortSignal: options.abortSignal || new AbortController().signal,
    unstable_threadId: options.threadId,
  };
}

async function collectRun(adapter, input = runInput()) {
  const chunks = [];
  for await (const chunk of adapter.run(input)) {
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
    const chunks = await collectRun(adapter, runInput({ threadId: 'local-thread' }));
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

  it('maps final SSE observability and artifact refs into page metadata', async () => {
    streamChatEvents.mockReturnValue(events([
      {
        type: 'step',
        node: 'query_plan',
        status: 'done',
        query_plan: { query_type: 'metric_query', execution_strategy: 'query_graph' },
      },
      {
        type: 'final',
        answer: '最近30日 GMV 为 100。',
        sql: 'SELECT 100 AS gmv',
        sql_result: null,
        query_plan: { query_type: 'metric_query' },
        candidate_assets: { summary: { metrics: 1 } },
        result_ref: 'artifact:result-1',
        report_ref: 'artifact:report-1',
        message_id: 42,
        conversation_id: 7,
        langfuse_trace_id: 'trace-1',
        langfuse_session_id: 'session-1',
        observability: { trace_id: 'trace-1', session_id: 'session-1' },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 3 } });
    const chunks = await collectRun(adapter, runInput({
      question: '最近30日GMV趋势如何',
      threadId: 'local-thread',
    }));

    const final = chunks.at(-1);
    expect(final.status).toEqual({ type: 'complete', reason: 'stop' });
    expect(final.metadata.custom.resultRef).toBe('artifact:result-1');
    expect(final.metadata.custom.reportRef).toBe('artifact:report-1');
    expect(final.metadata.custom.langfuseTraceId).toBe('trace-1');
    expect(final.metadata.custom.observability).toEqual({ trace_id: 'trace-1', session_id: 'session-1' });
    expect(final.metadata.custom.stepTrace).toHaveLength(1);
    expect(final.metadata.custom.sqlResult).toBeNull();
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

  it('does not fabricate ArtifactCard refs when replaying old history metadata', () => {
    const custom = buildHistoryMessageCustom({
      id: 99,
      response_metadata: {
        query_plan: { query_type: 'metric_query' },
        langfuse: { trace_id: 'trace-old', session_id: 'session-old' },
      },
    });

    expect(custom.resultRef).toBeNull();
    expect(custom.reportRef).toBeNull();
    expect(custom.subagentToolResults).toBeNull();
    expect(custom.langfuseTraceId).toBe('trace-old');
  });
});
