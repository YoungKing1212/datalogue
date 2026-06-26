import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  buildCandidateConfirmation,
  buildTaskTimeline,
  extractArtifactCard,
  extractCandidateDatasets,
  makeChatAdapter,
  normalizeEventEnvelope,
} from './chat-adapter';
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

async function collectRun(adapter, input) {
  const chunks = [];
  for await (const chunk of adapter.run(input)) {
    chunks.push(chunk);
  }
  return chunks;
}

describe('chat-adapter C-ready protocol helpers', () => {
  it('normalizes event_envelope while keeping legacy payload compatible', () => {
    const envelope = normalizeEventEnvelope({
      type: 'final',
      event_envelope: {
        event_id: 'evt-1',
        event_type: 'answer.completed',
        visibility: 'user_visible',
        task_id: 'task-1',
        trace_id: 'trace-1',
        payload: { answer: 'ok' },
      },
    });

    expect(envelope).toMatchObject({
      eventId: 'evt-1',
      eventType: 'answer.completed',
      taskId: 'task-1',
      traceId: 'trace-1',
      payload: { answer: 'ok' },
    });
  });

  it('builds candidate confirmation without schema details', () => {
    const confirmation = buildCandidateConfirmation({
      retry_checkpoint: { checkpoint_ref: 'checkpoint://task-1/dataset' },
      candidate_datasets: [
        {
          dataset_id: 12,
          dataset_name: '工作日志',
          reason: '能回答工作日志类问题',
          schema: { tables: ['internal'] },
        },
      ],
    });

    expect(confirmation.candidates[0]).toEqual({
      candidate_id: 12,
      dataset_id: 12,
      dataset_name: '工作日志',
      reason: '能回答工作日志类问题',
      confidence: null,
      checkpoint_ref: 'checkpoint://task-1/dataset',
    });
    expect(JSON.stringify(confirmation)).not.toContain('internal');
  });

  it('builds task timeline and artifact card refs from final payload', () => {
    const finalPayload = {
      answer: '查询完成',
      artifact_card: {
        title: 'BI 查询结果',
        summary: '2 行结果',
        refs: [{ ref: 'artifact:result:1' }],
      },
      primary_ref: { ref: 'artifact:result:1' },
      related_refs: [{ ref: 'artifact:trace:1', kind: 'trace' }],
    };

    expect(extractCandidateDatasets({ candidate_datasets: [] })).toEqual([]);
    expect(extractArtifactCard(finalPayload)).toMatchObject({
      title: 'BI 查询结果',
      summary_for_chat: '2 行结果',
      primary_ref: { ref: 'artifact:result:1' },
    });

    const timeline = buildTaskTimeline({
      eventEnvelopes: [
        { eventType: 'route.started' },
        { eventType: 'dataset.query.completed' },
        { eventType: 'answer.completed' },
      ],
      finalPayload,
      stepTrace: [{ node: 'query_plan' }, { node: 'sql_execute' }],
    });

    expect(timeline.map((item) => item.label)).toEqual([
      '任务理解',
      '数据集匹配',
      '用户确认',
      'BI 执行',
      '结果产物',
      '下一步动作',
    ]);
    expect(timeline.find((item) => item.id === 'execute_bi').status).toBe('done');
  });
});

describe('main chain acceptance metadata adapter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('maps final SSE observability and artifact refs into page metadata', async () => {
    streamChatEvents.mockReturnValue((async function* events() {
      yield {
        type: 'step',
        node: 'query_plan',
        status: 'done',
        query_plan: { query_type: 'metric_query', execution_strategy: 'query_graph' },
      };
      yield {
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
      };
    })());

    const adapter = makeChatAdapter({ datasetIdRef: { current: 3 } });
    const chunks = await collectRun(adapter, {
      messages: [{ role: 'user', content: [{ type: 'text', text: '最近30日GMV趋势如何' }] }],
      abortSignal: { aborted: false },
      unstable_threadId: 'local-thread',
    });

    const final = chunks.at(-1);
    expect(final.status).toEqual({ type: 'complete', reason: 'stop' });
    expect(final.metadata.custom.resultRef).toBe('artifact:result-1');
    expect(final.metadata.custom.reportRef).toBe('artifact:report-1');
    expect(final.metadata.custom.langfuseTraceId).toBe('trace-1');
    expect(final.metadata.custom.observability).toEqual({ trace_id: 'trace-1', session_id: 'session-1' });
    expect(final.metadata.custom.stepTrace).toHaveLength(1);
    expect(final.metadata.custom.sqlResult).toBeNull();
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
    expect(custom.artifactCard).toBeNull();
    expect(custom.langfuseTraceId).toBe('trace-old');
  });
});
