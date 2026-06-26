import { describe, expect, it } from 'vitest';

import {
  buildCandidateConfirmation,
  buildTaskTimeline,
  extractArtifactCard,
  extractCandidateDatasets,
  normalizeEventEnvelope,
} from './chat-adapter';

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
